"""Offline demo (``make demo``): audit the bundled demo tasks from recorded responses.

Model calls are disabled; every requirement extraction and model review is served
from the recorded, ingested responses in ``examples/demo/model_store``. The printed
report is deterministic (no timings, paths, or sandbox names) so that it can be
compared byte for byte with ``tests/golden/demo_output.txt``.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path

from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.audit import AuditConfig, Auditor
from graderproof.models import ModelClient
from graderproof.run import Runner
from graderproof.sandbox import LocalSandbox, Sandbox, best_sandbox
from graderproof.score import TaskResult, agreement
from graderproof.validate import ModelReviewer, RequirementExtractor
from graderproof.variants.model import ModelProposer

DEMO_CONFIG = AuditConfig(
    k=3, confirm_runs=2, seed=0, max_per_operator=6, max_total=40, replicates=1000
)


def demo_sandbox() -> Sandbox:
    """bwrap when it works, else a network namespace, else none (demo tasks are our own)."""
    return best_sandbox(require_write_isolation=False) or LocalSandbox()


def render(results: Sequence[TaskResult], evidence_witness: dict[str, str]) -> str:
    """Deterministic plain-text report."""
    lines = [
        f"graderproof demo: {len(results)} synthetic toybench demo tasks, recorded model responses"
    ]
    for r in results:
        lines.append("")
        lines.append(
            f"task {r.task_key}: grader on reference {r.determinism.value}; "
            f"{r.n_requirements} requirements ({r.n_requirements_invalid} dropped)"
        )
        for kind in ("violating", "preserving"):
            vs = [v for v in r.variants if v.variant.kind.value == kind]
            counted = [v for v in vs if v.counted]
            flagged = [
                v for v in counted if (v.survives if kind == "violating" else v.wrongly_rejected)
            ]
            verb = "accepted by grader" if kind == "violating" else "rejected by grader"
            lines.append(
                f"  {kind}: {len(vs)} generated, {len(counted)} validated, {len(flagged)} {verb}"
            )
            for v in sorted(flagged, key=lambda x: (x.variant.operator, x.variant.id))[:3]:
                lines.append(f"    {v.variant.operator}: {evidence_witness.get(v.variant.id, '')}")
        equivalent = r.n_equivalent
        score = "n/a" if r.mutation_score is None else f"{r.mutation_score:.2f}"
        flags = [
            n for n, f in (("FALSE ACCEPT", r.false_accept), ("FALSE REJECT", r.false_reject)) if f
        ]
        lines.append(
            f"  mutation score {score}; equivalent variants {equivalent}; "
            f"flags: {', '.join(flags) or 'none'}"
        )
    rate, agree, judged = agreement(results)
    fa = sum(r.false_accept for r in results)
    fr = sum(r.false_reject for r in results)
    lines.append("")
    n = len(results)
    lines.append(f"tasks with a false accept: {fa} of {n}; with a false reject: {fr} of {n}")
    rate_text = "n/a" if rate is None else f"{rate:.2f}"
    lines.append(f"validator agreement {rate_text} ({agree} of {judged} variants)")
    return "\n".join(lines) + "\n"


def run_demo(tasks_dir: Path, store: Path, ledger: Path, budget: Path) -> str:
    """Audit the demo tasks offline and return the report text."""
    adapter = ToybenchAdapter()
    tasks = adapter.load(tasks_dir)
    client = ModelClient(store=store, ledger=ledger, budget=budget, disabled=True)
    cache = Path(tempfile.mkdtemp(prefix="gp-demo-cache-"))
    try:
        runner = Runner(adapter, demo_sandbox(), cache_dir=cache)
        auditor = Auditor(
            adapter=adapter,
            runner=runner,
            extractor=RequirementExtractor(client),
            reviewer=ModelReviewer(client),
            config=DEMO_CONFIG,
            proposer=ModelProposer(client),
        )
        results, evidence = auditor.run(tasks)
    finally:
        shutil.rmtree(cache, ignore_errors=True)
    notes: dict[str, str] = {}
    for ev in evidence:
        for v in ev.variants:
            w = ev.witnesses.get(v.id)
            if w and w.get("type") == "requirement-broken":
                b = w["broken"][0]
                notes[v.id] = f"{b['requirement']} broken ({b['failed'][0]})"
            elif w:
                notes[v.id] = f"all {len(w['held'])} requirements still hold"
    return render(results, notes)
