"""블로그 포스트 이미지 자동 생성

폴백 순서 (쿼터 소진 시 자동으로 다음 모델):
  [AI 생성]
  1. Gemini 2.0 Flash  — 일 500장 무료, 신용카드 불필요 (GEMINI_API_KEY 재사용)
  2. Pollinations.ai   — 완전 무료, 가입 불필요, 클라우드 FLUX (15초/req)
  [스톡 사진 — 저작권 걱정 없음, 상업용 무료]
  3. Pexels            — 월 25,000회 (PEXELS_API_KEY 필요, 무료 발급)
  4. Unsplash          — 시간당 50회 (UNSPLASH_ACCESS_KEY 필요, 무료 발급)
  5. Pixabay           — 시간당 100회 (PIXABAY_API_KEY 필요, 무료 발급)

.env 설정:
  IMAGE_GENERATION=true
  IMGBB_API_KEY=xxx          # AI 생성 이미지 → Notion URL용 (이미 있음)
  PEXELS_API_KEY=xxx         # https://www.pexels.com/api/
  UNSPLASH_ACCESS_KEY=xxx    # https://unsplash.com/developers
  PIXABAY_API_KEY=xxx        # https://pixabay.com/api/docs/

로컬 GPU 사용 안 함 — 모든 생성은 클라우드 API.
"""
import os, sys, re, base64, time, logging, urllib.parse, random, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime
from pathlib import Path
import requests
from google import genai
from google.genai import types
from config import IMAGE_AI_MODELS, IMAGE_SOURCE_ORDER, IMAGE_WIDTH, IMAGE_HEIGHT

log = logging.getLogger(__name__)

OUTPUT_DIR = Path("outputs/images")

# ── 스톡 이미지 검색용 영어 키워드 (템플릿별) ────────────────────
_STOCK_KEYWORDS = {
    "info":              "brand trademark protection business law",
    "howto":             "business registration documents process steps",
    "checklist":         "business checklist paperwork planning",
    "compare":           "business comparison decision scale",
    "faq":               "business questions answers consultation",
    "case":              "legal dispute court trademark conflict",
    "industry-trend":    "business market growth chart analytics",
    "data-analysis":     "data statistics analytics dashboard report",
    "image-search-demo": "AI technology digital scanning computer",
}

# ── 템플릿 JSON에서 image_hints 로드 (단일 진실 소스) ─────────────
_TEMPLATES_DIR = Path(__file__).parent / "blog_templates"

def _load_template_image_hints() -> dict:
    hints = {}
    for f in _TEMPLATES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            key = data.get("key")
            if key and "image_hints" in data:
                hints[key] = data["image_hints"]
        except Exception as e:
            log.warning(f"  [템플릿 로드] {f.name} 실패: {e}")
    return hints

TEMPLATE_IMAGE_HINTS = _load_template_image_hints()


class ImageGenerator:
    def __init__(self):
        self.gemini_client      = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
        self.imgbb_key          = os.environ.get("IMGBB_API_KEY", "")
        self.pexels_key         = os.environ.get("PEXELS_API_KEY", "")
        self.unsplash_key       = os.environ.get("UNSPLASH_ACCESS_KEY", "")
        self.pixabay_key        = os.environ.get("PIXABAY_API_KEY", "")
        self.enabled            = os.environ.get("IMAGE_GENERATION", "false").lower() == "true"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def generate_for_post(self, post: dict) -> list:
        """글 내용 기반 이미지 생성 후 결과 목록 반환"""
        if not self.enabled:
            return []

        tpl_key = post.get("template_key", "info")
        hints   = TEMPLATE_IMAGE_HINTS.get(tpl_key, [])
        if not hints:
            return []

        main_keyword = post.get("main_keyword", "상표")
        results = []

        for hint in hints:
            try:
                # ── 글 내용 기반 AI 프롬프트 (제목 + 포지션 컨텍스트 추가)
                ai_prompt = self._build_ai_prompt(post, hint)

                # ── 글 내용 기반 영문 스톡 검색어 (Gemini text 1회 호출)
                stock_query = self._build_stock_query(post, hint)

                alt = hint.get("alt_text", "").replace("{main_keyword}", main_keyword)

                result = self._generate_with_fallback(
                    ai_prompt, stock_query, main_keyword, hint["position"], alt
                )
                if result:
                    results.append(result)
                    log.info(f"  [이미지] {hint['position']} ({result['source']}) → {result.get('path', result.get('url',''))[:60]}")

            except Exception as e:
                log.warning(f"  [이미지] {hint['position']} 모든 모델 실패: {e}")

        return results

    def _build_ai_prompt(self, post: dict, hint: dict) -> str:
        """글 제목·키워드·포지션을 반영한 AI 이미지 생성 프롬프트"""
        main_keyword = post.get("main_keyword", "상표")
        title        = post.get("title", "")
        base_prompt  = hint["prompt"].replace("{main_keyword}", main_keyword)

        # 본문 첫 소제목 추가 컨텍스트로 활용
        body = post.get("body", [])
        first_heading = body[0].get("heading", "") if body else ""

        extra = ""
        if title:
            extra += f"Blog post: {title}. "
        if first_heading:
            extra += f"Topic: {first_heading}. "

        return f"{extra}{base_prompt}"

    def _build_stock_query(self, post: dict, hint: dict) -> str:
        """글 내용 기반 영문 스톡 이미지 검색어 생성 (Gemini text 1회)"""
        title        = post.get("title", "")
        main_keyword = post.get("main_keyword", "")
        tpl_key      = post.get("template_key", "info")
        position     = hint.get("position", "cover")
        fallback     = _STOCK_KEYWORDS.get(tpl_key, "trademark business professional")

        try:
            prompt = (
                f"Generate 4-6 English keywords for a stock photo search on Pexels/Unsplash.\n"
                f"Korean blog post title: {title}\n"
                f"Main keyword: {main_keyword}\n"
                f"Image position: {position}\n"
                f"Rules: English only, no quotes, no explanation, just space-separated keywords.\n"
                f"Example output: trademark registration documents business professional office"
            )
            resp = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            query = resp.text.strip().replace('"', "").replace("\n", " ").split(".")[0]
            return query if query else fallback
        except Exception as e:
            log.debug(f"  [stock_query 생성 실패] {e} → fallback 사용")
            return fallback

    # ── 폴백 체인 ────────────────────────────────────────────────

    def _generate_with_fallback(
        self, ai_prompt: str, stock_query: str,
        keyword: str, position: str, alt: str
    ) -> dict | None:
        """config.yaml의 image_source_order 순서대로 시도"""
        for source in IMAGE_SOURCE_ORDER:
            try:
                if source == "pexels" and self.pexels_key:
                    url = self._pexels_url(stock_query)
                    return {"position": position, "path": "", "url": url, "alt_text": alt, "source": "pexels"}
                elif source == "unsplash" and self.unsplash_key:
                    url = self._unsplash_url(stock_query)
                    return {"position": position, "path": "", "url": url, "alt_text": alt, "source": "unsplash"}
                elif source == "pixabay" and self.pixabay_key:
                    url = self._pixabay_url(stock_query)
                    return {"position": position, "path": "", "url": url, "alt_text": alt, "source": "pixabay"}
                elif source == "local_sd":
                    img_bytes = self._local_sd(ai_prompt)
                    path = self._save(img_bytes, keyword, position, "png", "local_sd")
                    url  = self._upload_imgbb(path) if self.imgbb_key else None
                    return {"position": position, "path": str(path), "url": url, "alt_text": alt, "source": "local_sd"}
                elif source == "pollinations":
                    img_bytes = self._pollinations(ai_prompt)
                    path = self._save(img_bytes, keyword, position, "jpg", "pollinations")
                    url  = self._upload_imgbb(path) if self.imgbb_key else None
                    return {"position": position, "path": str(path), "url": url, "alt_text": alt, "source": "pollinations"}
                elif source == "gemini":
                    img_bytes = self._gemini_flash_image(ai_prompt)
                    path = self._save(img_bytes, keyword, position, "png", "gemini")
                    url  = self._upload_imgbb(path) if self.imgbb_key else None
                    return {"position": position, "path": str(path), "url": url, "alt_text": alt, "source": "gemini"}
            except Exception as e:
                log.warning(f"  [{source}] 실패: {e}")
        return None

    # ── AI 생성 메서드 ────────────────────────────────────────────

    def _gemini_flash_image(self, prompt: str) -> bytes:
        """Gemini 이미지 생성 — config.yaml의 image_ai_models 순서로 폴백"""
        _IMG_MODELS = IMAGE_AI_MODELS
        last_err: Exception = ValueError("Gemini 이미지 생성 모든 모델 실패")
        for model in _IMG_MODELS:
            try:
                response = self.gemini_client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                    ),
                )
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        data = part.inline_data.data
                        return data if isinstance(data, bytes) else base64.b64decode(data)
                last_err = ValueError(f"{model}: 응답에 이미지 없음")
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    log.warning(f"  [Gemini Image {model}] 한도 초과, 다음 모델 시도")
                else:
                    log.warning(f"  [Gemini Image {model}] 실패: {e}")
                last_err = e
        raise last_err

    def _local_sd(self, prompt: str) -> bytes:
        """Automatic1111 WebUI API — SDXL 로컬 생성
        실행: python launch.py --api --xformers  (12GB)
              python launch.py --api --xformers --medvram  (8GB)
        """
        import os
        a1111_url = os.environ.get("A1111_URL", "http://localhost:7860")
        negative  = (
            "text, watermark, blurry, ugly, deformed, low quality, "
            "cartoon, anime, logo, signature, nsfw"
        )
        payload = {
            "prompt":          prompt,
            "negative_prompt": negative,
            "width":           IMAGE_WIDTH,
            "height":          IMAGE_HEIGHT,
            "steps":           25,
            "cfg_scale":       7.5,
            "sampler_name":    "DPM++ 2M Karras",
        }
        res = requests.post(
            f"{a1111_url}/sdapi/v1/txt2img",
            json=payload,
            timeout=120,
        )
        res.raise_for_status()
        img_b64 = res.json()["images"][0]
        return base64.b64decode(img_b64)

    def _pollinations(self, prompt: str) -> bytes:
        """Pollinations.ai — 무료, 가입 불필요, 클라우드 FLUX (5xx 시 1회 재시도)"""
        encoded = urllib.parse.quote(prompt[:400])  # URL 길이 제한
        seed    = random.randint(1, 99999)
        url     = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?model=flux&width={IMAGE_WIDTH}&height={IMAGE_HEIGHT}&nologo=true&seed={seed}"
        )
        for attempt in range(2):
            res = requests.get(url, timeout=90)
            if res.status_code in (500, 502, 503, 504) and attempt == 0:
                log.warning(f"  [Pollinations] {res.status_code} → 20초 후 재시도")
                time.sleep(20)
                continue
            res.raise_for_status()
            ct = res.headers.get("Content-Type", "")
            if "image" not in ct:
                raise ValueError(f"이미지 아닌 응답: {ct}")
            time.sleep(16)  # 15초/req 제한 준수
            return res.content
        raise ValueError("Pollinations 재시도 실패")

    # ── 스톡 이미지 메서드 (URL만 반환, 다운로드 없음) ────────────

    def _pexels_url(self, query: str) -> str:
        """Pexels API — 월 25,000회 무료, 상업용 허가"""
        res = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": self.pexels_key},
            params={"query": query, "per_page": 3, "orientation": "landscape"},
            timeout=10,
        )
        res.raise_for_status()
        photos = res.json().get("photos", [])
        if not photos:
            raise ValueError("검색 결과 없음")
        photo = random.choice(photos)  # 상위 3개 중 랜덤
        return photo["src"]["large2x"]

    def _unsplash_url(self, query: str) -> str:
        """Unsplash API — 시간당 50회 무료, 상업용 허가"""
        res = requests.get(
            "https://api.unsplash.com/search/photos",
            headers={"Authorization": f"Client-ID {self.unsplash_key}"},
            params={"query": query, "per_page": 3, "orientation": "landscape"},
            timeout=10,
        )
        res.raise_for_status()
        results = res.json().get("results", [])
        if not results:
            raise ValueError("검색 결과 없음")
        photo = random.choice(results)
        return photo["urls"]["regular"]

    def _pixabay_url(self, query: str) -> str:
        """Pixabay API — 시간당 100회 무료, 상업용 허가"""
        res = requests.get(
            "https://pixabay.com/api/",
            params={
                "key":          self.pixabay_key,
                "q":            query,
                "image_type":   "photo",
                "orientation":  "horizontal",
                "per_page":     3,
                "safesearch":   "true",
            },
            timeout=10,
        )
        res.raise_for_status()
        hits = res.json().get("hits", [])
        if not hits:
            raise ValueError("검색 결과 없음")
        photo = random.choice(hits)
        return photo.get("largeImageURL") or photo["webformatURL"]

    # ── 공통 유틸 ────────────────────────────────────────────────

    def _save(self, img_bytes: bytes, keyword: str, position: str, ext: str, source: str) -> Path:
        date_str = datetime.now().strftime("%Y%m%d")
        safe_kw  = re.sub(r"[^\w\-]", "_", keyword)[:20]
        day_dir  = OUTPUT_DIR / date_str
        day_dir.mkdir(parents=True, exist_ok=True)
        idx  = len(list(day_dir.glob(f"{safe_kw}_*.{ext}")))
        path = day_dir / f"{safe_kw}_{position}_{source}_{idx}.{ext}"
        path.write_bytes(img_bytes)
        return path

    def _upload_imgbb(self, img_path: Path) -> str | None:
        """생성 이미지를 imgbb에 업로드 → Notion external image용 공개 URL"""
        b64 = base64.b64encode(img_path.read_bytes()).decode()
        res = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": self.imgbb_key, "image": b64, "name": img_path.stem},
            timeout=30,
        )
        res.raise_for_status()
        url = res.json()["data"]["url"]
        log.info(f"  [imgbb] {url}")
        return url
