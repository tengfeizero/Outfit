"""出图：先试真图，不行退回搭配板。

设计文档 7.4 的降级链在这里落地。真图那一步需要外部图像服务，
没有配置时直接走搭配板——不是"失败"，是"这一档现在只有这个"。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from ..models import Garment
from .board import build_board


@dataclass
class RenderResult:
    path: Path | None
    mode: str  # photo / board / failed
    note: str = ""


def render(
    items: list[Garment],
    out_dir: Path,
    *,
    title: str = "",
    subtitle: str = "",
    rationale: str = "",
    filename: str | None = None,
    provider=None,
) -> RenderResult:
    """provider 是个可调用对象：传进去一套衣服，返回一张图的路径。

    现在没有接任何图像服务，所以 provider 为空，一律出搭配板。
    接口留在这里，是为了将来接上时不用动调用方。
    """
    name = filename or f"{uuid.uuid4().hex}.png"
    target = out_dir / name

    if provider is not None:
        try:
            produced = provider(items)
            if produced:
                return RenderResult(Path(produced), "photo")
            note = "出图服务没有返回结果，已退回搭配板"
        except Exception as error:  # noqa: BLE001
            note = f"出图失败，已退回搭配板：{error}"
        build_board(items, target, title=title, subtitle=subtitle, rationale=rationale)
        return RenderResult(target, "board", note)

    build_board(items, target, title=title, subtitle=subtitle, rationale=rationale)
    return RenderResult(target, "board", "还没接出图服务，这是搭配板——它不会把格纹糊掉。")
