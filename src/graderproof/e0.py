"""E0 tool validity: graderproof's flags on toybench scored against the planted labels.

Definitions (frozen in prereg/0001-e0-tool-validity.md):

* A task is **flagged** when graderproof reports a false accept, a false reject, a
  grader that rejects the reference, or a grader that is flaky on the reference.
* A planted task is **detected** when it is flagged in the planted direction:
  ``accept`` weaknesses need a false-accept flag; ``reject`` weaknesses need a
  false-reject flag, a rejected reference, or a flaky grader (each rejects some
  solution that satisfies the task).
* **Recall** is detected planted tasks over planted tasks; **precision** is detections
  over detections plus false positives, where a false positive is a flag that is not a
  detection and was not adjudicated a real weakness. Precision without adjudication
  is reported beside it. Both use the task bootstrap in :mod:`graderproof.stats`
  (recall ``seed``, precision ``seed + 1``).
* The ``extra`` slice (weakness types outside the written list) is reported
  separately and is not counted in recall or precision.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from graderproof.stats import Estimate, recall_precision

FLAG_KEYS = ("false_accept", "false_reject", "reference_rejected", "flaky")


@dataclass(frozen=True)
class TaskScore:
    """One toybench task: its label and graderproof's flags."""

    task: str
    planted: bool
    slice: str
    weakness_type: str | None
    direction: str | None
    flags: Mapping[str, bool]
    adjudicated_real: bool

    @property
    def flagged(self) -> bool:
        """Any flag at all."""
        return any(self.flags.get(k, False) for k in FLAG_KEYS)

    @property
    def detected(self) -> bool:
        """Flagged in the planted direction (False for unplanted tasks)."""
        if not self.planted:
            return False
        if self.direction == "accept":
            return bool(self.flags.get("false_accept"))
        if self.direction == "reject":
            return any(
                self.flags.get(k, False) for k in ("false_reject", "reference_rejected", "flaky")
            )
        return False

    def row(self) -> dict[str, Any]:
        """The per-task record banked in results.json."""
        return {
            "task": self.task,
            "planted": self.planted,
            "slice": self.slice,
            "weakness_type": self.weakness_type,
            "direction": self.direction,
            "flags": {k: bool(self.flags.get(k, False)) for k in FLAG_KEYS},
            "flagged": self.flagged,
            "detected": self.detected,
            "adjudicated_real": self.adjudicated_real,
        }


def task_scores(
    audit_rows: Sequence[Mapping[str, Any]],
    labels: Mapping[str, Mapping[str, Any]],
    adjudication: Mapping[str, Mapping[str, Any]],
) -> list[TaskScore]:
    """Join audit task rows (with public ``task`` ids) and labels.

    Raises:
        ValueError: if a task is missing from either side, or a label is malformed.
    """
    by_task = {str(r["task"]): r for r in audit_rows}
    task_ids = {t.split(":", 1)[-1]: t for t in by_task}
    missing = sorted(set(labels) - set(task_ids))
    extra = sorted(set(task_ids) - set(labels))
    if missing or extra:
        raise ValueError(f"labels and audit disagree: missing {missing[:5]}, unlabeled {extra[:5]}")
    scores = []
    for tid in sorted(labels):
        lab = labels[tid]
        row = by_task[task_ids[tid]]
        if lab.get("planted") and lab.get("direction") not in ("accept", "reject"):
            raise ValueError(f"{tid}: planted task needs direction accept or reject")
        ts = TaskScore(
            task=tid,
            planted=bool(lab.get("planted")),
            slice=str(lab.get("slice")),
            weakness_type=lab.get("weakness_type"),
            direction=lab.get("direction"),
            flags={k: bool(row.get(k, False)) for k in FLAG_KEYS},
            adjudicated_real=False,
        )
        real = bool(adjudication.get(tid, {}).get("real", False))
        scores.append(
            replace(ts, adjudicated_real=real) if real and ts.flagged and not ts.detected else ts
        )
    return scores


def needs_adjudication(scores: Sequence[TaskScore]) -> list[TaskScore]:
    """Flags that are not detections: each must be adjudicated real or not."""
    return [s for s in scores if s.flagged and not s.detected]


def score(
    scores: Sequence[TaskScore], seed: int, replicates: int, alpha: float = 0.05
) -> dict[str, Any]:
    """Recall, precision (with and without adjudication), per-type and extra-slice counts."""
    counted = [s for s in scores if s.slice != "extra"]
    planted = [s.planted for s in counted]
    detected = [s.detected for s in counted]
    flagged = [s.flagged for s in counted]
    real = [s.adjudicated_real for s in counted]
    adj = recall_precision(planted, detected, flagged, real, seed, replicates, alpha)
    raw = recall_precision(
        planted, detected, flagged, [False] * len(counted), seed, replicates, alpha
    )
    by_type: dict[str, dict[str, int]] = {}
    for s in scores:
        if s.planted:
            row = by_type.setdefault(f"{s.slice}:{s.weakness_type}", {"planted": 0, "detected": 0})
            row["planted"] += 1
            row["detected"] += s.detected
    extra = [s for s in scores if s.slice == "extra"]
    return {
        "n_counted": len(counted),
        "n_planted": sum(planted),
        "n_clean": len(counted) - sum(planted),
        "recall": _est(adj[0] if adj else None),
        "precision": _est(adj[1] if adj else None),
        "precision_unadjudicated": _est(raw[1] if raw else None),
        "by_type": dict(sorted(by_type.items())),
        "extra_slice": {"n": len(extra), "detected": sum(s.detected for s in extra)},
        "misses": [s.task for s in counted if s.planted and not s.detected],
        "false_positives": [
            s.task for s in counted if s.flagged and not s.detected and not s.adjudicated_real
        ],
        "adjudicated_real": [s.task for s in counted if s.adjudicated_real],
        "extra_misses": [s.task for s in extra if not s.detected],
    }


def _est(e: Estimate | None) -> dict[str, Any] | None:
    return None if e is None else {"point": e.point, "ci": [e.lo, e.hi], "n": e.n}
