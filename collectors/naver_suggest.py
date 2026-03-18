"""네이버 자동완성(Suggest) + 연관 검색어 수집 — AEO 질문형 키워드 확보

인증 불필요, 무료.
네이버 검색창 자동완성 API를 활용하여 사용자가 실제로 검색하는
롱테일 키워드와 질문형 키워드를 수집한다.
"""
import re
import requests
from .utils import save_csv

# ── 시드 키워드: 자동완성을 펼칠 기본 키워드
SEED_KEYWORDS = [
    "상표 출원", "상표 등록", "상표 검색", "상표 침해",
    "상표 갱신", "상표 이전", "상표 취소",
    "브랜드 등록", "브랜드 보호",
    "마크클라우드", "마크뷰", "마크픽",
    "프랜차이즈 상표", "해외 상표 등록",
    "셀프 상표 출원", "상표 등록 비용",
]

# ── 질문 접두사: AEO용 의문문 키워드 생성
QUESTION_PREFIXES = [
    "{kw} 방법", "{kw} 비용", "{kw} 기간", "{kw} 서류",
    "{kw} 절차", "{kw} 뜻", "{kw} 차이",
]

SUGGEST_URL = "https://ac.search.naver.com/nx/ac"


class NaverSuggestCollector:
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; blog-pipeline/1.0)"}

    def collect(self) -> dict:
        all_suggestions: list[dict] = []
        seen = set()

        # 1) 시드 키워드 자동완성
        for seed in SEED_KEYWORDS:
            suggestions = self._fetch_suggest(seed)
            for s in suggestions:
                if s not in seen:
                    seen.add(s)
                    all_suggestions.append({
                        "seed": seed,
                        "suggest": s,
                        "type": "autocomplete",
                    })

        # 2) 질문형 키워드 자동완성 (AEO)
        base_keywords = ["상표 출원", "상표 등록", "상표 검색", "상표 침해", "브랜드 등록"]
        for kw in base_keywords:
            for prefix_tpl in QUESTION_PREFIXES:
                query = prefix_tpl.format(kw=kw)
                suggestions = self._fetch_suggest(query)
                for s in suggestions:
                    if s not in seen:
                        seen.add(s)
                        all_suggestions.append({
                            "seed": query,
                            "suggest": s,
                            "type": "question",
                        })

        # CSV 저장
        csv_path = save_csv("naver_suggest", all_suggestions)
        print(f"  [Naver Suggest] {len(all_suggestions)}개 키워드 수집, CSV 저장: {csv_path}")

        # 질문형 키워드만 분리
        question_keywords = [
            r["suggest"] for r in all_suggestions
            if self._is_question(r["suggest"])
        ]

        return {
            "total": len(all_suggestions),
            "suggestions": all_suggestions,
            "question_keywords": question_keywords,
        }

    def _fetch_suggest(self, query: str) -> list[str]:
        """네이버 자동완성 API 호출"""
        try:
            params = {
                "q": query,
                "con": "1",
                "frm": "nv",
                "ans": "2",
                "t_koreng": "1",
                "r_format": "json",
                "r_enc": "UTF-8",
                "r_unicode": "0",
                "st": "100",
            }
            res = requests.get(
                SUGGEST_URL,
                params=params,
                headers=self.HEADERS,
                timeout=5,
            )
            res.raise_for_status()
            data = res.json()
            # 응답 구조: {"items": [["keyword1", ...], ...]} 또는 유사
            items = data.get("items", [])
            results = []
            for item in items:
                if isinstance(item, list):
                    for sub in item:
                        if isinstance(sub, str) and sub.strip():
                            results.append(sub.strip())
                        elif isinstance(sub, list) and sub:
                            results.append(str(sub[0]).strip())
            return results[:10]
        except Exception as e:
            print(f"  [Suggest] '{query}' 수집 실패: {e}")
            return []

    @staticmethod
    def _is_question(text: str) -> bool:
        """질문형 키워드 판별"""
        question_patterns = [
            r"방법", r"비용", r"얼마", r"기간", r"어떻게",
            r"뭐", r"무엇", r"왜", r"언제", r"어디",
            r"차이", r"뜻", r"서류", r"필요",
            r"할 수", r"해야", r"되나", r"인가",
        ]
        return any(re.search(p, text) for p in question_patterns)
