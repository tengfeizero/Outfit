"""候选池的硬过滤测试。这里最要紧的一条：十二月的池子里不能有短袖。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from outfit import candidates, rules
from outfit.models import Garment

NOW = datetime(2026, 12, 15, 8, 0, tzinfo=timezone.utc)


def _pool_ids(pool: candidates.Pool) -> set[int]:
    return {g.id for g in pool.all_items()}


def test_winter_pool_has_no_summer_tee(wardrobe):
    pool = candidates.build(wardrobe, occasion="work", temp_c=5.0, now=NOW)
    assert 4 not in _pool_ids(pool), "5℃ 的池子里不应该出现短袖"
    lo, hi = rules.allowed_warmth("freezing")
    for g in pool.all_items():
        assert lo <= g.warmth <= hi


def test_every_candidate_respects_warmth_and_formality(wardrobe):
    pool = candidates.build(wardrobe, occasion="work", temp_c=18.0, now=NOW)
    lo_w, hi_w = rules.allowed_warmth("mild")
    lo_f, hi_f = rules.formality_range("work")
    for g in pool.all_items():
        assert lo_w <= g.warmth <= hi_w
        assert lo_f <= g.formality <= hi_f


def test_jacket_required_below_22(wardrobe):
    assert candidates.build(wardrobe, occasion="work", temp_c=18.0, now=NOW).needs_jacket
    assert not candidates.build(wardrobe, occasion="date", temp_c=26.0, now=NOW).needs_jacket


def test_stored_items_are_excluded(wardrobe):
    wardrobe[0].status = "stored"
    pool = candidates.build(wardrobe, occasion="date", temp_c=26.0, now=NOW)
    assert 1 not in _pool_ids(pool)


def test_recently_worn_excluded_when_wardrobe_is_thick(wardrobe):
    wardrobe[1].last_worn_at = NOW - timedelta(days=2)  # 浅蓝衬衫
    pool = candidates.build(wardrobe, occasion="work", temp_c=18.0, now=NOW)
    assert 2 not in _pool_ids(pool)


def test_recent_rule_relaxes_for_thin_wardrobe():
    thin = [
        Garment(
            id=index,
            name=f"测试{index}",
            category=category,
            color_primary="黑",
            warmth=3,
            formality=3,
            status="active",
            last_worn_at=NOW - timedelta(days=2),
        )
        for index, category in enumerate(
            ["top", "bottom", "shoes", "bag", "accessory"], start=1
        )
    ]
    pool = candidates.build(thin, occasion="work", temp_c=18.0, now=NOW)
    assert pool.relaxed is True
    assert pool.count() == 5, "衣橱太薄时应放宽新鲜度规则"


def test_unusable_pool_explains_what_is_missing(wardrobe):
    pool = candidates.build(wardrobe, occasion="work", temp_c=-10.0, now=NOW)
    assert not pool.is_usable()
    assert "缺少" in pool.explain()
