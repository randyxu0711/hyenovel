"""python -m den [--port N]:綁 127.0.0.1 起 den,印出 token 檔位置。"""
import argparse
import logging

import uvicorn

from den.app import create_app
from den.config import HOST, PORT
from marrow import db


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m den")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    d = db.data_dir()
    print(f"den token 檔:{d / 'den.token'}(請求帶 Authorization: Bearer <內容>)", flush=True)
    uvicorn.run(create_app(db.database_url(), d, port=args.port), host=HOST, port=args.port,
                timeout_graceful_shutdown=3)   # 開著的 SSE 不能讓 Ctrl+C 等到 job 跑完


if __name__ == "__main__":
    main()
