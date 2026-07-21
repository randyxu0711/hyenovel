"""討論逐字正本:每輪一行 append 到 stories/<slug>/transcript.jsonl。

與 ledger.py 同層、同 pattern、同契約 —— 差別只在記的是「說了什麼」而非「花了多少」。
兩者刻意分檔:ledger 丟了可以重跑一次拿回數字,transcript 丟了就永遠沒了。
append-only、同步寫(不 await)→ 對其他 asyncio task 原子;per-slug 不同檔,結構上零競爭。

注意:log 只出現 slug/role/例外型別 —— 內容不進 log(見 log.py 開頭的約定)。
"""
import json
import time

from . import config
from .log import log


def _path(slug):
    return config.STORIES / slug / "transcript.jsonl"


def record_of(session, role, text, anchors):
    """攤成一筆 record(純函式,好測)。
    anchors 空 → None 而非 []:讓「這輪沒有錨定」在檔案裡是個明確的值,不是空集合的巧合。"""
    return {
        "ts": round(time.time(), 3),
        "session": session,
        "role": role,
        "text": text,
        "anchors": list(anchors) or None,
    }


def append(slug, session, role, text, anchors=()):
    """append 一行。目錄不存在就跳過(捕獲絕不擋討論)。
    I/O 失敗吞掉並記 log —— 同 ledger 的理由:記錄失敗不該打斷使用者正在進行的對話。"""
    if not (config.STORIES / slug).is_dir():
        return
    line = json.dumps(record_of(session, role, text, anchors), ensure_ascii=False)
    try:
        with _path(slug).open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        log.warning(f"event=transcript-append-fail slug={slug} role={role} err={type(e).__name__}")


def load(slug):
    """讀該篇所有 record;檔不存在回 [];壞行跳過(一行壞不讓整份讀不了)。"""
    p = _path(slug)
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        log.warning(f"event=transcript-load-fail slug={slug} err={type(e).__name__}")
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


def session_range(rows, session):
    """該 session 涵蓋 rows 的 [首行, 末行] 索引(純函式)。
    給結論的 provenance.turns 用 —— 之後要下鑽回完整語境靠這兩個數字。
    沒有任何一行屬於該 session 時回 [0, 0](退化區間,語意是「涵蓋不到東西」)。"""
    idx = [i for i, r in enumerate(rows) if r.get("session") == session]
    return [idx[0], idx[-1]] if idx else [0, 0]
