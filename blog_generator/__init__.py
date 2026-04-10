# blog_generator 패키지 — 블로그 발행 파이프라인 전체
#
# 단계별 모듈 (Streamlit UI + 로직):
#   collect.py    — 일일 데이터 수집
#   plan.py       — 글 기획 (LLM 기사 평가)
#   generate.py   — 글 생성 (LLM 본문 작성)
#   publish.py    — 네이버 블로그 발행
#   tabs.py       — 상세 테스트 탭
#
# 발행 인프라:
#   naver_session.py  — 네이버 블로그 Playwright 세션 매니저 (get_session, _check_login)
#   slack_notify.py   — 발행 성공/실패/쿠키만료 슬랙 알림
#
# 보조 모듈:
#   quality_checker.py  — 글 품질 검증
#   region_selector.py  — 지역 선택
#   thumbnail_maker.py  — 썸네일 생성
#
# 저수준 데이터 수집 라이브러리는 별도 패키지:
#   collectors/  — 네이버 뉴스/행사 크롤링
