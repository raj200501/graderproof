#!/usr/bin/env python3
"""Every live number still matches its artifact (`make freshness`).

Gate G10 and non-negotiable 1 of docs/BUILD_BRIEF.md. Writing nothing, it rebuilds in memory
what ``make report`` would write from docs/claims/spec.json, the templates, and the
artifacts (tools/report.py), then checks:

1. every declared claim re-derives from its artifact now (a missing artifact, or a path or
   format that no longer applies, fails);
2. docs/claims/registry.json holds exactly the declared claims, each with the value,
   artifact, and path re-derived now, and each ``artifact_sha256`` equals the SHA-256 of the
   artifact file now (an artifact changed after the registry was built fails even when the
   value did not change);
3. every ``<!--claim:KEY-->`` in README.md, docs/REPORT.md, docs/cards/*.md, and the other
   template outputs follows the value re-derived now, and every KEY is declared;
4. each document that has a template is that template's current rendering, each declared
   figure under docs/figures/ is what the artifacts give now, and
   artifacts/figures/manifest.json lists exactly those figures with their hashes.

Output: the problems, then one line per document, ``freshness: <file> OK (<n> live claims)``
or ``freshness: <file> FAIL (...)``, then ``freshness: FAIL`` and exit status 1 if anything
is stale, unknown, or missing. A missing README.md or docs/REPORT.md fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import claimcheck
import report

REPO = claimcheck.REPO
SPEC = claimcheck.SPEC
REGISTRY = claimcheck.REGISTRY
MANIFEST = report.MANIFEST


def registry_problems(root: Path, built: report.Build) -> list[str]:
    """Differences between docs/claims/registry.json and the claims re-derived now."""
    path = root / REGISTRY
    if not path.is_file():
        return [f"{REGISTRY} missing (run make report)"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"{REGISTRY} is not valid JSON: {exc}"]
    if not isinstance(data, dict):
        return [f"{REGISTRY} must be a JSON object"]
    problems: list[str] = []
    for key in sorted(set(data) | set(built.spec.claims)):
        if key not in built.spec.claims:
            problems.append(f"{REGISTRY} has claim {key}, which {SPEC} does not declare")
            continue
        claim = built.claims.get(key)
        if claim is None:
            continue  # the reason it does not re-derive is already listed
        have = data.get(key)
        if not isinstance(have, dict):
            problems.append(f"claim {key} is not in {REGISTRY} (run make report)")
            continue
        if (have.get("artifact"), have.get("path")) != (claim.artifact, claim.path):
            problems.append(
                f"claim {key}: {REGISTRY} was built from {have.get('artifact')} "
                f"{have.get('path')!r}, but {SPEC} now says {claim.artifact} {claim.path!r}"
            )
        if have.get("artifact_sha256") != claim.artifact_sha256:
            problems.append(
                f"claim {key}: {claim.artifact} changed after {REGISTRY} was built "
                "(its sha256 differs; run make report)"
            )
        if have.get("value") != claim.value:
            problems.append(
                f"claim {key}: {REGISTRY} has {have.get('value')}, "
                f"but {claim.artifact} now gives {claim.value}"
            )
    return problems


def figure_problems(root: Path, built: report.Build) -> list[str]:
    """Figures and the figure manifest that differ from what the artifacts give now."""
    problems: list[str] = []
    for rel, svg in sorted(built.figures.items()):
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel} missing (run make report)")
        elif path.read_bytes() != svg.encode("utf-8"):
            problems.append(f"{rel} is stale: it is not what the artifacts give now")
    if len(built.figures) != len(built.spec.figures):
        return problems  # a figure could not be drawn; that problem is already listed
    path = root / MANIFEST
    if path.is_file():
        try:
            listed = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            listed = None
        if listed != built.manifest:
            problems.append(f"{MANIFEST} does not list exactly the current figures and hashes")
    elif built.manifest:
        problems.append(f"{MANIFEST} missing (run make report)")
    return problems


def document_problems(rel: str, text: str, built: report.Build) -> tuple[list[str], int]:
    """Stale or unknown claims in one document, and its number of live claims."""
    found, malformed = claimcheck.claim_occurrences(text)
    problems = [f"{rel}:{p}" for p in malformed]
    for occ in found:
        where = f"{rel}:{occ.line}"
        claim = built.claims.get(occ.key)
        if occ.key not in built.spec.claims:
            problems.append(f"{where}: unknown claim {occ.key} (not declared in {SPEC})")
        elif claim is None:
            problems.append(f"{where}: claim {occ.key} does not re-derive (see above)")
        elif occ.shown is None:
            problems.append(f"{where}: claim marker for {occ.key} does not follow a number")
        elif occ.shown != claim.value:
            problems.append(
                f"{where}: claim {occ.key} shows {occ.shown}, "
                f"but {claim.artifact} now gives {claim.value}"
            )
    rendered = built.docs.get(rel)
    if rendered is not None and text != rendered.text:
        problems.append(f"{rel} is not the current rendering of {rendered.template}")
    return problems, len(found)


def run(root: Path) -> tuple[list[str], int]:
    """Check everything; output lines and exit status."""
    built = report.build(root)
    problems = [*built.problems, *registry_problems(root, built), *figure_problems(root, built)]
    out = [f"freshness: {p}" for p in problems]
    failed = bool(problems)
    docs = claimcheck.documents(root)
    docs += [d for d in sorted(built.docs) if d not in docs]
    for rel in docs:
        path = root / rel
        if not path.is_file():
            out.append(f"freshness: {rel} missing")
            failed = True
            continue
        found, live = document_problems(rel, path.read_text(encoding="utf-8"), built)
        if found:
            failed = True
            out += [f"freshness: {p}" for p in found]
            out.append(f"freshness: {rel} FAIL ({len(found)} stale or unknown; run make report)")
        else:
            out.append(f"freshness: {rel} OK ({live} live claims)")
    if failed:
        out.append("freshness: FAIL")
    return out, 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="re-derive every live number from its artifact")
    ap.add_argument("--root", type=Path, default=REPO, help="repository root (default: this one)")
    args = ap.parse_args(argv)
    out, rc = run(args.root.resolve())
    print("\n".join(out))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
