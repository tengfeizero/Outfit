"""组套：从候选池里拼出 3 套说得通的方案。

M1 阶段没有大模型参与——纯规则 + 打分。这样有两件事是确定的：
一是不花钱，二是错了能查。M2 再把"措辞"和"精排"交给模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product

from .. import candidates, rules, scoring
from ..models import BodyProfile, Garment

MAX_COMBOS = 20000
PER_CATEGORY_CAP = {"tops": 6, "bottoms": 6, "outers": 4, "shoes": 5, "bags": 3, "accessories": 3}
DIVERSITY_PENALTY = 0.20

OCCASION_LABELS = {
    "interview": "面试",
    "work": "上班",
    "date": "约会",
    "sport": "运动",
    "home": "居家",
    "custom": "今天",
}


@dataclass
class Plan:
    items: list[Garment]
    score: float
    rationale: str
    label: str = "备选"

    @property
    def ids(self) -> list[int]:
        return [g.id for g in self.items if g.id is not None]

    @property
    def avg_formality(self) -> float:
        return sum(g.formality for g in self.items) / len(self.items)

    @property
    def comfort(self) -> float:
        return sum(rules.comfort_score(g.warmth, g.fit) for g in self.items) / len(self.items)

    def summary(self) -> list[dict]:
        return [
            {
                "id": g.id,
                "name": g.name,
                "category": g.category,
                "subcategory": g.subcategory,
                "color_primary": g.color_primary,
                "color_hex": g.color_hex,
                "image_path": g.image_path,
                "cutout_path": g.cutout_path,
            }
            for g in self.items
        ]


@dataclass
class _Entry:
    items: list[Garment]
    score: float

    @property
    def ids(self) -> set[int]:
        return {g.id for g in self.items if g.id is not None}

    @property
    def core_ids(self) -> set[int]:
        return {g.id for g in self.items if g.id is not None and g.category in scoring.CORE_CATEGORIES}

    @property
    def comfort(self) -> float:
        return sum(rules.comfort_score(g.warmth, g.fit) for g in self.items) / len(self.items)

    @property
    def avg_formality(self) -> float:
        return sum(g.formality for g in self.items) / len(self.items)


def _rank(group: list[Garment], ctx: scoring.Context) -> list[Garment]:
    return sorted(group, key=lambda g: scoring.item_score(g, ctx), reverse=True)


def _bodies(pool: candidates.Pool) -> list[list[Garment]]:
    bodies: list[list[Garment]] = [[d] for d in pool.dresses]
    for top, bottom in product(pool.tops, pool.bottoms):
        bodies.append([top, bottom])
    return bodies


def _extras(pool: candidates.Pool, ctx: scoring.Context):
    """鞋、包、配饰的有限组合，避免组合爆炸同时保留 0..2 件配饰。"""
    shoes = _rank(pool.shoes, ctx)[: PER_CATEGORY_CAP["shoes"]]
    bags = [None] + _rank(pool.bags, ctx)[: PER_CATEGORY_CAP["bags"]]
    accs = _rank(pool.accessories, ctx)[: PER_CATEGORY_CAP["accessories"]]

    acc_options: list[list[Garment]] = [[]]
    acc_options.extend([a] for a in accs)
    if len(accs) >= 2:
        acc_options.append(accs[:2])

    for combo in product(shoes, bags, acc_options):
        shoe, bag, acc = combo
        yield [shoe] + ([bag] if bag else []) + list(acc)


def build_plans(
    garments: list[Garment],
    *,
    occasion: str,
    temp_c: float,
    profile: BodyProfile | None = None,
    recent_outfit_ids: list[set[int]] | None = None,
    preference: scoring.Preference | None = None,
    limit: int = 3,
    now: datetime | None = None,
) -> tuple[list[Plan], candidates.Pool]:
    """返回 (方案列表, 候选池)。池子一并返回，是为了让界面能解释"为什么没有"。"""
    now = now or datetime.now(timezone.utc)
    pool = candidates.build(garments, occasion=occasion, temp_c=temp_c, now=now)

    if not pool.is_usable():
        return [], pool

    ctx = scoring.Context(
        occasion=occasion,
        temp_c=temp_c,
        band=pool.band,
        formality_range=pool.formality,
        skin_tone=profile.skin_tone if profile else None,
        recent_outfit_ids=recent_outfit_ids or [],
        preference=preference,
        now=now,
    )

    tops = _rank(pool.tops, ctx)[: PER_CATEGORY_CAP["tops"]]
    bottoms = _rank(pool.bottoms, ctx)[: PER_CATEGORY_CAP["bottoms"]]
    outers = _rank(pool.outers, ctx)[: PER_CATEGORY_CAP["outers"]]
    dresses = _rank(pool.dresses, ctx)[: PER_CATEGORY_CAP["tops"]]

    outer_options: list[Garment | None]
    if pool.needs_jacket:
        if not outers:
            return [], pool
        outer_options = list(outers)
    else:
        outer_options = [None] + outers

    inner_pool = candidates.Pool(
        tops=tops, bottoms=bottoms, dresses=dresses, band=pool.band
    )

    entries: list[_Entry] = []
    seen_bodies = 0
    for body in _bodies(inner_pool):
        seen_bodies += 1
        for outer in outer_options:
            for extra in _extras(pool, ctx):
                items = list(body) + ([outer] if outer else []) + extra
                if len(entries) >= MAX_COMBOS:
                    break
                entries.append(_Entry(items=items, score=scoring.combo_score(items, ctx)))

    if not entries:
        return [], pool

    entries.sort(key=lambda e: e.score, reverse=True)

    chosen: list[tuple[_Entry, str]] = []
    taken_ids: list[set[int]] = []
    taken_core: list[set[int]] = []
    best_formality = max(e.avg_formality for e in entries)
    best_comfort = max(e.comfort for e in entries)

    def diversified(entry: _Entry) -> float:
        """和已选方案重合越多，越往后排。硬性"必须不同"做不到时，这层软惩罚更稳。"""
        if not taken_ids:
            return entry.score
        worst = max(len(entry.ids & s) / max(1, len(entry.ids)) for s in taken_ids)
        return entry.score - DIVERSITY_PENALTY * worst

    def _take(entry: _Entry, role: str) -> None:
        chosen.append((entry, role))
        taken_ids.append(entry.ids)
        taken_core.append(entry.core_ids)

    def choose(predicate=None, need_core_diff: int = 1, role: str = "备选") -> bool:
        options = sorted(
            (e for e in entries if e.ids not in taken_ids and (predicate is None or predicate(e))),
            key=diversified,
            reverse=True,
        )
        if not options:
            return False
        for entry in options:
            if all(len(entry.core_ids - previous) >= need_core_diff for previous in taken_core):
                _take(entry, role)
                return True
        # 衣橱撑不住，给最好的那套——少一套比给一套几乎一样的更糟
        _take(options[0], role)
        return True

    choose(role="首选")  # 综合最优
    choose(lambda e: e.avg_formality >= best_formality - 0.6, role="更正式")
    choose(lambda e: e.comfort >= best_comfort - 0.08, role="更舒服")
    while len(chosen) < limit and choose():
        pass

    plans = [
        Plan(
            items=entry.items,
            score=round(entry.score, 3),
            rationale=_rationale(entry.items, pool, temp_c),
            label=role,
        )
        for entry, role in chosen[:limit]
    ]
    return plans, pool


def _rationale(items: list[Garment], pool: candidates.Pool, temp_c: float) -> str:
    occ = OCCASION_LABELS.get(pool.occasion, "今天")
    formality = sum(g.formality for g in items) / len(items)
    words: list[str] = [f"正式度 {formality:.1f}/5，适合{occ}"]

    outer = next((g for g in items if g.category == "outerwear"), None)
    if outer:
        words.append(f"{temp_c:.0f}℃ 加一件{outer.color_primary}外套")
    elif pool.band == "hot":
        words.append(f"{temp_c:.0f}℃ 不用外套，越透气越好")

    colors = [g.color_primary for g in items if g.category in ("top", "bottom", "dress", "outerwear")]
    if len(colors) >= 2:
        colors_named = "＋".join(dict.fromkeys(colors))
        words.append(f"{colors_named}这一组配色不出错")

    if any(g.category == "accessory" for g in items):
        words.append("加了一件配饰提神")

    return "；".join(words) + "。"
