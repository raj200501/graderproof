"""Helper programs that run inside the sandbox (``python -m graderproof._runners``).

* ``probe <module> <probes.json> <result.json>``: import ``<module>`` from the working
  directory and call each probe ``{"function", "args", "kwargs"}``, recording
  ``{"ok", "value"}`` or ``{"ok": false, "error"}`` under its probe key.
* ``trajectory <env.py> <trajectory.json> <outdir>``: load a stateful tool environment
  (``initial_state()`` and a ``TOOLS`` mapping of ``name -> fn(state, **args)``), execute
  the trajectory's calls in order, and write ``state.json`` and ``trajectory.json``.

These programs execute untrusted task code, so they are only ever started by a
sandbox backend; they import nothing from graderproof except :mod:`graderproof.core`.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import signal
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from graderproof.core import canonical_json, sha256_text

PROBE_TIMEOUT_S = 5


def jsonable(value: Any) -> Any:
    """Convert a Python value to plain JSON (tuples to lists, sets sorted, others repr)."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, set | frozenset):
        return sorted((jsonable(v) for v in value), key=canonical_json)
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    return {"__repr__": repr(value)}


def probe_key(probe: Mapping[str, Any]) -> str:
    """Same key as :func:`graderproof.spec.probe_key`."""
    return sha256_text(canonical_json(dict(probe)))[:16]


class ProbeTimeoutError(Exception):
    """A probe exceeded its time budget."""


def _alarm(signum: int, frame: object) -> None:  # pragma: no cover - signal handler
    raise ProbeTimeoutError


def run_probes(module_name: str, probes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Import ``module_name`` from the working directory and run each probe."""
    sys.path.insert(0, str(Path.cwd()))
    results: dict[str, dict[str, Any]] = {}
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # untrusted code: any failure is a recorded outcome
        err = f"import failed: {type(exc).__name__}: {exc}"
        return {probe_key(p): {"ok": False, "error": err} for p in probes}
    signal.signal(signal.SIGALRM, _alarm)
    for p in probes:
        key = probe_key(p)
        try:
            fn = getattr(module, str(p["function"]))
            signal.alarm(PROBE_TIMEOUT_S)
            try:
                value = fn(*p.get("args", []), **p.get("kwargs", {}))
            finally:
                signal.alarm(0)
            results[key] = {"ok": True, "value": jsonable(value)}
        except ProbeTimeoutError:
            results[key] = {"ok": False, "error": "timeout"}
        except Exception as exc:  # untrusted code: record, never propagate
            results[key] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return results


def run_trajectory(env_path: Path, calls: list[dict[str, Any]]) -> tuple[Any, list[dict[str, Any]]]:
    """Execute tool calls against the environment defined in ``env_path``."""
    spec = importlib.util.spec_from_file_location("gp_task_env", env_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {env_path}")
    env = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(env)
    state = env.initial_state()
    log: list[dict[str, Any]] = []
    for call in calls:
        tool = str(call.get("tool"))
        args = dict(call.get("args") or {})
        entry: dict[str, Any] = {"tool": tool, "args": args}
        fn = env.TOOLS.get(tool)
        if fn is None:
            entry["error"] = f"unknown tool {tool}"
        else:
            try:
                entry["result"] = jsonable(fn(state, **args))
            except Exception as exc:  # task code: record, keep going
                entry["error"] = f"{type(exc).__name__}: {exc}"
        log.append(entry)
    return jsonable(state), log


def main(argv: list[str]) -> int:
    """Entry point; returns the exit status."""
    if len(argv) == 4 and argv[0] == "probe":
        probes = json.loads(Path(argv[2]).read_text())
        Path(argv[3]).write_text(json.dumps(run_probes(argv[1], probes)))
        return 0
    if len(argv) == 4 and argv[0] == "trajectory":
        calls = json.loads(Path(argv[2]).read_text())
        out = Path(argv[3])
        out.mkdir(parents=True, exist_ok=True)
        try:
            state, log = run_trajectory(Path(argv[1]), calls)
        except Exception as exc:  # task environment failed to load
            (out / "error.txt").write_text(f"{type(exc).__name__}: {exc}")
            return 1
        (out / "state.json").write_text(json.dumps(state, sort_keys=True))
        (out / "trajectory.json").write_text(json.dumps(log))
        return 0
    print("usage: python -m graderproof._runners probe|trajectory ...", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
