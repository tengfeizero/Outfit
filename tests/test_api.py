"""接口测试：全程假数据、零网络调用。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from outfit.config import Settings
from outfit.web.api import create_app


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(root=tmp_path, data_dir=tmp_path / "data")
    settings.ensure_dirs()
    return TestClient(create_app(settings))


def _add(client: TestClient, **overrides) -> dict:
    payload = {
        "name": "白衬衫",
        "category": "top",
        "color_primary": "白",
        "color_hex": "#FFFFFF",
        "warmth": 2,
        "formality": 3,
    }
    payload.update(overrides)
    response = client.post("/api/garments", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_status_on_empty_install(client):
    body = client.get("/api/status").json()
    assert body["garments"] == 0
    assert body["has_profile"] is False
    assert body["offline"] is True


def test_profile_roundtrip(client):
    response = client.put("/api/profile", json={"height_cm": 175, "weight_kg": 68, "skin_tone": "warm"})
    assert response.status_code == 200

    body = client.get("/api/profile").json()
    assert body["profile"]["height_cm"] == 175
    assert body["report"]["bmi"] == pytest.approx(22.2, abs=0.1)
    assert body["report"]["body_shape"] is None
    assert body["report"]["hints"]


def test_profile_rejects_nonsense(client):
    assert client.put("/api/profile", json={"height_cm": 0, "weight_kg": 68}).status_code == 400


def test_garment_lifecycle(client):
    created = _add(client)
    assert created["id"] is not None

    listed = client.get("/api/garments").json()["garments"]
    assert len(listed) == 1

    patched = client.patch(f"/api/garments/{created['id']}", json={"status": "stored"}).json()
    assert patched["status"] == "stored"

    assert client.delete(f"/api/garments/{created['id']}").status_code == 200
    assert client.get("/api/garments").json()["garments"] == []


def test_garment_validation(client):
    bad = client.post("/api/garments", json={"name": "x", "category": "spaceship", "color_primary": "白", "warmth": 2, "formality": 3})
    assert bad.status_code == 400
    bad = client.post("/api/garments", json={"name": "x", "category": "top", "color_primary": "白", "warmth": 9, "formality": 3})
    assert bad.status_code == 400


def test_plan_with_empty_wardrobe_explains(client):
    body = client.post("/api/plan", json={"occasion": "work", "temp_c": 18}).json()
    assert body["plans"] == []
    assert body["usable"] is False
    assert body["reason"]


def test_plan_returns_three_plans(client, wardrobe):
    for garment in wardrobe:
        _add(
            client,
            name=garment.name,
            category=garment.category,
            color_primary=garment.color_primary,
            color_hex=garment.color_hex,
            warmth=garment.warmth,
            formality=garment.formality,
        )

    body = client.post("/api/plan", json={"occasion": "work", "temp_c": 18}).json()
    assert body["usable"] is True
    assert len(body["plans"]) == 3
    for plan in body["plans"]:
        assert plan["items"]
        assert plan["label"] in {"首选", "更正式", "更舒服", "备选"}
        assert plan["rationale"]

    first = body["plans"][0]
    saved = client.post(
        "/api/outfits",
        json={"occasion": "work", "temp_c": 18, "garment_ids": first["garment_ids"]},
    ).json()
    assert saved["ok"] is True
    assert client.post(f"/api/outfits/{saved['id']}/worn").json()["ok"] is True


def test_occasions_have_formality_ranges(client):
    body = client.get("/api/occasions").json()
    keys = {item["key"] for item in body["occasions"]}
    assert {"interview", "work", "date", "sport", "home"} <= keys
    for item in body["occasions"]:
        assert item["formality"][0] <= item["formality"][1]


def test_upload_rejects_weird_extension(client):
    response = client.post("/api/upload", files={"file": ("evil.exe", b"x", "application/octet-stream")})
    assert response.status_code == 400


def _jpeg_bytes(color=(31, 42, 68), background=(255, 255, 255)) -> bytes:
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (240, 240), background)
    image.paste(Image.new("RGB", (120, 240), color), (0, 0))
    buffer = BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


def test_upload_saves_photo_and_guesses_color(client, tmp_path, monkeypatch):
    # 抠图要加载 170MB 模型，测试里一律关掉；抠图本身另有专门的测试
    monkeypatch.setattr("outfit.wardrobe.cutout_available", lambda: False)

    response = client.post(
        "/api/upload", files={"file": ("shirt.jpg", _jpeg_bytes(), "image/jpeg")}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["path"].startswith("photos/")
    assert (tmp_path / "data" / body["path"]).exists()
    assert body["color_hex"].startswith("#")
    assert body["color_name"]
    assert body["cutout_path"] is None
    assert "rembg" in body["notice"]


def test_upload_rejects_broken_image(client):
    response = client.post(
        "/api/upload", files={"file": ("x.jpg", b"not-an-image", "image/jpeg")}
    )
    assert response.status_code == 400


def test_weather_is_unconfigured_by_default(client):
    assert client.get("/api/weather").json() == {"configured": False}


def test_set_city_stores_coordinates(client, monkeypatch):
    from outfit.web import api as api_module

    monkeypatch.setattr(
        api_module.weather_client,
        "geocode",
        lambda name: api_module.weather_client.City(
            name="杭州", latitude=30.29, longitude=120.16, admin="浙江"
        ),
    )
    body = client.post("/api/weather/city", json={"city": "杭州"}).json()
    assert body["ok"] is True
    assert "杭州" in body["city"]

    from outfit import db

    assert db.get_setting("city_lat") == "30.29"
    assert db.get_setting("city_name") == "杭州"


def test_set_city_reports_unknown_place(client, monkeypatch):
    from outfit.web import api as api_module

    monkeypatch.setattr(api_module.weather_client, "geocode", lambda name: None)
    response = client.post("/api/weather/city", json={"city": "火星"})
    assert response.status_code == 404


def test_render_produces_a_board(client):
    top = _add(client, name="白衬衫", category="top")
    bottom = _add(client, name="黑西裤", category="bottom", color_primary="黑", color_hex="#1A1A1A")

    body = client.post(
        "/api/render",
        json={"garment_ids": [top["id"], bottom["id"]], "title": "上班", "rationale": "配色稳。"},
    ).json()
    assert body["mode"] == "board"
    assert body["url"].startswith("/media/renders/")
    assert "搭配板" in body["note"]

    image = client.get(body["url"])
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")


def test_render_rejects_unknown_garments(client):
    assert client.post("/api/render", json={"garment_ids": [999]}).status_code == 400


def test_shopping_judges_a_new_piece(client):
    _add(client, name="黑西裤", category="bottom", color_primary="黑", color_hex="#1A1A1A")
    _add(client, name="黑乐福鞋", category="shoes", color_primary="黑", color_hex="#1A1A1A")

    body = client.post(
        "/api/shopping",
        json={"category": "top", "color_hex": "#F2F2F0", "color_primary": "白", "formality": 3},
    ).json()
    assert body["verdict"] in {"buy", "skip", "depends"}
    assert body["title"]
    assert body["reasons"]
    assert body["pairs"]


def test_shopping_rejects_unknown_category(client):
    assert client.post("/api/shopping", json={"category": "spaceship"}).status_code == 400


def test_javascript_is_served_as_javascript(tmp_path):
    """Windows 注册表把 .js 登记成 text/plain，浏览器会拒绝执行模块脚本。

    这个回归测试守的就是"打开一片黑"那个 bug。
    """
    dist = tmp_path / "outfit" / "web" / "static"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id='root'></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "assets" / "app.css").write_text("body{}", encoding="utf-8")

    settings = Settings(root=tmp_path, data_dir=tmp_path / "data")
    settings.ensure_dirs()
    client = TestClient(create_app(settings))

    js = client.get("/assets/app.js")
    assert js.status_code == 200
    assert js.headers["content-type"].startswith("text/javascript")

    css = client.get("/assets/app.css")
    assert css.headers["content-type"].startswith("text/css")

    index = client.get("/")
    assert index.status_code == 200
    assert "root" in index.text
    # 页面必须每次回源，否则改版后旧页面指向已删除的文件，又变黑屏
    assert index.headers["cache-control"] == "no-cache"
    # 带哈希的资源可以永久缓存
    assert js.headers["cache-control"].startswith("public")
