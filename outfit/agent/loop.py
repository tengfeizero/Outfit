"""编排循环：让模型自己决定下一步调什么。

这是这个项目里唯一"像 agent"的部分，所以它必须：
- 有明确的停止条件（步数、预算、finish）
- 每一步都留痕（谁决定的、调了什么、结果、花了多少）
- 模型不可用时退化成确定性流程，而不是罢工
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import intent
from ..stylist.plan import Plan
from .tools import COSTS, TOOLS, tool_menu

MAX_STEPS = 6
MAX_COST = 1.2
MAX_IMAGES = 2

SYSTEM_PROMPT = """你是穿搭助手的调度器。每一步只输出一个 JSON 动作，不要解释、不要代码块：
{{"thought":"一句话说明为什么这么做","action":"工具名","args":{{...}}}}

可用工具：
{tools}

规则：
1. 不知道穿多厚，先调 get_weather。
2. 出图（render_outfit）之前必须先 compose_outfit 拿到方案。
3. 最多出 {images} 张图，超了预算就停。
4. 得到方案后调用 finish 结束，summary 用一句话告诉用户结论。
5. 不要重复调用同一个工具拿同样的结果。"""


@dataclass
class Step:
    index: int
    action: str
    args: dict
    observation: dict
    thought: str = ""
    cost: float = 0.0
    elapsed: float = 0.0

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "action": self.action,
            "args": self.args,
            "thought": self.thought,
            "observation": self.observation,
            "cost": round(self.cost, 3),
            "elapsed": round(self.elapsed, 2),
        }


@dataclass
class RunResult:
    status: str
    steps: list[Step]
    plans: list[Plan] = field(default_factory=list)
    cost: float = 0.0
    summary: str = ""
    source: str = "model"  # model / fallback
    occasion: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "source": self.source,
            "occasion": self.occasion,
            "cost": round(self.cost, 3),
            "summary": self.summary,
            "steps": [step.to_dict() for step in self.steps],
        }


class _Runner:
    def __init__(self, state: dict, hub, max_steps: int, budget: float) -> None:
        self.state = state
        self.hub = hub
        self.max_steps = max_steps
        self.budget = budget
        self.steps: list[Step] = []
        self.cost = 0.0
        self.images = 0

    # ------------------------------------------------------------ 执行一步

    def execute(self, action: str, args: dict, thought: str = "") -> dict:
        started = time.time()
        tool = TOOLS.get(action)
        if tool is None:
            observation = {"error": f"没有这个工具：{action}"}
        else:
            try:
                observation = tool.call(self.state, args)
            except Exception as error:  # noqa: BLE001 — 工具炸了不能把整次运行带走
                observation = {"error": f"{type(error).__name__}: {error}"}

        cost = COSTS.get(action, 0.0)
        if action == "render_outfit" and observation.get("mode") == "photo":
            self.images += 1
        elif action == "render_outfit" and observation.get("error"):
            cost = 0.0

        self.cost += cost
        self.steps.append(
            Step(
                index=len(self.steps) + 1,
                action=action,
                args=args,
                observation=observation,
                thought=thought,
                cost=cost if action != "render_outfit" or observation.get("mode") == "photo" else 0.0,
                elapsed=time.time() - started,
            )
        )
        return observation

    def over_budget(self) -> bool:
        return self.cost >= self.budget or self.images >= MAX_IMAGES

    # ------------------------------------------------------------ 两种模式

    def with_model(self, text: str) -> RunResult:
        invalid = 0
        for _ in range(self.max_steps):
            transcript = self._transcript(text)
            try:
                decision = self.hub.decide_action(self._system(), transcript)
            except Exception as error:  # noqa: BLE001
                # 调度器失手不等于整单报废：编排器接管，至少把方案交出来
                if not self.state.get("plans"):
                    self.execute("compose_outfit", {}, thought="调度器失手，编排器接管")
                self.execute(
                    "finish",
                    {"summary": f"调度器失手（{error}），已用固定流程兜底"},
                    thought="兜底收尾",
                )
                return self._result("degraded", "model")

            action = str(decision.get("action", "")).strip()
            args = decision.get("args") or {}
            thought = str(decision.get("thought", ""))[:120]
            if not isinstance(args, dict):
                args = {}

            if action not in TOOLS:
                invalid += 1
                self.steps.append(
                    Step(
                        index=len(self.steps) + 1,
                        action=action or "(空)",
                        args=args,
                        observation={"error": f"没有这个工具：{action!r}"},
                        thought=thought,
                    )
                )
                if invalid >= 2:
                    self.execute("finish", {"summary": "它连续给了不存在的工具，先停"})
                    return self._result("failed", "model")
                continue

            observation = self.execute(action, args, thought)

            if action == "finish":
                return self._result("ok" if self.state.get("plans") else "failed", "model")
            if self.over_budget():
                self.execute("finish", {"summary": "预算用完了，先给到这儿"})
                return self._result("budget", "model")
            if observation.get("error"):
                continue

        self.execute("finish", {"summary": "步数用完了"})
        return self._result("budget" if self.state.get("plans") else "failed", "model")

    def without_model(self, text: str) -> RunResult:
        """没有模型时按固定顺序走一遍，轨迹照样记下来。"""
        reading = intent.interpret(text, llm=None, fallback="work")
        self.state["occasion"] = reading.occasion
        self.execute("get_weather", {}, thought="没有模型，按固定顺序先查温度")
        self.execute("search_wardrobe", {}, thought="看看衣橱够不够")
        self.execute("compose_outfit", {}, thought="按规则组三套")
        if self.state.get("plans"):
            self.execute("finish", {"summary": "按固定流程给出了三套方案"}, thought="完成")
            return self._result("ok", "fallback")
        self.execute("finish", {"summary": "衣橱里凑不出方案"}, thought="完成")
        return self._result("failed", "fallback")

    # ------------------------------------------------------------ 辅助

    def _result(self, status: str, source: str) -> RunResult:
        plans = self.state.get("plans") or []
        summary = ""
        for step in reversed(self.steps):
            if step.action == "finish":
                summary = str(step.observation.get("summary", ""))
                break
        return RunResult(
            status=status,
            steps=self.steps,
            plans=plans,
            cost=self.cost,
            summary=summary,
            source=source,
            occasion=self.state.get("occasion"),
        )

    def _system(self) -> str:
        return SYSTEM_PROMPT.format(tools=tool_menu(), images=MAX_IMAGES)

    def _transcript(self, text: str) -> str:
        lines = [f"用户：{text}"]
        if self.steps:
            lines.append("已经做了：")
            for step in self.steps:
                observed = _short(step.observation)
                lines.append(f"{step.index}. {step.action} {step.args} -> {observed}")
        else:
            lines.append("还没开始。")
        lines.append(f"已花费约 {self.cost:.2f} 元，已出图 {self.images} 张。下一步做什么？")
        return "\n".join(lines)


def _short(observation: dict, limit: int = 400) -> str:
    """轨迹太长会把提示词撑爆，只留关键字段。"""
    if "plans" in observation:
        plans = [
            {"index": plan["index"], "label": plan["label"], "items": plan["items"][:4]}
            for plan in observation["plans"]
        ]
        observation = {**observation, "plans": plans}
    if "items" in observation:
        observation = {**observation, "items": observation["items"][:6]}
    text = str(observation)
    return text[:limit] + ("…" if len(text) > limit else "")


def run(
    text: str,
    *,
    hub,
    data_dir: Path,
    render_dir: Path,
    temp_override: float | None = None,
    max_steps: int = MAX_STEPS,
    budget: float = MAX_COST,
) -> RunResult:
    state: dict = {
        "hub": hub,
        "data_dir": data_dir,
        "render_dir": render_dir,
        "text": text,
        "temp_override": temp_override,
    }
    runner = _Runner(state, hub, max_steps, budget)
    if hub is not None and getattr(hub, "available", False):
        return runner.with_model(text)
    return runner.without_model(text)
