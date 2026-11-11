"""E0 tool validity: graderproof's flags on toybench scored against the planted labels.

Definitions (DECISIONS.md D23, frozen in prereg/0001-e0-tool-validity.md):

* A task is **flagged** when graderproof reports a witness-backed false accept or false
  reject. A grader that rejects the reference or is flaky on it is reported
  separately and is never a flag or a detection.
* A planted task is **detected** when it is flagged in the planted direction:
  ``accept`` weaknesses need a false accept, ``reject`` weaknesses a false reject.
* **Recall** is detected planted tasks over planted tasks; **precision** is detections
  over detections plus false positives, where a false positive is a flag that is not a
  detection and whose witness the adjudicator did not validate. Precision without
  adjudication is reported beside it. Both use the task bootstrap in
  :mod:`graderproof.stats` (recall ``seed``, precision ``seed + 1``); exact
  Clopper-Pearson intervals are reported beside them (exploratory).
* The ``extra`` slice (weakness types outside the written list) is reported
  separately and is not counted in recall or precision.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from graderproof.stats import Estimate, clopper_pearson, recall_precision

FLAG_KEYS = ("false_accept", "false_reject", "reference_rejected", "flaky")
SLICES = ("in_list", "clean", "extra")
DIRECTIONS = ("accept", "reject")


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
        """A witness-backed false accept or false reject."""
        return bool(self.flags.get("false_accept") or self.flags.get("false_reject"))

    @property
    def reference_level(self) -> bool:
        """The grader rejected the reference or was flaky on it (reported separately)."""
        return bool(self.flags.get("reference_rejected") or self.flags.get("flaky"))

    @property
    def detected(self) -> bool:
        """Flagged in the planted direction (False for unplanted tasks)."""
        if not self.planted:
            return False
        if self.direction == "accept":
            return bool(self.flags.get("false_accept"))
        if self.direction == "reject":
            return bool(self.flags.get("false_reject"))
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
            "reference_level": self.reference_level,
            "adjudicated_real": self.adjudicated_real,
        }


def validate_labels(labels: Mapping[str, Mapping[str, Any]]) -> None:
    """Reject malformed labels: unknown slices, planted flags that disagree with the slice,
    or planted tasks without a direction.

    Raises:
        ValueError: on the first malformed label.
    """
    for tid, lab in labels.items():
        sl = lab.get("slice")
        if sl not in SLICES:
            raise ValueError(f"{tid}: slice {sl!r} is not one of {SLICES}")
        planted = lab.get("planted")
        if not isinstance(planted, bool) or planted != (sl != "clean"):
            raise ValueError(f"{tid}: planted must be true exactly when the slice is not clean")
        if planted and lab.get("direction") not in DIRECTIONS:
            raise ValueError(f"{tid}: planted task needs direction accept or reject")


def task_scores(
    audit_rows: Sequence[Mapping[str, Any]],
    labels: Mapping[str, Mapping[str, Any]],
    adjudication: Mapping[str, Mapping[str, Any]],
) -> list[TaskScore]:
    """Join audit task rows (with public ``task`` ids), labels, and adjudications.

    Raises:
        ValueError: if a task is missing from either side, a label is malformed, or an
            adjudication's ``real`` is not a JSON boolean.
    """
    validate_labels(labels)
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
        ts = TaskScore(
            task=tid,
            planted=bool(lab.get("planted")),
            slice=str(lab.get("slice")),
            weakness_type=lab.get("weakness_type"),
            direction=lab.get("direction"),
            flags={k: bool(row.get(k, False)) for k in FLAG_KEYS},
            adjudicated_real=False,
        )
        ruling = adjudication.get(tid)
        if ruling is not None and not isinstance(ruling.get("real"), bool):
            raise ValueError(f"{tid}: adjudication 'real' must be true or false")
        real = ruling is not None and ruling.get("real") is True
        scores.append(
            replace(ts, adjudicated_real=True) if real and ts.flagged and not ts.detected else ts
        )
    return scores


def needs_adjudication(scores: Sequence[TaskScore]) -> list[TaskScore]:
    """Flags that are not detections: each must be adjudicated real or not."""
    return [s for s in scores if s.flagged and not s.detected]


def score(
    scores: Sequence[TaskScore], seed: int, replicates: int, alpha: float = 0.05
) -> dict[str, Any]:
    """Recall, precision (with and without adjudication), and the separate reports."""
    counted = [s for s in scores if s.slice != "extra"]
    planted = [s.planted for s in counted]
    detected = [s.detected for s in counted]
    flagged = [s.flagged for s in counted]
    real = [s.adjudicated_real for s in counted]
    recall, precision = recall_precision(planted, detected, flagged, real, seed, replicates, alpha)
    _, raw_precision = recall_precision(
        planted, detected, flagged, [False] * len(counted), seed, replicates, alpha
    )
    tp = sum(detected)
    fp = sum(1 for s in counted if s.flagged and not s.detected and not s.adjudicated_real)
    by_type: dict[str, dict[str, int]] = {}
    for s in scores:
        if s.planted:
            row = by_type.setdefault(f"{s.slice}:{s.weakness_type}", {"planted": 0, "detected": 0})
            row["planted"] += 1
            row["detected"] += s.detected
    extra = [s for s in scores if s.slice == "extra"]
    timing = [s for s in counted if s.planted and s.weakness_type == "timing"]
    return {
        "n_counted": len(counted),
        "n_planted": sum(planted),
        "n_clean": len(counted) - sum(planted),
        "recall": _est(recall),
        "precision": _est(precision),
        "precision_unadjudicated": _est(raw_precision),
        "exact_intervals": {
            "method": "Clopper-Pearson (exploratory)",
            "recall": _ci(clopper_pearson(tp, sum(planted), alpha)),
            "precision": _ci(clopper_pearson(tp, tp + fp, alpha)),
        },
        "by_type": dict(sorted(by_type.items())),
        "extra_slice": {"n": len(extra), "detected": sum(s.detected for s in extra)},
        "reference_level": {
            "planted": sorted(s.task for s in counted if s.planted and s.reference_level),
            "clean": sorted(s.task for s in counted if not s.planted and s.reference_level),
        },
        "exploratory_timing_with_reference_flags": {
            "n": len(timing),
            "detected": sum(1 for s in timing if s.detected or s.reference_level),
        },
        "misses": [s.task for s in counted if s.planted and not s.detected],
        "false_positives": [
            s.task for s in counted if s.flagged and not s.detected and not s.adjudicated_real
        ],
        "adjudicated_real": [s.task for s in counted if s.adjudicated_real],
        "extra_misses": [s.task for s in extra if not s.detected],
    }


def _est(e: Estimate | None) -> dict[str, Any] | None:
    return None if e is None else {"point": e.point, "ci": [e.lo, e.hi], "n": e.n}


def _ci(ci: tuple[float, float] | None) -> list[float] | None:
    return None if ci is None else [ci[0], ci[1]]
