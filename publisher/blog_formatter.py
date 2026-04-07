"""LLM 마크다운 → 네이버 블로그 발행용 구조화 포맷 변환."""

import csv
import json
import re
from pathlib import Path

IMAGE_CSV_PATH = Path("data/image/image_list.csv")
BLOG_LINKS_PATH = Path("data/image/blog_links.json")


def _load_image_links() -> dict:
    """image_list.csv에서 이미지명→링크 매핑."""
    links = {}
    if IMAGE_CSV_PATH.exists():
        with open(IMAGE_CSV_PATH, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                name = row.get("이미지이름", "")
                link = row.get("링크주소", "").strip()
                if name:
                    links[name] = link
    return links


def _load_blog_links(blog_id: str) -> dict:
    """블로그별 링크 매핑 로드. 기본 링크 → 블로그별 cutt.ly 링크로 치환."""
    if not BLOG_LINKS_PATH.exists() or not blog_id:
        return {}
    data = json.loads(BLOG_LINKS_PATH.read_text(encoding="utf-8"))
    return data.get(blog_id, {})


def _replace_link(link: str, blog_links: dict) -> str:
    """기본 링크를 블로그별 링크로 치환."""
    if not link or not blog_links:
        return link

    # 카카오톡 링크
    if "kakao" in link.lower() or "pf.kakao" in link:
        return blog_links.get("카카오", link)

    # 마크뷰 링크
    if "markview" in link.lower():
        return blog_links.get("마크뷰", link)

    # 마크픽 링크 (markpick 또는 기본 markpick.co.kr)
    if "markpick" in link.lower():
        return blog_links.get("마크픽", link)

    return link


def markdown_to_commands(body: str, template_name: str = "", blog_id: str = "") -> list[dict]:
    """마크다운 본문을 Playwright 명령 리스트로 변환한다.

    Args:
        body: 마크다운 본문
        template_name: 템플릿명
        blog_id: 블로그 ID (블로그별 링크 치환용)
    """
    image_links = _load_image_links()
    blog_links = _load_blog_links(blog_id)
    commands = []
    lines = body.split("\n")
    in_bold = False

    for line in lines:
        stripped = line.strip()

        # ── 빈 줄 ──
        if not stripped:
            commands.append({"type": "blank_line"})
            continue

        # ── 이미지 태그 ──
        img_match = re.match(r"\[(썸네일 이미지|서비스 이미지|CTA 이미지):\s*(.+?)\]", stripped)
        if img_match:
            img_path = img_match.group(2).strip()
            # IMGUR URL → 썸네일
            if img_path.startswith("IMGUR:"):
                thumb_dir = Path("data/generated/thumbnails")
                if thumb_dir.exists():
                    thumbs = sorted(thumb_dir.glob("*.png"),
                                    key=lambda f: f.stat().st_mtime, reverse=True)
                    if thumbs:
                        commands.append({
                            "type": "image",
                            "path": str(thumbs[0]),
                            "link": "",
                        })
                continue
            elif img_path.startswith("http"):
                continue

            # 로컬 이미지 — 블로그별 링크 치환
            filename = Path(img_path).name
            base_link = image_links.get(filename, "")
            final_link = _replace_link(base_link, blog_links)
            commands.append({
                "type": "image",
                "path": img_path,
                "link": final_link,
            })
            continue

        # ── 이미지 링크 가이드 스킵 ──
        if stripped.startswith("↑ 이미지 링크:"):
            continue

        # ── 구분선 ──
        if stripped == "---":
            commands.append({"type": "blank_line"})
            continue

        # ── 해시태그 ──
        if stripped.startswith("#") and stripped.count("#") >= 3 and not stripped.startswith("##"):
            hashtags = stripped.replace("#", " #").strip()
            commands.append({"type": "hashtags", "text": hashtags})
            continue

        # ── H2 소제목 ──
        if stripped.startswith("## "):
            text = stripped[3:].strip().strip("* ")
            commands.append({"type": "blank_line"})
            commands.append({"type": "heading", "text": text, "size": 19})
            commands.append({"type": "blank_line"})
            continue

        # ── H3 소제목 ──
        if stripped.startswith("### "):
            text = stripped[4:].strip().strip("* ")
            commands.append({"type": "blank_line"})
            commands.append({"type": "heading", "text": text, "size": 17})
            commands.append({"type": "blank_line"})
            continue

        # ── H1 ──
        if stripped.startswith("# ") and not stripped.startswith("## "):
            text = stripped[2:].strip().strip("* ")
            commands.append({"type": "blank_line"})
            commands.append({"type": "heading", "text": text, "size": 24})
            commands.append({"type": "blank_line"})
            continue

        # ── 일반 텍스트 (** 볼드 파싱) ──
        parts = re.split(r"(\*\*)", stripped)
        current_bold = in_bold
        line_commands = []

        for part in parts:
            if part == "**":
                current_bold = not current_bold
                continue
            if not part:
                continue
            if current_bold:
                line_commands.append({"type": "bold_text", "text": part})
            else:
                line_commands.append({"type": "text", "text": part})

        in_bold = current_bold

        if line_commands:
            commands.extend(line_commands)
        commands.append({"type": "newline"})

    return commands
