"""Tests for model-proposed variants (graderproof.variants.model)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graderproof.core import Task, VariantKind
from graderproof.models import ModelClient, PendingWorkError
from graderproof.spec import Requirement
from graderproof.variants.model import ModelProposer, merged_files, to_variants

TASK = Task("t", "b", "print hi", {"kind": "script"}, {"s.sh": "echo hi\n"}, ["bash", "g.sh"])
REQ = Requirement("R1", "prints hi", ({"type": "stdout_contains", "text": "hi"},))


def test_merged_files_rejects_bad_proposals() -> None:
    ref = {"s.sh": "echo hi\n"}
    assert merged_files(ref, {"files": {"s.sh": "echo ho\n"}}) == {"s.sh": "echo ho\n"}
    assert merged_files(ref, {"files": {"s.sh": "echo hi\n"}}) is None
    assert merged_files(ref, {"files": {"other.sh": "x"}}) is None
    assert merged_files(ref, {"files": {"s.sh": 3}}) is None
    assert merged_files(ref, {"files": {}}) is None
    assert merged_files(ref, "junk") is None
    assert merged_files(ref, {"files": "x"}) is None


def test_to_variants_kinds_limits_and_dedupe() -> None:
    response = {
        "violating": [{"requirement": "R1", "files": {"s.sh": "echo ho\n"}}] * 2 + ["junk"],
        "preserving": [{"files": {"s.sh": "printf 'hi\\n'\n"}}],
    }
    vs = to_variants(TASK, response)
    assert [v.kind for v in vs] == [VariantKind.VIOLATING, VariantKind.PRESERVING]
    assert {v.operator for v in vs} == {"model-violating", "model-preserving"}
    assert vs[0].diff.startswith("--- a/s.sh")
    assert to_variants(TASK, {"violating": "x"}) == []


def test_proposer_round_trip(tmp_path: Path) -> None:
    budget = tmp_path / "b.toml"
    budget.write_text(
        "cash_usd = 0\nclaude_agent_runs_per_day = 30\nclaude_agent_max_turns = 40\n"
        "claude_single_calls_per_day = 300\nclaude_review_runs_per_day = 6\n"
        "local_model_max_params_b = 8\ndisk_floor_gb = 8\n"
    )
    client = ModelClient(tmp_path / "s", tmp_path / "l.jsonl", budget, disabled=False)
    proposer = ModelProposer(client)
    item = proposer.item(TASK, [REQ])
    assert item["requirements"] == [{"id": "R1", "text": "prints hi"}]
    assert "checks" not in json.dumps(item)
    with pytest.raises(PendingWorkError) as exc:
        proposer.propose([(TASK, [REQ])])
    h = exc.value.hashes[0]
    resp = {
        "request": h,
        "backend": "t",
        "model": "m",
        "items": {TASK.key: {"violating": [{"files": {"s.sh": "echo no\n"}}], "preserving": []}},
    }
    (client.store / "responses").mkdir(parents=True)
    (client.store / "responses" / f"{h}.json").write_text(json.dumps(resp))
    client.ingest(h)
    out = proposer.propose([(TASK, [REQ])])
    assert len(out[TASK.key]) == 1
    assert proposer.propose([(TASK, [])]) == {TASK.key: []}


def test_later_rounds_are_new_requests() -> None:
    client = ModelClient(
        Path("/nonexistent"), Path("/nonexistent/l"), Path("/nonexistent/b"), disabled=True
    )
    first = ModelProposer(client).item(TASK, [REQ])
    again = ModelProposer(client, round=2).item(TASK, [REQ])
    assert "round" not in first and again["round"] == 2
    assert {k: v for k, v in again.items() if k != "round"} == first
