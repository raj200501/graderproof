"""Tests for graderproof.lint (static grader smells)."""

from __future__ import annotations

from pathlib import Path

import pytest

from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.core import Task
from graderproof.lint import LintResult, Smell, auc, lint_task

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo"


def task(
    grader: str,
    instructions: str = "Write out.txt.",
    kind: str = "script",
    ws: dict[str, str] | None = None,
) -> Task:
    env = {"kind": kind, "grader_files": {"grade.sh": grader}, "workspace_files": ws or {}}
    return Task("t", "b", instructions, env, {"solve.sh": "x"}, ["bash", "grader/grade.sh"])


def rules(t: Task) -> set[str]:
    return {s.rule for s in lint_task(t).smells}


def test_demo_smells() -> None:
    found = {t.id: rules(t) for t in ToybenchAdapter().load(DEMO)}
    assert found["word-stats"] == {"membership"}
    assert found["status-json"] == {"exact-text"}
    assert {"outcome-only-process", "membership"} <= found["refund"]
    assert found["classify"] == {"few-checks"}
    assert found["greeting"] == set()


def test_existence_only_and_reads() -> None:
    assert "existence-only" in rules(task("[ -f out.txt ] || exit 1\n"))
    assert "existence-only" not in rules(task("[ -f out.txt ] || exit 1\ngrep -qx hi out.txt\n"))
    py = task(
        'from pathlib import Path\nimport sys\nsys.exit(0 if Path("out.json").exists() else 1)\n'
    )
    assert "existence-only" in rules(py)


def test_exit_code_only() -> None:
    assert "exit-code-only" in rules(task("if bash solve.sh; then exit 0; fi\nexit 1\n"))
    assert "exit-code-only" not in rules(task('out=$(bash solve.sh)\n[ "$out" = 4 ]\n'))


def test_loose_exact_timing_and_writable() -> None:
    assert "loose-match" in rules(
        task("python3 -c \"import sys; print(open('o').read().lower())\"\n")
    )
    assert "exact-text" in rules(task('[ "$(cat out.txt)" = "42" ]\n'))
    assert "timing" in rules(task("start=$SECONDS\nbash s.sh\n[ $((SECONDS-start)) -lt 1 ]\n"))
    writable = task("diff out.txt expected_out.txt\n", ws={"expected_out.txt": "1\n"})
    assert "agent-writable-expected" in rules(writable)
    assert "agent-writable-expected" not in rules(task("diff out.txt expected_out.txt\n"))


def test_process_rule_needs_an_unobserved_process() -> None:
    text = "Back up config.ini before editing it, then set debug = false."
    assert "outcome-only-process" in rules(task("grep -qx 'debug = false' config.ini\n", text))
    observed = task("[ -f config.ini.bak ] && grep -qx 'debug = false' config.ini\n", text)
    assert "outcome-only-process" not in rules(observed)


def test_few_checks_only_for_module_graders() -> None:
    many = "\n".join(f"assert f({i}) == {i}" for i in range(6))
    assert "few-checks" not in rules(task(many, kind="module"))
    assert "few-checks" in rules(task("assert f(1) == 1\n", kind="module"))
    assert "few-checks" not in rules(task("assert f(1) == 1\n"))


def test_score_and_serialization() -> None:
    r = LintResult("b:t", [Smell("a", "x"), Smell("a", "y"), Smell("b", "z", ("l",))])
    assert r.score == 2
    assert r.to_dict()["smells"][2] == {"rule": "b", "detail": "z", "lines": ["l"]}


def test_auc() -> None:
    assert auc([3, 2, 1, 0], [True, True, False, False]) == 1.0
    assert auc([1, 1], [True, False]) == 0.5
    assert auc([0, 1], [True, False]) == 0.0
    assert auc([1], [True]) is None
    with pytest.raises(ValueError):
        auc([1, 2], [True])
