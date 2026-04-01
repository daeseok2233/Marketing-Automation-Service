"""파이프라인 과정을 마크다운으로 기록한다."""

from datetime import datetime


def build_process_log(step_num, topic, ref_queries, ref_news, ref_blogs, blog):
    """파이프라인 과정을 마크다운으로 정리."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "---",
        "",
        f"## 파이프라인 생성 과정 (#{step_num})",
        f"생성 시각: {now}",
        "",
        "### 1단계: AI 플래너 — 주제 계획",
        "",
        "AI가 아래 정보를 읽고 주제를 기획했습니다:",
        "- data/templates/*.json (블로그 템플릿 14종)",
        "- data/service_data/services.json (마크클라우드 서비스 정보)",
        "- data/service_data/blogs.json (블로그 계정 정보)",
        "- data/collected/ (오늘 수집된 트렌드·뉴스·키워드 데이터)",
        "- data/schedule_state.json (이전에 사용한 지역+업종 조합)",
        "",
        "AI 판단 결과:",
        f"- 지역: {topic.get('region', '')}",
        f"- 업종: {topic.get('business', '')}",
        f"- 앵글: {topic.get('angle', '')}",
        f"- 제목 아이디어: {topic.get('title_idea', '')}",
        "",
        "### 2단계: 타겟 데이터 수집",
        "",
        "AI가 정한 검색 쿼리로 네이버 API를 호출했습니다:",
        "",
    ]

    for q in ref_queries:
        lines.append(f'검색 쿼리: "{q}"')
    lines.append("")

    lines.append("네이버 뉴스 API (openapi.naver.com/v1/search/news.json)")
    if ref_news:
        for n in ref_news:
            lines.append(f"- {n.get('title', '')}")
    else:
        lines.append("- 결과 없음")
    lines.append("")

    lines.append("네이버 블로그 API (openapi.naver.com/v1/search/blog.json)")
    if ref_blogs:
        for b in ref_blogs:
            lines.append(f"- {b.get('title', '')}")
    else:
        lines.append("- 결과 없음")
    lines.append("")

    lines.extend([
        "### 3단계: 글 생성",
        "",
        f"- 사용 모델: {blog['model_info']['model']} ({blog['model_info']['provider']})",
        f"- 유저 프롬프트: 지역({topic.get('region', '')}) + 업종({topic.get('business', '')}) + 레퍼런스(뉴스 {len(ref_news)}건 + 블로그 {len(ref_blogs)}건)",
        f"- SEO 키워드: {', '.join(topic.get('keywords', []))}",
        f"- 생성된 본문: {len(blog.get('body', ''))}자",
        "",
        "### 전체 흐름 요약",
        "",
        "```",
        "템플릿 + 서비스정보 + 수집데이터",
        "         │",
        "    [AI 플래너]",
        "         │",
        f"    주제: {topic.get('region', '')} × {topic.get('business', '')}",
        f"    검색쿼리: {ref_queries}",
        "         │",
        "    [네이버 API 검색]",
        f"    뉴스 {len(ref_news)}건 + 블로그 {len(ref_blogs)}건",
        "         │",
        f"    [글 생성] ← {blog['model_info']['model']}",
        "         │",
        "    [노션 업로드]",
        "```",
    ])

    return "\n".join(lines)
