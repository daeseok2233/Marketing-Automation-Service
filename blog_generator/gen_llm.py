# generator.py
import os, time
import requests as _req
from google import genai
from google.genai import types
from schema import BlogPost

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
]


class BlogGenerator:
    def __init__(self):
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

    def _make_config(self, model: str) -> types.GenerateContentConfig:
        config = dict(
            temperature=0.75,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=BlogPost,  # Pydantic 모델 직접 전달
        )
        if "2.5" in model:
            config["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        return types.GenerateContentConfig(**config)

    def generate(self, prompt: str) -> BlogPost | None:
        for model in MODELS:
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=self._make_config(model),
                )
                # 구조화 출력 시 resp.parsed에 Pydantic 객체가 바로 들어옴
                if resp.parsed:
                    return resp.parsed
                print(f"  Gemini {model} 파싱 실패, 다음 모델 시도...")
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    print(f"  Gemini {model} 한도 초과, 다음 모델 시도...")
                    time.sleep(5)
                    continue
                print(f"  Gemini 오류 ({model}): {e}")
        print("  모든 Gemini 모델 실패 → Ollama 시도...")
        return self._call_ollama(prompt)

    def _call_ollama(self, prompt: str) -> BlogPost | None:
        """Gemini 전부 실패 시 로컬 Ollama 폴백 — 구조화 출력 미지원으로 수동 파싱"""
        import json, re
        try:
            tags = _req.get(f"{OLLAMA_URL}/api/tags", timeout=5).json()
            models = [m["name"] for m in tags.get("models", [])]
        except Exception:
            print("  Ollama 연결 실패")
            return None
        if not models:
            print("  Ollama 모델 없음")
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
            raw = resp.json().get("response", "").strip()
            cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
            m = re.search(r'\{[\s\S]*\}', cleaned)
            if not m:
                print("  Ollama JSON 추출 실패")
                return None
            return BlogPost(**json.loads(m.group()))
        except Exception as e:
            print(f"  Ollama 오류: {e}")
        return None


def quality_check(post: BlogPost, service_name: str) -> tuple[bool, str]:
    full_text = post.full_text()
    checks = [
        (len(post.sections) >= 5,             f"섹션 부족 ({len(post.sections)}개)"),
        (len(full_text) >= 1500,              f"본문 부족 ({len(full_text)}자)"),
        (len(post.title) >= 15,               f"제목 짧음 ({len(post.title)}자)"),
        (full_text.count(service_name) >= 2,  f"서비스 언급 부족 ({service_name} {full_text.count(service_name)}회)"),
        (8 <= len(post.hashtags) <= 15,       f"해시태그 범위 오류 ({len(post.hashtags)}개)"),
    ]
    for ok, reason in checks:
        if not ok:
            return False, reason
    return True, ""