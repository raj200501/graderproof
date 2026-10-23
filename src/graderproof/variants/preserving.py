"""Spec-preserving (metamorphic) operators.

* Output formatting for script tasks: trailing newline, trailing spaces, JSON key order,
  JSON indentation, integer-valued numbers written as floats, a Markdown code fence
  around printed output. These wrap the reference entry script: the original runs
  unchanged, then a small transform rewrites its outputs.
* Harmless renaming for Python: consistent renaming of local variables.
* Equivalent shell commands: ``echo`` written as ``printf``.
* Harmless ordering for tool trajectories: swapping adjacent independent calls and
  adding a read-only lookup.
* Harmless timing for script tasks: starting a few seconds later, well inside the
  task's time limit.

The label is a hypothesis. A format change can violate a task whose text demands an
exact format; validation decides.
"""

from __future__ import annotations

import ast
import builtins
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from graderproof.core import VariantKind
from graderproof.variants import Context, Operator, Proposal
from graderproof.variants import pysource as ps
from graderproof.variants.violating import (
    CONFIRM_RE,
    _dump,
    _files_with,
    _trajectories,
    bash_parses,
    shares_values,
    shell_command_lines,
)
from graderproof.variants.wrap import wrap_entry

P = VariantKind.PRESERVING
READONLY_RE = re.compile(r"^(get|list|find|search|lookup|read|view|show)_", re.I)


def output_formats(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Format-only rewrites of the reference's output files and stdout."""
    if ctx.kind != "script" or not ctx.entry or ctx.entry not in files:
        return
    text_outputs = [o for o in ctx.outputs if o not in ctx.json_outputs]
    json_outputs = list(ctx.json_outputs)
    plans: list[tuple[str, list[str], str]] = []
    if ctx.outputs:
        plans.append(("out-trailing-newline", list(ctx.outputs), "toggle trailing newline"))
    if text_outputs:
        plans.append(("out-trailing-spaces", text_outputs, "add trailing spaces"))
    if json_outputs:
        plans.append(("out-json-key-order", json_outputs, "reverse JSON key order"))
        plans.append(("out-json-indent", json_outputs, "re-indent JSON"))
        plans.append(("out-json-float", json_outputs, "write integers as floats"))
    if ctx.stdout_nonempty:
        plans.append(("stdout-trailing-newline", [], "toggle stdout trailing newline"))
    if ctx.stdout_json:
        plans.append(("stdout-json-key-order", [], "reverse printed JSON key order"))
        plans.append(("stdout-code-fence", [], "wrap printed JSON in a code fence"))
    for op, targets, desc in plans:
        yield Proposal(P, op, wrap_entry(files, ctx.entry, op, targets), desc, ",".join(targets))
    delay = harmless_delay(ctx.timeout_s)
    if delay > 0:
        files_d = wrap_entry(files, ctx.entry, "none", [], delay_s=delay)
        yield Proposal(P, "pre-delay", files_d, f"start {delay:g}s later", ctx.entry)


def harmless_delay(timeout_s: float) -> float:
    """A start delay well inside the task's time limit (0 when the limit is too short)."""
    if timeout_s < 4:
        return 0.0
    return float(min(3.0, round(timeout_s * 0.25, 1)))


def _function_locals(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    params = {a.arg for a in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]}
    if fn.args.vararg:
        params.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        params.add(fn.args.kwarg.arg)
    declared: set[str] = set()
    nested: set[str] = set()
    assigned: set[str] = set()
    for node in ast.walk(fn):
        if node is not fn and isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef
        ):
            nested |= {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        if isinstance(node, ast.Global | ast.Nonlocal):
            declared |= set(node.names)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
            assigned.add(node.id)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("locals", "vars", "eval", "exec")
        ):
            return set()
    return assigned - params - declared - nested - set(dir(builtins))


def py_rename_locals(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Rename every local variable of one function consistently."""
    for path, src in files.items():
        if ctx.languages.get(path) != "python":
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for fn in [
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
        ]:
            names = _function_locals(fn)
            if not names:
                continue
            spans = sorted(
                (
                    ps.span(src, n)
                    for n in ast.walk(fn)
                    if isinstance(n, ast.Name) and n.id in names
                ),
                reverse=True,
            )
            new = src
            for start, end in spans:
                old = new.encode("utf-8")[start:end].decode("utf-8")
                new = ps.replace(new, start, end, f"{old}_gp")
            if new != src and ps.compiles(new):
                yield Proposal(
                    P,
                    "py-rename-locals",
                    _files_with(files, path, new),
                    f"rename locals of {fn.name}: {', '.join(sorted(names))}",
                    f"{path}:{fn.lineno}",
                )


ECHO_RE = re.compile(r"^(\s*)echo\s+(\"[^\"$`\\]*\"|'[^']*')(\s*(?:>>?\s*\S+)?\s*)$")


def sh_echo_printf(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Write one ``echo "text"`` as the equivalent ``printf '%s\\n' "text"``."""
    for path, src in files.items():
        if ctx.languages.get(path) != "shell":
            continue
        lines = src.splitlines(keepends=True)
        for i in shell_command_lines(src):
            body = lines[i].rstrip("\n")
            m = ECHO_RE.match(body)
            if not m:
                continue
            line = f"{m.group(1)}printf '%s\\n' {m.group(2)}{m.group(3)}" + (
                "\n" if lines[i].endswith("\n") else ""
            )
            new = "".join([*lines[:i], line, *lines[i + 1 :]])
            if bash_parses(new):
                yield Proposal(
                    P,
                    "sh-echo-printf",
                    _files_with(files, path, new),
                    f"echo -> printf on line {i + 1}",
                    f"{path}:{i + 1}",
                )


def traj_swap_independent(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Swap two adjacent calls with no shared argument values and no confirmation role."""
    for path, calls in _trajectories(files, ctx):
        for i in range(len(calls) - 1):
            a, b = calls[i], calls[i + 1]
            tools = str(a.get("tool", "")) + str(b.get("tool", ""))
            if a != b and not shares_values(a, b) and not CONFIRM_RE.search(tools):
                new = [*calls[:i], b, a, *calls[i + 2 :]]
                yield Proposal(
                    P,
                    "traj-swap-independent",
                    _files_with(files, path, _dump(new)),
                    f"swap calls {i} and {i + 1}",
                    f"{path}#{i}",
                )


def traj_add_readonly(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Repeat one read-only lookup call at the start of the trajectory."""
    for path, calls in _trajectories(files, ctx):
        for i, call in enumerate(calls):
            if READONLY_RE.match(str(call.get("tool", ""))):
                new: list[dict[str, Any]] = [dict(call), *calls]
                yield Proposal(
                    P,
                    "traj-add-readonly",
                    _files_with(files, path, _dump(new)),
                    f"extra lookup {call.get('tool')}",
                    f"{path}#{i}",
                )


def json_like(text: str) -> bool:
    """Whether ``text`` parses as a JSON object or array."""
    try:
        return isinstance(json.loads(text), dict | list)
    except ValueError:
        return False


ALL: tuple[Operator, ...] = (
    output_formats,
    py_rename_locals,
    sh_echo_printf,
    traj_swap_independent,
    traj_add_readonly,
)
