"""국가법령정보센터 Open API — 상표법 조문 + 판례 수집
LAW_OC 없으면 빈 결과 반환 (파이프라인은 계속 실행)
API 신청: https://open.law.go.kr
"""
import os, requests
import xml.etree.ElementTree as ET

LAW_BASE  = "http://www.law.go.kr/DRF/lawService.do"
PREC_BASE = "http://www.law.go.kr/DRF/lawSearch.do"


class LawKrCollector:
    def __init__(self):
        self.oc = os.environ.get("LAW_OC", "")

    def collect(self) -> dict:
        if not self.oc:
            return {
                "articles": [],
                "cases":    [],
                "note":     "LAW_OC 미설정 — https://open.law.go.kr 에서 인증키 발급 후 .env에 추가",
            }
        articles = self._fetch_trademark_articles()
        cases    = self._fetch_recent_cases()
        return {"articles": articles, "cases": cases}

    # ─────────────────────────────────────────────────────────────
    def _fetch_trademark_articles(self) -> list:
        """상표법 주요 조항 수집"""
        try:
            params = {
                "OC":     self.oc,
                "target": "law",
                "type":   "XML",
                "query":  "상표법",
                "exact":  "1",
            }
            res  = requests.get(LAW_BASE, params=params, timeout=15)
            root = ET.fromstring(res.text)
            articles = []
            for article in root.findall(".//조문단위"):
                num     = article.findtext("조문번호", "").strip()
                title   = article.findtext("조문제목", "").strip()
                content = article.findtext("조문내용", "").strip()
                if num and content:
                    articles.append({
                        "number":  num,
                        "title":   title,
                        "content": content[:400],
                    })
            return articles[:40]
        except Exception as e:
            print(f"  법령 수집 경고: {e}")
            return []

    def _fetch_recent_cases(self) -> list:
        """최근 상표 관련 판례 수집 (최신순 10건)"""
        try:
            params = {
                "OC":      self.oc,
                "target":  "prec",
                "type":    "XML",
                "query":   "상표",
                "display": "10",
                "sort":    "ddes",
            }
            res  = requests.get(PREC_BASE, params=params, timeout=15)
            root = ET.fromstring(res.text)
            cases = []
            for prec in root.findall(".//PrecInfo"):
                summary = prec.findtext("판결요지", "").strip()
                if not summary:
                    continue
                cases.append({
                    "case_name": prec.findtext("사건명",   "").strip(),
                    "case_no":   prec.findtext("사건번호", "").strip(),
                    "date":      prec.findtext("선고일자", "").strip(),
                    "court":     prec.findtext("법원명",   "").strip(),
                    "summary":   summary[:300],
                })
            return cases[:10]
        except Exception as e:
            print(f"  판례 수집 경고: {e}")
            return []
