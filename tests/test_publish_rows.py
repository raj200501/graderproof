"""Tests for tools/publish_rows.py: keyed public rows for third-party audits (D44)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import publish_rows as pr
import pytest

KEY = bytes(range(32))
OTHER_KEY = bytes(range(1, 33))
T1, T2 = "a" * 64, "b" * 64


def row(
    task: str, vid: str, operator: str = "py-constant", witness: str | None = "c" * 64
) -> dict[str, Any]:
    """A variant row shaped like the frozen code's output."""
    return {
        "counted_in_headline": True,
        "grader_passed": False,
        "grader_runs": 1,
        "kind": "violating",
        "operator": operator,
        "task_hash": task,
        "validation_status": "validated",
        "validations": [
            {"validator": "witness:requirements/v1", "verdict": "violating"},
            {"validator": "model:claude-subagent/review/v1", "verdict": "violating"},
        ],
        "variant_id": vid,
        "witness_sha256": witness,
    }


def test_keyed_is_deterministic_and_depends_on_key_and_field() -> None:
    value = "d" * 64
    first = pr.keyed(KEY, "variant_id", value)
    assert first == pr.keyed(KEY, "variant_id", value)
    assert first != pr.keyed(OTHER_KEY, "variant_id", value)
    assert first != pr.keyed(KEY, "witness_sha256", value)
    assert first != value and first != hashlib.sha256(value.encode()).hexdigest()
    assert isinstance(first, str) and len(first) == 64


def test_keyed_keeps_null_and_rejects_other_values() -> None:
    assert pr.keyed(KEY, "witness_sha256", None) is None
    with pytest.raises(ValueError):
        pr.keyed(KEY, "variant_id", "")
    with pytest.raises(ValueError):
        pr.keyed(KEY, "variant_id", 7)


def test_publish_keys_ids_drops_operator_and_copies_the_rest() -> None:
    original = [row(T1, "1" * 64), row(T1, "2" * 64, witness=None)]
    out = pr.publish(original, {T1: 0}, KEY)
    assert len(out) == 2
    for pub in out:
        assert "operator" not in pub
        assert pub["variant_id"] not in {"1" * 64, "2" * 64}
    by_id = {pub["variant_id"]: pub for pub in out}
    first = by_id[pr.keyed(KEY, "variant_id", "1" * 64)]
    assert first["witness_sha256"] == pr.keyed(KEY, "witness_sha256", "c" * 64)
    assert by_id[pr.keyed(KEY, "variant_id", "2" * 64)]["witness_sha256"] is None
    unchanged = {
        k: v
        for k, v in original[0].items()
        if k not in ("operator", "variant_id", "witness_sha256")
    }
    assert {k: first[k] for k in unchanged} == unchanged
    assert original[0]["operator"] == "py-constant"  # the input is not modified


def test_publish_orders_by_task_then_keyed_id() -> None:
    original = [row(T2, "1" * 64), row(T1, "2" * 64), row(T1, "3" * 64), row(T2, "4" * 64)]
    out = pr.publish(original, {T2: 0, T1: 1}, KEY)
    assert [r["task_hash"] for r in out] == [T2, T2, T1, T1]
    for task in (T1, T2):
        ids = [r["variant_id"] for r in out if r["task_hash"] == task]
        assert ids == sorted(ids)


def test_publish_rejects_unknown_tasks_duplicates_and_short_keys() -> None:
    with pytest.raises(ValueError, match="unknown task"):
        pr.publish([row(T2, "1" * 64)], {T1: 0}, KEY)
    with pytest.raises(ValueError, match="duplicate"):
        pr.publish([row(T1, "1" * 64), row(T1, "1" * 64)], {T1: 0}, KEY)
    with pytest.raises(ValueError, match="key"):
        pr.publish([row(T1, "1" * 64)], {T1: 0}, b"short")
    bad = row(T1, "1" * 64)
    del bad["variant_id"]
    with pytest.raises(ValueError, match="variant_id"):
        pr.publish([bad], {T1: 0}, KEY)


def test_task_order_rejects_repeats_and_missing_hashes() -> None:
    assert pr.task_order([{"task_hash": T1}, {"task_hash": T2}]) == {T1: 0, T2: 1}
    with pytest.raises(ValueError):
        pr.task_order([{"task_hash": T1}, {"task_hash": T1}])
    with pytest.raises(ValueError):
        pr.task_order([{"determinism": "stable_pass"}])


def make_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A repository with a third-party audit directory and its private original."""
    repo = tmp_path / "repo"
    audit = repo / "artifacts" / "audit" / "bench"
    audit.mkdir(parents=True)
    (audit / "summary.json").write_text(json.dumps({"third_party": True}), encoding="utf-8")
    tasks = [
        {"task_hash": T1, "determinism": "stable_pass"},
        {"task_hash": T2, "determinism": "stable_pass"},
    ]
    (audit / "tasks.jsonl").write_text(
        "".join(json.dumps(t) + "\n" for t in tasks), encoding="utf-8"
    )
    original = repo / "private" / "audit" / "bench" / "variants.jsonl"
    original.parent.mkdir(parents=True)
    rows = [row(T2, "1" * 64), row(T1, "2" * 64, operator="py-return-none"), row(T1, "3" * 64)]
    original.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8"
    )
    (audit / "variants.jsonl").write_bytes(original.read_bytes())  # as the frozen code wrote it
    return repo, audit, original


def run_main(repo: Path, audit: Path, original: Path, *extra: str) -> int:
    key = repo / "private" / "keys" / "public_rows.key"
    return pr.main(
        [
            "--repo",
            str(repo),
            "--audit",
            str(audit),
            "--original",
            str(original),
            "--key",
            str(key),
            *extra,
        ]
    )


def test_main_publishes_rows_and_manifest_that_verify(tmp_path: Path) -> None:
    repo, audit, original = make_repo(tmp_path)
    assert run_main(repo, audit, original, "--new-key") == 0
    key_path = repo / "private" / "keys" / "public_rows.key"
    assert key_path.stat().st_mode & 0o077 == 0
    public = (audit / "variants.jsonl").read_bytes()
    assert b"operator" not in public and b"1" * 64 not in public
    manifest = json.loads((audit / pr.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["schema"] == pr.SCHEMA and manifest["scheme"] == pr.SCHEME
    assert manifest["private_original"] == "private/audit/bench/variants.jsonl"
    assert manifest["private_sha256"] == hashlib.sha256(original.read_bytes()).hexdigest()
    assert manifest["rows_sha256"] == hashlib.sha256(public).hexdigest()
    assert pr.verify(repo, audit, key_path) == []
    # Publishing again with the same key reproduces the same bytes.
    assert run_main(repo, audit, original) == 0
    assert (audit / "variants.jsonl").read_bytes() == public


def test_verify_reports_tampering_and_missing_inputs(tmp_path: Path) -> None:
    repo, audit, original = make_repo(tmp_path)
    assert run_main(repo, audit, original, "--new-key") == 0
    key_path = repo / "private" / "keys" / "public_rows.key"
    public = audit / "variants.jsonl"
    public.write_bytes(public.read_bytes().replace(b'"grader_runs": 1', b'"grader_runs": 2', 1))
    assert any("reproduce" in p for p in pr.verify(repo, audit, key_path))
    assert run_main(repo, audit, original) == 0
    original.write_bytes(original.read_bytes() + b"\n")
    assert any("sha256" in p for p in pr.verify(repo, audit, key_path))
    original.unlink()
    assert any("missing" in p for p in pr.verify(repo, audit, key_path))


def test_verify_without_key_or_with_a_bad_manifest_path(tmp_path: Path) -> None:
    repo, audit, original = make_repo(tmp_path)
    assert run_main(repo, audit, original, "--new-key") == 0
    assert any("key" in p for p in pr.verify(repo, audit, repo / "private" / "keys" / "absent.key"))
    manifest = json.loads((audit / pr.MANIFEST).read_text(encoding="utf-8"))
    manifest["private_original"] = "artifacts/audit/bench/variants.jsonl"
    (audit / pr.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    assert any(
        "private/" in p
        for p in pr.verify(repo, audit, repo / "private" / "keys" / "public_rows.key")
    )


def test_main_refuses_unsafe_inputs(tmp_path: Path) -> None:
    repo, audit, original = make_repo(tmp_path)
    # The original must live under private/.
    outside = repo / "artifacts" / "copy.jsonl"
    outside.write_bytes(original.read_bytes())
    assert run_main(repo, audit, outside, "--new-key") != 0
    # The key must exist unless --new-key is given, and --new-key never overwrites one.
    assert run_main(repo, audit, original) != 0
    assert run_main(repo, audit, original, "--new-key") == 0
    assert run_main(repo, audit, original, "--new-key") != 0
    # Only third-party audits are published this way.
    (audit / "summary.json").write_text(json.dumps({"third_party": False}), encoding="utf-8")
    assert run_main(repo, audit, original) != 0
