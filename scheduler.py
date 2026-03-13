"""매일 실행 스케줄 — 서비스·템플릿 순환 관리"""
import json, os
from datetime import date

SERVICE_ROTATION  = ["markview", "markpick", "markpass", "markcloud"]
TEMPLATE_ROTATION = ["info", "howto", "case", "compare"]

SERVICE_KEYWORDS = {
    "markview": ["상표 검색", "유사 상표 검색", "상표 이미지 검색", "브랜드 중복 확인"],
    "markpick": ["상표 출원 방법", "상표 등록 비용", "셀프 상표 출원", "변리사 없이 상표"],
    "markpass": ["상표 의견제출", "상표 거절 대응", "출원 자동화", "상표 심사"],
    "markcloud":["상표권 침해", "브랜드 보호", "지식재산권 분석", "상표 분쟁 사례"],
}

class DailyScheduler:
    def __init__(self, state_file: str = "data/schedule_state.json"):
        self.state_file = state_file
        self.state = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.state_file):
            with open(self.state_file, encoding="utf-8") as f:
                return json.load(f)
        return {"service_idx": 0, "template_idx": 0, "total_posts": 0, "log": {}}

    def save(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def get_today_plan(self, count: int = 2) -> list[dict]:
        plans = []
        for i in range(count):
            si = (self.state["service_idx"]  + i) % len(SERVICE_ROTATION)
            ti = (self.state["template_idx"] + i) % len(TEMPLATE_ROTATION)
            svc = SERVICE_ROTATION[si]
            tpl = TEMPLATE_ROTATION[ti]
            plans.append({
                "service_key":    svc,
                "template_key":   tpl,
                "focus_keywords": SERVICE_KEYWORDS[svc],
                "label": f"{svc}/{tpl}",
            })
        return plans

    def advance(self, n: int):
        self.state["service_idx"]  = (self.state["service_idx"]  + n) % len(SERVICE_ROTATION)
        self.state["template_idx"] = (self.state["template_idx"] + n) % len(TEMPLATE_ROTATION)
        self.state["total_posts"] += n
        self.state["log"][date.today().isoformat()] = n
        self.save()

    def summary(self) -> str:
        return f"누적 {self.state['total_posts']}개 생성"
