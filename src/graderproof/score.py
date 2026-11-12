"""Per-task scores and benchmark aggregates.

Definitions (task is the unit of analysis):

* A variant **counts** only if it has two agreeing, independent validations and a
  witness (:attr:`graderproof.core.Variant.counts_in_headline`) and the grader's
  verdict on it is stable over repeated runs.
* **False accept** (task level): some counted violating variant passes the grader.
* **False reject** (task level): some counted preserving variant fails the grader.
* **Mutation score**: killed counted violating variants over all counted violating
  variants (None when there are none).
* **Equivalent variants**: generated as violating, but both validators agree they
  preserve the specification; excluded from the mutation score and reported.
* Tasks whose grader rejects the reference, or is flaky on it, get no indicators and
  are reported separately.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from graderproof.core import Determinism, ValidationStatus, Variant, VariantKind
from graderproof.stats import Estimate, proportion


@dataclass(frozen=True)
class VariantResult:
    """A validated variant with the grader's verdict on it.

    Attributes:
        variant: The variant with its validations and witness.
        grader_passed: The grader's stable verdict, or None if unstable or not run.
        runs: How many times the grader ran on it.
        generated_kind: The operator's intended label (same as ``variant.kind``).
    """

    variant: Variant
    grader_passed: bool | None
    runs: int

    @property
    def counted(self) -> bool:
        """Counts toward headline numbers: validated with witness and stable verdict."""
        return self.variant.counts_in_headline and self.grader_passed is not None

    @property
    def equivalent(self) -> bool:
        """Generated as violating but validated as preserving by both validators."""
        return (
            self.variant.kind is VariantKind.VIOLATING
            and self.variant.validation_status is ValidationStatus.REJECTED
        )

    @property
    def survives(self) -> bool:
        """A counted violating variant the grader accepts (a false accept)."""
        return (
            self.counted
            and self.variant.kind is VariantKind.VIOLATING
            and self.grader_passed is True
        )

    @property
    def wrongly_rejected(self) -> bool:
        """A counted preserving variant the grader rejects (a false reject)."""
        return (
            self.counted
            and self.variant.kind is VariantKind.PRESERVING
            and self.grader_passed is False
        )


@dataclass
class TaskResult:
    """Everything graderproof concluded about one task."""

    task_key: str
    task_hash: str
    determinism: Determinism
    n_requirements: int
    n_requirements_invalid: int
    variants: list[VariantResult] = field(default_factory=list)
    stratum: str = ""

    @property
    def scorable(self) -> bool:
        """Only tasks whose grader passes the reference stably get indicators."""
        return self.determinism is Determinism.STABLE_PASS

    @property
    def flaky(self) -> bool:
        """The grader is not deterministic on the reference."""
        return self.determinism is Determinism.FLAKY

    @property
    def counted_violating(self) -> list[VariantResult]:
        """Counted violating variants."""
        return [v for v in self.variants if v.counted and v.variant.kind is VariantKind.VIOLATING]

    @property
    def counted_preserving(self) -> list[VariantResult]:
        """Counted preserving variants."""
        return [v for v in self.variants if v.counted and v.variant.kind is VariantKind.PRESERVING]

    @property
    def false_accept(self) -> bool:
        """Some counted violating variant passes."""
        return self.scorable and any(v.survives for v in self.variants)

    @property
    def false_reject(self) -> bool:
        """Some counted preserving variant fails."""
        return self.scorable and any(v.wrongly_rejected for v in self.variants)

    @property
    def mutation_score(self) -> float | None:
        """Share of counted violating variants the grader rejects."""
        vs = self.counted_violating
        if not self.scorable or not vs:
            return None
        return sum(1 for v in vs if v.grader_passed is False) / len(vs)

    @property
    def n_equivalent(self) -> int:
        """Equivalent (generated-violating, validated-preserving) variants."""
        return sum(1 for v in self.variants if v.equivalent)

    def summary(self) -> dict[str, Any]:
        """Task-level record for tasks.jsonl."""
        return {
            "task_hash": self.task_hash,
            "stratum": self.stratum,
            "determinism": self.determinism.value,
            "flaky": self.flaky,
            "reference_rejected": self.determinism is Determinism.STABLE_FAIL,
            "n_requirements": self.n_requirements,
            "n_requirements_invalid": self.n_requirements_invalid,
            "n_variants": len(self.variants),
            "n_counted_violating": len(self.counted_violating),
            "n_counted_preserving": len(self.counted_preserving),
            "n_killed": sum(1 for v in self.counted_violating if v.grader_passed is False),
            "n_equivalent": self.n_equivalent,
            "mutation_score": self.mutation_score,
            "false_accept": self.false_accept,
            "false_reject": self.false_reject,
        }


def variant_record(task_hash: str, vr: VariantResult, witness_sha256: str | None) -> dict[str, Any]:
    """Variant-level record for variants.jsonl.

    It holds no solution content, but ``variant_id`` is a content address: anyone who can
    regenerate a deterministic variant can match it. Rows of third-party audits are
    therefore published through ``tools/publish_rows.py``, with keyed ids and no
    operator (DECISIONS.md D43, D44).
    """
    v = vr.variant
    return {
        "variant_id": v.id,
        "task_hash": task_hash,
        "kind": v.kind.value,
        "operator": v.operator,
        "validation_status": v.validation_status.value,
        "validations": [
            {"validator": x.validator, "verdict": None if x.verdict is None else x.verdict.value}
            for x in v.validations
        ],
        "witness_sha256": witness_sha256,
        "counted_in_headline": vr.counted,
        "grader_passed": vr.grader_passed,
        "grader_runs": vr.runs,
    }


@dataclass(frozen=True)
class Aggregate:
    """Benchmark-level numbers with task bootstrap intervals."""

    n_tasks: int
    n_scorable: int
    n_flaky: int
    n_reference_rejected: int
    false_accept: Estimate | None
    false_reject: Estimate | None
    mean_mutation_score: float | None
    agreement_rate: float | None
    n_headline_variants: int
    n_excluded_variants: int
    n_unsure_variants: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation."""
        return {
            "n_tasks": self.n_tasks,
            "n_scorable": self.n_scorable,
            "n_flaky": self.n_flaky,
            "n_reference_rejected": self.n_reference_rejected,
            "false_accept_task_rate": None
            if self.false_accept is None
            else self.false_accept.to_dict(),
            "false_reject_task_rate": None
            if self.false_reject is None
            else self.false_reject.to_dict(),
            "mean_mutation_score": self.mean_mutation_score,
            "agreement_rate": self.agreement_rate,
            "n_headline_variants": self.n_headline_variants,
            "n_excluded_variants": self.n_excluded_variants,
            "n_unsure_variants": self.n_unsure_variants,
        }


def agreement(results: Sequence[TaskResult]) -> tuple[float | None, int, int]:
    """(rate, agreeing, judged) over variants whose 2+ validators all gave a label.

    A variant with any ``unsure`` or evidence-free verdict is not judged (DECISIONS.md
    D26); :func:`unsure_count` reports those separately.
    """
    judged = agree = 0
    for t in results:
        for vr in t.variants:
            vals = vr.variant.validations
            if len({x.validator for x in vals}) >= 2 and all(x.verdict is not None for x in vals):
                judged += 1
                agree += len({x.verdict for x in vals}) == 1
    return (agree / judged if judged else None), agree, judged


def unsure_count(results: Sequence[TaskResult]) -> int:
    """Variants where some validator returned no label verdict."""
    return sum(
        1
        for t in results
        for vr in t.variants
        if any(x.verdict is None for x in vr.variant.validations)
    )


def aggregate(results: Sequence[TaskResult], seed: int, replicates: int) -> Aggregate:
    """Rates over scorable tasks: false accept with ``seed``, false reject with ``seed + 1``."""
    scorable = [t for t in results if t.scorable]
    fa = proportion([t.false_accept for t in scorable], seed, replicates)
    fr = proportion([t.false_reject for t in scorable], seed + 1, replicates)
    scores = [t.mutation_score for t in scorable if t.mutation_score is not None]
    rate, _, _ = agreement(results)
    all_variants = [v for t in results for v in t.variants]
    headline = sum(1 for v in all_variants if v.counted)
    return Aggregate(
        n_tasks=len(results),
        n_scorable=len(scorable),
        n_flaky=sum(1 for t in results if t.flaky),
        n_reference_rejected=sum(1 for t in results if t.determinism is Determinism.STABLE_FAIL),
        false_accept=fa,
        false_reject=fr,
        mean_mutation_score=sum(scores) / len(scores) if scores else None,
        agreement_rate=rate,
        n_headline_variants=headline,
        n_excluded_variants=len(all_variants) - headline,
        n_unsure_variants=unsure_count(results),
    )


def operator_counts(results: Sequence[TaskResult]) -> dict[str, dict[str, int]]:
    """Per-operator counts of generated, counted, surviving, and wrongly rejected variants."""
    out: dict[str, dict[str, int]] = {}
    for t in results:
        for vr in t.variants:
            row = out.setdefault(
                vr.variant.operator,
                {"generated": 0, "counted": 0, "survived": 0, "wrongly_rejected": 0},
            )
            row["generated"] += 1
            row["counted"] += vr.counted
            row["survived"] += vr.survives and t.scorable
            row["wrongly_rejected"] += vr.wrongly_rejected and t.scorable
    return dict(sorted(out.items()))


def by_key(results: Sequence[TaskResult]) -> Mapping[str, TaskResult]:
    """Results indexed by task key."""
    return {t.task_key: t for t in results}
