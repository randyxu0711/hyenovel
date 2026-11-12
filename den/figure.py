"""角色長相(`extensions.hyenovel.figure`)的機械閘門:只認文法檔裡的姿態、筆、群組,路徑只收絕對座標指令且不出界。"""
import json
import re
from pathlib import Path

GRAMMAR = json.loads((Path(__file__).resolve().parent.parent / "marrow" / "figure.json").read_text(encoding="utf-8"))
LIMITS = GRAMMAR["limits"]
MAX_D = 600
_ARGS = {"M": 2, "L": 2, "C": 6, "Q": 4, "A": 7, "Z": 0}
_TOKEN = re.compile(r"[MLCQAZ]|-?(?:\d+\.?\d*|\.\d+)")
_SEPARATORS = re.compile(r"[\s,]*")
_KEYS = {"pose", "parts", "eyes", "mouth", "main", "second", "tempo", "move"}
_PART_KEYS = {"group", "d", "fill", "line", "detail"}


def _in(v) -> bool:
    lo, hi = LIMITS["coord"]
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def _points(value, n: int) -> bool:
    return (isinstance(value, list) and len(value) == n
            and all(isinstance(p, list) and len(p) == 2 and all(map(_in, p)) for p in value))


def path_errors(d) -> list[str]:
    if not isinstance(d, str) or len(d) > MAX_D or not _SEPARATORS.fullmatch(_TOKEN.sub(" ", d)):
        return ["bad-path"]
    tokens = _TOKEN.findall(d)
    if not tokens or tokens[0] != "M":
        return ["bad-path"]
    commands, i = 0, 0
    while i < len(tokens):
        cmd, i = tokens[i], i + 1
        if cmd not in _ARGS:
            return ["bad-path"]
        n = _ARGS[cmd]
        args = tokens[i:i + n]
        if len(args) < n or any(a in _ARGS for a in args):
            return ["bad-path"]
        nums = [float(a) for a in args]
        if cmd == "A":
            rx, ry, _, large, sweep, x, y = nums
            coords_ok = 0 <= rx <= LIMITS["coord"][1] and 0 <= ry <= LIMITS["coord"][1] and large in (0, 1) and sweep in (0, 1)
            if not (coords_ok and _in(x) and _in(y)):
                return ["out-of-bounds"]
        elif not all(map(_in, nums)):
            return ["out-of-bounds"]
        commands, i = commands + 1, i + n
    return ["too-many-commands"] if commands > LIMITS["commands"] else []


def command_count(d: str) -> int:
    return sum(t in _ARGS for t in _TOKEN.findall(d))


def bbox(d: str) -> tuple[float, float, float, float]:
    """路徑的外框;A 以終點加減半徑估,寧大不小。只收過了 path_errors 的路徑。"""
    tokens, xs, ys, i = _TOKEN.findall(d), [], [], 0
    while i < len(tokens):
        cmd, i = tokens[i], i + 1
        nums = [float(a) for a in tokens[i:i + _ARGS[cmd]]]
        i += _ARGS[cmd]
        if cmd == "A":
            rx, ry, *_, x, y = nums
            xs += [x - rx, x + rx]
            ys += [y - ry, y + ry]
        else:
            xs += nums[0::2]
            ys += nums[1::2]
    return min(xs), min(ys), max(xs), max(ys)


FRAME = (8, 14, 112, 93)


def _map_path(d: str, at, k: float) -> str:
    tokens, out, i = _TOKEN.findall(d), [], 0
    while i < len(tokens):
        cmd, i = tokens[i], i + 1
        nums = [float(a) for a in tokens[i:i + _ARGS[cmd]]]
        i += _ARGS[cmd]
        if cmd == "A":
            rx, ry, rot, large, sweep, x, y = nums
            out.append(f"A{_r(rx * k)} {_r(ry * k)} {_r(rot)} {int(large)} {int(sweep)} {' '.join(map(_r, at(x, y)))}")
        else:
            pts = [_r(v) for j in range(0, len(nums), 2) for v in at(nums[j], nums[j + 1])]
            out.append(cmd + " ".join(pts))
    return " ".join(out)


def _r(v: float) -> str:
    return f"{round(v, 1):g}"


def fit(fig: dict) -> dict:
    """等比例縮放平移到 FRAME:水平置中、底貼地面。只收過了 errors 的 parts/eyes/mouth。"""
    boxes = [bbox(p["d"]) for p in fig["parts"]]
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    fx0, fy0, fx1, fy1 = FRAME
    k = min((fx1 - fx0) / max(x1 - x0, 1), (fy1 - fy0) / max(y1 - y0, 1))
    cx, mid = (x0 + x1) / 2, (fx0 + fx1) / 2
    at = lambda x, y: (mid + (x - cx) * k, fy1 - (y1 - y) * k)
    point = lambda p: [round(v, 1) for v in at(*p)]
    return {**fig, "parts": [{**p, "d": _map_path(p["d"], at, k)} for p in fig["parts"]],
            "eyes": [point(p) for p in fig["eyes"]], "mouth": [point(p) for p in fig["mouth"]]}


def _one_of(value, allowed) -> bool:
    return isinstance(value, str) and value in allowed


def _part_errors(part) -> list[str]:
    if not isinstance(part, dict) or not {"group", "d", "fill"} <= set(part) <= _PART_KEYS:
        return ["bad-part"]
    if not _one_of(part["group"], GRAMMAR["groups"]) or not _one_of(part["fill"], GRAMMAR["fills"]):
        return ["bad-part"]
    if any(not isinstance(part.get(k, False), bool) for k in ("line", "detail")):
        return ["bad-part"]
    return path_errors(part["d"])


def errors(figure) -> list[str]:
    """空 list = 能畫。"""
    if not isinstance(figure, dict) or not set(figure) <= _KEYS:
        return ["bad-figure"]
    bad = [] if _one_of(figure.get("main"), GRAMMAR["pens"]) and _one_of(figure.get("second"), GRAMMAR["pens"]) else ["bad-pen"]
    for key, allowed in (("tempo", GRAMMAR["tempos"]), ("move", GRAMMAR["moves"])):
        if key in figure and not _one_of(figure[key], allowed):
            bad.append(f"bad-{key}")
    pose = figure.get("pose")
    if pose is not None and not _one_of(pose, GRAMMAR["poses"]):
        bad.append("bad-pose")
    parts = figure.get("parts")
    if not isinstance(parts, list) or len(parts) > LIMITS["parts"]:
        return bad + ["bad-parts"]
    for n, part in enumerate(parts):
        bad += [f"parts/{n}: {e}" for e in _part_errors(part)]
    for key, n in (("eyes", 2), ("mouth", 3)):
        if key in figure and not _points(figure[key], n):
            bad.append(f"bad-{key}")
        if pose is None and key not in figure:
            bad.append(f"no-{key}")
    if pose is None and not parts:
        bad.append("no-parts")
    return bad


def pen_colors(main: str) -> dict:
    """生成角色的 colors:fill = 筆色,名字色 = 文法檔裡驗過對比的那支。"""
    pen = GRAMMAR["pens"][main]
    return {s: {"fill": pen[s], "text": pen["text"][s]} for s in ("light", "dark")}
