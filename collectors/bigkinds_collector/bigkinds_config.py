from config import DOWNLOAD_DIR

BIGKINDS_DIR = DOWNLOAD_DIR / "bigkinds"
BIGKINDS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_CYCLE_DAYS = 7