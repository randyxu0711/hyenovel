"""兩版原文對照:切句後句內逐字 diff(空白、全半形標點差異不算),與上一版筆記引文的去向。位置一律 code point。"""
from difflib import SequenceMatcher

from marrow.gate import _PUNCT, locate

_ENDS = "。！？"
_CLOSERS = "」』）”’"


def _sentences(text: str) -> list[list[tuple[int, str]]]:
    out: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    ended = False
    for i, ch in enumerate(text):
        if ch == "\n":
            if cur:
                out.append(cur)
            cur, ended = [], False
            continue
        if ch.isspace():
            continue
        k = ch.translate(_PUNCT)
        if ended and k not in _CLOSERS:
            out.append(cur)
            cur, ended = [], False
        cur.append((i, k))
        if k in _ENDS:
            ended = True
    if cur:
        out.append(cur)
    return out


def _key(toks: list[tuple[int, str]]) -> str:
    return "".join(k for _, k in toks)


def _blocks(old: str, new: str):
    """(pairs, dels, inss):dels/inss 是連續未配對字的原文位置串列。"""
    a, b = _sentences(old), _sentences(new)
    pairs: dict[int, int] = {}
    dels: list[list[int]] = []
    inss: list[list[int]] = []
    sm = SequenceMatcher(None, [_key(s) for s in a], [_key(s) for s in b], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        x = [t for s in a[i1:i2] for t in s]
        y = [t for s in b[j1:j2] for t in s]
        if tag == "equal":
            pairs.update((p[0], q[0]) for p, q in zip(x, y))
            continue
        cm = SequenceMatcher(None, _key(x), _key(y), autojunk=False)
        for t, p1, p2, q1, q2 in cm.get_opcodes():
            if t == "equal":
                pairs.update((x[p][0], y[q][0]) for p, q in zip(range(p1, p2), range(q1, q2)))
                continue
            if p1 < p2:
                dels.append([x[p][0] for p in range(p1, p2)])
            if q1 < q2:
                inss.append([y[q][0] for q in range(q1, q2)])
    return pairs, dels, inss


def _line_bounds(text: str, start: int, end: int) -> tuple[bool, bool]:
    """[start, end) 前面到行首、後面到行尾是不是都只有空白。"""
    head = text[text.rfind("\n", 0, start) + 1:start]
    nl = text.find("\n", end)
    tail = text[end:] if nl == -1 else text[end:nl]
    return not head.strip(), not tail.strip()


def _del_run(old: str, new: str, idx: list[int], pairs: dict[int, int]) -> dict:
    s, e = idx[0], idx[-1] + 1
    prev = [pairs[i] for i in pairs if i < s]
    at = max(prev) + 1 if prev else 0
    whole_head, whole_tail = _line_bounds(old, s, e)
    if whole_head and whole_tail:
        nl = old.find("\n", e)
        cut = new.find("\n", at) if prev else -1
        if nl != -1 and (not prev or cut != -1):
            e = nl + 1
            at = cut + 1 if prev else 0
        elif s > 0:
            s = old.rfind("\n", 0, s)
    text = old[s:e]
    return {"op": "del", "at": at, "text": text, "chars": sum(1 for c in text if not c.isspace()),
            "old": {"start": s, "end": e}}


def diff(old: str, new: str) -> dict:
    pairs, dels, inss = _blocks(old, new)
    runs = [_del_run(old, new, d, pairs) for d in dels]
    runs += [{"op": "ins", "start": i[0], "end": i[-1] + 1} for i in inss]
    runs.sort(key=lambda r: (r.get("at", r.get("start")), r["op"] != "del"))
    n = {"del": 0, "ins": 0}
    for r in runs:
        r["id"] = f"{r['op'][0]}{n[r['op']]}"
        n[r["op"]] += 1
    paired_new = set(pairs.values())
    hunks: list[dict] = []
    last_end = None
    for r in runs:
        pos = r.get("at", r.get("start"))
        if last_end is not None and not any(i in paired_new for i in range(last_end, pos)):
            hunks[-1]["ids"].append(r["id"])
        else:
            hunks.append({"ids": [r["id"]], "at": pos})
        last_end = max(last_end or 0, r.get("end", pos))
    return {"runs": [_ordered(r) for r in runs], "hunks": hunks, "same": not runs, "pairs": pairs}


def _ordered(r: dict) -> dict:
    keys = ("op", "id", "at", "text", "chars", "old") if r["op"] == "del" else ("op", "id", "start", "end")
    return {k: r[k] for k in keys}


def _fate(quote: str, old: str, new: str, d: dict, hunk_of: dict, runs: dict) -> dict:
    out = {"quote": quote, "fate": "lost", "old": None, "new": None, "new_text": None, "del": None}
    hit = locate(quote, old) if quote.strip() else None
    if hit is None:
        return out
    s, e = hit
    out["old"] = {"start": s, "end": e}
    chars = [i for i in range(s, e) if not old[i].isspace()]
    matched = [d["pairs"][i] for i in chars if i in d["pairs"]]
    if len(matched) == len(chars):
        out.update(fate="kept", new={"start": min(matched), "end": max(matched) + 1})
        return out
    moved = locate(quote, new)
    if moved is not None:
        out.update(fate="kept", new={"start": moved[0], "end": moved[1]})
        return out
    dels = [r for r in d["runs"] if r["op"] == "del" and r["old"]["start"] < e and s < r["old"]["end"]]
    out["del"] = dels[0]["id"] if dels else None
    ins = [runs[i] for r in dels for i in hunk_of[r["id"]] if runs[i]["op"] == "ins"]
    if not matched and not ins:
        out["fate"] = "gone"
        return out
    lo = min([*matched, *(r["start"] for r in ins)])
    hi = max([*(m + 1 for m in matched), *(r["end"] for r in ins)])
    out.update(fate="changed", new={"start": lo, "end": hi}, new_text=new[lo:hi])
    return out


def trace(points: list[dict], old: str, new: str, d: dict) -> list[dict]:
    hunk_of = {i: h["ids"] for h in d["hunks"] for i in h["ids"]}
    runs = {r["id"]: r for r in d["runs"]}
    out = []
    for n, p in enumerate(points):
        qs = [_fate(q, old, new, d, hunk_of, runs) for q in p.get("quotes") or []]
        states = {q["fate"] for q in qs} - {"lost"}
        fate = "untracked" if not states else "kept" if states == {"kept"} else "changed"
        label = None if not states else next(iter(states)) if len(states) == 1 else "mixed"
        out.append({"i": n, "kind": p.get("kind"), "title": p.get("title"), "body": p.get("body"),
                    "question": p.get("question"), "fate": fate, "label": label, "quotes": qs})
    return out


def pin(runs: list[dict], points: list[dict]) -> None:
    spans = [q["old"] for p in points for q in p["quotes"] if q["old"] is not None]
    for r in runs:
        if r["op"] == "del":
            r["pinned"] = any(sp["start"] < r["old"]["end"] and r["old"]["start"] < sp["end"] for sp in spans)


def public(d: dict) -> dict:
    return {"runs": [{k: v for k, v in r.items() if k != "old"} for r in d["runs"]],
            "hunks": d["hunks"], "same": d["same"]}
