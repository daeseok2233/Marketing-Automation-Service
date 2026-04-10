"""글 기획 파이프라인 v2.

템플릿별로 뉴스 목록에서 활용할만한 기사를 LLM이 선별.
선별된 기사의 제목+내용 = 레퍼런스.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from model import generate


def _load_template(name: str) -> dict:
    """템플릿 JSON 로드."""
    p = Path(f"data/templates/{name}.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_today_data() -> tuple[list, list]:
    """오늘 수집된 행사 + 뉴스 로드."""
    today = datetime.now().strftime("%Y%m%d")

    events = []
    f = Path(f"data/collected/{today}_events.json")
    if f.exists():
        events = json.loads(f.read_text(encoding="utf-8"))

    news = []
    f = Path(f"data/collected/{today}_daily_news.json")
    if f.exists():
        news = json.loads(f.read_text(encoding="utf-8"))

    return events, news


def select_articles_for_template(template_name: str, news: list, events: list = None) -> list[int]:
    """LLM이 템플릿에 활용할만한 기사 번호를 선별."""
    tpl = _load_template(template_name)
    tpl_desc = tpl.get("_comment", tpl.get("name", template_name))
    example_titles = tpl.get("example_titles", [])
    writing_rules = tpl.get("writing_rules", [])

    # 뉴스 목록 (번호 붙여서)
    news_lines = []
    for i, n in enumerate(news):
        title = n.get("title", "")
        desc = n.get("description", "")
        line = f"[{i}] {title}"
        if desc:
            line += f" — {desc[:80]}"
        news_lines.append(line)

    # 행사 데이터 (local_event용)
    events_text = ""
    if events and "event" in template_name:
        events_lines = [f"[E{i}] {e['name']} | {e['period']} | {e['place']}"
                        for i, e in enumerate(events)]
        events_text = f"\n\n## 행사 데이터\n" + "\n".join(events_lines)

    prompt = f"""너는 블로그 콘텐츠 기획자다.

## 템플릿: {template_name}
설명: {tpl_desc}
예시 제목: {', '.join(example_titles[:3])}
작성 규칙: {', '.join(writing_rules[:3])}

## 뉴스 목록
{chr(10).join(news_lines)}
{events_text}

위 뉴스 목록에서 이 템플릿으로 블로그 글을 쓸 수 있는 기사를 골라줘.
번호만 응답. 예: [0, 3, 7, 12]"""

    result = generate(prompt, max_tokens=1024)
    raw = result["text"].strip()

    # 번호 파싱
    numbers = re.findall(r"\d+", raw)
    indices = [int(n) for n in numbers if int(n) < len(news)]

    # 중복 제거
    return list(dict.fromkeys(indices))


def plan_blog_topics(blog_id: str, count: int = 30) -> list[dict]:
    """블로그별 글 기획.

    템플릿별로 LLM이 기사 선별 → 선별된 기사 = 주제 + 레퍼런스.
    """
    blogs_data = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))
    blog_info = blogs_data.get("blogs", {}).get(blog_id, {})
    templates = blog_info.get("templates", ["local_event", "local_issue", "local_trend"])

    events, news = _load_today_data()

    # 블로그별 관련 키워드 필터
    BLOG_KEYWORDS = {
        "blog_02": ["상표", "특허", "창업", "브랜드", "신제품"],
        "blog_03": ["상표", "지식재산", "프랜차이즈", "상호명", "특허"],
        "blog_04": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌", "지원사업"],
        "blog_05": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌", "지원사업"],
        "blog_06": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌", "지원사업"],
        "blog_07": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌", "지원사업"],
    }

    allowed_keywords = BLOG_KEYWORDS.get(blog_id, [])
    if allowed_keywords:
        filtered_news = [n for n in news if n.get("keyword", "") in allowed_keywords]
    else:
        filtered_news = news

    print(f"  [기획] 데이터: 행사 {len(events)}건, 뉴스 {len(news)}건 → 필터링 후 {len(filtered_news)}건")

    all_plans = []

    for template_name in templates:
        print(f"  [기획] {template_name} — 기사 선별 중...")
        indices = select_articles_for_template(template_name, filtered_news, events)
        print(f"  [기획] {template_name} → {len(indices)}개 기사 선별")


        for idx in indices:
            article = filtered_news[idx]
            all_plans.append({
                "template": template_name,
                "article_title": article["title"],
                "article_desc": article.get("description", ""),
                "article_link": article.get("link", ""),
                "article_keyword": article.get("keyword", ""),
                "article_source": article.get("source", ""),
            })

    # count 제한
    all_plans = all_plans[:count]

    # 저장
    today = datetime.now().strftime("%Y%m%d")
    out_dir = Path("data/generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today}_{blog_id}_plan.json"
    out_path.write_text(json.dumps(all_plans, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [기획] 저장: {out_path} ({len(all_plans)}개)")

    return all_plans


if __name__ == "__main__":
    import sys
    blog_id = sys.argv[1] if len(sys.argv) > 1 else "blog_07"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    plans = plan_blog_topics(blog_id, count)
    for i, p in enumerate(plans):
        print(f"\n{i+1}. [{p['template']}] {p['article_title'][:50]}")
        if p.get("article_desc"):
            print(f"   설명: {p['article_desc'][:60]}")
