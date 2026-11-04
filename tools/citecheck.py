#!/usr/bin/env python3
"""Every external reference in the shipped documents was opened and verified (`make citecheck`).

Gate G13 and non-negotiable 11 of docs/BUILD_BRIEF.md. Offline: it never opens a URL. It
reads artifacts/citecheck.json, which the citation-checker subagent writes
(.claude/agents/citation-checker.md), and checks:

1. the file matches that schema: ``schema`` is ``graderproof.citecheck/1``; every entry has a
   unique ``key``; ``claimed`` (``title``, ``authors``, ``year``, ``url``) and ``observed``
   (``title``, ``authors``, ``year``) objects; ``final_url``; ``page_title``; ``retrieved_utc``
   as ``YYYY-MM-DDTHH:MM:SSZ``; ``content_sha256`` as 64 lowercase hex digits, or null with
   non-empty ``notes``; ``status`` one of verified, mismatch, unreachable; and ``notes``. A
   verified entry needs a ``page_title`` and a ``final_url``. Other fields are ignored.
2. every external http(s) URL in README.md, docs/REPORT.md, and docs/cards/*.md (found
   exactly as tools/ship_check.py finds them; this repository's own
   github.com/raj200501/graderproof URLs are skipped) has an entry with status ``verified``,
   a ``page_title``, and a ``claimed.url`` or ``final_url`` equal to it, ignoring a trailing
   slash.

Output: ``citecheck: <n> references verified in README.md and docs/REPORT.md``, where n counts
the distinct URLs of those two documents exactly as tools/ship_check.py does, preceded by a
line for the cards when there are any; or the unverified references and schema problems, then
``citecheck: FAIL`` and exit status 1. A missing README.md or docs/REPORT.md fails.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
CITECHECK = "artifacts/citecheck.json"
SCHEMA = "graderproof.citecheck/1"
REQUIRED_DOCS = ("README.md", "docs/REPORT.md")
STATUSES = ("verified", "mismatch", "unreachable")
FIELDS = (
    "key",
    "claimed",
    "observed",
    "final_url",
    "page_title",
    "retrieved_utc",
    "content_sha256",
    "status",
    "notes",
)
URL_RE = re.compile(r"https?://[^\s)>\]\"'`]+")  # the same pattern as tools/ship_check.py
OWN_RE = re.compile(r"https?://(?:www\.)?github\.com/raj200501/graderproof(?:[/#?.]|$)")
HTTP_RE = re.compile(r"https?://\S+")
UTC_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
HEX64_RE = re.compile(r"[0-9a-f]{64}")


def is_own(url: str) -> bool:
    """A URL of this repository (never a reference that needs checking)."""
    return OWN_RE.match(url) is not None


def cited_urls(text: str) -> list[str]:
    """External URLs in a document, trailing ``.,;`` removed, sorted and unique."""
    return sorted({u.rstrip(".,;") for u in URL_RE.findall(text) if not is_own(u)})


def first_location(rel: str, text: str, url: str) -> str:
    """``file:line`` of the first line that cites ``url``."""
    for i, line in enumerate(text.splitlines(), start=1):
        if url in line:
            return f"{rel}:{i}"
    return rel


def optional_text(value: Any) -> bool:
    """A string or null."""
    return value is None or isinstance(value, str)


def optional_year(value: Any) -> bool:
    """An integer year or null."""
    return value is None or (isinstance(value, int) and not isinstance(value, bool))


def utc_ok(value: Any) -> bool:
    """An ISO 8601 UTC timestamp such as 2026-10-23T01:58:11Z."""
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        return False
    try:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def entry_problems(entry: Any, where: str) -> list[str]:
    """Schema problems of one entry."""
    if not isinstance(entry, dict):
        return [f"{where} is not an object"]
    missing = [f for f in FIELDS if f not in entry]
    if missing:
        return [f"{where}: missing {', '.join(missing)}"]
    problems: list[str] = []
    status = entry["status"]
    if status not in STATUSES:
        problems.append(f"{where}: status must be one of {', '.join(STATUSES)}")
    if not utc_ok(entry["retrieved_utc"]):
        problems.append(f"{where}: retrieved_utc must be YYYY-MM-DDTHH:MM:SSZ")
    notes = entry["notes"]
    if not isinstance(notes, str):
        problems.append(f"{where}: notes must be a string")
    sha = entry["content_sha256"]
    if sha is None:
        if not (isinstance(notes, str) and notes.strip()):
            problems.append(f"{where}: content_sha256 is null, so notes must say why")
    elif not (isinstance(sha, str) and HEX64_RE.fullmatch(sha)):
        problems.append(f"{where}: content_sha256 must be 64 lowercase hex digits or null")
    claimed, observed = entry["claimed"], entry["observed"]
    if not isinstance(claimed, dict) or not isinstance(claimed.get("url"), str):
        problems.append(f"{where}: claimed must be an object with a url")
    elif not HTTP_RE.fullmatch(claimed["url"]):
        problems.append(f"{where}: claimed.url must be an http(s) URL")
    for name, obj in (("claimed", claimed), ("observed", observed)):
        if not isinstance(obj, dict):
            if name == "observed":
                problems.append(f"{where}: observed must be an object")
            continue
        for part in ("title", "authors", "year"):
            if part not in obj:
                problems.append(f"{where}: {name}.{part} missing")
            elif not (optional_year if part == "year" else optional_text)(obj[part]):
                kind = "an integer" if part == "year" else "a string"
                problems.append(f"{where}: {name}.{part} must be {kind} or null")
    final_url, title = entry["final_url"], entry["page_title"]
    if final_url is not None and not (isinstance(final_url, str) and HTTP_RE.fullmatch(final_url)):
        problems.append(f"{where}: final_url must be an http(s) URL or null")
    if not optional_text(title):
        problems.append(f"{where}: page_title must be a string or null")
    if status == "verified":
        if not (isinstance(title, str) and title.strip()):
            problems.append(f"{where}: a verified entry needs a page_title")
        if not isinstance(final_url, str):
            problems.append(f"{where}: a verified entry needs a final_url")
    return problems


def schema_problems(data: Any) -> list[str]:
    """Every way ``data`` departs from the citation-checker schema."""
    if not isinstance(data, dict):
        return [f"{CITECHECK} must be a JSON object"]
    problems: list[str] = []
    if data.get("schema") != SCHEMA:
        problems.append(f"{CITECHECK}: schema must be {SCHEMA!r}")
    entries = data.get("entries")
    if not isinstance(entries, list):
        return [*problems, f"{CITECHECK}: entries must be a list"]
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        key = entry.get("key") if isinstance(entry, dict) else None
        where = f"{CITECHECK} entry {key if isinstance(key, str) and key else i}"
        if isinstance(entry, dict) and not (isinstance(key, str) and key.strip()):
            problems.append(f"{where}: key must be a non-empty string")
        elif isinstance(key, str):
            if key in seen:
                problems.append(f"{where}: duplicate key")
            seen.add(key)
        problems += entry_problems(entry, where)
    return problems


def claimed_url(entry: dict[str, Any]) -> Any:
    """``claimed.url`` of an entry, or None."""
    claimed = entry.get("claimed")
    return claimed.get("url") if isinstance(claimed, dict) else None


def verified_urls(entries: Sequence[Any]) -> set[str]:
    """URLs (trailing slash removed) that a verified entry with a page title covers."""
    out: set[str] = set()
    for e in entries:
        if not isinstance(e, dict) or e.get("status") != "verified":
            continue
        if not (e.get("page_title") and e.get("retrieved_utc")):
            continue
        for url in (claimed_url(e), e.get("final_url")):
            if isinstance(url, str) and url:
                out.add(url.rstrip("/"))
    return out


def status_of(entries: Sequence[Any], url: str) -> str:
    """How the citation file describes ``url`` when it is not verified."""
    for e in entries:
        if not isinstance(e, dict):
            continue
        urls = {str(u).rstrip("/") for u in (claimed_url(e), e.get("final_url")) if u}
        if url.rstrip("/") in urls:
            return f"entry {e.get('key')} is {e.get('status')}"
    return f"no entry in {CITECHECK}"


def run(root: Path) -> tuple[list[str], int]:
    """Check the citation file and every cited URL; output lines and exit status."""
    out: list[str] = []
    problems: list[str] = []
    cards = sorted(p.relative_to(root).as_posix() for p in (root / "docs" / "cards").glob("*.md"))
    texts: dict[str, str] = {}
    for rel in [*REQUIRED_DOCS, *cards]:
        path = root / rel
        if path.is_file():
            texts[rel] = path.read_text(encoding="utf-8")
        else:
            problems.append(f"{rel} missing")
    entries: list[Any] = []
    path = root / CITECHECK
    if not path.is_file():
        problems.append(f"{CITECHECK} missing")
    else:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            data = None
            problems.append(f"{CITECHECK} is not valid JSON: {exc}")
        if data is not None:
            problems += schema_problems(data)
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                entries = data["entries"]
    verified = verified_urls(entries)
    urls = sorted({u for text in texts.values() for u in cited_urls(text)})
    unverified = [u for u in urls if u.rstrip("/") not in verified]
    for url in unverified:
        where = next(first_location(r, t, url) for r, t in texts.items() if url in t)
        out.append(f"citecheck: unverified reference {url} ({where}; {status_of(entries, url)})")
    out += [f"citecheck: {p}" for p in problems]
    if problems or unverified:
        out.append("citecheck: FAIL")
        return out, 1
    main_urls = {u for rel in REQUIRED_DOCS for u in cited_urls(texts[rel])}
    if cards:
        card_urls = {u for rel in cards for u in cited_urls(texts[rel])}
        out.append(
            f"citecheck: {len(card_urls)} references verified in "
            f"{len(cards)} grader cards under docs/cards/"
        )
    out.append(f"citecheck: {len(main_urls)} references verified in README.md and docs/REPORT.md")
    return out, 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="every cited reference is verified (offline)")
    ap.add_argument("--root", type=Path, default=REPO, help="repository root (default: this one)")
    args = ap.parse_args(argv)
    out, rc = run(args.root.resolve())
    print("\n".join(out))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
