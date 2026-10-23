"""Command-line interface: ``graderproof <command>``.

Commands not yet built exit with status 2 and say so, so that no caller can
mistake a placeholder for a result. ``audit`` exits with status 3 when model
responses are pending, after printing where the requests are.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

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
}
BUILT = {"audit", "demo", "models"}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with one subcommand per entry in :data:`COMMANDS`."""
    parser = argparse.ArgumentParser(prog="graderproof", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"graderproof {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, help_text in COMMANDS.items():
        p = sub.add_parser(name, help=help_text)
        if name in ("audit", "report", "repair", "lint", "card"):
            p.add_argument("target", nargs="?", help="path or dataset")
            p.add_argument("--adapter", default="toybench", help="task format adapter")
        if name == "audit":
            p.add_argument(
                "--out", type=Path, default=Path("runs/audit"), help="public artifact dir"
            )
            p.add_argument("--evidence", type=Path, help="evidence dir (default <out>/evidence)")
            p.add_argument("--cache", type=Path, default=Path("runs/cache"))
            p.add_argument("--public-task-ids", action="store_true")
            p.add_argument("--k", type=int, default=3)
            p.add_argument("--seed", type=int, default=0)
            p.add_argument("--max-total", type=int, default=40)
            p.add_argument(
                "--sandbox", choices=["auto", "bwrap", "unshare", "local"], default="auto"
            )
        if name in ("audit", "models", "demo"):
            p.add_argument("--store", type=Path, default=Path("artifacts/model_calls"))
            p.add_argument("--ledger", type=Path, default=Path("artifacts/usage/ledger.jsonl"))
            p.add_argument("--budget", type=Path, default=Path("budget.toml"))
        if name == "models":
            p.add_argument("action", choices=["pending", "ingest"])
        if name == "demo":
            p.add_argument("--tasks", type=Path, default=Path("examples/demo"))
            p.add_argument("--check", type=Path, help="fail if the output differs from this file")
    return parser


def cmd_audit(args: argparse.Namespace) -> int:
    """``graderproof audit``."""
    from graderproof.adapters.toybench import ToybenchAdapter
    from graderproof.audit import AuditConfig, Auditor, write_outputs
    from graderproof.models import ModelClient, PendingWorkError
    from graderproof.run import Runner
    from graderproof.sandbox import (
        BwrapSandbox,
        LocalSandbox,
        Sandbox,
        UnshareSandbox,
        best_sandbox,
    )
    from graderproof.validate import ModelReviewer, RequirementExtractor

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
    adapter = ToybenchAdapter()
    tasks = adapter.load(Path(args.target))
    client = ModelClient(store=args.store, ledger=args.ledger, budget=args.budget)
    config = AuditConfig(k=args.k, seed=args.seed, max_total=args.max_total)
    auditor = Auditor(
        adapter=adapter,
        runner=Runner(adapter, sandbox, cache_dir=args.cache),
        extractor=RequirementExtractor(client),
        reviewer=ModelReviewer(client),
        config=config,
    )
    try:
        results, evidence = auditor.run(tasks)
    except PendingWorkError as exc:
        for h in exc.hashes:
            print(f"pending {args.store / 'requests' / (h + '.json')}")
        print(f"graderproof audit: {len(exc.hashes)} model requests pending", file=sys.stderr)
        return PENDING
    meta = {"benchmark": Path(args.target).name, "adapter": args.adapter, "sandbox": sandbox.name}
    summary = write_outputs(
        results,
        evidence,
        args.out,
        args.evidence or args.out / "evidence",
        config,
        meta,
        args.public_task_ids,
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


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the process exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "audit":
        return cmd_audit(args)
    if args.command == "models":
        return cmd_models(args)
    if args.command == "demo":
        return cmd_demo(args)
    print(f"graderproof {args.command}: not built yet", file=sys.stderr)
    return NOT_BUILT


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
