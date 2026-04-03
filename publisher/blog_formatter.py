"""LLM 마크다운 → 네이버 블로그 발행용 구조화 포맷 변환."""

import csv
import re
from pathlib import Path

IMAGE_CSV_PATH = Path("data/image/image_list.csv")


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


def markdown_to_commands(body: str, template_name: str = "") -> list[dict]:
    """마크다운 본문을 Playwright 명령 리스트로 변환한다.

    각 명령:
        {"type": "heading", "text": "...", "size": 24}
        {"type": "text", "text": "...", "bold": False}
        {"type": "bold_text", "text": "..."}
        {"type": "blank_line"}
        {"type": "image", "path": "...", "link": ""}
        {"type": "hashtags", "text": "#태그1 #태그2"}
    """
    image_links = _load_image_links()
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
                # 로컬 썸네일 파일로 매핑
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

            # 로컬 이미지
            filename = Path(img_path).name
            link = image_links.get(filename, "")
            commands.append({
                "type": "image",
                "path": img_path,
                "link": link,
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
        # 여는 **만 있고 닫는 **가 없으면 제거
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

        # 볼드가 열린 채로 줄이 끝나면 다음 줄에서 이어감
        in_bold = current_bold

        if line_commands:
            commands.extend(line_commands)
        commands.append({"type": "newline"})

    return commands


