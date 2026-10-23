"""Model-proposed variants (requirement-targeted and equivalent alternatives).

For each task, a model sees the task text, the reference solution, and the task's
requirements (text only, never the grader or the checks) and proposes:

* for each requirement, a minimal edit of the reference that breaks exactly that
  requirement and keeps the others (``model-violating``);
* a few alternative solutions that satisfy every requirement but differ in form:
  formatting the task text leaves open, another algorithm or tool path, harmless
  reordering or renaming, valid alternative argument forms (``model-preserving``).

Proposals are hypotheses like any other variant; both validators rule on them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from graderproof.core import Task, Variant, VariantKind
from graderproof.models import ModelClient
from graderproof.spec import Requirement
from graderproof.variants import unified_diff

PROPOSE_PROMPT_VERSION = "propose/v1"
MAX_VIOLATING = 6
MAX_PRESERVING = 4

PROPOSE_INSTRUCTIONS = f"""\
You propose modified versions of the reference solution of a software task. For each
item you get the task text, the reference solution files (they satisfy the task), and
the task's numbered requirements. You are not told how the task is graded and must
not guess.

1. "violating": for up to {MAX_VIOLATING} requirements (prefer the most important
   ones), one minimal edit of the reference that breaks exactly that requirement while
   keeping every other requirement satisfied. Make the edit look like a plausible
   mistake (an off-by-one, a skipped step, a wrong field, a partial result, a missing
   confirmation), not sabotage.
2. "preserving": up to {MAX_PRESERVING} alternative solutions that satisfy every
   requirement but differ from the reference in a way an overly strict checker might
   reject: formatting the task text leaves open (whitespace, key order, number format,
   a trailing newline, a code fence around structured output only if the text allows
   it), a different algorithm or tool path, harmless reordering or renaming, or a
   valid alternative argument form. If the task text fixes the exact form, do not
   change it.

Return the full new content of every file you change, using only the reference's
file paths. Do not add comments that describe the change. Return for each item:
{{"violating": [{{"requirement": "R1", "description": "one sentence",
"files": {{"<path>": "<full content>"}}}}], "preserving": [{{"description": "one
sentence", "files": {{"<path>": "<full content>"}}}}]}}.
"""


@dataclass
class ModelProposer:
    """Requests model-proposed variants through the client wrapper."""

    client: ModelClient
    batch_size: int = 4

    def item(self, task: Task, requirements: Sequence[Requirement]) -> dict[str, Any]:
        """The request item for one task (requirement text only; no checks, no grader)."""
        return {
            "id": task.key,
            "task_text": task.instructions,
            "reference_solution": dict(task.reference_solution),
            "requirements": [{"id": r.id, "text": r.text} for r in requirements],
        }

    def propose(
        self, pairs: Sequence[tuple[Task, Sequence[Requirement]]]
    ) -> dict[str, list[Variant]]:
        """Unvalidated variants keyed by task key; raises PendingWorkError until answered."""
        tasks = {t.key: t for t, _ in pairs}
        items = [self.item(t, reqs) for t, reqs in pairs if reqs]
        schema = {"required": ["violating", "preserving"]}
        out: dict[str, list[Variant]] = {key: [] for key in tasks}
        responses = self.client.batch_items(
            "propose", PROPOSE_PROMPT_VERSION, PROPOSE_INSTRUCTIONS, schema, items, self.batch_size
        )
        for key, r in responses.items():
            task = tasks.get(key)
            if task is not None:
                out[key] = to_variants(task, r)
        return out


def to_variants(task: Task, response: Mapping[str, Any]) -> list[Variant]:
    """Variants from one proposal response; malformed or no-op proposals are dropped."""
    variants: list[Variant] = []
    seen: set[str] = set()
    plans = (
        ("violating", VariantKind.VIOLATING, "model-violating", MAX_VIOLATING),
        ("preserving", VariantKind.PRESERVING, "model-preserving", MAX_PRESERVING),
    )
    for key, kind, operator, limit in plans:
        raw = response.get(key)
        if not isinstance(raw, list):
            continue
        for proposal in raw[:limit]:
            files = merged_files(task.reference_solution, proposal)
            if files is None:
                continue
            v = Variant(
                task.id, kind, operator, unified_diff(task.reference_solution, files), files
            )
            if v.id not in seen:
                seen.add(v.id)
                variants.append(v)
    return variants


def merged_files(reference: Mapping[str, str], proposal: Any) -> dict[str, str] | None:
    """The reference with the proposal's file replacements, or None if invalid or unchanged."""
    if not isinstance(proposal, Mapping) or not isinstance(proposal.get("files"), Mapping):
        return None
    changes = proposal["files"]
    if not changes or any(p not in reference or not isinstance(t, str) for p, t in changes.items()):
        return None
    files = {**dict(reference), **{str(p): str(t) for p, t in changes.items()}}
    return None if files == dict(reference) else files
