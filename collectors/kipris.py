"""특허청 KIPRIS OpenAPI — 상표 출원 통계 + 브랜드 상표 검색"""
import os, requests, xml.etree.ElementTree as ET
from datetime import datetime

class KIPRISCollector:
    def __init__(self):
        self.api_key  = os.environ.get("KIPRIS_API_KEY", "")
        self.base_url = "http://plus.kipris.or.kr/kipo-api/kipi"

    def collect(self) -> dict:
        year = datetime.now().year
        if not self.api_key:
            return {
                "year": year,
                "total_applications_ytd": 0,
                "annual_benchmark": 270000,
                "note": "KIPRIS_API_KEY 미설정 — 기본값 사용",
            }
        try:
            url = f"{self.base_url}/trademarkInfoSearchService/search"
            params = {
                "query":                "상표",
                "applicationStartDate": f"{year}0101",
                "applicationEndDate":   datetime.now().strftime("%Y%m%d"),
                "ServiceKey":           self.api_key,
                "numOfRows":            1,
            }
            res = requests.get(url, params=params, timeout=15)
            root  = ET.fromstring(res.text)
            total_el = root.find(".//totalCount")
            total = int(total_el.text) if total_el is not None else 0
        except Exception as e:
            print(f"  KIPRIS 경고: {e}")
            total = 0

        result = {
            "year": year,
            "total_applications_ytd": total,
            "annual_benchmark": 270000,
            "source": "특허청 KIPRIS OpenAPI",
        }

        return result

    def search_brand(self, brand_name: str, max_results: int = 5) -> dict:
        """
        특정 브랜드명으로 상표 출원 현황 조회.
        brand-check / quick-verdict / brand-story 템플릿에서 사용.

        반환 예시:
        {
            "brand_name": "쿨피스",
            "found": True,
            "total": 12,
            "items": [
                {
                    "application_number": "4020230012345",
                    "application_date": "2023-05-12",
                    "status": "등록",
                    "applicant": "동원F&B(주)",
                    "goods_class": "32류",
                    "title": "쿨피스"
                }
            ],
            "summary": "쿨피스 관련 상표 12건 출원 확인 (최근 5건 표시)"
        }
        """
        if not self.api_key:
            return {
                "brand_name": brand_name,
                "found": False,
                "total": 0,
                "items": [],
                "summary": f"KIPRIS_API_KEY 미설정 — '{brand_name}' 조회 불가",
            }
        try:
            url = f"{self.base_url}/trademarkInfoSearchService/search"
            params = {
                "query":      brand_name,
                "ServiceKey": self.api_key,
                "numOfRows":  max_results,
                "pageNo":     1,
            }
            res  = requests.get(url, params=params, timeout=15)
            root = ET.fromstring(res.text)

            total_el = root.find(".//totalCount")
            total    = int(total_el.text) if total_el is not None else 0

            items = []
            for item in root.findall(".//item")[:max_results]:
                def t(tag):
                    el = item.find(tag)
                    return el.text.strip() if el is not None and el.text else ""

                items.append({
                    "application_number": t("applicationNumber"),
                    "application_date":   t("applicationDate"),
                    "status":             t("registerStatus") or t("applicationStatus"),
                    "applicant":          t("applicantName"),
                    "goods_class":        t("classificationCode"),
                    "title":              t("title") or t("trademarkName"),
                })

            summary = (
                f"'{brand_name}' 관련 상표 {total}건 출원 확인 (상위 {len(items)}건 표시)"
                if total > 0 else
                f"'{brand_name}' 관련 출원 상표 없음 (미출원 또는 검색어 불일치)"
            )
            return {
                "brand_name": brand_name,
                "found":      total > 0,
                "total":      total,
                "items":      items,
                "summary":    summary,
            }

        except Exception as e:
            return {
                "brand_name": brand_name,
                "found":      False,
                "total":      0,
                "items":      [],
                "summary":    f"'{brand_name}' KIPRIS 조회 오류: {e}",
            }
