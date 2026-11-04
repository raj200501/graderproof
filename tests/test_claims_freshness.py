"""Tests for tools/freshness.py (`make freshness`) on temporary synthetic layouts."""

from __future__ import annotations

import json
from pathlib import Path

import claimcheck
import freshness
import pytest
import report
from test_claims_tooling import ARTIFACT, built, edit, put, put_json

REGISTRY = claimcheck.REGISTRY


def registry_of(root: Path) -> dict[str, dict[str, str]]:
    """The registry on disk."""
    data: dict[str, dict[str, str]] = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    return data


def test_registry_problems(tmp_path: Path) -> None:
    root = built(tmp_path)
    fresh = report.build(root)
    assert freshness.registry_problems(root, fresh) == []
    good = registry_of(root)
    (root / REGISTRY).unlink()
    assert freshness.registry_problems(root, fresh) == [f"{REGISTRY} missing (run make report)"]
    put(root, REGISTRY, "{bad")
    assert "is not valid JSON" in freshness.registry_problems(root, fresh)[0]
    put(root, REGISTRY, "[]")
    assert freshness.registry_problems(root, fresh) == [f"{REGISTRY} must be a JSON object"]
    changed = json.loads(json.dumps(good))
    changed["extra"] = {"value": "1"}
    del changed["example.tasks"]
    changed["example.rate"]["path"] = "e1.other"
    changed["example.rate"]["value"] = "0.99"
    changed["example.rate_lo"]["artifact_sha256"] = "0" * 64
    changed["example.rate_hi"] = "0.45"
    put_json(root, REGISTRY, changed)
    assert freshness.registry_problems(root, fresh) == [
        f"claim example.rate: {REGISTRY} was built from {ARTIFACT} 'e1.other', "
        f"but docs/claims/spec.json now says {ARTIFACT} 'e1.false_accept_task_rate.point'",
        f"claim example.rate: {REGISTRY} has 0.99, but {ARTIFACT} now gives 0.25",
        f"claim example.rate_hi is not in {REGISTRY} (run make report)",
        f"claim example.rate_lo: {ARTIFACT} changed after {REGISTRY} was built "
        "(its sha256 differs; run make report)",
        f"claim example.tasks is not in {REGISTRY} (run make report)",
        f"{REGISTRY} has claim extra, which docs/claims/spec.json does not declare",
    ]
    (root / ARTIFACT).unlink()
    gone = report.build(root)
    assert freshness.registry_problems(root, gone) == [
        f"{REGISTRY} has claim extra, which docs/claims/spec.json does not declare"
    ]  # claims that no longer re-derive are reported once, by the build


def test_figure_problems(tmp_path: Path) -> None:
    root = built(tmp_path)
    fresh = report.build(root)
    assert freshness.figure_problems(root, fresh) == []
    svg = root / "docs/figures/example.svg"
    svg.unlink()
    assert freshness.figure_problems(root, fresh) == [
        "docs/figures/example.svg missing (run make report)"
    ]
    report.run(root)
    edit(svg, "<title", "<title lang='en'")
    assert freshness.figure_problems(root, fresh) == [
        "docs/figures/example.svg is stale: it is not what the artifacts give now"
    ]
    report.run(root)
    manifest = root / report.MANIFEST
    stale = "artifacts/figures/manifest.json does not list exactly the current figures and hashes"
    edit(manifest, '"generator": "tools/report.py"', '"generator": "by hand"')
    assert freshness.figure_problems(root, fresh) == [stale]
    put(root, report.MANIFEST, "{bad")
    assert freshness.figure_problems(root, fresh) == [stale]
    manifest.unlink()
    assert freshness.figure_problems(root, fresh) == [
        "artifacts/figures/manifest.json missing (run make report)"
    ]
    (root / ARTIFACT).unlink()
    assert freshness.figure_problems(root, report.build(root)) == []  # the build lists why


def test_document_problems(tmp_path: Path) -> None:
    root = built(tmp_path)
    fresh = report.build(root)
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert freshness.document_problems("README.md", readme, fresh) == ([], 7)
    extra = (
        "Unknown 0.1<!--claim:zz-->, dangling<!--claim:example.rate-->, "
        "stale 0.24<!--claim:example.rate-->, bad 1<!-- claim:x -->\n"
    )
    problems, live = freshness.document_problems("README.md", readme + extra, fresh)
    line = readme.count("\n") + 1
    assert live == 10
    assert problems == [
        f"README.md:{line}: malformed claim marker '<!-- claim:x -->' (write <!--claim:KEY-->)",
        f"README.md:{line}: unknown claim zz (not declared in docs/claims/spec.json)",
        f"README.md:{line}: claim marker for example.rate does not follow a number",
        f"README.md:{line}: claim example.rate shows 0.24, but {ARTIFACT} now gives 0.25",
        "README.md is not the current rendering of docs/templates/README.md.in",
    ]
    by_hand = "Card 0.25<!--claim:example.rate-->.\n"
    assert freshness.document_problems("docs/cards/hand.md", by_hand, fresh) == ([], 1)
    (root / ARTIFACT).unlink()
    gone = report.build(root)
    problems, _ = freshness.document_problems("docs/cards/hand.md", by_hand, gone)
    assert problems == ["docs/cards/hand.md:1: claim example.rate does not re-derive (see above)"]


def test_run_and_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = built(tmp_path)
    put(root, "docs/templates/cards/x.md.in", "Card {{claim:example.tasks}}.\n")
    out, rc = freshness.run(root)
    assert rc == 1
    assert out[-3:] == [
        "freshness: docs/REPORT.md OK (7 live claims)",
        "freshness: docs/cards/x.md missing",
        "freshness: FAIL",
    ]
    report.run(root)
    assert freshness.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "freshness: README.md OK (7 live claims)",
        "freshness: docs/REPORT.md OK (7 live claims)",
        "freshness: docs/cards/x.md OK (1 live claims)",
    ]
    empty = tmp_path / "empty"
    empty.mkdir()
    out, rc = freshness.run(empty)
    assert rc == 1
    assert out == [
        "freshness: docs/claims/spec.json missing",
        "freshness: docs/claims/registry.json missing (run make report)",
        "freshness: README.md missing",
        "freshness: docs/REPORT.md missing",
        "freshness: FAIL",
    ]
