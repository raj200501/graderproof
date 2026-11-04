"""Tests for graderproof.stats, including exact agreement with tools/ship_check.py."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
import ship_check

from graderproof import stats


def test_bootstrap_matches_ship_check_exactly() -> None:
    values = [True, False, True, True, False, False, True, False, True, True] * 4
    ours = stats.bootstrap_ci(len(values), stats.mean_of(values), 11, 400)
    theirs = ship_check.bootstrap_ci(len(values), ship_check.mean_of(values), 11, 400)
    assert ours == theirs
    assert ours is not None


def test_bootstrap_edge_cases() -> None:
    assert stats.bootstrap_ci(0, stats.mean_of([]), 1, 10) is None
    assert stats.bootstrap_ci(3, lambda idx: None, 1, 10) is None
    assert stats.ratio(1, 0) is None


def test_proportion_estimate() -> None:
    est = stats.proportion([True] * 3 + [False] * 7, seed=1, replicates=300)
    assert est is not None
    assert est.point == pytest.approx(0.3)
    assert est.lo <= est.point <= est.hi
    assert est.to_dict()["ci"] == [est.lo, est.hi]
    assert est.n == 10
    assert stats.proportion([], 1, 10) is None


def test_recall_precision_definitions() -> None:
    planted = [True] * 10 + [False] * 10
    detected = [True] * 9 + [False] * 11
    flagged = [True] * 10 + [True, True] + [False] * 8  # task 9: wrong-direction flag
    real = [False] * 10 + [True] + [False] * 9  # one clean-task flag adjudicated real
    rec, prec = stats.recall_precision(planted, detected, flagged, real, seed=5, replicates=300)
    assert rec is not None and prec is not None
    assert rec.point == pytest.approx(0.9)
    assert prec.point == pytest.approx(9 / 11)  # FPs: wrong-direction flag and one clean flag

    def r(idx: Sequence[int]) -> float | None:
        tp = sum(1 for i in idx if planted[i] and detected[i])
        return ship_check.ratio(tp, sum(1 for i in idx if planted[i]))

    assert (rec.lo, rec.hi) == ship_check.bootstrap_ci(20, r, 5, 300)
    with pytest.raises(ValueError):
        stats.recall_precision([True], [True, False], [True], [False], 1, 10)
    assert stats.recall_precision([False], [False], [False], [False], 1, 10) == (None, None)
    rec_only, prec_none = stats.recall_precision([True], [False], [False], [False], 1, 10)
    assert rec_only is not None and rec_only.point == 0.0 and prec_none is None


def test_clopper_pearson() -> None:
    lo, hi = stats.clopper_pearson(30, 30) or (0.0, 0.0)
    assert hi == 1.0 and lo == pytest.approx(0.025 ** (1 / 30), abs=1e-9)
    lo0, hi0 = stats.clopper_pearson(0, 30) or (1.0, 1.0)
    assert lo0 == 0.0 and hi0 == pytest.approx(1 - 0.025 ** (1 / 30), abs=1e-9)
    lo27, hi27 = stats.clopper_pearson(27, 30) or (0.0, 0.0)
    assert lo27 == pytest.approx(0.7347, abs=1e-3) and hi27 == pytest.approx(0.9789, abs=1e-3)
    assert stats.clopper_pearson(0, 0) is None and stats.clopper_pearson(5, 3) is None


def test_holm() -> None:
    assert stats.holm([0.01, 0.04, 0.03], alpha=0.05) == [True, False, False]
    assert stats.holm([0.001, 0.01, 0.02], alpha=0.05) == [True, True, True]
    adj = stats.holm_adjusted([0.01, 0.04, 0.03])
    assert adj == pytest.approx([0.03, 0.06, 0.06])
    assert stats.holm_adjusted([0.5, 0.9]) == pytest.approx([1.0, 1.0])


def test_binomial_tails() -> None:
    assert stats.binomial_tail_ge(0, 5, 0.3) == 1.0
    assert stats.binomial_tail_ge(6, 5, 0.3) == 0.0
    assert stats.binomial_tail_ge(5, 5, 0.5) == pytest.approx(1 / 32)
    assert stats.binomial_tail_le(-1, 5, 0.5) == 0.0
    assert stats.binomial_tail_le(5, 5, 0.5) == 1.0
    assert stats.binomial_tail_le(0, 5, 0.5) == pytest.approx(1 / 32)
