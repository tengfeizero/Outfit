"""买前判断的测试。全部规则，不联网。"""

from __future__ import annotations

import pytest

from outfit import shopping
from outfit.models import Garment


def _g(**kwargs) -> Garment:
    data = dict(
        name="测试",
        category="top",
        color_primary="黑",
        color_hex="#1A1A1A",
        warmth=3,
        formality=3,
        status="active",
    )
    data.update(kwargs)
    return Garment(**data)


def test_color_similarity_bounds():
    assert shopping.color_similarity("#000000", "#000000") == pytest.approx(1.0)
    assert shopping.color_similarity("#000000", "#FFFFFF") == pytest.approx(0.0, abs=0.01)
    assert shopping.color_similarity(None, "#FFFFFF") == 0.5


def test_empty_wardrobe_says_depends():
    verdict = shopping.evaluate(_g(), [])
    assert verdict.verdict == "depends"
    assert verdict.reasons


def test_two_similar_items_means_skip():
    wardrobe = [
        _g(id=1, name="黑针织", color_primary="黑", color_hex="#1A1A1A", formality=3),
        _g(id=2, name="黑T恤", color_primary="黑", color_hex="#1B1B1B", formality=3),
        _g(id=3, name="灰西裤", category="bottom", color_primary="深灰", color_hex="#3A3A3A", formality=3),
    ]
    candidate = _g(name="新黑上衣", color_primary="黑", color_hex="#191919", formality=3)
    verdict = shopping.evaluate(candidate, wardrobe)
    assert verdict.verdict == "skip"
    assert len(verdict.duplicate_of) == 2
    assert any("很像" in reason for reason in verdict.reasons)


def test_duplicates_beat_versatility():
    """再百搭，家里已经有两件一样的，也不该买。"""
    wardrobe = [
        _g(id=1, name="黑针织", color_primary="黑", color_hex="#1A1A1A"),
        _g(id=2, name="黑T恤", color_primary="黑", color_hex="#1B1B1B"),
        _g(id=3, name="米裤", category="bottom", color_primary="米", color_hex="#D8CDB8"),
        _g(id=4, name="灰裤", category="bottom", color_primary="深灰", color_hex="#3A3A3A"),
        _g(id=5, name="白鞋", category="shoes", color_primary="白", color_hex="#F2F2F0"),
        _g(id=6, name="黑鞋", category="shoes", color_primary="黑", color_hex="#1A1A1A"),
        _g(id=7, name="驼外套", category="outerwear", color_primary="驼", color_hex="#B08A5E"),
    ]
    verdict = shopping.evaluate(_g(name="新黑上衣", color_hex="#191919"), wardrobe)
    assert len(verdict.pairs_with) == 3, "前提：它确实很百搭"
    assert verdict.verdict == "skip"
    assert "不必买" in verdict.title


def test_no_duplicates_and_many_partners_means_buy():
    wardrobe = [
        _g(id=1, name="米色阔腿裤", category="bottom", color_primary="米", color_hex="#D8CDB8", formality=3),
        _g(id=2, name="藏蓝西裤", category="bottom", color_primary="藏蓝", color_hex="#1F2A44", formality=3),
        _g(id=3, name="黑西裤", category="bottom", color_primary="黑", color_hex="#1A1A1A", formality=3),
        _g(id=4, name="驼色大衣", category="outerwear", color_primary="驼", color_hex="#B08A5E", formality=3),
        _g(id=5, name="黑乐福鞋", category="shoes", color_primary="黑", color_hex="#1A1A1A", formality=3),
    ]
    candidate = _g(name="白衬衫", color_primary="白", color_hex="#F2F2F0", formality=3)
    verdict = shopping.evaluate(candidate, wardrobe)
    assert verdict.verdict == "buy"
    assert len(verdict.pairs_with) == 3
    assert any("件搭" in reason for reason in verdict.reasons)


def test_candidate_that_matches_nothing_is_skip():
    wardrobe = [
        _g(id=1, name="黑礼服", category="dress", color_primary="黑", color_hex="#1A1A1A", formality=5),
        _g(id=2, name="黑皮鞋", category="shoes", color_primary="黑", color_hex="#1A1A1A", formality=5),
    ]
    candidate = _g(
        name="荧光绿运动裤",
        category="bottom",
        color_primary="绿",
        color_hex="#39FF14",
        formality=1,
        warmth=1,
    )
    verdict = shopping.evaluate(candidate, wardrobe)
    assert verdict.verdict in {"skip", "depends"}
    assert verdict.pairs_with == []


def test_missing_category_is_reported_as_gap():
    wardrobe = [
        _g(id=1, name="黑西裤", category="bottom", color_primary="黑", color_hex="#1A1A1A"),
        _g(id=2, name="白T恤", category="top", color_primary="白", color_hex="#F2F2F0"),
    ]
    candidate = _g(id=None, name="新外套", category="outerwear", color_primary="驼", color_hex="#B08A5E")
    verdict = shopping.evaluate(candidate, wardrobe)
    assert any("还没有外套" in reason for reason in verdict.reasons)


def test_stored_items_are_ignored():
    wardrobe = [
        _g(id=1, name="收起来的黑衫", color_primary="黑", color_hex="#1A1A1A", status="stored"),
        _g(id=2, name="收起来的黑衫2", color_primary="黑", color_hex="#1A1A1A", status="stored"),
    ]
    verdict = shopping.evaluate(_g(), wardrobe)
    assert verdict.duplicate_of == []


def test_same_slot_never_pairs():
    wardrobe = [_g(id=1, name="另一件上装", category="top", color_primary="米", color_hex="#D8CDB8")]
    verdict = shopping.evaluate(_g(name="新上装"), wardrobe)
    assert verdict.pairs_with == []
