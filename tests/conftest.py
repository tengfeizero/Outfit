"""共用的测试数据：一套 15 件的种子衣橱。

刻意覆盖了四种场合、四季温度、以及"冬天不该出现"的短袖，
好让规则层的测试有真实的边界可打。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from outfit.models import Garment  # noqa: E402


def _g(**kwargs) -> Garment:
    defaults = dict(
        color_hex=None,
        subcategory=None,
        fit="regular",
        pattern="solid",
        material="cotton",
        seasons=[],
        style_tags=[],
        status="active",
        wear_count=0,
        last_worn_at=None,
        label_confidence=1.0,
    )
    defaults.update(kwargs)
    return Garment(**defaults)


@pytest.fixture
def wardrobe() -> list[Garment]:
    return [
        _g(id=1, name="白棉T恤", category="top", subcategory="tee",
           color_primary="白", color_hex="#F2F2F0", warmth=1, formality=2),
        _g(id=2, name="浅蓝牛津衬衫", category="top", subcategory="shirt",
           color_primary="浅蓝", color_hex="#9DB4C8", warmth=2, formality=3),
        _g(id=3, name="黑羊毛针织", category="top", subcategory="knit",
           color_primary="黑", color_hex="#1A1A1A", warmth=3, formality=3, material="wool"),
        _g(id=4, name="灰短袖T", category="top", subcategory="tee",
           color_primary="灰", color_hex="#8A8A8A", warmth=1, formality=1),
        _g(id=5, name="藏蓝西裤", category="bottom", subcategory="trousers",
           color_primary="藏蓝", color_hex="#1F2A44", warmth=3, formality=4),
        _g(id=6, name="浅蓝直筒牛仔", category="bottom", subcategory="jeans",
           color_primary="浅蓝", color_hex="#6E8CA8", warmth=3, formality=2, material="denim"),
        _g(id=7, name="米色阔腿裤", category="bottom", subcategory="trousers",
           color_primary="米", color_hex="#D8CDB8", warmth=2, formality=3),
        _g(id=8, name="藏蓝西装外套", category="outerwear", subcategory="blazer",
           color_primary="藏蓝", color_hex="#1F2A44", warmth=3, formality=4, material="wool"),
        _g(id=9, name="驼色大衣", category="outerwear", subcategory="coat",
           color_primary="驼", color_hex="#B08A5E", warmth=5, formality=4, material="wool"),
        _g(id=10, name="白运动鞋", category="shoes", subcategory="sneaker",
           color_primary="白", color_hex="#F2F2F0", warmth=1, formality=2),
        _g(id=11, name="黑乐福鞋", category="shoes", subcategory="loafers",
           color_primary="黑", color_hex="#1A1A1A", warmth=2, formality=4, material="leather"),
        _g(id=12, name="黑托特包", category="bag", subcategory="tote",
           color_primary="黑", color_hex="#1A1A1A", warmth=1, formality=3),
        _g(id=13, name="银手表", category="accessory", subcategory="watch",
           color_primary="银", color_hex="#C0C0C0", warmth=1, formality=3),
        _g(id=14, name="藏蓝连衣裙", category="dress", subcategory="dress",
           color_primary="藏蓝", color_hex="#1F2A44", warmth=2, formality=3),
        _g(id=15, name="黑短靴", category="shoes", subcategory="boots",
           color_primary="黑", color_hex="#1A1A1A", warmth=4, formality=3, material="leather"),
        _g(id=16, name="深灰高领毛衣", category="top", subcategory="knit",
           color_primary="深灰", color_hex="#3A3A3A", warmth=4, formality=3, material="wool"),
        _g(id=17, name="浅灰西装外套", category="outerwear", subcategory="blazer",
           color_primary="浅灰", color_hex="#6B6B6B", warmth=3, formality=4),
        _g(id=18, name="米色风衣", category="outerwear", subcategory="trench",
           color_primary="米", color_hex="#D8CDB8", warmth=4, formality=3),
        _g(id=19, name="灰西裤", category="bottom", subcategory="trousers",
           color_primary="深灰", color_hex="#3A3A3A", warmth=3, formality=4),
    ]
