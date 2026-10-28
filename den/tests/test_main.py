"""den.__main__:選 port、把閒置退場接到 uvicorn.Server.should_exit。"""
import socket

from den import __main__ as m


def test_pick_port_preferred_free():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    free = s.getsockname()[1]
    s.close()
    assert m.pick_port(free) == free


def test_pick_port_occupied_falls_back():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    busy = s.getsockname()[1]
    try:
        got = m.pick_port(busy)
        assert got != busy and got > 0
    finally:
        s.close()


def test_main_wires_on_idle_to_should_exit(monkeypatch, tmp_path, capsys):
    seen = {}

    class FakeServer:
        should_exit = False

        def __init__(self, config):
            seen["config"] = config
            seen["server"] = self

        def run(self):
            seen["ran"] = True

    monkeypatch.setattr(m, "pick_port", lambda p: 4321)
    monkeypatch.setattr(m.db, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(m.db, "database_url", lambda: "sqlite:///x")
    monkeypatch.setattr(m, "create_app", lambda url, d, **kw: seen.update(kw) or "APP")
    monkeypatch.setattr(m.uvicorn, "Server", FakeServer)
    monkeypatch.setattr(m.uvicorn, "Config", lambda app, **kw: {"app": app, **kw})
    m.main([])
    assert seen["port"] == 4321 and seen["ran"]
    assert seen["config"]["port"] == 4321 and seen["config"]["timeout_graceful_shutdown"] == 3
    # on_idle 要能把「同一個」server 的 should_exit 設 True
    assert seen["server"].should_exit is False
    seen["on_idle"]()
    assert seen["server"].should_exit is True
    assert "4321" in capsys.readouterr().out
