"""数据库表定义。

字段含义见设计文档第 6 节。这里只放结构，不放业务逻辑。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


GARMENT_CATEGORIES = (
    "top",
    "bottom",
    "outerwear",
    "dress",
    "shoes",
    "bag",
    "accessory",
)

GARMENT_STATUSES = ("active", "stored", "laundry", "lent")

OCCASIONS = ("interview", "work", "date", "sport", "home", "custom")


class BodyProfile(SQLModel, table=True):
    __tablename__ = "body_profile"

    id: int = Field(default=1, primary_key=True)
    height_cm: float
    weight_kg: float
    chest_cm: float | None = None
    waist_cm: float | None = None
    hip_cm: float | None = None
    shoulder_cm: float | None = None
    inseam_cm: float | None = None
    body_shape: str | None = None
    skin_tone: str | None = None
    photo_full: str | None = None
    photo_upper: str | None = None
    updated_at: datetime = Field(default_factory=utcnow)


class Garment(SQLModel, table=True):
    __tablename__ = "garment"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    category: str
    subcategory: str | None = None

    color_primary: str
    color_hex: str | None = None
    color_secondary: str | None = None
    pattern: str | None = None
    material: str | None = None

    warmth: int
    formality: int
    seasons: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    style_tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    fit: str | None = None

    brand: str | None = None
    size: str | None = None

    image_path: str | None = None
    cutout_path: str | None = None
    label_confidence: float = 1.0

    wear_count: int = 0
    last_worn_at: datetime | None = None
    status: str = "active"

    created_at: datetime = Field(default_factory=utcnow)


class Outfit(SQLModel, table=True):
    __tablename__ = "outfit"

    id: int | None = Field(default=None, primary_key=True)
    occasion: str
    temp_c: float | None = None
    weather_text: str | None = None

    garment_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    rationale: str | None = None
    coverage: str = "full"

    render_path: str | None = None
    render_status: str = "none"
    render_quality: float | None = None

    is_saved: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class ShoppingVerdict(SQLModel, table=True):
    __tablename__ = "shopping_verdict"

    id: int | None = Field(default=None, primary_key=True)
    image_path: str
    verdict: str
    reasons: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    pairs_with: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Event(SQLModel, table=True):
    __tablename__ = "event"

    id: int | None = Field(default=None, primary_key=True)
    type: str
    payload: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class AppSetting(SQLModel, table=True):
    """零散的键值配置：城市、坐标、上次的天气缓存。

    不为这些单开字段，是因为它们会一直长，表结构不想跟着改。
    """

    __tablename__ = "app_setting"

    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=utcnow)


class AgentRun(SQLModel, table=True):
    """一次 agent 运行的完整轨迹。

    存下来不是为了审计，是为了能回放：面试时"它是怎么想的"比"它做成了"更有说服力。
    """

    __tablename__ = "agent_run"

    id: int | None = Field(default=None, primary_key=True)
    text: str
    status: str = "ok"  # ok / failed / budget / fallback
    occasion: str | None = None
    steps: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    cost: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)
