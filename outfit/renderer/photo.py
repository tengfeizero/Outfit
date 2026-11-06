"""把"人 + 衣服 → 试穿图"这段封装成可复用的 provider。

api 和 agent 循环都要用它，所以从接口层挪出来——同一段逻辑只有一个实现。
"""

from __future__ import annotations

from pathlib import Path

from ..clients.tokenhub import TokenHub
from ..models import BodyProfile, Garment


def make_provider(hub: TokenHub, data_dir: Path, profile: BodyProfile | None):
    """返回一个 provider(items) -> bytes。任何一步不齐都抛错，由 renderer 降级。"""

    def provider(garments: list[Garment]) -> bytes:
        if profile is None or not profile.photo_full:
            raise RuntimeError("还没传身体照片，去「我的」传一张全身照")
        body_path = data_dir / profile.photo_full
        if not body_path.exists():
            raise RuntimeError("身体照片找不到了，重新传一张")

        references: list[bytes] = []
        for garment in garments:
            relative = garment.cutout_path or garment.image_path
            if not relative:
                continue
            path = data_dir / relative
            if path.exists():
                references.append(path.read_bytes())
        if not references:
            raise RuntimeError("这套里的衣服都还没有照片")

        body = body_path.read_bytes()
        description = "、".join(garment.name for garment in garments[:4])

        # 第一次用全部参考图；不过就缩到三件再试一次（参考图越多越容易走形）
        attempts = [references]
        if len(references) > 3:
            attempts.append(references[:3])

        last_note = ""
        for attempt in attempts:
            image = hub.try_on(body, attempt, description=description)
            verdict = hub.judge_try_on(body, image, description)
            if verdict.ok:
                return image
            last_note = verdict.note
        raise RuntimeError(f"生成的图没通过校验：{last_note}")

    return provider
