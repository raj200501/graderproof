"""Tests for tools/e6_lint.py (E6 lint AUC)."""

from __future__ import annotations

import json
from pathlib import Path

import e6_lint
import pytest

from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.lint import lint_task

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo"


def test_e6_on_demo_tasks(tmp_path: Path) -> None:
    tasks = ToybenchAdapter().load(DEMO)
    audit = tmp_path / "audit"
    audit.mkdir()
    scores = [0.4, 0.95, 1.0, 0.6, None]
    rows = []
    for t, ms in zip(tasks, scores, strict=True):
        rows.append({"task_hash": t.key_hash, "determinism": "stable_pass", "mutation_score": ms})
    rows.append({"task_hash": "f" * 64, "determinism": "flaky", "mutation_score": 0.1})
    (audit / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = tmp_path / "e6"
    args = ["--audit", f"demo={audit}:{DEMO}", "--out", str(out), "--replicates", "200"]
    assert e6_lint.main(args) == 0
    summary = json.loads((out / "summary.json").read_text())
    got = [json.loads(line) for line in (out / "rows.jsonl").read_text().splitlines()]
    assert summary["n_tasks"] == 4 and len(got) == 4  # flaky and undefined rows dropped
    assert summary["n_low_mutation_score"] == 2
    assert [r["lint_score"] for r in got] == [lint_task(t).score for t in tasks[:4]]
    est = summary["auc"]
    if est is not None:
        assert est["ci"][0] <= est["point"] <= est["ci"][1] and est["n"] == 4
    assert summary["bootstrap"] == {"seed": 2031, "B": 200, "alpha": 0.05}


def test_e6_errors(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        e6_lint.main(["--audit", "bad"])
    audit = tmp_path / "a"
    audit.mkdir()
    row = {"task_hash": "0" * 64, "determinism": "stable_pass", "mutation_score": 0.5}
    (audit / "tasks.jsonl").write_text(json.dumps(row) + "\n")
    with pytest.raises(SystemExit):
        e6_lint.main(["--audit", f"demo={audit}:{DEMO}", "--out", str(tmp_path / "o")])
    assert e6_lint.analyse([], 1, 10)["auc"] is None
