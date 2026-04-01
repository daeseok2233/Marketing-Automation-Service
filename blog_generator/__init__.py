# blog_generator 패키지
#
# 파이프라인:
#   1) 범용: topic_selector → reference_builder → prompt_builder → writer → legal_checker
#   2) 지역 블로그: planner → local_blog_writer (+ thumbnail_maker)
