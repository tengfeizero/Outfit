"""偏好记忆的测试：收藏过的组合，应该更容易再被推荐。"""

from __future__ import annotations

from datetime import datetime, timezone

from outfit import scoring
from outfit.stylist.plan import build_plans

NOW = datetime(2026, 12, 15, 8, 0, tzinfo=timezone.utc)


def test_empty_preference_is_neutral():
    preference = scoring.Preference.from_saved([])
    assert preference.outfits == 0
    assert preference.confidence == 0.0
    assert preference.bonus([]) == 0.0


def test_preference_counts_items_and_pairs():
    preference = scoring.Preference.from_saved([[1, 2, 3], [1, 2, 4], [1, 2, 3]])
    assert preference.outfits == 3
    assert preference.items[1] == 3
    assert preference.pairs[(1, 2)] == 3
    assert preference.pairs[(1, 3)] == 2
    assert preference.pairs[(2, 4)] == 1


def test_single_saved_outfit_is_discounted():
    """只收藏过一套时，信心只有三分之一——别拿偶然当规律。"""
    one = scoring.Preference.from_saved([[1, 2, 3]])
    three = scoring.Preference.from_saved([[1, 2, 3]] * 3)
    assert one.confidence < three.confidence
    assert one.confidence == 1 / 3


def test_bonus_rewards_matching_pairs(wardrobe):
    by_id = {g.id: g for g in wardrobe}
    liked = [by_id[2], by_id[7], by_id[17]]  # 衬衫＋米裤＋风衣

    preference = scoring.Preference.from_saved([[2, 7, 17]] * 3)
    assert preference.bonus(liked) > 0.8

    other = [by_id[3], by_id[5], by_id[15]]  # 完全另一套
    assert preference.bonus(other) == 0.0


def test_saved_combination_gets_promoted(wardrobe):
    base, _ = build_plans(wardrobe, occasion="work", temp_c=18.0, now=NOW)
    favourite = base[2].ids  # 挑一个本来不是第一名的组合

    preference = scoring.Preference.from_saved([favourite] * 3)
    promoted, _ = build_plans(
        wardrobe, occasion="work", temp_c=18.0, now=NOW, preference=preference
    )
    assert set(promoted[0].ids) == set(favourite), "收藏过的组合应该排到第一"


def test_preference_does_not_break_hard_rules(wardrobe):
    """再怎么偏好，也不能把短袖塞进冬天的方案里。"""
    preference = scoring.Preference.from_saved([[4, 6, 10]] * 5)  # 全是夏装
    plans, pool = build_plans(
        wardrobe, occasion="work", temp_c=5.0, now=NOW, preference=preference
    )
    for plan in plans:
        assert all(g.warmth >= 4 for g in plan.items)


def test_no_preference_keeps_ranking_unchanged(wardrobe):
    plain, _ = build_plans(wardrobe, occasion="work", temp_c=18.0, now=NOW)
    neutral, _ = build_plans(
        wardrobe,
        occasion="work",
        temp_c=18.0,
        now=NOW,
        preference=scoring.Preference.from_saved([]),
    )
    assert [p.ids for p in plain] == [p.ids for p in neutral]
