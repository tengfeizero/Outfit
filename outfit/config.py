"""配置：路径、端口、以及"有没有接外部服务"的判断。

没有密钥时进入离线模式——衣橱、组套、档案全部可用，只有出图和打标不可用。
这样用户第一次打开不会看到一堆报错。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    host: str = "0.0.0.0"
    port: int = 8765
    image_provider: str = "qwen"
    llm_provider: str = "qwen"
    daily_render_limit: int = 6
    env: dict[str, str] = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "outfit.db"

    @property
    def photo_dir(self) -> Path:
        return self.data_dir / "photos"

    @property
    def cutout_dir(self) -> Path:
        return self.data_dir / "cutouts"

    @property
    def render_dir(self) -> Path:
        return self.data_dir / "renders"

    @property
    def dist_dir(self) -> Path:
        return self.root / "outfit" / "web" / "static"

    @property
    def has_image_key(self) -> bool:
        return bool(self.env.get("IMAGE_API_KEY"))

    @property
    def has_llm_key(self) -> bool:
        return bool(self.env.get("LLM_API_KEY"))

    def ensure_dirs(self) -> None:
        for directory in (self.data_dir, self.photo_dir, self.cutout_dir, self.render_dir):
            directory.mkdir(parents=True, exist_ok=True)


def load(root: Path | None = None) -> Settings:
    root = root or ROOT
    env = {**_read_env(root / ".env")}
    # 真实环境变量优先于 .env，方便临时覆盖
    for key in ("IMAGE_API_KEY", "LLM_API_KEY", "OUTFIT_HOST", "OUTFIT_PORT"):
        if os.environ.get(key):
            env[key] = os.environ[key]

    settings = Settings(root=root, env=env)
    if env.get("OUTFIT_HOST"):
        settings.host = env["OUTFIT_HOST"]
    if env.get("OUTFIT_PORT"):
        settings.port = int(env["OUTFIT_PORT"])
    settings.ensure_dirs()
    return settings
