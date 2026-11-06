"""agent 能用的工具。

每个工具是一个纯函数：吃 (state, args)，吐一段 observation。
state 是这一次运行的共享上下文——天气、候选、方案、出过的图都放里面，
所以工具之间不用互相知道对方的存在，编排器负责串。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .. import candidates, db, intent, rules
from ..clients import weather as weather_client
from ..models import Garment
from ..renderer import render as render_plan
from ..renderer.photo import make_provider
from ..stylist.plan import build_plans

# 每个动作的估价比（人民币），用于预算控制。不是为了精确，是为了能刹车。
COSTS = {
    "get_weather": 0.0,
    "search_wardrobe": 0.0,
    "compose_outfit": 0.01,
    "render_outfit": 0.35,
    "finish": 0.0,
}


@dataclass
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    run: Callable[[dict, dict], dict]

    def call(self, state: dict, args: dict) -> dict:
        return self.run(state, args or {})


_LABEL_TO_KEY = {label: key for key, label in intent.LABELS.items()}


def normalize_occasion(value, fallback: str = "work") -> str:
    """模型经常直接把中文标签填进参数（"面试"），这里统一转成内部键。"""
    raw = str(value or "").strip()
    if raw in intent.OCCASIONS:
        return raw
    if raw in _LABEL_TO_KEY:
        return _LABEL_TO_KEY[raw]
    return fallback


# ---------------------------------------------------------------- 天气


def _get_weather(state: dict, args: dict) -> dict:
    override = state.get("temp_override")
    if override is not None:
        state["temp_c"] = float(override)
        return {"temp_c": float(override), "source": "user", "note": "用户已经说了温度，不用查"}

    latitude = db.get_setting("city_lat")
    longitude = db.get_setting("city_lon")
    if not latitude or not longitude:
        state.setdefault("temp_c", 18.0)
        return {
            "temp_c": 18.0,
            "source": "default",
            "note": "还没设城市，先按 18℃ 算",
        }

    city = weather_client.City(
        name=db.get_setting("city_name") or "",
        latitude=float(latitude),
        longitude=float(longitude),
    )
    try:
        current = weather_client.fetch(city)
    except weather_client.WeatherError as error:
        state.setdefault("temp_c", 18.0)
        return {"temp_c": 18.0, "source": "default", "note": f"天气没取到（{error}），按 18℃ 算"}

    state["temp_c"] = current.effective_c
    return {
        "temp_c": current.effective_c,
        "range": f"{current.temp_min:.0f}–{current.temp_max:.0f}℃",
        "condition": current.condition,
        "rainy": current.is_rainy,
        "source": "weather",
    }


# ---------------------------------------------------------------- 衣橱检索


def _search_wardrobe(state: dict, args: dict) -> dict:
    garments = db.list_garments()
    occasion = normalize_occasion(args.get("occasion") or state.get("occasion"))

    temp_c = float(args.get("temp_c", state.get("temp_c", 18.0) or 18.0))
    band = rules.temp_band(temp_c)
    lo_w, hi_w = rules.allowed_warmth(band)
    lo_f, hi_f = rules.formality_range(occasion)

    if args.get("min_formality") is not None:
        lo_f = max(1, int(args["min_formality"]))
    if args.get("max_formality") is not None:
        hi_f = min(5, int(args["max_formality"]))

    pool = candidates.build(
        garments,
        occasion=occasion,
        temp_c=temp_c,
        formality=(lo_f, hi_f),
    )
    items = [
        {"id": g.id, "name": g.name, "category": g.category, "warmth": g.warmth}
        for g in pool.all_items()[:20]
    ]
    state["candidate_count"] = pool.count()
    return {
        "count": pool.count(),
        "usable": pool.is_usable(),
        "items": items,
        "reason": pool.explain(),
        "warmth_range": [lo_w, hi_w],
        "formality_range": [lo_f, hi_f],
    }


# ---------------------------------------------------------------- 组套


def _compose_outfit(state: dict, args: dict) -> dict:
    occasion = normalize_occasion(args.get("occasion") or state.get("occasion"))
    temp_c = float(args.get("temp_c", state.get("temp_c", 18.0) or 18.0))

    garments = db.list_garments()
    profile = db.get_profile()
    plans, pool = build_plans(
        garments,
        occasion=occasion,
        temp_c=temp_c,
        profile=profile,
        recent_outfit_ids=db.recent_outfit_sets(limit=3),
    )

    state["occasion"] = occasion
    state["temp_c"] = temp_c
    state["plans"] = plans
    state["pool"] = pool

    return {
        "plans": [
            {
                "index": index + 1,
                "label": plan.label,
                "items": [g.name for g in plan.items],
                "rationale": plan.rationale,
            }
            for index, plan in enumerate(plans)
        ],
        "relaxed": (
            f"正式度放宽到 {pool.formality[0]}–{pool.formality[1]}"
            if pool.original_formality
            else ""
        ),
        "reason": pool.explain(),
    }


# ---------------------------------------------------------------- 出图


def _render_outfit(state: dict, args: dict) -> dict:
    plans = state.get("plans") or []
    if not plans:
        return {"error": "还没有方案，先调用 compose_outfit"}

    index = int(args.get("plan_index", 1)) - 1
    if not 0 <= index < len(plans):
        return {"error": f"方案序号超出范围（1–{len(plans)}）"}

    hub = state.get("hub")
    data_dir: Path = state["data_dir"]
    render_dir: Path = state["render_dir"]

    provider = None
    if hub is not None and getattr(hub, "available", False):
        provider = make_provider(hub, data_dir, db.get_profile())

    plan = plans[index]
    result = render_plan(
        plan.items,
        render_dir,
        title=f"{intent.LABELS.get(state.get('occasion', ''), '')} · {plan.label}",
        subtitle=f"{float(state.get('temp_c', 18)):.0f}℃",
        rationale=plan.rationale,
        provider=provider,
    )
    url = f"/media/renders/{result.path.name}" if result.path else None
    state.setdefault("renders", {})[index] = {"mode": result.mode, "url": url, "note": result.note}
    return {"mode": result.mode, "url": url, "note": result.note, "plan_index": index + 1}


def _finish(state: dict, args: dict) -> dict:
    return {"summary": str(args.get("summary", "完成"))}


TOOLS: dict[str, Tool] = {
    "get_weather": Tool(
        name="get_weather",
        description="查今天出门时的温度。不知道穿多厚时先调它。",
        schema={"type": "object", "properties": {}},
        run=_get_weather,
    ),
    "search_wardrobe": Tool(
        name="search_wardrobe",
        description="按场合和温度筛出可穿的单品，看看够不够凑一套。",
        schema={
            "type": "object",
            "properties": {
                "occasion": {"type": "string"},
                "temp_c": {"type": "number"},
                "min_formality": {"type": "integer"},
                "max_formality": {"type": "integer"},
            },
        },
        run=_search_wardrobe,
    ),
    "compose_outfit": Tool(
        name="compose_outfit",
        description="生成三套方案。需要先知道场合和温度。",
        schema={
            "type": "object",
            "properties": {
                "occasion": {"type": "string"},
                "temp_c": {"type": "number"},
            },
        },
        run=_compose_outfit,
    ),
    "render_outfit": Tool(
        name="render_outfit",
        description="把某一套方案画成试穿图。会花钱，也会校验，可能失败。",
        schema={
            "type": "object",
            "properties": {"plan_index": {"type": "integer"}},
        },
        run=_render_outfit,
    ),
    "finish": Tool(
        name="finish",
        description="结束，给用户一句话总结。",
        schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
        },
        run=_finish,
    ),
}


def tool_menu() -> str:
    lines = []
    for tool in TOOLS.values():
        lines.append(f"- {tool.name}{_args_hint(tool.schema)}：{tool.description}")
    return "\n".join(lines)


def _args_hint(schema: dict) -> str:
    properties = list((schema.get("properties") or {}).keys())
    return "{" + ", ".join(properties) + "}" if properties else "{}"


def describe_garments(items: list[Garment]) -> list[dict]:
    return [{"id": g.id, "name": g.name, "category": g.category} for g in items]
