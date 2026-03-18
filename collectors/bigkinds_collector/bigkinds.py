"""빅카인즈(한국언론진흥재단) — xlsx 파일 확보만 담당

collect() 호출 시:
  1. data/bigkinds/*.xlsx 파일이 있는지 확인
  2. 없으면 bigkinds_crawler.py로 자동 다운로드 시도
  3. 분석은 하지 않음 (활용처가 생기면 그때 추가)
"""
import os
import glob


class BigKindsCollector:
    def __init__(self, data_dir: str = "data/bigkinds"):
        self.data_dir = data_dir

    def collect(self) -> dict:
        files = sorted(
            [f for f in glob.glob(f"{self.data_dir}/*.xlsx")
             if not os.path.basename(f).startswith("~$")],
            reverse=True,
        )

        if files:
            print(f"  [BigKinds] xlsx 확인: {files[0]}")
            return {"source_file": files[0]}

        # xlsx 없으면 크롤러로 다운로드 시도
        print("  [BigKinds] xlsx 없음 — 크롤러 다운로드 시도")
        try:
            from collectors.bigkinds_collector.bigkinds_crawler import download_bigkinds_xlsx
            downloaded = download_bigkinds_xlsx(headless=True)
            if downloaded:
                print(f"  [BigKinds] 다운로드 완료: {downloaded}")
                return {"source_file": str(downloaded)}
        except Exception as e:
            print(f"  [BigKinds] 다운로드 실패: {e}")

        print(
            f"  [BigKinds] xlsx 확보 실패 — "
            f"bigkinds.or.kr에서 수동 다운로드 후 {self.data_dir}/에 저장"
        )
        return {"source_file": None}
