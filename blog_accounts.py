"""블로그 계정 정보 로더

blogs/*.json 파일을 읽어 계정별 톤/타깃/키워드 정보를 반환.
새 계정 추가: blogs/ 폴더에 JSON 파일 추가 (코드 수정 불필요)
"""
import json
from pathlib import Path

BLOGS_DIR = Path(__file__).parent / "blogs"


def load_accounts() -> dict[str, dict]:
    """active 계정 전체 반환 {account_id: account_data}"""
    accounts = {}
    if not BLOGS_DIR.exists():
        return accounts
    for path in sorted(BLOGS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("active", True):
                aid = data.get("account_id", path.stem)
                accounts[aid] = data
        except Exception as e:
            print(f"  [blog_accounts] {path.name} 로드 실패: {e}")
    return accounts


def get_account(account_id: str) -> dict:
    """특정 계정 정보 반환. 없으면 빈 dict."""
    accounts = load_accounts()
    return accounts.get(account_id, {})


def build_account_block(account: dict) -> str:
    """프롬프트 삽입용 계정 컨텍스트 문자열 빌드"""
    if not account:
        return ""
    lines = [
        "━━━ 블로그 계정 정보 ━━━",
        f"계정명     : {account.get('account_name', '')} ({account.get('platform', '')})",
        f"URL        : {account.get('url', '')}",
        f"작성 톤    : {account.get('tone', '')}",
        f"타깃 독자  : {account.get('target_audience', '')}",
        f"SEO 키워드 : {', '.join(account.get('seo_focus_keywords', []))}",
        f"작성 페르소나 : {account.get('writing_persona', '')}",
        f"CTA 스타일 : {account.get('cta_style', '')}",
        f"선호 구조  : {account.get('preferred_structure', '')}",
    ]
    avoid = account.get("avoid", [])
    if avoid:
        lines.append(f"금지 사항  : {', '.join(avoid)}")
    return "\n".join(lines)
