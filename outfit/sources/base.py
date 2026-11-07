"""采集源的公共形状。

一个采集源只负责两件事：**把站点翻译成 RawItem**，以及**说清楚自己为什么失败**。
入库、去重、下载图片、映射到我们的字段——都不归它管，那是 runner 的事。
这样加一个新站点，只需要写一个 fetch()。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class SourceError(RuntimeError):
    """采集失败。message 会原样展示给使用者，所以要写人话。"""


class SourceUnavailable(SourceError):
    """这个源现在拿不到数据——通常是接口变了，而不是网络问题。"""


@dataclass
class RawItem:
    """站点上的一件商品，已经尽量抽干净了，但还没映射成我们的 Garment。"""

    external_id: str
    title: str
    category_hint: str | None = None
    color_name: str | None = None
    color_hex: str | None = None
    price: float | None = None
    image_urls: list[str] = field(default_factory=list)
    product_url: str | None = None
    extra: dict = field(default_factory=dict)


@runtime_checkable
class Source(Protocol):
    name: str

    def fetch(self, target: str, limit: int | None = None) -> list[RawItem]:
        """target 可以是分类页 URL、商品 ID、或本地目录，由各源自己解释。"""
        ...
