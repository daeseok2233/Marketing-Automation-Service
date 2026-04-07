"""블로그 자동화 파이프라인 — Streamlit 대시보드."""

import csv
import json
import re
import streamlit as st
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="블로그 파이프라인", layout="wide")
st.title("블로그 자동화 파이프라인")

# ── 사이드바: 블로그 선택 ──
blogs_data = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))
blog_options = {bid: f"{bid} — {info['name']}" for bid, info in blogs_data["blogs"].items() if info.get("blog_url")}
selected_blog = st.sidebar.selectbox("블로그 선택", list(blog_options.keys()), format_func=lambda x: blog_options[x])

blog_info = blogs_data["blogs"][selected_blog]
st.sidebar.markdown(f"**테마**: {blog_info.get('theme', '')[:80]}...")
st.sidebar.markdown(f"**템플릿**: {', '.join(blog_info.get('templates', []))}")

# ── 세션 상태 초기화 ──
for key in ["topics", "selected_topic", "reference", "blog_result", "commands", "collected_data"]:
    if key not in st.session_state:
        st.session_state[key] = None


# ── 수집 데이터 로드 헬퍼 ──
def _load_collected_data() -> dict:
    """오늘 수집된 CSV 데이터를 로드."""
    today = datetime.now().strftime("%Y%m%d")
    collected = Path("data/collected")
    data = {}

    # 가장 최근 날짜 찾기 (오늘 없으면 가장 최근)
    dates = set()
    for f in collected.glob("*_naver_news.csv"):
        dates.add(f.name[:8])
    target_date = today if today in dates else (sorted(dates)[-1] if dates else "")

    if not target_date:
        return {"date": "없음", "trending": [], "datalab": [], "news": [], "suggest": []}

    # Google Trending
    f = collected / f"{target_date}_google_trending.csv"
    trending = []
    if f.exists():
        with open(f, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                trending.append({"keyword": row.get("keyword", ""), "traffic": row.get("traffic", "")})

    # Naver DataLab
    f = collected / f"{target_date}_naver_datalab.csv"
    datalab = []
    if f.exists():
        with open(f, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                datalab.append({"keyword": row.get("keyword", ""), "growth_rate": row.get("growth_rate", "0")})

    # Naver News
    f = collected / f"{target_date}_naver_news.csv"
    news = []
    if f.exists():
        with open(f, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                news.append({"title": row.get("title", ""), "source": row.get("source", "")})

    # Naver Suggest
    f = collected / f"{target_date}_naver_suggest.csv"
    suggest = []
    if f.exists():
        with open(f, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                suggest.append(row.get("suggest", ""))

    return {
        "date": target_date,
        "trending": trending[:20],
        "datalab": datalab,
        "news": news[:20],
        "suggest": list(set(suggest))[:30],
    }


# ── 탭 ──
tab0, step1, step2, step3, step4 = st.tabs([
    "0. 수집 데이터", "1. 주제 계획", "2. 데이터 수집", "3. 글 생성", "4. 미리보기"
])

# ============================================================
# STEP 0: 오늘 수집 데이터
# ============================================================
with tab0:
    st.header("수집 데이터 현황")

    if st.button("데이터 로드", type="primary", key="load_collected"):
        st.session_state.collected_data = _load_collected_data()

    # 자동 로드 (처음 접속 시)
    if st.session_state.collected_data is None:
        st.session_state.collected_data = _load_collected_data()

    cd = st.session_state.collected_data
    st.info(f"데이터 날짜: **{cd['date']}**")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader(f"구글 트렌딩 ({len(cd['trending'])}건)")
        if cd["trending"]:
            for t in cd["trending"][:15]:
                st.markdown(f"- **{t['keyword']}** ({t['traffic']})")
        else:
            st.caption("데이터 없음")

        st.subheader(f"네이버 자동완성 ({len(cd['suggest'])}건)")
        if cd["suggest"]:
            st.markdown(", ".join(f"`{s}`" for s in cd["suggest"][:20]))
        else:
            st.caption("데이터 없음")

    with col2:
        st.subheader(f"네이버 데이터랩 ({len(cd['datalab'])}건)")
        if cd["datalab"]:
            rising = [d for d in cd["datalab"] if float(d.get("growth_rate", "0") or "0") > 0]
            for d in rising[:15]:
                st.markdown(f"- **{d['keyword']}** (+{d['growth_rate']}%)")
            if not rising:
                for d in cd["datalab"][:10]:
                    st.markdown(f"- {d['keyword']} ({d['growth_rate']}%)")
        else:
            st.caption("데이터 없음")

        st.subheader(f"뉴스 ({len(cd['news'])}건)")
        if cd["news"]:
            for n in cd["news"][:15]:
                st.markdown(f"- {n['title']}")
        else:
            st.caption("데이터 없음")

    # 수집 실행 버튼
    st.divider()
    if st.button("지금 데이터 수집 실행", key="run_collect"):
        with st.spinner("데이터 수집 중... (1~2분)"):
            try:
                from collectors import collect_all
                collect_all()
                st.session_state.collected_data = _load_collected_data()
                st.success("수집 완료!")
                st.rerun()
            except Exception as e:
                st.error(f"수집 실패: {e}")

# ============================================================
# STEP 1: 주제 계획
# ============================================================
with step1:
    st.header("1단계: AI 주제 계획")

    # 트렌드 데이터 요약 표시
    cd = st.session_state.collected_data or _load_collected_data()
    with st.expander(f"주제 계획에 활용되는 트렌드 데이터 ({cd['date']})", expanded=False):
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if cd["trending"]:
                st.markdown("**구글 트렌딩**: " + ", ".join(t["keyword"] for t in cd["trending"][:10]))
            if cd["suggest"]:
                st.markdown("**자동완성**: " + ", ".join(cd["suggest"][:10]))
        with col_t2:
            rising = [d for d in cd["datalab"] if float(d.get("growth_rate", "0") or "0") > 20]
            if rising:
                st.markdown("**급상승**: " + ", ".join(f"{d['keyword']}(+{d['growth_rate']}%)" for d in rising[:5]))
            if cd["news"]:
                st.markdown("**뉴스**: " + " / ".join(n["title"][:30] for n in cd["news"][:5]))

        if cd["date"] == "없음":
            st.warning("수집 데이터가 없습니다. 0단계에서 수집을 먼저 실행하세요.")

    col1, col2 = st.columns([1, 3])
    with col1:
        topic_count = st.number_input("주제 수", min_value=1, max_value=10, value=1)

    if st.button("주제 계획 실행", type="primary", key="plan"):
        with st.spinner("AI가 주제를 계획하고 있습니다..."):
            from blog_generator.planner import plan_topics
            topics = plan_topics(count=topic_count, blog_id=selected_blog)
            st.session_state.topics = topics

    if st.session_state.topics:
        topics = st.session_state.topics
        meta = topics[0].get("_planner_meta", {}) if topics else {}

        st.success(f"{len(topics)}개 주제 생성 완료")

        # 모델 정보
        if meta:
            st.markdown(f"**모델**: `{meta.get('provider', '')}/{meta.get('model', '')}`")

        # 프롬프트 확인
        if meta:
            with st.expander("시스템 프롬프트 보기"):
                st.text_area("시스템 프롬프트", meta.get("system_prompt", ""), height=300, disabled=True, key="plan_sys")
            with st.expander("유저 프롬프트 보기 (트렌드 데이터 포함)"):
                st.text_area("유저 프롬프트", meta.get("user_prompt", ""), height=400, disabled=True, key="plan_user")
            with st.expander("LLM 원본 응답 보기"):
                st.text_area("원본 응답", meta.get("raw_response", ""), height=300, disabled=True, key="plan_raw")

        st.divider()

        # 주제 목록
        for i, t in enumerate(topics):
            with st.expander(f"주제 {i+1}: {t.get('region', '')} × {t.get('business', '')}", expanded=(i == 0)):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**제목 아이디어**: {t.get('title_idea', '')}")
                    st.markdown(f"**템플릿**: `{t.get('template', '')}`")
                    st.markdown(f"**앵글**: {t.get('angle', '')}")
                with col_b:
                    st.markdown(f"**키워드**: {', '.join(t.get('keywords', []))}")
                    st.markdown(f"**검색 쿼리**: {', '.join(t.get('search_queries', []))}")

                if st.button(f"이 주제 선택", key=f"select_{i}"):
                    st.session_state.selected_topic = t
                    st.success(f"주제 {i+1} 선택됨")

        st.divider()
        st.subheader("원본 JSON")
        display_topics = [{k: v for k, v in t.items() if k != "_planner_meta"} for t in topics]
        st.json(display_topics)

# ============================================================
# STEP 2: 데이터 수집
# ============================================================
with step2:
    st.header("2단계: 주제별 데이터 수집")

    if st.session_state.selected_topic:
        topic = st.session_state.selected_topic
        st.info(f"선택된 주제: **{topic.get('region', '')} × {topic.get('business', '')}**")

        if st.button("데이터 수집 실행", type="primary", key="search"):
            with st.spinner("네이버 뉴스/블로그 검색 중..."):
                from blog_generator.planner import search_for_topic
                ref = search_for_topic(topic)
                st.session_state.reference = ref

                # topic에 레퍼런스 주입
                if ref.get("news"):
                    topic["ref_news"] = "\n".join(f"- {n['title']}" for n in ref["news"])
                if ref.get("blogs"):
                    topic["ref_blogs"] = "\n".join(f"- {b['title']}" for b in ref["blogs"])

        if st.session_state.reference:
            ref = st.session_state.reference
            col_n, col_b = st.columns(2)

            with col_n:
                st.subheader(f"뉴스 ({len(ref.get('news', []))}건)")
                for n in ref.get("news", []):
                    st.markdown(f"- {n['title']}")

            with col_b:
                st.subheader(f"블로그 ({len(ref.get('blogs', []))}건)")
                for b in ref.get("blogs", []):
                    st.markdown(f"- {b['title']}")

            st.divider()
            st.subheader("검색 쿼리")
            st.write(ref.get("queries", []))
    else:
        st.warning("1단계에서 주제를 먼저 선택하세요.")

# ============================================================
# STEP 3: 글 생성
# ============================================================
with step3:
    st.header("3단계: 블로그 글 생성")

    if st.session_state.selected_topic:
        topic = st.session_state.selected_topic
        template_name = topic.get("template", blog_info.get("templates", ["local_trend"])[0])

        st.info(f"주제: **{topic.get('region', '')} × {topic.get('business', '')}** | 템플릿: `{template_name}`")

        # 프롬프트 미리보기/편집
        with st.expander("시스템 프롬프트 보기/편집"):
            from blog_generator.local_blog_writer import _build_system_prompt, _get_random_tone
            preview_tone = _get_random_tone()
            preview_system = _build_system_prompt(preview_tone)
            st.markdown(f"**미리보기 톤**: {preview_tone['name']}")
            edited_system = st.text_area("시스템 프롬프트", preview_system, height=400, key="sys_prompt")

        with st.expander("유저 프롬프트 미리보기"):
            from blog_generator.local_blog_writer import _build_user_prompt, _load_blog_images, _load_image_layout, _build_image_prompt

            region = topic.get("region", "")
            business = topic.get("business", "")
            parts = region.split() if region else []
            ambiguous = ["서구", "북구", "남구", "중구", "동구"]
            if len(parts) == 2 and parts[-1] in ambiguous:
                region_short = region
            elif parts:
                region_short = parts[-1]
            else:
                region_short = ""

            blog_images = _load_blog_images()
            image_layout = _load_image_layout(template_name)
            image_guide = _build_image_prompt(blog_images, image_layout)

            user_prompt = _build_user_prompt(
                template_name=template_name,
                region=region, region_short=region_short,
                business=business, business_desc=business,
                angle=topic.get("angle", ""), keywords=topic.get("keywords", []),
                topic=topic, image_guide=image_guide,
            )
            st.text_area("유저 프롬프트", user_prompt, height=400, key="user_prompt", disabled=True)

        if st.button("글 생성 실행", type="primary", key="write"):
            with st.spinner("AI가 블로그 글을 작성하고 있습니다... (30초~1분)"):
                from blog_generator.local_blog_writer import write_local_blog
                blog = write_local_blog(topic, template_name=template_name)
                st.session_state.blog_result = blog

        if st.session_state.blog_result:
            blog = st.session_state.blog_result
            st.success(f"글 생성 완료 — 모델: {blog['model_info']['model']}")

            st.subheader(blog.get("title", "(제목 없음)"))
            st.caption(blog.get("meta_description", ""))

            st.divider()

            # 본문 표시
            body = blog.get("body", "")
            st.markdown(f"**본문 길이**: {len(body)}자")

            # 이미지 태그를 읽기 쉽게 표시
            display_body = body
            display_body = re.sub(r"\[썸네일 이미지[^\]]*\]", "🖼 [썸네일]", display_body)
            display_body = re.sub(r"\[서비스 이미지[^\]]*\]", "🖼 [서비스 이미지]", display_body)

            st.text_area("생성된 본문 (마크다운)", body, height=500, key="body_view")

            st.divider()
            st.subheader("마크다운 렌더링")
            st.markdown(display_body)
    else:
        st.warning("1단계에서 주제를 먼저 선택하세요.")

# ============================================================
# STEP 4: 미리보기 + 발행
# ============================================================
with step4:
    st.header("4단계: 네이버 포맷 미리보기")

    if st.session_state.blog_result:
        blog = st.session_state.blog_result
        body = blog.get("body", "")

        # 포맷 변환
        from publisher.blog_formatter import markdown_to_commands
        template_name = st.session_state.selected_topic.get("template", "local_trend")
        commands = markdown_to_commands(body, template_name=template_name)
        st.session_state.commands = commands

        st.markdown(f"**변환된 명령 수**: {len(commands)}개")

        # 명령 목록 표시
        with st.expander("명령 리스트 보기"):
            for i, cmd in enumerate(commands):
                t = cmd["type"]
                if t == "heading":
                    st.markdown(f"`{i:3d}` **[H{cmd['size']}]** {cmd['text']}")
                elif t == "text":
                    st.markdown(f"`{i:3d}` [TEXT] {cmd['text'][:80]}")
                elif t == "bold_text":
                    st.markdown(f"`{i:3d}` **[BOLD]** {cmd['text'][:80]}")
                elif t == "image":
                    link = f" → {cmd['link']}" if cmd.get("link") else ""
                    st.markdown(f"`{i:3d}` 🖼 [IMAGE] {Path(cmd['path']).name}{link}")
                elif t == "hashtags":
                    st.markdown(f"`{i:3d}` 🏷 {cmd['text'][:80]}")
                elif t == "blank_line":
                    st.markdown(f"`{i:3d}` ---")

        # 네이버 스타일 미리보기
        st.divider()
        st.subheader("네이버 블로그 미리보기")

        preview_html = '<div style="font-family: Malgun Gothic, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px;">'
        for cmd in commands:
            t = cmd["type"]
            if t == "heading":
                size = {24: "1.6em", 19: "1.3em", 17: "1.1em"}.get(cmd["size"], "1.2em")
                preview_html += f'<h2 style="font-size: {size}; margin: 20px 0 10px 0;">{cmd["text"]}</h2>'
            elif t == "text":
                preview_html += f'<span>{cmd["text"]}</span>'
            elif t == "bold_text":
                preview_html += f'<strong>{cmd["text"]}</strong>'
            elif t == "newline":
                preview_html += "<br>"
            elif t == "blank_line":
                preview_html += "<br><br>"
            elif t == "image":
                name = Path(cmd["path"]).name
                preview_html += f'<div style="background: #e8e8e8; padding: 20px; text-align: center; margin: 10px 0; border-radius: 8px;">🖼 {name}</div>'
            elif t == "hashtags":
                tags = cmd["text"].replace("#", '<span style="color: #0068c3; margin-right: 8px;">#')
                tags = tags.replace(" <span", "</span> <span")
                preview_html += f'<div style="margin-top: 20px; color: #0068c3;">{tags}</span></div>'
        preview_html += "</div>"

        st.html(preview_html)

        # 발행 버튼
        st.divider()
        blog_url = blog_info.get("blog_url", "")
        st.warning(f"발행 대상: **{selected_blog}** ({blog_url})")
        if st.button("네이버 블로그에 발행", type="primary", key="publish"):
            with st.spinner("네이버 블로그에 발행 중..."):
                from publisher.naver_blog import publish_to_naver
                url = publish_to_naver(blog, blog_id=blog_url, template_name=template_name, cookie_blog_id=selected_blog)
                if url:
                    st.success(f"발행 완료! {url}")
                    st.balloons()
                else:
                    st.error("발행 실패 — 쿠키 만료 또는 에디터 오류")
    else:
        st.warning("3단계에서 글을 먼저 생성하세요.")
