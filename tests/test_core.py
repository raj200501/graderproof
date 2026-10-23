"""Tests for graderproof.core."""

from __future__ import annotations

import pytest

from graderproof.core import (
    Determinism,
    GraderRun,
    Task,
    Validation,
    ValidationStatus,
    Variant,
    VariantKind,
    canonical_json,
    determinism,
    sha256_text,
)


def make_task(**overrides: object) -> Task:
    data: dict[str, object] = {
        "id": "t1",
        "benchmark": "toy",
        "instructions": "Write hello to out.txt",
        "environment": {"image": "none"},
        "reference_solution": {"solve.sh": "echo hello > out.txt\n"},
        "grading_entrypoint": ["bash", "grade.sh"],
    }
    data.update(overrides)
    return Task(**data)  # type: ignore[arg-type]  # test helper passes heterogeneous overrides


def make_variant(kind: VariantKind = VariantKind.VIOLATING, **kw: object) -> Variant:
    base: dict[str, object] = {
        "task_id": "t1",
        "kind": kind,
        "operator": "stmt-delete",
        "diff": "-echo hello > out.txt\n",
        "files": {"solve.sh": "\n"},
        "witness": {"requirement": "R1", "check": "out.txt contains hello"},
    }
    base.update(kw)
    return Variant(**base)  # type: ignore[arg-type]  # test helper passes heterogeneous overrides


def run(passed: bool, exit_status: int = 0, timed_out: bool = False) -> GraderRun:
    return GraderRun(
        task_id="t1",
        variant_id=None,
        exit_status=exit_status,
        passed=passed,
        stdout="",
        stderr="",
        duration_s=0.1,
        backend="subprocess",
        timed_out=timed_out,
    )


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1})
    assert canonical_json({"a": 1}) == '{"a":1}'


def test_sha256_text_known_value() -> None:
    assert sha256_text("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_task_round_trip_and_hashes() -> None:
    task = make_task(metadata={"license": "MIT"})
    again = Task.from_dict(task.to_dict())
    assert again == task
    assert again.content_hash() == task.content_hash()
    assert task.key == "toy:t1"
    assert task.key_hash == sha256_text("toy:t1")
    assert make_task(id="t2").content_hash() != task.content_hash()


@pytest.mark.parametrize("field", [{"id": ""}, {"benchmark": ""}, {"grading_entrypoint": []}])
def test_task_rejects_empty_required_fields(field: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        make_task(**field)


def test_variant_id_is_content_addressed() -> None:
    a = make_variant()
    b = make_variant(diff="different human diff")
    assert a.id == b.id  # diff is presentation only
    assert a.id != make_variant(files={"solve.sh": "echo hi\n"}).id
    assert a.id != make_variant(kind=VariantKind.PRESERVING).id


def test_validation_status_needs_two_distinct_validators() -> None:
    v = make_variant()
    assert v.validation_status is ValidationStatus.UNVALIDATED
    one = v.with_validation(Validation("witness", VariantKind.VIOLATING))
    assert one.validation_status is ValidationStatus.UNVALIDATED
    same_twice = one.with_validation(Validation("witness", VariantKind.VIOLATING))
    assert same_twice.validation_status is ValidationStatus.UNVALIDATED
    two = one.with_validation(Validation("model", VariantKind.VIOLATING))
    assert two.validation_status is ValidationStatus.VALIDATED
    assert two.counts_in_headline


def test_validation_status_disagreement_and_rejection() -> None:
    v = make_variant()
    disagree = v.with_validation(Validation("witness", VariantKind.VIOLATING)).with_validation(
        Validation("model", VariantKind.PRESERVING)
    )
    assert disagree.validation_status is ValidationStatus.DISAGREED
    assert not disagree.counts_in_headline
    unsure = v.with_validation(Validation("witness", VariantKind.VIOLATING)).with_validation(
        Validation("model", None)
    )
    assert unsure.validation_status is ValidationStatus.DISAGREED
    rejected = v.with_validation(Validation("witness", VariantKind.PRESERVING)).with_validation(
        Validation("model", VariantKind.PRESERVING)
    )
    assert rejected.validation_status is ValidationStatus.REJECTED
    all_unsure = v.with_validation(Validation("a", None)).with_validation(Validation("b", None))
    assert all_unsure.validation_status is ValidationStatus.DISAGREED


def test_validated_variant_without_witness_is_not_headline() -> None:
    v = (
        make_variant(witness=None)
        .with_validation(Validation("witness", VariantKind.VIOLATING))
        .with_validation(Validation("model", VariantKind.VIOLATING))
    )
    assert v.validation_status is ValidationStatus.VALIDATED
    assert not v.counts_in_headline


def test_variant_round_trip_and_id_check() -> None:
    v = make_variant().with_validation(Validation("witness", VariantKind.VIOLATING, "R1 broken"))
    data = v.to_dict()
    assert data["validation_status"] == "unvalidated"
    assert Variant.from_dict(data) == v
    assert Variant.from_dict({**data, "witness": None}).witness is None
    with pytest.raises(ValueError, match="id mismatch"):
        Variant.from_dict({**data, "id": "0" * 64})
    unsure = Validation("m", None)
    assert Validation.from_dict(unsure.to_dict()) == unsure


def test_grader_run_round_trip() -> None:
    r = run(True)
    assert GraderRun.from_dict(r.to_dict()) == r
    rv = GraderRun.from_dict({**r.to_dict(), "variant_id": "abc"})
    assert rv.variant_id == "abc"


def test_determinism_classification() -> None:
    assert determinism([run(True), run(True)]) is Determinism.STABLE_PASS
    assert determinism([run(False, 1), run(False, 1)]) is Determinism.STABLE_FAIL
    assert determinism([run(True), run(False, 1)]) is Determinism.FLAKY
    assert determinism([run(False, 1), run(False, 2)]) is Determinism.FLAKY
    assert determinism([run(True), run(True, timed_out=True)]) is Determinism.FLAKY


def test_determinism_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        determinism([])
    other = GraderRun.from_dict({**run(True).to_dict(), "task_id": "t2"})
    with pytest.raises(ValueError):
        determinism([run(True), other])
