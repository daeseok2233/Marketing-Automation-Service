"""슬랙 알림 — 블로그 발행 성공/실패 알림."""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")


def notify_success(blog_id: str, title: str, url: str = "", template: str = "", region: str = "", tone: str = ""):
    """발행 성공 알림."""
    if not WEBHOOK_URL:
        return
    fields = f"*블로그*: {blog_id}"
    if template:
        fields += f"  |  *템플릿*: {template}"
    if region:
        fields += f"  |  *지역*: {region}"
    if tone:
        fields += f"  |  *톤*: {tone}"
    if url:
        fields += f"\n<{url}|글 보기>"
    text = f":white_check_mark: *발행 성공*\n{fields}\n*제목*: {title}"
    _send(text)


def notify_fail(blog_id: str, error: str = "", title: str = ""):
    """발행 실패 알림."""
    if not WEBHOOK_URL:
        return
    text = f":x: *발행 실패* — {blog_id}"
    if title:
        text += f"\n*제목*: {title}"
    if error:
        text += f"\n*오류*: {error[:200]}"
    _send(text)


def notify_daily_summary(results: list, date: str = ""):
    """하루 발행 요약 알림."""
    if not WEBHOOK_URL:
        return
    success = [r for r in results if "error" not in r]
    fail = [r for r in results if "error" in r]

    # 블로그별 집계
    from collections import Counter
    blog_counts = Counter(r.get("blog_id", "") for r in success)
    summary_lines = [f"  {bid}: {cnt}개" for bid, cnt in sorted(blog_counts.items())]

    text = f":bar_chart: *{date} 일일 요약*\n"
    text += f"*성공*: {len(success)}개  |  *실패*: {len(fail)}개\n"
    if summary_lines:
        text += "\n".join(summary_lines)
    if fail:
        text += f"\n\n:warning: 실패 목록:"
        for r in fail[:5]:
            text += f"\n  - {r.get('blog_id','')}: {r.get('error','')[:50]}"
    _send(text)


def notify_login_expired(blog_id: str):
    """쿠키 만료 알림."""
    if not WEBHOOK_URL:
        return
    text = f":rotating_light: *로그인 만료* — {blog_id}\n`python save_naver_cookies.py {blog_id}`"
    _send(text)


def _send(text: str):
    """슬랙 Webhook으로 메시지 전송."""
    try:
        requests.post(WEBHOOK_URL, json={"text": text}, timeout=10)
    except Exception as e:
        print(f"  [Slack] 알림 전송 실패: {e}")
