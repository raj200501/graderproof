"""Tests for tools/report.py (`make report`): spec validation, claim resolution, figures,
template rendering, and what it writes. Layouts are temporary and synthetic.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import claimcheck
import pytest
import report
from test_claims_tooling import ARTIFACT, CLAIMS, EXAMPLE, FIGURE, SYNTHETIC, built, put, put_json


def spec_of(root: Path, value: dict[str, Any]) -> report.Spec:
    """Write a spec and load it (it must be valid)."""
    put_json(root, claimcheck.SPEC, value)
    spec, problems = report.load_spec(root)
    assert problems == [], problems
    return spec


def resolved(root: Path) -> tuple[report.Spec, dict[str, report.Claim]]:
    """The synthetic artifact, the example claims and figure, resolved."""
    put_json(root, ARTIFACT, SYNTHETIC)
    spec = spec_of(root, {"claims": CLAIMS, "figures": {"example": FIGURE}})
    claims, problems = report.resolve_claims(root, spec)
    assert problems == []
    return spec, claims


# ---------------------------------------------------------------- values and paths


def test_sha256_text_and_dump() -> None:
    assert report.sha256_text("abc") == hashlib.sha256(b"abc").hexdigest()
    assert report.dump({"b": 1, "a": "é"}) == '{\n  "a": "é",\n  "b": 1\n}\n'


def test_json_type_and_json_equal() -> None:
    kinds: list[Any] = [None, True, 1, 1.5, "s", [], {}]
    assert [report.json_type(v) for v in kinds] == [
        "null",
        "boolean",
        "number",
        "number",
        "string",
        "array",
        "object",
    ]
    assert report.json_equal(1, 1.0) and report.json_equal(None, None)
    assert not report.json_equal(True, 1) and not report.json_equal(1, True)
    assert report.json_equal(True, True) and not report.json_equal("1", 1)
    assert report.json_equal([1, {"a": True}], [1.0, {"a": True}])
    assert not report.json_equal([1], [1, 2]) and not report.json_equal({"a": 1}, {"b": 1})
    assert not report.json_equal({"a": 1}, {"a": 2})


def test_parse_match_and_parse_path() -> None:
    assert [report.parse_match(v) for v in ("true", "3", '"3"', "abc", "")] == [
        True,
        3,
        "3",
        "abc",
        "",
    ]
    assert report.parse_path("a.b.-1") == report.Selector(("a", "b", "-1"))
    assert report.parse_path("") == report.Selector(())
    assert report.parse_path("|len") == report.Selector((), "len")
    assert report.parse_path("tasks|len") == report.Selector(("tasks",), "len")
    assert report.parse_path("v|count:kind=x y") == report.Selector(("v",), "count", "kind", "x y")
    assert report.parse_path("v|count:flaky=true").count_value is True
    for bad in ("a..b", ".a", "a|bad", "a|count:=x", "a|count:k", "a|count:k=v|len"):
        with pytest.raises(ValueError, match=re.escape(repr(bad))):
            report.parse_path(bad)


def test_resolve() -> None:
    data = {"a": {"ci": [0.1, 0.4]}, "rows": [{"k": "x"}, {"k": "y"}, {"j": 1}], "n": 3}
    assert report.resolve(data, report.parse_path("a.ci.0")) == 0.1
    assert report.resolve(data, report.parse_path("a.ci.-1")) == 0.4
    assert report.resolve(data, report.parse_path("")) is data
    assert report.resolve(data, report.parse_path("rows|len")) == 3
    assert report.resolve(data, report.parse_path("a|len")) == 1
    assert report.resolve(data, report.parse_path("rows|count:k=x")) == 1
    assert report.resolve(data, report.parse_path("rows|count:k=z")) == 0
    assert report.resolve([{"0": 5}], report.parse_path("0.0")) == 5
    cases = {
        "a.ci.2": "index 2 is out of range for a.ci (length 2)",
        "a.ci.x": "a.ci is a list and 'x' is not an index",
        "a.nope": "a has no key 'nope'",
        "n.x": "n is a number, so 'x' cannot select in it",
        "n|len": "|len needs a list or object, found a number",
        "a|count:k=x": "|count needs a list of objects",
        "a.ci|count:k=x": "|count needs a list of objects",
    }
    for path, message in cases.items():
        with pytest.raises(ValueError, match=re.escape(message)):
            report.resolve(data, report.parse_path(path))
    with pytest.raises(ValueError, match="the document root has no key 'x'"):
        report.resolve({}, report.parse_path("x"))


def test_check_format_and_format_value() -> None:
    for good in ("{:.2f}", "{}", "{:d}", "{:.1%}", "{}%", "{:,}"):
        report.check_format(good)
    for bad in ("{0:.2f}", "{:.2f} {}", "{!r}", "{:{w}}", "no field", "{"):
        with pytest.raises(ValueError):
            report.check_format(bad)
    assert report.format_value(0.25, "{:.2f}") == "0.25"
    assert report.format_value(4, "{:d}") == "4"
    assert report.format_value(1234, "{:,}") == "1,234"
    assert report.format_value(0.123, "{:.1%}") == "12.3%"
    assert report.format_value(-0.05, "{:+.2f}") == "-0.05"
    cases: list[tuple[Any, str, str]] = [
        (True, "{}", "is a boolean, not a number"),
        ("0.25", "{}", "is a string, not a number"),
        (float("nan"), "{}", "not a finite number"),
        (0.25, "{:d}", "does not apply"),
        (40, "{} tasks", "not a single number token"),
        (40, "{:>6}", "not a single number token"),
    ]
    for value, fmt, message in cases:
        with pytest.raises(ValueError, match=message):
            report.format_value(value, fmt)


def test_safe_relpath() -> None:
    assert report.safe_relpath("a/b.json")
    for bad in ("/a", "a//b", "./a", "a/../b", ""):
        assert not report.safe_relpath(bad), bad


# ---------------------------------------------------------------- the spec


def test_parse_claim() -> None:
    good = {"artifact": "artifacts/a/s.json", "path": "x.0", "format": "{:.2f}", "note": "n"}
    claim, problems = report.parse_claim("e1.a_b-c", good)
    assert problems == [] and claim is not None
    assert (claim.artifact, claim.selector) == ("artifacts/a/s.json", report.Selector(("x", "0")))
    lines = {**good, "artifact": "artifacts/a/v.jsonl"}
    assert report.parse_claim("k", lines)[0] is not None
    cases: list[tuple[str, Any, str]] = [
        ("bad key", good, "keys are letters and digits"),
        ("k", [], "must be an object"),
        ("k", {**good, "extra": 1}, "unknown field 'extra'"),
        ("k", {**good, "note": 3}, "note must be a string"),
        ("k", {"artifact": "artifacts/a.json", "path": "x"}, "must all be strings"),
        ("k", {**good, "artifact": "data/a.json"}, "artifact must be a .json or .jsonl file"),
        ("k", {**good, "artifact": "artifacts/../a.json"}, "artifact must be a .json"),
        ("k", {**good, "artifact": "artifacts/a.csv"}, "artifact must be a .json"),
        ("k", {**good, "format": "{} tasks {}"}, "needs exactly one field"),
        ("k", {**good, "path": "a..b"}, "has an empty component"),
    ]
    for key, raw, message in cases:
        claim, problems = report.parse_claim(key, raw)
        assert claim is None and any(message in p for p in problems), (key, raw, problems)


def test_check_mapping() -> None:
    assert report.check_mapping("README.md.in", "README.md") is None
    assert report.check_mapping("cards/*.md.in", "docs/cards/*.md") is None
    assert report.check_mapping("example.md.in", None) is None
    cases: list[tuple[str, Any, str]] = [
        ("README.md", "README.md", "ending in .md.in"),
        ("../x.md.in", "x.md", "ending in .md.in"),
        ("a*b*.md.in", "x.md", "at most one *"),
        ("*/a.md.in", "x.md", "at most one *"),
        ("a.md.in", "a.txt", "ending in .md, or null"),
        ("a.md.in", 3, "ending in .md, or null"),
        ("a.md.in", "/abs.md", "ending in .md, or null"),
        ("a*.md.in", "a.md", "use one * in the file name of both"),
        ("a*.md.in", "*/a.md", "use one * in the file name of both"),
        ("a.md.in", "docs/templates/a.md", "must not be under"),
        ("a.md.in", "artifacts/a.md", "must not be under"),
    ]
    for template, output, message in cases:
        why = report.check_mapping(template, output)
        assert why is not None and message in why, (template, output, why)


def test_figure_text_and_parse_domain() -> None:
    assert report.figure_text(None, "axis_label", "W", False) == (None, [])
    assert report.figure_text("Title", "title", "W", True) == ("Title", [])
    for bad in (None, "", "  ", 3):
        assert report.figure_text(bad, "title", "W", True)[1] == [
            "W: title must be a non-empty string"
        ]
    for bad in ("a [b]", "a\nb"):
        assert "without [ or ]" in report.figure_text(bad, "alt", "W", True)[1][0]
    assert report.parse_domain(None, "W") == (None, [])
    assert report.parse_domain([0, 1], "W") == ((0.0, 1.0), [])
    assert report.parse_domain([-1, 0.5], "W") == ((-1.0, 0.5), [])
    for bad_domain in ([1, 0], [0], [True, 1], [0, float("inf")], "x", [0, "1"], [0.5, 1]):
        assert report.parse_domain(bad_domain, "W")[1], bad_domain


def test_parse_figure() -> None:
    claims = {k: report.parse_claim(k, v)[0] for k, v in CLAIMS.items()}
    known = {k: c for k, c in claims.items() if c is not None}
    fig, problems = report.parse_figure("example", FIGURE, known)
    assert problems == [] and fig is not None
    assert fig.alt == FIGURE["title"] and fig.domain == (0.0, 1.0)
    assert fig.bars == (
        report.BarSpec("Example", "example.rate", "example.rate_lo", "example.rate_hi"),
    )
    plain = {"title": "T", "alt": "A", "bars": [{"label": "L", "value": "example.rate"}]}
    fig, problems = report.parse_figure("plain", plain, known)
    assert fig is not None and fig.alt == "A" and fig.bars[0].lo is None
    assert fig.tick_format is None and fig.axis_label is None
    bar: dict[str, Any] = {"label": "L", "value": "example.rate"}
    cases: list[tuple[str, Any, str]] = [
        ("Bad Name", plain, "names are lowercase"),
        ("f", [], "must be an object"),
        ("f", {**plain, "colour": "red"}, "unknown field 'colour'"),
        ("f", {**plain, "title": ""}, "title must be a non-empty string"),
        ("f", {**plain, "tick_format": 3}, "tick_format must be a string"),
        ("f", {**plain, "tick_format": "{:d}"}, "Unknown format code"),
        ("f", {**plain, "tick_format": "{} {}"}, "needs exactly one field"),
        ("f", {**plain, "domain": [1, 0]}, "domain must be [low, high]"),
        ("f", {**plain, "bars": []}, "bars must be a non-empty list"),
        ("f", {**plain, "bars": "x"}, "bars must be a non-empty list"),
        ("f", {**plain, "bars": [3]}, "bar 0 must be an object"),
        ("f", {**plain, "bars": [{**bar, "size": 1}]}, "unknown field 'size'"),
        ("f", {**plain, "bars": [{"value": "example.rate"}]}, "label must be a non-empty"),
        ("f", {**plain, "bars": [{**bar, "value": "nope"}]}, "value must name a declared claim"),
        ("f", {**plain, "bars": [{**bar, "lo": "example.rate_lo"}]}, "give both lo and hi"),
        ("f", {**plain, "bars": [{**bar, "lo": "x", "hi": "y"}]}, "lo and hi must name declared"),
    ]
    for name, raw, message in cases:
        fig, problems = report.parse_figure(name, raw, known)
        assert fig is None and any(message in p for p in problems), (name, raw, problems)


def test_load_spec(tmp_path: Path) -> None:
    root = tmp_path
    assert report.load_spec(root)[1] == ["docs/claims/spec.json missing"]
    put(root, claimcheck.SPEC, "{bad")
    assert "is not valid JSON" in report.load_spec(root)[1][0]
    put_json(root, claimcheck.SPEC, [])
    assert report.load_spec(root)[1] == ["docs/claims/spec.json must be a JSON object"]
    put_json(root, claimcheck.SPEC, {"claims": [], "templates": 3, "figures": "x", "other": 1})
    assert report.load_spec(root)[1] == [
        "docs/claims/spec.json: unknown top-level key 'other'",
        "docs/claims/spec.json: claims must be an object",
        "docs/claims/spec.json: templates must be an object",
        "docs/claims/spec.json: figures must be an object",
    ]
    value = {
        "comment": "allowed",
        "claims": {**CLAIMS, "bad key": CLAIMS["example.rate"]},
        "templates": {"README.md.in": "README.md", "x.md": "x.md"},
        "figures": {"example": FIGURE, "Bad": FIGURE},
    }
    put_json(root, claimcheck.SPEC, value)
    spec, problems = report.load_spec(root)
    assert sorted(spec.claims) == sorted(CLAIMS)
    assert spec.templates == {"README.md.in": "README.md"}
    assert sorted(spec.figures) == ["example"]
    assert len(problems) == 3


# ---------------------------------------------------------------- artifacts and claims


def test_load_artifact(tmp_path: Path) -> None:
    root = tmp_path
    assert report.load_artifact(root, "artifacts/a.json") == "artifacts/a.json missing"
    path = put(root, "artifacts/a.json", '{"x": 1}\n')
    loaded = report.load_artifact(root, "artifacts/a.json")
    assert loaded == ({"x": 1}, hashlib.sha256(path.read_bytes()).hexdigest())
    put(root, "artifacts/b.json", "{bad")
    assert "artifacts/b.json is not valid JSON" in str(
        report.load_artifact(root, "artifacts/b.json")
    )
    (root / "artifacts/c.json").write_bytes(b"\xff\xfe")
    assert "artifacts/c.json is not UTF-8" in str(report.load_artifact(root, "artifacts/c.json"))
    put(root, "artifacts/v.jsonl", '{"k": "x"}\n\n{"k": "y"}\n')
    lines = report.load_artifact(root, "artifacts/v.jsonl")
    assert isinstance(lines, tuple) and lines[0] == [{"k": "x"}, {"k": "y"}]
    put(root, "artifacts/w.jsonl", '{"k": "x"}\n{bad\n')
    assert "artifacts/w.jsonl:2 is not valid JSON" in str(
        report.load_artifact(root, "artifacts/w.jsonl")
    )


def test_resolve_claims(tmp_path: Path) -> None:
    root = tmp_path
    spec, claims = resolved(root)
    assert {k: c.value for k, c in claims.items()} == {
        "example.flaky": "1",
        "example.rate": "0.25",
        "example.rate_hi": "0.45",
        "example.rate_lo": "0.10",
        "example.tasks": "4",
    }
    sha = hashlib.sha256((root / ARTIFACT).read_bytes()).hexdigest()
    assert claims["example.rate"] == report.Claim(
        "example.rate", "0.25", 0.25, ARTIFACT, "e1.false_accept_task_rate.point", sha
    )
    put(root, "artifacts/v.jsonl", '{"kind": "violating"}\n{"kind": "valid"}\n')
    broken = {
        "gone": {"artifact": "artifacts/none.json", "path": "x", "format": "{}"},
        "path": {"artifact": ARTIFACT, "path": "e1.nope", "format": "{}"},
        "text": {"artifact": ARTIFACT, "path": "synthetic", "format": "{}"},
        "lines": {"artifact": "artifacts/v.jsonl", "path": "|count:kind=valid", "format": "{}"},
    }
    spec = spec_of(root, {"claims": broken})
    claims, problems = report.resolve_claims(root, spec)
    assert list(claims) == ["lines"] and claims["lines"].value == "1"
    assert problems == [
        "claim gone: artifacts/none.json missing",
        f"claim path: {ARTIFACT} 'e1.nope': e1 has no key 'nope'",
        f"claim text: {ARTIFACT} 'synthetic': the value is a string, not a number",
    ]


def test_text_numbers() -> None:
    allow = [claimcheck.AllowEntry("95%", re.compile("95% CI"), "level", 3)]
    assert report.text_numbers("Rate (95% CI)", "figure f title", allow) == []
    assert report.text_numbers("Rate 0.31", "figure f title", allow) == [
        "figure f title: unbacked number 0.31"
    ]
    assert report.text_numbers("1. First", "figure f alt", []) == [
        "figure f alt: unbacked number 1"
    ]


def test_draw_figures(tmp_path: Path) -> None:
    spec, claims = resolved(tmp_path)
    figures, problems = report.draw_figures(spec, claims, [])
    assert problems == [] and list(figures) == ["docs/figures/example.svg"]
    assert figures["docs/figures/example.svg"].startswith("<svg ")
    fig, _ = report.parse_figure(
        "f", {**FIGURE, "title": "Rate over 40 tasks", "alt": "Rate"}, spec.claims
    )
    assert fig is not None
    figures, problems = report.draw_figures(report.Spec(spec.claims, {}, {"f": fig}), claims, [])
    assert figures == {} and problems == ["figure f title: unbacked number 40"]
    figures, problems = report.draw_figures(spec, {}, [])
    assert figures == {} and "did not resolve" in problems[0]
    narrow = report.Spec(
        spec.claims,
        {},
        {"f": report.FigureSpec("f", "T", "T", spec.figures["example"].bars, None, (0.0, 0.2))},
    )
    figures, problems = report.draw_figures(narrow, claims, [])
    assert figures == {} and "outside the domain" in problems[0]


# ---------------------------------------------------------------- templates


def test_match_template() -> None:
    assert report.match_template("README.md.in", "README.md.in") == ""
    assert report.match_template("README.md.in", "REPORT.md.in") is None
    assert report.match_template("cards/bfcl.md.in", "cards/*.md.in") == "bfcl"
    assert report.match_template("cards/x/y.md.in", "cards/*.md.in") is None
    assert report.match_template("other/x.md.in", "cards/*.md.in") is None
    assert report.match_template("a.md.in", "a*.md.in") is None


def test_render(tmp_path: Path) -> None:
    spec, claims = resolved(tmp_path)
    figures, _ = report.draw_figures(spec, claims, [])
    text = "Rate {{claim:example.rate}}.\n{{figure:example}}\nKeep ${{ github.sha }} and {{x}}.\n"
    for output, link in (
        ("README.md", "docs/figures/example.svg"),
        ("docs/REPORT.md", "figures/example.svg"),
        ("docs/cards/a.md", "../figures/example.svg"),
    ):
        rendered, problems = report.render(text, "T.md.in", output, spec, claims, figures)
        assert problems == [] and rendered is not None
        assert rendered.text == (
            "Rate 0.25<!--claim:example.rate-->.\n"
            f"![False-accept task rate (synthetic example)]({link})\n"
            "Keep ${{ github.sha }} and {{x}}.\n\n"
            + report.BANNER.format(template="T.md.in")
            + "\n"
        )
        assert (rendered.claims, rendered.figures) == (1, 1)
    cases = {
        "{{claim:example.nope}}": "T: unknown claim 'example.nope' (declare it in",
        "{{figure:nope}}": "T: unknown figure 'nope' (declare it in",
        "{{ claim:example.rate }}": "malformed placeholder '{{ claim:example.rate }}'",
        "{{Figure:example}}": "malformed placeholder",
        "x{{claim:example.rate}}": (
            "T:1: claim example.rate renders as no number token, not 0.25 (keep the placeholder"
        ),
        "1{{claim:example.rate}}": "claim example.rate renders as 10.25, not 0.25",
        "0.24<!--claim:example.rate-->": "claim example.rate renders as 0.24, not 0.25",
        "1<!--claim:example.zz-->": "T:1: marker for unknown claim example.zz",
        "1<!-- claim:example.rate -->": "T:1: malformed claim marker",
    }
    for body, message in cases.items():
        rendered, problems = report.render(body, "T", "README.md", spec, claims, figures)
        assert rendered is None and any(message in p for p in problems), (body, problems)
    partial = {k: c for k, c in claims.items() if k != "example.rate"}
    for body, message in (
        ("{{claim:example.rate}}", "T: claim example.rate did not resolve"),
        ("1<!--claim:example.rate-->", "T:1: marker for claim example.rate, which did not"),
        ("{{figure:example}}", "T: figure example was not drawn"),
    ):
        rendered, problems = report.render(body, "T", "README.md", spec, partial, {})
        assert rendered is None and any(message in p for p in problems), (body, problems)


def test_render_templates(tmp_path: Path) -> None:
    root = tmp_path
    spec, claims = resolved(root)
    assert report.render_templates(root, spec, claims, {}) == ({}, [], [])
    put(root, "docs/templates/README.md.in", "Rate {{claim:example.rate}}.\n")
    put(root, "docs/templates/cards/bfcl.md.in", "Card {{claim:example.tasks}}.\n")
    put(root, "docs/templates/example.md.in", EXAMPLE)
    put(root, "docs/templates/stray.md.in", "x\n")
    put(root, "docs/templates/notes.txt", "ignored\n")
    spec.templates = {
        "README.md.in": "README.md",
        "cards/*.md.in": "docs/cards/*.md",
        "example.md.in": None,
        "s*.md.in": "docs/s*.md",
        "st*.md.in": "docs/st*.md",
    }
    docs, examples, problems = report.render_templates(root, spec, claims, {})
    assert sorted(docs) == ["README.md", "docs/cards/bfcl.md"]
    assert docs["docs/cards/bfcl.md"].text.startswith("Card 4<!--claim:example.tasks-->.")
    assert examples == ["docs/templates/example.md.in"]
    assert problems == [
        "docs/templates/stray.md.in matches more than one entry of templates in "
        "docs/claims/spec.json (map it, or null)"
    ]
    spec.templates = {"README.md.in": "README.md", "x/*.md.in": "*.md"}
    put(root, "docs/templates/x/README.md.in", "Other.\n")
    docs, _, problems = report.render_templates(root, spec, claims, {})
    collision = "docs/templates/x/README.md.in and docs/templates/README.md.in both render"
    assert collision in problems[-1]
    assert "docs/templates/cards/bfcl.md.in matches no entry" in problems[0]
    (root / "docs/templates/x/README.md.in").unlink()
    put(root, "docs/templates/README.md.in", "Rate {{claim:example.nope}}.\n")
    docs, _, problems = report.render_templates(root, spec, claims, {})
    assert "README.md" not in docs and any("unknown claim 'example.nope'" in p for p in problems)


# ---------------------------------------------------------------- building and writing


def test_build_and_its_documents(tmp_path: Path) -> None:
    root = built(tmp_path)
    result = report.build(root)
    assert result.problems == []
    assert sorted(result.docs) == ["README.md", "docs/REPORT.md"]
    assert result.examples == ["docs/templates/example.md.in"]
    registry = result.registry
    assert list(registry) == sorted(CLAIMS)
    assert registry["example.tasks"] == {
        "artifact": ARTIFACT,
        "artifact_sha256": hashlib.sha256((root / ARTIFACT).read_bytes()).hexdigest(),
        "path": "tasks|len",
        "value": "4",
    }
    svg = (root / "docs/figures/example.svg").read_text(encoding="utf-8")
    assert result.manifest == [
        {
            "generator": "tools/report.py",
            "path": "docs/figures/example.svg",
            "sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
        }
    ]
    on_disk = json.loads((root / report.MANIFEST).read_text(encoding="utf-8"))
    assert on_disk == result.manifest
    assert json.loads((root / claimcheck.REGISTRY).read_text(encoding="utf-8")) == registry


def test_write_file(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b.txt"
    assert report.write_file(path, "x\n") is True
    assert path.read_bytes() == b"x\n"
    assert report.write_file(path, "x\n") is False
    assert report.write_file(path, "y\n") is True and path.read_text(encoding="utf-8") == "y\n"


def test_run_writes_everything_or_nothing(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    put_json(root, ARTIFACT, SYNTHETIC)
    put_json(root, claimcheck.SPEC, {"claims": {**CLAIMS, "bad": {**CLAIMS["example.rate"]}}})
    put(root, "docs/templates/README.md.in", "{{claim:example.nope}}\n")
    spec = json.loads((root / claimcheck.SPEC).read_text(encoding="utf-8"))
    spec["claims"]["bad"]["path"] = "e1.missing"
    spec["templates"] = {"README.md.in": "README.md"}
    put_json(root, claimcheck.SPEC, spec)
    out, rc = report.run(root)
    assert rc == 1 and out[-1] == "report: FAIL (nothing written)"
    assert "report: docs/templates/README.md.in: unknown claim 'example.nope'" in " ".join(out)
    assert not (root / claimcheck.REGISTRY).exists() and not (root / "README.md").exists()


def test_run_without_templates_or_figures(tmp_path: Path) -> None:
    root = tmp_path
    put_json(root, ARTIFACT, SYNTHETIC)
    spec: dict[str, Any] = {
        "claims": CLAIMS,
        "templates": {"README.md.in": "README.md", "example.md.in": None},
    }
    put_json(root, claimcheck.SPEC, spec)
    put(root, "docs/templates/example.md.in", EXAMPLE)
    out, rc = report.run(root)
    assert rc == 0
    assert out == [
        "report: 5 claims resolved into docs/claims/registry.json",
        "report: docs/templates/example.md.in is an example (mapped to null); not rendered",
        "report: no templates yet under docs/templates/ (mapped: README.md.in)",
    ]
    assert not (root / report.MANIFEST).exists()
    put(root, report.MANIFEST, '[{"path": "docs/figures/old.svg"}]\n')
    put(root, "docs/figures/old.svg", "<svg/>\n")
    out, rc = report.run(root)
    assert rc == 0
    assert "report: wrote artifacts/figures/manifest.json (0 figures)" in out
    assert out[-1] == (
        "report: note: docs/figures/old.svg is not declared in docs/claims/spec.json "
        "and not in artifacts/figures/manifest.json"
    )
    assert json.loads((root / report.MANIFEST).read_text(encoding="utf-8")) == []
    spec["templates"] = {}
    put_json(root, claimcheck.SPEC, spec)
    (root / "docs/templates/example.md.in").unlink()
    assert (
        report.run(root)[0][-2] == "report: no templates yet under docs/templates/ (mapped: none)"
    )


def test_run_and_main_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = built(tmp_path)
    put(root, "docs/templates/cards/x.md.in", "Card {{claim:example.tasks}}.\n")
    assert report.main(["--root", str(root)]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed == [
        "report: 5 claims resolved into docs/claims/registry.json",
        "report: drew docs/figures/example.svg",
        "report: wrote artifacts/figures/manifest.json (1 figures)",
        "report: rendered docs/templates/README.md.in -> README.md (7 claims, 1 figures)",
        "report: rendered docs/templates/REPORT.md.in -> docs/REPORT.md (7 claims, 1 figures)",
        "report: rendered docs/templates/cards/x.md.in -> docs/cards/x.md (1 claims, 0 figures)",
        "report: docs/templates/example.md.in is an example (mapped to null); not rendered",
    ]
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert report.run(root)[1] == 0
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before  # deterministic
