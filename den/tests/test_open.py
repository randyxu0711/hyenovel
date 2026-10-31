"""den.open:假 DenClient + 假 webbrowser,不起真 den、不開真瀏覽器。"""
import httpx

from den import open as den_open


def test_open_prints_and_opens_url(monkeypatch, capsys, tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["path"] = request.url.path
        return httpx.Response(200, json={"url": "http://127.0.0.1:8788/login?code=abc"})

    class FakeDen:
        def __init__(self, data_dir):
            seen["dir"] = data_dir

        def ensure(self):
            return httpx.Client(base_url="http://127.0.0.1:8788",
                                transport=httpx.MockTransport(handler)), "tok"

    opened = []
    monkeypatch.setattr(den_open, "DenClient", FakeDen)
    monkeypatch.setattr(den_open.webbrowser, "open", opened.append)
    den_open.main([])
    assert seen["auth"] == "Bearer tok" and seen["path"] == "/api/launch"
    assert opened == ["http://127.0.0.1:8788/login?code=abc"]
    assert capsys.readouterr().out.strip() == "http://127.0.0.1:8788/login?code=abc"
