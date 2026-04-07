"""에이전틱 플래너 — Gemini Function Calling 기반.

Gemini가 템플릿을 보고 스스로 판단:
- "이 템플릿에는 뉴스 검색이 필요하겠다" → search_naver_news 호출
- "지역 블로그니까 행사 정보를 확인하자" → get_public_events 호출
- "트렌딩 키워드를 활용하자" → get_google_trending 호출

사람이 파이프라인을 하드코딩하지 않고, 모델이 알아서 결정.
"""

import json
import os
import csv
import random
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from model import generate_with_tools, generate

load_dotenv()

# ── Gemini에 노출할 도구 정의 ──

AGENT_TOOLS = [
    {
        "name": "search_naver_news",
        "description": "네이버 뉴스 검색 API. 특정 키워드로 최신 뉴스를 검색한다. 상표/특허/창업/브랜드 관련 뉴스나, 특정 지역+업종 뉴스를 찾을 때 사용.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "검색 키워드 (예: '강남 카페 창업', '상표 출원 비용')"},
                "count": {"type": "INTEGER", "description": "가져올 뉴스 수 (1~10, 기본 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_naver_blog",
        "description": "네이버 블로그 검색 API. 경쟁 블로그나 참고할 만한 기존 블로그 글을 검색한다. 어떤 블로그 글이 이미 있는지 확인할 때 사용.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "검색 키워드"},
                "count": {"type": "INTEGER", "description": "가져올 결과 수 (1~10, 기본 3)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_google_trending",
        "description": "구글 실시간 인기 검색어 (한국). 지금 사람들이 가장 많이 검색하는 키워드를 확인한다. 뉴스재킹(newsjacking) 템플릿이나 트렌드 기반 콘텐츠에 유용.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "get_public_events",
        "description": "공공데이터 축제/행사 정보. 현재 진행 중이거나 예정된 지역 행사를 확인한다. 지역(local_*) 템플릿에서 지역 이벤트와 상표 출원을 연결할 때 유용.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "region": {"type": "STRING", "description": "지역명 (예: '부산', '대전'). 비워두면 전국."},
            },
        },
    },
    {
        "name": "get_naver_suggest",
        "description": "네이버 자동완성(서제스트). 특정 키워드를 입력하면 사람들이 실제로 검색하는 연관 검색어를 보여준다. 롱테일 키워드나 사용자 의도를 파악할 때 유용.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "keyword": {"type": "STRING", "description": "기본 키워드 (예: '상표 출원')"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "search_trademark_db",
        "description": "KIPRIS 상표 데이터베이스 검색. 특정 브랜드/상표명이 이미 등록되어 있는지 확인한다. 분쟁/비교/사례 관련 콘텐츠에 유용.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "brand_name": {"type": "STRING", "description": "검색할 브랜드/상표명"},
                "count": {"type": "INTEGER", "description": "가져올 결과 수 (기본 5)"},
            },
            "required": ["brand_name"],
        },
    },
    {
        "name": "get_search_trend",
        "description": "네이버 데이터랩 검색량 트렌드. 특정 키워드의 최근 검색량 추이와 증감률을 확인한다. 검색량이 급증하는 키워드를 찾을 때 유용.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "keywords": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "확인할 키워드 리스트 (최대 5개)",
                },
            },
            "required": ["keywords"],
        },
    },
]


# ── 도구 실행 함수들 ──

def _exec_search_naver_news(args: dict) -> dict:
    query = args.get("query", "")
    count = min(args.get("count", 5), 10)
    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    try:
        r = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            params={"query": query, "display": count, "sort": "date"},
            headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
            timeout=5,
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            return {"results": [
                {"title": it["title"].replace("<b>", "").replace("</b>", ""),
                 "description": it.get("description", "").replace("<b>", "").replace("</b>", "")[:150]}
                for it in items
            ]}
    except Exception as e:
        return {"error": str(e)}
    return {"results": []}


def _exec_search_naver_blog(args: dict) -> dict:
    query = args.get("query", "")
    count = min(args.get("count", 3), 10)
    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    try:
        r = requests.get(
            "https://openapi.naver.com/v1/search/blog.json",
            params={"query": query, "display": count, "sort": "sim"},
            headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
            timeout=5,
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            return {"results": [
                {"title": it["title"].replace("<b>", "").replace("</b>", ""),
                 "description": it.get("description", "").replace("<b>", "").replace("</b>", "")[:150]}
                for it in items
            ]}
    except Exception as e:
        return {"error": str(e)}
    return {"results": []}


def _exec_get_google_trending(args: dict) -> dict:
    try:
        r = requests.get(
            "https://trends.google.com/trending/rss?geo=KR",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10,
        )
        if r.status_code != 200:
            return {"trends": []}
        root = ET.fromstring(r.content)
        ns = {"ht": "https://trends.google.com/trending/rss"}
        trends = []
        for item in root.findall(".//item"):
            keyword = item.findtext("title", "").strip()
            traffic = item.findtext("ht:approx_traffic", "", ns).strip()
            news_titles = []
            for ni in item.findall("ht:news_item", ns):
                nt = ni.findtext("ht:news_item_title", "", ns).strip()
                if nt:
                    news_titles.append(nt[:60])
            if keyword:
                trends.append({"keyword": keyword, "traffic": traffic, "news": news_titles[:2]})
        return {"trends": trends[:15]}
    except Exception:
        return {"trends": []}


def _exec_get_public_events(args: dict) -> dict:
    api_key = os.environ.get("PUBLIC_DATA_API_KEY", "")
    if not api_key:
        return {"events": [], "note": "PUBLIC_DATA_API_KEY 미설정"}
    region_filter = args.get("region", "")
    today = datetime.now().strftime("%Y%m%d")
    try:
        r = requests.get(
            "http://apis.data.go.kr/B551011/KorService1/searchFestival1",
            params={
                "serviceKey": api_key, "numOfRows": 20, "pageNo": 1,
                "MobileOS": "ETC", "MobileApp": "BlogPipeline",
                "_type": "json", "eventStartDate": today,
            },
            timeout=10,
        )
        if r.status_code != 200:
            return {"events": [], "note": f"API 응답 {r.status_code}"}
        data = r.json()
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        events = []
        for item in items:
            title = item.get("title", "")
            addr = item.get("addr1", "")
            if region_filter and region_filter not in addr and region_filter not in title:
                continue
            events.append({"title": title, "address": addr,
                           "start": item.get("eventstartdate", ""), "end": item.get("eventenddate", "")})
        return {"events": events[:10]}
    except Exception as e:
        return {"events": [], "error": str(e)}


def _exec_get_naver_suggest(args: dict) -> dict:
    keyword = args.get("keyword", "")
    try:
        r = requests.get(
            "https://ac.search.naver.com/nx/ac",
            params={"q": keyword, "con": 1, "frm": "nv", "ans": 2},
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [[]])[0]
            suggestions = [item[0] for item in items if item]
            return {"suggestions": suggestions[:10]}
    except Exception:
        pass
    return {"suggestions": []}


def _exec_search_trademark_db(args: dict) -> dict:
    brand_name = args.get("brand_name", "")
    count = min(args.get("count", 5), 10)
    api_key = os.environ.get("KIPRIS_API_KEY", "")
    if not api_key:
        return {"results": [], "note": "KIPRIS_API_KEY 미설정"}
    try:
        r = requests.get(
            "http://plus.kipris.or.kr/kipo-api/kipi/trademarkInfoSearchService/search",
            params={"query": brand_name, "numOfRows": count, "pageNo": 1, "ServiceKey": api_key},
            timeout=10,
        )
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            results = []
            for item in items:
                results.append({
                    "title": item.findtext("title", ""),
                    "status": item.findtext("applicationStatus", ""),
                    "applicant": item.findtext("applicantName", ""),
                    "date": item.findtext("applicationDate", ""),
                })
            return {"results": results, "total": len(items)}
    except Exception as e:
        return {"results": [], "error": str(e)}
    return {"results": []}


def _exec_get_search_trend(args: dict) -> dict:
    keywords = args.get("keywords", [])[:5]
    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    if not client_id:
        return {"trends": {}, "note": "NAVER_CLIENT_ID 미설정"}

    today = datetime.now()
    start = (today - __import__("datetime").timedelta(days=90)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    keyword_groups = [{"groupName": kw, "keywords": [kw]} for kw in keywords]

    try:
        r = requests.post(
            "https://openapi.naver.com/v1/datalab/search",
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
                "Content-Type": "application/json",
            },
            json={
                "startDate": start, "endDate": end,
                "timeUnit": "week", "keywordGroups": keyword_groups,
            },
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            results = {}
            for group in data.get("results", []):
                name = group["title"]
                ratios = [d["ratio"] for d in group.get("data", []) if d.get("ratio")]
                if len(ratios) >= 4:
                    recent = sum(ratios[-4:]) / 4
                    prev = sum(ratios[-8:-4]) / 4 if len(ratios) >= 8 else recent
                    growth = round((recent - prev) / prev * 100, 1) if prev > 0 else 0
                    results[name] = {"avg_ratio": round(recent, 1), "growth_pct": growth}
                elif ratios:
                    results[name] = {"avg_ratio": round(sum(ratios) / len(ratios), 1), "growth_pct": 0}
            return {"trends": results}
    except Exception as e:
        return {"trends": {}, "error": str(e)}
    return {"trends": {}}


# ── 도구 실행 라우터 ──

TOOL_EXECUTORS = {
    "search_naver_news": _exec_search_naver_news,
    "search_naver_blog": _exec_search_naver_blog,
    "get_google_trending": _exec_get_google_trending,
    "get_public_events": _exec_get_public_events,
    "get_naver_suggest": _exec_get_naver_suggest,
    "search_trademark_db": _exec_search_trademark_db,
    "get_search_trend": _exec_get_search_trend,
}


def execute_tool(name: str, args: dict) -> dict:
    """도구 이름+인자 → 실행 결과."""
    executor = TOOL_EXECUTORS.get(name)
    if not executor:
        return {"error": f"Unknown tool: {name}"}
    return executor(args)


# ── 헬퍼 ──

def _load_json(path: str) -> dict | list:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_template_detail(template_name: str) -> dict:
    p = Path(f"data/templates/{template_name}.json")
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _load_used_history(blog_id: str) -> str:
    path = Path("data/schedule_state.json")
    if not path.exists() or not blog_id:
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get(blog_id, [])
    cutoff = datetime.now().timestamp() - 3 * 86400
    combos = set()
    for u in entries:
        try:
            ts = datetime.strptime(u.get("date", "20200101"), "%Y%m%d").timestamp()
            if ts > cutoff:
                combos.add(f"{u.get('region', '')}×{u.get('business', '')}")
        except ValueError:
            continue
    return f"최근 3일 사용 조합 (피할 것): {', '.join(combos)}" if combos else ""


# ── 에이전틱 플래너 메인 ──

def agent_plan_topic(blog_id: str = "", template_name: str = "") -> dict:
    """Gemini가 템플릿+도구를 보고 스스로 정보를 수집하고 주제를 결정한다.

    Returns:
        {
            "region": "...",
            "business": "...",
            "template": "...",
            "angle": "...",
            "keywords": [...],
            "ref_news": "...",
            "ref_blogs": "...",
            "ref_trending": "...",
            "search_queries": [...],  # 에이전트가 실행한 검색 쿼리
            "_agent_meta": {
                "tool_calls": [...],
                "system_prompt": "...",
                "user_prompt": "...",
                "raw_response": "...",
                "model": "...",
                "provider": "...",
            },
        }
    """

    # 블로그 정보
    blogs_data = _load_json("data/service_data/blogs.json")
    blog_info = blogs_data.get("blogs", {}).get(blog_id, {})
    blog_name = blog_info.get("name", "")
    blog_theme = blog_info.get("theme", "")
    available_templates = blog_info.get("templates", [])

    # 템플릿 선택
    if not template_name:
        template_name = random.choice(available_templates) if available_templates else "local_trend"
    tpl = _load_template_detail(template_name)
    tpl_name = tpl.get("name", template_name)
    tpl_conditions = tpl.get("conditions", {})
    tpl_examples = tpl.get("example_titles", [])
    is_local = tpl.get("is_local", False)

    # 사용 이력
    history = _load_used_history(blog_id)

    # 지역 풀 (지역 블로그용)
    region_pool_text = ""
    if is_local:
        from blog_generator.region_selector import REGION_POOL
        sample = random.sample(REGION_POOL, min(20, len(REGION_POOL)))
        region_pool_text = f"\n사용 가능 지역 예시: {', '.join(sample)}"

    # ── 시스템 프롬프트 ──
    system_prompt = f"""너는 블로그 콘텐츠 기획 에이전트다.
마크클라우드(상표·디자인·특허 출원 대행 서비스) 블로그에 올릴 글의 주제를 기획한다.

## 너의 역할
1. 주어진 도구(API)들을 활용해서 필요한 정보를 직접 수집한다.
2. 수집한 정보를 바탕으로 블로그 글의 주제/앵글/키워드를 결정한다.
3. 어떤 도구를 쓸지, 뭘 검색할지는 네가 판단한다.

## 사용 가능한 도구
- search_naver_news: 네이버 뉴스 검색 (최신 뉴스, 업종/지역 뉴스)
- search_naver_blog: 네이버 블로그 검색 (경쟁 블로그 확인)
- get_google_trending: 실시간 인기 검색어 (트렌드 파악)
- get_public_events: 지역 축제/행사 정보
- get_naver_suggest: 자동완성 키워드 (사용자 검색 의도)
- search_trademark_db: KIPRIS 상표 DB 검색
- get_search_trend: 네이버 데이터랩 검색량 트렌드

## 전략 가이드
- 지역 블로그(local_*): 먼저 get_public_events로 행사를 확인하거나, get_google_trending으로 핫한 지역을 파악. 그 후 해당 지역+상표로 뉴스/블로그 검색.
- 뉴스재킹(newsjacking): 반드시 get_google_trending 먼저. 인기 키워드 중 상표와 연결 가능한 것을 찾아서 뉴스 검색.
- 비교(compare)/FAQ/howto: get_naver_suggest로 사람들이 실제 검색하는 키워드를 먼저 확인. 그걸로 뉴스/블로그 검색.
- 칼럼(column)/분쟁(dispute_report): search_trademark_db로 실제 사례를 찾거나, 뉴스에서 분쟁 사례 검색.
- 도구를 2~4개 적절히 조합해서 사용. 너무 많이 쓰지 말 것.

## 출력 형식 (반드시 JSON)
도구 호출이 끝나면 아래 JSON으로 응답:
```json
{{
    "region": "지역명 (지역 블로그면 필수, 아니면 빈 문자열)",
    "business": "업종/주제",
    "template": "{template_name}",
    "angle": "글의 앵글/관점 (한 줄)",
    "keywords": ["SEO키워드1", "키워드2", "키워드3"],
    "ref_news": "수집한 뉴스 요약 (줄바꿈으로 구분)",
    "ref_blogs": "수집한 블로그 요약",
    "ref_trending": "트렌딩 키워드 요약",
    "search_queries": ["실제로 검색한 쿼리들"]
}}
```"""

    # ── 유저 프롬프트 ──
    user_prompt = f"""블로그: {blog_name} — {blog_theme}
템플릿: {template_name} ({tpl_name})
{'지역 블로그' if is_local else '전국 블로그'}

## 템플릿 상세
사용 조건: {json.dumps(tpl_conditions, ensure_ascii=False)[:200] if tpl_conditions else '없음'}
제목 예시: {', '.join(tpl_examples[:3]) if tpl_examples else '없음'}
{region_pool_text}
{history}

도구를 활용해서 이 블로그+템플릿에 맞는 주제를 기획해줘.
먼저 필요한 정보를 도구로 수집하고, 수집한 정보를 바탕으로 최종 주제를 JSON으로 출력해."""

    print(f"\n  [Agent] 에이전틱 기획 시작 — {blog_id} / {template_name}")

    # ── Gemini Function Calling 실행 ──
    result = generate_with_tools(
        prompt=user_prompt,
        tools=AGENT_TOOLS,
        tool_executor=execute_tool,
        system=system_prompt,
        max_tokens=4096,
        max_turns=6,
    )

    text = result.get("text", "")
    tool_calls = result.get("tool_calls", [])

    # JSON 파싱
    topic = _parse_agent_response(text, template_name, is_local)

    # 메타 정보 추가
    topic["_agent_meta"] = {
        "tool_calls": tool_calls,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "raw_response": text,
        "model": result.get("model", ""),
        "provider": result.get("provider", ""),
    }

    print(f"  [Agent] 완료 — 지역: {topic.get('region', '')}, 업종: {topic.get('business', '')}")
    print(f"  [Agent] 도구 호출 {len(tool_calls)}회: {', '.join(tc['function'] for tc in tool_calls)}")

    return topic


def _parse_agent_response(text: str, template_name: str, is_local: bool) -> dict:
    """에이전트 응답에서 JSON 추출."""
    # ```json ... ``` 블록 추출
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue

    # 전체 텍스트에서 JSON 시도
    try:
        # { 로 시작하는 부분 찾기
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        pass

    # 폴백
    print("  [Agent] JSON 파싱 실패 — 폴백 사용")
    return {
        "region": "" if not is_local else "서울 강남구",
        "business": "상표 출원",
        "template": template_name,
        "angle": "상표 출원의 중요성",
        "keywords": ["상표 출원", "브랜드 보호"],
        "ref_news": "",
        "ref_blogs": "",
        "ref_trending": "",
        "search_queries": [],
    }


# ── 배치 생성 (스케줄러용) ──

def agent_plan_topics(count: int = 10, blog_id: str = "") -> list[dict]:
    """여러 주제를 에이전틱하게 기획한다."""
    blogs_data = _load_json("data/service_data/blogs.json")
    blog_info = blogs_data.get("blogs", {}).get(blog_id, {})
    available_templates = blog_info.get("templates", [])

    topics = []
    for i in range(count):
        tpl = random.choice(available_templates) if available_templates else "local_trend"
        print(f"\n  [{i+1}/{count}] {blog_id} / {tpl}")
        topic = agent_plan_topic(blog_id=blog_id, template_name=tpl)
        topics.append(topic)

    # 저장
    out = Path("data/generated")
    out.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    save_data = [{k: v for k, v in t.items() if k != "_agent_meta"} for t in topics]
    (out / f"{today}_agent_topics.json").write_text(
        json.dumps(save_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return topics
