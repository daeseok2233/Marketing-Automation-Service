# 블로그 자동화 파이프라인 아키텍처

## 개요

마크클라우드 서비스(상표 출원/검색) 홍보를 위한 **네이버 블로그 자동 생성 + 발행 시스템**.
6개 블로그 계정(blog_02~07)에 AI 생성 글을 자동 발행한다.

---

## 디렉토리 구조

```
blog_pipeline/
│
├── scheduler.py              # 멀티 블로그 자동 발행 스케줄러
├── app.py                    # Streamlit 대시보드 (단계별 테스트)
├── model.py                  # LLM 인터페이스 (Gemini + Function Calling)
├── publish_one.py            # 단건 발행 스크립트 (Streamlit용)
├── save_naver_cookies.py     # 네이버 수동 로그인 → 쿠키 저장
├── run.py                    # CLI 진입점
├── .env                      # API 키, 인증 정보
│
├── collectors/               # 데이터 수집
│   ├── __init__.py           #   collect_all() — 전체 수집
│   ├── naver_suggest.py      #   네이버 자동완성
│   ├── naver_news.py         #   네이버 뉴스 API + Google News RSS
│   ├── naver_datalab.py      #   네이버 데이터랩 검색 트렌드
│   ├── google_trends.py      #   구글 트렌드
│   ├── google_trending.py    #   구글 실시간 트렌딩
│   ├── competitor.py         #   경쟁 블로그 분석
│   ├── bigkinds.py           #   한국언론진흥재단 뉴스
│   ├── kipris.py             #   특허청 KIPRIS 상표 통계
│   └── public_events.py      #   공공데이터 축제/행사 API
│
├── blog_generator/           # 글 생성
│   ├── agent_planner.py      #   에이전틱 플래너 (Gemini Function Calling)
│   ├── blog_writer.py        #   슬롯 기반 글 생성
│   ├── quality_checker.py    #   글 품질 검증
│   ├── planner.py            #   기존 플래너 (하위 호환)
│   ├── region_selector.py    #   지역 선정 (행사/트렌딩/랜덤)
│   └── thumbnail_maker.py    #   썸네일 자동 생성 (950x950)
│
├── publisher/                # 발행
│   ├── naver_blog.py         #   네이버 블로그 자동 발행 (Playwright)
│   ├── blog_formatter.py     #   structure → Playwright 명령 변환
│   └── slack_notify.py       #   슬랙 알림 (성공/실패/일일요약)
│
└── data/
    ├── service_data/
    │   ├── blogs.json        #   블로그 계정 설정
    │   ├── services.json     #   마크클라우드 서비스 정보 (프롬프트에 자동 삽입)
    │   └── tones.json        #   톤 설정
    │
    ├── templates/            #   16개 콘텐츠 템플릿
    │   ├── local_event.json  #     지역 행사 → 상권 → 상표 보호
    │   ├── local_trend.json  #     지역 트렌드 분석
    │   ├── local_issue.json  #     지역 이슈 분석
    │   ├── howto.json        #     절차 가이드
    │   ├── checklist.json    #     체크리스트
    │   ├── compare.json      #     비교 분석
    │   ├── faq.json          #     FAQ
    │   ├── newsjacking.json  #     뉴스재킹 (트렌딩 활용)
    │   └── ...               #     기타 (column, warning, myth 등)
    │
    ├── image/
    │   ├── basic/            #   서비스 소개 이미지
    │   ├── event/            #   이벤트 이미지 (쿠폰 등)
    │   ├── blog_links.json   #   블로그별 cutt.ly 링크 매핑
    │   └── image_list.csv    #   이미지 ↔ 링크 매핑
    │
    ├── collected/            #   일일 수집 데이터 (YYYYMMDD_*.csv)
    ├── generated/            #   생성된 글, 썸네일, 로그
    └── schedule_state.json   #   발행 이력 (7일 롤링)
```

---

## 전체 파이프라인 흐름

```
┌─────────────────────────────────────────────────────────┐
│  scheduler.py — run_forever()                           │
│  매일 00:00~23:59, 블로그별 간격에 맞춰 publish_one()   │
└──────────────────────┬──────────────────────────────────┘
                       │
                  publish_one(blog_id)
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
 ① 에이전틱 플래너   (또는 기존 플래너)
 (agent_planner.py)
 Gemini가 API 도구를   planner.py +
 스스로 선택해서       region_selector.py
 정보 수집 + 주제 결정
       │
       ▼
 ② 글 생성 (blog_writer.py)
 template structure의 {} 슬롯에
 LLM이 텍스트만 채움
       │
       ▼
 ③ 품질 검증 (quality_checker.py)
 실패 시 최대 3회 재생성
       │
       ▼
 ④ structure → Playwright 명령 (blog_formatter.py)
 마크다운 중간 단계 없이 structure에서 직접 변환
 폰트 크기, 인용구 스타일, 구분선 등 정확히 반영
       │
       ▼
 ⑤ 네이버 발행 (naver_blog.py)
 Playwright로 에디터 조작
       │
       ▼
 ⑥ 슬랙 알림 + 이력 저장
```

---

## 핵심 구조: 슬롯 기반 글 생성

### template structure (설계도)
```json
{"type": "image", "content": "썸네일 (자동생성)", "fixed": true},
{"type": "heading", "size": 19, "content": "행사 소개"},
{"type": "text", "content": "행사 소개 (언제, 어디서, 누가) / 200자"},
{"type": "quote", "style": 3, "content": "핵심 경고 메시지 / 30자"},
{"type": "image", "content": "서비스소개 이미지 중 1개 선택"},
{"type": "hashtags", "content": "지역명 포함 10개"}
```

### LLM에게 보내는 프롬프트
```
[1] 행사 소개 (언제, 어디서, 누가 주최) / 200자
[2] 상권 영향 (유동인구, 경쟁 심화) / 200자
[3] 상표등록 필요성 + 마크뷰/마크픽 안내 / 300자
...
```

### LLM 응답
```
제목: 해운대 축제 시즌, 사장님 상표등록은?
[1] 2026 해운대 수산물 축제가 4월 11일부터...
[2] 50만 명의 방문객이 예상되며...
[3] 마크뷰로 상호명 검색, 마크픽으로 출원(10만원)...
```

### 코드가 조립 (structure + 슬롯 → Playwright 명령)
```
썸네일 이미지 삽입
→ H19 "행사 소개" 입력 (폰트 19pt)
→ [1] 텍스트 입력
→ 이미지 삽입 (cutt.ly 링크 포함)
→ H19 "사장님, 상표등록은?" 입력
→ [3] 텍스트 입력
→ 쿠폰 이미지 삽입
→ 해시태그 입력
```

---

## 에이전틱 플래너 (agent_planner.py)

Gemini Function Calling으로 LLM이 **어떤 API로 무엇을 검색할지 스스로 판단**:

| 도구 | 설명 |
|------|------|
| search_naver_news | 네이버 뉴스 검색 |
| search_naver_blog | 네이버 블로그 검색 |
| get_google_trending | 실시간 인기 검색어 |
| get_public_events | 지역 축제/행사 |
| get_naver_suggest | 자동완성 키워드 |
| search_trademark_db | KIPRIS 상표 DB |
| get_search_trend | 검색량 트렌드 |

---

## LLM 모델

```
Gemini (GCP $300 크레딧):
  1. gemini-2.5-flash
  2. gemini-2.5-flash-lite
  3. gemini-2.0-flash-001
  4. gemini-1.5-flash
  × N개 API 키 순환

전부 실패 시 → Ollama (로컬 qwen2.5:14b)
```

---

## 운영 명령어

```bash
# 스케줄러 시작 (자동 발행)
python scheduler.py

# Streamlit 대시보드
streamlit run app.py

# 네이버 쿠키 갱신
python save_naver_cookies.py all

# 단건 발행 (JSON 파일)
python publish_one.py <json_file>
```
