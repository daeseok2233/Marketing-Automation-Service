"""상세 테스트용 탭 — 행사/축제, 지역 상권, 핫한 지역, 경쟁 블로그, 실시간 트렌딩."""

import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import requests
import streamlit as st


NAVER_HEADERS = {
    "X-Naver-Client-Id": os.environ.get("NAVER_CLIENT_ID", ""),
    "X-Naver-Client-Secret": os.environ.get("NAVER_CLIENT_SECRET", ""),
}


# ─── 공용 검색 함수 ────────────────────────────────────────
def search_naver_news(query, count=5):
    try:
        r = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            params={"query": query, "display": count, "sort": "date"},
            headers=NAVER_HEADERS, timeout=5,
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            return [{
                "title": it["title"].replace("<b>", "").replace("</b>", ""),
                "description": it.get("description", "").replace("<b>", "").replace("</b>", "")[:150],
                "link": it.get("link", ""),
                "pubDate": it.get("pubDate", ""),
            } for it in items]
    except Exception:
        pass
    return []


def search_naver_blog(query, count=5):
    try:
        r = requests.get(
            "https://openapi.naver.com/v1/search/blog.json",
            params={"query": query, "display": count, "sort": "sim"},
            headers=NAVER_HEADERS, timeout=5,
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            return [{
                "title": it["title"].replace("<b>", "").replace("</b>", ""),
                "description": it.get("description", "").replace("<b>", "").replace("</b>", "")[:150],
                "link": it.get("link", ""),
            } for it in items]
    except Exception:
        pass
    return []


def get_google_trending():
    import xml.etree.ElementTree as ET
    try:
        r = requests.get(
            "https://trends.google.com/trending/rss?geo=KR",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10,
        )
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
    try:
        r = requests.get(
            "https://ac.search.naver.com/nx/ac",
            params={"q": keyword, "con": 1, "frm": "nv", "ans": 2}, timeout=5,
        )
        if r.status_code == 200:
            items = r.json().get("items", [[]])[0]
            return [item[0] for item in items if item][:10]
    except Exception:
        pass
    return []


def get_search_trend(keywords):
    today = datetime.now()
    start = (today - timedelta(days=90)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    keyword_groups = [{"groupName": kw, "keywords": [kw]} for kw in keywords[:5]]
    try:
        r = requests.post(
            "https://openapi.naver.com/v1/datalab/search",
            headers={**NAVER_HEADERS, "Content-Type": "application/json"},
            json={"startDate": start, "endDate": end, "timeUnit": "week", "keywordGroups": keyword_groups},
            timeout=10,
        )
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


# ─── 탭 렌더 함수 ──────────────────────────────────────────
def _tab_events():
    st.header("행사/축제 정보 수집 (네이버 크롤링)")

    col1, col2 = st.columns(2)
    with col1:
        event_keywords = st.text_area(
            "검색 키워드 (줄바꿈 구분)", "축제\n박람회",
            height=100, key="event_kw",
        )
    with col2:
        event_pages = st.slider("키워드당 페이지 수", 1, 10, 5, key="event_pg")
        st.caption("1페이지 = 약 4~8건")

    today_file = Path(f"data/collected/{datetime.now().strftime('%Y%m%d')}_events.json")
    if today_file.exists():
        saved = json.loads(today_file.read_text(encoding="utf-8"))
        st.info(f"오늘 저장된 데이터: {len(saved)}건 ({today_file.name})")

    if st.button("크롤링 수집 시작", type="primary", key="run_event"):
        keywords = [q.strip() for q in event_keywords.split("\n") if q.strip()]
        with st.spinner(f"네이버에서 {', '.join(keywords)} 크롤링 중... (약 30초)"):
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
                saved_path = Path(f"data/collected/{datetime.now().strftime('%Y%m%d')}_events.json")
                if saved_path.exists():
                    events = json.loads(saved_path.read_text(encoding="utf-8"))
                    st.success(f"수집 완료: {len(events)}건")
                    kw_counts = Counter(e["keyword"] for e in events)
                    for kw, cnt in kw_counts.items():
                        st.markdown(f"- **{kw}**: {cnt}건")
                    st.divider()
                    st.subheader("수집 결과")
                    for i, e in enumerate(events):
                        with st.expander(f"{i+1}. [{e['keyword']}] {e['name']}"):
                            st.markdown(f"**기간**: {e['period']}")
                            st.markdown(f"**장소**: {e['place']}")
                else:
                    st.error("저장 파일을 찾을 수 없습니다")
            else:
                st.error(f"크롤링 실패: {result.stderr[:200]}")

    st.divider()
    st.subheader("저장된 행사 데이터")
    event_files = sorted(Path("data/collected").glob("*_events.json"), reverse=True)
    if event_files:
        selected_file = st.selectbox("파일 선택", event_files, format_func=lambda f: f.name)
        if selected_file:
            data = json.loads(selected_file.read_text(encoding="utf-8"))
            st.markdown(f"**총 {len(data)}건**")
            all_keywords = list(set(e.get("keyword", "") for e in data))
            filter_kw = st.multiselect("키워드 필터", all_keywords, default=all_keywords)
            filtered = [e for e in data if e.get("keyword", "") in filter_kw]
            for i, e in enumerate(filtered):
                st.markdown(f"{i+1}. **{e['name']}** | {e['period']} | {e['place']}")
    else:
        st.info("저장된 행사 데이터가 없습니다. 위에서 수집을 실행하세요.")


def _tab_market():
    st.header("지역 상권 정보 수집")

    region = st.text_input("지역명", "서울 마포구", key="region_input")
    market_queries_default = f"{region} 창업\n{region} 맛집\n{region} 상권\n{region} 카페"
    market_queries = st.text_area("검색 키워드", market_queries_default, height=120, key="market_q")

    if st.button("상권 정보 수집", type="primary", key="run_market"):
        queries = [q.strip() for q in market_queries.split("\n") if q.strip()]

        st.subheader("뉴스")
        for query in queries:
            results = search_naver_news(query, 3)
            st.markdown(f"**\"{query}\"** — {len(results)}건")
            for r in results:
                st.markdown(f"- {r['title']}")
                st.caption(r['description'][:100])

        st.subheader("검색량 트렌드")
        trend_keywords = [q.split()[-1] if " " in q else q for q in queries[:5]]
        trends = get_search_trend(trend_keywords)
        if trends:
            for kw, data in trends.items():
                growth_emoji = "📈" if data["growth"] > 0 else "📉"
                st.markdown(f"- **{kw}**: 평균 {data['avg']} {growth_emoji} {data['growth']}%")
        else:
            st.info("데이터랩 결과 없음")

        st.subheader("연관 검색어")
        suggests = get_naver_suggest(f"{region} 상표")
        if suggests:
            st.markdown(", ".join(suggests))
        else:
            st.info("자동완성 결과 없음")


def _tab_hot_regions():
    st.header("핫한 지역 추출")

    if st.button("핫한 지역 분석", type="primary", key="run_hot"):
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

        st.subheader("구글 트렌딩 전체")
        for t in trends:
            news_str = " / ".join(t["news"][:2]) if t["news"] else ""
            st.markdown(f"- **{t['keyword']}** ({t['traffic']}) {news_str}")


def _tab_competitors():
    st.header("경쟁 블로그 수집")

    comp_queries = st.text_area(
        "검색 키워드 (줄바꿈 구분)",
        "상표 출원 방법\n상표 등록 비용\n브랜드 보호\n상표 셀프 출원\n지역 상표등록",
        height=120, key="comp_q",
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


def _tab_trending():
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


def render():
    """5개 상세 테스트 탭."""
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "행사/축제 상세", "지역 상권", "핫한 지역", "경쟁 블로그", "실시간 트렌딩"
    ])
    with tab1:
        _tab_events()
    with tab2:
        _tab_market()
    with tab3:
        _tab_hot_regions()
    with tab4:
        _tab_competitors()
    with tab5:
        _tab_trending()
