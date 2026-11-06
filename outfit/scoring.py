"""软打分：同一堆候选里，哪件更该被选上。

权重来自设计文档 8.4，集中在这里，方便以后调参时只改一个地方。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import rules
from .models import Garment

W_FORMALITY = 1.0
W_HARMONY = 0.8
W_FRESHNESS = 0.6
W_SKIN = 0.5
W_AFFINITY = 0.4
P_OVERLAP = 0.7

_FRESHNESS_WINDOW_DAYS = 30

# 只有这几类单品决定"这身衣服长什么样"，配色只看它们。
# 把鞋包配饰也算进去会出问题：件数越多、两两对数越多，均值反而被拉低，
# 结果就是包和手表永远选不上。
CORE_CATEGORIES = frozenset({"top", "bottom", "outerwear", "dress"})

# 参与"单件打分"的还包括鞋——鞋在很大程度上决定这身衣服正不正式。
SCORED_CATEGORIES = CORE_CATEGORIES | {"shoes"}

EXTRA_BONUS = 0.03
EXTRA_BONUS_CAP = 0.12


@dataclass
class Context:
    occasion: str
    temp_c: float
    band: str
    formality_range: tuple[int, int]
    skin_tone: str | None = None
    recent_outfit_ids: list[set[int]] | None = None
    now: datetime | None = None


def freshness(garment: Garment, now: datetime) -> float:
    """越久没穿越高，0..1。没穿过给满分。"""
    if garment.last_worn_at is None:
        return 1.0
    last = garment.last_worn_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days = (now - last).total_seconds() / 86400.0
    return max(0.0, min(1.0, days / _FRESHNESS_WINDOW_DAYS))


def affinity(garment: Garment) -> float:
    """穿得多的说明喜欢；10 次封顶。"""
    return min(1.0, garment.wear_count / 10.0)


def formality_fit(garment: Garment, ctx: Context) -> float:
    lo, hi = ctx.formality_range
    mid = (lo + hi) / 2.0
    return max(0.0, 1.0 - abs(garment.formality - mid) / 2.5)


def item_score(garment: Garment, ctx: Context) -> float:
    """单件在这个场合温暖度下的得分，0..1。"""
    now = ctx.now or datetime.now(timezone.utc)
    total = (
        W_FORMALITY * formality_fit(garment, ctx)
        + W_FRESHNESS * freshness(garment, now)
        + W_SKIN * rules.skin_tone_fit(ctx.skin_tone, garment.color_hex)
        + W_AFFINITY * affinity(garment)
    )
    denom = W_FORMALITY + W_FRESHNESS + W_SKIN + W_AFFINITY
    return total / denom


def harmony(items: list[Garment]) -> float:
    """核心单品两两之间的配色和谐度均值。件数不影响基准。"""
    core = [g for g in items if g.category in CORE_CATEGORIES]
    if len(core) < 2:
        return 0.8
    pairs = 0
    total = 0.0
    for i in range(len(core)):
        for j in range(i + 1, len(core)):
            a, b = core[i], core[j]
            total += rules.color_harmony(a.color_hex, b.color_hex, a.color_primary, b.color_primary)
            pairs += 1
    return total / pairs


def extras_bonus(items: list[Garment]) -> float:
    """鞋包配饰做的是"完整度"，不是"多一件多一分"，所以给小额固定加成。"""
    count = sum(1 for g in items if g.category in ("bag", "accessory"))
    return min(EXTRA_BONUS_CAP, EXTRA_BONUS * count)


def overlap(items: list[Garment], recent: list[set[int]] | None) -> float:
    """和最近几套里重合最多的一套的重合比例，0..1。"""
    if not recent:
        return 0.0
    ids = {g.id for g in items if g.id is not None}
    if not ids:
        return 0.0
    worst = 0.0
    for past in recent:
        if past:
            worst = max(worst, len(ids & past) / len(ids))
    return worst


def combo_score(items: list[Garment], ctx: Context) -> float:
    """一套的最终得分，0..1。

    单件均分只算"决定这身衣服长什么样"的那几件（上装/下装/外套/连衣裙/鞋）；
    包和配饰走固定加成，否则它们会被均值稀释掉，永远选不上。
    """
    scored = [g for g in items if g.category in SCORED_CATEGORIES] or items
    item_avg = sum(item_score(g, ctx) for g in scored) / len(scored)
    harm = harmony(items)
    fresh = sum(freshness(g, ctx.now or datetime.now(timezone.utc)) for g in scored) / len(scored)
    skin = sum(rules.skin_tone_fit(ctx.skin_tone, g.color_hex) for g in scored) / len(scored)
    like = sum(affinity(g) for g in scored) / len(scored)

    raw = (
        W_FORMALITY * item_avg
        + W_HARMONY * harm
        + W_FRESHNESS * fresh
        + W_SKIN * skin
        + W_AFFINITY * like
    ) / (W_FORMALITY + W_HARMONY + W_FRESHNESS + W_SKIN + W_AFFINITY)

    return max(0.0, raw + extras_bonus(items) - P_OVERLAP * overlap(items, ctx.recent_outfit_ids))
