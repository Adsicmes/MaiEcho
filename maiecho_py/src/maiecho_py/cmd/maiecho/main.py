from __future__ import annotations

import argparse

import uvicorn

from maiecho_py.app import create_app
from maiecho_py.internal.config.loader import load_app_config


def _parse_bind(value: str) -> tuple[str, int]:
    if value.startswith(":"):
        return "0.0.0.0", int(value[1:])

    if ":" not in value:
        return "0.0.0.0", int(value)

    host, port = value.rsplit(":", 1)
    bind_host = host or "0.0.0.0"
    return bind_host, int(port)


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 MaiEcho Python 服务")
    parser.add_argument("--host", help="覆盖监听地址")
    parser.add_argument("--port", type=int, help="覆盖监听端口")
    args = parser.parse_args()

    config = load_app_config()
    default_host, default_port = _parse_bind(config.server_port)
    host = args.host or default_host
    port = args.port or default_port

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
