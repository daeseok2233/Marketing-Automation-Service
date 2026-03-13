"""네이버 DataLab 검색어 트렌드 수집"""
import os
import requests
from datetime import datetime, timedelta

KEYWORDS = [
    "상표 출원", "상표 등록", "상표 검색", "상표 침해", "브랜드 등록",
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

        body = {
            "startDate": start,
            "endDate": end,
            "timeUnit": "week",
            "keywordGroups": [{"groupName": kw, "keywords": [kw]} for kw in KEYWORDS],
        }
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
            "Content-Type": "application/json",
        }
        res = requests.post(self.url, headers=headers, json=body, timeout=10)
        res.raise_for_status()
        data = res.json()

        results = {}
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
        return results
