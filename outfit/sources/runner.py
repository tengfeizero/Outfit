"""把采集到的商品写进衣橱。

采集器只管捞数据，这里管：去重、下载图片、落库、留档、出报告。
所有副作用集中在这一个文件，所以它最值得写测试。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .. import capture, db
from ..models import Garment
from . import mapping
from .base import RawItem, Source

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"


@dataclass
class ImportReport:
    source: str
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    run_dir: Path | None = None
    details: list[dict] = field(default_factory=list)

    def add(self, status: str, item: RawItem, **extra) -> None:
        setattr(self, status, getattr(self, status) + 1)
        self.details.append(
            {"status": status, "id": item.external_id, "title": item.title, **extra}
        )

    def summary(self) -> str:
        return (
            f"新增 {self.created} 件，更新 {self.updated} 件，"
            f"跳过 {self.skipped} 件，失败 {self.failed} 件"
        )

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "run_dir": str(self.run_dir) if self.run_dir else None,
            "details": self.details,
        }


def _fetch_image(url: str, target: Path, client: httpx.Client | None = None) -> bool:
    """远程 URL 下载，本地路径直接拷。失败返回 False，不抛。"""
    try:
        if url.startswith("http"):
            owns = client is None
            http = client or httpx.Client(timeout=30, follow_redirects=True)
            try:
                response = http.get(url, headers={"User-Agent": UA})
                response.raise_for_status()
                target.write_bytes(response.content)
            finally:
                if owns:
                    http.close()
        else:
            shutil.copyfile(url, target)
        return True
    except Exception:  # noqa: BLE001 — 一张图失败不该毁掉整批导入
        return False


def run(
    source: Source,
    target: str,
    *,
    settings,
    limit: int | None = None,
    dry_run: bool = False,
    with_images: bool = True,
    with_cutout: bool = True,
    client: httpx.Client | None = None,
) -> ImportReport:
    items = source.fetch(target, limit=limit)
    report = ImportReport(source=source.name)

    if not dry_run:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        report.run_dir = settings.data_dir / "imports" / source.name / stamp
        report.run_dir.mkdir(parents=True, exist_ok=True)
        (report.run_dir / "items.json").write_text(
            json.dumps([item.__dict__ for item in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    image_dir = settings.photo_dir / source.name

    for item in items:
        fields = mapping.to_garment(item)

        existing = db.find_external(source.name, item.external_id, fields["color_primary"])
        if existing is not None:
            if not dry_run:
                existing.price_cny = fields.get("price_cny") or existing.price_cny
                existing.source_url = fields.get("source_url") or existing.source_url
                db.update_garment(existing)
            report.add("updated", item, garment_id=existing.id)
            continue

        if dry_run:
            report.add("created", item, preview=fields)
            continue

        photo_path = None
        if with_images and item.image_urls:
            image_dir.mkdir(parents=True, exist_ok=True)
            safe_color = (fields["color_primary"] or "x").replace("/", "-")
            target_file = image_dir / f"{item.external_id}-{safe_color}.jpg"
            if _fetch_image(item.image_urls[0], target_file, client=client):
                try:
                    capture.normalize(target_file)
                    photo_path = target_file
                except Exception:  # noqa: BLE001
                    photo_path = None

        relative = None
        cutout_relative = None
        if photo_path is not None:
            relative = str(photo_path.relative_to(settings.data_dir)).replace("\\", "/")
            if with_cutout:
                from .. import wardrobe

                result = wardrobe.ingest(photo_path, settings.cutout_dir, settings.model_dir)
                if result.cutout_path:
                    cutout = Path(result.cutout_path)
                    cutout_relative = str(cutout.relative_to(settings.data_dir)).replace("\\", "/")
                if not fields.get("color_hex") and result.color_hex:
                    fields["color_hex"] = result.color_hex

        garment = Garment(
            name=fields["name"],
            category=fields["category"],
            color_primary=fields["color_primary"],
            color_hex=fields.get("color_hex"),
            warmth=fields["warmth"],
            formality=fields["formality"],
            status="active",
            image_path=relative,
            cutout_path=cutout_relative,
            label_confidence=0.9,
            source=source.name,
            source_url=fields.get("source_url"),
            external_id=item.external_id,
            price_cny=fields.get("price_cny"),
            imported_at=datetime.now(timezone.utc),
        )
        try:
            saved = db.add_garment(garment)
        except Exception as error:  # noqa: BLE001
            report.add("failed", item, error=f"{type(error).__name__}: {error}")
            continue
        report.add("created", item, garment_id=saved.id, image=relative)

    if not dry_run and report.run_dir is not None:
        (report.run_dir / "report.json").write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report
