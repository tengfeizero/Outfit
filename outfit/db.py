"""数据访问：引擎、会话、以及几个必要的查询。

不做隐藏的自动建表魔法——启动时显式调 `init_engine()`，测试里显式传临时路径。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import event as sa_event
from sqlmodel import Session, SQLModel, create_engine, select

from .models import AgentRun, AppSetting, BodyProfile, Event, Garment, Outfit

_engine = None


def init_engine(db_path: Path | str):
    """建引擎并建表。重复调用是安全的（幂等）。"""
    global _engine
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @sa_event.listens_for(_engine, "connect")
    def _pragmas(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(_engine)
    _ensure_columns(_engine)
    return _engine


# 新加的列。SQLite 的 create_all 不会改已有表，只能自己补。
_EXTRA_COLUMNS = (
    ("source", "TEXT"),
    ("source_url", "TEXT"),
    ("external_id", "TEXT"),
    ("price_cny", "REAL"),
    ("imported_at", "TIMESTAMP"),
)


def _ensure_columns(engine) -> None:
    with engine.connect() as connection:
        existing = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(garment)")}
        for name, ddl in _EXTRA_COLUMNS:
            if name not in existing:
                connection.exec_driver_sql(f"ALTER TABLE garment ADD COLUMN {name} {ddl}")
        connection.commit()


def get_engine():
    if _engine is None:
        raise RuntimeError("数据库还没初始化，先调用 init_engine()")
    return _engine


@contextmanager
def session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


# ---------------------------------------------------------------- 身体档案


def save_profile(profile: BodyProfile) -> BodyProfile:
    """档案只有一行。第二次保存覆盖第一次，而不是新增。"""
    profile.id = 1
    profile.updated_at = datetime.now(timezone.utc)
    with session() as s:
        existing = s.get(BodyProfile, 1)
        if existing is None:
            s.add(profile)
            s.commit()
            s.refresh(profile)
            return profile

        data = profile.model_dump(exclude={"id"})
        for key, value in data.items():
            setattr(existing, key, value)
        s.add(existing)
        s.commit()
        s.refresh(existing)
        return existing


def get_profile() -> BodyProfile | None:
    with session() as s:
        return s.get(BodyProfile, 1)


# ---------------------------------------------------------------- 衣橱


def add_garment(garment: Garment) -> Garment:
    with session() as s:
        s.add(garment)
        s.commit()
        s.refresh(garment)
        return garment


def update_garment(garment: Garment) -> Garment:
    with session() as s:
        s.add(garment)
        s.commit()
        s.refresh(garment)
        return garment


def get_garment(garment_id: int) -> Garment | None:
    with session() as s:
        return s.get(Garment, garment_id)


def list_garments(status: str | None = "active") -> list[Garment]:
    with session() as s:
        statement = select(Garment)
        if status:
            statement = statement.where(Garment.status == status)
        return list(s.exec(statement.order_by(Garment.category, Garment.id)).all())


def find_external(source: str, external_id: str, color: str | None = None) -> Garment | None:
    """同一个站点、同一件商品、同一个颜色，只该有一行。采集靠它做幂等。"""
    with session() as s:
        statement = select(Garment).where(
            Garment.source == source, Garment.external_id == external_id
        )
        if color:
            statement = statement.where(Garment.color_primary == color)
        return s.exec(statement).first()


def delete_garment(garment_id: int) -> bool:
    with session() as s:
        garment = s.get(Garment, garment_id)
        if garment is None:
            return False
        s.delete(garment)
        s.commit()
        return True


def mark_worn(garment_ids: list[int], when: datetime | None = None) -> None:
    when = when or datetime.now(timezone.utc)
    with session() as s:
        for garment_id in garment_ids:
            garment = s.get(Garment, garment_id)
            if garment is None:
                continue
            garment.wear_count += 1
            garment.last_worn_at = when
            s.add(garment)
        s.commit()


# ---------------------------------------------------------------- 方案


def save_outfit(outfit: Outfit) -> Outfit:
    with session() as s:
        s.add(outfit)
        s.commit()
        s.refresh(outfit)
        return outfit


def recent_outfit_sets(limit: int = 3) -> list[set[int]]:
    """最近几套方案的衣物 id 集合，用于"别连着穿同一套"的扣分。"""
    with session() as s:
        rows = s.exec(select(Outfit).order_by(Outfit.created_at.desc()).limit(limit)).all()
    return [{int(i) for i in row.garment_ids} for row in rows if row.garment_ids]


def saved_outfit_sets(limit: int = 50) -> list[list[int]]:
    """收藏过的方案。这是"你喜欢什么"唯一的一手证据——比穿着次数诚实。"""
    with session() as s:
        rows = s.exec(
            select(Outfit)
            .where(Outfit.is_saved.is_(True))
            .order_by(Outfit.created_at.desc())
            .limit(limit)
        ).all()
    return [[int(i) for i in row.garment_ids] for row in rows if row.garment_ids]


# ---------------------------------------------------------------- 设置


def get_setting(key: str, default: str | None = None) -> str | None:
    with session() as s:
        row = s.get(AppSetting, key)
        return row.value if row else default


def set_setting(key: str, value: str) -> None:
    with session() as s:
        row = s.get(AppSetting, key)
        if row is None:
            s.add(AppSetting(key=key, value=value))
        else:
            row.value = value
            row.updated_at = datetime.now(timezone.utc)
            s.add(row)
        s.commit()


def delete_setting(key: str) -> None:
    with session() as s:
        row = s.get(AppSetting, key)
        if row is not None:
            s.delete(row)
            s.commit()


# ---------------------------------------------------------------- 运行轨迹


def save_run(run: AgentRun) -> AgentRun:
    with session() as s:
        s.add(run)
        s.commit()
        s.refresh(run)
        return run


def list_runs(limit: int = 20) -> list[AgentRun]:
    with session() as s:
        return list(s.exec(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)).all())


def get_run(run_id: int) -> AgentRun | None:
    with session() as s:
        return s.get(AgentRun, run_id)


# ---------------------------------------------------------------- 事件


def log_event(kind: str, payload: str = "") -> None:
    with session() as s:
        s.add(Event(type=kind, payload=payload))
        s.commit()


def count_events_today(kind: str) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with session() as s:
        rows = s.exec(select(Event).where(Event.type == kind, Event.created_at >= start)).all()
    return len(rows)
