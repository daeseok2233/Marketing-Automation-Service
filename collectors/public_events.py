"""공공데이터포털 — 지역 축제/행사/공모전 수집.

한국관광공사 국문 관광정보 서비스 API 활용.
https://www.data.go.kr
"""
import os
import requests
from datetime import datetime
from collectors import save_csv


class PublicEventsCollector:
    BASE_URL = "http://apis.data.go.kr/B551011/KorService1"

    def __init__(self):
        self.api_key = os.environ.get("PUBLIC_DATA_API_KEY", "")

    def collect(self) -> dict:
        if not self.api_key:
            print("  [공공데이터] PUBLIC_DATA_API_KEY 미설정")
            return {"events": []}

        events = []

        # 1) 행사/축제 정보 (오늘 이후)
        festival_events = self._fetch_festivals()
        events.extend(festival_events)

        # 2) 키워드 검색 — 창업지원, 공모전
        for keyword in ["창업지원", "공모전", "지식재산", "상표"]:
            search_events = self._search_keyword(keyword)
            events.extend(search_events)

        # 중복 제거
        seen = set()
        unique = []
        for e in events:
            key = e.get("title", "")
            if key not in seen:
                seen.add(key)
                unique.append(e)

        # CSV 저장
        if unique:
            csv_path = save_csv("public_events", unique)
            print(f"  [공공데이터] {len(unique)}건 행사 수집, CSV 저장: {csv_path}")

        return {"events": unique}

    def _fetch_festivals(self) -> list[dict]:
        """행사/축제 정보 조회 (오늘 이후)."""
        today = datetime.now().strftime("%Y%m%d")
        try:
            r = requests.get(
                f"{self.BASE_URL}/searchFestival1",
                params={
                    "serviceKey": self.api_key,
                    "numOfRows": 30,
                    "pageNo": 1,
                    "MobileOS": "ETC",
                    "MobileApp": "BlogPipeline",
                    "_type": "json",
                    "eventStartDate": today,
                },
                timeout=10,
            )
            if r.status_code != 200:
                print(f"  [공공데이터] 행사 조회 실패: {r.status_code}")
                return []

            data = r.json()
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if isinstance(items, dict):
                items = [items]

            results = []
            for item in items:
                results.append({
                    "title": item.get("title", ""),
                    "addr": item.get("addr1", ""),
                    "start_date": item.get("eventstartdate", ""),
                    "end_date": item.get("eventenddate", ""),
                    "tel": item.get("tel", ""),
                    "image": item.get("firstimage", ""),
                    "type": "축제/행사",
                })
            return results

        except Exception as e:
            print(f"  [공공데이터] 행사 조회 오류: {e}")
            return []

    def _search_keyword(self, keyword: str) -> list[dict]:
        """키워드 검색으로 관광/행사 정보 조회."""
        try:
            r = requests.get(
                f"{self.BASE_URL}/searchKeyword1",
                params={
                    "serviceKey": self.api_key,
                    "numOfRows": 10,
                    "pageNo": 1,
                    "MobileOS": "ETC",
                    "MobileApp": "BlogPipeline",
                    "_type": "json",
                    "keyword": keyword,
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
                results.append({
                    "title": item.get("title", ""),
                    "addr": item.get("addr1", ""),
                    "start_date": "",
                    "end_date": "",
                    "tel": item.get("tel", ""),
                    "image": item.get("firstimage", ""),
                    "type": f"검색:{keyword}",
                })
            return results

        except Exception:
            return []
