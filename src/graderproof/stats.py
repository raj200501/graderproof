"""Task-level statistics: percentile bootstrap over tasks and Holm correction.

The bootstrap procedure is fixed (DECISIONS.md D8) so that tools/ship_check.py can
recompute every banked interval exactly with the standard library:

* ``rng = random.Random(seed)``;
* each of ``replicates`` replicates draws ``n`` task indices with ``rng.randrange(n)``;
* replicates whose statistic is undefined (``None``) are dropped;
* with ``m`` kept replicates sorted ascending, the interval is the order statistics at
  ``floor(alpha / 2 * m)`` and ``ceil((1 - alpha / 2) * m) - 1``.

When one artifact carries two intervals, the second uses ``seed + 1``.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

Statistic = Callable[[Sequence[int]], float | None]


@dataclass(frozen=True)
class Estimate:
    """A point estimate with a percentile bootstrap interval."""

    point: float
    lo: float
    hi: float
    n: int

    def to_dict(self) -> dict[str, object]:
        """Plain-JSON representation used in artifacts: ``{point, ci: [lo, hi], n}``."""
        return {"point": self.point, "ci": [self.lo, self.hi], "n": self.n}


def bootstrap_ci(
    n: int, stat: Statistic, seed: int, replicates: int, alpha: float = 0.05
) -> tuple[float, float] | None:
    """Percentile bootstrap interval of ``stat`` over resampled task indices.

    Returns None when ``n`` or ``replicates`` is not positive or every replicate is
    undefined.
    """
    if n <= 0 or replicates <= 0:
        return None
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(replicates):
        idx = [rng.randrange(n) for _ in range(n)]
        v = stat(idx)
        if v is not None:
            values.append(v)
    if not values:
        return None
    values.sort()
    m = len(values)
    lo = values[math.floor(alpha / 2 * m)]
    hi = values[max(0, math.ceil((1 - alpha / 2) * m) - 1)]
    return lo, hi


def ratio(num: int, den: int) -> float | None:
    """``num / den``, or None when ``den`` is zero."""
    return num / den if den else None


def mean_of(values: Sequence[bool]) -> Statistic:
    """Statistic: share of resampled tasks whose indicator is True."""

    def stat(idx: Sequence[int]) -> float | None:
        return ratio(sum(values[i] for i in idx), len(idx))

    return stat


def proportion(
    values: Sequence[bool], seed: int, replicates: int, alpha: float = 0.05
) -> Estimate | None:
    """Share of True indicators with a task bootstrap interval, or None if empty."""
    point = ratio(sum(values), len(values))
    ci = bootstrap_ci(len(values), mean_of(values), seed, replicates, alpha)
    if point is None or ci is None:
        return None
    return Estimate(point, ci[0], ci[1], len(values))


def recall_precision(
    planted: Sequence[bool],
    flagged: Sequence[bool],
    real: Sequence[bool],
    seed: int,
    replicates: int,
    alpha: float = 0.05,
) -> tuple[Estimate, Estimate] | None:
    """Planted-weakness recall and precision with intervals.

    Recall uses ``seed`` and precision ``seed + 1``.

    A flag on a clean task counts as a false positive unless ``real`` marks it as an
    adjudicated real weakness, which is reported separately and excluded here.
    """
    n = len(planted)
    if not (len(flagged) == len(real) == n):
        raise ValueError("planted, flagged, and real must have equal length")

    def rec(idx: Sequence[int]) -> float | None:
        tp = sum(1 for i in idx if planted[i] and flagged[i])
        return ratio(tp, sum(1 for i in idx if planted[i]))

    def prec(idx: Sequence[int]) -> float | None:
        tp = sum(1 for i in idx if planted[i] and flagged[i])
        fp = sum(1 for i in idx if flagged[i] and not planted[i] and not real[i])
        return ratio(tp, tp + fp)

    everything = list(range(n))
    r_pt, p_pt = rec(everything), prec(everything)
    r_ci = bootstrap_ci(n, rec, seed, replicates, alpha)
    p_ci = bootstrap_ci(n, prec, seed + 1, replicates, alpha)
    if r_pt is None or p_pt is None or r_ci is None or p_ci is None:
        return None
    return Estimate(r_pt, r_ci[0], r_ci[1], n), Estimate(p_pt, p_ci[0], p_ci[1], n)


def holm(pvalues: Sequence[float], alpha: float = 0.05) -> list[bool]:
    """Holm step-down: which hypotheses are rejected at family-wise level ``alpha``."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    rejected = [False] * len(pvalues)
    m = len(pvalues)
    for rank, i in enumerate(order):
        if pvalues[i] <= alpha / (m - rank):
            rejected[i] = True
        else:
            break
    return rejected


def holm_adjusted(pvalues: Sequence[float]) -> list[float]:
    """Holm-adjusted p-values (monotone, capped at 1)."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def binomial_tail_ge(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), exact."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return sum(math.comb(n, j) * p**j * (1 - p) ** (n - j) for j in range(k, n + 1))


def binomial_tail_le(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p), exact."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(math.comb(n, j) * p**j * (1 - p) ** (n - j) for j in range(0, k + 1))
