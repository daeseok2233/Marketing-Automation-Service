"""글 품질 검증."""


def check_quality(blog_data: dict) -> tuple[bool, str]:
    """글 품질 검증. (통과여부, 사유) 반환."""
    # 슬롯 존재
    slots = blog_data.get("_slots", {})
    if not slots:
        return False, "슬롯 없음"

    # 전체 글자수
    total = sum(len(str(v)) for v in slots.values())
    if total < 200:
        return False, f"짧음({total}자)"

    # 제목 존재
    if not blog_data.get("title"):
        return False, "제목 없음"

    return True, "OK"
