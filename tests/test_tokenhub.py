"""TokenHub 适配器的测试。全部用假的 HTTP 传输层，不联网、不花钱。"""

from __future__ import annotations

import json

import httpx
import pytest

from outfit.clients import tokenhub


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------- JSON 提取


def test_extract_json_plain():
    assert tokenhub.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_takes_the_first_of_several():
    """模型有时候会连着吐两个对象，贪婪正则会把它们粘成非法 JSON。"""
    assert tokenhub.extract_json('{"a": 1} 然后 {"b": 2}') == {"a": 1}


def test_extract_json_skips_surrounding_prose():
    raw = '好的，这一步应该收工：{"action": "finish", "args": {"summary": "好了"}} 完成'
    assert tokenhub.extract_json(raw)["action"] == "finish"


def test_extract_json_strips_code_fence():
    assert tokenhub.extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_ignores_braces_inside_strings():
    assert tokenhub.extract_json('{"note": "这里有个 } 括号", "a": 1}')["a"] == 1


def test_extract_json_repairs_fullwidth_quotes():
    """中文模型常输出全角引号，那不是合法 JSON。"""
    raw = "{“action”: “finish”, “args”: {“summary”: “好了”}}"
    assert tokenhub.extract_json(raw)["action"] == "finish"


def test_extract_json_rejects_garbage():
    with pytest.raises(tokenhub.TokenHubError):
        tokenhub.extract_json("完全没有 JSON")


def test_extract_json_rejects_empty():
    with pytest.raises(tokenhub.TokenHubError):
        tokenhub.extract_json("   ")


# ---------------------------------------------------------------- 打标解析


def test_parse_tags_plain_json():
    tags = tokenhub.parse_tags(
        '{"category":"top","color":"藏蓝","warmth":2,"formality":4,"material":"棉","confidence":0.8}'
    )
    assert tags.category == "top"
    assert tags.color_name == "藏蓝"
    assert tags.warmth == 2
    assert tags.formality == 4
    assert tags.confidence == pytest.approx(0.8)


def test_parse_tags_strips_code_fence_and_chatter():
    messy = '好的，结果如下：\n```json\n{"category":"shoes","color":"黑","warmth":2,"formality":3}\n```\n希望有帮助'
    tags = tokenhub.parse_tags(messy)
    assert tags.category == "shoes"
    assert tags.material is None


def test_parse_tags_clamps_out_of_range_numbers():
    tags = tokenhub.parse_tags('{"category":"top","color":"白","warmth":99,"formality":-3}')
    assert tags.warmth == 5
    assert tags.formality == 1


def test_parse_tags_rejects_unknown_category():
    with pytest.raises(tokenhub.TokenHubError):
        tokenhub.parse_tags('{"category":"spaceship","color":"白","warmth":3,"formality":3}')


def test_parse_tags_rejects_garbage():
    with pytest.raises(tokenhub.TokenHubError):
        tokenhub.parse_tags("我不知道这是什么")


def test_tag_garment_posts_image_and_parses():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"category":"outerwear","color":"驼","warmth":5,"formality":4,"confidence":0.9}'
                        }
                    }
                ]
            },
        )

    hub = tokenhub.TokenHub("sk-test", client=_client(handler))
    tags = hub.tag_garment(b"fake-image-bytes")

    assert tags.category == "outerwear"
    assert tags.warmth == 5
    assert seen["url"].endswith("/v1/chat/completions")
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == tokenhub.VISION_MODEL
    content = seen["body"]["messages"][0]["content"]
    assert content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


# ---------------------------------------------------------------- 出图


def test_collect_image_urls_finds_nested_result():
    payload = {
        "assembled_history": [
            {"content": [{"text": "思考"}]},
            {"content": [{"image_url": {"url": "https://example.com/a.png"}}]},
            {"content": [{"image_url": {"url": "https://example.com/b.png?sign=1"}}]},
        ]
    }
    assert tokenhub.collect_image_urls(payload) == [
        "https://example.com/a.png",
        "https://example.com/b.png?sign=1",
    ]


def test_build_try_on_messages_puts_body_first():
    messages = tokenhub.build_try_on_messages(b"body", [b"g1", b"g2"], description="白衬衫和黑西裤")
    content = messages[0]["content"]
    assert content[0]["type"] == "image_url"
    assert len([c for c in content if c["type"] == "image_url"]) == 3
    text = [c for c in content if c["type"] == "text"][0]["text"]
    assert "白衬衫和黑西裤" in text
    assert "@Image1" in text


def test_try_on_rejects_missing_body():
    hub = tokenhub.TokenHub("sk-test", client=_client(lambda r: httpx.Response(200, json={})))
    with pytest.raises(tokenhub.TokenHubError):
        hub.try_on(b"", [b"g1"])


def test_try_on_returns_downloaded_bytes():
    def handler(request: httpx.Request) -> httpx.Response:
        if "v35-generation" in str(request.url):
            return httpx.Response(
                200,
                json={"assembled_history": [
                    {"content": [{"image_url": {"url": "https://img.example/x.png"}}]}
                ]},
            )
        return httpx.Response(200, content=b"PNG-BYTES")

    hub = tokenhub.TokenHub("sk-test", client=_client(handler))
    assert hub.try_on(b"body", [b"g1"], description="白衬衫") == b"PNG-BYTES"


def test_try_on_caps_references_at_four():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "v35-generation" in str(request.url):
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200, json={"assembled_history": [{"content": [{"image_url": {"url": "https://i/x.png"}}]}]}
            )
        return httpx.Response(200, content=b"x")

    hub = tokenhub.TokenHub("sk-test", client=_client(handler))
    hub.try_on(b"body", [b"1", b"2", b"3", b"4", b"5", b"6"])
    parts = captured["body"]["messages"][0]["content"]
    # 1 张身体 + 最多 4 件衣服
    assert len([p for p in parts if p["type"] == "image_url"]) == 5


def test_quota_error_is_explained():
    hub = tokenhub.TokenHub("sk-test", client=_client(lambda r: httpx.Response(402, json={"error": {}})))
    with pytest.raises(tokenhub.TokenHubError) as error:
        hub.tag_garment(b"x")
    assert "配额" in str(error.value)


def test_missing_key_fails_fast():
    hub = tokenhub.TokenHub(None, client=_client(lambda r: httpx.Response(200, json={})))
    assert hub.available is False
    with pytest.raises(tokenhub.TokenHubError):
        hub.tag_garment(b"x")


def test_generate_without_image_in_response_raises():
    hub = tokenhub.TokenHub(
        "sk-test", client=_client(lambda r: httpx.Response(200, json={"assembled_history": []}))
    )
    with pytest.raises(tokenhub.TokenHubError):
        hub.try_on(b"body", [b"g1"])


# ---------------------------------------------------------------- 忠实度校验


def test_judgement_passes_when_all_good():
    verdict = tokenhub.parse_judgement(
        '{"same_person":true,"body_intact":true,"garment_ok":true,"issue":"无"}'
    )
    assert verdict.ok is True
    assert verdict.note == "校验通过"


def test_judgement_fails_when_face_changed():
    verdict = tokenhub.parse_judgement(
        '{"same_person":false,"body_intact":true,"garment_ok":true,"issue":"脸被换了"}'
    )
    assert verdict.ok is False
    assert "脸被换了" in verdict.note
    assert verdict.same_person is False


def test_judgement_is_conservative_on_garbage():
    """解析不出来时不能当通过——宁可退回搭配板。"""
    assert tokenhub.parse_judgement("看起来挺像的").ok is False


def test_judgement_requires_every_check():
    verdict = tokenhub.parse_judgement('{"same_person":true,"body_intact":true,"garment_ok":false}')
    assert verdict.ok is False


def test_judge_try_on_sends_two_images():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"same_person":true,"body_intact":true,"garment_ok":true}'}}]},
        )

    hub = tokenhub.TokenHub("sk-test", client=_client(handler))
    verdict = hub.judge_try_on(b"body", b"result", description="藏蓝外套")
    assert verdict.ok is True
    parts = captured["body"]["messages"][0]["content"]
    assert len([p for p in parts if p["type"] == "image_url"]) == 2
    assert "藏蓝外套" in parts[-1]["text"]
