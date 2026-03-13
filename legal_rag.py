"""법률 RAG - 검증된 상표법 사실을 블로그 프롬프트에 주입해 할루시네이션 차단

동작 방식:
  1. VERIFIED (하드코딩) - 특허청·법제처 공식 자료 기반 핵심 사실 (항상 포함)
  2. law_data (API) - LawKrCollector로 수집한 실제 조문·판례 (있으면 추가)

프롬프트에 주입되는 규칙:
  - 이 섹션 밖의 법률 수치·판례·조항 번호는 절대 사용 금지
  - 수수료 금액은 단정하지 말고 patent.go.kr 확인 안내로 대체
"""

# ── 검증된 핵심 사실 ─────────────────────────────────────────────
# 수정 시 반드시 특허청(kipo.go.kr) 또는 국가법령정보센터(law.go.kr) 에서 확인
VERIFIED = {
    "fees_note": (
        "수수료 금액은 특허로(www.patent.go.kr)에서 최신 금액을 확인해야 합니다. "
        "블로그 본문에 수수료를 언급할 때는 구체적 금액을 단정하지 말고 "
        "'특허로에서 확인 가능'으로 안내하거나 '유형별로 상이'라고만 쓸 것."
    ),
    "timeline": {
        "일반심사":    "출원 후 평균 14~16개월 소요",
        "우선심사":    "우선심사 신청 시 2~4개월로 단축 가능",
        "이의신청기간": "출원공고 후 2개월 이내",
        "권리존속기간": "등록일로부터 10년 (10년마다 갱신 가능)",
        "출처":        "특허청 공식 통계",
    },
    "key_articles": [
        {"조항": "상표법 제2조",   "내용": "상표의 정의 - 자기의 상품을 타인의 상품과 식별하기 위한 표장"},
        {"조항": "상표법 제33조",  "내용": "상표등록 요건 - 식별력 없는 표장(기술적·성질표시·보통명칭 등)은 등록 불가"},
        {"조항": "상표법 제34조",  "내용": "등록받을 수 없는 상표 - 공서양속 위반, 국가명, 저명 상표와 혼동 우려 등 절대적 거절사유"},
        {"조항": "상표법 제35조",  "내용": "선출원주의 - 동일·유사 상표·지정상품에 대해 먼저 출원한 자가 우선 등록"},
        {"조항": "상표법 제65조",  "내용": "출원공고 - 심사관이 등록 결정하면 2개월간 공고, 이의신청 기간"},
        {"조항": "상표법 제108조", "내용": "침해금지청구 - 상표권자는 침해자에게 침해 금지·예방 청구 가능"},
        {"조항": "상표법 제109조", "내용": "손해배상청구 - 고의·과실로 상표권 침해 시 손해배상 책임"},
        {"조항": "상표법 제119조", "내용": "불사용 취소심판 - 3년 이상 국내에서 사용하지 않으면 취소심판 청구 가능"},
    ],
    "rejection_reasons": [
        "식별력 없음 - 상품의 보통명칭·품질·효능·원산지를 직접 표시 (상표법 제33조)",
        "선출원·선등록 동일·유사 상표 존재 (상표법 제35조)",
        "저명한 타인의 상표와 혼동 우려 (상표법 제34조 제1항 제9호)",
        "공서양속 또는 공익에 반하는 상표 (상표법 제34조)",
        "국가명·공공기관 명칭 포함 (상표법 제34조)",
    ],
    "procedure": [
        "① 출원 (특허청 전자출원 또는 서면 접수)",
        "② 방식심사 - 서류 적합성 검토 (약 1개월)",
        "③ 실체심사 - 유사 상표 조사·식별력 판단 (평균 14~16개월)",
        "④ 거절이유통지 → 의견서·보정서 제출 (지정기간 이내, 통상 2개월)",
        "⑤ 출원공고 - 이의신청 기간 2개월",
        "⑥ 등록결정 → 등록료 납부 → 상표권 발생",
    ],
    "important_notes": [
        "상표권은 선출원주의 - 실제 사용 여부와 무관하게 먼저 출원한 자가 원칙적으로 우선",
        "유사 여부 판단은 외관·호칭·관념 세 가지 기준으로 종합 판단 (대법원 판례 원칙)",
        "지정상품 범위가 넓을수록 보호 범위도 넓지만 심사 통과 난이도 상승",
        "국제상표등록(마드리드 의정서)으로 해외 여러 국가에 동시 출원 가능",
        "상표권은 업종(지정상품류)별로 별도 출원 필요 - 같은 이름이라도 업종 다르면 중복 가능",
    ],
}


class LegalRAG:
    def __init__(self, law_data: dict = None):
        """
        law_data: LawKrCollector().collect() 결과
                  없으면 VERIFIED 하드코딩 사실만 사용 (할루시 방지 효과는 동일)
        """
        self.law_data = law_data or {}

    def get_context(self, main_keyword: str = "") -> str:
        """프롬프트에 주입할 검증된 법률 컨텍스트 블록 반환"""
        parts = [self._base_block()]

        case_block = self._case_block(main_keyword)
        if case_block:
            parts.append(case_block)

        article_block = self._article_block(main_keyword)
        if article_block:
            parts.append(article_block)

        return "\n\n".join(parts)

    # ── private ──────────────────────────────────────────────────
    def _base_block(self) -> str:
        v  = VERIFIED
        tl = v["timeline"]

        lines = [
            "━━━ 검증된 상표법 사실 [이 섹션 내용만 법률 정보로 인용할 것] ━━━",
            "",
            "◆ 심사기간 (출처: 특허청 공식 통계)",
            f"  · 일반 심사: {tl['일반심사']}",
            f"  · 우선심사: {tl['우선심사']}",
            f"  · 이의신청 기간: {tl['이의신청기간']}",
            f"  · 권리 존속기간: {tl['권리존속기간']}",
            "",
            "◆ 수수료 안내",
            f"  · {v['fees_note']}",
            "",
            "◆ 핵심 법조항 (상표법)",
        ]
        for art in v["key_articles"]:
            lines.append(f"  · {art['조항']}: {art['내용']}")

        lines += ["", "◆ 주요 거절 이유"]
        for r in v["rejection_reasons"]:
            lines.append(f"  · {r}")

        lines += ["", "◆ 출원 절차"]
        for step in v["procedure"]:
            lines.append(f"  {step}")

        lines += ["", "◆ 중요 원칙"]
        for note in v["important_notes"]:
            lines.append(f"  · {note}")

        lines += [
            "",
            "⚠️ 주의사항 (반드시 준수)",
            "  · 위 목록에 없는 구체적 판례 번호·사건명·손해배상 금액은 절대 지어내지 말 것",
            "  · 법조항 번호는 위에 명시된 것만 인용할 것 (없는 조항 번호 사용 금지)",
            "  · 수수료 구체적 금액은 단정하지 말고 patent.go.kr 확인 안내로 대체할 것",
            "  · 실제 기업명·상표명을 특정 분쟁의 당사자로 단정하지 말 것",
        ]
        return "\n".join(lines)

    def _case_block(self, keyword: str) -> str:
        cases = self.law_data.get("cases", [])
        if not cases:
            return ""
        relevant = [
            c for c in cases
            if keyword in c.get("case_name", "") or keyword in c.get("summary", "")
        ][:3]
        if not relevant:
            relevant = cases[:2]
        if not relevant:
            return ""
        lines = ["◆ 실제 판례 (법제처 공식 데이터 - 아래 판례만 사례로 인용 가능)"]
        for c in relevant:
            lines.append(
                f"  · [{c['court']}] {c['case_no']} ({c['date']}): {c['summary'][:200]}"
            )
        return "\n".join(lines)

    def _article_block(self, keyword: str) -> str:
        articles = self.law_data.get("articles", [])
        relevant = [
            a for a in articles
            if keyword in a.get("content", "") or keyword in a.get("title", "")
        ][:3]
        if not relevant:
            return ""
        lines = ["◆ 관련 법조항 (국가법령정보센터 공식 데이터)"]
        for a in relevant:
            lines.append(
                f"  · 제{a['number']}조 {a['title']}: {a['content'][:250]}"
            )
        return "\n".join(lines)
