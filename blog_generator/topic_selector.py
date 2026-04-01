"""1단계: 주제 선정 — 템플릿 + 블로그정보 + 서비스정보 + 수집 데이터 → 주제."""

import json
from pathlib import Path
from model import generate


def _load_json(path: str) -> dict | list:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _load_templates() -> list[dict]:
    """data/templates/*.json 전체 로드."""
    templates_dir = Path("data/templates")
    templates = []
    for f in sorted(templates_dir.glob("*.json")):
        if f.name.startswith("00_"):
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        data["_filename"] = f.stem
        templates.append(data)
    return templates


def _load_collected_summary() -> str:
    """오늘 수집된 CSV 데이터 요약."""
    from datetime import datetime
    collected_dir = Path("data/collected")
    today = datetime.now().strftime("%Y%m%d")
    lines = []

    for f in sorted(collected_dir.glob(f"{today}_*.csv")):
        name = f.stem.replace(f"{today}_", "")
        with open(f, encoding="utf-8-sig") as fh:
            content = fh.read()
            row_count = content.count("\n") - 1
            # 첫 10줄만 요약
            preview = "\n".join(content.split("\n")[:11])
            lines.append(f"[{name}] {row_count}건\n{preview}\n")

    return "\n".join(lines)


def select_topic() -> dict:
    """주제를 선정하고 결과를 반환한다.

    Returns:
        {
            "topic": "선정된 주제",
            "template": "사용할 템플릿 이름",
            "reason": "선정 이유",
            "keywords": ["SEO 키워드 리스트"],
            "model_info": {"model": ..., "provider": ...},
        }
    """
    # 입력 데이터 로드
    templates = _load_templates()
    blog_info = _load_json("data/service_data/blogs.json")
    service_info = _load_json("data/service_data/services.json")
    collected = _load_collected_summary()

    template_names = [t.get("_filename", "") for t in templates]
    template_summaries = []
    for t in templates:
        name = t.get("_filename", "")
        desc = t.get("description", t.get("설명", ""))
        template_summaries.append(f"- {name}: {desc}")

    system = """당신은 SEO/AEO/GEO 전문가입니다.
마크클라우드(상표 출원/등록 서비스)의 블로그 포스팅 주제를 선정합니다.
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력합니다."""

    prompt = f"""아래 정보를 기반으로 오늘의 블로그 포스팅 주제를 1개 선정하세요.

## 사용 가능한 템플릿
{chr(10).join(template_summaries)}

## 블로그 정보
{json.dumps(blog_info, ensure_ascii=False, indent=2)[:1000]}

## 서비스 정보
{json.dumps(service_info, ensure_ascii=False, indent=2)[:1000]}

## 오늘 수집된 데이터 (트렌드/뉴스/경쟁사)
{collected[:3000]}

## 출력 형식 (JSON만)
{{
    "topic": "블로그 포스팅 주제 (구체적으로)",
    "template": "사용할 템플릿 파일명 (위 목록 중 하나)",
    "reason": "이 주제를 선정한 이유 (트렌드/검색량/경쟁 분석 근거)",
    "keywords": ["SEO 키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]
}}"""

    result = generate(prompt, system=system)

    # JSON 파싱
    text = result["text"].strip()
    # ```json ... ``` 블록 제거
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        topic_data = json.loads(text)
    except json.JSONDecodeError:
        topic_data = {
            "topic": "상표 출원 방법 완벽 가이드",
            "template": "howto",
            "reason": "JSON 파싱 실패 — 기본 주제 사용",
            "keywords": ["상표출원", "상표등록", "상표출원방법", "셀프출원", "마크클라우드"],
        }

    topic_data["model_info"] = {
        "model": result["model"],
        "provider": result["provider"],
    }

    # 중간결과 저장
    _save_intermediate("01_topic", topic_data)

    return topic_data


def _save_intermediate(step: str, data: dict):
    """중간결과를 data/generated/에 저장."""
    from datetime import datetime
    out_dir = Path("data/generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    path = out_dir / f"{today}_{step}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [저장] {path}")
