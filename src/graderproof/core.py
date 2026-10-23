"""Core data model: tasks, variants of a reference solution, and grader runs.

Every object serializes to canonical JSON (sorted keys, no whitespace) so that
artifacts can be content-addressed and compared byte for byte.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

MIN_VALIDATORS = 2
"""Independent validations a variant needs before it may count in a headline number."""


def canonical_json(obj: Any) -> str:
    """Serialize ``obj`` as canonical JSON: sorted keys, compact separators, UTF-8 text."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    """Return the hex SHA-256 of ``text`` encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class VariantKind(StrEnum):
    """Whether a variant is meant to break the task specification or preserve it."""

    VIOLATING = "violating"
    PRESERVING = "preserving"


class ValidationStatus(StrEnum):
    """Outcome of independent validation of a variant's label."""

    UNVALIDATED = "unvalidated"
    """Fewer than two distinct validators have ruled."""
    VALIDATED = "validated"
    """At least two distinct validators agree with the variant's label."""
    DISAGREED = "disagreed"
    """Validators disagree; the variant goes to the review queue and is excluded."""
    REJECTED = "rejected"
    """Validators agree the label is wrong (for example an equivalent mutant)."""


class Determinism(StrEnum):
    """Classification of repeated grader runs on the same input."""

    STABLE_PASS = "stable_pass"
    STABLE_FAIL = "stable_fail"
    FLAKY = "flaky"


@dataclass(frozen=True)
class Task:
    """One benchmark task with a reference solution and a grading entrypoint.

    Attributes:
        id: Task identifier, unique within its benchmark.
        benchmark: Benchmark or suite name.
        instructions: The task text given to the agent; requirements are parsed from it.
        environment: Environment spec (image, files, resource limits), adapter-defined.
        reference_solution: Solution files, relative path to text content.
        grading_entrypoint: Argument vector that runs the grader.
        metadata: Adapter-specific extras (source revision, license, category).
    """

    id: str
    benchmark: str
    instructions: str
    environment: Mapping[str, Any]
    reference_solution: Mapping[str, str]
    grading_entrypoint: Sequence[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Task.id must be non-empty")
        if not self.benchmark:
            raise ValueError("Task.benchmark must be non-empty")
        if not self.grading_entrypoint:
            raise ValueError("Task.grading_entrypoint must be non-empty")

    @property
    def key(self) -> str:
        """Benchmark-qualified task key, ``<benchmark>:<id>``."""
        return f"{self.benchmark}:{self.id}"

    @property
    def key_hash(self) -> str:
        """SHA-256 of :attr:`key`; the only task identifier allowed in public artifacts."""
        return sha256_text(self.key)

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation."""
        return {
            "id": self.id,
            "benchmark": self.benchmark,
            "instructions": self.instructions,
            "environment": dict(self.environment),
            "reference_solution": dict(self.reference_solution),
            "grading_entrypoint": list(self.grading_entrypoint),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Task:
        """Inverse of :meth:`to_dict`."""
        return cls(
            id=str(data["id"]),
            benchmark=str(data["benchmark"]),
            instructions=str(data["instructions"]),
            environment=dict(data.get("environment", {})),
            reference_solution={str(k): str(v) for k, v in data["reference_solution"].items()},
            grading_entrypoint=[str(a) for a in data["grading_entrypoint"]],
            metadata=dict(data.get("metadata", {})),
        )

    def content_hash(self) -> str:
        """SHA-256 of the canonical JSON of this task."""
        return sha256_text(canonical_json(self.to_dict()))


@dataclass(frozen=True)
class Validation:
    """One validator's ruling on a variant's label.

    Attributes:
        validator: Stable validator name, for example ``witness:requirement`` or
            ``model:haiku/prompt-v1``. Two validations count as independent only if
            their names differ.
        verdict: The kind the validator believes the variant is, or ``None`` if unsure.
        evidence: Short, machine-readable or human-readable justification.
    """

    validator: str
    verdict: VariantKind | None
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation."""
        return {
            "validator": self.validator,
            "verdict": None if self.verdict is None else self.verdict.value,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Validation:
        """Inverse of :meth:`to_dict`."""
        verdict = data.get("verdict")
        return cls(
            validator=str(data["validator"]),
            verdict=None if verdict is None else VariantKind(verdict),
            evidence=str(data.get("evidence", "")),
        )


@dataclass(frozen=True)
class Variant:
    """A modified reference solution with a claimed label and its validation evidence.

    Attributes:
        task_id: The task this variant belongs to.
        kind: Claimed label: violating (breaks a requirement) or preserving.
        operator: Name of the operator that produced it, for example ``stmt-delete``.
        diff: Unified diff against the reference solution, for humans.
        files: The variant solution files, relative path to text content.
        witness: Machine-checkable evidence for the label derived from the task text
            (never from the grader), or ``None`` if none exists yet.
        validations: Independent rulings on the label.
    """

    task_id: str
    kind: VariantKind
    operator: str
    diff: str
    files: Mapping[str, str]
    witness: Mapping[str, Any] | None = None
    validations: tuple[Validation, ...] = ()

    @property
    def id(self) -> str:
        """Content address: SHA-256 over task, kind, operator, and files."""
        return sha256_text(
            canonical_json(
                {
                    "task_id": self.task_id,
                    "kind": self.kind.value,
                    "operator": self.operator,
                    "files": dict(self.files),
                }
            )
        )

    @property
    def validation_status(self) -> ValidationStatus:
        """Combine validations: needs two distinct validators that all agree."""
        by_validator: dict[str, VariantKind | None] = {}
        for v in self.validations:
            by_validator[v.validator] = v.verdict
        if len(by_validator) < MIN_VALIDATORS:
            return ValidationStatus.UNVALIDATED
        verdicts = set(by_validator.values())
        if verdicts == {self.kind}:
            return ValidationStatus.VALIDATED
        if len(verdicts) == 1 and None not in verdicts:
            return ValidationStatus.REJECTED
        return ValidationStatus.DISAGREED

    @property
    def counts_in_headline(self) -> bool:
        """True only for validated variants that carry a witness."""
        return self.validation_status is ValidationStatus.VALIDATED and bool(self.witness)

    def with_validation(self, validation: Validation) -> Variant:
        """Return a copy with ``validation`` appended."""
        return Variant(
            task_id=self.task_id,
            kind=self.kind,
            operator=self.operator,
            diff=self.diff,
            files=self.files,
            witness=self.witness,
            validations=(*self.validations, validation),
        )

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation, including the derived id and status."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "kind": self.kind.value,
            "operator": self.operator,
            "diff": self.diff,
            "files": dict(self.files),
            "witness": None if self.witness is None else dict(self.witness),
            "validations": [v.to_dict() for v in self.validations],
            "validation_status": self.validation_status.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Variant:
        """Inverse of :meth:`to_dict`; rejects data whose stored id does not match."""
        witness = data.get("witness")
        variant = cls(
            task_id=str(data["task_id"]),
            kind=VariantKind(data["kind"]),
            operator=str(data["operator"]),
            diff=str(data.get("diff", "")),
            files={str(k): str(v) for k, v in data["files"].items()},
            witness=None if witness is None else dict(witness),
            validations=tuple(Validation.from_dict(v) for v in data.get("validations", [])),
        )
        stored = data.get("id")
        if stored is not None and stored != variant.id:
            raise ValueError(f"variant id mismatch: stored {stored}, computed {variant.id}")
        return variant


@dataclass(frozen=True)
class GraderRun:
    """One execution of a grader on the reference solution or a variant.

    Attributes:
        task_id: The task graded.
        variant_id: The variant graded, or ``None`` for the unmodified reference.
        exit_status: Grader process exit status.
        passed: Whether the grader accepted the solution.
        stdout: Captured standard output (possibly truncated by the runner).
        stderr: Captured standard error (possibly truncated by the runner).
        duration_s: Wall-clock seconds.
        backend: Execution backend, for example ``docker`` or ``subprocess-unshare``.
        timed_out: Whether the runner killed the grader at its time limit.
    """

    task_id: str
    variant_id: str | None
    exit_status: int
    passed: bool
    stdout: str
    stderr: str
    duration_s: float
    backend: str
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation."""
        return {
            "task_id": self.task_id,
            "variant_id": self.variant_id,
            "exit_status": self.exit_status,
            "passed": self.passed,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_s": self.duration_s,
            "backend": self.backend,
            "timed_out": self.timed_out,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GraderRun:
        """Inverse of :meth:`to_dict`."""
        variant_id = data.get("variant_id")
        return cls(
            task_id=str(data["task_id"]),
            variant_id=None if variant_id is None else str(variant_id),
            exit_status=int(data["exit_status"]),
            passed=bool(data["passed"]),
            stdout=str(data.get("stdout", "")),
            stderr=str(data.get("stderr", "")),
            duration_s=float(data["duration_s"]),
            backend=str(data["backend"]),
            timed_out=bool(data.get("timed_out", False)),
        )


def determinism(runs: Sequence[GraderRun]) -> Determinism:
    """Classify repeated runs of one grader on one input.

    A set of runs is stable only if every run has the same pass/fail outcome,
    the same exit status, and none timed out. Anything else is flaky.

    Raises:
        ValueError: if ``runs`` is empty or mixes tasks or variants.
    """
    if not runs:
        raise ValueError("determinism() needs at least one run")
    targets = {(r.task_id, r.variant_id) for r in runs}
    if len(targets) != 1:
        raise ValueError("determinism() runs must share one task and variant")
    outcomes = {(r.passed, r.exit_status) for r in runs}
    if len(outcomes) != 1 or any(r.timed_out for r in runs):
        return Determinism.FLAKY
    return Determinism.STABLE_PASS if runs[0].passed else Determinism.STABLE_FAIL
