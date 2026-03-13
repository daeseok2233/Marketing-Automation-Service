"""
마크클라우드 블로그 자동화 파이프라인
실행: python main.py
"""
import logging, os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # .env 파일 로드

# ── 로거 설정
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            f"logs/{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8"
        ),
    ],
)
log = logging.getLogger(__name__)

# ── Import
from topic_finder    import TopicFinder
from templates       import build_angle_prompt
from generator       import BlogGenerator, quality_check
from notion_uploader import NotionUploader
from legal_rag       import LegalRAG
from screenshot_tool import capture_markview_search, screenshot_to_notion_block

from collectors.naver_datalab  import NaverDataLabCollector
from collectors.naver_news     import NaverNewsCollector
from collectors.bigkinds       import BigKindsCollector
from collectors.google_trends  import GoogleTrendsCollector
from collectors.kipris         import KIPRISCollector
from collectors.competitor     import CompetitorCollector
from collectors.law_kr         import LawKrCollector

# 브랜드 조회가 필요한 템플릿 키
BRAND_CHECK_TEMPLATES = {"brand-check", "quick-verdict", "brand-story"}

# ── 서비스 정의
SERVICES = {
    "markview":  {"name":"마크뷰",    "usp":"AI 기반 이미지·텍스트 상표 유사 검색, 국내 유일 이미지 검색",  "url":"https://www.markview.co.kr"},
    "markpick":  {"name":"마크픽",    "usp":"셀프 상표 출원 + 변리사 대행, 합리적 비용으로 출원 절차 간소화","url":"https://www.markpick.co.kr"},
    "markpass":  {"name":"마크패스",  "usp":"상표 출원 및 의견제출 자동화 플랫폼, 거절 대응 자동화",        "url":"https://markpass.co.kr"},
    "markcloud": {"name":"마크클라우드","usp":"AI 기반 지식재산권 분석·컨설팅, 기업 브랜드 보호 솔루션",   "url":"https://www.markcloud.co.kr"},
}

POSTS_PER_DAY = 2  # 하루 생성 포스트 수


def collect_all() -> dict:
    raw = {}
    sources = {
        "naver":      NaverDataLabCollector(),
        "naver_news": NaverNewsCollector(),
        "bigkinds":   BigKindsCollector(),
        "google":     GoogleTrendsCollector(),
        "kipris":     KIPRISCollector(),
        "competitor": CompetitorCollector(),
        "law":        LawKrCollector(),
    }
    for name, col in sources.items():
        try:
            raw[name] = col.collect()
            log.info(f"  [OK] {name}")
        except Exception as e:
            log.warning(f"  [SKIP] {name}: {e}")
            raw[name] = {}
    return raw


def run():
    log.info("=" * 50)
    log.info(f" 파이프라인 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info("=" * 50)

    # 1. 데이터 수집
    log.info("[1/4] 데이터 수집")
    raw_data = collect_all()
    news_count = len(raw_data.get("naver_news", {}).get("headlines", []))
    log.info(f"  뉴스 헤드라인 {news_count}건 수집")

    # 1.5. 수집 리포트 노션 업로드
    try:
        NotionUploader().upload_report(raw_data)
        log.info("  수집 리포트 노션 저장 완료")
    except Exception as e:
        log.warning(f"  수집 리포트 저장 실패: {e}")

    # 2. 뉴스재킹 앵글 발굴 (Gemini가 오늘 데이터 전체를 읽고 제안)
    log.info("[2/4] 앵글 발굴 (Gemini)")
    finder = TopicFinder()
    angles = finder.find_angles(raw_data, n=POSTS_PER_DAY)
    for a in angles:
        log.info(f"  앵글: {a.get('title','?')} [{a.get('service_key','')}]")

    # 3. 글 생성
    log.info("[3/4] 글 생성")
    generator = BlogGenerator()
    legal_rag = LegalRAG(raw_data.get("law", {}))
    posts     = []

    # 뉴스 제목 → 링크 매핑 (참고자료 링크 표시용)
    news_link_map = {
        item["title"]: item.get("link", "")
        for item in raw_data.get("naver_news", {}).get("headlines", [])
        if item.get("link")
    }

    kipris_collector = KIPRISCollector()

    for angle in angles:
        svc_key   = angle.get("service_key", "markcloud")
        service   = SERVICES.get(svc_key, SERVICES["markcloud"])
        tpl_key   = angle.get("template_key", "info")
        log.info(f"  → [{service['name']}] {tpl_key}형 — {angle.get('title','?')[:30]}...")

        # ── 브랜드 상표 조회 (brand-check / quick-verdict / brand-story 템플릿)
        brand_name   = angle.get("brand_name") or angle.get("main_keyword", "")
        kipris_brand = {}
        if tpl_key in BRAND_CHECK_TEMPLATES and brand_name:
            try:
                kipris_brand = kipris_collector.search_brand(brand_name)
                log.info(f"  [KIPRIS] '{brand_name}' 조회: {kipris_brand.get('summary','')}")
            except Exception as e:
                log.warning(f"  [KIPRIS] 브랜드 조회 실패: {e}")

        # ── 마크뷰 스크린샷 (image-search-demo + brand-check + quick-verdict)
        SCREENSHOT_TEMPLATES = {"image-search-demo", "brand-check", "quick-verdict"}
        screenshot = {}
        if tpl_key in SCREENSHOT_TEMPLATES:
            try:
                screenshot = capture_markview_search(brand_name or angle.get("main_keyword", ""))
                log.info(f"  [스크린샷] {screenshot.get('path') or screenshot.get('error')}")
            except Exception as e:
                log.warning(f"  [스크린샷] 캡처 실패: {e}")

        legal_context = legal_rag.get_context(angle.get("main_keyword", ""))
        prompt = build_angle_prompt(
            angle, service, raw_data, legal_context,
            kipris_brand=kipris_brand,
            screenshot=screenshot,
        )
        post = generator.generate(prompt)

        if post:
            news_ref  = angle.get("news_reference", "")
            news_link = news_link_map.get(news_ref, "")
            post.update({
                "service_key":    svc_key,
                "template_key":   tpl_key,
                "main_keyword":   angle.get("main_keyword", ""),
                "trend_score":    angle.get("trend_score", 0),
                "news_reference": news_ref,
                "news_link":      news_link,
                "kipris_brand":   kipris_brand,
                "screenshot":     screenshot,
            })
            posts.append(post)
            log.info(f"  [OK] 생성: {post.get('title','?')}")
        else:
            log.warning(f"  [FAIL] 생성 실패: {angle.get('title','?')[:30]}")

    # 4. 품질 검수 + 노션 업로드
    log.info("[4/4] 품질 검수 + 업로드")
    uploaded = 0
    try:
        uploader = NotionUploader()
        for p in posts:
            ok, reason = quality_check(p)
            if not ok:
                log.warning(f"  [SKIP] 품질 미달: {p.get('title','?')} — {reason}")
                continue
            try:
                uploader.upload(p)
                uploaded += 1
            except Exception as e:
                log.error(f"  [ERROR] 업로드 실패: {e}")
    except EnvironmentError as e:
        log.error(f"  [ERROR] 노션 설정 오류: {e}")

    log.info("=" * 50)
    log.info(f" 완료: {uploaded}/{POSTS_PER_DAY}개 저장")
    log.info("=" * 50)


if __name__ == "__main__":
    run()
