---
name: model strategy
description: LLM 모델 전략 — Gemini 무료 모델 순차 사용 후 Ollama 폴백
type: project
---

LLM 호출은 model.py로 분리. Gemini 무료 모델을 순서대로 사용하고, 할당량 소진 시 Ollama로 폴백.

**Why:** 비용 최소화 + 무료 API 한도 최대 활용
**How to apply:** model.py에서 Gemini 키 여러 개 순환 → 429 시 다음 키 → 전부 소진 시 Ollama 호출. generator/writer.py는 model.py만 호출.
