"""命令行入口。

    python -m outfit.sources list
    python -m outfit.sources import uniqlo <分类页URL> [--limit 20] [--dry-run]
    python -m outfit.sources import local <目录>

--dry-run 只打印"会导入什么"，不写库、不下载图——先看清楚再按回车。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..config import load
from .. import db
from . import SOURCES, get_source
from .base import SourceError
from .runner import run

CATEGORY_LABELS = {
    "top": "上装",
    "bottom": "下装",
    "outerwear": "外套",
    "dress": "连衣裙",
    "shoes": "鞋",
    "bag": "包",
    "accessory": "配饰",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m outfit.sources", description="把外部商品导入衣橱")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="列出可用的采集源")

    imp = sub.add_parser("import", help="从某个源导入")
    imp.add_argument("source", choices=sorted(SOURCES))
    imp.add_argument("target", help="分类页 URL / 本地目录 / 商品 ID，由源自己解释")
    imp.add_argument("--limit", type=int, default=30, help="最多导入多少件（默认 30）")
    imp.add_argument("--dry-run", action="store_true", help="只看结果，不写库、不下载")
    imp.add_argument("--endpoint", help="直接指定数据接口（站点改版时用）")
    imp.add_argument("--from-file", type=Path, help="从存好的 JSON 响应导入，不联网")
    imp.add_argument("--no-images", action="store_true", help="不下载图片")
    imp.add_argument("--no-cutout", action="store_true", help="下载图但不抠图（快很多）")
    imp.add_argument("--tag", action="store_true", help="让视觉模型认品类和颜色（约 ¥0.01/件）")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "list"):
        print("可用的采集源：")
        for name in sorted(SOURCES):
            print(f"  {name}")
        return 0

    settings = load()
    db.init_engine(settings.db_path)

    source = get_source(args.source, endpoint=args.endpoint, from_file=args.from_file)

    hub = None
    if args.tag:
        from ..clients.tokenhub import TokenHub

        hub = TokenHub(settings.tokenhub_key, settings.tokenhub_base, text_model=settings.text_model)
        if not hub.available:
            print("要 --tag 得先配 TOKENHUB_API_KEY（见 .env.example）。", file=sys.stderr)
            return 1

    print(f"采集源：{args.source}    目标：{args.target}")
    if args.dry_run:
        print("（dry-run：不写库、不下载图片）")
    if args.tag:
        print(f"（会用视觉模型认品类和颜色，约 ¥0.01/件，最多 {args.limit} 件）")
    print()

    try:
        report = run(
            source,
            args.target,
            settings=settings,
            limit=args.limit,
            dry_run=args.dry_run,
            with_images=not args.no_images,
            with_cutout=not args.no_cutout,
            with_tag=args.tag,
            hub=hub,
        )
    except SourceError as error:
        print(f"\n采集失败：\n{error}", file=sys.stderr)
        return 1

    for detail in report.details:
        if detail["status"] == "created":
            preview = detail.get("preview") or {}
            label = CATEGORY_LABELS.get(preview.get("category", ""), preview.get("category", ""))
            color = preview.get("color_primary", "")
            price = preview.get("price_cny")
            money = f" ¥{price:.0f}" if price else ""
            shown = preview.get("name") or detail["title"]
            print(f"  + {shown}  [{label} · {color}]{money}")
            if detail.get("tag_error"):
                print(f"    ! {detail['tag_error']}")
        elif detail["status"] == "updated":
            print(f"  = {detail['title']}（已存在，更新价格/链接）")
        elif detail["status"] == "failed":
            print(f"  ! {detail['title']}  {detail.get('error', '')}")

    print()
    print(report.summary())
    if report.run_dir:
        print(f"留档：{report.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
