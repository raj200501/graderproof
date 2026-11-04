"""Variant generation from a task's reference solution.

Operators propose edited copies of the reference solution, each with an intended
label: ``violating`` (meant to break a requirement) or ``preserving`` (meant to keep
every requirement). The label is only a hypothesis until :mod:`graderproof.validate`
confirms it with two independent validations.
"""

from __future__ import annotations

import difflib
import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from graderproof.core import Variant, VariantKind


@dataclass(frozen=True)
class Proposal:
    """One operator application: edited solution files plus a description."""

    kind: VariantKind
    operator: str
    files: Mapping[str, str]
    description: str
    target: str = ""


@dataclass(frozen=True)
class Context:
    """What operators may know about a task besides its solution files.

    Attributes:
        languages: Solution file path to language.
        entry: The solution entry file for script tasks ("" otherwise).
        outputs: Workspace files the reference solution creates or changes.
        json_outputs: The subset of ``outputs`` that hold a JSON object or array.
        stdout_json: Whether the reference prints JSON on stdout.
        stdout_nonempty: Whether the reference prints anything on stdout.
        kind: The task kind (``script``, ``module``, ``trajectory``, or ``data``).
        timeout_s: The task's time limit in seconds.
    """

    languages: Mapping[str, str]
    entry: str = ""
    outputs: Sequence[str] = ()
    json_outputs: Sequence[str] = ()
    stdout_json: bool = False
    stdout_nonempty: bool = False
    kind: str = "script"
    timeout_s: float = 0.0


Operator = Callable[[Mapping[str, str], Context], Iterable[Proposal]]


def unified_diff(before: Mapping[str, str], after: Mapping[str, str]) -> str:
    """Unified diff between two solution file sets."""
    chunks: list[str] = []
    for path in sorted(set(before) | set(after)):
        a = before.get(path, "").splitlines(keepends=True)
        b = after.get(path, "").splitlines(keepends=True)
        if a != b:
            chunks.extend(difflib.unified_diff(a, b, f"a/{path}", f"b/{path}"))
    return "".join(c if c.endswith("\n") else c + "\n" for c in chunks)


@dataclass
class Generator:
    """Applies a set of operators and samples a bounded, stratified set of variants."""

    operators: Sequence[Operator] = field(default_factory=list)
    max_per_operator: int = 6
    max_total: int = 40
    seed: int = 0

    def proposals(self, files: Mapping[str, str], ctx: Context) -> list[Proposal]:
        """All distinct proposals, deduplicated by resulting files."""
        seen: set[tuple[tuple[str, str], ...]] = {tuple(sorted(files.items()))}
        out: list[Proposal] = []
        for op in self.operators:
            for p in op(files, ctx):
                key = tuple(sorted(p.files.items()))
                if key not in seen:
                    seen.add(key)
                    out.append(p)
        return out

    def sample(self, proposals: Sequence[Proposal], salt: str) -> list[Proposal]:
        """At most ``max_per_operator`` per operator and ``max_total`` overall, seeded.

        When the per-operator sample still exceeds ``max_total``, preserving variants
        keep a reserved share (up to a third of ``max_total``, more if violating
        variants are scarce), so a single format variant that would expose a brittle
        grader is not dropped by chance among many violating ones.
        """
        rng = random.Random(f"{self.seed}:{salt}")
        by_op: dict[str, list[Proposal]] = {}
        for p in proposals:
            by_op.setdefault(p.operator, []).append(p)
        picked: list[Proposal] = []
        for op in sorted(by_op):
            group = by_op[op]
            if len(group) > self.max_per_operator:
                group = rng.sample(group, self.max_per_operator)
            picked.extend(group)
        if len(picked) > self.max_total:
            pres = [p for p in picked if p.kind is VariantKind.PRESERVING]
            viol = [p for p in picked if p.kind is VariantKind.VIOLATING]
            n_pres = min(len(pres), max(self.max_total // 3, self.max_total - len(viol)))
            n_viol = min(len(viol), self.max_total - n_pres)
            picked = rng.sample(pres, n_pres) + rng.sample(viol, n_viol)
        return sorted(picked, key=lambda p: (p.operator, p.target, p.description))

    def variants(self, task_id: str, files: Mapping[str, str], ctx: Context) -> list[Variant]:
        """Sampled proposals as unvalidated :class:`Variant` objects."""
        chosen = self.sample(self.proposals(files, ctx), salt=task_id)
        return [
            Variant(
                task_id=task_id,
                kind=p.kind,
                operator=p.operator,
                diff=unified_diff(files, p.files),
                files=dict(p.files),
            )
            for p in chosen
        ]
