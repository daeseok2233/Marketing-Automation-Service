"""글 생성 — 기획 결과에서 선택한 기사 + 템플릿으로 블로그 글을 LLM이 작성."""

import json
from pathlib import Path

import streamlit as st


def _parse_llm_output(raw: str):
    """LLM 출력 → (title, slots) 파싱."""
    lines = raw.split("\n")
    title = ""
    slots = {}
    current_slot = None
    current_lines = []
    heading_idx = 0
    title_found = False

    for line in lines:
        l = line.strip()

        # 제목
        if not title_found and (l.startswith("제목:") or (l.startswith("##") and heading_idx == 0)):
            if l.startswith("제목:"):
                title = l.split(":", 1)[1].strip()
            else:
                title = l.lstrip("#").strip()
            title_found = True
            continue

        # 해시태그
        if l.startswith("#") and l.count("#") >= 3 and not l.startswith("##"):
            slots["해시태그"] = l
            continue

        # 소제목
        is_heading = False
        heading_text = ""
        if l.startswith("##"):
            is_heading = True
            heading_text = l.lstrip("#").strip()
        elif l.startswith("소제목:") or l.startswith("소제목 :"):
            is_heading = True
            heading_text = l.split(":", 1)[1].strip()

        if is_heading:
            if current_slot and current_lines:
                slots[current_slot] = "\n".join(current_lines)
            heading_idx += 1
            slots[f"소제목{heading_idx}"] = heading_text
            current_slot = f"본문{heading_idx}"
            current_lines = []
            continue

        # 본문
        if current_slot:
            if l:
                current_lines.append(l)
        elif title_found and l and heading_idx == 0:
            if "도입" not in slots:
                slots["도입"] = l
            else:
                slots["도입"] += "\n" + l

    if current_slot and current_lines:
        slots[current_slot] = "\n".join(current_lines)

    # QA 분리 (본문에 Q&A가 섞인 경우)
    for key in list(slots.keys()):
        val = slots[key]
        if "Q:" in val or "Q." in val or "질문" in val:
            parts = val.split("\n")
            qa_start = -1
            for idx, p in enumerate(parts):
                if "Q:" in p or "Q." in p or "질문" in p:
                    qa_start = idx
                    break
            if qa_start > 0:
                slots[key] = "\n".join(parts[:qa_start])
                slots["QA"] = "\n".join(parts[qa_start:])

    return title, slots


def _render_preview(title: str, slots: dict, structure: list):
    """structure 기반 HTML 미리보기."""
    html = '<div style="font-family: Malgun Gothic, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">'
    if title:
        html += f'<h1 style="font-size: 1.8em; margin-bottom: 20px;">{title}</h1>'

    for item in structure:
        t = item.get("type", "")
        slot = item.get("slot", "")
        size = item.get("size", 15)
        content = item.get("content", "")

        if t == "blank":
            html += "<br>"
        elif t == "image":
            if "썸네일" in content:
                html += '<div style="background: #f0f0f0; padding: 20px; text-align: center; margin: 10px 0; border-radius: 8px;">[썸네일 이미지]</div>'
            elif "쿠폰" in content:
                html += '<div style="background: #e3f2fd; padding: 15px; text-align: center; margin: 10px 0; border-radius: 8px;">[쿠폰 이미지]</div>'
            else:
                html += '<div style="background: #f5f5f5; padding: 15px; text-align: center; margin: 10px 0; border-radius: 8px;">[서비스 이미지]</div>'
        elif t == "heading":
            text = slots.get(slot, f"[{slot}]")
            font_size = {24: "1.6em", 19: "1.3em", 17: "1.1em"}.get(size, "1.2em")
            html += f'<h2 style="font-size: {font_size}; font-weight: bold; margin: 20px 0 10px 0;">{text}</h2>'
        elif t == "text":
            text = slots.get(slot, f"[{slot}]")
            text_html = text.replace("\n", "<br>")
            html += f'<p style="font-size: {size}px; line-height: 1.8; margin: 5px 0;">{text_html}</p>'
        elif t == "quote":
            text = slots.get(slot, f"[{slot}]")
            html += f'<blockquote style="border-left: 3px solid #ccc; padding: 10px 15px; margin: 10px 0; color: #555;">{text}</blockquote>'
        elif t == "hashtags":
            text = slots.get(slot, "")
            html += f'<p style="color: #0068c3; margin-top: 20px;">{text}</p>'

    html += "</div>"
    return html


VALID_TEMPLATES = [
    "local_event", "local_issue", "local_trend",
    "event", "newsjacking", "dispute_report", "warning",
    "policy", "statistics", "success_story",
]


def build_generation_prompt(article: dict, template: str, blog_id: str, reason: str = "") -> tuple[str, dict]:
    """글 생성 프롬프트와 템플릿 데이터를 함께 반환 (스케줄러+UI 공용)."""
    tpl_path = Path(f"data/templates/{template}.json")
    tpl_data = json.loads(tpl_path.read_text(encoding="utf-8")) if tpl_path.exists() else {}
    prompt_tpl = tpl_data.get("prompt_template", "")

    blogs_json = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))
    blog_info = blogs_json["blogs"].get(blog_id, {})
    blog_theme = blog_info.get("theme", "")

    prompt = f"""당신은 전문 마크뷰/마크픽/마크패스 서비스 블로그 글쓴이다.

## 블로그 정보
{blog_theme}

서비스 정보:
- 마크뷰: AI 상표 검색 (유사발음·이미지 검색)
- 마크패스: 상표 출원 자동화 (출원서/의견서/보정서 자동작성, AI 지정상품 추천)
- 마크픽: 상표 출원 대행 (셀프 출원 지원/브랜드 네이밍/상표등록 침해 가능성/위조상품 무단도용 상표 모니터링)

## 레퍼런스 (이 기사를 활용해서 글을 작성)
제목: {article.get('title', '')}
내용: {article.get('description', '(내용 없음)')}
활용 방향: {reason}

## 규칙
- 기사의 팩트(수치, 지역, 이벤트명 등을)를 활용할 것
- 자연스럽게 상표/브랜드 보호 → 마크뷰/마크패스/마크픽 서비스로 연결
- 허구 사례/통계 금지
- 친근하고 실용적인 톤
- title에 핵심 키워드 포함
- intro 초반에 핵심 정의 포함
- body에 Q&A 형식 1개 이상 포함
- 이모지 적절히 활용 (✔ 📊 🛡 📌 등)
- 짧은 문장, 줄바꿈 자주 사용 (한 문장에 하나의 정보만)
- 마크다운(**, ##, *, - 등) 절대 사용 금지. 텍스트만 작성
- 출력 형식 필수 준수:
  · 제목 줄은 반드시 "제목: " 으로 시작
  · 소제목 줄은 반드시 "소제목: " 으로 시작 (이 접두어를 떼면 안 됨)
  · 해시태그는 마지막 줄에 # 으로 시작하는 한 줄로


## 템플릿
제목: {{30자 이내, 기사의 핵심 키워드 포함}}

{prompt_tpl}"""
    return prompt, tpl_data


def generate_post(article: dict, template: str, blog_id: str, reason: str = "") -> dict | None:
    """기사 + 템플릿 → 발행 가능한 post dict 반환 (스케줄러 호출용).

    Returns:
        {"title": str, "slots": dict, "structure": list, "template": str} 또는 None
    """
    from model import generate as llm_generate

    if template not in VALID_TEMPLATES:
        template = "local_issue"

    prompt, tpl_data = build_generation_prompt(article, template, blog_id, reason)
    result = llm_generate(prompt)
    text = result.get("text", "") if result else ""
    if not text:
        return None

    title, slots = _parse_llm_output(text)
    if not title or not slots:
        return None

    return {
        "title": title,
        "slots": slots,
        "structure": tpl_data.get("structure", []),
        "template": template,
    }


def render():
    st.header("글 생성")
    st.caption("기획 결과에서 선택한 기사 + 템플릿으로 블로그 글 생성")

    if "gen_result" not in st.session_state:
        st.session_state["gen_result"] = None

    plan_results = st.session_state.get("plan_results")
    if not plan_results:
        st.info("먼저 글 기획을 실행하세요.")
        return

    plan_blog = st.session_state.get("plan_blog", "blog_02")

    # 기사 선택
    article_options = []
    for i, r in enumerate(plan_results):
        score_line = [l for l in r["response"].split("\n") if "점수:" in l]
        score = score_line[0].split(":")[-1].strip() if score_line else "?"
        tpl_line = [l for l in r["response"].split("\n") if "템플릿:" in l]
        tpl = tpl_line[0].split(":")[-1].strip() if tpl_line else "?"
        article_options.append(f"{i+1}. [점수:{score}] [{tpl}] {r['article']['title'][:40]}")

    selected_idx = st.selectbox(
        "글 생성할 기사 선택", range(len(article_options)),
        format_func=lambda x: article_options[x], key="gen_select",
    )

    selected = plan_results[selected_idx]
    article = selected["article"]
    plan_response = selected["response"]

    # 템플릿 자동 검출 (plan 단계에서 LLM이 선택한 템플릿)
    tpl_line = [l for l in plan_response.split("\n") if "템플릿:" in l]
    detected_tpl = tpl_line[0].split(":")[-1].strip() if tpl_line else "local_issue"

    # plan.py의 TPL_DESC와 동일한 10개 템플릿 (기사 의존형)
    tpl_options = [
        "local_event", "local_issue", "local_trend",
        "event", "newsjacking", "dispute_report", "warning",
        "policy", "statistics", "success_story",
    ]
    if detected_tpl not in tpl_options:
        detected_tpl = "local_issue"
    gen_template = st.selectbox(
        "템플릿", tpl_options,
        index=tpl_options.index(detected_tpl),
        key="gen_tpl",
    )

    tpl_path = Path(f"data/templates/{gen_template}.json")
    tpl_data = json.loads(tpl_path.read_text(encoding="utf-8")) if tpl_path.exists() else {}
    prompt_tpl = tpl_data.get("prompt_template", "")

    reason_line = [l for l in plan_response.split("\n") if "이유:" in l]
    reason = reason_line[0].split(":")[-1].strip() if reason_line else ""

    # 블로그 정보
    blogs_json_gen = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))
    blog_info_gen = blogs_json_gen["blogs"].get(plan_blog, {})
    blog_theme = blog_info_gen.get("theme", "")

    gen_prompt = f"""당신은 전문 마크뷰/마크픽/마크패스 서비스 블로그 글쓴이다.

## 블로그 정보
{blog_theme}

서비스 정보:
- 마크뷰: AI 상표 검색 (유사발음·이미지 검색)
- 마크패스: 상표 출원 자동화 (출원서/의견서/보정서 자동작성, AI 지정상품 추천)
- 마크픽: 상표 출원 대행 (셀프 출원 지원/브랜드 네이밍/상표등록 침해 가능성/위조상품 무단도용 상표 모니터링)

## 레퍼런스 (이 기사를 활용해서 글을 작성)
제목: {article['title']}
내용: {article.get('description', '(내용 없음)')}
활용 방향: {reason}

## 규칙
- 기사의 팩트(수치, 지역, 이벤트명 등을)를 활용할 것
- 자연스럽게 상표/브랜드 보호 → 마크뷰/마크패스/마크픽 서비스로 연결
- 허구 사례/통계 금지
- 친근하고 실용적인 톤
- title에 핵심 키워드 포함
- intro 초반에 핵심 정의 포함
- body에 Q&A 형식 1개 이상 포함
- 이모지 적절히 활용 (✔ 📊 🛡 📌 등)
- 짧은 문장, 줄바꿈 자주 사용 (한 문장에 하나의 정보만)
- 마크다운(**, ##, *, - 등) 절대 사용 금지. 텍스트만 작성
- 출력 형식 필수 준수:
  · 제목 줄은 반드시 "제목: " 으로 시작
  · 소제목 줄은 반드시 "소제목: " 으로 시작 (이 접두어를 떼면 안 됨)
  · 해시태그는 마지막 줄에 # 으로 시작하는 한 줄로


## 템플릿
제목: {{30자 이내, 기사의 핵심 키워드 포함}}

{prompt_tpl}"""

    with st.expander("글 생성 프롬프트 편집"):
        gen_prompt = st.text_area("프롬프트", gen_prompt, height=500, key="gen_prompt_edit")

    if st.button("글 생성", type="primary", key="run_gen"):
        with st.spinner("블로그 글 생성 중..."):
            from model import generate as llm_generate
            result = llm_generate(gen_prompt)
            if result.get("text"):
                st.session_state["gen_result"] = result["text"]
                st.success(f"글 생성 완료 (모델: {result['model']})")

    if not st.session_state.get("gen_result"):
        return

    raw = st.session_state["gen_result"]
    st.subheader("생성된 글 (원문)")
    st.text_area("LLM 출력", raw, height=300)

    # 파싱 + 미리보기
    title, slots = _parse_llm_output(raw)
    structure = tpl_data.get("structure", [])

    st.subheader("Playwright 발행 미리보기")
    st.caption(f"템플릿: {gen_template} / structure 기반")
    st.html(_render_preview(title, slots, structure))

    with st.expander("Playwright 명령 상세"):
        for item in structure:
            t = item.get("type", "")
            slot = item.get("slot", "")
            size = item.get("size", "")
            content = item.get("content", "")
            text = slots.get(slot, "") if slot else ""

            if t == "blank":
                st.markdown("- [빈줄]")
            elif t == "image":
                st.markdown(f"- [이미지] {content}")
            elif t == "heading":
                st.markdown(f"- [H{size}] {text[:40]}")
            elif t == "text":
                st.markdown(f"- [텍스트 {size}pt] {text[:50]}...")
            elif t == "hashtags":
                st.markdown(f"- [해시태그] {text[:50]}")

    # 다음 단계(발행)에서 사용할 데이터를 세션에 저장
    st.session_state["gen_title"] = title
    st.session_state["gen_slots"] = slots
    st.session_state["gen_structure"] = structure
    st.session_state["gen_template"] = gen_template
