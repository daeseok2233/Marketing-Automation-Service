"""블로그 포스팅 자동화 파이프라인 — 메인 진입점.

사용법:
    python run.py collect      — 데이터 수집만
    python run.py generate     — 글 생성만 (수집 데이터 필요)
    python run.py local [blog_id] [N] — 지역 블로그 생성 (예: local blog_04 10)
    python run.py all          — 수집 + 생성
"""

from dotenv import load_dotenv
load_dotenv()


def run_collect():
    """데이터 수집 파이프라인."""
    print("=" * 60)
    print("  데이터 수집 파이프라인")
    print("=" * 60)
    from collectors import collect_all
    return collect_all()


def run_generate():
    """범용 글 생성 파이프라인 (수집 데이터 기반)."""
    print("=" * 60)
    print("  블로그 생성 파이프라인")
    print("=" * 60)

    print("\n[1/5] 주제 선정 중...")
    from blog_generator.topic_selector import select_topic
    topic = select_topic()
    print(f"  주제: {topic['topic']}")
    print(f"  템플릿: {topic['template']}")

    print("\n[2/5] 레퍼런스 생성 중...")
    from blog_generator.reference_builder import build_reference
    reference = build_reference(topic)
    print(f"  뉴스 {len(reference.get('related_news', []))}건, 경쟁사 {len(reference.get('related_competitors', []))}건")

    print("\n[3/5] 프롬프트 구성 중...")
    from blog_generator.prompt_builder import build_prompt
    prompt = build_prompt(topic, reference)
    print(f"  시스템: {len(prompt['system_prompt'])}자, 유저: {len(prompt['user_prompt'])}자")

    print("\n[4/5] 글 생성 중...")
    from blog_generator.writer import write_blog
    blog = write_blog(prompt)
    print(f"  제목: {blog.get('title', '(파싱 실패)')}")
    print(f"  본문: {len(blog.get('body', ''))}자")

    print("\n[5/5] 법률 검증 중...")
    from blog_generator.legal_checker import check_legal
    final = check_legal(blog)
    print(f"  검증: {final.get('legal_note', '')}")

    print(f"\n  완료! 제목: {final.get('title', '')}")
    return final


def run_local(count: int = 10, upload: bool = True, blog_id: str = "blog_04"):
    """AI 플래너 기반 지역 블로그 생성 + 노션 업로드."""
    import json
    from pathlib import Path
    from datetime import datetime

    print("=" * 60)
    print(f"  {blog_id} — 지역 블로그 {count}개 생성")
    print("=" * 60)

    # 블로그별 사용 가능 템플릿 로드
    import random
    blogs_data = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))
    blog_templates = blogs_data.get("blogs", {}).get(blog_id, {}).get("templates", ["local_trend"])

    # ── 1단계: AI가 주제 계획 ──
    print(f"\n[1/3] AI 플래너 — {blog_id} 주제 계획 중...")
    print(f"  사용 가능 템플릿: {blog_templates}")
    from blog_generator.planner import plan_topics, search_for_topic
    topics = plan_topics(count=count, blog_id=blog_id)
    for i, t in enumerate(topics):
        print(f"  {i+1:2d}. {t['region']} × {t['business']} — {t.get('angle', '')[:30]}")

    # ── 2단계: 주제별 타겟 데이터 수집 ──
    print(f"\n[2/3] 주제별 맞춤 데이터 수집 중...")
    for i, topic in enumerate(topics):
        ref = search_for_topic(topic)
        topic["_reference"] = ref
        print(f"  {i+1:2d}. 뉴스 {len(ref['news'])}건 + 블로그 {len(ref['blogs'])}건")

    # ── 3단계: 글 생성 + 업로드 ──
    from blog_generator.local_blog_writer import write_local_blog

    results = []
    today = datetime.now().strftime("%Y%m%d")
    out = Path("data/generated")
    out.mkdir(parents=True, exist_ok=True)

    for i, topic in enumerate(topics):
        print(f"\n[3/3] [{i+1}/{count}] {topic['region']} × {topic['business']}")

        # 레퍼런스 추출
        ref = topic.pop("_reference", {})
        ref_news_list = ref.get("news", [])
        ref_blog_list = ref.get("blogs", [])
        ref_queries = ref.get("queries", [])

        if ref_news_list:
            topic["ref_news"] = "\n".join(f"- {n['title']}" for n in ref_news_list)
        if ref_blog_list:
            topic["ref_blogs"] = "\n".join(f"- {b['title']}" for b in ref_blog_list)

        # 템플릿 랜덤 선택
        selected_template = random.choice(blog_templates)
        print(f"  템플릿: {selected_template}")

        blog = write_local_blog(topic, template_name=selected_template)
        print(f"  제목: {blog.get('title', '(파싱실패)')}")
        print(f"  본문: {len(blog.get('body', ''))}자")
        print(f"  모델: {blog['model_info']['model']}")

        # 파이프라인 과정 로그
        from publisher.process_logger import build_process_log
        process_log = build_process_log(
            step_num=i + 1, topic=topic,
            ref_queries=ref_queries, ref_news=ref_news_list,
            ref_blogs=ref_blog_list, blog=blog,
        )
        blog["_process_log"] = process_log

        # 저장
        safe_biz = topic["business"].replace("/", "_").replace("\\", "_").replace(" ", "_")
        (out / f"{today}_blog_{i+1:02d}_{safe_biz}.json").write_text(
            json.dumps(blog, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Word 파일 저장
        from publisher.docx_exporter import export_to_docx
        safe_title = blog.get("title", "untitled").replace("/", "_")[:30]
        docx_path = export_to_docx(blog, str(out / f"{today}_blog_{i+1:02d}_{safe_title}.docx"))
        blog["docx_path"] = docx_path

        # 노션 업로드
        if upload:
            from publisher.notion_upload import upload_to_notion
            blog_with_log = blog.copy()
            blog_with_log["body"] = blog["body"] + "\n\n" + process_log
            url = upload_to_notion(
                blog_with_log, template_name=selected_template,
                keywords=", ".join(topic.get("keywords", []))
            )
            blog["notion_url"] = url

        results.append(blog)

    # 블로그별 사용 기록 저장
    state_path = Path("data/schedule_state.json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if blog_id not in state:
        state[blog_id] = []
    for i2, t in enumerate(topics):
        state[blog_id].append({
            "date": today,
            "region": t.get("region", ""),
            "business": t.get("business", ""),
            "title": results[i2].get("title", "") if i2 < len(results) else "",
        })
    # 최근 100개만 유지
    state[blog_id] = state[blog_id][-100:]
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"  완료! {len(results)}개 글 생성")
    for i, r in enumerate(results):
        status = "✓" if r.get("body") else "✗"
        print(f"  {status} {i+1:2d}. {r.get('title', '제목없음')[:50]}")
    print("=" * 60)

    return results


def run_all():
    """데이터 수집 + 글 생성 전체 파이프라인."""
    run_collect()
    return run_generate()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "collect":
            run_collect()
        elif cmd == "generate":
            run_generate()
        elif cmd == "local":
            blog_id = sys.argv[2] if len(sys.argv) > 2 else "blog_04"
            count = int(sys.argv[3]) if len(sys.argv) > 3 else 10
            run_local(count=count, blog_id=blog_id)
        elif cmd == "all":
            run_all()
        else:
            print(__doc__)
    else:
        print(__doc__)
