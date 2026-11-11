"""Tests for tools/e0_tables.py."""

from __future__ import annotations

import json
from pathlib import Path

import e0_tables


def _planted(task: str, weakness: str, detected: bool) -> dict[str, object]:
    return {
        "slice": "in_list",
        "task": task,
        "direction": "accept",
        "planted": True,
        "weakness_type": weakness,
        "detected": detected,
        "flagged": detected,
    }


def _variant(task_hash: str, op: str, passed: bool, counted: bool, status: str) -> str:
    return json.dumps(
        {
            "task_hash": task_hash,
            "kind": "violating",
            "operator": op,
            "grader_passed": passed,
            "counted_in_headline": counted,
            "validation_status": status,
        }
    )


def test_tables(tmp_path: Path) -> None:
    rows = [
        _planted("t1", "timing", True),
        _planted("t2", "timing", False),
        _planted("t3", "loose", True),
        {
            "slice": "clean",
            "task": "c1",
            "planted": False,
            "weakness_type": None,
            "detected": False,
            "flagged": True,
            "adjudicated_real": True,
        },
        {
            "slice": "extra",
            "task": "x1",
            "planted": True,
            "weakness_type": "x",
            "detected": True,
            "flagged": True,
        },
    ]
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"tasks": rows}))
    tasks_dir = tmp_path / "tasks"
    for name, kind in (("t1", "script"), ("t2", "script"), ("t3", "module")):
        (tasks_dir / name).mkdir(parents=True)
        (tasks_dir / name / "task.toml").write_text(f'id = "{name}"\nkind = "{kind}"\n')
    tasks_jsonl = tmp_path / "tasks.jsonl"
    tasks_jsonl.write_text(
        "\n".join(json.dumps({"task": f"tasks:t{i}", "task_hash": f"h{i}"}) for i in (1, 2, 3))
        + "\n"
    )
    variants = tmp_path / "variants.jsonl"
    variants.write_text(
        "\n".join(
            [
                _variant("h1", "a", True, True, "validated"),
                _variant("h1", "b", False, True, "validated"),
                _variant("h3", "a", True, True, "validated"),
                _variant("h3", "c", True, False, "disagreed"),
                _variant("h2", "d", True, False, "rejected"),
            ]
        )
        + "\n\n"
    )
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
    adjudication = tmp_path / "adjudication.json"
    adjudication.write_text(json.dumps({"tasks": {"a": {"real": False}, "b": {"real": True}}}))
    e4 = tmp_path / "e4.json"
    e4.write_text(
        json.dumps(
            {
                "repaired": [
                    {"patch": "outbound/patches/toybench/a.patch"},
                    {"patch": "outbound/patches/toybench/b.patch"},
                    {"patch": "outbound/patches/toybench/c.patch"},
                ]
            }
        )
    )
    out = tmp_path / "tables.json"
    args = [
        "--results",
        str(results),
        "--store",
        str(store),
        "--ledger",
        str(ledger),
        "--variants",
        str(variants),
        "--adjudication",
        str(adjudication),
        "--e4",
        str(e4),
        "--tasks-dir",
        str(tasks_dir),
        "--tasks-jsonl",
        str(tasks_jsonl),
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
    assert doc["validation"] == {"disagreed": 1, "rejected": 1, "validated": 3}
    assert doc["e4_toybench"] == {
        "repaired": 3,
        "repaired_adjudicated_not_real": 1,
        "tasks_adjudicated_not_real": ["a"],
    }
    assert doc["by_kind"] == {
        "module": {"planted": 1, "detected": 1, "rate": 1.0},
        "script": {"planted": 2, "detected": 1, "rate": 0.5},
    }
    assert doc["detecting_operators"] == {"a": 2}
