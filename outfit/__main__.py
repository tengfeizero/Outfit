"""启动入口：起服务、打印局域网地址和二维码。

    python -m outfit
"""

from __future__ import annotations

import socket
import sys

import uvicorn

from .config import load
from .web.api import create_app


def lan_ip() -> str:
    """取本机在局域网里的地址。取不到就退回回环地址。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _print_banner(url: str) -> None:
    import qrcode

    port = url.rsplit(":", 1)[-1]
    print()
    print("  本地穿搭助手已启动")
    print(f"  电脑上打开：   http://127.0.0.1:{port}")
    print(f"  手机上打开：   {url}")
    print("  （手机要和电脑连同一个 Wi-Fi。第一次启动 Windows 会问防火墙，")
    print("    勾上「专用网络」再点允许，否则手机连不进来。）")
    print()
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    print()
    print("  按 Ctrl+C 停止")
    print()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = load()
    app = create_app(settings)
    url = f"http://{lan_ip()}:{settings.port}"
    _print_banner(url)

    if not settings.has_image_key:
        print("  提示：没配图片 API 密钥，当前是离线模式——搭配方案照常可用，出图不可用。")
        print("  要出图，把密钥写进项目根目录的 .env（见 .env.example）。\n")

    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
