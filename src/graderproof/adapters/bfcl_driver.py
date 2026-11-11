"""Grade one BFCL task with BFCL's own AST checker (graderproof's BFCL adapter).

The BFCL adapter copies this file into every converted task as
``grader/bfcl_driver.py``, and ``grader/grade.sh`` runs it inside the sandbox::

    "${GP_BFCL_PYTHON:-python3}" -I bfcl_driver.py bfcl_task.json .gp/trajectory.json

It reads the solution's tool calls, ``[{"tool": name, "args": {...}}]``, converts them
to BFCL's decoded format, ``[{name: {...}}]``, and calls
``bfcl_eval.eval_checker.ast_eval.ast_checker.ast_checker`` from the checkout named by
``GP_BFCL_ROOT`` (its ``berkeley-function-call-leaderboard`` directory). The arguments
are those of BFCL's ``_evaluate_single_ast_entry``: the function documentation, the
decoded calls, the possible answer, ``Language.PYTHON``, the test category, and the
model name, all read from ``bfcl_task.json``.

``ast_checker`` imports ``bfcl_eval.constants.model_config`` only to read the model's
``underscore_to_dot`` flag, and that module imports every model handler and, through
them, the vendor SDKs. The driver runs BFCL's real ``model_config`` but serves every
module under ``bfcl_eval.model_handler`` as a placeholder whose public attributes are
empty classes, so no handler code and no SDK is imported. No other BFCL module is
replaced. The driver uses the standard library only.

Output: one JSON line ``{"id", "valid", "error_type", "error"}`` on standard output.
Exit status: 0 valid, 1 invalid (including calls that cannot be decoded), 2 setup error
(task data, ``GP_BFCL_ROOT``, or the checker import), 3 the checker raised.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import json
import os
import re
import sys
import types
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

HANDLER_PACKAGE = "bfcl_eval.model_handler"
CHECKER_MODULE = "bfcl_eval.eval_checker.ast_eval.ast_checker"
ENUMS_MODULE = "bfcl_eval.constants.enums"
CHECKER_FILE = Path("bfcl_eval", "eval_checker", "ast_eval", "ast_checker.py")
TASK_KEYS = ("id", "category", "language", "model_name", "function", "ground_truth")
MAX_ERROR_CHARS = 2000
SHA_RE = re.compile(r"[0-9a-f]{40}")

VALID, INVALID, SETUP_ERROR, CHECKER_RAISED = 0, 1, 2, 3
DECODER_FAILED = "ast_decoder:decoder_failed"
WRONG_FORMAT = "ast_decoder:decoder_wrong_output_format"
"""BFCL's error types for output it cannot decode or that is not ``[{name: {...}}]``."""


class DecodeError(ValueError):
    """The solution's calls cannot be put into BFCL's decoded format."""

    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type


class SetupError(RuntimeError):
    """The task data, the checkout, or the checker import is unusable."""


def decode(calls: Any) -> list[dict[str, Any]]:
    """Turn ``[{"tool": name, "args": {...}}]`` into BFCL's ``[{name: {...}}]``.

    A missing or null ``args`` means no arguments, as in toybench trajectories, and
    keys other than ``tool`` and ``args`` are ignored. Raises :class:`DecodeError` with
    BFCL's ``decoder_failed`` type when ``calls`` is not a list of objects with a string
    ``tool``, and with ``decoder_wrong_output_format`` when some ``args`` is not an
    object (the condition of BFCL's ``is_function_calling_format_output``).
    """
    if not isinstance(calls, list):
        raise DecodeError(DECODER_FAILED, f"calls are a {type(calls).__name__}, not a list")
    decoded: list[dict[str, Any]] = []
    for i, call in enumerate(calls):
        if not isinstance(call, dict) or not isinstance(call.get("tool"), str):
            raise DecodeError(DECODER_FAILED, f"call {i} is not an object with a string 'tool'")
        args = call.get("args")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise DecodeError(WRONG_FORMAT, f"call {i} args are a {type(args).__name__}")
        decoded.append({call["tool"]: args})
    return decoded


def checkout_commit(root: Path) -> str | None:
    """The detached ``HEAD`` commit of the git checkout holding ``root``, if there is one.

    Looks for ``.git/HEAD`` in ``root`` and in its parent (the gorilla checkout that
    holds ``berkeley-function-call-leaderboard``). Returns None when neither exists or
    ``HEAD`` names a branch.
    """
    for git_dir in (root / ".git", root.parent / ".git"):
        head = git_dir / "HEAD"
        if head.is_file():
            text = head.read_text(encoding="utf-8").strip()
            return text if SHA_RE.fullmatch(text) else None
    return None


class _Placeholder(types.ModuleType):
    """Stands in for a BFCL model-handler module: public attributes are empty classes."""

    def __getattr__(self, name: str) -> type:
        if name.startswith("__"):
            raise AttributeError(name)
        return type(name, (), {"__module__": self.__name__})


class HandlerPlaceholders(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Import hook that serves every module under ``bfcl_eval.model_handler`` as a placeholder."""

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: types.ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        """A package spec for handler modules; None (not ours) for every other module."""
        if fullname == HANDLER_PACKAGE or fullname.startswith(HANDLER_PACKAGE + "."):
            return importlib.machinery.ModuleSpec(fullname, self, is_package=True)
        return None

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> types.ModuleType:
        """An empty placeholder module."""
        return _Placeholder(spec.name)

    def exec_module(self, module: types.ModuleType) -> None:
        """Placeholders have no code to run."""


def load_checker(root: Path) -> tuple[Callable[..., Any], Any]:
    """BFCL's ``ast_checker`` function and ``Language`` enum, imported from ``root``.

    Raises :class:`SetupError` when ``root`` has no AST checker, the import fails, or the
    module that was imported does not come from ``root``.
    """
    if not (root / CHECKER_FILE).is_file():
        raise SetupError(f"{root} has no {CHECKER_FILE.as_posix()}")
    sys.dont_write_bytecode = True
    sys.meta_path.insert(0, HandlerPlaceholders())
    sys.path.insert(0, str(root))
    try:
        checker = importlib.import_module(CHECKER_MODULE)
        enums = importlib.import_module(ENUMS_MODULE)
    except Exception as exc:
        raise SetupError(f"cannot import {CHECKER_MODULE} from {root}: {exc!r}") from exc
    origin = Path(str(getattr(checker, "__file__", ""))).resolve()
    if origin != (root / CHECKER_FILE).resolve():
        raise SetupError(f"imported {CHECKER_MODULE} from {origin}, not from {root}")
    return checker.ast_checker, enums.Language


def read_task(path: Path) -> dict[str, Any]:
    """The task data written by the adapter; raises :class:`SetupError` if unusable."""
    try:
        task = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SetupError(f"cannot read task data {path}: {exc}") from exc
    if not isinstance(task, dict) or any(k not in task for k in TASK_KEYS):
        raise SetupError(f"task data {path} lacks one of {', '.join(TASK_KEYS)}")
    return task


def grade(
    task: dict[str, Any], calls: Any, checker: Callable[..., Any], language: Any
) -> dict[str, Any]:
    """The checker's verdict ``{"valid", "error_type", "error"}`` on ``calls``.

    Calls that cannot be decoded are invalid with BFCL's decoder error type, as in
    BFCL's evaluation. ``error_type`` is None for a valid verdict. Exceptions raised by
    the checker propagate.
    """
    try:
        decoded = decode(calls)
    except DecodeError as exc:
        return {"valid": False, "error_type": exc.error_type, "error": [str(exc)]}
    result = checker(
        task["function"],
        decoded,
        task["ground_truth"],
        language(task["language"]),
        task["category"],
        task["model_name"],
    )
    valid = bool(result["valid"])
    return {
        "valid": valid,
        "error_type": None if valid else result.get("error_type"),
        "error": result.get("error", []),
    }


def _emit(task_id: Any, verdict: dict[str, Any]) -> None:
    error = json.dumps(verdict.get("error", []), ensure_ascii=False, default=str)
    line = {
        "id": task_id,
        "valid": verdict["valid"],
        "error_type": verdict.get("error_type"),
        "error": error[:MAX_ERROR_CHARS],
    }
    print(json.dumps(line, ensure_ascii=False))


def main(argv: Sequence[str] | None = None) -> int:
    """Grade ``TRAJECTORY_JSON`` for the task in ``TASK_JSON``; returns the exit status."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: bfcl_driver.py TASK_JSON TRAJECTORY_JSON", file=sys.stderr)
        return SETUP_ERROR
    try:
        task = read_task(Path(args[0]))
        root_text = os.environ.get("GP_BFCL_ROOT", "")
        if not root_text:
            raise SetupError("GP_BFCL_ROOT is not set")
        root = Path(root_text)
        head, want = checkout_commit(root), task.get("source_commit")
        if head is not None and want and head != want:
            raise SetupError(f"{root} is at commit {head}; the task was converted from {want}")
        checker, language = load_checker(root)
    except SetupError as exc:
        print(f"bfcl_driver: {exc}", file=sys.stderr)
        return SETUP_ERROR
    try:
        calls = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit(task["id"], {"valid": False, "error_type": DECODER_FAILED, "error": [str(exc)]})
        return INVALID
    try:
        verdict = grade(task, calls, checker, language)
    except Exception as exc:
        _emit(task["id"], {"valid": False, "error_type": "checker_exception", "error": [repr(exc)]})
        return CHECKER_RAISED
    _emit(task["id"], verdict)
    return VALID if verdict["valid"] else INVALID


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
