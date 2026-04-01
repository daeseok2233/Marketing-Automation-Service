"""LLM 호출 모듈 — Gemini 무료 모델 순차 사용, 소진 시 Ollama 폴백."""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Gemini 설정 ──────────────────────────────────────────
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

_keys_raw = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "")
GEMINI_API_KEYS = [k.strip() for k in _keys_raw.split(",") if k.strip()]

# ── Ollama 설정 ──────────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")


def _call_gemini(prompt: str, system: str = "", model: str = "", api_key: str = "", max_tokens: int = 8192) -> str | None:
    """Gemini API 단일 호출. 성공 시 텍스트, 실패 시 None."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": api_key}

    contents = []
    if system:
        contents.append({"role": "user", "parts": [{"text": f"[SYSTEM]\n{system}"}]})
        contents.append({"role": "model", "parts": [{"text": "understood."}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    body = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": max_tokens,
        },
    }

    try:
        r = requests.post(url, headers=headers, params=params, json=body, timeout=120)
        if r.status_code == 200:
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        elif r.status_code == 429:
            print(f"  [Gemini] {model} 할당량 초과 (429)")
            return None
        else:
            print(f"  [Gemini] {model} 오류 ({r.status_code}): {r.text[:200]}")
            return None
    except requests.exceptions.Timeout:
        print(f"  [Gemini] {model} 타임아웃")
        return None
    except Exception as e:
        print(f"  [Gemini] {model} 예외: {e}")
        return None


def _call_ollama(prompt: str, system: str = "") -> str | None:
    """Ollama 로컬 모델 호출. 성공 시 텍스트, 실패 시 None."""
    url = f"{OLLAMA_URL}/api/generate"
    body = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 8192,
        },
    }

    try:
        print(f"  [Ollama] {OLLAMA_MODEL} 호출 중...")
        r = requests.post(url, json=body, timeout=300)
        if r.status_code == 200:
            return r.json().get("response", "")
        else:
            print(f"  [Ollama] 오류 ({r.status_code}): {r.text[:200]}")
            return None
    except requests.exceptions.ConnectionError:
        print(f"  [Ollama] 연결 실패 — ollama serve 실행 필요")
        return None
    except Exception as e:
        print(f"  [Ollama] 예외: {e}")
        return None


def generate(prompt: str, system: str = "", max_tokens: int = 8192) -> dict:
    """LLM 호출 — Gemini 무료 모델 순차 시도 → Ollama 폴백.

    Returns:
        {
            "text": "생성된 텍스트",
            "model": "사용된 모델명",
            "provider": "gemini" | "ollama",
        }
    """
    # 1) Gemini 순차 시도: 모든 모델 × 모든 키
    for model in GEMINI_MODELS:
        for key in GEMINI_API_KEYS:
            result = _call_gemini(prompt, system=system, model=model, api_key=key, max_tokens=max_tokens)
            if result:
                print(f"  [Model] {model} 성공")
                return {"text": result, "model": model, "provider": "gemini"}

    # 2) Ollama 폴백
    print("  [Model] Gemini 전부 실패 → Ollama 폴백")
    result = _call_ollama(prompt, system=system)
    if result:
        print(f"  [Model] {OLLAMA_MODEL} 성공")
        return {"text": result, "model": OLLAMA_MODEL, "provider": "ollama"}

    # 3) 전부 실패
    return {"text": "", "model": "none", "provider": "none"}
