"""Tests for tools/e0_adjudicate.py (E0 adjudication of flags that are not detections)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import e0_adjudicate as adj
import pytest

from graderproof import e0
from graderproof.core import sha256_text
from graderproof.models import ModelClient

LABELS: dict[str, dict[str, Any]] = {
    "a": {"planted": True, "slice": "in_list", "weakness_type": "w", "direction": "accept"},
    "c": {"planted": True, "slice": "in_list", "weakness_type": "w", "direction": "reject"},
    "e": {"planted": False, "slice": "clean", "weakness_type": None, "direction": None},
    "x": {"planted": True, "slice": "extra", "weakness_type": "w", "direction": "accept"},
}
BUDGET = (
    "cash_usd = 0\nclaude_agent_runs_per_day = 30\nclaude_agent_max_turns = 40\n"
    "claude_single_calls_per_day = 300\nclaude_review_runs_per_day = 6\n"
    "local_model_max_params_b = 8\ndisk_floor_gb = 8\n"
)


def row(tid: str, fa: bool = False, fr: bool = False) -> dict[str, Any]:
    key = f"tasks:{tid}"
    flags = {"false_accept": fa, "false_reject": fr, "reference_rejected": False, "flaky": False}
    return {"task": key, "task_hash": sha256_text(key), "determinism": "stable_pass", **flags}


def var(vid: str, kind: str, passed: bool, counted: bool = True) -> dict[str, Any]:
    witness: dict[str, Any] | None = None
    if kind == "violating":
        witness = {"broken": [{"requirement": "R1", "detail": "x"}]}
    if kind == "preserving":
        witness = {"held": ["R1"]}
    return {
        "id": vid,
        "kind": kind,
        "grader_passed": passed,
        "counted_in_headline": counted,
        "diff": f"diff {vid}",
        "files": {"s.sh": vid},
        "witness": witness,
    }


def setup(tmp_path: Path) -> list[str]:
    audit, tasks = tmp_path / "e0", tmp_path / "tasks"
    (audit / "evidence").mkdir(parents=True)
    rows = [row("a", fa=True), row("c", fa=True), row("e", fr=True, fa=True), row("x", fa=True)]
    (audit / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    variants = {
        "a": [var("va", "violating", True)],
        "c": [var("vc", "violating", True), var("vk", "violating", False)],
        "e": [
            var("ve1", "violating", True),
            var("ve2", "preserving", False),
            var("ve3", "preserving", True),
            var("ve4", "violating", True, counted=False),
        ],
        "x": [var("vx", "violating", True)],
    }
    for r in rows:
        tid = r["task"].split(":")[1]
        reqs = [{"id": "R1", "text": "prints ok", "checks": []}]
        ev = {"requirements": reqs, "variants": variants[tid]}
        (audit / "evidence" / f"{r['task_hash']}.json").write_text(json.dumps(ev))
        d = tasks / tid
        (d / "solution").mkdir(parents=True)
        (d / "grader").mkdir()
        (d / "instruction.md").write_text(f"task {tid}")
        (d / "solution" / "s.sh").write_text("echo ok\n")
        (d / "grader" / "g.sh").write_text("true\n")
    (tmp_path / "labels.json").write_text(json.dumps({"tasks": LABELS}))
    (tmp_path / "budget.toml").write_text(BUDGET)
    args = ["--audit", str(audit), "--labels", str(tmp_path / "labels.json")]
    args += ["--tasks", str(tasks), "--store", str(tmp_path / "store")]
    args += ["--ledger", str(tmp_path / "ledger.jsonl"), "--budget", str(tmp_path / "budget.toml")]
    return [*args, "--out", str(audit / "adjudication.json")]


def test_helpers() -> None:
    ev = {"variants": [var("v1", "violating", True), var("v2", "preserving", False)]}
    both = adj.flagged_variants(ev, {"false_accept": True, "false_reject": True})
    assert [(v["id"], v["flag"]) for v in both] == [("v1", "false accept"), ("v2", "false reject")]
    assert [v["id"] for v in adj.flagged_variants(ev, {"false_reject": True})] == ["v2"]
    w = adj.witness_text(
        {"broken": [{"requirement": "R1"}], "held": ["R2"]}, {"R1": "a", "R2": "b"}
    )
    assert w == {
        "broken": [{"requirement": "R1", "requirement_text": "a"}],
        "held": [{"requirement": "R2", "requirement_text": "b"}],
    }
    assert adj.witness_text(None, {}) is None
    out = adj.rulings(
        {"t": ["v1", "v2"], "u": ["v3"], "z": []},
        {
            "v1": {"verdict": "does-not-validate", "reason": "fine"},
            "v2": {"verdict": "validates", "reason": "broken"},
            "v3": {"verdict": "does-not-validate", "reason": "fine"},
        },
    )
    assert out["t"]["real"] and out["t"]["reason"] == "broken"
    assert not out["u"]["real"] and out["u"]["reason"] == "fine"
    assert not out["z"]["real"] and "no counted" in out["z"]["reason"]


def test_adjudication_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = setup(tmp_path)
    assert adj.main(args) == adj.PENDING
    pending = [line.split()[1] for line in capsys.readouterr().out.splitlines()]
    assert len(pending) == 1
    req = json.loads(Path(pending[0]).read_text())
    ids = sorted(i["id"] for i in req["items"])
    assert ids == ["vc", "ve1", "ve2"]  # a is detected, x is extra, vk and ve3, ve4 not flags
    text = json.dumps(req)
    assert "planted" not in text and "in_list" not in text and "tasks:" not in text
    item = next(i for i in req["items"] if i["id"] == "ve2")
    assert item["flag"] == "false reject" and item["grader_files"] == {"g.sh": "true\n"}
    assert item["witness"]["held"][0]["requirement_text"] == "prints ok"
    verdicts = {"vc": "does-not-validate", "ve1": "does-not-validate", "ve2": "validates"}
    resp = {
        "request": req["hash"],
        "backend": "test",
        "model": "m",
        "items": {i: {"verdict": v, "reason": f"r-{i}"} for i, v in verdicts.items()},
    }
    client = ModelClient(tmp_path / "store", tmp_path / "ledger.jsonl", tmp_path / "budget.toml")
    (client.store / "responses").mkdir(parents=True, exist_ok=True)
    (client.store / "responses" / f"{req['hash']}.json").write_text(json.dumps(resp))
    client.ingest(req["hash"])
    assert adj.main(args) == 0
    doc = json.loads((tmp_path / "e0" / "adjudication.json").read_text())
    assert sorted(doc["tasks"]) == ["c", "e"]
    assert doc["tasks"]["e"]["real"] is True and doc["tasks"]["c"]["real"] is False
    assert doc["models"] == ["test:m"] and doc["prompt_version"] == "adjudicate/v1"
    rows = [json.loads(line) for line in (tmp_path / "e0" / "tasks.jsonl").read_text().splitlines()]
    scores = e0.task_scores(rows, LABELS, doc["tasks"])
    assert [s.task for s in scores if s.adjudicated_real] == ["e"]


def test_no_flags_writes_an_empty_file(tmp_path: Path) -> None:
    args = setup(tmp_path)
    rows = [row("a", fa=True), row("c", fr=True), row("e"), row("x")]
    (tmp_path / "e0" / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert adj.main(args) == 0
    doc = json.loads((tmp_path / "e0" / "adjudication.json").read_text())
    assert doc["tasks"] == {}
