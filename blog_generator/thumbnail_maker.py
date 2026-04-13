"""썸네일 이미지 생성 — 마크픽 카드뉴스 스타일."""

import os
import io
import random
import time
import requests as req
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FINAL_SIZE = (950, 950)
BORDER_COLOR = "#3b94fa"
BORDER_WIDTH = 30
LOGO_PATH = Path("data/image/basic/logo_markpick.png")
BG_DIR = Path("data/image/thumbnail_bg")
OUTPUT_DIR = Path("data/generated/thumbnails")
MAX_TEXT_W = 860  # 양쪽 45px 여백


def _load_font(name: str, size: int):
    """폰트 로드."""
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        win_fonts = Path("C:/Windows/Fonts")
        for candidate in [name, f"{name}.ttf", f"{name}.ttc"]:
            p = win_fonts / candidate
            if p.exists():
                return ImageFont.truetype(str(p), size)
        return ImageFont.load_default()


def _center_x(draw, text, font, canvas_w=950):
    bbox = draw.textbbox((0, 0), text, font=font)
    return (canvas_w - (bbox[2] - bbox[0])) // 2


def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _wrap_text(draw, text: str, font, max_w: int) -> list[str]:
    """텍스트를 max_w 이내로 자동 줄바꿈."""
    if _text_width(draw, text, font) <= max_w:
        return [text]

    # 단어 단위로 줄바꿈
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if _text_width(draw, test, font) <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            # 단어 하나가 max_w 초과하면 글자 단위로 자르기
            if _text_width(draw, word, font) > max_w:
                chars = list(word)
                current = ""
                for ch in chars:
                    test = current + ch
                    if _text_width(draw, test, font) <= max_w:
                        current = test
                    else:
                        if current:
                            lines.append(current)
                        current = ch
            else:
                current = word
    if current:
        lines.append(current)

    return lines if lines else [text]


def _draw_centered_lines(draw, lines: list[str], font, y_start: int, line_gap: int = 10, **kwargs):
    """여러 줄을 중앙 정렬로 그린다. 최종 y 반환."""
    y = y_start
    for line in lines:
        x = _center_x(draw, line, font)
        draw.text((x, y), line, font=font, **kwargs)
        bbox = draw.textbbox((0, 0), line, font=font)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def _fetch_bg_image(query: str) -> Path | None:
    """네이버 이미지 검색 API로 지역 배경 이미지를 다운로드한다."""
    import os
    from dotenv import load_dotenv
    load_dotenv()

    BG_DIR.mkdir(parents=True, exist_ok=True)

    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")

    if not client_id:
        print("  [Thumbnail] 네이버 API 키 없음 — 단색 배경 사용")
        return None

    search_query = f"{query} 풍경"
    try:
        r = req.get("https://openapi.naver.com/v1/search/image", params={
            "query": search_query,
            "display": 10,
            "filter": "large",
        }, headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }, timeout=10)

        if r.status_code != 200:
            print(f"  [Thumbnail] 이미지 검색 실패 ({r.status_code})")
            return None

        items = r.json().get("items", [])
        random.shuffle(items)

        for item in items[:5]:
            link = item.get("link", "")
            try:
                img_r = req.get(link, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                if img_r.status_code == 200 and len(img_r.content) > 10000:
                    img = Image.open(io.BytesIO(img_r.content))
                    if img.size[0] >= 400:
                        safe_query = query.replace(" ", "_")[:20]
                        filename = f"bg_{safe_query}_{random.randint(100,999)}.jpg"
                        save_path = BG_DIR / filename
                        img.convert("RGB").save(save_path, "JPEG")
                        print(f"  [Thumbnail] 배경 다운로드: {filename} ({img.size})")
                        return save_path
            except Exception:
                continue

        print(f"  [Thumbnail] '{search_query}' 다운로드 가능한 이미지 없음")
    except Exception as e:
        print(f"  [Thumbnail] 배경 검색 오류: {e}")

    return None


def make_thumbnail(
    main_title: str,
    sub_title_1: str = "",
    sub_title_2: str = "",
    region: str = "",
    output_name: str = "",
) -> str:
    """썸네일 이미지를 생성하고 저장 경로를 반환한다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    BG_DIR.mkdir(parents=True, exist_ok=True)

    # ── 배경 이미지 (지역에 맞는 이미지를 매번 다운로드) ──
    bg_query = region if region else "city"
    fetched = _fetch_bg_image(bg_query)

    if fetched:
        bg = Image.open(fetched).convert("RGBA")
        bw, bh = bg.size
        side = min(bw, bh)
        bg = bg.crop((
            (bw - side) // 2, (bh - side) // 2,
            (bw + side) // 2, (bh + side) // 2,
        )).resize(FINAL_SIZE, Image.Resampling.LANCZOS)
    else:
        bg = Image.new("RGBA", FINAL_SIZE, (45, 45, 45, 255))

    # ── 어두운 오버레이 ──
    overlay = Image.new("RGBA", FINAL_SIZE, (0, 0, 0, 165))
    canvas = Image.alpha_composite(bg, overlay)
    draw = ImageDraw.Draw(canvas)

    # ── 폰트 ──
    f_blue = _load_font("malgunbd", 42)
    f_main = _load_font("malgunbd", 72)
    f_sub = _load_font("malgun", 36)

    # ── 1줄: "마크픽 상표·디자인·특허 출원" (파란색, 작은 폰트) ──
    t1 = "마크픽 상표·디자인·특허 출원"
    draw.text((_center_x(draw, t1, f_blue), 200), t1, font=f_blue, fill=BORDER_COLOR)

    # ── 2줄: 메인 제목 (흰색, 큰 폰트) ──
    main_font_size = 72
    while main_font_size > 40:
        f_main = _load_font("malgunbd", main_font_size)
        wrapped = _wrap_text(draw, main_title, f_main, MAX_TEXT_W)
        if len(wrapped) <= 2:
            break
        main_font_size -= 4

    y_after_main = _draw_centered_lines(
        draw, wrapped, f_main, y_start=300, line_gap=15,
        fill="white", stroke_width=1, stroke_fill="white",
    )

    # ── 3줄: 소제목 1 (흰색, 작은 폰트) ──
    sub_y = max(y_after_main + 40, 490)

    if sub_title_1:
        sub1_lines = _wrap_text(draw, sub_title_1, f_sub, MAX_TEXT_W)
        sub_y = _draw_centered_lines(draw, sub1_lines, f_sub, y_start=sub_y, line_gap=8, fill="white")
        sub_y += 5

    # ── 4줄: 소제목 2 (흰색, 작은 폰트) ──
    if sub_title_2:
        sub2_lines = _wrap_text(draw, sub_title_2, f_sub, MAX_TEXT_W)
        _draw_centered_lines(draw, sub2_lines, f_sub, y_start=sub_y, line_gap=8, fill="white")

    # ── 로고 ──
    # NOTE: logo_markpick.png는 미리 배경 투명 처리된 PNG여야 함
    if LOGO_PATH.exists():
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo_w = 180
        logo_h = int((logo_w / logo.size[0]) * logo.size[1])
        logo_f = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
        canvas.paste(logo_f, ((950 - logo_w) // 2, 740), logo_f)

    # ── 테두리 ──
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, 949, 949], outline=BORDER_COLOR, width=BORDER_WIDTH)

    # ── 임시 저장 (발행 후 삭제) ──
    import tempfile
    if not output_name:
        output_name = f"thumbnail_{int(time.time())}.png"
    tmp_dir = Path(tempfile.gettempdir()) / "blog_thumbnails"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    output_path = tmp_dir / output_name
    canvas.convert("RGB").save(output_path, "PNG")
    print(f"  [Thumbnail] 생성: {output_path}")

    return str(output_path)


def upload_thumbnail_imgur(image_path: str) -> str:
    """썸네일을 Imgur에 업로드하고 URL을 반환한다."""
    import base64

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    try:
        import os
        imgur_id = os.environ.get("IMGUR_CLIENT_ID", "546c25a59c58ad7")
        r = req.post(
            "https://api.imgur.com/3/image",
            headers={"Authorization": f"Client-ID {imgur_id}"},
            data={"image": b64, "type": "base64"},
            timeout=30,
        )
        if r.status_code == 200:
            url = r.json()["data"]["link"]
            print(f"  [Thumbnail] Imgur 업로드: {url}")
            return url
        else:
            print(f"  [Thumbnail] Imgur 실패 ({r.status_code})")
            return ""
    except Exception as e:
        print(f"  [Thumbnail] Imgur 오류: {e}")
        return ""
