"""照片进来后的第一道加工：转正、缩尺寸、猜主色。

这些全都用 Pillow 在本地算，不调任何外部服务——因为它要快，而且
"这件衣服大致什么颜色"这件事不值得为它联网。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

MAX_EDGE = 1600
SAMPLE_EDGE = 64

# 常见颜色名 → 代表色值。用来把"#8E2F35"说成"酒红"，比一堆十六进制好读。
PALETTE: dict[str, str] = {
    "黑": "#121212",
    "深灰": "#3A3A3A",
    "灰": "#8A8A8A",
    "浅灰": "#C9C9C9",
    "白": "#F5F5F2",
    "米白": "#EFE7D6",
    "米": "#D8CDB8",
    "卡其": "#B9A57F",
    "驼": "#B08A5E",
    "棕": "#6B4A32",
    "酒红": "#7B2C33",
    "红": "#C0392B",
    "粉": "#E3A6B0",
    "橙": "#D97B33",
    "黄": "#D9B23C",
    "军绿": "#4F5B3A",
    "绿": "#3E7B4F",
    "墨绿": "#1F3A2E",
    "浅蓝": "#9DB4C8",
    "蓝": "#3C6E9F",
    "藏蓝": "#1F2A44",
    "紫": "#6B4E7A",
    "银": "#C0C0C0",
    "金": "#C8A15A",
}


def normalize(path: Path) -> Path:
    """按 EXIF 转正、长边缩到 1600、统一存成 JPEG。返回处理后的路径。"""
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            converted = image.convert("RGBA")
            background.paste(converted, mask=converted.split()[-1])
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        longest = max(image.size)
        if longest > MAX_EDGE:
            scale = MAX_EDGE / longest
            image = image.resize(
                (round(image.width * scale), round(image.height * scale)),
                Image.LANCZOS,
            )
        image.save(path, "JPEG", quality=88, optimize=True)
    return path


def _is_background(pixel: tuple[int, int, int]) -> bool:
    """接近纯白的算背景。多数衣服照片是白底或浅灰底。"""
    r, g, b = pixel
    return r > 240 and g > 240 and b > 240


def dominant_color(path: Path) -> str:
    """猜主色。先剔除白底，剩下的按色块投票。"""
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((SAMPLE_EDGE, SAMPLE_EDGE), Image.LANCZOS)
        raw = image.tobytes()  # RGB 三字节一像素，避免用已弃用的 getdata
    pixels = [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]

    buckets: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
    for pixel in pixels:
        if _is_background(pixel):
            continue
        key = (pixel[0] // 24, pixel[1] // 24, pixel[2] // 24)
        buckets.setdefault(key, []).append(pixel)

    if not buckets:  # 整张图都是白的——白色衣服，就返回白
        return PALETTE["白"]

    biggest = max(buckets.values(), key=len)
    r = round(sum(p[0] for p in biggest) / len(biggest))
    g = round(sum(p[1] for p in biggest) / len(biggest))
    b = round(sum(p[2] for p in biggest) / len(biggest))
    return f"#{r:02X}{g:02X}{b:02X}"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    raw = hex_color.lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def nearest_color_name(hex_color: str) -> str:
    """把色值翻译成中文色名。用平方距离，菜谱级精度就够。"""
    target = _rgb(hex_color)
    best_name = "灰"
    best_distance = None
    for name, value in PALETTE.items():
        red, green, blue = _rgb(value)
        distance = (
            (target[0] - red) ** 2 * 0.3
            + (target[1] - green) ** 2 * 0.59
            + (target[2] - blue) ** 2 * 0.11
        )
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_name = name
    return best_name


def describe_color(hex_color: str) -> tuple[str, str]:
    return hex_color, nearest_color_name(hex_color)
