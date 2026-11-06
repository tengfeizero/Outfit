"""把一句人话翻译成场合参数。

两级：关键词兜底（永远可用、零成本）+ 模型精修（有密钥时更准）。
兜底先跑，所以没网、没额度、模型抽风时功能不会消失——只是笨一点。
"""

from __future__ import annotations

from dataclasses import dataclass

OCCASIONS = ("interview", "work", "date", "sport", "home", "custom")

LABELS = {
    "interview": "面试",
    "work": "上班",
    "date": "约会",
    "sport": "运动",
    "home": "居家",
    "custom": "日常",
}

# 越具体的词排前面：先匹配"面试"再匹配"面"
KEYWORDS: list[tuple[str, str]] = [
    ("interview", "面试"),
    ("interview", "面谈"),
    ("interview", "群面"),
    ("interview", "终面"),
    ("interview", "答辩"),
    ("work", "开会"),
    ("work", "汇报"),
    ("work", "见客户"),
    ("work", "出差"),
    ("work", "上班"),
    ("work", "公司"),
    ("work", "办公室"),
    ("date", "约会"),
    ("date", "相亲"),
    ("date", "看电影"),
    ("sport", "健身"),
    ("sport", "跑步"),
    ("sport", "骑车"),
    ("sport", "爬山"),
    ("sport", "徒步"),
    ("sport", "打球"),
    ("sport", "游泳"),
    ("sport", "运动"),
    ("home", "在家"),
    ("home", "家里"),
    ("home", "宅"),
    ("home", "休息"),
    ("home", "居家"),
]


@dataclass
class Interpretation:
    occasion: str
    source: str  # llm / keyword / default
    explanation: str


def guess_occasion(text: str) -> tuple[str | None, str]:
    """关键词兜底。返回 (场合, 命中的词)。"""
    cleaned = (text or "").strip()
    if not cleaned:
        return None, ""
    for occasion, keyword in KEYWORDS:
        if keyword in cleaned:
            return occasion, keyword
    return None, ""


def describe(occasion: str, source: str, matched: str = "") -> str:
    label = LABELS.get(occasion, occasion)
    if source == "llm":
        return f"理解成：{label}"
    if source == "keyword" and matched:
        return f"理解成：{label}（看到「{matched}」）"
    return f"按默认算作：{label}"


def interpret(text: str, llm=None, fallback: str = "work") -> Interpretation:
    """先问模型，不行退回关键词，再不行用界面上的选择。"""
    cleaned = (text or "").strip()
    if not cleaned:
        return Interpretation(fallback, "default", describe(fallback, "default"))

    if llm is not None:
        try:
            parsed = llm.parse_intent(cleaned)
            occasion = str(parsed.get("occasion", "")).strip().lower()
            if occasion in OCCASIONS and occasion != "custom":
                reason = str(parsed.get("reason", "") or "").strip()
                explanation = describe(occasion, "llm")
                if reason:
                    explanation += f"：{reason}"
                return Interpretation(occasion, "llm", explanation)
        except Exception:  # noqa: BLE001 — 模型不可用就退回关键词，不打扰用户
            pass

    occasion, matched = guess_occasion(cleaned)
    if occasion:
        return Interpretation(occasion, "keyword", describe(occasion, "keyword", matched))

    return Interpretation(fallback, "default", describe(fallback, "default"))
