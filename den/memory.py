"""記憶的政策:companion 讀什麼。SQL 在 marrow/repo.py。"""
from marrow import repo


def load(conn, story_id: int) -> dict:
    return {"author": [m["text"] for m in repo.active_memories(conn, "author")],
            "work": [m["text"] for m in repo.active_memories(conn, "work", story_id)]}
