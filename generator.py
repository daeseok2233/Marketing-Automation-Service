"""Gemini 2.0 Flash 블로그 생성 + 품질 검수"""
import os, json, re, time
import requests as _req
from google import genai
from google.genai import types
from schema import BlogPost

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# 무료 한도 소진 시 순서대로 폴백 (각 모델 독립 쿼터)
MODELS = [
    "gemini-2.0-flash",       # 1순위: 빠름, 15 RPM 무료
    "gemini-2.0-flash-lite",  # 2순위: 더 빠름, 30 RPM 무료
    "gemini-2.5-flash-lite",  # 3순위: 신규 경량, 독립 쿼터
    "gemini-2.5-flash",       # 4순위: 고품질, 10 RPM 무료
    "gemini-flash-lite-latest", # 5순위: 최신 lite 알리아스
]

class BlogGenerator:
    def __init__(self):
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

    def _make_config(self, model: str) -> types.GenerateContentConfig:
        # 2.5 계열은 thinking 비활성화로 출력 토큰 확보
        if "2.5" in model:
            return types.GenerateContentConfig(
                temperature=0.75,
                max_output_tokens=8192,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
        return types.GenerateContentConfig(
            temperature=0.75,
            max_output_tokens=8192,
        )

    def generate(self, prompt: str) -> dict | None:
        for model in MODELS:
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=self._make_config(model),
                )
                result = self._parse(resp.text.strip())
                if result is not None:
                    return result
                print(f"  Gemini {model} JSON 파싱 실패, 다음 모델 시도...")
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    print(f"  Gemini {model} 한도 초과, 다음 모델 시도...")
                    time.sleep(5)
                    continue
                print(f"  Gemini 오류 ({model}): {e}")
        print("  Gemini 오류: 모든 모델 실패 → Ollama 시도...")
        return self._call_ollama(prompt)

    def _call_ollama(self, prompt: str) -> dict | None:
        """Gemini 전부 실패 시 로컬 Ollama 폴백"""
        try:
            tags = _req.get(f"{OLLAMA_URL}/api/tags", timeout=5).json()
            models = [m["name"] for m in tags.get("models", [])]
        except Exception:
            print("  Ollama 연결 실패 (실행 중인지 확인하세요)")
            return None
        if not models:
            print("  Ollama 모델 없음 — 'ollama pull llama3.2' 실행 후 재시도")
            return None
        model = models[0]
        print(f"  Ollama 모델 사용: {model}")
        try:
            resp = _req.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
                timeout=120,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
            result = self._parse(text)
            if result is not None:
                return result
            print(f"  Ollama JSON 파싱 실패\n  원본: {text[:200]}")
        except Exception as e:
            print(f"  Ollama 오류: {e}")
        return None

    def _parse(self, raw: str) -> dict | None:
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        m = re.search(r'\{[\s\S]*\}', cleaned)
        if not m:
            return None
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError as e:
            print(f"  JSON 파싱 실패: {e}\n  원본: {raw[:200]}")
            return None

        # ── Pydantic 검증 + 정규화 (해시태그 # 자동 보정 등)
        try:
            post = BlogPost(**data)
            return post.to_dict()
        except Exception as e:
            print(f"  Pydantic 검증 실패: {e}")
            # 구형 flat body 포맷(Ollama 등)은 그대로 통과
            if isinstance(data.get("body"), str) and data.get("title"):
                return data
            return None


def quality_check(post: dict) -> tuple[bool, str]:
    """(통과여부, 실패이유) 반환 — 구조형(intro+body[]+conclusion) 및 flat body 모두 지원"""
    title = post.get("title", "")
    tags  = post.get("hashtags", [])
    meta  = post.get("meta_description", "")
    svc   = {"markview":"마크뷰","markpick":"마크픽",
              "markpass":"마크패스","markcloud":"마크클라우드"}.get(post.get("service_key",""), "마크")

    # 전체 본문 텍스트 구성 (구조형 / flat 모두 대응)
    if isinstance(post.get("body"), list):
        parts = [post.get("intro", "")]
        for s in post.get("body", []):
            if isinstance(s, dict):
                parts.extend([s.get("heading", ""), s.get("content", "")])
        parts.extend([post.get("conclusion", ""), post.get("cta", "")])
        full_text = "\n".join(filter(None, parts))
    else:
        full_text = post.get("body", "")

    checks = [
        (len(full_text) >= 1500, f"본문 부족 ({len(full_text)}자)"),
        (len(title)     >= 15,   f"제목 짧음 ({len(title)}자)"),
        (full_text.count(svc) >= 2, f"서비스 언급 부족 ({svc} {full_text.count(svc)}회)"),
        (len(tags)      >= 4,    f"해시태그 부족 ({len(tags)}개)"),
        (len(meta)      >= 20,   "메타설명 없음"),
    ]
    for ok, reason in checks:
        if not ok:
            return False, reason
    return True, ""
