"""本地文件夹采集器：给"已经存好图的商品"用。

两个用途：
1. 站点接口挂了的时候，手动存图也能入库；
2. 测试里不联网就能验证整条导入链路。
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import RawItem, SourceError

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class LocalSource:
    name = "local"

    def fetch(self, target: str, limit: int | None = None) -> list[RawItem]:
        root = Path(target)
        if not root.is_dir():
            raise SourceError(f"不是一个目录：{root}")

        sidecar: dict = {}
        meta_file = root / "metadata.json"
        if meta_file.exists():
            try:
                sidecar = json.loads(meta_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise SourceError(f"metadata.json 不是合法 JSON：{error}") from error

        items: list[RawItem] = []
        for path in sorted(root.iterdir()):
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            meta = sidecar.get(path.name, {})
            items.append(
                RawItem(
                    external_id=path.stem,
                    title=meta.get("title") or path.stem,
                    category_hint=meta.get("category"),
                    color_name=meta.get("color"),
                    price=meta.get("price"),
                    image_urls=[str(path)],
                    product_url=meta.get("url"),
                )
            )
            if limit and len(items) >= limit:
                break
        return items
