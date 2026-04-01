"""2단계: 레퍼런스 생성 — 선정된 주제 + 수집 데이터 → 관련 데이터 추출."""

import csv
import json
from pathlib import Path
from datetime import datetime


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def build_reference(topic_data: dict) -> dict:
    """주제와 관련된 수집 데이터를 추출하여 레퍼런스를 구성한다.

    Args:
        topic_data: topic_selector에서 반환된 dict

    Returns:
        {
            "topic": "...",
            "related_news": [...],
            "related_competitors": [...],
            "trending_keywords": [...],
            "search_trends": [...],
        }
    """
    topic = topic_data.get("topic", "")
    keywords = topic_data.get("keywords", [])
    today = datetime.now().strftime("%Y%m%d")
    collected = Path("data/collected")

    # ── 관련 뉴스 추출 ──
    news = _read_csv(collected / f"{today}_naver_news.csv")
    related_news = []
    for row in news:
        title = row.get("title", "")
        desc = row.get("description", "")
        text = f"{title} {desc}"
        if any(kw in text for kw in keywords) or any(kw in text for kw in topic.split()):
            related_news.append({
                "title": title,
                "description": desc[:200],
                "source": row.get("source", ""),
                "link": row.get("link", ""),
            })
    related_news = related_news[:5]  # 최대 5건

    # ── 관련 경쟁사 블로그 추출 ──
    competitors = _read_csv(collected / f"{today}_competitor.csv")
    related_competitors = []
    for row in competitors:
        title = row.get("title", "")
        desc = row.get("description", "")
        text = f"{title} {desc}"
        if any(kw in text for kw in keywords) or any(kw in text for kw in topic.split()):
            related_competitors.append({
                "title": title,
                "description": desc[:200],
                "blogger": row.get("blogger", ""),
            })
    related_competitors = related_competitors[:5]

    # ── 트렌딩 키워드 ──
    trending = _read_csv(collected / f"{today}_google_trending.csv")
    trending_keywords = [
        {"keyword": r.get("keyword", ""), "traffic": r.get("traffic", "")}
        for r in trending[:10]
    ]

    # ── 검색 트렌드 (naver_datalab + google_trends) ──
    datalab = _read_csv(collected / f"{today}_naver_datalab.csv")
    search_trends = [
        {"keyword": r.get("keyword", ""), "growth": r.get("growth_rate", "")}
        for r in datalab
        if r.get("growth_rate", "0") != "0"
    ]

    # ── 자동완성 키워드 ──
    suggest = _read_csv(collected / f"{today}_naver_suggest.csv")
    suggest_keywords = [
        r.get("suggest", "")
        for r in suggest
        if any(kw in r.get("suggest", "") for kw in keywords)
    ][:10]

    reference = {
        "topic": topic,
        "keywords": keywords,
        "related_news": related_news,
        "related_competitors": related_competitors,
        "trending_keywords": trending_keywords,
        "search_trends": search_trends,
        "suggest_keywords": suggest_keywords,
    }

    # 중간결과 저장
    _save_intermediate("02_reference", reference)

    return reference


def _save_intermediate(step: str, data: dict):
    out_dir = Path("data/generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    path = out_dir / f"{today}_{step}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [저장] {path}")
