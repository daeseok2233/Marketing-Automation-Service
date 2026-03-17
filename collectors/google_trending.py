"""Google Trends 실시간 인기 검색어 수집 — 키워드 지정 없이 한국 트렌드 파악

인증 불필요, 무료.
Google Trends RSS에서 한국 실시간 인기 검색어 + 관련 뉴스 제목을 수집한다.
"""
import requests
import xml.etree.ElementTree as ET
from collectors import save_csv

TRENDING_RSS = "https://trends.google.com/trending/rss?geo=KR"
NS = {"ht": "https://trends.google.com/trending/rss"}


class GoogleTrendingCollector:
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; blog-pipeline/1.0)"}

    def collect(self) -> dict:
        try:
            r = requests.get(TRENDING_RSS, headers=self.HEADERS, timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:
            print(f"  [Google Trending] RSS 수집 실패: {e}")
            return {"trends": []}

        trends = []
        for item in root.findall(".//item"):
            title   = item.findtext("title", "").strip()
            traffic = item.findtext("ht:approx_traffic", "", NS).strip()
            pub     = item.findtext("pubDate", "").strip()

            # 관련 뉴스 제목 수집
            news_titles = []
            for ni in item.findall("ht:news_item", NS):
                news_title = ni.findtext("ht:news_item_title", "", NS).strip()
                news_url   = ni.findtext("ht:news_item_url", "", NS).strip()
                if news_title:
                    news_titles.append({"title": news_title, "url": news_url})

            trends.append({
                "keyword": title,
                "traffic": traffic,
                "pub_date": pub,
                "news": news_titles,
            })

        # CSV 저장 — 뉴스 제목은 첫 2개만 컬럼으로
        rows = []
        for t in trends:
            row = {
                "keyword": t["keyword"],
                "traffic": t["traffic"],
                "pub_date": t["pub_date"],
                "news_1": t["news"][0]["title"] if len(t["news"]) > 0 else "",
                "news_1_url": t["news"][0]["url"] if len(t["news"]) > 0 else "",
                "news_2": t["news"][1]["title"] if len(t["news"]) > 1 else "",
                "news_2_url": t["news"][1]["url"] if len(t["news"]) > 1 else "",
            }
            rows.append(row)

        csv_path = save_csv("google_trending", rows)
        print(f"  [Google Trending] {len(trends)}개 인기 검색어 수집, CSV 저장: {csv_path}")

        return {"trends": trends}
