#!/usr/bin/env python3
"""Preregistered E1/E2 summaries per benchmark, from the banked audits (DECISIONS.md D46).

Reads ``artifacts/audit/<benchmark>/summary.json`` and ``tasks.jsonl`` for every
confirmatory audit and writes ``artifacts/e1/tables.json``. For each benchmark, over
scorable tasks (``determinism == "stable_pass"``):

- ``mutation_score``: the per-task mutation score distribution that prereg 0002 names,
  as the median and the first and third quartiles over tasks with a defined score
  (``statistics.quantiles``, ``n=4``, ``method="inclusive"``);
- ``e1`` and ``e2``: the number of tasks with a false accept or false reject, and the
  exact Clopper-Pearson 95% interval of that share (exploratory, printed beside the
  preregistered percentile bootstrap intervals of ``summary.json``);
- ``preserving_per_task``: the fewest and most counted preserving variants of a task;
- ``n_sampled`` and ``n_scorable``.

``--check`` recomputes the tables and exits 1 when the banked file differs.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from graderproof.stats import clopper_pearson

SCHEMA = "graderproof.e1_tables/1"
METHOD = {
    "scorable": 'determinism == "stable_pass"',
    "mutation_score": (
        "median and quartiles over scorable tasks with a defined score, "
        'statistics.quantiles(n=4, method="inclusive")'
    ),
    "exact_ci": "Clopper-Pearson, 95%, exploratory beside the preregistered bootstrap",
}


def flag_summary(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    """Count of scorable tasks with ``field`` true, with its exact 95% interval."""
    k = sum(1 for r in rows if r.get(field) is True)
    ci = clopper_pearson(k, len(rows))
    return {"n_flagged": k, "exact_ci": list(ci) if ci else None}


def benchmark_table(tasks: Sequence[Mapping[str, Any]], n_sampled: int) -> dict[str, Any]:
    """The table of one benchmark; raises ``ValueError`` when no task is scorable."""
    scorable = [t for t in tasks if t.get("determinism") == "stable_pass"]
    if not scorable:
        raise ValueError("no scorable task")
    scores = [float(t["mutation_score"]) for t in scorable if t.get("mutation_score") is not None]
    q1: float | None
    median: float | None
    q3: float | None
    if len(scores) >= 2:
        q1, median, q3 = statistics.quantiles(scores, n=4, method="inclusive")
    else:
        q1 = median = q3 = scores[0] if scores else None
    preserving = [int(t.get("n_counted_preserving") or 0) for t in scorable]
    return {
        "n_sampled": n_sampled,
        "n_scorable": len(scorable),
        "mutation_score": {"n": len(scores), "median": median, "q1": q1, "q3": q3},
        "e1": flag_summary(scorable, "false_accept"),
        "e2": flag_summary(scorable, "false_reject"),
        "preserving_per_task": {"min": min(preserving), "max": max(preserving)},
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSON objects, one per non-blank line."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def tables(root: Path) -> dict[str, Any]:
    """Tables for every confirmatory audit under ``root/artifacts/audit``."""
    out: dict[str, Any] = {}
    base = root / "artifacts" / "audit"
    for d in sorted(p for p in base.iterdir() if (p / "summary.json").is_file()):
        summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        if not (isinstance(summary, dict) and summary.get("confirmatory") is True):
            continue
        out[d.name] = benchmark_table(read_jsonl(d / "tasks.jsonl"), int(summary["n_sampled"]))
    return {"schema": SCHEMA, "method": METHOD, "benchmarks": out}


def main(argv: Sequence[str] | None = None) -> int:
    """Command line; returns the exit status."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    ap.add_argument("--out", type=Path, default=Path("artifacts/e1/tables.json"))
    ap.add_argument("--check", action="store_true", help="fail if the banked file differs")
    args = ap.parse_args(argv)
    doc = tables(args.root)
    out = args.out if args.out.is_absolute() else args.root / args.out
    if args.check:
        banked = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None
        if banked != doc:
            print(f"e1_tables: {out} differs from its recomputation", file=sys.stderr)
            return 1
        print(f"e1_tables: {out} matches its recomputation")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"e1_tables: wrote {out} ({len(doc['benchmarks'])} benchmarks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
