"""优衣库（中国官网）采集器。

站点是重前端，商品只能从它的数据接口拿。接口路径改过好几次，所以这里：
1. 按顺序试几个已知的地址；
2. 允许用 --endpoint 直接指定（开发者工具里复制那条 XHR 就行）；
3. 全都不行时，抛 SourceUnavailable 并说清楚下一步怎么做，而不是返回空列表。

返回空列表是最糟的失败方式——你会以为"这个分类没货"。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from .base import RawItem, SourceUnavailable

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# 按顺序试。{code} 是分类页 URL 里那段，比如 2mouterwr。
ENDPOINTS = [
    "https://www.uniqlo.cn/api/commerce/v5/zh/products?path=/c/{code}&limit={limit}&offset=0",
    "https://www.uniqlo.cn/api/commerce/v3/zh/products?path=/c/{code}&limit={limit}&offset=0",
    "https://www.uniqlo.cn/p/l4api?path=/v3/products&categoryId={code}&limit={limit}&offset=0",
]

CATEGORY_IN_URL = re.compile(r"/c/([a-z0-9]+)\.html", re.IGNORECASE)


class UniqloSource:
    name = "uniqlo"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        endpoint: str | None = None,
        from_file: Path | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._client = client
        self._endpoint = endpoint
        self._from_file = from_file
        self._timeout = timeout
        self.last_attempts: list[str] = []

    def fetch(self, target: str, limit: int | None = None) -> list[RawItem]:
        limit = limit or 60

        if self._from_file is not None:
            payload = json.loads(self._from_file.read_text(encoding="utf-8"))
            return self.parse(payload, limit=limit)

        code = extract_code(target)
        urls = [self._endpoint] if self._endpoint else []
        urls += [template.format(code=code, limit=limit) for template in ENDPOINTS]

        errors: list[str] = []
        for url in urls:
            if not url:
                continue
            try:
                payload = self._get(url)
            except Exception as error:  # noqa: BLE001
                self.last_attempts.append(f"{url} → {type(error).__name__}")
                errors.append(f"{url} → {error}")
                continue

            items = self.parse(payload, limit=limit)
            if items:
                self.last_attempts.append(f"{url} → {len(items)} 件")
                return items
            self.last_attempts.append(f"{url} → 200 但没有商品")
            errors.append(f"{url} → 返回 200 但解析不出商品")

        raise SourceUnavailable(
            "优衣库的数据接口没拿到商品。试过：\n  "
            + "\n  ".join(self.last_attempts)
            + "\n这个站点的接口改版很勤。两个办法：\n"
            "  1) 浏览器打开分类页 → F12 → Network → 筛 XHR → 找到返回商品列表那条，"
            "复制 URL，用 --endpoint '...' 传进来；\n"
            "  2) 把那条请求的响应存成 json，用 --from-file 直接导入（离线也能跑）。"
        )

    # ------------------------------------------------------------ 网络

    def _get(self, url: str) -> Any:
        owns = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout, follow_redirects=True)
        try:
            response = client.get(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://www.uniqlo.cn/",
                },
            )
            response.raise_for_status()
            return response.json()
        finally:
            if owns:
                client.close()

    # ------------------------------------------------------------ 解析

    def parse(self, payload: Any, limit: int | None = None) -> list[RawItem]:
        """容忍几种常见的包装：result.items / items / products / data。"""
        rows = _find_list(payload)
        items: list[RawItem] = []
        for row in rows:
            items.extend(_expand(row))
            if limit and len(items) >= limit:
                break
        return items[:limit] if limit else items


def extract_code(url: str) -> str:
    match = CATEGORY_IN_URL.search(url)
    if match:
        return match.group(1)
    return url.rstrip("/").split("/")[-1].replace(".html", "")


def _find_list(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("items", "products", "data", "list", "goods"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]

    result = payload.get("result")
    if isinstance(result, dict):
        return _find_list(result)
    if isinstance(result, list):
        return [row for row in result if isinstance(row, dict)]
    return []


def _first(row: dict, *keys: str, default=None):
    for key in keys:
        value = row.get(key)
        if value not in (None, "", []):
            return value
    return default


def _price(row: dict) -> float | None:
    value = _first(row, "price", "salePrice", "originPrice")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for path in (("currency", "value"), ("value",), ("amount",)):
            node: Any = value
            for step in path:
                node = node.get(step) if isinstance(node, dict) else None
            if isinstance(node, (int, float)):
                return float(node)
    if isinstance(value, str):
        digits = re.sub(r"[^\d.]", "", value)
        try:
            return float(digits)
        except ValueError:
            return None
    return None


def _image(row: dict) -> list[str]:
    urls: list[str] = []
    images = row.get("images")
    if isinstance(images, dict):
        for node in images.values():
            if isinstance(node, str):
                urls.append(node)
            elif isinstance(node, dict) and node.get("imageUrl"):
                urls.append(str(node["imageUrl"]))
    if isinstance(images, list):
        for node in images:
            if isinstance(node, str):
                urls.append(node)
            elif isinstance(node, dict) and node.get("url"):
                urls.append(str(node["url"]))
    main = _first(row, "imageUrl", "mainImage", "image")
    if isinstance(main, str):
        urls.insert(0, main)
    return urls[:2]


def _expand(row: dict) -> list[RawItem]:
    """一件商品有多个颜色。每个颜色在我们这里是一件独立的衣服。"""
    external_id = str(_first(row, "productId", "id", "product_id", "goodsId", default=""))
    if not external_id:
        return []

    title = str(_first(row, "name", "title", "productName", "goodsName", default="未命名"))
    url = _first(row, "productUrl", "url", "pdpUrl")
    price = _price(row)
    images = _image(row)
    parent_code = _first(row, "productCode", "code")

    colors = row.get("colors") or row.get("colorList") or []
    if not isinstance(colors, list) or not colors:
        return [
            RawItem(
                external_id=external_id,
                title=title,
                price=price,
                image_urls=images,
                product_url=url,
                extra={"parent_code": parent_code},
            )
        ]

    items: list[RawItem] = []
    for color in colors:
        if not isinstance(color, dict):
            continue
        color_name = _first(color, "name", "colorName", "displayName")
        items.append(
            RawItem(
                external_id=str(_first(color, "productId", default=external_id)),
                title=title,
                color_name=str(color_name) if color_name else None,
                color_hex=_first(color, "hex", "colorCode", "rgb"),
                price=price,
                image_urls=images,
                product_url=url,
                extra={"parent_code": parent_code, "color_display": color_name},
            )
        )
    return items or [
        RawItem(
            external_id=external_id,
            title=title,
            price=price,
            image_urls=images,
            product_url=url,
            extra={"parent_code": parent_code},
        )
    ]
