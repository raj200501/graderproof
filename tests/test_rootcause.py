"""Tests for E3 root-cause coding (graderproof.rootcause)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.core import Task
from graderproof.models import ModelClient, PendingWorkError
from graderproof.rootcause import (
    CODES,
    CodingItem,
    ModelCoder,
    agreement,
    cohen_kappa,
    items_from_evidence,
    rule_code,
)

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo"
TASKS = {t.id: t for t in ToybenchAdapter().load(DEMO)}


def item(
    task_id: str, direction: str, operator: str, witness: dict[str, Any] | None = None
) -> CodingItem:
    return CodingItem("v", TASKS[task_id], direction, operator, "diff", witness)


REQS = {
    "R1": {"checks": [{"type": "file_json"}]},
    "R2": {"checks": [{"type": "trajectory_before"}]},
    "R3": {"checks": [{"type": "call"}]},
}


def test_rule_codes_on_demo_graders() -> None:
    broken_content = {"broken": [{"requirement": "R1"}]}
    assert (
        rule_code(item("word-stats", "accept", "py-constant", broken_content), REQS)
        == "presence-not-content"
    )
    assert (
        rule_code(
            item("refund", "accept", "traj-drop-confirmation", {"broken": [{"requirement": "R2"}]}),
            REQS,
        )
        == "outcome-only-process"
    )
    assert (
        rule_code(
            item("classify", "accept", "py-return-none", {"broken": [{"requirement": "R3"}]}), REQS
        )
        == "coverage-gap"
    )
    assert (
        rule_code(item("status-json", "reject", "stdout-json-key-order"), REQS) == "brittle-parsing"
    )
    assert rule_code(item("greeting", "reject", "pre-delay"), REQS) == "timing"
    assert rule_code(item("greeting", "reject", "reference-flaky"), REQS) == "timing"
    assert (
        rule_code(item("refund", "reject", "traj-swap-independent"), REQS) == "over-specification"
    )
    assert rule_code(item("greeting", "reject", "sh-constant"), REQS) == "other-reject"
    assert rule_code(item("greeting", "accept", "sh-constant"), REQS) == "other-accept"


def test_items_from_evidence() -> None:
    task = TASKS["word-stats"]
    ev = {
        "determinism": "flaky",
        "variants": [
            {
                "id": "a",
                "kind": "violating",
                "counted_in_headline": True,
                "grader_passed": True,
                "operator": "x",
                "diff": "d",
                "witness": None,
            },
            {"id": "b", "kind": "violating", "counted_in_headline": True, "grader_passed": False},
            {
                "id": "c",
                "kind": "preserving",
                "counted_in_headline": True,
                "grader_passed": False,
                "operator": "out-x",
            },
            {"id": "d", "kind": "preserving", "counted_in_headline": False, "grader_passed": False},
            {"id": "e", "kind": "violating", "counted_in_headline": True, "grader_passed": None},
        ],
    }
    items = items_from_evidence(task, ev)
    assert [(i.id, i.direction) for i in items] == [
        ("a", "accept"),
        ("c", "reject"),
        (f"{task.key_hash}:reference", "reject"),
    ]
    assert items[0].broken_check_types(REQS) == set()
    held = CodingItem("h", task, "reject", "out-x", "", {"held": ["R1", "R2"]})
    assert held.broken_check_types(REQS) == {"file_json", "trajectory_before"}


def test_kappa_and_agreement() -> None:
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert cohen_kappa([], []) is None
    assert cohen_kappa(["a", "a"], ["a", "a"]) is None
    k = cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"])
    assert k == pytest.approx(0.0)
    with pytest.raises(ValueError):
        cohen_kappa(["a"], [])
    out = agreement(["a", "b"], ["a", "c"])
    assert out["raw"] == 0.5 and out["confusion"] == {"a|a": 1, "b|c": 1}
    assert agreement([], [])["raw"] is None


def test_model_coder_round_trip(tmp_path: Path) -> None:
    budget = tmp_path / "b.toml"
    budget.write_text(
        "cash_usd = 0\nclaude_agent_runs_per_day = 30\nclaude_agent_max_turns = 40\n"
        "claude_single_calls_per_day = 300\nclaude_review_runs_per_day = 6\n"
        "local_model_max_params_b = 8\ndisk_floor_gb = 8\n"
    )
    client = ModelClient(tmp_path / "s", tmp_path / "l.jsonl", budget, disabled=False)
    coder = ModelCoder(client)
    it = item("word-stats", "accept", "py-constant", {"broken": [{"requirement": "R1"}]})
    payload = coder.item(it)
    assert (
        payload["error"] == "accepts a violating solution" and "grade.py" in payload["grader_files"]
    )
    assert "operator" not in payload and "rule" not in json.dumps(payload)
    with pytest.raises(PendingWorkError) as exc:
        coder.code([it])
    h = exc.value.hashes[0]
    (client.store / "responses").mkdir(parents=True)
    resp = {
        "request": h,
        "backend": "t",
        "model": "m",
        "items": {"v": {"code": CODES[0], "reason": "r"}},
    }
    (client.store / "responses" / f"{h}.json").write_text(json.dumps(resp))
    client.ingest(h)
    assert coder.code([it]) == {"v": CODES[0]}
    assert isinstance(TASKS["greeting"], Task)
