"""候选池：把衣橱按"今天能不能穿"筛成几堆。

这是整个系统里最重要的一道闸——设计文档 5.2 第 3 条：候选池由规则生成，
模型只在池子里挑。所以这里全部是确定性逻辑，没有模型参与。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import rules
from .models import Garment

# 衣橱可用单品少于这个数时，"最近三天穿过"的规则放宽成一天
THIN_WARDROBE = 8


@dataclass
class Pool:
    tops: list[Garment] = field(default_factory=list)
    bottoms: list[Garment] = field(default_factory=list)
    dresses: list[Garment] = field(default_factory=list)
    outers: list[Garment] = field(default_factory=list)
    shoes: list[Garment] = field(default_factory=list)
    bags: list[Garment] = field(default_factory=list)
    accessories: list[Garment] = field(default_factory=list)

    band: str = "warm"
    occasion: str = "work"
    formality: tuple[int, int] = (2, 4)
    needs_jacket: bool = False
    relaxed: bool = False
    dropped: dict[str, int] = field(default_factory=dict)

    def all_items(self) -> list[Garment]:
        out: list[Garment] = []
        for group in (
            self.tops,
            self.bottoms,
            self.dresses,
            self.outers,
            self.shoes,
            self.bags,
            self.accessories,
        ):
            out.extend(group)
        return out

    def count(self) -> int:
        return len(self.all_items())

    def is_usable(self) -> bool:
        """至少能凑出一套。"""
        body = bool(self.dresses) or (bool(self.tops) and bool(self.bottoms))
        return body and bool(self.shoes)

    def explain(self) -> str:
        if self.is_usable():
            return ""
        missing = []
        if not self.dresses and not (self.tops and self.bottoms):
            missing.append("上装+下装（或连衣裙）")
        if not self.shoes:
            missing.append("鞋")
        if self.needs_jacket and not self.outers:
            missing.append("外套")
        return "衣橱里缺少：" + "、".join(missing) + f"（{rules.BAND_LABELS[self.band]}天）"


def _worn_within(garment: Garment, now: datetime, days: int) -> bool:
    if garment.last_worn_at is None:
        return False
    last = garment.last_worn_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last) < timedelta(days=days)


def build(
    garments: list[Garment],
    *,
    occasion: str,
    temp_c: float,
    now: datetime | None = None,
) -> Pool:
    now = now or datetime.now(timezone.utc)
    band = rules.temp_band(temp_c)
    lo_warmth, hi_warmth = rules.allowed_warmth(band)
    f_lo, f_hi = rules.formality_range(occasion)

    pool = Pool(
        band=band,
        occasion=occasion,
        formality=(f_lo, f_hi),
        needs_jacket=rules.jacket_required(band),
    )

    # 第一步：硬性条件
    eligible: list[Garment] = []
    for g in garments:
        if g.status != "active":
            pool.dropped["状态不是在用"] = pool.dropped.get("状态不是在用", 0) + 1
            continue
        if not (lo_warmth <= g.warmth <= hi_warmth):
            pool.dropped["厚薄不合天气"] = pool.dropped.get("厚薄不合天气", 0) + 1
            continue
        if not (f_lo <= g.formality <= f_hi):
            pool.dropped["正式度不合场合"] = pool.dropped.get("正式度不合场合", 0) + 1
            continue
        eligible.append(g)

    # 第二步：新鲜度——衣橱太薄就放宽
    fresh = [g for g in eligible if not _worn_within(g, now, 3)]
    if len(fresh) < THIN_WARDROBE:
        fresh = [g for g in eligible if not _worn_within(g, now, 1)]
        pool.relaxed = True

    # 第三步：分堆
    for g in fresh:
        target = {
            "top": pool.tops,
            "bottom": pool.bottoms,
            "dress": pool.dresses,
            "outerwear": pool.outers,
            "shoes": pool.shoes,
            "bag": pool.bags,
            "accessory": pool.accessories,
        }.get(g.category)
        if target is not None:
            target.append(g)

    return pool
