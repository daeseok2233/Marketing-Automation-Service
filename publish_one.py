"""Streamlit에서 호출하는 단건 발행 스크립트.

Playwright는 Streamlit의 asyncio 이벤트 루프와 충돌하므로,
별도 프로세스로 실행한다.

Usage: python publish_one.py <json_file>
"""

import json
import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python publish_one.py <json_file>", file=sys.stderr)
        sys.exit(1)

    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    blog = data["blog"]
    blog_id = data["blog_id"]
    template_name = data["template_name"]
    cookie_blog_id = data["cookie_blog_id"]

    from publisher.naver_blog import publish_to_naver
    url = publish_to_naver(blog, blog_id=blog_id, template_name=template_name, cookie_blog_id=cookie_blog_id)

    if url:
        print(url)
    else:
        print("발행 실패 — URL 없음", file=sys.stderr)
        sys.exit(1)
