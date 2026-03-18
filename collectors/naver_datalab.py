"""네이버 DataLab 검색어 트렌드 수집"""
import os
import requests
from datetime import datetime, timedelta
from .utils import save_csv

KEYWORDS = [
    # ── 핵심 키워드
    "상표 출원", "상표 등록", "상표 검색", "상표 침해", "브랜드 등록",
    # ── 롱테일: 비용·절차 (SEO 유입 키워드)
    "상표 등록 비용", "상표 출원 방법", "상표 등록 절차", "상표 등록 기간",
    # ── 롱테일: 갱신·이전·취소
    "상표 갱신", "상표 이전", "상표 취소심판",
    # ── 업종·상황별
    "프랜차이즈 상표", "셀프 상표 출원", "해외 상표 등록",
    # ── 자사 브랜드 (GEO 인지도 추적)
    "마크클라우드", "마크뷰",
]

class NaverDataLabCollector:
    def __init__(self):
        self.client_id     = os.environ.get("NAVER_CLIENT_ID", "")
        self.client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
        self.url = "https://openapi.naver.com/v1/datalab/search"

    def collect(self) -> dict:
        if not self.client_id:
            raise EnvironmentError("NAVER_CLIENT_ID 환경변수가 없습니다")

        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
            "Content-Type": "application/json",
        }

        # DataLab API는 한 번에 keywordGroups 최대 5개 → 청크 분할
        results = {}
        for i in range(0, len(KEYWORDS), 5):
            chunk = KEYWORDS[i : i + 5]
            body = {
                "startDate": start,
                "endDate": end,
                "timeUnit": "week",
                "keywordGroups": [{"groupName": kw, "keywords": [kw]} for kw in chunk],
            }
            try:
                res = requests.post(self.url, headers=headers, json=body, timeout=10)
                res.raise_for_status()
                data = res.json()

                for group in data.get("results", []):
                    name   = group["title"]
                    ratios = [d["ratio"] for d in group["data"][-4:]]
                    prev   = [d["ratio"] for d in group["data"][-8:-4]]
                    avg_now  = sum(ratios) / len(ratios)  if ratios else 0
                    avg_prev = sum(prev)   / len(prev)    if prev   else 1
                    results[name] = {
                        "avg_ratio":   round(avg_now, 2),
                        "growth_rate": round((avg_now - avg_prev) / max(avg_prev, 0.01) * 100, 1),
                    }
            except Exception as e:
                print(f"  [Naver DataLab] 청크 {chunk} 실패: {e}")

        # CSV 저장
        rows = [
            {"keyword": name, "avg_ratio": v["avg_ratio"], "growth_rate": v["growth_rate"]}
            for name, v in results.items()
        ]
        csv_path = save_csv("naver_datalab", rows)
        print(f"  [Naver DataLab] {len(results)}개 키워드 수집, CSV 저장: {csv_path}")

        return results
