#!/usr/bin/env python3
"""Power analysis for the E1/E2 confirmatory tests (exact one-sided binomial, Holm).

For a benchmark audited on ``n`` sampled tasks, H0: task-level rate <= ``p0`` is
rejected when the number of flagged tasks ``x`` satisfies P(X >= x | n, p0) <= the
Holm-adjusted level. The least favourable Holm level is ``alpha / m`` for ``m``
benchmarks. This script tabulates, for each ``n``, the critical count and the power
against alternatives ``p1``, and the 95% Wilson-free worst-case half-width of a
proportion interval (1.96 * sqrt(0.25 / n)), so the preregistration can cite a banked
calculation instead of a hand-typed one.

Usage: python3 tools/power.py --out artifacts/prereg/power_e1e2.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from graderproof.stats import binomial_tail_ge  # noqa: E402


def critical_count(n: int, p0: float, level: float) -> int:
    """Smallest x with P(X >= x | n, p0) <= level (n + 1 if none)."""
    for x in range(n + 1):
        if binomial_tail_ge(x, n, p0) <= level:
            return x
    return n + 1


def table(ns: list[int], p0: float, p1s: list[float], alpha: float, m: int) -> dict[str, object]:
    """Critical counts and power for each sample size."""
    level = alpha / m
    rows = []
    for n in ns:
        k = critical_count(n, p0, level)
        rows.append(
            {
                "n": n,
                "critical_count": k,
                "size": binomial_tail_ge(k, n, p0),
                "power": {f"{p1:g}": binomial_tail_ge(k, n, p1) for p1 in p1s},
                "worst_case_half_width_95": 1.96 * math.sqrt(0.25 / n),
            }
        )
    return {"p0": p0, "alpha": alpha, "m": m, "least_favourable_level": level, "rows": rows}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ns", default="30,40,50,60,80")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--m", type=int, default=4)
    args = ap.parse_args(argv)
    ns = [int(x) for x in args.ns.split(",")]
    result = {
        "schema": "graderproof.power/1",
        "false_accept": table(ns, 0.10, [0.2, 0.3, 0.4], args.alpha, args.m),
        "false_reject": table(ns, 0.05, [0.15, 0.2, 0.3], args.alpha, args.m),
        "command": "python3 tools/power.py " + " ".join(argv),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for name in ("false_accept", "false_reject"):
        t = result[name]
        assert isinstance(t, dict)
        for r in t["rows"]:
            print(f"{name} n={r['n']} critical={r['critical_count']} power={r['power']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
