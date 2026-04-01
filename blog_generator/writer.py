"""4단계: 글 생성 — 레퍼런스 + 프롬프트 → model.py → 블로그 본문 + 제목."""

import json
from pathlib import Path
from datetime import datetime

from model import generate


def write_blog(prompt_data: dict) -> dict:
    """LLM을 호출하여 블로그 글을 생성한다.

    Args:
        prompt_data: prompt_builder에서 반환된 dict (system_prompt, user_prompt)

    Returns:
        {
            "title": "포스팅 제목",
            "meta_description": "메타 디스크립션",
            "body": "본문 전체 (마크다운)",
            "model_info": {"model": ..., "provider": ...},
        }
    """
    result = generate(
        prompt=prompt_data["user_prompt"],
        system=prompt_data["system_prompt"],
    )

    raw_text = result["text"]

    # ── 파싱: 제목 / 메타디스크립션 / 본문 분리 ──
    title = ""
    meta = ""
    body = raw_text

    lines = raw_text.split("\n")
    body_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("제목:") or stripped.startswith("제목 :"):
            title = stripped.split(":", 1)[1].strip().strip("[]")
            body_start = i + 1
        elif stripped.startswith("메타디스크립션:") or stripped.startswith("메타 디스크립션:"):
            meta = stripped.split(":", 1)[1].strip().strip("[]")
            body_start = i + 1

    if body_start > 0:
        body = "\n".join(lines[body_start:]).strip()

    output = {
        "title": title,
        "meta_description": meta,
        "body": body,
        "raw_output": raw_text,
        "model_info": {
            "model": result["model"],
            "provider": result["provider"],
        },
    }

    # 중간결과 저장
    _save_intermediate("04_blog", output)

    return output


def _save_intermediate(step: str, data: dict):
    out_dir = Path("data/generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    path = out_dir / f"{today}_{step}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [저장] {path}")
