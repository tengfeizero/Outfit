"""搭配板：把一套方案拼成一张图。

这是"看效果"在没有出图 API 时的降级产物——不生成"你穿着它"的照片，
而是把衣服按层级排成一张可以直接看、可以存下来的搭配图。

它比合成图更忠实的另一面：格纹不会被糊掉，颜色就是你那件衣服的颜色。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..models import Garment

BG = (11, 11, 12)
SURFACE = (21, 21, 23)
EDGE = (38, 38, 42)
PAPER = (237, 234, 228)
MUTED = (138, 138, 144)
BRASS = (200, 161, 90)

WIDTH = 900
PADDING = 60
COLUMNS = 2
CELL = 370
GAP = 34

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\PingFang.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)

CATEGORY_LABELS = {
    "top": "上装",
    "bottom": "下装",
    "outerwear": "外套",
    "dress": "连衣裙",
    "shoes": "鞋",
    "bag": "包",
    "accessory": "配饰",
}


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


def _wrap(text: str, per_line: int) -> list[str]:
    """按字数硬折行。中文没有空格，measure 每行更准但收益不大。"""
    lines = []
    for paragraph in text.split("\n"):
        while paragraph:
            lines.append(paragraph[:per_line])
            paragraph = paragraph[per_line:]
    return lines or [""]


def _hex_rgb(value: str | None, fallback: tuple[int, int, int] = (58, 58, 62)):
    if not value:
        return fallback
    raw = value.lstrip("#")
    if len(raw) == 3:
        raw = "".join(char * 2 for char in raw)
    try:
        return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except (ValueError, IndexError):
        return fallback


def _paste_contain(canvas: Image.Image, image: Image.Image, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    area_w, area_h = right - left, bottom - top
    scale = min(area_w / image.width, area_h / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(size, Image.LANCZOS)
    x = left + (area_w - size[0]) // 2
    y = top + (area_h - size[1]) // 2
    if resized.mode == "RGBA":
        canvas.paste(resized, (x, y), resized)
    else:
        canvas.paste(resized, (x, y))


def build_board(
    items: list[Garment],
    out_path: Path,
    *,
    title: str = "",
    subtitle: str = "",
    rationale: str = "",
) -> Path:
    """拼一张搭配板。缺图的单品用色块代替，不影响出图。"""
    rows = max(1, (len(items) + COLUMNS - 1) // COLUMNS)
    header_h = 190
    rationale_lines = _wrap(rationale, 34) if rationale else []
    footer_h = 60 + len(rationale_lines) * 34 if rationale_lines else 40
    height = header_h + rows * (CELL + 20) + footer_h

    canvas = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(canvas)

    draw.text((PADDING, 54), title or "今日搭配", font=_font(38), fill=PAPER)
    if subtitle:
        draw.text((PADDING, 108), subtitle, font=_font(20), fill=MUTED)
    draw.line([(PADDING, header_h - 24), (WIDTH - PADDING, header_h - 24)], fill=EDGE, width=2)

    for index, item in enumerate(items):
        row, column = divmod(index, COLUMNS)
        left = PADDING + column * (CELL + GAP)
        top = header_h + row * (CELL + 20)

        draw.rounded_rectangle(
            [left, top, left + CELL, top + CELL], radius=26, fill=SURFACE, outline=EDGE, width=2
        )

        inner = (left + 24, top + 24, left + CELL - 24, top + CELL - 90)
        pasted = False
        for candidate in (item.cutout_path, item.image_path):
            if not candidate:
                continue
            path = Path(candidate)
            if not path.is_absolute():
                path = Path("data") / candidate
            if path.exists():
                try:
                    with Image.open(path) as image:
                        _paste_contain(canvas, image.convert("RGBA"), inner)
                    pasted = True
                    break
                except OSError:
                    continue

        if not pasted:
            swatch = [inner[0] + 60, inner[1] + 50, inner[2] - 60, inner[3] - 50]
            # 黑色单品的色块会糊进深色背景里，给一条描边把它托出来
            draw.rounded_rectangle(
                swatch, radius=18, fill=_hex_rgb(item.color_hex), outline=(72, 72, 78), width=2
            )

        draw.text(
            (left + 24, top + CELL - 76),
            item.name[:14],
            font=_font(22),
            fill=PAPER,
        )
        meta = f"{CATEGORY_LABELS.get(item.category, item.category)} · {item.color_primary}"
        draw.text((left + 24, top + CELL - 44), meta, font=_font(17), fill=MUTED)

    if rationale_lines:
        base = header_h + rows * (CELL + 20) + 5
        draw.text((PADDING, base), "为什么是这套", font=_font(17), fill=BRASS)
        for offset, line in enumerate(rationale_lines):
            draw.text(
                (PADDING, base + 32 + offset * 34),
                line,
                font=_font(19),
                fill=MUTED,
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG", optimize=True)
    return out_path
