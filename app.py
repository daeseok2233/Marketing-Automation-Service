"""블로그 자동화 파이프라인 — 에이전틱 대시보드."""

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

# 모드 선택
mode = st.sidebar.radio("플래닝 모드", ["에이전틱 (AI 자율)", "수동 (기존 파이프라인)"])

# ── 세션 상태 초기화 ──
for key in ["agent_result", "step3_result"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ── 탭 ──
if mode == "에이전틱 (AI 자율)":
    tab_agent, tab_write, tab_publish = st.tabs([
        "1. AI 에이전트 기획",
        "2. 글 생성",
        "3. 미리보기 + 발행",
    ])
else:
    tab_agent, tab_write, tab_publish = st.tabs([
        "1. 검색 쿼리 생성 + 정보 수집",
        "2. 글 생성",
        "3. 미리보기 + 발행",
    ])

# ============================================================
# STEP 1: 에이전틱 기획 / 수동 파이프라인
# ============================================================
with tab_agent:
    if mode == "에이전틱 (AI 자율)":
        st.header("1단계: AI 에이전트 기획")
        st.caption("Gemini가 템플릿을 보고 어떤 API로 무엇을 검색할지 스스로 판단합니다.")

        # 템플릿 선택
        available_templates = blog_info.get("templates", [])
        template_choice = st.selectbox(
            "템플릿 (비워두면 랜덤)",
            ["(랜덤)"] + available_templates,
            key="tpl_choice",
        )
        tpl_name = "" if template_choice == "(랜덤)" else template_choice

        # 입력 표시
        with st.expander("📥 에이전트에게 주어지는 정보", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**블로그**: {selected_blog} — {blog_info.get('name', '')}")
                st.markdown(f"**테마**: {blog_info.get('theme', '')[:100]}")
            with col2:
                st.markdown(f"**템플릿**: {tpl_name or '랜덤 선택'}")
                st.markdown("**사용 가능 도구:**")
                tools_desc = {
                    "search_naver_news": "네이버 뉴스 검색",
                    "search_naver_blog": "네이버 블로그 검색",
                    "get_google_trending": "실시간 인기 검색어",
                    "get_public_events": "지역 축제/행사",
                    "get_naver_suggest": "자동완성 키워드",
                    "search_trademark_db": "상표 DB 검색",
                    "get_search_trend": "검색량 트렌드",
                }
                for name, desc in tools_desc.items():
                    st.markdown(f"- `{name}`: {desc}")

        # 실행
        if st.button("🤖 에이전트 실행", type="primary", key="run_agent"):
            with st.spinner("Gemini 에이전트가 도구를 선택하고 정보를 수집하고 있습니다..."):
                from blog_generator.agent_planner import agent_plan_topic
                topic = agent_plan_topic(blog_id=selected_blog, template_name=tpl_name)
                st.session_state.agent_result = topic
                st.session_state.step3_result = None

        # 출력 표시
        if st.session_state.agent_result:
            topic = st.session_state.agent_result
            meta = topic.get("_agent_meta", {})
            tool_calls = meta.get("tool_calls", [])

            # 도구 호출 기록
            with st.expander(f"🔧 에이전트 도구 호출 ({len(tool_calls)}회)", expanded=True):
                for i, tc in enumerate(tool_calls):
                    fn = tc["function"]
                    args = tc.get("args", {})
                    preview = tc.get("result_preview", "")[:150]
                    st.markdown(f"**{i+1}. `{fn}`**")
                    st.markdown(f"   인자: `{json.dumps(args, ensure_ascii=False)}`")
                    st.text(f"   결과: {preview}")
                    if i < len(tool_calls) - 1:
                        st.divider()

            # 최종 기획 결과
            with st.expander("📤 최종 기획 결과", expanded=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**템플릿**: `{topic.get('template', '')}`")
                    st.markdown(f"**지역**: {topic.get('region', '(없음)')}")
                    st.markdown(f"**업종**: {topic.get('business', '')}")
                    st.markdown(f"**앵글**: {topic.get('angle', '')}")
                with col2:
                    st.markdown("**키워드:**")
                    for kw in topic.get("keywords", []):
                        st.markdown(f"- {kw}")
                    st.markdown("**검색 쿼리:**")
                    for sq in topic.get("search_queries", []):
                        st.markdown(f"- `{sq}`")

            # 수집된 레퍼런스
            with st.expander("📚 수집된 레퍼런스"):
                if topic.get("ref_news"):
                    st.subheader("📰 뉴스")
                    st.text(topic["ref_news"][:500])
                if topic.get("ref_blogs"):
                    st.subheader("📝 블로그")
                    st.text(topic["ref_blogs"][:500])
                if topic.get("ref_trending"):
                    st.subheader("🔥 트렌딩")
                    st.text(topic["ref_trending"][:500])

            # 프롬프트 상세
            with st.expander("🔧 프롬프트 상세"):
                if meta.get("model"):
                    st.markdown(f"**모델**: `{meta.get('provider', '')}/{meta.get('model', '')}`")
                if meta.get("system_prompt"):
                    st.text_area("시스템 프롬프트", meta["system_prompt"], height=300, disabled=True, key="agent_sys")
                if meta.get("user_prompt"):
                    st.text_area("유저 프롬프트", meta["user_prompt"], height=200, disabled=True, key="agent_user")
                if meta.get("raw_response"):
                    st.text_area("에이전트 최종 응답", meta["raw_response"], height=200, disabled=True, key="agent_raw")

            st.success("✅ 1단계 완료 — 2단계에서 글을 생성하세요")

    else:
        # ── 수동 모드 (기존 파이프라인) ──
        st.header("1단계: 검색 쿼리 생성 + 정보 수집")
        st.caption("기존 방식: 코드가 정해진 순서로 쿼리 생성 → 네이버 검색 → 트렌딩 수집")

        if st.button("🚀 기존 파이프라인 실행", type="primary", key="run_manual"):
            with st.spinner("검색 쿼리 생성 + 정보 수집 중..."):
                from blog_generator.planner import plan_search_queries, collect_references, select_topic_from_references
                queries = plan_search_queries(count=1, blog_id=selected_blog)
                if queries:
                    q = queries[0]
                    refs = collect_references(q)
                    select_topic_from_references(q, refs)
                    st.session_state.agent_result = q
                    st.session_state.step3_result = None

        if st.session_state.agent_result:
            q = st.session_state.agent_result
            with st.expander("📤 결과", expanded=True):
                st.json({k: v for k, v in q.items() if k != "_planner_meta" and k != "_agent_meta"})
            st.success("✅ 1단계 완료 — 2단계로 이동하세요")

# ============================================================
# STEP 2: 글 생성
# ============================================================
with tab_write:
    st.header("2단계: 글 생성")
    st.caption("수집된 정보를 보고 AI가 제목 + 본문을 한 번에 생성합니다.")

    if not st.session_state.agent_result:
        st.warning("⬆️ 1단계를 먼저 실행하세요")
    else:
        topic = st.session_state.agent_result
        template_name = topic.get("template", blog_info.get("templates", ["local_trend"])[0])

        # 입력 표시
        with st.expander("📥 입력 데이터", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**템플릿**: `{template_name}`")
                st.markdown(f"**지역**: {topic.get('region', '(없음)')}")
                st.markdown(f"**업종**: {topic.get('business', '')}")
                st.markdown(f"**앵글**: {topic.get('angle', '')}")
            with col2:
                has_news = bool(topic.get("ref_news"))
                has_blogs = bool(topic.get("ref_blogs"))
                has_trending = bool(topic.get("ref_trending"))
                st.markdown(f"**뉴스**: {'✅' if has_news else '❌'}")
                st.markdown(f"**블로그**: {'✅' if has_blogs else '❌'}")
                st.markdown(f"**트렌딩**: {'✅' if has_trending else '❌'}")

        # 프롬프트 미리보기
        with st.expander("🔧 글 생성 프롬프트 미리보기"):
            from blog_generator.blog_writer import _build_prompt

            region = topic.get("region", "")
            parts = region.split() if region else []
            ambiguous = ["서구", "북구", "남구", "중구", "동구"]
            if len(parts) == 2 and parts[-1] in ambiguous:
                region_short = region
            elif parts:
                region_short = parts[-1]
            else:
                region_short = ""

            tpl_path = Path(f"data/templates/{template_name}.json")
            tpl_data = json.loads(tpl_path.read_text(encoding="utf-8")) if tpl_path.exists() else {}

            user_prompt = _build_prompt(
                tpl_data, region, region_short,
                topic.get("business", ""), topic.get("angle", ""),
                topic.get("keywords", []), topic,
            )
            st.text_area("프롬프트", user_prompt, height=400, disabled=True, key="s3_user")

        # 실행
        if st.button("🚀 글 생성 실행", type="primary", key="run_step3"):
            with st.spinner("AI가 제목 + 본문을 작성하고 있습니다... (30초~1분)"):
                from blog_generator.blog_writer import write_local_blog
                blog = write_local_blog(topic, template_name=template_name)
                st.session_state.step3_result = blog

        # 출력 표시
        if st.session_state.step3_result:
            blog = st.session_state.step3_result

            with st.expander("📤 출력 결과", expanded=True):
                st.markdown(f"**모델**: `{blog['model_info']['model']}`")
                st.markdown(f"**톤**: {blog.get('tone', '')}")
                st.markdown(f"**본문 길이**: {len(blog.get('body', ''))}자")

                st.divider()
                st.subheader(blog.get("title", "(제목 없음)"))
                st.caption(blog.get("meta_description", ""))

                st.divider()
                body = blog.get("body", "")
                st.text_area("생성된 본문 (원본)", body, height=400, key="s3_body")

            with st.expander("📖 마크다운 렌더링"):
                display_body = re.sub(r"\[썸네일 이미지[^\]]*\]", "[썸네일]", body)
                display_body = re.sub(r"\[서비스 이미지[^\]]*\]", "[서비스 이미지]", display_body)
                st.markdown(display_body)

            st.success("✅ 2단계 완료 — 3단계에서 미리보기 확인하세요")

# ============================================================
# STEP 3: 미리보기 + 발행
# ============================================================
with tab_publish:
    st.header("3단계: 미리보기 + 발행")
    st.caption("네이버 블로그에 올라갈 최종 형태를 확인하고 발행합니다.")

    if not st.session_state.step3_result:
        st.warning("⬆️ 2단계를 먼저 실행하세요")
    else:
        blog = st.session_state.step3_result
        template_name = st.session_state.agent_result.get("template", "local_trend")

        # structure → Playwright 명령 변환
        from publisher.blog_formatter import structure_to_commands
        commands = structure_to_commands(
            tpl_data=blog.get("_tpl_data", {}),
            slots=blog.get("_slots", {}),
            blog_images=blog.get("_blog_images", []),
            blog_id=selected_blog,
            thumb_url=blog.get("_thumb_path", ""),
            region=blog.get("region", ""),
            region_short=blog.get("region_short", ""),
        )

        # 입력 표시
        with st.expander("📥 입력 데이터"):
            st.markdown(f"**제목**: {blog.get('title', '')}")
            st.markdown(f"**변환 명령 수**: {len(commands)}개")
            st.markdown(f"**블로그**: {selected_blog} ({blog_info.get('blog_url', '')})")

        # 명령 리스트
        with st.expander("🔧 Playwright 명령 리스트"):
            for i, cmd in enumerate(commands):
                t = cmd["type"]
                if t == "heading":
                    st.markdown(f"`{i:3d}` **[H{cmd['size']}]** {cmd['text']}")
                elif t == "text":
                    st.markdown(f"`{i:3d}` {cmd['text'][:80]}")
                elif t == "bold_text":
                    st.markdown(f"`{i:3d}` **{cmd['text'][:80]}**")
                elif t == "image":
                    link = f" → {cmd['link'][:30]}" if cmd.get("link") else ""
                    st.markdown(f"`{i:3d}` [이미지] {Path(cmd['path']).name}{link}")
                elif t == "hashtags":
                    st.markdown(f"`{i:3d}` [태그] {cmd['text'][:80]}")

        # 네이버 미리보기
        st.divider()
        st.subheader("네이버 블로그 미리보기")

        preview_html = '<div style="font-family: Malgun Gothic, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">'
        for cmd in commands:
            t = cmd["type"]
            if t == "heading":
                size = {24: "1.6em", 19: "1.3em", 17: "1.1em"}.get(cmd["size"], "1.2em")
                preview_html += f'<h2 style="font-size: {size}; margin: 20px 0 10px 0; font-weight: bold;">{cmd["text"]}</h2>'
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
                link_text = f'<br><small style="color:#888;">링크: {cmd["link"][:40]}</small>' if cmd.get("link") else ""
                preview_html += f'<div style="background: #f5f5f5; padding: 15px; text-align: center; margin: 10px 0; border-radius: 8px;">[이미지] {name}{link_text}</div>'
            elif t == "hashtags":
                preview_html += f'<div style="margin-top: 20px; color: #0068c3; font-size: 0.9em;">{cmd["text"]}</div>'
        preview_html += "</div>"
        st.html(preview_html)

        # 발행
        st.divider()
        blog_url = blog_info.get("blog_url", "")
        st.warning(f"발행 대상: **{selected_blog}** (blog.naver.com/{blog_url})")

        if st.button("발행", type="primary", key="publish"):
            with st.spinner("네이버 블로그에 발행 중... (별도 프로세스)"):
                import subprocess, tempfile
                # Playwright는 Streamlit 이벤트 루프와 충돌 → 별도 프로세스로 실행
                publish_data = {
                    "blog": blog,
                    "blog_id": blog_url,
                    "template_name": template_name,
                    "cookie_blog_id": selected_blog,
                }
                tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
                json.dump(publish_data, tmp, ensure_ascii=False)
                tmp.close()

                result = subprocess.run(
                    ["python", "publish_one.py", tmp.name],
                    capture_output=True, text=True, timeout=120,
                    encoding="utf-8",
                )
                Path(tmp.name).unlink(missing_ok=True)

                if result.returncode == 0 and result.stdout.strip():
                    url = result.stdout.strip().split("\n")[-1]
                    if url.startswith("http"):
                        st.success(f"발행 완료! {url}")
                        st.balloons()
                    else:
                        st.error(f"발행 실패 — {url}")
                else:
                    error_msg = result.stderr.strip()[-200:] if result.stderr else "알 수 없는 오류"
                    st.error(f"발행 실패 — {error_msg}")
