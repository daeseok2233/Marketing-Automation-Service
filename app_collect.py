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
st.caption("수집된 데이터를 기반으로 LLM이 주제 선정 + 코드가 레퍼런스 확보")

col_plan1, col_plan2 = st.columns(2)
with col_plan1:
    plan_blog = st.selectbox("블로그 선택", ["blog_02", "blog_03", "blog_04", "blog_05", "blog_06", "blog_07"], key="plan_blog")
with col_plan2:
    plan_count = st.slider("기획할 글 수", 1, 30, 5, key="plan_count")

# 오늘 기획 파일 확인
plan_file = Path(f"data/generated/{today_str}_{plan_blog}_plan.json")
if plan_file.exists():
    saved_plans = json.loads(plan_file.read_text(encoding="utf-8"))
    st.info(f"오늘 기획된 데이터: {len(saved_plans)}개 ({plan_file.name})")

if st.button("글 기획 실행", type="primary", key="run_plan"):
    import subprocess
    with st.spinner(f"{plan_blog} — {plan_count}개 기획 중... (주제 선정 + 레퍼런스 수집)"):
        result = subprocess.run(
            ["python", "-X", "utf8", "-c",
             f"from blog_generator.planner_v2 import plan_blog_topics; plan_blog_topics('{plan_blog}', {plan_count})"],
            capture_output=True, text=True, timeout=180, encoding="utf-8",
        )
        if plan_file.exists():
            saved_plans = json.loads(plan_file.read_text(encoding="utf-8"))
            st.success(f"기획 완료: {len(saved_plans)}개")
        else:
            st.error(f"기획 실패: {result.stderr[:200]}")

# 기획 결과 표시
if plan_file.exists():
    plans = json.loads(plan_file.read_text(encoding="utf-8"))

    # 템플릿별 카운트
    tpl_counts = Counter(p.get("template", "") for p in plans)
    if tpl_counts:
        cols = st.columns(len(tpl_counts))
        for col, (tpl, cnt) in zip(cols, tpl_counts.items()):
            col.metric(tpl, f"{cnt}개")
    else:
        st.warning("기획된 글이 없습니다")

    st.divider()

    for i, p in enumerate(plans):
        template = p.get("template", "")
        title = p.get("article_title", "")
        desc = p.get("article_desc", "")
        link = p.get("article_link", "")
        keyword = p.get("article_keyword", "")
        source = p.get("article_source", "naver")
        source_label = "N" if source == "naver" else "G"

        with st.expander(f"{i+1}. [{template}] [{source_label}] {title[:60]}"):
            st.markdown(f"**기사 제목**: {title}")
            if desc:
                st.markdown(f"**기사 설명**: {desc[:150]}")
            st.markdown(f"**키워드**: {keyword}")
            st.markdown(f"**출처**: {'네이버' if source == 'naver' else '구글'}")
            if link:
                st.markdown(f"[기사 링크]({link})")

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
