"""5단계: 법률 검증 — 생성된 글에서 법률 인용이 필요한 부분 검증/채우기."""

import json
from pathlib import Path
from datetime import datetime

from model import generate

LEGAL_CACHE = Path("data/legal_cache/articles.json")


def _load_legal_articles() -> list[dict]:
    """상표법 조문 캐시 로드."""
    if LEGAL_CACHE.exists():
        return json.loads(LEGAL_CACHE.read_text(encoding="utf-8"))
    return []


def _build_legal_context() -> str:
    """법률 검증에 필요한 핵심 조문 컨텍스트."""
    articles = _load_legal_articles()
    key_articles = ["2", "33", "34", "35", "65", "108", "109", "119"]

    context_parts = []
    for art in articles:
        if art.get("number") in key_articles:
            title = art.get("title", "")
            content = art.get("content", "")
            context_parts.append(f"제{art['number']}조 ({title}): {content[:300]}")

    return "\n".join(context_parts)


def check_legal(blog_data: dict) -> dict:
    """생성된 블로그에서 법률 관련 내용을 검증하고 보완한다.

    Args:
        blog_data: writer에서 반환된 dict (title, body, ...)

    Returns:
        blog_data에 legal_verified 필드 추가
    """
    body = blog_data.get("body", "")

    # 법률 관련 키워드가 있는지 체크
    legal_keywords = [
        "상표법", "제", "조", "법률", "법적", "침해", "손해배상",
        "취소심판", "이의신청", "거절", "등록요건", "식별력",
    ]
    has_legal = any(kw in body for kw in legal_keywords)

    if not has_legal:
        blog_data["legal_verified"] = True
        blog_data["legal_note"] = "법률 인용 없음 — 검증 불필요"
        _save_intermediate("05_final", blog_data)
        return blog_data

    # 법률 내용이 있으면 검증
    legal_context = _build_legal_context()

    system = """당신은 상표법 전문가입니다.
블로그 글에서 법률 관련 내용이 정확한지 검증하고, 잘못된 부분을 수정합니다.
수정된 전체 본문을 출력하세요. 법률 인용이 필요한 부분에는 정확한 조항 번호를 추가합니다."""

    prompt = f"""## 상표법 핵심 조문 (검증 기준)
{legal_context}

## 검증 대상 블로그 본문
{body}

## 요청
1. 법률 조항 번호가 잘못 인용된 부분이 있으면 수정
2. 법적 내용이 부정확한 부분이 있으면 수정
3. 법률 인용이 필요하지만 빠진 부분에 조항 번호 추가
4. 수정된 전체 본문을 출력 (수정 없으면 원본 그대로)"""

    result = generate(prompt, system=system)

    if result["text"]:
        blog_data["body"] = result["text"]
        blog_data["legal_verified"] = True
        blog_data["legal_note"] = f"법률 검증 완료 ({result['model']})"
    else:
        blog_data["legal_verified"] = False
        blog_data["legal_note"] = "법률 검증 모델 호출 실패 — 원본 유지"

    _save_intermediate("05_final", blog_data)

    return blog_data


def _save_intermediate(step: str, data: dict):
    out_dir = Path("data/generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    path = out_dir / f"{today}_{step}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [저장] {path}")
