"""매일 뉴스 수집 — 핵심 키워드별 네이버 뉴스.

상표/특허/창업/중소기업/신제품 키워드로 최신 뉴스 수집.
매일 1회 실행, JSON 저장.
"""

import json
import os
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DEFAULT_KEYWORDS = [
    "상표", "특허", "창업", "중소기업", "신제품",
    "브랜드", "지식재산", "프랜차이즈", "상호명",
    "소상공인", "스타트업", "자영업",
    "상권", "폐업", "매출",
    "축제", "박람회", "공모전", "페스티벌", "지원사업",
]


def _parse_pub_date(pub_date_str: str) -> str:
    """네이버 API pubDate → YYYY-MM-DD 변환.
    예: 'Wed, 09 Apr 2026 10:30:00 +0900' → '2026-04-09'
    """
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(pub_date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def collect_news(keywords=None, count_per_keyword=20, yesterday_only=True) -> list[dict]:
    """키워드별 네이버 뉴스 검색.

    Args:
        keywords: 검색 키워드 리스트
        count_per_keyword: 키워드당 가져올 뉴스 수 (필터 전)
        yesterday_only: True면 어제 날짜 뉴스만 필터링

    Returns:
        [{"keyword": "상표", "title": "...", "description": "...", "link": "...", "date": "2026-04-08"}, ...]
    """
    if keywords is None:
        keywords = DEFAULT_KEYWORDS

    from datetime import timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    all_news = []
    seen = set()

    for keyword in keywords:
        fetched = 0
        filtered = 0
        try:
            r = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                params={"query": keyword, "display": count_per_keyword, "sort": "date"},
                headers=headers,
                timeout=5,
            )
            if r.status_code == 200:
                items = r.json().get("items", [])
                fetched = len(items)
                for item in items:
                    title = item["title"].replace("<b>", "").replace("</b>", "")
                    pub_date = _parse_pub_date(item.get("pubDate", ""))

                    # 어제 날짜 필터
                    if yesterday_only and pub_date != yesterday:
                        continue

                    if title not in seen:
                        seen.add(title)
                        all_news.append({
                            "keyword": keyword,
                            "title": title,
                            "description": item.get("description", "").replace("<b>", "").replace("</b>", "")[:200],
                            "link": item.get("link", ""),
                            "date": pub_date,
                            "source": "naver",
                        })
                        filtered += 1
                date_info = f"(어제: {filtered}건)" if yesterday_only else ""
                print(f"  [뉴스수집] '{keyword}' → {fetched}건 수집, {filtered}건 저장 {date_info}")
            else:
                print(f"  [뉴스수집] '{keyword}' → 실패 ({r.status_code})")
        except Exception as e:
            print(f"  [뉴스수집] '{keyword}' → 오류: {e}")

        import time as _time
        _time.sleep(0.3)  # API 할당량 초과 방지

    # 구글 뉴스 RSS 추가 수집
    for keyword in keywords:
        fetched = 0
        filtered = 0
        try:
            import xml.etree.ElementTree as ET
            r = requests.get(
                "https://news.google.com/rss/search",
                params={"q": keyword, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                items = root.findall(".//item")
                fetched = len(items)
                for item in items:
                    title = item.findtext("title", "").strip()
                    pub_date_raw = item.findtext("pubDate", "").strip()
                    pub_date = _parse_pub_date(pub_date_raw)
                    link = item.findtext("link", "").strip()

                    if yesterday_only and pub_date != yesterday:
                        continue

                    if title and title not in seen:
                        seen.add(title)
                        all_news.append({
                            "keyword": keyword,
                            "title": title,
                            "description": "",
                            "link": link,
                            "date": pub_date,
                            "source": "google",
                        })
                        filtered += 1
                if filtered > 0:
                    print(f"  [구글뉴스] '{keyword}' → {fetched}건 수집, {filtered}건 저장")
        except Exception:
            pass

    print(f"  [뉴스수집] 총 {len(all_news)}건 (어제 뉴스, 네이버+구글, 중복 제거)")
    return all_news


def collect_and_save(keywords=None, count_per_keyword=30) -> Path:
    """수집 + JSON 저장."""
    news = collect_news(keywords=keywords, count_per_keyword=count_per_keyword)

    out_dir = Path("data/collected")
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    out_path = out_dir / f"{today}_daily_news.json"

    out_path.write_text(
        json.dumps(news, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  [뉴스수집] 저장: {out_path} ({len(news)}건)")
    return out_path


if __name__ == "__main__":
    collect_and_save()
