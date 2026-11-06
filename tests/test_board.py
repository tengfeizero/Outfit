"""搭配板的测试：能出一张图、尺寸对、缺图不炸。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from outfit.models import Garment
from outfit.renderer import render
from outfit.renderer.board import build_board


def _g(**kwargs) -> Garment:
    data = dict(
        name="黑羊毛针织",
        category="top",
        color_primary="黑",
        color_hex="#1A1A1A",
        warmth=3,
        formality=3,
    )
    data.update(kwargs)
    return Garment(**data)


def test_board_is_written(tmp_path):
    items = [_g(), _g(id=2, name="米色阔腿裤", category="bottom", color_primary="米", color_hex="#D8CDB8")]
    target = build_board(items, tmp_path / "board.png", title="上班", subtitle="18℃", rationale="配色稳。")
    assert target.exists()
    with Image.open(target) as image:
        assert image.width == 900
        assert image.height > 400


def test_board_survives_missing_images(tmp_path):
    items = [_g(image_path=None, cutout_path=None)]
    target = build_board(items, tmp_path / "board.png")
    assert target.exists()


def test_board_with_many_items_grows(tmp_path):
    items = [_g(id=index, name=f"单品{index}") for index in range(6)]
    target = build_board(items, tmp_path / "big.png")
    with Image.open(target) as image:
        assert image.height > 900  # 6 件 → 3 行


def test_render_without_provider_falls_back_to_board(tmp_path):
    result = render([_g()], tmp_path, title="上班")
    assert result.mode == "board"
    assert result.path is not None and result.path.exists()
    assert "搭配板" in result.note


def test_render_uses_provider_when_it_works(tmp_path):
    png = b"\x89PNG\r\n\x1a\n" + b"fake-body"

    result = render([_g()], tmp_path, provider=lambda items: png)
    assert result.mode == "photo"
    assert result.path is not None and result.path.suffix == ".png"
    assert result.path.read_bytes() == png


def test_render_falls_back_when_provider_raises(tmp_path):
    def broken(_items):
        raise RuntimeError("服务没响应")

    result = render([_g()], tmp_path, provider=broken)
    assert result.mode == "board"
    assert "服务没响应" in result.note
    assert result.path.exists()


def test_render_falls_back_when_provider_returns_nothing(tmp_path):
    result = render([_g()], tmp_path, provider=lambda items: None)
    assert result.mode == "board"
    assert "没有返回" in result.note


def test_board_resolves_relative_image_paths(tmp_path, monkeypatch):
    """数据库里存的是 photos/xxx.jpg 这种相对路径，平铺时要能找到文件。"""
    monkeypatch.chdir(tmp_path)
    photo = Path("data/photos/a.png")
    photo.parent.mkdir(parents=True)
    Image.new("RGB", (50, 50), (200, 50, 50)).save(photo)

    target = build_board([_g(image_path="photos/a.png")], tmp_path / "board.png")
    assert target.exists()
