"""Task-format adapters.

An adapter loads tasks from one benchmark format and executes a candidate solution
and the task's grader inside a sandbox, returning an :class:`Execution`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from graderproof.core import GraderRun, Task
from graderproof.sandbox import Limits, Sandbox
from graderproof.spec import Outcome


@dataclass(frozen=True)
class Execution:
    """One execution of a solution followed by the grader, in a fresh workspace."""

    outcome: Outcome
    grade: GraderRun

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation."""
        return {"outcome": self.outcome.to_dict(), "grade": self.grade.to_dict()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Execution:
        """Inverse of :meth:`to_dict`."""
        return cls(Outcome.from_dict(data["outcome"]), GraderRun.from_dict(data["grade"]))


class Adapter(Protocol):
    """A benchmark task format."""

    name: str

    def load(self, root: Path) -> list[Task]:
        """Load every task under ``root``."""
        ...

    def mutable_files(self, task: Task) -> dict[str, str]:
        """Solution files variants may edit, mapped to their language."""
        ...

    def execute(
        self,
        task: Task,
        solution: Mapping[str, str],
        sandbox: Sandbox,
        probes: Sequence[Mapping[str, Any]] = (),
        limits: Limits | None = None,
        variant_id: str | None = None,
    ) -> Execution:
        """Run ``solution`` for ``task`` and then its grader, both inside ``sandbox``."""
        ...


def language_of(path: str) -> str:
    """Language of a solution file by name: python, shell, trajectory, json, or text."""
    name = path.rsplit("/", 1)[-1]
    if name.endswith(".py"):
        return "python"
    if name.endswith(".sh") or name.endswith(".bash"):
        return "shell"
    if name == "trajectory.json":
        return "trajectory"
    if name.endswith(".json"):
        return "json"
    return "text"
