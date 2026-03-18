"""뉴스 헤드라인 수집 — 네이버 뉴스 검색 API (1순위) + Google News RSS (폴백)

네이버 뉴스 API: NAVER_CLIENT_ID 필요, 상표/IP 특화 쿼리
Google News RSS: 인증 불필요, 넓은 트렌드 쿼리 (뉴스재킹용)
"""
import os
import re
import requests
import xml.etree.ElementTree as ET
from .utils import save_csv
from config import DOWNLOAD_DIR

# ── 네이버 뉴스 API 쿼리: 상표/IP에 특화된 키워드
NAVER_QUERIES = [
    # 직접 관련
    "상표 출원", "상표 등록", "상표권 침해", "상표 분쟁",
    "상표 소송", "브랜드 보호", "상표법 개정",
    # 업종 연결 (뉴스재킹 소재)
    "프랜차이즈 상표", "해외 상표", "마드리드 의정서",
    "짝퉁 단속", "위조 상품", "지식재산권",
    # 트렌드 (시즌성)
    "창업 브랜드", "스타트업 브랜딩", "IP 투자",
]

# ── Google News RSS 쿼리: 넓은 트렌드 (뉴스재킹 도입부용)
GOOGLE_QUERIES = [
    "상표 분쟁", "브랜드 짝퉁", "특허 소송",
    "프랜차이즈 창업", "스타트업 투자", "신규 브랜드 론칭",
]

RSS_BASE = "https://news.google.com/rss/search"


class NaverNewsCollector:
    NAVER_API = "https://openapi.naver.com/v1/search/news.json"
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; blog-pipeline/1.0)"}

    def __init__(self):
        self.client_id     = os.environ.get("NAVER_CLIENT_ID", "")
        self.client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")

    def collect(self) -> dict:
        headlines = []
        seen = set()

        # 1순위: 네이버 뉴스 검색 API
        if self.client_id:
            naver_results = self._collect_naver_api(seen)
            headlines.extend(naver_results)
            print(f"  [Naver News API] {len(naver_results)}개 수집")

        # 2순위: Google News RSS (폴백 + 추가 트렌드)
        google_results = self._collect_google_rss(seen)
        headlines.extend(google_results)
        print(f"  [Google News RSS] {len(google_results)}개 수집")

        # CSV 저장
        csv_path = save_csv(DOWNLOAD_DIR, "naver_news", headlines)
        print(f"  [News] 총 {len(headlines)}개 헤드라인, CSV 저장: {csv_path}")

        return {"headlines": headlines}

    def _collect_naver_api(self, seen: set) -> list[dict]:
        """네이버 뉴스 검색 API로 상표/IP 특화 뉴스 수집"""
        results = []
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        for query in NAVER_QUERIES:
            try:
                r = requests.get(
                    self.NAVER_API,
                    headers=headers,
                    params={"query": query, "display": 5, "sort": "date"},
                    timeout=8,
                )
                r.raise_for_status()
                for item in r.json().get("items", []):
                    title = self._clean(item.get("title", ""))
                    link  = item.get("originallink", "") or item.get("link", "")
                    desc  = self._clean(item.get("description", ""))
                    pub   = item.get("pubDate", "")
                    if title and title not in seen:
                        seen.add(title)
                        results.append({
                            "source": "naver",
                            "query": query,
                            "title": title,
                            "description": desc[:150],
                            "link": link,
                            "pub_date": pub,
                        })
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    print("  [Naver News] API 인증 실패 — Google RSS로 폴백")
                    break
                print(f"  [Naver News] {query} 경고: {e}")
            except Exception as e:
                print(f"  [Naver News] {query} 수집 실패: {e}")
        return results

    def _collect_google_rss(self, seen: set) -> list[dict]:
        """Google News RSS로 넓은 트렌드 뉴스 수집"""
        results = []
        for q in GOOGLE_QUERIES:
            try:
                r = requests.get(
                    RSS_BASE,
                    params={"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
                    headers=self.HEADERS,
                    timeout=8,
                )
                r.raise_for_status()
                root = ET.fromstring(r.content)
                for item in root.findall(".//item")[:5]:
                    title = self._clean(item.findtext("title", ""))
                    link  = item.findtext("link", "").strip()
                    if title and title not in seen:
                        seen.add(title)
                        results.append({
                            "source": "google",
                            "query": q,
                            "title": title,
                            "description": "",
                            "link": link,
                            "pub_date": item.findtext("pubDate", "").strip(),
                        })
            except Exception as e:
                print(f"  [Google RSS] {q} 수집 실패: {e}")
        return results

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text).strip()
        text = re.sub(r"\s*-\s*[^-]+$", "", text).strip()
        return text
