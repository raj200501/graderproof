"""The audit pipeline: from tasks to validated, scored variants and banked artifacts.

Stages, each over every task so model calls can be batched:

A. Run the unmodified reference once to see what it produces.
B. Extract requirements from the task text (model, via the client wrapper).
C. Determinism pre-check: grade the reference ``k`` times with the requirement probes;
   keep requirements that hold on every reference run; generate classical variants;
   execute each variant once; validate it deterministically (witness).
C2. Ask the model for requirement-targeted and equivalent variants (optional), then
   execute and witness-validate them the same way.
D. Review every variant with the model validator.
E. Combine validations; re-run the grader on variants that would raise a flag so
   only stable verdicts count; score.

If any model request is unanswered, :class:`~graderproof.models.PendingWorkError` is
raised after all independent work is done; rerunning after the responses are
ingested resumes from the execution cache.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from graderproof import __version__
from graderproof.adapters import Adapter, Execution
from graderproof.core import Task, Validation, Variant, canonical_json, sha256_text
from graderproof.models import PendingWorkError, utc_now
from graderproof.run import Runner, package_fingerprint
from graderproof.score import TaskResult, VariantResult, aggregate, operator_counts, variant_record
from graderproof.spec import Outcome, Requirement, probes_of
from graderproof.validate import (
    ModelReviewer,
    RequirementExtractor,
    valid_requirements,
    witness_hash,
    witness_validation,
)
from graderproof.variants import Context, Generator
from graderproof.variants import preserving as pres
from graderproof.variants import violating as viol
from graderproof.variants.model import ModelProposer


@dataclass(frozen=True)
class AuditConfig:
    """Frozen audit parameters (recorded in every artifact)."""

    k: int = 3
    confirm_runs: int = 2
    seed: int = 0
    max_per_operator: int = 6
    max_total: int = 40
    replicates: int = 2000

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation."""
        return dict(self.__dict__)


@dataclass
class TaskEvidence:
    """Full evidence for one task (private for unpatched third-party tasks)."""

    task: Task
    requirements: list[Requirement] = field(default_factory=list)
    invalid_requirements: list[Requirement] = field(default_factory=list)
    reference: Outcome | None = None
    variants: list[Variant] = field(default_factory=list)
    executions: dict[str, Execution] = field(default_factory=dict)
    witnesses: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    grader_runs: dict[str, list[bool]] = field(default_factory=dict)

    def to_dict(self, result: TaskResult) -> dict[str, Any]:
        """Plain-JSON evidence document."""
        rows = []
        for vr in result.variants:
            v = vr.variant
            rows.append(
                {
                    **v.to_dict(),
                    "witness": self.witnesses.get(v.id),
                    "grader_runs": self.grader_runs.get(v.id, []),
                    "grader_passed": vr.grader_passed,
                    "counted_in_headline": vr.counted,
                }
            )
        return {
            "schema": "graderproof.evidence/1",
            "task": self.task.key,
            "task_hash": self.task.key_hash,
            "determinism": result.determinism.value,
            "requirements": [r.to_dict() for r in self.requirements],
            "invalid_requirements": [r.to_dict() for r in self.invalid_requirements],
            "reference_outcome": None if self.reference is None else self.reference.to_dict(),
            "variants": rows,
        }


def context_for(task: Task, reference: Outcome, languages: Mapping[str, str]) -> Context:
    """What variant operators may know about the task's reference outcome."""
    initial = task.environment.get("workspace_files", {})
    outputs = sorted(p for p, t in reference.files.items() if initial.get(p) != t)
    json_outputs = [p for p in outputs if pres.json_like(reference.files[p])]
    return Context(
        languages=languages,
        entry=str(task.environment.get("solution_entry", "")),
        outputs=outputs,
        json_outputs=json_outputs,
        stdout_json=pres.json_like(reference.stdout.strip()),
        stdout_nonempty=bool(reference.stdout.strip()),
        kind=str(task.environment.get("kind", "script")),
        timeout_s=float(task.environment.get("timeout_s", 0) or 0),
    )


def default_generator(config: AuditConfig) -> Generator:
    """Every classical violating and metamorphic preserving operator."""
    return Generator(
        operators=[*viol.ALL, *pres.ALL],
        max_per_operator=config.max_per_operator,
        max_total=config.max_total,
        seed=config.seed,
    )


@dataclass
class Auditor:
    """Runs the five audit stages over a list of tasks."""

    adapter: Adapter
    runner: Runner
    extractor: RequirementExtractor
    reviewer: ModelReviewer
    config: AuditConfig = field(default_factory=AuditConfig)
    generator: Generator | None = None
    proposer: ModelProposer | None = None

    def run(self, tasks: Sequence[Task]) -> tuple[list[TaskResult], list[TaskEvidence]]:
        """Audit ``tasks``; raises PendingWorkError when model responses are missing."""
        gen = self.generator or default_generator(self.config)
        evidence = {t.key: TaskEvidence(task=t) for t in tasks}
        first = {t.key: self.runner.execute(t, t.reference_solution).outcome for t in tasks}
        requirements = self.extractor.extract([(t, first[t.key]) for t in tasks])
        determinism: dict[str, Any] = {}
        classical: list[tuple[Task, Variant]] = []
        for t in tasks:
            ev = evidence[t.key]
            reqs = requirements.get(t.key, [])
            probes = probes_of(reqs)
            det, runs = self.runner.precheck(t, self.config.k, probes)
            determinism[t.key] = det
            refs = [r.outcome for r in runs]
            ev.reference = refs[0]
            ev.requirements, ev.invalid_requirements = valid_requirements(reqs, refs)
            ctx = context_for(t, refs[0], self.adapter.mutable_files(t))
            for v in gen.variants(t.id, t.reference_solution, ctx):
                classical += self._execute_variant(t, v, ev)
        pending: list[str] = []
        proposed: list[tuple[Task, Variant]] = []
        if self.proposer is not None:
            try:
                proposals = self.proposer.propose(
                    [(t, evidence[t.key].requirements) for t in tasks]
                )
            except PendingWorkError as exc:
                pending += exc.hashes
                proposals = {}
            for t in tasks:
                for v in proposals.get(t.key, []):
                    proposed += self._execute_variant(t, v, evidence[t.key])
        reviews: dict[str, Validation] = {}
        for group in (classical, proposed):
            if not group:
                continue
            try:
                reviews.update(self.reviewer.review(group))
            except PendingWorkError as exc:
                pending += exc.hashes
        if pending:
            raise PendingWorkError(pending)
        results: list[TaskResult] = []
        for t in tasks:
            ev = evidence[t.key]
            vrs: list[VariantResult] = []
            final: list[Variant] = []
            for v in ev.variants:
                review = reviews.get(v.id) or Validation(self.reviewer.name, None, "no review")
                witness = ev.witnesses.get(v.id)
                v3 = Variant(
                    v.task_id,
                    v.kind,
                    v.operator,
                    v.diff,
                    v.files,
                    witness,
                    (*v.validations, review),
                )
                passed = self._stable_verdict(t, v3, ev)
                final.append(v3)
                vrs.append(VariantResult(v3, passed, len(ev.grader_runs[v3.id])))
            ev.variants = final
            results.append(
                TaskResult(
                    task_key=t.key,
                    task_hash=t.key_hash,
                    determinism=determinism[t.key],
                    n_requirements=len(ev.requirements),
                    n_requirements_invalid=len(ev.invalid_requirements),
                    variants=vrs,
                    stratum=str(t.metadata.get("stratum", "")),
                )
            )
        return results, [evidence[t.key] for t in tasks]

    def _execute_variant(
        self, task: Task, v: Variant, ev: TaskEvidence
    ) -> list[tuple[Task, Variant]]:
        """Run one variant once and witness-validate it (skipping duplicates)."""
        if v.id in ev.executions or ev.reference is None:
            return []
        ex = self.runner.execute(task, v.files, probes_of(ev.requirements), variant_id=v.id)
        validation, witness = witness_validation(v, ev.requirements, ev.reference, ex.outcome)
        v2 = v.with_validation(validation)
        ev.variants.append(v2)
        ev.executions[v2.id] = ex
        ev.witnesses[v2.id] = witness if validation.verdict is v.kind else None
        ev.grader_runs[v2.id] = [ex.grade.passed]
        return [(task, v2)]

    def _stable_verdict(self, task: Task, v: Variant, ev: TaskEvidence) -> bool | None:
        """The grader's verdict, confirmed by extra runs when it would raise a flag."""
        runs = ev.grader_runs[v.id]
        flag = v.counts_in_headline and (
            (v.kind.value == "violating" and runs[0])
            or (v.kind.value == "preserving" and not runs[0])
        )
        if flag and self.config.confirm_runs > 0:
            extra = self.runner.repeat(
                task, v.files, self.config.confirm_runs, probes_of(ev.requirements), v.id, start=1
            )
            runs.extend(e.grade.passed for e in extra)
        return runs[0] if len(set(runs)) == 1 else None


def git_sha(cwd: Path | None = None) -> str:
    """HEAD of the repository containing ``cwd`` (``unknown`` outside git)."""
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def dirty_paths(
    paths: Sequence[str] = ("src", "tools", "prereg"), cwd: Path | None = None
) -> list[str]:
    """Uncommitted changes (including untracked files) under ``paths``."""
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *paths],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ["<not a git checkout>"]
    return [line[3:] for line in proc.stdout.splitlines() if line.strip()]


def provenance(config: AuditConfig, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Provenance block for artifacts.

    ``git_dirty`` is true when the code that produced the artifact (``src/``,
    ``tools/``, ``prereg/``) differed from ``git_sha``; ``package_fingerprint`` hashes
    the package source actually loaded.
    """
    return {
        "git_sha": git_sha(),
        "git_dirty": bool(dirty_paths()),
        "package_fingerprint": package_fingerprint(),
        "command": " ".join(sys.argv),
        "created_utc": utc_now(),
        "graderproof_version": __version__,
        "python": platform.python_version(),
        "config": config.to_dict(),
        "config_hash": sha256_text(canonical_json(config.to_dict())),
        **(dict(extra) if extra else {}),
    }


def write_outputs(
    results: Sequence[TaskResult],
    evidence: Sequence[TaskEvidence],
    public_dir: Path,
    evidence_dir: Path,
    config: AuditConfig,
    meta: Mapping[str, Any],
    public_task_ids: bool,
    review_queue: Path | None = None,
) -> dict[str, Any]:
    """Bank tasks.jsonl, variants.jsonl, summary.json (public) and per-task evidence.

    Variants whose validators disagree are excluded from headline numbers and, when
    ``review_queue`` is given, listed in ``<review_queue>/<benchmark>.jsonl`` for a
    human decision (brief section 4).
    """
    public_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with (public_dir / "tasks.jsonl").open("w") as fh:
        for r in results:
            row = r.summary()
            if public_task_ids:
                row["task"] = r.task_key
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    with (public_dir / "variants.jsonl").open("w") as fh:
        for r, ev in zip(results, evidence, strict=True):
            for vr in r.variants:
                rec = variant_record(r.task_hash, vr, witness_hash(ev.witnesses.get(vr.variant.id)))
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
    for r, ev in zip(results, evidence, strict=True):
        (evidence_dir / f"{r.task_hash}.json").write_text(
            json.dumps(ev.to_dict(r), indent=1, sort_keys=True) + "\n"
        )
    if review_queue is not None:
        write_review_queue(results, review_queue / f"{meta.get('benchmark', 'audit')}.jsonl")
    agg = aggregate(results, config.seed, config.replicates)
    summary = {
        "schema": "graderproof.audit/1",
        **dict(meta),
        "bootstrap": {"seed": config.seed, "B": config.replicates, "alpha": 0.05},
        "aggregate": agg.to_dict(),
        "e1": {"false_accept_task_rate": agg.to_dict()["false_accept_task_rate"]},
        "e2": {"false_reject_task_rate": agg.to_dict()["false_reject_task_rate"]},
        "operators": operator_counts(results),
        "n_sampled": len(results),
        "provenance": provenance(config),
    }
    (public_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def write_review_queue(results: Sequence[TaskResult], path: Path) -> int:
    """List every variant whose validators disagree; returns how many were written."""
    rows = [
        {
            "task_hash": r.task_hash,
            "variant_id": vr.variant.id,
            "kind": vr.variant.kind.value,
            "operator": vr.variant.operator,
            "validations": [
                {
                    "validator": x.validator,
                    "verdict": None if x.verdict is None else x.verdict.value,
                    "evidence": x.evidence,
                }
                for x in vr.variant.validations
            ],
        }
        for r in results
        for vr in r.variants
        if vr.variant.validation_status.value == "disagreed"
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    return len(rows)


__all__ = [
    "AuditConfig",
    "Auditor",
    "PendingWorkError",
    "TaskEvidence",
    "context_for",
    "default_generator",
    "provenance",
    "write_outputs",
]
