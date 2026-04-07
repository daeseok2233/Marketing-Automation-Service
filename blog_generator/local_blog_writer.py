"""블로그 글 생성 — 마크클라우드 서비스 홍보."""

import csv
import json
import re
from pathlib import Path
from datetime import datetime
from model import generate

IMAGE_CSV_PATH = Path("data/image/image_list.csv")


def _load_blog_images() -> list[dict]:
    """블로그에 삽입 가능한 이미지 목록을 CSV에서 로드."""
    images = []
    if IMAGE_CSV_PATH.exists():
        with open(IMAGE_CSV_PATH, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("블로그삽입", "").strip() == "O":
                    images.append({
                        "filename": row.get("이미지이름", ""),
                        "path": row.get("이미지경로", ""),
                        "link": row.get("링크주소", ""),
                        "desc": row.get("설명", ""),
                    })
    return images


def _load_image_layout(template_name: str) -> dict:
    tpl_path = Path(f"data/templates/{template_name}.json")
    if tpl_path.exists():
        data = json.loads(tpl_path.read_text(encoding="utf-8"))
        return data.get("image_layout", {})
    return {}


def _build_image_prompt(images: list[dict], layout: dict) -> str:
    """이미지 선택 가이드 (간결 버전)."""
    lines = ["## 이미지"]
    for img in images:
        lines.append(f"- {img['filename']}: {img['desc'][:40]}")
    lines.append("")
    lines.append("태그: [이미지: 파일명.png] / 같은 이미지 2번 쓰지 말 것")
    return "\n".join(lines)


def _get_random_tone() -> dict:
    """tones.json에서 랜덤 톤을 선택."""
    import random
    tones_path = Path("data/service_data/tones.json")
    if tones_path.exists():
        data = json.loads(tones_path.read_text(encoding="utf-8"))
        tones = data.get("tones", [])
        if tones:
            return random.choice(tones)
    return {"key": "friendly", "name": "기본", "instruction": "친근하고 실용적인 톤으로 작성하세요."}


def _build_system_prompt(tone: dict = None) -> str:
    """시스템 프롬프트 (간결 버전)."""
    if tone is None:
        tone = _get_random_tone()

    return f"""마크클라우드(상표·디자인·특허 출원) 블로그 작성자.

## 톤: {tone['name']}
{tone['instruction']}

## 금지
- 허구 브랜드/사례/통계 금지
- 과대광고("1위","최고") 금지
- 뉴스 제목 그대로 복사 금지
- 검색량 수치 본문 포함 금지
- 글자수/메타 정보 언급 금지
- 제목 과장 금지 ("심장이 덜컥", "충격", "경악" 등 자극적 표현 금지)

## 스타일
- 짧은 문장, 줄바꿈. ✔ 👉 사용
- **굵은 블록** 강조. ## 소제목
- 1200~1500자 (1500자 절대 초과 금지!)
- 해시태그 20+개
- 번호 목록(1. 2.) 금지 → ## 소제목으로 구분
- 제목은 30자 이내, 간결하게

## 서비스
- 마크픽: 출원 대행, 대행비 10만원 (정상특허법률사무소)
- 마크뷰: AI 상표 검색 (유사발음·이미지, 국내유일)
- 마크클라우드: 통합 IP 관리"""


def _build_user_prompt(template_name, region, region_short, business, business_desc,
                       angle, keywords, topic, image_guide) -> str:
    """유저 프롬프트 (간결 버전)."""

    # 템플릿 구조 로드
    tpl_path = Path(f"data/templates/{template_name}.json")
    tpl_data = {}
    if tpl_path.exists():
        tpl_data = json.loads(tpl_path.read_text(encoding="utf-8"))

    is_local = tpl_data.get("is_local", False)
    prompt_lines = tpl_data.get("prompt_structure", [])

    # prompt_structure → 문자열
    structure_text = "\n".join(prompt_lines)
    structure_text = structure_text.replace("{region}", region or "")
    structure_text = structure_text.replace("{region_short}", region_short or "")

    # 주제 방향 (제목은 LLM이 레퍼런스 보고 직접 결정)
    if is_local:
        subject = f"{region} {business} 관련 상표·디자인·특허 출원"
    else:
        subject = f"{business} 관련 상표 출원 콘텐츠"

    kw_str = ", ".join(keywords) if keywords else ""
    ref_news = topic.get("ref_news", "")
    ref_blogs = topic.get("ref_blogs", "")
    ref_trending = topic.get("ref_trending", "")

    # 레퍼런스 (있는 것만)
    ref_parts = []
    if ref_trending:
        ref_parts.append(f"실시간 트렌드:\n{ref_trending}")
    if ref_news:
        ref_parts.append(f"뉴스:\n{ref_news}")
    if ref_blogs:
        ref_parts.append(f"경쟁 블로그:\n{ref_blogs}")
    ref_section = "\n\n".join(ref_parts) if ref_parts else "없음"

    return f"""주제 방향: {subject}
앵글: {angle}
키워드: {kw_str}

## 참고 데이터 (이 데이터를 기반으로 제목과 본문을 작성)
{ref_section}

{image_guide}

## 본문 구조 (이 순서대로)
{structure_text}

## 출력 (반드시 지킬 것)
제목: [참고 데이터를 기반으로 제목 작성. 제목과 본문 내용이 반드시 일치해야 함]
메타디스크립션: [150자]

[본문 1500~2000자. 제목에서 약속한 내용을 본문에서 다룰 것]"""


def write_local_blog(topic: dict, template_name: str = "local_trend") -> dict:
    """블로그 글 1개를 생성한다."""
    region = topic.get("region", "")
    business = topic.get("business", "")
    business_desc = topic.get("business_desc", business)
    angle = topic.get("angle", "상표 출원 필요성")
    keywords = topic.get("keywords", [])

    # 지역 단축명
    parts = region.split() if region else []
    ambiguous = ["서구", "북구", "남구", "중구", "동구"]
    if len(parts) == 2 and parts[-1] in ambiguous:
        region_short = region
    elif parts:
        region_short = parts[-1]
    else:
        region_short = ""

    # 이미지 가이드
    blog_images = _load_blog_images()
    image_layout = _load_image_layout(template_name)
    image_guide = _build_image_prompt(blog_images, image_layout)

    # 프롬프트 생성
    prompt = _build_user_prompt(
        template_name=template_name,
        region=region, region_short=region_short,
        business=business, business_desc=business_desc,
        angle=angle, keywords=keywords,
        topic=topic, image_guide=image_guide,
    )

    # 톤 선택 + LLM 호출
    tone = _get_random_tone()
    system_prompt = _build_system_prompt(tone)
    print(f"  톤: {tone['name']}")
    result = generate(prompt, system=system_prompt, max_tokens=8192)
    raw = result["text"]

    # 파싱
    title = ""
    meta = ""
    body = raw
    lines = raw.split("\n")
    body_start = 0

    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("제목:"):
            title = s.split(":", 1)[1].strip().strip("[]\"")
            body_start = i + 1
        elif "메타디스크립션:" in s or "메타 디스크립션:" in s:
            meta = s.split(":", 1)[1].strip().strip("[]\"")
            body_start = i + 1

    if body_start > 0:
        body = "\n".join(lines[body_start:]).strip()

    # 후처리
    body = re.sub(r"\(?\s*(?:총|약)\s*\d{3,5}\s*(?:글자|자|단어|words?)\s*\)?\.?\s*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"(?:이 글은|위 글은|본문은).*?(?:글자|자로|단어로).*?(?:작성|구성|완성).*", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body).rstrip()

    # 끊긴 마지막 줄 제거
    body_lines = body.split("\n")
    while body_lines:
        last = body_lines[-1].strip()
        if last and len(last) <= 3 and not last.startswith("#") and not last.startswith("["):
            body_lines.pop()
        else:
            break
    body = "\n".join(body_lines).rstrip()

    # 제목 폴백
    if not title:
        for line in lines:
            s = line.strip()
            if s.startswith("# ") and not s.startswith("## "):
                title = s[2:].strip("* ")
                break
        if not title:
            title = f"{region_short} {business_desc}, 상표 출원이 필요한 이유"

    # 이미지 태그 치환
    image_path_map = {img["filename"]: img["path"] for img in blog_images}
    body = _resolve_image_tags(body, image_path_map)

    # 썸네일 생성
    from blog_generator.thumbnail_maker import make_thumbnail, upload_thumbnail_imgur

    if template_name in ("compare", "beginner", "howto", "faq", "checklist",
                          "column", "myth", "warning", "info", "event",
                          "dispute_report", "newsjacking"):
        thumb_main = title if title else template_name
        thumb_sub1 = ""
        thumb_sub2 = ""
    else:
        thumb_main = f"{region_short} 상표·특허 출원"
        thumb_sub1 = f"{region_short}에서 많이 하는 사업 유형"
        thumb_sub2 = "상표·디자인·특허 출원이 중요한 이유"

    thumb_path = make_thumbnail(
        main_title=thumb_main,
        sub_title_1=thumb_sub1,
        sub_title_2=thumb_sub2,
        region=region,
        output_name=f"thumb_{region.replace(' ', '_')}_{re.sub(r'[/\\\\|:*?\"<>]', '_', business)}.png",
    )
    thumb_url = upload_thumbnail_imgur(thumb_path)

    if thumb_url:
        body = re.sub(r"\[썸네일 이미지[^\]]*\]\n?", "", body)
        body = f"[썸네일 이미지: IMGUR:{thumb_url}]\n\n{body.lstrip()}"

    return {
        "title": title,
        "meta_description": meta,
        "body": body,
        "region": region,
        "business": business,
        "angle": angle,
        "tone": tone.get("name", ""),
        "model_info": {"model": result["model"], "provider": result["provider"]},
    }


def _resolve_image_tags(body: str, path_map: dict) -> str:
    """[이미지: 파일명.png] → [서비스 이미지: 경로]."""

    def replacer(match):
        filename = match.group(1).strip()
        if filename in path_map:
            return f"[서비스 이미지: {path_map[filename]}]"
        return match.group(0)

    body = re.sub(r"\[이미지:\s*([^\]]+)\]", replacer, body)

    remaining_images = list(path_map.values())
    img_idx = [0]

    def fallback_replacer(match):
        tag = match.group(0).strip()
        if tag in ("[이미지]", "[서비스 이미지]", "[CTA 이미지]"):
            if img_idx[0] < len(remaining_images):
                path = remaining_images[img_idx[0]]
                img_idx[0] += 1
                return f"[서비스 이미지: {path}]"
        return tag

    body = re.sub(r"\[(이미지|서비스 이미지|CTA 이미지)\]", fallback_replacer, body)
    return body
