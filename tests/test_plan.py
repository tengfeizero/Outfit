"""组套测试：输出必须永远满足设计文档 8.5 的约束。"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

import pytest

from outfit import rules
from outfit.stylist.plan import build_plans

NOW = datetime(2026, 12, 15, 8, 0, tzinfo=timezone.utc)


def _check(plan, occasion, temp_c, formality=None):
    counts = Counter(g.category for g in plan.items)
    band = rules.temp_band(temp_c)
    lo_w, hi_w = rules.allowed_warmth(band)
    lo_f, hi_f = formality or rules.formality_range(occasion)

    # 需要的品类都在
    if counts["dress"]:
        assert counts["top"] == 0 and counts["bottom"] == 0
    else:
        assert counts["top"] == 1, f"应恰好 1 件上装，实际 {counts['top']}"
        assert counts["bottom"] == 1, f"应恰好 1 件下装，实际 {counts['bottom']}"

    assert counts["shoes"] == 1, "应恰好 1 双鞋"
    assert counts["bag"] <= 1
    assert counts["accessory"] <= 2

    if rules.jacket_required(band):
        assert counts["outerwear"] == 1, "22℃ 以下必须有外套"
    else:
        assert counts["outerwear"] <= 1

    for g in plan.items:
        assert lo_w <= g.warmth <= hi_w, f"{g.name} 厚薄越界"
        assert lo_f <= g.formality <= hi_f, f"{g.name} 正式度越界"


def test_work_mild_returns_three_valid_plans(wardrobe):
    plans, pool = build_plans(wardrobe, occasion="work", temp_c=18.0, now=NOW)
    assert pool.is_usable()
    assert len(plans) == 3
    for plan in plans:
        _check(plan, "work", 18.0)
        assert plan.rationale.endswith("。")
        assert plan.score > 0


def test_plans_are_diverse(wardrobe):
    plans, _ = build_plans(wardrobe, occasion="work", temp_c=18.0, now=NOW)
    core = {"top", "bottom", "outerwear", "dress"}
    for i in range(len(plans)):
        for j in range(i + 1, len(plans)):
            first = {g.id for g in plans[i].items if g.category in core}
            second = {g.id for g in plans[j].items if g.category in core}
            assert first != second, "两套方案的核心单品不能完全相同"
            assert set(plans[i].ids) != set(plans[j].ids), "不能出现两套一模一样的方案"


def test_warm_occasion_has_no_forced_jacket(wardrobe):
    plans, _ = build_plans(wardrobe, occasion="date", temp_c=26.0, now=NOW)
    assert len(plans) == 3
    for plan in plans:
        _check(plan, "date", 26.0)
        assert all(g.warmth <= 3 for g in plan.items)


def test_cold_day_always_has_outerwear(wardrobe):
    plans, _ = build_plans(wardrobe, occasion="work", temp_c=10.0, now=NOW)
    assert len(plans) == 3
    for plan in plans:
        _check(plan, "work", 10.0)
        assert any(g.category == "outerwear" for g in plan.items)


def test_plan_is_deterministic(wardrobe):
    first, _ = build_plans(wardrobe, occasion="work", temp_c=18.0, now=NOW)
    second, _ = build_plans(wardrobe, occasion="work", temp_c=18.0, now=NOW)
    assert [p.ids for p in first] == [p.ids for p in second]


def test_interview_relaxes_formality_when_wardrobe_is_thin(wardrobe):
    """衣橱里没有 4–5 分的上装，不应该直接放弃，应该退一步并说明。"""
    plans, pool = build_plans(wardrobe, occasion="interview", temp_c=18.0, now=NOW)
    assert plans, "放宽后应该能凑出方案"
    assert pool.original_formality == (4, 5)
    assert pool.formality[0] < 4, "放宽之后的区间应该更低"


def test_no_relaxation_when_wardrobe_fits(wardrobe):
    plans, pool = build_plans(wardrobe, occasion="work", temp_c=18.0, now=NOW)
    assert plans
    assert pool.original_formality is None, "本来够穿就不该放宽"


def test_relaxation_never_touches_weather_rules(wardrobe):
    plans, pool = build_plans(wardrobe, occasion="interview", temp_c=5.0, now=NOW)
    for plan in plans:
        assert all(g.warmth >= 4 for g in plan.items), "放宽正式度不能放宽厚薄"


def test_empty_wardrobe_returns_no_plans():
    plans, pool = build_plans([], occasion="work", temp_c=18.0, now=NOW)
    assert plans == []
    assert not pool.is_usable()


def test_missing_shoes_returns_no_plans(wardrobe):
    no_shoes = [g for g in wardrobe if g.category != "shoes"]
    plans, pool = build_plans(no_shoes, occasion="work", temp_c=18.0, now=NOW)
    assert plans == []
    assert "鞋" in pool.explain()


def test_recent_overlap_is_penalised(wardrobe):
    base, _ = build_plans(wardrobe, occasion="work", temp_c=18.0, now=NOW)
    recent = [set(base[0].ids)]
    with_recent, _ = build_plans(
        wardrobe, occasion="work", temp_c=18.0, now=NOW, recent_outfit_ids=recent
    )
    assert with_recent[0].ids != base[0].ids, "刚穿过的那套不应再次排第一"


@pytest.mark.parametrize("occasion", ["interview", "work", "date", "home"])
def test_all_occasions_produce_valid_plans(wardrobe, occasion):
    for temp in (8.0, 16.0, 22.0, 30.0):
        plans, pool = build_plans(wardrobe, occasion=occasion, temp_c=temp, now=NOW)
        if not pool.is_usable():
            continue
        for plan in plans:
            _check(plan, occasion, temp, formality=pool.formality)
