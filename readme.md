# 마크  클라우드 블로그 자동화

마크 클라우드 블로그 자동화를 위한 프로젝트 입니다.
정해진 탬플릿에 맞추어 SEO, GEO, AEO에 부합하는 글을 쓰는 것을 목적으로 합니다.
프로젝트 참여자는 수정시 아래 내용을 반드시 수정해 주십시오.

### 파일 구조

프로젝트의 파일 및 패키지들의 구조입니다. 패키지 단위 기능을 기입하여 주십시오.
깃헙에 업로드 되지 않아 별도 작성이 필요할 경우 필요 사항을 기재해 주십시오

---

config : 파일 경로 설정

.env : 깃헙에 업로드 되지 않으므로 필요정보 기재
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

#### 미구현(아직 구현되지 않은 것들을 기재)

model_loader : 사용 모델 정의

---


### 파일 저장 구조

파일의 저장소 구조입니다.
파일 저장소는 data 폴더의 하위 폴더로 구성되며, 별도의 저장소 폴더를 만들어내지 않아야합니다.
용량이 큰 파일의 경우 업로드가 불가능하므로 별도로 공유하여야 합니다.

---

data : 파일 저장소

data/download : 수집 파일 저장소

data/download/bigkinds : 빅카인즈 데이터

data/images : 이미지 저장소, 깃헙에 저장되지 않으므로 별도로 구성 필요

data/images/basic : 기본 이미지

data/images/event : 이벤트 이미지

data/log : 로그 데이터

data/service_data : 서비스 및 블로그, 등 기타 정보 저장소

data/templates : 템플릿 저장소