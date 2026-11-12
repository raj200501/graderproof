"""Tests for tools/e1_tables.py: preregistered E1/E2 summaries per benchmark (D46)."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

import e1_tables as et
import pytest

from graderproof.stats import clopper_pearson

REPO = Path(__file__).resolve().parents[1]


def task(
    score: float | None, fa: bool = False, fr: bool = False, det: str = "stable_pass", pres: int = 2
) -> dict[str, Any]:
    """A tasks.jsonl row with the fields the tables read."""
    return {
        "determinism": det,
        "false_accept": fa,
        "false_reject": fr,
        "mutation_score": score,
        "n_counted_preserving": pres,
        "task_hash": f"{len(str(score))}",
    }


def test_benchmark_table_uses_scorable_tasks_with_a_score() -> None:
    rows = [
        task(1.0, pres=1),
        task(0.5, fa=True, pres=4),
        task(0.9, fr=True, pres=3),
        task(None),  # no counted violating variant: no score
        task(0.1, fa=True, det="stable_fail"),  # unscorable: left out everywhere
    ]
    t = et.benchmark_table(rows, n_sampled=5)
    assert t["n_sampled"] == 5 and t["n_scorable"] == 4
    ms = t["mutation_score"]
    assert ms["n"] == 3
    q1, med, q3 = statistics.quantiles([1.0, 0.5, 0.9], n=4, method="inclusive")
    assert (ms["q1"], ms["median"], ms["q3"]) == (q1, med, q3)
    assert t["e1"]["n_flagged"] == 1 and t["e2"]["n_flagged"] == 1
    assert t["e1"]["exact_ci"] == list(clopper_pearson(1, 4) or ())
    assert t["preserving_per_task"] == {"min": 1, "max": 4}


def test_benchmark_table_handles_a_single_score_and_zero_flags() -> None:
    t = et.benchmark_table([task(0.75)], n_sampled=1)
    assert t["mutation_score"] == {"n": 1, "median": 0.75, "q1": 0.75, "q3": 0.75}
    assert t["e2"]["n_flagged"] == 0 and t["e2"]["exact_ci"][0] == 0.0


def test_benchmark_table_rejects_an_empty_audit() -> None:
    with pytest.raises(ValueError):
        et.benchmark_table([task(0.5, det="flaky")], n_sampled=1)


def write_audit(
    root: Path, name: str, rows: list[dict[str, Any]], confirmatory: bool = True
) -> None:
    """A minimal banked audit directory."""
    d = root / "artifacts" / "audit" / name
    d.mkdir(parents=True)
    summary = {
        "confirmatory": confirmatory,
        "prereg": "prereg/0003-e1e2-full-task-text.md",
        "n_sampled": len(rows),
    }
    (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (d / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_tables_cover_only_confirmatory_audits(tmp_path: Path) -> None:
    write_audit(tmp_path, "bench", [task(1.0), task(0.5, fa=True)])
    write_audit(tmp_path, "pilot", [task(0.2)], confirmatory=False)
    doc = et.tables(tmp_path)
    assert doc["schema"] == et.SCHEMA
    assert list(doc["benchmarks"]) == ["bench"]


def test_main_writes_and_check_detects_drift(tmp_path: Path) -> None:
    write_audit(tmp_path, "bench", [task(1.0), task(0.5, fa=True)])
    out = tmp_path / "artifacts" / "e1" / "tables.json"
    assert et.main(["--root", str(tmp_path), "--out", str(out)]) == 0
    assert et.main(["--root", str(tmp_path), "--out", str(out), "--check"]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["benchmarks"]["bench"]["n_scorable"] = 7
    out.write_text(json.dumps(doc), encoding="utf-8")
    assert et.main(["--root", str(tmp_path), "--out", str(out), "--check"]) == 1


def test_banked_tables_match_their_recomputation() -> None:
    """The committed artifacts/e1/tables.json equals a fresh run over the banked audits."""
    banked = REPO / "artifacts" / "e1" / "tables.json"
    assert json.loads(banked.read_text(encoding="utf-8")) == et.tables(REPO)
