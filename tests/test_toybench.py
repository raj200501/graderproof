"""Tests for the toybench adapter, the in-sandbox runners, and the Runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graderproof import _runners
from graderproof.adapters import Execution, language_of
from graderproof.adapters.toybench import (
    ToybenchAdapter,
    _read_trajectory,
    interpreter,
    read_json_nofollow,
    read_nofollow,
    snapshot,
)
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


def test_data_kind_with_extra_env(tmp_path: Path) -> None:
    d = tmp_path / "bench" / "calls"
    for sub in ("solution", "grader", "support"):
        (d / sub).mkdir(parents=True)
    (d / "task.toml").write_text(
        'id = "calls"\nkind = "data"\nthird_party = true\n[grader]\nentry = "grade.sh"\n'
    )
    (d / "instruction.md").write_text("Call add(2, 3).")
    (d / "solution" / "trajectory.json").write_text('[{"tool": "add", "args": {"a": 2, "b": 3}}]\n')
    (d / "support" / "run_solution.sh").write_text(
        'mkdir -p .gp\ncp "$GP_SOLUTION_DIR/trajectory.json" .gp/trajectory.json\n'
        'echo "{\\"tag\\": \\"$GP_TAG\\"}" > .gp/state.json\n'
    )
    (d / "grader" / "grade.sh").write_text(
        'grep -q \'"a": 2\' .gp/trajectory.json && [ "$GP_TAG" = x ]\n'
    )
    adapter = ToybenchAdapter(extra_env={"GP_TAG": "x"})
    task = adapter.load(tmp_path / "bench")[0]
    assert task.metadata["trusted_local"] is False
    assert adapter.mutable_files(task) == {"trajectory.json": "trajectory"}
    ex = adapter.execute(task, task.reference_solution, LocalSandbox())
    assert ex.grade.passed, ex.grade.stderr
    assert ex.outcome.state == {"tag": "x"}
    assert ex.outcome.trajectory[0]["tool"] == "add"
    bad = adapter.execute(
        task, {"trajectory.json": '[{"tool": "add", "args": {"a": 3}}]'}, LocalSandbox()
    )
    assert not bad.grade.passed


def test_snapshot_never_follows_links(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET\n")
    ws = tmp_path / "ws"
    (ws / "sub").mkdir(parents=True)
    (ws / "ok.txt").write_text("fine\n")
    (ws / "sub" / "deep.txt").write_text("deep\n")
    (ws / "blob.dat").write_bytes(b"\0\1\2")
    (ws / "link.txt").symlink_to(secret)
    (ws / "dirlink").symlink_to(tmp_path)
    (ws / "dangling").symlink_to(tmp_path / "missing")
    snap = snapshot(ws)
    assert snap["ok.txt"] == "fine\n" and snap["sub/deep.txt"] == "deep\n"
    assert snap["link.txt"] == f"<symlink to {secret}>"
    assert snap["dirlink"] == f"<symlink to {tmp_path}>"
    assert snap["dangling"] == f"<symlink to {tmp_path / 'missing'}>"
    assert snap["blob.dat"] == "<binary 3 bytes>"
    assert "TOP SECRET" not in json.dumps(snap)
    assert read_nofollow(ws / "ok.txt") == b"fine\n"
    assert read_nofollow(ws / "link.txt") is None and read_nofollow(ws / "nope") is None
    (ws / "r.json").write_text('{"a": 1}')
    (ws / "bad.json").write_text("{")
    (ws / "r-link.json").symlink_to(ws / "r.json")
    assert read_json_nofollow(ws / "r.json") == {"a": 1}
    assert read_json_nofollow(ws / "bad.json") is None
    assert read_json_nofollow(ws / "r-link.json") is None


def test_trajectory_reader_refuses_links_and_junk(tmp_path: Path) -> None:
    state_dir = tmp_path / ".gp"
    state_dir.mkdir()
    (state_dir / "state.json").write_text("[1, 2]")
    (state_dir / "trajectory.json").write_text('[{"tool": "a"}, 3, "x"]')
    assert _read_trajectory(state_dir) == (None, [{"tool": "a"}])
    (state_dir / "state.json").write_text('{"ok": true}')
    (state_dir / "trajectory.json").write_text('{"tool": "a"}')
    assert _read_trajectory(state_dir) == ({"ok": True}, [])
    linked = tmp_path / "linked"
    linked.symlink_to(state_dir)
    assert _read_trajectory(linked) == (None, [])


def test_third_party_task_cannot_claim_trusted_local(tmp_path: Path) -> None:
    d = tmp_path / "bench" / "calls"
    for sub in ("solution", "grader", "support"):
        (d / sub).mkdir(parents=True)
    (d / "task.toml").write_text(
        'id = "calls"\nkind = "data"\nthird_party = true\n[grader]\nentry = "grade.sh"\n'
        '[metadata]\ntrusted_local = true\nsource = "x"\n'
    )
    (d / "instruction.md").write_text("Call add(2, 3).")
    (d / "solution" / "trajectory.json").write_text('[{"tool": "add"}]\n')
    (d / "support" / "run_solution.sh").write_text("true\n")
    (d / "grader" / "grade.sh").write_text("true\n")
    task = ToybenchAdapter().load(tmp_path / "bench")[0]
    assert task.metadata["trusted_local"] is False and task.metadata["source"] == "x"
    with pytest.raises(SandboxPolicyError):
        Runner(ToybenchAdapter(), UnshareSandbox()).execute(task, task.reference_solution)
