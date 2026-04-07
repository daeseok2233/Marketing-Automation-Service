"""AI 플래너 — 새 파이프라인.

Step 1: 템플릿 확인 → 검색 쿼리 생성 (주제는 아직 안 정함)
Step 2: 검색 쿼리로 뉴스/블로그/트렌딩 수집
Step 3: 수집 결과를 보고 주제+레퍼런스 확정
"""

import json
import os
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

from model import generate


# ── 헬퍼 ──

def _load_json(path: str) -> dict | list:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_templates_summary(filter_keys: list = None) -> str:
    lines = []
    for f in sorted(Path("data/templates").glob("*.json")):
        if f.name.startswith("00_"):
            continue
        if filter_keys and f.stem not in filter_keys:
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        lines.append(f"- {f.stem}: {data.get('name', f.stem)}")
        for t in data.get("example_titles", [])[:2]:
            lines.append(f"  예시: {t}")
    return "\n".join(lines)


def _load_service_summary() -> str:
    data = _load_json("data/service_data/services.json")
    lines = []
    for _, svc in data.get("services", {}).items():
        features = ", ".join(svc.get("features", [])[:3])
        lines.append(f"- {svc.get('name', '')} ({svc.get('type', '')}): {features}")
    return "\n".join(lines)


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


# ── Step 1: 검색 쿼리 생성 ──

def plan_search_queries(count: int = 10, blog_id: str = "") -> list[dict]:
    """템플릿+블로그 정보를 보고 검색 쿼리만 생성. 주제는 아직 안 정함."""

    blog_info = _load_json("data/service_data/blogs.json")
    available_templates = []
    blog_theme = ""
    blog_name = ""
    if blog_id and "blogs" in blog_info:
        bi = blog_info["blogs"].get(blog_id, {})
        available_templates = bi.get("templates", [])
        blog_theme = bi.get("theme", "")
        blog_name = bi.get("name", "")

    is_local = any(t.startswith("local_") for t in available_templates)

    if available_templates:
        print(f"  사용 가능 템플릿: {available_templates}")

    import random

    if is_local:
        # ── 지역 블로그: 지역 선정 로직 사용 (LLM에게 지역을 맡기지 않음) ──
        from blog_generator.region_selector import select_regions
        regions = select_regions(count=count, blog_id=blog_id)

        items = []
        for region_info in regions:
            tpl = random.choice(available_templates) if available_templates else "local_trend"
            region = region_info["region"]
            event = region_info.get("event", "")
            # 검색 쿼리: 지역+상표 기본 + 행사 있으면 행사 쿼리 추가
            queries = [f"{region} 상표 출원", f"{region} 창업"]
            if event:
                queries.insert(0, event)
            items.append({
                "region": region,
                "business": "",  # 글 생성 시 LLM이 결정
                "template": tpl,
                "search_queries": queries[:3],
                "event": event,
                "source": region_info.get("source", ""),
            })

        # 메타 정보
        _meta = {
            "system_prompt": "(지역 선정 로직 — LLM 미사용)",
            "user_prompt": f"select_regions(count={count}, blog_id={blog_id})",
            "model": "code",
            "provider": "region_selector",
            "raw_response": json.dumps([{"region": r["region"], "source": r["source"]} for r in regions], ensure_ascii=False),
        }
        for item in items:
            item["_planner_meta"] = _meta

    else:
        # ── 비지역 블로그: LLM으로 검색 쿼리 생성 ──
        context = f"{blog_name} — {blog_theme}"
        history = _load_used_history(blog_id)

        items_per_template = []
        for _ in range(count):
            tpl = random.choice(available_templates) if available_templates else "howto"
            items_per_template.append(tpl)

        selected_templates = set(items_per_template)
        tpl_info = _load_templates_summary(filter_keys=list(selected_templates))
        tpl_assignments = ", ".join(f"{i+1}번: {t}" for i, t in enumerate(items_per_template))

        system = f"""검색 쿼리 생성기. 블로그: {context}. JSON만 응답."""
        prompt = f"""포스팅 {count}개의 검색 쿼리 생성. 주제/제목 정하지 말 것.

템플릿 배정: {tpl_assignments}
{tpl_info}
{history}

형식: [{{"region":"", "business":"업종", "template":"배정된 템플릿", "search_queries":["쿼리1","쿼리2"]}}]"""

        result = generate(prompt, system=system)
        text = result["text"].strip()

        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            print("  [Planner] JSON 파싱 실패, 기본 쿼리 사용")
            items = [{
                "region": "",
                "business": "셀프출원",
                "template": available_templates[0] if available_templates else "howto",
                "search_queries": ["상표 출원 방법", "상표 등록 비용"],
            }] * count

        items = items[:count]

        _meta = {
            "system_prompt": system,
            "user_prompt": prompt,
            "model": result.get("model", ""),
            "provider": result.get("provider", ""),
            "raw_response": result.get("text", ""),
        }
        for item in items:
            item["_planner_meta"] = _meta

    # 저장
    out = Path("data/generated")
    out.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    (out / f"{today}_00_queries.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  [Planner] {len(items)}개 검색 쿼리 생성 완료")
    return items


# ── Step 2: 정보 수집 ──

def _fetch_realtime_trending() -> list[dict]:
    """구글 트렌딩 RSS 실시간 인기 검색어."""
    try:
        r = requests.get(
            "https://trends.google.com/trending/rss?geo=KR",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10,
        )
        if r.status_code != 200:
            return []
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
        return trends[:15]
    except Exception:
        return []


def collect_references(query_item: dict) -> dict:
    """검색 쿼리로 뉴스/블로그/트렌딩을 수집."""
    from dotenv import load_dotenv
    load_dotenv()

    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    queries = query_item.get("search_queries", [])
    region = query_item.get("region", "")
    business = query_item.get("business", "")
    if not queries:
        queries = [f"{region} {business} 상표", f"{region} 창업"]

    news_results = []
    blog_results = []

    for query in queries[:3]:
        try:
            r = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                params={"query": query, "display": 5, "sort": "date"},
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

    # 실시간 트렌딩
    trending = _fetch_realtime_trending()

    # 중복 제거
    seen = set()
    unique_news = [n for n in news_results if n["title"] not in seen and not seen.add(n["title"])]
    seen = set()
    unique_blogs = [b for b in blog_results if b["title"] not in seen and not seen.add(b["title"])]

    return {
        "news": unique_news[:7],
        "blogs": unique_blogs[:5],
        "trending": trending,
        "queries": queries,
    }


# ── Step 3: 주제+레퍼런스 확정 ──

def select_topic_from_references(query_item: dict, references: dict) -> dict:
    """수집된 정보를 보고 주제와 레퍼런스를 확정한다.

    Returns:
        query_item에 ref_news, ref_blogs, ref_trending, topic_direction 추가
    """
    region = query_item.get("region", "")
    business = query_item.get("business", "")

    # 뉴스 요약
    news_text = "\n".join(f"- {n['title']}" for n in references.get("news", []))
    blog_text = "\n".join(f"- {b['title']}" for b in references.get("blogs", []))
    trending_text = "\n".join(
        f"- {t['keyword']} ({t['traffic']})" for t in references.get("trending", [])[:10]
    )

    # topic에 레퍼런스 주입
    if news_text:
        query_item["ref_news"] = news_text
    if blog_text:
        query_item["ref_blogs"] = blog_text
    if trending_text:
        query_item["ref_trending"] = trending_text

    # 주제 방향 설정 (LLM이 글 생성 시 이걸 보고 제목+본문 결정)
    if region:
        query_item["topic_direction"] = f"{region} {business} 상표·디자인·특허 출원"
    else:
        query_item["topic_direction"] = f"{business} 관련 상표 출원 콘텐츠"

    return query_item


# ── 하위 호환: 기존 코드에서 호출하는 함수 ──

def plan_topics(count: int = 10, blog_id: str = "") -> list[dict]:
    """기존 인터페이스 유지. 내부적으로 새 파이프라인 사용."""
    return plan_search_queries(count=count, blog_id=blog_id)


def search_for_topic(topic: dict) -> dict:
    """기존 인터페이스 유지. collect_references + select_topic_from_references."""
    refs = collect_references(topic)
    select_topic_from_references(topic, refs)
    return refs
