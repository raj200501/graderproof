"""Tests for graderproof.validate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graderproof.core import Task, Variant, VariantKind
from graderproof.models import ModelClient, PendingWorkError
from graderproof.spec import Outcome, Requirement
from graderproof.validate import (
    MAX_OUTCOME_FILE,
    MAX_REQUEST_FILE,
    WITNESS_VALIDATOR,
    ModelReviewer,
    RequirementExtractor,
    parse_requirements,
    patterns_compile,
    valid_requirements,
    witness_hash,
    witness_validation,
)
from graderproof.variants.wrap import wrap_entry

TASK = Task(
    "t",
    "b",
    "write ok to a.txt",
    {"kind": "script"},
    {"s.sh": "echo ok > a.txt\n"},
    ["bash", "g.sh"],
)
REQ = Requirement(
    "R1",
    "a.txt says ok",
    ({"type": "file_equals", "path": "a.txt", "text": "ok", "normalize": "strip"},),
)
BAD = Requirement("R2", "impossible", ({"type": "file_exists", "path": "nope"},))
REF = Outcome(files={"a.txt": "ok\n"})


def variant(kind: VariantKind = VariantKind.VIOLATING) -> Variant:
    return Variant("t", kind, "op", "diff", {"s.sh": "echo no > a.txt\n"})


def test_witness_violating_preserving_and_none() -> None:
    v, w = witness_validation(variant(), [REQ, BAD], REF, Outcome(files={"a.txt": "no\n"}))
    assert v.validator == WITNESS_VALIDATOR and v.verdict is VariantKind.VIOLATING
    assert w is not None and w["broken"][0]["requirement"] == "R1"
    v2, w2 = witness_validation(variant(), [REQ], REF, Outcome(files={"a.txt": "ok"}))
    assert v2.verdict is VariantKind.PRESERVING and w2 is not None and w2["held"] == ["R1"]
    v3, w3 = witness_validation(variant(), [BAD], REF, REF)
    assert v3.verdict is None and w3 is None
    assert witness_hash(None) is None
    assert len(witness_hash({"a": 1}) or "") == 64


def test_valid_requirements_and_parse() -> None:
    good, bad = valid_requirements([REQ, BAD], [REF, REF])
    assert good == [REQ] and bad == [BAD]
    broken = Requirement("R3", "x", ({"type": "same_as_reference", "target": "nope"},))
    assert valid_requirements([broken], [REF])[1] == [broken]
    raw = [
        REQ.to_dict(),
        {"id": "R9", "checks": [{"type": "bogus"}]},
        {"checks": [{"type": "file_exists", "path": "a"}]},
        "junk",
    ]
    parsed = parse_requirements(raw, "src")
    assert [r.id for r in parsed] == ["R1"] and parsed[0].source == "src"


def store(tmp_path: Path) -> ModelClient:
    budget = tmp_path / "budget.toml"
    budget.write_text(
        "cash_usd = 0\nclaude_agent_runs_per_day = 30\nclaude_agent_max_turns = 40\n"
        "claude_single_calls_per_day = 300\nclaude_review_runs_per_day = 6\n"
        "local_model_max_params_b = 8\ndisk_floor_gb = 8\n"
    )
    return ModelClient(tmp_path / "store", tmp_path / "ledger.jsonl", budget, disabled=False)


def respond(client: ModelClient, exc: PendingWorkError, make: object) -> None:
    for h in exc.hashes:
        req = json.loads((client.store / "requests" / f"{h}.json").read_text())
        items = {i["id"]: make(i) for i in req["items"]}  # type: ignore[operator]  # test callback
        path = client.store / "responses" / f"{h}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"request": h, "backend": "test", "model": "m", "items": items}))
        client.ingest(h)


def test_reviewer_round_trip_and_item_content(tmp_path: Path) -> None:
    client = store(tmp_path)
    reviewer = ModelReviewer(client, batch_size=1)
    v1, v2 = variant(), variant(VariantKind.PRESERVING)
    item = reviewer.item(TASK, v1)
    assert set(item) == {"id", "task_text", "reference_solution", "modified_diff", "modified_files"}
    assert "op" not in json.dumps(item) or "operator" not in item
    with pytest.raises(PendingWorkError) as exc:
        reviewer.review([(TASK, v1), (TASK, v2)])
    assert len(exc.value.hashes) == 2
    answers = {
        v1.id: {"verdict": "violating", "requirement": "R1", "reason": "wrong text"},
        v2.id: {"verdict": "unsure", "reason": "?"},
    }
    respond(client, exc.value, lambda i: answers[i["id"]])
    out = reviewer.review([(TASK, v1), (TASK, v2)])
    assert out[v1.id].verdict is VariantKind.VIOLATING and out[v1.id].evidence.startswith("R1:")
    assert out[v2.id].verdict is None
    assert out[v1.id].validator == reviewer.name


def test_extractor_round_trip(tmp_path: Path) -> None:
    client = store(tmp_path)
    ex = RequirementExtractor(client)
    item = ex.item(TASK, REF)
    assert "grader" not in json.dumps(item).lower()
    with pytest.raises(PendingWorkError) as exc:
        ex.extract([(TASK, REF)])
    respond(
        client, exc.value, lambda i: {"requirements": [REQ.to_dict(), {"id": "Rx", "checks": []}]}
    )
    out = ex.extract([(TASK, REF)])
    assert [r.id for r in out[TASK.key]] == ["R1"]


def test_uncompilable_patterns_and_raising_checks() -> None:
    assert patterns_compile([{"type": "stdout_regex", "pattern": "a+"}, {"type": "x"}])
    assert not patterns_compile([{"type": "file_regex", "path": "a.txt", "pattern": "("}])
    raw = [
        {"id": "R1", "text": "ok", "checks": [{"type": "stdout_regex", "pattern": "ok"}]},
        {"id": "R2", "text": "bad", "checks": [{"type": "stdout_regex", "pattern": "(["}]},
    ]
    assert [r.id for r in parse_requirements(raw, "model")] == ["R1"]
    broken = Requirement("R9", "bad regex", ({"type": "stdout_regex", "pattern": "(["},))
    v, w = witness_validation(variant(), [broken, REQ], REF, Outcome(files={"a.txt": "no\n"}))
    assert v.verdict is VariantKind.VIOLATING and w is not None
    assert [b["requirement"] for b in w["broken"]] == ["R1"]
    v2, w2 = witness_validation(variant(), [broken], REF, REF)
    assert v2.verdict is None and w2 is None


def test_model_items_carry_hashes_not_names(tmp_path: Path) -> None:
    client = store(tmp_path)
    item = RequirementExtractor(client).item(TASK, REF)
    assert item["id"] == TASK.key_hash and TASK.key not in json.dumps(item)
    wrapped = Variant(
        "t",
        VariantKind.PRESERVING,
        "out-json-key-order",
        "diff",
        wrap_entry({"s.sh": "echo ok > a.txt\n"}, "s.sh", "out-json-key-order", ["a.txt"]),
    )
    text = json.dumps(ModelReviewer(client).item(TASK, wrapped))
    assert "out-json-key-order" not in text and "key-order" not in text


def long_text(n: int) -> str:
    """Deterministic text of exactly ``n`` characters."""
    line = "the customer asks to cancel order 1234 and to change the address\n"
    return (line * (n // len(line) + 1))[:n]


def test_extraction_sends_long_task_text_and_outcome_files_whole(tmp_path: Path) -> None:
    ex = RequirementExtractor(store(tmp_path))
    task = Task("t", "b", long_text(30_500), {"kind": "script"}, {"s.sh": "x\n"}, ["bash", "g"])
    simulation = long_text(24_999)
    item = ex.item(task, Outcome(files={"simulation.json": simulation}))
    assert item["task_text"] == task.instructions
    assert item["reference_outcome"]["files"] == {"simulation.json": simulation}
    # outcome files stay bounded well above 25000 characters, and a cut is marked
    assert MAX_OUTCOME_FILE >= 25_000
    huge = long_text(MAX_OUTCOME_FILE + 7)
    item = ex.item(task, Outcome(files={"huge.json": huge}))
    marked = huge[:MAX_OUTCOME_FILE] + "\n[... 7 more chars]"
    assert item["reference_outcome"]["files"] == {"huge.json": marked}


def test_review_sends_long_task_text_and_files_whole(tmp_path: Path) -> None:
    reviewer = ModelReviewer(store(tmp_path))
    reference = long_text(20_000)
    task = Task(
        "t", "b", long_text(30_500), {"kind": "script"}, {"trajectory.json": reference}, ["g"]
    )
    changed = reference + long_text(5_000)
    v = Variant("t", VariantKind.VIOLATING, "op", long_text(25_000), {"trajectory.json": changed})
    item = reviewer.item(task, v)
    assert item["task_text"] == task.instructions
    assert item["reference_solution"] == {"trajectory.json": reference}
    assert item["modified_files"] == {"trajectory.json": changed}
    assert item["modified_diff"] == v.diff
    # files and the diff stay bounded, and a cut is marked
    huge = long_text(MAX_REQUEST_FILE + 3)
    item = reviewer.item(
        task, Variant("t", VariantKind.VIOLATING, "op", huge, {"trajectory.json": huge})
    )
    marked = huge[:MAX_REQUEST_FILE] + "\n[... 3 more chars]"
    assert item["modified_diff"] == marked
    assert item["modified_files"] == {"trajectory.json": marked}
