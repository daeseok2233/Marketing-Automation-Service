"""
파이프라인 — 이미지 생성 + 피그마 플러그인용 로컬 HTTP 서버(포트 8765)
1단계: 헤드라인 → 시각 장면 변환 (Claude Haiku)
2단계: 페르소나 → 스타일/색감 변환 (Claude Haiku)
3단계: Imagen 3 Fast로 배경 이미지 생성
4단계: 로컬 서버로 피그마 플러그인에 데이터 제공
"""

import base64
import json
import os
import re
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import anthropic
import gspread
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
import yaml
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

BASE_DIR = Path(__file__).parent
CONFIG = yaml.safe_load((BASE_DIR / "config.yaml").read_text(encoding="utf-8"))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheet():
    creds = Credentials.from_service_account_file(
        BASE_DIR / CONFIG["google_sheet"]["creds_file"], scopes=SCOPES
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_url(CONFIG["google_sheet"]["sheet_url"])
    return sh.worksheet(CONFIG["google_sheet"]["worksheet_name"])


def load_prompt(filename: str) -> str:
    return (BASE_DIR / "prompts" / filename).read_text(encoding="utf-8")


claude_client = anthropic.Anthropic()

# ── Vertex AI (Imagen) 초기화 ──────────────────────────────────
_creds_path = str(BASE_DIR / CONFIG["google_sheet"]["creds_file"])
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _creds_path
vertexai.init(project=CONFIG.get("gcp_project_id", "cardnews-agent-492005"), location="us-central1")


def call_claude_haiku(prompt: str) -> str:
    resp = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


# ── 이미지 프롬프트 생성 ────────────────────────────────────────
def generate_scene_description(card_type: str, card_text: str) -> str:
    """카드 텍스트 → 영어 시각 장면 묘사"""
    prompt = load_prompt("generate_image_scene.txt").format(
        card_type=card_type,
        card_text=card_text,
    )
    return call_claude_haiku(prompt)


def generate_style_description(persona: str, desire: str, angle: str) -> str:
    """페르소나 → 스타일/색감 묘사"""
    prompt = load_prompt("generate_image_style.txt").format(
        persona=persona, desire=desire, angle_name=angle
    )
    return call_claude_haiku(prompt)


# ── Imagen 3 이미지 생성 ───────────────────────────────────────
_imagen_model = ImageGenerationModel.from_pretrained("imagen-3.0-fast-generate-001")


def generate_background_image(scene: str, style: str) -> str:
    """Imagen 3 Fast로 배경 이미지 생성, base64 반환"""
    full_prompt = (
        f"{scene}. {style}. "
        "No text, no letters, no words in the image. "
        "Clean background suitable for overlaying text. "
        "Aspect ratio 1:1, high quality, modern design."
    )
    print(f"    Imagen 프롬프트: {full_prompt[:100]}...")

    response = _imagen_model.generate_images(
        prompt=full_prompt,
        number_of_images=1,
        aspect_ratio="1:1",
    )

    img_bytes = response.images[0]._image_bytes
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    print(f"    이미지 생성 완료 ({len(img_bytes)} bytes)")
    return b64


# ── 승인된 행 데이터 + 이미지 준비 ──────────────────────────────
def prepare_figma_data() -> list[dict]:
    """'본문 승인' 상태인 행들의 데이터와 배경 이미지를 준비"""
    ws = get_sheet()
    all_rows = ws.get_all_records()
    sets = []

    for i, row in enumerate(all_rows):
        row_idx = i + 2
        if row.get("본문 상태") != "본문 승인":
            continue
        png_folder = row.get("PNG 폴더", "")
        if png_folder and png_folder != "":
            continue  # 이미 처리됨

        # 중복 방지: 처리 시작 표시
        ws.update_cell(row_idx, 22, "이미지 생성 중")  # V: PNG 폴더

        headline = row.get("Card01 헤드라인", "")
        persona = row.get("페르소나", "")
        desire = row.get("욕구", "")
        angle = row.get("앵글", "")

        card02_title = row.get("Card02 섹션타이틀", "")
        card02_text = row.get("Card02 인풋텍스트", "")
        card03_title = row.get("Card03 섹션타이틀", "")
        card03_text = row.get("Card03 인풋텍스트", "")
        card04_title = row.get("Card04 섹션타이틀", "")
        card04_text = row.get("Card04 인풋텍스트", "")

        print(f"\n[행 {row_idx}] 이미지 생성 — 앵글: {angle}")

        # 스타일 묘사 (전체 공통)
        style = generate_style_description(persona, desire, angle)
        print(f"    스타일: {style[:80]}...")

        # 카드별 장면 묘사 + 이미지 생성
        card_texts = {
            "card01": f"헤드라인:\n{headline}",
            "card02": f"섹션타이틀: {card02_title}\n내용: {card02_text}",
            "card03": f"섹션타이틀: {card03_title}\n내용: {card03_text}",
            "card04": f"섹션타이틀: {card04_title}\n내용: {card04_text}",
        }

        background_images = {}
        for card_key, text in card_texts.items():
            print(f"    [{card_key}] 장면 묘사 생성 중...")
            scene = generate_scene_description(card_key, text)
            print(f"    [{card_key}] 장면: {scene[:60]}...")
            print(f"    [{card_key}] Imagen 이미지 생성 중...")
            background_images[card_key] = generate_background_image(scene, style)

        # 카드 데이터 구성
        card_set = {
            "row_index": row_idx,
            "angle": angle,
            "card01": {
                "headline": headline,
                "chip1": row.get("Card01 칩1", ""),
                "chip2": row.get("Card01 칩2", ""),
            },
            "card02": {
                "section_title": card02_title,
                "input_text": card02_text,
            },
            "card03": {
                "section_title": card03_title,
                "input_text": card03_text,
            },
            "card04": {
                "section_title": card04_title,
                "input_text": card04_text,
            },
            "card05_cta": row.get("Card05 CTA 유도문구", ""),
            "background_images": background_images,
        }
        sets.append(card_set)

    return sets


# ── HTTP 서버 (피그마 플러그인용) ────────────────────────────────
class FigmaHandler(BaseHTTPRequestHandler):
    card_sets = []

    def do_GET(self):
        if self.path == "/api/cards":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            # 이미지 데이터가 크므로 세트별로 나눠서 전송 가능
            payload = json.dumps({"sets": self.card_sets}, ensure_ascii=False)
            self.wfile.write(payload.encode("utf-8"))
        elif self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "sets_count": len(self.card_sets)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/complete":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
            data = json.loads(body) if body else {}
            row_index = data.get("row_index")

            if row_index:
                try:
                    ws = get_sheet()
                    ws.update_cell(row_index, 22, "Figma 생성 완료")  # V: PNG 폴더
                    print(f"  행 {row_index} → Figma 생성 완료")
                except Exception as e:
                    print(f"  시트 업데이트 실패: {e}")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass  # 로그 억제


def serve(card_sets: list[dict] = None):
    """로컬 서버 시작"""
    if card_sets is None:
        print("데이터 준비 중...")
        card_sets = prepare_figma_data()

    if not card_sets:
        print("처리할 승인된 본문이 없습니다.")
        return

    FigmaHandler.card_sets = card_sets
    port = CONFIG["figma_server_port"]
    server = HTTPServer(("localhost", port), FigmaHandler)
    print(f"\nFigma 플러그인 서버 시작 — http://localhost:{port}")
    print(f"  {len(card_sets)}개 세트 준비 완료")
    print(f"  피그마에서 플러그인을 실행하세요.")
    print(f"  종료: Ctrl+C\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료")
        server.server_close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        serve()
    else:
        print("사용법: python pipeline.py serve")
