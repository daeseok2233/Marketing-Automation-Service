"""
마크클라우드 블로그 자동화 파이프라인
실행: python main.py
"""
import logging, os, sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # .env 파일 로드

# Windows cp949 콘솔에서 유니코드 문자(em dash 등) 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
from config          import TEMPLATES as ALL_TEMPLATES
from topic_finder    import TopicFinder
from templates       import build_angle_prompt
from generator       import BlogGenerator, quality_check
from notion_uploader import NotionUploader
from legal_rag       import LegalRAG
from screenshot_tool  import capture_markview_search, screenshot_to_notion_block
from image_generator  import ImageGenerator
from blog_accounts   import load_accounts

from collectors.naver_datalab  import NaverDataLabCollector
from collectors.naver_news     import NaverNewsCollector
from collectors.bigkinds       import BigKindsCollector
from collectors.google_trends  import GoogleTrendsCollector
from collectors.kipris         import KIPRISCollector
from collectors.competitor     import CompetitorCollector
from collectors.law_kr         import LawKrCollector

# ── 서비스 정의
SERVICES = {
    "markview":  {"name":"마크뷰",      "usp":"국내 유일 AI 이미지 상표 검색 + 텍스트 유사 검색, KIPRIS 연동 무제한 상세 검색",         "url":"https://www.markview.co.kr"},
    "markpick":  {"name":"마크픽",      "usp":"셀프 출원 + 서울대 출신 변리사 대행, Standard 월 10만원부터 합리적 비용으로 상표 출원",  "url":"https://www.markpick.co.kr"},
    "markpass":  {"name":"마크패스",    "usp":"AI 출원서 자동 작성·KIPRIS 500만 건 DB·거절 대응(의견서·보정서)·마드리드 국제출원 자동화","url":"https://markpass.co.kr"},
    "markcloud": {"name":"마크클라우드","usp":"브랜드 네이밍 AI 생성 + 상표 침해 가능성 분석 + 위조상품 온라인 모니터링 종합 솔루션",   "url":"https://www.markcloud.co.kr"},
}

POSTS_PER_DAY = len(ALL_TEMPLATES)  # config.yaml의 templates 개수


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
    angles = finder.find_angles(raw_data, n=POSTS_PER_DAY, required_templates=ALL_TEMPLATES)
    for a in angles:
        log.info(f"  앵글: {a.get('title','?')} [{a.get('service_key','')}]")

    # 3. 글 생성
    log.info("[3/4] 글 생성")
    generator    = BlogGenerator()
    img_gen      = ImageGenerator()
    legal_rag    = LegalRAG(raw_data.get("law", {}))
    blog_accounts = load_accounts()
    posts        = []
    log.info(f"  블로그 계정 {len(blog_accounts)}개 로드: {', '.join(blog_accounts.keys())}")

    # 뉴스 제목 → 링크 매핑 (참고자료 링크 표시용)
    news_link_map = {
        item["title"]: item.get("link", "")
        for item in raw_data.get("naver_news", {}).get("headlines", [])
        if item.get("link")
    }

    # 서비스 키 → 블로그 계정 매핑
    # 지역 블로그(naver_region_*)는 아래 확장 키로 앵글에 service_key 지정 시 활용
    SERVICE_ACCOUNT_MAP = {
        "markview":          "naver_brand_people",    # 마크뷰 → 브랜드하는 사람들
        "markpick":          "naver_trademark_apply", # 마크픽 → 상표출원·등록·중간사건
        "markpass":          "naver_attorney_jeong",  # 마크패스 → 정상일 변리사
        "markcloud":         "naver_brand_people",    # 마크클라우드 → 브랜드하는 사람들
        # 지역 특화 앵글용 (TopicFinder가 서비스 키를 아래로 지정 시 작동)
        "markpass_seoul":    "naver_region_seoul",
        "markpass_gyeonggi": "naver_region_gyeonggi",
        "markpass_busan":    "naver_region_busan",
    }

    for angle in angles:
        svc_key   = angle.get("service_key", "markcloud")
        service   = SERVICES.get(svc_key, SERVICES["markcloud"])
        tpl_key   = angle.get("template_key", "info")
        log.info(f"  → [{service['name']}] {tpl_key}형 — {angle.get('title','?')[:30]}...")

        # ── 블로그 계정 선택
        acct_id      = SERVICE_ACCOUNT_MAP.get(svc_key, "naver_brand_people")
        blog_account = blog_accounts.get(acct_id, {})

        # ── 마크뷰 스크린샷 (image-search-demo 템플릿)
        screenshot = {}
        if tpl_key == "image-search-demo":
            try:
                screenshot = capture_markview_search(angle.get("main_keyword", ""))
                log.info(f"  [스크린샷] {screenshot.get('path') or screenshot.get('error')}")
            except Exception as e:
                log.warning(f"  [스크린샷] 캡처 실패: {e}")

        legal_context = legal_rag.get_context(angle.get("main_keyword", ""))
        prompt = build_angle_prompt(
            angle, service, raw_data, legal_context,
            screenshot=screenshot,
            blog_account=blog_account,
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
                "screenshot":     screenshot,
            })

            # ── 이미지 생성 (IMAGE_GENERATION=true 시 활성화)
            images = img_gen.generate_for_post(post)
            if images:
                post["images"] = images
                log.info(f"  [이미지] {len(images)}개 생성")
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
    log.info(f" 완료: {uploaded}/{len(angles)}개 저장 (템플릿 {len(ALL_TEMPLATES)}종)")
    log.info("=" * 50)


if __name__ == "__main__":
    run()
