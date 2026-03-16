"""빅카인즈 Playwright 자동화 — 엑셀 다운로드
필요: pip install playwright && playwright install chromium

사용법:
  1. 최초 1회 쿠키 저장 (.env에 BIGKINDS_ID, BIGKINDS_PW 설정 후):
       python collectors/bigkinds_crawler.py --save-cookies
  2. 이후 자동 실행 (파이프라인이 자동 호출):
       python collectors/bigkinds_crawler.py
"""
import os, time, json, argparse
from pathlib import Path
from datetime import datetime, timedelta

DOWNLOAD_DIR   = Path("data/bigkinds")
COOKIE_FILE    = Path("data/bigkinds/.cookies.json")
BIGKINDS_URL   = "https://www.bigkinds.or.kr"
SEARCH_KEYWORD = "상표"


def save_cookies():
    """이메일/비번으로 로그인 후 쿠키 저장 (최초 1회)"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 미설치 — 'pip install playwright && playwright install chromium'")
        return

    user_id = os.environ.get("BIGKINDS_ID", "")
    user_pw = os.environ.get("BIGKINDS_PW", "")
    if not user_id or not user_pw:
        print("BIGKINDS_ID / BIGKINDS_PW 미설정 — .env 파일 확인")
        return

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page    = context.new_page()

        print("빅카인즈 접속 중...")
        page.goto(BIGKINDS_URL, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=20000)

        # 로그인 버튼 클릭
        try:
            page.click("a:has-text('로그인'), .login-btn, #loginBtn", timeout=8000)
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # 이메일/비번 입력
        print(f"  로그인 시도: {user_id}")
        try:
            page.fill("#userId, input[name='userId'], input[type='email']", user_id)
            page.fill("#userPw, input[name='userPw'], input[type='password']", user_pw)
            page.click("button[type='submit'], input[type='submit'], .login-submit, button:has-text('로그인')")
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)
        except Exception as e:
            print(f"  자동 로그인 실패: {e}")
            print("  브라우저에서 직접 로그인 후 Enter를 누르세요...")
            input()

        cookies = context.cookies()
        COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"쿠키 저장 완료: {COOKIE_FILE} ({len(cookies)}개)")
        browser.close()


def download_bigkinds_xlsx(headless: bool = True) -> Path | None:
    """저장된 쿠키로 빅카인즈 접속 → '상표' 검색 → 엑셀 다운로드"""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("  [BigKinds] playwright 미설치")
        return None

    if not COOKIE_FILE.exists():
        print("  [BigKinds] 쿠키 없음 — 먼저 'python collectors/bigkinds_crawler.py --save-cookies' 실행")
        return None

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True)
        context.add_cookies(cookies)
        page = context.new_page()

        try:
            # ── 1. 메인 페이지 이동
            print("  [BigKinds] 접속 중...")
            page.goto(BIGKINDS_URL, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)

            # ── 2. 현재 상태 스크린샷
            ss = DOWNLOAD_DIR / f"debug_main_{datetime.now().strftime('%H%M%S')}.png"
            page.screenshot(path=str(ss))
            print(f"  [BigKinds] 메인 페이지 스크린샷: {ss}")

            # ── 3. 키워드 검색
            print(f"  [BigKinds] '{SEARCH_KEYWORD}' 검색 중...")
            search_box = page.locator(
                "#searchKeyword, #srchText, input[placeholder*='검색어'], input[name*='query']"
            ).first
            search_box.fill(SEARCH_KEYWORD)
            search_box.press("Enter")
            page.wait_for_load_state("networkidle", timeout=20000)
            time.sleep(2)

            # ── 4. 날짜 범위 (최근 30일)
            date_to   = datetime.now().strftime("%Y-%m-%d")
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            try:
                page.locator("#startDate, input[id*='start']").first.fill(date_from)
                page.locator("#endDate,   input[id*='end']"  ).first.fill(date_to)
                page.click("button:has-text('검색'), #searchBtn")
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)
            except Exception:
                pass

            # ── 5. STEP 03 분석 결과 및 시각화 클릭
            print("  [BigKinds] STEP 03 클릭 중...")
            # 여러 셀렉터 순서대로 시도
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
                # JS로 텍스트 기반 클릭 시도
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
            save_path = DOWNLOAD_DIR / f"bigkinds_{date_str}.xlsx"
            download.save_as(save_path)
            print(f"  [BigKinds] 저장 완료: {save_path}")
            return save_path

        except PWTimeout as e:
            print(f"  [BigKinds] 타임아웃: {e}")
        except Exception as e:
            print(f"  [BigKinds] 오류: {e}")
            try:
                ss = DOWNLOAD_DIR / f"debug_{datetime.now().strftime('%H%M%S')}.png"
                page.screenshot(path=str(ss))
                print(f"  [BigKinds] 스크린샷: {ss}")
            except Exception:
                pass
        finally:
            browser.close()

        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--save-cookies", action="store_true", help="로그인 후 쿠키 저장")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    if args.save_cookies:
        save_cookies()
    else:
        result = download_bigkinds_xlsx(headless=False)
        print(f"결과: {result}")
