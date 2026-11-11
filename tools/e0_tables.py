#!/usr/bin/env python3
"""Derived E0 tables for the report (non-negotiable 1: numbers come from artifacts by script).

Reads the banked ``artifacts/e0/results.json`` (from ``graderproof e0-score``), the E0
model store, and the usage ledger, and writes ``artifacts/e0/tables.json``:

* ``counted``: detected and planted counts over the counted slices (in_list and clean);
* ``by_type``: for every in_list weakness type, planted and detected counts and the
  detection rate; ``extra`` the same for the extra slice as a whole;
* ``model_calls``: the single calls E0 used, by purpose (ledger lines whose request file
  is in the E0 store).

Nothing here is a new statistic: every value is a count or a ratio of counts already in
the banked artifacts. Usage: ``python3 tools/e0_tables.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any


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
    ap.add_argument("--out", type=Path, default=Path("artifacts/e0/tables.json"))
    args = ap.parse_args(argv)
    doc = tables(json.loads(args.results.read_text(encoding="utf-8")), args.store, args.ledger)
    args.out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"e0-tables: {doc['counted']['detected']} of {doc['counted']['planted']} detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
