"""agent 循环的测试：用脚本化的假模型驱动，不联网、不花钱。

这里测的不是"模型聪不聪明"，是"编排器靠不靠谱"：
循环停不停得下来、非法动作会不会炸、没模型会不会罢工、轨迹记不记得全。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from outfit import db
from outfit.agent import loop
from outfit.agent.tools import COSTS, TOOLS
from outfit.seed import demo_wardrobe


@pytest.fixture
def shop(tmp_path):
    db.init_engine(tmp_path / "agent.db")
    for garment in demo_wardrobe():
        db.add_garment(garment)
    return tmp_path


class ScriptedHub:
    """按剧本一步步回动作，模拟模型的选择。"""

    available = True

    def __init__(self, actions: list[dict]):
        self.actions = list(actions)
        self.transcripts: list[str] = []

    def decide_action(self, system: str, transcript: str) -> dict:
        self.transcripts.append(transcript)
        if not self.actions:
            return {"action": "finish", "args": {"summary": "剧本演完了"}}
        return self.actions.pop(0)


def _actions(*items):
    return [{"thought": item[0], "action": item[1], "args": item[2]} for item in items]


# ---------------------------------------------------------------- 工具


def test_every_tool_has_a_description_and_schema():
    for name, tool in TOOLS.items():
        assert tool.description, f"{name} 没有说明，模型不知道怎么用"
        assert tool.schema.get("type") == "object"
        assert name in COSTS, f"{name} 没有成本估算，预算控制会漏掉它"


def test_compose_without_wards_data_is_reported(shop):
    state = {"data_dir": shop, "render_dir": shop}
    observation = TOOLS["render_outfit"].call(state, {})
    assert "error" in observation and "compose_outfit" in observation["error"]


def test_chinese_occasion_label_is_normalised(shop):
    """模型常把"面试"直接填进参数，不能因此掉回 work。"""
    state = {"data_dir": shop, "render_dir": shop}
    observation = TOOLS["compose_outfit"].call(state, {"occasion": "面试", "temp_c": 10})
    assert observation["plans"] or observation["reason"]
    assert state["occasion"] == "interview"


# ---------------------------------------------------------------- 循环


def test_happy_path_records_every_step(shop):
    hub = ScriptedHub(
        _actions(
            ("先看天气", "get_weather", {}),
            ("看看衣橱", "search_wardrobe", {}),
            ("组三套", "compose_outfit", {"occasion": "work", "temp_c": 18}),
            ("收工", "finish", {"summary": "三套都在上面"}),
        )
    )
    result = loop.run("今天上班", hub=hub, data_dir=shop, render_dir=shop)

    assert result.status == "ok"
    assert result.source == "model"
    assert [step.action for step in result.steps] == [
        "get_weather",
        "search_wardrobe",
        "compose_outfit",
        "finish",
    ]
    assert len(result.plans) == 3
    assert result.summary == "三套都在上面"
    assert all(step.thought for step in result.steps)


def test_transcript_grows_so_the_model_can_see_progress(shop):
    hub = ScriptedHub(
        _actions(
            ("看天气", "get_weather", {}),
            ("收工", "finish", {"summary": "好了"}),
        )
    )
    loop.run("今天上班", hub=hub, data_dir=shop, render_dir=shop)
    assert "还没开始" in hub.transcripts[0]
    assert "get_weather" in hub.transcripts[1]


def test_unknown_tool_does_not_crash(shop):
    hub = ScriptedHub(
        _actions(
            ("试试", "make_coffee", {}),
            ("还是组套吧", "compose_outfit", {"occasion": "work", "temp_c": 18}),
            ("收工", "finish", {"summary": "好了"}),
        )
    )
    result = loop.run("今天上班", hub=hub, data_dir=shop, render_dir=shop)
    assert result.steps[0].observation["error"]
    assert result.status == "ok"
    assert len(result.plans) == 3


def test_two_bad_actions_stop_the_run(shop):
    hub = ScriptedHub(_actions(("胡来", "nope", {}), ("再胡来", "nada", {})))
    result = loop.run("今天上班", hub=hub, data_dir=shop, render_dir=shop)
    assert result.status == "failed"


def test_step_limit_is_enforced(shop):
    hub = ScriptedHub([{"action": "search_wardrobe", "args": {}} for _ in range(20)])
    result = loop.run("今天上班", hub=hub, data_dir=shop, render_dir=shop, max_steps=3)
    assert result.status in {"failed", "budget"}
    assert len(result.steps) <= 4  # 3 步 + 收尾的一步


def test_finish_without_plans_is_a_failure(shop):
    hub = ScriptedHub(_actions(("直接收工", "finish", {"summary": "没方案"})))
    result = loop.run("今天上班", hub=hub, data_dir=shop, render_dir=shop)
    assert result.status == "failed"


def test_model_crash_ends_gracefully(shop):
    class BrokenHub:
        available = True

        def decide_action(self, system, transcript):
            raise RuntimeError("接口 500")

    result = loop.run("今天上班", hub=BrokenHub(), data_dir=shop, render_dir=shop)
    assert result.status == "degraded", "调度失手时应该由编排器接管，而不是整单报废"
    assert result.plans, "兜底也要把方案交出来"
    assert "500" in result.summary


# ---------------------------------------------------------------- 无模型降级


def test_without_model_it_still_produces_plans(shop):
    result = loop.run("今天上班", hub=None, data_dir=shop, render_dir=shop)
    assert result.source == "fallback"
    assert result.status == "ok"
    assert len(result.plans) == 3
    assert [step.action for step in result.steps][-1] == "finish"


def test_without_model_it_still_reasons_about_the_sentence(shop):
    result = loop.run("在家躺一天", hub=None, data_dir=shop, render_dir=shop)
    assert result.occasion == "home"


def test_temp_override_skips_the_weather_call(shop):
    hub = ScriptedHub(
        _actions(
            ("看天气", "get_weather", {}),
            ("组套", "compose_outfit", {}),
            ("收工", "finish", {"summary": "好了"}),
        )
    )
    result = loop.run("今天上班", hub=hub, data_dir=shop, render_dir=shop, temp_override=26.0)
    assert result.steps[0].observation["source"] == "user"
    assert result.steps[0].observation["temp_c"] == 26.0


# ---------------------------------------------------------------- 轨迹结构


def test_trace_is_serialisable(shop):
    hub = ScriptedHub(_actions(("组套", "compose_outfit", {"occasion": "work", "temp_c": 18}),))
    result = loop.run("今天上班", hub=hub, data_dir=shop, render_dir=shop)
    payload = result.to_dict()
    assert {"status", "source", "cost", "steps", "summary"} <= set(payload)
    step = payload["steps"][0]
    assert {"index", "action", "args", "thought", "observation", "cost", "elapsed"} <= set(step)
    assert isinstance(step["cost"], float)
