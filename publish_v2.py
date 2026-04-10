"""structure + slots 기반 발행 스크립트.

app_collect.py에서 호출. Playwright로 네이버 블로그에 발행.
structure의 size/type에 따라 글자크기, 이미지 배치 제어.

Usage: python publish_v2.py <json_file>
"""

import json
import os
import sys
import time
import random
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python publish_v2.py <json_file>", file=sys.stderr)
        sys.exit(1)

    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    title = data["title"]
    slots = data["slots"]
    structure = data["structure"]
    blog_id = data["blog_id"]
    cookie_blog_id = data["cookie_blog_id"]

    from publisher.naver_blog import get_session, _check_login, _random_delay

    context, page = get_session(cookie_blog_id)

    try:
        logged_in = _check_login(page, blog_url=blog_id)
        if not logged_in:
            print(f"  [Naver] 로그인 실패! python save_naver_cookies.py {cookie_blog_id}")
            sys.exit(1)

        # 글쓰기 페이지
        for sel in [".se-popup-button-cancel", ".se-help-panel-close-button"]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    time.sleep(0.5)
            except Exception:
                pass

        page.goto(f"https://blog.naver.com/{blog_id}/postwrite", timeout=15000)
        time.sleep(3)
        print(f"  [Naver] 글쓰기 페이지 접속")

        # 팝업 닫기
        for sel in [".se-popup-button-cancel", ".se-help-panel-close-button"]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    time.sleep(0.5)
                    print(f"  [Naver] 팝업 닫기: {sel}")
            except Exception:
                pass

        # 제목 입력
        title_area = page.locator(".se-title-text .se-text-paragraph").first
        title_area.click()
        time.sleep(0.5)
        page.keyboard.type(title, delay=random.randint(30, 60))
        print(f"  [Naver] 제목 입력: {title[:30]}")
        _random_delay(1, 2)

        # 본문 클릭
        body_area = page.locator(".se-component.se-text .se-text-paragraph").first
        body_area.click()
        _random_delay(1, 2)

        # 글자크기 변경 함수
        def change_font_size(size):
            try:
                btn = page.locator(".se-font-size-code-toolbar-button").first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    time.sleep(0.7)
                    opt = page.locator(f"button[data-value='fs{size}']").first
                    if opt.is_visible(timeout=1000):
                        opt.click()
                        time.sleep(0.5)
                    else:
                        page.keyboard.press("Escape")
            except Exception:
                pass

        # 이미지 업로드 함수
        def upload_image(img_path):
            abs_path = os.path.abspath(img_path)
            if not os.path.exists(abs_path):
                return
            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    page.click(".se-image-toolbar-button")
                fc_info.value.set_files(abs_path)
                _random_delay(3, 5)
                print(f"  [Naver] 이미지: {Path(img_path).name}")
            except Exception as e:
                print(f"  [Naver] 이미지 실패: {e}")

        # 이미지 링크 삽입 함수
        def add_link_to_image(url):
            try:
                images = page.query_selector_all(".se-image-resource")
                if images:
                    images[-1].click()
                    _random_delay(0.5, 1)
                    link_btn = page.locator("button[data-name='link'], button.se-link-toolbar-button").first
                    if link_btn.is_visible(timeout=2000):
                        link_btn.click()
                        _random_delay(0.5, 1)
                        url_input = page.locator("input[placeholder*='URL'], input[type='url'], .se-popup-link input").first
                        if url_input.is_visible(timeout=2000):
                            url_input.fill(url)
                            _random_delay(0.3, 0.5)
                            confirm = page.locator("button:has-text('확인'), button:has-text('적용')").first
                            if confirm.is_visible(timeout=1000):
                                confirm.click()
                                _random_delay(0.5, 1)
                                print(f"  [Naver] 링크: {url[:30]}")
                    # 본문 영역 다시 클릭
                    body_area = page.locator(".se-component.se-text .se-text-paragraph").last
                    body_area.click()
                    _random_delay(0.3, 0.5)
            except Exception as e:
                print(f"  [Naver] 링크 삽입 실패: {e}")

        # 이미지 목록 + 링크 로드
        import csv
        blog_images = []
        image_links = {}
        img_csv = Path("data/image/image_list.csv")
        if img_csv.exists():
            with open(img_csv, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if row.get("블로그삽입", "").strip() == "O":
                        blog_images.append(row.get("이미지경로", ""))
                    name = row.get("이미지이름", "")
                    link = row.get("링크주소", "").strip()
                    if name:
                        image_links[name] = link

        # 블로그별 링크 매핑
        blog_links = {}
        blog_links_path = Path("data/image/blog_links.json")
        if blog_links_path.exists():
            all_blog_links = json.loads(blog_links_path.read_text(encoding="utf-8"))
            blog_links = all_blog_links.get(cookie_blog_id, {})

        def get_link(img_path):
            """이미지 경로 → 블로그별 cutt.ly 링크."""
            filename = Path(img_path).name
            base_link = image_links.get(filename, "")
            if not base_link or not blog_links:
                return base_link
            if "kakao" in base_link.lower():
                return blog_links.get("카카오", base_link)
            if "markview" in base_link.lower():
                return blog_links.get("마크뷰", base_link)
            if "markpick" in base_link.lower():
                return blog_links.get("마크픽", base_link)
            return base_link

        img_idx = 0

        # structure 기반 명령 실행
        for item in structure:
            t = item.get("type", "")
            slot = item.get("slot", "")
            size = item.get("size", 15)
            content = item.get("content", "")
            text = slots.get(slot, "") if slot else ""

            if t == "blank":
                page.keyboard.press("Enter")

            elif t == "image":
                img_path = ""
                if "썸네일" in content:
                    # 제목 기반으로 썸네일 생성 (이모지 제거)
                    from blog_generator.thumbnail_maker import make_thumbnail
                    import re as _re
                    clean_title = _re.sub(r'[^\w\s가-힣a-zA-Z0-9.,!?~·\-\'\"()%]', '', title).strip()
                    thumb_path = make_thumbnail(
                        main_title=clean_title,
                        sub_title_1="",
                        sub_title_2="",
                        region="",
                        output_name=f"thumb_{_re.sub(r'[/\\\\|:*?\"<>]', '_', title[:20])}.png",
                    )
                    if thumb_path:
                        img_path = thumb_path
                        upload_image(img_path)
                        print(f"  [Naver] 썸네일 생성+업로드: {Path(img_path).name}")
                elif "쿠폰" in content:
                    img_path = "data/image/event/image_mark_pick_coupon.png"
                    upload_image(img_path)
                    link = get_link(img_path)
                    if link:
                        add_link_to_image(link)
                elif "카카오" in content:
                    img_path = "data/image/basic/image_mark_pick_kakao.png"
                    upload_image(img_path)
                    link = get_link(img_path)
                    if link:
                        add_link_to_image(link)
                else:
                    if img_idx < len(blog_images):
                        img_path = blog_images[img_idx]
                        upload_image(img_path)
                        link = get_link(img_path)
                        if link:
                            add_link_to_image(link)
                        img_idx += 1

            elif t == "heading":
                if text:
                    change_font_size(size)
                    page.keyboard.press("Control+b")
                    page.keyboard.type(text, delay=random.randint(3, 10))
                    page.keyboard.press("Control+b")
                    page.keyboard.press("Enter")
                    change_font_size(15)

            elif t == "text":
                if text:
                    for line in text.split("\n"):
                        if line.strip():
                            page.keyboard.type(line, delay=random.randint(3, 8))
                            page.keyboard.press("Enter")

            elif t == "hashtags":
                if text:
                    page.keyboard.type(text, delay=random.randint(3, 10))
                    page.keyboard.press("Enter")

            time.sleep(0.3)

        print(f"  [Naver] 본문 입력 완료")
        _random_delay(2, 3)

        # 발행 버튼 (여러 셀렉터 시도)
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
            print("  [Naver] 발행 버튼 찾기 실패", file=sys.stderr)
            page.screenshot(path="data/generated/naver_no_publish_btn.png")
            sys.exit(1)

        publish_btn.click()
        print(f"  [Naver] 발행 버튼 클릭")
        _random_delay(3, 5)

        # 발행 확인 다이얼로그
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
            print(f"  [Naver] 발행 확인 클릭")
        _random_delay(3, 5)

        # URL 확인 (최대 15초 대기)
        for _ in range(5):
            time.sleep(3)
            current_url = page.url
            if "postwrite" not in current_url and blog_id in current_url:
                print(current_url)
                break
        else:
            print(f"https://blog.naver.com/{blog_id}")

    except Exception as e:
        print(f"발행 실패: {e}", file=sys.stderr)
        sys.exit(1)
