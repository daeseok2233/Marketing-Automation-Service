from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

# ========================
# GEMINI 설정
# ========================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ========================
# 경로
# ========================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" # 데이터 저장소
DOWNLOAD_DIR = DATA_DIR / "download" # 수집 데이터 저장소
TEMPLATES_DIR = DATA_DIR / "templates" # 템플릿 저장소
IMAGES_DIR = DATA_DIR / "images" # 이미지 저장소
LOG_DIR = DATA_DIR / "log" # 로그 저장소
CACHE_DIR = DATA_DIR / "cache" # 캐시, 쿠키 저장소

# 필요한 폴더 자동 생성
for _dir in [DATA_DIR, DOWNLOAD_DIR, TEMPLATES_DIR, IMAGES_DIR, LOG_DIR, CACHE_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)