"""Tests for tools/store_manifest.py."""

from __future__ import annotations

import json
from pathlib import Path

import store_manifest as sm


def test_manifest_lists_hashes_without_content(tmp_path: Path) -> None:
    store = tmp_path / "store"
    (store / "requests").mkdir(parents=True)
    (store / "responses").mkdir()
    secret = "SECRET VARIANT CONTENT"
    for h, items in (("aa", 2), ("bb", 1)):
        req = {"purpose": "review", "prompt_version": "review/v1", "items": [secret] * items}
        (store / "requests" / f"{h}.json").write_text(json.dumps(req))
    (store / "responses" / "aa.json").write_text(json.dumps({"items": {"x": secret}}))
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"request": "aa"}) + "\n\n")
    out = tmp_path / "public"
    assert sm.main(["--store", str(store), "--ledger", str(ledger), "--out", str(out)]) == 0
    text = (out / "MANIFEST.json").read_text()
    assert secret not in text
    doc = json.loads(text)
    assert doc["n_requests"] == 2 and doc["n_ingested"] == 1
    first, second = doc["requests"]
    assert first["request"] == "aa" and first["n_items"] == 2 and first["ingested"]
    assert first["response_sha256"] == sm.sha256_file(store / "responses" / "aa.json")
    assert second["response_sha256"] is None and not second["ingested"]
    assert sm.manifest(store, tmp_path / "missing.jsonl")["n_ingested"] == 0
