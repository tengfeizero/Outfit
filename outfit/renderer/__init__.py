"""出图：先试真图，不行退回搭配板。

设计文档 7.4 的降级链在这里落地。provider 是个可调用对象：传进去一套衣服，
返回图片字节。没有配置、报错、返回空——三种情况都退回搭配板，而不是让用户看报错。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from ..models import Garment
from .board import build_board

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@dataclass
class RenderResult:
    path: Path | None
    mode: str  # photo / board / failed
    note: str = ""


def _write(out_dir: Path, data: bytes) -> Path:
    suffix = ".png" if data[:8] == PNG_MAGIC else ".jpg"
    target = out_dir / f"{uuid.uuid4().hex}{suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def render(
    items: list[Garment],
    out_dir: Path,
    *,
    title: str = "",
    subtitle: str = "",
    rationale: str = "",
    provider=None,
) -> RenderResult:
    out_dir.mkdir(parents=True, exist_ok=True)

    if provider is not None:
        try:
            produced = provider(items)
            if produced:
                return RenderResult(_write(out_dir, produced), "photo")
            note = "出图服务没有返回图片，已退回搭配板"
        except Exception as error:  # noqa: BLE001 — 任何失败都要能降级
            note = f"出图失败，已退回搭配板：{error}"
        target = out_dir / f"{uuid.uuid4().hex}.png"
        build_board(items, target, title=title, subtitle=subtitle, rationale=rationale)
        return RenderResult(target, "board", note)

    target = out_dir / f"{uuid.uuid4().hex}.png"
    build_board(items, target, title=title, subtitle=subtitle, rationale=rationale)
    return RenderResult(target, "board", "还没接出图服务，这是搭配板——它不会把格纹糊掉。")
