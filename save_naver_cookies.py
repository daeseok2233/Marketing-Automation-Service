"""네이버 수동 로그인 → 블로그별 persistent context 프로필 저장. 터미널에서 직접 실행하세요."""
from playwright.sync_api import sync_playwright
import json, sys, time
from pathlib import Path

PROFILE_BASE = Path("data/browser_profiles")

blog_id = sys.argv[1] if len(sys.argv) > 1 else None

if not blog_id:
    print("사용법: python save_naver_cookies.py blog_02")
    print("       python save_naver_cookies.py all")
    sys.exit(1)

blogs_to_login = []

if blog_id == "all":
    data = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))
    for bid, info in data["blogs"].items():
        if info.get("naver_id"):
            blogs_to_login.append((bid, info["naver_id"], info.get("blog_url", "")))
else:
    data = json.loads(Path("data/service_data/blogs.json").read_text(encoding="utf-8"))
    info = data["blogs"].get(blog_id, {})
    blogs_to_login.append((blog_id, info.get("naver_id", blog_id), info.get("blog_url", "")))

for bid, naver_id, blog_url in blogs_to_login:
    print(f"\n{'='*40}")
    print(f"  {bid} ({naver_id}) 로그인")
    print(f"{'='*40}")
    print("브라우저가 열리면 네이버에 직접 로그인하세요.")
    print("로그인 완료 후 이 터미널에서 엔터를 누르세요.")
    print()

    profile_dir = PROFILE_BASE / bid
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # persistent context — 로그인 상태가 프로필 디렉토리에 자동 저장됨
        context = p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://nid.naver.com/nidlogin.login")

        input(">>> 로그인 완료 후 엔터 <<<")

        # 글쓰기 페이지까지 접속해서 추가 쿠키 확보
        if blog_url:
            print(f"  글쓰기 페이지 접속 중: {blog_url}/postwrite")
            try:
                page.goto(f"https://blog.naver.com/{blog_url}/postwrite", timeout=15000)
                time.sleep(3)
                # 팝업 닫기
                for sel in [".se-popup-button-cancel", ".se-help-panel-close-button"]:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            time.sleep(0.5)
                    except:
                        pass
                print(f"  글쓰기 페이지 접속 완료")
            except Exception as e:
                print(f"  글쓰기 페이지 접속 실패: {e}")

        # JSON 쿠키도 백업 저장 (호환용)
        cookies = context.cookies()
        cookie_path = Path(f"data/naver_blog_cookies_{bid}.json")
        cookie_path.write_text(
            json.dumps(cookies, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  프로필 저장: {profile_dir}")
        print(f"  쿠키 백업: {cookie_path} ({len(cookies)}개)")
        context.close()

print("\n완료!")
