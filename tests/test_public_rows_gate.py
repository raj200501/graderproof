"""G14 checks for keyed public third-party rows (DECISIONS.md D44)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import publish_rows as pr
import ship_check as sc

T1, T2 = "a" * 64, "b" * 64


def row(task: str, vid: str, operator: str = "py-constant") -> dict[str, Any]:
    """A variant row shaped like the frozen code's output."""
    return {
        "counted_in_headline": True,
        "grader_passed": True,
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
        "witness_sha256": "c" * 64,
    }


def audit_repo(tmp_path: Path, third_party: bool = True, publish: bool = True) -> tuple[Path, Path]:
    """A repository with one audit directory, published with keyed ids when asked."""
    repo = tmp_path / "repo"
    audit = repo / "artifacts" / "audit" / "bench"
    audit.mkdir(parents=True)
    (audit / "summary.json").write_text(json.dumps({"third_party": third_party}), encoding="utf-8")
    tasks = [
        {"task_hash": T1, "determinism": "stable_pass"},
        {"task_hash": T2, "determinism": "stable_pass"},
    ]
    (audit / "tasks.jsonl").write_text(
        "".join(json.dumps(t) + "\n" for t in tasks), encoding="utf-8"
    )
    raw = "".join(
        json.dumps(r, sort_keys=True) + "\n"
        for r in (row(T1, "1" * 64), row(T2, "2" * 64), row(T1, "3" * 64))
    )
    (audit / "variants.jsonl").write_text(raw, encoding="utf-8")
    if publish:
        original = repo / "private" / "audit" / "bench" / "variants.jsonl"
        original.parent.mkdir(parents=True)
        original.write_text(raw, encoding="utf-8")
        key = repo / pr.KEY_PATH
        code = pr.main(
            [
                "--repo",
                str(repo),
                "--audit",
                str(audit),
                "--original",
                str(original),
                "--key",
                str(key),
                "--new-key",
            ]
        )
        assert code == 0
    return repo, audit


def set_manifest(audit: Path, **changes: Any) -> None:
    """Rewrite PUBLIC_ROWS.json with ``changes`` applied."""
    doc = json.loads((audit / pr.MANIFEST).read_text(encoding="utf-8"))
    doc.update(changes)
    (audit / pr.MANIFEST).write_text(json.dumps(doc), encoding="utf-8")


def test_published_rows_pass_both_checks(tmp_path: Path) -> None:
    repo, _ = audit_repo(tmp_path)
    assert sc.public_rows_problems(repo) == []
    assert sc.verify_public_rows(repo) == []


def test_raw_third_party_rows_fail(tmp_path: Path) -> None:
    repo, _ = audit_repo(tmp_path, publish=False)
    problems = sc.public_rows_problems(repo)
    assert problems and pr.MANIFEST in problems[0]


def test_own_benchmark_rows_need_no_keys(tmp_path: Path) -> None:
    repo, _ = audit_repo(tmp_path, third_party=False, publish=False)
    assert sc.public_rows_problems(repo) == []
    assert sc.verify_public_rows(repo) == []


def test_operator_names_and_changed_rows_fail(tmp_path: Path) -> None:
    repo, audit = audit_repo(tmp_path)
    rows = [
        json.loads(line)
        for line in (audit / "variants.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["operator"] = "py-constant"
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode("utf-8")
    (audit / "variants.jsonl").write_bytes(data)
    problems = sc.public_rows_problems(repo)
    assert any("rows_sha256" in p for p in problems)
    set_manifest(audit, rows_sha256=hashlib.sha256(data).hexdigest())
    assert any("operator" in p for p in sc.public_rows_problems(repo))
    assert any("reproduce" in p for p in sc.verify_public_rows(repo))


def test_unordered_rows_and_bad_ids_fail(tmp_path: Path) -> None:
    repo, audit = audit_repo(tmp_path)
    lines = (audit / "variants.jsonl").read_text(encoding="utf-8").splitlines()
    reordered = ("\n".join(reversed(lines)) + "\n").encode("utf-8")
    (audit / "variants.jsonl").write_bytes(reordered)
    set_manifest(audit, rows_sha256=hashlib.sha256(reordered).hexdigest())
    assert any("order" in p for p in sc.public_rows_problems(repo))
    rows = [json.loads(line) for line in lines]
    rows[0]["variant_id"] = "not-a-hash"
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode("utf-8")
    (audit / "variants.jsonl").write_bytes(data)
    set_manifest(audit, rows_sha256=hashlib.sha256(data).hexdigest())
    assert any("64-hex" in p for p in sc.public_rows_problems(repo))


def test_wrong_scheme_fails(tmp_path: Path) -> None:
    repo, audit = audit_repo(tmp_path)
    set_manifest(audit, scheme="sha256")
    assert any("scheme" in p for p in sc.public_rows_problems(repo))


def test_missing_private_original_fails_in_the_origin(tmp_path: Path) -> None:
    repo, _ = audit_repo(tmp_path)
    (repo / "private" / "audit" / "bench" / "variants.jsonl").unlink()
    assert any("missing" in p for p in sc.verify_public_rows(repo))
