"""命令行试跑：不启动服务、不调网络，直接看三套方案长什么样。

    python -m outfit.demo --occasion work --temp 18
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import db, profiler, rules
from .models import BodyProfile
from .seed import demo_wardrobe
from .stylist.plan import OCCASION_LABELS, build_plans

ROOT = Path(__file__).resolve().parent.parent

CATEGORY_LABELS = {
    "top": "上装",
    "bottom": "下装",
    "outerwear": "外套",
    "dress": "连衣裙",
    "shoes": "鞋",
    "bag": "包",
    "accessory": "配饰",
}


def _ensure_seed(force: bool) -> None:
    existing = db.list_garments(status=None)
    if force and existing:
        for garment in existing:
            db.delete_garment(garment.id)
        existing = []
    if not existing:
        for garment in demo_wardrobe():
            db.add_garment(garment)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="本地穿搭助手 · 命令行试跑")
    parser.add_argument("--occasion", default="work", choices=[*OCCASION_LABELS])
    parser.add_argument("--temp", type=float, default=18.0, help="出门时的温度（摄氏度）")
    parser.add_argument("--reseed", action="store_true", help="重建演示衣橱")
    parser.add_argument("--db", default=str(ROOT / "data" / "outfit.db"))
    args = parser.parse_args(argv)

    db.init_engine(args.db)
    _ensure_seed(args.reseed)

    if db.get_profile() is None:
        db.save_profile(BodyProfile(height_cm=175, weight_kg=68, skin_tone="warm"))

    profile = db.get_profile()
    wardrobe = db.list_garments()
    recent = db.recent_outfit_sets(limit=3)

    band = rules.temp_band(args.temp)
    print(f"\n场合：{OCCASION_LABELS[args.occasion]}    温度：{args.temp:.0f}℃（{rules.BAND_LABELS[band]}）")
    print(f"衣橱：{len(wardrobe)} 件可用    档案：{profiler.describe(profiler.analyse(profile))}")
    print(rules.temperature_advice(band, args.temp))

    plans, pool = build_plans(
        wardrobe,
        occasion=args.occasion,
        temp_c=args.temp,
        profile=profile,
        recent_outfit_ids=recent,
    )

    if not plans:
        print(f"\n凑不出方案。{pool.explain()}")
        if pool.dropped:
            print("被筛掉的原因：" + "，".join(f"{k} {v} 件" for k, v in pool.dropped.items()))
        return 1

    for index, plan in enumerate(plans, start=1):
        print(f"\n—— 方案 {index} · {plan.label}（评分 {plan.score}）——")
        for garment in plan.items:
            label = CATEGORY_LABELS.get(garment.category, garment.category)
            print(f"  [{label}] {garment.name}  {garment.color_primary}·厚薄{garment.warmth}·正式度{garment.formality}")
        print(f"  {plan.rationale}")

    if len(plans) < 3:
        print(f"\n注意：衣橱里只凑得出 {len(plans)} 套不重复的组合，补几件单品会更好选。")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
