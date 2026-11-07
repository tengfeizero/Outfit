"""采集链路的测试：解析、映射、去重、dry-run。全离线。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outfit import db
from outfit.config import Settings
from outfit.sources import SOURCES, get_source, mapping
from outfit.sources.base import SourceUnavailable
from outfit.sources.local import LocalSource
from outfit.sources.runner import run
from outfit.sources.uniqlo import UniqloSource, extract_code

FIXTURE = {
    "result": {
        "items": [
            {
                "productId": "461234",
                "name": "男装 摇粒绒拉链夹克",
                "price": {"currency": {"value": 299}},
                "colors": [
                    {"name": "09 BLACK", "productId": "461234001"},
                    {"name": "32 BEIGE", "productId": "461234002"},
                ],
                "images": {"main": {"imageUrl": "https://img.example/a.jpg"}},
            },
            {
                "productId": "462000",
                "name": "男装 羊毛混纺大衣",
                "price": {"currency": {"value": 599}},
                "colors": [{"name": "藏青", "productId": "462000001"}],
                "images": {"main": {"imageUrl": "https://img.example/b.jpg"}},
            },
        ]
    }
}


@pytest.fixture
def settings(tmp_path):
    config = Settings(root=tmp_path, data_dir=tmp_path / "data")
    config.ensure_dirs()
    db.init_engine(config.db_path)
    return config


# ---------------------------------------------------------------- 解析


def test_extract_code_from_category_url():
    assert extract_code("https://www.uniqlo.cn/c/2mouterwr.html") == "2mouterwr"


def test_parse_expands_colors_into_separate_garments():
    source = UniqloSource()
    items = source.parse(FIXTURE)
    assert len(items) == 3, "两个颜色的夹克应该拆成两件"
    assert {item.color_name for item in items} == {"09 BLACK", "32 BEIGE", "藏青"}
    assert items[0].price == 299


def test_parse_respects_limit():
    source = UniqloSource()
    assert len(source.parse(FIXTURE, limit=2)) == 2


def test_parse_survives_unknown_shape():
    source = UniqloSource()
    assert source.parse({"unexpected": True}) == []


def test_from_file_works_without_network(tmp_path):
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    source = UniqloSource(from_file=path)
    items = source.fetch("anything", limit=10)
    assert len(items) == 3


def test_dead_endpoint_raises_with_instructions():
    def handler(request):
        import httpx

        return httpx.Response(404, json={})

    import httpx

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = UniqloSource(client=client)
    with pytest.raises(SourceUnavailable) as error:
        source.fetch("https://www.uniqlo.cn/c/2mouterwr.html")
    message = str(error.value)
    assert "没拿到商品" in message
    assert "--endpoint" in message, "失败信息必须告诉用户下一步怎么做"


# ---------------------------------------------------------------- 映射


@pytest.mark.parametrize(
    "title,expected",
    [
        ("男装 摇粒绒拉链夹克", "outerwear"),
        ("男装 羊毛混纺大衣", "outerwear"),
        ("男装 圆领T恤", "top"),
        ("男装 牛津纺衬衫", "top"),
        ("男装 修身牛仔裤", "bottom"),
    ],
)
def test_guess_category(title, expected):
    assert mapping.guess_category(title) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("09 BLACK", ("黑", "#121212")),
        ("32 BEIGE", ("米", "#D8CDB8")),
        ("藏青", ("藏蓝", "#1F2A44")),
        ("藏青色", ("藏蓝", "#1F2A44")),
        ("米色", ("米", "#D8CDB8")),
        ("", ("未标注", None)),
    ],
)
def test_normalize_color(raw, expected):
    assert mapping.normalize_color(raw) == expected


def test_warmth_and_formality_follow_the_title():
    assert mapping.guess_warmth("男装 羽绒服", "outerwear") == 5
    assert mapping.guess_warmth("男装 圆领T恤", "top") == 1
    assert mapping.guess_formality("男装 修身西裤", "bottom") == 4
    assert mapping.guess_formality("男装 摇粒绒夹克", "outerwear") == 2


# ---------------------------------------------------------------- 本地源


def test_local_source_reads_folder(tmp_path):
    folder = tmp_path / "inbox"
    folder.mkdir()
    from PIL import Image

    Image.new("RGB", (100, 100), (30, 30, 30)).save(folder / "coat.jpg")
    (folder / "metadata.json").write_text(
        json.dumps({"coat.jpg": {"title": "黑色大衣", "color": "黑"}}), encoding="utf-8"
    )

    items = LocalSource().fetch(str(folder))
    assert len(items) == 1
    assert items[0].title == "黑色大衣"
    assert items[0].color_name == "黑"


def test_local_source_rejects_missing_folder(tmp_path):
    from outfit.sources.base import SourceError

    with pytest.raises(SourceError):
        LocalSource().fetch(str(tmp_path / "nope"))


# ---------------------------------------------------------------- 入库


def _inbox_with_image(tmp_path, name="coat.jpg", meta=None):
    folder = tmp_path / "inbox"
    folder.mkdir(exist_ok=True)
    from PIL import Image

    Image.new("RGB", (200, 200), (25, 25, 25)).save(folder / name)
    (folder / "metadata.json").write_text(json.dumps(meta or {}), encoding="utf-8")
    return folder


def test_dry_run_writes_nothing(settings, tmp_path):
    folder = _inbox_with_image(tmp_path, meta={"coat.jpg": {"title": "黑大衣", "color": "黑"}})
    report = run(LocalSource(), str(folder), settings=settings, dry_run=True)
    assert report.created == 1
    assert db.list_garments(status=None) == []
    assert report.run_dir is None


def test_import_writes_garment_with_provenance(settings, tmp_path):
    folder = _inbox_with_image(tmp_path, meta={"coat.jpg": {"title": "黑大衣", "color": "黑"}})
    report = run(
        LocalSource(), str(folder), settings=settings, with_cutout=False
    )
    assert report.created == 1

    garments = db.list_garments(status=None)
    assert len(garments) == 1
    assert garments[0].source == "local"
    assert garments[0].external_id == "coat"
    assert garments[0].image_path and garments[0].image_path.startswith("photos/")
    assert report.run_dir and (report.run_dir / "report.json").exists()


def test_import_is_idempotent(settings, tmp_path):
    folder = _inbox_with_image(tmp_path, meta={"coat.jpg": {"title": "黑大衣", "color": "黑"}})
    run(LocalSource(), str(folder), settings=settings, with_cutout=False)
    second = run(LocalSource(), str(folder), settings=settings, with_cutout=False)

    assert second.created == 0
    assert second.updated == 1
    assert len(db.list_garments(status=None)) == 1, "同一件商品不该重复入库"


def test_get_source_filters_options():
    source = get_source("local", endpoint="ignored")
    assert isinstance(source, LocalSource)
    assert "uniqlo" in SOURCES
