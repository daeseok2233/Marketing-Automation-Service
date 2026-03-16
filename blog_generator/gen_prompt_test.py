import json
from config import KNOW_DIR, TEMPLATES_DIR


def _load_json(path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_service_info(service_id: str) -> dict:
    return _load_json(KNOW_DIR / "services.json")["services"][service_id]


def get_blog_info(blog_id: str) -> dict:
    return _load_json(KNOW_DIR / "blogs.json")["blogs"][blog_id]


def get_template(template_id: str) -> dict:
    return _load_json(TEMPLATES_DIR / f"{template_id}.json")


def build_prompt(
    topic: str,
    blog_code: str,
    template_id: str,
    service_id: str,
    data: dict = None,  # 외부 데이터 주입 (bigkinds, kipris 등)
) -> str:
    service  = get_service_info(service_id)
    blog     = get_blog_info(blog_code)
    template = get_template(template_id)
    data     = data or {}

    structure = json.dumps(template["structure"], ensure_ascii=False, indent=2)
    example_titles = "\n".join(f"  - {e}" for e in template.get("example_titles", []))

    return f"""\
당신은 {blog["name"]}의 블로그 콘텐츠 작성 전문가입니다.

━━━ 작성 주제 ━━━
{topic}

━━━ 템플릿: {template["name"]} ━━━
{structure}

━━━ 제목 예시 ━━━
{example_titles}

━━━ 데이터 ━━━
서비스명 : {service["name"]}
서비스 USP : {service["usp"]}
빅카인즈 : {data.get("bigkinds", "")}
KIPRIS   : {data.get("kipris", "")}

━━━ 출력 규칙 ━━━
- 아래 JSON만 출력 (코드블록 없이 순수 JSON)
- sections[0] = 서문, sections[-1] = 결론
- sections 최소 5개 이상
- hashtags 8~15개, # 접두사 포함
- event 없으면 빈 문자열

━━━ 출력 형식 ━━━
{{
  "title": "블로그 제목 (40~50자)",
  "sections": [
    {{"heading": "서문 소제목", "content": "서문 내용 (300자 이상)"}},
    {{"heading": "본론 소제목1", "content": "트렌드 설명 + 사업 예시 + 상품 분류 (300자 이상)"}},
    {{"heading": "본론 소제목2", "content": "트렌드 설명 + 사업 예시 + 상품 분류 (300자 이상)"}},
    {{"heading": "본론 소제목3", "content": "트렌드 설명 + 사업 예시 + 상품 분류 (300자 이상)"}},
    {{"heading": "결론 소제목", "content": "상표 출원 중요성 + {service['name']} 언급 (200자 이상)"}}
  ],
  "cta": "CTA 한 줄",
  "event": "이벤트 문구 또는 빈 문자열",
  "hashtags": ["#태그1", "#태그2", "..."]
}}"""