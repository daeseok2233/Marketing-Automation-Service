"""
본문 에이전트 — 승인된 썸네일의 본문 3장(Card02~04) + CTA(Card05) 생성
톤 일관성 검증 루프 포함
"""

import json
import re
from pathlib import Path

import anthropic
import gspread
import openai
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


# ── LLM API 호출 (config 기반 provider 전환) ───────────────────
TEXT_MODEL_CFG = CONFIG["text_model"]
_provider = TEXT_MODEL_CFG["provider"]
_model = TEXT_MODEL_CFG["model"]

if _provider == "openai":
    _openai_client = openai.OpenAI()
elif _provider == "anthropic":
    _anthropic_client = anthropic.Anthropic()


def call_llm(prompt: str) -> str:
    if _provider == "openai":
        resp = _openai_client.chat.completions.create(
            model=_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    else:
        resp = _anthropic_client.messages.create(
            model=_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()


def parse_json(text: str) -> dict:
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    return json.loads(text)


# ── 시트에서 승인된 행 읽기 ──────────────────────────────────────
def get_approved_thumbnail_rows() -> list[dict]:
    """'썸네일 승인' 상태인 행들을 읽어옴"""
    ws = get_sheet()
    all_rows = ws.get_all_records()
    approved = []
    for i, row in enumerate(all_rows):
        if row.get("썸네일 상태") == "썸네일 승인" and row.get("본문 상태") == "":
            approved.append({"row_index": i + 2, "data": row})  # +2: 헤더 + 0-index
    return approved


# ── 본문 규칙 검증 ──────────────────────────────────────────────
def validate_body(data: dict) -> tuple[bool, str]:
    issues = []
    for card_key in ["card02", "card03", "card04"]:
        card = data.get(card_key, {})
        title = card.get("section_title", "")
        text = card.get("input_text", "")
        if len(title) > 15:
            issues.append(f"{card_key} 섹션타이틀 {len(title)}자 (15자 이내)")
        if len(text) > 80:
            issues.append(f"{card_key} 인풋텍스트 {len(text)}자 (80자 이내)")
    cta = data.get("card05_cta", "")
    if len(cta) > 20:
        issues.append(f"CTA {len(cta)}자 (20자 이내)")
    if issues:
        return False, " / ".join(issues)
    return True, ""


# ── 톤 일관성 평가 (Claude) ─────────────────────────────────────
def evaluate_body_tone(headline: str, data: dict) -> dict:
    lines = headline.split("\n")
    line1 = lines[0] if len(lines) > 0 else ""
    line2 = lines[1] if len(lines) > 1 else ""
    line3 = lines[2] if len(lines) > 2 else ""

    prompt_template = load_prompt("evaluate_body.txt")
    prompt = prompt_template.format(
        headline_line1=line1,
        headline_line2=line2,
        headline_line3=line3,
        card02_title=data["card02"]["section_title"],
        card02_text=data["card02"]["input_text"],
        card03_title=data["card03"]["section_title"],
        card03_text=data["card03"]["input_text"],
        card04_title=data["card04"]["section_title"],
        card04_text=data["card04"]["input_text"],
        card05_cta=data["card05_cta"],
    )
    result = call_llm(prompt)
    return parse_json(result)


# ── 단일 행 본문 생성 (자기 검증 루프) ──────────────────────────
def generate_body_for_row(row_data: dict) -> dict:
    headline = row_data.get("Card01 헤드라인", "")
    lines = headline.split("\n")
    line1 = lines[0] if len(lines) > 0 else ""
    line2 = lines[1] if len(lines) > 1 else ""
    line3 = lines[2] if len(lines) > 2 else ""

    prompt_template = load_prompt("generate_body.txt")
    max_retries = CONFIG["max_retries"]
    threshold = CONFIG["quality_threshold"]

    prompt = prompt_template.format(
        persona=row_data.get("페르소나", ""),
        desire=row_data.get("욕구", ""),
        awareness=row_data.get("인지단계", ""),
        angle_name=row_data.get("앵글", ""),
        service_name=CONFIG["service_name"],
        service_desc=CONFIG["service_desc"],
        headline_line1=line1,
        headline_line2=line2,
        headline_line3=line3,
    )

    for attempt in range(1, max_retries + 1):
        print(f"  본문 생성 시도 {attempt}/{max_retries}")
        raw = call_llm(prompt)
        try:
            data = parse_json(raw)
        except json.JSONDecodeError:
            print(f"    JSON 파싱 실패, 재시도...")
            continue

        # 규칙 검증
        ok, feedback = validate_body(data)
        if not ok:
            print(f"    규칙 검증 실패: {feedback}")
            prompt += f"\n\n피드백: {feedback}\n글자 수 규칙을 지켜서 다시 작성하세요."
            continue
        print(f"    규칙 검증 통과")

        # 톤 일관성 평가
        print(f"    톤 일관성 평가 중...")
        evaluation = evaluate_body_tone(headline, data)
        total = evaluation.get("total", 0)
        print(f"    평가 점수: {total}/10 — {evaluation.get('feedback', '')}")

        if total >= threshold:
            print(f"    {total}점 >= {threshold}점 — 통과!")
            return data

        if evaluation.get("needs_rewrite"):
            prompt += f"\n\n톤 평가 피드백: {evaluation.get('feedback', '')}\n썸네일과 톤을 맞춰서 다시 작성하세요."
        else:
            return data

    print(f"  최대 재시도 도달, 마지막 결과 사용")
    return data


# ── 시트에 본문 저장 ─────────────────────────────────────────────
def save_body_to_sheet(row_index: int, body: dict):
    ws = get_sheet()
    # L열(12) ~ R열(18) 에 본문 데이터 저장
    ws.update_cell(row_index, 12, body["card02"]["section_title"])  # L: Card02 섹션타이틀
    ws.update_cell(row_index, 13, body["card02"]["input_text"])     # M: Card02 인풋텍스트
    ws.update_cell(row_index, 14, body["card03"]["section_title"])  # N: Card03 섹션타이틀
    ws.update_cell(row_index, 15, body["card03"]["input_text"])     # O: Card03 인풋텍스트
    ws.update_cell(row_index, 16, body["card04"]["section_title"])  # P: Card04 섹션타이틀
    ws.update_cell(row_index, 17, body["card04"]["input_text"])     # Q: Card04 인풋텍스트
    ws.update_cell(row_index, 18, body["card05_cta"])               # R: Card05 CTA
    ws.update_cell(row_index, 21, "본문 대기")                       # U: 본문 상태
    print(f"    행 {row_index} 본문 저장 완료")


# ── 메인 실행 ───────────────────────────────────────────────────
def run() -> list[int]:
    print("=" * 60)
    print("본문 에이전트 시작")
    print("=" * 60)

    approved = get_approved_thumbnail_rows()
    if not approved:
        print("승인된 썸네일이 없습니다. 시트에서 '썸네일 승인'으로 변경해주세요.")
        return []

    print(f"승인된 썸네일 {len(approved)}개 발견\n")
    processed_rows = []

    for item in approved:
        row_idx = item["row_index"]
        row_data = item["data"]
        angle = row_data.get("앵글", "")
        print(f"[행 {row_idx}] 앵글: {angle}")
        print(f"  썸네일: {row_data.get('Card01 헤드라인', '')[:30]}...")

        body = generate_body_for_row(row_data)
        save_body_to_sheet(row_idx, body)
        processed_rows.append(row_idx)

        print(f"  Card02: {body['card02']['section_title']}")
        print(f"  Card03: {body['card03']['section_title']}")
        print(f"  Card04: {body['card04']['section_title']}")
        print(f"  CTA: {body['card05_cta']}\n")

    print(f"\n본문 에이전트 완료! ({len(processed_rows)}행 처리)")
    return processed_rows


if __name__ == "__main__":
    run()
