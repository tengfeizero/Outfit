"""数据层测试：建表、单行档案、JSON 字段往返、穿着记录。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from outfit import db
from outfit.models import BodyProfile, Garment, Outfit


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    db.init_engine(tmp_path / "test.db")
    yield


def _garment(name="白衬衫", **kwargs) -> Garment:
    data = dict(
        name=name,
        category="top",
        color_primary="白",
        color_hex="#FFFFFF",
        warmth=2,
        formality=3,
        seasons=["spring", "summer"],
        style_tags=["minimal"],
    )
    data.update(kwargs)
    return Garment(**data)


def test_add_and_read_garment_keeps_json_fields():
    saved = db.add_garment(_garment())
    assert saved.id is not None

    fetched = db.get_garment(saved.id)
    assert fetched is not None
    assert fetched.seasons == ["spring", "summer"]
    assert fetched.style_tags == ["minimal"]
    assert fetched.status == "active"


def test_list_filters_by_status():
    db.add_garment(_garment("A"))
    stored = db.add_garment(_garment("B"))
    stored.status = "stored"
    db.update_garment(stored)

    active = db.list_garments()
    assert len(active) == 1
    assert len(db.list_garments(status=None)) == 2


def test_profile_is_single_row():
    db.save_profile(BodyProfile(height_cm=175, weight_kg=68))
    db.save_profile(BodyProfile(height_cm=180, weight_kg=75))

    profile = db.get_profile()
    assert profile is not None
    assert profile.id == 1
    assert profile.height_cm == 180

    with db.session() as s:
        from sqlmodel import select

        rows = s.exec(select(BodyProfile)).all()
    assert len(rows) == 1, "身体档案只能有一行"


def test_mark_worn_updates_count_and_timestamp():
    saved = db.add_garment(_garment())
    when = datetime.now(timezone.utc) - timedelta(days=2)
    db.mark_worn([saved.id], when=when)

    fetched = db.get_garment(saved.id)
    assert fetched.wear_count == 1
    assert fetched.last_worn_at is not None


def test_recent_outfit_sets_returns_ids():
    db.save_outfit(Outfit(occasion="work", garment_ids=[1, 2, 3]))
    db.save_outfit(Outfit(occasion="date", garment_ids=[4, 5]))

    sets = db.recent_outfit_sets(limit=3)
    assert {1, 2, 3} in sets
    assert {4, 5} in sets


def test_event_counter_is_per_day():
    db.log_event("render_ok")
    db.log_event("render_ok")
    assert db.count_events_today("render_ok") == 2
    assert db.count_events_today("render_failed") == 0


def test_delete_garment():
    saved = db.add_garment(_garment())
    assert db.delete_garment(saved.id) is True
    assert db.get_garment(saved.id) is None
    assert db.delete_garment(saved.id) is False
