"""config.yaml 로더 — 앱 시작 시 1회 로드"""
from pathlib import Path
import yaml

_CONFIG_PATH = Path(__file__).parent / "config.yaml"

def _load() -> dict:
    try:
        return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as e:
        print(f"  [config] config.yaml 로드 실패, 기본값 사용: {e}")
        return {}

CFG = _load()

# ── 편의 접근자
TEXT_MODELS: list       = CFG.get("text_models", [
    "gemini-2.0-flash", "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-flash-lite-latest",
])
IMAGE_AI_MODELS: list   = CFG.get("image_ai_models", [
    "gemini-2.5-flash-image", "gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview",
])
IMAGE_SOURCE_ORDER: list = CFG.get("image_source_order", [
    "pexels", "unsplash", "pixabay", "pollinations", "gemini",
])
IMAGE_WIDTH: int        = CFG.get("image_width", 1280)
IMAGE_HEIGHT: int       = CFG.get("image_height", 720)
TEMPLATES: list         = CFG.get("templates", [
    "info", "howto", "checklist", "compare", "faq",
    "case", "industry-trend", "data-analysis", "image-search-demo",
])
OLLAMA_URL: str         = CFG.get("ollama_url", "http://localhost:11434")
QUALITY: dict           = CFG.get("quality", {
    "min_body_length": 1500,
    "min_title_length": 15,
    "min_service_mentions": 2,
    "min_hashtags": 4,
    "min_meta_length": 20,
})
