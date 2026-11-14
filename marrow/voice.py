"""讀伴回覆的機械指標與唯讀報表:`python -m marrow.voice [--character ID] [--since-version N] [--json] [--thinking]`。"""
import argparse
import json
import re
import sqlite3
import statistics
import sys
from collections import Counter

from marrow import db, repo

_END = r"[。！？!?…\n]"
_CLOSE = "」』）)\"'”’"
_SENT = re.compile(rf"[^。！？!?…\n]+{_END}*[{_CLOSE}]*")
_SPACE = re.compile(r"\s+")

RULES = {
    "停在": re.compile(r"停在|停了一下|卡在"),
    "不是X而是Y": re.compile(r"不是[^。！？!?\n]{1,24}(而是|是在|只是)|與其說[^。\n]{1,24}不如說"),
    "只是X才是Y": re.compile(r"只是[^。！？!?\n]{1,24}才是"),
    "免責": re.compile(r"這只是我的|只是我的(猜|想法|讀法|感覺)|我不確定|可能是我"),
    "講意義": re.compile(r"其實是在|說的是|象徵|意味著|代表著|整篇(都|就)"),
    "被推": re.compile(r"被推(出|了|進|回)"),
    "二選一問句": re.compile(r"還是[^。！？!?\n]{1,40}[？?]"),
    "列舉": re.compile(r"首先|其次|第一[,，、]|一方面"),
    "破折號": re.compile(r"——"),
    "引文開頭": re.compile(r"^\s*(我[^「\n]{0,8})?「"),
}
_PRAISE = re.compile(r"喜歡|很好|很美|漂亮|好看|厲害|好在|動人|成立|有力")
_BUT = re.compile(r"但|可是|不過|只是")
_JUDGE = re.compile(r"多餘|太|不夠|拿掉|應該|可惜|我覺得|好像")


def _asks(sentence):
    return sentence.endswith(("?", "？"))


def sentences(text):
    return [s.strip() for s in _SENT.findall(text) if s.strip()]


def scan(text):
    hits = Counter()
    for name, pat in RULES.items():
        n = len(pat.findall(text)) if name != "引文開頭" else int(bool(pat.search(text)))
        if n:
            hits[name] += n
    ss = sentences(text)
    if ss and _asks(ss[-1]) and any(_JUDGE.search(s) for s in ss[:-1]):
        hits["判斷後補問"] += 1
    if len(ss) >= 2 and _PRAISE.search(ss[0]) and any(_BUT.search(s[:4]) for s in ss[1:]):
        hits["先褒後貶"] += 1
    return hits


def ngrams(text, n=6):
    t = _SPACE.sub("", text)
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def copy_ratio(text, examples):
    mine = ngrams(text)
    if not mine or not examples:
        return None
    return round(len(mine & ngrams(examples)) / len(mine), 3)


def opening(text):
    return _SPACE.sub("", text)[:4]


def metrics(text, examples, usage, thinking):
    usage = usage or {}
    out, think = usage.get("output"), usage.get("thinking")
    ss = sentences(text)
    hits = scan(text)
    return {"len": len(text), "question_end": bool(ss) and _asks(ss[-1]),
            "slop": dict(hits), "slop_n": sum(hits.values()), "copy": copy_ratio(text, examples),
            "opening": opening(text), "thinking_tokens": think,
            "thinking_share": round(think / out, 2) if think is not None and out else None,
            "thinking_chars": len(thinking) if thinking else 0,
            "duration_ms": usage.get("duration_ms"), "first_delta_ms": usage.get("first_delta_ms")}


_COLS = ("{t}.discussion_id AS discussion_id, {t}.seq AS seq, {t}.text AS text, {t}.usage AS usage, "
         "{t}.recipe AS recipe, {t}.thinking AS thinking, {t}.analysis_fp AS analysis_fp, "
         "{t}.edited_at AS edited_at, u.character AS character, d.story_id AS story_id, ")
_ROWS = (
    "SELECT " + _COLS.format(t="u") + "u.variant AS variant, 1 AS kept "
    "FROM utterance u JOIN discussion d ON d.id = u.discussion_id WHERE u.role = 'assistant' "
    "UNION ALL SELECT " + _COLS.format(t="v") + "v.n AS variant, 0 AS kept "
    "FROM utterance_variant v JOIN utterance u ON u.discussion_id = v.discussion_id AND u.seq = v.seq "
    "JOIN discussion d ON d.id = v.discussion_id "
    "ORDER BY discussion_id, seq, kept DESC, variant")


def load(conn):
    examples = {(r["character_id"], r["n"]): (r["card"].get("data") or {}).get("mes_example") or ""
                for r in map(repo._row, conn.execute("SELECT character_id, n, card FROM character_version"))}
    rows = []
    for r in map(repo._row, conn.execute(_ROWS)):
        recipe = r["recipe"] or {}
        rows.append({"discussion": r["discussion_id"], "seq": r["seq"], "variant": r["variant"],
                     "kept": bool(r["kept"]), "text": r["text"], "usage": r["usage"], "thinking": r["thinking"],
                     "character": r["character"], "card_v": recipe.get("character_v"),
                     "story": r["story_id"] is not None, "analysis": r["analysis_fp"] is not None,
                     "retrieved": len(recipe.get("retrieved", ())), "edited": r["edited_at"] is not None,
                     "examples": examples.get((r["character"], recipe.get("character_v")), "")})
    return rows


def measure(rows, character=None, since_version=None):
    out, seen = [], {}
    for r in rows:
        repeat = None
        if r["kept"]:
            openings = seen.setdefault(r["discussion"], set())
            repeat = opening(r["text"]) in openings
            openings.add(opening(r["text"]))
        if character is not None and r["character"] != character:
            continue
        if since_version is not None and (r["card_v"] is None or r["card_v"] < since_version):
            continue
        m = metrics(r["text"], r["examples"], r["usage"], r["thinking"])
        out.append({**{k: v for k, v in r.items() if k not in ("examples", "usage")}, **m, "repeat_opening": repeat})
    return out


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _rate(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def summarize(measured):
    groups = {}
    for m in measured:
        if not m["edited"]:
            groups.setdefault((m["character"], m["card_v"], m["story"]), []).append(m)
    return [{"character": c, "card_v": v, "story": s, "n": len(g), "shelved": sum(not m["kept"] for m in g),
             "len": _median(m["len"] for m in g), "slop_n": _median(m["slop_n"] for m in g),
             "question_end": _rate([m["question_end"] for m in g]),
             "repeat_opening": _rate([m["repeat_opening"] for m in g]),
             "copy": _median(m["copy"] for m in g),
             "thinking_tokens": _median(m["thinking_tokens"] for m in g),
             "duration_ms": _median(m["duration_ms"] for m in g),
             "first_delta_ms": _median(m["first_delta_ms"] for m in g)}
            for (c, v, s), g in groups.items()]


def _cell(v):
    return "-" if v is None else str(v)


def render(measured, groups, thinking=False):
    cols = ("discussion", "seq", "variant", "kept", "edited", "character", "card_v", "story", "len",
            "question_end", "slop_n", "copy", "repeat_opening", "thinking_tokens", "duration_ms", "first_delta_ms")
    lines = ["\t".join(cols)]
    for m in measured:
        lines.append("\t".join(_cell(m[c]) for c in cols))
        if thinking and m["thinking"]:
            lines.append("  thinking: " + m["thinking"].strip().replace("\n", "\n  "))
    gcols = ("character", "card_v", "story", "n", "shelved", "len", "question_end", "slop_n", "copy",
             "repeat_opening", "thinking_tokens", "duration_ms", "first_delta_ms")
    lines += ["", "\t".join(gcols)] + ["\t".join(_cell(g[c]) for c in gcols) for g in groups]
    return "\n".join(lines) + "\n"


def main(argv=None, out=sys.stdout, err=sys.stderr):
    ap = argparse.ArgumentParser(prog="python -m marrow.voice")
    ap.add_argument("--db", default=None)
    ap.add_argument("--character")
    ap.add_argument("--since-version", type=int)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--thinking", action="store_true")
    args = ap.parse_args(argv)
    if args.since_version is not None and args.character is None:
        ap.error("--since-version 要配 --character(卡版是各角色自己編號)")
    try:
        conn = db.connect_readonly(args.db or db.database_url())
        try:
            measured = measure(load(conn), args.character, args.since_version)
        finally:
            conn.close()
    except sqlite3.OperationalError as e:
        err.write(f"讀不到報表要的資料({e})。DB 不存在,或還沒升到含 thinking 的版本:重啟 den 會自動升級。\n")
        return 1
    groups = summarize(measured)
    if args.json:
        if not args.thinking:
            measured = [{k: v for k, v in m.items() if k != "thinking"} for m in measured]
        out.write(json.dumps({"rows": measured, "groups": groups}, ensure_ascii=False, indent=1) + "\n")
    else:
        out.write(render(measured, groups, args.thinking))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
