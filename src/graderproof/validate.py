"""Independent validation of variant labels, and requirement extraction.

Two validators rule on every variant, and they never see the grader:

* :func:`witness_validation` (deterministic): evaluates the task's requirements on
  the reference outcome and the variant outcome. A requirement that holds on the
  reference and fails on the variant is a machine-checkable witness of a violation; a
  variant on which every reference-satisfied requirement still holds is differential
  evidence of preservation.
* :class:`ModelReviewer`: a model reads the task text, the reference solution, and
  the variant's diff (not its operator, not its intended label, not the witness) and
  rules ``violating``, ``preserving``, or ``unsure``.

Requirements come from :class:`RequirementExtractor`, which shows a model the task
text, the reference solution, and the reference outcome, never the grader.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from graderproof.core import Task, Validation, Variant, VariantKind, canonical_json, sha256_text
from graderproof.models import ModelClient
from graderproof.spec import CHECK_TYPES, Outcome, Requirement, holds

WITNESS_VALIDATOR = "witness:requirements/v1"
REVIEW_PROMPT_VERSION = "review/v1"
EXTRACT_PROMPT_VERSION = "requirements/v1"
MAX_TEXT = 4000

REVIEW_INSTRUCTIONS = """\
You review modified solutions to software tasks. For each item you get the task text,
the original reference solution (which satisfies the task), and a modified solution
(as a unified diff plus the full changed files). Decide whether the modified solution
still satisfies every requirement that the task text states or clearly implies.

Answer "violating" if it breaks at least one requirement (name it), "preserving" if it
satisfies all of them, or "unsure" if you cannot tell. Judge only against the task
text: a change in formatting, naming, ordering, or implementation is "preserving"
unless the task text requires the exact form that changed. A change that makes the
solution crash, produce a different result, skip a required step, write to the wrong
place, or omit required output is "violating". You are not told how the task is
graded and must not guess; do not reward or penalize anything for how a checker might
react.
Return for each item: {"verdict": "violating"|"preserving"|"unsure",
"requirement": "<the broken requirement, or empty>", "reason": "<one sentence>"}.
"""

EXTRACT_INSTRUCTIONS = """\
You turn a task's text into atomic, machine-checkable requirements. For each item you
get the task text, the task kind, the reference solution (it satisfies the task), the
initial workspace, and what the reference produced (files, stdout, exit status, tool
calls, final state). You are not shown how the task is graded and must not guess.

Write one requirement per distinct obligation in the task text (outputs, their
content, required steps, ordering constraints, prohibited actions, policies). Each
requirement has an "id" (R1, R2, ...), "text" (the obligation in plain words, quoting
the task where possible), and "checks": a list of typed checks that pass on the
reference outcome and fail when the obligation is broken. Allowed check types and
fields: file_exists {path}; file_absent {path}; file_equals {path, text, normalize:
none|strip|trailing_ws}; file_contains {path, text}; file_regex {path, pattern};
file_json {path, pointer, equals, lenient}; file_lines {path, count};
stdout_contains {text}; stdout_regex {pattern}; stdout_json {pointer, equals,
lenient}; exit_code {code}; call {probe: {function, args, kwargs}, equals} or
{probe, matches_reference: true}; same_as_reference {target: stdout|state|file:<path>,
normalize}; trajectory_includes {tool, args}; trajectory_excludes {tool, args};
trajectory_before {first: {tool, args}, then: {tool, args}}; state_equals {pointer,
equals}.

Be exactly as strict as the task text. If the text demands an exact format, check it
exactly; if it only asks for content, check content (use "normalize" or "lenient" so
that harmless formatting does not fail the check). For function tasks, add call
probes on the examples in the text and on a few further valid inputs, using
matches_reference for inputs whose expected output the text does not state. Return
for each item: {"requirements": [ ... ]}.
"""


def witness_validation(
    variant: Variant,
    requirements: Sequence[Requirement],
    reference: Outcome,
    outcome: Outcome,
) -> tuple[Validation, dict[str, Any] | None]:
    """Deterministic ruling plus the witness supporting it (None if no evidence)."""
    broken: list[dict[str, Any]] = []
    held: list[str] = []
    for req in requirements:
        ok_ref, _ = holds(req, reference, reference)
        if not ok_ref:
            continue
        ok, results = holds(req, outcome, reference)
        if ok:
            held.append(req.id)
        else:
            broken.append(
                {
                    "requirement": req.id,
                    "text": req.text,
                    "failed": [r.detail for r in results if not r.passed],
                }
            )
    if broken:
        witness = {"type": "requirement-broken", "variant": variant.id, "broken": broken}
        first = broken[0]
        return Validation(
            WITNESS_VALIDATOR,
            VariantKind.VIOLATING,
            f"{first['requirement']}: {first['failed'][0]}",
        ), witness
    if held:
        witness = {"type": "all-requirements-hold", "variant": variant.id, "held": held}
        return Validation(
            WITNESS_VALIDATOR, VariantKind.PRESERVING, f"{len(held)} requirements hold"
        ), witness
    return Validation(WITNESS_VALIDATOR, None, "no valid requirements"), None


def witness_hash(witness: Mapping[str, Any] | None) -> str | None:
    """SHA-256 of a witness's canonical JSON."""
    return None if witness is None else sha256_text(canonical_json(dict(witness)))


def _clip(text: str, limit: int = MAX_TEXT) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n[... {len(text) - limit} more chars]"


@dataclass
class ModelReviewer:
    """Second, independent validator: a model review of the variant against the task text."""

    client: ModelClient
    model_label: str = "claude-subagent"
    batch_size: int = 25

    @property
    def name(self) -> str:
        """Validator name recorded on each validation."""
        return f"model:{self.model_label}/{REVIEW_PROMPT_VERSION}"

    def item(self, task: Task, variant: Variant) -> dict[str, Any]:
        """The request item for one variant (no operator, label, witness, or grader)."""
        changed = {
            p: _clip(t) for p, t in variant.files.items() if task.reference_solution.get(p) != t
        }
        return {
            "id": variant.id,
            "task_text": _clip(task.instructions),
            "reference_solution": {p: _clip(t) for p, t in task.reference_solution.items()},
            "modified_diff": _clip(variant.diff),
            "modified_files": changed,
        }

    def review(self, pairs: Sequence[tuple[Task, Variant]]) -> dict[str, Validation]:
        """Validations keyed by variant id; raises PendingResponseError until answered."""
        items = [self.item(t, v) for t, v in pairs]
        schema = {
            "required": ["verdict", "reason"],
            "enums": {"verdict": ["violating", "preserving", "unsure"]},
        }
        out: dict[str, Validation] = {}
        responses = self.client.batch_items(
            "review", REVIEW_PROMPT_VERSION, REVIEW_INSTRUCTIONS, schema, items, self.batch_size
        )
        for vid, r in responses.items():
            verdict = r.get("verdict")
            kind = VariantKind(verdict) if verdict in ("violating", "preserving") else None
            reason = str(r.get("reason", ""))
            if r.get("requirement"):
                reason = f"{r['requirement']}: {reason}"
            out[vid] = Validation(self.name, kind, reason[:300])
        return out


@dataclass
class RequirementExtractor:
    """Requirements from the task text via the model client (never shown the grader)."""

    client: ModelClient
    batch_size: int = 8

    def item(self, task: Task, reference: Outcome) -> dict[str, Any]:
        """The request item for one task."""
        env = task.environment
        return {
            "id": task.key,
            "kind": str(env.get("kind", "")),
            "task_text": _clip(task.instructions, 8000),
            "reference_solution": {p: _clip(t) for p, t in task.reference_solution.items()},
            "initial_workspace": {
                p: _clip(t, 1000) for p, t in env.get("workspace_files", {}).items()
            },
            "reference_outcome": {
                "files": {p: _clip(t, 2000) for p, t in reference.files.items()},
                "stdout": _clip(reference.stdout, 2000),
                "exit_status": reference.exit_status,
                "trajectory": [dict(c) for c in reference.trajectory][:50],
                "state": json.loads(json.dumps(reference.state))
                if reference.state is not None
                else None,
            },
        }

    def extract(self, pairs: Sequence[tuple[Task, Outcome]]) -> dict[str, list[Requirement]]:
        """Requirements keyed by task key; malformed requirements are dropped."""
        items = [self.item(t, o) for t, o in pairs]
        schema = {"required": ["requirements"]}
        responses = self.client.batch_items(
            "requirements",
            EXTRACT_PROMPT_VERSION,
            EXTRACT_INSTRUCTIONS,
            schema,
            items,
            self.batch_size,
        )
        return {
            key: parse_requirements(
                r.get("requirements", []), source=f"model:{EXTRACT_PROMPT_VERSION}"
            )
            for key, r in responses.items()
        }


def parse_requirements(raw: Sequence[Any], source: str) -> list[Requirement]:
    """Requirements from model output, dropping any that are malformed."""
    reqs: list[Requirement] = []
    for r in raw:
        if not isinstance(r, Mapping):
            continue
        checks = [
            c
            for c in r.get("checks", [])
            if isinstance(c, Mapping) and c.get("type") in CHECK_TYPES
        ]
        if not checks or not r.get("id"):
            continue
        try:
            reqs.append(
                Requirement(
                    id=str(r["id"]),
                    text=str(r.get("text", "")),
                    checks=tuple(dict(c) for c in checks),
                    source=source,
                )
            )
        except (ValueError, KeyError, TypeError):
            continue
    return reqs


def valid_requirements(
    requirements: Sequence[Requirement], references: Sequence[Outcome]
) -> tuple[list[Requirement], list[Requirement]]:
    """Split requirements into those holding on every reference run and the rest."""
    good: list[Requirement] = []
    bad: list[Requirement] = []
    for req in requirements:
        try:
            ok = all(holds(req, ref, references[0])[0] for ref in references)
        except (ValueError, KeyError, TypeError):
            ok = False
        (good if ok else bad).append(req)
    return good, bad
