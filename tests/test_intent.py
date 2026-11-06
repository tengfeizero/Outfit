"""语言入口的测试：关键词兜底要稳，模型精修要能降级。"""

from __future__ import annotations

import pytest

from outfit import intent


@pytest.mark.parametrize(
    "text,expected",
    [
        ("明天上午面试", "interview"),
        ("下午二面", None),  # "二面"不在词表里，宁可交给模型
        ("和客户开会", "work"),
        ("今晚约会", "date"),
        ("下午骑车去郊区", "sport"),
        ("在家躺一天", "home"),
        ("随便穿穿", None),
        ("", None),
    ],
)
def test_guess_occasion(text, expected):
    occasion, _ = intent.guess_occasion(text)
    assert occasion == expected


def test_keyword_prefers_specific_word():
    _, matched = intent.guess_occasion("上午面试，下午去公司开会")
    assert matched == "面试", "同时出现两个词时，应该先命中最具体的那个"


def test_interpret_falls_back_to_keywords_without_model():
    reading = intent.interpret("下午骑车去郊区")
    assert reading.occasion == "sport"
    assert reading.source == "keyword"
    assert "骑车" in reading.explanation


def test_interpret_uses_model_when_available():
    class FakeLLM:
        def parse_intent(self, text):
            return {"occasion": "interview", "reason": "提到终面"}

    reading = intent.interpret("下午二面", llm=FakeLLM())
    assert reading.occasion == "interview"
    assert reading.source == "llm"
    assert "终面" in reading.explanation


def test_interpret_survives_model_failure():
    class BrokenLLM:
        def parse_intent(self, text):
            raise RuntimeError("配额没了")

    reading = intent.interpret("下午骑车", llm=BrokenLLM())
    assert reading.occasion == "sport"
    assert reading.source == "keyword"


def test_interpret_ignores_model_custom_verdict():
    class VagueLLM:
        def parse_intent(self, text):
            return {"occasion": "custom", "reason": "说不准"}

    reading = intent.interpret("随便", llm=VagueLLM())
    assert reading.occasion == "work"  # 退回界面上的选择
    assert reading.source == "default"


def test_empty_text_uses_fallback():
    reading = intent.interpret("   ", fallback="date")
    assert reading.occasion == "date"
    assert reading.source == "default"


def test_unknown_reading_does_not_crash():
    reading = intent.interpret("量子力学")
    assert reading.occasion == "work"
    assert reading.explanation
