"""각 블로그마다 5개씩 발행하는 배치 스크립트."""

import json
import sys
import os
import random
import time
from pathlib import Path
from datetime import datetime

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

blogs_data = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))

# 블로그별 예시 토픽
TOPICS = {
    "blog_02": [
        {"business": "상표 출원", "angle": "상표 출원 절차, 초보자도 쉽게 따라하는 방법", "keywords": ["상표 출원 방법", "상표 등록 절차"]},
        {"business": "상표 비용", "angle": "상표 출원 비용, 얼마나 들까? 비용 비교", "keywords": ["상표 출원 비용", "변리사 비용"]},
        {"business": "상표 검색", "angle": "상표 검색 방법, 등록 전 반드시 확인해야 할 것", "keywords": ["상표 검색", "유사 상표"]},
        {"business": "상표 갱신", "angle": "상표 갱신 시기와 절차, 놓치면 상표를 잃는다", "keywords": ["상표 갱신", "상표 존속기간"]},
        {"business": "셀프 출원", "angle": "셀프 상표 출원 vs 변리사 대행, 어떤 게 나을까?", "keywords": ["셀프 출원", "변리사 대행"]},
    ],
    "blog_03": [
        {"business": "상표 분쟁", "angle": "상표 분쟁 사례 분석, 이런 실수 하지 마세요", "keywords": ["상표 분쟁", "상표 침해"]},
        {"business": "상표법", "angle": "상표법 개정 포인트, 사업자가 알아야 할 변화", "keywords": ["상표법", "상표법 개정"]},
        {"business": "브랜드 보호", "angle": "브랜드 보호 전략, 전문가가 말하는 핵심 3가지", "keywords": ["브랜드 보호", "지식재산"]},
        {"business": "특허 출원", "angle": "특허 출원 전 꼭 확인해야 할 주의사항", "keywords": ["특허 출원", "특허 등록"]},
        {"business": "디자인 출원", "angle": "디자인 출원, 왜 상표와 함께 해야 할까?", "keywords": ["디자인 출원", "디자인 등록"]},
    ],
    "blog_04": [
        {"region": "서울 강남구", "business": "카페", "angle": "강남 카페 창업 트렌드, 상표등록은 필수", "keywords": ["강남 카페", "강남 상표등록"]},
        {"region": "부산 해운대구", "business": "요식업", "angle": "해운대 맛집 경쟁, 상표로 브랜드 지키기", "keywords": ["해운대 맛집", "해운대 상표등록"]},
        {"region": "대전 유성구", "business": "IT 스타트업", "angle": "유성구 스타트업 붐, 상표등록 서두르세요", "keywords": ["대전 스타트업", "유성구 창업"]},
        {"region": "인천 연수구", "business": "뷰티샵", "angle": "송도 뷰티 상권, 브랜드 보호가 급선무", "keywords": ["송도 뷰티", "인천 상표등록"]},
        {"region": "광주 서구", "business": "음식점", "angle": "광주 서구 음식점 창업 증가, 상표 보호 필수", "keywords": ["광주 음식점", "광주 상표등록"]},
    ],
    "blog_05": [
        {"region": "수원 영통구", "business": "학원", "angle": "영통 학원가 경쟁, 상표등록으로 브랜드 보호", "keywords": ["수원 학원", "영통 상표등록"]},
        {"region": "성남 분당구", "business": "카페", "angle": "분당 카페 상권, 유사 상호 조심하세요", "keywords": ["분당 카페", "분당 상표등록"]},
        {"region": "고양 일산동구", "business": "요식업", "angle": "일산 맛집 상권, 브랜드 보호가 시급합니다", "keywords": ["일산 맛집", "일산 상표등록"]},
        {"region": "제주시", "business": "관광업", "angle": "제주 관광업 브랜드, 상표등록 안 하면 위험", "keywords": ["제주 관광", "제주 상표등록"]},
        {"region": "춘천시", "business": "음식점", "angle": "춘천 닭갈비 상권, 상표 분쟁 사전 예방", "keywords": ["춘천 닭갈비", "춘천 상표등록"]},
    ],
    "blog_06": [
        {"region": "창원시", "business": "제조업", "angle": "창원 제조업 브랜드, 상표등록이 경쟁력입니다", "keywords": ["창원 제조업", "창원 상표등록"]},
        {"region": "전주시", "business": "한식당", "angle": "전주 한식 브랜드, 상표로 전통을 지키세요", "keywords": ["전주 한식", "전주 상표등록"]},
        {"region": "포항시", "business": "수산업", "angle": "포항 수산 브랜드, 상표등록 안 하면 손해", "keywords": ["포항 수산", "포항 상표등록"]},
        {"region": "여수시", "business": "관광업", "angle": "여수 관광 브랜드, 상표로 차별화하세요", "keywords": ["여수 관광", "여수 상표등록"]},
        {"region": "경주시", "business": "관광업", "angle": "경주 관광 상권, 브랜드 보호 체크리스트", "keywords": ["경주 관광", "경주 상표등록"]},
    ],
    "blog_07": [
        {"region": "서울 송파구", "business": "피트니스", "angle": "잠실 피트니스 경쟁, 상표등록으로 브랜드 보호", "keywords": ["잠실 피트니스", "송파구 상표등록"]},
        {"region": "서울 영등포구", "business": "카페", "angle": "여의도 카페 상권, 상표 없이 장사하면 위험", "keywords": ["여의도 카페", "영등포 상표등록"]},
        {"region": "울산 남구", "business": "요식업", "angle": "울산 남구 맛집 상권, 브랜드 보호 시급", "keywords": ["울산 맛집", "울산 상표등록"]},
        {"region": "대구 달서구", "business": "뷰티샵", "angle": "달서구 뷰티 상권, 유사 상호 주의보", "keywords": ["대구 뷰티", "달서구 상표등록"]},
        {"region": "세종시", "business": "교육업", "angle": "세종시 학원 창업 붐, 상표등록 잊지 마세요", "keywords": ["세종시 학원", "세종 상표등록"]},
    ],
}

results = []
total = sum(len(v) for v in TOPICS.values())
count = 0

for blog_id, topics in TOPICS.items():
    blog_info = blogs_data["blogs"].get(blog_id, {})
    blog_url = blog_info.get("blog_url", "")
    templates = blog_info.get("templates", [])

    if not blog_url:
        print(f"[SKIP] {blog_id}: blog_url 없음")
        continue

    print(f"\n{'='*50}")
    print(f"  {blog_id} ({blog_url}) — {len(topics)}개 발행")
    print(f"{'='*50}")

    for i, topic in enumerate(topics):
        count += 1
        template = random.choice(templates)
        topic["template"] = template

        print(f"\n  [{count}/{total}] {blog_id} / {template}")

        try:
            from blog_generator.blog_writer import write_local_blog
            blog = write_local_blog(topic, template_name=template)

            title = blog.get("title", "")
            slots = blog.get("_slots", {})
            print(f"  제목: {title[:40]}")
            print(f"  슬롯: {len(slots)}개")

            if not slots or not title:
                print(f"  [FAIL] 생성 실패 — 스킵")
                results.append({"blog_id": blog_id, "error": "생성 실패", "template": template})
                continue

            # 발행
            from publisher.naver_blog import publish_to_naver
            url = publish_to_naver(blog, blog_id=blog_url, template_name=template, cookie_blog_id=blog_id)

            if url:
                print(f"  [OK] {url}")
                results.append({"blog_id": blog_id, "title": title, "template": template, "url": url})
            else:
                print(f"  [FAIL] 발행 실패")
                results.append({"blog_id": blog_id, "title": title, "error": "발행 실패", "template": template})

        except Exception as e:
            print(f"  [ERROR] {e}")
            results.append({"blog_id": blog_id, "error": str(e)[:100], "template": template})

        # 글 사이 대기
        time.sleep(5)

# 결과 저장
log_path = Path("data/generated") / f"{datetime.now().strftime('%Y%m%d')}_batch_publish.json"
log_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

# 요약
success = len([r for r in results if "error" not in r])
fail = len([r for r in results if "error" in r])
print(f"\n{'='*50}")
print(f"  완료: {success} 성공 / {fail} 실패 (총 {len(results)})")
print(f"  로그: {log_path}")
print(f"{'='*50}")
