"""트렌드 분석 엔진 — 수집 데이터 → 블로그 주제 선정"""
from dataclasses import dataclass, field

KEYWORD_SERVICE_MAP = {
    "상표 검색":  "markview", "유사 상표":  "markview", "이미지 검색": "markview",
    "상표 출원":  "markpick", "셀프 출원":  "markpick", "출원 비용":   "markpick", "변리사": "markpick",
    "의견제출":   "markpass", "거절 대응":  "markpass", "자동화":      "markpass",
    "상표권 침해":"markcloud", "브랜드 보호":"markcloud", "IP 분석":    "markcloud",
}
KEYWORD_TEMPLATE_MAP = {
    "방법": "howto", "절차": "howto", "단계": "howto",
    "비용": "compare", "비교": "compare", "vs": "compare",
    "사례": "case",  "분쟁": "case",  "침해": "case",
    "란":   "info",  "뜻":   "info",  "개념": "info",
}

@dataclass
class BlogTopic:
    main_keyword:    str
    related_keywords: list
    template_key:    str
    service_key:     str
    trend_score:     float
    bigkinds_stat:   str
    news_context:    str
    suggested_title: str
    h2_questions:    list = field(default_factory=list)


class TrendAnalyzer:
    def __init__(self, services: dict):
        self.services = services

    def analyze(self, raw_data: dict,
                focus_keywords: list = None,
                keyword_affinities: list = None) -> dict:
        scores = self._score(raw_data)

        # 서비스 포커스 키워드를 점수 부스팅
        if focus_keywords:
            for kw in focus_keywords:
                for scored_kw in list(scores.keys()):
                    if any(fk in scored_kw for fk in focus_keywords):
                        scores[scored_kw]["score"] += 20

        top = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)[:5]
        topics = [self._build(kw, data, raw_data) for kw, data in top]
        return {"top_topics": topics}

    def _score(self, raw_data: dict) -> dict:
        scores = {}

        for kw, d in raw_data.get("naver", {}).items():
            s = scores.setdefault(kw, {"score": 0})
            s["score"] += d.get("avg_ratio", 0) * 0.35
            if d.get("growth_rate", 0) > 10:
                s["score"] += 10

        for kw, d in raw_data.get("google", {}).items():
            s = scores.setdefault(kw, {"score": 0})
            s["score"] += d.get("avg", 0) * 0.25

        for kw, d in raw_data.get("bigkinds", {}).get("keyword_growth", {}).items():
            s = scores.setdefault(kw, {"score": 0})
            cnt    = d.get("recent_count", 0)
            growth = d.get("growth_pct", 0)
            s["score"] += min(cnt * 0.4, 40)
            if growth > 20:
                s["score"] += 15
            s["bigkinds_count"]  = cnt
            s["bigkinds_growth"] = growth

        # 점수가 0이면 기본 키워드라도 추가
        if not scores:
            default_kw = ["상표 출원", "상표 검색", "상표권 침해", "상표 등록 비용"]
            for kw in default_kw:
                scores[kw] = {"score": 10}

        return scores

    def _build(self, keyword: str, score_data: dict, raw_data: dict) -> dict:
        service_key  = next((v for k, v in KEYWORD_SERVICE_MAP.items() if k in keyword), "markcloud")
        template_key = next((v for k, v in KEYWORD_TEMPLATE_MAP.items() if k in keyword), "info")

        cnt    = score_data.get("bigkinds_count", 0)
        growth = score_data.get("bigkinds_growth", 0)

        bigkinds_stat = (
            f"최근 한 달간 국내 주요 언론 보도 기준 '{keyword}' 관련 뉴스 {cnt}건 "
            f"(전월 대비 {growth:+.0f}%, 빅카인즈 분석)"
            if cnt else ""
        )

        kipris = raw_data.get("kipris", {})
        news_context = (
            f"올해 상표 출원 건수 {kipris['total_applications_ytd']:,}건 (특허청 KIPRIS)"
            if kipris.get("total_applications_ytd") else
            f"연간 상표 출원 건수 약 {kipris.get('annual_benchmark', 270000):,}건 수준 (특허청)"
        )

        h2_map = {
            "howto":   [f"{keyword}은 어떻게 하나요?", f"{keyword} 비용은?", "주의사항은?", "기간은?"],
            "info":    [f"{keyword}이란 무엇인가요?", f"{keyword}이 왜 중요한가요?", "자주 묻는 질문"],
            "case":    [f"실제 {keyword} 사례는?", "피해 예방법은?"],
            "compare": [f"{keyword}, 직접 vs 전문가?", "비용 비교"],
        }

        title_map = {
            "howto":   f"{keyword} 완벽 가이드 | 초보도 따라하는 단계별 방법",
            "info":    f"{keyword}이란? 핵심 정보 총정리",
            "case":    f"실제 {keyword} 사례로 배우는 브랜드 보호 전략",
            "compare": f"{keyword} | 셀프 vs 전문가, 상황별 최적 선택법",
        }

        return {
            "main_keyword":     keyword,
            "related_keywords": list(raw_data.get("bigkinds", {}).get("top_related_words", {}).keys())[:5],
            "template_key":     template_key,
            "service_key":      service_key,
            "trend_score":      round(score_data.get("score", 0), 1),
            "bigkinds_stat":    bigkinds_stat,
            "news_context":     news_context,
            "suggested_title":  title_map.get(template_key, f"{keyword} 완벽 정리"),
            "h2_questions":     h2_map.get(template_key, []),
        }
