"""买前判断：这件新衣服值不值得买。

刻意不用大模型。判断依据就三条，全都能从衣橱数据直接算出来：
重复（已经有两件差不多的）、互补（能和多少件搭）、空缺（这个品类还没有）。

这些比"让模型凭感觉说"更稳，也更容易解释——用户会问"为什么"，答案必须站得住。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import rules
from .models import Garment

# 什么和什么能搭在一起。同一组里的不算互补（两件上装搭不成一套）。
SLOT_GROUPS = {
    "top": "upper",
    "dress": "upper",
    "outerwear": "layer",
    "bottom": "lower",
    "shoes": "shoes",
    "bag": "carry",
    "accessory": "carry",
}

CATEGORY_LABELS = {
    "top": "上装",
    "bottom": "下装",
    "outerwear": "外套",
    "dress": "连衣裙",
    "shoes": "鞋",
    "bag": "包",
    "accessory": "配饰",
}

# 相似判定：色差在这个范围内算"差不多的颜色"
SIMILAR_COLOR_DISTANCE = 60.0
PAIR_HARMONY_MIN = 0.75


@dataclass
class Verdict:
    verdict: str  # buy / skip / depends
    title: str
    reasons: list[str] = field(default_factory=list)
    pairs_with: list[int] = field(default_factory=list)
    duplicate_of: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "title": self.title,
            "reasons": self.reasons,
            "pairs_with": self.pairs_with,
            "duplicate_of": self.duplicate_of,
        }


def _rgb(hex_color: str) -> tuple[int, int, int]:
    raw = hex_color.lstrip("#")
    if len(raw) == 3:
        raw = "".join(char * 2 for char in raw)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def color_similarity(a: str | None, b: str | None) -> float:
    """0..1。两个色值都认不出来时给 0.5，不假装知道。"""
    if not a or not b:
        return 0.5
    try:
        first, second = _rgb(a), _rgb(b)
    except ValueError:
        return 0.5
    distance = sum((x - y) ** 2 for x, y in zip(first, second)) ** 0.5
    return max(0.0, 1.0 - distance / 441.67)  # 441.67 = 黑白之间的最大距离


def _slot(category: str) -> str:
    return SLOT_GROUPS.get(category, category)


def _complements(candidate: Garment, item: Garment) -> bool:
    """两件能不能穿在一起。"""
    if _slot(candidate.category) == _slot(item.category):
        return False
    if candidate.category == "dress" and item.category in ("top", "bottom"):
        return False
    if item.category == "dress" and candidate.category in ("top", "bottom"):
        return False
    if abs(candidate.formality - item.formality) > 2:
        return False
    return rules.color_harmony(
        candidate.color_hex, item.color_hex, candidate.color_primary, item.color_primary
    ) >= PAIR_HARMONY_MIN


def find_duplicates(candidate: Garment, wardrobe: list[Garment]) -> list[Garment]:
    duplicates = []
    for item in wardrobe:
        if item.status != "active":
            continue
        if item.category != candidate.category:
            continue
        if abs(item.formality - candidate.formality) > 1:
            continue
        if color_similarity(candidate.color_hex, item.color_hex) < 0.72:
            continue
        duplicates.append(item)
    return duplicates


def evaluate(candidate: Garment, wardrobe: list[Garment], limit: int = 3) -> Verdict:
    active = [item for item in wardrobe if item.status == "active"]
    duplicates = find_duplicates(candidate, active)
    partners = [item for item in active if _complements(candidate, item)]
    partners.sort(
        key=lambda item: rules.color_harmony(
            candidate.color_hex, item.color_hex, candidate.color_primary, item.color_primary
        ),
        reverse=True,
    )
    pairs_with = [item.id for item in partners[:limit] if item.id is not None]

    label = CATEGORY_LABELS.get(candidate.category, "单品")
    reasons: list[str] = []

    if not active:
        return Verdict(
            verdict="depends",
            title="衣橱还空着，说不好",
            reasons=["先把常穿的衣服录进来，这类判断才有依据。"],
        )

    if duplicates:
        names = "、".join(f"「{item.name}」" for item in duplicates[:3])
        reasons.append(f"和你已有的{names}很像——同品类、同色系、正式度接近。")

    if len(partners) >= 4:
        reasons.append(f"能和衣橱里 {len(partners)} 件搭成一套，使用率不会低。")
    elif partners:
        reasons.append(f"能和 {len(partners)} 件搭，但选择不算多。")

    same_slot = [item for item in active if _slot(item.category) == _slot(candidate.category)]
    if not same_slot:
        reasons.append(f"衣橱里还没有{label}，补一件是填空缺。")

    # 结论：重复优先于百搭。
    # 一件再百搭的衣服，如果家里已经有两件几乎一样的，买回去也只是挂进衣柜。
    if len(duplicates) >= 2:
        verdict, title = "skip", "不必买，你已经有两件差不多的了"
    elif len(duplicates) == 1 and len(partners) <= 3:
        verdict, title = "skip", "和已有的一件太像，搭起来也不会多出花样"
    elif len(duplicates) == 1:
        verdict, title = "depends", "已有类似的，但它确实百搭——除非你现在就想要这件"
    elif len(partners) >= 4:
        verdict, title = "buy", "值得买，能搭的东西够多"
    elif len(partners) >= 3:
        verdict, title = "depends", "看价格，搭得上一套但不算必需"
    elif len(partners) >= 1:
        verdict, title = "depends", "能搭的很少，除非你就喜欢它"
    else:
        verdict, title = "skip", "搭不上你现有的衣服"

    if not reasons:
        reasons.append("衣橱数据太少，这条判断参考价值有限。")

    return Verdict(
        verdict=verdict,
        title=title,
        reasons=reasons,
        pairs_with=pairs_with,
        duplicate_of=[item.id for item in duplicates if item.id is not None],
    )
