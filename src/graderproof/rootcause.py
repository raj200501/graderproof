"""E3: root causes of grader errors, coded twice (rule-based and model) with agreement.

Every flagged variant (a counted violating variant the grader accepts, or a counted
preserving variant it rejects) and every task whose grader rejects or is flaky on the
reference gets one code from a fixed taxonomy (RQ3):

* accept side: ``presence-not-content``, ``exit-code-only``, ``loose-matching``,
  ``outcome-only-process``, ``coverage-gap`` (the checks never exercise the broken
  behavior), ``other-accept``;
* reject side: ``brittle-parsing`` (a harmless form difference is rejected),
  ``timing``, ``over-specification`` (the grader demands something the task text
  leaves open, such as an order or a tool path), ``other-reject``.

The rule-based coder uses the variant's operator, the check types of the
requirements its witness names, and the grader's lint smells. The model coder sees the
task text, the grader source, the variant diff, and the witness, and is not told the
rule-based code. Agreement is reported as raw agreement and Cohen's kappa.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from graderproof.core import Task
from graderproof.lint import lint_task
from graderproof.models import ModelClient

ROOTCAUSE_PROMPT_VERSION = "rootcause/v1"
ACCEPT_CODES = (
    "presence-not-content",
    "exit-code-only",
    "loose-matching",
    "outcome-only-process",
    "coverage-gap",
    "other-accept",
)
REJECT_CODES = ("brittle-parsing", "timing", "over-specification", "other-reject")
CODES = ACCEPT_CODES + REJECT_CODES
CONTENT_CHECKS = frozenset(
    {
        "file_equals",
        "file_contains",
        "file_regex",
        "file_json",
        "file_lines",
        "stdout_contains",
        "stdout_regex",
        "stdout_json",
        "same_as_reference",
        "state_equals",
        "call",
    }
)
PROCESS_CHECKS = frozenset({"trajectory_includes", "trajectory_excludes", "trajectory_before"})
FORMAT_OPERATORS = ("out-", "stdout-", "sh-echo-printf", "py-rename-locals")
ORDER_OPERATORS = ("traj-swap-independent", "traj-add-readonly")
PROCESS_OPERATORS = ("traj-drop-confirmation", "traj-reorder-dependent", "traj-drop-call")

ROOTCAUSE_INSTRUCTIONS = f"""\
You classify why a benchmark grader misjudged a solution. For each item you get the
task text, the grader's source files, the kind of error ("accepts a violating
solution" or "rejects a valid solution"), a unified diff from the reference solution
to the misjudged solution, and the requirement the solution breaks or keeps.

Choose exactly one code. For accepted violating solutions: presence-not-content (the
grader checks that something exists or has the right keys or shape, not its content),
exit-code-only (it trusts an exit status or the absence of an error), loose-matching
(its comparison is looser than the task demands: substring, prefix, case-insensitive,
permissive pattern, wide tolerance, partial set), outcome-only-process (the task
requires a step, order, or confirmation and the grader checks only the end result),
coverage-gap (the grader's checks never exercise the broken behavior, for example too
few test inputs), other-accept. For rejected valid solutions: brittle-parsing (a
harmless difference in form is rejected: whitespace, newline, key order, number format,
a code fence), timing (a time limit or timing-dependent check), over-specification
(the grader demands an order, tool path, name, or detail the task text leaves open),
other-reject. Return for each item {{"code": one of {list(CODES)}, "reason": "one
sentence citing the grader line"}}.
"""


@dataclass(frozen=True)
class CodingItem:
    """One misjudgment to code."""

    id: str
    task: Task
    direction: str
    operator: str
    diff: str
    witness: Mapping[str, Any] | None

    def broken_check_types(self, requirements: Mapping[str, Mapping[str, Any]]) -> set[str]:
        """Check types of the requirements the witness names (broken or held)."""
        if not self.witness:
            return set()
        ids = [b["requirement"] for b in self.witness.get("broken", [])] or list(
            self.witness.get("held", [])
        )
        return {
            str(c.get("type")) for rid in ids for c in requirements.get(rid, {}).get("checks", [])
        }


def items_from_evidence(task: Task, evidence: Mapping[str, Any]) -> list[CodingItem]:
    """Every flagged variant of one task, plus a reference-level item when relevant."""
    out: list[CodingItem] = []
    for v in evidence.get("variants", []):
        if not v.get("counted_in_headline") or v.get("grader_passed") is None:
            continue
        if v.get("kind") == "violating" and v.get("grader_passed") is True:
            direction = "accept"
        elif v.get("kind") == "preserving" and v.get("grader_passed") is False:
            direction = "reject"
        else:
            continue
        out.append(
            CodingItem(
                str(v["id"]),
                task,
                direction,
                str(v.get("operator", "")),
                str(v.get("diff", "")),
                v.get("witness"),
            )
        )
    det = evidence.get("determinism")
    if det in ("flaky", "stable_fail"):
        out.append(
            CodingItem(f"{task.key_hash}:reference", task, "reject", f"reference-{det}", "", None)
        )
    return out


def rule_code(item: CodingItem, requirements: Mapping[str, Mapping[str, Any]]) -> str:
    """The rule-based code for one item."""
    smells = {s.rule for s in lint_task(item.task).smells}
    if item.direction == "reject":
        return _reject_code(item.operator, smells)
    return _accept_code(item.operator, smells, item.broken_check_types(requirements))


def _reject_code(op: str, smells: set[str]) -> str:
    if op in {"reference-flaky", "pre-delay"} or "timing" in smells:
        return "timing"
    if op.startswith(FORMAT_OPERATORS) or "exact-text" in smells:
        return "brittle-parsing"
    if op.startswith(ORDER_OPERATORS) or op == "model-preserving":
        return "over-specification"
    return "other-reject"


def _accept_code(op: str, smells: set[str], types: set[str]) -> str:
    process_only = bool(types & PROCESS_CHECKS) and not types & CONTENT_CHECKS
    process_variant = op.startswith(PROCESS_OPERATORS) and "outcome-only-process" in smells
    rules = (
        (process_only or process_variant, "outcome-only-process"),
        ("exit-code-only" in smells, "exit-code-only"),
        (
            bool(smells & {"existence-only", "membership"} and types & CONTENT_CHECKS),
            "presence-not-content",
        ),
        ("loose-match" in smells, "loose-matching"),
        ("few-checks" in smells or "call" in types, "coverage-gap"),
    )
    return next((code for hit, code in rules if hit), "other-accept")


@dataclass
class ModelCoder:
    """Second, independent coder: a model reads the grader and the misjudged solution."""

    client: ModelClient
    batch_size: int = 25

    def item(self, ci: CodingItem) -> dict[str, Any]:
        """The request item for one misjudgment (never the rule-based code)."""
        witness: Any = None
        if ci.witness:
            witness = ci.witness.get("broken") or {"held": ci.witness.get("held")}
        return {
            "id": ci.id,
            "task_text": ci.task.instructions[:6000],
            "grader_files": {
                p: t[:6000] for p, t in ci.task.environment.get("grader_files", {}).items()
            },
            "error": "accepts a violating solution"
            if ci.direction == "accept"
            else "rejects a valid solution",
            "diff_from_reference": ci.diff[:6000],
            "requirement": witness,
        }

    def code(self, items: Sequence[CodingItem]) -> dict[str, str]:
        """Model codes keyed by item id; raises PendingWorkError until answered."""
        schema = {"required": ["code", "reason"], "enums": {"code": list(CODES)}}
        payload = [self.item(i) for i in items]
        answers = self.client.batch_items(
            "rootcause",
            ROOTCAUSE_PROMPT_VERSION,
            ROOTCAUSE_INSTRUCTIONS,
            schema,
            payload,
            self.batch_size,
        )
        return {k: str(v["code"]) for k, v in answers.items()}


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float | None:
    """Cohen's kappa for two coders over the same items (None if undefined)."""
    if len(a) != len(b):
        raise ValueError("coders must code the same items")
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[c] * cb[c] for c in set(ca) | set(cb)) / (n * n)
    if expected == 1.0:
        return None
    return (observed - expected) / (1 - expected)


def agreement(a: Sequence[str], b: Sequence[str]) -> dict[str, Any]:
    """Raw agreement, kappa, and the confusion counts."""
    n = len(a)
    confusion = Counter(zip(a, b, strict=True))
    return {
        "n": n,
        "raw": (sum(x == y for x, y in zip(a, b, strict=True)) / n) if n else None,
        "kappa": cohen_kappa(a, b),
        "confusion": {f"{x}|{y}": c for (x, y), c in sorted(confusion.items())},
    }
