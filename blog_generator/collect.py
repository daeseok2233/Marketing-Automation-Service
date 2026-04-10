"""일일 데이터 수집 — 행사/축제 크롤링 + 핵심 뉴스 수집."""

import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

import streamlit as st


def _today_files():
    today_str = datetime.now().strftime("%Y%m%d")
    return (
        Path(f"data/collected/{today_str}_events.json"),
        Path(f"data/collected/{today_str}_daily_news.json"),
    )


def render():
    st.header("일일 데이터 수집")
    st.caption("하루 1회 실행 — 행사/축제 크롤링 + 핵심 뉴스 수집")

    events_file, news_file = _today_files()

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
