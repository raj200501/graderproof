"""End-to-end tests: the audit pipeline, banked outputs, and the offline demo."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from graderproof import demo
from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.audit import (
    AuditConfig,
    Auditor,
    context_for,
    dirty_paths,
    git_sha,
    provenance,
    write_outputs,
    write_review_queue,
)
from graderproof.core import Determinism, Validation, Variant, VariantKind
from graderproof.models import ModelClient, PendingWorkError
from graderproof.run import Runner
from graderproof.sandbox import LocalSandbox
from graderproof.score import TaskResult, VariantResult
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


Kind = VariantKind | None


def queued(kind: VariantKind, a: Kind, b: Kind, n: int) -> VariantResult:
    v = Variant("t", kind, f"op{n}", "", {"f": str(n)}, {"w": 1})
    v = v.with_validation(Validation("witness", a)).with_validation(Validation("model", b))
    return VariantResult(v, True, 1)


def test_review_queue_lists_only_disagreements(tmp_path: Path) -> None:
    v, p = VariantKind.VIOLATING, VariantKind.PRESERVING
    results = [
        TaskResult(
            "b:t",
            "h1",
            Determinism.STABLE_PASS,
            3,
            1,
            [queued(v, v, v, 0), queued(v, v, p, 1), queued(p, p, None, 2), queued(v, p, p, 3)],
        )
    ]
    path = tmp_path / "queue" / "b.jsonl"
    assert write_review_queue(results, path) == 2
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [r["operator"] for r in rows] == ["op1", "op2"]
    assert rows[0]["task_hash"] == "h1" and "b:t" not in path.read_text()
    assert rows[1]["validations"][1] == {"validator": "model", "verdict": None, "evidence": ""}


def test_dirty_paths_reports_uncommitted_code(tmp_path: Path) -> None:
    assert dirty_paths(cwd=tmp_path) == ["<not a git checkout>"]
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "notes.md").write_text("n\n")
    subprocess.run([*git, "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run([*git, "commit", "-qm", "c"], cwd=tmp_path, check=True)
    assert dirty_paths(cwd=tmp_path) == []
    (tmp_path / "notes.md").write_text("changed\n")
    assert dirty_paths(cwd=tmp_path) == []  # outside src/, tools/, prereg/
    (tmp_path / "src" / "a.py").write_text("x = 2\n")
    (tmp_path / "src" / "new.py").write_text("y = 1\n")
    assert dirty_paths(cwd=tmp_path) == ["src/a.py", "src/new.py"]
    prov = provenance(AuditConfig(), {"x": 1})
    assert isinstance(prov["git_dirty"], bool) and len(prov["package_fingerprint"]) == 64
