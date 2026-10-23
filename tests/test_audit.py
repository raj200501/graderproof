"""End-to-end tests: the audit pipeline, banked outputs, and the offline demo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graderproof import demo
from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.audit import AuditConfig, Auditor, context_for, git_sha, provenance, write_outputs
from graderproof.models import ModelClient, PendingWorkError
from graderproof.run import Runner
from graderproof.sandbox import LocalSandbox
from graderproof.spec import Outcome
from graderproof.validate import ModelReviewer, RequirementExtractor

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo"
LEDGER = ROOT / "artifacts" / "usage" / "ledger.jsonl"
BUDGET = ROOT / "budget.toml"
GOLDEN = ROOT / "tests" / "golden" / "demo_output.txt"


def auditor(tmp_path: Path, store: Path, disabled: bool = True) -> Auditor:
    adapter = ToybenchAdapter()
    client = ModelClient(store, LEDGER, BUDGET, disabled=disabled)
    return Auditor(
        adapter,
        Runner(adapter, LocalSandbox(), cache_dir=tmp_path / "cache"),
        RequirementExtractor(client),
        ModelReviewer(client),
        demo.DEMO_CONFIG,
    )


def test_demo_matches_golden_without_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo, "demo_sandbox", LocalSandbox)
    assert demo.run_demo(DEMO, DEMO / "model_store", LEDGER, BUDGET) == GOLDEN.read_text()


def test_audit_writes_public_and_evidence_outputs(tmp_path: Path) -> None:
    tasks = ToybenchAdapter().load(DEMO)
    results, evidence = auditor(tmp_path, DEMO / "model_store").run(tasks)
    summary = write_outputs(
        results,
        evidence,
        tmp_path / "pub",
        tmp_path / "ev",
        demo.DEMO_CONFIG,
        {"benchmark": "demo"},
        public_task_ids=True,
    )
    assert summary["schema"] == "graderproof.audit/1" and summary["n_sampled"] == 5
    assert (
        summary["provenance"]["config_hash"]
        and summary["bootstrap"]["B"] == demo.DEMO_CONFIG.replicates
    )
    tasks_rows = [
        json.loads(x) for x in (tmp_path / "pub" / "tasks.jsonl").read_text().splitlines()
    ]
    assert {r["task"] for r in tasks_rows} == {t.key for t in tasks}
    variants = [
        json.loads(x) for x in (tmp_path / "pub" / "variants.jsonl").read_text().splitlines()
    ]
    assert all("files" not in v for v in variants)
    headline = [v for v in variants if v["counted_in_headline"]]
    assert headline and all(len(v["witness_sha256"]) == 64 for v in headline)
    ev = json.loads(next((tmp_path / "ev").glob("*.json")).read_text())
    assert ev["schema"] == "graderproof.evidence/1" and ev["variants"][0]["files"]
    write_outputs(
        results,
        evidence,
        tmp_path / "pub2",
        tmp_path / "ev2",
        demo.DEMO_CONFIG,
        {},
        public_task_ids=False,
    )
    assert all(
        "task" not in json.loads(x)
        for x in (tmp_path / "pub2" / "tasks.jsonl").read_text().splitlines()
    )


def test_audit_reports_pending_requests(tmp_path: Path) -> None:
    tasks = ToybenchAdapter().load(DEMO)[:1]
    with pytest.raises(PendingWorkError) as exc:
        auditor(tmp_path, tmp_path / "empty_store", disabled=False).run(tasks)
    assert len(exc.value.hashes) == 1
    assert list((tmp_path / "empty_store" / "requests").glob("*.json"))


def test_context_and_provenance() -> None:
    task = ToybenchAdapter().load(DEMO)[-1]
    ref = Outcome(
        files={
            "input.txt": task.environment["workspace_files"]["input.txt"],
            "stats.json": '{"a": 1}',
        },
        stdout="",
    )
    ctx = context_for(task, ref, {"solve.py": "python"})
    assert (
        ctx.outputs == ["stats.json"]
        and ctx.json_outputs == ["stats.json"]
        and not ctx.stdout_nonempty
    )
    prov = provenance(AuditConfig(), {"x": 1})
    assert prov["x"] == 1 and prov["git_sha"] == git_sha()
    assert git_sha(Path("/")) == "unknown"
