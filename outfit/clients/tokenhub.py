"""腾讯云 TokenHub（混元）适配器：打标和出图都走这里。

一个供应商一个文件——以后要换阿里云百炼或火山，新写一个同接口的文件即可，
调用方不用动。这是设计文档 5.2 里"适配器隔离"那条的落地。

两个接口：
  /v1/chat/completions                       视觉理解（认衣服）
  /v1/wand/hunyuan-image/v35-generation      多图参考出图（试穿）
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_BASE = "https://tokenhub.tencentmaas.com"
VISION_MODEL = "hy-vision-2.0-instruct"
IMAGE_MODEL = "hy-image-v3.5-preview"

TAG_PROMPT = """你是服装标注员。看这张照片里的单件衣服（不是模特，是衣服本身），输出一个 JSON 对象，不要任何解释、不要代码块：

{
  "category": "top|bottom|outerwear|dress|shoes|bag|accessory",
  "color": "中文色名，两个字以内，如 藏蓝、米、黑",
  "warmth": 1到5的整数（1 最薄如短袖，5 最厚如大衣）,
  "formality": 1到5的整数（1 睡衣，3 日常上班，5 正式礼服）,
  "material": "材质，如 棉、羊毛、牛仔、皮革，看不出来写 未知",
  "confidence": 0到1的小数（你对这次判断有多确定）
}"""

VALID_CATEGORIES = {
    "top",
    "bottom",
    "outerwear",
    "dress",
    "shoes",
    "bag",
    "accessory",
}

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class TokenHubError(RuntimeError):
    """调用失败。调用方要么降级、要么把这句话原样给用户看。"""


@dataclass
class Tags:
    category: str
    color_name: str
    warmth: int
    formality: int
    material: str | None
    confidence: float

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "color_name": self.color_name,
            "warmth": self.warmth,
            "formality": self.formality,
            "material": self.material,
            "confidence": self.confidence,
        }


def _data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"


def _clamp(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def parse_tags(raw: str) -> Tags:
    """从模型输出里抠出 JSON。模型偶尔会加代码块或解释，所以不全信它。"""
    match = _JSON_BLOCK.search(raw or "")
    if not match:
        raise TokenHubError("模型没有返回可解析的内容")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as error:
        raise TokenHubError(f"模型返回的不是合法 JSON：{error}") from error

    category = str(payload.get("category", "")).strip().lower()
    if category not in VALID_CATEGORIES:
        raise TokenHubError(f"模型给了一个不存在的品类：{category!r}")

    color = str(payload.get("color", "")).strip() or "未标注"
    material = payload.get("material")
    if material in ("未知", "", "null", None):
        material = None

    try:
        confidence = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    return Tags(
        category=category,
        color_name=color[:4],
        warmth=_clamp(payload.get("warmth"), 1, 5, 3),
        formality=_clamp(payload.get("formality"), 1, 5, 3),
        material=str(material)[:20] if material else None,
        confidence=max(0.0, min(1.0, confidence)),
    )


def collect_image_urls(payload: Any) -> list[str]:
    """出图接口把结果塞在 assembled_history 的某个 image_url 里，位置不固定，全树捞一遍。"""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            image = node.get("image_url")
            if isinstance(image, dict) and image.get("url"):
                found.append(str(image["url"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def build_try_on_messages(
    body_image: bytes,
    garment_images: list[bytes],
    *,
    description: str,
    keep_background: bool = True,
) -> list[dict]:
    """拼一条多图编辑指令。图 1 是身体，后面依次是衣服。"""
    pieces: list[dict] = [
        {"type": "image_url", "image_url": {"url": _data_url(body_image)}},
    ]
    for image in garment_images:
        pieces.append({"type": "image_url", "image_url": {"url": _data_url(image)}})

    task = (
        f"把后面这些参考图里的衣服，穿到 @Image1 这个人的身上。要穿的是：{description}。"
        "严格保持这个人的脸、发型、体型和站姿不变，不要美化、不要换脸、不要改变身高比例。"
    )
    if keep_background:
        task += "背景保持原样，光线跟着原图。"
    task += "输出一张完整的全身照。"
    pieces.append({"type": "text", "text": task})
    return [{"role": "user", "content": pieces}]


class TokenHub:
    def __init__(
        self,
        api_key: str | None,
        base: str = DEFAULT_BASE,
        *,
        client: httpx.Client | None = None,
        vision_model: str = VISION_MODEL,
        image_model: str = IMAGE_MODEL,
        timeout: float = 180.0,
    ) -> None:
        self.api_key = api_key
        self.base = base.rstrip("/")
        self.vision_model = vision_model
        self.image_model = image_model
        self._client = client
        self._timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _http(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=self._timeout)

    def _post(self, path: str, payload: dict) -> dict:
        if not self.api_key:
            raise TokenHubError("没有配置 TokenHub 的 API KEY")
        http = self._http()
        try:
            response = http.post(
                f"{self.base}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as error:
            raise TokenHubError(f"连不上 TokenHub：{error}") from error
        finally:
            if self._client is None:
                http.close()

        if response.status_code == 402:
            raise TokenHubError("API Key 配额已用完，去控制台开通后付费或充值")
        if response.status_code != 200:
            detail = response.text[:200]
            raise TokenHubError(f"TokenHub 返回 {response.status_code}：{detail}")
        try:
            return response.json()
        except ValueError as error:
            raise TokenHubError("TokenHub 返回的不是 JSON") from error

    # ------------------------------------------------------------ 打标

    def tag_garment(self, image_bytes: bytes, mime: str = "image/jpeg") -> Tags:
        payload = {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": _data_url(image_bytes, mime)}},
                        {"type": "text", "text": TAG_PROMPT},
                    ],
                }
            ],
            "max_tokens": 300,
        }
        data = self._post("/v1/chat/completions", payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise TokenHubError("返回里没有可用的内容") from error
        return parse_tags(content)

    # ------------------------------------------------------------ 出图

    def try_on(
        self,
        body_image: bytes,
        garment_images: list[bytes],
        *,
        description: str = "",
        size: str = "1024x1536",
    ) -> bytes:
        if not body_image:
            raise TokenHubError("没有身体照片，出不了试穿图")
        if not garment_images:
            raise TokenHubError("没有可用的衣服图")
        # 参考图上限 5 张：1 张身体 + 4 件衣服
        references = garment_images[:4]
        payload = {
            "model": self.image_model,
            "messages": build_try_on_messages(body_image, references, description=description),
            "size": size,
            "resize_max_pixels": 1048576,
        }
        data = self._post("/v1/wand/hunyuan-image/v35-generation", payload)
        urls = collect_image_urls(data)
        if not urls:
            raise TokenHubError("出图接口没有返回图片")

        http = self._http()
        try:
            image = http.get(urls[-1], timeout=60)
        except httpx.HTTPError as error:
            raise TokenHubError(f"下载生成结果失败：{error}") from error
        finally:
            if self._client is None:
                http.close()

        if image.status_code != 200 or not image.content:
            raise TokenHubError("生成结果的下载链接打不开")
        return image.content
