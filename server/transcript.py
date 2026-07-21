"""討論逐字正本:每輪一行 append 到 stories/<slug>/transcript.jsonl。

與 ledger.py 同層、同 pattern、同契約 —— 差別只在記的是「說了什麼」而非「花了多少」。
兩者刻意分檔:ledger 丟了可以重跑一次拿回數字,transcript 丟了就永遠沒了。
append-only、同步寫(不 await)→ 對其他 asyncio task 原子;per-slug 不同檔,結構上零競爭。

注意:log 只出現 slug/role/例外型別 —— 內容不進 log(見 log.py 開頭的約定)。
"""
import json
import time

import conclusions

from . import config
from .log import log


def _path(slug):
    return config.STORIES / slug / "transcript.jsonl"


def _as_list(v):
    """anchors 正規化,同 conclusions._as_list 的作法:是 list/tuple 才轉成 list,
    其餘型別(尤其是字串)原樣照抄 —— 絕不用 list() 硬轉,那會把純量 "t1" 拆成
    ['t','1'] 這種看起來合法、其實是垃圾的單字元陣列。目前有 app._anchors 在
    HTTP 邊界擋著只會是 list,但第二個呼叫端(終端機捕獲、P2)一出現就會直接餵純量。"""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return v


def record_of(session, role, text, anchors, analysis_fp):
    """攤成一筆 record(純函式,好測)。
    anchors 空 → None 而非 []:讓「這輪沒有錨定」在檔案裡是個明確的值,不是空集合的巧合。
    analysis_fp:當時 analysis.json 的指紋(conclusions.analysis_fp 算的同一份)——
    node id 會在每次 re-analyze 被重鑄,沒有這個回頭比對,P2 的 recall(anchors=["t3"])
    會靜默撈到「當時 t3 指的是另一個主題」的舊行,而且無從偵測。"""
    return {
        "ts": round(time.time(), 3),
        "session": session,
        "role": role,
        "text": text,
        "anchors": _as_list(anchors) or None,
        "analysis_fp": analysis_fp,
    }


def append(slug, session, role, text, anchors=()):
    """append 一行。目錄不存在就跳過(捕獲絕不擋討論)。
    I/O 失敗吞掉並記 log —— 同 ledger 的理由:記錄失敗不該打斷使用者正在進行的對話。"""
    if not (config.STORIES / slug).is_dir():
        return
    fp = conclusions.analysis_fp(slug)
    line = json.dumps(record_of(session, role, text, anchors, fp), ensure_ascii=False)
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
    這是**過濾後清單**(rows,通常來自 load())的索引,不是實體行號 —— 一行壞掉會位移
    後續所有索引,是 best-effort,不是精確的檔案座標。
    沒有任何一行屬於該 session 時回 [-1, -1](自明為空的退化區間):[0, 0] 會跟「這個
    session 剛好只涵蓋第 0 行」無法區分,萬一某次 transcript 寫入被 OSError 吞掉,
    distill 可能因此蓋出一份指向別的 session 第一行的 provenance —— 一個看起來合理的謊。"""
    idx = [i for i, r in enumerate(rows) if r.get("session") == session]
    return [idx[0], idx[-1]] if idx else [-1, -1]
