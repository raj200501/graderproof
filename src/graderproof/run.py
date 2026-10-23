"""Grader execution with content-addressed caching and a determinism pre-check.

The :class:`Runner` executes a solution plus grader through an adapter and a sandbox.
Results are cached by a content address over the adapter, the task, the solution
files, the probes, the sandbox backend, and the repetition index, so a run is never
repeated. Before any variant is graded, :meth:`Runner.precheck` runs the unmodified
reference ``k`` times: tasks whose grader does not pass the reference stably are
reported (flaky or rejecting the reference), never silently dropped.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from graderproof.adapters import Adapter, Execution
from graderproof.core import Determinism, Task, canonical_json, determinism, sha256_text
from graderproof.sandbox import Limits, Sandbox


class SandboxPolicyError(RuntimeError):
    """A task needs a stronger sandbox than the one available."""


@dataclass
class Runner:
    """Executes solutions and graders for one adapter in one sandbox."""

    adapter: Adapter
    sandbox: Sandbox
    cache_dir: Path | None = None
    limits: Limits | None = None
    executions: int = field(default=0, init=False)
    cache_hits: int = field(default=0, init=False)

    def check_policy(self, task: Task) -> None:
        """Third-party tasks need a sandbox that isolates writes (section 8)."""
        if not self.sandbox.isolates_writes and not task.metadata.get("trusted_local"):
            raise SandboxPolicyError(
                f"{task.key}: third-party task needs a write-isolating sandbox, "
                f"have {self.sandbox.name}"
            )

    def key(
        self,
        task: Task,
        solution: Mapping[str, str],
        probes: Sequence[Mapping[str, Any]],
        index: int,
    ) -> str:
        """Content address of one execution."""
        return sha256_text(
            canonical_json(
                {
                    "adapter": self.adapter.name,
                    "task": task.content_hash(),
                    "solution": dict(solution),
                    "probes": [dict(p) for p in probes],
                    "backend": self.sandbox.name,
                    "index": index,
                }
            )
        )

    def execute(
        self,
        task: Task,
        solution: Mapping[str, str],
        probes: Sequence[Mapping[str, Any]] = (),
        index: int = 0,
        variant_id: str | None = None,
    ) -> Execution:
        """One execution, served from the cache when present."""
        self.check_policy(task)
        key = self.key(task, solution, probes, index)
        path = self.cache_dir / key[:2] / f"{key}.json" if self.cache_dir else None
        if path is not None and path.exists():
            self.cache_hits += 1
            return Execution.from_dict(json.loads(path.read_text()))
        result = self.adapter.execute(
            task, solution, self.sandbox, probes, self.limits, variant_id=variant_id
        )
        self.executions += 1
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result.to_dict(), sort_keys=True))
        return result

    def repeat(
        self,
        task: Task,
        solution: Mapping[str, str],
        k: int,
        probes: Sequence[Mapping[str, Any]] = (),
        variant_id: str | None = None,
        start: int = 0,
    ) -> list[Execution]:
        """``k`` independent executions (repetition indices ``start`` to ``start + k - 1``)."""
        return [
            self.execute(task, solution, probes, index=i, variant_id=variant_id)
            for i in range(start, start + k)
        ]

    def precheck(
        self, task: Task, k: int, probes: Sequence[Mapping[str, Any]] = ()
    ) -> tuple[Determinism, list[Execution]]:
        """Grade the unmodified reference ``k`` times and classify the grader's behavior."""
        runs = self.repeat(task, task.reference_solution, k, probes)
        return determinism([r.grade for r in runs]), runs
