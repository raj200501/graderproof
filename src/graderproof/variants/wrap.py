"""Entry-script wrappers that run the original solution, then transform its outputs.

Used by output-level operators in both directions: format-only rewrites
(:mod:`graderproof.variants.preserving`) and content mutations such as an extra or
missing line (:mod:`graderproof.variants.violating`), plus a harmless start delay.
The original entry script is kept unchanged as ``_gp_orig_<name>``.

The generated transform contains only the code for its own rewrite: no operator name,
no label, and no table of other rewrites, so a model reviewing the variant sees what
the change does and nothing about how graderproof classified it.
"""

from __future__ import annotations

from collections.abc import Mapping

TRANSFORM = "_gp_transform.py"

HELPERS: dict[str, str] = {
    "toggle_newline": (
        "def toggle_newline(text):\n"
        '    return text[:-1] if text.endswith("\\n") else text + "\\n"\n'
    ),
    "trailing_spaces": (
        "def trailing_spaces(text):\n"
        '    return "\\n".join(line + "  " if line else line for line in text.split("\\n"))\n'
    ),
    "reorder": (
        "def reorder(obj):\n"
        "    if isinstance(obj, dict):\n"
        "        return {k: reorder(obj[k]) for k in reversed(list(obj))}\n"
        "    if isinstance(obj, list):\n"
        "        return [reorder(x) for x in obj]\n"
        "    return obj\n"
    ),
    "floatify": (
        "def floatify(obj):\n"
        "    if isinstance(obj, bool):\n"
        "        return obj\n"
        "    if isinstance(obj, int):\n"
        "        return float(obj)\n"
        "    if isinstance(obj, dict):\n"
        "        return {k: floatify(v) for k, v in obj.items()}\n"
        "    if isinstance(obj, list):\n"
        "        return [floatify(x) for x in obj]\n"
        "    return obj\n"
    ),
    "rewrite_json": (
        "def rewrite_json(text, fn, indent):\n"
        '    end = "\\n" if text.endswith("\\n") else ""\n'
        "    return json.dumps(fn(json.loads(text)), indent=indent) + end\n"
    ),
    "extra_line": (
        "def extra_line(text):\n"
        '    return text + ("" if text.endswith("\\n") or not text else "\\n") + "extra\\n"\n'
    ),
    "drop_last_line": (
        "def drop_last_line(text):\n"
        '    lines = text.rstrip("\\n").split("\\n")\n'
        '    end = "\\n" if text.endswith("\\n") else ""\n'
        '    return "\\n".join(lines[:-1]) + (end if len(lines) > 1 else "")\n'
    ),
}

# operator -> (helpers, expression over ``text`` for each target file,
#              expression over ``out`` for the captured stdout)
REWRITES: dict[str, tuple[tuple[str, ...], str, str]] = {
    "none": ((), "text", "out"),
    "out-trailing-newline": (("toggle_newline",), "toggle_newline(text)", "out"),
    "out-trailing-spaces": (("trailing_spaces",), "trailing_spaces(text)", "out"),
    "out-json-key-order": (("reorder", "rewrite_json"), "rewrite_json(text, reorder, 2)", "out"),
    "out-json-indent": (("rewrite_json",), "rewrite_json(text, lambda o: o, 4)", "out"),
    "out-json-float": (("floatify", "rewrite_json"), "rewrite_json(text, floatify, 2)", "out"),
    "out-extra-line": (("extra_line",), "extra_line(text)", "out"),
    "out-drop-last-line": (("drop_last_line",), "drop_last_line(text)", "out"),
    "stdout-extra-line": (("extra_line",), "text", "extra_line(out)"),
    "stdout-drop-last-line": (
        ("drop_last_line",),
        "text",
        "drop_last_line(out) if out.strip() else out",
    ),
    "stdout-json-key-order": (
        ("reorder", "rewrite_json"),
        "text",
        "rewrite_json(out, reorder, None) if out.strip() else out",
    ),
    "stdout-code-fence": (
        (),
        "text",
        '"```json\\n" + out.rstrip("\\n") + "\\n```\\n" if out.strip() else out',
    ),
    "stdout-trailing-newline": (("toggle_newline",), "text", "toggle_newline(out) if out else out"),
}

MAIN = """

def transform_file(text):
    return {file_expr}


def transform_stdout(out):
    return {stdout_expr}


def main():
    captured = pathlib.Path(sys.argv[1])
    out = captured.read_text() if captured.exists() else ""
    for name in TARGETS:
        path = pathlib.Path(name)
        if path.is_file():
            path.write_text(transform_file(path.read_text()))
    sys.stdout.write(transform_stdout(out))


main()
"""

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


def transform_source(op: str, targets: list[str]) -> str:
    """The transform program for one rewrite, naming no operator.

    Raises:
        ValueError: for an unknown rewrite.
    """
    if op not in REWRITES:
        raise ValueError(f"unknown output rewrite {op!r}")
    helpers, file_expr, stdout_expr = REWRITES[op]
    head = (
        '"""Rewrite outputs after the original entry runs."""\n'
        "import json\nimport pathlib\nimport sys\n\n"
    )
    head += f"TARGETS = {targets!r}\n"
    body = "".join("\n\n" + HELPERS[h] for h in helpers)
    return head + body + MAIN.format(file_expr=file_expr, stdout_expr=stdout_expr)


def wrap_entry(
    files: Mapping[str, str], entry: str, op: str, targets: list[str], delay_s: float = 0.0
) -> dict[str, str]:
    """Solution files where ``entry`` runs the original, then the ``op`` rewrite.

    With ``delay_s`` the wrapper first sleeps that long (op ``none`` keeps outputs).
    """
    directory, _, name = entry.rpartition("/")
    prefix = f"{directory}/" if directory else ""
    orig = f"_gp_orig_{name}"
    out = dict(files)
    out[prefix + orig] = files[entry]
    out[prefix + TRANSFORM] = transform_source(op, targets)
    template = PY_WRAPPER if entry.endswith(".py") else SH_WRAPPER
    out[entry] = template.format(orig=orig, transform=TRANSFORM, delay=delay_s)
    return out
