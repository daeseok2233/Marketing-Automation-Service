# blog_generator 패키지
#
# 파이프라인:
#   1) 기획: planner (뉴스 기반 기사 선별)
#   2) 글 생성: app_collect.py에서 직접 LLM 호출
#   3) 품질 검증: quality_checker
#   4) 썸네일: thumbnail_maker
