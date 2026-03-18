"""국가법령정보센터 Open API — 상표법 조문 (월 1회 업데이트 캐싱)

용도: 블로그 글 작성 시 할루시네이션 방지용 법률 팩트 소스
- 조문은 거의 안 바뀌므로 30일 캐시
- 판례는 수집하지 않음 (필요 시 별도 처리)

API 신청: https://open.law.go.kr
"""
import json
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from config import CACHE_DIR

LAW_BASE = "http://www.law.go.kr/DRF/lawService.do"
TRADEMARK_LAW_MST = "279819"  # 상표법 법령일련번호

CACHE_DAYS = 30  # 월 1회 업데이트


class LawKrCollector:
    def __init__(self):
        self.oc = os.environ.get("LAW_OC", "")

    def get_articles(self) -> list:
        """상표법 조문 반환 (30일 캐시)"""
        cached = self._load_cache()
        if cached is not None:
            return cached

        if not self.oc:
            print("  [법령] LAW_OC 미설정 — VERIFIED 하드코딩만 사용")
            return []

        articles = self._fetch_articles()
        if articles:
            self._save_cache(articles)
        return articles

    # ── 캐시 ─────────────────────────────────────────────────────

    def _cache_path(self) -> Path:
        return CACHE_DIR / "articles.json"

    def _load_cache(self) -> list | None:
        path = self._cache_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(data["cached_at"])
            if datetime.now() - cached_at > timedelta(days=CACHE_DAYS):
                print(f"  [법령] 캐시 만료 ({cached_at.strftime('%Y-%m-%d')}) → API 재호출")
                return None
            print(f"  [법령] 조문 캐시 사용 ({cached_at.strftime('%Y-%m-%d')}, {len(data['items'])}건)")
            return data["items"]
        except Exception:
            return None

    def _save_cache(self, items: list):
        path = self._cache_path()
        data = {
            "cached_at": datetime.now().isoformat(),
            "law_name": "상표법",
            "law_mst": TRADEMARK_LAW_MST,
            "total": len(items),
            "items": items,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [법령] 조문 캐시 저장 ({len(items)}건)")

    # ── API 호출 ─────────────────────────────────────────────────

    def _fetch_articles(self) -> list:
        """상표법 전체 조문 수집"""
        try:
            params = {
                "OC":     self.oc,
                "target": "law",
                "type":   "XML",
                "MST":    TRADEMARK_LAW_MST,
            }
            res = requests.get(LAW_BASE, params=params, timeout=15)
            root = ET.fromstring(res.text)
            articles = []
            for article in root.findall(".//조문단위"):
                num     = article.findtext("조문번호", "").strip()
                title   = article.findtext("조문제목", "").strip()
                header  = article.findtext("조문내용", "").strip()

                # 실제 내용은 <항>/<항내용>에 분리되어 있음
                paragraphs = []
                for hang in article.findall("항"):
                    hang_text = hang.findtext("항내용", "").strip()
                    if hang_text:
                        paragraphs.append(hang_text)

                # 조문내용(제목) + 항내용(본문) 합치기
                content = header
                if paragraphs:
                    content = header + " " + " ".join(paragraphs)

                if num and content:
                    articles.append({
                        "number":  num,
                        "title":   title,
                        "content": content[:1500],
                    })
            print(f"  [법령] 상표법 조문 {len(articles)}건 수집 완료")
            return articles
        except Exception as e:
            print(f"  [법령] 조문 수집 실패: {e}")
            return []
