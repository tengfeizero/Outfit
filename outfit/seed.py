"""一套用于演示和空库初始化的种子衣橱。

和 tests/conftest.py 里的数据同源：19 件覆盖四季、四种场合，
刻意留了几件"冬天不该出现"的短袖，好让规则看得出来。
"""

from __future__ import annotations

from .models import Garment

_RAW = [
    # (id, 名称, 品类, 子类, 主色名, 色值, 厚薄, 正式度, 版型, 材质)
    (1, "白棉T恤", "top", "tee", "白", "#F2F2F0", 1, 2, "regular", "cotton"),
    (2, "浅蓝牛津衬衫", "top", "shirt", "浅蓝", "#9DB4C8", 2, 3, "regular", "cotton"),
    (3, "黑羊毛针织", "top", "knit", "黑", "#1A1A1A", 3, 3, "regular", "wool"),
    (4, "灰短袖T", "top", "tee", "灰", "#8A8A8A", 1, 1, "regular", "cotton"),
    (5, "藏蓝西裤", "bottom", "trousers", "藏蓝", "#1F2A44", 3, 4, "regular", "wool"),
    (6, "浅蓝直筒牛仔", "bottom", "jeans", "浅蓝", "#6E8CA8", 3, 2, "regular", "denim"),
    (7, "米色阔腿裤", "bottom", "trousers", "米", "#D8CDB8", 2, 3, "oversized", "cotton"),
    (8, "藏蓝西装外套", "outerwear", "blazer", "藏蓝", "#1F2A44", 3, 4, "regular", "wool"),
    (9, "驼色大衣", "outerwear", "coat", "驼", "#B08A5E", 5, 4, "regular", "wool"),
    (10, "白运动鞋", "shoes", "sneaker", "白", "#F2F2F0", 1, 2, "regular", "leather"),
    (11, "黑乐福鞋", "shoes", "loafers", "黑", "#1A1A1A", 2, 4, "regular", "leather"),
    (12, "黑托特包", "bag", "tote", "黑", "#1A1A1A", 1, 3, "regular", "leather"),
    (13, "银手表", "accessory", "watch", "银", "#C0C0C0", 1, 3, "regular", "metal"),
    (14, "藏蓝连衣裙", "dress", "dress", "藏蓝", "#1F2A44", 2, 3, "regular", "silk"),
    (15, "黑短靴", "shoes", "boots", "黑", "#1A1A1A", 4, 3, "regular", "leather"),
    (16, "深灰高领毛衣", "top", "knit", "深灰", "#3A3A3A", 4, 3, "regular", "wool"),
    (17, "浅灰西装外套", "outerwear", "blazer", "浅灰", "#6B6B6B", 3, 4, "regular", "wool"),
    (18, "米色风衣", "outerwear", "trench", "米", "#D8CDB8", 4, 3, "regular", "cotton"),
    (19, "灰西裤", "bottom", "trousers", "深灰", "#3A3A3A", 3, 4, "regular", "wool"),
]


def demo_wardrobe() -> list[Garment]:
    return [
        Garment(
            id=gid,
            name=name,
            category=category,
            subcategory=subcategory,
            color_primary=color,
            color_hex=hex_value,
            warmth=warmth,
            formality=formality,
            fit=fit,
            material=material,
            pattern="solid",
            seasons=[],
            style_tags=[],
            status="active",
            label_confidence=1.0,
        )
        for (gid, name, category, subcategory, color, hex_value, warmth, formality, fit, material) in _RAW
    ]
