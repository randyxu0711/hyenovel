"""den.memory 行為契約:載入與寫入政策。"""
from den import memory
from marrow import repo


def test_load_returns_active_text_in_order(conn):
    s1 = repo.ensure_story(conn, "s1", None, 0)
    repo.add_memory(conn, "author", "甲", 1.0)
    gone = repo.add_memory(conn, "author", "封存", 2.0)
    repo.add_memory(conn, "author", "乙", 3.0)
    repo.add_memory(conn, "work", "丙", 4.0, story_id=s1)
    repo.invalidate_memory(conn, gone, 5.0)
    assert memory.load(conn, s1) == {"author": ["甲", "乙"], "work": ["丙"]}
