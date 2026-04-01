"""AI 플래너 — 템플릿+서비스정보+수집데이터를 보고 10개 주제를 계획한다."""

import csv
import json
import os
import requests
from pathlib import Path
from datetime import datetime

from model import generate


def _load_json(path: str) -> dict | list:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _load_templates_summary() -> str:
    """템플릿 목록 요약."""
    templates_dir = Path("data/templates")
    lines = []
    for f in sorted(templates_dir.glob("*.json")):
        if f.name.startswith("00_"):
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        name = data.get("name", f.stem)
        titles = data.get("example_titles", [])
        lines.append(f"- {f.stem}: {name}")
        for t in titles[:2]:
            lines.append(f"  예시: {t}")
    return "\n".join(lines)


def _load_collected_summary() -> str:
    """오늘 수집 데이터 핵심 요약."""
    today = datetime.now().strftime("%Y%m%d")
    collected = Path("data/collected")
    parts = []

    # 트렌딩
    f = collected / f"{today}_google_trending.csv"
    if f.exists():
        with open(f, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        if rows:
            kws = [r.get("keyword", "") for r in rows[:10]]
            parts.append(f"오늘 인기 검색어: {', '.join(kws)}")

    # DataLab 급상승
    f = collected / f"{today}_naver_datalab.csv"
    if f.exists():
        with open(f, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        rising = [r for r in rows if float(r.get("growth_rate", "0") or "0") > 20]
        if rising:
            items = [f"{r['keyword']}(+{r['growth_rate']}%)" for r in rising[:5]]
            parts.append(f"급상승 키워드: {', '.join(items)}")

    # 뉴스 제목 샘플
    f = collected / f"{today}_naver_news.csv"
    if f.exists():
        with open(f, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        if rows:
            titles = [r.get("title", "")[:60] for r in rows[:10]]
            parts.append(f"최근 뉴스:\n" + "\n".join(f"  - {t}" for t in titles))

    # suggest
    f = collected / f"{today}_naver_suggest.csv"
    if f.exists():
        with open(f, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        if rows:
            suggests = list(set(r.get("suggest", "") for r in rows[:20]))
            parts.append(f"자동완성 키워드: {', '.join(suggests[:15])}")

    return "\n\n".join(parts) if parts else "수집 데이터 없음"


def _load_used_regions(blog_id: str = "") -> str:
    """특정 블로그의 최근 7일 사용 이력을 로드."""
    path = Path("data/schedule_state.json")
    if not path.exists():
        return ""

    data = json.loads(path.read_text(encoding="utf-8"))

    if not blog_id:
        # blog_id 없으면 전체에서 최근 것만
        all_used = []
        for bid, entries in data.items():
            if isinstance(entries, list):
                all_used.extend(entries)
        recent = [f"{u['region']}×{u['business']}" for u in all_used[-20:]]
        if recent:
            return "최근 사용한 조합 (중복 피해야 함):\n" + ", ".join(recent)
        return ""

    # 블로그별 최근 7일 이력
    entries = data.get(blog_id, [])
    cutoff = (datetime.now().timestamp() - 7 * 86400)
    recent = []
    for u in entries:
        try:
            entry_ts = datetime.strptime(u.get("date", "20200101"), "%Y%m%d").timestamp()
            if entry_ts > cutoff:
                recent.append(f"{u.get('region', '')}×{u.get('business', '')} ({u.get('title', '')[:20]})")
        except ValueError:
            continue

    if recent:
        return f"{blog_id}의 최근 7일 발행 이력 (중복 피해야 함):\n" + "\n".join(recent)
    return ""


def plan_topics(count: int = 10, blog_id: str = "") -> list[dict]:
    """AI가 주제를 계획하고, 각 주제별 검색 쿼리를 반환한다."""
    templates = _load_templates_summary()
    service_info = _load_json("data/service_data/services.json")
    blog_info = _load_json("data/service_data/blogs.json")
    collected = _load_collected_summary()
    used = _load_used_regions(blog_id)

    # 블로그별 사용 가능한 템플릿 확인
    available_templates = []
    blog_theme = ""
    blog_name = ""
    if blog_id and "blogs" in blog_info:
        bi = blog_info["blogs"].get(blog_id, {})
        available_templates = bi.get("templates", [])
        blog_theme = bi.get("theme", "")
        blog_name = bi.get("name", "")

    # 지역 블로그인지 비지역 블로그인지 판단
    is_local = any(t.startswith("local_") for t in available_templates)

    if available_templates:
        print(f"  사용 가능 템플릿: {available_templates}")
        templates_filter = "\n".join(
            line for line in templates.split("\n")
            if any(t in line for t in available_templates) or line.startswith("  예시:")
        )
    else:
        templates_filter = templates

    if is_local:
        system = """당신은 마크클라우드(상표·디자인·특허 출원 서비스) 블로그의 편집장입니다.
매일 지역 타겟 블로그 포스팅 주제를 기획합니다.

핵심 원칙:
- 지역은 구체적으로 (시·구·동 단위). "서울" 같은 큰 단위 금지.
- 지역과 업종의 조합이 현실적이어야 함 (제주+카페 ✓, 강남+농산물 ✗)
- 각 주제마다 네이버에서 검색할 쿼리를 2~3개 제안 (실제 API 검색에 사용됨)
- 트렌드 데이터를 활용해 시의성 있는 주제 선정
- 이전에 사용한 지역+업종 조합은 피할 것

반드시 JSON 배열로만 응답하세요. 다른 텍스트 없이 JSON만."""

        prompt = f"""아래 정보를 기반으로 오늘 작성할 블로그 주제 {count}개를 기획하세요.

## 사용 가능한 템플릿
{templates_filter}

## 서비스 정보
{json.dumps(service_info, ensure_ascii=False, indent=2)[:800]}

## 오늘 수집된 트렌드 데이터
{collected[:2000]}

## {used}

## 출력 형식 (JSON 배열)
[
  {{
    "region": "구체적 지역명 (시+구 또는 시+동)",
    "business": "업종",
    "template": "사용할 템플릿 key ({', '.join(available_templates)})",
    "title_idea": "블로그 제목 아이디어",
    "angle": "이 주제를 쓰는 이유 (트렌드 연결)",
    "search_queries": ["네이버 검색 쿼리1", "검색 쿼리2"],
    "keywords": ["SEO키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]
  }}
]"""

    else:
        # 비지역 블로그 (blog_02, blog_03 등)
        system = f"""당신은 마크클라우드(상표·디자인·특허 출원 서비스) 블로그의 편집장입니다.

이 블로그의 성격:
- 블로그명: {blog_name}
- 테마: {blog_theme}
- 사용 가능 템플릿: {', '.join(available_templates)}

핵심 원칙:
- 지역 키워드를 사용하지 않는 전문 콘텐츠를 기획합니다.
- 상표·디자인·특허 출원에 관한 실무 정보, 비교, 분석, 사례 중심입니다.
- 트렌드 데이터를 활용해 시의성 있는 주제를 선정합니다.
- 이전에 사용한 주제와 겹치지 않아야 합니다.
- region 필드는 빈 문자열("")로 두세요.

반드시 JSON 배열로만 응답하세요. 다른 텍스트 없이 JSON만."""

        prompt = f"""아래 정보를 기반으로 오늘 작성할 블로그 주제 {count}개를 기획하세요.

## 사용 가능한 템플릿
{templates_filter}

## 서비스 정보
{json.dumps(service_info, ensure_ascii=False, indent=2)[:800]}

## 오늘 수집된 트렌드 데이터
{collected[:2000]}

## {used}

## 출력 형식 (JSON 배열)
[
  {{
    "region": "",
    "business": "주제 카테고리 (예: 셀프출원, 상표분쟁, 해외출원 등)",
    "template": "사용할 템플릿 key ({', '.join(available_templates)})",
    "title_idea": "블로그 제목 아이디어",
    "angle": "이 주제를 쓰는 이유 (트렌드 연결)",
    "search_queries": ["네이버 검색 쿼리1", "검색 쿼리2"],
    "keywords": ["SEO키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]
  }}
]"""

    result = generate(prompt, system=system)
    text = result["text"].strip()

    # JSON 파싱
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        topics = json.loads(text)
    except json.JSONDecodeError:
        print(f"  [Planner] JSON 파싱 실패, 기본 주제 사용")
        topics = [
            {
                "region": "수원 영통구",
                "business": "카페",
                "title_idea": "영통구 카페 창업, 상표 출원이 필요한 이유",
                "angle": "기본 주제",
                "search_queries": ["영통구 카페 상표", "수원 카페 창업"],
                "keywords": ["영통구상표등록", "영통구카페", "수원창업", "상표출원", "마크클라우드"],
            }
        ] * count

    topics = topics[:count]

    # 중간결과 저장
    out = Path("data/generated")
    out.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    (out / f"{today}_00_plan.json").write_text(
        json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  [Planner] {len(topics)}개 주제 계획 완료")

    return topics


def search_for_topic(topic: dict) -> dict:
    """AI가 정한 검색 쿼리로 네이버 검색 → 주제별 맞춤 레퍼런스 수집.

    Returns:
        {
            "news": [...],
            "blogs": [...],
        }
    """
    from dotenv import load_dotenv
    load_dotenv()

    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    queries = topic.get("search_queries", [])
    region = topic.get("region", "")
    business = topic.get("business", "")

    # 기본 쿼리 보강
    if not queries:
        queries = [f"{region} {business} 상표", f"{region} 창업"]

    news_results = []
    blog_results = []

    for query in queries[:3]:
        # 뉴스 검색
        try:
            r = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                params={"query": query, "display": 3, "sort": "date"},
                headers=headers, timeout=5,
            )
            if r.status_code == 200:
                for item in r.json().get("items", []):
                    news_results.append({
                        "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                        "description": item.get("description", "").replace("<b>", "").replace("</b>", "")[:200],
                    })
        except Exception:
            pass

        # 블로그 검색
        try:
            r = requests.get(
                "https://openapi.naver.com/v1/search/blog.json",
                params={"query": query, "display": 3, "sort": "sim"},
                headers=headers, timeout=5,
            )
            if r.status_code == 200:
                for item in r.json().get("items", []):
                    blog_results.append({
                        "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                        "description": item.get("description", "").replace("<b>", "").replace("</b>", "")[:200],
                    })
        except Exception:
            pass

    # 중복 제거
    seen = set()
    unique_news = []
    for n in news_results:
        if n["title"] not in seen:
            seen.add(n["title"])
            unique_news.append(n)

    seen = set()
    unique_blogs = []
    for b in blog_results:
        if b["title"] not in seen:
            seen.add(b["title"])
            unique_blogs.append(b)

    return {
        "news": unique_news[:5],
        "blogs": unique_blogs[:5],
        "queries": queries,
    }
