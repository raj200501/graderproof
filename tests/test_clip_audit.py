"""Tests for tools/clip_audit.py."""

from __future__ import annotations

import json
from pathlib import Path

import clip_audit


def _request(store: Path, name: str, purpose: str, items: list[dict[str, object]]) -> None:
    (store / "requests").mkdir(parents=True, exist_ok=True)
    body = {"purpose": purpose, "items": items}
    (store / "requests" / f"{name}.json").write_text(json.dumps(body))


def test_counts_clipped_fields_without_content(tmp_path: Path) -> None:
    store = tmp_path / "s"
    clipped = "x" * 10 + "\n[... 90 more chars]"
    _request(
        store,
        "a",
        "requirements",
        [
            {"task_text": clipped, "reference_outcome": {"files": {"out.json": clipped}}},
            {"task_text": "short", "reference_outcome": {"files": {"out.json": "ok"}}},
        ],
    )
    _request(store, "b", "review", [{"task_text": "y" * 4 + "\n[... 6 more chars]"}])
    out = tmp_path / "audit.json"
    assert clip_audit.main(["--store", f"s={store}", "--out", str(out)]) == 0
    doc = json.loads(out.read_text())
    s = doc["stores"]["s"]
    assert s["n_requests"] == 2
    assert s["n_items"] == 3
    assert s["clipped"] == {
        "requirements.reference_outcome.files.*": {"n": 1, "full_min": 100, "full_max": 100},
        "requirements.task_text": {"n": 1, "full_min": 100, "full_max": 100},
        "review.task_text": {"n": 1, "full_min": 10, "full_max": 10},
    }
    assert "xxxx" not in out.read_text()


def test_empty_store(tmp_path: Path) -> None:
    out = tmp_path / "audit.json"
    assert clip_audit.main(["--store", f"none={tmp_path / 'missing'}", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["stores"]["none"] == {
        "n_requests": 0,
        "n_items": 0,
        "clipped": {},
    }
