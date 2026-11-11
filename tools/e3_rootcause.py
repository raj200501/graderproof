#!/usr/bin/env python3
"""E3 root-cause coding (prereg/0002): two independent coders for every misjudgment.

For one audited benchmark, every counted surviving violating variant, every counted
wrongly rejected preserving variant, and every task whose grader rejects or is flaky on
the reference (``graderproof.rootcause.items_from_evidence``) is coded into the section 3
taxonomy by the rule-based coder and by the model coder (prompt ``rootcause/v1``, through
the client wrapper). The build session does not resolve disagreements.

Writes ``<out>/summary.json`` (code distributions, raw agreement, Cohen's kappa, and the
confusion counts) and ``<private>/codes.jsonl`` (one row per item). Per-item rows name
variants of unpatched third-party tasks, so they stay under ``private/`` (D35); for
toybench they may be public. Run it in the environment of the frozen E1 worktree.

Usage::

    python3 tools/e3_rootcause.py --name tau2 --tasks runs/e1/tau2 \
        --evidence <main>/private/evidence/tau2 --store artifacts/model_calls/e3-tau2 \
        --ledger <main>/artifacts/usage/ledger.jsonl --out artifacts/e3/tau2 \
        --private <main>/private/e3/tau2

Exit status 0 when written, 3 when model requests are pending.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PENDING = 3


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    from graderproof.adapters.toybench import ToybenchAdapter
    from graderproof.audit import AuditConfig, provenance
    from graderproof.models import ModelClient, PendingWorkError
    from graderproof.rootcause import (
        ROOTCAUSE_PROMPT_VERSION,
        ModelCoder,
        agreement,
        items_from_evidence,
        rule_code,
    )

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True, help="benchmark name")
    ap.add_argument("--tasks", type=Path, required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--ledger", type=Path, default=Path("artifacts/usage/ledger.jsonl"))
    ap.add_argument("--budget", type=Path, default=Path("budget.toml"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--private", type=Path, required=True, help="directory for per-item codes")
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--prereg", default="prereg/0002-e1e2-audit.md")
    args = ap.parse_args(argv)

    items = []
    requirements: dict[str, dict[str, Any]] = {}
    for task in ToybenchAdapter().load(args.tasks):
        path = args.evidence / f"{task.key_hash}.json"
        if not path.exists():
            continue
        evidence = json.loads(path.read_text(encoding="utf-8"))
        for r in evidence.get("requirements", []):
            requirements[f"{task.key_hash}:{r['id']}"] = r
        items += items_from_evidence(task, evidence)
    client = ModelClient(store=args.store, ledger=args.ledger, budget=args.budget)
    model_codes: dict[str, str] = {}
    if items:
        try:
            model_codes = ModelCoder(client, batch_size=args.batch).code(items)
        except PendingWorkError as exc:
            for h in exc.hashes:
                print(f"pending {args.store / 'requests' / (h + '.json')}")
            print(f"e3: {len(exc.hashes)} model requests pending", file=sys.stderr)
            return PENDING
    rows = []
    for it in items:
        reqs = {
            key.split(":", 1)[1]: r
            for key, r in requirements.items()
            if key.startswith(f"{it.task.key_hash}:")
        }
        rows.append(
            {
                "item": it.id,
                "task_hash": it.task.key_hash,
                "direction": it.direction,
                "operator": it.operator,
                "rule_code": rule_code(it, reqs),
                "model_code": model_codes[it.id],
            }
        )
    rule = [r["rule_code"] for r in rows]
    model = [r["model_code"] for r in rows]
    summary = {
        "schema": "graderproof.e3/1",
        "benchmark": args.name,
        "prereg": args.prereg,
        "prompt_version": ROOTCAUSE_PROMPT_VERSION,
        "n_items": len(rows),
        "by_direction": dict(sorted(Counter(r["direction"] for r in rows).items())),
        "rule_codes": dict(sorted(Counter(rule).items())),
        "model_codes": dict(sorted(Counter(model).items())),
        "agreement": agreement(rule, model),
        "models": client.served_models(),
        "provenance": provenance(AuditConfig(), {"tool": "tools/e3_rootcause.py"}),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    args.private.mkdir(parents=True, exist_ok=True)
    (args.private / "codes.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    )
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"e3: {args.name}: {len(rows)} items coded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
