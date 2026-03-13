"""경쟁사 블로그 상위 노출글 제목 수집 — 네이버 블로그 검색 API"""
import os
import requests

QUERIES = ["상표 출원 방법", "상표 등록 비용", "상표 검색 방법", "상표권 침해 사례"]


class CompetitorCollector:
    BASE = "https://openapi.naver.com/v1/search/blog.json"

    def __init__(self):
        self.headers = {
            "X-Naver-Client-Id":     os.environ.get("NAVER_CLIENT_ID", ""),
            "X-Naver-Client-Secret": os.environ.get("NAVER_CLIENT_SECRET", ""),
        }

    def collect(self) -> dict:
        titles = []
        for query in QUERIES:
            try:
                r = requests.get(
                    self.BASE,
                    headers=self.headers,
                    params={"query": query, "display": 5, "sort": "sim"},
                    timeout=8,
                )
                r.raise_for_status()
                for item in r.json().get("items", []):
                    title = self._clean(item.get("title", ""))
                    if title:
                        titles.append({"query": query, "title": title})
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    raise PermissionError(
                        "네이버 검색 API 권한 없음. "
                        "https://developers.naver.com/apps 에서 앱 선택 → API 설정 → '검색' 추가"
                    )
                print(f"  경쟁사 수집 경고 ({query}): {e}")
            except Exception as e:
                print(f"  경쟁사 수집 경고 ({query}): {e}")
        return {"sample_titles": titles}

    @staticmethod
    def _clean(text: str) -> str:
        import re
        return re.sub(r"<[^>]+>", "", text).strip()