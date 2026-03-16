"""빅카인즈(한국언론진흥재단) 뉴스 분석
우선순위:
  1. BIGKINDS_API_KEY 있으면 → BigKinds OpenAPI 직접 호출
  2. 없으면 → data/bigkinds/*.xlsx 파일 파싱 (기존 방식 유지)
"""
import os, glob, requests, re
from collections import Counter
from datetime import datetime, timedelta

import pandas as pd

SEARCH_KEYWORDS = ["상표", "상표권", "상표출원", "상표등록", "상표침해", "브랜드보호"]

BIGKINDS_URL = "https://tools.kinds.or.kr/search/news"


class BigKindsCollector:
    def __init__(self, data_dir: str = "data/bigkinds"):
        self.data_dir = data_dir
        self.api_key  = os.environ.get("BIGKINDS_API_KEY", "")

    def collect(self) -> dict:
        if self.api_key:
            return self._collect_api()
        return self._collect_xlsx()

    def _collect_api(self) -> dict:
        today     = datetime.now()
        date_to   = today.strftime("%Y-%m-%d")
        date_from = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        date_prev = (today - timedelta(days=60)).strftime("%Y-%m-%d")

        def _search(keyword, from_dt, to_dt, size=1):
            try:
                payload = {
                    "access_key": self.api_key,
                    "argument": {
                        "query":        keyword,
                        "published_at": {"from": from_dt, "until": to_dt},
                        "fields":       ["title"],
                        "sort":         {"date": "desc"},
                        "page":         1,
                        "size":         size,
                    },
                }
                res = requests.post(BIGKINDS_URL, json=payload, timeout=15)
                res.raise_for_status()
                data  = res.json().get("result", {})
                total = data.get("total_hits", 0)
                docs  = [d.get("title", "") for d in data.get("documents", []) if d.get("title")]
                return total, docs
            except Exception as e:
                print(f"  [BigKinds] '{keyword}' 조회 실패: {e}")
                return 0, []

        growth = {}
        for kw in SEARCH_KEYWORDS:
            recent_cnt, _ = _search(kw, date_from, date_to)
            prev_cnt,   _ = _search(kw, date_prev, date_from)
            growth[kw] = {
                "recent_count": recent_cnt,
                "prev_count":   prev_cnt,
                "growth_pct":   round((recent_cnt - prev_cnt) / max(prev_cnt, 1) * 100, 1),
            }

        total_recent, titles = _search("상표", date_from, date_to, size=30)
        stop = {"있는", "하는", "위한", "통한", "관련", "대한", "이후", "지난", "이번", "올해"}
        words = Counter()
        for title in titles:
            for w in re.findall(r"[가-힣]{2,}", title):
                if w not in stop:
                    words[w] += 1

        return {
            "total_articles":    total_recent,
            "keyword_growth":    growth,
            "top_related_words": dict(words.most_common(15)),
            "source":            "BigKinds OpenAPI",
        }

    def _collect_xlsx(self) -> dict:
        files = sorted(glob.glob(f"{self.data_dir}/*.xlsx"), reverse=True)
        if not files:
            # xlsx 없으면 Playwright 자동 다운로드 시도
            try:
                from collectors.bigkinds_crawler import download_bigkinds_xlsx
                downloaded = download_bigkinds_xlsx(headless=True)
                if downloaded:
                    files = [str(downloaded)]
            except Exception as e:
                print(f"  [BigKinds] 자동 다운로드 실패: {e}")
        if not files:
            raise FileNotFoundError(
                f"빅카인즈 엑셀 파일이 없습니다.\n"
                f"bigkinds.or.kr -> '상표' 검색 -> 엑셀 다운로드 -> {self.data_dir}/ 에 저장 후 재실행\n"
                f"또는 .env 에 BIGKINDS_ID / BIGKINDS_PW 를 설정하면 자동 수집됩니다."
            )

        df = pd.read_excel(files[0])
        df.columns = df.columns.str.strip()

        date_col = "일자" if "일자" in df.columns else df.columns[0]
        df["_date"] = pd.to_datetime(df[date_col].astype(str), format="%Y%m%d", errors="coerce")

        cutoff      = pd.Timestamp.now() - pd.Timedelta(days=30)
        prev_cutoff = cutoff - pd.Timedelta(days=30)
        recent      = df[df["_date"] >= cutoff]
        prev_period = df[(df["_date"] >= prev_cutoff) & (df["_date"] < cutoff)]

        kw_col = "키워드" if "키워드" in df.columns else "제목"
        growth = {}
        for kw in SEARCH_KEYWORDS:
            now_cnt  = int(recent[kw_col].astype(str).str.contains(kw, na=False).sum())
            prev_cnt = int(prev_period[kw_col].astype(str).str.contains(kw, na=False).sum())
            growth[kw] = {
                "recent_count": now_cnt,
                "prev_count":   prev_cnt,
                "growth_pct":   round((now_cnt - prev_cnt) / max(prev_cnt, 1) * 100, 1),
            }

        all_kw = []
        if "키워드" in recent.columns:
            for cell in recent["키워드"].dropna():
                all_kw.extend(str(cell).split(","))
        top_words = pd.Series(all_kw).str.strip().value_counts().head(15).to_dict()

        return {
            "total_articles":    len(recent),
            "keyword_growth":    growth,
            "top_related_words": top_words,
            "source_file":       files[0],
        }
