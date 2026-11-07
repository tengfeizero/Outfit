"""商品采集：一个源一个文件，新增站点只需要再写一个 fetch()。

用法见 cli.py：

    python -m outfit.sources list
    python -m outfit.sources import uniqlo https://www.uniqlo.cn/c/2mouterwr.html --limit 20 --dry-run
    python -m outfit.sources import local ./data/inbox/shirts
"""

from __future__ import annotations

import inspect

from .base import RawItem, Source, SourceError, SourceUnavailable
from .local import LocalSource
from .uniqlo import UniqloSource

SOURCES: dict[str, type] = {
    "uniqlo": UniqloSource,
    "local": LocalSource,
}

__all__ = [
    "RawItem",
    "Source",
    "SourceError",
    "SourceUnavailable",
    "SOURCES",
    "get_source",
]


def get_source(name: str, **options):
    """按名字造一个源，只传它认识的参数——这样新增源不用改这里。"""
    factory = SOURCES.get(name)
    if factory is None:
        raise KeyError(f"没有这个采集源：{name}（可用：{'、'.join(SOURCES)}）")
    accepted = set(inspect.signature(factory.__init__).parameters)
    return factory(**{key: value for key, value in options.items() if key in accepted})
