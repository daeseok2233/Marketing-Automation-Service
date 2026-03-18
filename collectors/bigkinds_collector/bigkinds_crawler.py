"""빅카인즈 Playwright 자동화 — 엑셀 다운로드
필요: pip install playwright && playwright install chromium

쿠키가 없거나 만료되면 .env의 BIGKINDS_ID/PW로 자동 로그인 → 쿠키 저장.
이후 실행에서는 저장된 쿠키 재사용.
"""
import os, time, json
from config import DOWNLOAD_DIR
from pathlib import Path
from datetime import datetime, timedelta

BIGKINDS_DIR = DOWNLOAD_DIR/"bigkinds"
COOKIE_FILE    = BIGKINDS_DIR / ".cookies.json"
BIGKINDS_URL   = "https://www.bigkinds.or.kr"
SEARCH_KEYWORD = "상표"


def _auto_login(page) -> bool:
    """BIGKINDS_ID/PW로 자동 로그인 시도. 성공하면 True."""
    user_id = os.environ.get("BIGKINDS_ID", "")
    user_pw = os.environ.get("BIGKINDS_PW", "")
    if not user_id or not user_pw:
        print("  [BigKinds] BIGKINDS_ID / BIGKINDS_PW 미설정 — .env 파일 확인")
        return False

    print(f"  [BigKinds] 자동 로그인 시도: {user_id}")
    try:
        # 1) MEMBERSHIP 메뉴 클릭 → 2) 로그인 서브메뉴 클릭 → 모달 오픈
        try:
            page.locator("text=MEMBERSHIP").first.click()
            time.sleep(1)
            page.locator("text=로그인").first.click()
            time.sleep(1)
        except Exception:
            pass

        # 로그인 폼이 안 열렸으면 직접 로그인 페이지로 이동
        if not page.locator("#login-user-id").first.is_visible():
            page.goto(f"{BIGKINDS_URL}/v2/auth/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            time.sleep(1)
            # 다시 모달 열기 시도
            try:
                page.locator("text=MEMBERSHIP").first.click()
                time.sleep(1)
                page.locator("text=로그인").first.click()
                time.sleep(1)
            except Exception:
                pass

        # ID/PW 입력
        page.locator("#login-user-id").first.fill(user_id)
        page.locator("#login-user-password").first.fill(user_pw)

        # 로그인 버튼 클릭 (모달 내부)
        for btn_sel in [
            ".modal-login button:has-text('로그인')",
            "button:has-text('로그인')",
            ".login-submit",
        ]:
            try:
                el = page.locator(btn_sel).first
                if el.count() > 0 and el.is_visible():
                    el.click()
                    break
            except Exception:
                continue

        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(2)

        # 로그인 성공 확인
        if _is_logged_in(page):
            print("  [BigKinds] 로그인 성공")
            return True

        print("  [BigKinds] 로그인 실패 — ID/PW 확인 필요")
        return False

    except Exception as e:
        print(f"  [BigKinds] 로그인 오류: {e}")
        return False


def _save_cookies(context):
    """현재 브라우저 컨텍스트의 쿠키를 파일로 저장"""
    BIGKINDS_DIR.mkdir(parents=True, exist_ok=True)
    cookies = context.cookies()
    COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [BigKinds] 쿠키 저장 ({len(cookies)}개)")


def _is_logged_in(page) -> bool:
    """현재 페이지에서 로그인 상태인지 확인"""
    try:
        # 로그아웃 버튼이 있으면 로그인된 상태
        if page.locator("a:has-text('로그아웃'), button:has-text('로그아웃'), .logout-btn").first.count() > 0:
            return True
        # 로그인 버튼이 보이면 미로그인
        if page.locator("a:has-text('로그인'), button:has-text('로그인'), .login-btn").first.count() > 0:
            return False
    except Exception:
        pass
    return True  # 판단 불가 시 일단 진행


def download_bigkinds_xlsx(headless: bool = True) -> Path | None:
    """빅카인즈 접속 → (필요 시 로그인) → 검색 → 엑셀 다운로드"""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("  [BigKinds] playwright 미설치")
        return None

    BIGKINDS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True)

        # 쿠키 파일이 있으면 로드
        if COOKIE_FILE.exists():
            try:
                cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
                context.add_cookies(cookies)
                print("  [BigKinds] 쿠키 로드")
            except Exception:
                pass

        page = context.new_page()

        try:
            # ── 1. 메인 페이지 이동
            print("  [BigKinds] 접속 중...")
            page.goto(BIGKINDS_URL, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)

            # ── 2. 로그인 상태 확인 → 미로그인이면 자동 로그인
            if not _is_logged_in(page):
                print("  [BigKinds] 로그인 필요")
                if not _auto_login(page):
                    browser.close()
                    return None
                _save_cookies(context)
                # 메인으로 복귀
                page.goto(BIGKINDS_URL, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)
            else:
                print("  [BigKinds] 로그인 상태 확인")

            # ── 3. 키워드 검색
            print(f"  [BigKinds] '{SEARCH_KEYWORD}' 검색 중...")
            search_box = page.locator(
                "#searchKeyword, #srchText, input[placeholder*='검색어'], input[name*='query']"
            ).first
            search_box.fill(SEARCH_KEYWORD)
            search_box.press("Enter")
            page.wait_for_load_state("networkidle", timeout=20000)
            time.sleep(2)

            # ── 4. 날짜 범위 (최근 3개월)
            date_to   = datetime.now().strftime("%Y-%m-%d")
            date_from = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            try:
                page.locator("#startDate, input[id*='start']").first.fill(date_from)
                page.locator("#endDate,   input[id*='end']").first.fill(date_to)
                page.click("button:has-text('검색'), #searchBtn")
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)
            except Exception:
                pass

            # ── 5. STEP 03 분석 결과 및 시각화 클릭
            print("  [BigKinds] STEP 03 클릭 중...")
            step03_clicked = False
            for selector in [
                "text=분석 결과 및 시각화",
                "text=STEP 03",
                ".step03-btn",
                "#step03",
                "[data-step='3']",
                "li:has-text('분석 결과')",
                "a:has-text('분석결과')",
            ]:
                try:
                    el = page.locator(selector).first
                    if el.count() > 0:
                        el.scroll_into_view_if_needed()
                        el.click(timeout=5000)
                        step03_clicked = True
                        print(f"  [BigKinds] STEP 03 클릭 성공: {selector}")
                        break
                except Exception:
                    continue

            if not step03_clicked:
                page.evaluate("""
                    const els = [...document.querySelectorAll('*')];
                    const el = els.find(e => e.innerText && e.innerText.includes('분석 결과 및 시각화'));
                    if (el) el.click();
                """)
                print("  [BigKinds] STEP 03 JS 클릭 시도")

            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)

            # ── 6. 엑셀 다운로드
            print("  [BigKinds] 엑셀 다운로드 중...")
            with page.expect_download(timeout=60000) as dl_info:
                page.click(
                    "button:has-text('엑셀다운로드'), a:has-text('엑셀다운로드'), "
                    "button:has-text('엑셀 다운로드'), a:has-text('엑셀 다운로드'), "
                    "#excelDownload, .excel-download, [onclick*='excel'], [onclick*='Excel']"
                )
            download  = dl_info.value
            date_str  = datetime.now().strftime("%Y%m%d")
            save_path = BIGKINDS_DIR / f"bigkinds_{date_str}.xlsx"
            download.save_as(save_path)
            print(f"  [BigKinds] 저장 완료: {save_path}")

            # 다운로드 성공 시 쿠키 갱신
            _save_cookies(context)
            return save_path

        except PWTimeout as e:
            print(f"  [BigKinds] 타임아웃: {e}")
        except Exception as e:
            print(f"  [BigKinds] 오류: {e}")
            try:
                ss = BIGKINDS_DIR / f"debug_{datetime.now().strftime('%H%M%S')}.png"
                page.screenshot(path=str(ss))
                print(f"  [BigKinds] 스크린샷: {ss}")
            except Exception:
                pass
        finally:
            browser.close()

        return None


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    result = download_bigkinds_xlsx(headless=False)
    print(f"결과: {result}")
