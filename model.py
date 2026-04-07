"""LLM 호출 모듈 — Gemini API (GCP 크레딧) → Ollama 폴백."""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Gemini 설정 (GCP 프로젝트 API 키 → $300 크레딧 차감) ──
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-001",
    "gemini-1.5-flash",
]

_keys_raw = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "")
GEMINI_API_KEYS = [k.strip() for k in _keys_raw.split(",") if k.strip()]

# ── Ollama 설정 ──────────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")


def _call_gemini(prompt: str, system: str = "", model: str = "", api_key: str = "", max_tokens: int = 8192) -> str | None:
    """Gemini API 호출 (GCP 크레딧 차감)."""
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


def _call_gemini_with_tools(
    contents: list,
    tools: list[dict],
    tool_executor: callable,
    system: str = "",
    model: str = "",
    api_key: str = "",
    max_tokens: int = 8192,
    max_turns: int = 5,
) -> dict | None:
    """Gemini Function Calling — 에이전트 루프.

    모델이 functionCall을 반환하면 tool_executor로 실행하고 결과를 돌려줌.
    텍스트를 반환하면 종료.

    Returns:
        {"text": "최종 텍스트", "tool_calls": [...호출 기록...]} 또는 None
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": api_key}

    # 시스템 프롬프트 → contents 앞에 삽입
    full_contents = []
    if system:
        full_contents.append({"role": "user", "parts": [{"text": f"[SYSTEM]\n{system}"}]})
        full_contents.append({"role": "model", "parts": [{"text": "understood."}]})
    full_contents.extend(contents)

    tool_call_log = []

    for turn in range(max_turns):
        body = {
            "contents": full_contents,
            "tools": [{"function_declarations": tools}],
            "tool_config": {"function_calling_config": {"mode": "AUTO"}},
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": max_tokens,
            },
        }

        try:
            r = requests.post(url, headers=headers, params=params, json=body, timeout=120)
            if r.status_code == 429:
                print(f"  [Gemini] {model} 할당량 초과 (429)")
                return None
            if r.status_code != 200:
                print(f"  [Gemini] {model} 오류 ({r.status_code}): {r.text[:200]}")
                return None

            data = r.json()
            candidate = data["candidates"][0]["content"]
            parts = candidate.get("parts", [])

            # function call이 있는지 확인
            func_calls = [p for p in parts if "functionCall" in p]
            text_parts = [p["text"] for p in parts if "text" in p]

            if not func_calls:
                # 텍스트만 반환 → 완료
                final_text = "\n".join(text_parts)
                return {"text": final_text, "tool_calls": tool_call_log}

            # function call 실행
            full_contents.append({"role": "model", "parts": parts})

            func_responses = []
            for fc in func_calls:
                call = fc["functionCall"]
                fn_name = call["name"]
                fn_args = call.get("args", {})
                print(f"  [Agent] 🔧 {fn_name}({json.dumps(fn_args, ensure_ascii=False)[:80]})")

                result = tool_executor(fn_name, fn_args)
                tool_call_log.append({"function": fn_name, "args": fn_args, "result_preview": str(result)[:200]})

                func_responses.append({
                    "functionResponse": {
                        "name": fn_name,
                        "response": {"result": result},
                    }
                })

            full_contents.append({"role": "user", "parts": func_responses})

        except requests.exceptions.Timeout:
            print(f"  [Gemini] {model} 타임아웃")
            return None
        except Exception as e:
            print(f"  [Gemini] {model} 예외: {e}")
            return None

    # max_turns 초과
    print(f"  [Agent] 최대 턴({max_turns}) 초과")
    return {"text": "", "tool_calls": tool_call_log}


def generate_with_tools(
    prompt: str,
    tools: list[dict],
    tool_executor: callable,
    system: str = "",
    max_tokens: int = 8192,
    max_turns: int = 5,
) -> dict:
    """Function Calling이 포함된 LLM 호출 — Gemini만 지원.

    Args:
        prompt: 유저 프롬프트
        tools: Gemini function_declarations 리스트
        tool_executor: fn(name, args) -> result 함수
        system: 시스템 프롬프트
        max_tokens: 최대 토큰
        max_turns: 최대 tool call 반복 횟수

    Returns:
        {"text": "최종 텍스트", "model": "모델명", "provider": "gemini",
         "tool_calls": [...호출 기록...]}
    """
    contents = [{"role": "user", "parts": [{"text": prompt}]}]

    for model in GEMINI_MODELS:
        for key in GEMINI_API_KEYS:
            result = _call_gemini_with_tools(
                contents, tools, tool_executor,
                system=system, model=model, api_key=key,
                max_tokens=max_tokens, max_turns=max_turns,
            )
            if result and result.get("text"):
                print(f"  [Model] {model} 성공 (tool calls: {len(result['tool_calls'])})")
                return {
                    "text": result["text"],
                    "model": model,
                    "provider": "gemini",
                    "tool_calls": result["tool_calls"],
                }

    return {"text": "", "model": "none", "provider": "none", "tool_calls": []}


def _call_ollama(prompt: str, system: str = "") -> str | None:
    """Ollama 로컬 모델 호출."""
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
    """LLM 호출 — Gemini (GCP 크레딧) → Ollama 폴백.

    Returns:
        {"text": "생성된 텍스트", "model": "모델명", "provider": "gemini|ollama"}
    """
    # 1) Gemini (GCP 크레딧)
    for model in GEMINI_MODELS:
        for key in GEMINI_API_KEYS:
            result = _call_gemini(prompt, system=system, model=model, api_key=key, max_tokens=max_tokens)
            if result:
                print(f"  [Model] {model} 성공")
                return {"text": result, "model": model, "provider": "gemini"}

    # 2) Ollama (로컬 폴백)
    print("  [Model] Gemini 전부 실패 → Ollama 폴백")
    result = _call_ollama(prompt, system=system)
    if result:
        print(f"  [Model] {OLLAMA_MODEL} 성공")
        return {"text": result, "model": OLLAMA_MODEL, "provider": "ollama"}

    # 3) 전부 실패
    return {"text": "", "model": "none", "provider": "none"}
