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


def _load_heading_sizes(template_name: str) -> dict:
    """template structure에서 heading content → size 매핑 로드."""
    if not template_name:
        return {}
    tpl_path = Path(f"data/templates/{template_name}.json")
    if not tpl_path.exists():
        return {}
    data = json.loads(tpl_path.read_text(encoding="utf-8"))
    structure = data.get("structure", [])
    if not structure or not isinstance(structure, list):
        return {}
    sizes = {}
    for item in structure:
        if item.get("type") == "heading" and "content" in item and "size" in item:
            # {region} 등 변수는 제거하고 핵심 텍스트만 키로
            key = item["content"].replace("{region}", "").replace("{region_short}", "").strip()
            sizes[key] = item["size"]
    return sizes


def structure_to_commands(tpl_data: dict, slots: dict, blog_images: list,
                          blog_id: str = "", thumb_url: str = "",
                          region: str = "", region_short: str = "") -> list[dict]:
    """template structure + LLM 슬롯 → Playwright 명령 직접 생성.

    마크다운 중간 단계 없이 structure를 그대로 Playwright 명령으로 변환.
    font size, quote style, divider 등 structure에 정의된 대로 정확히 반영.
    """
    # JSON 직렬화 후 키가 문자열로 바뀌는 문제 대응 (1 → "1")
    slots = {int(k): v for k, v in slots.items()}

    image_links = _load_image_links()
    blog_links = _load_blog_links(blog_id)

    img_list = [img for img in blog_images]
    img_idx = [0]

    def _pick_image():
        if img_idx[0] < len(img_list):
            img = img_list[img_idx[0]]
            img_idx[0] += 1
            return img
        return None

    commands = []
    slot_idx = 0

    for item in tpl_data.get("structure", []):
        t = item.get("type", "")
        content = item.get("content", "")
        content = content.replace("{region}", region or "")
        content = content.replace("{region_short}", region_short or "")

        if t == "blank":
            commands.append({"type": "blank_line"})

        elif t == "divider":
            commands.append({"type": "divider"})

        elif t == "heading":
            size = item.get("size", 19)
            commands.append({"type": "blank_line"})
            commands.append({"type": "heading", "text": content, "size": size})
            commands.append({"type": "blank_line"})

        elif t == "text":
            slot_idx += 1
            text = slots.get(slot_idx, content)
            # 줄바꿈 단위로 분리해서 각각 텍스트 명령으로
            for line in text.split("\n"):
                if line.strip():
                    commands.append({"type": "text", "text": line})
                    commands.append({"type": "newline"})
                else:
                    commands.append({"type": "blank_line"})

        elif t == "quote":
            slot_idx += 1
            text = slots.get(slot_idx, content)
            style = item.get("style", 3)
            commands.append({"type": "quote", "text": text, "style": style})

        elif t == "bold_text":
            slot_idx += 1
            text = slots.get(slot_idx, content)
            commands.append({"type": "bold_text", "text": text})
            commands.append({"type": "newline"})

        elif t == "hashtags":
            slot_idx += 1
            text = slots.get(slot_idx, "")
            if text and not text.startswith("#"):
                text = " ".join(f"#{w.strip().lstrip('#')}" for w in text.split() if w.strip())
            commands.append({"type": "hashtags", "text": text})

        elif t == "image":
            if "썸네일" in content:
                # 썸네일 — 최신 생성된 파일 사용
                thumb_dir = Path("data/generated/thumbnails")
                if thumb_dir.exists():
                    thumbs = sorted(thumb_dir.glob("*.png"),
                                    key=lambda f: f.stat().st_mtime, reverse=True)
                    if thumbs:
                        commands.append({"type": "image", "path": str(thumbs[0]), "link": ""})
            elif "쿠폰" in content or "coupon" in content.lower():
                path = "data/image/event/image_mark_pick_coupon.png"
                filename = Path(path).name
                base_link = image_links.get(filename, "")
                final_link = _replace_link(base_link, blog_links)
                commands.append({"type": "image", "path": path, "link": final_link})
            elif item.get("fixed"):
                # 고정 이미지 (파일명이 content에 있을 수 있음)
                commands.append({"type": "image", "path": content, "link": ""})
            else:
                img = _pick_image()
                if img:
                    base_link = image_links.get(img["filename"], "")
                    final_link = _replace_link(base_link, blog_links)
                    commands.append({"type": "image", "path": img["path"], "link": final_link})

    return commands


def markdown_to_commands(body: str, template_name: str = "", blog_id: str = "") -> list[dict]:
    """마크다운 본문을 Playwright 명령 리스트로 변환한다.

    Args:
        body: 마크다운 본문
        template_name: 템플릿명
        blog_id: 블로그 ID (블로그별 링크 치환용)
    """
    image_links = _load_image_links()
    blog_links = _load_blog_links(blog_id)
    heading_sizes = _load_heading_sizes(template_name)
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
            commands.append({"type": "divider"})
            continue

        # ── 인용문 ──
        if stripped.startswith("> "):
            quote_text = stripped[2:].strip()
            commands.append({"type": "quote", "text": quote_text, "style": 3})
            continue

        # ── 해시태그 ──
        if stripped.startswith("#") and stripped.count("#") >= 3 and not stripped.startswith("##"):
            hashtags = stripped.replace("#", " #").strip()
            commands.append({"type": "hashtags", "text": hashtags})
            continue

        # ── H2 소제목 ──
        if stripped.startswith("## "):
            text = stripped[3:].strip().strip("* ")
            # template structure에서 size 가져오기 (매칭되는 키 찾기)
            size = 19  # 기본값
            for key, sz in heading_sizes.items():
                if key and key in text:
                    size = sz
                    break
            commands.append({"type": "blank_line"})
            commands.append({"type": "heading", "text": text, "size": size})
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
