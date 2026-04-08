"""블로그 글 생성 — 슬롯 방식.

template의 structure 배열에서 {} 빈칸을 추출하고,
LLM은 텍스트만 채움. 레이아웃/이미지/폰트는 structure가 제어.
"""

import csv
import json
import re
from pathlib import Path
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


def _load_service_info() -> str:
    """services.json에서 서비스 정보를 읽어 텍스트로 변환."""
    svc_path = Path("data/service_data/services.json")
    if not svc_path.exists():
        return "- 마크픽, 마크뷰, 마크클라우드"
    data = json.loads(svc_path.read_text(encoding="utf-8"))
    lines = []
    for _, svc in data.get("services", {}).items():
        features = ", ".join(svc.get("features", [])[:3])
        lines.append(f"- {svc['name']} ({svc['type']}): {features}")
    return "\n".join(lines)


SERVICE_INFO = _load_service_info()


def _build_prompt(tpl_data: dict, region: str, region_short: str,
                  business: str, angle: str, keywords: list, topic: dict) -> str:
    """프롬프트 하나로 생성 — 역할 + 참고 데이터 + 템플릿 빈칸."""

    # 참고 데이터
    ref_parts = []
    if topic.get("ref_trending"):
        ref_parts.append(f"트렌드:\n{topic['ref_trending']}")
    if topic.get("ref_news"):
        ref_parts.append(f"뉴스:\n{topic['ref_news']}")
    if topic.get("ref_blogs"):
        ref_parts.append(f"블로그:\n{topic['ref_blogs']}")
    ref_section = "\n\n".join(ref_parts) if ref_parts else "없음"

    # structure 전체를 보여줌 (LLM이 글의 전체 흐름을 파악하도록)
    template_lines = []
    slot_idx = 0
    for item in tpl_data.get("structure", []):
        t = item.get("type", "")
        content = item.get("content", "")
        content = content.replace("{region}", region or "")
        content = content.replace("{region_short}", region_short or "")
        content = content.replace("{trending_keyword}", topic.get("angle", "").split(",")[0].strip())

        if t == "blank":
            template_lines.append("")
        elif t == "heading":
            template_lines.append(f"[소제목: {content}]")
        elif t == "divider":
            template_lines.append("---")
        elif t == "image":
            template_lines.append(f"[이미지]")
        elif t in ("text", "quote", "bold_text"):
            slot_idx += 1
            template_lines.append("{" + f"{slot_idx}: {content}" + "}")
        elif t == "hashtags":
            slot_idx += 1
            template_lines.append("{" + f"{slot_idx}: 해시태그 {content}" + "}")

    slots_text = "\n".join(template_lines)

# 기본값
    length = tpl_data.get("length", {})
    min_len = length.get("min", 2000)
    max_len = length.get("max", 3000)

    return f"""너는 마크클라우드 블로그 글쓴이다.
마크클라우드는 AI 기반 IP(상표·디자인·특허) 서비스 전문 기업이다.

## 서비스 정보
{SERVICE_INFO}

## 규칙
- 친근하고 실용적인 톤. 사장님한테 말하듯이
- 짧은 문장. 한 문장에 하나의 정보만
- 허구 브랜드/사례/통계 금지. 참고 데이터에 없는 수치나 사실을 지어내지 말 것
- "증가했다", "늘었다" 등 변화를 말할 때는 참고 데이터에 근거가 있을 때만
- 과대광고("1위","최고") 금지
- 제목 과장 금지 ("심장이 덜컥", "충격" 등)
- 뉴스 제목 그대로 복사 금지
- 글자수/메타 정보 본문에 언급 금지
- AI스러운 문체 금지 ("눈에 띄게", "속속", "불어넣고 있습니다", "시점입니다", "다채로운", "선사하며", "활력을 불어넣고")

아래 참고 데이터를 활용해서 블로그 글 하나를 작성합니다.
템플릿의 각 {{}} 부분을 글의 흐름에 맞게 자연스럽게 이어지도록 채워주세요.
각 슬롯은 독립된 빈칸이 아니라, 하나의 블로그 글 안에서 자연스럽게 연결되어야 합니다.

## 참고 데이터
주제: {angle}
키워드: {', '.join(keywords) if keywords else ''}
{ref_section}

## 템플릿
제목: {{30자 이내. [1]에서 다루는 행사명/핵심 키워드를 제목에 반드시 포함}}
{slots_text}

## 응답 형식
제목: 여기에 제목
[1] 여기에 텍스트
[2] 여기에 텍스트
...

마크다운 쓰지 말 것. 모든 슬롯을 지시사항대로 채울 것."""


def _parse_response(raw: str, tpl_data: dict = None) -> dict:
    """LLM 응답 파싱 → 제목 + 슬롯 텍스트.

    LLM이 {1}, {2} 형식으로 답하면 그걸로 파싱.
    아니면 ## 소제목 사이의 텍스트를 슬롯 순서대로 매핑.
    """
    title = ""
    slots = {}

    lines = raw.split("\n")

    for line in lines:
        s = line.strip()
        if s.startswith("제목:"):
            title = s.split(":", 1)[1].strip().strip("[]\"")

    # 방법1: {N} 또는 [N] 패턴
    current_slot = None
    current_lines = []
    for line in lines:
        m = re.match(r"^\{(\d+)\}\s*(.*)", line)
        if not m:
            m = re.match(r"^\[(\d+)\]\s*(.*)", line)
        if m:
            if current_slot is not None:
                slots[current_slot] = "\n".join(current_lines).strip()
            current_slot = int(m.group(1))
            current_lines = [m.group(2)] if m.group(2) else []
        elif current_slot is not None:
            current_lines.append(line)

    if current_slot is not None:
        slots[current_slot] = "\n".join(current_lines).strip()

    if slots:
        return {"title": title, "slots": slots}

    # 방법2: ## 소제목 사이의 텍스트를 슬롯으로 매핑
    if tpl_data:
        # structure에서 슬롯 타입 순서 파악
        slot_types = []
        for item in tpl_data.get("structure", []):
            if item.get("type") in ("text", "quote", "hashtags"):
                slot_types.append(item["type"])

        # 제목 줄 이후부터 파싱
        body_lines = []
        started = False
        for line in lines:
            s = line.strip()
            if s.startswith("제목:"):
                started = True
                continue
            if started:
                body_lines.append(line)

        # ## 소제목 / [이미지] / 빈줄 을 구분자로 텍스트 블록 추출
        text_blocks = []
        current_block = []
        for line in body_lines:
            s = line.strip()
            if s.startswith("##") or s.startswith("[이미지") or not s:
                if current_block:
                    text_blocks.append("\n".join(current_block).strip())
                    current_block = []
            else:
                current_block.append(line)
        if current_block:
            text_blocks.append("\n".join(current_block).strip())

        # 텍스트 블록을 슬롯에 매핑
        for i, block in enumerate(text_blocks):
            if block and i < len(slot_types):
                slots[i + 1] = block

    return {"title": title, "slots": slots}


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

    # 템플릿 로드
    tpl_path = Path(f"data/templates/{template_name}.json")
    tpl_data = json.loads(tpl_path.read_text(encoding="utf-8")) if tpl_path.exists() else {}

    # 이미지
    blog_images = _load_blog_images()

    # LLM 호출 (프롬프트 하나로)
    prompt = _build_prompt(tpl_data, region, region_short, business, angle, keywords, topic)
    result = generate(prompt, max_tokens=4096)
    parsed = _parse_response(result["text"], tpl_data=tpl_data)

    title = parsed["title"]

    # 썸네일 생성
    from blog_generator.thumbnail_maker import make_thumbnail, upload_thumbnail_imgur
    thumb_path = make_thumbnail(
        main_title=title or f"{region_short} 상표·특허 출원",
        sub_title_1="", sub_title_2="",
        region=region,
        output_name=f"thumb_{region.replace(' ', '_')}_{re.sub(r'[/\\\\|:*?\"<>]', '_', business)}.png",
    )
    thumb_url = upload_thumbnail_imgur(thumb_path)

    if not title:
        title = f"{region_short} {business_desc}, 상표 출원이 필요한 이유"

    return {
        "title": title,
        "region": region,
        "region_short": region_short,
        "business": business,
        "angle": angle,
        "model_info": {"model": result["model"], "provider": result["provider"]},
        # structure_to_commands()에서 직접 사용
        "_tpl_data": tpl_data,
        "_slots": parsed["slots"],
        "_blog_images": blog_images,
        "_thumb_url": thumb_url,
        "_thumb_path": str(thumb_path) if thumb_path else "",
    }
