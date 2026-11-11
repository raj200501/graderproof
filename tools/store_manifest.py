#!/usr/bin/env python3
"""Public hash manifest of a private model store (DECISIONS.md D35).

Model calls about unpatched third-party tasks contain variants, so their store lives
under ``private/``. This writes ``<out>/MANIFEST.json``: for every request in the store,
its hash, purpose, prompt version, item count, and the SHA-256 of the request file and
(when present) the response file, plus whether the ledger records its ingestion. The
manifest reveals no request or response content, and lets anyone holding the private
files check them against the tracked hashes.

Usage::

    python3 tools/store_manifest.py --store private/model_calls/tau2 \
        --ledger artifacts/usage/ledger.jsonl --out artifacts/model_calls/tau2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(store: Path, ledger: Path) -> dict[str, Any]:
    """The manifest document for ``store``."""
    ingested: set[str] = set()
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("request"):
                    ingested.add(str(row["request"]))
    rows = []
    for req in sorted((store / "requests").glob("*.json")):
        data = json.loads(req.read_text(encoding="utf-8"))
        resp = store / "responses" / req.name
        rows.append(
            {
                "request": req.stem,
                "purpose": data.get("purpose"),
                "prompt_version": data.get("prompt_version"),
                "n_items": len(data.get("items", [])),
                "request_sha256": sha256_file(req),
                "response_sha256": sha256_file(resp) if resp.exists() else None,
                "ingested": req.stem in ingested,
            }
        )
    return {
        "schema": "graderproof.store_manifest/1",
        "store": store.as_posix(),
        "private": True,
        "n_requests": len(rows),
        "n_ingested": sum(1 for r in rows if r["ingested"]),
        "requests": rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--ledger", type=Path, default=Path("artifacts/usage/ledger.jsonl"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    doc = manifest(args.store, args.ledger)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "MANIFEST.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"store-manifest: {doc['n_requests']} requests, {doc['n_ingested']} ingested")
    return 0


if __name__ == "__main__":
    sys.exit(main())
