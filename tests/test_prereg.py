"""Tests for tools/prereg.py (the preregistration chain)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import prereg

ENV = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def commit(repo: Path, msg: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), *ENV, "commit", "-qm", msg], check=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "r"
    (r / "prereg").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    (r / "README").write_text("x\n")
    commit(r, "init")
    return r


def test_empty_fails(repo: Path) -> None:
    assert prereg.verify(repo) == ["no preregistrations"]


def test_freeze_verify_and_artifact_order(repo: Path) -> None:
    f = repo / "prereg" / "0001-study.md"
    f.write_text("# Study\n")
    entry = prereg.freeze(f, repo, now="2026-10-23T00:00:00Z")
    assert entry["prev_hash"] == prereg.GENESIS and entry["entry_hash"] == prereg.entry_hash(entry)
    with pytest.raises(ValueError, match="already frozen"):
        prereg.freeze(f, repo)
    with pytest.raises(ValueError, match="NNNN"):
        prereg.freeze(repo / "prereg" / "bad.md", repo)
    commit(repo, "freeze 0001")
    assert prereg.verify(repo) == []
    art = repo / "artifacts" / "audit" / "b" / "summary.json"
    art.parent.mkdir(parents=True)
    art.write_text(json.dumps({"confirmatory": True, "prereg": "prereg/0001-study.md"}))
    commit(repo, "data")
    assert prereg.verify(repo) == []
    assert prereg.confirmatory_artifacts(repo) == [art]


def test_detects_edits_unfrozen_and_bad_citations(repo: Path) -> None:
    f = repo / "prereg" / "0001-study.md"
    f.write_text("# Study\n")
    prereg.freeze(f, repo)
    (repo / "prereg" / "0002-other.md").write_text("Amends: 0009\n")
    art = repo / "artifacts" / "e0" / "results.json"
    art.parent.mkdir(parents=True)
    art.write_text(json.dumps({"prereg": "prereg/0001-study.md"}))
    bad = repo / "artifacts" / "x" / "summary.json"
    bad.parent.mkdir(parents=True)
    bad.write_text(json.dumps({"confirmatory": True, "prereg": "prereg/none.md"}))
    commit(repo, "same commit")
    f.write_text("# Study, edited\n")
    commit(repo, "edit")
    text = " | ".join(prereg.verify(repo))
    assert "changed after it was frozen" in text
    assert "has 2 commits" in text
    assert "0002-other.md has no chain entry" in text
    assert "amends 0009" in text
    assert "was not committed before artifacts/e0/results.json" in text
    assert "cites no existing preregistration" in text


def test_chain_tampering(repo: Path) -> None:
    for name in ("0001-a.md", "0002-b.md"):
        p = repo / "prereg" / name
        p.write_text(name)
        prereg.freeze(p, repo)
    commit(repo, "both")
    chain = prereg.read_chain(repo / "prereg" / "FROZEN.jsonl")
    chain[1]["prev_hash"] = "f" * 64
    chain.append(dict(chain[0]))
    chain.append({**chain[0], "file": "0003-gone.md"})
    (repo / "prereg" / "FROZEN.jsonl").write_text("".join(json.dumps(e) + "\n" for e in chain))
    text = " | ".join(prereg.verify(repo))
    assert "does not link" in text and "hash does not recompute" in text
    assert "frozen twice" in text and "0003-gone.md, which does not exist" in text


def test_main_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert prereg.main(["bogus"]) == 2
    assert prereg.main(["show"]) == 0
    capsys.readouterr()
