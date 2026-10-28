"""python -m den [--port N]:綁 127.0.0.1 起 den,印出 token 檔位置。"""
import argparse
import logging
import socket

import uvicorn

from den.app import create_app
from den.config import HOST, PORT
from marrow import db


def pick_port(preferred: int) -> int:
    """能 bind 就用 preferred,否則讓系統給一個(den.json 會記實際值)。"""
    for p in (preferred, 0):
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # 同 uvicorn:TIME_WAIT 不算佔用
            try:
                s.bind((HOST, p))
            except OSError:
                continue
            return s.getsockname()[1]
    raise OSError("沒有可 bind 的 port")   # pragma: no cover


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m den")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    d = db.data_dir()
    port = pick_port(args.port)
    print(f"den token 檔:{d / 'den.token'}(請求帶 Authorization: Bearer <內容>)", flush=True)
    print(f"den port:{port}", flush=True)
    server = uvicorn.Server(uvicorn.Config(
        create_app(db.database_url(), d, port=port,
                   on_idle=lambda: setattr(server, "should_exit", True)),
        host=HOST, port=port,
        timeout_graceful_shutdown=3))   # 開著的 SSE 不能讓 Ctrl+C 等到 job 跑完
    server.run()


if __name__ == "__main__":
    main()
