"""블로그 템플릿 로더 + Gemini 프롬프트 빌더

템플릿 파일 위치: blog_templates/*.json
새 템플릿 추가 방법: blog_templates/ 에 JSON 파일 추가 (코드 수정 불필요)
"""
import json
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "blog_templates"

COMMON_RULES = """
━━━ 작성 규칙 ━━━
[SEO]  제목 40~50자·메인 키워드 앞쪽 배치 / 첫·끝 문단에 키워드 포함 / H2는 **굵게**
[AEO]  H2는 반드시 의문문 / 각 H2 바로 아래 핵심 답변 2~3문장 먼저 제시
[GEO]  빅카인즈 통계·특허청 수치 본문 인용(출처 표기) / 전문가 단정 문체
[품질]  본문 1,800자 이상 / 광고 문구 금지 / 해시태그 6~8개
"""


def _load_templates() -> dict:
    """blog_templates/*.json 파일을 모두 읽어 dict 반환"""
    templates = {}
    if not TEMPLATES_DIR.exists():
        return templates
    for path in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            key = data.get("key", path.stem)
            templates[key] = data
        except Exception as e:
            print(f"  [templates] {path.name} 로드 실패: {e}")
    return templates


# 앱 시작 시 1회 로드 (런타임 중 파일 수정은 반영 안 됨)
_TEMPLATE_DATA: dict = _load_templates()

# 하위 호환용 — 구조 문자열만 추출 (build_prompt 등에서 사용)
TEMPLATES: dict[str, str] = {
    k: "\n".join(v.get("structure", []))
    for k, v in _TEMPLATE_DATA.items()
}


def get_template_rules() -> str:
    """topic_finder 프롬프트에 삽입할 템플릿 선택 규칙 문자열 반환"""
    lines = ["5. template_key 선택 규칙 (반드시 준수):"]
    for k, data in _TEMPLATE_DATA.items():
        when = data.get("when_to_use", "")
        not_for = data.get("not_for", [])
        lines.append(f'   - "{k}" ({data.get("name","")}) : {when}')
        for rule in not_for:
            lines.append(f'     ※ {rule}')
    return "\n".join(lines)


def get_template_names() -> list[str]:
    """사용 가능한 template_key 목록 반환"""
    return list(_TEMPLATE_DATA.keys())