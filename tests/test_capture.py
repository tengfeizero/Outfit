"""图像处理的测试：主色、色名、转正缩放、抠图降级。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

from outfit import capture, wardrobe


def _make_image(path: Path, color, size=(200, 200), background=None) -> Path:
    image = Image.new("RGB", size, background or color)
    if background is not None:
        half = size[0] // 2
        image.paste(Image.new("RGB", (half, size[1]), color), (0, 0))
    image.save(path)
    return path


def test_dominant_color_ignores_white_background(tmp_path):
    path = _make_image(tmp_path / "shirt.jpg", (192, 57, 43), background=(255, 255, 255))
    hex_color = capture.dominant_color(path)
    red, green, blue = capture._rgb(hex_color)
    assert red > 150 and green < 100 and blue < 100


def test_dominant_color_on_all_white_returns_white(tmp_path):
    path = _make_image(tmp_path / "white.jpg", (255, 255, 255))
    assert capture.nearest_color_name(capture.dominant_color(path)) == "白"


@pytest.mark.parametrize(
    "hex_color,expected",
    [
        ("#121212", "黑"),
        ("#F5F5F2", "白"),
        ("#1F2A44", "藏蓝"),
        ("#C0392B", "红"),
        ("#B08A5E", "驼"),
    ],
)
def test_nearest_color_name(hex_color, expected):
    assert capture.nearest_color_name(hex_color) == expected


def test_normalize_shrinks_long_edge(tmp_path):
    path = tmp_path / "big.jpg"
    Image.new("RGB", (3200, 1200), (10, 10, 10)).save(path)
    capture.normalize(path)
    with Image.open(path) as image:
        assert max(image.size) == capture.MAX_EDGE


def test_normalize_handles_rgba(tmp_path):
    path = tmp_path / "alpha.png"
    Image.new("RGBA", (300, 300), (0, 0, 0, 0)).save(path)
    capture.normalize(path)
    with Image.open(path) as image:
        assert image.mode == "RGB"


def test_guess_name_reads_naturally():
    assert wardrobe.guess_name("top", "黑") == "黑上装"
    assert wardrobe.guess_name("shoes", "白") == "白鞋"
    assert wardrobe.guess_name("unknown", "灰") == "灰单品"


def test_ingest_without_rembg_still_returns_color(tmp_path, monkeypatch):
    monkeypatch.setattr(wardrobe, "cutout_available", lambda: False)
    path = _make_image(tmp_path / "item.jpg", (31, 42, 68), background=(255, 255, 255))
    result = wardrobe.ingest(path, tmp_path / "cutouts")
    assert result.color_hex.startswith("#")
    assert result.color_name
    assert result.cutout_path is None
    assert "rembg" in result.cutout_skipped_reason


def test_cutout_failure_carries_the_real_reason(tmp_path, monkeypatch):
    """失败原因不能被一句"未安装"盖掉——用户得知道是网络还是磁盘。"""

    class BrokenRembg:
        @staticmethod
        def remove(_data):
            raise RuntimeError("模型下载被墙")

    monkeypatch.setattr(wardrobe, "cutout_available", lambda: True)
    monkeypatch.setitem(sys.modules, "rembg", BrokenRembg())

    path = _make_image(tmp_path / "item.jpg", (31, 42, 68))
    result = wardrobe.ingest(path, tmp_path / "cutouts", tmp_path / "models")
    assert result.cutout_path is None
    assert "模型下载被墙" in result.cutout_skipped_reason
