"""빅카인즈 엑셀 파일 파싱 — data/bigkinds/*.xlsx"""
import glob
import pandas as pd

SEARCH_KEYWORDS = ["상표", "상표권", "상표출원", "상표등록", "상표침해", "브랜드보호"]

class BigKindsCollector:
    def __init__(self, data_dir: str = "data/bigkinds"):
        self.data_dir = data_dir

    def collect(self) -> dict:
        files = sorted(glob.glob(f"{self.data_dir}/*.xlsx"), reverse=True)
        if not files:
            raise FileNotFoundError(
                f"빅카인즈 엑셀 파일이 없습니다.\n"
                f"bigkinds.or.kr → '상표' 검색 → 엑셀 다운로드 → {self.data_dir}/ 에 저장 후 재실행"
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
            "total_articles":  len(recent),
            "keyword_growth":  growth,
            "top_related_words": top_words,
            "source_file":     files[0],
        }
