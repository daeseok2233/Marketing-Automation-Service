"""6개 블로그에 각각 1개씩 글 생성 테스트."""

from dotenv import load_dotenv
load_dotenv()

import json
from pathlib import Path
from datetime import datetime
from model import generate
from publisher.notion_upload import upload_to_notion
from publisher.docx_exporter import export_to_docx

today = datetime.now().strftime("%Y%m%d")
out = Path("data/generated")
out.mkdir(parents=True, exist_ok=True)

blogs = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))
services = json.loads(Path("data/service_data/services.json").read_text(encoding="utf-8"))

# 블로그별 생성 설정
BLOG_CONFIGS = [
    {
        "blog": "blog_01",
        "template": "beginner",
        "topic": "처음 상표 출원하는 1인 사업자를 위한 완벽 가이드",
        "style": "친근하고 쉬운 말투. 창업 초보자가 공감할 수 있는 톤. '~이에요', '~거든요' 구어체.",
    },
    {
        "blog": "blog_02",
        "template": "howto",
        "topic": "상표 출원 절차 총정리 — 준비부터 등록까지 단계별 안내",
        "style": "실무 중심, 신뢰감 있는 문체. 단계별로 명확하게 설명. 전문 용어는 괄호로 보충설명.",
    },
    {
        "blog": "blog_03",
        "template": "column",
        "topic": "상표 분쟁이 늘고 있습니다 — 변리사가 본 최근 트렌드와 대응 전략",
        "style": "변리사 전문가 톤. 격식체 사용. 분석적이고 권위 있는 문체. '~입니다', '~합니다'.",
    },
    {
        "blog": "blog_04",
        "template": "local_trend",
        "topic": None,  # AI 플래너가 결정
        "style": "local",
    },
    {
        "blog": "blog_05",
        "template": "local_issue",
        "topic": None,
        "style": "local",
    },
    {
        "blog": "blog_06",
        "template": "local_event",
        "topic": None,
        "style": "local",
    },
]

# 블로그별 시스템 프롬프트
def get_system_prompt(config, blog_info):
    template_data = {}
    tpl_path = Path(f"data/templates/{config['template']}.json")
    if tpl_path.exists():
        template_data = json.loads(tpl_path.read_text(encoding="utf-8"))

    return f"""당신은 마크클라우드(상표·디자인·특허 출원 서비스)의 블로그 작성자입니다.

## 블로그 정보
블로그명: {blog_info.get('name', '')}
블로그 성격: {blog_info.get('theme', '')}

## 글쓰기 스타일
{config['style']}

## ⚠️ 절대 금지
- 실존하지 않는 브랜드명, 사례, 통계 만들어내기 금지
- 과대광고 표현 금지 ("1위", "최고", "독보적" 등)
- 상표와 무관한 내용 금지

## 글쓰기 규칙
- 짧은 문장 (25자 이내), 문장마다 줄바꿈
- ✔ 👉 기호 적극 사용
- 소제목은 ## (H2)
- 핵심 메시지는 **굵은 글씨**
- 본문 길이: 2000~2500자
- 해시태그 20개 이상
- [서비스 이미지] 태그 2~3곳 삽입
- [CTA 이미지] 태그 마지막에 삽입

## 템플릿 구조
{json.dumps(template_data.get('structure', {}), ensure_ascii=False, indent=2)[:1000]}

## 서비스 정보
- 마크픽: 상표·디자인·특허 출원 대행 (순수 대행비 10만원)
- 마크뷰: AI 기반 상표 검색 (이미지·유사발음 검색)
- 마크클라우드: 통합 IP 관리 플랫폼

## CTA (마지막에 반드시 포함)
"마크뷰 블로그 보고 왔습니다" 라고 말씀해주시면
1만원 추가 할인이 적용됩니다."""


results = []

for i, config in enumerate(BLOG_CONFIGS):
    blog_key = config["blog"]
    blog_info = blogs["blogs"][blog_key]
    print(f"\n{'='*60}")
    print(f"  [{i+1}/6] {blog_key}: {blog_info['name'][:25]} ({config['template']})")
    print(f"{'='*60}")

    # blog_04~06은 기존 local 파이프라인
    if config["style"] == "local":
        from blog_generator.planner import plan_topics, search_for_topic
        from blog_generator.blog_writer import write_local_blog

        topics = plan_topics(count=1)
        topic = topics[0]
        ref = search_for_topic(topic)
        if ref.get("news"):
            topic["ref_news"] = "\n".join(f"- {n['title']}" for n in ref["news"])
        if ref.get("blogs"):
            topic["ref_blogs"] = "\n".join(f"- {b['title']}" for b in ref["blogs"])

        blog = write_local_blog(topic)

    # blog_01~03은 범용 프롬프트
    else:
        system = get_system_prompt(config, blog_info)
        prompt = f"""## 주제
{config['topic']}

## 출력 형식
제목: [포스팅 제목]
메타디스크립션: [150자 이내]

[본문 2000~2500자]

[해시태그 20개 이상]"""

        result = generate(prompt, system=system, max_tokens=4000)
        raw = result["text"]

        # 파싱
        title = ""
        meta = ""
        body = raw
        lines = raw.split("\n")
        body_start = 0
        for j, line in enumerate(lines):
            s = line.strip()
            if s.startswith("제목:"):
                title = s.split(":", 1)[1].strip().strip("[]\"")
                body_start = j + 1
            elif "메타디스크립션:" in s or "메타 디스크립션:" in s:
                meta = s.split(":", 1)[1].strip().strip("[]\"")
                body_start = j + 1
        if body_start > 0:
            body = "\n".join(lines[body_start:]).strip()
        if not title:
            title = config["topic"]

        blog = {
            "title": title,
            "meta_description": meta,
            "body": body,
            "model_info": {"model": result["model"], "provider": result["provider"]},
        }

    print(f"  제목: {blog.get('title', '')[:50]}")
    print(f"  본문: {len(blog.get('body', ''))}자")
    print(f"  모델: {blog['model_info']['model']}")

    # Word 저장
    import re
    safe_title = re.sub(r'[\\/*?:"<>|]', "", blog.get("title", ""))[:25]
    docx_path = export_to_docx(blog, str(out / f"{today}_{blog_key}_{safe_title}.docx"))

    # 노션 업로드
    url = upload_to_notion(blog, template_name=config["template"])
    blog["notion_url"] = url
    blog["blog"] = blog_key

    results.append(blog)

print(f"\n{'='*60}")
print(f"  완료! 6개 블로그 글 생성")
for i, r in enumerate(results):
    status = "✓" if r.get("body") else "✗"
    print(f"  {status} {r['blog']}: {r.get('title', '')[:45]}")
print(f"{'='*60}")
