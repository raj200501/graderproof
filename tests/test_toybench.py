"""Tests for the toybench adapter, the in-sandbox runners, and the Runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graderproof import _runners
from graderproof.adapters import Execution, language_of
from graderproof.adapters.toybench import ToybenchAdapter, interpreter, snapshot
from graderproof.core import Determinism, Task
from graderproof.run import Runner, SandboxPolicyError
from graderproof.sandbox import LocalSandbox, Sandbox, UnshareSandbox, best_sandbox
from graderproof.spec import probe_key

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo"


@pytest.fixture(scope="module")
def tasks() -> dict[str, Task]:
    return {t.id: t for t in ToybenchAdapter().load(DEMO)}


def sandbox() -> Sandbox:
    return best_sandbox(require_write_isolation=False) or LocalSandbox()


def test_load_demo_tasks(tasks: dict[str, Task]) -> None:
    assert sorted(tasks) == ["classify", "greeting", "refund", "status-json", "word-stats"]
    t = tasks["word-stats"]
    assert t.environment["kind"] == "script"
    assert "solve.py" in t.reference_solution
    assert t.metadata["trusted_local"] is True


def test_reference_solutions_pass_their_graders(tasks: dict[str, Task]) -> None:
    adapter = ToybenchAdapter()
    for t in tasks.values():
        ex = adapter.execute(t, t.reference_solution, sandbox())
        assert ex.grade.passed, (t.id, ex.grade.stderr)


def test_script_outcome_and_broken_solution(tasks: dict[str, Task]) -> None:
    adapter = ToybenchAdapter()
    t = tasks["word-stats"]
    ex = adapter.execute(t, t.reference_solution, sandbox())
    assert json.loads(ex.outcome.files["stats.json"]) == {"lines": 3, "words": 9}
    broken = {"solve.py": "raise SystemExit(4)\n"}
    ex2 = adapter.execute(t, broken, sandbox(), variant_id="v1")
    assert ex2.outcome.exit_status == 4
    assert not ex2.grade.passed
    assert ex2.grade.variant_id == "v1"
    assert Execution.from_dict(ex2.to_dict()) == ex2


def test_module_probes(tasks: dict[str, Task]) -> None:
    t = tasks["classify"]
    probes: list[dict[str, object]] = [
        {"function": "classify", "args": [9]},
        {"function": "missing", "args": []},
    ]
    ex = ToybenchAdapter().execute(t, t.reference_solution, sandbox(), probes)
    assert ex.outcome.probes[probe_key(probes[0])] == {"ok": True, "value": "fizz"}
    assert ex.outcome.probes[probe_key(probes[1])]["ok"] is False


def test_trajectory_outcome(tasks: dict[str, Task]) -> None:
    t = tasks["refund"]
    ex = ToybenchAdapter().execute(t, t.reference_solution, sandbox())
    assert ex.outcome.state is not None
    assert ex.outcome.state["orders"]["A17"]["status"] == "refunded"
    assert [c["tool"] for c in ex.outcome.trajectory][-1] == "send_receipt"


def test_runner_cache_precheck_and_policy(tasks: dict[str, Task], tmp_path: Path) -> None:
    adapter = ToybenchAdapter()
    runner = Runner(adapter, LocalSandbox(), cache_dir=tmp_path)
    t = tasks["greeting"]
    det, runs = runner.precheck(t, 2)
    assert det is Determinism.STABLE_PASS and len(runs) == 2
    assert runner.executions == 2
    runner.precheck(t, 2)
    assert runner.cache_hits == 2
    third = Task.from_dict({**t.to_dict(), "metadata": {}})
    with pytest.raises(SandboxPolicyError):
        Runner(adapter, UnshareSandbox()).execute(third, third.reference_solution)


def test_language_and_interpreter_helpers(tmp_path: Path) -> None:
    assert language_of("a/b.py") == "python"
    assert language_of("x.sh") == "shell"
    assert language_of("trajectory.json") == "trajectory"
    assert language_of("d.json") == "json"
    assert language_of("README") == "text"
    assert interpreter("x.py")[0] == "python3"
    assert interpreter("x.sh")[0] == "bash"
    (tmp_path / ".gp").mkdir()
    (tmp_path / ".gp" / "s.json").write_text("{}")
    (tmp_path / "bin").write_bytes(b"\0\1")
    (tmp_path / "t.txt").write_text("t")
    snap = snapshot(tmp_path)
    assert snap == {"bin": "<binary 2 bytes>", "t.txt": "t"}


def test_unknown_kind_rejected(tmp_path: Path) -> None:
    d = tmp_path / "bench" / "bad"
    d.mkdir(parents=True)
    (d / "task.toml").write_text('kind = "weird"\n')
    (d / "instruction.md").write_text("x")
    with pytest.raises(ValueError):
        ToybenchAdapter().load(tmp_path / "bench")


def test_runners_in_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mod_gp_test.py").write_text(
        "def f(x):\n    return {x, 1}, (x,)\n\ndef boom():\n    raise ValueError('no')\n"
    )
    res = _runners.run_probes("mod_gp_test", [{"function": "f", "args": [2]}, {"function": "boom"}])
    values = list(res.values())
    assert values[0] == {"ok": True, "value": [[1, 2], [2]]}
    assert values[1]["ok"] is False and "ValueError" in values[1]["error"]
    assert _runners.run_probes("no_such_module_gp", [{"function": "f"}])
    assert _runners.jsonable(object())["__repr__"].startswith("<object")
    env = tmp_path / "env.py"
    env.write_text(
        "def initial_state():\n    return {'n': 0}\n\n"
        "def inc(s, by):\n    s['n'] += by\n    return s['n']\n\n"
        "TOOLS = {'inc': inc}\n"
    )
    state, log = _runners.run_trajectory(
        env, [{"tool": "inc", "args": {"by": 2}}, {"tool": "nope"}, {"tool": "inc", "args": {}}]
    )
    assert state == {"n": 2}
    assert log[0]["result"] == 2 and "unknown tool" in log[1]["error"] and "error" in log[2]
    traj = tmp_path / "t.json"
    traj.write_text(json.dumps([{"tool": "inc", "args": {"by": 1}}]))
    assert _runners.main(["trajectory", str(env), str(traj), str(tmp_path / "out")]) == 0
    assert json.loads((tmp_path / "out" / "state.json").read_text()) == {"n": 1}
    (tmp_path / "bad.py").write_text("raise RuntimeError('x')\n")
    assert (
        _runners.main(["trajectory", str(tmp_path / "bad.py"), str(traj), str(tmp_path / "o2")])
        == 1
    )
    probes = tmp_path / "p.json"
    probes.write_text(json.dumps([{"function": "f", "args": [3]}]))
    assert _runners.main(["probe", "mod_gp_test", str(probes), str(tmp_path / "r.json")]) == 0
    assert _runners.main(["bogus"]) == 2
