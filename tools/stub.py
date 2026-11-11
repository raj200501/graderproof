#!/usr/bin/env python3
"""Placeholder for a make target that is not built yet. Always fails, loudly.

Usage: python3 tools/stub.py <target> <gate>
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    target = argv[1] if len(argv) > 1 else "?"
    gate = argv[2] if len(argv) > 2 else "?"
    print(f"make {target}: not built yet (needed for {gate})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
