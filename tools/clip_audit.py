#!/usr/bin/env python3
"""Which model-request fields were clipped, store by store (DECISIONS.md D38, prereg 0003).

graderproof's request builder once cut long strings and appended a marker of the form
``\\n[... N more chars]``. This scans the request files of each model store for that
marker and writes, per store and per request purpose and field, how many item fields
carry it and the full lengths those fields had (the kept prefix plus N). It reads
private stores but writes only counts and lengths, never content, so the output can be
committed (non-negotiable 14). Usage::

    python3 tools/clip_audit.py --store e0=artifacts/model_calls/e0 \\
        --store tau2=private/model_calls/tau2 --out artifacts/e1/clip_audit.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

MARKER = re.compile(r"\n\[\.\.\. (\d+) more chars\]$")
#: Keys whose values map file paths to contents: the path is not a field name.
FILE_MAPS = frozenset(
    {"files", "reference_solution", "workspace_files", "modified_files", "initial_workspace"}
)


def _walk(path: str, value: Any, out: dict[str, list[int]]) -> None:
    if isinstance(value, str):
        m = MARKER.search(value)
        if m:
            out.setdefault(path, []).append(m.start() + int(m.group(1)))
    elif isinstance(value, dict):
        last = path.rsplit(".", 1)[-1]
        for key, sub in value.items():
            _walk(f"{path}.{'*' if last in FILE_MAPS else key}", sub, out)
    elif isinstance(value, list):
        for sub in value:
            _walk(f"{path}[]", sub, out)


def audit_store(store: Path) -> dict[str, Any]:
    """Clip counts for one store."""
    requests = sorted((store / "requests").glob("*.json"))
    n_items = 0
    clipped: dict[str, list[int]] = {}
    for path in requests:
        req = json.loads(path.read_text(encoding="utf-8"))
        items = req.get("items") or []
        n_items += len(items)
        for item in items:
            _walk(str(req.get("purpose")), item, clipped)
    return {
        "n_requests": len(requests),
        "n_items": n_items,
        "clipped": {
            field: {"n": len(lengths), "full_min": min(lengths), "full_max": max(lengths)}
            for field, lengths in sorted(clipped.items())
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", action="append", required=True, help="NAME=PATH")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    doc: dict[str, Any] = {"schema": "graderproof.clip_audit/1", "stores": {}}
    for spec in args.store:
        name, _, path = spec.partition("=")
        doc["stores"][name] = audit_store(Path(path))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, s in doc["stores"].items():
        n = sum(f["n"] for f in s["clipped"].values())
        print(f"clip-audit: {name}: {n} clipped fields in {s['n_items']} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
