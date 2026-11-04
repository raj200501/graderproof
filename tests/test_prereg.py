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
    assert "results.json cites prereg/0001-study.md, which is not committed exactly once" in text
    assert "cites no existing preregistration" in text


E0_PREREG = "prereg/0001-e0-tool-validity.md"


def e0_outputs(repo: Path, confirmatory: object = True) -> None:
    """What graderproof audit writes for E0: model calls first, then the outputs."""
    calls = repo / "artifacts" / "model_calls" / "e0" / "requests" / "r1.json"
    calls.parent.mkdir(parents=True, exist_ok=True)
    calls.write_text('{"items": []}\n')
    out = repo / "artifacts" / "e0"
    out.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {"prereg": E0_PREREG, "model_store": "artifacts/model_calls/e0"}
    if confirmatory is not None:
        summary["confirmatory"] = confirmatory
    (out / "summary.json").write_text(json.dumps(summary))
    (out / "tasks.jsonl").write_text('{"task": "toybench:t1"}\n')


def e0_score(repo: Path) -> None:
    (repo / "artifacts" / "e0" / "results.json").write_text(json.dumps({"prereg": E0_PREREG}))


def freeze_e0(repo: Path) -> None:
    f = repo / E0_PREREG
    f.write_text("# E0\n")
    prereg.freeze(f, repo, now="2026-11-04T00:00:00Z")


def test_e0_order_is_checked_from_the_first_output(repo: Path) -> None:
    """Review B3 (g11_e0order.py): outputs, then the freeze, then results.json."""
    e0_outputs(repo, confirmatory=None)
    commit(repo, "E0 audit outputs (data exists)")
    freeze_e0(repo)
    commit(repo, "freeze prereg 0001 (after the data)")
    e0_score(repo)
    commit(repo, "e0-score")
    text = " | ".join(prereg.verify(repo))
    assert "artifacts/e0/summary.json is not marked confirmatory" in text
    assert f"{E0_PREREG} was not committed before artifacts/e0/results.json" in text
    assert len(prereg.confirmatory_artifacts(repo)) == 2


def test_e0_model_calls_date_the_run(repo: Path) -> None:
    calls = repo / "artifacts" / "model_calls" / "e0" / "requests" / "r0.json"
    calls.parent.mkdir(parents=True)
    calls.write_text('{"items": ["first"]}\n')
    commit(repo, "first model call")
    freeze_e0(repo)
    commit(repo, "freeze")
    e0_outputs(repo)
    e0_score(repo)
    commit(repo, "outputs and score")
    text = " | ".join(prereg.verify(repo))
    assert f"{E0_PREREG} was not committed before artifacts/e0/summary.json" in text
    assert "artifacts/model_calls/e0" in text


def test_e0_in_the_right_order_passes(repo: Path) -> None:
    freeze_e0(repo)
    commit(repo, "freeze")
    e0_outputs(repo)
    commit(repo, "outputs")
    e0_score(repo)
    commit(repo, "score")
    assert prereg.verify(repo) == []


def test_a_named_model_store_dates_an_audit(repo: Path) -> None:
    calls = repo / "artifacts" / "model_calls" / "b1" / "r0.json"
    calls.parent.mkdir(parents=True)
    calls.write_text("{}\n")
    commit(repo, "b1 calls")
    f = repo / "prereg" / "0001-audit.md"
    f.write_text("# audit\n")
    prereg.freeze(f, repo)
    commit(repo, "freeze")
    art = repo / "artifacts" / "audit" / "b1" / "summary.json"
    art.parent.mkdir(parents=True)
    doc = {"confirmatory": True, "prereg": "prereg/0001-audit.md"}
    art.write_text(json.dumps({**doc, "model_store": "artifacts/model_calls/b1"}))
    commit(repo, "audit")
    assert "was not committed before artifacts/audit/b1/summary.json" in " ".join(
        prereg.verify(repo)
    )
    art.write_text(json.dumps({**doc, "model_store": "runs/model_calls"}))
    commit(repo, "store outside artifacts")
    assert "is not a directory under artifacts/" in " ".join(prereg.verify(repo))
    art.write_text(json.dumps(doc))
    commit(repo, "no store named")
    assert prereg.verify(repo) == []


def test_data_moved_in_from_a_pilot_is_dated_by_its_first_add(repo: Path) -> None:
    pilot = repo / "artifacts" / "pilot" / "tasks.jsonl"
    pilot.parent.mkdir(parents=True)
    pilot.write_text('{"task": "toybench:t1", "determinism": "stable_pass"}\n')
    commit(repo, "pilot")
    freeze_e0(repo)
    commit(repo, "freeze")
    e0_outputs(repo)
    pilot.replace(repo / "artifacts" / "e0" / "tasks.jsonl")
    e0_score(repo)
    commit(repo, "move the pilot in")
    assert f"{E0_PREREG} was not committed before" in " ".join(prereg.verify(repo))


def test_citations_must_name_a_frozen_numbered_preregistration(repo: Path) -> None:
    freeze_e0(repo)
    (repo / "prereg" / "0002-draft.md").write_text("# draft\n")
    commit(repo, "freeze 0001; 0002 not frozen")
    art = repo / "artifacts" / "audit" / "b1" / "summary.json"
    art.parent.mkdir(parents=True)
    for cited, message in (
        ("prereg/FROZEN.jsonl", "cites no existing preregistration"),
        ("prereg/0002-draft.md", "cites prereg/0002-draft.md, which is not frozen"),
    ):
        art.write_text(json.dumps({"confirmatory": True, "prereg": cited}))
        commit(repo, f"cite {cited}")
        assert message in " ".join(prereg.verify(repo))
    art.write_text("[1, 2]")
    commit(repo, "not an object")
    assert "summary.json is not a JSON object" in " ".join(prereg.verify(repo))


def test_a_preregistration_merged_from_a_branch_counts_once(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "side"], check=True)
    freeze_e0(repo)
    commit(repo, "freeze on a branch")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-"], check=True)
    (repo / "NOTES").write_text("x\n")
    commit(repo, "main moves on")
    merge = ["merge", "-q", "--no-ff", "--no-edit", "side"]
    subprocess.run(["git", "-C", str(repo), *ENV, *merge], check=True)
    e0_outputs(repo)
    e0_score(repo)
    commit(repo, "E0")
    assert prereg.verify(repo) == []


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
