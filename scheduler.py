"""멀티 블로그 자동 발행 스케줄러.

매일 동작 흐름:
  1) 05:00 — 일일 데이터 수집 (뉴스 + 행사)
  2) 05:10 — 블로그별 기사 평가 → 발행 큐 생성 (data/plans/{date}_{blog_id}.json)
  3) 06:00~22:00 — 매 시간대마다 블로그를 라운드로빈으로 순회하며 큐에서 1개씩 발행

수집/기획이 안 돼 있으면 발행 시점에 즉시 실행한다.

블로그별 설정:
  blog_02~06: 하루 10개, 30~45분 간격
  blog_07: 하루 20개, 20~35분 간격

실행: python scheduler.py
"""

import json
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

# UTF-8 인코딩 강제 (Windows 콘솔)
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


# ════════════════════════════════════════════════════════════
#  설정
# ════════════════════════════════════════════════════════════
COLLECT_HOUR = 5        # 일일 수집 시작 시각
COLLECT_MIN = 0
PLAN_HOUR = 5           # 일일 기획 시작 시각
PLAN_MIN = 10
PUBLISH_START_HOUR = 6  # 발행 시작
PUBLISH_END_HOUR = 22   # 발행 종료

# 블로그별 발행 설정
BLOG_CONFIGS = {
    "blog_02": {"posts_per_day": 10, "min_interval_min": 30, "max_interval_min": 45},
    "blog_03": {"posts_per_day": 10, "min_interval_min": 30, "max_interval_min": 45},
    "blog_04": {"posts_per_day": 10, "min_interval_min": 30, "max_interval_min": 45},
    "blog_05": {"posts_per_day": 10, "min_interval_min": 30, "max_interval_min": 45},
    "blog_06": {"posts_per_day": 10, "min_interval_min": 30, "max_interval_min": 45},
    "blog_07": {"posts_per_day": 20, "min_interval_min": 20, "max_interval_min": 35},
}

STATE_PATH = Path("data/schedule_state.json")
PLANS_DIR = Path("data/plans")
LOG_DIR = Path("data/generated")


# ════════════════════════════════════════════════════════════
#  공통 유틸
# ════════════════════════════════════════════════════════════
def _today_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def _load_blogs_json() -> dict:
    return json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))


def _news_file() -> Path:
    return Path(f"data/collected/{_today_str()}_daily_news.json")


def _plan_file(blog_id: str) -> Path:
    return PLANS_DIR / f"{_today_str()}_{blog_id}.json"


# ── 발행 이력 관리 ──
def _get_today_count(blog_id: str) -> int:
    if not STATE_PATH.exists():
        return 0
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    today = _today_str()
    entries = state.get(blog_id, [])
    return sum(1 for e in entries if e.get("date") == today)


def _save_history(blog_id: str, post: dict, url: str):
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    if blog_id not in state:
        state[blog_id] = []
    state[blog_id].append({
        "date": _today_str(),
        "time": datetime.now().strftime("%H:%M"),
        "title": post.get("title", ""),
        "template": post.get("template", ""),
        "url": url,
    })
    # 7일치만 유지
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
    state[blog_id] = [e for e in state[blog_id] if e.get("date", "") >= cutoff]
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ════════════════════════════════════════════════════════════
#  파이프라인 단계
# ════════════════════════════════════════════════════════════
def run_collect():
    """일일 데이터 수집 (뉴스 + 행사)."""
    print(f"  [{datetime.now():%H:%M}] 수집 시작")
    try:
        from collectors.daily_news import collect_and_save as save_news
        save_news()
        print(f"  [{datetime.now():%H:%M}] 뉴스 수집 완료")
    except Exception as e:
        print(f"  [Collect] 뉴스 수집 실패: {e}")

    try:
        from collectors.naver_events import collect_and_save as save_events
        save_events(keywords=["축제", "박람회"], max_pages=2)
        print(f"  [{datetime.now():%H:%M}] 행사 수집 완료")
    except Exception as e:
        print(f"  [Collect] 행사 수집 실패: {e}")


def ensure_collected():
    """오늘 수집이 안 됐으면 즉시 실행."""
    if not _news_file().exists():
        print(f"  [Guard] 뉴스 미수집 — 즉시 수집")
        run_collect()


def run_plan_all():
    """모든 기사를 한 번에 평가 → 블로그별 큐 일괄 생성.

    LLM 호출 1세트로 6개 블로그 큐를 모두 채운다 (per-blog 평가 대비 1/6 비용).
    같은 기사가 여러 블로그에 들어가도 generate_post() 단계에서 톤이 달라진다.
    """
    from collections import Counter
    from blog_generator.plan import evaluate_all_articles, assign_to_blogs

    # 전체 목표 = 모든 블로그 합 × 2 (여유)
    total_target = sum(c["posts_per_day"] for c in BLOG_CONFIGS.values())
    max_eval = max(total_target * 3, 100)

    print(f"\n{'=' * 60}")
    print(f"  [Plan] 전체 평가 시작 (목표 합 {total_target}개, 최대 평가 {max_eval}건)")
    print(f"{'=' * 60}")
    scored = evaluate_all_articles(max_evaluate=max_eval)

    # 템플릿별 통과 분포
    if scored:
        tpl_counts = Counter(s["template"] for s in scored)
        print(f"\n  [Plan] 템플릿별 통과 분포:")
        for tpl, cnt in sorted(tpl_counts.items(), key=lambda x: -x[1]):
            print(f"    {tpl:<18} {cnt}건")

    # 블로그별 큐 배정
    queues = assign_to_blogs(scored, BLOG_CONFIGS)

    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n  [Plan] 블로그별 큐 배정:")
    print(f"  {'─' * 56}")
    for blog_id, queue in queues.items():
        _plan_file(blog_id).write_text(
            json.dumps(queue, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        target = BLOG_CONFIGS[blog_id]["posts_per_day"]
        bar_len = 20
        filled = int(bar_len * len(queue) / target) if target else 0
        bar = "█" * filled + "░" * (bar_len - filled)
        warn = "" if len(queue) >= target else "  ⚠ 부족"
        print(f"  {blog_id}  {bar}  {len(queue)}/{target}{warn}")

        # 큐에 들어간 템플릿 분포
        if queue:
            q_tpls = Counter(item["template"] for item in queue)
            tpl_str = ", ".join(f"{t}×{c}" for t, c in q_tpls.most_common())
            print(f"           └ {tpl_str}")
    print(f"  {'─' * 56}\n")


def ensure_planned():
    """오늘 기획 큐가 하나라도 없으면 전체 기획을 한 번에 실행."""
    missing = [bid for bid in BLOG_CONFIGS if not _plan_file(bid).exists()]
    if missing:
        print(f"  [Guard] 기획 미완료 ({len(missing)}/{len(BLOG_CONFIGS)} 블로그) — 즉시 기획")
        ensure_collected()
        run_plan_all()


def publish_one(blog_id: str) -> dict | None:
    """블로그 큐에서 1건 꺼내 생성 + 발행."""
    from blog_generator.generate import generate_post
    from blog_generator.publish import publish_post

    ensure_planned()

    plan_path = _plan_file(blog_id)
    if not plan_path.exists():
        print(f"  [{blog_id}] 기획 파일 없음 — 스킵")
        return None

    queue = json.loads(plan_path.read_text(encoding="utf-8"))
    if not queue:
        print(f"  [{blog_id}] 큐 비어있음 — 스킵")
        return None

    item = queue.pop(0)
    article = item["article"]
    template = item["template"]
    reason = item.get("reason", "")

    print(f"  [{blog_id}] 글 생성: {article['title'][:40]} (템플릿: {template})")
    post = generate_post(article=article, template=template, blog_id=blog_id, reason=reason)
    if not post:
        print(f"  [{blog_id}] 글 생성 실패")
        # 실패한 항목은 큐 끝으로 (다음 차례에서 재시도하려면 push, 아니면 drop)
        plan_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        return None

    # 큐에서 제거된 상태로 우선 저장 (발행 실패해도 다음으로 진행)
    plan_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    # 네이버 블로그 URL 정보
    blogs_json = _load_blogs_json()
    blog_info = blogs_json["blogs"].get(blog_id, {})
    blog_url = blog_info.get("blog_url", "")
    if not blog_url:
        print(f"  [{blog_id}] blog_url 없음 — 스킵")
        return None

    print(f"  [{blog_id}] 네이버 발행 중...")
    url = publish_post(post=post, blog_id=blog_url, cookie_blog_id=blog_id)
    if not url:
        print(f"  [{blog_id}] 발행 실패")
        return None

    _save_history(blog_id, post, url)
    print(f"  [{blog_id}] ✓ 발행 완료: {url}")
    return {"blog_id": blog_id, "title": post.get("title", ""), "url": url, "template": template}


# ════════════════════════════════════════════════════════════
#  스케줄 생성
# ════════════════════════════════════════════════════════════
def make_daily_schedule() -> list:
    """오늘 남은 시간 안에 모든 블로그의 발행 시각을 생성한다.

    Returns:
        [{"blog_id": str, "time": datetime}, ...] (시간순 정렬)
    """
    schedule = []
    now = datetime.now()
    end_of_day = now.replace(hour=PUBLISH_END_HOUR, minute=0, second=0, microsecond=0)
    if end_of_day <= now:
        return []
    remaining_minutes = int((end_of_day - now).total_seconds() // 60)

    for blog_id, config in BLOG_CONFIGS.items():
        already = _get_today_count(blog_id)
        remaining = max(0, config["posts_per_day"] - already)
        if remaining == 0:
            continue

        min_gap = config["min_interval_min"]
        max_gap = config["max_interval_min"]

        # 남은 시간 안에 못 끼우면 간격 압축
        needed = remaining * min_gap
        if needed > remaining_minutes:
            min_gap = max(1, remaining_minutes // remaining)
            max_gap = max(min_gap, remaining_minutes // remaining)

        times = []
        for _ in range(remaining):
            if not times:
                # 첫 포스팅: 5~15분 후
                offset = random.randint(5, min(15, max(5, min_gap)))
            else:
                offset = times[-1] + random.randint(min_gap, max_gap)
            if offset >= remaining_minutes:
                offset = remaining_minutes - 1
            times.append(offset)

        for t in times:
            schedule.append({"blog_id": blog_id, "time": now + timedelta(minutes=t)})

    schedule.sort(key=lambda x: x["time"])
    return schedule


# ════════════════════════════════════════════════════════════
#  메인 루프
# ════════════════════════════════════════════════════════════
def run_forever():
    """매일 00:00~24:00 자동 발행."""
    print(f"\n스케줄러 시작: {datetime.now():%Y-%m-%d %H:%M}\n")

    while True:
        today = datetime.now().strftime("%Y-%m-%d")

        # 1) 일일 수집 (없으면 실행)
        ensure_collected()

        # 2) 일일 기획 (한 번에 전체 평가 → 블로그별 큐 일괄 생성)
        if any(not _plan_file(bid).exists() for bid in BLOG_CONFIGS):
            run_plan_all()

        # 3) 발행 스케줄 생성
        schedule = make_daily_schedule()

        print(f"\n{'#' * 60}")
        print(f"  {today} 스케줄 ({len(schedule)}개)")
        print(f"{'#' * 60}")
        for blog_id, config in BLOG_CONFIGS.items():
            done = _get_today_count(blog_id)
            total = config["posts_per_day"]
            slots = len([s for s in schedule if s["blog_id"] == blog_id])
            print(f"  {blog_id}: {done}/{total} 완료, {slots}개 예약")

        if schedule:
            print(f"\n  예약 시간:")
            for i, s in enumerate(schedule[:20]):
                print(f"    {i+1:2d}. {s['time'].strftime('%H:%M')} — {s['blog_id']}")
            if len(schedule) > 20:
                print(f"    ... (총 {len(schedule)}개)")
            print()

            # 발행 루프
            log_path = LOG_DIR / f"{_today_str()}_scheduler_log.json"
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            results = []

            for i, entry in enumerate(schedule):
                blog_id = entry["blog_id"]
                scheduled = entry["time"]

                # 예약 시각까지 대기
                wait_sec = (scheduled - datetime.now()).total_seconds()
                if wait_sec > 0:
                    mins = int(wait_sec // 60)
                    print(f"\n  대기 중... {scheduled.strftime('%H:%M')} ({mins}분 후) → {blog_id}")
                    time.sleep(wait_sec)

                print(f"\n{'─' * 50}")
                print(f"  [{i+1}/{len(schedule)}] {datetime.now():%H:%M} — {blog_id}")
                print(f"{'─' * 50}")

                try:
                    result = publish_one(blog_id)
                    if result:
                        results.append(result)
                    else:
                        results.append({"blog_id": blog_id, "error": "발행 실패",
                                        "time": datetime.now().strftime("%H:%M")})
                except Exception as e:
                    print(f"  [{blog_id}] 예외: {e}")
                    results.append({"blog_id": blog_id, "error": str(e),
                                    "time": datetime.now().strftime("%H:%M")})

                log_path.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                    encoding="utf-8")

            success = len([r for r in results if "error" not in r])
            print(f"\n  {today} 완료: {success}/{len(schedule)} 성공")

            # 일일 요약 슬랙
            try:
                from blog_generator.slack_notify import notify_daily_summary
                notify_daily_summary(results, date=today)
            except Exception:
                pass
        else:
            print("  오늘 발행 완료 또는 시간 종료")

        # 다음 날 00:00까지 대기
        now = datetime.now()
        tomorrow_0am = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wait_sec = (tomorrow_0am - now).total_seconds()
        if wait_sec > 0:
            hours = int(wait_sec // 3600)
            mins = int((wait_sec % 3600) // 60)
            print(f"\n  다음 사이클: {tomorrow_0am:%Y-%m-%d %H:%M} ({hours}시간 {mins}분 후)\n")
            time.sleep(wait_sec)


if __name__ == "__main__":
    try:
        run_forever()
    except KeyboardInterrupt:
        print("\n스케줄러 종료")
