"""記憶的政策:companion 讀什麼、誰能寫、上限怎麼算。SQL 在 marrow/repo.py。

一條記憶是一條 chain,每次改動都新增一列,chain 同時最多一列生效。每個寫入函式自己開 transaction。
"""
from marrow import gate, repo

CAPS = {"author": 800, "work": 600, "character": 300}


class MemoryFull(Exception):
    pass


class NotCurrent(Exception):
    pass


class AlreadyCurrent(Exception):
    pass


class BadSource(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def load(conn, story_id: int | None) -> dict:
    return {"author": [m["text"] for m in repo.active_memories(conn, "author")],
            "work": [m["text"] for m in repo.active_memories(conn, "work", story_id)]}


def usage(conn, scope: str, story_id: int | None = None) -> int:
    return sum(len(m["text"]) for m in repo.active_memories(conn, scope, story_id))


def _check_cap(conn, scope: str, story_id: int | None, added: str, replaced: str = "") -> None:
    if usage(conn, scope, story_id) - len(replaced) + len(added) > CAPS[scope]:
        raise MemoryFull(scope)


def _resolve_source(conn, story_id: int | None, source: dict) -> dict:
    d = repo.discussion_by_external(conn, story_id, source["session"])
    if d is None:
        raise BadSource("unknown-session")
    u = repo.utterance(conn, d["id"], source["seq"])
    if u is None:
        raise BadSource("unknown-turn")
    if gate.gate_utterance_quote(source["quote"], u):
        raise BadSource("quote-not-in-turn")
    return u


def _row_or_raise(conn, memory_id: int) -> dict:
    row = repo.memory(conn, memory_id)
    if row is None:
        raise LookupError(memory_id)
    return row


def _current_or_raise(conn, memory_id: int) -> dict:
    row = _row_or_raise(conn, memory_id)
    if row["invalidated_at"] is not None:
        raise NotCurrent(memory_id)
    return row


def _chain_id(row: dict) -> int:
    return row["id"] if row["root_id"] is None else row["root_id"]


def _next_in_chain(conn, row: dict, text: str, now: float) -> int:
    return repo.add_memory(conn, row["scope"], text, now, story_id=row["story_id"],
                           character=row["character"], quote=row["quote"],
                           discussion_id=row["discussion_id"], seq=row["seq"],
                           root_id=_chain_id(row))


def remember(conn, scope: str, text: str, now: float, *, story_id: int | None = None,
             source: dict | None = None) -> int:
    row_story = story_id if scope == "work" else None
    with conn:
        u = _resolve_source(conn, story_id, source) if source else None
        _check_cap(conn, scope, row_story, text)
        if u is None:
            return repo.add_memory(conn, scope, text, now, story_id=row_story)
        return repo.add_memory(conn, scope, text, now, story_id=row_story, quote=source["quote"],
                               discussion_id=u["discussion_id"], seq=u["seq"], valid_from=u["ts"])


def edit(conn, memory_id: int, text: str, now: float) -> int:
    with conn:
        row = _current_or_raise(conn, memory_id)
        _check_cap(conn, row["scope"], row["story_id"], text, row["text"])
        repo.invalidate_memory(conn, memory_id, now)
        return _next_in_chain(conn, row, text, now)


def archive(conn, memory_id: int, now: float) -> None:
    with conn:
        _current_or_raise(conn, memory_id)
        repo.invalidate_memory(conn, memory_id, now)


def revert(conn, memory_id: int, now: float) -> int:
    with conn:
        row = _row_or_raise(conn, memory_id)
        if row["invalidated_at"] is None:
            raise AlreadyCurrent(memory_id)
        live = repo.current_in_chain(conn, _chain_id(row))
        _check_cap(conn, row["scope"], row["story_id"], row["text"], live["text"] if live else "")
        if live:
            repo.invalidate_memory(conn, live["id"], now)
        return _next_in_chain(conn, row, row["text"], now)
