"""E4: grader repairs built from validated requirement checks, and their validation.

For a task with surviving violating variants (validated, counted, and accepted by the
grader), every survivor's witness names the requirements it breaks; those
requirements' checks were derived from the task text and hold on every reference run.
A repair is a smallest greedy set of such requirements that covers every coverable
survivor, grafted onto the grader as a standalone checker:

* the checker (``grader/gp_repair_checker.py``) embeds :mod:`graderproof.spec` and the
  probe runner verbatim, so its verdicts are exactly the audit's requirement verdicts;
  differential checks (``same_as_reference``, ``matches_reference``) are evaluated
  against a frozen snapshot of the reference outcome stored beside it;
* the repaired grader (``grader/gp_repaired.sh``) runs the checker on the untouched
  workspace and then the original grader; it accepts only if both accept.

A repair is **accepted** only if, executed in the sandbox, the patched grader passes
the reference ``k`` times, still accepts every validated preserving variant the
original grader accepted, rejects every targeted survivor, and gives the same verdict
on every repetition. Requirements with ``exit_code`` checks are never used (a grader
cannot see the solution's exit status), and survivors with no other broken
requirement are reported as uncovered.
"""

from __future__ import annotations

import difflib
import hashlib
import inspect
import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from graderproof import _runners, spec
from graderproof.adapters import Adapter
from graderproof.adapters.toybench import interpreter
from graderproof.core import Task
from graderproof.run import Runner
from graderproof.spec import Outcome, Requirement

CHECKER = "gp_repair_checker.py"
CHECKS = "gp_repair_checks.json"
WRAPPER = "gp_repaired.sh"
UNREPAIRABLE_CHECKS = frozenset({"exit_code"})


@dataclass(frozen=True)
class RepairPlan:
    """Which requirements to graft, which survivors they target, which stay uncovered."""

    requirements: tuple[Requirement, ...]
    targets: tuple[str, ...]
    uncovered: tuple[str, ...]


@dataclass
class RepairResult:
    """A synthesized repair with its patch and execution-based validation."""

    task_key: str
    task_hash: str
    plan: RepairPlan
    files: dict[str, str]
    patch: str
    validation: dict[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        """All acceptance criteria held."""
        return bool(self.validation.get("accepted"))

    def log(self) -> dict[str, Any]:
        """The validation log banked beside the patch."""
        return {
            "schema": "graderproof.repair_validation/1",
            "task": self.task_key,
            "task_hash": self.task_hash,
            "requirements": [r.id for r in self.plan.requirements],
            "targets": list(self.plan.targets),
            "uncovered": list(self.plan.uncovered),
            **self.validation,
        }


def repairable(req: Requirement) -> bool:
    """A requirement can be grafted onto a grader (no exit-status checks)."""
    return not any(c.get("type") in UNREPAIRABLE_CHECKS for c in req.checks)


def survivors(evidence: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Counted violating variants the original grader accepts (false accepts).

    Only scorable tasks (the grader passes the reference stably, DECISIONS.md D26) have
    survivors; a task whose reference is rejected or flaky is not a repair target (D33).
    """
    if evidence.get("determinism", "stable_pass") != "stable_pass":
        return []
    return [
        v
        for v in evidence.get("variants", [])
        if v.get("counted_in_headline")
        and v.get("kind") == "violating"
        and v.get("grader_passed") is True
    ]


def plan_repair(evidence: Mapping[str, Any]) -> RepairPlan | None:
    """Greedy set cover of survivors by the repairable requirements their witnesses name."""
    reqs = {r["id"]: Requirement.from_dict(r) for r in evidence.get("requirements", [])}
    targets = survivors(evidence)
    if not targets:
        return None
    covers: dict[str, set[str]] = {}
    uncovered: list[str] = []
    for v in targets:
        broken = [b["requirement"] for b in (v.get("witness") or {}).get("broken", [])]
        usable = [rid for rid in broken if rid in reqs and repairable(reqs[rid])]
        if not usable:
            uncovered.append(str(v["id"]))
        for rid in usable:
            covers.setdefault(rid, set()).add(str(v["id"]))
    remaining = set().union(*covers.values()) if covers else set()
    chosen: list[str] = []
    while remaining:
        best = max(sorted(covers), key=lambda rid: len(covers[rid] & remaining))
        chosen.append(best)
        remaining -= covers[best]
    covered = sorted(set().union(*(covers[r] for r in chosen))) if chosen else []
    return RepairPlan(tuple(reqs[r] for r in chosen), tuple(covered), tuple(sorted(uncovered)))


def frozen_reference(
    reference: Mapping[str, Any], requirements: Sequence[Requirement]
) -> dict[str, Any]:
    """The parts of the reference outcome the differential checks need."""
    needs_files: set[str] = set()
    for req in requirements:
        for c in req.checks:
            target = str(c.get("target", ""))
            if c.get("type") == "same_as_reference" and target.startswith("file:"):
                needs_files.add(target[5:])
    ref = Outcome.from_dict(reference)
    return {
        "files": {p: t for p, t in ref.files.items() if p in needs_files},
        "stdout": ref.stdout,
        "state": ref.state,
        "probes": {k: dict(v) for k, v in ref.probes.items()},
    }


def _module_source(module: Any) -> str:
    """Source of a graderproof module without its graderproof and __future__ imports."""
    drop = ("from graderproof", "import graderproof", "from __future__")
    lines = inspect.getsource(module).splitlines()
    return "\n".join(ln for ln in lines if not ln.startswith(drop))


CHECKER_MAIN = """

# ---- graderproof repair checker entry point -------------------------------------
import os as _os
import shutil as _shutil
import tempfile as _tempfile
from pathlib import Path as _Path

MAX_FILE_BYTES = 1_000_000
STATE_DIR = ".gp"


def snapshot(root):
    files = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if not p.is_file() or rel == STATE_DIR or rel.startswith(STATE_DIR + "/"):
            continue
        data = p.read_bytes()
        if len(data) > MAX_FILE_BYTES or b"\\0" in data[:8192]:
            files[rel] = f"<binary {len(data)} bytes>"
        else:
            files[rel] = data.decode("utf-8", errors="replace")
    return files


def _read_json(path):
    return json.loads(path.read_text()) if path.exists() else None


def checker_main():
    data = json.loads((_Path(__file__).resolve().parent / "gp_repair_checks.json").read_text())
    ws = _Path.cwd()
    out_path = _os.environ.get("GP_SOLUTION_STDOUT", "")
    stdout = _Path(out_path).read_text() if out_path and _Path(out_path).exists() else ""
    requirements = [Requirement.from_dict(r) for r in data["requirements"]]
    probes = probes_of(requirements)
    results = {}
    if probes:
        tmp = _Path(_tempfile.mkdtemp(prefix="gp-probe-"))
        try:
            copy = tmp / "ws"
            _shutil.copytree(ws, copy)
            cwd = _Path.cwd()
            _os.chdir(copy)
            try:
                results = run_probes(data["module"], probes)
            finally:
                _os.chdir(cwd)
        finally:
            _shutil.rmtree(tmp, ignore_errors=True)
    outcome = Outcome(
        files=snapshot(ws),
        stdout=stdout,
        trajectory=tuple(_read_json(ws / ".gp" / "trajectory.json") or ()),
        state=_read_json(ws / ".gp" / "state.json"),
        probes=results,
    )
    ref = data["reference"]
    reference = Outcome(
        files=ref["files"], stdout=ref["stdout"], state=ref["state"], probes=ref["probes"]
    )
    failed = []
    for req in requirements:
        ok, checks = holds(req, outcome, reference)
        if not ok:
            failed.append(req.id + ": " + "; ".join(c.detail for c in checks if not c.passed))
    for line in failed:
        print("repair check failed: " + line)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    checker_main()
"""


def checker_source() -> str:
    """A standalone, standard-library-only checker embedding spec and the probe runner."""
    header = (
        '"""graderproof repair checker (generated). Evaluates the requirements in\n'
        "gp_repair_checks.json on the workspace with graderproof's own check semantics.\n"
        '"""\n\nfrom __future__ import annotations\n\nimport hashlib\nimport json\n\n\n'
        "def canonical_json(obj):\n"
        "    return json.dumps(\n"
        '        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False\n'
        "    )\n\n\n"
        "def sha256_text(text):\n"
        '    return hashlib.sha256(text.encode("utf-8")).hexdigest()\n\n'
    )
    entry_point = (
        'if __name__ == "__main__":  # pragma: no cover\n    raise SystemExit(main(sys.argv[1:]))'
    )
    runners = _module_source(_runners).replace(entry_point, "")
    return header + _module_source(spec) + "\n\n" + runners + CHECKER_MAIN


def patched_files(task: Task, plan: RepairPlan, reference: Mapping[str, Any]) -> dict[str, str]:
    """New and changed task files (paths relative to the task directory)."""
    entry = str(task.environment["grader_entry"])
    checks = {
        "schema": "graderproof.repair_checks/1",
        "task": task.key,
        "module": str(task.environment.get("module") or "solution"),
        "requirements": [r.to_dict() for r in plan.requirements],
        "reference": frozen_reference(reference, plan.requirements),
    }
    wrapper = (
        "#!/usr/bin/env bash\n"
        'here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        f'python3 "$here/{CHECKER}" || exit 1\n'
        f'exec {interpreter(entry)[0]} "$here/{entry}"\n'
    )
    return {
        f"grader/{CHECKER}": checker_source(),
        f"grader/{CHECKS}": json.dumps(checks, indent=2, sort_keys=True) + "\n",
        f"grader/{WRAPPER}": wrapper,
    }


def git_patch(before: Mapping[str, str], after: Mapping[str, str]) -> str:
    """A git-style unified diff (new files and modifications) between two file maps."""
    out: list[str] = []
    for path in sorted(set(before) | set(after)):
        a, b = before.get(path), after.get(path)
        if a == b:
            continue
        out.append(f"diff --git a/{path} b/{path}\n")
        if a is None:
            out.append("new file mode 100644\n")
        a_lines = (a or "").splitlines(keepends=True)
        b_lines = (b or "").splitlines(keepends=True)
        for line in difflib.unified_diff(
            a_lines, b_lines, "/dev/null" if a is None else f"a/{path}", f"b/{path}"
        ):
            out.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    return "".join(out)


def toml_with_entry(toml_text: str, new_entry: str) -> str:
    """task.toml with the ``[grader] entry`` replaced (appended when absent)."""
    lines = toml_text.splitlines(keepends=True)
    out: list[str] = []
    in_grader = replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            if in_grader and not replaced:
                out.append(f'entry = "{new_entry}"\n')
                replaced = True
            in_grader = stripped == "[grader]"
        if in_grader and stripped.startswith("entry") and "=" in stripped:
            out.append(f'entry = "{new_entry}"\n')
            replaced = True
            continue
        out.append(line)
    if not replaced:
        if not in_grader:
            out.append("\n[grader]\n")
        out.append(f'entry = "{new_entry}"\n')
    return "".join(out)


def build_repair(task: Task, task_dir: Path, evidence: Mapping[str, Any]) -> RepairResult | None:
    """Plan and write (in memory) the repair for one task; None without survivors."""
    plan = plan_repair(evidence)
    if plan is None:
        return None
    reference = evidence["reference_outcome"]
    new_files = patched_files(task, plan, reference) if plan.requirements else {}
    before: dict[str, str] = {}
    after: dict[str, str] = {}
    if plan.requirements:
        toml_text = (task_dir / "task.toml").read_text(encoding="utf-8")
        before["task.toml"] = toml_text
        after["task.toml"] = toml_with_entry(toml_text, WRAPPER)
        after.update(new_files)
    return RepairResult(
        task_key=task.key,
        task_hash=task.key_hash,
        plan=plan,
        files=after,
        patch=git_patch(before, after),
    )


def materialize(task_dir: Path, files: Mapping[str, str], dest: Path) -> Path:
    """Copy a task directory and apply the repaired files to the copy."""
    shutil.copytree(task_dir, dest)
    for rel, text in files.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if rel.endswith((".sh", ".py")):
            path.chmod(0o755)
    return dest


def validate_repair(
    result: RepairResult,
    task_dir: Path,
    evidence: Mapping[str, Any],
    adapter: Adapter,
    runner_for: Any,
    k: int,
) -> dict[str, Any]:
    """Execute the patched grader: reference k times, targets and preserving variants k times.

    ``runner_for`` maps an adapter to a :class:`Runner` (so tests can supply a sandbox).
    """
    if not result.plan.requirements:
        result.validation = {
            "accepted": False,
            "reason": "no repairable requirement covers any survivor",
        }
        return result.validation
    with tempfile.TemporaryDirectory(prefix="gp-repair-") as tmp:
        bench = Path(tmp) / "bench"
        bench.mkdir()
        materialize(task_dir, result.files, bench / task_dir.name)
        task = adapter.load(bench)[0]
        runner: Runner = runner_for(adapter)
        ref_runs = [e.grade.passed for e in runner.repeat(task, task.reference_solution, k)]
        variants = {str(v["id"]): v for v in evidence.get("variants", [])}
        target_runs = {
            vid: [
                e.grade.passed
                for e in runner.repeat(task, variants[vid]["files"], k, variant_id=vid)
            ]
            for vid in result.plan.targets
        }
        preserving = [
            v
            for v in evidence.get("variants", [])
            if v.get("counted_in_headline")
            and v.get("kind") == "preserving"
            and v.get("grader_passed") is True
        ]
        preserving_runs = {
            str(v["id"]): [
                e.grade.passed for e in runner.repeat(task, v["files"], k, variant_id=str(v["id"]))
            ]
            for v in preserving
        }
    deterministic = all(
        len(set(runs)) == 1 for runs in [ref_runs, *target_runs.values(), *preserving_runs.values()]
    )
    validation = {
        "k": k,
        "reference_runs": ref_runs,
        "target_runs": target_runs,
        "preserving_runs": preserving_runs,
        "reference_passes": all(ref_runs),
        "targets_caught": all(not any(r) for r in target_runs.values()),
        "preserving_kept": all(all(r) for r in preserving_runs.values()),
        "deterministic": deterministic,
    }
    validation["accepted"] = bool(
        validation["reference_passes"]
        and validation["targets_caught"]
        and validation["preserving_kept"]
        and deterministic
    )
    result.validation = validation
    return validation


def evaluate_fresh(
    original: Mapping[str, Any],
    fresh: Mapping[str, Any],
    result: RepairResult,
    task_dir: Path,
    adapter: Adapter,
    runner_for: Any,
) -> dict[str, Any]:
    """Run the repaired grader on a post-repair batch of variants the repair never saw.

    Only counted fresh variants with a stable original verdict and an id absent from
    the original audit are used.
    """
    seen = {str(v["id"]) for v in original.get("variants", [])}
    batch = [
        v
        for v in fresh.get("variants", [])
        if str(v["id"]) not in seen
        and v.get("counted_in_headline")
        and v.get("grader_passed") is not None
    ]
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="gp-gen-") as tmp:
        bench = Path(tmp) / "bench"
        bench.mkdir()
        materialize(task_dir, result.files, bench / task_dir.name)
        task = adapter.load(bench)[0]
        runner: Runner = runner_for(adapter)
        for v in batch:
            repaired = runner.execute(task, v["files"], variant_id=str(v["id"])).grade.passed
            rows.append(
                {
                    "variant_id": str(v["id"]),
                    "kind": v.get("kind"),
                    "operator": v.get("operator"),
                    "original_passed": bool(v["grader_passed"]),
                    "repaired_passed": repaired,
                }
            )
    return {"rows": rows, **generalization_counts(rows)}


def generalization_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Counts over fresh variants: survivors before and after repair, induced rejects."""
    viol = [r for r in rows if r["kind"] == "violating"]
    pres = [r for r in rows if r["kind"] == "preserving"]
    return {
        "n_fresh_variants": len(rows),
        "n_fresh_violating": len(viol),
        "n_fresh_preserving": len(pres),
        "survivors_original": sum(1 for r in viol if r["original_passed"]),
        "caught_by_repair": sum(
            1 for r in viol if r["original_passed"] and not r["repaired_passed"]
        ),
        "survivors_repaired": sum(1 for r in viol if r["repaired_passed"]),
        "preserving_accepted_original": sum(1 for r in pres if r["original_passed"]),
        "induced_false_rejects": sum(
            1 for r in pres if r["original_passed"] and not r["repaired_passed"]
        ),
    }


def mutation_scores(evidence: Mapping[str, Any], result: RepairResult | None) -> dict[str, Any]:
    """Mutation score on the original counted violating variants, before and after repair."""
    viol = [
        v
        for v in evidence.get("variants", [])
        if v.get("counted_in_headline")
        and v.get("kind") == "violating"
        and v.get("grader_passed") is not None
    ]
    if not viol:
        return {"n": 0, "before": None, "after": None}
    killed = sum(1 for v in viol if v["grader_passed"] is False)
    caught = len(result.plan.targets) if result is not None and result.accepted else 0
    return {"n": len(viol), "before": killed / len(viol), "after": (killed + caught) / len(viol)}


def write_patch(
    result: RepairResult,
    benchmark: str,
    task_id: str,
    public_root: Path,
    private_root: Path,
    public: bool,
) -> dict[str, str]:
    """Write the patch and validation log; private files are named by task hash."""
    root = public_root if public else private_root
    stem = task_id if public else result.task_hash
    root.mkdir(parents=True, exist_ok=True)
    patch, log = root / f"{stem}.patch", root / f"{stem}.validation.json"
    patch.write_text(result.patch, encoding="utf-8")
    log.write_text(json.dumps(result.log(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"patch": patch.as_posix(), "validation_log": log.as_posix(), "benchmark": benchmark}


def update_manifest(manifest: Path, paths: Sequence[str], repo_root: Path) -> None:
    """Record the SHA-256 of private patch files in the tracked manifest (merge by path)."""
    data = json.loads(manifest.read_text()) if manifest.exists() else {"files": []}
    entries = {e["path"]: e for e in data.get("files", [])}
    for rel in paths:
        digest = hashlib.sha256((repo_root / rel).read_bytes()).hexdigest()
        entries[rel] = {"path": rel, "sha256": digest}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "schema": "graderproof.patch_manifest/1",
        "note": (
            "SHA-256 of patches for third-party tasks not yet fixed upstream; "
            "the files live in private/."
        ),
        "files": [entries[k] for k in sorted(entries)],
    }
    manifest.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
