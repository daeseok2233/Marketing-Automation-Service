"""Notion에 생성된 블로그를 업로드한다."""

import os
import re
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DB_ID = os.environ.get("NOTION_DATABASE_ID", "")

# GitHub raw URL 베이스 (이미지 호스팅)
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/daeseok2233/Marketing-Automation-Service/daeseok"
IMAGE_CSV_PATH = Path("data/image/image_list.csv")


def _load_image_links() -> dict:
    """image_list.csv에서 이미지명→링크 매핑."""
    import csv
    links = {}
    if IMAGE_CSV_PATH.exists():
        with open(IMAGE_CSV_PATH, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                name = row.get("이미지이름", "")
                link = row.get("링크주소", "").strip()
                if name and link:
                    links[name] = link
    return links
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def _rich_text(content: str, bold: bool = False) -> dict:
    rt = {"type": "text", "text": {"content": content[:2000]}}
    if bold:
        rt["annotations"] = {"bold": True}
    return rt


def _parse_bold(text: str) -> list[dict]:
    """**bold** 마크다운을 Notion rich_text로 변환."""
    parts = []
    segments = re.split(r"\*\*(.*?)\*\*", text)
    for i, seg in enumerate(segments):
        if not seg:
            continue
        if i % 2 == 1:
            parts.append(_rich_text(seg, bold=True))
        else:
            parts.append(_rich_text(seg))
    return parts or [_rich_text(text)]


_IMAGE_LINKS = None

def _get_image_links():
    global _IMAGE_LINKS
    if _IMAGE_LINKS is None:
        _IMAGE_LINKS = _load_image_links()
    return _IMAGE_LINKS


def md_to_blocks(md_text: str) -> list[dict]:
    """마크다운 텍스트를 Notion 블록 리스트로 변환."""
    blocks = []
    lines = md_text.strip().split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 이미지 태그 감지: [썸네일 이미지: path], [서비스 이미지: path], [CTA 이미지: path]
        img_match = re.match(r"\[(썸네일 이미지|서비스 이미지|CTA 이미지):\s*(.+?)\]", stripped)
        if img_match:
            img_type = img_match.group(1)
            img_path = img_match.group(2).strip()
            # Imgur URL은 그대로, 로컬 경로는 GitHub raw URL로 변환
            if img_path.startswith("IMGUR:"):
                img_url = img_path.replace("IMGUR:", "")
            elif img_path.startswith("http"):
                img_url = img_path
            else:
                img_url = f"{GITHUB_RAW_BASE}/{img_path}"
            blocks.append({
                "object": "block",
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {"url": img_url},
                },
            })
            # 이미지에 링크가 있으면 아래에 표시
            img_links = _get_image_links()
            img_filename = Path(img_path).name
            link_url = img_links.get(img_filename, "")
            if link_url:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{
                        "type": "text",
                        "text": {"content": f"↑ 이미지 링크: {link_url}"},
                        "annotations": {"color": "gray"},
                    }]},
                })
            i += 1
            continue

        # 처리 안 된 [이미지] 태그도 처리
        if stripped in ("[썸네일 이미지]", "[서비스 이미지]", "[CTA 이미지]", "[이미지]"):
            # 이미지 경로 없이 태그만 있는 경우 — 텍스트로 표시
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [_rich_text(stripped)]},
            })
            i += 1
            continue

        # 테이블 감지
        if "|" in stripped and i + 1 < len(lines) and "---" in lines[i + 1]:
            table_lines = [stripped]
            i += 1
            while i < len(lines) and "|" in lines[i].strip():
                if "---" not in lines[i]:
                    table_lines.append(lines[i].strip())
                i += 1

            rows = []
            for tl in table_lines:
                cells = [c.strip() for c in tl.strip("|").split("|")]
                rows.append(cells)

            if rows:
                width = max(len(r) for r in rows)
                children = []
                for row in rows:
                    while len(row) < width:
                        row.append("")
                    children.append({
                        "type": "table_row",
                        "table_row": {
                            "cells": [[_rich_text(c)] for c in row[:width]]
                        },
                    })
                blocks.append({
                    "object": "block",
                    "type": "table",
                    "table": {
                        "table_width": width,
                        "has_column_header": True,
                        "has_row_header": False,
                        "children": children,
                    },
                })
            continue

        # H1
        if stripped.startswith("# ") and not stripped.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": [_rich_text(stripped[2:].strip("* "))]},
            })
        # H2
        elif stripped.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [_rich_text(stripped[3:].strip("* "))]},
            })
        # H3
        elif stripped.startswith("### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [_rich_text(stripped[4:].strip("* "))]},
            })
        # 리스트
        elif stripped.startswith(("* ", "- ")):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _parse_bold(stripped[2:].strip())},
            })
        # 구분선
        elif stripped == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        # 일반 문단
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": _parse_bold(stripped)},
            })

        i += 1

    return blocks


def upload_to_notion(blog_data: dict, template_name: str = "", keywords: str = "") -> str:
    """블로그 데이터를 Notion DB에 페이지로 업로드한다.

    Returns:
        생성된 Notion 페이지 URL
    """
    body = blog_data.get("body", "")
    title = blog_data.get("title", "")
    meta = blog_data.get("meta_description", "")

    # 해시태그 추출 (본문 마지막 줄)
    hashtags = ""
    body_lines = body.strip().split("\n")
    if body_lines and "#" in body_lines[-1] and body_lines[-1].count("#") >= 3:
        hashtags = body_lines[-1].strip()
        body = "\n".join(body_lines[:-1])

    # 제목이 없으면 본문에서 추출
    if not title:
        for line in body_lines:
            s = line.strip()
            if s.startswith("# "):
                title = s[2:].strip("* ")
                break

    blocks = md_to_blocks(body)

    # 페이지 생성 (첫 100블록)
    page_body = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "제목": {"title": [{"text": {"content": title[:2000]}}]},
            "메타설명": {"rich_text": [{"text": {"content": (meta or "")[:2000]}}]},
            "상태": {"select": {"name": "초안"}},
            "해시태그": {"rich_text": [{"text": {"content": hashtags[:2000]}}]},
            "메인키워드": {"rich_text": [{"text": {"content": keywords[:2000]}}]},
            "생성일": {"date": {"start": __import__("datetime").date.today().isoformat()}},
        },
        "children": blocks[:100],
    }

    if template_name:
        page_body["properties"]["템플릿"] = {"select": {"name": template_name}}

    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers=HEADERS, json=page_body, timeout=30,
    )

    if r.status_code != 200:
        print(f"  [Notion] 페이지 생성 실패 ({r.status_code}): {r.text[:300]}")
        return ""

    page_id = r.json()["id"]
    url = r.json().get("url", "")
    print(f"  [Notion] 페이지 생성: {url}")

    # 나머지 블록 추가 (100개씩)
    remaining = blocks[100:]
    for idx in range(0, len(remaining), 100):
        chunk = remaining[idx:idx + 100]
        r2 = requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=HEADERS, json={"children": chunk}, timeout=30,
        )
        if r2.status_code != 200:
            print(f"  [Notion] 블록 추가 실패: {r2.text[:200]}")

    print(f"  [Notion] 총 {len(blocks)}개 블록 업로드 완료")
    return url
