#!/usr/bin/env python3
"""E6 lint validity (prereg/0002): AUC of the lint score for a mutation score below 0.8.

For every scorable task (``stable_pass``) with a defined mutation score in the given
audits, the lint score (``graderproof.lint.lint_task``, the number of distinct smell
rules that fire on the task's grader and text) is the predictor and "mutation score
below 0.8" the outcome. The AUC (Mann-Whitney, ties counted half) gets a percentile task
bootstrap interval (``graderproof.stats``; prereg 0002: B = 2000, seed 2031). H6 is
supported when the interval's lower bound exceeds 0.5.

Writes ``<out>/summary.json`` (aggregates) and ``<out>/rows.jsonl`` (one row per task,
task hashes only). Run it in the environment of the frozen E1 worktree so that the lint
code is the preregistered one.

Usage::

    python3 tools/e6_lint.py --audit tau2=artifacts/audit/tau2:runs/e1/tau2 \
        --audit bfcl=artifacts/audit/bfcl:runs/e1/bfcl --out artifacts/e6
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

THRESHOLD = 0.8


def rows_for(name: str, audit: Path, tasks_dir: Path) -> list[dict[str, Any]]:
    """Lint score and mutation score for every scorable task of one audit."""
    from graderproof.adapters.toybench import ToybenchAdapter
    from graderproof.lint import lint_task

    tasks = {t.key_hash: t for t in ToybenchAdapter().load(tasks_dir)}
    out = []
    for line in (audit / "tasks.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        ms = row.get("mutation_score")
        if row.get("determinism") != "stable_pass" or ms is None:
            continue
        task = tasks.get(str(row["task_hash"]))
        if task is None:
            raise SystemExit(f"e6: {name}: no task directory for {row['task_hash'][:12]}")
        out.append(
            {
                "benchmark": name,
                "task_hash": row["task_hash"],
                "lint_score": lint_task(task).score,
                "mutation_score": ms,
                "low_mutation_score": ms < THRESHOLD,
            }
        )
    return out


def analyse(rows: Sequence[dict[str, Any]], seed: int, replicates: int) -> dict[str, Any]:
    """AUC point estimate and bootstrap interval over tasks."""
    from graderproof.lint import auc
    from graderproof.stats import bootstrap_ci

    scores = [float(r["lint_score"]) for r in rows]
    low = [bool(r["low_mutation_score"]) for r in rows]

    def stat(idx: Sequence[int]) -> float | None:
        return auc([scores[i] for i in idx], [low[i] for i in idx])

    point = auc(scores, low)
    ci = bootstrap_ci(len(rows), stat, seed, replicates)
    if point is None or ci is None:
        return {
            "n_tasks": len(rows),
            "n_low_mutation_score": sum(low),
            "auc": None,
            "h6_supported": None,
        }
    return {
        "n_tasks": len(rows),
        "n_low_mutation_score": sum(low),
        "auc": {"point": point, "ci": [ci[0], ci[1]], "n": len(rows)},
        "h6_supported": ci[0] > 0.5,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    from graderproof.audit import AuditConfig, provenance

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--audit", action="append", required=True, metavar="NAME=AUDIT_DIR:TASKS_DIR")
    ap.add_argument("--out", type=Path, default=Path("artifacts/e6"))
    ap.add_argument("--seed", type=int, default=2031)
    ap.add_argument("--replicates", type=int, default=2000)
    ap.add_argument("--prereg", default="prereg/0002-e1e2-audit.md")
    args = ap.parse_args(argv)
    rows: list[dict[str, Any]] = []
    for spec in args.audit:
        name, _, dirs = spec.partition("=")
        audit, _, tasks = dirs.partition(":")
        if not name or not audit or not tasks:
            raise SystemExit(f"--audit expects NAME=AUDIT_DIR:TASKS_DIR, got {spec!r}")
        rows += rows_for(name, Path(audit), Path(tasks))
    result = analyse(rows, args.seed, args.replicates)
    summary = {
        "schema": "graderproof.e6/1",
        "prereg": args.prereg,
        "threshold": THRESHOLD,
        "benchmarks": sorted({r["benchmark"] for r in rows}),
        "bootstrap": {"seed": args.seed, "B": args.replicates, "alpha": 0.05},
        **result,
        "provenance": provenance(AuditConfig(), {"tool": "tools/e6_lint.py"}),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "rows.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    )
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"e6: {len(rows)} tasks, AUC {result['auc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
