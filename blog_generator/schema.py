"""블로그 포스트 Pydantic 스키마 — AI 출력 검증 및 정규화"""
from pydantic import BaseModel, Field, field_validator


class BodySection(BaseModel):
    heading: str = Field(..., description="소제목 (의문문 권장)")
    content: str = Field(..., description="본문 내용")

    @field_validator("heading", "content")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("비어있을 수 없습니다")
        return v.strip()


class BlogPost(BaseModel):
    title: str              = Field(..., description="블로그 제목")
    meta_description: str   = Field(default="", description="검색 미리보기")
    hashtags: list[str]     = Field(default_factory=list, description="해시태그 목록")
    intro: str              = Field(default="", description="도입부")
    body: list[BodySection] = Field(default_factory=list, description="본론 섹션 리스트")
    conclusion: str         = Field(default="", description="마무리 문단")
    cta: str                = Field(default="", description="CTA 한 줄")

    @field_validator("hashtags")
    @classmethod
    def ensure_hash_prefix(cls, tags: list[str]) -> list[str]:
        return [t if t.startswith("#") else f"#{t}" for t in tags]

    @field_validator("title", "intro", "conclusion")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()

    def full_text(self) -> str:
        """품질 검수용 전체 본문 텍스트"""
        parts = [self.intro]
        for s in self.body:
            parts.extend([s.heading, s.content])
        parts.extend([self.conclusion, self.cta])
        return "\n".join(filter(None, parts))

    def to_dict(self) -> dict:
        d = self.model_dump()
        # body 섹션을 dict 리스트로 직렬화
        d["body"] = [{"heading": s.heading, "content": s.content} for s in self.body]
        return d
