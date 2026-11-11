"""Tests for graderproof.run: cache keys and infrastructure failures (DECISIONS.md D25)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from graderproof.adapters import Execution
from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.core import GraderRun, Task
from graderproof.run import Runner, infrastructure_failure, package_fingerprint, sandbox_version
from graderproof.sandbox import Limits, LocalSandbox, Sandbox
from graderproof.spec import Outcome

TASK = Task("t", "b", "say hi", {"kind": "script"}, {"s.sh": "echo hi\n"}, ["bash", "g.sh"])


def execution(grade_status: int = 0, grade_err: str = "", out_err: str = "") -> Execution:
    grade = GraderRun("b:t", None, grade_status, grade_status == 0, "", grade_err, 0.1, "local")
    return Execution(Outcome(stderr=out_err), grade)


def test_package_fingerprint_and_sandbox_version() -> None:
    fp = package_fingerprint()
    assert len(fp) == 64 and fp == package_fingerprint()
    assert sandbox_version("local") == "" and sandbox_version("no-such-backend") == ""


def test_infrastructure_failures_are_recognized() -> None:
    assert not infrastructure_failure(execution())
    assert not infrastructure_failure(execution(1, "assertion failed"))
    assert infrastructure_failure(execution(127))
    assert infrastructure_failure(execution(1, "bwrap: Can't mount proc"))
    assert infrastructure_failure(execution(out_err="could not start solution"))


def test_cache_key_covers_limits_and_environment(tmp_path: Path) -> None:
    base = Runner(ToybenchAdapter(), LocalSandbox(), cache_dir=tmp_path)
    key = base.key(TASK, TASK.reference_solution, (), 0)
    assert key == base.key(TASK, TASK.reference_solution, (), 0)
    limited = Runner(ToybenchAdapter(), LocalSandbox(), tmp_path, Limits(timeout_s=1.0))
    assert limited.key(TASK, TASK.reference_solution, (), 0) != key
    env = Runner(ToybenchAdapter(extra_env={"X": "1"}), LocalSandbox(), cache_dir=tmp_path)
    assert env.key(TASK, TASK.reference_solution, (), 0) != key
    assert base.key(TASK, TASK.reference_solution, (), 1) != key


class FailingAdapter(ToybenchAdapter):
    """Every execution fails to start, as when the sandbox is broken."""

    def execute(
        self,
        task: Task,
        solution: Mapping[str, str],
        sandbox: Sandbox,
        probes: Sequence[Mapping[str, Any]] = (),
        limits: Limits | None = None,
        variant_id: str | None = None,
    ) -> Execution:
        return execution(127, "bwrap: setting up uid map: Permission denied")


def test_infrastructure_failures_are_not_cached(tmp_path: Path) -> None:
    trusted = Task.from_dict({**TASK.to_dict(), "metadata": {"trusted_local": True}})
    runner = Runner(FailingAdapter(), LocalSandbox(), cache_dir=tmp_path)
    runner.execute(trusted, trusted.reference_solution)
    runner.execute(trusted, trusted.reference_solution)
    assert runner.executions == 2 and runner.cache_hits == 0
    assert not list(tmp_path.rglob("*.json"))
