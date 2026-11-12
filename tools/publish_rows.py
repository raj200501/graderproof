#!/usr/bin/env python3
"""Publish the variant rows of a third-party audit with keyed ids (DECISIONS.md D44).

For a third-party audit (``summary.json`` with ``third_party: true``), the frozen code's
``variants.jsonl`` is the private original. Its ``variant_id`` is a content address of
the variant, so anyone who regenerates a deterministic variant from public data can
match it (D43). This tool writes the public copy:

- ``variant_id`` and ``witness_sha256`` become HMAC-SHA-256 values under a 256-bit key
  kept in ``private/keys/public_rows.key``, with one domain-separation prefix per field;
  a null stays null;
- ``operator`` is dropped (per-benchmark operator counts stay in ``summary.json``);
- rows are ordered by task, in the order of ``tasks.jsonl``, then by keyed id;
- every other field is copied unchanged.

``PUBLIC_ROWS.json`` beside the rows records the scheme, the SHA-256 of the private
original and of the public rows, and this tool's SHA-256. ``tools/ship_check.py`` (G14)
checks the public side on a fresh clone and calls :func:`verify` in the original
checkout, where the private original and the key live.

Usage, from the repository root::

    python tools/publish_rows.py --audit artifacts/audit/humaneval \\
        --original private/audit/humaneval-0003/variants.jsonl \\
        --key private/keys/public_rows.key [--new-key]
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "graderproof.public_rows/1"
SCHEME = "hmac-sha256/v1"
MANIFEST = "PUBLIC_ROWS.json"
KEY_PATH = "private/keys/public_rows.key"
KEY_BYTES = 32
KEYED_FIELDS = ("variant_id", "witness_sha256")
DROPPED_FIELDS = ("operator",)
ORDER = "tasks.jsonl order, then keyed variant_id"
DOMAINS = {
    "variant_id": b"graderproof/public_rows/v1/variant_id:",
    "witness_sha256": b"graderproof/public_rows/v1/witness_sha256:",
}


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def keyed(key: bytes, field: str, value: Any) -> str | None:
    """HMAC-SHA-256 of a non-empty string under ``key``, with ``field``'s domain.

    ``None`` stays ``None``; any other non-string or empty value raises ``ValueError``.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string or null, not {value!r}")
    return hmac.new(key, DOMAINS[field] + value.encode("utf-8"), hashlib.sha256).hexdigest()


def read_jsonl(data: bytes, where: str) -> list[dict[str, Any]]:
    """JSON objects, one per non-blank line; raises ``ValueError`` on anything else."""
    rows: list[dict[str, Any]] = []
    for n, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"{where}:{n} is not a JSON object")
        rows.append(obj)
    return rows


def task_order(tasks: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Position of each ``task_hash`` in tasks.jsonl; raises on a missing or repeated one."""
    order: dict[str, int] = {}
    for t in tasks:
        h = t.get("task_hash")
        if not isinstance(h, str) or not h:
            raise ValueError("a tasks.jsonl row lacks task_hash")
        if h in order:
            raise ValueError(f"tasks.jsonl lists task {h[:12]} twice")
        order[h] = len(order)
    return order


def publish(
    original: Sequence[Mapping[str, Any]], order: Mapping[str, int], key: bytes
) -> list[dict[str, Any]]:
    """Public rows for ``original``: keyed ids, no operator, ordered by task then keyed id."""
    if len(key) < KEY_BYTES:
        raise ValueError(f"the key must have at least {KEY_BYTES} bytes")
    out: list[dict[str, Any]] = []
    for r in original:
        h = r.get("task_hash")
        if not isinstance(h, str) or h not in order:
            raise ValueError(f"a variant of unknown task {str(h)[:12]}")
        if "variant_id" not in r:
            raise ValueError("a row lacks variant_id")
        pub = {k: v for k, v in r.items() if k not in DROPPED_FIELDS}
        for name in KEYED_FIELDS:
            if name in pub:
                pub[name] = keyed(key, name, pub[name])
        out.append(pub)
    out.sort(key=lambda p: (order[str(p["task_hash"])], str(p["variant_id"])))
    ids = [p["variant_id"] for p in out]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate variant_id among the rows")
    return out


def dump_jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    """Rows as JSON lines with sorted keys, the format of the audit's own tables."""
    return "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode("utf-8")


def manifest(original: bytes, public: bytes, original_rel: str, tool: bytes) -> dict[str, Any]:
    """The ``PUBLIC_ROWS.json`` record for one publication."""
    return {
        "schema": SCHEMA,
        "scheme": SCHEME,
        "keyed_fields": list(KEYED_FIELDS),
        "dropped_fields": list(DROPPED_FIELDS),
        "order": ORDER,
        "private_original": original_rel,
        "private_sha256": sha256_bytes(original),
        "rows_sha256": sha256_bytes(public),
        "tool": "tools/publish_rows.py",
        "tool_sha256": sha256_bytes(tool),
    }


def load_key(path: Path) -> bytes:
    """The key stored as hex in ``path``; raises ``ValueError`` if it is too short."""
    key = bytes.fromhex(path.read_text(encoding="ascii").strip())
    if len(key) < KEY_BYTES:
        raise ValueError(f"{path} holds fewer than {KEY_BYTES} bytes")
    return key


def new_key(path: Path) -> bytes:
    """Create a random key at ``path`` (mode 0600); never overwrites an existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(KEY_BYTES)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(key.hex() + "\n")
    return key


def private_rel(repo: Path, path: Path) -> str | None:
    """``path`` relative to ``repo`` as POSIX text when it lies under ``private/``."""
    try:
        rel = PurePosixPath(path.resolve().relative_to(repo.resolve()).as_posix())
    except ValueError:
        return None
    return str(rel) if rel.parts[:1] == ("private",) and ".." not in rel.parts else None


def republish(repo: Path, audit: Path, original: Path, key: bytes) -> tuple[bytes, dict[str, Any]]:
    """(public rows, manifest) for ``audit`` from its private ``original``."""
    rel = private_rel(repo, original)
    if rel is None:
        raise ValueError(f"{original} is not under {repo / 'private'}")
    data = original.read_bytes()
    tasks = read_jsonl((audit / "tasks.jsonl").read_bytes(), f"{audit}/tasks.jsonl")
    rows = publish(read_jsonl(data, str(original)), task_order(tasks), key)
    public = dump_jsonl(rows)
    return public, manifest(data, public, rel, Path(__file__).read_bytes())


def verify(repo: Path, audit: Path, key_path: Path) -> list[str]:
    """Problems with a published audit directory, checked where the private files live.

    The private original named in ``PUBLIC_ROWS.json`` must lie under ``private/``,
    exist, and match its recorded SHA-256, and republishing it with the key must
    reproduce the committed ``variants.jsonl`` byte for byte.
    """
    where = audit.name
    try:
        doc = json.loads((audit / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{where}: {MANIFEST} unreadable: {exc}"]
    rel = doc.get("private_original") if isinstance(doc, dict) else None
    original = repo / str(rel)
    if not isinstance(rel, str) or private_rel(repo, original) is None:
        return [f"{where}: private_original {rel!r} is not under private/"]
    if not original.is_file():
        return [f"{where}: private original {rel} is missing"]
    problems: list[str] = []
    if sha256_bytes(original.read_bytes()) != doc.get("private_sha256"):
        problems.append(f"{where}: private original {rel} does not match its recorded sha256")
    if not key_path.is_file():
        return [*problems, f"{where}: key {KEY_PATH} is missing, so the rows cannot be checked"]
    try:
        public, _ = republish(repo, audit, original, load_key(key_path))
    except (OSError, ValueError) as exc:
        return [*problems, f"{where}: republishing failed: {exc}"]
    if public != (audit / "variants.jsonl").read_bytes():
        problems.append(f"{where}: republishing does not reproduce variants.jsonl")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Command line; returns the exit status."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root")
    ap.add_argument("--audit", type=Path, required=True, help="artifacts/audit/<benchmark>")
    ap.add_argument("--original", type=Path, required=True, help="private original rows")
    ap.add_argument("--key", type=Path, required=True, help=f"key file, normally {KEY_PATH}")
    ap.add_argument("--new-key", action="store_true", help="create the key (never overwrites)")
    args = ap.parse_args(argv)
    try:
        summary = json.loads((args.audit / "summary.json").read_text(encoding="utf-8"))
        if not (isinstance(summary, dict) and summary.get("third_party") is True):
            raise ValueError(f"{args.audit}: not a third-party audit (summary.json third_party)")
        if private_rel(args.repo, args.original) is None:
            raise ValueError(f"{args.original} is not under {args.repo / 'private'}")
        if args.new_key:
            key = new_key(args.key)
        elif args.key.is_file():
            key = load_key(args.key)
        else:
            raise ValueError(f"{args.key} missing; pass --new-key to create it")
        public, doc = republish(args.repo, args.audit, args.original, key)
    except (OSError, ValueError) as exc:
        print(f"publish_rows: {exc}", file=sys.stderr)
        return 1
    (args.audit / "variants.jsonl").write_bytes(public)
    text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    (args.audit / MANIFEST).write_text(text, encoding="utf-8")
    n = public.count(b"\n")
    print(f"publish_rows: {args.audit}: {n} rows with keyed ids, {MANIFEST} written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
