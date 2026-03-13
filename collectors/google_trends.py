"""Google Trends — pytrends (429 시 조용히 스킵)"""
import time
from pytrends.request import TrendReq

TREND_KEYWORDS = [
    ["상표출원", "상표등록", "상표검색"],
    ["브랜드보호", "상표권침해"],
]


class GoogleTrendsCollector:
    def collect(self) -> dict:
        pt = TrendReq(hl="ko", tz=540, timeout=(10, 30))
        results = {}
        for group in TREND_KEYWORDS:
            try:
                pt.build_payload(group, timeframe="today 3-m", geo="KR")
                df = pt.interest_over_time()
                if df.empty:
                    continue
                for kw in group:
                    if kw in df.columns:
                        avg_now  = float(df[kw].tail(4).mean())
                        avg_prev = float(df[kw].iloc[-8:-4].mean()) if len(df) >= 8 else avg_now
                        results[kw] = {
                            "avg":    round(avg_now, 1),
                            "growth": round((avg_now - avg_prev) / max(avg_prev, 1) * 100, 1),
                        }
                time.sleep(2)
            except Exception as e:
                err = str(e)
                if "429" in err or "response with code 429" in err:
                    # Google IP 차단 — 정상적인 상황, 경고 불필요
                    pass
                else:
                    print(f"  Google Trends 경고 ({group}): {e}")
        return results
