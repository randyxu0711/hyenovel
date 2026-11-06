"""錨點檢索:依這輪提到的原文位置與標籤,挑出要展開細節的分析 node。"""
from den import spans
from marrow import gate

NEAR = 120
MAX_NODES = 6
_MIN_LABEL = 2


def _gap(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(a[0] - b[1], b[0] - a[1], 0)


def _near(quotes, source: str, positions: dict[str, list[tuple[int, int]]]) -> list[str]:
    hits = [h for q in quotes if (h := gate.locate(q, source))]
    if not hits:
        return []
    gaps = {nid: min(_gap(h, p) for h in hits for p in ps) for nid, ps in positions.items() if ps}
    return sorted((nid for nid, g in gaps.items() if g <= NEAR), key=gaps.__getitem__)


def pick(analysis: dict | None, source: str, *, quotes, message: str, last_reply: str,
         previous=()) -> list[dict]:
    """順位:作者帶的或訊息裡的引文 → 訊息提到的標籤 → 上一則回覆的引文 → 上一輪展開過的 node。"""
    if analysis is None:
        return []
    nodes = analysis.get("nodes") or []
    positions = {n["id"]: [h for e in n.get("evidence") or ()
                           if e["quote"].strip() and (h := gate.locate(e["quote"], source))] for n in nodes}
    ranked = _near((*quotes, *spans.quotes_in(message)), source, positions)
    ranked += [n["id"] for n in nodes if len(n["label"]) >= _MIN_LABEL and n["label"] in message]
    ranked += _near(spans.quotes_in(last_reply), source, positions)
    by_id = {n["id"]: n for n in nodes}
    return [by_id[nid] for nid in dict.fromkeys((*ranked, *previous)) if nid in by_id][:MAX_NODES]


def render(analysis: dict | None, picked: list[dict]) -> str:
    if not picked:
        return ""
    by_id = {n["id"]: n for n in analysis.get("nodes") or ()}
    edges = analysis.get("edges") or ()
    lines = ["這輪可能用得上的細節(私下筆記,不要原樣念給作者):"]
    for n in picked:
        lines.append(f"- {n['type']} {n['label']}" + (f":{n['note']}" if n.get("note") else ""))
        lines += [f"  原文:「{e['quote']}」" for e in n.get("evidence") or ()]
        for e in edges:
            if e["from"] == n["id"] and e["to"] in by_id:
                lines.append(f"  {e['type']} → {by_id[e['to']]['type']} {by_id[e['to']]['label']}")
            elif e["to"] == n["id"] and e["from"] in by_id:
                lines.append(f"  {e['type']} ← {by_id[e['from']]['type']} {by_id[e['from']]['label']}")
    return "\n".join(lines)
