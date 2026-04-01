# 블로그 자동화 파이프라인 아키텍처

## 개요

마크클라우드 서비스(상표 출원/검색) 홍보를 위한 **네이버 블로그 자동 생성 + 발행 시스템**.
6개 블로그 계정(blog_02~07)에 하루 10~20개씩 AI 생성 글을 자동 발행한다.

---

## 디렉토리 구조

```
blog_pipeline/
│
├── run.py                    # CLI 진입점 (collect / generate / local / all)
├── scheduler.py              # 멀티 블로그 자동 발행 스케줄러
├── model.py                  # LLM 인터페이스 (Gemini → Ollama 폴백)
├── save_naver_cookies.py     # 네이버 수동 로그인 → 쿠키 저장
├── test_all_blogs.py         # 전체 블로그 테스트
├── requirements.txt
├── .env                      # API 키, 인증 정보
│
├── collectors/               # [1단계] 데이터 수집
│   ├── __init__.py           #   collect_all() — 전체 수집 오케스트레이션
│   ├── naver_suggest.py      #   네이버 자동완성 + 연관 키워드
│   ├── naver_news.py         #   네이버 뉴스 API + Google News RSS
│   ├── naver_datalab.py      #   네이버 데이터랩 검색 트렌드
│   ├── google_trends.py      #   구글 트렌드 (3개월 관심도)
│   ├── google_trending.py    #   구글 실시간 트렌딩
│   ├── competitor.py         #   경쟁 블로그 분석
│   ├── bigkinds.py           #   한국언론진흥재단 뉴스
│   ├── bigkinds_crawler.py   #   빅카인즈 자동 다운로드
│   ├── kipris.py             #   특허청 KIPRIS 상표 통계
│   └── law_kr.py             #   상표법 조문 (30일 캐시)
│
├── blog_generator/           # [2단계] 글 생성
│   ├── __init__.py
│   ├── topic_selector.py     #   주제 선정 (LLM 기반)
│   ├── reference_builder.py  #   레퍼런스 데이터 추출
│   ├── prompt_builder.py     #   시스템/유저 프롬프트 구성
│   ├── writer.py             #   글 생성 (LLM 호출)
│   ├── legal_checker.py      #   법률 인용 검증
│   ├── planner.py            #   지역 블로그 AI 플래너 (10개 주제 일괄 계획)
│   ├── local_blog_writer.py  #   지역 블로그 글 생성
│   └── thumbnail_maker.py    #   썸네일 자동 생성 (950x950)
│
├── publisher/                # [3단계] 발행
│   ├── __init__.py
│   ├── naver_blog.py         #   네이버 블로그 자동 발행 (Playwright)
│   ├── blog_formatter.py     #   마크다운 → 네이버 에디터 명령 변환
│   ├── docx_exporter.py      #   Word 파일 내보내기
│   ├── notion_upload.py      #   노션 데이터베이스 업로드
│   └── process_logger.py     #   파이프라인 과정 로그
│
└── data/
    ├── service_data/
    │   ├── blogs.json        #   7개 블로그 계정 설정 (테마, 템플릿, URL)
    │   ├── services.json     #   마크클라우드 서비스 정보
    │   └── event.json        #   현재 진행중 이벤트/프로모션
    │
    ├── templates/            #   14개 콘텐츠 템플릿
    │   ├── 00_base.json      #     기본 구조
    │   ├── howto.json        #     절차 가이드
    │   ├── checklist.json    #     체크리스트
    │   ├── compare.json      #     비교 분석
    │   ├── faq.json          #     FAQ
    │   ├── column.json       #     전문가 칼럼
    │   ├── warning.json      #     경고/주의
    │   ├── myth.json         #     오해 바로잡기
    │   ├── beginner.json     #     초보자용
    │   ├── info.json         #     정보 교육
    │   ├── event.json        #     이벤트
    │   ├── dispute_report.json#    분쟁 사례
    │   ├── local_trend.json  #     지역 트렌드
    │   ├── local_event.json  #     지역 행사
    │   └── local_issue.json  #     지역 이슈
    │
    ├── collected/            #   일일 수집 데이터 (YYYYMMDD_*.csv)
    ├── generated/            #   생성된 글, 썸네일, 스크린샷
    ├── image/                #   서비스 이미지, 썸네일 배경
    │   ├── basic/            #     로고, 배너, CTA 이미지
    │   ├── event/            #     이벤트 이미지 (쿠폰 등)
    │   ├── thumbnail_bg/     #     썸네일 배경 (매 글마다 갱신)
    │   └── image_list.csv    #     이미지 ↔ 링크 매핑
    │
    ├── legal_cache/          #   상표법 조문 캐시
    ├── bigkinds/             #   빅카인즈 다운로드 데이터
    ├── browser_profiles/     #   Playwright 브라우저 프로필
    ├── naver_blog_cookies_*.json  # 네이버 쿠키 백업
    └── schedule_state.json   #   발행 이력 (7일 롤링)
```

---

## 전체 파이프라인 흐름

```
┌─────────────────────────────────────────────────────────────┐
│  scheduler.py — run_forever()                               │
│  매일 00:00~23:59, 블로그별 간격에 맞춰 publish_one() 호출  │
└────────────────────────┬────────────────────────────────────┘
                         │
                    publish_one(blog_id)
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ① AI 플래너      ② 데이터 수집    ③ 글 생성
   (planner.py)    (search_for_topic) (local_blog_writer.py)
   주제 1개 계획    뉴스/블로그 검색    LLM으로 본문 생성
         │               │               │
         └───────────────┼───────────────┘
                         │
                    ④ 품질 검증
                    1000자 미만? → 재생성 (최대 3회)
                    끊긴 글? → 재생성
                         │
                    ⑤ 네이버 발행
                    (naver_blog.py)
                    Playwright로 에디터 조작
                         │
                    ⑥ 이력 저장
                    schedule_state.json
```

---

## 스케줄러 설정

| 블로그 | 하루 목표 | 간격 | 용도 |
|--------|----------|------|------|
| blog_02 | 10개 | 1~2시간 | 실무 중심 (howto, checklist, compare) |
| blog_03 | 10개 | 1~2시간 | 전문가 칼럼 (column, dispute_report, warning) |
| blog_04 | 10개 | 1~2시간 | 지역 블로그 (local_event, local_issue, local_trend) |
| blog_05 | 10개 | 1~2시간 | 지역 블로그 |
| blog_06 | 10개 | 1~2시간 | 지역 블로그 |
| blog_07 | 20개 | 30~42분 | 지역 블로그 |

---

## LLM 모델 전략

```
Gemini (무료) 시도 순서:
  1. gemini-2.5-flash
  2. gemini-2.5-flash-lite
  3. gemini-2.5-pro
  4. gemini-2.0-flash
  5. gemini-2.0-flash-lite

  × N개 API 키 순환

  전부 실패 시 → Ollama (로컬)
  모델: qwen2.5:14b
```

---

## 네이버 발행 방식

Playwright로 네이버 블로그 에디터를 직접 조작:

1. **세션 관리**: 단일 브라우저에서 블로그별 컨텍스트 유지 (쿠키 기반)
2. **마크다운 → 명령 변환**: `blog_formatter.py`가 마크다운을 에디터 명령으로 변환
3. **명령 종류**: text, bold_text, heading, image, blank_line, hashtags
4. **이미지 처리**: 썸네일(자동생성) + 서비스 소개 이미지 + 쿠폰 이미지
5. **이미지 링크**: `image_list.csv`에서 이미지 → URL 매핑
6. **발행 감지**: 발행 버튼 클릭 → URL 전환 대기 → 블로그 홈 확인

---

## 주요 데이터 파일

### blogs.json
블로그별 설정 (테마, 허용 템플릿, 네이버 ID, URL)

### templates/*.json
각 템플릿에 포함된 정보:
- `structure`: 섹션 순서 및 가이드라인
- `writing_rules`: 필수 규칙
- `image_layout`: 이미지 배치 규칙
- `prompt_structure`: LLM에게 전달할 구조
- `length`: 글자수 범위 (min/max)
- `is_local`: 지역 블로그 여부

### schedule_state.json
발행 이력 (7일 롤링):
```json
{
  "blog_02": [
    {"date": "20260401", "region": "", "business": "", "title": "...", "template": "howto"},
    ...
  ]
}
```

---

## 운영 명령어

```bash
# 스케줄러 시작 (자동 발행)
python scheduler.py

# 네이버 쿠키 저장 (전체)
python save_naver_cookies.py all

# 데이터 수집만
python run.py collect

# 글 생성만 (범용)
python run.py generate

# 지역 블로그 10개 생성 (blog_04)
python run.py local blog_04 10
```
