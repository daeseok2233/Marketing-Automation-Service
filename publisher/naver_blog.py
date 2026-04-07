"""네이버 블로그 자동 발행 — 브라우저 세션 유지 방식."""

import os
import json
import time
import random
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

# 블로그별 계정 정보 (.env에서 로드)
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

# persistent context용 프로필 디렉토리
PROFILE_BASE = Path("data/browser_profiles")


# ── 세션 매니저: 단일 Playwright + 블로그별 브라우저 컨텍스트를 열어두고 재사용 ──
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
    # 기존 JSON 쿠키 로드
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


def close_all_sessions():
    """모든 브라우저 세션 종료."""
    global _pw_instance, _browser_instance
    for bid, sess in list(_sessions.items()):
        try:
            sess["context"].close()
        except Exception:
            pass
    _sessions.clear()
    if _browser_instance:
        try:
            _browser_instance.close()
        except Exception:
            pass
        _browser_instance = None
    if _pw_instance:
        try:
            _pw_instance.stop()
        except Exception:
            pass
        _pw_instance = None
    print("  [Naver] 모든 세션 종료")


def _random_delay(min_sec=0.5, max_sec=1.5):
    """사람처럼 랜덤 딜레이."""
    time.sleep(random.uniform(min_sec, max_sec))


def _cookie_path(cookie_blog_id: str) -> Path:
    """블로그별 쿠키 파일 경로."""
    if cookie_blog_id:
        return Path(f"data/naver_blog_cookies_{cookie_blog_id}.json")
    return Path("data/naver_blog_cookies.json")


def _save_cookies(context, cookie_blog_id: str = ""):
    """쿠키 저장 (JSON 백업용)."""
    cookies = context.cookies()
    path = _cookie_path(cookie_blog_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")


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


def publish_to_naver(blog_data: dict, blog_id: str = "", template_name: str = "local_trend", cookie_blog_id: str = "") -> str:
    """생성된 블로그 글을 네이버 블로그에 발행한다.
    브라우저 세션을 닫지 않고 유지하여 로그인 만료를 방지한다.

    Args:
        blog_data: {"title": ..., "body": ..., ...}
        blog_id: 네이버 블로그 ID
        cookie_blog_id: 블로그별 쿠키/프로필 ID

    Returns:
        발행된 글 URL (실패 시 빈 문자열)
    """
    naver_id = blog_id
    if not naver_id:
        print("  [Naver] 블로그 ID 없음")
        return ""

    title = blog_data.get("title", "")
    # structure → Playwright 명령 직접 변환 (마크다운 중간 단계 없음)
    from publisher.blog_formatter import structure_to_commands
    if blog_data.get("_tpl_data") and blog_data.get("_slots"):
        commands = structure_to_commands(
            tpl_data=blog_data["_tpl_data"],
            slots=blog_data["_slots"],
            blog_images=blog_data.get("_blog_images", []),
            blog_id=cookie_blog_id,
            thumb_url=blog_data.get("_thumb_url", ""),
            region=blog_data.get("region", ""),
            region_short=blog_data.get("region_short", ""),
        )
    else:
        # 폴백: body가 있으면 기존 마크다운 파싱
        from publisher.blog_formatter import markdown_to_commands
        body = blog_data.get("body", "")
        commands = markdown_to_commands(body, template_name=template_name, blog_id=cookie_blog_id)
    print(f"  [Format] {len(commands)}개 명령 생성")

    # 세션 가져오기 (기존 세션 재사용 또는 새로 생성)
    context, page = get_session(cookie_blog_id)

    try:
        # 로그인 확인
        logged_in = _check_login(page, blog_url=naver_id)

        if not logged_in:
            # 세션이 죽었으면 컨텍스트 재생성 시도
            print(f"  [Naver] 로그인 없음 — 세션 재생성 ({cookie_blog_id})")
            try:
                context.close()
            except Exception:
                pass
            if cookie_blog_id in _sessions:
                del _sessions[cookie_blog_id]
            context, page = get_session(cookie_blog_id)
            logged_in = _check_login(page, blog_url=naver_id)

        if not logged_in:
            print(f"  [Naver] 로그인 실패! 수동 갱신 필요: python save_naver_cookies.py {cookie_blog_id}")
            _save_cookies(context, cookie_blog_id)
            try:
                from publisher.slack_notify import notify_login_expired
                notify_login_expired(cookie_blog_id)
            except Exception:
                pass
            return ""

        print(f"  [Naver] 로그인 확인 ({cookie_blog_id})")

        # 글쓰기 페이지 — _check_login에서 이미 postwrite 접속
        _random_delay(3, 5)

        # 팝업/도움말 전부 닫기
        _random_delay(2, 3)
        for close_sel in [
            ".se-popup-button-cancel",
            ".se-popup-button-confirm",
            ".se-help-panel-close-button",
            "button:has-text('닫기')",
        ]:
            try:
                el = page.query_selector(close_sel)
                if el and el.is_visible():
                    el.click()
                    _random_delay(0.5, 1)
                    print(f"  [Naver] 팝업 닫기: {close_sel[:30]}")
            except Exception:
                pass

        print("  [Naver] 글쓰기 페이지 접속")

        # ── 제목 입력 ──
        title_selector = ".se-title-text .se-text-paragraph"
        page.wait_for_selector(title_selector, timeout=10000)
        page.click(title_selector)
        _random_delay(1, 2)
        page.keyboard.type(title, delay=random.randint(30, 60))
        print(f"  [Naver] 제목 입력: {title[:30]}")
        _random_delay(1, 2)

        # ── 본문 영역 클릭 ──
        body_area = page.locator(".se-component.se-text .se-text-paragraph").first
        body_area.click()
        _random_delay(1, 2)

        # ── 명령 실행 ──
        image_count = 0
        for cmd in commands:
            t = cmd["type"]

            if t == "blank_line":
                page.keyboard.press("Enter")

            elif t == "newline":
                page.keyboard.press("Enter")

            elif t == "text":
                page.keyboard.type(cmd["text"], delay=random.randint(3, 10))

            elif t == "bold_text":
                page.keyboard.press("Control+b")
                page.keyboard.type(cmd["text"], delay=random.randint(3, 10))
                page.keyboard.press("Control+b")

            elif t == "heading":
                _change_font_size(page, cmd["size"])
                page.keyboard.press("Control+b")
                page.keyboard.type(cmd["text"], delay=random.randint(3, 10))
                page.keyboard.press("Control+b")
                page.keyboard.press("Enter")
                _change_font_size(page, 15)

            elif t == "quote":
                # 인용구 삽입: 네이버 에디터 인용구 버튼
                try:
                    quote_btn = page.locator("button.se-quote-toolbar-button, button[data-name='quotation']").first
                    if quote_btn.is_visible(timeout=2000):
                        quote_btn.click()
                        _random_delay(0.5, 1)
                        # 스타일 선택 (style 1~5)
                        style = cmd.get("style", 3)
                        style_btn = page.locator(f".se-popup-quote-style button >> nth={style - 1}")
                        if style_btn.is_visible(timeout=1000):
                            style_btn.click()
                            _random_delay(0.5, 1)
                    page.keyboard.type(cmd["text"], delay=random.randint(3, 10))
                    page.keyboard.press("Enter")
                    page.keyboard.press("Enter")
                    _random_delay(0.3, 0.5)
                except Exception as e:
                    # 인용구 버튼 실패 시 일반 텍스트로 대체
                    page.keyboard.type(cmd["text"], delay=random.randint(3, 10))
                    page.keyboard.press("Enter")
                    print(f"  [Naver] 인용구 실패 → 텍스트 대체: {e}")

            elif t == "divider":
                # 구분선 삽입: 네이버 에디터 구분선 버튼
                try:
                    line_btn = page.locator("button.se-horizontal-line-toolbar-button, button[data-name='horizontalLine']").first
                    if line_btn.is_visible(timeout=2000):
                        line_btn.click()
                        _random_delay(0.5, 1)
                    else:
                        page.keyboard.press("Enter")
                except Exception:
                    page.keyboard.press("Enter")

            elif t == "image":
                abs_path = os.path.abspath(cmd["path"])
                if os.path.exists(abs_path):
                    try:
                        with page.expect_file_chooser(timeout=5000) as fc_info:
                            page.click(".se-image-toolbar-button")
                        fc_info.value.set_files(abs_path)
                        _random_delay(3, 5)

                        # 파일 전송 오류 팝업 처리 (최대 3초 대기)
                        upload_failed = False
                        for popup_sel in [
                            ".se-popup-button-confirm",
                            "button:has-text('확인')",
                        ]:
                            try:
                                popup_btn = page.locator(popup_sel).first
                                if popup_btn.is_visible(timeout=2000):
                                    # 팝업 텍스트에 "오류" 또는 "전송"이 있는지 확인
                                    popup_text = page.locator(".se-popup-content, .layer_popup").first.inner_text(timeout=1000) if True else ""
                                    popup_btn.click()
                                    _random_delay(0.5, 1)
                                    print(f"  [Naver] 이미지 전송 오류 — 스킵: {Path(cmd['path']).name}")
                                    upload_failed = True
                                    # 본문 영역 다시 클릭
                                    try:
                                        body_area = page.locator(".se-component.se-text .se-text-paragraph").last
                                        body_area.click()
                                        _random_delay(0.5, 1)
                                    except Exception:
                                        pass
                                    break
                            except Exception:
                                continue

                        if upload_failed:
                            continue

                        image_count += 1
                        print(f"  [Naver] 이미지 {image_count}: {Path(cmd['path']).name}")

                        if cmd.get("link"):
                            _add_link_to_image(page, cmd["link"])
                            print(f"  [Naver] 링크: {cmd['link']}")
                    except Exception as e:
                        print(f"  [Naver] 이미지 실패: {e}")

            elif t == "hashtags":
                page.keyboard.type(cmd["text"], delay=random.randint(3, 10))
                page.keyboard.press("Enter")

        print(f"  [Naver] 본문 입력 완료 (이미지 {image_count}개)")

        # 입력 확인 스크린샷
        page.screenshot(path="data/generated/naver_before_publish.png")
        _random_delay(2, 3)

        # 발행 버튼
        publish_btn = None
        for sel in [
            "button:has-text('발행')",
            "button[class*='publish_btn']",
            "button.publish_btn__m9KHH",
        ]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    publish_btn = btn
                    break
            except Exception:
                continue

        if not publish_btn:
            print("  [Naver] 발행 버튼 찾기 실패")
            page.screenshot(path="data/generated/naver_no_publish_btn.png")
            return ""

        publish_btn.click()
        print("  [Naver] 발행 버튼 클릭")
        _random_delay(3, 5)

        # 발행 확인 다이얼로그
        page.screenshot(path="data/generated/naver_publish_dialog.png")
        try:
            dialog_btn = None
            for sel in [
                ".se-popup-button-confirm",
                "button[class*='confirm_btn']",
                "button:has-text('발행')",
            ]:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=3000):
                        dialog_btn = btn
                        break
                except Exception:
                    continue

            if dialog_btn:
                dialog_btn.click()
                print("  [Naver] 발행 확인 클릭")
            else:
                print("  [Naver] 발행 확인 다이얼로그 못 찾음")
        except Exception:
            pass

        # 발행 완료 대기
        for _ in range(15):
            time.sleep(1)
            if "postwrite" not in page.url:
                break

        current_url = page.url
        page.screenshot(path="data/generated/naver_after_publish.png")
        _save_cookies(context, cookie_blog_id)

        if "postwrite" not in current_url:
            print(f"  [Naver] 발행 완료! {current_url}")
            return current_url
        else:
            print(f"  [Naver] URL 전환 안 됨 — 최근 글 확인 중...")
            try:
                page.goto(f"https://blog.naver.com/{naver_id}", timeout=10000)
                _random_delay(2, 3)
                latest_url = page.url
                if naver_id in latest_url and "postwrite" not in latest_url:
                    print(f"  [Naver] 발행 확인! {latest_url}")
                    return latest_url
            except Exception:
                pass
            print(f"  [Naver] 발행 실패")
            return ""

    except Exception as e:
        print(f"  [Naver] 오류: {e}")
        try:
            page.screenshot(path="data/generated/naver_error.png")
        except Exception:
            pass
        return ""


def _change_font_size(page, size: int):
    """네이버 에디터 글자 크기 변경. size: 11,13,15,16,19,24,28,30,34,38"""
    try:
        # 글자 크기 버튼 클릭
        size_btn = page.query_selector(".se-font-size-code-toolbar-button")
        if size_btn:
            size_btn.click()
            _random_delay(0.5, 1)

            # data-value="fs19" 형식으로 선택
            size_option = page.query_selector(f"button[data-value='fs{size}']")
            if size_option and size_option.is_visible():
                size_option.click()
                _random_delay(0.3, 0.5)
            else:
                # 드롭다운 닫기
                page.keyboard.press("Escape")
    except Exception as e:
        print(f"  [Naver] 글자 크기 변경 실패: {e}")


def _add_link_to_image(page, url: str):
    """현재 선택된 이미지에 링크를 건다."""
    try:
        # 마지막으로 추가된 이미지 클릭
        images = page.query_selector_all(".se-image-resource")
        if images:
            images[-1].click()
            _random_delay(0.5, 1)

            # 링크 버튼 클릭
            link_btn = page.query_selector(".se-link-toolbar-button")
            if link_btn and link_btn.is_visible():
                link_btn.click()
                _random_delay(0.5, 1)

                # URL 입력
                link_input = page.query_selector(".se-custom-layer-link-input")
                if link_input:
                    link_input.fill(url)
                    _random_delay(0.3, 0.5)

                    # 적용 버튼 클릭
                    page.click(".se-custom-layer-link-apply-button")
                    _random_delay(1, 2)

            # 이미지 뒤로 커서 이동 — 이미지 컴포넌트 다음의 텍스트 영역으로
            # 방법: 이미지 아래 빈 영역 클릭 또는 End → Enter
            page.keyboard.press("Escape")  # 이미지 선택 해제
            _random_delay(0.3, 0.5)
            page.keyboard.press("End")     # 줄 끝으로
            _random_delay(0.3, 0.5)
            page.keyboard.press("Enter")   # 새 줄
            _random_delay(0.3, 0.5)
    except Exception as e:
        print(f"  [Naver] 링크 걸기 실패: {e}")


