"""Tests for E0 scoring (graderproof.e0 and `graderproof e0-score`)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from graderproof import e0
from graderproof.cli import main

LABELS: dict[str, dict[str, Any]] = {
    "a": {
        "planted": True,
        "slice": "in_list",
        "weakness_type": "loose-matching",
        "direction": "accept",
    },
    "b": {
        "planted": True,
        "slice": "in_list",
        "weakness_type": "brittle-parsing",
        "direction": "reject",
    },
    "c": {"planted": True, "slice": "in_list", "weakness_type": "timing", "direction": "reject"},
    "d": {
        "planted": True,
        "slice": "in_list",
        "weakness_type": "exit-code-only",
        "direction": "accept",
    },
    "e": {"planted": False, "slice": "clean", "weakness_type": None, "direction": None},
    "f": {"planted": False, "slice": "clean", "weakness_type": None, "direction": None},
    "g": {"planted": True, "slice": "extra", "weakness_type": "self-graded", "direction": "accept"},
}


def row(task: str, **flags: bool) -> dict[str, Any]:
    base = {k: False for k in e0.FLAG_KEYS}
    base.update(flags)
    return {"task": f"bench:{task}", **base}


ROWS = [
    row("a", false_accept=True),  # detected
    row("b", false_reject=True),  # detected (reject direction)
    row("c", false_accept=True),  # flagged in the wrong direction: not detected
    row("d", reference_rejected=True),  # reference-level only: a miss, reported separately
    row("e", false_reject=True),  # clean-task flag
    row("f", flaky=True),  # clean task with a flaky grader: not a flag
    row("g", false_accept=True),  # extra slice
]


def test_detection_rules() -> None:
    scores = {s.task: s for s in e0.task_scores(ROWS, LABELS, {})}
    assert scores["a"].detected and scores["b"].detected
    assert scores["c"].flagged and not scores["c"].detected
    assert not scores["d"].flagged and not scores["d"].detected and scores["d"].reference_level
    assert scores["e"].flagged and not scores["e"].detected
    assert not scores["f"].flagged and scores["f"].reference_level
    flaky = e0.task_scores([row("b", flaky=True)], {"b": LABELS["b"]}, {})[0]
    assert not flaky.detected  # reference-level flags are never detections (D23)
    odd = e0.TaskScore("x", True, "in_list", "t", "sideways", {"false_accept": True}, False)
    assert not odd.detected
    assert sorted(s.task for s in e0.needs_adjudication(list(scores.values()))) == ["c", "e"]


def test_adjudication_applies_only_to_flags_that_are_not_detections() -> None:
    adj: dict[str, dict[str, Any]] = {"e": {"real": True}, "a": {"real": True}, "f": {"real": True}}
    scores = {s.task: s for s in e0.task_scores(ROWS, LABELS, adj)}
    assert scores["e"].adjudicated_real
    assert not scores["a"].adjudicated_real  # a detection is never "adjudicated"
    assert not scores["f"].adjudicated_real  # an unflagged task cannot be adjudicated
    false_ruling = e0.task_scores(ROWS, LABELS, {"e": {"real": False}})
    assert not next(s for s in false_ruling if s.task == "e").adjudicated_real


def test_score_numbers() -> None:
    scores = e0.task_scores(ROWS, LABELS, {"e": {"real": True}, "c": {"real": False}})
    out = e0.score(scores, seed=3, replicates=200)
    assert out["n_counted"] == 6 and out["n_planted"] == 4 and out["n_clean"] == 2
    assert out["recall"]["point"] == pytest.approx(0.5)  # a, b detected; c, d missed
    assert out["precision"]["point"] == pytest.approx(2 / 3)  # FP: c only (e adjudicated real)
    assert out["precision_unadjudicated"]["point"] == pytest.approx(0.5)
    lo, hi = out["exact_intervals"]["recall"]
    assert lo < 0.5 < hi
    assert out["reference_level"] == {"planted": ["d"], "clean": ["f"]}
    assert out["misses"] == ["c", "d"]
    assert out["false_positives"] == ["c"]
    assert out["adjudicated_real"] == ["e"]
    assert out["extra_slice"] == {"n": 1, "detected": 1}
    assert out["by_type"]["in_list:timing"] == {"planted": 1, "detected": 0}
    assert out["exploratory_timing_with_reference_flags"] == {"n": 1, "detected": 0}
    none = e0.score(e0.task_scores([row("f")], {"f": LABELS["f"]}, {}), 1, 10)
    assert none["recall"] is None and none["precision"] is None
    unflagged = e0.score(e0.task_scores([row("a")], {"a": LABELS["a"]}, {}), 1, 10)
    assert unflagged["recall"]["point"] == 0.0 and unflagged["precision"] is None


def test_label_and_join_errors() -> None:
    with pytest.raises(ValueError, match="disagree"):
        e0.task_scores(ROWS[:2], LABELS, {})
    with pytest.raises(ValueError, match="direction"):
        e0.task_scores([row("a")], {"a": {**LABELS["a"], "direction": None}}, {})
    with pytest.raises(ValueError, match="slice"):
        e0.task_scores([row("a")], {"a": {**LABELS["a"], "slice": "inlist"}}, {})
    with pytest.raises(ValueError, match="planted"):
        e0.task_scores([row("e")], {"e": {**LABELS["e"], "planted": True}}, {})
    with pytest.raises(ValueError, match="true or false"):
        e0.task_scores([row("e", false_reject=True)], {"e": LABELS["e"]}, {"e": {"real": "false"}})


def test_e0_score_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    audit = tmp_path / "e0"
    audit.mkdir()
    (audit / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ROWS))
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"tasks": LABELS}))
    digest = tmp_path / "labels.sha256"
    digest.write_text("0" * 64 + "  labels.json\n")
    adjud = tmp_path / "adjudication.json"
    out = tmp_path / "results.json"
    args = ["e0-score", "--audit", str(audit), "--labels", str(labels)]
    args += ["--labels-sha256", str(digest), "--adjudication", str(adjud)]
    args += ["--out", str(out), "--seed", "3", "--replicates", "100"]
    assert main(args) == 1
    assert "committed hash" in capsys.readouterr().err
    digest.write_text(hashlib.sha256(labels.read_bytes()).hexdigest() + "  labels.json\n")
    assert main(args) == 1
    assert "awaiting adjudication" in capsys.readouterr().err
    adjud.write_text(json.dumps({"tasks": {"c": {"real": "no"}, "e": {"real": True}}}))
    assert main(args) == 1
    assert "true or false" in capsys.readouterr().err
    rulings = {
        "c": {"real": False, "reason": "wrong direction"},
        "e": {"real": True, "reason": "x"},
    }
    adjud.write_text(json.dumps({"tasks": rulings}))
    assert main(args) == 0
    res = json.loads(out.read_text())
    assert res["schema"] == "graderproof.e0/1" and res["bootstrap"] == {
        "seed": 3,
        "B": 100,
        "alpha": 0.05,
    }
    assert res["labels_path"] == str(labels) and res["prereg"].startswith("prereg/")
    assert {"git_sha", "git_dirty", "command", "created_utc"} <= set(res["provenance"])
    assert [t["task"] for t in res["tasks"]] == sorted(LABELS)
    assert res["recall"]["ci"][0] <= res["recall"]["point"] <= res["recall"]["ci"][1]
