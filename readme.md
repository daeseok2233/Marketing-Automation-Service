### 파일 구조(파일을 추가하거나 기능을 수정하면 작성바람)

---

config : 파일 경로 설정

.env : 필요정보 기재(뭐필요한지 적어주세요)

- 빅카인즈 ID, 비밀번호
- 제미나이 API

---

blog_generator : AI 기반 블로그 생성기

blog_generator/prompt_builder : 프롬프트 생성기

blog_generator/blog_generator : 블로그 생성기

---

collector : 파일 수집기

collector/bigkinds_collector : 빅카인즈 파일 수집기

---

logger : 로그 생성기(이전 코드에서 가져옴)

---

#### 미구현

model_loader : 사용 모델 정의

---


### 파일 저장 구조

data : 파일 저장소

data/download : 수집 파일 저장소

data/download/bigkinds : 빅카인즈 데이터

data/images : 이미지 저장소

data/images/basic : 기본 이미지

data/images/event : 이벤트 이미지

data/log : 로그 데이터

data/service_data : 서비스 및 블로그, 등 기타 정보 저장소

data/templates : 템플릿 저장소