#!/usr/bin/env python3
"""Every number in the results documents traces to a banked artifact (`make claimcheck`).

Non-negotiable 1 and gate G10 of docs/BUILD_BRIEF.md. The documents are README.md,
docs/REPORT.md, docs/cards/*.md, and any other output path that docs/claims/spec.json
maps a template to. Every number token in them must be one of:

(a) a claim: immediately followed by ``<!--claim:KEY-->``, where the value of KEY in
    docs/claims/registry.json (written by ``make report`` from the artifact) equals the
    token text exactly;
(b) in an excluded context: a URL or Markdown link target, an inline code span, a fenced
    code block whose info string is bash, sh, shell, console, toml, json, yaml, or text,
    a hex string of 7 or more characters, an ISO date, a year 1900 to 2099, a version
    (v1.0, Python 3.12, 1.2.3), an identifier with letters attached (G7, E0, x86_64,
    SHA-256), an ordered-list marker, a numbered heading, an arXiv id, a footnote label,
    or a reference such as "section 8", "rule 15", or "steps 1 to 3";
(c) listed in docs/claims/allowlist.tsv (number, context regex that must match the line,
    reason) as a design parameter that is not a result.

A line that ends with ``<!-- claimcheck:ignore-line REASON -->`` is exempt from the number
check; the reason is required. Claim markers are checked on every line. The rules are
documented with examples in docs/claims/README.md.

Output: one line per document, ``claimcheck: <file> OK (<n> claims, <m> allowlisted)``, or
its problems with line numbers; then ``claimcheck: FAIL`` and exit status 1 if anything
failed. A missing README.md or docs/REPORT.md fails. ``--verbose`` also prints how every
number token was classified.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY = "docs/claims/registry.json"
ALLOWLIST = "docs/claims/allowlist.tsv"
SPEC = "docs/claims/spec.json"
REQUIRED_DOCS = ("README.md", "docs/REPORT.md")
CARDS_DIR = "docs/cards"

KEY_RE = re.compile(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*")
_CORE = r"(?:[0-9]{1,3}(?:,[0-9]{3})+(?![0-9])|[0-9]+)(?:\.[0-9]+)*|\.[0-9]+"
NUMBER_PATTERN = rf"[-+]?(?:{_CORE})(?:[eE][-+]?[0-9]+)?%?"
NUMBER_FULL = re.compile(NUMBER_PATTERN)
# A token is never attached to a letter, digit, or dot before it, to a letter or digit
# through an underscore (x86_64), or to a letter through a hyphen or at sign (SHA-256,
# pass@1); such numbers belong to identifiers and are not tokens at all.
TOKEN_RE = re.compile(rf"(?<![^\W_])(?<!\.)(?<![^\W_]_)(?<![^\W\d_][-@]){NUMBER_PATTERN}")

EXCLUDED_FENCES = frozenset({"bash", "sh", "shell", "console", "toml", "json", "yaml", "text"})
FENCE_OPEN_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
FENCE_CLOSE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})[ \t]*$")
HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]|$)")
HEADING_NUM_RE = re.compile(
    r"^ {0,3}#{1,6}[ \t]+(?P<num>[1-9][0-9]*(?:\.[0-9]+)*)(?P<punct>[.)]?)(?=[ \t]|$)"
)
ORDERED_RE = re.compile(r"^\s*(?:>\s*)*(?P<num>[0-9]{1,9})[.)](?=\s|$)")
BULLET_RE = re.compile(r"^\s*(?:>\s*)*[-*+](?=\s)")

COMMENT_RE = re.compile(r"<!--(.*?)-->")
URL_RE = re.compile(r"https?://[^\s)>\]\"'`]+")  # the same pattern as tools/ship_check.py
LINK_DEST_RE = re.compile(r"\]\((?:[^()\s]|\([^()\s]*\))*(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
REF_LABEL_RE = re.compile(r"\]\[[^\]]*\]")
FOOTNOTE_RE = re.compile(r"\[\^[^\]\s]+\]:?")
REF_DEF_RE = re.compile(r"^ {0,3}\[(?!\^)[^\]]+\]:\s*\S")

HEX_RE = re.compile(r"(?<![\w.])(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{7,}(?!\w)")
DATE_RE = re.compile(
    r"(?<![\w.])(?:19|20)[0-9]{2}-(?:0[1-9]|1[0-2])"
    r"(?:-(?:0[1-9]|[12][0-9]|3[01])"
    r"(?:[T ](?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9](?:\.[0-9]+)?)?"
    r"(?:Z|[+-](?:[01][0-9]|2[0-3]):?[0-5][0-9])?)?)?(?!\w)"
)
ARXIV_RE = re.compile(
    r"(?<![\w.])(?:0[7-9]|[1-9][0-9])(?:0[1-9]|1[0-2])\.[0-9]{4,5}(?:v[0-9]+)?(?!\w|\.[0-9])"
)
EN_DASH, SECTION_SIGN = chr(0x2013), chr(0xA7)  # code points keep this file ASCII
_SEP = r"(?:\s*,\s*(?:and\s+|or\s+)?|\s+(?:and|or|to|through)\s+|\s*[-" + EN_DASH + r"]\s*)"
_REF_NUM = r"[1-9][0-9]*(?:\.[0-9]+)*"
_REF_ONE = (
    r"section|subsection|rule|step|non-negotiable|gate|appendix|chapter|figure|fig\.|"
    r"table|equation|eq\.|line|item|" + SECTION_SIGN
)
_REF_MANY = (
    r"sections|subsections|rules|steps|non-negotiables|gates|appendices|chapters|figures|"
    r"figs\.|tables|equations|eqs\.|lines|items|" + SECTION_SIGN * 2
)
REF_RE = re.compile(
    rf"(?i)(?<![\w-])(?:(?:{_REF_MANY})\s*{_REF_NUM}(?:{_SEP}{_REF_NUM})*"
    rf"|(?:{_REF_ONE})\s*{_REF_NUM})(?!\w)"
)
_VERSIONED = (
    r"python|cpython|pypy|uv|ruff|mypy|pytest-cov|pytest|hatchling|docker|bubblewrap|bwrap|"
    r"ubuntu|debian|linux|macos|node\.js|git|versions|version|releases|release"
)
VERSION_RE = re.compile(
    rf"(?i)(?<![\w-])(?:{_VERSIONED})\s+v?[0-9]+(?:\.[0-9]+)*"
    rf"(?:{_SEP}v?[0-9]+(?:\.[0-9]+)+)*(?!\w)"
)
YEAR_RE = re.compile(r"(?:19|20)[0-9]{2}")
DOTTED_RE = re.compile(r"[0-9]+(?:\.[0-9]+){2,}")
DIRECTIVE = "claimcheck:ignore-line"


@dataclass(frozen=True)
class AllowEntry:
    """One allowlisted design parameter."""

    number: str
    context: re.Pattern[str]
    reason: str
    line: int


@dataclass(frozen=True)
class Line:
    """A document line and how to read it."""

    number: int
    text: str
    mode: str  # "prose", "code" (a fenced block that is checked), or "skip"
    list_ok: bool  # an ordered-list marker at the start is a real list marker


@dataclass(frozen=True)
class Token:
    """A number token on a line (offsets into the line)."""

    text: str
    start: int
    end: int


@dataclass(frozen=True)
class Marker:
    """A claim marker ``<!--claim:KEY-->`` on a line."""

    key: str
    start: int
    end: int


@dataclass
class Scan:
    """What one line contains, after code spans, URLs, and markers are masked."""

    masked: str
    tokens: list[Token]
    markers: list[Marker]
    spans: list[tuple[int, int, str]]
    directive: str | None
    problems: list[str]
    list_marker: int | None
    heading_number: int | None


@dataclass(frozen=True)
class Occurrence:
    """A claim marker in a document and the number shown before it (None if none)."""

    line: int
    key: str
    shown: str | None


@dataclass
class FileReport:
    """Result of checking one document."""

    rel: str
    claims: int = 0
    allowlisted: int = 0
    ignored_lines: int = 0
    problems: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


def code_spans(line: str) -> list[tuple[int, int]]:
    """Inline code spans on one line: a run of n backticks up to the next run of exactly n."""
    spans: list[tuple[int, int]] = []
    i, n = 0, len(line)
    while i < n:
        if line[i] != "`":
            i += 1
            continue
        j = i
        while j < n and line[j] == "`":
            j += 1
        run, k, close = j - i, j, -1
        while k < n:
            if line[k] != "`":
                k += 1
                continue
            m = k
            while m < n and line[m] == "`":
                m += 1
            if m - k == run:
                close = k
                break
            k = m
        if close < 0:
            i = j
            continue
        spans.append((i, close + run))
        i = close + run
    return spans


def iter_lines(text: str) -> Iterator[Line]:
    """Document lines with their reading mode (fenced code and ordered lists tracked)."""
    fence: tuple[str, int] | None = None
    fence_mode = "skip"
    in_list = False
    boundary = True  # no paragraph is open, so any number may start an ordered list
    prev_blank = True
    for number, line in enumerate(text.splitlines(), start=1):
        if fence is not None:
            close = FENCE_CLOSE_RE.match(line)
            if (
                close
                and close.group("fence")[0] == fence[0]
                and len(close.group("fence")) >= fence[1]
            ):
                fence = None
                in_list, boundary, prev_blank = False, True, False
                yield Line(number, line, "skip", False)
            else:
                yield Line(number, line, fence_mode, False)
            continue
        opened = FENCE_OPEN_RE.match(line)
        if opened and not (opened.group("fence")[0] == "`" and "`" in opened.group("info")):
            fence = (opened.group("fence")[0], len(opened.group("fence")))
            words = opened.group("info").split()
            fence_mode = "skip" if words and words[0].lower() in EXCLUDED_FENCES else "code"
            yield Line(number, line, "skip", False)
            continue
        if not line.strip():
            boundary, prev_blank = True, True
            yield Line(number, line, "prose", False)
            continue
        if HEADING_RE.match(line):
            in_list, boundary, prev_blank = False, True, False
            yield Line(number, line, "prose", False)
            continue
        ordered = ORDERED_RE.match(line)
        if ordered:
            ok = in_list or boundary or int(ordered.group("num")) == 1
            in_list = in_list or ok
            boundary, prev_blank = False, False
            yield Line(number, line, "prose", ok)
            continue
        if BULLET_RE.match(line):
            in_list = True
        elif prev_blank and not line[0].isspace():
            in_list = False
        boundary, prev_blank = False, False
        yield Line(number, line, "prose", False)


def scan_line(text: str, mode: str = "prose", list_ok: bool = False) -> Scan:
    """Mask code spans, markers, and URLs on a line; find tokens and excluded spans."""
    chars = list(text)
    prose = mode == "prose"

    def mask(a: int, b: int) -> None:
        chars[a:b] = " " * (b - a)

    if prose:
        for a, b in code_spans(text):
            mask(a, b)
    markers: list[Marker] = []
    problems: list[str] = []
    directive: str | None = None
    for m in COMMENT_RE.finditer("".join(chars)):
        body, stripped = m.group(1), m.group(1).strip()
        if body.startswith("claim:"):
            key = body[len("claim:") :]
            if KEY_RE.fullmatch(key):
                markers.append(Marker(key, m.start(), m.end()))
                mask(m.start(), m.end())
            else:
                problems.append(f"malformed claim marker {m.group(0)!r} (key {key!r})")
        elif re.match(r"claim\b", stripped, re.I):
            problems.append(f"malformed claim marker {m.group(0)!r} (write <!--claim:KEY-->)")
        elif stripped.lower().startswith("claimcheck:"):
            name, *rest = stripped.split(None, 1)
            reason = rest[0] if rest else ""
            if name != DIRECTIVE:
                problems.append(f"unknown claimcheck directive {name!r}")
            elif text[m.end() :].strip():
                problems.append(f"{DIRECTIVE} must end the line")
            elif not reason.strip():
                problems.append(f"{DIRECTIVE} needs a reason")
            else:
                directive = reason.strip()
            mask(m.start(), m.end())
    if prose and REF_DEF_RE.match("".join(chars)):
        mask(0, len(chars))  # a link reference definition is not rendered
    patterns = [URL_RE, LINK_DEST_RE, REF_LABEL_RE, FOOTNOTE_RE] if prose else [URL_RE]
    for pattern in patterns:
        for m in pattern.finditer("".join(chars)):
            mask(m.start(), m.end())
    masked = "".join(chars)
    tokens = [Token(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(masked)]
    spans = [
        (m.start(), m.end(), why)
        for pattern, why in (
            (HEX_RE, "hex string"),
            (DATE_RE, "date"),
            (ARXIV_RE, "arXiv id"),
            (REF_RE, "section or rule reference"),
            (VERSION_RE, "version"),
        )
        for m in pattern.finditer(masked)
    ]
    list_marker = heading_number = None
    ordered = ORDERED_RE.match(masked) if list_ok else None
    if ordered:
        list_marker = ordered.start("num")
    heading = HEADING_NUM_RE.match(masked) if prose else None
    if heading and (heading.group("punct") or "." in heading.group("num")):
        heading_number = heading.start("num")
    return Scan(masked, tokens, markers, spans, directive, problems, list_marker, heading_number)


def excluded(token: Token, scan: Scan) -> str | None:
    """Why ``token`` is not a result number, or None if it must be backed."""
    for a, b, why in scan.spans:
        if token.start < b and a < token.end:
            return why
    if token.start == scan.list_marker:
        return "ordered-list marker"
    if token.start == scan.heading_number:
        return "heading number"
    if DOTTED_RE.fullmatch(token.text):
        return "version"
    if YEAR_RE.fullmatch(token.text):
        return "year"
    return None


def allowlisted(token: str, line: str, entries: Sequence[AllowEntry]) -> AllowEntry | None:
    """The allowlist entry that covers ``token`` on ``line``, if any."""
    for entry in entries:
        if entry.number == token and entry.context.search(line):
            return entry
    return None


def load_allowlist(path: Path, rel: str = ALLOWLIST) -> tuple[list[AllowEntry], list[str]]:
    """Allowlist entries and problems. Columns: number, context regex, reason (tab separated).

    Blank lines, lines starting with ``#``, and the header ``number<TAB>context<TAB>reason``
    are skipped. A missing file is an empty allowlist.
    """
    if not path.exists():
        return [], []
    entries: list[AllowEntry] = []
    problems: list[str] = []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        cols = raw.split("\t")
        if [c.strip().lower() for c in cols] == ["number", "context", "reason"]:
            continue
        where = f"{rel}:{i}"
        if len(cols) != 3:
            problems.append(f"{where}: needs 3 tab-separated columns (number, context, reason)")
            continue
        number, context, reason = (c.strip() for c in cols)
        if not NUMBER_FULL.fullmatch(number):
            problems.append(f"{where}: {number!r} is not a number token")
            continue
        if not context:
            problems.append(f"{where}: context regex missing")
            continue
        try:
            pattern = re.compile(context)
        except re.error as exc:
            problems.append(f"{where}: bad context regex: {exc}")
            continue
        if not reason:
            problems.append(f"{where}: reason missing for {number}")
            continue
        entries.append(AllowEntry(number, pattern, reason, i))
    return entries, problems


def load_registry(path: Path, rel: str = REGISTRY) -> tuple[dict[str, str], list[str]]:
    """Claim values from the registry written by ``make report``, and problems."""
    if not path.exists():
        return {}, [f"{rel} missing (run make report)"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return {}, [f"{rel} is not valid JSON: {exc}"]
    if not isinstance(data, dict):
        return {}, [f"{rel} must be a JSON object"]
    values: dict[str, str] = {}
    problems: list[str] = []
    for key, entry in sorted(data.items()):
        if isinstance(entry, dict) and isinstance(entry.get("value"), str):
            values[key] = entry["value"]
        else:
            problems.append(f"{rel}: claim {key} has no string value")
    return values, problems


def template_outputs(root: Path) -> list[str]:
    """Existing documents that docs/claims/spec.json maps a template to (best effort)."""
    try:
        spec = json.loads((root / SPEC).read_text(encoding="utf-8"))
        targets = [v for v in dict(spec.get("templates") or {}).values() if isinstance(v, str)]
    except (OSError, ValueError, TypeError, AttributeError):
        return []
    found: set[str] = set()
    for target in targets:
        if ".." in target.split("/") or target.startswith("/"):
            continue
        paths = root.glob(target) if "*" in target else [root / target]
        found.update(p.relative_to(root).as_posix() for p in paths if p.is_file())
    return sorted(found)


def documents(root: Path) -> list[str]:
    """README.md, docs/REPORT.md, docs/cards/*.md, then other template outputs."""
    cards_dir = root / CARDS_DIR
    cards = sorted(p.relative_to(root).as_posix() for p in cards_dir.glob("*.md"))
    docs = [*REQUIRED_DOCS, *cards]
    return docs + [d for d in template_outputs(root) if d not in docs]


def check_text(
    text: str,
    rel: str,
    registry: dict[str, str],
    allowlist: Sequence[AllowEntry],
    verbose: bool = False,
) -> FileReport:
    """Check every number token and claim marker in a document."""
    report = FileReport(rel)
    for line in iter_lines(text):
        if line.mode == "skip":
            continue
        scan = scan_line(line.text, line.mode, line.list_ok)
        where = f"{rel}:{line.number}"
        report.problems += [f"{where}: {p}" for p in scan.problems]
        by_end = {t.end: t for t in scan.tokens}
        backed: set[int] = set()
        for marker in scan.markers:
            token = by_end.get(marker.start)
            if token is None:
                report.problems.append(
                    f"{where}: claim marker for {marker.key} does not follow a number"
                )
                continue
            backed.add(token.start)
            want = registry.get(marker.key)
            if want is None:
                report.problems.append(f"{where}: unknown claim {marker.key} (not in {REGISTRY})")
            elif token.text != want:
                report.problems.append(
                    f"{where}: {token.text} is marked as claim {marker.key}, "
                    f"whose registry value is {want}"
                )
            else:
                report.claims += 1
                if verbose:
                    report.details.append(f"{where}: {token.text} claim {marker.key}")
        if scan.directive is not None:
            report.ignored_lines += 1
            if verbose:
                report.details.append(f"{where}: line ignored ({scan.directive})")
            continue
        for token in scan.tokens:
            if token.start in backed:
                continue
            why = excluded(token, scan)
            if why:
                if verbose:
                    report.details.append(f"{where}: {token.text} excluded ({why})")
                continue
            entry = allowlisted(token.text, line.text, allowlist)
            if entry is not None:
                report.allowlisted += 1
                if verbose:
                    report.details.append(
                        f"{where}: {token.text} allowlisted ({ALLOWLIST}:{entry.line})"
                    )
                continue
            report.problems.append(f"{where}: unbacked number {token.text}")
    return report


def claim_occurrences(text: str) -> tuple[list[Occurrence], list[str]]:
    """Every claim marker in a document with the number before it; malformed markers."""
    found: list[Occurrence] = []
    problems: list[str] = []
    for line in iter_lines(text):
        if line.mode == "skip":
            continue
        scan = scan_line(line.text, line.mode, line.list_ok)
        by_end = {t.end: t for t in scan.tokens}
        for marker in scan.markers:
            token = by_end.get(marker.start)
            found.append(Occurrence(line.number, marker.key, token.text if token else None))
        problems += [f"{line.number}: {p}" for p in scan.problems if "claim marker" in p]
    return found, problems


def run(root: Path, verbose: bool = False) -> tuple[list[str], int]:
    """Check every document under ``root``; output lines and exit status."""
    out: list[str] = []
    registry, reg_problems = load_registry(root / REGISTRY)
    allow, allow_problems = load_allowlist(root / ALLOWLIST)
    failed = bool(reg_problems or allow_problems)
    out += [f"claimcheck: {p}" for p in reg_problems + allow_problems]
    for rel in documents(root):
        path = root / rel
        if not path.is_file():
            out.append(f"claimcheck: {rel} missing")
            failed = True
            continue
        report = check_text(path.read_text(encoding="utf-8"), rel, registry, allow, verbose)
        out += [f"claimcheck: {d}" for d in report.details]
        if report.problems:
            failed = True
            out += [f"claimcheck: {p}" for p in report.problems]
            out.append(f"claimcheck: {rel} FAIL ({len(report.problems)} problems)")
        else:
            out.append(
                f"claimcheck: {rel} OK ({report.claims} claims, {report.allowlisted} allowlisted)"
            )
    if failed:
        out.append("claimcheck: FAIL")
    return out, 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="every result number traces to a banked artifact")
    ap.add_argument("--root", type=Path, default=REPO, help="repository root (default: this one)")
    ap.add_argument("--verbose", action="store_true", help="print how every token was classified")
    args = ap.parse_args(argv)
    out, rc = run(args.root.resolve(), args.verbose)
    print("\n".join(out))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
