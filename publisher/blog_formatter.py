"""LLM 마크다운 → 네이버 블로그 발행용 구조화 포맷 변환."""

import csv
import json
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
    blog_structure = load_blog_structure(template_name) if template_name else []
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


def _apply_blog_structure(commands: list[dict], structure: list[dict]) -> list[dict]:
    """blog_structure 기반으로 독립 볼드 문장을 인용구로 변환.

    규칙: 한 줄이 bold_text만으로 이루어진 경우 → 인용구
    (문장 중간의 볼드는 그대로 볼드로 유지)
    구분선은 사용하지 않음 (기존 블로그 패턴)
    """
    quote_styles = [s.get("style", 3) for s in structure if s["type"] == "quote"]
    if not quote_styles:
        return commands

    # 독립 볼드 줄 감지: bold_text 다음에 바로 newline이 오는 경우
    result = []
    quote_idx = 0
    i = 0

    while i < len(commands):
        cmd = commands[i]

        if cmd["type"] == "divider":
            i += 1
            continue

        # bold_text + newline = 독립 볼드 줄 → 인용구로 변환
        if cmd["type"] == "bold_text":
            # 다음 명령이 newline이면 독립 줄
            next_cmd = commands[i + 1] if i + 1 < len(commands) else {}
            # 이전 명령이 text가 아니면 독립 줄 (문장 중간 볼드가 아님)
            prev_cmd = commands[i - 1] if i > 0 else {}

            is_standalone = (
                next_cmd.get("type") in ("newline", "blank_line", None)
                and prev_cmd.get("type") in ("newline", "blank_line", "quote", "image", "heading", None)
            )

            if is_standalone:
                style = quote_styles[quote_idx % len(quote_styles)]
                result.append({"type": "quote", "style": style, "text": cmd["text"]})
                quote_idx += 1
                i += 1
                continue

        result.append(cmd)
        i += 1

    return result


def load_blog_structure(template_name: str) -> list[dict]:
    """템플릿 JSON에서 blog_structure를 로드."""
    tpl_path = Path(f"data/templates/{template_name}.json")
    if tpl_path.exists():
        data = json.loads(tpl_path.read_text(encoding="utf-8"))
        return data.get("blog_structure", [])
    return []


def print_commands(commands: list[dict]):
    """디버깅용 — 명령 리스트 출력."""
    for i, cmd in enumerate(commands):
        t = cmd["type"]
        if t == "heading":
            print(f"  {i:3d} [H {cmd['size']}pt] {cmd['text'][:50]}")
        elif t == "text":
            print(f"  {i:3d} [TEXT    ] {cmd['text'][:50]}")
        elif t == "bold_text":
            print(f"  {i:3d} [BOLD    ] {cmd['text'][:50]}")
        elif t == "blank_line":
            print(f"  {i:3d} [BLANK   ]")
        elif t == "newline":
            print(f"  {i:3d} [ENTER   ]")
        elif t == "image":
            link = f" → {cmd['link']}" if cmd["link"] else ""
            print(f"  {i:3d} [IMAGE   ] {Path(cmd['path']).name}{link}")
        elif t == "hashtags":
            print(f"  {i:3d} [TAGS    ] {cmd['text'][:50]}")
