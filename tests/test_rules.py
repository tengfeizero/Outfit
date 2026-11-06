"""规则层的边界测试。分档的上下界是这类系统最常出错的地方。"""

from __future__ import annotations

import pytest

from outfit import rules


@pytest.mark.parametrize(
    "temp,expected",
    [
        (35.0, "hot"),
        (28.0, "hot"),
        (27.9, "warm"),
        (22.0, "warm"),
        (21.9, "mild"),
        (15.0, "mild"),
        (14.9, "cold"),
        (8.0, "cold"),
        (7.9, "freezing"),
        (-5.0, "freezing"),
    ],
)
def test_temp_band_boundaries(temp, expected):
    assert rules.temp_band(temp) == expected


def test_warmth_ranges_never_empty_and_ordered():
    for band in rules.TEMP_BANDS:
        lo, hi = rules.allowed_warmth(band)
        assert 1 <= lo <= hi <= 5


def test_colder_bands_never_allow_thinner_garments():
    lo_prev = None
    for band in ("hot", "warm", "mild", "cold", "freezing"):
        lo, hi = rules.allowed_warmth(band)
        if lo_prev is not None:
            assert lo >= lo_prev
        lo_prev = lo


def test_jacket_required_below_22():
    assert not rules.jacket_required("hot")
    assert not rules.jacket_required("warm")
    assert rules.jacket_required("mild")
    assert rules.jacket_required("cold")
    assert rules.jacket_required("freezing")


def test_formality_ranges():
    assert rules.formality_range("interview") == (4, 5)
    assert rules.formality_range("home") == (1, 1)
    assert rules.formality_range("完全没见过的场合") == rules.DEFAULT_FORMALITY


def test_hex_parsing():
    h, s, l = rules.hex_to_hsl("#FF0000")
    assert h == pytest.approx(0.0, abs=0.5)
    assert s == pytest.approx(1.0, abs=0.01)
    assert rules.hex_to_hsl("fff") == pytest.approx(rules.hex_to_hsl("#FFFFFF"))
    with pytest.raises(ValueError):
        rules.hex_to_hsl("不是颜色")


def test_neutral_detection():
    assert rules.is_neutral("#000000")
    assert rules.is_neutral("#FFFFFF")
    assert rules.is_neutral("#8A8A8A")
    assert rules.is_neutral(name="米白")
    assert not rules.is_neutral("#C81E1E")


def test_neutral_pairs_score_high():
    assert rules.color_harmony("#000000", "#FFFFFF") >= 0.8
    assert rules.color_harmony("#000000", "#2E5E8C") >= 0.85


def test_same_hue_beats_clashing_hues():
    same = rules.color_harmony("#1F2A44", "#2C3E63")
    clash = rules.color_harmony("#C81E1E", "#1EA84A")
    assert same > clash


def test_two_loud_colors_penalised():
    loud_same_lightness = rules.color_harmony("#C81E1E", "#1EA84A")
    assert loud_same_lightness < 0.8


def test_skin_tone_fit_prefers_warm_for_warm_skin():
    assert rules.skin_tone_fit("warm", "#B08A5E") > rules.skin_tone_fit("warm", "#2E5E8C")
    assert rules.skin_tone_fit("cool", "#2E5E8C") > rules.skin_tone_fit("cool", "#B08A5E")
    assert rules.skin_tone_fit(None, "#B08A5E") == pytest.approx(0.5)


def test_comfort_orders_by_thickness():
    assert rules.comfort_score(1, "regular") > rules.comfort_score(5, "regular")
    assert rules.comfort_score(3, "oversized") > rules.comfort_score(3, "slim")
