#!/usr/bin/env python3
"""假 claude:模式讀自同目錄的 fake_mode(工人 env 是白名單,讀不到測試設的變數)。"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

here = Path(__file__).resolve()
mode = here.with_name("fake_mode").read_text().strip()

if mode == "ok":
    stdin = sys.stdin.read()
    here.with_name("seen.json").write_text(json.dumps(
        {"argv": sys.argv, "env": dict(os.environ), "cwd": os.getcwd(), "stdin": stdin}))
    print(here.with_name("claude_ok.json").read_text())
elif mode == "sleep":
    child = subprocess.Popen(["sleep", "60"])
    here.with_name("child.pid").write_text(str(child.pid))
    time.sleep(60)
elif mode.startswith("stream"):
    sys.stdin.read()
    lines = here.with_name("claude_stream_ok.jsonl").read_text().splitlines()
    deltas = [ln for ln in lines if '"text_delta"' in ln]

    def emit(ln):
        print(ln, flush=True)

    if mode == "stream-cut":
        for ln in deltas[:2]:
            emit(ln)
        sys.exit(1)
    if mode == "stream-slow":
        emit(deltas[0])
        child = subprocess.Popen(["sleep", "60"])
        here.with_name("child.pid").write_text(str(child.pid))
        time.sleep(60)
    for ln in lines:
        if mode == "stream-429" and json.loads(ln).get("type") == "result":
            obj = json.loads(ln)
            obj.update(is_error=True, api_error_status=429)
            ln = json.dumps(obj)
        emit(ln)
else:  # garbage
    print("not json")
    sys.exit(1)
