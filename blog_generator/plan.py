"""글 기획 — 수집된 뉴스에서 LLM이 템플릿별 활용 가능 기사를 선별."""

import json
from datetime import datetime
from pathlib import Path

import streamlit as st


# 블로그별 키워드 매핑 (collect 단계의 키워드 풀에서 블로그 타겟에 맞게 필터)
BLOG_KEYWORDS = {
    "blog_02": ["상표", "특허", "창업", "브랜드", "신제품"],
    "blog_03": ["상표", "지식재산", "프랜차이즈", "상호명", "특허"],
    "blog_04": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌"],
    "blog_05": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌"],
    "blog_06": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌"],
    "blog_07": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌"],
}


TPL_DESC = """- local_event: 지역 행사/축제/박람회/공모전 등 소식.
  반드시 특정 지역(시/군/구/동/읍/면)이 포함된 기사만 선택할 것
  행사 정보를 소개하고 자연스럽게 상표등록 필요성을 연결.
  예: "송파 벚꽃축제 개막", "대전 창업 박람회 개최"

- local_issue: 지역 상권/사업자 관련 뉴스나 사건.
  반드시 특정 지역이 포함된 기사만 선택할 것
  이슈를 소개하고 상표/브랜드 보호 필요성을 연결.
  예: "A지역 프랜차이즈 상표 분쟁", "B 지역 자영업 폐업률 증가", "C 지역 위조상품 단속"

- local_trend: 지역 창업/상권 트렌드.
  반드시 특정 지역이 포함된 기사만 선택할 것
  트렌드를 소개하고 경쟁 속 브랜드 차별화를 위한 상표등록을 연결.
  예: "강릉 카페 창업 증가", "서울시 소상공인 지원사업 확대"

- event: 일반 상표/브랜드 관련 사건이나 이슈.
  사건을 소개하고 상표/브랜드 보호 필요성을 연결.
  예: "갤럭시 S26 출시, 삼성은 상표를 어떻게 보호할까?", "유사 상표로 소송당한 스타트업, 어떻게 됐을까?"

- newsjacking: 트렌딩 키워드/화제를 상표 주제와 연결.
  화제의 사건/인물/콘텐츠를 끌어와 상표 보호 메시지로 연결.
  예: "넷플릭스 오징어게임3 흥행, 오징어게임 상표는 누구 것?", "BTS 컴백에 불법 굿즈, 상표권 침해 어떻게 대응?"

- dispute_report: 실제 상표 분쟁 사례 심층 분석.
  분쟁 경위·판결·교훈을 정리하는 리포트 형식.
  예: "이 두 브랜드, 왜 상표 분쟁까지 갔을까?", "유사 상표 기준, 실제 사례로 보면 이렇게 다릅니다"

- warning: 위험 사례·흔한 실수 경고.
  실수 시나리오를 보여주고 예방책을 제시.
  예: "사업자등록만 하고 상표 안 냈다가 벌어지는 일", "상표 출원 전 이것만은 하지 마세요"

- policy: 정책/법령 변경 안내.
  특허청 고시, 상표법 개정, 수수료/제도 변경 등을 사업자 관점에서 해설.
  예: "2026년 상표법 개정안 통과, 사업자가 알아야 할 변화", "특허청 출원 수수료 인하, 누구에게 유리할까?"

- statistics: 공식 통계·리포트 데이터 분석.
  특허청·산업계 통계나 조사 결과를 인용해 트렌드와 시사점을 정리.
  예: "2025년 상표 출원 50만건 돌파, 어떤 분야가 늘었나?", "스타트업 상표 등록률 30% 증가, 그 의미는?"

- success_story: 상표를 잘 챙겨 성공한 브랜드 사례.
  성공 비결을 상표 보호·브랜드 전략 관점에서 분석.
  예: "이 카페가 5년간 4개 상표로 보호한 비결", "K-뷰티 OO 브랜드, 해외 진출 성공기\""""


def _build_default_prompt():
    return f"""당신은 전문 마크뷰/마크패스/마크픽 서비스 블로그 콘텐츠 기획자이다.

서비스 내용:
- 마크뷰: AI 상표 검색 (유사발음·이미지 검색)
- 마크패스: 상표 출원 자동화 (출원서/의견서/보정서 자동작성, AI 지정상품 추천)
- 마크픽: 상표 출원 대행 (셀프 출원 지원/브랜드 네이밍/상표등록 침해 가능성/위조상품 무단도용 상표 모니터링)

아래는 "{{keyword}}" 키워드로 검색한 뉴스 기사 제목과 내용이다.

제목: {{title}}
내용: {{description}}

---

이 기사가 마크뷰/마크패스/마크픽 서비스 블로그 포스팅에 사용가능한 래퍼런스인지 판단해라.

## 판단 기준
- 이 기사 내용과 상표/브랜드 보호를 자연스럽게 연결할 수 있는가?
- 아래 템플릿에 적절히 잘 활용한 정보를 담고 있는가?
- 활용 가능성을 100점 만점으로 평가
- 90점 이상인 템플릿만 선택

## 매칭할 템플릿
{TPL_DESC}

## 출력 형식
점수: (0~100)
템플릿: (템플릿명 / 해당없음)
기획: (어떤 흐름으로 글을 쓰면 좋을지 200자 이내)"""


def _parse_eval_response(response: str) -> dict:
    """LLM 평가 응답에서 점수/템플릿/사유 추출."""
    score = 0
    template = ""
    reason = ""
    for line in response.split("\n"):
        if "점수:" in line:
            digits = "".join(c for c in line.split(":", 1)[-1] if c.isdigit())
            if digits:
                try:
                    score = int(digits[:3])
                except ValueError:
                    pass
        elif "템플릿:" in line:
            template = line.split(":", 1)[-1].strip()
        elif "기획:" in line or "이유:" in line:
            reason = line.split(":", 1)[-1].strip()
    return {"score": score, "template": template, "reason": reason}


def evaluate_all_articles(max_evaluate: int = 200) -> list[dict]:
    """오늘 수집된 모든 뉴스 기사를 한 번에 평가 (스케줄러 호출용).

    블로그별 필터링 없이 LLM이 점수 + 템플릿 매칭만 판단.
    같은 평가 결과를 모든 블로그가 공유하므로 LLM 비용이 1/6.

    Args:
        max_evaluate: LLM 평가 한도 (비용 cap)

    Returns:
        [{"article": {...}, "score": int, "template": str, "reason": str, "response": str}]
        score >= 90 이고 template이 유효한 항목만 반환.
    """
    from model import generate as llm_generate

    today_str = datetime.now().strftime("%Y%m%d")
    news_file = Path(f"data/collected/{today_str}_daily_news.json")
    if not news_file.exists():
        return []

    all_news = json.loads(news_file.read_text(encoding="utf-8"))
    if not all_news:
        return []

    prompt_tmpl = _build_default_prompt()
    results = []

    for article in all_news[:max_evaluate]:
        prompt = prompt_tmpl
        for k, v in [
            ("keyword", article.get("keyword", "")),
            ("title", article.get("title", "")),
            ("description", article.get("description", "(내용 없음)")),
        ]:
            prompt = prompt.replace("{{" + k + "}}", v).replace("{" + k + "}", v)

        result = llm_generate(prompt)
        text = result.get("text", "") if result else ""
        if not text:
            continue

        parsed = _parse_eval_response(text)
        if parsed["score"] < 90 or not parsed["template"]:
            continue

        results.append({
            "article": article,
            "score": parsed["score"],
            "template": parsed["template"],
            "reason": parsed["reason"],
            "response": text,
        })

    return results


def assign_to_blogs(scored_articles: list[dict], blog_configs: dict) -> dict[str, list[dict]]:
    """평가 결과를 블로그별로 배치. 같은 기사가 여러 블로그에 갈 수 있음.

    각 블로그는 자신의 templates 리스트에 매칭되는 기사 중 상위 N개(posts_per_day)를 받는다.

    Args:
        scored_articles: evaluate_all_articles() 반환값
        blog_configs: {blog_id: {"posts_per_day": int, ...}}

    Returns:
        {blog_id: [scored_article, ...]} (점수 높은 순)
    """
    blogs_json = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))

    # 점수 높은 순으로 정렬
    sorted_articles = sorted(scored_articles, key=lambda x: x.get("score", 0), reverse=True)

    queues: dict[str, list[dict]] = {}
    for blog_id, config in blog_configs.items():
        blog_info = blogs_json["blogs"].get(blog_id, {})
        blog_templates = set(blog_info.get("templates", []))
        if not blog_templates:
            queues[blog_id] = []
            continue

        target = config.get("posts_per_day", 10)
        eligible = [a for a in sorted_articles if a["template"] in blog_templates]
        queues[blog_id] = eligible[:target]

    return queues


def render():
    st.header("글 기획")
    st.caption("수집된 뉴스에서 템플릿별로 활용할만한 기사를 LLM이 선별")

    today_str = datetime.now().strftime("%Y%m%d")
    news_file = Path(f"data/collected/{today_str}_daily_news.json")

    plan_blog = st.selectbox(
        "블로그 선택",
        ["blog_02", "blog_03", "blog_04", "blog_05", "blog_06", "blog_07"],
        key="plan_blog",
    )
    # st.session_state["plan_blog"]는 selectbox의 key="plan_blog"가 자동으로 채워줌

    plan_keywords = BLOG_KEYWORDS.get(plan_blog, [])
    st.markdown(f"**참고 키워드**: {', '.join(plan_keywords)}")

    if not news_file.exists():
        st.warning("뉴스 데이터가 없습니다. 먼저 일일 수집을 실행하세요.")
        return

    all_news = json.loads(news_file.read_text(encoding="utf-8"))
    filtered_news = [n for n in all_news if n.get("keyword", "") in plan_keywords]
    st.markdown(f"**필터된 뉴스**: {len(filtered_news)}건 (전체 {len(all_news)}건 중)")

    prompt_template = _build_default_prompt()

    with st.expander("프롬프트 템플릿 편집"):
        prompt_template = st.text_area(
            "기사 1건당 LLM에게 보내는 프롬프트",
            prompt_template, height=400, key="plan_prompt",
        )

    st.markdown(f"**평가할 기사**: {len(filtered_news)}건")
    if not filtered_news:
        return

    eval_count = st.slider(
        "평가할 기사 수 (테스트용)",
        1, min(len(filtered_news), 50), min(5, len(filtered_news)),
        key="eval_count",
    )

    if st.button("글 기획 실행 (기사별 개별 판단)", type="primary", key="run_plan"):
        from model import generate as llm_generate
        results = []
        target_news = filtered_news[:eval_count]
        progress = st.progress(0)
        status = st.empty()

        for i, article in enumerate(target_news):
            status.text(f"[{i+1}/{len(target_news)}] {article['title'][:40]}...")
            progress.progress((i + 1) / len(target_news))

            prompt = prompt_template
            prompt = prompt.replace("{{keyword}}", article.get("keyword", ""))
            prompt = prompt.replace("{keyword}", article.get("keyword", ""))
            prompt = prompt.replace("{{title}}", article.get("title", ""))
            prompt = prompt.replace("{title}", article.get("title", ""))
            prompt = prompt.replace("{{description}}", article.get("description", "(내용 없음)"))
            prompt = prompt.replace("{description}", article.get("description", "(내용 없음)"))

            result = llm_generate(prompt)
            if result.get("text"):
                results.append({"article": article, "response": result["text"]})

        st.session_state["plan_results"] = results
        st.success(f"기획 완료: {len(results)}건 평가")

    if st.session_state.get("plan_results"):
        st.subheader("기획 결과")
        for i, r in enumerate(st.session_state["plan_results"]):
            article = r["article"]
            response = r["response"]
            score_line = [l for l in response.split("\n") if "점수:" in l]
            score = score_line[0].split(":")[-1].strip() if score_line else "?"

            with st.expander(f"{i+1}. [{article['keyword']}] [점수:{score}] {article['title'][:50]}"):
                st.markdown(f"**기사 제목**: {article['title']}")
                if article.get("description"):
                    st.markdown(f"**기사 내용**: {article['description'][:150]}")
                st.divider()
                st.markdown("**LLM 판단:**")
                st.markdown(response)
