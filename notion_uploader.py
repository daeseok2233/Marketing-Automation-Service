"""노션 데이터베이스 자동 업로드"""
import os, re, requests
from datetime import date


def _rich_text(text: str) -> list:
    """마크다운 인라인 서식(**bold**, *italic*) → Notion rich_text 배열로 변환"""
    parts = []
    # **bold** 또는 *italic* 파싱
    pattern = re.compile(r'\*\*(.+?)\*\*|\*(.+?)\*')
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            parts.append({"type": "text", "text": {"content": text[last:m.start()]}})
        if m.group(1) is not None:  # **bold**
            parts.append({"type": "text", "text": {"content": m.group(1)},
                          "annotations": {"bold": True}})
        else:  # *italic*
            parts.append({"type": "text", "text": {"content": m.group(2)},
                          "annotations": {"italic": True}})
        last = m.end()
    if last < len(text):
        parts.append({"type": "text", "text": {"content": text[last:]}})
    if not parts:
        parts = [{"type": "text", "text": {"content": text}}]
    # Notion rich_text 단일 항목 2000자 제한
    result = []
    for p in parts:
        content = p["text"]["content"]
        for i in range(0, max(len(content), 1), 2000):
            chunk = dict(p)
            chunk["text"] = dict(p["text"])
            chunk["text"]["content"] = content[i:i+2000]
            result.append(chunk)
    return result


def _strip_md(text: str) -> str:
    """소제목 등에서 **마크다운** 기호만 제거한 순수 텍스트 반환"""
    return re.sub(r'\*+', '', text).strip()


def _h2(text: str) -> dict:
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": _strip_md(text)}}]}}

def _bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _rich_text(text[:2000])}}

def _para(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _rich_text(text[:2000])}}

def _image_block(url: str, caption: str = "") -> dict:
    block = {
        "object": "block", "type": "image",
        "image": {"type": "external", "external": {"url": url}},
    }
    if caption:
        block["image"]["caption"] = [{"type": "text", "text": {"content": caption[:2000]}}]
    return block

def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}

def _callout(text: str, emoji: str = "📌") -> dict:
    return {
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": text[:2000]}}],
            "icon": {"type": "emoji", "emoji": emoji},
            "color": "gray_background",
        },
    }

def _link_bullet(label: str, url: str) -> dict:
    return {
        "object": "block", "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [
                {"type": "text", "text": {"content": f"{label}: "}},
                {"type": "text", "text": {"content": url, "link": {"url": url}}},
            ]
        },
    }

class NotionUploader:
    def __init__(self):
        self.token   = os.environ.get("NOTION_TOKEN", "")
        self.db_id   = os.environ.get("NOTION_DATABASE_ID", "")
        self.headers = {
            "Authorization":  f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type":   "application/json",
        }
        if not self.token or not self.db_id:
            raise EnvironmentError("NOTION_TOKEN 또는 NOTION_DATABASE_ID 환경변수가 없습니다")

    def upload(self, post: dict, date_str: str = None) -> str:
        date_str = date_str or date.today().isoformat()
        payload  = self._build(post, date_str)
        res = requests.post(
            "https://api.notion.com/v1/pages",
            headers=self.headers,
            json=payload,
            timeout=15,
        )
        res.raise_for_status()
        page_id = res.json().get("id", "")
        print(f"  [OK] 노션 저장: {post.get('title','?')} [{page_id[:8]}...]")
        return page_id

    def upload_report(self, raw_data: dict, date_str: str = None) -> str:
        """수집 데이터 요약 리포트를 노션에 업로드"""
        date_str = date_str or date.today().isoformat()
        blocks   = self._build_report_blocks(raw_data)
        payload  = {
            "parent": {"database_id": self.db_id},
            "properties": {
                "제목":   {"title": [{"text": {"content": f"[수집리포트] {date_str}"}}]},
                "상태":   {"select": {"name": "리포트"}},
                "생성일": {"date":   {"start": date_str}},
            },
            "children": blocks,
        }
        res = requests.post("https://api.notion.com/v1/pages",
                            headers=self.headers, json=payload, timeout=15)
        res.raise_for_status()
        page_id = res.json().get("id", "")
        print(f"  [OK] 수집리포트 저장: {date_str} [{page_id[:8]}...]")
        return page_id

    def _build_report_blocks(self, raw_data: dict) -> list:
        blocks = []

        # ── 네이버 DataLab ──────────────────────────────────────
        naver = raw_data.get("naver", {})
        blocks.append(_h2("네이버 DataLab 트렌드"))
        if naver:
            sorted_naver = sorted(naver.items(), key=lambda x: x[1].get("avg_ratio", 0), reverse=True)
            for kw, d in sorted_naver:
                avg    = d.get("avg_ratio", 0)
                growth = d.get("growth_rate", 0)
                sign   = "+" if growth >= 0 else ""
                blocks.append(_bullet(f"{kw}  |  평균 {avg:.2f}  |  전주대비 {sign}{growth:.1f}%"))
        else:
            blocks.append(_para("수집 실패 (API 키 확인 필요)"))
        blocks.append(_divider())

        # ── 구글 트렌드 ─────────────────────────────────────────
        google = raw_data.get("google", {})
        blocks.append(_h2("구글 트렌드"))
        if google:
            sorted_google = sorted(google.items(), key=lambda x: x[1].get("avg", 0), reverse=True)
            for kw, d in sorted_google:
                avg    = d.get("avg", 0)
                growth = d.get("growth", 0)
                sign   = "+" if growth >= 0 else ""
                blocks.append(_bullet(f"{kw}  |  관심도 {avg:.1f}  |  증감 {sign}{growth:.1f}%"))
        else:
            blocks.append(_para("수집 실패 또는 데이터 없음 (구글 429 제한 가능)"))
        blocks.append(_divider())

        # ── BigKinds ────────────────────────────────────────────
        bigkinds = raw_data.get("bigkinds", {})
        blocks.append(_h2("빅카인즈 뉴스 분석"))
        if bigkinds:
            blocks.append(_para(f"최근 30일 기사 수: {bigkinds.get('total_articles', 0)}건"))
            for kw, d in bigkinds.get("keyword_growth", {}).items():
                cnt    = d.get("recent_count", 0)
                growth = d.get("growth_pct", 0)
                sign   = "+" if growth >= 0 else ""
                blocks.append(_bullet(f"{kw}  |  최근 {cnt}건  |  전월대비 {sign}{growth:.1f}%"))
            top_words = bigkinds.get("top_related_words", {})
            if top_words:
                words_str = "  ".join(f"{w}({c})" for w, c in list(top_words.items())[:10])
                blocks.append(_para(f"연관 키워드: {words_str}"))
        else:
            blocks.append(_para("수집 실패 — data/bigkinds/*.xlsx 파일 없음"))
        blocks.append(_divider())

        # ── KIPRIS ──────────────────────────────────────────────
        kipris = raw_data.get("kipris", {})
        blocks.append(_h2("KIPRIS 출원 통계"))
        if kipris:
            ytd  = kipris.get("total_applications_ytd", 0)
            year = kipris.get("year", "")
            note = kipris.get("note", "")
            if ytd:
                blocks.append(_para(f"{year}년 상표 출원 건수 (누적): {ytd:,}건"))
            blocks.append(_para(f"연간 기준값: {kipris.get('annual_benchmark', 270000):,}건"))
            if note:
                blocks.append(_para(f"참고: {note}"))
        else:
            blocks.append(_para("수집 실패"))
        blocks.append(_divider())

        # ── 오늘의 뉴스 헤드라인 ────────────────────────────────
        news = raw_data.get("naver_news", {}).get("headlines", [])
        blocks.append(_h2("오늘의 뉴스 헤드라인 (앵글 소스)"))
        if news:
            current_q = None
            for item in news[:20]:
                q = item.get("query", "")
                if q != current_q:
                    blocks.append(_para(f"[{q}]"))
                    current_q = q
                blocks.append(_bullet(item.get("title", "")))
        else:
            blocks.append(_para("수집 실패 또는 결과 없음"))
        blocks.append(_divider())

        # ── 경쟁사 블로그 ────────────────────────────────────────
        competitor = raw_data.get("competitor", {})
        blocks.append(_h2("경쟁사 블로그 상위 노출 제목"))
        titles = competitor.get("sample_titles", [])
        if titles:
            current_query = None
            for item in titles:
                q = item.get("query", "")
                if q != current_query:
                    blocks.append(_para(f"[{q}]"))
                    current_query = q
                blocks.append(_bullet(item.get("title", "")))
        else:
            blocks.append(_para("수집 실패 또는 결과 없음"))

        return blocks

    def _build(self, post: dict, date_str: str) -> dict:
        blocks = []
        images = post.get("images", [])  # [{position, url, alt_text, ...}]

        def _insert_images(position: str):
            for img in images:
                if img.get("position") == position and img.get("url"):
                    blocks.append(_image_block(img["url"], img.get("alt_text", "")))

        def _paras(text: str):
            """줄바꿈 기준으로 분리 후 각각 paragraph 블록으로 추가"""
            for line in text.split("\n"):
                line = line.strip()
                if line:
                    blocks.append(_para(line))

        # ── 본문 렌더링 (구조형: intro + body[sections] + conclusion + cta)
        if isinstance(post.get("body"), list):
            # 도입부
            intro = post.get("intro", "")
            _paras(intro)
            _insert_images("cover")  # 커버 이미지: 도입부 직후

            # 본론 섹션 (H2 소제목 + 내용)
            body_sections = post.get("body", [])
            mid_idx = max(1, len(body_sections) // 2)  # 중간 지점
            for idx, section in enumerate(body_sections):
                if isinstance(section, dict):
                    heading = section.get("heading", "")
                    content = section.get("content", "")
                    if heading:
                        blocks.append(_h2(heading))
                    _paras(content)
                if idx == mid_idx - 1:
                    _insert_images("mid")  # 중간 이미지: 절반 섹션 후

            # 마무리 전 이미지
            _insert_images("outro")

            # 마무리
            conclusion = post.get("conclusion", "")
            _paras(conclusion)

            # CTA
            cta = post.get("cta", "")
            if cta:
                blocks.append(_callout(cta, "💡"))

        else:
            # 구형 flat body 폴백 (하위 호환)
            body = post.get("body", "")
            _insert_images("cover")
            for i in range(0, len(body), 2000):
                blocks.append({
                    "object": "block", "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": body[i:i+2000]}}]},
                })

        # ── 스크린샷 블록 (image-search-demo 템플릿)
        screenshot = post.get("screenshot", {})
        if screenshot:
            blocks.append(_divider())
            blocks.append(_h2("마크뷰 검색 화면"))
            if screenshot.get("success") and screenshot.get("url"):
                blocks.append({
                    "object": "block", "type": "image",
                    "image": {"type": "external", "external": {"url": screenshot["url"]}},
                })
            else:
                msg = screenshot.get("path") or screenshot.get("error", "스크린샷 없음")
                blocks.append(_callout(f"[스크린샷] {msg}", "📷"))

        # ── KIPRIS 브랜드 조회 결과 블록
        kb = post.get("kipris_brand", {})
        if kb and kb.get("found"):
            blocks.append(_divider())
            blocks.append(_h2("KIPRIS 상표 조회 결과"))
            blocks.append(_para(kb.get("summary", "")))
            for item in kb.get("items", []):
                line = (
                    f"{item.get('title','')} | {item.get('goods_class','')}류 | "
                    f"출원일 {item.get('application_date','')} | "
                    f"상태: {item.get('status','')} | "
                    f"출원인: {item.get('applicant','')} | "
                    f"출원번호: {item.get('application_number','')}"
                )
                blocks.append(_bullet(line))

        # ── 참고자료 섹션 (페이지 하단)
        blocks.append(_divider())
        blocks.append(_callout("📋 참고자료 및 데이터 출처", "📋"))

        news_ref  = post.get("news_reference", "")
        news_link = post.get("news_link", "")
        if news_ref:
            if news_link:
                blocks.append(_link_bullet(f"참조 뉴스: {news_ref}", news_link))
            else:
                blocks.append(_bullet(f"참조 뉴스/트렌드: {news_ref}"))

        blocks.append(_h2("수집 데이터 출처"))
        blocks.append(_link_bullet("네이버 DataLab (검색어 트렌드)", "https://datalab.naver.com"))
        blocks.append(_link_bullet("Google Trends", "https://trends.google.com/trends/?geo=KR"))
        blocks.append(_link_bullet("특허청 KIPRIS (상표 출원 통계)", "https://www.kipris.or.kr"))
        blocks.append(_link_bullet("Google News (뉴스 헤드라인)", "https://news.google.com/home?hl=ko&gl=KR&ceid=KR:ko"))

        blocks.append(_h2("법률 근거"))
        blocks.append(_link_bullet("국가법령정보센터 - 상표법", "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=257469"))
        blocks.append(_link_bullet("특허청 공식 사이트", "https://www.kipo.go.kr"))
        blocks.append(_link_bullet("특허로 수수료 안내", "https://www.patent.go.kr/smart/jsp/ka/menu/fee/main/FeeMain01.do"))

        return {
            "parent": {"database_id": self.db_id},
            "properties": {
                "제목":      {"title":     [{"text": {"content": post.get("title", "")}}]},
                "상태":      {"select":    {"name": "검토중"}},
                "서비스":    {"select":    {"name": post.get("service_key","").upper()}},
                "템플릿":    {"select":    {"name": post.get("template_key","info")}},
                "메인키워드":{"rich_text": [{"text": {"content": post.get("main_keyword","")}}]},
                "트렌드점수":{"number":    post.get("trend_score", 0)},
                "해시태그":  {"rich_text": [{"text": {"content": " ".join(f"#{t}" for t in post.get("hashtags",[]))}}]},
                "생성일":    {"date":      {"start": date_str}},
                "메타설명":  {"rich_text": [{"text": {"content": post.get("meta_description","")}}]},
            },
            "children": blocks,
        }
