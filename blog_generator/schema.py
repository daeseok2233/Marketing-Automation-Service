from pydantic import BaseModel, Field, field_validator

class Section(BaseModel):
    """단락 1개"""
    heading: str = Field(..., description="소제목")
    content: str = Field(..., description="본문 (\\n으로 줄바꿈)")

class BlogPost(BaseModel):
    """
    구조화된 블로그 포스트 전체

    섹션 순서:
        title → sections[0](서문) → sections[1:-1](본론) → sections[-1](결론) → cta → event → hashtags
    """
    title:    str           = Field(..., description="포스트 제목")
    sections: list[Section] = Field(..., min_length=5, description="단락 리스트. sections[0]=서문, sections[-1]=결론(상표출원), 나머지=본론")
    cta:      str           = Field(..., description="CTA 한 줄")
    event:    str           = Field("", description="이벤트 문구 (없으면 빈 문자열)")
    hashtags: list[str]     = Field(..., min_length=3, description="해시태그 리스트")

    @field_validator("hashtags")
    @classmethod
    def ensure_hash_prefix(cls, tags: list[str]) -> list[str]:
        return [t if t.startswith("#") else f"#{t}" for t in tags]

    @field_validator("sections")  # body → sections
    @classmethod
    def ensure_sections_not_empty(cls, sections: list[Section]) -> list[Section]:
        for s in sections:
            if not s.heading.strip() or not s.content.strip():
                raise ValueError("sections의 heading과 content는 비어있을 수 없습니다.")
        return sections