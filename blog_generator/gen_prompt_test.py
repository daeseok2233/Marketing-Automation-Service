import json
from config import KNOW_DIR, TEMPLATES_DIR


# ========================
# 데이터 로더
# ========================

def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_service_info(service_id: str) -> dict:
    return _load_json(KNOW_DIR / "services.json")["services"][service_id]


def get_blog_info(blog_id: str) -> dict:
    return _load_json(KNOW_DIR / "blogs.json")["blogs"][blog_id]


def get_template(template_id: str) -> dict:
    return _load_json(TEMPLATES_DIR / f"{template_id}.json")


# ========================
# 프롬프트 빌더
# ========================

def build_prompt(
    topic: str,
    blog_code: str,
    template_id: str,
    service_id: str,
) -> str:
    service  = get_service_info(service_id)
    blog     = get_blog_info(blog_code)
    template = get_template(template_id)

    structure = "\n".join(template["structure"]).format(
        kw=topic,
        svc=service["name"],
        usp=service["usp"],
        bigkinds="",  # 필요 시 외부에서 주입
        kipris="",
    )

    example_titles = "\n".join(f"  - {e}" for e in template.get("example_titles", []))

    return f"""\
당신은 {blog["name"]}의 블로그 콘텐츠 작성 전문가입니다.

━━━ 템플릿: {template["name"]} ━━━
{structure}

━━━ 제목 예시 ━━━
{example_titles}

━━━ 출력 ━━━

아래 JSON만 출력 (코드블록 없이 순수 JSON):
{{
  "title": "블로그 제목 (40~50자, 뉴스 키워드 포함)",
  "meta_description": "검색 미리보기 (80자 이내)",
  "hashtags": ["태그1","태그2","태그3","태그4","태그5","태그6"],
  "intro": "도입부 전체 — 뉴스 훅으로 시작, 3~4문장 (300자 이상)",
  "body": [
    {{"heading": "소제목1 (의문문)", "content": "본문 내용 (300자 이상)"}},
    {{"heading": "소제목2 (의문문)", "content": "본문 내용 (300자 이상)"}},
    {{"heading": "소제목3 (의문문)", "content": "본문 내용 (300자 이상)"}}
  ],
  "conclusion": "마무리 문단 — 뉴스 키워드 재언급 + 서비스 자연스러운 언급 (200자 이상)",
  "cta": "서비스 CTA 한 줄"
}}"""