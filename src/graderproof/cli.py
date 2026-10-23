"""Command-line interface: ``graderproof <command>``.

Commands not yet built exit with status 2 and say so, so that no caller can
mistake a placeholder for a result.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from graderproof import __version__

NOT_BUILT = 2

COMMANDS: dict[str, str] = {
    "audit": "measure false-accept and false-reject rates for a task set",
    "report": "render results and figures from banked artifacts",
    "repair": "synthesize and validate extra grader checks",
    "lint": "flag static grader smells",
    "card": "write a one-page grader card for a benchmark",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with one subcommand per entry in :data:`COMMANDS`."""
    parser = argparse.ArgumentParser(prog="graderproof", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"graderproof {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, help_text in COMMANDS.items():
        p = sub.add_parser(name, help=help_text)
        p.add_argument("target", nargs="?", help="path or dataset")
        p.add_argument("--adapter", help="task format adapter")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the process exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    print(f"graderproof {args.command}: not built yet", file=sys.stderr)
    return NOT_BUILT


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
