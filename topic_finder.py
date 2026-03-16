"""뉴스재킹 블로그 앵글 발굴 — Gemini가 오늘 데이터를 읽고 창의적 각도를 제안"""
import os, json, re, time
import requests as _req
from google import genai
from google.genai import types
from templates import get_template_rules, get_template_names

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# 무료 한도 소진 시 순서대로 폴백 (각 모델 독립 쿼터)
MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
]

SERVICES = {
    "markview":          {"name": "마크뷰",           "usp": "AI 기반 이미지·텍스트 상표 유사 검색 (국내 유일 이미지 검색)"},
    "markpick":          {"name": "마크픽",           "usp": "셀프 상표 출원 + 변리사 대행, 합리적 비용"},
    "markpass":          {"name": "마크패스",         "usp": "상표 출원 및 의견제출 자동화, 거절 대응 자동화"},
    "markcloud":         {"name": "마크클라우드",      "usp": "AI 기반 지식재산권 분석·컨설팅, 기업 브랜드 보호 솔루션"},
    # 지역 특화 블로그 — 지역 키워드가 뚜렷한 앵글에만 사용
    "markpass_seoul":    {"name": "마크패스(서울)",    "usp": "서울 소재 기업·스타트업 상표·특허 출원 자동화"},
    "markpass_gyeonggi": {"name": "마크패스(경기·인천)","usp": "경기·인천 제조업·스타트업 상표·특허 출원 자동화"},
    "markpass_busan":    {"name": "마크패스(부산·경남)","usp": "부산·경남 수산·조선·관광 기업 상표·특허 출원 자동화"},
}


class TopicFinder:
    def __init__(self):
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

    def find_angles(self, raw_data: dict, n: int = 2, required_templates: list = None) -> list:
        """수집 데이터 전체를 분석해 n개의 뉴스재킹 블로그 앵글 반환.
        required_templates 지정 시 각 템플릿을 1개씩 사용하도록 Gemini에 지시."""
        summary = self._summarize(raw_data)
        prompt  = self._build_prompt(summary, n, required_templates)
        result  = self._call_gemini(prompt)
        if result:
            return result[:n]
        print("  [TopicFinder] Gemini 실패 → 기본 앵글 사용")
        return self._fallback(n, required_templates)

    # ─────────────────────────────────────────────────────────────
    def _summarize(self, raw_data: dict) -> str:
        lines = []

        naver = raw_data.get("naver", {})
        if naver:
            top = sorted(naver.items(), key=lambda x: x[1].get("avg_ratio", 0), reverse=True)[:5]
            lines.append("[네이버 인기 검색어]")
            for kw, d in top:
                lines.append(f"  {kw}: 평균 {d.get('avg_ratio',0):.1f} (전주대비 {d.get('growth_rate',0):+.0f}%)")

        google = raw_data.get("google", {})
        if google:
            top = sorted(google.items(), key=lambda x: x[1].get("avg", 0), reverse=True)[:5]
            lines.append("[구글 인기 검색어]")
            for kw, d in top:
                lines.append(f"  {kw}: 관심도 {d.get('avg',0):.0f} ({d.get('growth',0):+.0f}%)")

        news = raw_data.get("naver_news", {}).get("headlines", [])
        if news:
            lines.append("[오늘의 주요 뉴스 헤드라인]")
            for item in news[:30]:
                lines.append(f"  [{item.get('query','')}] {item.get('title','')}")

        competitor = raw_data.get("competitor", {})
        titles = competitor.get("sample_titles", [])
        if titles:
            lines.append("[경쟁사 블로그 제목 (참고용)]")
            for item in titles[:8]:
                lines.append(f"  {item.get('title','')}")

        kipris = raw_data.get("kipris", {})
        if kipris:
            lines.append(f"[출원 통계] 연간 약 {kipris.get('annual_benchmark', 270000):,}건 (특허청)")

        return "\n".join(lines)

    def _build_prompt(self, summary: str, n: int, required_templates: list = None) -> str:
        svc_list = "\n".join(
            f"  - {v['name']} ({k}): {v['usp']}"
            for k, v in SERVICES.items()
        )

        if required_templates:
            template_rule = (
                f"5. 아래 템플릿 목록에서 각각 정확히 1개씩 사용 (중복 금지, 누락 금지):\n"
                + "\n".join(f"   {i+1}. {t}" for i, t in enumerate(required_templates))
                + f"\n   → 총 {len(required_templates)}개 앵글, 각 앵글의 template_key는 위 목록 중 하나"
            )
            template_key_hint = " | ".join(required_templates)
        else:
            template_rule = f"5. 각 앵글은 서로 다른 template_key 사용\n{get_template_rules()}"
            template_key_hint = " | ".join(get_template_names())

        return f"""당신은 한국 지식재산권·상표 전문 블로그의 콘텐츠 전략가입니다.

[오늘 수집한 트렌드·뉴스 데이터]
{summary}

[홍보 서비스]
{svc_list}

━━━ 임무 ━━━
위 데이터를 보고, 오늘 한국에서 화제인 뉴스·검색어를 상표/지식재산권 주제와
창의적으로 연결하는 블로그 앵글을 정확히 {n}개 제안하세요.

원칙:
1. 뉴스/트렌드 키워드를 제목에 직접 사용 — SEO 검색량 확보 (뉴스재킹)
2. "이 뉴스가 왜 상표와 관계있는가?"를 자연스럽게 연결
3. 각 앵글은 서로 다른 서비스를 홍보 (같은 서비스 연속 중복 지양)
   지역 뉴스/트렌드(서울·경기·인천·부산·경남 등)가 있으면 해당 지역 서비스 키 활용
4. 제목은 40~50자, 클릭욕구 + SEO 동시 충족
{template_rule}

[템플릿 설명]
{get_template_rules()}

예시 연결 방식:
- "갤럭시 S26 출시" → "갤럭시 S26 브랜드, 삼성은 상표 등록했을까요?"
- "이란 분쟁 뉴스" → "당신의 사업장에서도 브랜드 전쟁은 일어나고 있습니다"
- "스타벅스 신메뉴 논란" → "상표권 없는 브랜드가 겪는 진짜 위기"

아래 JSON 배열만 출력 (코드블록 없이, 반드시 배열로, 정확히 {n}개):
[
  {{
    "title": "제목 (40~50자, 뉴스 키워드 포함)",
    "hook": "도입부 2문장 (뉴스 이야기로 시작해 독자 끌어들이기)",
    "connection": "뉴스→상표 연결 전략 (1~2문장, 본문 방향)",
    "main_keyword": "메인 SEO 키워드",
    "news_reference": "참조한 뉴스 헤드라인 또는 트렌드 키워드",
    "service_key": "markview | markpick | markpass | markcloud | markpass_seoul | markpass_gyeonggi | markpass_busan 중 하나 (지역 뉴스·트렌드면 지역 키 우선)",
    "template_key": "{template_key_hint} 중 하나",
    "trend_score": 85
  }}
]"""

    def _call_gemini(self, prompt: str) -> list | None:
        for model in MODELS:
            try:
                if "2.5" in model or "latest" in model:
                    config = types.GenerateContentConfig(
                        temperature=0.85,
                        max_output_tokens=4096,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    )
                else:
                    config = types.GenerateContentConfig(temperature=0.85, max_output_tokens=4096)

                resp = self.client.models.generate_content(
                    model=model, contents=prompt, config=config,
                )
                cleaned = re.sub(r"```(?:json)?", "", resp.text.strip()).replace("```", "").strip()
                m = re.search(r'\[[\s\S]*\]', cleaned)
                if m:
                    return json.loads(m.group())
                print(f"  [TopicFinder] {model} JSON 파싱 실패")
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    print(f"  [TopicFinder] {model} 한도 초과, 다음 모델...")
                    time.sleep(5)
                    continue
                print(f"  [TopicFinder] 오류 ({model}): {e}")
        print("  [TopicFinder] Gemini 모든 모델 실패 → Ollama 시도...")
        return self._call_ollama(prompt)

    def _call_ollama(self, prompt: str) -> list | None:
        """Gemini 전부 실패 시 로컬 Ollama 폴백"""
        try:
            tags = _req.get(f"{OLLAMA_URL}/api/tags", timeout=5).json()
            models = [m["name"] for m in tags.get("models", [])]
        except Exception:
            print("  [TopicFinder] Ollama 연결 실패")
            return None
        if not models:
            print("  [TopicFinder] Ollama 모델 없음 — 'ollama pull llama3.2' 실행 후 재시도")
            return None
        model = models[0]
        print(f"  [TopicFinder] Ollama 모델 사용: {model}")
        try:
            resp = _req.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
                timeout=180,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
            cleaned = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
            m = re.search(r'\[[\s\S]*\]', cleaned)
            if m:
                return json.loads(m.group())
            print(f"  [TopicFinder] Ollama JSON 파싱 실패\n  원본: {text[:200]}")
        except Exception as e:
            print(f"  [TopicFinder] Ollama 오류: {e}")
        return None

    def _fallback(self, n: int, required_templates: list = None) -> list:
        all_defaults = [
            {"title": "상표 출원, 당신의 브랜드를 지키는 가장 확실한 방법", "hook": "열심히 키운 브랜드를 하루아침에 빼앗길 수 있다는 걸 알고 계셨나요? 상표 등록 없이는 법적 보호를 받을 수 없습니다.", "connection": "상표 출원의 필요성을 설명하고 마크픽의 간편 출원 서비스를 자연스럽게 소개", "main_keyword": "상표 출원", "news_reference": "상표 출원 트렌드", "service_key": "markpick", "template_key": "info", "trend_score": 60},
            {"title": "유사 상표 검색 안 했다가 출원 거절? 사전 조사가 답입니다", "hook": "상표 출원 후 거절 통보를 받은 경험, 알고 보면 사전 검색 한 번이면 막을 수 있었습니다.", "connection": "유사 상표 조사의 중요성을 강조하고 마크뷰의 AI 이미지 검색 기능 소개", "main_keyword": "유사 상표 검색", "news_reference": "상표 거절 사례", "service_key": "markview", "template_key": "howto", "trend_score": 55},
            {"title": "스타트업 상표 분쟁, 수억 원 날린 실제 사례와 교훈", "hook": "브랜드를 키운 뒤 상표 분쟁에 휘말린 스타트업들이 매년 늘고 있습니다.", "connection": "실제 분쟁 사례를 통해 상표 사전 보호의 중요성과 마크클라우드 모니터링 소개", "main_keyword": "상표 분쟁", "news_reference": "브랜드 분쟁 뉴스", "service_key": "markcloud", "template_key": "case", "trend_score": 58},
            {"title": "상표 출원 셀프 vs 변리사 대행, 2026년 완전 비교", "hook": "셀프로 할지 전문가에게 맡길지, 창업자들이 가장 많이 고민하는 질문입니다.", "connection": "비용·성공률·기간을 비교해 마크픽의 하이브리드 방식을 자연스럽게 소개", "main_keyword": "상표 출원 비용 비교", "news_reference": "창업 트렌드", "service_key": "markpick", "template_key": "compare", "trend_score": 52},
            {"title": "마크뷰로 직접 검색해봤습니다 — 유사 상표가 이렇게나 많다고?", "hook": "출원 전 유사 상표를 검색해보셨나요? AI 이미지 검색으로 직접 확인해봤습니다.", "connection": "마크뷰 AI 이미지 검색 체험을 통해 서비스 기능 직접 시연", "main_keyword": "AI 이미지 상표 검색", "news_reference": "AI 상표 검색 트렌드", "service_key": "markview", "template_key": "image-search-demo", "trend_score": 50},
            {"title": "상표 FAQ: 창업자가 가장 많이 묻는 10가지 질문", "hook": "상표에 대해 궁금한 게 많은 창업자분들을 위해 핵심 질문만 모았습니다.", "connection": "FAQ 형식으로 상표 지식을 전달하고 각 답변에서 서비스 자연 연결", "main_keyword": "상표 출원 FAQ", "news_reference": "창업 상표 트렌드", "service_key": "markpick", "template_key": "faq", "trend_score": 48},
            {"title": "상표 출원 체크리스트: 창업자가 놓치면 안 되는 7단계", "hook": "상표 출원 순서를 몰라 처음부터 다시 해야 했던 경험, 이제 체크리스트로 해결하세요.", "connection": "단계별 체크리스트로 실용 정보를 제공하고 마크패스 자동화 소개", "main_keyword": "상표 출원 절차", "news_reference": "스타트업 창업 트렌드", "service_key": "markpass", "template_key": "checklist", "trend_score": 45},
            {"title": "2026년 상표 출원 통계로 보는 5가지 핵심 트렌드", "hook": "올해 상표 출원 건수가 역대 최고를 기록했습니다. 데이터로 보는 시장 신호는?", "connection": "특허청 KIPRIS 통계 데이터로 트렌드를 분석하고 마크클라우드 인사이트 연결", "main_keyword": "상표 출원 통계 트렌드", "news_reference": "특허청 상표 출원 통계", "service_key": "markcloud", "template_key": "data-analysis", "trend_score": 55},
            {"title": "식음료 업종 상표 출원 급증, 브랜드 선점 경쟁 시작됐다", "hook": "식음료 신제품이 쏟아지는 지금, 상표 출원 경쟁도 뜨거워지고 있습니다.", "connection": "업종별 상표 출원 트렌드를 분석하고 선출원주의 관점에서 마크뷰 조기 검색 소개", "main_keyword": "식음료 상표 출원", "news_reference": "식음료 신제품 트렌드", "service_key": "markview", "template_key": "industry-trend", "trend_score": 53},
        ]
        if required_templates:
            # required_templates 순서대로 해당 template_key 가진 기본값 선택
            result = []
            used = set()
            for tpl in required_templates:
                for d in all_defaults:
                    if d["template_key"] == tpl and tpl not in used:
                        result.append(d)
                        used.add(tpl)
                        break
            return result[:n]
        return all_defaults[:n]
