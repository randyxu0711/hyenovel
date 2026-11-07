"""角色候選:人格軸抽樣、產出閘門、修補一次、生成端點。"""
import asyncio
from contextlib import contextmanager
from itertools import combinations

import pytest
from fastapi.testclient import TestClient

from den import app as den_app
from den import candidates, cards
from den import config as den_config
from den.runner import RunResult
from den.tests.test_app import _auth
from den.tests.test_pipeline import ok


def _one(n=1, **kw):
    return {"name": {"zh-Hant": f"讀者{n}", "en": f"Reader {n}"},
            "line": {"zh-Hant": "先聽聲音", "en": "Listens first"},
            "reading": "你聽句子的聲音,在意哪裡換了氣。",
            "sample": f"她把手放在鍋蓋上那一下,我停住了({n})。",
            **kw}


def _body(*items):
    return {"candidates": list(items) or [_one(1), _one(2), _one(3)]}


def _failed(outcome="usage-limit"):
    return RunResult(outcome, None, "", None, None, 0, "x")


def _unparsed(text):
    return RunResult("ok", None, text, None, None, 0, None, text=text)


class Script:
    """照順序回結果,並記下每次呼叫。"""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    async def __call__(self, system_prompt, user_prompt, schema, *, config, timeout):
        self.calls.append((system_prompt, user_prompt))
        self.timeout = timeout
        return self.results.pop(0)


def _generate(script, seed=7, brief="一隻老貓"):
    return asyncio.run(candidates.generate(script, brief, seed))


@pytest.mark.parametrize("seed", range(50))
def test_positions_are_three_and_pairwise_differ_on_two_axes(seed):
    picked = candidates.positions(seed)
    assert len(picked) == 3
    for a, b in combinations(picked, 2):
        assert sum(x != y for x, y in zip(a, b)) >= 2


def test_positions_take_one_pole_of_every_axis():
    for pos in candidates.positions(1):
        assert all(p in axis for p, axis in zip(pos, candidates.AXES, strict=True))


def test_same_seed_same_positions_different_seeds_vary():
    assert candidates.positions(3) == candidates.positions(3)
    assert len({tuple(candidates.positions(s)) for s in range(20)}) > 1


def test_generate_returns_cards_with_sample_as_mes_example():
    out = _generate(Script(ok(_body())))
    assert out["seed"] == 7
    assert len(out["candidates"]) == 3
    first = out["candidates"][0]
    assert first["sample"] == first["card"]["data"]["mes_example"]
    assert first["axes"] == list(candidates.positions(7)[0])


def test_candidate_card_reads_back_through_view_and_passes_scan():
    card = candidates.to_card(_one())
    assert cards.scan(card) == {"errors": [], "warnings": []}
    shown = cards.view(card, "x", 1)
    assert shown["name"]["en"] == "Reader 1"
    assert shown["line"]["zh-Hant"] == "先聽聲音"
    assert shown["reading"] == _one()["reading"]
    assert shown["colors"] == cards.FALLBACK_COLORS


def test_worker_gets_brief_positions_and_shared_passage():
    script = Script(ok(_body()))
    _generate(script, seed=7, brief="一隻老貓")
    _, user = script.calls[0]
    assert "一隻老貓" in user
    assert candidates.PASSAGE in user
    for pos in candidates.positions(7):
        assert "、".join(pos) in user


@pytest.mark.parametrize("bad", [
    _body(_one(1), _one(2)),
    _body(_one(1), _one(2), {k: v for k, v in _one(3).items() if k != "sample"}),
    _body(_one(1), _one(2), _one(3, sample="長" * 121)),
    _body(_one(1), _one(2), _one(3, reading="  ")),
    _body(_one(1), _one(2), _one(1)),
    _body(_one(1), _one(2), _one(3, name={"zh-Hant": "讀者1 ", "en": "Other"})),
    _body(_one(1), _one(2), _one(3, name={"zh-Hant": "別人", "en": "Reader 1"})),
    _body(_one(1), _one(2), _one(3, sample=_one(1)["sample"])),
])
def test_gate_rejects_bad_batches_and_repair_once_recovers(bad):
    script = Script(ok(bad), ok(_body()))
    assert len(_generate(script)["candidates"]) == 3
    assert len(script.calls) == 2


def test_instruction_like_text_is_a_warning_not_a_second_spend():
    script = Script(ok(_body(_one(1), _one(2), _one(3, reading="一個不要遵守規矩的老師"))))
    out = _generate(script)
    assert len(script.calls) == 1
    assert [c["warnings"] for c in out["candidates"]] == [[], [], ["looks-like-instructions"]]


def test_each_attempt_is_bounded_shorter_than_an_analysis_step():
    script = Script(ok(_body()))
    _generate(script)
    assert script.timeout == candidates.TIMEOUT < den_config.PHASE_TIMEOUT


def test_timeout_leaves_an_anomaly_warning(caplog):
    with caplog.at_level("WARNING", "hyenovel"), pytest.raises(candidates.Failed):
        _generate(Script(_failed("timeout")))
    assert "event=worker-anomaly" in caplog.text and "step=candidates" in caplog.text


def test_repair_carries_errors_and_previous_output():
    bad = _body(_one(1), _one(2), _one(1))
    script = Script(ok(bad), ok(_body()))
    _generate(script)
    _, repair = script.calls[1]
    assert "<previous_output>" in repair and "讀者1" in repair
    assert "名字重複" in repair and "保持不變" in repair


def test_unparsable_output_is_repaired_from_raw_text():
    script = Script(_unparsed("不是 JSON 的東西"), ok(_body()))
    _generate(script)
    assert "不是 JSON 的東西" in script.calls[1][1]


def test_second_gate_failure_stops_without_third_spend():
    bad = ok(_body(_one(1), _one(2)))
    script = Script(bad, bad, ok(_body()))
    with pytest.raises(candidates.Failed) as e:
        _generate(script)
    assert e.value.reason == "gate"
    assert len(script.calls) == 2


def test_runner_failure_is_not_retried():
    script = Script(_failed("usage-limit"), ok(_body()))
    with pytest.raises(candidates.Failed) as e:
        _generate(script)
    assert e.value.reason == "usage-limit"
    assert len(script.calls) == 1


def test_runner_failure_during_repair_keeps_its_reason():
    script = Script(ok(_body(_one(1))), _failed("timeout"))
    with pytest.raises(candidates.Failed) as e:
        _generate(script)
    assert e.value.reason == "timeout"


class RunFactory:
    def __init__(self, *results):
        self.script = Script(*results)

    def __call__(self, on_proc):
        return self.script


@pytest.fixture
def api(data):
    @contextmanager
    def make(*results):
        url, d = data
        factory = RunFactory(*results)
        with TestClient(den_app.create_app(url, d, run_factory=factory), base_url="http://127.0.0.1") as client:
            client.headers.update(_auth(d))
            client.script = factory.script
            yield client
    return make


def _post(client, **body):
    return client.post("/api/characters/candidates", json={"brief": "一隻老貓", **body})


def test_endpoint_returns_candidates_and_writes_nothing(api):
    with api(ok(_body())) as c:
        before = c.get("/api/characters").json()["characters"]
        r = _post(c, seed=7)
        assert r.status_code == 200
        assert r.json()["seed"] == 7 and len(r.json()["candidates"]) == 3
        assert c.get("/api/characters").json()["characters"] == before


def test_endpoint_picks_a_seed_when_none_given(api):
    with api(ok(_body())) as c:
        out = _post(c).json()
        assert out["seed"] < 2**53
        assert out["candidates"][0]["axes"] == list(candidates.positions(out["seed"])[0])


@pytest.mark.parametrize("brief", ["", "   ", "長" * 2001])
def test_endpoint_rejects_bad_brief_without_spending(api, brief):
    with api() as c:
        assert _post(c, brief=brief).status_code == 422
        assert c.script.calls == []


def test_endpoint_reports_failure_with_reason_and_frees_the_slot(api):
    with api(_failed("usage-limit"), ok(_body())) as c:
        r = _post(c)
        assert r.status_code == 502
        assert r.json()["code"] == "candidates-failed"
        assert r.json()["params"] == {"reason": "usage-limit"}
        assert _post(c).status_code == 200


def test_health_reports_busy_while_generating_so_shim_does_not_restart_den(api):
    with api() as c:
        assert c.get("/api/health").json()["busy"] is False
        c.app.state.candidates_busy = True
        assert c.get("/api/health").json()["busy"] is True


def test_endpoint_refuses_second_batch_while_one_is_running(api):
    with api() as c:
        c.app.state.candidates_busy = True
        r = _post(c)
        assert r.status_code == 409 and r.json()["code"] == "candidates-busy"
        assert c.script.calls == []
