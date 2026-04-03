"""
오케스트레이터 — 3개 에이전트를 하나의 파이프라인으로 연결
단계: 썸네일 생성 → (승인) → 본문 생성 → (승인) → 이미지 생성 + 피그마 서버
"""

import argparse
import sys
import time
from pathlib import Path

import gspread
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


def auto_approve_thumbnails(row_numbers: list[int]):
    """--auto 모드: 모든 썸네일을 자동 승인"""
    ws = get_sheet()
    for row in row_numbers:
        ws.update_cell(row, 11, "썸네일 승인")  # K열
    print(f"[자동 승인] 썸네일 {len(row_numbers)}행 승인 완료")


def auto_approve_body(row_numbers: list[int]):
    """--auto 모드: 모든 본문을 자동 승인"""
    ws = get_sheet()
    for row in row_numbers:
        ws.update_cell(row, 21, "본문 승인")  # U열
    print(f"[자동 승인] 본문 {len(row_numbers)}행 승인 완료")


def wait_for_approval(stage: str):
    """수동 모드: 사용자가 시트에서 승인할 때까지 대기"""
    print(f"\n{'='*60}")
    print(f"  구글 시트에서 '{stage}'으로 변경한 후")
    print(f"  여기서 Enter를 눌러주세요.")
    print(f"{'='*60}")
    input("  >> Enter를 눌러 계속...")
    print()


def run_all(persona: str, desire: str, awareness: str, auto: bool):
    """전체 파이프라인 실행"""
    print("\n" + "=" * 60)
    print("  카드뉴스 자동화 에이전트 파이프라인")
    print("=" * 60)
    print(f"  페르소나: {persona}")
    print(f"  욕구: {desire}")
    print(f"  인지단계: {awareness}")
    print(f"  모드: {'자동' if auto else '수동 (시트 승인 필요)'}")
    print("=" * 60 + "\n")

    # ── 1단계: 썸네일 에이전트 ───────────────────────────────────
    print("=" * 60)
    print("  1단계: 썸네일 에이전트")
    print("=" * 60)
    from thumbnail_agent import run as run_thumbnail
    row_numbers = run_thumbnail(persona, desire, awareness)

    if not row_numbers:
        print("썸네일 생성 실패. 종료합니다.")
        return

    # ── 2단계: 썸네일 승인 ──────────────────────────────────────
    if auto:
        auto_approve_thumbnails(row_numbers)
    else:
        wait_for_approval("썸네일 승인")

    # ── 3단계: 본문 에이전트 ────────────────────────────────────
    print("\n" + "=" * 60)
    print("  3단계: 본문 에이전트")
    print("=" * 60)
    from body_agent import run as run_body
    body_rows = run_body()

    if not body_rows:
        print("본문 생성 실패 또는 승인된 썸네일 없음. 종료합니다.")
        return

    # ── 4단계: 본문 승인 ───────────────────────────────────────
    if auto:
        auto_approve_body(body_rows)
    else:
        wait_for_approval("본문 승인")

    # ── 5단계: 이미지 생성 + 피그마 서버 ────────────────────────
    print("\n" + "=" * 60)
    print("  5단계: 이미지 생성 + Figma 플러그인 서버")
    print("=" * 60)
    from pipeline import serve
    serve()


def run_thumbnail_only(persona: str, desire: str, awareness: str):
    from thumbnail_agent import run as run_thumbnail
    run_thumbnail(persona, desire, awareness)


def run_body_only():
    from body_agent import run as run_body
    run_body()


def run_figma_only():
    from pipeline import serve
    serve()


def main():
    parser = argparse.ArgumentParser(
        description="카드뉴스 자동화 에이전트 오케스트레이터"
    )
    subparsers = parser.add_subparsers(dest="command")

    # all: 전체 파이프라인
    all_parser = subparsers.add_parser("all", help="전체 파이프라인 실행")
    all_parser.add_argument("--persona", required=True, help="타겟 페르소나")
    all_parser.add_argument("--desire", required=True, help="페르소나의 욕구")
    all_parser.add_argument("--awareness", default="problem-aware",
                            choices=["unaware", "problem-aware", "solution-aware", "product-aware"])
    all_parser.add_argument("--auto", action="store_true", help="승인 단계 자동 건너뛰기")

    # thumbnail: 썸네일만
    thumb_parser = subparsers.add_parser("thumbnail", help="썸네일 에이전트만 실행")
    thumb_parser.add_argument("--persona", required=True)
    thumb_parser.add_argument("--desire", required=True)
    thumb_parser.add_argument("--awareness", default="problem-aware",
                              choices=["unaware", "problem-aware", "solution-aware", "product-aware"])

    # body: 본문만
    subparsers.add_parser("body", help="본문 에이전트만 실행")

    # figma: 피그마 서버만
    subparsers.add_parser("figma", help="피그마 서버만 실행")

    args = parser.parse_args()

    if args.command == "all":
        run_all(args.persona, args.desire, args.awareness, args.auto)
    elif args.command == "thumbnail":
        run_thumbnail_only(args.persona, args.desire, args.awareness)
    elif args.command == "body":
        run_body_only()
    elif args.command == "figma":
        run_figma_only()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
