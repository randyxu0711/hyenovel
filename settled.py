#!/usr/bin/env python3
"""自動收束的水位與交代:stories/<slug>/settled.jsonl。

一局討論只煉一次。判斷「煉過了嗎」**不能只看 conclusions.jsonl** —— 煉出零條的局
(LLM 回 [] 或草稿全被閘門擋)在那裡查不到自己,於是每輪掃描都重煉一次,無限花錢。
反過來只看 settled.jsonl 也不夠:結論已落地但這裡寫入失敗,重煉會產生重複結論。
**故兩個來源互補,任一有記錄就不再煉** —— 各自補上對方的盲點。

這個檔同時是自動路徑唯一的交代:鈕拿掉之後,失敗沒有 UI 可回報,只剩這裡跟 log。

分工同 conclusions.py:本模組是確定性層(純判斷 + append),不認識 SDK,也不認識
server/。「哪些 session 還活著」與「逐字」都由呼叫端(server/settle.py)餵進來。
"""
import json
import logging
import time
from pathlib import Path

import conclusions

ROOT = Path(__file__).resolve().parent
STORIES = ROOT / "stories"

# 同一局最多嘗試幾次。滿了就放棄 —— 沒有上限的重試是一個沒有出口的花錢迴圈。
MAX_ATTEMPTS = 3

log = logging.getLogger("hyenovel")


def _path(slug):
    return STORIES / slug / "settled.jsonl"


def load(slug):
    """讀該篇所有收束記錄;檔不存在回 [];壞行跳過(一行壞不讓整份讀不了)。
    讀取 I/O 失敗也吞掉回 [] —— 照 conclusions.load 的契約。"""
    p = _path(slug)
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        log.warning(f"event=settled-load-fail slug={slug} err={type(e).__name__}")
        return []
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def record(slug, session, ok, written, errors):
    """append 一列。目錄不存在就跳過;I/O 失敗吞掉並記 log。

    吞掉的理由同 transcript.append:記錄失敗不該讓背景 worker 掛掉。代價是這一局會被
    重煉 —— 而那正是 pending() 要同時看 conclusions 的原因(§雙來源)。
    """
    if not (STORIES / slug).is_dir():
        return
    line = json.dumps({
        "session": session,
        "ts": round(time.time(), 3),
        "ok": bool(ok),
        "written": written,
        "errors": list(errors),
    }, ensure_ascii=False)
    try:
        with _path(slug).open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        log.warning(f"event=settled-record-fail slug={slug} session={session} "
                    f"err={type(e).__name__}")


def _distilled(slug):
    """conclusions.jsonl 裡已經有結論的 session id。"""
    out = set()
    for r in conclusions.load(slug):
        sid = (r.get("provenance") or {}).get("session")
        if isinstance(sid, str):
            out.add(sid)
    return out


def pending(slug, rows, live):
    """該篇「已結束且還沒收束」的 session id,依逐字裡首次出現的順序(純函式)。

    rows = transcript.load(slug);live = 還活著的 session id(呼叫端從 registry 給)。
    依賴倒過來傳,是為了讓本模組不必 import server/ —— 同 conclusions.py 的立場。

    四道排除,任一成立就不煉:
      ① 還活著        —— 它還可能長出新輪次,現在煉會得到半局(而且之後沒有第二次機會)
      ② 已有結論      —— conclusions 裡查得到
      ③ 已成功收束    —— settled 裡有 ok:true(含 written:0:閘門跑過了,那是合法結果)
      ④ 試滿 MAX_ATTEMPTS
    另:沒有 analysis.json 的故事整篇跳過 —— refs 閘門沒有基準,煉了也一定過不了。
    """
    if not (STORIES / slug / "analysis.json").exists():
        return []
    done = _distilled(slug)
    attempts, succeeded = {}, set()
    for r in load(slug):
        sid = r.get("session")
        if not isinstance(sid, str):
            continue
        attempts[sid] = attempts.get(sid, 0) + 1
        if r.get("ok"):
            succeeded.add(sid)
    out = []
    for r in rows:
        sid = r.get("session")
        if not isinstance(sid, str) or sid in out:
            continue
        if sid in live or sid in done or sid in succeeded:
            continue
        if attempts.get(sid, 0) >= MAX_ATTEMPTS:
            continue
        out.append(sid)
    return out
