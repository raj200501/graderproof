#!/usr/bin/env python3
"""Budget report (`make budget`, docs/BUILD_BRIEF.md section 8).

Reads budget.toml and the usage ledgers, then prints cash spent and per-day usage
against every cap. Exit status 1 if cash is not exactly zero or any cap was
exceeded on any day.

Ledgers:
* ``artifacts/usage/ledger.jsonl``: one line per model call from the client wrapper,
  ``{"utc", "kind", "backend", "model", "turns", "cash_usd", "plan_equivalent_usd", ...}``
  where ``kind`` is ``agent_run``, ``single_call``, ``review_run``, or ``local``.
* ``artifacts/review/runs.jsonl``: one line per review run (counts as ``review_run``).

History is checked against the base caps (the ceiling); ``CAP_SHARE`` scales the caps
the wrapper enforces from now on and is shown for today.
"""

from __future__ import annotations

import json
import math
import os
import sys
import tomllib
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "artifacts" / "usage" / "ledger.jsonl"
REVIEW_RUNS = REPO / "artifacts" / "review" / "runs.jsonl"

DAILY_CAPS = {
    "agent_run": "claude_agent_runs_per_day",
    "single_call": "claude_single_calls_per_day",
    "review_run": "claude_review_runs_per_day",
}


def load_caps(path: Path) -> dict[str, Any]:
    """Parse budget.toml."""
    with path.open("rb") as fh:
        return tomllib.load(fh)


def cap_share(env: Mapping[str, str]) -> float:
    """CAP_SHARE in (0, 1]; values above 1 or unparsable fall back to 1 (never raises caps)."""
    raw = env.get("CAP_SHARE")
    if not raw:
        return 1.0
    try:
        share = float(raw)
    except ValueError:
        return 1.0
    return share if 0.0 < share <= 1.0 else 1.0


def effective_caps(caps: Mapping[str, Any], share: float) -> dict[str, int]:
    """Daily claude_* caps scaled by ``share`` (floored)."""
    return {k: math.floor(int(caps[k]) * share) for k in DAILY_CAPS.values()}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Records of a JSON-lines file; missing file means no records."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def evaluate(
    caps: Mapping[str, Any],
    ledger: Iterable[Mapping[str, Any]],
    reviews: Iterable[Mapping[str, Any]],
) -> tuple[float, dict[str, Counter[str]], list[str]]:
    """Return (cash spent, per-day counts by kind, violations)."""
    violations: list[str] = []
    if caps.get("cash_usd") != 0:
        violations.append(f"budget.toml cash_usd is {caps.get('cash_usd')!r}, must be 0")
    cash = 0.0
    per_day: dict[str, Counter[str]] = {}
    max_turns = int(caps["claude_agent_max_turns"])
    for row in ledger:
        day = str(row.get("utc", ""))[:10] or "unknown"
        kind = str(row.get("kind", "unknown"))
        per_day.setdefault(day, Counter())[kind] += 1
        cash += float(row.get("cash_usd", 0) or 0)
        if kind == "agent_run" and int(row.get("turns", 0) or 0) > max_turns:
            violations.append(f"{day}: agent run with {row.get('turns')} turns > {max_turns}")
    for row in reviews:
        day = str(row.get("utc", ""))[:10] or "unknown"
        per_day.setdefault(day, Counter())["review_run"] += 1
    if cash != 0:
        violations.append(f"cash spent {cash} != 0")
    for day, counts in sorted(per_day.items()):
        for kind, cap_name in DAILY_CAPS.items():
            if counts[kind] > int(caps[cap_name]):
                violations.append(f"{day}: {kind} {counts[kind]} > {cap_name} {caps[cap_name]}")
    return cash, per_day, violations


def main() -> int:
    caps = load_caps(REPO / "budget.toml")
    share = cap_share(os.environ)
    cash, per_day, violations = evaluate(caps, read_jsonl(LEDGER), read_jsonl(REVIEW_RUNS))
    print(f"cash_usd = {0 if cash == 0 else cash}")
    print(f"cap_share = {share}")
    eff = effective_caps(caps, share)
    for cap_name in DAILY_CAPS.values():
        print(f"cap {cap_name} = {caps[cap_name]} (effective now {eff[cap_name]})")
    print(f"cap claude_agent_max_turns = {caps['claude_agent_max_turns']}")
    print(f"cap local_model_max_params_b = {caps['local_model_max_params_b']}")
    print(f"cap disk_floor_gb = {caps['disk_floor_gb']}")
    for day, counts in sorted(per_day.items()):
        used = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        print(f"usage {day}: {used}")
    if not per_day:
        print("usage: no model calls recorded")
    for v in violations:
        print(f"VIOLATION {v}")
    print("budget: FAIL" if violations else "budget: OK (every cap respected)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
