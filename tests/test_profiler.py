"""身体档案的测试。重点：没有三围时也要能给出可用的建议，且不编造身形。"""

from __future__ import annotations

import pytest

from outfit import profiler
from outfit.models import BodyProfile


def _profile(**kwargs) -> BodyProfile:
    data = dict(height_cm=175.0, weight_kg=68.0)
    data.update(kwargs)
    return BodyProfile(**data)


def test_bmi():
    assert profiler.bmi(175, 68) == pytest.approx(22.2, abs=0.1)
    with pytest.raises(ValueError):
        profiler.bmi(0, 68)


@pytest.mark.parametrize(
    "value,label",
    [(17.0, "slim"), (18.5, "regular"), (23.9, "regular"), (24.0, "solid"), (27.9, "solid"), (28.0, "heavy")],
)
def test_build_label_boundaries(value, label):
    assert profiler.build_label(value) == label


@pytest.mark.parametrize(
    "chest,waist,hip,expected",
    [
        (90, 66, 90, "hourglass"),
        (88, 84, 88, "rectangle"),
        (86, 70, 96, "pear"),
        (100, 78, 92, "inverted_triangle"),
        (94, 98, 96, "apple"),
    ],
)
def test_body_shape(chest, waist, hip, expected):
    assert profiler.body_shape(chest, waist, hip) == expected


def test_shape_needs_measurements():
    with pytest.raises(ValueError):
        profiler.body_shape(0, 70, 90)


def test_analyse_without_measurements_does_not_guess_shape():
    report = profiler.analyse(_profile())
    assert report.body_shape is None, "没有三围就不该声称知道身形"
    assert report.hints, "至少要给出通用的版型建议"
    assert any("胸围" in hint for hint in report.hints)


def test_analyse_with_measurements_gives_shape_hint():
    report = profiler.analyse(_profile(chest_cm=86, waist_cm=70, hip_cm=96))
    assert report.body_shape == "pear"
    assert report.hints


def test_describe_is_readable():
    report = profiler.analyse(_profile(chest_cm=90, waist_cm=66, hip_cm=90))
    text = profiler.describe(report)
    assert "BMI" in text and "沙漏形" in text
