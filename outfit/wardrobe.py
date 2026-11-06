"""衣橱入库：照片 → 主色 → 抠图 → 待确认的草稿。

抠图是可选的：装了 rembg 就自动抠，没装就保留原图铺白底。
不因为一个依赖没装就让整个入库流程卡住——这是设计文档第 10 节的要求。

但"降级"不等于"含糊"：失败原因要原样带出去，否则用户看到一句
"未安装"永远不知道自己其实是网络问题。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import capture

# rembg 默认把模型下到 ~/.u2net，我们把它收进 data/models：
# 数据集中在一个目录里，备份和迁移都只搬一个地方。
MODEL_ENV = "U2NET_HOME"


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


def make_cutout(
    image_path: Path, out_dir: Path, model_dir: Path | None = None
) -> tuple[Path | None, str | None]:
    """抠掉背景。返回 (路径, 失败原因)，二者必有一个是 None。"""
    if not cutout_available():
        return None, "未安装抠图组件（rembg），已保留原图"

    try:
        from rembg import remove
    except Exception as error:  # noqa: BLE001
        return None, f"抠图组件装坏了：{error}"

    if model_dir is not None:
        model_dir.mkdir(parents=True, exist_ok=True)
        os.environ[MODEL_ENV] = str(model_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{image_path.stem}.png"
    try:
        with image_path.open("rb") as source:
            data = remove(source.read())
        target.write_bytes(data)
    except Exception as error:  # noqa: BLE001
        # 最常见的是模型下载被墙或磁盘满，把原话带出去比"失败"有用得多
        return None, f"抠图失败：{type(error).__name__}: {error}"
    return target, None


def ingest(
    image_path: Path, cutout_dir: Path, model_dir: Path | None = None
) -> IngestResult:
    """一次入库要算的东西。全部本地，毫秒级（抠图除外）。"""
    hex_color = capture.dominant_color(image_path)
    name = capture.nearest_color_name(hex_color)
    cutout, reason = make_cutout(image_path, cutout_dir, model_dir)
    return IngestResult(
        color_hex=hex_color,
        color_name=name,
        cutout_path=str(cutout) if cutout else None,
        cutout_skipped_reason=reason,
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
