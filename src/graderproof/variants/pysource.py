"""Span-preserving edits of Python source using AST node positions.

Edits replace only the source span of the node they change, so the rest of the file
(comments, formatting) is untouched and diffs stay minimal.
"""

from __future__ import annotations

import ast


def _line_offsets(source: str) -> list[int]:
    """Byte offset of the start of each line (1-indexed lines map to index line - 1)."""
    offsets = [0]
    for line in source.encode("utf-8").splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def span(source: str, node: ast.AST) -> tuple[int, int]:
    """Byte span ``[start, end)`` of ``node`` in ``source``."""
    offs = _line_offsets(source)
    lineno, col = node.lineno, node.col_offset  # type: ignore[attr-defined]  # expr/stmt nodes
    end_lineno = node.end_lineno  # type: ignore[attr-defined]  # expr/stmt nodes
    end_col = node.end_col_offset  # type: ignore[attr-defined]  # expr/stmt nodes
    if end_lineno is None or end_col is None:
        raise ValueError("node has no end position")
    return offs[lineno - 1] + col, offs[end_lineno - 1] + end_col


def replace(source: str, start: int, end: int, text: str) -> str:
    """Replace the byte span ``[start, end)`` with ``text``."""
    data = source.encode("utf-8")
    return (data[:start] + text.encode("utf-8") + data[end:]).decode("utf-8")


def replace_node(source: str, node: ast.AST, text: str) -> str:
    """Replace the source of ``node`` with ``text``."""
    start, end = span(source, node)
    return replace(source, start, end, text)


def node_source(source: str, node: ast.AST) -> str:
    """The exact source text of ``node``."""
    start, end = span(source, node)
    return source.encode("utf-8")[start:end].decode("utf-8")


def replace_statement_lines(source: str, stmt: ast.stmt, text: str) -> str | None:
    """Replace the full lines of ``stmt`` with ``text`` at its indentation.

    Returns None if the statement shares a line with other code.
    """
    lines = source.splitlines(keepends=True)
    first, last = stmt.lineno - 1, (stmt.end_lineno or stmt.lineno) - 1
    head = lines[first][: stmt.col_offset] if first < len(lines) else ""
    if head.strip():
        return None
    tail_line = lines[last]
    end_col = stmt.end_col_offset or 0
    rest = tail_line.encode("utf-8")[end_col:].decode("utf-8", errors="replace").strip()
    if rest and not rest.startswith("#"):
        return None
    newline = "\n" if tail_line.endswith("\n") else ""
    new = [*lines[:first], head + text + newline, *lines[last + 1 :]]
    return "".join(new)


def compiles(source: str) -> bool:
    """Whether ``source`` is syntactically valid Python."""
    try:
        compile(source, "<variant>", "exec")
    except (SyntaxError, ValueError):
        return False
    return True


def is_docstring(node: ast.AST, parent: ast.AST | None) -> bool:
    """Whether ``node`` is the docstring expression of ``parent``."""
    body = getattr(parent, "body", None)
    return (
        isinstance(node, ast.Expr)
        and isinstance(body, list)
        and bool(body)
        and body[0] is node
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def parents(tree: ast.AST) -> dict[int, ast.AST]:
    """Map ``id(child)`` to its parent node."""
    out: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[id(child)] = node
    return out
