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
    "blog_02": {"posts_per_day": 30, "min_interval_min": 30, "max_interval_min": 45},
    "blog_03": {"posts_per_day": 30, "min_interval_min": 30, "max_interval_min": 45},
    "blog_04": {"posts_per_day": 30, "min_interval_min": 30, "max_interval_min": 45},
    "blog_05": {"posts_per_day": 30, "min_interval_min": 30, "max_interval_min": 45},
    "blog_06": {"posts_per_day": 30, "min_interval_min": 30, "max_interval_min": 45},
    "blog_07": {"posts_per_day": 40, "min_interval_min": 20, "max_interval_min": 35},
}

STATE_PATH = Path("data/schedule_state.json")
PLANS_DIR = Path("data/plans")
LOG_DIR = Path("data/generated")

# Live 모드 설정
LIVE_INTERVAL_MIN = 15        # 슬롯 간격 최소 (분)
LIVE_INTERVAL_MAX = 25        # 슬롯 간격 최대 (분)
LIVE_MAX_TRIES_PER_SLOT = 50  # 한 슬롯에서 평가할 최대 기사 수


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


def _live_state_file() -> Path:
    """Live 모드: 오늘 어디까지 평가했는지 인덱스 저장."""
    return PLANS_DIR / f"{_today_str()}_live_state.json"


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
#  Live 모드 — 실시간 평가 + 다중 블로그 동시 발행
# ════════════════════════════════════════════════════════════
def _load_live_index() -> int:
    """오늘 평가 인덱스 로드 (없으면 0)."""
    p = _live_state_file()
    if not p.exists():
        return 0
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("next_index", 0)
    except Exception:
        return 0


def _save_live_index(idx: int):
    """오늘 평가 인덱스 저장."""
    p = _live_state_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"next_index": idx}), encoding="utf-8")


def _matching_blogs_with_room(template: str) -> list[str]:
    """template을 가진 블로그 중 오늘 발행 한도가 남은 것만 반환."""
    blogs_json = _load_blogs_json()
    targets = []
    for bid, config in BLOG_CONFIGS.items():
        info = blogs_json["blogs"].get(bid, {})
        if template not in info.get("templates", []):
            continue
        if _get_today_count(bid) >= config["posts_per_day"]:
            continue
        targets.append(bid)
    return targets


def publish_to_blogs(article: dict, template: str, reason: str, blog_ids: list[str]) -> list[dict]:
    """매칭된 블로그들에 동시 발행. 각각 generate_post → publish_post."""
    from blog_generator.generate import generate_post
    from blog_generator.publish import publish_post

    blogs_json = _load_blogs_json()
    results = []

    for bid in blog_ids:
        info = blogs_json["blogs"].get(bid, {})
        blog_url = info.get("blog_url", "")
        if not blog_url:
            print(f"  [{bid}] blog_url 없음 — 스킵")
            continue

        print(f"  [{bid}] 글 생성 중...")
        post = generate_post(article=article, template=template, blog_id=bid, reason=reason)
        if not post:
            print(f"  [{bid}] ✗ 글 생성 실패")
            results.append({"blog_id": bid, "error": "생성 실패"})
            continue

        print(f"  [{bid}] 네이버 발행 중...")
        url = publish_post(post=post, blog_id=blog_url, cookie_blog_id=bid)
        if not url:
            print(f"  [{bid}] ✗ 발행 실패")
            results.append({"blog_id": bid, "error": "발행 실패", "title": post.get("title", "")})
            continue

        _save_history(bid, post, url)
        print(f"  [{bid}] ✓ 완료: {url}")
        results.append({"blog_id": bid, "title": post.get("title", ""), "url": url, "template": template})

    return results


def run_live():
    """Live 모드 — 슬롯마다 기사 1건씩 평가해 매칭 블로그에 동시 발행.

    흐름:
      1) 수집 확인 (없으면 즉시 수집)
      2) 무한 루프:
         a) 평가 인덱스에서 다음 기사 꺼냄
         b) LLM 평가 → 통과 시 매칭 블로그 추출 → 동시 발행 → 1슬롯 종료
         c) 미통과 또는 매칭 블로그 없음 → 다음 기사 (대기 없이 즉시)
         d) 한 슬롯에서 LIVE_MAX_TRIES_PER_SLOT 초과 시 종료
         e) 다음 슬롯까지 LIVE_INTERVAL_MIN~MAX 분 대기
    """
    print(f"\nLive 스케줄러 시작: {datetime.now():%Y-%m-%d %H:%M}")
    print(f"  슬롯 간격: {LIVE_INTERVAL_MIN}~{LIVE_INTERVAL_MAX}분")
    print(f"  슬롯당 최대 평가: {LIVE_MAX_TRIES_PER_SLOT}건\n")

    from blog_generator.plan import evaluate_one_article

    while True:
        # 1) 수집 확인
        ensure_collected()

        # 오늘 뉴스 로드
        news_path = _news_file()
        if not news_path.exists():
            print("  [Live] 뉴스 파일 없음 — 1시간 대기")
            time.sleep(3600)
            continue

        all_news = json.loads(news_path.read_text(encoding="utf-8"))
        idx = _load_live_index()

        if idx >= len(all_news):
            # 오늘 기사 다 봄 → 다음 날 00:00까지 대기
            now = datetime.now()
            tomorrow_0am = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            wait_sec = (tomorrow_0am - now).total_seconds()
            hours = int(wait_sec // 3600)
            mins = int((wait_sec % 3600) // 60)
            print(f"\n  [Live] 오늘 기사 모두 평가 완료 ({len(all_news)}건)")
            print(f"  [Live] 다음 날까지 대기: {hours}시간 {mins}분")
            time.sleep(wait_sec)
            continue

        # 모든 블로그가 한도를 채웠는지 확인
        all_full = all(
            _get_today_count(bid) >= cfg["posts_per_day"]
            for bid, cfg in BLOG_CONFIGS.items()
        )
        if all_full:
            now = datetime.now()
            tomorrow_0am = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            wait_sec = (tomorrow_0am - now).total_seconds()
            hours = int(wait_sec // 3600)
            print(f"\n  [Live] 모든 블로그 발행 한도 도달 — 다음 날까지 {hours}시간 대기")
            time.sleep(wait_sec)
            continue

        # 2) 슬롯 시작 — 통과할 때까지 또는 max_tries 까지 평가
        print(f"\n{'─' * 56}")
        print(f"  [Live 슬롯] {datetime.now():%H:%M}  (평가 인덱스 {idx}/{len(all_news)})")
        print(f"{'─' * 56}")

        published_in_slot = False
        for try_n in range(LIVE_MAX_TRIES_PER_SLOT):
            if idx >= len(all_news):
                print(f"  [Live] 기사 풀 끝 — 다음 사이클로")
                break

            article = all_news[idx]
            idx += 1
            _save_live_index(idx)

            title_short = article.get("title", "")[:35]
            print(f"  [{try_n+1:2d}] {title_short}", end="  ", flush=True)

            scored = evaluate_one_article(article)
            if not scored:
                print("→ LLM 응답 없음")
                continue

            if scored.get("_failed"):
                print(f"✗ {scored['score']:>3}점 [{scored['template'] or '?'}]")
                continue

            template = scored["template"]
            score = scored["score"]
            print(f"✓ {score:>3}점 [{template}]")

            # 매칭 블로그 (한도 안 찬 것만)
            targets = _matching_blogs_with_room(template)
            if not targets:
                print(f"       └ 매칭 블로그 없음 또는 한도 도달 — 다음 기사")
                continue

            print(f"       └ 발행 대상: {', '.join(targets)}")

            # 동시 발행
            results = publish_to_blogs(article, template, scored.get("reason", ""), targets)
            success = [r for r in results if "url" in r]
            if success:
                published_in_slot = True
                break  # 1슬롯 = 1성공 발행
            else:
                print(f"       └ 모든 블로그 발행 실패 — 다음 기사")

        # 3) 다음 슬롯까지 대기
        if published_in_slot:
            wait_min = random.randint(LIVE_INTERVAL_MIN, LIVE_INTERVAL_MAX)
            print(f"\n  [Live] {wait_min}분 대기 후 다음 슬롯")
            time.sleep(wait_min * 60)
        else:
            # 슬롯 내에서 한 건도 발행 못 함 → 짧은 대기 후 재시도
            print(f"\n  [Live] 슬롯 내 발행 없음 — 5분 후 재시도")
            time.sleep(5 * 60)


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
    # CLI: python scheduler.py [queue|live]
    #   queue (기본) — 새벽에 일괄 평가 → 큐 생성 → 시간표대로 발행
    #   live          — 슬롯마다 1건씩 평가 → 통과 시 매칭 블로그 동시 발행
    mode = sys.argv[1] if len(sys.argv) > 1 else "queue"

    try:
        if mode == "live":
            run_live()
        elif mode == "queue":
            run_forever()
        else:
            print(f"알 수 없는 모드: {mode}")
            print("사용법: python scheduler.py [queue|live]")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n스케줄러 종료")
