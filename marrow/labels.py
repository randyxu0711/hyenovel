import re

_ID = re.compile(r"(?<![A-Za-z0-9_])([tmkecb]\d+)(?![A-Za-z0-9_])(「([^」\n]*)」)?")


def label_map(analysis: dict | None) -> dict[str, str]:
    nodes = (analysis or {}).get("nodes")
    return {n["id"]: n["label"] for n in nodes if isinstance(n, dict)
            and isinstance(n.get("id"), str) and isinstance(n.get("label"), str)} if isinstance(nodes, list) else {}


def relabel(text: str, labels: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        label = labels.get(m[1])
        if label is None:
            return m[0]
        return f"〈{label}〉" + ("" if m[3] == label else (m[2] or ""))
    return _ID.sub(sub, text) if labels else text
