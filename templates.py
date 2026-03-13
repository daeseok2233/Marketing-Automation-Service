"""블로그 템플릿 로더 + Gemini 프롬프트 빌더

템플릿 파일 위치: blog_templates/*.json
새 템플릿 추가 방법: blog_templates/ 에 JSON 파일 추가 (코드 수정 불필요)
"""
import json
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "blog_templates"

COMMON_RULES = """
━━━ 작성 규칙 ━━━
[SEO]  제목 40~50자·메인 키워드 앞쪽 배치 / 첫·끝 문단에 키워드 포함 / H2는 **굵게**
[AEO]  H2는 반드시 의문문 / 각 H2 바로 아래 핵심 답변 2~3문장 먼저 제시
[GEO]  빅카인즈 통계·특허청 수치 본문 인용(출처 표기) / 전문가 단정 문체
[품질]  본문 1,800자 이상 / 광고 문구 금지 / 해시태그 6~8개
"""


def _load_templates() -> dict:
    """blog_templates/*.json 파일을 모두 읽어 dict 반환"""
    templates = {}
    if not TEMPLATES_DIR.exists():
        return templates
    for path in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            key = data.get("key", path.stem)
            templates[key] = data
        except Exception as e:
            print(f"  [templates] {path.name} 로드 실패: {e}")
    return templates


# 앱 시작 시 1회 로드 (런타임 중 파일 수정은 반영 안 됨)
_TEMPLATE_DATA: dict = _load_templates()

# 하위 호환용 — 구조 문자열만 추출 (build_prompt 등에서 사용)
TEMPLATES: dict[str, str] = {
    k: "\n".join(v.get("structure", []))
    for k, v in _TEMPLATE_DATA.items()
}


def get_template_rules() -> str:
    """topic_finder 프롬프트에 삽입할 템플릿 선택 규칙 문자열 반환"""
    lines = ["5. template_key 선택 규칙 (반드시 준수):"]
    for k, data in _TEMPLATE_DATA.items():
        when = data.get("when_to_use", "")
        not_for = data.get("not_for", [])
        lines.append(f'   - "{k}" ({data.get("name","")}) : {when}')
        for rule in not_for:
            lines.append(f'     ※ {rule}')
    return "\n".join(lines)


def get_template_names() -> list[str]:
    """사용 가능한 template_key 목록 반환"""
    return list(_TEMPLATE_DATA.keys())


def build_angle_prompt(
    angle: dict,
    service: dict,
    raw_data: dict,
    legal_context: str = "",
    kipris_brand: dict = None,
    screenshot: dict = None,
) -> str:
    """뉴스재킹 앵글 기반 프롬프트 — TopicFinder 결과를 받아 실제 글 생성용 프롬프트 빌드"""
    tpl_key = angle.get("template_key", "info")
    tpl_data = _TEMPLATE_DATA.get(tpl_key) or _TEMPLATE_DATA.get("info", {})
    tpl = "\n".join(tpl_data.get("structure", []))

    # 예시 제목 (해당 템플릿의 올바른 사용 예를 Gemini에게 보여줌)
    examples = tpl_data.get("example_titles", [])
    example_block = ""
    if examples:
        example_block = "이 템플릿의 올바른 제목 예시:\n" + "\n".join(f"  - {e}" for e in examples)

    kipris = raw_data.get("kipris", {})
    kipris_stat = (
        f"올해 상표 출원 {kipris['total_applications_ytd']:,}건 (특허청 KIPRIS)"
        if kipris.get("total_applications_ytd") else
        f"연간 상표 출원 약 {kipris.get('annual_benchmark', 270000):,}건 (특허청)"
    )

    bigkinds = raw_data.get("bigkinds", {})
    kw = angle.get("main_keyword", "상표 출원")
    bk_data = bigkinds.get("keyword_growth", {}).get(kw, {})
    bk_stat = (
        f"'{kw}' 최근 뉴스 {bk_data['recent_count']}건 (전월 대비 {bk_data.get('growth_pct', 0):+.0f}%, 빅카인즈)"
        if bk_data.get("recent_count") else ""
    )

    # 브랜드 조회 결과 요약 (템플릿 구조 내 {kipris_result_block} 치환용)
    brand_name_val = (kipris_brand or {}).get("brand_name", angle.get("main_keyword", ""))
    kipris_result_val = (kipris_brand or {}).get("summary", "") if kipris_brand else ""
    screenshot_val = ("캡처 완료" if (screenshot or {}).get("success") else "미첨부") if screenshot else ""

    body = tpl.format(
        kw=kw,
        svc=service["name"],
        usp=service["usp"],
        bigkinds=bk_stat,
        kipris=kipris_stat,
        brand_name=brand_name_val,
        kipris_result_block=kipris_result_val,
        screenshot_block=screenshot_val,
    )

    # ── 브랜드 KIPRIS 조회 결과 블록
    kipris_brand_block = ""
    if kipris_brand and kipris_brand.get("found"):
        lines = [f"[KIPRIS 조회 결과] {kipris_brand['summary']}"]
        for item in kipris_brand.get("items", []):
            status    = item.get("status", "")
            app_no    = item.get("application_number", "")
            app_date  = item.get("application_date", "")
            applicant = item.get("applicant", "")
            cls_code  = item.get("goods_class", "")
            title     = item.get("title", "")
            lines.append(f"  · {title} | {cls_code} | 출원일 {app_date} | 상태: {status} | 출원인: {applicant} | 출원번호: {app_no}")
        kipris_brand_block = "\n".join(lines)
    elif kipris_brand:
        kipris_brand_block = f"[KIPRIS 조회 결과] {kipris_brand.get('summary', '')}"

    # ── 스크린샷 상태 블록
    screenshot_block = ""
    if screenshot:
        if screenshot.get("success"):
            screenshot_block = f"[마크뷰 스크린샷 캡처 완료] 파일: {screenshot.get('path', '')}\n본문에 '위 화면처럼' 형태로 캡처 화면을 언급하세요."
        else:
            screenshot_block = f"[스크린샷 미첨부] {screenshot.get('error', '')}\n화면 캡처 없이 마크뷰 기능을 텍스트로 설명하세요."

    news_ref = angle.get("news_reference", "")
    hook = angle.get("hook", "")

    return f"""당신은 한국 지식재산권·상표 전문 블로그 작가입니다.

━━━ 오늘의 뉴스재킹 앵글 ━━━
참조 뉴스/트렌드 : {news_ref}
제안 제목        : {angle.get("title", "")}
도입 훅          : {hook}
연결 전략        : {angle.get("connection", "")}

━━━ 블로그 데이터 ━━━
메인 키워드 : {kw}
트렌드 점수 : {angle.get("trend_score", 0)}점
뉴스 통계   : {bk_stat}
출원 통계   : {kipris_stat}
홍보 서비스 : {service["name"]} — {service["usp"]}
서비스 URL  : {service["url"]}

━━━ 선택된 템플릿: {tpl_data.get("name", tpl_key)} ━━━
{example_block}

{body}
{f"━━━ KIPRIS 브랜드 조회 데이터 ━━━{chr(10)}{kipris_brand_block}" if kipris_brand_block else ""}
{f"━━━ 마크뷰 스크린샷 ━━━{chr(10)}{screenshot_block}" if screenshot_block else ""}
{COMMON_RULES}

{legal_context}

━━━ 템플릿 사용 주의 ━━━
- "사례형(case)" 구조를 쓰는 경우: 반드시 실제 분쟁·침해·법적 갈등이 존재해야 함
- 참조 뉴스가 신제품 출시·긍정적 성과·트렌드 증가라면 사례형 소제목
  ("어떤 사건이었나요?", "무엇이 문제였을까요?", "실제 피해 규모는?")을 사용하지 말 것
- 대신 정보형 소제목으로 자연스럽게 변경하거나, info/howto 구조를 따를 것

━━━ 뉴스재킹 본문 필수 규칙 ━━━
[핵심] 본문은 반드시 아래 순서를 따를 것:

1. [도입 — 뉴스 이야기로 시작]
   - 첫 문단은 반드시 위 '도입 훅'을 그대로 활용해 시작
   - '{news_ref}' 키워드를 도입부에 자연스럽게 언급 (독자가 검색한 이유를 충족)
   - 2~3문장으로 뉴스/트렌드 상황을 간략히 설명

2. [브릿지 — 상표/IP로 연결]
   - "그런데 이 상황, 상표권 관점에서 보면..." 형태로 자연스럽게 전환
   - 뉴스 키워드와 상표 주제의 연결 고리를 1문단으로 명확히 설명

3. [본문 — 위 구조대로 작성]

4. [마무리 — 뉴스 키워드 재언급]
   - 마지막 문단에서 '{news_ref}' 맥락으로 다시 돌아와 마무리
   - {service["name"]} CTA로 끝낼 것

[검색 일관성] '{news_ref}' 키워드가 본문 전체에 최소 2회 이상 등장해야 함

━━━ 출력 ━━━
아래 JSON만 출력 (코드블록 없이 순수 JSON):
{{
  "title": "블로그 제목 (40~50자, 뉴스 키워드 포함)",
  "meta_description": "검색 미리보기 (80자 이내)",
  "hashtags": ["태그1","태그2","태그3","태그4","태그5","태그6"],
  "body": "본문 전체 (마크다운, 1800자 이상, 뉴스 도입으로 시작)"
}}"""


def build_prompt(template_key: str, topic: dict, service: dict) -> str:
    tpl = TEMPLATES.get(template_key, TEMPLATES.get("info", ""))
    body = tpl.format(
        kw=topic["main_keyword"],
        svc=service["name"],
        usp=service["usp"],
        bigkinds=topic.get("bigkinds_stat", ""),
        kipris=topic.get("news_context", ""),
    )
    related = ", ".join(topic.get("related_keywords", []))

    return f"""당신은 한국 지식재산권·상표 전문 블로그 작가입니다.

━━━ 블로그 데이터 ━━━
메인 키워드 : {topic["main_keyword"]}
연관 키워드 : {related}
트렌드 점수 : {topic.get("trend_score", 0)}점
뉴스 통계   : {topic.get("bigkinds_stat", "")}
출원 통계   : {topic.get("news_context", "")}
홍보 서비스 : {service["name"]} — {service["usp"]}
서비스 URL  : {service["url"]}

{body}
{COMMON_RULES}

━━━ 출력 ━━━
아래 JSON만 출력 (코드블록 없이 순수 JSON):
{{
  "title": "블로그 제목 (40~50자)",
  "meta_description": "검색 미리보기 (80자 이내)",
  "hashtags": ["태그1","태그2","태그3","태그4","태그5","태그6"],
  "body": "본문 전체 (마크다운, 1800자 이상)"
}}"""
