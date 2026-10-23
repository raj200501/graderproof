#!/usr/bin/env python3
"""graderproof ship-check: the 14 Definition-of-Done gates of docs/BUILD_BRIEF.md section 6.

Procedure (docs/BUILD_BRIEF.md section 10.1 step 9):

1. In the original checkout, check the parts of G14 about the working tree and
   ``private/``, and verify private hash manifests (``outbound/patches/MANIFEST.json``)
   against the files under ``private/``.
2. Make a fresh clone of HEAD in a temporary directory and run every other check there.
   Banked artifacts are verified (presence, provenance, hashes, preregistration links,
   thresholds) and statistics are recomputed from them. No experiment is run and no
   model is called. Nothing is written inside the working tree; sub-command logs go to
   the temporary directory.

Stdout is exactly ``HEAD <sha> fresh-clone``, one ``G<n> <PASS|FAIL> <evidence>`` line
per gate, then ``SHIP-CHECK: PASS 14/14`` or ``SHIP-CHECK: FAIL <passed>/14``. With
``--fast`` the slow ``make ci`` reruns are skipped (G3 is derived from the G1, G2, and
G4 steps instead) and the last line is ``SHIP-CHECK-FAST (does not count): <passed>/14``.

A gate whose property ranges over a set (preregistrations, headline variants,
references, benchmarks) fails when the set is empty: an empty set proves nothing.

Artifact contracts checked here (later iterations may tighten them, never loosen):

* E0 ``artifacts/e0/results.json``: ``labels_path``, ``labels_sha256_path``,
  ``bootstrap {seed, B, alpha}``, ``tasks [{task, planted, slice, flagged,
  adjudicated_real}]``, ``recall`` and ``precision`` as ``{point, ci: [lo, hi]}``,
  ``provenance``. Labels file: ``{"tasks": {<task>: {"planted": bool, "slice": str}}}``.
* Audits ``artifacts/audit/<benchmark>/``: ``summary.json`` (``benchmark``,
  ``category``, ``confirmatory``, ``prereg``, ``substitute_for``,
  ``n_tasks_population``, ``n_sampled``, ``bootstrap``, ``e1.false_accept_task_rate``,
  ``e2.false_reject_task_rate``, ``provenance``), ``tasks.jsonl`` (``task_hash``,
  ``flaky``), ``variants.jsonl`` (``variant_id``, ``task_hash``, ``kind``,
  ``counted_in_headline``, ``witness_sha256``, ``validations [{validator, verdict}]``,
  ``grader_passed``).
* E4 ``artifacts/e4/summary.json``: ``ran``, ``repaired [{task_hash, benchmark,
  public, patch, validation_log}]``, ``generalization {n_fresh_variants, ...}``.
* E5 ``artifacts/e5/<benchmark>/summary.json``: ``ran``, ``pass_flips``,
  ``rank_changes``, each with ``ci``.
* Review ``artifacts/review/latest.json`` (schema in tools/review.py).
* Citations ``artifacts/citecheck.json`` (schema in .claude/agents/citation-checker.md).
* Figures ``artifacts/figures/manifest.json``: ``[{path, sha256}]`` written by make report.

Bootstrap intervals use the percentile method over tasks with ``random.Random(seed)``:
each of ``B`` replicates draws ``n`` task indices with ``rng.randrange(n)``; replicates
whose statistic is undefined (zero denominator) are dropped; the interval is the
``floor(alpha/2 * m)`` and ``ceil((1 - alpha/2) * m) - 1`` order statistics of the ``m``
kept replicates. graderproof's own statistics must use the identical procedure. When one
artifact carries two intervals, the second uses ``seed + 1`` (E0: recall ``seed``,
precision ``seed + 1``; audits: E1 ``seed``, E2 ``seed + 1``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ORIGIN = Path(__file__).resolve().parent.parent
EM_DASH = chr(0x2014)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
COVERAGE_MIN = 85.0
E0_MIN = 0.90
E0_MIN_TASKS = 60
AUDIT_MIN_BENCHMARKS = 3
AUDIT_MIN_SAMPLE = 40
DEMO_MAX_S = 180.0
REPORT_WORDS = (4000, 8000)
CI_STEPS = ("lint", "typecheck", "test", "demo")
REVIEW_ALLOWED_PREFIXES = ("artifacts/review/",)
REVIEW_ALLOWED_FILES = ("STATUS.md", "docs/LOG.md")
REQUIRED_FILES = ("LICENSE", "CITATION.cff", "SECURITY.md", "CONTRIBUTING.md")
README_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("what it is and is not", ("what it is",)),
    ("key results", ("key results", "results")),
    ("how it works", ("how it works",)),
    ("use on your own benchmark", ("your own",)),
    ("reproduce", ("reproduc",)),
    ("limitations", ("limitation",)),
    ("responsible disclosure", ("disclosure",)),
    ("related work", ("related work",)),
    ("citation", ("citation", "cite")),
    ("license", ("license",)),
)
REPORT_SECTIONS = (
    "abstract",
    "introduction",
    "related work",
    "method",
    "experiments",
    "results",
    "limitations",
    "ethics",
    "disclosure",
    "reproducib",
)


# --------------------------------------------------------------------------- helpers


@dataclass
class Result:
    """Outcome of one gate."""

    ok: bool
    evidence: str


@dataclass
class Step:
    """Outcome of one sub-command."""

    rc: int
    out: str
    seconds: float
    stdout: str = ""


@dataclass
class Ctx:
    """Shared state for one ship-check run."""

    origin: Path
    work: Path
    fast: bool
    head: str = ""
    clone: Path = field(default_factory=Path)
    steps: dict[str, Step] = field(default_factory=dict)
    origin_facts: dict[str, Any] = field(default_factory=dict)

    @property
    def logs(self) -> Path:
        return self.work / "logs"

    def run(
        self,
        name: str,
        cmd: Sequence[str],
        cwd: Path | None = None,
        timeout: float = 1800.0,
        env: Mapping[str, str] | None = None,
    ) -> Step:
        """Run a sub-command, log it to the temp dir, and remember it by ``name``."""
        self.logs.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                list(cmd),
                cwd=str(cwd or self.clone),
                env=dict(env) if env is not None else clean_env(),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            rc, out, stdout = proc.returncode, proc.stdout + proc.stderr, proc.stdout
        except subprocess.TimeoutExpired as exc:
            rc, out, stdout = 124, f"timeout after {timeout}s: {exc}", ""
        except OSError as exc:
            rc, out, stdout = 127, f"could not start: {exc}", ""
        step = Step(rc, out, time.monotonic() - start, stdout)
        (self.logs / f"{name}.log").write_text(f"$ {' '.join(cmd)}\n{out}\nrc={rc}\n")
        self.steps[name] = step
        return step


def clean_env() -> dict[str, str]:
    """Environment for sub-commands: no activated venv, no bytecode in the origin."""
    env = dict(os.environ)
    for k in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH"):
        env.pop(k, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["UV_NO_PROGRESS"] = "1"
    return env


def git(cwd: Path, *args: str) -> tuple[int, str]:
    """Run git without taking optional locks (so the origin index is not rewritten)."""
    proc = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    """Hex SHA-256 of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    """Parse a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSON-lines file (missing file means no rows)."""
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def first_commit(repo: Path, path: str) -> str | None:
    """The commit that first added ``path`` (a file or directory), or None."""
    rc, out = git(repo, "log", "--diff-filter=A", "--format=%H", "--reverse", "--", path)
    lines = out.splitlines() if rc == 0 else []
    return lines[0] if lines else None


def commits_touching(repo: Path, path: str) -> list[str]:
    """Every commit that changed ``path``, newest first."""
    rc, out = git(repo, "log", "--format=%H", "--", path)
    return out.splitlines() if rc == 0 and out else []


def strictly_before(repo: Path, a: str, b: str) -> bool:
    """True if commit ``a`` is a proper ancestor of commit ``b``."""
    if a == b:
        return False
    rc, _ = git(repo, "merge-base", "--is-ancestor", a, b)
    return rc == 0


def earliest_commit(repo: Path, paths: Iterable[str]) -> str | None:
    """Of the first-add commits of ``paths``, the one that is an ancestor of all others."""
    commits = [c for c in (first_commit(repo, p) for p in paths) if c]
    if not commits:
        return None
    best = commits[0]
    for c in commits[1:]:
        if strictly_before(repo, c, best):
            best = c
    return best


def one_line(text: str, limit: int = 160) -> str:
    """Collapse whitespace and truncate for an evidence field."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def tail(out: str, n: int = 1) -> str:
    """Last ``n`` non-empty lines of command output, collapsed."""
    lines = [ln for ln in out.splitlines() if ln.strip() and "UV_NATIVE_TLS" not in ln]
    return one_line(" | ".join(lines[-n:])) if lines else "(no output)"


def fmt(x: float) -> str:
    """Format a statistic for evidence."""
    return f"{x:.3f}"


# ------------------------------------------------------------------------ statistics


def bootstrap_ci(
    n: int,
    stat: Callable[[Sequence[int]], float | None],
    seed: int,
    replicates: int,
    alpha: float = 0.05,
) -> tuple[float, float] | None:
    """Percentile bootstrap interval of ``stat`` over resampled task indices.

    ``stat`` takes a list of task indices and returns the statistic, or None when it
    is undefined for that resample. See the module docstring for the exact procedure.
    """
    if n <= 0 or replicates <= 0:
        return None
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(replicates):
        idx = [rng.randrange(n) for _ in range(n)]
        v = stat(idx)
        if v is not None:
            values.append(v)
    if not values:
        return None
    values.sort()
    m = len(values)
    lo = values[math.floor(alpha / 2 * m)]
    hi = values[max(0, math.ceil((1 - alpha / 2) * m) - 1)]
    return lo, hi


def ratio(num: int, den: int) -> float | None:
    """num / den, or None when den is zero."""
    return num / den if den else None


def close(a: Any, b: float, tol: float = 1e-9) -> bool:
    """Whether an artifact number ``a`` equals a recomputed ``b``."""
    return isinstance(a, int | float) and abs(float(a) - b) <= tol


def close_ci(a: Any, b: tuple[float, float] | None, tol: float = 1e-9) -> bool:
    """Whether an artifact interval ``a`` equals a recomputed interval ``b``."""
    return (
        b is not None
        and isinstance(a, list)
        and len(a) == 2
        and close(a[0], b[0], tol)
        and close(a[1], b[1], tol)
    )


def bootstrap_params(obj: Mapping[str, Any]) -> tuple[int, int, float]:
    """(seed, B, alpha) from an artifact's ``bootstrap`` block."""
    b = obj.get("bootstrap") or {}
    return int(b["seed"]), int(b["B"]), float(b.get("alpha", 0.05))


def provenance_ok(obj: Mapping[str, Any]) -> list[str]:
    """Missing provenance fields of an artifact."""
    prov = obj.get("provenance")
    if not isinstance(prov, Mapping):
        return ["provenance"]
    need = ("git_sha", "command", "created_utc")
    return [k for k in need if not prov.get(k)]


# ------------------------------------------------------------- phase A: the origin


def check_origin(ctx: Ctx) -> None:
    """Checks that must run in the original checkout (G14 tree parts, G8 manifests)."""
    rc, status = git(ctx.origin, "status", "--porcelain", "--untracked-files=all")
    ctx.origin_facts["tree_clean"] = rc == 0 and status == ""
    ctx.origin_facts["tree_dirty_count"] = len(status.splitlines()) if status else 0
    _, tracked_private = git(ctx.origin, "ls-files", "--", "private")
    ctx.origin_facts["private_tracked"] = [p for p in tracked_private.splitlines() if p]
    ctx.origin_facts["manifest"] = verify_manifest(ctx.origin)


def verify_manifest(repo: Path) -> dict[str, Any]:
    """Verify outbound/patches/MANIFEST.json entries against files under private/."""
    path = repo / "outbound" / "patches" / "MANIFEST.json"
    rc, _ = git(repo, "ls-files", "--error-unmatch", "outbound/patches/MANIFEST.json")
    if not path.exists() or rc != 0:
        return {"present": False, "entries": {}, "problems": []}
    problems: list[str] = []
    entries: dict[str, str] = {}
    try:
        data = load_json(path)
        rows = data.get("files", []) if isinstance(data, Mapping) else []
    except ValueError as exc:
        return {"present": True, "entries": {}, "problems": [f"MANIFEST.json invalid: {exc}"]}
    for row in rows:
        rel = str(row.get("path", ""))
        want = str(row.get("sha256", ""))
        if not rel.startswith("private/outbound/patches/"):
            problems.append(f"{rel}: not under private/outbound/patches/")
            continue
        f = repo / rel
        if not f.exists():
            problems.append(f"{rel}: missing")
        elif sha256_file(f) != want:
            problems.append(f"{rel}: sha256 mismatch")
        entries[rel] = want
    return {"present": True, "entries": entries, "problems": problems}


def make_clone(ctx: Ctx) -> None:
    """Fresh clone of HEAD into the temp dir."""
    ctx.clone = ctx.work / "clone"
    step = ctx.run(
        "clone",
        ["git", "clone", "--quiet", "--no-hardlinks", str(ctx.origin), str(ctx.clone)],
        cwd=ctx.work,
        timeout=600,
    )
    if step.rc != 0:
        raise RuntimeError(f"git clone failed: {tail(step.out)}")
    step = ctx.run("checkout", ["git", "checkout", "--quiet", "--detach", ctx.head])
    if step.rc != 0:
        raise RuntimeError(f"git checkout failed: {tail(step.out)}")


# --------------------------------------------------------------------------- gates


def g1_build_and_tests(ctx: Ctx) -> Result:
    """make setup, make test, >= 85% line coverage on core modules."""
    setup = ctx.run("setup", ["make", "setup"], timeout=1200)
    if setup.rc != 0:
        return Result(False, f"make setup failed: {tail(setup.out)}")
    test = ctx.run("test", ["make", "test"], timeout=3600)
    junit = junit_counts(ctx.clone / "junit.xml")
    if test.rc != 0:
        return Result(False, f"make test failed: {tail(test.out)}")
    if junit is None or junit["tests"] == 0:
        return Result(False, "make test ran no tests (junit.xml missing or empty)")
    if junit["failures"] or junit["errors"]:
        return Result(False, f"junit reports failures {junit['failures']} errors {junit['errors']}")
    cov = core_coverage(ctx.clone)
    if isinstance(cov, str):
        return Result(False, cov)
    pct, n_files, excluded = cov
    ok = pct >= COVERAGE_MIN
    return Result(
        ok,
        f"setup ok; {junit['tests']} tests pass ({junit['skipped']} skipped); core line coverage "
        f"{pct:.1f}% over {n_files} files (min {COVERAGE_MIN:.0f}%); "
        f"{len(excluded)} fixture-covered adapters excluded",
    )


def junit_counts(path: Path) -> dict[str, int] | None:
    """Totals from a pytest junit.xml."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for m in re.finditer(r"<testsuite\b([^>]*)>", text):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        for k in totals:
            totals[k] += int(attrs.get(k, "0") or 0)
    return totals


def core_coverage(clone: Path) -> tuple[float, int, list[str]] | str:
    """Summed line coverage over every package module except fixture-covered adapters."""
    cov_path = clone / "coverage.json"
    if not cov_path.exists():
        return "coverage.json not written by make test"
    with (clone / "pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)
    excluded = list(
        pyproject.get("tool", {})
        .get("graderproof", {})
        .get("coverage", {})
        .get("external_adapters", [])
    )
    for rel in excluded:
        stem = Path(rel).stem
        if not rel.startswith("src/graderproof/adapters/"):
            return f"coverage exclusion {rel} is not an adapter"
        contract = clone / "tests" / "contract" / f"test_{stem}.py"
        fixtures = clone / "tests" / "fixtures" / stem
        if not contract.exists() or not fixtures.is_dir() or not any(fixtures.iterdir()):
            return f"excluded adapter {rel} lacks a recorded-fixture contract test"
    files = load_json(cov_path).get("files", {})
    measured = {str(Path(k).as_posix()): v for k, v in files.items()}
    package = sorted(
        p.relative_to(clone).as_posix() for p in (clone / "src" / "graderproof").rglob("*.py")
    )
    covered = statements = 0
    n = 0
    for rel in package:
        if rel in excluded:
            continue
        data = measured.get(rel)
        if data is None:
            return f"{rel} not measured by coverage"
        summary = data.get("summary", {})
        covered += int(summary.get("covered_lines", 0))
        statements += int(summary.get("num_statements", 0))
        n += 1
    if statements == 0:
        return "no statements measured"
    return 100.0 * covered / statements, n, excluded


def g2_static_quality(ctx: Ctx) -> Result:
    """ruff check, ruff format --check, mypy --strict on the package, reasons on ignores."""
    if ctx.steps.get("setup") is None or ctx.steps["setup"].rc != 0:
        return Result(False, "no environment (make setup failed)")
    problems = []
    checks = {
        "ruff-check": ["uv", "run", "--frozen", "ruff", "check", "."],
        "ruff-format": ["uv", "run", "--frozen", "ruff", "format", "--check", "."],
        "mypy": ["uv", "run", "--frozen", "mypy", "--strict", "src/graderproof"],
    }
    for name, cmd in checks.items():
        step = ctx.run(name, cmd, timeout=900)
        if step.rc != 0:
            problems.append(f"{name}: {tail(step.out)}")
    weak = mypy_weakening(ctx.clone)
    if weak:
        problems.append(f"mypy config weakened: {weak}")
    bare = bare_type_ignores(ctx.clone)
    if bare:
        problems.append(f"type: ignore without reason at {', '.join(bare[:3])}")
    if problems:
        return Result(False, "; ".join(problems))
    return Result(
        True, "ruff check, ruff format --check, mypy --strict clean; every ignore has a reason"
    )


def mypy_weakening(clone: Path) -> str:
    """Config that would make mypy --strict pass vacuously."""
    with (clone / "pyproject.toml").open("rb") as fh:
        mypy = tomllib.load(fh).get("tool", {}).get("mypy", {})
    if mypy.get("ignore_errors"):
        return "ignore_errors"
    for ov in mypy.get("overrides", []):
        if ov.get("ignore_errors"):
            return f"ignore_errors override for {ov.get('module')}"
    if (clone / "mypy.ini").exists() or (clone / "setup.cfg").exists():
        return "extra mypy config file"
    return ""


IGNORE_RE = re.compile(r"#\s*type:\s*ignore(\[[^\]]*\])?(.*)$")


def bare_type_ignores(clone: Path) -> list[str]:
    """``type: ignore`` comments without a trailing ``# reason``."""
    hits = []
    for top in ("src", "tests", "tools"):
        for p in sorted((clone / top).rglob("*.py")) if (clone / top).exists() else []:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                m = IGNORE_RE.search(line)
                if m and not re.match(r"\s*#\s*\S", m.group(2)):
                    hits.append(f"{p.relative_to(clone).as_posix()}:{i}")
    return hits


def g3_ci_parity(ctx: Ctx) -> Result:
    """ci.yml runs make ci on 3.11 and 3.12; make ci covers lint/typecheck/test/demo; passes."""
    wf = workflow_problems(ctx)
    if wf:
        return Result(False, wf)
    mk = makefile_ci_problems(ctx.clone / "Makefile")
    if mk:
        return Result(False, mk)
    if ctx.fast:
        parts = {
            "lint": all(
                ctx.steps[k].rc == 0 for k in ("ruff-check", "ruff-format") if k in ctx.steps
            )
            and "ruff-check" in ctx.steps,
            "typecheck": "mypy" in ctx.steps and ctx.steps["mypy"].rc == 0,
            "test": "test" in ctx.steps and ctx.steps["test"].rc == 0,
            "demo": "demo" in ctx.steps and ctx.steps["demo"].rc == 0,
        }
        bad = [k for k, v in parts.items() if not v]
        if bad:
            return Result(False, f"ci.yml ok; make ci parts failing (fast, not rerun): {bad}")
        return Result(True, "ci.yml runs make ci on 3.11 and 3.12; parts pass (fast, not rerun)")
    step = ctx.run("ci", ["make", "ci"], timeout=3600)
    if step.rc != 0:
        return Result(False, f"make ci failed: {tail(step.out)}")
    return Result(
        True, f"ci.yml runs make ci on 3.11 and 3.12; make ci passed in {step.seconds:.0f}s"
    )


def workflow_problems(ctx: Ctx) -> str:
    """Problems with .github/workflows/ci.yml, parsed with the clone's PyYAML."""
    path = ctx.clone / ".github" / "workflows" / "ci.yml"
    if not path.exists():
        return ".github/workflows/ci.yml missing"
    code = (
        "import json,sys,yaml;"
        "print(json.dumps(yaml.safe_load(open(sys.argv[1], encoding='utf-8'))))"
    )
    step = ctx.run("ci-yaml", ["uv", "run", "--frozen", "python", "-c", code, str(path)])
    if step.rc != 0:
        return f"ci.yml unparsable: {tail(step.out)}"
    try:
        doc = json.loads(step.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return "ci.yml unparsable"
    for job in (doc.get("jobs") or {}).values():
        matrix = ((job or {}).get("strategy") or {}).get("matrix") or {}
        versions = {str(v) for v in matrix.get("python-version", [])}
        runs = [str(s.get("run", "")) for s in (job.get("steps") or []) if isinstance(s, dict)]
        runs_ci = any(re.search(r"(^|\s|;|&&)make ci(\s|$|;|&)", r) for r in runs)
        uses_matrix = "matrix.python-version" in json.dumps(job)
        if {"3.11", "3.12"} <= versions and runs_ci and uses_matrix:
            return ""
    return "no ci.yml job runs `make ci` with a matrix over Python 3.11 and 3.12"


def makefile_ci_problems(makefile: Path) -> str:
    """Whether the ``ci`` target depends on lint, typecheck, test, and demo."""
    text = makefile.read_text(encoding="utf-8")
    m = re.search(r"^ci:([^\n#]*)", text, re.M)
    if not m:
        return "Makefile has no ci target"
    deps = m.group(1).split()
    missing = [s for s in CI_STEPS if s not in deps]
    return f"make ci does not run {missing}" if missing else ""


def network_isolation() -> tuple[list[str], str] | None:
    """A command prefix that runs a child with no network, and its name."""
    if shutil.which("unshare"):
        probe = subprocess.run(["unshare", "-rn", "true"], capture_output=True, check=False)
        if probe.returncode == 0:
            return ["unshare", "-rn"], "unshare -rn"
    if shutil.which("sandbox-exec"):
        return ["sandbox-exec", "-p", "(version 1)(allow default)(deny network*)"], "sandbox-exec"
    return None


def g4_offline_demo(ctx: Ctx) -> Result:
    """make demo < 3 min, no network, no model calls, output equals golden."""
    if ctx.steps.get("setup") is None or ctx.steps["setup"].rc != 0:
        return Result(False, "no environment (make setup failed)")
    golden = ctx.clone / "tests" / "golden" / "demo_output.txt"
    iso = network_isolation()
    if iso is None:
        return Result(False, "cannot isolate the network for make demo on this machine")
    prefix, iso_name = iso
    env = clean_env()
    for k in list(env):
        if k.lower() in ("http_proxy", "https_proxy", "all_proxy"):
            env.pop(k)
    env.update({"UV_OFFLINE": "1", "GRADERPROOF_OFFLINE": "1", "GRADERPROOF_NO_MODEL_CALLS": "1"})
    ledger = ctx.clone / "artifacts" / "usage" / "ledger.jsonl"
    before = sha256_file(ledger) if ledger.exists() else None
    step = ctx.run("demo", [*prefix, "make", "-s", "demo"], timeout=DEMO_MAX_S * 3, env=env)
    after = sha256_file(ledger) if ledger.exists() else None
    if step.rc != 0:
        return Result(False, f"make demo failed: {tail(step.out)}")
    if before != after:
        return Result(False, "make demo changed the usage ledger (model call)")
    if step.seconds >= DEMO_MAX_S:
        return Result(False, f"make demo took {step.seconds:.0f}s (limit {DEMO_MAX_S:.0f}s)")
    if not golden.exists():
        return Result(False, "tests/golden/demo_output.txt missing")
    (ctx.logs / "demo.stdout").write_text(step.stdout)
    if step.stdout != golden.read_text(encoding="utf-8"):
        return Result(False, "make demo output differs from tests/golden/demo_output.txt")
    return Result(True, f"{step.seconds:.0f}s under {iso_name}, no ledger change, matches golden")


def g5_tool_validity(ctx: Ctx) -> Result:
    """E0 recall and precision >= 0.90 with 95% intervals; misses explained."""
    c = ctx.clone
    res_path = c / "artifacts" / "e0" / "results.json"
    if not res_path.exists():
        return Result(False, "artifacts/e0/results.json missing (E0 not run)")
    res = load_json(res_path)
    missing = provenance_ok(res)
    if missing:
        return Result(False, f"E0 results lack provenance fields {missing}")
    labels_path = c / str(res.get("labels_path", ""))
    hash_path = c / str(res.get("labels_sha256_path", ""))
    if not labels_path.is_file() or not hash_path.is_file():
        return Result(False, "toybench labels or labels hash file missing")
    committed = hash_path.read_text().split()[0] if hash_path.read_text().split() else ""
    if sha256_file(labels_path) != committed:
        return Result(False, "toybench labels do not match their committed hash")
    hash_commit = first_commit(c, str(res["labels_sha256_path"]))
    e0_files = [p.relative_to(c).as_posix() for p in (c / "artifacts" / "e0").rglob("*")]
    first_run = earliest_commit(c, [f for f in e0_files if (c / f).is_file()])
    if not hash_commit or not first_run or not strictly_before(c, hash_commit, first_run):
        return Result(False, "labels hash was not committed before the first E0 artifact")
    labels = load_json(labels_path).get("tasks", {})
    rows = [r for r in res.get("tasks", []) if r.get("slice") != "extra"]
    for r in res.get("tasks", []):
        lab = labels.get(r.get("task"))
        if lab is None or bool(lab.get("planted")) != bool(r.get("planted")):
            return Result(False, f"E0 task {r.get('task')} disagrees with the committed labels")
        if lab.get("slice") != r.get("slice"):
            return Result(False, f"E0 task {r.get('task')} slice disagrees with the labels")
    if len(rows) < E0_MIN_TASKS:
        return Result(False, f"E0 has {len(rows)} counted tasks (< {E0_MIN_TASKS})")
    planted = [bool(r.get("planted")) for r in rows]
    flagged = [bool(r.get("flagged")) for r in rows]
    real = [bool(r.get("adjudicated_real")) and not p for r, p in zip(rows, planted, strict=True)]

    def rec(idx: Sequence[int]) -> float | None:
        tp = sum(1 for i in idx if planted[i] and flagged[i])
        return ratio(tp, sum(1 for i in idx if planted[i]))

    def prec(idx: Sequence[int]) -> float | None:
        tp = sum(1 for i in idx if planted[i] and flagged[i])
        fp = sum(1 for i in idx if flagged[i] and not planted[i] and not real[i])
        return ratio(tp, tp + fp)

    all_idx = list(range(len(rows)))
    r_pt, p_pt = rec(all_idx), prec(all_idx)
    if r_pt is None or p_pt is None:
        return Result(False, "E0 recall or precision undefined")
    seed, b, alpha = bootstrap_params(res)
    r_ci = bootstrap_ci(len(rows), rec, seed, b, alpha)
    p_ci = bootstrap_ci(len(rows), prec, seed + 1, b, alpha)
    stated_r, stated_p = res.get("recall", {}), res.get("precision", {})
    if not (close(stated_r.get("point"), r_pt) and close(stated_p.get("point"), p_pt)):
        return Result(False, "E0 stated recall/precision differ from recomputation")
    if not (close_ci(stated_r.get("ci"), r_ci) and close_ci(stated_p.get("ci"), p_ci)):
        return Result(False, "E0 stated intervals differ from recomputation")
    misses = [str(r["task"]) for r, p, f in zip(rows, planted, flagged, strict=True) if p and not f]
    misses_doc = c / "docs" / "E0_MISSES.md"
    if not misses_doc.exists():
        return Result(False, "docs/E0_MISSES.md missing")
    doc = misses_doc.read_text(encoding="utf-8")
    unexplained = [m for m in misses if m not in doc]
    assert r_ci is not None and p_ci is not None
    ev = (
        f"recall {fmt(r_pt)} [{fmt(r_ci[0])}, {fmt(r_ci[1])}], precision {fmt(p_pt)} "
        f"[{fmt(p_ci[0])}, {fmt(p_ci[1])}], n={len(rows)}, {len(misses)} misses"
    )
    if unexplained:
        return Result(False, f"{ev}; unexplained misses {unexplained[:3]}")
    return Result(r_pt >= E0_MIN and p_pt >= E0_MIN, f"{ev} (min {E0_MIN})")


def audit_dirs(clone: Path) -> list[Path]:
    """Benchmark audit directories under artifacts/audit/."""
    root = clone / "artifacts" / "audit"
    return (
        sorted(p for p in root.iterdir() if (p / "summary.json").exists()) if root.exists() else []
    )


def all_variant_files(clone: Path) -> list[Path]:
    """Every banked variants.jsonl (E0 and audits)."""
    return sorted((clone / "artifacts").rglob("variants.jsonl"))


def g6_validation_integrity(ctx: Ctx) -> Result:
    """Every headline variant has two agreeing validations and a witness."""
    files = all_variant_files(ctx.clone)
    rows = [r for f in files for r in read_jsonl(f)]
    headline = [r for r in rows if r.get("counted_in_headline")]
    if not headline:
        return Result(False, "no headline variants banked (artifacts/**/variants.jsonl)")
    bad_val = bad_wit = 0
    for r in headline:
        verdicts: dict[str, Any] = {}
        for v in r.get("validations", []):
            verdicts[str(v.get("validator"))] = v.get("verdict")
        if len(verdicts) < 2 or set(verdicts.values()) != {r.get("kind")}:
            bad_val += 1
        if not HEX64.match(str(r.get("witness_sha256", ""))):
            bad_wit += 1
    judged = [
        r for r in rows if len({str(v.get("validator")) for v in r.get("validations", [])}) >= 2
    ]
    agree = sum(1 for r in judged if len({v.get("verdict") for v in r.get("validations", [])}) == 1)
    excluded = len(rows) - len(headline)
    rate = agree / len(judged) if judged else 0.0
    ev = (
        f"{len(headline)} headline variants; agreement {fmt(rate)} ({agree}/{len(judged)}); "
        f"excluded {excluded}; lacking two agreeing validations {bad_val}; "
        f"lacking witness {bad_wit}"
    )
    return Result(bad_val == 0 and bad_wit == 0, ev)


def task_indicators(adir: Path) -> tuple[list[dict[str, Any]], list[bool], list[bool]] | str:
    """Per-task false-accept and false-reject indicators recomputed from variants.

    Flaky tasks are excluded from both rates (they are reported separately).
    """
    tasks = read_jsonl(adir / "tasks.jsonl")
    variants = read_jsonl(adir / "variants.jsonl")
    if not tasks:
        return "tasks.jsonl missing or empty"
    by_task: dict[str, list[dict[str, Any]]] = {}
    for v in variants:
        by_task.setdefault(str(v.get("task_hash")), []).append(v)
    kept = [t for t in tasks if not t.get("flaky")]
    fa, fr = [], []
    for t in kept:
        vs = [v for v in by_task.get(str(t.get("task_hash")), []) if v.get("counted_in_headline")]
        fa.append(any(v.get("kind") == "violating" and v.get("grader_passed") for v in vs))
        fr.append(any(v.get("kind") == "preserving" and not v.get("grader_passed") for v in vs))
    return kept, fa, fr


def g7_confirmatory_audit(ctx: Ctx) -> Result:
    """E1 and E2 as preregistered on >= 3 benchmarks, with intervals; substitutes justified."""
    c = ctx.clone
    dirs = audit_dirs(c)
    good: list[str] = []
    problems: list[str] = []
    categories: set[str] = set()
    decisions = (
        (c / "DECISIONS.md").read_text(encoding="utf-8") if (c / "DECISIONS.md").exists() else ""
    )
    for d in dirs:
        s = load_json(d / "summary.json")
        name = str(s.get("benchmark", d.name))
        why = audit_problems(c, d, s, decisions)
        if why:
            problems.append(f"{name}: {why}")
            continue
        good.append(name)
        categories.add(str(s.get("category", "")))
    if len(good) < AUDIT_MIN_BENCHMARKS:
        detail = f"; {problems[0]}" if problems else ""
        return Result(
            False, f"{len(good)} benchmarks pass E1/E2 checks (< {AUDIT_MIN_BENCHMARKS}){detail}"
        )
    if "tool-use" not in categories:
        return Result(False, f"no tool-use benchmark among {good}")
    if problems:
        return Result(False, f"{problems[0]}")
    return Result(
        True, f"E1 and E2 banked with recomputed intervals on {len(good)} benchmarks: {good}"
    )


def audit_problems(c: Path, d: Path, s: Mapping[str, Any], decisions: str) -> str:
    """Why one benchmark audit does not meet G7, or empty if it does."""
    missing = provenance_ok(s)
    if missing:
        return f"provenance lacks {missing}"
    if not s.get("confirmatory"):
        return "not marked confirmatory"
    prereg = str(s.get("prereg", ""))
    if not prereg.startswith("prereg/") or not (c / prereg).is_file():
        return "cites no existing preregistration"
    pop, n = int(s.get("n_tasks_population", 0)), int(s.get("n_sampled", 0))
    if n < min(AUDIT_MIN_SAMPLE, pop) or pop <= 0:
        return f"sample {n} below min(40, population {pop})"
    ind = task_indicators(d)
    if isinstance(ind, str):
        return ind
    _, fa, fr = ind
    total = len(read_jsonl(d / "tasks.jsonl"))
    if total != n:
        return f"tasks.jsonl has {total} tasks, summary says {n}"
    seed, b, alpha = bootstrap_params(s)
    for key, sub, vals, offset in (
        ("e1", "false_accept_task_rate", fa, 0),
        ("e2", "false_reject_task_rate", fr, 1),
    ):
        stated = (s.get(key) or {}).get(sub) or {}
        point = ratio(sum(vals), len(vals))
        if point is None:
            return f"{key} has no non-flaky tasks"
        ci = bootstrap_ci(len(vals), mean_of(vals), seed + offset, b, alpha)
        if not close(stated.get("point"), point) or not close_ci(stated.get("ci"), ci):
            return f"{key} {sub} differs from recomputation"
    sub_for = s.get("substitute_for")
    if sub_for:
        did = str((sub_for or {}).get("decision", ""))
        if not did or did not in decisions:
            return "substitution not justified in DECISIONS.md"
        dec_commit = first_commit_containing(c, "DECISIONS.md", did)
        art_commit = earliest_commit(
            c, [p.relative_to(c).as_posix() for p in d.rglob("*") if p.is_file()]
        )
        if not dec_commit or not art_commit or not strictly_before(c, dec_commit, art_commit):
            return f"substitution decision {did} not committed before data collection"
    return ""


def mean_of(values: Sequence[bool]) -> Callable[[Sequence[int]], float | None]:
    """Statistic for :func:`bootstrap_ci`: the share of resampled tasks that are True."""

    def stat(idx: Sequence[int]) -> float | None:
        return ratio(sum(values[i] for i in idx), len(idx))

    return stat


def first_commit_containing(repo: Path, path: str, needle: str) -> str | None:
    """The oldest commit whose change to ``path`` added ``needle`` (git log -S)."""
    rc, out = git(repo, "log", "--reverse", "--format=%H", "-S", needle, "--", path)
    lines = out.splitlines() if rc == 0 and out else []
    return lines[0] if lines else None


def g8_repair(ctx: Ctx) -> Result:
    """E4 with generalization batch; every repaired task has a patch and validation log."""
    c = ctx.clone
    man = ctx.origin_facts.get("manifest", {})
    if man.get("problems"):
        return Result(False, f"private patch manifest: {man['problems'][0]}")
    path = c / "artifacts" / "e4" / "summary.json"
    if not path.exists():
        return Result(False, "artifacts/e4/summary.json missing (E4 not run)")
    s = load_json(path)
    missing = provenance_ok(s)
    if missing or not s.get("ran"):
        return Result(False, f"E4 not marked ran or lacks provenance {missing}")
    gen = s.get("generalization") or {}
    if int(gen.get("n_fresh_variants", 0)) <= 0:
        return Result(False, "no post-repair generalization batch")
    repaired = s.get("repaired") or []
    entries = man.get("entries", {})
    pub = priv = 0
    for r in repaired:
        for key in ("patch", "validation_log"):
            rel = str(r.get(key, ""))
            if r.get("public"):
                if not rel.startswith("outbound/patches/") or not (c / rel).is_file():
                    return Result(
                        False, f"public {key} {rel or '?'} missing under outbound/patches/"
                    )
            else:
                if not rel.startswith("private/outbound/patches/") or rel not in entries:
                    return Result(False, f"private {key} {rel or '?'} not in MANIFEST.json")
                if (c / rel).exists():
                    return Result(False, f"private {key} {rel} is tracked")
        pub += bool(r.get("public"))
        priv += not r.get("public")
    return Result(
        True,
        f"E4 ran; {len(repaired)} repaired ({pub} public, {priv} private, hashes verified); "
        f"generalization batch {gen.get('n_fresh_variants')} variants",
    )


def g9_impact_and_cards(ctx: Ctx) -> Result:
    """E5 on >= 1 benchmark; a grader card per audited benchmark, aggregates only."""
    c = ctx.clone
    e5 = (
        sorted((c / "artifacts" / "e5").glob("*/summary.json"))
        if (c / "artifacts" / "e5").exists()
        else []
    )
    ran = []
    for p in e5:
        s = load_json(p)
        if s.get("ran") and not provenance_ok(s):
            flips, ranks = s.get("pass_flips") or {}, s.get("rank_changes") or {}
            if isinstance(flips.get("ci"), list) and isinstance(ranks.get("ci"), list):
                ran.append(p.parent.name)
    if not ran:
        return Result(False, "no E5 impact artifact with intervals (artifacts/e5/*/summary.json)")
    dirs = audit_dirs(c)
    if not dirs:
        return Result(False, "no audited benchmarks to card")
    for d in dirs:
        bench = str(load_json(d / "summary.json").get("benchmark", d.name))
        md, js = c / "docs" / "cards" / f"{bench}.md", c / "docs" / "cards" / f"{bench}.json"
        if not md.exists() or not js.exists():
            return Result(False, f"grader card for {bench} missing (docs/cards/{bench}.md/.json)")
        card = load_json(js)
        leak = card_leak(bench, card, md.read_text(encoding="utf-8"), d)
        if leak:
            return Result(False, f"card {bench}: {leak}")
    return Result(True, f"E5 ran on {ran}; {len(dirs)} cards, aggregates only")


TASK_KEYS = {"tasks", "task_ids", "variants", "witnesses", "surviving_variants"}


def card_leak(bench: str, card: Mapping[str, Any], md: str, adir: Path) -> str:
    """Task-level detail for unfixed tasks in a card, or empty."""
    bad = TASK_KEYS & set(card)
    if bad:
        return f"task-level keys {sorted(bad)}"
    fixed = {sha256_text(f"{bench}:{t}") for t in card.get("fixed_upstream_tasks", [])}
    ind = task_indicators(adir)
    if isinstance(ind, str):
        return ind
    kept, fa, fr = ind
    flagged = {
        str(t.get("task_hash")) for t, a, r in zip(kept, fa, fr, strict=True) if a or r
    } - fixed
    text = md + json.dumps(card)
    for tok in set(re.findall(r"[A-Za-z0-9_\-./:]+", text)):
        if sha256_text(f"{bench}:{tok}") in flagged or tok in flagged:
            return "names a flagged task not fixed upstream"
    return ""


def g10_claim_integrity(ctx: Ctx) -> Result:
    """make claimcheck and make freshness pass on README.md and docs/REPORT.md."""
    c = ctx.clone
    if not (c / "docs" / "REPORT.md").exists():
        return Result(False, "docs/REPORT.md missing")
    out = []
    for name in ("claimcheck", "freshness"):
        step = ctx.run(name, ["make", "-s", name], timeout=1800)
        if step.rc != 0:
            return Result(False, f"make {name} failed: {tail(step.out)}")
        for doc in ("README.md", "docs/REPORT.md"):
            if doc not in step.out:
                return Result(False, f"make {name} did not report on {doc}")
        out.append(tail(step.out))
    return Result(True, "; ".join(out))


def confirmatory_artifacts(clone: Path) -> list[Path]:
    """Every summary.json under artifacts/ marked confirmatory."""
    found = []
    for p in sorted((clone / "artifacts").rglob("summary.json")):
        try:
            if load_json(p).get("confirmatory"):
                found.append(p)
        except ValueError:
            continue
    return found


def g11_prereg_integrity(ctx: Ctx) -> Result:
    """make prereg-verify, prereg commits predate artifacts, no prereg edited after freeze."""
    c = ctx.clone
    step = ctx.run("prereg-verify", ["make", "-s", "prereg-verify"], timeout=600)
    if step.rc != 0:
        return Result(False, f"make prereg-verify failed: {tail(step.out)}")
    preregs = sorted((c / "prereg").glob("[0-9][0-9][0-9][0-9]-*.md"))
    if not preregs:
        return Result(False, "no preregistrations")
    for p in preregs:
        rel = p.relative_to(c).as_posix()
        if len(commits_touching(c, rel)) != 1:
            return Result(False, f"{rel} changed after it was frozen")
    arts = confirmatory_artifacts(c)
    if not arts:
        return Result(False, "no confirmatory artifacts")
    for a in arts:
        s = load_json(a)
        prereg = str(s.get("prereg", ""))
        if not (c / prereg).is_file() or not prereg.startswith("prereg/"):
            return Result(False, f"{a.relative_to(c).as_posix()} cites no preregistration")
        pc = first_commit(c, prereg)
        files = [p.relative_to(c).as_posix() for p in a.parent.rglob("*") if p.is_file()]
        ac = earliest_commit(c, files)
        if not pc or not ac or not strictly_before(c, pc, ac):
            return Result(False, f"{prereg} does not predate {a.parent.relative_to(c).as_posix()}")
    return Result(
        True,
        f"{len(preregs)} preregistrations frozen; {len(arts)} confirmatory artifacts "
        f"follow them; {tail(step.out)}",
    )


def g12_independent_review(ctx: Ctx) -> Result:
    """Latest review is REVIEW: SHIP for the current code; non-blocking issues logged."""
    c = ctx.clone
    path = c / "artifacts" / "review" / "latest.json"
    if not path.exists():
        return Result(False, "no review yet (artifacts/review/latest.json missing)")
    step = ctx.run(
        "review-validate", ["python3", "tools/review.py", "--validate-only"], timeout=300
    )
    last = [ln for ln in step.out.splitlines() if ln.strip()][-1:] or [""]
    if last[0].strip() != "REVIEW: SHIP":
        return Result(False, f"latest review ends with {last[0].strip() or 'nothing'!r}")
    review = load_json(path)
    if review.get("blocking"):
        return Result(False, "open blocking issues")
    sha = str(review.get("reviewed_commit", ""))
    rc, names = git(c, "diff", "--name-only", sha, "HEAD")
    if rc != 0:
        return Result(False, "reviewed commit not in history")
    stray = [
        n
        for n in names.splitlines()
        if n and not (n.startswith(REVIEW_ALLOWED_PREFIXES) or n in REVIEW_ALLOWED_FILES)
    ]
    if stray:
        return Result(False, f"code changed since review: {stray[:3]}")
    log = c / "docs" / "REVIEW_LOG.md"
    nb = review.get("non_blocking") or []
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    unlisted = [
        i.get("id") for i in nb if str(i.get("id")) not in text or str(i.get("title")) not in text
    ]
    if unlisted:
        return Result(False, f"non-blocking issues not in docs/REVIEW_LOG.md: {unlisted[:3]}")
    return Result(True, f"REVIEW: SHIP for {sha[:12]}; 0 blocking; {len(nb)} non-blocking logged")


def headings(md: str) -> list[str]:
    """Markdown ATX headings (outside fenced code), lowercased."""
    out, fenced = [], False
    for line in md.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and re.match(r"^#{1,6}\s", line):
            out.append(line.lstrip("#").strip().lower())
    return out


def section(md: str, keyword: str) -> str:
    """Text of the first section whose heading contains ``keyword``."""
    lines = md.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m and start is None and keyword in m.group(2).lower():
            start, level = i + 1, len(m.group(1))
            continue
        if m and start is not None and level is not None and len(m.group(1)) <= level:
            return "\n".join(lines[start:i])
    return "\n".join(lines[start:]) if start is not None else ""


def readme_problems(clone: Path) -> str:
    """Section 11 structure of README.md, or empty if it complies."""
    readme = clone / "README.md"
    brief = clone / "docs" / "BUILD_BRIEF.md"
    if not readme.exists():
        return "README.md missing"
    md = readme.read_text(encoding="utf-8")
    if brief.exists() and md == brief.read_text(encoding="utf-8"):
        return "README.md is still the build brief"
    if EM_DASH in md:
        return "README.md contains an em dash"
    lines = md.splitlines()
    if not lines or not re.match(r"^#\s+graderproof\b", lines[0]):
        return "README.md does not start with '# graderproof'"
    first = "\n".join(lines[:60])
    if not re.search(r"\[\s*-?\d*\.?\d+\s*,\s*-?\d*\.?\d+\s*\]|\d+%\s*CI", first):
        return "first screen has no finding with a confidence interval"
    svg = re.search(r"!\[[^\]]*\]\(([^)\s]+\.svg)\)", first)
    if not svg:
        return "first screen has no SVG headline figure"
    fig = clone / svg.group(1)
    manifest = clone / "artifacts" / "figures" / "manifest.json"
    if not fig.exists() or not manifest.exists():
        return "headline figure or artifacts/figures/manifest.json missing"
    listed = {str(e.get("path")): str(e.get("sha256")) for e in load_json(manifest)}
    if listed.get(svg.group(1)) != sha256_file(fig):
        return "headline figure is not the one make report generated"
    if not re.search(r"^\|.*\|\s*$\n^\|[\s:|-]+\|\s*$", first, re.M):
        return "first screen has no table"
    qs = section(md, "quickstart")
    if "```" not in qs or "quickstart" not in first.lower():
        return "first screen has no quickstart with a code block"
    heads = headings(md)
    pos = 0
    for label, keys in README_SECTIONS:
        found = next((i for i in range(pos, len(heads)) if any(k in heads[i] for k in keys)), None)
        if found is None:
            return f"README.md lacks section '{label}' (in order)"
        pos = found + 1
    results = section(md, "key results") or section(md, "results")
    if "artifacts/" not in results or "prereg/" not in results:
        return "key results do not link artifacts and preregistrations"
    how = section(md, "how it works")
    if "```mermaid" not in how and not re.search(r"!\[[^\]]*\]\(", how):
        return "how it works has no diagram"
    return ""


def report_problems(clone: Path) -> str:
    """Completeness of docs/REPORT.md, or empty."""
    path = clone / "docs" / "REPORT.md"
    if not path.exists():
        return "docs/REPORT.md missing"
    md = path.read_text(encoding="utf-8")
    if EM_DASH in md:
        return "docs/REPORT.md contains an em dash"
    heads = " | ".join(headings(md))
    missing = [s for s in REPORT_SECTIONS if s not in heads]
    if missing:
        return f"docs/REPORT.md lacks sections {missing}"
    prose = re.sub(r"```.*?```", " ", md, flags=re.S)
    words = len(re.findall(r"\b[\w'-]+\b", prose))
    if not REPORT_WORDS[0] <= words <= REPORT_WORDS[1]:
        return f"docs/REPORT.md has {words} words (needs {REPORT_WORDS[0]} to {REPORT_WORDS[1]})"
    figs = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", md)
    if not figs:
        return "docs/REPORT.md has no figures"
    for f in figs:
        if not (path.parent / f).exists() and not (clone / f).exists():
            return f"docs/REPORT.md figure {f} missing"
    return ""


URL_RE = re.compile(r"https?://[^\s)>\]\"'`]+")


def cited_urls(clone: Path) -> list[str]:
    """External URLs cited in README.md and docs/REPORT.md (not this repository's own)."""
    urls: list[str] = []
    for rel in ("README.md", "docs/REPORT.md"):
        p = clone / rel
        if p.exists():
            urls += URL_RE.findall(p.read_text(encoding="utf-8"))
    own = "github.com/raj200501/graderproof"
    return sorted({u.rstrip(".,;") for u in urls if own not in u})


def citecheck_problems(clone: Path, urls: Sequence[str]) -> str:
    """Every cited URL has a verified entry in artifacts/citecheck.json."""
    path = clone / "artifacts" / "citecheck.json"
    if not path.exists():
        return "artifacts/citecheck.json missing"
    entries = load_json(path).get("entries", [])
    verified = set()
    for e in entries:
        if e.get("status") == "verified" and e.get("retrieved_utc") and e.get("page_title"):
            for u in (str((e.get("claimed") or {}).get("url", "")), str(e.get("final_url", ""))):
                if u:
                    verified.add(u.rstrip("/"))
    unverified = [u for u in urls if u.rstrip("/") not in verified]
    return f"unverified references {unverified[:3]}" if unverified else ""


def g13_documentation(ctx: Ctx) -> Result:
    """README follows section 11, REPORT complete, every reference verified."""
    c = ctx.clone
    for check in (readme_problems, report_problems):
        why = check(c)
        if why:
            return Result(False, why)
    step = ctx.run("citecheck", ["make", "-s", "citecheck"], timeout=600)
    if step.rc != 0:
        return Result(False, f"make citecheck failed: {tail(step.out)}")
    urls = cited_urls(c)
    if not urls:
        return Result(False, "no references cited")
    why = citecheck_problems(c, urls)
    if why:
        return Result(False, why)
    return Result(True, f"README section 11 ok; REPORT complete; {len(urls)} references verified")


def g14_hygiene(ctx: Ctx) -> Result:
    """secrets-scan clean, budget cash 0 and caps kept, private/ untracked, files, clean tree."""
    c = ctx.clone
    problems = []
    if not ctx.origin_facts.get("tree_clean"):
        problems.append(
            f"working tree not clean ({ctx.origin_facts.get('tree_dirty_count')} paths)"
        )
    if ctx.origin_facts.get("private_tracked"):
        problems.append(f"private/ tracked: {ctx.origin_facts['private_tracked'][:2]}")
    missing = [f for f in REQUIRED_FILES if not (c / f).is_file()]
    if missing:
        problems.append(f"missing {missing}")
    scan = ctx.run("secrets-scan", ["make", "-s", "secrets-scan"], timeout=900)
    if scan.rc != 0:
        problems.append(f"secrets-scan: {tail(scan.out)}")
    budget = ctx.run("budget", ["make", "-s", "budget"], timeout=300)
    if budget.rc != 0 or not re.search(r"^cash_usd = 0$", budget.out, re.M):
        problems.append(f"budget: {tail(budget.out)}")
    try:
        with (c / "budget.toml").open("rb") as fh:
            if tomllib.load(fh).get("cash_usd") != 0:
                problems.append("budget.toml cash_usd != 0")
    except (OSError, tomllib.TOMLDecodeError):
        problems.append("budget.toml unreadable")
    if problems:
        return Result(False, "; ".join(problems))
    return Result(
        True, f"{tail(scan.out)}; cash_usd = 0, caps kept; private/ untracked; tree clean"
    )


GATES: tuple[tuple[int, Callable[[Ctx], Result]], ...] = (
    (1, g1_build_and_tests),
    (2, g2_static_quality),
    (4, g4_offline_demo),
    (3, g3_ci_parity),
    (5, g5_tool_validity),
    (6, g6_validation_integrity),
    (7, g7_confirmatory_audit),
    (8, g8_repair),
    (9, g9_impact_and_cards),
    (10, g10_claim_integrity),
    (11, g11_prereg_integrity),
    (12, g12_independent_review),
    (13, g13_documentation),
    (14, g14_hygiene),
)


def run_all(ctx: Ctx) -> dict[int, Result]:
    """Phase A in the origin, then every gate in a fresh clone."""
    results: dict[int, Result] = {}
    check_origin(ctx)
    try:
        make_clone(ctx)
    except RuntimeError as exc:
        return {n: Result(False, str(exc)) for n, _ in GATES}
    for n, gate in GATES:
        try:
            results[n] = gate(ctx)
        except Exception as exc:  # a crashing check is a failing gate, never a pass
            results[n] = Result(
                False, f"check error {type(exc).__name__}: {one_line(str(exc), 100)}"
            )
    return results


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="graderproof ship-check (G1 to G14)")
    ap.add_argument("--fast", action="store_true", help="skip slow steps; result does not count")
    ap.add_argument("--keep", action="store_true", help="keep the temporary clone")
    args = ap.parse_args(argv)
    rc, head = git(ORIGIN, "rev-parse", "HEAD")
    if rc != 0:
        print("ship-check: not a git checkout", file=sys.stderr)
        return 2
    work = Path(tempfile.mkdtemp(prefix="graderproof-ship-"))
    ctx = Ctx(origin=ORIGIN, work=work, fast=args.fast, head=head)
    print(f"HEAD {head} fresh-clone", flush=True)
    results = run_all(ctx)
    passed = 0
    for n in range(1, 15):
        r = results.get(n, Result(False, "not run"))
        passed += r.ok
        print(f"G{n} {'PASS' if r.ok else 'FAIL'} {one_line(r.evidence)}", flush=True)
    if not args.keep and ctx.clone != Path() and ctx.clone.exists():
        shutil.rmtree(ctx.clone, ignore_errors=True)
    print(f"ship-check: logs in {ctx.logs}", file=sys.stderr)
    if args.fast:
        print(f"SHIP-CHECK-FAST (does not count): {passed}/14")
        return 0 if passed == 14 else 1
    print("SHIP-CHECK: PASS 14/14" if passed == 14 else f"SHIP-CHECK: FAIL {passed}/14")
    return 0 if passed == 14 else 1


if __name__ == "__main__":
    raise SystemExit(main())
