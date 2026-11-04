"""Tests for E4 repairs (graderproof.repair)."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from graderproof import demo, repair
from graderproof.adapters import Adapter
from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.audit import Auditor
from graderproof.models import ModelClient
from graderproof.run import Runner
from graderproof.sandbox import LocalSandbox
from graderproof.spec import Requirement
from graderproof.validate import ModelReviewer, RequirementExtractor
from graderproof.variants.model import ModelProposer

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo"


def req(rid: str, *types: str) -> dict[str, Any]:
    checks = [{"type": t, "path": "a", "code": 0} for t in types]
    return Requirement(rid, rid, tuple(checks)).to_dict()


def variant(
    vid: str, broken: list[str], kind: str = "violating", passed: bool = True
) -> dict[str, Any]:
    return {
        "id": vid,
        "kind": kind,
        "counted_in_headline": True,
        "grader_passed": passed,
        "files": {},
        "witness": {"broken": [{"requirement": r} for r in broken]},
    }


def test_plan_greedy_cover_and_unrepairable() -> None:
    evidence = {
        "requirements": [
            req("R1", "file_exists"),
            req("R2", "file_exists"),
            req("R3", "exit_code"),
        ],
        "variants": [
            variant("v1", ["R1", "R2"]),
            variant("v2", ["R2"]),
            variant("v3", ["R3"]),  # only an exit-status requirement: uncovered
            variant("v4", ["R1"], passed=False),  # killed: not a target
            variant("v5", ["R1"], kind="preserving"),
        ],
    }
    plan = repair.plan_repair(evidence)
    assert plan is not None
    assert [r.id for r in plan.requirements] == ["R2"]
    assert plan.targets == ("v1", "v2")
    assert plan.uncovered == ("v3",)
    assert repair.plan_repair({"variants": [variant("x", ["R1"], passed=False)]}) is None
    assert not repair.repairable(Requirement.from_dict(req("R", "exit_code")))


def test_toml_entry_rewrite() -> None:
    base = 'id = "t"\n\n[grader]\nentry = "grade.sh"\n\n[metadata]\nx = 1\n'
    assert 'entry = "gp_repaired.sh"' in repair.toml_with_entry(base, "gp_repaired.sh")
    assert "grade.sh" not in repair.toml_with_entry(base, "gp_repaired.sh")
    no_entry = 'id = "t"\n[grader]\n[metadata]\nx = 1\n'
    out = repair.toml_with_entry(no_entry, "w.sh")
    assert out.index('entry = "w.sh"') < out.index("[metadata]")
    assert repair.toml_with_entry('id = "t"\n', "w.sh").endswith('[grader]\nentry = "w.sh"\n')
    tail = repair.toml_with_entry('id = "t"\n[grader]\n', "w.sh")
    assert tail.endswith('[grader]\nentry = "w.sh"\n')


def test_git_patch_format() -> None:
    patch = repair.git_patch({"a.txt": "x\n"}, {"a.txt": "y\n", "new.sh": "echo hi"})
    assert "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n" in patch
    assert "new file mode 100644\n--- /dev/null\n+++ b/new.sh\n" in patch
    assert "\\ No newline at end of file\n" in patch
    assert repair.git_patch({"a": "1"}, {"a": "1"}) == ""


def test_checker_source_is_standalone() -> None:
    src = repair.checker_source()
    tree = ast.parse(src)
    imported = {
        (n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
    } | {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert "graderproof" not in imported
    assert src.count("from __future__") == 1


@pytest.fixture(scope="module")
def demo_evidence() -> list[tuple[Any, dict[str, Any]]]:
    adapter = ToybenchAdapter()
    tasks = adapter.load(DEMO)
    client = ModelClient(
        DEMO / "model_store",
        ROOT / "artifacts/usage/ledger.jsonl",
        ROOT / "budget.toml",
        disabled=True,
    )
    aud = Auditor(
        adapter,
        Runner(adapter, LocalSandbox()),
        RequirementExtractor(client),
        ModelReviewer(client),
        demo.DEMO_CONFIG,
        proposer=ModelProposer(client),
    )
    results, evidence = aud.run(tasks)
    return [(t, ev.to_dict(r)) for t, r, ev in zip(tasks, results, evidence, strict=True)]


def local_runner(adapter: Adapter) -> Runner:
    return Runner(adapter, LocalSandbox())


@pytest.mark.parametrize("task_id", ["word-stats", "classify", "refund"])
def test_demo_repairs_are_accepted(
    demo_evidence: list[tuple[Any, dict[str, Any]]], task_id: str
) -> None:
    task, doc = next((t, d) for t, d in demo_evidence if t.id == task_id)
    result = repair.build_repair(task, DEMO / task_id, doc)
    assert result is not None and result.plan.requirements
    assert "diff --git a/task.toml b/task.toml" in result.patch
    checks = json.loads(result.files["grader/gp_repair_checks.json"])
    assert checks["task"] == task.key and checks["requirements"]
    val = repair.validate_repair(result, DEMO / task_id, doc, ToybenchAdapter(), local_runner, k=2)
    assert val["accepted"], val
    assert result.accepted
    log = result.log()
    assert log["schema"] == "graderproof.repair_validation/1" and log["targets"]


def test_tasks_without_survivors_get_no_repair(
    demo_evidence: list[tuple[Any, dict[str, Any]]],
) -> None:
    task, doc = next((t, d) for t, d in demo_evidence if t.id == "greeting")
    assert repair.build_repair(task, DEMO / "greeting", doc) is None


def test_uncoverable_repair_is_not_accepted(
    demo_evidence: list[tuple[Any, dict[str, Any]]],
) -> None:
    task, doc = next((t, d) for t, d in demo_evidence if t.id == "word-stats")
    only_exit = {
        **doc,
        "requirements": [req("R1", "exit_code")],
        "variants": [variant("v", ["R1"])],
    }
    result = repair.build_repair(task, DEMO / "word-stats", only_exit)
    assert result is not None and not result.plan.requirements and result.patch == ""
    val = repair.validate_repair(
        result, DEMO / "word-stats", only_exit, ToybenchAdapter(), local_runner, k=1
    )
    assert val == {"accepted": False, "reason": "no repairable requirement covers any survivor"}


def test_repair_command_public_private_and_generalize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, demo_evidence: list[tuple[Any, dict[str, Any]]]
) -> None:
    from graderproof.cli import PENDING, main

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for task, doc in demo_evidence:
        (evidence / f"{task.key_hash}.json").write_text(json.dumps(doc))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    budget = tmp_path / "b.toml"
    budget.write_text(
        "cash_usd = 0\nclaude_agent_runs_per_day = 30\nclaude_agent_max_turns = 40\n"
        "claude_single_calls_per_day = 300\nclaude_review_runs_per_day = 6\n"
        "local_model_max_params_b = 8\ndisk_floor_gb = 8\n"
    )
    common = [str(DEMO), "--evidence", str(evidence), "--benchmark", "demo", "--k", "1"]
    common += [
        "--store",
        str(tmp_path / "store"),
        "--ledger",
        str(tmp_path / "l.jsonl"),
        "--budget",
        str(budget),
    ]
    assert main(["repair", *common, "--out", str(tmp_path / "e4")]) == 0
    summary = json.loads((tmp_path / "e4" / "summary.json").read_text())
    assert summary["ran"] and summary["tasks_with_survivors"] == 3
    assert {Path(r["patch"]).name for r in summary["repaired"]} == {
        "word-stats.patch",
        "classify.patch",
        "refund.patch",
    }
    assert all(
        Path(r["patch"]).exists() and Path(r["validation_log"]).exists()
        for r in summary["repaired"]
    )
    assert summary["generalization"] == {"ran": False}
    assert main(["repair", *common, "--out", str(tmp_path / "e4p"), "--private"]) == 0
    manifest = json.loads(Path("outbound/patches/MANIFEST.json").read_text())
    assert len(manifest["files"]) == 6
    assert all(e["path"].startswith("private/outbound/patches/demo/") for e in manifest["files"])
    assert main(["repair", *common, "--out", str(tmp_path / "e4g"), "--generalize"]) == PENDING
    assert list((tmp_path / "store" / "requests").glob("*.json"))
