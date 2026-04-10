"""네이버 블로그 Playwright 세션 매니저.

쿠키를 디스크에서 로드해서 "이미 로그인된 브라우저"를 만들어 publish.py에 넘긴다.
6개 블로그 계정을 cookie_blog_id로 구분.
"""

import json
import os
import random
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()


# ── 블로그별 계정 정보 (.env에서 로드) ──
def _load_blog_credentials() -> dict:
    creds = {}
    for i in range(2, 8):
        bid = f"blog_{i:02d}"
        nid = os.environ.get(f"NAVER_BLOG_{i:02d}_ID", "")
        npw = os.environ.get(f"NAVER_BLOG_{i:02d}_PW", "")
        if nid:
            creds[bid] = {"naver_id": nid, "naver_pw": npw}
    return creds


BLOG_CREDENTIALS = _load_blog_credentials()
PROFILE_BASE = Path("data/browser_profiles")


# ── 세션 매니저: 단일 Playwright + 블로그별 브라우저 컨텍스트를 재사용 ──
_pw_instance = None
_browser_instance = None
_sessions = {}  # {cookie_blog_id: {"context": BrowserContext, "page": Page}}


def _get_browser():
    """단일 Playwright + Browser 인스턴스를 반환한다."""
    global _pw_instance, _browser_instance
    if _pw_instance is None:
        _pw_instance = sync_playwright().start()
    if _browser_instance is None:
        _browser_instance = _pw_instance.chromium.launch(headless=False, slow_mo=50)
    return _browser_instance


def _cookie_path(cookie_blog_id: str) -> Path:
    """블로그별 쿠키 파일 경로."""
    if cookie_blog_id:
        return Path(f"data/naver_blog_cookies_{cookie_blog_id}.json")
    return Path("data/naver_blog_cookies.json")


def _random_delay(min_sec=0.5, max_sec=1.5):
    """사람처럼 랜덤 딜레이."""
    time.sleep(random.uniform(min_sec, max_sec))


def get_session(cookie_blog_id: str):
    """블로그별 컨텍스트를 가져오거나 새로 생성. 쿠키를 로드하여 세션 유지."""
    if cookie_blog_id in _sessions:
        sess = _sessions[cookie_blog_id]
        try:
            sess["page"].url
            return sess["context"], sess["page"]
        except Exception:
            print(f"  [Naver] 세션 만료 — 재생성 ({cookie_blog_id})")
            try:
                sess["context"].close()
            except Exception:
                pass
            del _sessions[cookie_blog_id]

    # 새 컨텍스트 생성 — 쿠키 로드
    browser = _get_browser()
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    )
    cookie_path = _cookie_path(cookie_blog_id)
    if cookie_path.exists():
        try:
            cookies = json.loads(cookie_path.read_text(encoding="utf-8"))
            context.add_cookies(cookies)
        except Exception:
            pass
    page = context.new_page()
    _sessions[cookie_blog_id] = {"context": context, "page": page}
    print(f"  [Naver] 새 세션 생성 ({cookie_blog_id})")
    return context, page


def _check_login(page, blog_url: str = "") -> bool:
    """현재 페이지에서 로그인 상태 확인. postwrite 접속 시도."""
    if blog_url:
        check_url = f"https://blog.naver.com/{blog_url}/postwrite"
    else:
        check_url = "https://blog.naver.com/"
    page.goto(check_url, timeout=15000)
    _random_delay(2, 3)
    current = page.url.lower()
    return "login" not in current and "nid.naver.com" not in current
