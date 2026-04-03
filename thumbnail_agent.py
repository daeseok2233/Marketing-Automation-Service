"""
썸네일 에이전트 — P.D.A. 프레임워크 기반 5가지 마케팅 앵글 헤드라인 생성
자기 검증 루프: 규칙 검증(Python) → 자기 평가(Claude) → 재작성
"""

import json
import os
import re
from datetime import datetime
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

# ── Google Sheets 연결 ──────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheet():
    creds = Credentials.from_service_account_file(
        BASE_DIR / CONFIG["google_sheet"]["creds_file"], scopes=SCOPES
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_url(CONFIG["google_sheet"]["sheet_url"])
    return sh.worksheet(CONFIG["google_sheet"]["worksheet_name"])


# ── 프롬프트 로드 ───────────────────────────────────────────────
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
    """LLM 응답에서 JSON 추출"""
    # ```json ... ``` 블록이 있으면 그 안의 내용만 추출
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    return json.loads(text)


# ── 규칙 검증 (Python) ──────────────────────────────────────────
def validate_headline(data: dict) -> tuple[bool, str]:
    """3줄, 각 줄 7~12자 규칙 검증. (ok, feedback) 반환"""
    lines = [data.get("headline_line1", ""), data.get("headline_line2", ""), data.get("headline_line3", "")]
    issues = []
    for i, line in enumerate(lines, 1):
        length = len(line)
        if length < CONFIG["thumbnail_char_min"] or length > CONFIG["thumbnail_char_max"]:
            issues.append(f"{i}줄 '{line}'은 {length}자 (규칙: {CONFIG['thumbnail_char_min']}~{CONFIG['thumbnail_char_max']}자)")
    if not data.get("chip1") or not data.get("chip2"):
        issues.append("칩 태그가 비어있습니다.")
    if issues:
        return False, " / ".join(issues)
    return True, ""


# ── 자기 평가 (Claude) ──────────────────────────────────────────
def self_evaluate(data: dict, persona: str, desire: str, awareness: str, angle: dict) -> dict:
    prompt_template = load_prompt("evaluate_thumbnail.txt")
    prompt = prompt_template.format(
        persona=persona,
        desire=desire,
        awareness=awareness,
        angle_name=angle["name"],
        headline_line1=data["headline_line1"],
        headline_line2=data["headline_line2"],
        headline_line3=data["headline_line3"],
        chip1=data["chip1"],
        chip2=data["chip2"],
    )
    result = call_llm(prompt)
    return parse_json(result)


# ── 단일 앵글 헤드라인 생성 (자기 검증 루프 포함) ─────────────────
def generate_for_angle(
    persona: str, desire: str, awareness: str, angle: dict
) -> dict:
    prompt_template = load_prompt("generate_thumbnails.txt")
    max_retries = CONFIG["max_retries"]
    threshold = CONFIG["quality_threshold"]
    total = 0
    data = {}

    prompt = prompt_template.format(
        persona=persona,
        desire=desire,
        awareness=awareness,
        service_name=CONFIG["service_name"],
        service_desc=CONFIG["service_desc"],
        brand_label=CONFIG["brand_label"],
        angle_name=angle["name"],
        angle_english=angle["english"],
        angle_description=angle["description"],
    )

    for attempt in range(1, max_retries + 1):
        print(f"  [{angle['name']}] 생성 시도 {attempt}/{max_retries}")
        raw = call_llm(prompt)
        try:
            data = parse_json(raw)
        except json.JSONDecodeError:
            print(f"    JSON 파싱 실패, 재시도...")
            continue

        # 1단계: 규칙 검증 (Python)
        ok, feedback = validate_headline(data)
        if not ok:
            print(f"    규칙 검증 실패: {feedback}")
            prompt += f"\n\n이전 시도 피드백: {feedback}\n위 피드백을 반영해 다시 작성하세요."
            continue
        print(f"    규칙 검증 통과")

        # 2단계: 자기 평가 (Claude)
        print(f"    Claude 자기 평가 중...")
        evaluation = self_evaluate(data, persona, desire, awareness, angle)
        total = evaluation.get("total", 0)
        print(f"    평가 점수: {total}/10 — {evaluation.get('feedback', '')}")

        if total >= threshold:
            print(f"    {total}점 >= {threshold}점 — 통과!")
            data["eval_score"] = total
            return data

        # 7점 미만: Claude가 제안한 개선본 사용
        improved = evaluation.get("improved_headline")
        if improved and improved.get("headline_line1"):
            print(f"    {total}점 < {threshold}점 — Claude 개선본으로 교체")
            data.update(improved)
            ok2, fb2 = validate_headline(data)
            if ok2:
                data["eval_score"] = total
                return data
            print(f"    개선본도 규칙 위반: {fb2}, 재생성...")
        else:
            prompt += f"\n\n자기평가 피드백: {evaluation.get('feedback', '')}\n이 피드백을 반영해 더 좋은 카피를 작성하세요."

    print(f"  [{angle['name']}] 최대 재시도 도달, 마지막 결과 사용")
    data["eval_score"] = total
    return data


# ── 5개 앵글 전체 생성 ──────────────────────────────────────────
def generate_all_thumbnails(persona: str, desire: str, awareness: str) -> list[dict]:
    print("=" * 60)
    print("썸네일 에이전트 시작")
    print(f"  페르소나: {persona}")
    print(f"  욕구: {desire}")
    print(f"  인지단계: {awareness}")
    print("=" * 60)

    results = []
    for angle in CONFIG["angles"]:
        data = generate_for_angle(persona, desire, awareness, angle)
        data["angle"] = angle["name"]
        results.append(data)
        headline = f"{data['headline_line1']}\n{data['headline_line2']}\n{data['headline_line3']}"
        print(f"\n  [{angle['name']}] 최종 헤드라인:\n{headline}")
        print(f"  칩: {data['chip1']} {data['chip2']} (점수: {data.get('eval_score', '?')}/10)\n")

    return results


# ── 구글 시트에 저장 ─────────────────────────────────────────────
def save_to_sheet(
    results: list[dict], persona: str, desire: str, awareness: str
) -> list[int]:
    """시트에 5행 저장하고, 저장된 행 번호 리스트 반환"""
    ws = get_sheet()
    today = datetime.now().strftime("%Y-%m-%d")
    folder = datetime.now().strftime("%Y%m%d_%H%M")
    row_numbers = []

    for r in results:
        funnel = "TOFU"  # Top of Funnel (기본값)
        row = [
            today,                          # A: 날짜
            folder,                         # B: 폴더명
            persona,                        # C: 페르소나
            desire,                         # D: 욕구
            awareness,                      # E: 인지단계
            funnel,                         # F: 펀넬
            r["angle"],                     # G: 앵글
            f"{r['headline_line1']}\n{r['headline_line2']}\n{r['headline_line3']}",  # H: Card01 헤드라인
            r.get("chip1", ""),             # I: Card01 칩1
            r.get("chip2", ""),             # J: Card01 칩2
            "썸네일 대기",                   # K: 썸네일 상태
            "", "", "", "", "", "",         # L~Q: Card02~04 (본문 에이전트가 채움)
            "",                             # R: Card05 CTA
            r.get("concept", ""),           # S: 컨셉
            r.get("expected_reaction", ""), # T: 기대반응
            "",                             # U: 본문 상태
            "",                             # V: PNG 폴더
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")
        row_numbers.append(len(ws.get_all_values()))

    print(f"\n시트에 {len(results)}행 저장 완료 (행 {row_numbers})")
    return row_numbers


# ── 메인 실행 ───────────────────────────────────────────────────
def run(persona: str, desire: str, awareness: str = "problem-aware") -> list[int]:
    results = generate_all_thumbnails(persona, desire, awareness)
    row_numbers = save_to_sheet(results, persona, desire, awareness)
    print("\n썸네일 에이전트 완료!")
    return row_numbers


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="썸네일 에이전트")
    parser.add_argument("--persona", required=True, help="타겟 페르소나")
    parser.add_argument("--desire", required=True, help="페르소나의 욕구")
    parser.add_argument("--awareness", default="problem-aware",
                        choices=["unaware", "problem-aware", "solution-aware", "product-aware"])
    args = parser.parse_args()
    run(args.persona, args.desire, args.awareness)
