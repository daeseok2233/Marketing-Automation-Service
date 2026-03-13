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
    "markview":  {"name": "마크뷰",      "usp": "AI 기반 이미지·텍스트 상표 유사 검색 (국내 유일 이미지 검색)"},
    "markpick":  {"name": "마크픽",      "usp": "셀프 상표 출원 + 변리사 대행, 합리적 비용"},
    "markpass":  {"name": "마크패스",    "usp": "상표 출원 및 의견제출 자동화, 거절 대응 자동화"},
    "markcloud": {"name": "마크클라우드","usp": "AI 기반 지식재산권 분석·컨설팅, 기업 브랜드 보호 솔루션"},
}


class TopicFinder:
    def __init__(self):
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

    def find_angles(self, raw_data: dict, n: int = 2) -> list:
        """수집 데이터 전체를 분석해 n개의 뉴스재킹 블로그 앵글 반환"""
        summary = self._summarize(raw_data)
        prompt  = self._build_prompt(summary, n)
        result  = self._call_gemini(prompt)
        if result:
            return result[:n]
        print("  [TopicFinder] Gemini 실패 → 기본 앵글 사용")
        return self._fallback(n)

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

    def _build_prompt(self, summary: str, n: int) -> str:
        svc_list = "\n".join(
            f"  - {v['name']} ({k}): {v['usp']}"
            for k, v in SERVICES.items()
        )
        return f"""당신은 한국 지식재산권·상표 전문 블로그의 콘텐츠 전략가입니다.

[오늘 수집한 트렌드·뉴스 데이터]
{summary}

[홍보 서비스]
{svc_list}

━━━ 임무 ━━━
위 데이터를 보고, 오늘 한국에서 화제인 뉴스·검색어를 상표/지식재산권 주제와
창의적으로 연결하는 블로그 앵글을 {n}개 제안하세요.

원칙:
1. 뉴스/트렌드 키워드를 제목에 직접 사용 — SEO 검색량 확보 (뉴스재킹)
2. "이 뉴스가 왜 상표와 관계있는가?"를 자연스럽게 연결
3. 각 앵글은 서로 다른 서비스를 홍보 (같은 서비스 중복 금지)
4. 제목은 40~50자, 클릭욕구 + SEO 동시 충족
{get_template_rules()}

예시 연결 방식:
- "갤럭시 S26 출시" → "갤럭시 S26 브랜드, 삼성은 상표 등록했을까요?"
- "이란 분쟁 뉴스" → "당신의 사업장에서도 브랜드 전쟁은 일어나고 있습니다"
- "스타벅스 신메뉴 논란" → "상표권 없는 브랜드가 겪는 진짜 위기"

아래 JSON 배열만 출력 (코드블록 없이, 반드시 배열로):
[
  {{
    "title": "제목 (40~50자, 뉴스 키워드 포함)",
    "hook": "도입부 2문장 (뉴스 이야기로 시작해 독자 끌어들이기)",
    "connection": "뉴스→상표 연결 전략 (1~2문장, 본문 방향)",
    "main_keyword": "메인 SEO 키워드",
    "news_reference": "참조한 뉴스 헤드라인 또는 트렌드 키워드",
    "service_key": "markview 또는 markpick 또는 markpass 또는 markcloud",
    "template_key": "{'또는'.join(get_template_names())}",
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

    def _fallback(self, n: int) -> list:
        defaults = [
            {
                "title": "상표 출원, 당신의 브랜드를 지키는 가장 확실한 방법",
                "hook": "열심히 키운 브랜드를 하루아침에 빼앗길 수 있다는 걸 알고 계셨나요? 상표 등록 없이는 법적 보호를 받을 수 없습니다.",
                "connection": "상표 출원의 필요성을 설명하고 마크픽의 간편 출원 서비스를 자연스럽게 소개",
                "main_keyword": "상표 출원",
                "news_reference": "상표 출원 트렌드",
                "service_key": "markpick",
                "template_key": "info",
                "trend_score": 60,
            },
            {
                "title": "유사 상표 검색 안 했다가 출원 거절? 사전 조사가 답입니다",
                "hook": "상표 출원 후 거절 통보를 받은 경험, 알고 보면 사전 검색 한 번이면 막을 수 있었습니다. 이미 같은 상표가 있었던 것입니다.",
                "connection": "유사 상표 조사의 중요성을 강조하고 마크뷰의 AI 이미지 검색 기능 소개",
                "main_keyword": "유사 상표 검색",
                "news_reference": "상표 거절 사례",
                "service_key": "markview",
                "template_key": "howto",
                "trend_score": 55,
            },
        ]
        return defaults[:n]
