"""HTTP 接口。

刻意保持薄：这里只做参数校验、调下层、把结果转成前端要的形状。
所有判断都在 rules / candidates / scoring / stylist 里，能单独测。
"""

from __future__ import annotations

import json
import mimetypes
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import capture, db, intent, profiler, rules, scoring, shopping, wardrobe
from ..clients import weather as weather_client
from ..clients.tokenhub import TokenHub, TokenHubError
from ..config import Settings, load
from ..models import BodyProfile, Garment, Outfit
from ..renderer import render as render_plan
from ..stylist.plan import OCCASION_LABELS, build_plans

WEATHER_TTL = timedelta(hours=3)

_STATIC_TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".webp": "image/webp",
}


def fix_mimetypes() -> None:
    """修 Windows 的 MIME 映射。

    很多 Windows 机器的注册表把 .js 登记成 text/plain，Python 的 mimetypes 会照抄，
    于是服务把前端脚本当纯文本发出去。浏览器对模块脚本做严格 MIME 检查，直接拒绝执行，
    页面就停在"黑底、什么都没有"——CSS 是好的，JS 一行没跑。这个坑必须显式堵上。
    """
    for extension, media_type in _STATIC_TYPES.items():
        mimetypes.add_type(media_type, extension)


fix_mimetypes()


class StaticBundle(StaticFiles):
    """带缓存策略的静态文件服务。

    - index.html 每次都要回来问一句（no-cache）。否则改了版、旧页面还指着已经删掉的
      旧文件名，浏览器就会给你一片黑。
    - 带哈希的 assets 可以永久缓存，文件名一变自然就换新的。
    """

    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        # Windows 上这里拿到的是反斜杠路径，先归一化再判断
        normalized = path.replace("\\", "/")
        if normalized.endswith(".html") or normalized in ("", "."):
            response.headers["Cache-Control"] = "no-cache"
        elif "assets/" in normalized:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


OCCASION_LABELS_FOR_UI = [
    {"key": "interview", "label": "面试"},
    {"key": "work", "label": "上班"},
    {"key": "date", "label": "约会"},
    {"key": "sport", "label": "运动"},
    {"key": "home", "label": "居家"},
]


def _media_url(path: str | None) -> str | None:
    if not path:
        return None
    return "/media/" + path.replace("\\", "/").lstrip("/")


def _garment_dict(garment: Garment) -> dict:
    return {
        "id": garment.id,
        "name": garment.name,
        "category": garment.category,
        "subcategory": garment.subcategory,
        "color_primary": garment.color_primary,
        "color_hex": garment.color_hex,
        "pattern": garment.pattern,
        "material": garment.material,
        "warmth": garment.warmth,
        "formality": garment.formality,
        "fit": garment.fit,
        "seasons": garment.seasons,
        "style_tags": garment.style_tags,
        "status": garment.status,
        "wear_count": garment.wear_count,
        "label_confidence": garment.label_confidence,
        "image_url": _media_url(garment.image_path),
        "cutout_url": _media_url(garment.cutout_path),
    }


class GarmentPayload(BaseModel):
    name: str
    category: str
    subcategory: str | None = None
    color_primary: str = "未标注"
    color_hex: str | None = None
    pattern: str | None = "solid"
    material: str | None = None
    warmth: int = 3
    formality: int = 3
    fit: str | None = "regular"
    image_path: str | None = None
    label_confidence: float = 1.0


class PlanRequest(BaseModel):
    occasion: str = "work"
    temp_c: float = 18.0
    text: str = ""
    exclude_ids: list[int] = []


class OutfitPayload(BaseModel):
    occasion: str
    temp_c: float | None = None
    garment_ids: list[int]
    rationale: str | None = None


class CityPayload(BaseModel):
    city: str


class RenderPayload(BaseModel):
    garment_ids: list[int]
    title: str = ""
    subtitle: str = ""
    rationale: str = ""


class ShoppingPayload(BaseModel):
    name: str = "新衣服"
    category: str
    color_primary: str = "未标注"
    color_hex: str | None = None
    warmth: int = 3
    formality: int = 3
    image_path: str | None = None


class ProfilePayload(BaseModel):
    height_cm: float
    weight_kg: float
    chest_cm: float | None = None
    waist_cm: float | None = None
    hip_cm: float | None = None
    shoulder_cm: float | None = None
    inseam_cm: float | None = None
    skin_tone: str | None = None
    photo_full: str | None = None
    photo_upper: str | None = None


class AutoTagPayload(BaseModel):
    image_path: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load()
    db.init_engine(settings.db_path)
    hub = TokenHub(settings.tokenhub_key, settings.tokenhub_base)

    app = FastAPI(title="本地穿搭助手", version="0.1.0")
    app.mount("/media", StaticFiles(directory=str(settings.data_dir)), name="media")

    # ---------------------------------------------------------- 状态

    @app.get("/api/status")
    def status() -> dict:
        profile = db.get_profile()
        garments = db.list_garments(status=None)
        return {
            "garments": len(garments),
            "active": len([g for g in garments if g.status == "active"]),
            "has_profile": profile is not None,
            "offline": not settings.has_image_key,
            "auto_tag": hub.available,
            "daily_render_limit": settings.daily_render_limit,
        }

    # ---------------------------------------------------------- 档案

    @app.get("/api/profile")
    def get_profile() -> dict:
        profile = db.get_profile()
        if profile is None:
            return {"profile": None}
        report = profiler.analyse(profile)
        return {
            "profile": {
                "height_cm": profile.height_cm,
                "weight_kg": profile.weight_kg,
                "chest_cm": profile.chest_cm,
                "waist_cm": profile.waist_cm,
                "hip_cm": profile.hip_cm,
                "shoulder_cm": profile.shoulder_cm,
                "inseam_cm": profile.inseam_cm,
                "skin_tone": profile.skin_tone,
                "photo_full": profile.photo_full,
                "photo_upper": profile.photo_upper,
            },
            "report": {
                "bmi": report.bmi,
                "build": report.build,
                "body_shape": report.body_shape,
                "summary": profiler.describe(report),
                "hints": report.hints,
            },
        }

    @app.put("/api/profile")
    def put_profile(payload: ProfilePayload) -> dict:
        if payload.height_cm <= 0 or payload.weight_kg <= 0:
            raise HTTPException(400, "身高体重必须大于 0")
        saved = db.save_profile(BodyProfile(**payload.model_dump()))
        return {"ok": True, "updated_at": saved.updated_at.isoformat()}

    # ---------------------------------------------------------- 衣橱

    @app.get("/api/garments")
    def list_garments(status: str | None = "active") -> dict:
        items = db.list_garments(status=status)
        return {"garments": [_garment_dict(g) for g in items]}

    @app.post("/api/garments")
    def create_garment(payload: GarmentPayload) -> dict:
        if payload.category not in ("top", "bottom", "outerwear", "dress", "shoes", "bag", "accessory"):
            raise HTTPException(400, "未知的品类")
        if not 1 <= payload.warmth <= 5:
            raise HTTPException(400, "厚薄必须在 1–5 之间")
        if not 1 <= payload.formality <= 5:
            raise HTTPException(400, "正式度必须在 1–5 之间")
        saved = db.add_garment(Garment(**payload.model_dump()))
        return _garment_dict(saved)

    @app.post("/api/garments/autotag")
    def autotag(payload: AutoTagPayload) -> dict:
        """让视觉模型认一遍照片，返回建议的标签。只给建议，不落库。"""
        path = settings.data_dir / payload.image_path
        if not path.exists():
            raise HTTPException(404, "找不到这张照片")
        try:
            tags = hub.tag_garment(path.read_bytes())
        except TokenHubError as error:
            raise HTTPException(502, str(error)) from error
        return tags.to_dict()

    @app.patch("/api/garments/{garment_id}")
    def patch_garment(garment_id: int, payload: dict) -> dict:
        garment = db.get_garment(garment_id)
        if garment is None:
            raise HTTPException(404, "没有这件衣服")
        allowed = {
            "name",
            "category",
            "subcategory",
            "color_primary",
            "color_hex",
            "warmth",
            "formality",
            "fit",
            "status",
            "image_path",
        }
        for key, value in payload.items():
            if key in allowed:
                setattr(garment, key, value)
        return _garment_dict(db.update_garment(garment))

    @app.delete("/api/garments/{garment_id}")
    def remove_garment(garment_id: int) -> dict:
        if not db.delete_garment(garment_id):
            raise HTTPException(404, "没有这件衣服")
        return {"ok": True}

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)) -> dict:
        suffix = Path(file.filename or "photo.jpg").suffix.lower() or ".jpg"
        if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".heic"}:
            raise HTTPException(400, "只支持 jpg / png / webp / heic")
        name = f"{uuid.uuid4().hex}{suffix}"
        target = settings.photo_dir / name
        target.write_bytes(await file.read())

        try:
            capture.normalize(target)
        except Exception as error:  # noqa: BLE001 — 图坏了不该让整个入库失败
            target.unlink(missing_ok=True)
            raise HTTPException(400, f"这张图打不开：{error}") from error

        result = wardrobe.ingest(target, settings.cutout_dir, settings.model_dir)
        cutout_rel = None
        if result.cutout_path:
            cutout_rel = f"cutouts/{Path(result.cutout_path).name}"

        return {
            "path": f"photos/{name}",
            "url": f"/media/photos/{name}",
            "color_hex": result.color_hex,
            "color_name": result.color_name,
            "cutout_path": cutout_rel,
            "cutout_url": _media_url(cutout_rel),
            "notice": result.cutout_skipped_reason,
        }

    # ---------------------------------------------------------- 天气

    @app.get("/api/weather")
    def get_weather() -> dict:
        latitude = db.get_setting("city_lat")
        longitude = db.get_setting("city_lon")
        city_name = db.get_setting("city_name")

        if not latitude or not longitude:
            return {"configured": False}

        city = weather_client.City(
            name=city_name or "",
            latitude=float(latitude),
            longitude=float(longitude),
        )

        cached_raw = db.get_setting("weather_cache")
        cached = json.loads(cached_raw) if cached_raw else None
        if cached:
            cached_at = datetime.fromisoformat(cached["fetched_at"])
            fresh_enough = datetime.now(timezone.utc) - cached_at < WEATHER_TTL
            if fresh_enough:
                return {"configured": True, "stale": False, **cached, "city": city.name}

        try:
            current = weather_client.fetch(city)
        except weather_client.WeatherError as error:
            if cached:
                return {
                    "configured": True,
                    "stale": True,
                    "city": city.name,
                    **cached,
                    "error": f"这次没取到天气，下面是上一次的：{error}",
                }
            return {"configured": True, "stale": True, "city": city.name, "error": str(error)}

        payload = {
            "temp_c": current.effective_c,
            "hour_temp": current.hour_temp,
            "temp_min": current.temp_min,
            "temp_max": current.temp_max,
            "condition": current.condition,
            "code": current.code,
            "is_rainy": current.is_rainy,
            "summary": current.summary(),
            "fetched_at": current.fetched_at.isoformat(),
        }
        db.set_setting("weather_cache", json.dumps(payload))
        return {"configured": True, "stale": False, "city": city.name, **payload}

    @app.post("/api/weather/city")
    def set_city(payload: CityPayload) -> dict:
        try:
            city = weather_client.geocode(payload.city)
        except weather_client.WeatherError as error:
            raise HTTPException(502, str(error)) from error
        if city is None:
            raise HTTPException(404, "没找到这个城市，换个写法试试（比如「杭州」而不是「杭」）")

        db.set_setting("city_name", city.name)
        db.set_setting("city_lat", str(city.latitude))
        db.set_setting("city_lon", str(city.longitude))
        db.delete_setting("weather_cache")
        return {"ok": True, "city": city.label}

    # ---------------------------------------------------------- 方案

    @app.get("/api/occasions")
    def occasions() -> dict:
        result = []
        for item in OCCASION_LABELS_FOR_UI:
            lo, hi = rules.formality_range(item["key"])
            result.append({**item, "formality": [lo, hi]})
        return {"occasions": result, "labels": OCCASION_LABELS}

    @app.post("/api/plan")
    def plan(request: PlanRequest) -> dict:
        profile = db.get_profile()
        wardrobe = db.list_garments()
        recent = db.recent_outfit_sets(limit=3)
        if request.exclude_ids:
            # "换一套"：把刚看过的这套当成"最近穿过"，用同一套重合扣分把它压下去
            recent = [*recent, set(request.exclude_ids)]

        # 说了人话就先理解人话；模型不可用会退回关键词，不会因此失败
        reading = intent.interpret(
            request.text,
            llm=hub if hub.available else None,
            fallback=request.occasion,
        )

        plans, pool = build_plans(
            wardrobe,
            occasion=reading.occasion,
            temp_c=request.temp_c,
            profile=profile,
            recent_outfit_ids=recent,
            preference=scoring.Preference.from_saved(db.saved_outfit_sets()),
        )

        band = rules.temp_band(request.temp_c)
        return {
            "band": band,
            "band_label": rules.BAND_LABELS[band],
            "advice": rules.temperature_advice(band, request.temp_c),
            "occasion": reading.occasion,
            "interpretation": reading.explanation,
            "usable": pool.is_usable(),
            "reason": pool.explain(),
            "pool_counts": {
                "tops": len(pool.tops),
                "bottoms": len(pool.bottoms),
                "outers": len(pool.outers),
                "shoes": len(pool.shoes),
                "bags": len(pool.bags),
                "accessories": len(pool.accessories),
                "dropped": pool.dropped,
            },
            "plans": [
                {
                    "label": item.label,
                    "score": item.score,
                    "rationale": item.rationale,
                    "garment_ids": item.ids,
                    "items": [_garment_dict(g) for g in item.items],
                }
                for item in plans
            ],
        }

    @app.post("/api/outfits")
    def save_outfit(payload: OutfitPayload) -> dict:
        if not payload.garment_ids:
            raise HTTPException(400, "方案里没有衣服")
        saved = db.save_outfit(
            Outfit(
                occasion=payload.occasion,
                temp_c=payload.temp_c,
                garment_ids=payload.garment_ids,
                rationale=payload.rationale,
                is_saved=True,
            )
        )
        return {"ok": True, "id": saved.id}

    @app.post("/api/outfits/{outfit_id}/worn")
    def mark_worn(outfit_id: int) -> dict:
        with db.session() as session:
            outfit = session.get(Outfit, outfit_id)
            if outfit is None:
                raise HTTPException(404, "没有这套方案")
            ids = list(outfit.garment_ids)
        db.mark_worn(ids, datetime.now(timezone.utc))
        db.log_event("outfit_worn", str(ids))
        return {"ok": True}

    # ---------------------------------------------------------- 出图

    @app.post("/api/render")
    def render_outfit(payload: RenderPayload) -> dict:
        items = [db.get_garment(garment_id) for garment_id in payload.garment_ids]
        items = [item for item in items if item is not None]
        if not items:
            raise HTTPException(400, "这套里没有有效的单品")

        def provider(garments: list[Garment]) -> bytes:
            """把人和衣服交给混元，出完再看一眼对不对。不齐或不对都抛错，由 renderer 降级。"""
            profile = db.get_profile()
            if profile is None or not profile.photo_full:
                raise RuntimeError("还没传身体照片，去「我的」传一张全身照")
            body_path = settings.data_dir / profile.photo_full
            if not body_path.exists():
                raise RuntimeError("身体照片找不到了，重新传一张")

            references: list[bytes] = []
            for garment in garments:
                relative = garment.cutout_path or garment.image_path
                if not relative:
                    continue
                path = settings.data_dir / relative
                if path.exists():
                    references.append(path.read_bytes())
            if not references:
                raise RuntimeError("这套里的衣服都还没有照片")

            body = body_path.read_bytes()
            description = "、".join(garment.name for garment in garments[:4])

            # 第一次用全部参考图；不过就缩到三件再试一次（参考图越多越容易走形）
            attempts = [references]
            if len(references) > 3:
                attempts.append(references[:3])

            last_note = ""
            for attempt in attempts:
                image = hub.try_on(body, attempt, description=description)
                verdict = hub.judge_try_on(body, image, description)
                if verdict.ok:
                    return image
                last_note = verdict.note
            raise RuntimeError(f"生成的图没通过校验：{last_note}")

        used_today = db.count_events_today("render_photo")
        over_quota = hub.available and used_today >= settings.daily_render_limit
        use_provider = hub.available and not over_quota

        result = render_plan(
            items,
            settings.render_dir,
            title=payload.title,
            subtitle=payload.subtitle,
            rationale=payload.rationale,
            provider=provider if use_provider else None,
        )
        if over_quota:
            result.note = (
                f"今天 {settings.daily_render_limit} 张试穿图已经用完了，这是搭配板——明天恢复。"
            )
        if result.mode == "photo":
            db.log_event("render_photo", str(payload.garment_ids))

        relative = f"renders/{Path(result.path).name}" if result.path else None
        return {
            "url": _media_url(relative),
            "mode": result.mode,
            "note": result.note,
            "quota_left": max(0, settings.daily_render_limit - db.count_events_today("render_photo")),
        }

    # ---------------------------------------------------------- 买不买

    @app.post("/api/shopping")
    def judge_purchase(payload: ShoppingPayload) -> dict:
        if payload.category not in (
            "top",
            "bottom",
            "outerwear",
            "dress",
            "shoes",
            "bag",
            "accessory",
        ):
            raise HTTPException(400, "未知的品类")

        candidate = Garment(**payload.model_dump())
        wardrobe = db.list_garments()
        verdict = shopping.evaluate(candidate, wardrobe)

        partners = [db.get_garment(garment_id) for garment_id in verdict.pairs_with]
        return {
            **verdict.to_dict(),
            "pairs": [_garment_dict(item) for item in partners if item is not None],
        }

    # ---------------------------------------------------------- 静态前端
    if settings.dist_dir.exists():
        app.mount("/", StaticBundle(directory=str(settings.dist_dir), html=True), name="ui")

    return app
