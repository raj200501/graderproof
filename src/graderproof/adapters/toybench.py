"""toybench: graderproof's local task format, used for tests, the demo, and E0.

A task is a directory::

    <task>/
      task.toml        id, kind, timeout_s, [solution] entry, [grader] entry, [metadata]
      instruction.md   the task text given to the agent
      solution/        reference solution files
      grader/          grader files; the grader passes the solution iff it exits 0
      workspace/       optional initial workspace files
      support/         optional task environment files (env.py for trajectory tasks)

Kinds:

* ``script``: the solution entry (``.sh`` run with bash, ``.py`` with python3) runs in
  the workspace and leaves outputs there; its stdout is given to the grader as the
  file named by ``$GP_SOLUTION_STDOUT``.
* ``module``: the solution files are placed in the workspace and the grader imports
  them (``[solution] module`` names the module for function-call probes).
* ``trajectory``: the solution is ``trajectory.json``, a list of tool calls executed
  against ``support/env.py``; the grader reads ``.gp/state.json`` and
  ``.gp/trajectory.json`` in the workspace.

Execution order in a fresh temporary directory: initial workspace, solution run,
workspace snapshot, grader run, then function-call probes on a copy of the snapshot.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graderproof.adapters import Execution, language_of
from graderproof.core import GraderRun, Task
from graderproof.sandbox import Limits, Sandbox
from graderproof.spec import Outcome, probe_key

KINDS = ("script", "module", "trajectory")
MAX_FILE_BYTES = 1_000_000
STATE_DIR = ".gp"


def _read_tree(root: Path) -> dict[str, str]:
    """Every file under ``root`` as text, relative path to content."""
    files: dict[str, str] = {}
    if not root.is_dir():
        return files
    for p in sorted(root.rglob("*")):
        if p.is_file():
            files[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return files


def _write_tree(root: Path, files: Mapping[str, str]) -> None:
    for rel, text in files.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        if rel.endswith((".sh", ".py")):
            dest.chmod(0o755)


def snapshot(root: Path, skip: str = STATE_DIR) -> dict[str, str]:
    """Workspace text files after a run; binary or oversized files become a marker."""
    files: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if not p.is_file() or rel == skip or rel.startswith(skip + "/"):
            continue
        data = p.read_bytes()
        if len(data) > MAX_FILE_BYTES or b"\0" in data[:8192]:
            files[rel] = f"<binary {len(data)} bytes>"
        else:
            files[rel] = data.decode("utf-8", errors="replace")
    return files


def interpreter(entry: str) -> list[str]:
    """How to run a task script by its extension."""
    return ["python3", entry] if entry.endswith(".py") else ["bash", entry]


@dataclass
class ToybenchAdapter:
    """Loads and executes toybench tasks."""

    name: str = "toybench"
    scratch: Path | None = None

    def load(self, root: Path) -> list[Task]:
        """Every task directory (containing task.toml) directly under ``root``, sorted."""
        tasks = []
        for d in sorted(p for p in root.iterdir() if (p / "task.toml").exists()):
            tasks.append(self.load_one(d, benchmark=root.name))
        return tasks

    def load_one(self, d: Path, benchmark: str) -> Task:
        """Load one task directory."""
        with (d / "task.toml").open("rb") as fh:
            meta = tomllib.load(fh)
        kind = str(meta.get("kind", "script"))
        if kind not in KINDS:
            raise ValueError(f"{d}: unknown kind {kind!r}")
        solution = meta.get("solution", {})
        grader = meta.get("grader", {})
        entry = str(solution.get("entry", "trajectory.json" if kind == "trajectory" else ""))
        g_entry = str(grader.get("entry", "grade.sh"))
        env = {
            "kind": kind,
            "timeout_s": float(meta.get("timeout_s", 20)),
            "solution_entry": entry,
            "module": str(solution.get("module", "")),
            "grader_entry": g_entry,
            "grader_files": _read_tree(d / "grader"),
            "workspace_files": _read_tree(d / "workspace"),
            "support_files": _read_tree(d / "support"),
        }
        return Task(
            id=str(meta.get("id", d.name)),
            benchmark=str(meta.get("benchmark", benchmark)),
            instructions=(d / "instruction.md").read_text(encoding="utf-8"),
            environment=env,
            reference_solution=_read_tree(d / "solution"),
            grading_entrypoint=[*interpreter(g_entry)[:1], f"grader/{g_entry}"],
            metadata={"trusted_local": True, **dict(meta.get("metadata", {}))},
        )

    def mutable_files(self, task: Task) -> dict[str, str]:
        """Solution files by language (all reference solution files are mutable)."""
        return {path: language_of(path) for path in task.reference_solution}

    def execute(
        self,
        task: Task,
        solution: Mapping[str, str],
        sandbox: Sandbox,
        probes: Sequence[Mapping[str, Any]] = (),
        limits: Limits | None = None,
        variant_id: str | None = None,
    ) -> Execution:
        """Run the solution and the grader in a fresh temporary directory."""
        env = task.environment
        timeout = float(env.get("timeout_s", 20))
        lim = limits or Limits(timeout_s=timeout, cpu_s=int(timeout * 2) + 1)
        root = Path(tempfile.mkdtemp(prefix="gp-run-", dir=self.scratch))
        try:
            return self._execute(task, solution, sandbox, probes, lim, variant_id, root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _execute(
        self,
        task: Task,
        solution: Mapping[str, str],
        sandbox: Sandbox,
        probes: Sequence[Mapping[str, Any]],
        lim: Limits,
        variant_id: str | None,
        root: Path,
    ) -> Execution:
        env = task.environment
        kind = str(env["kind"])
        ws, sol, grd, sup, out = (root / n for n in ("ws", "solution", "grader", "support", "out"))
        for d in (ws, sol, grd, sup, out):
            d.mkdir()
        _write_tree(ws, env.get("workspace_files", {}))
        _write_tree(sup, env.get("support_files", {}))
        _write_tree(grd, env.get("grader_files", {}))
        trajectory: list[dict[str, Any]] = []
        state: dict[str, Any] | None = None
        if kind == "module":
            _write_tree(ws, solution)
            stdout = stderr = ""
            status, timed_out = 0, False
        else:
            _write_tree(sol, solution)
            if kind == "script":
                argv = interpreter(str(sol / str(env["solution_entry"])))
            else:
                argv = [sys.executable, "-m", "graderproof._runners", "trajectory"]
                argv += [str(sup / "env.py"), str(sol / "trajectory.json"), str(ws / STATE_DIR)]
            res = sandbox.run(argv, cwd=ws, writable=[ws], readonly=[sol, sup], limits=lim)
            stdout, stderr = res.stdout, res.stderr
            status, timed_out = res.exit_status, res.timed_out
            if kind == "trajectory":
                state, trajectory = _read_trajectory(ws / STATE_DIR)
        files = snapshot(ws)
        probe_ws = root / "probe_ws"
        shutil.copytree(ws, probe_ws)
        (out / "solution.stdout").write_text(stdout, encoding="utf-8")
        g_entry = str(env["grader_entry"])
        g_env = {"GP_SOLUTION_STDOUT": str(out / "solution.stdout"), "GP_SUPPORT_DIR": str(sup)}
        g = sandbox.run(
            interpreter(str(grd / g_entry)),
            cwd=ws,
            writable=[ws],
            readonly=[grd, sup, out],
            env=g_env,
            limits=lim,
        )
        grade = GraderRun(
            task_id=task.id,
            variant_id=variant_id,
            exit_status=g.exit_status,
            passed=g.exit_status == 0 and not g.timed_out,
            stdout=g.stdout,
            stderr=g.stderr,
            duration_s=round(g.duration_s, 3),
            backend=g.backend,
            timed_out=g.timed_out,
        )
        results = self._probe(task, probes, sandbox, probe_ws, out, lim) if probes else {}
        outcome = Outcome(
            files=files,
            stdout=stdout,
            stderr=stderr,
            exit_status=status,
            timed_out=timed_out,
            trajectory=tuple(trajectory),
            state=state,
            probes=results,
        )
        return Execution(outcome, grade)

    def _probe(
        self,
        task: Task,
        probes: Sequence[Mapping[str, Any]],
        sandbox: Sandbox,
        ws: Path,
        out: Path,
        lim: Limits,
    ) -> dict[str, dict[str, Any]]:
        module = str(task.environment.get("module") or "solution")
        (out / "probes.json").write_text(json.dumps([dict(p) for p in probes]))
        result_path = ws / ".gp-probes.json"
        argv = [sys.executable, "-m", "graderproof._runners", "probe", module]
        argv += [str(out / "probes.json"), str(result_path)]
        res = sandbox.run(argv, cwd=ws, writable=[ws], readonly=[out], limits=lim)
        if res.exit_status != 0 or not result_path.exists():
            err = f"probe runner failed: {res.stderr.strip()[-200:]}"
            return {probe_key(p): {"ok": False, "error": err} for p in probes}
        data: dict[str, dict[str, Any]] = json.loads(result_path.read_text())
        return data


def _read_trajectory(state_dir: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    state_file, traj_file = state_dir / "state.json", state_dir / "trajectory.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else None
    traj = json.loads(traj_file.read_text()) if traj_file.exists() else []
    return state, traj
