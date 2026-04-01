"""3단계: 프롬프트 구성 — 템플릿 + 블로그정보 + 서비스정보 → 프롬프트."""

import json
from pathlib import Path
from datetime import datetime


def _load_json(path: str) -> dict | list:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def build_prompt(topic_data: dict, reference: dict) -> dict:
    """LLM에 보낼 system/user 프롬프트를 구성한다.

    Args:
        topic_data: 1단계 결과 (topic, template, keywords)
        reference: 2단계 결과 (관련 뉴스/경쟁사/트렌드)

    Returns:
        {
            "system_prompt": "...",
            "user_prompt": "...",
            "template_name": "...",
        }
    """
    template_name = topic_data.get("template", "howto")
    topic = topic_data.get("topic", "")
    keywords = topic_data.get("keywords", [])

    # 템플릿 로드
    template_path = Path(f"data/templates/{template_name}.json")
    if not template_path.exists():
        template_path = Path("data/templates/howto.json")
        template_name = "howto"
    template = json.loads(template_path.read_text(encoding="utf-8"))

    # 베이스 템플릿 로드
    base_path = Path("data/templates/00_base.json")
    base = json.loads(base_path.read_text(encoding="utf-8")) if base_path.exists() else {}

    # 블로그/서비스 정보
    blog_info = _load_json("data/service_data/blogs.json")
    service_info = _load_json("data/service_data/services.json")
    event_info = _load_json("data/service_data/event.json")

    # ── system prompt ──
    system_prompt = f"""당신은 마크클라우드 서비스의 전문 블로그 작성자입니다.
SEO, AEO(Answer Engine Optimization), GEO(Generative Engine Optimization)를 모두 고려하여 블로그 글을 작성합니다.

## 작성 원칙
- 독자가 실제로 궁금해하는 정보를 명확하게 전달
- 자연스러운 키워드 배치 (키워드 스터핑 금지)
- H2/H3 소제목으로 구조화 (AEO: AI가 답변으로 추출하기 쉽게)
- 신뢰할 수 있는 데이터/출처 인용 (GEO: 생성형 검색에서 인용되도록)
- 마크클라우드 서비스를 자연스럽게 CTA로 연결

## 블로그 정보
{json.dumps(blog_info, ensure_ascii=False, indent=2)[:800]}

## 서비스 정보
{json.dumps(service_info, ensure_ascii=False, indent=2)[:800]}

## 이벤트 정보
{json.dumps(event_info, ensure_ascii=False, indent=2)[:500]}"""

    # ── user prompt ──
    # 레퍼런스 요약
    ref_news = ""
    if reference.get("related_news"):
        ref_news = "\n".join([
            f"- {n['title']}" for n in reference["related_news"]
        ])

    ref_competitors = ""
    if reference.get("related_competitors"):
        ref_competitors = "\n".join([
            f"- {c['title']}" for c in reference["related_competitors"]
        ])

    ref_trends = ""
    if reference.get("search_trends"):
        ref_trends = "\n".join([
            f"- {t['keyword']}: 성장률 {t['growth']}%"
            for t in reference["search_trends"][:5]
        ])

    ref_suggest = ""
    if reference.get("suggest_keywords"):
        ref_suggest = ", ".join(reference["suggest_keywords"][:10])

    # 템플릿 구조
    template_structure = json.dumps(template, ensure_ascii=False, indent=2)[:2000]

    user_prompt = f"""## 주제
{topic}

## SEO 키워드
{', '.join(keywords)}

## 템플릿 구조 ({template_name})
{template_structure}

## 레퍼런스 데이터

### 관련 뉴스
{ref_news or '없음'}

### 경쟁사 상위 블로그 제목
{ref_competitors or '없음'}

### 검색 트렌드
{ref_trends or '없음'}

### 사용자 검색 키워드 (자동완성)
{ref_suggest or '없음'}

## 요청
위 템플릿 구조에 맞춰 블로그 글을 작성하세요.
- 포스팅 제목 1개
- 본문 전체 (H2/H3 소제목 포함)
- 메타 디스크립션 (150자 이내)

출력 형식:
```
제목: [포스팅 제목]
메타디스크립션: [150자 이내]

[본문 전체 — 마크다운 형식]
```"""

    result = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "template_name": template_name,
    }

    # 중간결과 저장
    _save_intermediate("03_prompt", result)

    return result


def _save_intermediate(step: str, data: dict):
    out_dir = Path("data/generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    path = out_dir / f"{today}_{step}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [저장] {path}")
