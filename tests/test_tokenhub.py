"""TokenHub 适配器的测试。全部用假的 HTTP 传输层，不联网、不花钱。"""

from __future__ import annotations

import json

import httpx
import pytest

from outfit.clients import tokenhub


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


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
