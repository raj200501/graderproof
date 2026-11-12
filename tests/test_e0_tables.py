"""Tests for tools/e0_tables.py, and for how the documents state the E0 (G5) threshold.

Review B2 found a false comparison with that threshold: a sentence said the upper end of the
exact recall interval was below 0.90, the artifact puts it above, and claimcheck passed the
line because the 0.90 row of docs/claims/allowlist.tsv allowed "preregistered 0.90". The
row now allows 0.90 only inside a threshold phrase, but it cannot tell whether a comparison
is true ("below the 0.90 threshold" passes whatever the result), and claims render only
numbers, so met and not met stay typed. Instead, every sentence of the rendered documents
that writes the threshold is listed here: in G5_COMPARISONS with what it asserts, or in
G5_STATEMENTS if it compares nothing. The tests check each assertion against the claim's
artifact, require the sentence to show each compared result as a claim, and fail on a 0.90
in any sentence that no list holds. A comparison that does not write 0.90 is not found, so
write the threshold in it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import claimcheck
import e0_tables
import pytest
import report
import ship_check as sc

REPO = Path(__file__).resolve().parent.parent


def _planted(task: str, weakness: str, detected: bool) -> dict[str, object]:
    return {
        "slice": "in_list",
        "task": task,
        "direction": "accept",
        "planted": True,
        "weakness_type": weakness,
        "detected": detected,
        "flagged": detected,
    }


def _variant(task_hash: str, op: str, passed: bool, counted: bool, status: str) -> str:
    return json.dumps(
        {
            "task_hash": task_hash,
            "kind": "violating",
            "operator": op,
            "grader_passed": passed,
            "counted_in_headline": counted,
            "validation_status": status,
        }
    )


def test_tables(tmp_path: Path) -> None:
    rows = [
        _planted("t1", "timing", True),
        _planted("t2", "timing", False),
        _planted("t3", "loose", True),
        {
            "slice": "clean",
            "task": "c1",
            "planted": False,
            "weakness_type": None,
            "detected": False,
            "flagged": True,
            "adjudicated_real": True,
        },
        {
            "slice": "extra",
            "task": "x1",
            "planted": True,
            "weakness_type": "x",
            "detected": True,
            "flagged": True,
        },
    ]
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"tasks": rows}))
    tasks_dir = tmp_path / "tasks"
    for name, kind in (("t1", "script"), ("t2", "script"), ("t3", "module")):
        (tasks_dir / name).mkdir(parents=True)
        (tasks_dir / name / "task.toml").write_text(f'id = "{name}"\nkind = "{kind}"\n')
    tasks_jsonl = tmp_path / "tasks.jsonl"
    tasks_jsonl.write_text(
        "\n".join(json.dumps({"task": f"tasks:t{i}", "task_hash": f"h{i}"}) for i in (1, 2, 3))
        + "\n"
    )
    variants = tmp_path / "variants.jsonl"
    variants.write_text(
        "\n".join(
            [
                _variant("h1", "a", True, True, "validated"),
                _variant("h1", "b", False, True, "validated"),
                _variant("h3", "a", True, True, "validated"),
                _variant("h3", "c", True, False, "disagreed"),
                _variant("h2", "d", True, False, "rejected"),
            ]
        )
        + "\n\n"
    )
    store = tmp_path / "store"
    (store / "requests").mkdir(parents=True)
    (store / "requests" / "aa.json").write_text("{}")
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps({"request": "aa", "purpose": "review"})
        + "\n"
        + json.dumps({"request": "zz"})
        + "\n\n"
    )
    adjudication = tmp_path / "adjudication.json"
    adjudication.write_text(json.dumps({"tasks": {"a": {"real": False}, "b": {"real": True}}}))
    e4 = tmp_path / "e4.json"
    e4.write_text(
        json.dumps(
            {
                "repaired": [
                    {"patch": "outbound/patches/toybench/a.patch"},
                    {"patch": "outbound/patches/toybench/b.patch"},
                    {"patch": "outbound/patches/toybench/c.patch"},
                ]
            }
        )
    )
    out = tmp_path / "tables.json"
    args = [
        "--results",
        str(results),
        "--store",
        str(store),
        "--ledger",
        str(ledger),
        "--variants",
        str(variants),
        "--adjudication",
        str(adjudication),
        "--e4",
        str(e4),
        "--tasks-dir",
        str(tasks_dir),
        "--tasks-jsonl",
        str(tasks_jsonl),
        "--out",
        str(out),
    ]
    assert e0_tables.main(args) == 0
    doc = json.loads(out.read_text())
    assert doc["counted"] == {
        "n": 4,
        "planted": 3,
        "detected": 2,
        "flagged_clean": 1,
        "clean_real": 1,
    }
    assert doc["by_type"]["timing"] == {"planted": 2, "detected": 1, "rate": 0.5}
    assert doc["extra"] == {"planted": 1, "detected": 1, "rate": 1.0}
    assert doc["model_calls"] == {"total": 1, "by_purpose": {"review": 1}}
    assert doc["validation"] == {"disagreed": 1, "rejected": 1, "validated": 3}
    assert doc["e4_toybench"] == {
        "repaired": 3,
        "repaired_adjudicated_not_real": 1,
        "tasks_adjudicated_not_real": ["a"],
    }
    assert doc["by_kind"] == {
        "module": {"planted": 1, "detected": 1, "rate": 1.0},
        "script": {"planted": 2, "detected": 1, "rate": 0.5},
    }
    assert doc["detecting_operators"] == {"a": 2}


G5_THRESHOLD = "0.90"  # the G5 threshold as the documents write it (docs/claims/allowlist.tsv)

# Every sentence of a rendered document that compares an E0 result with the G5 threshold, as
# (document, text, assertions). The text is as rendered, with each claim written {KEY} in place
# of its value. An assertion "KEY op T" (op one of <, <=, >=, >) is what the text says of that
# claim's unrounded value and the threshold T, tools/ship_check.py E0_MIN: met is >= T, as G5
# scores it; above is > T; below, missed, and short of are < T; an interval contains T when its
# low end is <= T and its high end >= T. Add a sentence here when you write one; the tests fail
# on a 0.90 in any sentence that neither this list nor G5_STATEMENTS holds.
G5_COMPARISONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "README.md",
        "recall {e0.recall} (95% CI {e0.recall_lo} to {e0.recall_hi}), short of its "
        "preregistered 0.90 target, at precision {e0.precision} (95% CI {e0.precision_lo} to "
        "{e0.precision_hi}), which met it",
        ("e0.recall < T", "e0.precision >= T"),
    ),
    (
        "README.md",
        "recall {e0.recall} (95% CI {e0.recall_lo} to {e0.recall_hi}): **H1 not met**; "
        "precision {e0.precision} (95% CI {e0.precision_lo} to {e0.precision_hi}): H2 met "
        "(target 0.90 for both)",
        ("e0.recall < T", "e0.precision >= T"),
    ),
    ("README.md", "Recall, {e0.recall}, missed the preregistered 0.90 target", ("e0.recall < T",)),
    (
        "README.md",
        "G5 tool validity, because E0 recall, {e0.recall}, is below its preregistered 0.90 "
        "threshold",
        ("e0.recall < T",),
    ),
    ("README.md", "recall, {e0.recall}, missed its 0.90 target", ("e0.recall < T",)),
    (
        "docs/REPORT.md",
        "recall {e0.recall} (95% CI {e0.recall_lo} to {e0.recall_hi}), below the preregistered "
        "target of 0.90, at an adjudicated precision of {e0.precision} (95% CI {e0.precision_lo} "
        "to {e0.precision_hi}), above it",
        ("e0.recall < T", "e0.precision > T"),
    ),
    (
        "docs/REPORT.md",
        "Recall, {e0.recall} (95% CI {e0.recall_lo} to {e0.recall_hi}), missed its preregistered "
        "threshold of at least 0.90, so H1 is not supported",
        ("e0.recall < T",),
    ),
    (
        "docs/REPORT.md",
        "Precision, {e0.precision}, met the 0.90 threshold, so H2 is supported, but the lower "
        "bound of its 95% CI ({e0.precision_lo} to {e0.precision_hi}) is below the threshold",
        ("e0.precision >= T", "e0.precision_lo < T"),
    ),
    (
        "docs/REPORT.md",
        "| Recall (H1, target at least 0.90) | {e0.recall} | {e0.recall_lo} to {e0.recall_hi} | "
        "{e0.recall_exact_lo} to {e0.recall_exact_hi} | not met |",
        ("e0.recall < T",),
    ),
    (
        "docs/REPORT.md",
        "| Precision, adjudicated (H2, target at least 0.90) | {e0.precision} | "
        "{e0.precision_lo} to {e0.precision_hi} | {e0.precision_exact_lo} to "
        "{e0.precision_exact_hi} | met |",
        ("e0.precision >= T",),
    ),
    (
        "docs/REPORT.md",
        "**H1 is not met**: the point estimate of recall, the preregistered criterion, is "
        "{e0.recall}, below the 0.90 threshold, although both intervals contain it, "
        "{e0.recall_lo} to {e0.recall_hi} (bootstrap) and {e0.recall_exact_lo} to "
        "{e0.recall_exact_hi} (exact), so the data do not rule out a recall at that level",
        (
            "e0.recall < T",
            "e0.recall_lo <= T",
            "e0.recall_hi >= T",
            "e0.recall_exact_lo <= T",
            "e0.recall_exact_hi >= T",
        ),
    ),
    (
        "docs/REPORT.md",
        "**H2 is met**: after adjudication, precision is {e0.precision}, above the 0.90 "
        "threshold, although the lower end of its 95% CI, {e0.precision_lo}, is below it",
        ("e0.precision > T", "e0.precision_lo < T"),
    ),
    (
        "docs/REPORT.md",
        "both lower bounds fall below the 0.90 threshold ({e0.recall_lo} for recall, "
        "{e0.precision_lo} for precision), so even precision ({e0.precision}), which met it as "
        "a point estimate, is not shown to reach it",
        ("e0.recall_lo < T", "e0.precision_lo < T", "e0.precision >= T"),
    ),
    (
        "docs/cards/toybench.md",
        "| Recall on planted weaknesses (H1 target at least 0.90, not met) | {e0.recall} |",
        ("e0.recall < T",),
    ),
    (
        "docs/cards/toybench.md",
        "| Precision, adjudicated (H2 target at least 0.90, met) | {e0.precision} |",
        ("e0.precision >= T",),
    ),
)
# Sentences that state the threshold without comparing any result with it.
G5_STATEMENTS: tuple[tuple[str, str], ...] = (
    (
        "docs/REPORT.md",
        "with recall (H1) and precision (H2) each held to a point-estimate threshold of at "
        "least 0.90 (gate G5)",
    ),
)
COMPARISON_WORDS = re.compile(
    r"\b(?:met|miss\w*|below|above|short|reach\w*|exceed\w*|under|over|fell|falls?|"
    r"support\w*|contain\w*|includ\w*)\b",
    re.IGNORECASE,
)
CLAIMED = re.compile(rf"(?:{claimcheck.NUMBER_PATTERN})<!--claim:([^>]*)-->")
ASSERTION = re.compile(r"(?P<key>\S+) (?P<op><=|<|>=|>) T")


def _unbacked(line: str) -> list[str]:
    """What claimcheck reports for one line under the repository's own allowlist."""
    entries, problems = claimcheck.load_allowlist(REPO / claimcheck.ALLOWLIST)
    assert problems == []
    return claimcheck.check_text(f"{line}\n", "doc.md", {}, entries).problems


def _shown(doc: str) -> list[str]:
    """The lines of a rendered document, with each claim written {KEY} in place of its value."""
    text = (REPO / doc).read_text(encoding="utf-8")
    return [CLAIMED.sub(r"{\1}", line) for line in text.splitlines()]


def _assertion(assertion: str) -> tuple[str, str]:
    """The claim key and the operator of an assertion such as ``e0.recall < T``."""
    m = ASSERTION.fullmatch(assertion)
    assert m is not None, f"malformed assertion {assertion!r}"
    return m["key"], m["op"]


def _holds(assertion: str, values: Mapping[str, float]) -> bool:
    """Whether an assertion holds for its claim's unrounded value and the G5 threshold."""
    key, op = _assertion(assertion)
    value, t = values[key], sc.E0_MIN
    return {"<": value < t, "<=": value <= t, ">=": value >= t, ">": value > t}[op]


def _comparison_problems(
    lines: Sequence[str], text: str, assertions: Sequence[str], values: Mapping[str, float]
) -> list[str]:
    """Why a listed comparison fails: not on ``lines``, a compared claim not shown, or false."""
    problems = [] if any(text in line for line in lines) else [f"not in the document: {text!r}"]
    for assertion in assertions:
        key, _ = _assertion(assertion)
        if f"{{{key}}}" not in text:
            problems.append(f"{assertion}: the sentence does not show {key} as a claim")
        if not _holds(assertion, values):
            problems.append(f"{assertion} is false: {key} is {values[key]!r} in its artifact")
    return problems


def _unlisted(doc: str, lines: Sequence[str]) -> list[str]:
    """Each G5 threshold token on ``lines`` that no sentence listed for ``doc`` contains."""
    texts = [text for d, text, _ in G5_COMPARISONS if d == doc]
    texts += [text for d, text in G5_STATEMENTS if d == doc]
    found: list[str] = []
    for n, line in enumerate(lines, start=1):
        spans = [m.span() for t in texts for m in re.finditer(re.escape(t), line)]
        for token in claimcheck.TOKEN_RE.finditer(line):
            inside = any(a <= token.start() and token.end() <= b for a, b in spans)
            if token.group(0) == G5_THRESHOLD and not inside:
                found.append(
                    f"{doc}:{n}: {G5_THRESHOLD} is in no sentence of G5_COMPARISONS "
                    "or G5_STATEMENTS"
                )
    return found


@pytest.fixture(scope="module")
def g5_values() -> dict[str, float]:
    """The unrounded value of each claim a G5 comparison asserts about, from its artifact now."""
    spec, problems = report.load_spec(REPO)
    assert problems == []
    keys = {_assertion(a)[0] for _, _, assertions in G5_COMPARISONS for a in assertions}
    wanted = report.Spec(claims={key: spec.claims[key] for key in keys})
    claims, problems = report.resolve_claims(REPO, wanted)
    assert problems == []
    return {key: float(claim.raw) for key, claim in claims.items()}


@pytest.mark.parametrize(
    "line",
    [
        "The 0.90 threshold applies to recall and precision.",
        "Both hypotheses have 0.90 targets.",
        "H2 met (target 0.90 for both)",
        "Each hypothesis has a threshold of at least 0.90.",
        "| Recall (H1, target at least 0.90) | not met |",
        "recall and precision with point-estimate thresholds of at least 0.90",
        "below the preregistered target of 0.90",
    ],
)
def test_g5_threshold_passes_inside_a_threshold_phrase(line: str) -> None:
    """The 0.90 row passes a threshold phrase whatever stands around it, comparisons included."""
    assert _unbacked(line) == []


@pytest.mark.parametrize(
    "line",
    [
        # review B2's sentence, which passed through the old context "preregistered 0.90"
        "**H1 is not met**: the point estimate of recall is below the preregistered 0.90, "
        "and so is the upper end of the exact interval.",
        "The upper end of the exact interval is below 0.90.",
        "Precision is above 0.90.",
        "Both intervals reach 0.90.",
        "Precision is at least 0.90.",
        "an upper end of 0.90",
        "The repaired graders met their targets 0.90 of the time.",
        "Both measures have thresholds 0.90",
    ],
)
def test_g5_threshold_outside_a_threshold_phrase_is_unbacked(line: str) -> None:
    """A 0.90 outside a threshold phrase is unbacked (review N4).

    That is a 0.90 bare after a comparison word or after of, or right after a plural. This
    blocks only the bare form: B2's sentence passes claimcheck once it says "below the 0.90
    threshold", and the G5 lists catch it then (see the last test in this file).
    """
    assert _unbacked(line) == ["doc.md:1: unbacked number 0.90"]


def test_g5_threshold_is_the_gate_minimum() -> None:
    """The allowlisted 0.90 is G5's E0_MIN, the threshold the comparisons are checked against."""
    entries, problems = claimcheck.load_allowlist(REPO / claimcheck.ALLOWLIST)
    assert problems == []
    assert [float(e.number) for e in entries if e.number == G5_THRESHOLD] == [sc.E0_MIN]


@pytest.mark.parametrize(
    ("doc", "text", "assertions"),
    G5_COMPARISONS,
    ids=[f"{doc}-{i}" for i, (doc, _, _) in enumerate(G5_COMPARISONS)],
)
def test_g5_comparison_shows_its_claims_and_holds(
    doc: str, text: str, assertions: tuple[str, ...], g5_values: dict[str, float]
) -> None:
    assert _comparison_problems(_shown(doc), text, assertions, g5_values) == []


@pytest.mark.parametrize(("doc", "text"), G5_STATEMENTS)
def test_g5_statement_is_in_its_document_and_compares_nothing(doc: str, text: str) -> None:
    assert any(text in line for line in _shown(doc))
    assert COMPARISON_WORDS.search(text) is None


def test_every_g5_threshold_in_the_documents_is_listed() -> None:
    found = [p for doc in claimcheck.documents(REPO) for p in _unlisted(doc, _shown(doc))]
    assert found == []


def test_g5_comparison_must_show_its_claim_and_hold(g5_values: dict[str, float]) -> None:
    text = "Recall met the 0.90 threshold"
    assert _comparison_problems([text], text, ("e0.recall >= T",), g5_values) == [
        "e0.recall >= T: the sentence does not show e0.recall as a claim",
        f"e0.recall >= T is false: e0.recall is {g5_values['e0.recall']!r} in its artifact",
    ]


def test_g5_lists_catch_a_false_comparison_that_claimcheck_passes(
    g5_values: dict[str, float],
) -> None:
    """Review B2's sentence, reworded to name the threshold, passes claimcheck but not the lists.

    Unlisted, its 0.90 fails test_every_g5_threshold_in_the_documents_is_listed; listed with
    what it says and its claims shown, the assertion about the exact interval is false.
    """
    line = (
        "**H1 is not met**: the point estimate of recall is below the 0.90 threshold, "
        "and so is the upper end of the exact interval."
    )
    assert _unbacked(line) == []
    assert _unlisted("docs/REPORT.md", [line]) == [
        "docs/REPORT.md:1: 0.90 is in no sentence of G5_COMPARISONS or G5_STATEMENTS"
    ]
    shown = (
        "the point estimate of recall, {e0.recall}, is below the 0.90 threshold, "
        "and so is the upper end of the exact interval, {e0.recall_exact_hi}"
    )
    value = g5_values["e0.recall_exact_hi"]
    assertions = ("e0.recall < T", "e0.recall_exact_hi < T")
    assert _comparison_problems([shown], shown, assertions, g5_values) == [
        f"e0.recall_exact_hi < T is false: e0.recall_exact_hi is {value!r} in its artifact"
    ]
