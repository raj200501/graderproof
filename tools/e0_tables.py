#!/usr/bin/env python3
"""Derived E0 tables for the report (non-negotiable 1: numbers come from artifacts by script).

Reads the banked ``artifacts/e0/results.json`` (from ``graderproof e0-score``), the E0
model store, and the usage ledger, and writes ``artifacts/e0/tables.json``:

* ``counted``: detected and planted counts over the counted slices (in_list and clean);
* ``by_type``: for every in_list weakness type, planted and detected counts and the
  detection rate; ``extra`` the same for the extra slice as a whole;
* ``model_calls``: the single calls E0 used, by purpose (ledger lines whose request file
  is in the E0 store);
* ``validation``: E0 variants by validation status (``validated``: both validators agree
  with the label; ``disagreed``: they disagree or one is unsure; ``rejected``: both agree on
  the other label), from ``artifacts/e0/variants.jsonl``;
* ``e4_toybench``: the E4 repairs on toybench whose task's E0 flag the adjudicator ruled
  not real (an E0 false positive), from the E4 summary and ``artifacts/e0/adjudication.json``;
* ``by_kind``: planted and detected counts and the detection rate for each task kind
  (``kind`` in each task's ``task.toml``), over the counted planted tasks;
* ``detecting_operators``: for each operator, the number of detected planted tasks with at
  least one counted variant from it that the grader misjudged in the planted direction (a
  violating variant accepted, or a preserving variant rejected).

Nothing here is a new statistic: every value is a count or a ratio of counts already in
the banked artifacts. Usage: ``python3 tools/e0_tables.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def validation_counts(variants: Path) -> dict[str, int]:
    """E0 variants by validation status."""
    statuses: Counter[str] = Counter()
    for line in variants.read_text(encoding="utf-8").splitlines():
        if line.strip():
            statuses[str(json.loads(line).get("validation_status"))] += 1
    return dict(sorted(statuses.items()))


def e4_cross(e4: dict[str, Any], adjudication: dict[str, Any]) -> dict[str, Any]:
    """E4 repairs whose task the E0 adjudicator ruled not a real weakness."""
    names = sorted(Path(str(r["patch"])).stem for r in e4.get("repaired", []))
    rulings = adjudication.get("tasks", {})
    not_real = [n for n in names if n in rulings and rulings[n].get("real") is False]
    return {
        "repaired": len(names),
        "repaired_adjudicated_not_real": len(not_real),
        "tasks_adjudicated_not_real": not_real,
    }


def kinds_and_operators(
    results: dict[str, Any], tasks_dir: Path, tasks_jsonl: Path, variants: Path
) -> dict[str, Any]:
    """Detection by task kind, and the operators behind the detecting variants."""
    hashes: dict[str, str] = {}
    for line in tasks_jsonl.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            hashes[str(row["task"]).split(":", 1)[-1]] = str(row["task_hash"])
    rows = [
        json.loads(line)
        for line in variants.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_kind: dict[str, dict[str, Any]] = {}
    operators: Counter[str] = Counter()
    for r in results["tasks"]:
        if r["slice"] == "extra" or not r["planted"]:
            continue
        toml = tomllib.loads((tasks_dir / str(r["task"]) / "task.toml").read_text("utf-8"))
        k = by_kind.setdefault(str(toml["kind"]), {"planted": 0, "detected": 0})
        k["planted"] += 1
        k["detected"] += int(bool(r["detected"]))
        if r["detected"]:
            want = ("violating", True) if r["direction"] == "accept" else ("preserving", False)
            operators.update(
                {
                    str(v["operator"])
                    for v in rows
                    if v["task_hash"] == hashes.get(str(r["task"]))
                    and v["counted_in_headline"]
                    and (v["kind"], v["grader_passed"]) == want
                }
            )
    for k in by_kind.values():
        k["rate"] = k["detected"] / k["planted"]
    return {
        "by_kind": dict(sorted(by_kind.items())),
        "detecting_operators": dict(sorted(operators.items())),
    }


def tables(results: dict[str, Any], store: Path, ledger: Path) -> dict[str, Any]:
    """The derived tables."""
    rows = results["tasks"]
    counted = [r for r in rows if r["slice"] != "extra"]
    planted = [r for r in counted if r["planted"]]
    by_type: dict[str, dict[str, Any]] = {}
    for r in planted:
        t = by_type.setdefault(str(r["weakness_type"]), {"planted": 0, "detected": 0})
        t["planted"] += 1
        t["detected"] += int(bool(r["detected"]))
    for t in by_type.values():
        t["rate"] = t["detected"] / t["planted"]
    extra = [r for r in rows if r["slice"] == "extra"]
    requests = {p.stem for p in (store / "requests").glob("*.json")}
    calls: Counter[str] = Counter()
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("request") in requests:
                calls[str(row.get("purpose"))] += 1
    return {
        "schema": "graderproof.e0_tables/1",
        "source": "artifacts/e0/results.json",
        "counted": {
            "n": len(counted),
            "planted": len(planted),
            "detected": sum(1 for r in planted if r["detected"]),
            "flagged_clean": sum(1 for r in counted if not r["planted"] and r["flagged"]),
            "clean_real": sum(1 for r in counted if not r["planted"] and r.get("adjudicated_real")),
        },
        "by_type": dict(sorted(by_type.items())),
        "extra": {
            "planted": len(extra),
            "detected": sum(1 for r in extra if r["detected"]),
            "rate": (sum(1 for r in extra if r["detected"]) / len(extra)) if extra else None,
        },
        "model_calls": {"total": sum(calls.values()), "by_purpose": dict(sorted(calls.items()))},
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", type=Path, default=Path("artifacts/e0/results.json"))
    ap.add_argument("--store", type=Path, default=Path("artifacts/model_calls/e0"))
    ap.add_argument("--ledger", type=Path, default=Path("artifacts/usage/ledger.jsonl"))
    ap.add_argument("--variants", type=Path, default=Path("artifacts/e0/variants.jsonl"))
    ap.add_argument("--adjudication", type=Path, default=Path("artifacts/e0/adjudication.json"))
    ap.add_argument("--e4", type=Path, default=Path("artifacts/e4/toybench/summary.json"))
    ap.add_argument("--tasks-dir", type=Path, default=Path("toybench/tasks"))
    ap.add_argument("--tasks-jsonl", type=Path, default=Path("artifacts/e0/tasks.jsonl"))
    ap.add_argument("--out", type=Path, default=Path("artifacts/e0/tables.json"))
    args = ap.parse_args(argv)
    doc = tables(json.loads(args.results.read_text(encoding="utf-8")), args.store, args.ledger)
    doc["validation"] = validation_counts(args.variants)
    doc.update(
        kinds_and_operators(
            json.loads(args.results.read_text(encoding="utf-8")),
            args.tasks_dir,
            args.tasks_jsonl,
            args.variants,
        )
    )
    doc["e4_toybench"] = e4_cross(
        json.loads(args.e4.read_text(encoding="utf-8")),
        json.loads(args.adjudication.read_text(encoding="utf-8")),
    )
    args.out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"e0-tables: {doc['counted']['detected']} of {doc['counted']['planted']} detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
