"""지역 선정 로직 — 행사/트렌딩/랜덤 우선순위.

1순위: 공공데이터 행사가 있는 지역
2순위: 실시간 트렌딩/뉴스에서 추출한 핫한 지역
3순위: 중복 없이 랜덤 (전국 분산)
"""

import json
import random
import re
import requests
from pathlib import Path
from datetime import datetime


# ── 전국 지역 풀 (regions.json에서 로드) ──
def _load_region_pool() -> list[str]:
    """regions.json에서 전국 시/군/구 로드 → '서울 강남구' 형태 리스트."""
    regions_path = Path("data/service_data/regions.json")
    if not regions_path.exists():
        return ["서울 강남구", "부산 해운대구", "대전 유성구"]  # 최소 폴백
    data = json.loads(regions_path.read_text(encoding="utf-8"))
    pool = []
    # 시/도 이름 → 짧은 이름 매핑
    short = {
        "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
        "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
        "울산광역시": "울산", "세종특별자치시": "", "경기도": "",
        "강원도": "", "충청북도": "", "충청남도": "",
        "전라북도": "", "전라남도": "", "경상북도": "",
        "경상남도": "", "제주특별자치도": "",
    }
    for sido, districts in data.items():
        prefix = short.get(sido, "")
        for district in districts:
            if prefix:
                pool.append(f"{prefix} {district}")
            else:
                pool.append(district)
    return pool


REGION_POOL = _load_region_pool()


def _extract_regions_from_text(text: str) -> list[str]:
    """텍스트에서 지역명을 추출."""
    found = []
    for region in REGION_POOL:
        # "서울 강남구" → "강남", "강남구" 둘 다 매칭
        parts = region.split()
        for part in parts:
            if part in text:
                found.append(region)
                break
    return list(set(found))


def _get_event_regions() -> list[dict]:
    """공공데이터 행사 API에서 오늘~이번주 행사 지역 추출."""
    import os
    api_key = os.environ.get("PUBLIC_DATA_API_KEY", "")
    if not api_key:
        return []

    today = datetime.now().strftime("%Y%m%d")
    try:
        r = requests.get(
            "http://apis.data.go.kr/B551011/KorService1/searchFestival1",
            params={
                "serviceKey": api_key,
                "numOfRows": 20,
                "pageNo": 1,
                "MobileOS": "ETC",
                "MobileApp": "BlogPipeline",
                "_type": "json",
                "eventStartDate": today,
            },
            timeout=10,
        )
        if r.status_code != 200:
            return []

        data = r.json()
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]

        results = []
        for item in items:
            title = item.get("title", "")
            addr = item.get("addr1", "")
            regions = _extract_regions_from_text(f"{title} {addr}")
            for region in regions:
                results.append({
                    "region": region,
                    "event": title,
                    "source": "공공데이터_행사",
                })
        return results

    except Exception:
        return []


def _get_trending_regions() -> list[dict]:
    """구글 트렌딩 + 뉴스에서 지역 키워드 추출."""
    import xml.etree.ElementTree as ET

    results = []

    # 구글 트렌딩
    try:
        r = requests.get(
            "https://trends.google.com/trending/rss?geo=KR",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10,
        )
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                regions = _extract_regions_from_text(title)
                for region in regions:
                    results.append({
                        "region": region,
                        "event": f"트렌딩: {title}",
                        "source": "구글_트렌딩",
                    })
    except Exception:
        pass

    # 오늘 수집된 뉴스에서 지역 추출
    today = datetime.now().strftime("%Y%m%d")
    news_path = Path("data/collected") / f"{today}_naver_news.csv"
    if news_path.exists():
        import csv
        try:
            with open(news_path, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    title = row.get("title", "")
                    regions = _extract_regions_from_text(title)
                    for region in regions:
                        results.append({
                            "region": region,
                            "event": f"뉴스: {title[:30]}",
                            "source": "뉴스",
                        })
        except Exception:
            pass

    return results


def _get_used_regions(blog_id: str) -> set:
    """최근 3일 사용된 지역."""
    path = Path("data/schedule_state.json")
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get(blog_id, [])
    cutoff = datetime.now().timestamp() - 3 * 86400
    used = set()
    for u in entries:
        try:
            ts = datetime.strptime(u.get("date", "20200101"), "%Y%m%d").timestamp()
            if ts > cutoff:
                used.add(u.get("region", ""))
        except ValueError:
            continue
    return used


def select_regions(count: int, blog_id: str = "") -> list[dict]:
    """지역 선정 — 행사/트렌딩/랜덤 우선순위.

    Returns:
        [{"region": "대전 유성구", "event": "대전 창업 박람회", "source": "공공데이터_행사"}, ...]
    """
    used = _get_used_regions(blog_id)
    selected = []
    seen_regions = set()

    def _add(item):
        region = item["region"]
        if region not in seen_regions and region not in used:
            seen_regions.add(region)
            selected.append(item)

    # 1순위: 행사 지역
    event_regions = _get_event_regions()
    random.shuffle(event_regions)
    for item in event_regions:
        if len(selected) >= count:
            break
        _add(item)

    # 2순위: 트렌딩/뉴스 핫 지역
    trending_regions = _get_trending_regions()
    random.shuffle(trending_regions)
    for item in trending_regions:
        if len(selected) >= count:
            break
        _add(item)

    # 3순위: 랜덤 (전국 분산)
    pool = [r for r in REGION_POOL if r not in seen_regions and r not in used]
    random.shuffle(pool)
    for region in pool:
        if len(selected) >= count:
            break
        _add({"region": region, "event": "", "source": "랜덤"})

    print(f"  [지역선정] {len(selected)}개 (행사:{len([s for s in selected if s['source']=='공공데이터_행사'])} / 트렌딩:{len([s for s in selected if s['source'] in ('구글_트렌딩','뉴스')])} / 랜덤:{len([s for s in selected if s['source']=='랜덤'])})")

    return selected[:count]
