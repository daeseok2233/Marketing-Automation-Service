"""멀티 블로그 자동 발행 스케줄러.

blog_02~06: 하루 3개, 최소 3시간 텀
blog_07: 하루 10개, 최소 1시간 텀
"""

import random
import time
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

STATE_PATH = Path("data/schedule_state.json")

# 블로그별 설정
BLOG_CONFIGS = {
    "blog_02": {"posts_per_day": 30, "min_interval_hours": 1, "max_interval_hours": 2},
    "blog_03": {"posts_per_day": 30, "min_interval_hours": 1, "max_interval_hours": 2},
    "blog_04": {"posts_per_day": 30, "min_interval_hours": 1, "max_interval_hours": 2},
    "blog_05": {"posts_per_day": 30, "min_interval_hours": 1, "max_interval_hours": 2},
    "blog_06": {"posts_per_day": 30, "min_interval_hours": 1, "max_interval_hours": 2},
    "blog_07": {"posts_per_day": 40, "min_interval_min": 30, "max_interval_min": 42},
}


def _load_blogs_json() -> dict:
    return json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))


def _get_today_count(blog_id: str) -> int:
    if not STATE_PATH.exists():
        return 0
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    today = datetime.now().strftime("%Y%m%d")
    entries = state.get(blog_id, [])
    return sum(1 for e in entries if e.get("date") == today)


def _save_history(blog_id: str, topic: dict, blog: dict):
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    if blog_id not in state:
        state[blog_id] = []
    state[blog_id].append({
        "date": datetime.now().strftime("%Y%m%d"),
        "region": topic.get("region", ""),
        "business": topic.get("business", ""),
        "title": blog.get("title", ""),
        "template": topic.get("template", ""),
    })
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
    state[blog_id] = [e for e in state[blog_id] if e.get("date", "") >= cutoff]
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 블로그별 주제 큐 (하루 시작 시 한 번에 생성) ──
_topic_queues = {}  # {blog_id: [topic1, topic2, ...]}


def _ensure_topic_queue(blog_id: str):
    """블로그별 주제 큐가 비었으면 하루치를 한 번에 생성."""
    if blog_id in _topic_queues and _topic_queues[blog_id]:
        return  # 큐에 아직 주제가 남아있음

    config = BLOG_CONFIGS.get(blog_id, {})
    remaining = config.get("posts_per_day", 10) - _get_today_count(blog_id)
    if remaining <= 0:
        _topic_queues[blog_id] = []
        return

    print(f"  [{blog_id}] 하루치 주제 {remaining}개 일괄 생성 중...")
    from blog_generator.planner import plan_topics
    topics = plan_topics(count=remaining, blog_id=blog_id)
    _topic_queues[blog_id] = topics
    print(f"  [{blog_id}] 주제 큐: {len(topics)}개 준비 완료")


def publish_one(blog_id: str, use_agent: bool = True) -> dict | None:
    """블로그 1개에 글 1개 생성 + 발행.

    Args:
        blog_id: 블로그 ID
        use_agent: True면 에이전틱 플래너 사용, False면 기존 파이프라인
    """
    from blog_generator.blog_writer import write_local_blog
    from publisher.naver_blog import publish_to_naver

    blogs_json = _load_blogs_json()
    blog_info = blogs_json["blogs"].get(blog_id, {})
    blog_url = blog_info.get("blog_url", "")

    if not blog_url:
        print(f"  [{blog_id}] blog_url 없음 — 스킵")
        return None

    # 썸네일 배경 초기화
    bg_dir = Path("data/image/thumbnail_bg")
    if bg_dir.exists():
        shutil.rmtree(bg_dir, ignore_errors=True)
    bg_dir.mkdir(parents=True, exist_ok=True)

    if use_agent:
        # ── 에이전틱 모드: Gemini가 알아서 도구 선택 + 정보 수집 ──
        from blog_generator.agent_planner import agent_plan_topic
        topic = agent_plan_topic(blog_id=blog_id)
        template = topic.get("template", blog_info.get("templates", ["local_trend"])[0])
    else:
        # ── 기존 모드: 하드코딩된 파이프라인 ──
        from blog_generator.planner import search_for_topic
        _ensure_topic_queue(blog_id)
        queue = _topic_queues.get(blog_id, [])
        if not queue:
            raise RuntimeError("주제 생성 실패")

        topic = queue.pop(0)
        template = topic.get("template", blog_info.get("templates", ["local_trend"])[0])

        ref = search_for_topic(topic)
        if ref.get("news"):
            topic["ref_news"] = "\n".join(f"- {n['title']}" for n in ref["news"])
        if ref.get("blogs"):
            topic["ref_blogs"] = "\n".join(f"- {b['title']}" for b in ref["blogs"])
        if ref.get("realtime_trending"):
            topic["ref_trending"] = "\n".join(
                f"- {t['keyword']} ({t['traffic']})" for t in ref["realtime_trending"][:10]
            )

    # 글 생성
    blog = write_local_blog(topic, template_name=template)
    body_len = sum(len(str(v)) for v in blog.get("_slots", {}).values())

    from blog_generator.quality_checker import check_quality
    valid, reason = check_quality(blog)
    for retry in range(3):
        if valid:
            break
        print(f"  [{blog_id}] {reason} — 재생성 ({retry + 1})...")
        blog = write_local_blog(topic, template_name=template)
        body_len = sum(len(str(v)) for v in blog.get("_slots", {}).values())
        valid, reason = check_quality(blog)

    if not valid:
        print(f"  [{blog_id}] 품질 미달 ({reason}, {len(blog.get('body', ''))}자) — 스킵")
        raise RuntimeError(f"품질 미달: {reason}, {len(blog.get('body', ''))}자")

    # 발행
    url = publish_to_naver(blog, blog_id=blog_url, template_name=template, cookie_blog_id=blog_id)

    if not url:
        print(f"  [{blog_id}] 발행 실패 — URL 없음")
        raise RuntimeError("네이버 발행 실패 (URL 없음)")

    _save_history(blog_id, topic, blog)

    return {
        "blog_id": blog_id,
        "blog_url": blog_url,
        "title": blog.get("title", ""),
        "body_len": body_len,
        "template": template,
        "region": topic.get("region", ""),
        "business": topic.get("business", ""),
        "tone": blog.get("tone", ""),
        "time": datetime.now().strftime("%H:%M"),
        "url": url,
    }


def make_daily_schedule() -> list:
    """모든 블로그의 하루 발행 스케줄을 생성한다.

    Returns:
        [{"blog_id": "blog_02", "time": datetime}, ...]
        시간순 정렬.
    """
    schedule = []
    now = datetime.now()
    end_of_day = now.replace(hour=23, minute=59, second=0, microsecond=0)
    remaining_minutes = max(0, int((end_of_day - now).total_seconds() // 60))

    for blog_id, config in BLOG_CONFIGS.items():
        posts = config["posts_per_day"]
        # 분 단위 또는 시간 단위 간격 지원
        if "min_interval_min" in config:
            min_gap = config["min_interval_min"]
        else:
            min_gap = config["min_interval_hours"] * 60
        already = _get_today_count(blog_id)
        remaining = max(0, posts - already)

        if remaining == 0:
            continue

        # 남은 시간 내에 간격 조정
        needed = remaining * min_gap
        if needed > remaining_minutes:
            min_gap = max(1, remaining_minutes // remaining)

        # 현재 시각 기준으로 스케줄 생성
        times = []
        for _ in range(remaining):
            if not times:
                # 첫 포스팅은 5~15분 후
                t = random.randint(5, min(15, max(5, min_gap)))
            else:
                extra = max(1, min_gap // 4)
                t = times[-1] + min_gap + random.randint(0, extra)
            if t >= remaining_minutes:
                t = remaining_minutes - 1
            times.append(t)

        for t in times:
            scheduled_time = now + timedelta(minutes=t)
            schedule.append({"blog_id": blog_id, "time": scheduled_time})

    # 시간순 정렬
    schedule.sort(key=lambda x: x["time"])
    return schedule


def run_forever():
    """매일 00:00~24:00 사이 모든 블로그 자동 발행."""

    # 자정 이후에 시작하도록 대기
    now = datetime.now()
    if now.hour >= 22:
        tomorrow_0am = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wait = (tomorrow_0am - now).total_seconds()
        hours = int(wait // 3600)
        mins = int((wait % 3600) // 60)
        print(f"\n  현재 {now.strftime('%H:%M')} — 자정까지 대기 ({hours}시간 {mins}분)")
        time.sleep(wait)

    while True:
        today = datetime.now().strftime("%Y-%m-%d")

        # 매일 데이터 수집 (오늘 CSV가 없으면 실행)
        today_ymd = datetime.now().strftime("%Y%m%d")
        if not Path(f"data/collected/{today_ymd}_naver_news.csv").exists():
            print(f"\n  [{today}] 데이터 수집 시작...")
            try:
                from collectors import collect_all
                collect_all()
                print(f"  [{today}] 데이터 수집 완료")
            except Exception as e:
                print(f"  [{today}] 데이터 수집 실패: {e}")

        # 하루 시작 — 주제 큐 초기화
        _topic_queues.clear()

        schedule = make_daily_schedule()

        print(f"\n{'#' * 60}")
        print(f"  {today} 스케줄 ({len(schedule)}개)")
        print(f"{'#' * 60}")

        # 블로그별 오늘 현황
        for blog_id, config in BLOG_CONFIGS.items():
            done = _get_today_count(blog_id)
            total = config["posts_per_day"]
            remaining_count = len([s for s in schedule if s["blog_id"] == blog_id])
            print(f"  {blog_id}: {done}/{total} 완료, {remaining_count}개 예약")

        print(f"\n  예약 시간:")
        for i, s in enumerate(schedule):
            print(f"    {i + 1:2d}. {s['time'].strftime('%H:%M')} — {s['blog_id']}")
        print()

        if not schedule:
            print("  오늘 발행 완료!")
        else:
            results = []
            log_path = Path("data/generated") / f"{datetime.now().strftime('%Y%m%d')}_scheduler_log.json"

            for i, entry in enumerate(schedule):
                blog_id = entry["blog_id"]
                scheduled_time = entry["time"]

                # 예약 시간까지 대기
                now = datetime.now()
                wait_sec = (scheduled_time - now).total_seconds()
                if wait_sec > 0:
                    mins = int(wait_sec // 60)
                    print(f"\n  대기 중... {scheduled_time.strftime('%H:%M')} ({mins}분 후) → {blog_id}")
                    time.sleep(wait_sec)

                print(f"\n{'─' * 50}")
                print(f"  [{i + 1}/{len(schedule)}] {datetime.now().strftime('%H:%M')} — {blog_id}")
                print(f"{'─' * 50}")

                try:
                    result = publish_one(blog_id)
                    if result:
                        results.append(result)
                        print(f"  ✓ {blog_id}: {result['title'][:30]}")
                        # 슬랙 성공 알림
                        try:
                            from publisher.slack_notify import notify_success
                            notify_success(
                                blog_id=blog_id, title=result.get("title", ""),
                                url=result.get("url", ""), template=result.get("template", ""),
                                region=result.get("region", ""), tone=result.get("tone", ""),
                            )
                        except Exception:
                            pass
                    else:
                        results.append({"blog_id": blog_id, "error": "생성 실패", "time": datetime.now().strftime("%H:%M")})
                        print(f"  ✗ {blog_id}: 실패")
                        try:
                            from publisher.slack_notify import notify_fail
                            notify_fail(blog_id=blog_id, error="생성 실패")
                        except Exception:
                            pass
                except Exception as e:
                    results.append({"blog_id": blog_id, "error": str(e), "time": datetime.now().strftime("%H:%M")})
                    print(f"  ✗ {blog_id}: {e}")
                    try:
                        from publisher.slack_notify import notify_fail
                        notify_fail(blog_id=blog_id, error=str(e))
                    except Exception:
                        pass

                log_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

            success = len([r for r in results if "error" not in r])
            print(f"\n  {today} 완료: {success}/{len(schedule)} 성공")
            # 슬랙 일일 요약
            try:
                from publisher.slack_notify import notify_daily_summary
                notify_daily_summary(results, date=today)
            except Exception:
                pass

        # 브라우저 세션 유지 — 닫으면 쿠키 만료되므로 닫지 않음

        # 다음 날 00:00까지 대기
        now = datetime.now()
        tomorrow_0am = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        wait_sec = (tomorrow_0am - now).total_seconds()

        if wait_sec > 0:
            hours = int(wait_sec // 3600)
            mins = int((wait_sec % 3600) // 60)
            print(f"\n  다음: {tomorrow_0am.strftime('%Y-%m-%d %H:%M')} ({hours}시간 {mins}분 후)")
            time.sleep(wait_sec)


if __name__ == "__main__":
    run_forever()
