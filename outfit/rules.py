"""纯规则层：温区、正式度、配色。

这里所有函数都是纯函数——不碰数据库、不碰网络、不读配置。
这样它们可以被单元测试穷举边界，也可以被将来的任何入口复用。
"""

from __future__ import annotations

import colorsys

TEMP_BANDS = ("hot", "warm", "mild", "cold", "freezing")

BAND_LABELS = {
    "hot": "酷暑",
    "warm": "暖",
    "mild": "微凉",
    "cold": "冷",
    "freezing": "严寒",
}

_WARMTH_RANGE = {
    "hot": (1, 2),
    "warm": (1, 3),
    "mild": (2, 4),
    "cold": (3, 5),
    "freezing": (4, 5),
}

_FORMALITY_RANGE = {
    "interview": (4, 5),
    "work": (3, 4),
    "date": (2, 4),
    "sport": (1, 2),
    "home": (1, 1),
}

DEFAULT_FORMALITY = (2, 4)

NEUTRAL_NAMES = frozenset(
    {"黑", "白", "灰", "米", "米白", "藏蓝", "藏青", "驼", "卡其", "银"}
)


def temp_band(temp_c: float) -> str:
    """把温度归入五档。边界取"含下界"。"""
    if temp_c >= 28:
        return "hot"
    if temp_c >= 22:
        return "warm"
    if temp_c >= 15:
        return "mild"
    if temp_c >= 8:
        return "cold"
    return "freezing"


def allowed_warmth(band: str) -> tuple[int, int]:
    """该温区允许的衣物厚薄区间（1 最薄，5 最厚）。"""
    return _WARMTH_RANGE[band]


def jacket_required(band: str) -> bool:
    """22℃ 以下必须有外套。"""
    return band in ("mild", "cold", "freezing")


def formality_range(occasion: str) -> tuple[int, int]:
    return _FORMALITY_RANGE.get(occasion, DEFAULT_FORMALITY)


def hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    """#RRGGBB → (h 0..360, s 0..1, l 0..1)。解析失败抛 ValueError。"""
    raw = hex_color.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    if len(raw) != 6:
        raise ValueError(f"不是合法的十六进制颜色：{hex_color!r}")
    r, g, b = (int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360.0, s, l


def is_neutral(hex_color: str | None = None, name: str | None = None) -> bool:
    """中性色：黑白灰米驼一类，或色相饱和度极低。"""
    if name and name.strip() in NEUTRAL_NAMES:
        return True
    if hex_color:
        try:
            _, s, l = hex_to_hsl(hex_color)
        except ValueError:
            return False
        if s < 0.15 or l > 0.90 or l < 0.12:
            return True
    return False


def hue_distance(h1: float, h2: float) -> float:
    d = abs(h1 - h2) % 360.0
    return min(d, 360.0 - d)


def color_harmony(
    hex_a: str | None,
    hex_b: str | None,
    name_a: str | None = None,
    name_b: str | None = None,
) -> float:
    """两件衣服搭在一起的配色得分，0..1。没有色值时给中性分 0.6。"""
    if not hex_a or not hex_b:
        return 0.6

    neutral_a = is_neutral(hex_a, name_a)
    neutral_b = is_neutral(hex_b, name_b)

    if neutral_a and neutral_b:
        return 0.85
    if neutral_a or neutral_b:
        return 0.90

    try:
        h1, s1, l1 = hex_to_hsl(hex_a)
        h2, s2, l2 = hex_to_hsl(hex_b)
    except ValueError:
        return 0.6

    dh = hue_distance(h1, h2)
    if dh < 20:
        base = 0.95
    elif dh < 60:
        base = 0.85
    elif dh <= 120:
        base = 0.55
    else:
        base = 0.80

    # 两件都很艳、且明度接近 —— "打架"
    if s1 > 0.55 and s2 > 0.55 and abs(l1 - l2) < 0.12:
        base -= 0.25

    return max(0.0, min(1.0, base))


def skin_tone_fit(skin_tone: str | None, hex_color: str | None) -> float:
    """肤色与主色的契合度，0..1。仅作软加分，不做硬性排除。"""
    if not skin_tone or not hex_color:
        return 0.5
    try:
        h, s, l = hex_to_hsl(hex_color)
    except ValueError:
        return 0.5
    if s < 0.18:
        return 0.6  # 低饱和色基本不挑人

    warm_hues = 20 <= h <= 60  # 橘、棕、驼
    if skin_tone == "warm":
        return 0.75 if warm_hues else 0.45
    if skin_tone == "cool":
        return 0.45 if warm_hues else 0.75
    return 0.6


def comfort_score(warmth: int, fit: str | None) -> float:
    """舒适度，0..1。薄、宽松更舒适。"""
    base = (5 - warmth) / 4.0
    if fit == "oversized":
        base += 0.15
    elif fit == "slim":
        base -= 0.10
    return max(0.0, min(1.0, base))


def temperature_advice(band: str, temp_c: float) -> str:
    if band == "hot":
        return f"{temp_c:.0f}℃，越薄越透气越好，别穿深色吸热。"
    if band == "warm":
        return f"{temp_c:.0f}℃，短袖或薄长袖都行，带件薄外套备用。"
    if band == "mild":
        return f"{temp_c:.0f}℃，早晚凉，外套是必需的。"
    if band == "cold":
        return f"{temp_c:.0f}℃，要外套加内搭，别只穿毛衣。"
    return f"{temp_c:.0f}℃，里外三层，注意脖子和脚。"
