# collectors 패키지
import csv
import os
from datetime import datetime
from pathlib import Path

COLLECTED_DIR = Path("data/collected")


def save_csv(collector_name: str, rows: list[dict], date_str: str | None = None) -> Path:
    """수집 결과를 CSV로 저장하고 경로를 반환한다.

    Args:
        collector_name: 파일명에 쓸 수집기 이름 (예: "google_trends")
        rows: dict 리스트 — 각 dict가 CSV 한 행
        date_str: 날짜 문자열 (기본값: 오늘 YYYYMMDD)

    Returns:
        저장된 CSV 파일 경로
    """
    COLLECTED_DIR.mkdir(parents=True, exist_ok=True)
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    path = COLLECTED_DIR / f"{date_str}_{collector_name}.csv"

    if not rows:
        path.write_text("", encoding="utf-8")
        return path

    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return path


def collect_all() -> dict:
    """모든 수집기를 순차 실행하고 결과를 반환한다."""
    from collectors.naver_suggest import NaverSuggestCollector
    from collectors.google_trends import GoogleTrendsCollector
    from collectors.google_trending import GoogleTrendingCollector
    from collectors.naver_datalab import NaverDataLabCollector
    from collectors.naver_news import NaverNewsCollector
    from collectors.competitor import CompetitorCollector
    from collectors.bigkinds import BigKindsCollector
    from collectors.kipris import KIPRISCollector

    collectors = {
        "suggest": NaverSuggestCollector(),
        "google_trends": GoogleTrendsCollector(),
        "google_trending": GoogleTrendingCollector(),
        "naver_datalab": NaverDataLabCollector(),
        "naver_news": NaverNewsCollector(),
        "competitor": CompetitorCollector(),
        "bigkinds": BigKindsCollector(),
        "kipris": KIPRISCollector(),
    }

    results = {}
    for name, col in collectors.items():
        print(f"\n===== {name} =====")
        try:
            result = col.collect()
            results[name] = result
            if isinstance(result, dict):
                for k, v in result.items():
                    if isinstance(v, list):
                        print(f"  {k}: {len(v)}건")
                    elif isinstance(v, dict):
                        print(f"  {k}: {len(v)}개 항목")
                    else:
                        print(f"  {k}: {v}")
            print("  [OK]")
        except Exception as e:
            print(f"  [FAIL] {e}")
            results[name] = {"error": str(e)}

    return results
