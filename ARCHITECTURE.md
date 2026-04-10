# 블로그 자동화 파이프라인 아키텍처

## 개요

마크클라우드(상표 출원·검색 서비스) 홍보를 위한 **네이버 블로그 자동 생성·발행 시스템**.
자동 발행 대상은 `blog_02 ~ blog_07` 6개 계정. (blog_01은 수동 운영, 자동화 제외)

매일:
1. **05:00** — 뉴스/행사 데이터 수집
2. **05:10** — LLM이 모든 기사를 한 번에 평가 → 블로그별 발행 큐 생성
3. **06:00 ~ 22:00** — 블로그별 시간대에 맞춰 큐에서 1건씩 생성 + 발행

---

## 디렉토리 구조

```
blog_pipeline/
│
├── app.py                       # Streamlit 대시보드 (수동 단계별 실행)
├── scheduler.py                 # 멀티 블로그 자동 발행 스케줄러
├── model.py                     # LLM 인터페이스 (Gemini 2.5 Flash 다중 키 + Ollama 폴백)
├── save_naver_cookies.py        # 네이버 수동 로그인 → 쿠키 저장
├── ARCHITECTURE.md
├── requirements.txt
├── .env                         # API 키 (GEMINI_API_KEYS, NAVER_*, SLACK_WEBHOOK_URL)
│
├── blog_generator/              # 발행 파이프라인 전체 (UI + 로직 통합)
│   ├── __init__.py
│   │
│   │  # ── 4단계 UI/로직 모듈 ──
│   ├── collect.py               #   1) 일일 데이터 수집 UI + 로직
│   ├── plan.py                  #   2) 글 기획 (LLM 평가 + 블로그별 큐 라우팅)
│   ├── generate.py              #   3) 글 생성 (LLM 본문 작성 + 슬롯 파싱)
│   ├── publish.py               #   4) 네이버 발행 (UI render() + CLI subprocess 통합)
│   ├── tabs.py                  #     상세 테스트 탭 (행사/상권/트렌딩 등)
│   │
│   │  # ── 발행 인프라 ──
│   ├── naver_session.py         #   네이버 Playwright 세션 매니저 (get_session, _check_login)
│   ├── slack_notify.py          #   발행 성공/실패/쿠키만료 슬랙 알림
│   │
│   │  # ── 보조 모듈 ──
│   ├── quality_checker.py       #   글 품질 검증
│   ├── region_selector.py       #   지역 선정
│   └── thumbnail_maker.py       #   썸네일 자동 생성 (950×950)
│
├── collectors/                  # 저수준 데이터 수집 라이브러리
│   ├── daily_news.py            #   네이버 뉴스 API + Google News RSS (활성)
│   ├── naver_events.py          #   네이버 검색 크롤링 — 축제/박람회 (활성)
│   ├── naver_suggest.py         #   네이버 자동완성
│   ├── naver_datalab.py         #   네이버 데이터랩 검색 트렌드
│   ├── naver_news.py            #   네이버 뉴스 검색
│   ├── google_trending.py       #   구글 실시간 트렌딩
│   ├── google_trends.py         #   구글 트렌드
│   ├── competitor.py            #   경쟁 블로그 분석
│   ├── bigkinds.py              #   한국언론진흥재단 뉴스
│   ├── bigkinds_crawler.py      #
│   ├── kipris.py                #   특허청 KIPRIS 상표 통계
│   └── public_events.py         #   공공데이터 축제/행사 API
│
└── data/
    ├── service_data/
    │   ├── blogs.json           #   블로그 계정 + theme + templates 매핑
    │   ├── services.json        #   마크뷰/마크패스/마크픽 서비스 정보
    │   ├── regions.json         #   지역 풀
    │   └── event.json
    │
    ├── templates/               #   콘텐츠 템플릿 (16개 파일, 활성 10개)
    │   │
    │   │  # ── 활성: 기사 의존형 (스케줄러가 사용) ──
    │   ├── local_event.json     #     지역 행사/축제 (지역 필수)
    │   ├── local_issue.json     #     지역 사건/이슈 (지역 필수)
    │   ├── local_trend.json     #     지역 트렌드 (지역 필수)
    │   ├── event.json           #     일반 사건/이슈
    │   ├── newsjacking.json     #     트렌딩 키워드 연결
    │   ├── dispute_report.json  #     상표 분쟁 사례
    │   ├── warning.json         #     위험 사례 경고
    │   ├── policy.json          #     정책/법령 변경 ★ NEW
    │   ├── statistics.json      #     통계/데이터 분석 ★ NEW
    │   ├── success_story.json   #     성공 사례 분석 ★ NEW
    │   │
    │   │  # ── 비활성: 일반 가이드형 (기사 무관, plan에서 제외) ──
    │   ├── beginner.json
    │   ├── info.json
    │   ├── howto.json
    │   ├── checklist.json
    │   ├── faq.json
    │   ├── myth.json
    │   ├── compare.json
    │   ├── column.json
    │   └── 00_base.json
    │
    ├── image/
    │   ├── basic/               #   서비스 소개 이미지
    │   ├── event/               #   쿠폰/이벤트 이미지
    │   ├── thumbnail_bg/        #   썸네일 배경 (네이버 이미지 검색 캐시)
    │   ├── blog_links.json      #   블로그별 cutt.ly 링크 매핑
    │   └── image_list.csv       #   이미지 ↔ 링크 매핑
    │
    ├── collected/               #   일일 수집 데이터 (YYYYMMDD_daily_news.json, _events.json)
    ├── plans/                   #   블로그별 발행 큐 (YYYYMMDD_blog_XX.json)
    ├── generated/               #   생성 로그, 썸네일, 스케줄러 로그
    ├── browser_profiles/        #   Playwright persistent context (계정별 폴더)
    ├── naver_blog_cookies_blog_XX.json  # 블로그별 쿠키 백업
    └── schedule_state.json      #   발행 이력 (7일 롤링)
```

---

## 4단계 파이프라인

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. COLLECT — 일일 데이터 수집                                       │
│  collectors/daily_news.py + collectors/naver_events.py               │
│  → data/collected/{date}_daily_news.json, _events.json               │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  2. PLAN — 기사 평가 + 블로그별 큐 라우팅                            │
│  blog_generator/plan.py                                              │
│                                                                      │
│  ① evaluate_all_articles(max_evaluate=200)                           │
│      모든 기사를 한 번에 LLM 평가 (1세트, 6 블로그 공유)             │
│      각 기사 → {score, template, reason}                             │
│      90점 이상 + 유효 템플릿만 통과                                  │
│                                                                      │
│  ② assign_to_blogs(scored, BLOG_CONFIGS)                             │
│      각 블로그의 templates 리스트와 매칭되는 기사를                  │
│      점수순으로 배정. 같은 기사가 여러 블로그에 들어갈 수 있음       │
│                                                                      │
│  → data/plans/{date}_blog_XX.json (블로그별 발행 큐)                 │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  3. GENERATE — 블로그별 본문 생성                                    │
│  blog_generator/generate.py — generate_post(article, template,       │
│                                              blog_id, reason)        │
│                                                                      │
│  build_generation_prompt():                                          │
│    블로그 theme(타겟 연령/톤) + 템플릿 prompt_template +             │
│    레퍼런스 기사를 합쳐서 LLM에 전달                                 │
│                                                                      │
│  _parse_llm_output():                                                │
│    "제목:", "소제목:", 본문, 해시태그를 슬롯으로 분해                │
│                                                                      │
│  → {title, slots, structure, template}                               │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  4. PUBLISH — 네이버 블로그 발행                                     │
│  blog_generator/publish.py — publish_post(post, blog_id,             │
│                                            cookie_blog_id)           │
│                                                                      │
│  _do_publish(data):                                                  │
│    - naver_session.get_session() — 쿠키 로드된 Playwright 브라우저   │
│    - 글쓰기 페이지 이동 → 제목/본문 입력                             │
│    - structure 순서대로 명령 실행:                                   │
│      · image: 썸네일 자동 생성, 쿠폰/카카오 이미지 + cutt.ly 링크    │
│      · heading: 글자크기 변경 + 굵게 + 본문                          │
│      · text: 줄 단위 입력                                            │
│      · hashtags: 해시태그 입력                                       │
│    - 발행 버튼 + 확인 다이얼로그                                     │
│    - URL 회수 → slack_notify.notify_success/fail                     │
│                                                                      │
│  → published URL                                                     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 핵심 설계: 한 번 평가 → 여러 블로그 라우팅

기존 방식은 블로그마다 따로 LLM이 평가했지만, 새 방식은 **모든 기사를 한 번만 평가**하고
점수+템플릿을 기준으로 블로그별 큐에 배정한다. **LLM 비용 1/6.**

### 라우팅 예시

평가 결과:
| 기사 | 점수 | 템플릿 |
|---|---|---|
| A. "특허청 수수료 인하" | 95 | policy |
| B. "강릉 카페 트렌드" | 93 | local_trend |
| C. "BTS 굿즈 단속" | 92 | newsjacking |
| D. "스타트업 100억 투자" | 91 | success_story |

블로그별 templates (`data/service_data/blogs.json`):
- blog_02: `policy, newsjacking, event`
- blog_03: `policy, statistics, success_story, dispute_report, warning, newsjacking`
- blog_04~07: `local_event, local_issue, local_trend`

배치 결과:
| 블로그 | 큐 |
|---|---|
| blog_02 | A, C |
| blog_03 | A, C, D |
| blog_04~07 | B (4개 블로그 모두 동일) |

→ 기사 A 한 건이 blog_02·03에 동시 발행 (각 블로그의 theme/타겟 연령에 맞춰 톤만 다름)
→ 기사 B 한 건이 blog_04~07에 동시 발행 (20대/30대/40대/50대 톤 다름)

---

## 슬롯 기반 글 생성

### 1) 템플릿 structure (data/templates/*.json)
```json
[
  {"type": "image",   "content": "썸네일 (자동생성)", "fixed": true},
  {"type": "blank"},
  {"type": "text",    "size": 15, "slot": "도입"},
  {"type": "heading", "size": 19, "slot": "소제목1"},
  {"type": "text",    "size": 15, "slot": "본문1"},
  {"type": "heading", "size": 19, "slot": "소제목2"},
  {"type": "text",    "size": 15, "slot": "본문2"},
  {"type": "text",    "size": 15, "slot": "QA"},
  {"type": "image",   "content": "할인쿠폰 (image_mark_pick_coupon.png)", "fixed": true},
  {"type": "image",   "content": "카카오상담 (image_mark_pick_kakao.png)", "fixed": true},
  {"type": "hashtags","slot": "해시태그"}
]
```

### 2) 템플릿 prompt_template (LLM 가이드)
```
제목: {30자 이내, 정책명·제도명 포함}

{도입: 어떤 정책이 어떻게 바뀌는지 + 시행 시점 / 150자}

소제목: {바뀌는 핵심 내용}
{본문: 변경 사항 상세 설명, 출처 인용 / 300자}
...
```

### 3) LLM 응답
```
제목: 특허청 수수료 인하, 사장님 출원 부담 줄어
도입: 2026년 4월부터 특허청이...
소제목: 무엇이 바뀌나
본문1: 출원 수수료가 기존 56,000원에서...
...
```

### 4) 파서가 (title, slots) 추출
```python
{
  "title": "특허청 수수료 인하, 사장님 출원 부담 줄어",
  "slots": {
    "도입": "2026년 4월부터 특허청이...",
    "소제목1": "무엇이 바뀌나",
    "본문1": "출원 수수료가 기존 56,000원에서...",
    ...
  }
}
```

### 5) Playwright가 structure 순서대로 발행
```
썸네일 이미지 삽입
→ 도입 텍스트 입력 (15pt)
→ "무엇이 바뀌나" 입력 (19pt 굵게)
→ 본문1 입력 (15pt)
→ ...
→ 쿠폰 이미지 (cutt.ly 링크 포함)
→ 카카오 이미지
→ 해시태그
```

---

## 스케줄러 동작

### 시간표 (`scheduler.py` 상단 상수로 조정 가능)
| 시각 | 동작 |
|---|---|
| 05:00 | `run_collect()` — 뉴스 + 행사 수집 |
| 05:10 | `run_plan_all()` — 모든 기사 평가 + 블로그별 큐 생성 |
| 06:00 ~ 22:00 | `publish_one(blog_id)` — 라운드로빈으로 큐에서 1건씩 발행 |

### 자동 가드
스케줄러는 시작 시점에 미완료 단계가 있으면 즉시 실행:
- `ensure_collected()` — 오늘 뉴스 파일 없으면 즉시 수집
- `ensure_planned()` — 오늘 큐 파일 없으면 즉시 평가+배정

→ 한밤중에 시작해도, 점심에 시작해도 그 시점부터 정상 동작.

### BLOG_CONFIGS
| 블로그 | 일일 발행 | 간격 |
|---|---|---|
| blog_02~06 | 10개 | 30~45분 |
| blog_07 | 20개 | 20~35분 |

총 70개/일.

---

## LLM 모델 (model.py)

```
Gemini (GCP 크레딧):
  1. gemini-2.5-flash
  2. gemini-2.5-flash-lite
  3. gemini-2.0-flash-001
  4. gemini-1.5-flash
  × N개 API 키 순환 (GEMINI_API_KEYS=key1,key2,...)

전부 실패 시 → Ollama (로컬 qwen2.5:14b)
```

---

## 발행 인프라 (Streamlit/Playwright 분리)

Streamlit 이벤트 루프와 Playwright sync API가 충돌하므로 발행은 **항상 별도 프로세스**.

`blog_generator/publish.py`는 한 파일에서 두 역할:
- `render()` — Streamlit UI 버튼 (대시보드용)
- `_run_publish(json_path)` / `python -m blog_generator.publish` — subprocess 진입점
- `_do_publish(data)` — 실제 Playwright 로직 (UI/CLI/스케줄러 공통)
- `publish_post(post, blog_id, cookie_blog_id)` — 스케줄러용 dict 진입점

스케줄러는 별도 프로세스이므로 subprocess 없이 `publish_post()` 직접 호출.

---

## 운영 명령어

```bash
# 자동 발행 (메인)
python scheduler.py

# 수동 단계별 (Streamlit 대시보드)
streamlit run app.py

# 네이버 쿠키 갱신 (블로그별)
python save_naver_cookies.py blog_02
python save_naver_cookies.py blog_03
# ... blog_07까지

# 단건 발행 (JSON 파일에서)
python -m blog_generator.publish <json_file>
```

---

## 주요 데이터 파일

| 파일 | 역할 |
|---|---|
| `data/collected/{date}_daily_news.json` | 일일 수집 뉴스 (네이버 + 구글) |
| `data/collected/{date}_events.json` | 일일 수집 행사/축제 |
| `data/plans/{date}_blog_XX.json` | 블로그별 발행 큐 (1건 발행 시 1건 pop) |
| `data/schedule_state.json` | 발행 이력 (7일 롤링, 중복 방지) |
| `data/generated/{date}_scheduler_log.json` | 스케줄러 실행 로그 |
| `data/naver_blog_cookies_blog_XX.json` | 블로그별 네이버 로그인 쿠키 백업 |
| `data/service_data/blogs.json` | 블로그 계정 + theme + templates 매핑 |
