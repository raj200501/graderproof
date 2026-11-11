"""Tests for tools/e0_tables.py."""

from __future__ import annotations

import json
from pathlib import Path

import e0_tables


def test_tables(tmp_path: Path) -> None:
    rows = [
        {
            "slice": "in_list",
            "planted": True,
            "weakness_type": "timing",
            "detected": True,
            "flagged": True,
        },
        {
            "slice": "in_list",
            "planted": True,
            "weakness_type": "timing",
            "detected": False,
            "flagged": False,
        },
        {
            "slice": "in_list",
            "planted": True,
            "weakness_type": "loose",
            "detected": True,
            "flagged": True,
        },
        {
            "slice": "clean",
            "planted": False,
            "weakness_type": None,
            "detected": False,
            "flagged": True,
            "adjudicated_real": True,
        },
        {
            "slice": "extra",
            "planted": True,
            "weakness_type": "x",
            "detected": True,
            "flagged": True,
        },
    ]
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"tasks": rows}))
    store = tmp_path / "store"
    (store / "requests").mkdir(parents=True)
    (store / "requests" / "aa.json").write_text("{}")
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps({"request": "aa", "purpose": "review"})
        + "\n"
        + json.dumps({"request": "zz"})
        + "\n\n"
    )
    out = tmp_path / "tables.json"
    args = [
        "--results",
        str(results),
        "--store",
        str(store),
        "--ledger",
        str(ledger),
        "--out",
        str(out),
    ]
    assert e0_tables.main(args) == 0
    doc = json.loads(out.read_text())
    assert doc["counted"] == {
        "n": 4,
        "planted": 3,
        "detected": 2,
        "flagged_clean": 1,
        "clean_real": 1,
    }
    assert doc["by_type"]["timing"] == {"planted": 2, "detected": 1, "rate": 0.5}
    assert doc["extra"] == {"planted": 1, "detected": 1, "rate": 1.0}
    assert doc["model_calls"] == {"total": 1, "by_purpose": {"review": 1}}
