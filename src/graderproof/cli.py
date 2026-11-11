"""Command-line interface: ``graderproof <command>``.

Commands not yet built exit with status 2 and say so, so that no caller can
mistake a placeholder for a result. ``audit`` and ``repair`` exit with status 3 when
model responses are pending, after printing where the requests are.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from graderproof import __version__

NOT_BUILT = 2
PENDING = 3

COMMANDS: dict[str, str] = {
    "audit": "measure false-accept and false-reject rates for a task set",
    "report": "render results and figures from banked artifacts",
    "repair": "synthesize and validate extra grader checks",
    "lint": "flag static grader smells",
    "card": "write a one-page grader card for a benchmark",
    "demo": "run the offline demo on the bundled tasks",
    "models": "list pending model requests or ingest responses",
    "e0-score": "score E0 toybench flags against the planted labels",
}
BUILT = {"audit", "demo", "models", "e0-score", "repair"}


def _target_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("target", nargs="?", help="path or dataset")
    p.add_argument("--adapter", default="toybench", help="task format adapter")


def _model_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--store", type=Path, default=Path("artifacts/model_calls"))
    p.add_argument("--ledger", type=Path, default=Path("artifacts/usage/ledger.jsonl"))
    p.add_argument("--budget", type=Path, default=Path("budget.toml"))


def _env_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="environment passed to sandboxed task scripts (pinned third-party paths)",
    )


def _audit_args(p: argparse.ArgumentParser) -> None:
    _target_args(p)
    _env_args(p)
    _model_args(p)
    p.add_argument("--out", type=Path, default=Path("runs/audit"), help="public artifact dir")
    p.add_argument("--evidence", type=Path, help="evidence dir (default <out>/evidence)")
    p.add_argument("--cache", type=Path, default=Path("runs/cache"))
    p.add_argument("--public-task-ids", action="store_true")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--max-total", type=int, default=40)
    p.add_argument("--sandbox", choices=["auto", "bwrap", "unshare", "local"], default="auto")
    p.add_argument("--no-propose", action="store_true", help="skip model-proposed variants")
    p.add_argument("--max-per-operator", type=int, default=6)
    p.add_argument("--confirm-runs", type=int, default=2)
    p.add_argument("--replicates", type=int, default=2000)
    p.add_argument("--extract-batch", type=int, default=8, help="tasks per extraction call")
    p.add_argument("--propose-batch", type=int, default=4, help="tasks per proposal call")
    p.add_argument("--review-batch", type=int, default=25, help="variants per review call")
    p.add_argument("--confirmatory", action="store_true", help="a preregistered run")
    p.add_argument("--prereg", help="the preregistration this run follows (prereg/NNNN-*.md)")
    p.add_argument("--review-queue", type=Path, default=Path("private/review_queue"))
    p.add_argument("--category", help="benchmark category, for example tool-use or coding")
    p.add_argument(
        "--substitute-for",
        metavar="NAME=DECISION",
        help="the benchmark this one replaces and the DECISIONS.md entry that justifies it",
    )
    p.add_argument(
        "--sample",
        type=Path,
        help="committed sample file (tools/sample.py); the audit must cover exactly its tasks",
    )


def _repair_args(p: argparse.ArgumentParser) -> None:
    _target_args(p)
    _env_args(p)
    _model_args(p)
    p.add_argument("--evidence", type=Path, required=True, help="audit evidence dir")
    p.add_argument("--out", type=Path, required=True, help="E4 artifact dir")
    p.add_argument("--benchmark", required=True)
    p.add_argument("--private", action="store_true", help="third-party tasks not fixed upstream")
    p.add_argument("--manifest", type=Path, default=Path("outbound/patches/MANIFEST.json"))
    p.add_argument("--cache", type=Path, default=Path("runs/cache"))
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--seed", type=int, default=0, help="the original audit seed")
    p.add_argument("--generalize", action="store_true", help="run the post-repair batch")
    p.add_argument("--propose-batch", type=int, default=4)
    p.add_argument("--review-batch", type=int, default=25)


def _e0_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--audit", type=Path, default=Path("artifacts/e0"))
    p.add_argument("--labels", type=Path, default=Path("toybench/labels.json"))
    p.add_argument("--labels-sha256", type=Path, default=Path("toybench/labels.sha256"))
    p.add_argument("--adjudication", type=Path, default=Path("artifacts/e0/adjudication.json"))
    p.add_argument("--prereg", default="prereg/0001-e0-tool-validity.md")
    p.add_argument("--out", type=Path, default=Path("artifacts/e0/results.json"))
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--replicates", type=int, default=2000)


def _models_args(p: argparse.ArgumentParser) -> None:
    _model_args(p)
    p.add_argument("action", choices=["pending", "ingest"])


def _demo_args(p: argparse.ArgumentParser) -> None:
    _model_args(p)
    p.add_argument("--tasks", type=Path, default=Path("examples/demo"))
    p.add_argument("--check", type=Path, help="fail if the output differs from this file")


ARGS: dict[str, Callable[[argparse.ArgumentParser], None]] = {
    "audit": _audit_args,
    "repair": _repair_args,
    "e0-score": _e0_args,
    "models": _models_args,
    "demo": _demo_args,
    "report": _target_args,
    "lint": _target_args,
    "card": _target_args,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with one subcommand per entry in :data:`COMMANDS`."""
    parser = argparse.ArgumentParser(prog="graderproof", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"graderproof {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, help_text in COMMANDS.items():
        ARGS[name](sub.add_parser(name, help=help_text))
    return parser


def confirmatory_refusal(
    args: argparse.Namespace, dirty: Sequence[str], isolated: bool = True
) -> str:
    """Why a confirmatory run may not start (empty when it may).

    It needs an existing preregistration, no uncommitted changes to the code or tasks
    (``dirty``), and a sandbox that isolates writes and hides private paths
    (``isolated``; DECISIONS.md D25, D28).
    """
    prereg = str(args.prereg or "")
    if not prereg.startswith("prereg/") or not Path(prereg).is_file():
        return "a confirmatory run needs --prereg naming an existing prereg/NNNN-*.md"
    if dirty:
        return f"refusing a confirmatory run on uncommitted changes: {list(dirty)[:5]}"
    if not isolated:
        return "a confirmatory run needs a write-isolating sandbox (bwrap or docker)"
    return ""


def sample_check(sample: Path, benchmark: str, task_ids: Sequence[str]) -> tuple[int, str]:
    """``(population, refusal)``: the frame size, and why the tasks differ from the sample.

    ``sample`` is the output of tools/sample.py; ``refusal`` is empty when ``task_ids``
    are exactly the sampled tasks of ``benchmark``.
    """
    try:
        data = json.loads(sample.read_text(encoding="utf-8"))
        entry = data["benchmarks"][benchmark]
        expected = sorted(str(t) for t in entry["tasks"])
        population = int(entry["frame"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return 0, f"cannot read the sample of {benchmark!r} from {sample}: {exc}"
    got = sorted(task_ids)
    if got != expected:
        missing = sorted(set(expected) - set(got))
        extra = sorted(set(got) - set(expected))
        return population, f"tasks differ from the sample: missing {missing[:3]}, extra {extra[:3]}"
    return population, ""


def task_refusal(
    args: argparse.Namespace, task_ids: Sequence[str], third_party: bool
) -> tuple[int, str]:
    """``(population, refusal)`` for the loaded tasks.

    With ``--sample`` the tasks must be exactly the committed sample of the target's
    benchmark, and the population is the sample's frame; a confirmatory audit of a
    third-party benchmark must name its sample.
    """
    if args.sample is not None:
        return sample_check(args.sample, Path(args.target).name, task_ids)
    if args.confirmatory and third_party:
        return len(task_ids), "a confirmatory third-party audit needs --sample"
    return len(task_ids), ""


def parse_substitute(spec: str | None) -> dict[str, str] | None:
    """``NAME=DECISION`` to ``{"benchmark": NAME, "decision": DECISION}`` (None if unset)."""
    if not spec:
        return None
    name, sep, decision = spec.partition("=")
    if not sep or not name or not decision:
        raise SystemExit(f"--substitute-for expects NAME=DECISION, got {spec!r}")
    return {"benchmark": name, "decision": decision}


def parse_env(pairs: Sequence[str]) -> dict[str, str]:
    """``KEY=VALUE`` strings to a mapping."""
    out: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise SystemExit(f"--env expects KEY=VALUE, got {pair!r}")
        out[key] = value
    return out


def report_pending(command: str, store: Path, hashes: Sequence[str]) -> int:
    """Print pending request paths; returns :data:`PENDING`."""
    for h in hashes:
        print(f"pending {store / 'requests' / (h + '.json')}")
    print(f"graderproof {command}: {len(hashes)} model requests pending", file=sys.stderr)
    return PENDING


def cmd_audit(args: argparse.Namespace) -> int:
    """``graderproof audit``."""
    from graderproof.adapters.toybench import ToybenchAdapter
    from graderproof.audit import AuditConfig, Auditor, dirty_paths, write_outputs
    from graderproof.models import ModelClient, PendingWorkError
    from graderproof.run import Runner, sandbox_version
    from graderproof.sandbox import (
        BwrapSandbox,
        LocalSandbox,
        Sandbox,
        UnshareSandbox,
        best_sandbox,
    )
    from graderproof.validate import (
        EXTRACT_PROMPT_VERSION,
        REVIEW_PROMPT_VERSION,
        ModelReviewer,
        RequirementExtractor,
    )
    from graderproof.variants.model import PROPOSE_PROMPT_VERSION, ModelProposer

    if args.adapter != "toybench" or args.target is None:
        print(f"graderproof audit: adapter {args.adapter!r} not built yet", file=sys.stderr)
        return NOT_BUILT
    choice: dict[str, Sandbox | None] = {
        "bwrap": BwrapSandbox(),
        "unshare": UnshareSandbox(),
        "local": LocalSandbox(),
        "auto": best_sandbox(require_write_isolation=False),
    }
    sandbox = choice[args.sandbox]
    if sandbox is None:
        print("graderproof audit: no sandbox available", file=sys.stderr)
        return 1
    if args.confirmatory:
        refusal = confirmatory_refusal(
            args,
            dirty_paths(("src", "tools", "prereg", str(args.target))),
            isolated=sandbox.isolates_writes,
        )
        if refusal:
            print(f"graderproof audit: {refusal}", file=sys.stderr)
            return 1
    adapter = ToybenchAdapter(extra_env=parse_env(args.env))
    tasks = adapter.load(Path(args.target))
    third_party = any(not t.metadata.get("trusted_local") for t in tasks)
    substitute = parse_substitute(args.substitute_for)
    population, refusal = task_refusal(args, [t.id for t in tasks], third_party)
    if refusal:
        print(f"graderproof audit: {refusal}", file=sys.stderr)
        return 1
    client = ModelClient(store=args.store, ledger=args.ledger, budget=args.budget)
    config = AuditConfig(
        k=args.k,
        confirm_runs=args.confirm_runs,
        seed=args.seed,
        max_per_operator=args.max_per_operator,
        max_total=args.max_total,
        replicates=args.replicates,
    )
    auditor = Auditor(
        adapter=adapter,
        runner=Runner(adapter, sandbox, cache_dir=args.cache),
        extractor=RequirementExtractor(client, batch_size=args.extract_batch),
        reviewer=ModelReviewer(client, batch_size=args.review_batch),
        config=config,
        proposer=None if args.no_propose else ModelProposer(client, batch_size=args.propose_batch),
    )
    try:
        results, evidence = auditor.run(tasks)
    except PendingWorkError as exc:
        return report_pending("audit", args.store, exc.hashes)
    benchmark = Path(args.target).name
    default_evidence = (
        (Path("private/evidence") / benchmark) if third_party else args.out / "evidence"
    )
    out_evidence = args.evidence or default_evidence
    meta = {
        "benchmark": benchmark,
        "adapter": args.adapter,
        "confirmatory": bool(args.confirmatory),
        "prereg": args.prereg,
        "third_party": third_party,
        "category": args.category,
        "substitute_for": substitute,
        "n_tasks_population": population,
        "sample": None if args.sample is None else args.sample.as_posix(),
        "sample_sha256": (
            None if args.sample is None else hashlib.sha256(args.sample.read_bytes()).hexdigest()
        ),
        "sandbox": sandbox.name,
        "sandbox_version": sandbox_version(sandbox.name),
        "models": client.served_models(),
        "paths": {
            "target": str(args.target),
            "cache": str(args.cache),
            "evidence": str(out_evidence),
            "ledger": str(args.ledger),
            "store": str(args.store),
        },
        "model_store": args.store.as_posix(),
        "prompts": {
            "requirements": EXTRACT_PROMPT_VERSION,
            "propose": None if args.no_propose else PROPOSE_PROMPT_VERSION,
            "review": REVIEW_PROMPT_VERSION,
        },
        "batches": {
            "requirements": args.extract_batch,
            "propose": args.propose_batch,
            "review": args.review_batch,
        },
    }
    summary = write_outputs(
        results,
        evidence,
        args.out,
        out_evidence,
        config,
        meta,
        args.public_task_ids,
        review_queue=args.review_queue,
    )
    print(json.dumps(summary["aggregate"], indent=2, sort_keys=True))
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    """``graderproof models pending|ingest``."""
    from graderproof.models import CapExceededError, ModelClient, load_caps

    client = ModelClient(store=args.store, ledger=args.ledger, budget=args.budget, disabled=True)
    pending = client.pending()
    if args.action == "pending":
        cap = load_caps(args.budget)["single_call"]
        used = client.used_today("single_call")
        for p in pending:
            answered = (args.store / "responses" / p.name).exists()
            print(f"{p} {'answered' if answered else 'unanswered'}")
        print(f"{len(pending)} pending; single calls today {used} of {cap}")
        return 0
    status = 0
    for p in pending:
        if not (args.store / "responses" / p.name).exists():
            continue
        try:
            row = client.ingest(p.stem)
        except (ValueError, CapExceededError) as exc:
            print(f"not ingested {p.stem[:12]}: {exc}", file=sys.stderr)
            status = 1
            continue
        print(f"ingested {p.stem[:12]} {row['purpose']} {row['n_items']} items ({row['model']})")
    return status


def cmd_demo(args: argparse.Namespace) -> int:
    """``graderproof demo``."""
    from graderproof.demo import run_demo
    from graderproof.models import ModelCallBlockedError

    try:
        text = run_demo(args.tasks, args.tasks / "model_store", args.ledger, args.budget)
    except ModelCallBlockedError as exc:
        print(f"graderproof demo: recorded response missing: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(text)
    if args.check is not None:
        golden = args.check.read_text(encoding="utf-8")
        if text != golden:
            diff = difflib.unified_diff(
                golden.splitlines(True), text.splitlines(True), "golden", "demo"
            )
            sys.stderr.write("graderproof demo: output differs from golden\n" + "".join(diff))
            return 1
    return 0


def load_task_dirs(root: Path, adapter: Any) -> tuple[dict[str, Any], dict[str, Path]]:
    """Tasks under ``root`` keyed by task key, and their directories."""
    tasks: dict[str, Any] = {}
    dirs: dict[str, Path] = {}
    for d in sorted(root.iterdir()):
        if (d / "task.toml").exists():
            task = adapter.load_one(d, root.name)
            tasks[task.key], dirs[task.key] = task, d
    return tasks, dirs


def _repair_all(
    args: argparse.Namespace,
    tasks: dict[str, Any],
    dirs: dict[str, Path],
    docs: dict[str, Any],
    adapter: Any,
    runner_for: Callable[[Any], Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Build, validate, and write every repair; returns repaired, unrepaired, scores, built."""
    from graderproof import repair

    public_root = Path("outbound/patches") / args.benchmark
    private_root = Path("private/outbound/patches") / args.benchmark
    repaired: list[dict[str, Any]] = []
    unrepaired: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []
    built: dict[str, Any] = {}
    for key, doc in docs.items():
        task, task_dir = tasks[key], dirs[key]
        result = repair.build_repair(task, task_dir, doc)
        if result is not None:
            repair.validate_repair(result, task_dir, doc, adapter, runner_for, args.k)
        scores.append({"task_hash": task.key_hash, **repair.mutation_scores(doc, result)})
        if result is None:
            continue
        if not result.accepted:
            reason = result.validation.get("reason") or "acceptance criteria not met"
            unrepaired.append({"task_hash": task.key_hash, "reason": reason})
            continue
        paths = repair.write_patch(
            result, args.benchmark, task.id, public_root, private_root, not args.private
        )
        repaired.append({"task_hash": task.key_hash, "public": not args.private, **paths})
        built[key] = result
    return repaired, unrepaired, scores, built


def _generalize(
    args: argparse.Namespace,
    tasks: dict[str, Any],
    dirs: dict[str, Path],
    docs: dict[str, Any],
    built: dict[str, Any],
    adapter: Any,
    runner_for: Callable[[Any], Any],
) -> dict[str, Any] | int:
    """The post-repair batch: fresh variants the repairs never saw (or PENDING)."""
    from graderproof import repair
    from graderproof.audit import AuditConfig, Auditor
    from graderproof.models import ModelClient, PendingWorkError
    from graderproof.validate import ModelReviewer, RequirementExtractor
    from graderproof.variants.model import ModelProposer

    client = ModelClient(store=args.store, ledger=args.ledger, budget=args.budget)
    config = AuditConfig(k=args.k, seed=args.seed + 1000)
    fresh = Auditor(
        adapter=adapter,
        runner=runner_for(adapter),
        extractor=RequirementExtractor(client),
        reviewer=ModelReviewer(client, batch_size=args.review_batch),
        config=config,
        proposer=ModelProposer(client, batch_size=args.propose_batch, round=2),
    )
    order = sorted(built)
    try:
        fresh_results, fresh_evidence = fresh.run([tasks[k] for k in order])
    except PendingWorkError as exc:
        return report_pending("repair", args.store, exc.hashes)
    rows: list[dict[str, Any]] = []
    for key, fr, fe in zip(order, fresh_results, fresh_evidence, strict=True):
        res = repair.evaluate_fresh(
            docs[key], fe.to_dict(fr), built[key], dirs[key], adapter, runner_for
        )
        rows.extend({"task_hash": tasks[key].key_hash, **r} for r in res["rows"])
    return {
        "ran": True,
        "seed": config.seed,
        "proposal_round": 2,
        **repair.generalization_counts(rows),
        "rows": rows,
    }


def cmd_repair(args: argparse.Namespace) -> int:
    """``graderproof repair``: E4 repairs, validation, patches, and the post-repair batch."""
    from graderproof import repair
    from graderproof.adapters.toybench import ToybenchAdapter
    from graderproof.audit import AuditConfig, provenance
    from graderproof.run import Runner
    from graderproof.sandbox import BwrapSandbox

    adapter = ToybenchAdapter(extra_env=parse_env(args.env))
    tasks, dirs = load_task_dirs(Path(args.target), adapter)
    docs: dict[str, Any] = {}
    for f in sorted(args.evidence.glob("*.json")):
        doc = json.loads(f.read_text())
        if doc.get("task") in tasks:
            docs[doc["task"]] = doc
    sandbox = BwrapSandbox()

    def runner_for(a: Any) -> Runner:
        return Runner(a, sandbox, cache_dir=args.cache)

    repaired, unrepaired, scores, built = _repair_all(args, tasks, dirs, docs, adapter, runner_for)
    if args.private and repaired:
        files = [str(p) for r in repaired for p in (r["patch"], r["validation_log"])]
        repair.update_manifest(args.manifest, files, Path.cwd())
    generalization: dict[str, Any] = {"ran": False}
    if args.generalize and built:
        gen = _generalize(args, tasks, dirs, docs, built, adapter, runner_for)
        if isinstance(gen, int):
            return gen
        generalization = gen
    summary = {
        "schema": "graderproof.e4/1",
        "ran": True,
        "benchmark": args.benchmark,
        "public": not args.private,
        "tasks_with_survivors": sum(1 for d in docs.values() if repair.survivors(d)),
        "repaired": repaired,
        "unrepaired": unrepaired,
        "mutation_scores": scores,
        "generalization": generalization,
        "provenance": provenance(AuditConfig(k=args.k, seed=args.seed)),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    counts = {"with_survivors": summary["tasks_with_survivors"], "repaired": len(repaired)}
    print(json.dumps({**counts, "unrepaired": len(unrepaired)}))
    return 0


def cmd_e0_score(args: argparse.Namespace) -> int:
    """``graderproof e0-score``: bank artifacts/e0/results.json from the audit and labels."""
    from graderproof import e0
    from graderproof.audit import AuditConfig, provenance

    committed = args.labels_sha256.read_text().split()[:1] if args.labels_sha256.exists() else []
    actual = hashlib.sha256(args.labels.read_bytes()).hexdigest()
    if committed != [actual]:
        print("graderproof e0-score: labels do not match their committed hash", file=sys.stderr)
        return 1
    lines = (args.audit / "tasks.jsonl").read_text().splitlines()
    rows = [json.loads(x) for x in lines if x.strip()]
    labels = json.loads(args.labels.read_text())["tasks"]
    adjudication = json.loads(args.adjudication.read_text()) if args.adjudication.exists() else {}
    ruled = adjudication.get("tasks", {})
    try:
        scores = e0.task_scores(rows, labels, ruled)
    except ValueError as exc:
        print(f"graderproof e0-score: {exc}", file=sys.stderr)
        return 1
    pending = [s.task for s in e0.needs_adjudication(scores) if s.task not in ruled]
    if pending:
        print(f"graderproof e0-score: flags awaiting adjudication: {pending}", file=sys.stderr)
        return 1
    result = {
        "schema": "graderproof.e0/1",
        "prereg": args.prereg,
        "labels_path": args.labels.as_posix(),
        "labels_sha256_path": args.labels_sha256.as_posix(),
        "audit_dir": args.audit.as_posix(),
        "bootstrap": {"seed": args.seed, "B": args.replicates, "alpha": 0.05},
        **e0.score(scores, args.seed, args.replicates),
        "tasks": [s.row() for s in scores],
        "provenance": provenance(AuditConfig(seed=args.seed, replicates=args.replicates)),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("recall", "precision", "precision_unadjudicated")}))
    return 0


HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "audit": cmd_audit,
    "models": cmd_models,
    "demo": cmd_demo,
    "e0-score": cmd_e0_score,
    "repair": cmd_repair,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the process exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    handler = HANDLERS.get(args.command)
    if handler is None:
        print(f"graderproof {args.command}: not built yet", file=sys.stderr)
        return NOT_BUILT
    return handler(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
