"""정보 수집 테스트 대시보드."""

import json
import os
import requests
import streamlit as st
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from collections import Counter

load_dotenv()

st.set_page_config(page_title="정보 수집 테스트", layout="wide")
st.title("정보 수집 테스트 대시보드")

if "plan_result" not in st.session_state:
    st.session_state["plan_result"] = None
if "plan_results" not in st.session_state:
    st.session_state["plan_results"] = None

NAVER_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
NAVER_HEADERS = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
PUBLIC_KEY = os.environ.get("PUBLIC_DATA_API_KEY", "")


def search_naver_news(query, count=5):
    """네이버 뉴스 검색."""
    try:
        r = requests.get("https://openapi.naver.com/v1/search/news.json",
            params={"query": query, "display": count, "sort": "date"},
            headers=NAVER_HEADERS, timeout=5)
        if r.status_code == 200:
            items = r.json().get("items", [])
            return [{"title": it["title"].replace("<b>", "").replace("</b>", ""),
                      "description": it.get("description", "").replace("<b>", "").replace("</b>", "")[:150],
                      "link": it.get("link", ""),
                      "pubDate": it.get("pubDate", "")}
                     for it in items]
    except Exception:
        pass
    return []


def search_naver_blog(query, count=5):
    """네이버 블로그 검색."""
    try:
        r = requests.get("https://openapi.naver.com/v1/search/blog.json",
            params={"query": query, "display": count, "sort": "sim"},
            headers=NAVER_HEADERS, timeout=5)
        if r.status_code == 200:
            items = r.json().get("items", [])
            return [{"title": it["title"].replace("<b>", "").replace("</b>", ""),
                      "description": it.get("description", "").replace("<b>", "").replace("</b>", "")[:150],
                      "link": it.get("link", "")}
                     for it in items]
    except Exception:
        pass
    return []


def get_google_trending():
    """구글 실시간 트렌딩."""
    import xml.etree.ElementTree as ET
    try:
        r = requests.get("https://trends.google.com/trending/rss?geo=KR",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            ns = {"ht": "https://trends.google.com/trending/rss"}
            trends = []
            for item in root.findall(".//item"):
                keyword = item.findtext("title", "").strip()
                traffic = item.findtext("ht:approx_traffic", "", ns).strip()
                news = []
                for ni in item.findall("ht:news_item", ns):
                    nt = ni.findtext("ht:news_item_title", "", ns).strip()
                    if nt:
                        news.append(nt[:60])
                if keyword:
                    trends.append({"keyword": keyword, "traffic": traffic, "news": news[:2]})
            return trends[:15]
    except Exception:
        pass
    return []


def get_naver_suggest(keyword):
    """네이버 자동완성."""
    try:
        r = requests.get("https://ac.search.naver.com/nx/ac",
            params={"q": keyword, "con": 1, "frm": "nv", "ans": 2}, timeout=5)
        if r.status_code == 200:
            items = r.json().get("items", [[]])[0]
            return [item[0] for item in items if item][:10]
    except Exception:
        pass
    return []


def get_search_trend(keywords):
    """네이버 데이터랩 검색량."""
    from datetime import datetime, timedelta
    today = datetime.now()
    start = (today - timedelta(days=90)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    keyword_groups = [{"groupName": kw, "keywords": [kw]} for kw in keywords[:5]]
    try:
        r = requests.post("https://openapi.naver.com/v1/datalab/search",
            headers={**NAVER_HEADERS, "Content-Type": "application/json"},
            json={"startDate": start, "endDate": end, "timeUnit": "week", "keywordGroups": keyword_groups},
            timeout=10)
        if r.status_code == 200:
            results = {}
            for group in r.json().get("results", []):
                ratios = [d["ratio"] for d in group.get("data", []) if d.get("ratio")]
                if len(ratios) >= 4:
                    recent = sum(ratios[-4:]) / 4
                    prev = sum(ratios[-8:-4]) / 4 if len(ratios) >= 8 else recent
                    growth = round((recent - prev) / prev * 100, 1) if prev > 0 else 0
                    results[group["title"]] = {"avg": round(recent, 1), "growth": growth}
            return results
    except Exception:
        pass
    return {}


# ============================================================
# 일일 수집 (상단)
# ============================================================
st.header("일일 데이터 수집")
st.caption("하루 1회 실행 — 행사/축제 크롤링 + 핵심 뉴스 수집")

today_str = datetime.now().strftime("%Y%m%d")
events_file = Path(f"data/collected/{today_str}_events.json")
news_file = Path(f"data/collected/{today_str}_daily_news.json")

col_status1, col_status2 = st.columns(2)
with col_status1:
    if events_file.exists():
        events_data = json.loads(events_file.read_text(encoding="utf-8"))
        st.success(f"행사/축제: {len(events_data)}건 수집됨")
    else:
        st.warning("행사/축제: 미수집")
with col_status2:
    if news_file.exists():
        news_data = json.loads(news_file.read_text(encoding="utf-8"))
        st.success(f"핵심 뉴스: {len(news_data)}건 수집됨")
    else:
        st.warning("핵심 뉴스: 미수집")

if st.button("일일 데이터 수집 실행", type="primary", key="run_daily"):
    import subprocess

    # 1. 행사/축제 크롤링
    with st.spinner("행사/축제 크롤링 중... (약 30초)"):
        r1 = subprocess.run(
            ["python", "-X", "utf8", "-c",
             "from collectors.naver_events import collect_and_save; collect_and_save(keywords=['축제', '박람회'], max_pages=2)"],
            capture_output=True, text=True, timeout=600, encoding="utf-8",
        )
        if events_file.exists():
            events_data = json.loads(events_file.read_text(encoding="utf-8"))
            st.success(f"행사/축제: {len(events_data)}건 수집 완료")
        else:
            st.error(f"행사/축제 수집 실패: {r1.stderr[:200]}")

    # 2. 핵심 뉴스
    with st.spinner("핵심 뉴스 수집 중..."):
        r2 = subprocess.run(
            ["python", "-X", "utf8", "-c",
             "from collectors.daily_news import collect_and_save; collect_and_save()"],
            capture_output=True, text=True, timeout=30, encoding="utf-8",
        )
        if news_file.exists():
            news_data = json.loads(news_file.read_text(encoding="utf-8"))
            st.success(f"핵심 뉴스: {len(news_data)}건 수집 완료")
        else:
            st.error(f"뉴스 수집 실패: {r2.stderr[:200]}")

# 수집 결과 표시
st.divider()

col_events, col_news = st.columns(2)

with col_events:
    st.subheader("행사/축제")
    if events_file.exists():
        events_data = json.loads(events_file.read_text(encoding="utf-8"))
        kw_counts = Counter(e.get("keyword", "") for e in events_data)
        for kw, cnt in kw_counts.items():
            st.markdown(f"**{kw}**: {cnt}건")
        st.divider()
        for i, e in enumerate(events_data):
            st.markdown(f"{i+1}. **{e['name']}**")
            st.caption(f"{e['period']} | {e['place']}")
    else:
        st.info("수집 버튼을 눌러주세요")

with col_news:
    st.subheader("핵심 뉴스")
    if news_file.exists():
        news_data = json.loads(news_file.read_text(encoding="utf-8"))
        kw_counts = Counter(n.get("keyword", "") for n in news_data)
        for kw, cnt in kw_counts.items():
            st.markdown(f"**{kw}**: {cnt}건")
        st.divider()
        # 키워드 필터
        all_kws = list(kw_counts.keys())
        filter_kw = st.multiselect("키워드 필터", all_kws, default=all_kws, key="news_filter")
        filtered_news = [n for n in news_data if n.get("keyword", "") in filter_kw]
        st.caption(f"표시: {len(filtered_news)}건")

        for i, n in enumerate(filtered_news):
            source = n.get("source", "naver")
            source_label = "N" if source == "naver" else "G"
            with st.expander(f"{i+1}. [{source_label}][{n['keyword']}] {n['title'][:50]}"):
                st.markdown(f"**제목**: {n['title']}")
                if n.get('description'):
                    st.markdown(f"**설명**: {n['description']}")
                st.markdown(f"**날짜**: {n.get('date', '')}")
                st.markdown(f"**출처**: {'네이버' if source == 'naver' else '구글'}")
                if n.get('link'):
                    st.markdown(f"[기사 링크]({n['link']})")
    else:
        st.info("수집 버튼을 눌러주세요")

st.divider()

# ============================================================
# 글 기획
# ============================================================
st.header("글 기획")
st.caption("수집된 뉴스에서 템플릿별로 활용할만한 기사를 LLM이 선별")

# 블로그별 키워드 매핑
BLOG_KEYWORDS = {
    "blog_02": ["상표", "특허", "창업", "브랜드", "신제품"],
    "blog_03": ["상표", "지식재산", "프랜차이즈", "상호명", "특허"],
    "blog_04": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌"],
    "blog_05": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌"],
    "blog_06": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌"],
    "blog_07": ["축제", "박람회", "창업", "상권", "소상공인", "폐업", "자영업", "공모전", "페스티벌"],
}

plan_blog = st.selectbox("블로그 선택", ["blog_02", "blog_03", "blog_04", "blog_05", "blog_06", "blog_07"], key="plan_blog")
plan_keywords = BLOG_KEYWORDS.get(plan_blog, [])
st.markdown(f"**참고 키워드**: {', '.join(plan_keywords)}")

# 뉴스 필터링 + 프롬프트 미리보기
if news_file.exists():
    all_news = json.loads(news_file.read_text(encoding="utf-8"))
    filtered_news = [n for n in all_news if n.get("keyword", "") in plan_keywords]
    st.markdown(f"**필터된 뉴스**: {len(filtered_news)}건 (전체 {len(all_news)}건 중)")

    # 키워드별 뉴스 정리
    news_by_keyword = {}
    for n in filtered_news:
        kw = n["keyword"]
        if kw not in news_by_keyword:
            news_by_keyword[kw] = []
        news_by_keyword[kw].append(n["title"])

    news_text = ""
    for kw, titles in news_by_keyword.items():
        news_text += f"\n[{kw}]\n"
        for i, t in enumerate(titles):
            news_text += f"  {i+1}. {t}\n"

    tpl_desc = """- local_event: 지역 행사/축제/박람회/공모전 등 소식.
  행사 정보를 소개하고 자연스럽게 상표등록 필요성을 연결.
  예: "송파 벚꽃축제 개막", "대전 창업 박람회 개최"

- issue: 상권/사업자 관련 뉴스나 사건.
  이슈를 소개하고 상표/브랜드 보호 필요성을 연결.
  예: "프랜차이즈 상표 분쟁", "자영업 폐업률 증가", "위조상품 단속"

- local_issue: 지역 상권/사업자 관련 뉴스나 사건.
  반드시 특정 지역이 포함된 기사만 선택할 것
  (지역 = 시/군/구/동/읍/면 단위. 예: 서울, 강남구, 부산 해운대, 대전 유성구)
  이슈를 소개하고 상표/브랜드 보호 필요성을 연결.
  예: " A지역 프랜차이즈 상표 분쟁", "B 지역 자영업 폐업률 증가", "C 지역 위조상품 단속"

- local_trend: 지역 창업/상권 트렌드.
  반드시 특정 지역이 포함된 기사만 선택할 것
  트렌드를 소개하고 경쟁 속 브랜드 차별화를 위한 상표등록을 연결.  
  예: "강릉 카페 창업 증가", "서울시 소상공인 지원사업 확대\""""

    # 프롬프트 템플릿 (기사 1건용)
    prompt_template = f"""당신은 전문 마크뷰/마크패스/마크픽 서비스 블로그 콘텐츠 기획자이다.

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
{tpl_desc}

## 출력 형식
점수: (0~100)
템플릿: (템플릿명 / 해당없음)
기획: (어떤 흐름으로 글을 쓰면 좋을지 200자 이내)"""

    # 프롬프트 편집
    with st.expander("프롬프트 템플릿 편집"):
        prompt_template = st.text_area("기사 1건당 LLM에게 보내는 프롬프트", prompt_template, height=400, key="plan_prompt")

    # 기사 목록 표시
    st.markdown(f"**평가할 기사**: {len(filtered_news)}건")
    eval_count = st.slider("평가할 기사 수 (테스트용)", 1, min(len(filtered_news), 50), 5, key="eval_count")

    # 기획 실행
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
                results.append({
                    "article": article,
                    "response": result["text"],
                })

        st.session_state["plan_results"] = results
        st.success(f"기획 완료: {len(results)}건 평가")

    # 결과 표시
    if st.session_state.get("plan_results"):
        st.subheader("기획 결과")
        for i, r in enumerate(st.session_state["plan_results"]):
            article = r["article"]
            response = r["response"]

            # 점수 추출
            score_line = [l for l in response.split("\n") if "점수:" in l]
            score = score_line[0].split(":")[-1].strip() if score_line else "?"

            with st.expander(f"{i+1}. [{article['keyword']}] [점수:{score}] {article['title'][:50]}"):
                st.markdown(f"**기사 제목**: {article['title']}")
                if article.get("description"):
                    st.markdown(f"**기사 내용**: {article['description'][:150]}")
                st.divider()
                st.markdown("**LLM 판단:**")
                st.markdown(response)

else:
    st.warning("뉴스 데이터가 없습니다. 먼저 일일 수집을 실행하세요.")

st.divider()

# ============================================================
# 글 생성
# ============================================================
st.header("글 생성")
st.caption("기획 결과에서 선택한 기사 + 템플릿으로 블로그 글 생성")

if "gen_result" not in st.session_state:
    st.session_state["gen_result"] = None

if st.session_state.get("plan_results"):
    # 기획 결과에서 글 생성할 기사 선택
    plan_results = st.session_state["plan_results"]
    article_options = []
    for i, r in enumerate(plan_results):
        score_line = [l for l in r["response"].split("\n") if "점수:" in l]
        score = score_line[0].split(":")[-1].strip() if score_line else "?"
        tpl_line = [l for l in r["response"].split("\n") if "템플릿:" in l]
        tpl = tpl_line[0].split(":")[-1].strip() if tpl_line else "?"
        article_options.append(f"{i+1}. [점수:{score}] [{tpl}] {r['article']['title'][:40]}")

    selected_idx = st.selectbox("글 생성할 기사 선택", range(len(article_options)),
                                 format_func=lambda x: article_options[x], key="gen_select")

    selected = plan_results[selected_idx]
    article = selected["article"]
    plan_response = selected["response"]

    # 템플릿 선택
    tpl_line = [l for l in plan_response.split("\n") if "템플릿:" in l]
    detected_tpl = tpl_line[0].split(":")[-1].strip() if tpl_line else "local_issue"
    # local_ 로 시작하는 것만
    if not detected_tpl.startswith("local_"):
        detected_tpl = "local_issue"

    gen_template = st.selectbox("템플릿", ["local_event", "local_issue", "local_trend"],
                                 index=["local_event", "local_issue", "local_trend"].index(detected_tpl)
                                 if detected_tpl in ["local_event", "local_issue", "local_trend"] else 1,
                                 key="gen_tpl")

    # 템플릿에서 prompt_template 로드
    tpl_path = Path(f"data/templates/{gen_template}.json")
    tpl_data = json.loads(tpl_path.read_text(encoding="utf-8")) if tpl_path.exists() else {}
    prompt_tpl = tpl_data.get("prompt_template", "")

    # 이유 추출
    reason_line = [l for l in plan_response.split("\n") if "이유:" in l]
    reason = reason_line[0].split(":")[-1].strip() if reason_line else ""

    # 블로그 정보 로드
    blogs_json_gen = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))
    blog_info_gen = blogs_json_gen["blogs"].get(plan_blog, {})
    blog_name = blog_info_gen.get("name", plan_blog)
    blog_theme = blog_info_gen.get("theme", "")

    # 글 생성 프롬프트
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

    if st.session_state.get("gen_result"):
        st.subheader("생성된 글 (원문)")
        st.text_area("LLM 출력", st.session_state["gen_result"], height=300)

        # structure 기반 Playwright 미리보기
        st.subheader("Playwright 발행 미리보기")
        st.caption(f"템플릿: {gen_template} / structure 기반")

        raw = st.session_state["gen_result"]
        lines = raw.split("\n")

        # LLM 출력 파싱 → slot 매칭
        title = ""
        slots = {}
        current_slot = None
        current_lines = []
        slot_map = {
            "도입": "도입", "소제목1": None, "본문1": None,
            "소제목2": None, "본문2": None, "QA": None,
            "소제목3": None, "본문3": None, "해시태그": None,
        }
        heading_idx = 0
        text_idx = 0

        title_found = False
        for line in lines:
            l = line.strip()

            # 제목 파싱 ("제목:" 또는 "## 제목")
            if not title_found and (l.startswith("제목:") or (l.startswith("##") and heading_idx == 0)):
                if l.startswith("제목:"):
                    title = l.split(":", 1)[1].strip()
                else:
                    title = l.lstrip("#").strip()
                title_found = True
                continue

            # 해시태그 (#으로 시작하고 3개 이상)
            if l.startswith("#") and l.count("#") >= 3 and not l.startswith("##"):
                slots["해시태그"] = l
                continue

            # 소제목 파싱 ("## 텍스트" 또는 "소제목: 텍스트" 또는 "### 텍스트")
            is_heading = False
            heading_text = ""
            if l.startswith("##"):
                is_heading = True
                heading_text = l.lstrip("#").strip()
            elif l.startswith("소제목:") or l.startswith("소제목 :"):
                is_heading = True
                heading_text = l.split(":", 1)[1].strip()

            if is_heading:
                # 이전 슬롯 저장
                if current_slot and current_lines:
                    slots[current_slot] = "\n".join(current_lines)
                heading_idx += 1
                slots[f"소제목{heading_idx}"] = heading_text
                current_slot = f"본문{heading_idx}"
                current_lines = []
                continue

            # 본문 텍스트
            if current_slot:
                if l:
                    current_lines.append(l)
            elif title_found and l and heading_idx == 0:
                # 도입부 (제목 이후 ~ 첫 소제목 전)
                if "도입" not in slots:
                    slots["도입"] = l
                else:
                    slots["도입"] += "\n" + l

        # 마지막 슬롯 저장
        if current_slot and current_lines:
            slots[current_slot] = "\n".join(current_lines)

        # QA 분리 (본문2에 Q&A가 포함되어있을 수 있음)
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

        # structure 기반 미리보기 생성
        structure = tpl_data.get("structure", [])
        preview_html = '<div style="font-family: Malgun Gothic, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">'

        if title:
            preview_html += f'<h1 style="font-size: 1.8em; margin-bottom: 20px;">{title}</h1>'

        for item in structure:
            t = item.get("type", "")
            slot = item.get("slot", "")
            size = item.get("size", 15)
            content = item.get("content", "")

            if t == "blank":
                preview_html += "<br>"
            elif t == "image":
                if "썸네일" in content:
                    preview_html += '<div style="background: #f0f0f0; padding: 20px; text-align: center; margin: 10px 0; border-radius: 8px;">[썸네일 이미지]</div>'
                elif "쿠폰" in content:
                    preview_html += '<div style="background: #e3f2fd; padding: 15px; text-align: center; margin: 10px 0; border-radius: 8px;">[쿠폰 이미지]</div>'
                else:
                    preview_html += '<div style="background: #f5f5f5; padding: 15px; text-align: center; margin: 10px 0; border-radius: 8px;">[서비스 이미지]</div>'
            elif t == "heading":
                text = slots.get(slot, f"[{slot}]")
                font_size = {24: "1.6em", 19: "1.3em", 17: "1.1em"}.get(size, "1.2em")
                preview_html += f'<h2 style="font-size: {font_size}; font-weight: bold; margin: 20px 0 10px 0;">{text}</h2>'
            elif t == "text":
                text = slots.get(slot, f"[{slot}]")
                text_html = text.replace("\n", "<br>")
                preview_html += f'<p style="font-size: {size}px; line-height: 1.8; margin: 5px 0;">{text_html}</p>'
            elif t == "quote":
                text = slots.get(slot, f"[{slot}]")
                preview_html += f'<blockquote style="border-left: 3px solid #ccc; padding: 10px 15px; margin: 10px 0; color: #555;">{text}</blockquote>'
            elif t == "hashtags":
                text = slots.get(slot, "")
                preview_html += f'<p style="color: #0068c3; margin-top: 20px;">{text}</p>'

        preview_html += "</div>"
        st.html(preview_html)

        # Playwright 명령 리스트
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

        # 발행
        st.divider()
        st.subheader("네이버 블로그 발행")

        blogs_json_pub = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))
        blog_info_pub = blogs_json_pub["blogs"].get(plan_blog, {})
        blog_url = blog_info_pub.get("blog_url", "")

        st.warning(f"발행 대상: **{plan_blog}** (blog.naver.com/{blog_url})")

        if st.button("네이버 블로그에 발행", type="primary", key="publish_gen"):
            import subprocess, tempfile

            # structure 기반 Playwright 명령 생성 데이터
            publish_data = {
                "title": title,
                "slots": slots,
                "structure": structure,
                "blog_id": blog_url,
                "cookie_blog_id": plan_blog,
                "gen_template": gen_template,
            }

            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
            json.dump(publish_data, tmp, ensure_ascii=False)
            tmp.close()

            with st.spinner("네이버 블로그에 발행 중..."):
                result = subprocess.run(
                    ["python", "-X", "utf8", "publish_v2.py", tmp.name],
                    capture_output=True, text=True, timeout=180, encoding="utf-8",
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
                    st.error(f"발행 실패 — {result.stderr[:200] if result.stderr else '알 수 없는 오류'}")

else:
    st.info("먼저 글 기획을 실행하세요.")

st.divider()

# ── 탭 (상세 테스트용) ──
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "행사/축제 상세", "지역 상권", "핫한 지역", "경쟁 블로그", "실시간 트렌딩"
])

# ============================================================
# TAB 1: 행사/축제
# ============================================================
with tab1:
    st.header("행사/축제 정보 수집 (네이버 크롤링)")

    col1, col2 = st.columns(2)
    with col1:
        event_keywords = st.text_area(
            "검색 키워드 (줄바꿈 구분)",
            "축제\n박람회",
            height=100, key="event_kw"
        )
    with col2:
        event_pages = st.slider("키워드당 페이지 수", 1, 10, 5, key="event_pg")
        st.caption("1페이지 = 약 4~8건")

    # 저장된 데이터 표시
    today_file = Path(f"data/collected/{datetime.now().strftime('%Y%m%d')}_events.json")
    if today_file.exists():
        saved = json.loads(today_file.read_text(encoding="utf-8"))
        st.info(f"오늘 저장된 데이터: {len(saved)}건 ({today_file.name})")

    if st.button("크롤링 수집 시작", type="primary", key="run_event"):
        keywords = [q.strip() for q in event_keywords.split("\n") if q.strip()]

        with st.spinner(f"네이버에서 {', '.join(keywords)} 크롤링 중... (약 30초)"):
            import subprocess
            # Playwright는 별도 프로세스로 (Streamlit 이벤트 루프 충돌 방지)
            result = subprocess.run(
                ["python", "-X", "utf8", "-c", f"""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from collectors.naver_events import collect_and_save
path = collect_and_save(keywords={keywords}, max_pages={event_pages})
print(str(path))
"""],
                capture_output=True, text=True, timeout=120, encoding="utf-8",
            )

            if result.returncode == 0:
                # 저장된 파일 읽기
                saved_path = Path(f"data/collected/{datetime.now().strftime('%Y%m%d')}_events.json")
                if saved_path.exists():
                    events = json.loads(saved_path.read_text(encoding="utf-8"))
                    st.success(f"수집 완료: {len(events)}건")

                    # 요약
                    kw_counts = Counter(e["keyword"] for e in events)
                    for kw, cnt in kw_counts.items():
                        st.markdown(f"- **{kw}**: {cnt}건")

                    st.divider()

                    # 테이블 표시
                    st.subheader("수집 결과")
                    for i, e in enumerate(events):
                        with st.expander(f"{i+1}. [{e['keyword']}] {e['name']}"):
                            st.markdown(f"**기간**: {e['period']}")
                            st.markdown(f"**장소**: {e['place']}")
                else:
                    st.error("저장 파일을 찾을 수 없습니다")
            else:
                st.error(f"크롤링 실패: {result.stderr[:200]}")

    # 저장된 데이터 조회
    st.divider()
    st.subheader("저장된 행사 데이터")
    event_files = sorted(Path("data/collected").glob("*_events.json"), reverse=True)
    if event_files:
        selected_file = st.selectbox("파일 선택", event_files, format_func=lambda f: f.name)
        if selected_file:
            data = json.loads(selected_file.read_text(encoding="utf-8"))
            st.markdown(f"**총 {len(data)}건**")

            # 필터
            all_keywords = list(set(e.get("keyword", "") for e in data))
            filter_kw = st.multiselect("키워드 필터", all_keywords, default=all_keywords)
            filtered = [e for e in data if e.get("keyword", "") in filter_kw]

            for i, e in enumerate(filtered):
                st.markdown(f"{i+1}. **{e['name']}** | {e['period']} | {e['place']}")
    else:
        st.info("저장된 행사 데이터가 없습니다. 위에서 수집을 실행하세요.")

# ============================================================
# TAB 2: 지역 상권
# ============================================================
with tab2:
    st.header("지역 상권 정보 수집")

    region = st.text_input("지역명", "서울 마포구", key="region_input")
    market_queries_default = f"{region} 창업\n{region} 맛집\n{region} 상권\n{region} 카페"
    market_queries = st.text_area("검색 키워드", market_queries_default, height=120, key="market_q")

    if st.button("상권 정보 수집", type="primary", key="run_market"):
        queries = [q.strip() for q in market_queries.split("\n") if q.strip()]

        # 뉴스
        st.subheader("뉴스")
        for query in queries:
            results = search_naver_news(query, 3)
            st.markdown(f"**\"{query}\"** — {len(results)}건")
            for r in results:
                st.markdown(f"- {r['title']}")
                st.caption(r['description'][:100])

        # 데이터랩
        st.subheader("검색량 트렌드")
        trend_keywords = [q.split()[-1] if " " in q else q for q in queries[:5]]
        trends = get_search_trend(trend_keywords)
        if trends:
            for kw, data in trends.items():
                growth_emoji = "📈" if data["growth"] > 0 else "📉"
                st.markdown(f"- **{kw}**: 평균 {data['avg']} {growth_emoji} {data['growth']}%")
        else:
            st.info("데이터랩 결과 없음")

        # 자동완성
        st.subheader("연관 검색어")
        suggests = get_naver_suggest(f"{region} 상표")
        if suggests:
            st.markdown(", ".join(suggests))
        else:
            st.info("자동완성 결과 없음")

# ============================================================
# TAB 3: 핫한 지역
# ============================================================
with tab3:
    st.header("핫한 지역 추출")

    if st.button("핫한 지역 분석", type="primary", key="run_hot"):
        # 구글 트렌딩에서 지역명 추출
        st.subheader("구글 트렌딩 → 지역 추출")
        trends = get_google_trending()
        regions_json = Path("data/service_data/regions.json")
        all_regions = []
        if regions_json.exists():
            data = json.loads(regions_json.read_text(encoding="utf-8"))
            for districts in data.values():
                all_regions.extend(districts)

        hot_regions = []
        for t in trends[:10]:
            keyword = t["keyword"]
            for region in all_regions:
                short = region.replace("시", "").replace("구", "").replace("군", "")
                if short in keyword:
                    hot_regions.append({"지역": region, "키워드": keyword, "트래픽": t["traffic"]})

        if hot_regions:
            for h in hot_regions:
                st.markdown(f"- **{h['지역']}** (키워드: {h['키워드']}, {h['트래픽']})")
        else:
            st.info("트렌딩에서 지역명 없음")

        # 뉴스에서 지역 추출
        st.subheader("오늘 뉴스 → 지역 추출")
        news = search_naver_news("창업 상권", 10)
        news_regions = []
        for n in news:
            for region in all_regions:
                short = region.replace("시", "").replace("구", "").replace("군", "")
                if len(short) >= 2 and short in n["title"]:
                    news_regions.append({"지역": region, "뉴스": n["title"][:50]})

        if news_regions:
            for h in news_regions:
                st.markdown(f"- **{h['지역']}**: {h['뉴스']}")
        else:
            st.info("뉴스에서 지역명 없음")

        # 트렌딩 전체 표시
        st.subheader("구글 트렌딩 전체")
        for t in trends:
            news_str = " / ".join(t["news"][:2]) if t["news"] else ""
            st.markdown(f"- **{t['keyword']}** ({t['traffic']}) {news_str}")

# ============================================================
# TAB 4: 경쟁 블로그
# ============================================================
with tab4:
    st.header("경쟁 블로그 수집")

    comp_queries = st.text_area(
        "검색 키워드 (줄바꿈 구분)",
        "상표 출원 방법\n상표 등록 비용\n브랜드 보호\n상표 셀프 출원\n지역 상표등록",
        height=120, key="comp_q"
    )

    if st.button("경쟁 블로그 수집", type="primary", key="run_comp"):
        queries = [q.strip() for q in comp_queries.split("\n") if q.strip()]
        for query in queries:
            results = search_naver_blog(query, 3)
            st.markdown(f"**\"{query}\"** — {len(results)}건")
            for r in results:
                st.markdown(f"- [{r['title']}]({r['link']})")
                st.caption(r['description'][:100])
            st.divider()

# ============================================================
# TAB 5: 실시간 트렌딩
# ============================================================
with tab5:
    st.header("실시간 트렌딩")

    if st.button("구글 트렌딩 수집", type="primary", key="run_trending"):
        trends = get_google_trending()
        st.subheader(f"{len(trends)}개 트렌딩 키워드")
        for i, t in enumerate(trends):
            with st.expander(f"{i+1}. {t['keyword']} ({t['traffic']})"):
                if t["news"]:
                    for n in t["news"]:
                        st.markdown(f"- {n}")
                else:
                    st.info("관련 뉴스 없음")
