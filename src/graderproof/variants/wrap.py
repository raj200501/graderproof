"""Entry-script wrappers that run the original solution, then transform its outputs.

Used by output-level operators in both directions: format-only rewrites
(:mod:`graderproof.variants.preserving`) and content mutations such as an extra or
missing line (:mod:`graderproof.variants.violating`), plus a harmless start delay.
The original entry script is kept unchanged as ``_gp_orig_<name>``.
"""

from __future__ import annotations

from collections.abc import Mapping

TRANSFORM = "_gp_transform.py"

TRANSFORM_SRC = '''"""graderproof output transform (variant wrapper)."""
import json
import pathlib
import sys

OP = {op!r}
TARGETS = {targets!r}


def toggle_newline(text):
    return text[:-1] if text.endswith("\\n") else text + "\\n"


def trailing_spaces(text):
    return "\\n".join(line + "  " if line else line for line in text.split("\\n"))


def reorder(obj):
    if isinstance(obj, dict):
        return {{k: reorder(obj[k]) for k in reversed(list(obj))}}
    if isinstance(obj, list):
        return [reorder(x) for x in obj]
    return obj


def floatify(obj):
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int):
        return float(obj)
    if isinstance(obj, dict):
        return {{k: floatify(v) for k, v in obj.items()}}
    if isinstance(obj, list):
        return [floatify(x) for x in obj]
    return obj


def rewrite_json(text, fn, indent):
    end = "\\n" if text.endswith("\\n") else ""
    return json.dumps(fn(json.loads(text)), indent=indent) + end


def extra_line(text):
    return text + ("" if text.endswith("\\n") or not text else "\\n") + "extra\\n"


def drop_last_line(text):
    lines = text.rstrip("\\n").split("\\n")
    end = "\\n" if text.endswith("\\n") else ""
    return "\\n".join(lines[:-1]) + (end if len(lines) > 1 else "")


def transform_file(text):
    if OP == "out-extra-line":
        return extra_line(text)
    if OP == "out-drop-last-line":
        return drop_last_line(text)
    if OP == "out-trailing-newline":
        return toggle_newline(text)
    if OP == "out-trailing-spaces":
        return trailing_spaces(text)
    if OP == "out-json-key-order":
        return rewrite_json(text, reorder, 2)
    if OP == "out-json-indent":
        return rewrite_json(text, lambda o: o, 4)
    if OP == "out-json-float":
        return rewrite_json(text, floatify, 2)
    return text


def main():
    captured = pathlib.Path(sys.argv[1])
    out = captured.read_text() if captured.exists() else ""
    if OP.startswith("out-"):
        for name in TARGETS:
            path = pathlib.Path(name)
            if path.is_file():
                path.write_text(transform_file(path.read_text()))
    elif OP == "stdout-extra-line":
        out = extra_line(out)
    elif OP == "stdout-drop-last-line" and out.strip():
        out = drop_last_line(out)
    elif OP == "stdout-json-key-order" and out.strip():
        out = rewrite_json(out, reorder, None)
    elif OP == "stdout-code-fence" and out.strip():
        out = "```json\\n" + out.rstrip("\\n") + "\\n```\\n"
    elif OP == "stdout-trailing-newline" and out:
        out = toggle_newline(out)
    sys.stdout.write(out)


main()
'''

SH_WRAPPER = """#!/usr/bin/env bash
here="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
sleep {delay}
captured="$(mktemp)"
bash "$here/{orig}" "$@" > "$captured"
status=$?
python3 "$here/{transform}" "$captured"
rm -f "$captured"
exit $status
"""

PY_WRAPPER = """import pathlib
import subprocess
import sys
import tempfile
import time

here = pathlib.Path(__file__).resolve().parent
time.sleep({delay})
run = subprocess.run([sys.executable, str(here / {orig!r}), *sys.argv[1:]], stdout=subprocess.PIPE)
with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".out") as fh:
    fh.write(run.stdout)
subprocess.run([sys.executable, str(here / {transform!r}), fh.name])
pathlib.Path(fh.name).unlink()
sys.exit(run.returncode)
"""


def wrap_entry(
    files: Mapping[str, str], entry: str, op: str, targets: list[str], delay_s: float = 0.0
) -> dict[str, str]:
    """Solution files where ``entry`` runs the original, then the ``op`` transform.

    With ``delay_s`` the wrapper first sleeps that long (op ``none`` keeps outputs).
    """
    directory, _, name = entry.rpartition("/")
    prefix = f"{directory}/" if directory else ""
    orig = f"_gp_orig_{name}"
    out = dict(files)
    out[prefix + orig] = files[entry]
    out[prefix + TRANSFORM] = TRANSFORM_SRC.format(op=op, targets=targets)
    template = PY_WRAPPER if entry.endswith(".py") else SH_WRAPPER
    out[entry] = template.format(orig=orig, transform=TRANSFORM, delay=delay_s)
    return out
