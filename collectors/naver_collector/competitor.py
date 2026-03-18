"""경쟁사 블로그 상위 노출글 분석 — 네이버 블로그 검색 API

수집 항목:
  - 상위 노출 블로그 제목 + 본문 요약 (description)
"""
import os
import re
import requests
from collectors.utils import save_csv
from config import DOWNLOAD_DIR

# ── 쿼리 확장: 핵심 + 롱테일 + 업종별 + 질문형
QUERIES = [
    # 핵심 키워드
    "상표 출원 방법", "상표 등록 비용", "상표 검색 방법", "상표권 침해 사례",
    # 롱테일: 절차·비용·기간
    "상표 등록 절차", "상표 등록 기간", "상표 출원 서류", "상표 갱신 방법",
    "상표 이전 절차", "상표 취소심판",
    # 업종·상황별
    "프랜차이즈 상표 등록", "카페 상표 등록", "쇼핑몰 브랜드 등록",
    "셀프 상표 출원", "변리사 상표 비용",
    # 해외
    "해외 상표 등록 방법", "마드리드 의정서 상표",
    # 비교형 (compare 템플릿용)
    "상표 출원 셀프 vs 변리사", "상표 직접출원 대행 비교",
]


class CompetitorCollector:
    BLOG_API = "https://openapi.naver.com/v1/search/blog.json"

    def __init__(self):
        self.headers = {
            "X-Naver-Client-Id":     os.environ.get("NAVER_CLIENT_ID", ""),
            "X-Naver-Client-Secret": os.environ.get("NAVER_CLIENT_SECRET", ""),
        }

    def collect(self) -> dict:
        all_items = []

        for query in QUERIES:
            try:
                r = requests.get(
                    self.BLOG_API,
                    headers=self.headers,
                    params={"query": query, "display": 10, "sort": "sim"},
                    timeout=8,
                )
                r.raise_for_status()
                for item in r.json().get("items", []):
                    title = self._clean(item.get("title", ""))
                    desc  = self._clean(item.get("description", ""))
                    link  = item.get("link", "")
                    if not title:
                        continue

                    all_items.append({
                        "query": query,
                        "title": title,
                        "description": desc[:200],
                        "blogger": item.get("bloggername", ""),
                        "link": link,
                    })

            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    raise PermissionError(
                        "네이버 검색 API 권한 없음. "
                        "https://developers.naver.com/apps 에서 앱 선택 → API 설정 → '검색' 추가"
                    )
                print(f"  경쟁사 수집 경고 ({query}): {e}")
            except Exception as e:
                print(f"  경쟁사 수집 경고 ({query}): {e}")

        # CSV 저장: 블로그 목록
        csv_path = save_csv(DOWNLOAD_DIR,"competitor", all_items)
        print(f"  [Competitor] {len(all_items)}개 블로그 수집, CSV 저장: {csv_path}")

        return {"sample_titles": all_items}

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"<[^>]+>", "", text).strip()

