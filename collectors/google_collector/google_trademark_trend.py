"""Google Trends — pytrends (429 시 조용히 스킵)"""
import time
from pytrends.request import TrendReq
from logger import get_logger # Added logger import
from collectors.utils import save_csv # Updated import path for save_csv

logger = get_logger(__name__) # Added logger instance

TREND_KEYWORDS = [
    # ── 핵심 키워드
    ["상표출원", "상표등록", "상표검색"],
    ["브랜드보호", "상표권침해"],
    # ── 롱테일: 비용·절차·서류
    ["상표등록비용", "상표출원비용", "상표등록절차"],
    ["상표출원서류", "상표등록기간", "상표갱신"],
    # ── 롱테일: 업종·상황별
    ["프랜차이즈상표", "카페상표등록", "쇼핑몰브랜드"],
    ["셀프상표출원", "변리사비용"],
    # ── 롱테일: 해외·국제
    ["해외상표등록", "마드리드의정서", "미국상표출원"],
    # ── 자사 브랜드 (GEO 인지도 추적)
    ["마크클라우드", "마크뷰", "마크픽"],
]


class GoogleTrademarkTrendCollector: # Renamed class
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
                    logger.debug(f"  [Google Trademark Trend] Google IP 차단 (429): {err}") # Replaced print with logger.debug
                else:
                    logger.error(f"  [Google Trademark Trend] 경고 ({group}): {e}") # Replaced print with logger.error
        # CSV 저장
        rows = [
            {"keyword": kw, "avg": v["avg"], "growth": v["growth"]}
            for kw, v in results.items()
        ]
        csv_path = save_csv("google_trademark_trend", rows) # Updated collector name
        logger.info(f"  [Google Trademark Trend] CSV 저장: {csv_path}") # Replaced print with logger.info

        return results
