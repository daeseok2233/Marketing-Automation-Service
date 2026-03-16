from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

# ========================
# GEMINI 설정
# ========================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash-lite"

# ========================
# 경로
# ========================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
KNOW_DIR = DATA_DIR / "knowledge"
REFERENCE_DIR = DATA_DIR / "reference"
TEMPLATES_DIR = DATA_DIR / "templates"
IMAGES_DIR = DATA_DIR / "images"
LOG_DIR = BASE_DIR / "logs"

# 필요한 폴더 자동 생성
for _dir in [DATA_DIR, REFERENCE_DIR, TEMPLATES_DIR, IMAGES_DIR, LOG_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)