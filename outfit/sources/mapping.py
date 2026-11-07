"""把站点上的一件商品，翻译成我们衣橱里的字段。

英文色名、中文标题、价格、图片——各站点给的东西不一样，翻译规则集中放在这里，
采集器只负责把原始数据捞回来。这样加一个新站点时，大概率不用动这个文件。
"""

from __future__ import annotations

from .base import RawItem

# 英文色名 → 中文。优衣库这类站点给的是 "09 BLACK" 这种，前面还带编号。
EN_COLORS = {
    "BLACK": "黑",
    "WHITE": "白",
    "OFFWHITE": "米白",
    "IVORY": "米白",
    "NAVY": "藏蓝",
    "BLUE": "蓝",
    "LIGHTBLUE": "浅蓝",
    "GRAY": "灰",
    "GREY": "灰",
    "LIGHTGRAY": "浅灰",
    "DARKGRAY": "深灰",
    "BEIGE": "米",
    "BROWN": "棕",
    "DARKBROWN": "棕",
    "KHAKI": "卡其",
    "OLIVE": "军绿",
    "GREEN": "绿",
    "RED": "红",
    "WINE": "酒红",
    "BURGUNDY": "酒红",
    "PINK": "粉",
    "PURPLE": "紫",
    "YELLOW": "黄",
    "ORANGE": "橙",
    "CAMEL": "驼",
    "SILVER": "银",
    "GOLD": "金",
}

# 国内站点常见的说法，和我们衣橱里的色名对不上，先收拢
CN_ALIASES = {
    "藏青": "藏蓝",
    "藏蓝色": "藏蓝",
    "深蓝": "藏蓝",
    "宝蓝": "蓝",
    "天蓝": "浅蓝",
    "米色": "米",
    "杏色": "米",
    "驼色": "驼",
    "咖啡": "棕",
    "咖色": "棕",
    "军绿": "军绿",
    "墨绿": "墨绿",
    "酒红": "酒红",
    "灰色": "灰",
    "黑色": "黑",
    "白色": "白",
    "卡其": "卡其",
}

CATEGORY_RULES: list[tuple[tuple[str, ...], str]] = [    (("羽绒", "down", "棉服", "大衣", "风衣", "夹克", "外套", "jacket", "coat", "parka"), "outerwear"),
    (("连衣裙", "dress"), "dress"),
    (("长裤", "西裤", "牛仔裤", "短裤", "半身裙", "裙", "pants", "jeans", "trousers"), "bottom"),
    (("t恤", "衬衫", "polo", "针织", "卫衣", "毛衣", "背心", "shirt", "tee", "knit", "sweat"), "top"),
    (("鞋", "靴", "凉鞋", "sneaker", "shoes"), "shoes"),
    (("背包", "挎包", "包", "bag"), "bag"),
    (("帽", "围巾", "腰带", "袜", "手套", "配饰", "cap", "scarf", "belt"), "accessory"),
]

WARMTH_BY_KEYWORD: list[tuple[tuple[str, ...], int]] = [
    (("羽绒", "down", "厚"), 5),
    (("大衣", "棉服", "羊毛", "呢"), 5),
    (("夹克", "风衣", "西装", "jacket", "coat"), 4),
    (("卫衣", "针织", "毛衣", "sweat", "knit"), 3),
    (("衬衫", "长袖", "shirt"), 2),
    (("t恤", "短袖", "背心", "tee"), 1),
]

DEFAULT_WARMTH = {"outerwear": 4, "top": 3, "bottom": 3, "dress": 3, "shoes": 2, "bag": 1, "accessory": 1}
DEFAULT_FORMALITY = {"outerwear": 3, "top": 3, "bottom": 3, "dress": 3, "shoes": 3, "bag": 3, "accessory": 3}


def _has(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def guess_category(title: str, hint: str | None = None) -> str:
    if hint in DEFAULT_WARMTH:
        return hint
    for words, category in CATEGORY_RULES:
        if _has(title, words):
            return category
    return "top"


def guess_warmth(title: str, category: str) -> int:
    for words, value in WARMTH_BY_KEYWORD:
        if _has(title, words):
            return value
    return DEFAULT_WARMTH.get(category, 3)


def guess_formality(title: str, category: str) -> int:
    if category == "outerwear":
        if _has(title, ("西装", "blazer")):
            return 4
        if _has(title, ("大衣", "coat", "风衣")):
            return 4
        return 2
    if category == "top":
        if _has(title, ("衬衫", "shirt")):
            return 3
        if _has(title, ("卫衣", "sweat", "t恤", "tee")):
            return 2
        return 3
    if category == "bottom":
        if _has(title, ("西裤", "trousers")):
            return 4
        if _has(title, ("牛仔", "jeans", "运动")):
            return 2
        return 3
    if category == "shoes":
        if _has(title, ("皮鞋", "乐福", "loafer")):
            return 4
        if _has(title, ("运动", "sneaker")):
            return 2
        return 3
    return DEFAULT_FORMALITY.get(category, 3)


def normalize_color(raw: str | None) -> tuple[str, str | None]:
    """'09 BLACK' / '藏青' / '藏青色' / None → ('藏蓝', '#1F2A44')。"""
    from ..capture import PALETTE

    if not raw:
        return "未标注", None
    text = str(raw).strip()
    if not text:
        return "未标注", None

    # 去掉前导编号和空格：'09 BLACK' → 'BLACK'
    cleaned = "".join(char for char in text if not char.isdigit()).strip()
    key = cleaned.replace(" ", "").replace("-", "").upper()
    if key in EN_COLORS:
        name = EN_COLORS[key]
        return name, PALETTE.get(name)

    # 中文：先把"藏青色"这种带"色"的写法收成"藏青"
    simplified = cleaned[:-1] if cleaned.endswith("色") and len(cleaned) > 1 else cleaned
    if simplified in CN_ALIASES:
        name = CN_ALIASES[simplified]
        return name, PALETTE.get(name)
    if simplified in PALETTE:
        return simplified, PALETTE[simplified]

    for chinese in PALETTE:
        if chinese in text:
            return chinese, PALETTE[chinese]
    return simplified or "未标注", None


def to_garment(item: RawItem) -> dict:
    """映射成 Garment 的字段。不写库，纯函数，方便测。"""
    category = guess_category(item.title, item.category_hint)
    color_name, color_hex = normalize_color(item.color_name)
    if item.color_hex:
        color_hex = item.color_hex

    return {
        "name": _trim_name(item.title, color_name),
        "category": category,
        "color_primary": color_name,
        "color_hex": color_hex,
        "warmth": guess_warmth(item.title, category),
        "formality": guess_formality(item.title, category),
        "price_cny": item.price,
        "source_url": item.product_url,
        "external_id": item.external_id,
    }


def _trim_name(title: str, color: str) -> str:
    """标题太长的话，取前 18 个字——衣橱里要能一眼扫过去。"""
    name = " ".join(title.split())
    if color and color in name and color not in ("未标注",):
        return name
    return name[:18] if len(name) > 18 else name
