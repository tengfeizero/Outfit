"""身体档案：身高体重三围 → 体型档与版型建议。

刻意不做的事：不把身高体重换算成 S/M/L。没有品牌尺码表的情况下那是伪精确，
比不给建议更糟。这里只给"你属于哪一档、该往哪个方向选版型"。
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import BodyProfile

SHAPE_LABELS = {
    "hourglass": "沙漏形",
    "pear": "梨形",
    "apple": "苹果形",
    "rectangle": "矩形",
    "inverted_triangle": "倒三角",
}

BUILD_LABELS = {
    "slim": "偏瘦",
    "regular": "标准",
    "solid": "偏壮",
    "heavy": "壮实",
}

_SHAPE_HINTS = {
    "hourglass": ["腰线是你的优势，收腰版型值得多买", "避免从上到下都宽松，会吃掉比例"],
    "pear": ["上浅下深，把视觉重心提到肩线", "直筒或微喇的裤型比紧身更稳"],
    "apple": ["V 领和开襟外套能拉长上半身", "避免紧身针织贴腰腹"],
    "rectangle": ["用层次制造腰线：短外套＋长内搭", "上下不同材质比同色更显轮廓"],
    "inverted_triangle": ["下装可以亮一点、宽一点", "避开垫肩和落肩过宽的版型"],
}

_BUILD_HINTS = {
    "slim": ["合身比 oversize 更容易撑住", "外套选有结构的肩线"],
    "regular": ["大部分版型都能穿，重点在比例"],
    "solid": ["深色与竖线条更友好", "避免全身同色且贴身的组合"],
    "heavy": ["分件穿比叠穿更利落", "选择垂感面料，避开硬挺膨胀感"],
}


@dataclass
class ShapeReport:
    bmi: float
    build: str
    body_shape: str | None
    hints: list[str]


def bmi(height_cm: float, weight_kg: float) -> float:
    if height_cm <= 0:
        raise ValueError("身高必须大于 0")
    meters = height_cm / 100.0
    return weight_kg / (meters * meters)


def build_label(value: float) -> str:
    if value < 18.5:
        return "slim"
    if value < 24:
        return "regular"
    if value < 28:
        return "solid"
    return "heavy"


def body_shape(chest_cm: float, waist_cm: float, hip_cm: float) -> str:
    """有胸腰臀三个数时才有意义。"""
    if chest_cm <= 0 or waist_cm <= 0 or hip_cm <= 0:
        raise ValueError("三围必须大于 0")

    # 苹果形只认一条硬指标：腰围不小于臀围（肚子比胯宽）。
    # 再细的区分靠三个数做不到，宁可少说。
    if waist_cm >= hip_cm:
        return "apple"
    if abs(chest_cm - hip_cm) <= 5:
        return "hourglass" if waist_cm <= min(chest_cm, hip_cm) - 18 else "rectangle"
    if hip_cm > chest_cm:
        return "pear"
    return "inverted_triangle"


def analyse(profile: BodyProfile) -> ShapeReport:
    value = bmi(profile.height_cm, profile.weight_kg)
    build = build_label(value)

    shape: str | None = None
    if profile.chest_cm and profile.waist_cm and profile.hip_cm:
        shape = body_shape(profile.chest_cm, profile.waist_cm, profile.hip_cm)

    hints: list[str] = []
    if shape:
        hints.extend(_SHAPE_HINTS[shape])
    hints.extend(_BUILD_HINTS[build])
    if not shape:
        hints.append("补上胸围、腰围、臀围，版型建议能具体很多")

    return ShapeReport(bmi=round(value, 1), build=build, body_shape=shape, hints=hints)


def describe(report: ShapeReport) -> str:
    shape = SHAPE_LABELS.get(report.body_shape or "", "未测身形")
    return f"BMI {report.bmi}，{BUILD_LABELS[report.build]}，{shape}"
