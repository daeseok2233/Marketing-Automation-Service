"""네이버 검색 크롤링 — 축제/박람회 정보 수집.

수집: 축제명, 기간, 장소만 빠르게 가져옴.
상세 정보(홈페이지 크롤링 등)는 글 기획 시 필요한 것만 별도 수집.
"""

import json
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright


EXTRACT_JS = """() => {
    const results = [];
    const cards = document.querySelectorAll('.card_item');

    cards.forEach(card => {
        const nameEl = card.querySelector('a:not(.btn_place):not(.btn_find_way):not(.img_box)');
        const dates = card.querySelectorAll('.info_date');

        const name = nameEl ? nameEl.textContent.trim() : '';
        const startDate = dates[0] ? dates[0].textContent.trim() : '';
        const endDate = dates[1] ? dates[1].textContent.trim() : '';

        let place = '';
        const dts = card.querySelectorAll('dt');
        dts.forEach(dt => {
            if (dt.textContent.trim() === '장소') {
                const dd = dt.nextElementSibling;
                if (dd && dd.tagName === 'DD') {
                    place = dd.textContent.trim();
                }
            }
        });

        if (name && name.length > 2) {
            results.push({
                name: name,
                period: startDate + ' ~ ' + endDate,
                place: place,
            });
        }
    });

    return results;
}"""


def collect_events(keywords=None, max_pages=2, headless=True) -> list[dict]:
    """네이버 검색에서 축제/박람회 기본 정보를 크롤링."""
    if keywords is None:
        keywords = ["축제", "박람회"]

    all_events = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        for keyword in keywords:
            print(f"  [행사수집] '{keyword}' 검색 중...")
            page.goto(
                f"https://search.naver.com/search.naver?query={keyword}",
                timeout=15000,
            )
            page.wait_for_timeout(3000)

            for _ in range(max_pages):
                events = page.evaluate(EXTRACT_JS)
                for event in events:
                    key = event["name"]
                    if key not in seen:
                        seen.add(key)
                        event["keyword"] = keyword
                        all_events.append(event)

                next_btn = page.locator("a.pg_next.on")
                if next_btn.is_visible(timeout=2000):
                    next_btn.click()
                    page.wait_for_timeout(2000)
                else:
                    break

            print(f"  [행사수집] '{keyword}' → {len([e for e in all_events if e['keyword'] == keyword])}건")

        browser.close()

    print(f"  [행사수집] 총 {len(all_events)}건 (중복 제거)")
    return all_events


def collect_and_save(keywords=None, max_pages=2) -> Path:
    """수집 + JSON 저장."""
    events = collect_events(keywords=keywords, max_pages=max_pages)

    out_dir = Path("data/collected")
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    out_path = out_dir / f"{today}_events.json"

    out_path.write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  [행사수집] 저장: {out_path} ({len(events)}건)")
    return out_path


# ── 상세 정보 수집 (글 기획 시 호출) ──

DETAIL_JS = r"""() => {
    const results = {};

    const dts = document.querySelectorAll('dt');
    dts.forEach(dt => {
        const label = dt.textContent.trim();
        const dd = dt.nextElementSibling;
        if (dd) {
            results[label] = dd.textContent.trim().substring(0, 200);
        }
    });

    const links = document.querySelectorAll('a');
    links.forEach(a => {
        const text = a.textContent.trim();
        if (text === '홈페이지') {
            results['homepage_url'] = a.href;
        }
    });

    const allText = document.body.innerText;
    const lines = allText.split('\n').filter(l => l.trim().length > 10 && l.trim().length < 300);
    const keywords = ['축제', '프로그램', '공연', '체험', '마켓', '푸드트럭', '박람회', '무료', '입장'];
    const matched = lines.filter(l => keywords.some(kw => l.includes(kw)));
    results['description'] = matched.slice(0, 5).join(' | ');

    return results;
}"""


FULL_DESC_JS = r"""() => {
    // "더보기" 버튼 클릭
    const moreBtn = document.querySelector('a.cm_txt_more, a._more_btn, [class*=more]');
    if (moreBtn) moreBtn.click();

    const result = {};

    // 홈페이지 URL
    const links = document.querySelectorAll('a');
    links.forEach(a => {
        if (a.textContent.trim() === '홈페이지') result.homepage_url = a.href;
    });

    // 축제 설명 전체 (더보기 클릭 후)
    const allText = document.body.innerText;
    const lines = allText.split('\n').filter(l => l.trim().length > 20);
    // 축제 관련 긴 텍스트 찾기
    const descLines = lines.filter(l =>
        l.includes('축제') || l.includes('행사') || l.includes('공연') ||
        l.includes('체험') || l.includes('마켓') || l.includes('프로그램') ||
        l.includes('호수') || l.includes('벚꽃') || l.includes('유채') ||
        l.includes('박람') || l.includes('페스') || l.length > 50
    );
    result.description = descLines.slice(0, 5).join('\n');

    return result;
}"""


def fetch_event_detail(event_name: str) -> dict:
    """특정 행사의 상세 정보를 수집.

    1. 네이버 상세: 더보기 클릭 → 행사소개 전체
    2. 홈페이지: 프로그램 정보 (가능하면)

    Returns:
        {"description": "축제 소개...", "homepage_url": "...", "homepage_program": "..."}
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        result = {}

        # 1. 네이버 상세 — 더보기 클릭해서 전체 설명
        try:
            page.goto(
                f"https://search.naver.com/search.naver?query={event_name}",
                timeout=10000,
            )
            page.wait_for_timeout(2000)

            # 더보기 버튼 클릭
            more_btn = page.locator("a._more_btn, a.cm_txt_more, [class*='_more']").first
            if more_btn.is_visible(timeout=1000):
                more_btn.click()
                page.wait_for_timeout(1000)

            detail = page.evaluate(FULL_DESC_JS)
            result["description"] = detail.get("description", "")
            result["homepage_url"] = detail.get("homepage_url", "")
        except Exception:
            pass

        # 2. 홈페이지 — 프로그램 정보 (가능하면)
        homepage_url = result.get("homepage_url", "")
        if homepage_url:
            try:
                page.goto(homepage_url, timeout=10000)
                page.wait_for_timeout(2000)
                text = page.evaluate("() => document.body.innerText")

                lines = text.split("\n")
                program_lines = []
                stop_kw = ["개인정보", "이메일무단", "저작권", "만족하시나요", "담당부서"]
                start_kw = ["축제내용", "행사 취지", "행사내용", "주요 프로그램", "○ 축제",
                            "행사 개요", "세부 행사", "공연 일정"]

                # 시작 위치 찾기
                start_idx = -1
                for idx, line in enumerate(lines):
                    if any(kw in line for kw in start_kw):
                        start_idx = idx
                        break

                if start_idx >= 0:
                    for line in lines[start_idx:]:
                        l = line.strip()
                        if any(s in l for s in stop_kw):
                            break
                        if l and len(l) > 3:
                            program_lines.append(l)
                        if len(program_lines) > 25:
                            break

                    # 메뉴성이면 버림
                    if program_lines:
                        short = sum(1 for l in program_lines if len(l) < 10)
                        if short > len(program_lines) * 0.5:
                            program_lines = []

                if program_lines:
                    result["homepage_program"] = "\n".join(program_lines)[:1000]
            except Exception:
                pass

        browser.close()

    return result


if __name__ == "__main__":
    collect_and_save()
