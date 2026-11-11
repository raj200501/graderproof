#!/usr/bin/env python3
"""Stratified random sample of converted benchmark tasks for E1/E2 (prereg/0002).

For each benchmark directory of toybench-format tasks, the stratum of a task is the
first of ``[metadata] stratum``, ``category``, ``domain`` in its task.toml (or ``all``).
Stratum quotas are proportional to the frame (tasks minus exclusions) with
largest-remainder rounding (ties broken by stratum name); within a stratum, tasks are
drawn without replacement with ``random.Random(f"{benchmark}:{seed}")`` from the sorted
task ids. Strata are visited in sorted order with one generator per benchmark, so the
sample is a pure function of the frame, ``n``, and the seed.

Usage:
  python3 tools/sample.py --bench tau2=runs/tau2/tasks --bench bfcl=runs/bfcl/tasks \
      --n 40 --seed 2027 --exclude runs/pilot_ids.txt --out prereg/0002-sample.json \
      --materialize runs/e1
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import tomllib
from pathlib import Path
from typing import Any


def task_strata(root: Path) -> dict[str, str]:
    """Task id to stratum for every task directory under ``root``."""
    out: dict[str, str] = {}
    for d in sorted(p for p in root.iterdir() if (p / "task.toml").exists()):
        with (d / "task.toml").open("rb") as fh:
            meta = tomllib.load(fh)
        md = meta.get("metadata", {})
        stratum = md.get("stratum") or md.get("category") or md.get("domain") or "all"
        out[str(meta.get("id", d.name))] = str(stratum)
    return out


def quotas(sizes: dict[str, int], n: int) -> dict[str, int]:
    """Proportional allocation of ``n`` with largest-remainder rounding."""
    total = sum(sizes.values())
    if n >= total:
        return dict(sizes)
    exact = {s: n * k / total for s, k in sizes.items()}
    base = {s: math.floor(v) for s, v in exact.items()}
    left = n - sum(base.values())
    order = sorted(sizes, key=lambda s: (-(exact[s] - base[s]), s))
    for s in order[:left]:
        base[s] += 1
    return base


def stratified_sample(strata: dict[str, str], n: int, seed_key: str) -> list[str]:
    """Sorted sampled task ids."""
    by: dict[str, list[str]] = {}
    for tid, s in strata.items():
        by.setdefault(s, []).append(tid)
    q = quotas({s: len(v) for s, v in by.items()}, n)
    rng = random.Random(seed_key)
    picked: list[str] = []
    for s in sorted(by):
        picked += rng.sample(sorted(by[s]), q[s])
    return sorted(picked)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bench", action="append", required=True, metavar="NAME=DIR")
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--exclude", type=Path, help="file of task ids (NAME:id per line) to exclude")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--materialize", type=Path, help="write <dir>/<NAME>/<id> symlinks")
    args = ap.parse_args(argv)
    excluded: set[str] = set()
    if args.exclude and args.exclude.exists():
        excluded = {ln.strip() for ln in args.exclude.read_text().splitlines() if ln.strip()}
    result: dict[str, Any] = {
        "schema": "graderproof.sample/1",
        "n": args.n,
        "seed": args.seed,
        "benchmarks": {},
    }
    for spec in args.bench:
        name, _, path = spec.partition("=")
        root = Path(path)
        strata = {t: s for t, s in task_strata(root).items() if f"{name}:{t}" not in excluded}
        sample = stratified_sample(strata, args.n, f"{name}:{args.seed}")
        sizes: dict[str, int] = {}
        for s in strata.values():
            sizes[s] = sizes.get(s, 0) + 1
        result["benchmarks"][name] = {
            "frame": len(strata),
            "excluded": sorted(e.split(":", 1)[1] for e in excluded if e.startswith(f"{name}:")),
            "strata": {
                s: {"frame": k, "sampled": sum(1 for t in sample if strata[t] == s)}
                for s, k in sorted(sizes.items())
            },
            "tasks": sample,
        }
        if args.materialize:
            dest = args.materialize / name
            dest.mkdir(parents=True, exist_ok=True)
            dirs = {}
            for d in root.iterdir():
                if (d / "task.toml").exists():
                    with (d / "task.toml").open("rb") as fh:
                        dirs[str(tomllib.load(fh).get("id", d.name))] = d
            for tid in sample:
                link = dest / dirs[tid].name
                if not link.exists():
                    link.symlink_to(dirs[tid].resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for name, b in result["benchmarks"].items():
        print(f"{name}: frame {b['frame']}, sampled {len(b['tasks'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
