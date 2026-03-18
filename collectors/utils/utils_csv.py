# collectors 패키지
import csv
from datetime import datetime
from config import DOWNLOAD_DIR

def save_csv(collector_name: str, rows: list[dict], date_str: str | None = None):
    """수집 결과를 CSV로 저장하고 경로를 반환한다.

    Args:
        collector_name: 파일명에 쓸 수집기 이름 (예: "google_trends")
        rows: dict 리스트 — 각 dict가 CSV 한 행
        date_str: 날짜 문자열 (기본값: 오늘 YYYYMMDD)

    Returns:
        저장된 CSV 파일 경로
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    path = DOWNLOAD_DIR / f"{date_str}_{collector_name}.csv"

    if not rows:
        path.write_text("", encoding="utf-8")
        return path

    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return path
