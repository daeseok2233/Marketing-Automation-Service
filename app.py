"""블로그 자동화 메인 대시보드.

파이프라인:
  1) collect  — 일일 데이터 수집 (행사/뉴스)
  2) plan     — 글 기획 (LLM 기사 평가)
  3) generate — 글 생성 (LLM 본문 작성)
  4) publish  — 네이버 블로그 발행

각 단계 모듈은 blog_generator/ 폴더에 있다 (UI + 로직 통합).
저수준 라이브러리: collectors/ (수집), publisher/ (Playwright 세션).
실행: streamlit run app.py
"""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="블로그 자동화", layout="wide")
st.title("블로그 자동화 파이프라인")

from blog_generator import collect, plan, generate, publish, tabs

# 세션 상태 초기화
for key in ["plan_result", "plan_results", "gen_result"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ── 메인 파이프라인 ──
collect.render()
st.divider()

plan.render()
st.divider()

generate.render()
publish.render()
st.divider()

# ── 상세 테스트 탭 ──
tabs.render()
