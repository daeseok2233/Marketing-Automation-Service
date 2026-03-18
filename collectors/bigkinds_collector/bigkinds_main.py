import os
import glob
from datetime import datetime
from logger import get_logger

logger = get_logger(__name__)

# 재다운로드 주기 정의 (예: 1일이면 매일 다운로드)

class BigKindsCollector:
    def __init__(self):
        from .bigkinds_config import BIGKINDS_DIR, DOWNLOAD_CYCLE_DAYS
        self.data_dir = BIGKINDS_DIR
        self.download_cycle_days = DOWNLOAD_CYCLE_DAYS

    def collect(self) -> dict:
        latest_file_path = None
        needs_download = True

        # bigkinds_*.xlsx 패턴으로 좀 더 구체적인 glob 사용
        files = sorted(
            [f for f in glob.glob(f"{self.data_dir}/bigkinds_*.xlsx")
             if not os.path.basename(f).startswith("~$")], # 임시 파일(~$) 제외
            reverse=True,
        )

        if files:
            latest_file_path = files[0]
            file_name = os.path.basename(latest_file_path)
            try:
                # 파일 이름에서 날짜 부분 추출 (예: "bigkinds_20240318.xlsx" -> "20240318")
                date_str_in_file = file_name.split('_')[-1].split('.')[0]
                file_date = datetime.strptime(date_str_in_file, "%Y%m%d").date()
                today_date = datetime.now().date()

                # 파일 날짜가 재다운로드 주기 내인지 확인
                if (today_date - file_date).days < self.download_cycle_days:
                    logger.info(f"  [BigKinds] 최신 xlsx 파일 확인 ({latest_file_path}) - 재다운로드 주기({self.download_cycle_days}일) 내")
                    needs_download = False # 주기 내이므로 다운로드 필요 없음
                else:
                    logger.info(f"  [BigKinds] 최신 xlsx 파일({latest_file_path})이 주기({self.download_cycle_days}일) 만료. 재다운로드 시도.")
                    needs_download = True # 주기 만료되었으므로 다운로드 필요
            except ValueError:
                logger.warning(f"  [BigKinds] 파일명에서 날짜 파싱 실패: {file_name}. 재다운로드 시도.")
                needs_download = True # 날짜 파싱 실패 시, 일단 다운로드 필요하다고 가정
            except Exception as e:
                logger.error(f"  [BigKinds] 파일 날짜 확인 중 오류 발생: {e}. 재다운로드 시도.")
                needs_download = True

        if not needs_download and latest_file_path:
            return {"source_file": latest_file_path}

        # 다운로드가 필요하거나 (파일이 없거나, 오래되었거나, 날짜 파싱 오류 등)
        logger.info("  [BigKinds] xlsx 파일 없음 또는 주기 만료 - 크롤러 다운로드 시도")
        try:
            from .bigkinds_crawler import download_bigkinds_xlsx
            downloaded = download_bigkinds_xlsx(headless=True)
            if downloaded:
                logger.info(f"  [BigKinds] 다운로드 완료: {downloaded}")
                return {"source_file": str(downloaded)}
        except Exception as e:
            logger.error(f"  [BigKinds] 다운로드 실패: {e}")

        logger.warning(
            f"  [BigKinds] xlsx 확보 실패 — "
            f"bigkinds.or.kr에서 수동 다운로드 후 {self.data_dir}/에 저장"
        )
        return {"source_file": None}
