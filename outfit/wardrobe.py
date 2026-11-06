"""衣橱入库：照片 → 主色 → 抠图 → 待确认的草稿。

抠图是可选的：装了 rembg 就自动抠，没装就保留原图铺白底。
不因为一个依赖没装就让整个入库流程卡住——这是设计文档第 10 节的要求。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import capture


@dataclass
class IngestResult:
    color_hex: str
    color_name: str
    cutout_path: str | None
    cutout_skipped_reason: str | None = None


def cutout_available() -> bool:
    try:
        import rembg  # noqa: F401
    except Exception:  # noqa: BLE001 — 导入失败的理由五花八门，一律当作没有
        return False
    return True


def make_cutout(image_path: Path, out_dir: Path) -> Path | None:
    """抠掉背景。失败就返回 None，调用方保留原图。"""
    if not cutout_available():
        return None
    try:
        from rembg import remove

        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{image_path.stem}.png"
        with image_path.open("rb") as source, target.open("wb") as sink:
            sink.write(remove(source.read()))
        return target
    except Exception:  # noqa: BLE001 — 模型没下完、内存不够等等，都不该阻断入库
        return None


def ingest(image_path: Path, cutout_dir: Path) -> IngestResult:
    """一次入库要算的东西。全部本地，毫秒级（抠图除外）。"""
    hex_color = capture.dominant_color(image_path)
    name = capture.nearest_color_name(hex_color)

    cutout = make_cutout(image_path, cutout_dir)
    reason = None if cutout else "未安装抠图组件（rembg），已保留原图"
    return IngestResult(
        color_hex=hex_color,
        color_name=name,
        cutout_path=str(cutout) if cutout else None,
        cutout_skipped_reason=None if cutout else reason,
    )


def guess_name(category: str, color_name: str) -> str:
    """给个能直接用的默认名，用户想改再改。"""
    labels = {
        "top": "上装",
        "bottom": "下装",
        "outerwear": "外套",
        "dress": "连衣裙",
        "shoes": "鞋",
        "bag": "包",
        "accessory": "配饰",
    }
    return f"{color_name}{labels.get(category, '单品')}"
