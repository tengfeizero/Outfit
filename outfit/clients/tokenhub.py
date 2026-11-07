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
TEXT_MODEL = "hy4"

INTENT_PROMPT = """把用户这句话里的场合归类。只输出 JSON，不要解释：
{"occasion":"interview|work|date|sport|home|custom","reason":"十个字以内"}

面试、面谈、答辩 → interview
上班、开会、见客户、出差 → work
约会、相亲、看电影 → date
运动、健身、跑步、骑车、爬山 → sport
在家、休息、宅 → home

一句话里出现多个场合时，选最正式的那个，优先级：
interview > work > date > sport > home。
例如"上午面试，下午骑车"是同一天，但穿什么由面试决定 → interview。
只有完全没有场合信息时才回答 custom。"""

TAG_PROMPT = """你是服装标注员。看这张照片里的单件衣服（不是模特，是衣服本身），输出一个 JSON 对象，不要任何解释、不要代码块：

{
  "category": "top|bottom|outerwear|dress|shoes|bag|accessory",
  "color": "中文色名，两个字以内，如 藏蓝、米、黑",
  "warmth": 1到5的整数（1 最薄如短袖，5 最厚如大衣）,
  "formality": 1到5的整数（1 睡衣，3 日常上班，5 正式礼服）,
  "material": "材质，如 棉、羊毛、牛仔、皮革，看不出来写 未知",
  "confidence": 0到1的小数（你对这次判断有多确定）
}"""

JUDGE_PROMPT = """图1是原始照片，图2是穿上新衣服后的生成图。请严格检查：

1. 脸和发型是不是同一个人（不是"像"，是同一个）；
2. 身材比例、身高、站姿有没有被改动；
3. 要求穿上的衣服：品类对不对、颜色对不对、有没有变成别的衣服。

只输出 JSON，不要解释：
{"same_person": true/false, "body_intact": true/false, "garment_ok": true/false, "issue": "一句话说明问题，没问题写 无"}"""

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


def _repair_quotes(text: str) -> str:
    """中文模型常把引号写成全角，JSON 直接非法。这是最常见的坏法，先修它。"""
    for source, target in (
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\uff02", '"'),
    ):
        text = text.replace(source, target)
    return text


def extract_json(text: str) -> dict:
    """从模型输出里取出一个合法 JSON 对象。

    不用正则：`\\{.*\\}` 是贪婪的，模型吐两个对象或后面跟一段解释，
    就会粘成一段非法 JSON——实测踩过这个坑。这里按括号配对逐个试。
    """
    if not text or not text.strip():
        raise TokenHubError("模型没有返回内容")

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    for candidate_text in (cleaned, _repair_quotes(cleaned)):
        try:
            parsed = json.loads(candidate_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    text = _repair_quotes(text)

    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    candidate = json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    start = -1
                    continue
                if isinstance(candidate, dict):
                    return candidate
                start = -1

    raise TokenHubError(f"模型返回的不是合法 JSON：{text.strip()[:80]!r}")


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


def sniff_mime(data: bytes) -> str:
    """按文件头判断图片类型。写死 image/jpeg 会把 PNG 冒充成 JPEG，接口会拒。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/jpeg"


def _data_url(image_bytes: bytes, mime: str | None = None) -> str:
    kind = mime or sniff_mime(image_bytes)
    return f"data:{kind};base64,{base64.b64encode(image_bytes).decode()}"


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
        payload = extract_json(raw or "")
    except TokenHubError as error:
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


@dataclass
class Judgement:
    ok: bool
    note: str
    same_person: bool = True
    body_intact: bool = True
    garment_ok: bool = True


def parse_judgement(raw: str) -> Judgement:
    match = _JSON_BLOCK.search(raw or "")
    if not match:
        return Judgement(ok=False, note="校验没给出结论")
    try:
        payload = extract_json(raw or "")
    except TokenHubError:
        return Judgement(ok=False, note="校验结果不是合法 JSON")

    same_person = bool(payload.get("same_person", False))
    body_intact = bool(payload.get("body_intact", False))
    garment_ok = bool(payload.get("garment_ok", False))
    issue = str(payload.get("issue", "") or "").strip()
    ok = same_person and body_intact and garment_ok
    if ok:
        note = "校验通过"
    else:
        note = issue if issue and issue != "无" else "校验未通过"
    return Judgement(
        ok=ok, note=note, same_person=same_person, body_intact=body_intact, garment_ok=garment_ok
    )


class TokenHub:
    def __init__(
        self,
        api_key: str | None,
        base: str = DEFAULT_BASE,
        *,
        client: httpx.Client | None = None,
        vision_model: str = VISION_MODEL,
        image_model: str = IMAGE_MODEL,
        text_model: str = TEXT_MODEL,
        timeout: float = 180.0,
    ) -> None:
        self.api_key = api_key
        self.base = base.rstrip("/")
        self.vision_model = vision_model
        self.image_model = image_model
        self.text_model = text_model
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

    # ------------------------------------------------------------ 编排

    def decide_action(self, system: str, transcript: str) -> dict:
        """调度器的脑子：看完进展，决定下一步调什么工具。

        思维模型偶尔会把 token 花在思考上、正文是空的，所以给足预算，
        并且给一次重说的机会——调度失败一次就整单报废，代价太大。
        """
        last_error: Exception | None = None
        bad_answer = ""
        for attempt in range(2):
            prompt = transcript
            if attempt > 0:
                prompt = (
                    transcript
                    + f"\n\n你上一条回答是：{bad_answer}\n那不是合法 JSON。"
                    "请把它转成一个 JSON 动作对象，只输出 JSON。"
                )
            try:
                return self._decide_once(system, prompt)
            except TokenHubError as error:
                last_error = error
                bad_answer = str(error)[:200]
        raise TokenHubError(f"调度器连续两次没给出可解析的动作：{last_error}")

    def _decide_once(self, system: str, transcript: str) -> dict:
        payload = {
            "model": self.text_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": transcript},
            ],
            # 让服务端把格式钉死，比在提示词里求它"只输出 JSON"可靠得多
            "response_format": {"type": "json_object"},
            "max_tokens": 2000,
        }
        data = self._post("/v1/chat/completions", payload)
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise TokenHubError("调度器没有返回内容") from error
        content = message.get("content") or message.get("reasoning_content") or ""
        return extract_json(content)

    # ------------------------------------------------------------ 意图

    def parse_intent(self, text: str) -> dict:
        """一句话 → 场合。用的是便宜的文本模型，一次几分钱。"""
        payload = {
            "model": self.text_model,
            "messages": [
                {
                    "role": "user",
                    "content": f"{INTENT_PROMPT}\n\n用户：{text}",
                }
            ],
            # hy4 是思维模型：token 给少了，思考过程会把额度吃光，正文就是空的
            "response_format": {"type": "json_object"},
            "max_tokens": 800,
        }
        data = self._post("/v1/chat/completions", payload)
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise TokenHubError("意图识别没有返回内容") from error

        # 正文为空时退回思考内容——它末尾通常也带着那个 JSON
        content = message.get("content") or message.get("reasoning_content") or ""
        return extract_json(content)

    # ------------------------------------------------------------ 打标

    def tag_garment(self, image_bytes: bytes, mime: str | None = None) -> Tags:
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

    # ------------------------------------------------------------ 校验

    def judge_try_on(
        self, body_image: bytes, result_image: bytes, description: str = ""
    ) -> Judgement:
        """再看一眼：人还是不是那个人，衣服还是不是那件衣服。

        多花一次便宜调用，换掉"生成了一张好看但不像你"的图——那种图对用户
        比没有图更糟，因为它会让人不信任整个系统。
        """
        prompt = JUDGE_PROMPT
        if description:
            prompt += f"\n\n要求穿上的衣服是：{description}"
        payload = {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": _data_url(body_image)}},
                        {"type": "image_url", "image_url": {"url": _data_url(result_image)}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": 300,
        }
        data = self._post("/v1/chat/completions", payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise TokenHubError("校验没有返回内容") from error
        return parse_judgement(content)
