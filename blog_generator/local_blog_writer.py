"""지역 블로그 글 생성 — 마크클라우드 실제 스타일."""

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
    """템플릿에서 image_layout을 로드."""
    tpl_path = Path(f"data/templates/{template_name}.json")
    if tpl_path.exists():
        data = json.loads(tpl_path.read_text(encoding="utf-8"))
        return data.get("image_layout", {})
    return {}


def _build_image_prompt(images: list[dict], layout: dict) -> str:
    """LLM에게 보여줄 이미지 선택 가이드를 생성."""
    lines = ["## 사용 가능한 이미지 목록 (블로그삽입=O인 것만)"]
    for img in images:
        link_info = f" (링크: {img['link']})" if img["link"] else ""
        lines.append(f"- {img['filename']}: {img['desc']}{link_info}")

    lines.append("")
    lines.append("## 이미지 배치 규칙 (이 순서대로 이미지를 넣으세요)")
    layout_items = layout.get("layout", [])
    for i, item in enumerate(layout_items):
        if item.get("fixed"):
            lines.append(f"{i+1}. [{item['position']}] → {item['rule']} (고정)")
        else:
            lines.append(f"{i+1}. [{item['position']}] → {item['rule']} ← 위 목록에서 적절한 이미지 파일명을 골라주세요")

    lines.append("")
    lines.append("## 이미지 태그 작성 방법")
    lines.append("- 썸네일: [썸네일 이미지] ← 코드가 자동 처리하니 그대로 쓰세요")
    lines.append("- 나머지: [이미지: 파일명.png] ← 위 목록에서 골라서 파일명을 정확히 적으세요")
    lines.append("- 예시: [이미지: image_mark_pick_3.png]")
    lines.append("- 같은 이미지를 2번 쓰지 마세요. 글마다 다른 조합으로 골라주세요.")

    return "\n".join(lines)


SYSTEM_PROMPT = """당신은 마크클라우드(상표·디자인·특허 출원 서비스)의 전문 블로그 작성자입니다.

## ⚠️ 절대 금지
- 실존하지 않는 브랜드명, 사례, 소송, 통계 만들어내기 금지
- 레퍼런스에 없는 뉴스 인용 금지
- 상표와 무관한 내용 (날씨, 맛집 추천 등) 금지
- 과대광고 표현 금지: "1위", "최고", "독보적", "압도적", "유일무이" 등
- 서비스 소개는 담백하게 기능과 가격 중심으로. 과장하지 말 것
- 글자수, 단어수, 분량 언급 절대 금지 (예: "총 2500자", "약 3000자로 작성", "(2888글자)" 등)
- 글 마지막에 메타 정보 넣지 말 것 (글자수, 작성 방법, 프롬프트 관련 내용 등)

## 글쓰기 스타일
- 짧은 문장 (최대 25자), 문장마다 줄바꿈
- ✔ 👉 기호 적극 사용
- 구어체와 문어체 적절 혼합 (도입부는 구어체, 분석은 전문적)
- 핵심 메시지는 **굵은 글씨 블록**으로 강조
- 소제목은 ## (H2) 사용
- 본문 길이: **2000~2500자** (2500자 초과 절대 금지)
- 해시태그 20개 이상 (지역명 포함)
- ⚠️ 번호 목록(1. 2. 3.) 사용 금지. 업종 구분은 ## 소제목으로

## 서비스 정보
- 마크픽: 상표·디자인·특허 출원 대행 (정상특허법률사무소, 순수 대행비 10만원)
- 마크뷰: AI 기반 상표 검색 (이미지·유사발음 검색, 국내 유일 AI 이미지 검색)
- 마크클라우드: 통합 IP 관리 플랫폼

## 참고: 실제 블로그 예시 (이 톤과 구조를 따라하세요)
---
[썸네일 이미지]

청라는 인천 서구를 대표하는 신도시로,
같은 인천 송도와는 전혀 다른 성격의
사업 구조를 가지고 있습니다.

**청라는 '기술 도시'가 아니라
'소비형·생활형 사업이 밀집된 신도시 상권'**입니다.

[이미지: image_mark_pick_2.png]

## 청라에서 많이 하는 대표적인 사업 유형

1. 병원·의원·피부과·치과·한의원
이 업종의 핵심 자산은
**의료 기술보다 병원 이름과 브랜드 인지도**입니다.

## 마크뷰(MarkView) – 출원 전 필수 단계

✔ AI 기반 선행상표 조사
✔ 업종별 유사 상표 구조 비교

[이미지: image_mark_view_1.png]

## 마크픽(MarkPick) – 조사 + 출원을 한 번에

**👉 순수 대행비용 10만원**

[이미지: image_mark_pick_4.png]

## 블로그 보고 오면 1만원 할인

"마크뷰 블로그 보고 왔습니다"
라고 말씀해주시면
1만원 추가 할인이 적용됩니다.

[이미지: image_mark_pick_coupon.png]
---"""


def _build_user_prompt(template_name, region, region_short, business, business_desc,
                       angle, keywords, topic, image_guide) -> str:
    """템플릿 JSON의 prompt_structure를 읽어서 유저 프롬프트를 자동 생성."""
    import json as _json

    # 템플릿 JSON 로드
    tpl_path = Path(f"data/templates/{template_name}.json")
    tpl_data = {}
    if tpl_path.exists():
        tpl_data = _json.loads(tpl_path.read_text(encoding="utf-8"))

    is_local = tpl_data.get("is_local", False)
    prompt_lines = tpl_data.get("prompt_structure", [])

    # prompt_structure → 문자열, {region} 치환
    structure_text = "\n".join(prompt_lines)
    structure_text = structure_text.replace("{region}", region or "")
    structure_text = structure_text.replace("{region_short}", region_short or "")

    # 주제
    if is_local:
        subject = f"{region}에서 많이 하는 사업 유형과 상표·디자인·특허 출원이 중요한 이유"
    else:
        example_titles = tpl_data.get("example_titles", ["상표 출원 가이드"])
        subject = topic.get("title_idea", example_titles[0])

    kw_str = ", ".join(keywords) if keywords else ""
    ref_news = topic.get("ref_news", "없음")
    ref_blogs = topic.get("ref_blogs", "없음")

    return f"""## 주제
{subject}

## 트렌드 앵글: {angle}

## SEO 키워드
{kw_str}

## 레퍼런스 (이 정보만 인용 가능)
### 관련 뉴스
{ref_news}

### 경쟁사 블로그
{ref_blogs}

{image_guide}

## ★ 반드시 따라야 할 본문 구조 — 이 구조 정확히 따를 것

{structure_text}

## 출력 형식
제목: [포스팅 제목]
메타디스크립션: [150자 이내]

[본문 2000~2500자 — 2500자 초과 절대 금지]"""



def write_local_blog(topic: dict, template_name: str = "local_trend") -> dict:
    """지역 블로그 1개를 생성한다."""
    region = topic["region"]
    business = topic["business"]
    business_desc = topic.get("business_desc", business)
    angle = topic.get("angle", "상표 출원 필요성")
    hook = topic.get("hook", "브랜드 보호가 필요한 이유")
    keywords = topic.get("keywords", [])
    ambiguous = ["서구", "북구", "남구", "중구", "동구"]
    parts = region.split() if region else []
    if len(parts) == 2 and parts[-1] in ambiguous:
        region_short = region
    elif parts:
        region_short = parts[-1]
    else:
        region_short = ""

    # CSV에서 블로그 삽입 가능 이미지 로드
    blog_images = _load_blog_images()
    # 템플릿에서 이미지 배치 규칙 로드
    image_layout = _load_image_layout(template_name)
    # LLM용 이미지 가이드 생성
    image_guide = _build_image_prompt(blog_images, image_layout)

    prompt = _build_user_prompt(
        template_name=template_name,
        region=region, region_short=region_short,
        business=business, business_desc=business_desc,
        angle=angle, keywords=keywords,
        topic=topic, image_guide=image_guide,
    )

    result = generate(prompt, system=SYSTEM_PROMPT, max_tokens=8192)
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

    # 불필요한 메타 텍스트 제거
    # "총 2888글자", "(약 2500자)", "이 글은 ~자로 작성" 등
    body = re.sub(r"\(?\s*(?:총|약)\s*\d{3,5}\s*(?:글자|자|단어|words?)\s*\)?\.?\s*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"(?:이 글은|위 글은|본문은).*?(?:글자|자로|단어로).*?(?:작성|구성|완성).*", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body)  # 빈줄 정리
    body = body.rstrip()

    # 끊긴 마지막 줄 제거 (1~3글자로 끝나는 미완성 문장)
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

    # [이미지: 파일명.png] → [서비스 이미지: 경로] 변환
    image_path_map = {img["filename"]: img["path"] for img in blog_images}
    body = _resolve_image_tags(body, image_path_map)

    # 썸네일 생성 — 템플릿에 따라 다르게
    from blog_generator.thumbnail_maker import make_thumbnail, upload_thumbnail_imgur
    if template_name in ("compare", "beginner", "howto", "faq", "checklist",
                          "column", "myth", "warning", "info", "event",
                          "dispute_report"):
        # 비지역 템플릿 — 제목을 자연스럽게 2줄로 분리
        thumb_main = title if title else template_name
        thumb_sub1 = ""
        thumb_sub2 = ""
    else:
        # 지역 템플릿 (local_trend, local_issue, local_event)
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

    # 썸네일 최상단 강제 삽입
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
        "model_info": {"model": result["model"], "provider": result["provider"]},
    }


def _resolve_image_tags(body: str, path_map: dict) -> str:
    """[이미지: 파일명.png] 태그를 [서비스 이미지: 경로]로 변환."""

    def replacer(match):
        filename = match.group(1).strip()
        if filename in path_map:
            return f"[서비스 이미지: {path_map[filename]}]"
        # 파일명이 매칭 안 되면 그대로 유지
        return match.group(0)

    # [이미지: filename.png] 패턴
    body = re.sub(r"\[이미지:\s*([^\]]+)\]", replacer, body)

    # 아직 변환 안 된 [이미지], [서비스 이미지], [CTA 이미지] 태그 처리
    # (LLM이 태그를 안 쓰고 그냥 [이미지]만 쓴 경우 폴백)
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
