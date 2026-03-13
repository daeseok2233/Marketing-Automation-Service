"""
마크뷰 화면 캡처 유틸리티
- playwright 설치 필요: pip install playwright && playwright install chromium
- MARKVIEW_EMAIL / MARKVIEW_PASSWORD 환경변수로 로그인 (없으면 비로그인 검색)
- IMGUR_CLIENT_ID 환경변수 설정 시 Imgur에 자동 업로드 → 노션에 이미지 블록으로 삽입 가능
  Imgur Client ID 발급: https://api.imgur.com/oauth2/addclient (Anonymous usage 선택)
- 캡처한 이미지는 screenshots/ 폴더에도 항상 로컬 저장
"""
import os, base64, requests as _requests
from pathlib import Path
from datetime import datetime

SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
MARKVIEW_URL    = "https://www.markview.co.kr"


def _try_import_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def capture_markview_search(keyword: str) -> dict:
    """
    마크뷰에서 keyword를 텍스트 검색한 결과 화면을 캡처.

    반환:
    {
        "success": True/False,
        "path": "screenshots/markview_쿨피스_20250313_143022.png",
        "url": None,   ← 이미지 호스팅 후 URL (현재는 None)
        "error": ""
    }
    """
    sync_playwright = _try_import_playwright()
    if sync_playwright is None:
        return {
            "success": False,
            "path": None,
            "url": None,
            "error": "playwright 미설치. 'pip install playwright && playwright install chromium' 실행 필요",
        }

    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_kw   = "".join(c for c in keyword if c.isalnum() or c in "_-")[:20]
    filename  = SCREENSHOTS_DIR / f"markview_{safe_kw}_{timestamp}.png"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page    = browser.new_page(viewport={"width": 1280, "height": 900})

            # 로그인 시도 (환경변수 있는 경우)
            email    = os.environ.get("MARKVIEW_EMAIL", "")
            password = os.environ.get("MARKVIEW_PASSWORD", "")
            if email and password:
                page.goto(f"{MARKVIEW_URL}/login", timeout=20000)
                page.fill("input[type='email'], input[name='email']", email)
                page.fill("input[type='password'], input[name='password']", password)
                page.click("button[type='submit']")
                page.wait_for_load_state("networkidle", timeout=10000)

            # 검색 페이지로 이동
            page.goto(MARKVIEW_URL, timeout=20000)
            page.wait_for_load_state("networkidle", timeout=10000)

            # 마크뷰 검색창 입력 + 검색 버튼(두 번째 버튼) 클릭
            page.fill("input[type='text']", keyword, timeout=5000)
            page.wait_for_timeout(300)
            # 입력창 주변 버튼 중 두 번째가 검색 버튼
            clicked = page.evaluate("""() => {
                const inp = document.querySelector("input[type='text']");
                let el = inp.parentElement;
                for (let i = 0; i < 6; i++) {
                    const btns = el.querySelectorAll("button");
                    if (btns.length >= 2) { btns[1].click(); return true; }
                    el = el.parentElement;
                }
                return false;
            }""")
            if clicked:
                page.wait_for_load_state("networkidle", timeout=10000)
                page.wait_for_timeout(1500)  # 결과 렌더링 대기

            # 결과 화면 캡처
            page.screenshot(path=str(filename), full_page=False)
            browser.close()

        print(f"  [스크린샷] 저장: {filename}")
        url = _upload_imgur(str(filename))
        return {
            "success": True,
            "path":    str(filename),
            "url":     url,
            "error":   "",
        }

    except Exception as e:
        return {
            "success": False,
            "path":    None,
            "url":     None,
            "error":   str(e),
        }


def _upload_imgur(file_path: str) -> str | None:
    """ImgBB에 이미지 업로드 후 직접 링크 반환. IMGBB_API_KEY 없으면 None.
    API 키 발급: https://api.imgbb.com (로그인 후 Get API key)
    """
    api_key = os.environ.get("IMGBB_API_KEY", "")
    if not api_key:
        return None
    try:
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        res = _requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": api_key},
            data={"image": b64},
            timeout=20,
        )
        res.raise_for_status()
        link = res.json()["data"]["url"]
        print(f"  [ImgBB] 업로드 완료: {link}")
        return link
    except Exception as e:
        print(f"  [ImgBB] 업로드 실패: {e}")
        return None


def capture_markview_image_search(image_path: str) -> dict:
    """
    마크뷰에서 이미지로 유사 상표 검색 화면 캡처.
    image_path: 로컬 이미지 파일 경로
    """
    sync_playwright = _try_import_playwright()
    if sync_playwright is None:
        return {
            "success": False,
            "path": None,
            "url": None,
            "error": "playwright 미설치",
        }

    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = SCREENSHOTS_DIR / f"markview_img_{timestamp}.png"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page    = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(MARKVIEW_URL, timeout=20000)
            page.wait_for_load_state("networkidle", timeout=10000)

            # 이미지 업로드 인풋 찾기
            upload_selectors = [
                "input[type='file']",
                "input[accept*='image']",
            ]
            for selector in upload_selectors:
                try:
                    page.set_input_files(selector, image_path, timeout=3000)
                    page.wait_for_load_state("networkidle", timeout=10000)
                    break
                except Exception:
                    continue

            page.screenshot(path=str(filename), full_page=False)
            browser.close()

        url = _upload_imgur(str(filename))
        return {"success": True, "path": str(filename), "url": url, "error": ""}

    except Exception as e:
        return {"success": False, "path": None, "url": None, "error": str(e)}


def screenshot_to_notion_block(screenshot_result: dict) -> dict | None:
    """
    캡처 결과를 노션 이미지 블록으로 변환.
    현재는 URL이 없으므로 캡션 블록으로 대체.
    이미지 호스팅(Cloudinary·Imgur·S3) 연동 시 image 블록 반환 가능.
    """
    if not screenshot_result.get("success"):
        error = screenshot_result.get("error", "캡처 실패")
        return {
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": f"[스크린샷 미첨부] {error}"}}],
                "icon": {"type": "emoji", "emoji": "📷"},
                "color": "yellow_background",
            },
        }

    url = screenshot_result.get("url")
    if url:
        return {
            "object": "block", "type": "image",
            "image": {"type": "external", "external": {"url": url}},
        }

    # URL 없으면 파일 경로 안내 텍스트로 대체
    path = screenshot_result.get("path", "")
    return {
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": f"[스크린샷] {path}"}}],
            "icon": {"type": "emoji", "emoji": "📷"},
            "color": "blue_background",
        },
    }
