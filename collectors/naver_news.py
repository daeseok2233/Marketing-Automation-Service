"""뉴스 헤드라인 수집 — Google News RSS (인증 불필요, 무료)"""
import re
import requests
import xml.etree.ElementTree as ET

# 뉴스재킹에 유용한 광범위 쿼리 (한국어)
SEARCH_QUERIES = [
    "창업", "스타트업", "신제품 출시", "브랜드",
    "기업 뉴스", "마케팅", "특허", "상표",
]

RSS_BASE = "https://news.google.com/rss/search"


class NaverNewsCollector:
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; rss-reader/1.0)"}

    def collect(self) -> dict:
        headlines, seen = [], set()
        for q in SEARCH_QUERIES:
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
                        headlines.append({"query": q, "title": title, "link": link})
            except Exception as e:
                print(f"  [뉴스] {q} 수집 실패: {e}")
        return {"headlines": headlines}

    @staticmethod
    def _clean(text: str) -> str:
        # " - 언론사명" 제거
        text = re.sub(r"\s*-\s*[^-]+$", "", text).strip()
        return re.sub(r"<[^>]+>", "", text).strip()
