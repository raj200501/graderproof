"""Spec-violating operators: classical mutation of Python, shell, and tool trajectories.

Each operator yields one :class:`~graderproof.variants.Proposal` per mutation site.
Python operators edit only the span of the node they change; shell operators edit one
line; trajectory operators edit one call. Proposals that no longer parse are dropped.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from graderproof.core import VariantKind
from graderproof.variants import Context, Operator, Proposal
from graderproof.variants import pysource as ps

V = VariantKind.VIOLATING
SKIP_STMTS = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Import,
    ast.ImportFrom,
    ast.Pass,
    ast.Global,
    ast.Nonlocal,
)
COMPARE_SWAP: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}
ARITH_SWAP: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Mult,
    ast.Mod: ast.FloorDiv,
}
CONFIRM_RE = re.compile(r"confirm|verify|authenticat|approve|consent|check", re.I)


def _files_with(files: Mapping[str, str], path: str, text: str) -> dict[str, str]:
    out = dict(files)
    out[path] = text
    return out


def _python_files(files: Mapping[str, str], ctx: Context) -> Iterator[tuple[str, str, ast.Module]]:
    for path, src in files.items():
        if ctx.languages.get(path) != "python":
            continue
        try:
            yield path, src, ast.parse(src)
        except SyntaxError:
            continue


def _emit(
    files: Mapping[str, str], path: str, new: str | None, op: str, desc: str, target: str
) -> Iterator[Proposal]:
    if new is not None and new != files[path] and ps.compiles(new):
        yield Proposal(V, op, _files_with(files, path, new), desc, target)


def py_statement_delete(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Delete one statement (replaced by ``pass``): a skipped step."""
    for path, src, tree in _python_files(files, ctx):
        par = ps.parents(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.stmt) or isinstance(node, SKIP_STMTS):
                continue
            if ps.is_docstring(node, par.get(id(node))):
                continue
            new = ps.replace_statement_lines(src, node, "pass")
            yield from _emit(
                files,
                path,
                new,
                "py-stmt-delete",
                f"delete line {node.lineno}",
                f"{path}:{node.lineno}",
            )


def _new_constants(value: object) -> list[object]:
    if isinstance(value, bool):
        return [not value]
    if isinstance(value, int):
        return [value + 1, 0 if value != 0 else -1]
    if isinstance(value, float):
        return [value + 1.0]
    if isinstance(value, str) and value:
        out: list[object] = [""]
        if re.fullmatch(r"[\w./-]+\.\w+", value):
            out.append(value + ".bak")
        return out
    return []


def py_constant(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Change one literal: numbers off by one, strings emptied, file names retargeted."""
    for path, src, tree in _python_files(files, ctx):
        par = ps.parents(tree)
        in_fstring = {
            id(n) for j in ast.walk(tree) if isinstance(j, ast.JoinedStr) for n in ast.walk(j)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or id(node) in in_fstring:
                continue
            holder = par.get(id(node))
            if holder is not None and ps.is_docstring(holder, par.get(id(holder))):
                continue
            for new_value in _new_constants(node.value):
                op = "py-target-file" if str(new_value).endswith(".bak") else "py-constant"
                new = ps.replace_node(src, node, repr(new_value))
                yield from _emit(
                    files,
                    path,
                    new,
                    op,
                    f"{node.value!r} -> {new_value!r}",
                    f"{path}:{node.lineno}",
                )


def py_compare(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Change one comparison operator (boundary and equality mutations)."""
    for path, src, tree in _python_files(files, ctx):
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or len(node.ops) != 1:
                continue
            swap = COMPARE_SWAP.get(type(node.ops[0]))
            if swap is None:
                continue
            left, right = ps.node_source(src, node.left), ps.node_source(src, node.comparators[0])
            text = f"{left} {_cmp_symbol(swap)} {right}"
            new = ps.replace_node(src, node, text)
            yield from _emit(
                files, path, new, "py-compare", f"comparison -> {text}", f"{path}:{node.lineno}"
            )


def _cmp_symbol(op: type[ast.cmpop]) -> str:
    return {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}[
        op
    ]


def py_negate(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Negate one ``if``/``while``/conditional-expression test."""
    for path, src, tree in _python_files(files, ctx):
        for node in ast.walk(tree):
            if isinstance(node, ast.If | ast.While | ast.IfExp):
                test = node.test
                text = f"not ({ps.node_source(src, test)})"
                new = ps.replace_node(src, test, text)
                yield from _emit(
                    files, path, new, "py-negate", f"negate {text[5:-1]}", f"{path}:{test.lineno}"
                )


def py_arith(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Swap one arithmetic operator."""
    symbols = {
        ast.Add: "+",
        ast.Sub: "-",
        ast.Mult: "*",
        ast.Div: "/",
        ast.FloorDiv: "//",
        ast.Mod: "%",
    }
    for path, src, tree in _python_files(files, ctx):
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp):
                continue
            swap = ARITH_SWAP.get(type(node.op))
            if swap is None:
                continue
            left, right = ps.node_source(src, node.left), ps.node_source(src, node.right)
            text = f"({left}) {symbols[swap]} ({right})"
            new = ps.replace_node(src, node, text)
            yield from _emit(
                files,
                path,
                new,
                "py-arith",
                f"operator -> {symbols[swap]}",
                f"{path}:{node.lineno}",
            )


def py_boolop(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Swap ``and`` and ``or``."""
    for path, src, tree in _python_files(files, ctx):
        for node in ast.walk(tree):
            if not isinstance(node, ast.BoolOp):
                continue
            word = " or " if isinstance(node.op, ast.And) else " and "
            text = word.join(f"({ps.node_source(src, v)})" for v in node.values)
            new = ps.replace_node(src, node, text)
            yield from _emit(
                files, path, new, "py-boolop", f"boolean ->{word.strip()}", f"{path}:{node.lineno}"
            )


def py_return_none(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Replace one returned value with ``None``."""
    for path, src, tree in _python_files(files, ctx):
        for node in ast.walk(tree):
            if isinstance(node, ast.Return) and node.value is not None:
                if isinstance(node.value, ast.Constant) and node.value.value is None:
                    continue
                new = ps.replace_node(src, node.value, "None")
                yield from _emit(
                    files, path, new, "py-return-none", "return None", f"{path}:{node.lineno}"
                )


def py_loop_skip_last(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Skip the last item of one ``for`` loop: a partial output."""
    for path, src, tree in _python_files(files, ctx):
        for node in ast.walk(tree):
            if isinstance(node, ast.For):
                text = f"list({ps.node_source(src, node.iter)})[:-1]"
                new = ps.replace_node(src, node.iter, text)
                yield from _emit(
                    files, path, new, "py-partial-loop", "skip last item", f"{path}:{node.lineno}"
                )


# ------------------------------------------------------------------------ shell

CONTROL_RE = re.compile(
    r"^(if|then|else|elif|fi|for|while|until|do|done|case|esac|function|\{|\}|\)|;;)\b|^\w+\s*\(\)\s*\{?$"
)
HEREDOC_RE = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
NUMBER_RE = re.compile(r"(?<![\w.<>&-])(\d+)(?![\w.<>&])")
REDIRECT_RE = re.compile(r"(?<![0-9&])(>>?)\s*(\"[^\"]+\"|'[^']+'|[^\s;|&<>]+)")


def shell_command_lines(src: str) -> list[int]:
    """Indices of simple command lines (not comments, control words, or heredoc bodies)."""
    lines = src.splitlines()
    out: list[int] = []
    terminator: str | None = None
    for i, line in enumerate(lines):
        s = line.strip()
        if terminator is not None:
            if s == terminator:
                terminator = None
            continue
        m = HEREDOC_RE.search(line)
        if m:
            terminator = m.group(1)
        if not s or s.startswith("#") or s.startswith("set ") or CONTROL_RE.match(s):
            continue
        out.append(i)
    return out


def bash_parses(src: str) -> bool:
    """Syntax check with ``bash -n`` (parses only, executes nothing)."""
    if not shutil.which("bash"):
        return True
    proc = subprocess.run(["bash", "-n"], input=src.encode(), capture_output=True, check=False)
    return proc.returncode == 0


def _shell_files(files: Mapping[str, str], ctx: Context) -> Iterator[tuple[str, list[str]]]:
    for path, src in files.items():
        if ctx.languages.get(path) == "shell":
            yield path, src.splitlines(keepends=True)


def _emit_shell(
    files: Mapping[str, str], path: str, lines: list[str], op: str, desc: str, target: str
) -> Iterator[Proposal]:
    new = "".join(lines)
    if new != files[path] and bash_parses(new):
        yield Proposal(V, op, _files_with(files, path, new), desc, target)


def _nl(line: str) -> str:
    return "\n" if line.endswith("\n") else ""


def sh_line_delete(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Replace one command line with ``:`` (a skipped step)."""
    for path, lines in _shell_files(files, ctx):
        for i in shell_command_lines("".join(lines)):
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            new = [*lines[:i], indent + ":" + _nl(lines[i]), *lines[i + 1 :]]
            yield from _emit_shell(
                files, path, new, "sh-line-delete", f"skip line {i + 1}", f"{path}:{i + 1}"
            )


def sh_constant(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Increment one integer literal on a command line."""
    for path, lines in _shell_files(files, ctx):
        for i in shell_command_lines("".join(lines)):
            for m in NUMBER_RE.finditer(lines[i]):
                n = int(m.group(1)) + 1
                line = lines[i][: m.start(1)] + str(n) + lines[i][m.end(1) :]
                new = [*lines[:i], line, *lines[i + 1 :]]
                yield from _emit_shell(
                    files, path, new, "sh-constant", f"{m.group(1)} -> {n}", f"{path}:{i + 1}"
                )


def _retarget(word: str) -> str:
    if word[:1] in "\"'":
        return word[:-1] + ".wrong" + word[-1]
    return word + ".wrong"


def sh_target_file(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Redirect one output to a different file name (wrong target file)."""
    for path, lines in _shell_files(files, ctx):
        for i in shell_command_lines("".join(lines)):
            for m in REDIRECT_RE.finditer(lines[i]):
                word = m.group(2)
                if word.startswith("/dev/") or word.startswith("&"):
                    continue
                line = lines[i][: m.start(2)] + _retarget(word) + lines[i][m.end(2) :]
                new = [*lines[:i], line, *lines[i + 1 :]]
                yield from _emit_shell(
                    files,
                    path,
                    new,
                    "sh-target-file",
                    f"write to {_retarget(word)}",
                    f"{path}:{i + 1}",
                )


def sh_partial_output(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Keep only the first line of one redirected output (partial output)."""
    for path, lines in _shell_files(files, ctx):
        for i in shell_command_lines("".join(lines)):
            m = REDIRECT_RE.search(lines[i])
            if not m or m.group(2).startswith("/dev/") or m.group(1) != ">":
                continue
            line = lines[i][: m.start(1)].rstrip() + " | head -n 1 " + lines[i][m.start(1) :]
            new = [*lines[:i], line, *lines[i + 1 :]]
            yield from _emit_shell(
                files, path, new, "sh-partial-output", "keep first line", f"{path}:{i + 1}"
            )


# ------------------------------------------------------------------- trajectories


def _trajectories(
    files: Mapping[str, str], ctx: Context
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    for path, src in files.items():
        if ctx.languages.get(path) != "trajectory":
            continue
        try:
            calls = json.loads(src)
        except ValueError:
            continue
        if isinstance(calls, list) and all(isinstance(c, dict) for c in calls):
            yield path, calls


def _dump(calls: list[dict[str, Any]]) -> str:
    return json.dumps(calls, indent=2) + "\n"


def traj_drop_call(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Drop one call; confirmation-like calls are labeled as process variants."""
    for path, calls in _trajectories(files, ctx):
        for i, call in enumerate(calls):
            tool = str(call.get("tool", ""))
            op = "traj-drop-confirmation" if CONFIRM_RE.search(tool) else "traj-drop-call"
            new = [c for j, c in enumerate(calls) if j != i]
            yield Proposal(
                V, op, _files_with(files, path, _dump(new)), f"drop call {i} {tool}", f"{path}#{i}"
            )


def shares_values(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Whether two calls share any argument value (a data dependency heuristic)."""
    va = {json.dumps(v, sort_keys=True) for v in (a.get("args") or {}).values()}
    vb = {json.dumps(v, sort_keys=True) for v in (b.get("args") or {}).values()}
    return bool(va & vb)


def traj_reorder_dependent(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Swap two adjacent calls that look dependent (shared argument values)."""
    for path, calls in _trajectories(files, ctx):
        for i in range(len(calls) - 1):
            a, b = calls[i], calls[i + 1]
            if a != b and (shares_values(a, b) or CONFIRM_RE.search(str(a.get("tool", "")))):
                new = [*calls[:i], b, a, *calls[i + 2 :]]
                yield Proposal(
                    V,
                    "traj-reorder-dependent",
                    _files_with(files, path, _dump(new)),
                    f"swap calls {i} and {i + 1}",
                    f"{path}#{i}",
                )


def _changed(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    if isinstance(value, str):
        return value + "-x"
    return None


def traj_argument(files: Mapping[str, str], ctx: Context) -> Iterable[Proposal]:
    """Change one scalar argument of one call."""
    for path, calls in _trajectories(files, ctx):
        for i, call in enumerate(calls):
            for name, value in (call.get("args") or {}).items():
                new_value = _changed(value)
                if new_value is None:
                    continue
                new_call = {**call, "args": {**call["args"], name: new_value}}
                new = [*calls[:i], new_call, *calls[i + 1 :]]
                yield Proposal(
                    V,
                    "traj-argument",
                    _files_with(files, path, _dump(new)),
                    f"call {i} {name}: {value!r} -> {new_value!r}",
                    f"{path}#{i}.{name}",
                )


PYTHON_OPERATORS: tuple[Operator, ...] = (
    py_statement_delete,
    py_constant,
    py_compare,
    py_negate,
    py_arith,
    py_boolop,
    py_return_none,
    py_loop_skip_last,
)
SHELL_OPERATORS: tuple[Operator, ...] = (
    sh_line_delete,
    sh_constant,
    sh_target_file,
    sh_partial_output,
)
TRAJECTORY_OPERATORS: tuple[Operator, ...] = (traj_drop_call, traj_reorder_dependent, traj_argument)
ALL: tuple[Operator, ...] = PYTHON_OPERATORS + SHELL_OPERATORS + TRAJECTORY_OPERATORS
