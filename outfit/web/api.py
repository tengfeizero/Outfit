"""HTTP 接口。

刻意保持薄：这里只做参数校验、调下层、把结果转成前端要的形状。
所有判断都在 rules / candidates / scoring / stylist 里，能单独测。
"""

from __future__ import annotations

import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import db, profiler, rules
from ..config import Settings, load
from ..models import BodyProfile, Garment, Outfit
from ..stylist.plan import OCCASION_LABELS, build_plans

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
    exclude_ids: list[int] = []


class OutfitPayload(BaseModel):
    occasion: str
    temp_c: float | None = None
    garment_ids: list[int]
    rationale: str | None = None


class ProfilePayload(BaseModel):
    height_cm: float
    weight_kg: float
    chest_cm: float | None = None
    waist_cm: float | None = None
    hip_cm: float | None = None
    shoulder_cm: float | None = None
    inseam_cm: float | None = None
    skin_tone: str | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load()
    db.init_engine(settings.db_path)

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
        return {"path": f"photos/{name}", "url": f"/media/photos/{name}"}

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

        plans, pool = build_plans(
            wardrobe,
            occasion=request.occasion,
            temp_c=request.temp_c,
            profile=profile,
            recent_outfit_ids=recent,
        )

        band = rules.temp_band(request.temp_c)
        return {
            "band": band,
            "band_label": rules.BAND_LABELS[band],
            "advice": rules.temperature_advice(band, request.temp_c),
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

    # 静态前端放在最后挂载：挂在 "/" 会把 /api 和 /media 一起吞掉
    if settings.dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(settings.dist_dir), html=True), name="ui")

    return app
