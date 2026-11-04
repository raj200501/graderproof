#!/usr/bin/env python3
"""Every number in the results documents traces to a banked artifact (`make claimcheck`).

Non-negotiable 1 and gate G10 of docs/BUILD_BRIEF.md. The documents are README.md,
docs/REPORT.md, docs/cards/*.md, and any other output path that docs/claims/spec.json
maps a template to. Every number token in them must be one of:

(a) a claim: immediately followed by ``<!--claim:KEY-->``, where the value of KEY in
    docs/claims/registry.json (written by ``make report`` from the artifact) equals the
    token text exactly;
(b) in an excluded context: a URL or Markdown link target, a reference link label or
    definition, a footnote label, an HTML character reference, an inline code span, a
    fenced code block whose info string is bash, sh, shell, console, toml, json, yaml, or
    text, a hex string of 7 or more characters, an ISO date, a year 1900 to 2099, a
    version (v1.0, Python 3.12, 1.2.3), an identifier with letters attached (G7, E0,
    x86_64, SHA-256), an ordered-list marker, a numbered heading, an arXiv id, or a
    reference such as "section 8", "rule 15", or "steps 1 to 3";
(c) listed in docs/claims/allowlist.tsv (number, context regex, reason) as a design
    parameter that is not a result: a match of the regex on the same line must contain
    the number and reach beyond it.

A line that ends with ``<!-- claimcheck:ignore-line REASON -->`` is exempt from the number
check; the reason is required. Claim markers are checked on every line, and a fenced code
block that is never closed fails (it would hide the rest of the file). The rules are
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
from collections.abc import Sequence
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
_TITLE = r"(?:\"[^\"]*\"|'[^']*'|\([^()]*\))"
# An inline link or image target: only the destination is masked; a title stays checked.
LINK_DEST_RE = re.compile(
    rf"\]\((?P<dest><[^<>\n]*>|(?:[^()\s]|\([^()\s]*\))*)(?:\s+{_TITLE})?\s*\)"
)
REF_LABEL_RE = re.compile(r"\]\[[^\]]*\]")
SHORTCUT_RE = re.compile(r"\[(?P<label>[^\[\]]+)\](?:\[\])?(?![(\[:])")
FOOTNOTE_RE = re.compile(r"\[\^[^\]\s]+\]:?")
# A link reference definition (never rendered); a line that only looks like one is prose.
REF_DEF_RE = re.compile(
    r"^ {0,3}\[(?!\^)(?P<label>[^\[\]]+)\]:[ \t]*(?P<dest><[^<>\n]*>|\S+)"
    rf"(?:[ \t]+{_TITLE})?[ \t]*$"
)
ENTITY_RE = re.compile(r"&#(?:[0-9]{1,7}|[xX][0-9a-fA-F]{1,6});")

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


def classify_lines(text: str) -> tuple[list[Line], int | None]:
    """Document lines with their reading mode, and the line that opens a fence never closed.

    Fences follow CommonMark: a block closes with a run of the same character at least as
    long as the opening one. An ordered-list marker counts as one after a blank line or a
    heading, inside a list, or anywhere when it is 1 (only a list starting at 1 may
    interrupt a paragraph).
    """
    lines: list[Line] = []
    fence: tuple[str, int, int] | None = None  # character, length, opening line
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
                lines.append(Line(number, line, "skip", False))
            else:
                lines.append(Line(number, line, fence_mode, False))
            continue
        opened = FENCE_OPEN_RE.match(line)
        if opened and not (opened.group("fence")[0] == "`" and "`" in opened.group("info")):
            fence = (opened.group("fence")[0], len(opened.group("fence")), number)
            words = opened.group("info").split()
            fence_mode = "skip" if words and words[0].lower() in EXCLUDED_FENCES else "code"
            lines.append(Line(number, line, "skip", False))
            continue
        if not line.strip():
            boundary, prev_blank = True, True
            lines.append(Line(number, line, "prose", False))
            continue
        if HEADING_RE.match(line):
            in_list, boundary, prev_blank = False, True, False
            lines.append(Line(number, line, "prose", False))
            continue
        ordered = ORDERED_RE.match(line)
        if ordered:
            ok = in_list or boundary or int(ordered.group("num")) == 1
            in_list = in_list or ok
            boundary, prev_blank = False, False
            lines.append(Line(number, line, "prose", ok))
            continue
        if BULLET_RE.match(line):
            in_list = True
        elif prev_blank and not line[0].isspace():
            in_list = False
        boundary, prev_blank = False, False
        lines.append(Line(number, line, "prose", False))
    return lines, (fence[2] if fence is not None else None)


def normalize_label(label: str) -> str:
    """A link reference label as CommonMark compares them: case and inner spacing ignored."""
    return " ".join(label.split()).casefold()


def reference_labels(lines: Sequence[Line]) -> frozenset[str]:
    """Labels of the link reference definitions among ``lines`` (normalized)."""
    found = set()
    for line in lines:
        m = REF_DEF_RE.match(line.text) if line.mode == "prose" else None
        if m:
            found.add(normalize_label(m.group("label")))
    return frozenset(found)


def scan_line(
    text: str, mode: str = "prose", list_ok: bool = False, labels: frozenset[str] = frozenset()
) -> Scan:
    """Mask code spans, markers, URLs, and link syntax on a line; find tokens and excluded spans.

    ``labels`` are the document's link reference labels: a shortcut reference such as
    ``[3]`` is masked only when a definition ``[3]: URL`` exists.
    """
    chars = list(text)
    prose = mode == "prose"

    def mask(a: int, b: int) -> None:
        chars[a:b] = " " * (b - a)

    def current() -> str:
        return "".join(chars)

    if prose:
        for a, b in code_spans(text):
            mask(a, b)
    markers: list[Marker] = []
    problems: list[str] = []
    directive: str | None = None
    for m in COMMENT_RE.finditer(current()):
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
    definition = REF_DEF_RE.match(current()) if prose else None
    if definition:
        mask(0, definition.end("dest"))  # label and destination are never rendered
    for m in URL_RE.finditer(current()):
        mask(m.start(), m.end())
    if prose:
        for m in LINK_DEST_RE.finditer(current()):
            mask(m.start(), m.end("dest"))
        for m in SHORTCUT_RE.finditer(current()):
            if normalize_label(m.group("label")) in labels:
                mask(m.start(), m.end())
        for pattern in (REF_LABEL_RE, FOOTNOTE_RE, ENTITY_RE):
            for m in pattern.finditer(current()):
                mask(m.start(), m.end())
    masked = current()
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
    """Why ``token`` is not a result number, or None if it must be backed.

    An excluded span must contain the whole token: ``line 14`` is a reference, but the
    ``14,000`` in ``line 14,000`` is checked.
    """
    for a, b, why in scan.spans:
        if a <= token.start and token.end <= b:
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


def allowlisted(token: Token, line: str, entries: Sequence[AllowEntry]) -> AllowEntry | None:
    """The allowlist entry that covers ``token`` on ``line``, if any.

    The entry's number must equal the token text, and a match of its context regex on the
    line must contain the token and reach beyond it, so the regex names real context.
    """
    for entry in entries:
        if entry.number != token.text:
            continue
        for m in entry.context.finditer(line):
            inside = m.start() <= token.start and token.end <= m.end()
            if inside and m.end() - m.start() > len(token.text):
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
    lines, unclosed = classify_lines(text)
    labels = reference_labels(lines)
    for line in lines:
        if line.mode == "skip":
            continue
        scan = scan_line(line.text, line.mode, line.list_ok, labels)
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
            entry = allowlisted(token, line.text, allowlist)
            if entry is not None:
                report.allowlisted += 1
                if verbose:
                    report.details.append(
                        f"{where}: {token.text} allowlisted ({ALLOWLIST}:{entry.line})"
                    )
                continue
            report.problems.append(f"{where}: unbacked number {token.text}")
    if unclosed is not None:
        report.problems.append(
            f"{rel}:{unclosed}: this fenced code block is never closed, "
            "so the rest of the file would be code"
        )
    return report


def claim_occurrences(text: str) -> tuple[list[Occurrence], list[str]]:
    """Every claim marker in a document with the number before it; malformed markers."""
    found: list[Occurrence] = []
    problems: list[str] = []
    lines, _ = classify_lines(text)
    labels = reference_labels(lines)
    for line in lines:
        if line.mode == "skip":
            continue
        scan = scan_line(line.text, line.mode, line.list_ok, labels)
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
        if report.ignored_lines:
            n = report.ignored_lines
            noun = "line" if n == 1 else "lines"
            out.append(f"claimcheck: {rel}: {n} {noun} exempt by {DIRECTIVE}")
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
    """Command line: check the repository (or ``--root``) and print the result."""
    ap = argparse.ArgumentParser(description="every result number traces to a banked artifact")
    ap.add_argument("--root", type=Path, default=REPO, help="repository root (default: this one)")
    ap.add_argument("--verbose", action="store_true", help="print how every token was classified")
    args = ap.parse_args(argv)
    out, rc = run(args.root.resolve(), args.verbose)
    print("\n".join(out))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
