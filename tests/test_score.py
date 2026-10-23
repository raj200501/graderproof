"""Tests for graderproof.score."""

from __future__ import annotations

from graderproof.core import Determinism, Validation, Variant, VariantKind
from graderproof.score import (
    TaskResult,
    VariantResult,
    aggregate,
    agreement,
    by_key,
    operator_counts,
    variant_record,
)

V, P = VariantKind.VIOLATING, VariantKind.PRESERVING


def make(
    kind: VariantKind,
    verdicts: tuple[VariantKind | None, VariantKind | None],
    witness: bool = True,
    op: str = "op",
    n: int = 0,
) -> Variant:
    v = Variant("t", kind, op, "", {"f": f"{kind}{verdicts}{n}"}, {"w": 1} if witness else None)
    return v.with_validation(Validation("a", verdicts[0])).with_validation(
        Validation("b", verdicts[1])
    )


def test_variant_result_properties() -> None:
    survive = VariantResult(make(V, (V, V)), True, 3)
    killed = VariantResult(make(V, (V, V), n=1), False, 1)
    unstable = VariantResult(make(V, (V, V), n=2), None, 3)
    equivalent = VariantResult(make(V, (P, P)), True, 1)
    rejected = VariantResult(make(P, (P, P)), False, 3)
    assert survive.counted and survive.survives and not survive.wrongly_rejected
    assert killed.counted and not killed.survives
    assert not unstable.counted
    assert equivalent.equivalent and not equivalent.counted
    assert rejected.wrongly_rejected


def test_task_result_indicators_and_summary() -> None:
    vrs = [
        VariantResult(make(V, (V, V)), True, 3),
        VariantResult(make(V, (V, V), n=1), False, 1),
        VariantResult(make(V, (P, P)), True, 1),
        VariantResult(make(P, (P, P)), False, 3),
        VariantResult(make(P, (P, V)), False, 1),
    ]
    t = TaskResult("b:t", "h", Determinism.STABLE_PASS, 3, 1, vrs, "s1")
    assert t.false_accept and t.false_reject
    assert t.mutation_score == 0.5
    assert t.n_equivalent == 1
    s = t.summary()
    assert s["n_killed"] == 1 and s["n_counted_preserving"] == 1 and s["stratum"] == "s1"
    flaky = TaskResult("b:f", "h2", Determinism.FLAKY, 0, 0, vrs)
    assert flaky.flaky and not flaky.false_accept and flaky.mutation_score is None
    none = TaskResult("b:n", "h3", Determinism.STABLE_PASS, 0, 0, [])
    assert none.mutation_score is None and not none.false_reject


def test_aggregate_and_helpers() -> None:
    a = TaskResult(
        "b:a", "ha", Determinism.STABLE_PASS, 1, 0, [VariantResult(make(V, (V, V)), True, 3)]
    )
    b = TaskResult(
        "b:b",
        "hb",
        Determinism.STABLE_PASS,
        1,
        0,
        [VariantResult(make(V, (V, V), op="x"), False, 1)],
    )
    c = TaskResult(
        "b:c", "hc", Determinism.STABLE_FAIL, 1, 0, [VariantResult(make(V, (V, P)), True, 1)]
    )
    agg = aggregate([a, b, c], seed=1, replicates=200)
    d = agg.to_dict()
    assert d["n_tasks"] == 3 and d["n_scorable"] == 2 and d["n_reference_rejected"] == 1
    assert d["false_accept_task_rate"]["point"] == 0.5
    assert d["false_reject_task_rate"]["point"] == 0.0
    assert d["n_headline_variants"] == 2 and d["n_excluded_variants"] == 1
    rate, agree, judged = agreement([a, b, c])
    assert (agree, judged) == (2, 3) and rate is not None
    counts = operator_counts([a, b, c])
    assert counts["op"]["survived"] == 1 and counts["x"]["counted"] == 1
    assert by_key([a])["b:a"] is a
    rec = variant_record("ha", a.variants[0], "f" * 64)
    assert (
        rec["counted_in_headline"]
        and rec["grader_passed"] is True
        and rec["witness_sha256"] == "f" * 64
    )
    empty = aggregate([], 1, 10)
    assert empty.false_accept is None and empty.to_dict()["false_accept_task_rate"] is None
    assert agreement([]) == (None, 0, 0)
