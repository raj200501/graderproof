"""Tests for the claim-integrity tooling: tools/claimcheck.py, plus the end-to-end and
mutation tests that run report, claimcheck, freshness, and citecheck together.

Every test builds its own temporary repository layout. The artifact in it is synthetic
(labeled as such) and exists only to exercise the tools; it is not a result.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import citecheck
import claimcheck
import freshness
import pytest
import report
import ship_check

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = (REPO / "docs" / "templates" / "example.md.in").read_text(encoding="utf-8")
ARTIFACT = "artifacts/example/summary.json"
SYNTHETIC: dict[str, Any] = {
    "synthetic": "test fixture for the claim tooling; not a measured result",
    "e1": {"false_accept_task_rate": {"point": 0.25, "ci": [0.1, 0.45]}},
    "tasks": [
        {"id": "a", "flaky": False},
        {"id": "b", "flaky": True},
        {"id": "c", "flaky": False},
        {"id": "d", "flaky": False},
    ],
}
CLAIMS: dict[str, dict[str, str]] = {
    "example.rate": {
        "artifact": ARTIFACT,
        "path": "e1.false_accept_task_rate.point",
        "format": "{:.2f}",
    },
    "example.rate_lo": {
        "artifact": ARTIFACT,
        "path": "e1.false_accept_task_rate.ci.0",
        "format": "{:.2f}",
    },
    "example.rate_hi": {
        "artifact": ARTIFACT,
        "path": "e1.false_accept_task_rate.ci.-1",
        "format": "{:.2f}",
    },
    "example.tasks": {"artifact": ARTIFACT, "path": "tasks|len", "format": "{:d}"},
    "example.flaky": {"artifact": ARTIFACT, "path": "tasks|count:flaky=true", "format": "{:d}"},
}
FIGURE: dict[str, Any] = {
    "title": "False-accept task rate (synthetic example)",
    "axis_label": "share of tasks",
    "domain": [0, 1],
    "tick_format": "{:.0%}",
    "bars": [
        {"label": "Example", "value": "example.rate", "lo": "example.rate_lo", "hi": "example.rate_hi"}
    ],
}
TEMPLATES: dict[str, str | None] = {
    "README.md.in": "README.md",
    "REPORT.md.in": "docs/REPORT.md",
    "cards/*.md.in": "docs/cards/*.md",
    "example.md.in": None,
}
ALLOW = (
    "# allowlist for the synthetic layout\n"
    "number\tcontext\treason\n"
    "95%\t95% CI\tconfidence level of the intervals (design parameter)\n"
    "40\tat least 40 tasks\tpreregistered minimum sample size (design parameter)\n"
)
TOOLS = ("claimcheck.py", "freshness.py", "report.py", "svgchart.py", "citecheck.py")


def put(root: Path, rel: str, text: str) -> Path:
    """Write a file under ``root``, creating directories."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def put_json(root: Path, rel: str, value: Any) -> Path:
    """Write JSON under ``root``."""
    return put(root, rel, json.dumps(value, indent=2) + "\n")


def citation(url: str, status: str = "verified", key: str = "ref") -> dict[str, Any]:
    """A schema-valid artifacts/citecheck.json entry."""
    return {
        "key": key,
        "claimed": {"title": "T", "authors": "A", "year": 2026, "url": url},
        "observed": {"title": "T", "authors": "A", "year": 2026},
        "final_url": url,
        "page_title": "T" if status != "unreachable" else None,
        "retrieved_utc": "2026-10-23T01:58:11Z",
        "content_sha256": "a" * 64,
        "status": status,
        "notes": "",
    }


def make_layout(
    tmp_path: Path,
    readme: str | None = EXAMPLE,
    report_md: str | None = EXAMPLE,
    entries: list[dict[str, Any]] | None = None,
) -> Path:
    """A synthetic repository: artifact, spec, allowlist, templates, citations."""
    root = tmp_path / "repo"
    put_json(root, ARTIFACT, SYNTHETIC)
    spec = {"claims": CLAIMS, "figures": {"example": FIGURE}, "templates": TEMPLATES}
    put_json(root, claimcheck.SPEC, spec)
    put(root, claimcheck.ALLOWLIST, ALLOW)
    put(root, "docs/templates/example.md.in", EXAMPLE)
    if readme is not None:
        put(root, "docs/templates/README.md.in", readme)
    if report_md is not None:
        put(root, "docs/templates/REPORT.md.in", report_md)
    put_json(root, citecheck.CITECHECK, {"schema": citecheck.SCHEMA, "entries": entries or []})
    return root


def built(tmp_path: Path, **kwargs: Any) -> Path:
    """A synthetic layout on which ``make report`` already ran."""
    root = make_layout(tmp_path, **kwargs)
    out, rc = report.run(root)
    assert rc == 0, out
    return root


def edit(path: Path, old: str, new: str, count: int = 1) -> None:
    """Replace text in a file (the text must be present)."""
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def check(text: str, registry: dict[str, str] | None = None) -> claimcheck.FileReport:
    """claimcheck on one text with no allowlist."""
    return claimcheck.check_text(text, "D.md", registry or {}, [])


def unbacked(text: str) -> list[str]:
    """Unbacked tokens of a one-document check."""
    return [p.rsplit(" ", 1)[-1] for p in check(text).problems if "unbacked number" in p]


# ---------------------------------------------------------------- tokens and masking


def test_number_tokens_and_attachment() -> None:
    text = "a 0.25 b -0.05 +1 1,234 12.3% .5 1e-5 2.5E3 G7 E0 x86_64 SHA-256 pass@1 file.5"
    found = [m.group(0) for m in claimcheck.TOKEN_RE.finditer(text)]
    assert found == ["0.25", "-0.05", "+1", "1,234", "12.3%", ".5", "1e-5", "2.5E3"]
    assert [m.group(0) for m in claimcheck.TOKEN_RE.finditer("12,3456 and 1,000,000")] == [
        "12",
        "3456",
        "1,000,000",
    ]
    assert claimcheck.NUMBER_FULL.fullmatch("-12.5%")
    assert not claimcheck.NUMBER_FULL.fullmatch("12 tasks")


def test_code_spans() -> None:
    assert claimcheck.code_spans("a `x` b ``y ` z`` c") == [(2, 5), (8, 18)]
    assert claimcheck.code_spans("unclosed ` tick and ``mismatch`") == []
    assert claimcheck.code_spans("`a` `b`") == [(0, 3), (4, 7)]
    assert claimcheck.code_spans("no code") == []


def test_iter_lines_modes_and_lists() -> None:
    text = (
        "```bash\n1\n```\n"
        "```python\n2\n```\n"
        "~~~~ text\n3\n~~~\n4\n~~~~\n"
        "````\n```\n5\n````\n"
        "1. one\n2. two\n   more\n3. three\n\n"
        "para\n12. not a list\n\n"
        "- bullet\n4. continues the list\n"
        "para again\n\nnext para\n7. still prose\n"
        "## Heading\n5. after a heading\n"
    )
    lines = {ln.number: ln for ln in claimcheck.iter_lines(text)}
    assert [lines[i].mode for i in (1, 2, 3)] == ["skip", "skip", "skip"]
    assert [lines[i].mode for i in (4, 5, 6)] == ["skip", "code", "skip"]
    assert [lines[i].mode for i in (8, 9, 10, 11)] == ["skip", "skip", "skip", "skip"]
    assert [lines[i].mode for i in (13, 14, 15)] == ["code", "code", "skip"]
    ok = {n for n, ln in lines.items() if ln.list_ok}
    assert {16, 17, 19, 25, 31} <= ok
    assert 23 not in ok and 29 not in ok
    unclosed = list(claimcheck.iter_lines("```text\n1\n2\n"))
    assert [ln.mode for ln in unclosed] == ["skip", "skip", "skip"]
    inline = list(claimcheck.iter_lines("```inline``` 5\n"))
    assert inline[0].mode == "prose"


def test_scan_line_masks_and_markers() -> None:
    line = "x `9` 0.25<!--claim:a.b--> [t](p/9 \"T 9\") [r][9] [^9] https://h/9 <b 9>"
    scan = claimcheck.scan_line(line)
    assert [t.text for t in scan.tokens] == ["0.25", "9"]
    assert scan.markers == [claimcheck.Marker("a.b", 10, 26)]
    assert "9" not in scan.masked[: scan.tokens[1].start]
    ref = claimcheck.scan_line("[7]: https://example.org/7 \"Title 9\"")
    assert ref.tokens == []
    code = claimcheck.scan_line("`7` https://x/7 [t](8)", mode="code")
    assert [t.text for t in code.tokens] == ["7", "8"]


def test_scan_line_directives_and_malformed_markers() -> None:
    assert claimcheck.scan_line("a 1 <!-- claimcheck:ignore-line quoted text -->").directive == (
        "quoted text"
    )
    assert claimcheck.scan_line("a 1 <!--claimcheck:ignore-line\tquoted-->  ").directive == "quoted"
    cases = {
        "a 1 <!-- claimcheck:ignore-line -->": "needs a reason",
        "<!-- claimcheck:ignore-line why --> 1": "must end the line",
        "1 <!-- claimcheck:skip why -->": "unknown claimcheck directive",
        "1<!-- claim:a -->": "write <!--claim:KEY-->",
        "1<!--claim:a b-->": "malformed claim marker",
        "1<!--claim:-->": "malformed claim marker",
        "1<!--Claim:a-->": "write <!--claim:KEY-->",
    }
    for text, needle in cases.items():
        scan = claimcheck.scan_line(text)
        assert any(needle in p for p in scan.problems), (text, scan.problems)
        assert scan.directive is None
    assert claimcheck.scan_line("1 <!-- claims are fine here -->").problems == []


def test_excluded_contexts() -> None:
    text = (
        "Commit 843405b, hash 5e72198d1145ec73c16cb566f6bce69562623ac6b97ecef5a564a61137671be9.\n"
        "On 2026-10-23T01:58:11Z, 2026-10-23 12:30, 2026-11, and in 1999 and 2099.\n"
        "Python 3.11 and 3.12, uv 0.11.32, version 2, Linux 6.18.44, and 1.2.3.\n"
        "See section 8, sections 6 to 10, rules 1 and 11, steps 1-3, Figure 2, Table 3.\n"
        "Also §8, §§ 8, 9, appendix 2, line 14, items 1, 2, and 3.\n"
        "arXiv 2606.08960v2 and arXiv:2507.02825.\n"
        "## 3. Results\n"
        "### 3.2 Setup\n"
    )
    assert unbacked(text) == []
    whys = {d.rsplit("(", 1)[-1].rstrip(")") for d in claimcheck.check_text(
        text, "D.md", {}, [], verbose=True
    ).details}
    assert whys == {
        "hex string",
        "date",
        "year",
        "version",
        "section or rule reference",
        "arXiv id",
        "heading number",
    }


def test_strict_cases_stay_checked() -> None:
    text = (
        "## 3 tasks\n"
        "Rates [0.12,0.30], 3x faster, _0.42_, 10-23, 7B, 2nd, 1950-20, and 2100.\n"
        "section 8 and 40 tasks; Python 3.12 and 40 tasks; steps 0.5.\n"
        "A paragraph that wraps\n"
        "12. here is not a list marker.\n"
        "<!-- hidden 99 --> <img width=\"600\"> | 1 | 2 |\n"
        "```python\nx = 456\n```\n"
        "abc1234defg 1234567\n"
    )
    assert unbacked(text) == [
        "3",
        "0.12",
        "0.30",
        "3",
        "0.42",
        "10",
        "23",
        "7",
        "2",
        "1950",
        "20",
        "2100",
        "40",
        "40",
        "0.5",
        "12",
        "99",
        "600",
        "1",
        "2",
        "456",
        "1234567",
    ]


def test_excluded_and_allowlisted_helpers() -> None:
    scan = claimcheck.scan_line("1. In 2026, x 7")
    tok = {t.text: t for t in scan.tokens}
    assert claimcheck.excluded(tok["2026"], scan) == "year"
    assert claimcheck.excluded(tok["7"], scan) is None
    listed = claimcheck.scan_line("1. In 2026", list_ok=True)
    assert claimcheck.excluded(listed.tokens[0], listed) == "ordered-list marker"
    entry = claimcheck.AllowEntry("40", re.compile(r"at least 40"), "target", 2)
    assert claimcheck.allowlisted("40", "at least 40 tasks", [entry]) is entry
    assert claimcheck.allowlisted("40", "exactly 40 tasks", [entry]) is None
    assert claimcheck.allowlisted("41", "at least 40 tasks", [entry]) is None


# ---------------------------------------------------------------- loading


def test_load_allowlist(tmp_path: Path) -> None:
    path = tmp_path / "allow.tsv"
    assert claimcheck.load_allowlist(path) == ([], [])
    path.write_text(
        "# comment\n\nnumber\tcontext\treason\n"
        "95%\t95% CI\tconfidence level\n"
        "40\tat least 40\n"
        "forty\tx\tr\n"
        "40\t\tr\n"
        "40\t(\tr\n"
        "40\tat least 40\t \n",
        encoding="utf-8",
    )
    entries, problems = claimcheck.load_allowlist(path, "A.tsv")
    assert [(e.number, e.reason, e.line) for e in entries] == [("95%", "confidence level", 4)]
    text = " | ".join(problems)
    assert "A.tsv:5: needs 3 tab-separated columns" in text
    assert "A.tsv:6: 'forty' is not a number token" in text
    assert "A.tsv:7: context regex missing" in text
    assert "A.tsv:8: bad context regex" in text
    assert "A.tsv:9: reason missing for 40" in text


def test_load_registry(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    assert "missing" in claimcheck.load_registry(path)[1][0]
    path.write_text("{bad", encoding="utf-8")
    assert "not valid JSON" in claimcheck.load_registry(path)[1][0]
    path.write_text("[]", encoding="utf-8")
    assert "JSON object" in claimcheck.load_registry(path)[1][0]
    path.write_text(json.dumps({"a": {"value": "1"}, "b": {"value": 2}, "c": 3}), encoding="utf-8")
    values, problems = claimcheck.load_registry(path)
    assert values == {"a": "1"}
    assert len(problems) == 2


def test_documents_and_template_outputs(tmp_path: Path) -> None:
    root = tmp_path
    assert claimcheck.documents(root) == ["README.md", "docs/REPORT.md"]
    put(root, "docs/cards/b.md", "")
    put(root, "docs/cards/a.md", "")
    put(root, "docs/NOTES.md", "")
    put(root, "docs/extra/x.md", "")
    put_json(
        root,
        claimcheck.SPEC,
        {
            "templates": {
                "a.md.in": "docs/NOTES.md",
                "b.md.in": "docs/extra/*.md",
                "c.md.in": "../outside.md",
                "d.md.in": None,
                "e.md.in": "docs/absent.md",
            }
        },
    )
    assert claimcheck.template_outputs(root) == ["docs/NOTES.md", "docs/extra/x.md"]
    assert claimcheck.documents(root) == [
        "README.md",
        "docs/REPORT.md",
        "docs/cards/a.md",
        "docs/cards/b.md",
        "docs/NOTES.md",
        "docs/extra/x.md",
    ]
    put(root, claimcheck.SPEC, "{bad")
    assert claimcheck.template_outputs(root) == []
    put_json(root, claimcheck.SPEC, {"templates": ["x"]})
    assert claimcheck.template_outputs(root) == []


# ---------------------------------------------------------------- checking documents


def test_check_text_claims_and_problems() -> None:
    registry = {"a": "0.25", "n": "1,234", "p": "12.3%"}
    text = (
        "Rate **0.25<!--claim:a-->**, n 1,234<!--claim:n--> and 12.3%<!--claim:p-->.\n"
        "Stale 0.26<!--claim:a--> unknown 0.3<!--claim:zz--> dangling<!--claim:a-->.\n"
        "Two markers 0.25<!--claim:a--><!--claim:a--> and a bare 0.5.\n"
        "Ignored 12 of 12 <!-- claimcheck:ignore-line quoted --> \n"
        "Ignored but stale 0.24<!--claim:a--> <!-- claimcheck:ignore-line quoted -->\n"
    )
    rep = claimcheck.check_text(text, "D.md", registry, [], verbose=True)
    assert rep.claims == 4
    assert rep.ignored_lines == 2
    problems = " | ".join(rep.problems)
    assert "D.md:2: 0.26 is marked as claim a, whose registry value is 0.25" in problems
    assert "D.md:2: unknown claim zz" in problems
    assert "D.md:2: claim marker for a does not follow a number" in problems
    assert "D.md:3: claim marker for a does not follow a number" in problems
    assert "D.md:3: unbacked number 0.5" in problems
    assert "D.md:5: 0.24 is marked as claim a" in problems
    assert "D.md:4" not in problems
    assert any("line ignored (quoted)" in d for d in rep.details)
    assert any("claim a" in d for d in rep.details)


def test_check_text_allowlist_counts() -> None:
    entry = claimcheck.AllowEntry("95%", re.compile("95% CI"), "level", 3)
    rep = claimcheck.check_text("A (95% CI x) and 95% of y.\n", "D.md", {}, [entry], verbose=True)
    assert rep.allowlisted == 1
    assert rep.problems == ["D.md:1: unbacked number 95%"]
    assert any("allowlisted (docs/claims/allowlist.tsv:3)" in d for d in rep.details)


def test_claim_occurrences() -> None:
    text = "a 0.25<!--claim:a--> b<!--claim:b--> `0.1<!--claim:c-->`\n```text\n1<!--claim:d-->\n```\n"
    text += "bad 1<!-- claim:e -->\n"
    found, problems = claimcheck.claim_occurrences(text)
    assert found == [claimcheck.Occurrence(1, "a", "0.25"), claimcheck.Occurrence(1, "b", None)]
    assert len(problems) == 1 and problems[0].startswith("5: malformed claim marker")


def test_run_and_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path
    out, rc = claimcheck.run(root)
    assert rc == 1
    assert "claimcheck: docs/claims/registry.json missing (run make report)" in out
    assert "claimcheck: README.md missing" in out and out[-1] == "claimcheck: FAIL"
    put_json(root, claimcheck.REGISTRY, {"a": {"value": "0.25"}})
    put(root, claimcheck.ALLOWLIST, "number\tcontext\treason\n")
    put(root, "README.md", "# t\nRate 0.25<!--claim:a-->.\n")
    put(root, "docs/REPORT.md", "# r\nNo numbers.\n")
    put(root, "docs/cards/x.md", "card 7\n")
    out, rc = claimcheck.run(root)
    assert rc == 1
    assert out == [
        "claimcheck: README.md OK (1 claims, 0 allowlisted)",
        "claimcheck: docs/REPORT.md OK (0 claims, 0 allowlisted)",
        "claimcheck: docs/cards/x.md:1: unbacked number 7",
        "claimcheck: docs/cards/x.md FAIL (1 problems)",
        "claimcheck: FAIL",
    ]
    (root / "docs/cards/x.md").unlink()
    assert claimcheck.main(["--root", str(root)]) == 0
    assert claimcheck.main(["--root", str(root), "--verbose"]) == 0
    printed = capsys.readouterr().out
    assert "claimcheck: README.md:2: 0.25 claim a" in printed


# ---------------------------------------------------------------- end to end


def test_example_template_renders_and_passes(tmp_path: Path) -> None:
    root = built(tmp_path)
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "0.25<!--claim:example.rate-->" in readme
    assert "![False-accept task rate (synthetic example)](docs/figures/example.svg)" in readme
    report_md = (root / "docs/REPORT.md").read_text(encoding="utf-8")
    assert "(figures/example.svg)" in report_md
    out, rc = claimcheck.run(root)
    assert rc == 0, out
    assert out == [
        "claimcheck: README.md OK (7 claims, 2 allowlisted)",
        "claimcheck: docs/REPORT.md OK (7 claims, 2 allowlisted)",
    ]
    out, rc = freshness.run(root)
    assert rc == 0, out
    assert out == [
        "freshness: README.md OK (7 live claims)",
        "freshness: docs/REPORT.md OK (7 live claims)",
    ]
    out, rc = citecheck.run(root)
    assert (rc, out) == (0, ["citecheck: 0 references verified in README.md and docs/REPORT.md"])


def test_mutation_unbacked_number_fails(tmp_path: Path) -> None:
    root = built(tmp_path)
    readme = root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "Hand-typed rate 0.31.\n", "utf-8")
    out, rc = claimcheck.run(root)
    assert rc == 1
    assert any(re.search(r"README\.md:\d+: unbacked number 0\.31$", ln) for ln in out)
    assert freshness.run(root)[1] == 1  # README.md is no longer its template's rendering


def test_mutation_marker_value_differs_from_registry(tmp_path: Path) -> None:
    root = built(tmp_path)
    edit(root / "README.md", "0.25<!--claim:example.rate-->", "0.26<!--claim:example.rate-->")
    out, rc = claimcheck.run(root)
    assert rc == 1
    assert any("0.26 is marked as claim example.rate, whose registry value is 0.25" in o for o in out)
    out, rc = freshness.run(root)
    assert rc == 1
    assert any("claim example.rate shows 0.26, but" in o for o in out)


def test_mutation_stale_artifact_fails_freshness(tmp_path: Path) -> None:
    root = built(tmp_path)
    changed = json.loads(json.dumps(SYNTHETIC))
    changed["e1"]["false_accept_task_rate"]["point"] = 0.3
    put_json(root, ARTIFACT, changed)
    out, rc = freshness.run(root)
    assert rc == 1
    text = "\n".join(out)
    assert "claim example.rate: docs/claims/registry.json has 0.25, but" in text
    assert f"claim example.rate: {ARTIFACT} changed after docs/claims/registry.json" in text
    assert "docs/figures/example.svg is stale" in text
    assert "README.md is not the current rendering" in text
    assert "claim example.rate shows 0.25, but artifacts/example/summary.json now gives 0.30" in text
    assert claimcheck.run(root)[1] == 0  # the registry still agrees with the documents


def test_mutation_artifact_change_without_value_change(tmp_path: Path) -> None:
    root = built(tmp_path)
    changed = {**SYNTHETIC, "provenance": {"note": "added later"}}
    put_json(root, ARTIFACT, changed)
    out, rc = freshness.run(root)
    assert rc == 1
    assert sum("changed after docs/claims/registry.json was built" in o for o in out) == len(CLAIMS)
    assert "freshness: README.md OK (7 live claims)" in out


def test_mutation_unknown_claim_key(tmp_path: Path) -> None:
    root = built(tmp_path)
    readme = root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "Odd 0.25<!--claim:example.nope-->\n", "utf-8")
    out, rc = claimcheck.run(root)
    assert rc == 1 and any("unknown claim example.nope" in o for o in out)
    out, rc = freshness.run(root)
    assert rc == 1 and any("unknown claim example.nope (not declared" in o for o in out)
    put(root, "docs/templates/README.md.in", EXAMPLE + "{{claim:example.nope}}\n")
    out, rc = report.run(root)
    assert rc == 1 and any("unknown claim 'example.nope'" in o for o in out)


def test_mutation_allowlist_entry_without_reason(tmp_path: Path) -> None:
    root = built(tmp_path)
    put(root, claimcheck.ALLOWLIST, ALLOW.replace("(design parameter)\n", "\n").replace(
        "preregistered minimum sample size", ""
    ))
    out, rc = claimcheck.run(root)
    assert rc == 1
    assert any("allowlist.tsv:4: reason missing for 40" in o for o in out)


def test_mutation_unverified_reference(tmp_path: Path) -> None:
    url = "https://arxiv.org/abs/2606.08960"
    doc = EXAMPLE + f"\nRelated work: {url}.\n"
    root = built(tmp_path, readme=doc, entries=[citation(url)])
    assert citecheck.run(root)[0] == [
        "citecheck: 1 references verified in README.md and docs/REPORT.md"
    ]
    put_json(
        root,
        citecheck.CITECHECK,
        {"schema": citecheck.SCHEMA, "entries": [citation(url, "unreachable")]},
    )
    out, rc = citecheck.run(root)
    assert rc == 1
    assert out[0].startswith(f"citecheck: unverified reference {url} (README.md:")
    assert "entry ref is unreachable" in out[0] and out[-1] == "citecheck: FAIL"


@pytest.mark.parametrize("missing", ["README.md", "docs/REPORT.md"])
def test_mutation_missing_document(tmp_path: Path, missing: str) -> None:
    root = built(tmp_path)
    (root / missing).unlink()
    for tool in (claimcheck, freshness, citecheck):
        out, rc = tool.run(root)
        assert rc == 1, tool.__name__
        assert any(f"{missing} missing" in o for o in out), (tool.__name__, out)


def test_make_targets_drive_the_tools(tmp_path: Path) -> None:
    root = make_layout(tmp_path)
    shutil.copy(REPO / "Makefile", root / "Makefile")
    for name in TOOLS:
        shutil.copy(REPO / "tools" / name, root / "tools" / name if (root / "tools").is_dir()
                    else (root / "tools").mkdir() or root / "tools" / name)
    run = subprocess.run(
        ["make", "-s", "report", "claimcheck", "freshness", "citecheck", "reproduce",
         f"PY={sys.executable}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    for doc in ("README.md", "docs/REPORT.md"):
        assert f"claimcheck: {doc} OK" in run.stdout
        assert f"freshness: {doc} OK" in run.stdout
    edit(root / "README.md", "0.25<!--claim:example.rate-->", "0.20<!--claim:example.rate-->")
    for target in ("claimcheck", "freshness"):
        failed = subprocess.run(
            ["make", "-s", target, f"PY={sys.executable}"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert failed.returncode != 0 and f"{target}: FAIL" in failed.stdout


def test_ship_check_g10_and_readme_checks_accept_a_compliant_layout(tmp_path: Path) -> None:
    readme = (
        "# graderproof\n\n"
        "In a synthetic example, graders accepted {{claim:example.rate}} of broken solutions "
        "(95% CI {{claim:example.rate_lo}} to {{claim:example.rate_hi}}).\n\n"
        "{{figure:example}}\n\n"
        "| Benchmark | False-accept task rate |\n|---|---|\n| Example | {{claim:example.rate}} |\n\n"
        "## Quickstart\n\n```bash\nmake demo\n```\n\n"
        "## What it is and is not\n\nA measurement tool.\n\n"
        "## Key results\n\nSee [the artifact](artifacts/example/summary.json) and "
        "[the preregistration](prereg/0001-example.md).\n\n"
        "## How it works\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\n"
        "## Use it on your own benchmark\n\nWrite an adapter.\n\n"
        "## Reproduce\n\n`make reproduce`\n\n## Limitations\n\nSynthetic.\n\n"
        "## Responsible disclosure\n\nPrivate.\n\n## Related work\n\nNone.\n\n"
        "## Citation\n\nSee CITATION.cff.\n\n## License\n\nMIT.\n"
    )
    root = built(tmp_path, readme=readme)
    shutil.copy(REPO / "Makefile", root / "Makefile")
    (root / "tools").mkdir()
    for name in TOOLS:
        shutil.copy(REPO / "tools" / name, root / "tools" / name)
    assert ship_check.readme_problems(root) == ""
    ctx = ship_check.Ctx(origin=root, work=tmp_path / "work", fast=True, clone=root)
    result = ship_check.g10_claim_integrity(ctx)
    assert result.ok, result.evidence
    edit(root / "README.md", "0.10<!--claim:example.rate_lo-->", "0.11<!--claim:example.rate_lo-->")
    assert not ship_check.g10_claim_integrity(ctx).ok


def test_citecheck_finds_the_same_urls_as_ship_check(tmp_path: Path) -> None:
    text = (
        "See https://arxiv.org/abs/2606.08960. and <https://example.org/a>, "
        "`https://example.org/code` and https://github.com/raj200501/graderproof/x "
        "and https://github.com/raj200501/graderproof.git\n"
    )
    put(tmp_path, "README.md", text)
    assert citecheck.cited_urls(text) == ship_check.cited_urls(tmp_path)
