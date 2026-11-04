"""Tests for tools/citecheck.py (`make citecheck`, offline) on temporary layouts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import citecheck
import pytest
from test_claims_tooling import citation, put, put_json

CITE = citecheck.CITECHECK
OWN = "https://github.com/raj200501/graderproof"


def test_is_own_and_cited_urls() -> None:
    own = [OWN, f"{OWN}/blob/main/x", f"{OWN}.git", f"{OWN}#readme", f"http://{OWN[8:]}?tab=x"]
    own.append("https://www.github.com/raj200501/graderproof/issues")
    assert all(citecheck.is_own(u) for u in own)
    for other in (f"{OWN}-extra", "https://github.com/raj200501/arc-ttt-public"):
        assert not citecheck.is_own(other)
    text = f"See https://a.org/x. and https://a.org/x, and (https://b.org/y) {OWN}/x <{OWN}>\n"
    assert citecheck.cited_urls(text) == ["https://a.org/x", "https://b.org/y"]


def test_first_location() -> None:
    text = "intro\nsee https://x.org/a\n"
    assert citecheck.first_location("R.md", text, "https://x.org/a") == "R.md:2"
    assert citecheck.first_location("R.md", text, "https://y.org") == "R.md"


def test_optional_text_optional_year_and_utc_ok() -> None:
    assert citecheck.optional_text(None) and citecheck.optional_text("x")
    assert not citecheck.optional_text(3)
    assert citecheck.optional_year(None) and citecheck.optional_year(2026)
    assert not citecheck.optional_year(True) and not citecheck.optional_year("2026")
    assert citecheck.utc_ok("2026-10-23T01:58:11Z")
    for bad in ("2026-10-23 01:58:11Z", "2026-13-01T00:00:00Z", "2026-10-23T01:58:11+00:00", 5):
        assert not citecheck.utc_ok(bad), bad


def test_entry_problems() -> None:
    url = "https://arxiv.org/abs/2606.08960"
    base = citation(url)
    assert citecheck.entry_problems(base, "W") == []
    unreachable = {**citation(url, "unreachable"), "final_url": None, "content_sha256": None}
    unreachable["notes"] = "the site answered 403"
    assert citecheck.entry_problems(unreachable, "W") == []
    claimed = base["claimed"]
    observed = base["observed"]
    cases: list[tuple[Any, str]] = [
        ("x", "W is not an object"),
        (
            {k: v for k, v in base.items() if k not in ("status", "notes")},
            "W: missing status, notes",
        ),
        ({**base, "status": "ok"}, "status must be one of verified, mismatch, unreachable"),
        ({**base, "retrieved_utc": "yesterday"}, "retrieved_utc must be YYYY-MM-DDTHH:MM:SSZ"),
        ({**base, "notes": 3}, "notes must be a string"),
        ({**base, "content_sha256": None}, "content_sha256 is null, so notes must say why"),
        ({**base, "content_sha256": None, "notes": 3}, "content_sha256 is null, so notes"),
        ({**base, "content_sha256": "ABC"}, "must be 64 lowercase hex digits or null"),
        ({**base, "claimed": "x"}, "claimed must be an object with a url"),
        ({**base, "claimed": {**claimed, "url": 3}}, "claimed must be an object with a url"),
        ({**base, "claimed": {**claimed, "url": "ftp://x"}}, "claimed.url must be an http(s) URL"),
        ({**base, "claimed": {"url": url}}, "claimed.title missing"),
        ({**base, "observed": "x"}, "observed must be an object"),
        ({**base, "observed": {**observed, "year": "2026"}}, "observed.year must be an integer"),
        ({**base, "observed": {**observed, "title": 3}}, "observed.title must be a string or null"),
        ({**base, "final_url": "nope"}, "final_url must be an http(s) URL or null"),
        ({**base, "page_title": 3}, "page_title must be a string or null"),
        ({**base, "page_title": None}, "a verified entry needs a page_title"),
        ({**base, "page_title": "  "}, "a verified entry needs a page_title"),
        ({**base, "final_url": None}, "a verified entry needs a final_url"),
    ]
    for value, message in cases:
        problems = citecheck.entry_problems(value, "W")
        assert any(message in p for p in problems), (value, problems)


def test_schema_problems() -> None:
    schema = citecheck.SCHEMA
    assert citecheck.schema_problems("x") == [f"{CITE} must be a JSON object"]
    assert citecheck.schema_problems({"schema": schema, "entries": []}) == []
    assert citecheck.schema_problems({"schema": "other", "entries": []}) == [
        f"{CITE}: schema must be {schema!r}"
    ]
    for not_a_list in ({}, None):
        assert citecheck.schema_problems({"schema": schema, "entries": not_a_list}) == [
            f"{CITE}: entries must be a list"
        ]
    url = "https://a.org"
    entries: list[Any] = [
        citation(url, key="a"),
        citation(url, key="a"),
        "x",
        citation(url, key=""),
    ]
    assert citecheck.schema_problems({"schema": schema, "entries": entries}) == [
        f"{CITE} entry a: duplicate key",
        f"{CITE} entry 2 is not an object",
        f"{CITE} entry 3: key must be a non-empty string",
    ]


def test_claimed_url_verified_urls_and_status_of() -> None:
    assert citecheck.claimed_url({"claimed": {"url": "u"}}) == "u"
    assert citecheck.claimed_url({}) is None and citecheck.claimed_url({"claimed": "x"}) is None
    final = {**citation("https://d.org", key="d"), "final_url": "https://d.org/final"}
    entries: list[Any] = [
        citation("https://a.org/x/"),
        {**citation("https://b.org", key="b"), "status": "mismatch"},
        {**citation("https://c.org", key="c"), "page_title": None},
        {**citation("https://e.org", key="e"), "retrieved_utc": ""},
        "junk",
        final,
    ]
    assert citecheck.verified_urls(entries) == {
        "https://a.org/x",
        "https://d.org",
        "https://d.org/final",
    }
    assert citecheck.status_of(entries, "https://b.org/") == "entry b is mismatch"
    assert citecheck.status_of(entries, "https://none.org") == f"no entry in {CITE}"


def test_run_and_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path
    out, rc = citecheck.run(root)
    assert (out, rc) == (
        [
            "citecheck: README.md missing",
            "citecheck: docs/REPORT.md missing",
            f"citecheck: {CITE} missing",
            "citecheck: FAIL",
        ],
        1,
    )
    put(root, "README.md", f"# t\nSee https://a.org/x/ and {OWN}.\n")
    put(root, "docs/REPORT.md", "# r\n\nAlso https://b.org/y and https://a.org/x/.\n")
    put(root, CITE, "{bad")
    out, rc = citecheck.run(root)
    assert rc == 1 and out[:2] == [
        f"citecheck: unverified reference https://a.org/x/ (README.md:2; no entry in {CITE})",
        f"citecheck: unverified reference https://b.org/y (docs/REPORT.md:3; no entry in {CITE})",
    ]
    assert out[2].startswith(f"citecheck: {CITE} is not valid JSON")
    good = [citation("https://a.org/x", key="a"), citation("https://b.org/y", key="b")]
    put_json(root, CITE, {"schema": "old", "entries": good})
    out, rc = citecheck.run(root)
    assert (out, rc) == (
        [f"citecheck: {CITE}: schema must be 'graderproof.citecheck/1'", "citecheck: FAIL"],
        1,
    )
    put_json(root, CITE, {"schema": citecheck.SCHEMA, "entries": good})
    assert citecheck.run(root) == (
        ["citecheck: 2 references verified in README.md and docs/REPORT.md"],
        0,
    )
    put(root, "docs/cards/c.md", "Card cites https://c.org/z.\n")
    out, rc = citecheck.run(root)
    assert rc == 1 and out[0] == (
        f"citecheck: unverified reference https://c.org/z (docs/cards/c.md:1; no entry in {CITE})"
    )
    put_json(
        root, CITE, {"schema": citecheck.SCHEMA, "entries": [*good, citation("https://c.org/z")]}
    )
    assert citecheck.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "citecheck: 1 references verified in 1 grader cards under docs/cards/",
        "citecheck: 2 references verified in README.md and docs/REPORT.md",
    ]
