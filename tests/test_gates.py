"""Gate tests for tools/ship_check.py G5 to G11 on small temporary git repositories.

Each gate gets a minimal layout that passes. Each test then breaks it the way a
reviewer scenario did (artifacts/review/latest.json B1 to B5, N10, N12) or the way an
obvious variant would (missing files, empty sets, edited preregistrations, stale
hashes), and checks that the gate fails for that reason. The reviewer's scratch
scripts are ported as ``test_*_reviewer_*``: g5_falsepass.py scenarios A, B, and C
(``test_g5_reviewer_a/b/c_*``), g11_e0order.py (``test_g11_reviewer_b3_*``),
g8g9_vacuous.py (``test_g8_reviewer_b4_*`` and ``test_g9_reviewer_b5_*``), and
g7_mismatch.py (``test_g7_reviewer_n10_*``).

Expected statistics are computed in this file from the definitions in the ship_check
module docstring, independently of ship_check's own code; only the bootstrap
procedure is shared (tests/test_stats.py ties it to graderproof.stats). Offline.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
import ship_check as sc

import prereg

TOOLS = Path(__file__).resolve().parent.parent / "tools"
ENV = ("-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false")
PROV = {"git_sha": "0" * 40, "command": "graderproof test", "created_utc": "2026-11-04T00:00:00Z"}
SEED = 11
REPS = 1000
PREREG_E0 = "prereg/0001-e0-tool-validity.md"
PREREG_E1 = "prereg/0002-e1-e2-audit.md"

Files = dict[str, str | None]
Phases = list[tuple[str, Files]]


def sha(text: str) -> str:
    """Hex SHA-256 of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dump(obj: Any) -> str:
    """A JSON document as written by graderproof."""
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def jsonl(rows: Sequence[Mapping[str, Any]]) -> str:
    """JSON lines."""
    return "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)


class Repo:
    """A throwaway git repository."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True)
        self.git("init", "-q")

    def git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.root), *ENV, *args], capture_output=True, text=True, check=True
        )
        return proc.stdout.strip()

    def write(self, files: Mapping[str, str | None]) -> None:
        """Write files (None deletes one)."""
        for rel, text in files.items():
            path = self.root / rel
            if text is None:
                path.unlink(missing_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def commit(self, message: str, files: Mapping[str, str | None] | None = None) -> str:
        """Write ``files``, commit everything, and return the new HEAD."""
        if files:
            self.write(files)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def ctx(self, work: Path) -> sc.Ctx:
        """A ship-check context whose clone is this repository."""
        ctx = sc.Ctx(origin=self.root, work=work, fast=True, head=self.git("rev-parse", "HEAD"))
        ctx.clone = self.root
        return ctx


def build(tmp: Path, phases: Phases) -> sc.Ctx:
    """Commit each phase in order and return a context on the result."""
    repo = Repo(tmp / "repo")
    for name, files in phases:
        repo.commit(name, files)
    return repo.ctx(tmp / "work")


def files_of(phases: Phases, name: str) -> Files:
    """The (mutable) files of one phase."""
    return next(f for n, f in phases if n == name)


def vrow(
    task_hash: str,
    n: int,
    kind: str,
    passed: bool | None,
    counted: Any = True,
    verdicts: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """A variants.jsonl row with two agreeing validations and a witness."""
    vid = sha(f"{task_hash}:{n}")[:16]
    names = ("witness:requirements/v1", "model:reviewer/review/v1")
    marks = list(verdicts) if verdicts is not None else [kind, kind]
    return {
        "variant_id": vid,
        "task_hash": task_hash,
        "kind": kind,
        "operator": "op",
        "validations": [{"validator": names[i % 2], "verdict": v} for i, v in enumerate(marks)],
        "witness_sha256": sha(vid),
        "counted_in_headline": counted,
        "grader_passed": passed,
        "grader_runs": 3,
    }


# =========================================================================== G5 (E0)


@dataclass
class E0Case:
    """An E0 layout: labels, per-task (determinism, false accept, false reject), rulings."""

    labels: dict[str, dict[str, Any]]
    flags: dict[str, tuple[str, bool, bool]]
    rulings: dict[str, Any]
    misses: str
    benchmark: str = "toybench"


def planted(direction: str, sl: str = "in_list") -> dict[str, Any]:
    return {"planted": True, "slice": sl, "weakness_type": "loose-check", "direction": direction}


def clean() -> dict[str, Any]:
    return {"planted": False, "slice": "clean", "weakness_type": None, "direction": None}


def e0_case() -> E0Case:
    """64 counted tasks (32 planted, 32 clean) and 2 extra-slice tasks.

    Recall 30/32: pa26 is flaky on the reference and pa27 raises no flag. Precision
    30/31: c00 is flagged and adjudicated real, c01 is flagged and is a false positive,
    c02's reference is rejected (never a flag under D23).
    """
    labels: dict[str, dict[str, Any]] = {}
    flags: dict[str, tuple[str, bool, bool]] = {}
    for i in range(28):
        labels[f"pa{i:02d}"] = planted("accept")
        flags[f"pa{i:02d}"] = ("stable_pass", True, False)
    flags["pa26"] = ("flaky", False, False)
    flags["pa27"] = ("stable_pass", False, False)
    for i in range(4):
        labels[f"pr{i:02d}"] = planted("reject")
        flags[f"pr{i:02d}"] = ("stable_pass", False, True)
    for i in range(32):
        labels[f"c{i:02d}"] = clean()
        flags[f"c{i:02d}"] = ("stable_pass", False, False)
    flags["c00"] = ("stable_pass", True, False)
    flags["c01"] = ("stable_pass", False, True)
    flags["c02"] = ("stable_fail", False, False)
    labels["x00"] = planted("accept", "extra")
    flags["x00"] = ("stable_pass", True, False)
    labels["x01"] = planted("reject", "extra")
    flags["x01"] = ("stable_pass", False, False)
    rulings = {"c00": {"real": True, "note": "witness validates"}, "c01": {"real": False}}
    rulings["pa00"] = {"real": True}  # adjudicated blind to labels; a detection, so unused
    misses = "# E0 misses\n\n- pa26: flaky reference.\n- pa27: no variant broke it.\n"
    return E0Case(labels, flags, rulings, misses)


def e0_task_rows(case: E0Case) -> list[dict[str, Any]]:
    """artifacts/e0/tasks.jsonl as graderproof audit --public-task-ids writes it."""
    rows = []
    for tid in reversed(list(case.labels)):  # file order must not matter
        det, fa, fr = case.flags[tid]
        key = f"{case.benchmark}:{tid}"
        rows.append(
            {
                "task": key,
                "task_hash": sha(key),
                "determinism": det,
                "false_accept": fa,
                "false_reject": fr,
                "reference_rejected": det == "stable_fail",
                "flaky": det == "flaky",
            }
        )
    return rows


def e0_variant_rows(case: E0Case) -> list[dict[str, Any]]:
    """Variants consistent with the flags; unscorable tasks get would-be flags too."""
    rows = []
    for tid in case.labels:
        det, fa, fr = case.flags[tid]
        h = sha(f"{case.benchmark}:{tid}")
        rows.append(vrow(h, 0, "violating", False))
        rows.append(vrow(h, 1, "preserving", not (fr or det == "stable_fail")))
        if fa or det == "flaky":
            rows.append(vrow(h, 2, "violating", True))
        if tid == "c03":
            rows.append(vrow(h, 3, "violating", True, counted=False))
    return rows


@dataclass(frozen=True)
class Want:
    """One task as G5 should see it."""

    id: str
    planted: bool
    slice: str
    flagged: bool
    detected: bool
    real: bool


def e0_want(case: E0Case) -> list[Want]:
    """D23 detection, flags, and adjudication, in ascending id order."""
    out = []
    for tid in sorted(case.labels):
        lab = case.labels[tid]
        det, fa, fr = case.flags[tid]
        fa, fr = fa and det == "stable_pass", fr and det == "stable_pass"
        is_planted = lab["planted"] is True
        detected = is_planted and (
            (lab["direction"] == "accept" and fa) or (lab["direction"] == "reject" and fr)
        )
        flagged = fa or fr
        rule = case.rulings.get(tid)
        real = flagged and not detected and isinstance(rule, dict) and rule.get("real") is True
        out.append(Want(tid, is_planted, str(lab["slice"]), flagged, detected, real))
    return out


def e0_results(
    case: E0Case,
    rows: Sequence[Want] | None = None,
    seed: int = SEED,
    reps: int = REPS,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """artifacts/e0/results.json computed from ``rows`` (default: the right ones)."""
    want = list(e0_want(case) if rows is None else rows)
    counted = [w for w in want if w.slice != "extra"]

    def recall(idx: Sequence[int]) -> float | None:
        p = sum(1 for i in idx if counted[i].planted)
        return sum(1 for i in idx if counted[i].detected) / p if p else None

    def precision(idx: Sequence[int]) -> float | None:
        tp = sum(1 for i in idx if counted[i].detected)
        fp = sum(1 for i in idx if counted[i].flagged and not counted[i].detected)
        fp -= sum(1 for i in idx if counted[i].real)
        return tp / (tp + fp) if tp + fp else None

    every = list(range(len(counted)))
    doc: dict[str, Any] = {
        "schema": "graderproof.e0/1",
        "prereg": PREREG_E0,
        "bootstrap": {"seed": seed, "B": reps, "alpha": alpha},
        "tasks": [
            {
                "task": w.id,
                "planted": w.planted,
                "slice": w.slice,
                "flagged": w.flagged,
                "detected": w.detected,
                "adjudicated_real": w.real,
            }
            for w in want
        ],
        "provenance": PROV,
    }
    for key, stat, s in (("recall", recall, seed), ("precision", precision, seed + 1)):
        ci = sc.bootstrap_ci(len(counted), stat, s, reps, alpha)
        doc[key] = {"point": stat(every), "ci": list(ci) if ci else [], "n": len(counted)}
    return doc


def e0_phases(case: E0Case, results: dict[str, Any] | None = None) -> Phases:
    """plant (tasks and label hash), run (audit outputs and model calls), score."""
    labels_text = dump({"tasks": case.labels})
    plant: Files = {f"toybench/tasks/{t}/task.toml": f'id = "{t}"\n' for t in case.labels}
    plant["toybench/labels.sha256"] = f"{sha(labels_text)}  labels.json\n"
    summary = {
        "confirmatory": True,
        "prereg": PREREG_E0,
        "model_store": "artifacts/model_calls/e0",
        "provenance": PROV,
    }
    run: Files = {
        "artifacts/model_calls/e0/requests/r1.json": dump({"items": ["opaque"]}),
        "artifacts/e0/tasks.jsonl": jsonl(e0_task_rows(case)),
        "artifacts/e0/variants.jsonl": jsonl(e0_variant_rows(case)),
        "artifacts/e0/summary.json": dump(summary),
    }
    score: Files = {
        "toybench/labels.json": labels_text,
        "artifacts/e0/adjudication.json": dump({"tasks": case.rulings}),
        "artifacts/e0/results.json": dump(e0_results(case) if results is None else results),
        "docs/E0_MISSES.md": case.misses,
    }
    return [("plant", plant), ("run", run), ("score", score)]


def g5(tmp: Path, phases: Phases) -> sc.Result:
    return sc.g5_tool_validity(build(tmp, phases))


def test_g5_passes_on_a_correct_layout(tmp_path: Path) -> None:
    r = g5(tmp_path, e0_phases(e0_case()))
    assert r.ok, r.evidence
    assert r.evidence.startswith("recall 0.938 [")
    assert "precision 0.968 [" in r.evidence
    assert "n=64, 2 misses, 1 adjudicated real (min 0.9)" in r.evidence


def test_g5_reviewer_a_labels_and_hash_rewritten_after_the_run(tmp_path: Path) -> None:
    """g5_falsepass.py scenario A: the misses are relabeled clean and the hash rewritten."""
    case = e0_case()
    honest = e0_phases(case)
    case.labels["pa26"], case.labels["pa27"] = clean(), clean()
    case.misses = "# E0 misses\n\nNone.\n"
    relabeled = e0_phases(case)
    files_of(relabeled, "score")["toybench/labels.sha256"] = files_of(relabeled, "plant")[
        "toybench/labels.sha256"
    ]
    phases = [honest[0], relabeled[1], relabeled[2]]
    r = g5(tmp_path, phases)
    assert not r.ok
    assert "toybench/labels.sha256 has 2 commits" in r.evidence


def test_g5_fails_on_a_stale_labels_hash(tmp_path: Path) -> None:
    case = e0_case()
    phases = e0_phases(case)
    case.labels["pa27"] = clean()
    files_of(phases, "score")["toybench/labels.json"] = dump({"tasks": case.labels})
    r = g5(tmp_path, phases)
    assert not r.ok
    assert "toybench/labels.json does not match toybench/labels.sha256" in r.evidence


def test_g5_fails_when_the_hash_lands_with_the_run(tmp_path: Path) -> None:
    phases = e0_phases(e0_case())
    plant, run = files_of(phases, "plant"), files_of(phases, "run")
    run["toybench/labels.sha256"] = plant.pop("toybench/labels.sha256")
    r = g5(tmp_path, phases)
    assert not r.ok
    assert "was not committed before the E0 data" in r.evidence


def test_g5_dates_the_run_by_its_first_model_call(tmp_path: Path) -> None:
    """Reviewer B2: model requests under artifacts/model_calls/e0/ start the run."""
    phases = e0_phases(e0_case())
    early: Files = {"artifacts/model_calls/e0/requests/r0.json": dump({"items": ["first"]})}
    r = g5(tmp_path, [("first model call", early), *phases])
    assert not r.ok
    assert "was not committed before the E0 data" in r.evidence


def test_g5_dates_outputs_moved_in_from_a_pilot(tmp_path: Path) -> None:
    """A pilot run banked before the hash cannot be renamed into artifacts/e0/ later."""
    phases = e0_phases(e0_case())
    run = files_of(phases, "run")
    pilot: Files = {"artifacts/pilot/tasks.jsonl": run["artifacts/e0/tasks.jsonl"]}
    run["artifacts/pilot/tasks.jsonl"] = None
    r = g5(tmp_path, [("pilot", pilot), *phases])
    assert not r.ok
    assert "was not committed before the E0 data" in r.evidence


def test_g5_fails_when_toybench_tasks_change_after_the_hash(tmp_path: Path) -> None:
    phases = e0_phases(e0_case())
    files_of(phases, "score")["toybench/tasks/pa27/grader.sh"] = "exit 0\n"
    r = g5(tmp_path, phases)
    assert not r.ok
    assert "toybench/tasks/ changed after the labels hash commit" in r.evidence


def test_g5_fails_without_toybench_tasks(tmp_path: Path) -> None:
    phases = e0_phases(e0_case())
    plant = files_of(phases, "plant")
    for rel in [k for k in plant if k.startswith("toybench/tasks/")]:
        del plant[rel]
    r = g5(tmp_path, phases)
    assert not r.ok
    assert "toybench/tasks/ was not committed with or before the labels hash" in r.evidence


@pytest.mark.parametrize(
    ("phase", "rel", "message"),
    [
        ("score", "artifacts/e0/results.json", "artifacts/e0/results.json missing (E0 not run)"),
        ("score", "toybench/labels.json", "toybench/labels.json missing"),
        ("plant", "toybench/labels.sha256", "toybench/labels.sha256 missing"),
        ("run", "artifacts/e0/tasks.jsonl", "artifacts/e0/tasks.jsonl missing or empty"),
        ("score", "artifacts/e0/adjudication.json", "artifacts/e0/adjudication.json missing"),
        ("score", "docs/E0_MISSES.md", "docs/E0_MISSES.md missing"),
    ],
)
def test_g5_fails_on_a_missing_file(tmp_path: Path, phase: str, rel: str, message: str) -> None:
    phases = e0_phases(e0_case())
    del files_of(phases, phase)[rel]
    r = g5(tmp_path, phases)
    assert not r.ok
    assert message in r.evidence


def test_g5_reviewer_b_results_drop_misses_and_repeat_a_detection(tmp_path: Path) -> None:
    """g5_falsepass.py scenario B: rows omit the misses and repeat a detected task."""
    case = e0_case()
    want = [w for w in e0_want(case) if w.id not in ("pa26", "pa27")]
    want += [next(w for w in want if w.id == "pa00")] * 2
    results = e0_results(case, want)
    assert results["recall"]["point"] == 1.0
    r = g5(tmp_path, e0_phases(case, results))
    assert not r.ok
    assert "lists task pa00 twice" in r.evidence


def test_g5_fails_when_results_omit_a_labeled_task(tmp_path: Path) -> None:
    case = e0_case()
    want = [w for w in e0_want(case) if w.id != "pa27"]
    r = g5(tmp_path, e0_phases(case, e0_results(case, want)))
    assert not r.ok
    assert "lacks labeled tasks ['pa27']" in r.evidence


def test_g5_fails_on_an_unlabeled_results_row(tmp_path: Path) -> None:
    case = e0_case()
    results = e0_results(case)
    results["tasks"].append({"task": "ghost", "planted": False, "slice": "clean"})
    r = g5(tmp_path, e0_phases(case, results))
    assert not r.ok
    assert "row for unlabeled 'ghost'" in r.evidence


def test_g5_fails_when_tasks_jsonl_lacks_a_labeled_task(tmp_path: Path) -> None:
    case = e0_case()
    phases = e0_phases(case)
    rows = [r for r in e0_task_rows(case) if r["task"] != "toybench:pa27"]
    files_of(phases, "run")["artifacts/e0/tasks.jsonl"] = jsonl(rows)
    variants = [v for v in e0_variant_rows(case) if v["task_hash"] != sha("toybench:pa27")]
    files_of(phases, "run")["artifacts/e0/variants.jsonl"] = jsonl(variants)
    r = g5(tmp_path, phases)
    assert not r.ok
    assert "unaudited ['pa27']" in r.evidence


def test_g5_fails_when_tasks_jsonl_repeats_a_task(tmp_path: Path) -> None:
    case = e0_case()
    phases = e0_phases(case)
    rows = e0_task_rows(case)
    files_of(phases, "run")["artifacts/e0/tasks.jsonl"] = jsonl([*rows, rows[0]])
    r = g5(tmp_path, phases)
    assert not r.ok
    assert "twice" in r.evidence


def test_g5_fails_when_task_hash_is_not_the_hash_of_the_task(tmp_path: Path) -> None:
    case = e0_case()
    phases = e0_phases(case)
    rows = e0_task_rows(case)
    rows[0]["task"] = rows[0]["task"].replace("toybench:", "other:")
    files_of(phases, "run")["artifacts/e0/tasks.jsonl"] = jsonl(rows)
    r = g5(tmp_path, phases)
    assert not r.ok
    assert "is not its SHA-256" in r.evidence


def test_g5_reviewer_c_clean_flags_marked_real_without_adjudication(tmp_path: Path) -> None:
    """g5_falsepass.py scenario C: every clean task flagged, all marked real, no file."""
    case = e0_case()
    for i in range(32):
        case.flags[f"c{i:02d}"] = ("stable_pass", True, False)
    want = [
        Want(w.id, w.planted, w.slice, w.flagged, w.detected, w.flagged and not w.detected)
        for w in e0_want(case)
    ]
    results = e0_results(case, want)
    assert results["precision"]["point"] == 1.0
    phases = e0_phases(case, results)
    del files_of(phases, "score")["artifacts/e0/adjudication.json"]
    r = g5(tmp_path, phases)
    assert not r.ok
    assert "artifacts/e0/adjudication.json missing" in r.evidence


def test_g5_fails_on_flags_without_a_ruling(tmp_path: Path) -> None:
    case = e0_case()
    case.rulings = {}
    r = g5(tmp_path, e0_phases(case))
    assert not r.ok
    assert "flags without a ruling in artifacts/e0/adjudication.json: ['c00', 'c01']" in r.evidence


def test_g5_reads_real_only_as_a_json_boolean(tmp_path: Path) -> None:
    """Review N7: the string "false" must never count as adjudicated real."""
    case = e0_case()
    case.rulings["c01"] = {"real": "false"}
    r = g5(tmp_path, e0_phases(case))
    assert not r.ok
    assert "real for c01 is not true or false" in r.evidence


def test_g5_rejects_rulings_on_unlabeled_tasks(tmp_path: Path) -> None:
    case = e0_case()
    case.rulings["ghost"] = {"real": False}
    r = g5(tmp_path, e0_phases(case))
    assert not r.ok
    assert "rules on unlabeled task ghost" in r.evidence


def test_g5_recomputes_flags_from_variants(tmp_path: Path) -> None:
    """A hand-set false_accept with no surviving variant behind it fails."""
    case = e0_case()
    phases = e0_phases(case)
    rows = e0_task_rows(case)
    for row in rows:
        if row["task"] == "toybench:pa27":
            row["false_accept"] = True
    files_of(phases, "run")["artifacts/e0/tasks.jsonl"] = jsonl(rows)
    r = g5(tmp_path, phases)
    assert not r.ok
    assert "false_accept is True; recomputed" in r.evidence


def test_g5_rows_must_match_the_recomputed_detection(tmp_path: Path) -> None:
    """D23: a rejected reference is not a detection, even for a reject weakness."""
    case = e0_case()
    case.flags["pr03"] = ("stable_fail", False, False)
    want = [
        Want(
            w.id,
            w.planted,
            w.slice,
            w.id == "pr03" or w.flagged,
            w.id == "pr03" or w.detected,
            w.real,
        )
        for w in e0_want(case)
    ]
    r = g5(tmp_path, e0_phases(case, e0_results(case, want)))
    assert not r.ok
    assert "row pr03: detected is True, recomputed False" in r.evidence


def test_g5_recomputes_recall_without_per_row_fields(tmp_path: Path) -> None:
    """Old e0.py rule (rejected reference credited as a reject detection) is caught."""
    case = e0_case()
    case.flags["pr03"] = ("stable_fail", False, False)
    case.misses += "- pr03: reference rejected.\n"
    old_rule = [
        Want(
            w.id,
            w.planted,
            w.slice,
            w.id == "pr03" or w.flagged,
            w.id == "pr03" or w.detected,
            w.real,
        )
        for w in e0_want(case)
    ]
    results = e0_results(case, old_rule)
    results["tasks"] = [
        {"task": w.id, "planted": w.planted, "slice": w.slice} for w in e0_want(case)
    ]
    r = g5(tmp_path, e0_phases(case, results))
    assert not r.ok
    assert "E0 recall point 0.9375 differs from the recomputed 0.906" in r.evidence


@pytest.mark.parametrize(
    ("label", "message"),
    [
        ({"planted": True, "slice": "inlist", "direction": "accept"}, "slice 'inlist' not in"),
        ({"planted": True, "slice": "clean", "direction": "accept"}, "planted=True contradicts"),
        ({"planted": False, "slice": "in_list", "direction": None}, "planted=False contradicts"),
        ({"planted": True, "slice": "in_list", "direction": None}, "planted without direction"),
        ({"planted": "yes", "slice": "in_list", "direction": "accept"}, "planted is not true"),
    ],
)
def test_g5_validates_labels(tmp_path: Path, label: dict[str, Any], message: str) -> None:
    case = e0_case()
    case.labels["pa00"] = label
    r = g5(tmp_path, e0_phases(case, e0_results(e0_case())))
    assert not r.ok
    assert f"label pa00: {message}" in r.evidence


def test_g5_needs_sixty_counted_tasks(tmp_path: Path) -> None:
    case = e0_case()
    for i in range(10, 32):
        del case.labels[f"c{i:02d}"]
    r = g5(tmp_path, e0_phases(case))
    assert not r.ok
    assert "E0 has 42 counted tasks (< 60)" in r.evidence


def test_g5_needs_half_planted_and_half_clean(tmp_path: Path) -> None:
    """Brief section 5: half planted (including false-reject brittleness), half clean."""
    case = e0_case()
    for i in range(28, 34):  # 38 planted, 26 clean
        case.labels[f"c{i - 28:02d}"] = planted("accept")
        case.flags[f"c{i - 28:02d}"] = ("stable_pass", True, False)
    case.rulings = {}
    r = g5(tmp_path / "skewed", e0_phases(case))
    assert not r.ok
    assert "E0 needs at least 30 planted and 30 clean counted tasks (has 38 and 26)" in r.evidence
    case = e0_case()
    for i in range(4):
        case.labels[f"pr{i:02d}"] = planted("accept")
        case.flags[f"pr{i:02d}"] = ("stable_pass", True, False)
    r = g5(tmp_path / "noreject", e0_phases(case))
    assert not r.ok
    assert "E0 has no planted false-reject (direction reject) weakness" in r.evidence


def test_g5_fails_below_the_recall_threshold(tmp_path: Path) -> None:
    case = e0_case()
    for i in range(20, 26):
        case.flags[f"pa{i:02d}"] = ("stable_pass", False, False)
    case.misses += "".join(f"- pa{i:02d}: missed.\n" for i in range(20, 26))
    r = g5(tmp_path, e0_phases(case))
    assert not r.ok
    assert r.evidence.startswith("recall 0.750 [")
    assert "(min 0.9)" in r.evidence


def test_g5_fails_when_nothing_is_flagged(tmp_path: Path) -> None:
    case = e0_case()
    case.flags = {t: ("stable_pass", False, False) for t in case.labels}
    case.rulings = {}
    r = g5(tmp_path, e0_phases(case))
    assert not r.ok
    assert "E0 recall point 0.0 differs" in r.evidence or "undefined" in r.evidence


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"alpha": 0.1}, "bootstrap alpha is not 0.05"),
        ({"reps": 200}, "bootstrap B=200 (< 1000)"),
    ],
)
def test_g5_requires_a_95_percent_bootstrap(
    tmp_path: Path, kwargs: dict[str, Any], message: str
) -> None:
    case = e0_case()
    r = g5(tmp_path, e0_phases(case, e0_results(case, **kwargs)))
    assert not r.ok
    assert message in r.evidence


@pytest.mark.parametrize(
    ("key", "field", "value", "message"),
    [
        ("recall", "ci", [0.8, 1.0], "E0 recall interval [0.8, 1.0] differs"),
        ("recall", "ci", [], "E0 recall interval [] differs"),
        ("precision", "n", 66, "E0 precision n 66 differs from the 64 tasks"),
        ("precision", "point", True, "E0 precision point True differs"),
    ],
)
def test_g5_compares_stated_estimates(
    tmp_path: Path, key: str, field: str, value: Any, message: str
) -> None:
    case = e0_case()
    results = e0_results(case)
    results[key][field] = value
    r = g5(tmp_path, e0_phases(case, results))
    assert not r.ok
    assert message in r.evidence


def test_g5_needs_every_miss_explained(tmp_path: Path) -> None:
    case = e0_case()
    case.misses = "# E0 misses\n\n- pa26: flaky reference.\n"
    r = g5(tmp_path, e0_phases(case))
    assert not r.ok
    assert "misses not in docs/E0_MISSES.md: ['pa27']" in r.evidence


def test_g5_matches_miss_ids_as_whole_tokens(tmp_path: Path) -> None:
    """Review B1: miss 't1' is not explained by 't10'."""
    case = e0_case()
    case.misses = "# E0 misses\n\n- pa26: flaky reference.\n- pa270 and pa27-b are other tasks.\n"
    r = g5(tmp_path, e0_phases(case))
    assert not r.ok
    assert "['pa27']" in r.evidence
    assert sc.has_token("see `pa27`.", "pa27")
    assert sc.has_token("toybench:pa27", "pa27")
    assert not sc.has_token("pa270", "pa27")
    assert not sc.has_token("xpa27", "pa27")


# =========================================================================== G6


def g6(tmp: Path, rows: Sequence[Mapping[str, Any]]) -> sc.Result:
    path = tmp / "artifacts" / "audit" / "b1" / "variants.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(jsonl(rows), encoding="utf-8")
    ctx = sc.Ctx(origin=tmp, work=tmp / "work", fast=True)
    ctx.clone = tmp
    return sc.g6_validation_integrity(ctx)


def g6_rows() -> list[dict[str, Any]]:
    """Three headline variants, one disagreement, one with two unsure verdicts."""
    h = sha("b1:t0")
    return [
        vrow(h, 0, "violating", True),
        vrow(h, 1, "violating", False),
        vrow(h, 2, "preserving", True),
        vrow(h, 3, "violating", True, counted=False, verdicts=["violating", "preserving"]),
        vrow(h, 4, "preserving", True, counted=False, verdicts=[None, None]),
    ]


def two(a: Any, b: Any, names: tuple[str, str] = ("a", "b")) -> dict[str, Any]:
    """A validations list with two entries."""
    return {
        "validations": [
            {"validator": names[0], "verdict": a},
            {"validator": names[1], "verdict": b},
        ]
    }


def test_g6_passes_and_reports_agreement_over_label_verdicts(tmp_path: Path) -> None:
    """Review N12: two unsure verdicts are not an agreement."""
    r = g6(tmp_path, g6_rows())
    assert r.ok, r.evidence
    assert "3 headline variants; agreement 0.750 (3/4 with label verdicts); 1 unsure" in r.evidence
    assert "excluded 2; lacking two agreeing validations 0; lacking witness 0" in r.evidence


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"validations": [{"validator": "a", "verdict": "violating"}]}, "validations 1;"),
        (two("violating", "violating", ("a", "a")), "validations 1;"),
        (two("violating", "preserving"), "validations 1;"),
        (two(None, None), "validations 1;"),
        (two("preserving", "preserving"), "validations 1;"),
        (two(["violating"], "violating"), "validations 1;"),
        ({"validations": [{"verdict": "violating"}, {"verdict": "violating"}]}, "validations 1;"),
        ({"kind": "equivalent"}, "validations 1;"),
        ({"witness_sha256": None}, "lacking witness 1"),
        ({"witness_sha256": "None"}, "lacking witness 1"),
    ],
)
def test_g6_fails_on_a_bad_headline_variant(
    tmp_path: Path, change: dict[str, Any], message: str
) -> None:
    rows = g6_rows()
    rows[0].update(change)
    r = g6(tmp_path, rows)
    assert not r.ok
    assert message in r.evidence


def test_g6_fails_without_headline_variants(tmp_path: Path) -> None:
    rows = [{**r, "counted_in_headline": "true"} for r in g6_rows()]
    r = g6(tmp_path / "strings", rows)
    assert not r.ok
    assert "no headline variants banked" in r.evidence
    assert not g6(tmp_path / "empty", []).ok


# =========================================================================== G7

# (id, determinism, [(kind, grader_passed, counted_in_headline)])
AuditTask = tuple[str, str, list[tuple[str, bool | None, Any]]]
AUDIT_TASKS: list[AuditTask] = [
    ("t0", "stable_pass", [("violating", True, True), ("preserving", True, True)]),
    ("t1", "stable_pass", [("violating", False, True), ("preserving", False, True)]),
    ("t2", "stable_pass", [("violating", False, True), ("violating", True, False)]),
    ("t3", "stable_fail", [("preserving", False, True)]),
    ("t4", "flaky", [("violating", True, True)]),
]
BENCHES = (("b1", "tool-use"), ("b2", "coding"), ("b3", "function-calling"))


def indicators(det: str, variants: Sequence[tuple[str, bool | None, Any]]) -> tuple[bool, bool]:
    """(false accept, false reject) under the contract: scorable tasks, counted variants."""
    counted = [(k, p) for k, p, c in variants if c is True and isinstance(p, bool)]
    if det != "stable_pass":
        return False, False
    fa = any(k == "violating" and p is True for k, p in counted)
    fr = any(k == "preserving" and p is False for k, p in counted)
    return fa, fr


def audit_rows(
    bench: str, tasks: Sequence[AuditTask] = AUDIT_TASKS
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """tasks.jsonl and variants.jsonl rows as write_outputs banks them."""
    trows: list[dict[str, Any]] = []
    vrows: list[dict[str, Any]] = []
    for tid, det, variants in tasks:
        h = sha(f"{bench}:{tid}")
        fa, fr = indicators(det, variants)
        trows.append(
            {
                "task_hash": h,
                "determinism": det,
                "flaky": det == "flaky",
                "reference_rejected": det == "stable_fail",
                "false_accept": fa,
                "false_reject": fr,
            }
        )
        vrows += [vrow(h, n, k, p, counted=c) for n, (k, p, c) in enumerate(variants)]
    return trows, vrows


def rate(values: Sequence[bool], seed: int) -> dict[str, Any]:
    """{point, ci, n} for a share of tasks."""

    def share(idx: Sequence[int]) -> float | None:
        return sum(1 for i in idx if values[i]) / len(idx) if idx else None

    ci = sc.bootstrap_ci(len(values), share, seed, REPS)
    return {"point": share(range(len(values))), "ci": list(ci) if ci else [], "n": len(values)}


def audit_summary(bench: str, category: str, tasks: Sequence[AuditTask]) -> dict[str, Any]:
    """summary.json with E1 and E2 over the scorable tasks."""
    flags = [indicators(det, v) for _, det, v in tasks if det == "stable_pass"]
    return {
        "schema": "graderproof.audit/1",
        "benchmark": bench,
        "category": category,
        "confirmatory": True,
        "prereg": PREREG_E1,
        "model_store": f"artifacts/model_calls/{bench}",
        "n_tasks_population": len(tasks),
        "n_sampled": len(tasks),
        "bootstrap": {"seed": SEED, "B": REPS, "alpha": 0.05},
        "e1": {"false_accept_task_rate": rate([fa for fa, _ in flags], SEED)},
        "e2": {"false_reject_task_rate": rate([fr for _, fr in flags], SEED + 1)},
        "provenance": PROV,
    }


def audit_files(
    benches: Sequence[tuple[str, str]] = BENCHES,
    tasks: Mapping[str, Sequence[AuditTask]] | None = None,
) -> Files:
    """Audits of ``benches`` with their model calls and preregistration file."""
    files: Files = {PREREG_E1: "# E1 and E2\n", "DECISIONS.md": "# Decisions\n"}
    for bench, category in benches:
        bench_tasks = (tasks or {}).get(bench, AUDIT_TASKS)
        trows, vrows = audit_rows(bench, bench_tasks)
        base = f"artifacts/audit/{bench}"
        files[f"artifacts/model_calls/{bench}/requests/r1.json"] = dump({"items": ["opaque"]})
        files[f"{base}/tasks.jsonl"] = jsonl(trows)
        files[f"{base}/variants.jsonl"] = jsonl(vrows)
        files[f"{base}/summary.json"] = dump(audit_summary(bench, category, bench_tasks))
    return files


def summary_of(files: Files, bench: str) -> dict[str, Any]:
    text = files[f"artifacts/audit/{bench}/summary.json"]
    assert text is not None
    doc: dict[str, Any] = json.loads(text)
    return doc


def g7(tmp: Path, files: Files) -> sc.Result:
    return sc.g7_confirmatory_audit(build(tmp, [("audit", files)]))


def test_g7_passes_on_three_benchmarks(tmp_path: Path) -> None:
    r = g7(tmp_path, audit_files())
    assert r.ok, r.evidence
    assert "on 3 benchmarks: ['b1', 'b2', 'b3']" in r.evidence


def test_g7_reviewer_n10_rejected_reference_is_not_scored(tmp_path: Path) -> None:
    """g7_mismatch.py: score.py rates scorable tasks only, and G7 agrees (D26)."""
    files = audit_files()
    s = summary_of(files, "b1")
    assert s["e2"]["false_reject_task_rate"]["n"] == 3
    assert g7(tmp_path / "ok", files).ok
    old = [t for t in AUDIT_TASKS if t[1] != "flaky"]  # the old rule kept every non-flaky task
    flags = [indicators("stable_pass", v) for _, _, v in old]
    s["e2"]["false_reject_task_rate"] = rate([fr for _, fr in flags], SEED + 1)
    files["artifacts/audit/b1/summary.json"] = dump(s)
    r = g7(tmp_path / "old", files)
    assert not r.ok
    assert "b1: e2 false_reject_task_rate point 0.5 differs from the recomputed 0.333" in r.evidence


def test_g7_counts_only_counted_variants_with_a_stable_verdict(tmp_path: Path) -> None:
    unstable: AuditTask = ("t2", "stable_pass", [("violating", None, True)])
    tasks = {"b1": [*AUDIT_TASKS[:2], unstable, *AUDIT_TASKS[3:]]}
    files = audit_files(tasks=tasks)
    assert g7(tmp_path / "ok", files).ok
    s = summary_of(files, "b1")
    s["e1"]["false_accept_task_rate"] = rate([True, False, True], SEED)  # counted it
    files["artifacts/audit/b1/summary.json"] = dump(s)
    r = g7(tmp_path / "bad", files)
    assert not r.ok
    assert "b1: e1 false_accept_task_rate point" in r.evidence


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"confirmatory": "yes"}, "b1: not marked confirmatory"),
        ({"prereg": "prereg/FROZEN.jsonl"}, "b1: cites no existing preregistration"),
        ({"prereg": "prereg/0009-missing.md"}, "b1: cites no existing preregistration"),
        ({"n_sampled": 4}, "b1: sample 4 outside"),
        ({"n_tasks_population": 50}, "b1: sample 5 outside"),
        ({"n_sampled": "5"}, "must be integers"),
        ({"provenance": {}}, "b1: provenance lacks"),
        ({"bootstrap": {"seed": SEED, "B": REPS, "alpha": 0.1}}, "alpha is not 0.05"),
        ({"e1": {}}, "b1: e1 false_accept_task_rate missing"),
    ],
)
def test_g7_fails_on_a_bad_summary(tmp_path: Path, change: dict[str, Any], message: str) -> None:
    files = audit_files()
    files["artifacts/audit/b1/summary.json"] = dump({**summary_of(files, "b1"), **change})
    r = g7(tmp_path, files)
    assert not r.ok
    assert message in r.evidence


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("ci", [0.25, 0.5], "e1 false_accept_task_rate interval [0.25, 0.5] differs"),
        ("n", 4, "e1 false_accept_task_rate n 4 differs from the 3 tasks"),
    ],
)
def test_g7_compares_stated_rates(tmp_path: Path, key: str, value: Any, message: str) -> None:
    files = audit_files()
    s = summary_of(files, "b2")
    s["e1"]["false_accept_task_rate"][key] = value
    files["artifacts/audit/b2/summary.json"] = dump(s)
    r = g7(tmp_path, files)
    assert not r.ok
    assert f"b2: {message}" in r.evidence


def test_g7_validates_the_task_table(tmp_path: Path) -> None:
    trows, vrows = audit_rows("b1")
    ghost = vrow(sha("b1:ghost"), 0, "violating", True)
    stated = [
        {**t, "false_reject": True} if t["determinism"] == "stable_fail" else t for t in trows
    ]
    cases: list[tuple[list[dict[str, Any]], list[dict[str, Any]], str]] = [
        ([{**trows[0], "determinism": None}, *trows[1:]], vrows, "has determinism None"),
        ([*trows, trows[0]], vrows, "twice"),
        (trows, [*vrows, ghost], "variant of unknown task"),
        (trows, [*vrows, {**ghost, "task_hash": ["x"]}], "variant of unknown task"),
        (trows, [{**vrows[0], "kind": "equivalent"}, *vrows[1:]], "variant kind 'equivalent'"),
        (stated, vrows, "false_reject is True; recomputed"),
        ([], vrows, "tasks.jsonl missing or empty"),
    ]
    for i, (t, v, message) in enumerate(cases):
        files = audit_files()
        files["artifacts/audit/b1/tasks.jsonl"] = jsonl(t)
        files["artifacts/audit/b1/variants.jsonl"] = jsonl(v)
        r = g7(tmp_path / str(i), files)
        assert not r.ok, message
        assert message in r.evidence, (message, r.evidence)


def test_g7_needs_three_benchmarks_and_a_tool_use_one(tmp_path: Path) -> None:
    r = g7(tmp_path / "two", audit_files(BENCHES[:2]))
    assert not r.ok
    assert "2 benchmarks pass E1/E2 checks (< 3)" in r.evidence
    no_tool = (("b1", "coding"), ("b2", "coding"), ("b3", "function-calling"))
    r = g7(tmp_path / "notool", audit_files(no_tool))
    assert not r.ok
    assert "no tool-use benchmark" in r.evidence
    r = g7(tmp_path / "none", {PREREG_E1: "x\n"})
    assert not r.ok
    assert "0 benchmarks" in r.evidence


def test_g7_substitution_must_be_decided_before_data(tmp_path: Path) -> None:
    files = audit_files()
    s = summary_of(files, "b3")
    files["artifacts/audit/b3/summary.json"] = dump({**s, "substitute_for": {"decision": "D18"}})
    r = g7(tmp_path / "undecided", files)
    assert not r.ok
    assert "substitution not justified in DECISIONS.md" in r.evidence
    decision: Files = {"DECISIONS.md": "# Decisions\n\n## D18 substitute\n"}
    late = sc.g7_confirmatory_audit(build(tmp_path / "late", [("data", files), ("dec", decision)]))
    assert not late.ok
    assert "substitution decision D18 not committed before data collection" in late.evidence
    early = sc.g7_confirmatory_audit(
        build(tmp_path / "early", [("dec", decision), ("data", {**files, **decision})])
    )
    assert early.ok, early.evidence


# =========================================================================== G8 (E4)

SURVIVOR: AuditTask = ("t5", "stable_pass", [("violating", True, True)])
G8_TASKS: dict[str, list[AuditTask]] = {
    "b1": [*AUDIT_TASKS, SURVIVOR],  # surviving variants on t0 and t5
    "b2": AUDIT_TASKS,  # on t0 (t4 is flaky: its survivor does not count)
    "b3": AUDIT_TASKS[1:4],  # none
}


def generalization(**change: Any) -> dict[str, Any]:
    return {
        "ran": True,
        "n_fresh_variants": 6,
        "survivors_original": 2,
        "caught_by_repair": 2,
        "survivors_repaired": 0,
        "induced_false_rejects": 0,
        **change,
    }


@dataclass
class E4Case:
    """E4 summaries, private files (untracked), and public files (tracked)."""

    e4: dict[str, dict[str, Any]]
    private: dict[str, str]
    public: dict[str, str]
    manifest: dict[str, Any] | None = None
    tasks: dict[str, list[AuditTask]] | None = None


H_B1_T0, H_B1_T5, H_B2_T0 = sha("b1:t0"), sha("b1:t5"), sha("b2:t0")
PRIV_PATCH = f"private/outbound/patches/{H_B1_T0}.patch"
PRIV_LOG = f"private/outbound/patches/{H_B1_T0}.validation.json"
PUB_PATCH, PUB_LOG = "outbound/patches/b2-t0.patch", "outbound/patches/b2-t0.validation.json"


def e4_case() -> E4Case:
    """b1: t0 repaired privately, t5 unrepaired; b2: t0 repaired in public."""
    b1 = {
        "schema": "graderproof.e4/1",
        "ran": True,
        "benchmark": "b1",
        "repaired": [
            {
                "task_hash": H_B1_T0,
                "benchmark": "b1",
                "public": False,
                "patch": PRIV_PATCH,
                "validation_log": PRIV_LOG,
            }
        ],
        "unrepaired": [{"task_hash": H_B1_T5, "reason": "only exit-code requirements broken"}],
        "generalization": generalization(),
        "provenance": PROV,
    }
    pub = {"task_hash": H_B2_T0, "benchmark": "b2", "public": True}
    b2 = {
        **b1,
        "benchmark": "b2",
        "repaired": [{**pub, "patch": PUB_PATCH, "validation_log": PUB_LOG}],
        "unrepaired": [],
    }
    private = {
        PRIV_PATCH: "--- a/grader/grade.sh\n+++ b/grader/grade.sh\n",
        PRIV_LOG: dump({"accepted": True, "task_hash": H_B1_T0}),
    }
    public = {
        PUB_PATCH: "--- a/grader/grade.sh\n+++ b/grader/grade.sh\n",
        PUB_LOG: dump({"accepted": True, "task_hash": H_B2_T0}),
    }
    return E4Case({"b1": b1, "b2": b2}, private, public)


def g8(tmp: Path, case: E4Case, track: Sequence[str] = ()) -> sc.Result:
    """Build the origin checkout, run phase A there, clone it, and run G8 on the clone."""
    repo = Repo(tmp / "origin")
    files = audit_files(BENCHES, case.tasks or G8_TASKS)
    files[".gitignore"] = "private/\n"
    files.update(case.public)
    for bench, summary in case.e4.items():
        files[f"artifacts/e4/{bench}/summary.json"] = dump(summary)
    manifest = case.manifest or {
        "files": [{"path": p, "sha256": sha(t)} for p, t in sorted(case.private.items())]
    }
    files["outbound/patches/MANIFEST.json"] = dump(manifest)
    repo.write(files)
    repo.write(dict(case.private))
    for rel in track:
        repo.git("add", "-f", rel)
    repo.commit("e4")
    ctx = sc.Ctx(origin=repo.root, work=tmp / "work", fast=True, head=repo.git("rev-parse", "HEAD"))
    sc.check_origin(ctx)
    sc.make_clone(ctx)
    return sc.g8_repair(ctx)


def test_g8_passes_with_every_survivor_repaired_or_explained(tmp_path: Path) -> None:
    r = g8(tmp_path, e4_case())
    assert r.ok, r.evidence
    assert "3 tasks with surviving variants: 2 repaired (1 public, 1 private" in r.evidence
    assert "1 unrepaired with reasons; generalization 12 fresh variants" in r.evidence


def test_g8_reviewer_b4_empty_repair_set(tmp_path: Path) -> None:
    """g8g9_vacuous.py: a counted surviving variant and an E4 summary repairing nothing."""
    case = e4_case()
    case.e4["b1"]["repaired"], case.e4["b1"]["unrepaired"] = [], []
    r = g8(tmp_path, case)
    assert not r.ok
    assert "artifacts/e4/b1: 2 tasks with surviving variants are neither repaired" in r.evidence


def test_g8_fails_when_a_benchmark_with_survivors_has_no_e4_summary(tmp_path: Path) -> None:
    case = e4_case()
    del case.e4["b2"]
    r = g8(tmp_path, case)
    assert not r.ok
    assert "artifacts/e4/b2/summary.json missing (1 tasks with surviving variants)" in r.evidence


def test_g8_ignores_the_old_single_summary_layout(tmp_path: Path) -> None:
    case = e4_case()
    old = case.e4.pop("b1")
    case.public["artifacts/e4/summary.json"] = dump(old)
    r = g8(tmp_path, case)
    assert not r.ok
    assert "artifacts/e4/b1/summary.json missing" in r.evidence


def test_g8_fails_when_no_audit_has_a_surviving_variant(tmp_path: Path) -> None:
    """D6: an empty survivor set proves nothing."""
    case = e4_case()
    case.e4 = {}
    case.tasks = {b: AUDIT_TASKS[1:4] for b in ("b1", "b2", "b3")}
    r = g8(tmp_path, case)
    assert not r.ok
    assert "no surviving variants in any audit" in r.evidence


def test_g8_fails_when_nothing_is_repaired_anywhere(tmp_path: Path) -> None:
    case = e4_case()
    reason = "only exit-code requirements broken"
    case.e4["b1"]["repaired"] = []
    case.e4["b1"]["unrepaired"] = [{"task_hash": h, "reason": reason} for h in (H_B1_T0, H_B1_T5)]
    case.e4["b2"]["repaired"] = []
    case.e4["b2"]["unrepaired"] = [{"task_hash": H_B2_T0, "reason": reason}]
    case.private, case.public = {}, {}
    r = g8(tmp_path, case)
    assert not r.ok
    assert "no task repaired in any benchmark" in r.evidence


def unrepaired(**entry: Any) -> list[dict[str, Any]]:
    return [{"task_hash": H_B1_T5, **entry}]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"unrepaired": unrepaired(reason="")}, "unrepaired "),
        ({"unrepaired": unrepaired(reason=None)}, "has no reason"),
        (
            {"unrepaired": [*unrepaired(reason="x"), {"task_hash": sha("b1:t2"), "reason": "x"}]},
            "1 listed tasks have no surviving variant",
        ),
        (
            {"unrepaired": [*unrepaired(reason="x"), {"task_hash": sha("b1:t4"), "reason": "x"}]},
            "1 listed tasks have no surviving variant",
        ),
        (
            {"unrepaired": [*unrepaired(reason="x"), *unrepaired(reason="y")]},
            "listed more than once",
        ),
        ({"schema": None}, "schema is not graderproof.e4/1"),
        ({"ran": "true"}, "not marked ran"),
        ({"benchmark": "other"}, "benchmark 'other' is not 'b1'"),
        ({"provenance": None}, "provenance lacks"),
        ({"unrepaired": None}, "unrepaired is not a list"),
        ({"generalization": {"ran": False}}, "no post-repair generalization batch"),
        ({"generalization": generalization(n_fresh_variants=0)}, "has no fresh variants"),
        ({"generalization": generalization(induced_false_rejects=None)}, "lacks induced_false"),
        ({"generalization": generalization(caught_by_repair=3)}, "counts are inconsistent"),
    ],
)
def test_g8_fails_on_a_bad_e4_summary(tmp_path: Path, change: dict[str, Any], message: str) -> None:
    case = e4_case()
    case.e4["b1"].update(change)
    r = g8(tmp_path, case)
    assert not r.ok
    assert message in r.evidence
    assert r.evidence.startswith("artifacts/e4/b1: ")


@pytest.mark.parametrize(
    ("bench", "key", "value", "message"),
    [
        ("b2", "patch", "outbound/patches/missing.patch", "public patch 'outbound/patches/missing"),
        ("b2", "patch", "outbound/patches/../../README.md", "missing under outbound/patches/"),
        ("b2", "public", "yes", "public is not true or false"),
        ("b2", "benchmark", "b1", "names another benchmark"),
        ("b1", "patch", "private/outbound/patches/other.patch", "not in outbound/patches/MANIFEST"),
        ("b1", "patch", PRIV_LOG, "uses one file as patch and validation log"),
        ("b1", "validation_log", "outbound/patches/b2-t0.validation.json", "not in outbound"),
        ("b1", "task_hash", "t0", "repaired without task_hash"),
    ],
)
def test_g8_checks_where_patches_and_logs_live(
    tmp_path: Path, bench: str, key: str, value: Any, message: str
) -> None:
    case = e4_case()
    case.e4[bench]["repaired"][0][key] = value
    r = g8(tmp_path, case)
    assert not r.ok
    assert message in r.evidence


def test_g8_requires_accepted_logs_for_the_right_task(tmp_path: Path) -> None:
    case = e4_case()
    case.public[PUB_LOG] = dump({"accepted": False, "task_hash": H_B2_T0})
    r = g8(tmp_path / "public", case)
    assert not r.ok
    assert (
        'validation log outbound/patches/b2-t0.validation.json does not say "accepted": true'
        in (r.evidence)
    )
    case = e4_case()
    case.private[PRIV_LOG] = dump({"accepted": "true", "task_hash": H_B1_T0})
    r = g8(tmp_path / "private", case)
    assert not r.ok
    assert f'validation log {PRIV_LOG} does not say "accepted": true' in r.evidence
    case = e4_case()
    case.public[PUB_LOG] = dump({"accepted": True, "task_hash": H_B1_T0})
    r = g8(tmp_path / "other", case)
    assert not r.ok
    assert "is for another task" in r.evidence


def test_g8_verifies_private_hashes_in_the_origin(tmp_path: Path) -> None:
    case = e4_case()
    case.manifest = {
        "files": [{"path": p, "sha256": sha(t + "edited")} for p, t in case.private.items()]
    }
    r = g8(tmp_path / "stale", case)
    assert not r.ok
    assert "private patch manifest: " in r.evidence
    assert "sha256 mismatch" in r.evidence
    case = e4_case()
    del case.private[PRIV_PATCH]
    case.manifest = {"files": [{"path": PRIV_PATCH, "sha256": "0" * 64}]}
    r = g8(tmp_path / "gone", case)
    assert not r.ok
    assert f"{PRIV_PATCH}: missing" in r.evidence


def test_g8_fails_when_a_private_patch_is_tracked(tmp_path: Path) -> None:
    r = g8(tmp_path, e4_case(), track=[PRIV_PATCH])
    assert not r.ok
    assert f"private patch {PRIV_PATCH} is tracked" in r.evidence


def test_g8_fails_without_audits(tmp_path: Path) -> None:
    ctx = sc.Ctx(origin=tmp_path, work=tmp_path / "work", fast=True)
    ctx.clone = tmp_path
    r = sc.g8_repair(ctx)
    assert not r.ok
    assert "no audited benchmarks" in r.evidence


# =========================================================================== G9 (E5)

E5_TASKS = [sha(f"b1:e5-{i}") for i in range(8)]


def e5_row(model: str, task_hash: str, trial: int, original: Any, repaired: Any) -> dict[str, Any]:
    return {
        "model": model,
        "task_hash": task_hash,
        "trial": trial,
        "original_pass": original,
        "repaired_pass": repaired,
    }


def e5_rows() -> list[dict[str, Any]]:
    """m-a passes everything until the repair rejects tasks 0 to 4; m-b passes tasks 0 to 5
    under both graders; m-c passes tasks 0 to 3 until the repair rejects task 0.
    Pass flips 12/36; rank changes 2 (m-a vs m-b and m-a vs m-c)."""
    rows = []
    for i, h in enumerate(E5_TASKS):
        for trial in (0, 1):
            rows.append(e5_row("m-a", h, trial, True, i > 4))
            rows.append(e5_row("m-b", h, trial, i <= 5, i <= 5))
            rows.append(e5_row("m-c", h, trial, i <= 3, 1 <= i <= 3))
    return rows


def flips_of(rows: Sequence[Mapping[str, Any]]) -> float | None:
    passed = [r for r in rows if r["original_pass"]]
    return sum(1 for r in passed if not r["repaired_pass"]) / len(passed) if passed else None


def ranks_of(rows: Sequence[Mapping[str, Any]], models: Sequence[str]) -> float | None:
    rates: dict[str, tuple[Fraction, Fraction]] = {}
    for m in models:
        mine = [r for r in rows if r["model"] == m]
        if not mine:
            return None
        o = sum(1 for r in mine if r["original_pass"])
        p = sum(1 for r in mine if r["repaired_pass"])
        rates[m] = (Fraction(o, len(mine)), Fraction(p, len(mine)))

    def sign(x: Fraction) -> int:
        return (x > 0) - (x < 0)

    changed = 0
    for i, a in enumerate(models):
        for b in models[i + 1 :]:
            before = sign(rates[a][0] - rates[b][0])
            after = sign(rates[a][1] - rates[b][1])
            changed += before != after
    return float(changed)


def e5_summary(rows: Sequence[Mapping[str, Any]], seed: int = SEED) -> dict[str, Any]:
    """The task-cluster bootstrap of the module docstring, written out plainly."""
    tasks = sorted({str(r["task_hash"]) for r in rows})
    models = sorted({str(r["model"]) for r in rows})
    by_task = {t: [r for r in rows if r["task_hash"] == t] for t in tasks}

    def pooled(idx: Sequence[int]) -> list[Mapping[str, Any]]:
        return [r for i in idx for r in by_task[tasks[i]]]

    def flips(idx: Sequence[int]) -> float | None:
        return flips_of(pooled(idx))

    def ranks(idx: Sequence[int]) -> float | None:
        return ranks_of(pooled(idx), models)

    doc: dict[str, Any] = {
        "ran": True,
        "benchmark": "b1",
        "bootstrap": {"seed": seed, "B": REPS, "alpha": 0.05},
        "provenance": PROV,
    }
    for key, stat, s in (("pass_flips", flips, seed), ("rank_changes", ranks, seed + 1)):
        ci = sc.bootstrap_ci(len(tasks), stat, s, REPS)
        doc[key] = {"point": stat(list(range(len(tasks)))), "ci": list(ci) if ci else []}
    return doc


def g9_files(rows: Sequence[Mapping[str, Any]] | None = None) -> Files:
    data = e5_rows() if rows is None else list(rows)
    files = audit_files(BENCHES[:1])
    files["artifacts/e5/b1/rows.jsonl"] = jsonl(data)
    files["artifacts/e5/b1/summary.json"] = dump(e5_summary(data) if data else {})
    files["docs/cards/b1.md"] = "# b1 grader card\n\nFalse-accept task rate 0.333 over 3 tasks.\n"
    files["docs/cards/b1.json"] = dump({"benchmark": "b1", "false_accept_task_rate": 0.333})
    return files


def e5_doc(files: Files) -> dict[str, Any]:
    text = files["artifacts/e5/b1/summary.json"]
    assert text is not None
    doc: dict[str, Any] = json.loads(text)
    return doc


def g9(tmp: Path, files: Files) -> sc.Result:
    return sc.g9_impact_and_cards(build(tmp, [("e5", files)]))


def test_g9_passes_with_recomputed_flips_and_rank_changes(tmp_path: Path) -> None:
    files = g9_files()
    doc = e5_doc(files)
    assert doc["pass_flips"]["point"] == pytest.approx(1 / 3)
    assert doc["rank_changes"]["point"] == 2.0
    r = g9(tmp_path, files)
    assert r.ok, r.evidence
    assert "E5 recomputed: b1: pass_flips 0.333 [" in r.evidence
    assert "rank_changes 2.000 [" in r.evidence
    assert "over 8 tasks and 3 models; 1 cards, aggregates only" in r.evidence


def test_g9_reviewer_b5_empty_intervals(tmp_path: Path) -> None:
    """g8g9_vacuous.py: ran, provenance, and empty interval lists, nothing else."""
    files = g9_files()
    vacuous = {
        "ran": True,
        "provenance": PROV,
        "pass_flips": {"ci": []},
        "rank_changes": {"ci": []},
    }
    files["artifacts/e5/b1/summary.json"] = dump(vacuous)
    r = g9(tmp_path / "vacuous", files)
    assert not r.ok
    assert "artifacts/e5/b1/summary.json has no bootstrap block" in r.evidence
    files["artifacts/e5/b1/summary.json"] = dump(
        {**vacuous, "bootstrap": e5_doc(g9_files())["bootstrap"]}
    )
    r = g9(tmp_path / "nopoint", files)
    assert not r.ok
    assert "artifacts/e5/b1 pass_flips point None differs" in r.evidence


@pytest.mark.parametrize(
    ("key", "field", "value", "message"),
    [
        ("pass_flips", "point", 0.25, "pass_flips point 0.25 differs from the recomputed 0.333"),
        ("rank_changes", "point", 1, "rank_changes point 1 differs from the recomputed 2.000"),
        ("rank_changes", "ci", [0, 3, 4], "rank_changes interval [0, 3, 4] differs"),
        ("pass_flips", "ci", ["0", "1"], "pass_flips interval ['0', '1'] differs"),
    ],
)
def test_g9_compares_stated_estimates(
    tmp_path: Path, key: str, field: str, value: Any, message: str
) -> None:
    files = g9_files()
    doc = e5_doc(files)
    doc[key][field] = value
    files["artifacts/e5/b1/summary.json"] = dump(doc)
    r = g9(tmp_path, files)
    assert not r.ok
    assert message in r.evidence


def test_g9_requires_each_interval_to_contain_its_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = g9_files()
    doc = e5_doc(files)
    for key in ("pass_flips", "rank_changes"):
        doc[key]["ci"] = [2.5, 3.0]
    files["artifacts/e5/b1/summary.json"] = dump(doc)

    def fixed(*args: Any, **kwargs: Any) -> tuple[float, float]:
        return 2.5, 3.0

    monkeypatch.setattr(sc, "bootstrap_ci", fixed)
    r = g9(tmp_path, files)
    assert not r.ok
    assert "artifacts/e5/b1 pass_flips interval does not contain its point" in r.evidence


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([{**e5_rows()[0], "original_pass": "true"}, *e5_rows()[1:]], "must be true or false"),
        ([{**e5_rows()[0], "repaired_pass": None}, *e5_rows()[1:]], "must be true or false"),
        ([{**e5_rows()[0], "trial": True}, *e5_rows()[1:]], "a row has no trial"),
        ([{**e5_rows()[0], "model": ""}, *e5_rows()[1:]], "a row has no model"),
        ([{**e5_rows()[0], "task_hash": "e5-0"}, *e5_rows()[1:]], "a row has no task_hash"),
        ([*e5_rows(), e5_rows()[0]], "repeats a (model, task, trial) row"),
        ([r for r in e5_rows() if r["model"] == "m-a"], "need at least two models (found 1)"),
        ([{**r, "original_pass": False} for r in e5_rows()], "pass_flips undefined"),
        ([], "rows.jsonl missing or empty"),
    ],
)
def test_g9_validates_rows(tmp_path: Path, rows: list[dict[str, Any]], message: str) -> None:
    files = g9_files()
    files["artifacts/e5/b1/rows.jsonl"] = jsonl(rows)
    r = g9(tmp_path, files)
    assert not r.ok
    assert message in r.evidence


def test_g9_needs_an_e5_run_and_checks_every_one(tmp_path: Path) -> None:
    files = g9_files()
    files["artifacts/e5/b1/summary.json"] = dump({**e5_doc(files), "ran": False})
    r = g9(tmp_path / "notrun", files)
    assert not r.ok
    assert "no E5 impact artifact that ran" in r.evidence
    files = g9_files()
    del files["artifacts/e5/b1/summary.json"]
    assert not g9(tmp_path / "none", files).ok
    files = g9_files()
    files["artifacts/e5/b2/summary.json"] = dump({**e5_doc(files), "benchmark": "b2"})
    r = g9(tmp_path / "second", files)
    assert not r.ok
    assert "artifacts/e5/b2/rows.jsonl missing or empty" in r.evidence
    files = g9_files()
    files["artifacts/e5/b1/summary.json"] = dump(
        {**e5_doc(files), "bootstrap": {"seed": 1, "B": 999, "alpha": 0.05}}
    )
    assert "B=999 (< 1000)" in g9(tmp_path / "reps", files).evidence


def test_g9_card_checks(tmp_path: Path) -> None:
    files = g9_files()
    del files["docs/cards/b1.json"]
    r = g9(tmp_path / "missing", files)
    assert not r.ok
    assert "grader card for b1 missing" in r.evidence
    for i, (text, card, ok) in enumerate(
        [
            ("task t0 accepts a broken solution", {"benchmark": "b1"}, False),
            ("task t3 rejects its own reference", {"benchmark": "b1"}, False),
            ("task t2 is fine", {"benchmark": "b1"}, True),
            ("task t0 was fixed", {"benchmark": "b1", "fixed_upstream_tasks": ["t0"]}, True),
            ("aggregate only", {"benchmark": "b1", "tasks": []}, False),
        ]
    ):
        files = g9_files()
        files["docs/cards/b1.md"] = f"# b1\n\n{text}\n"
        files["docs/cards/b1.json"] = dump(card)
        r = g9(tmp_path / str(i), files)
        assert r.ok is ok, (text, r.evidence)


# =========================================================================== G10

GOOD_MAKE = (
    "claimcheck:\n\t@echo 'claimcheck: README.md 3 numbers ok; docs/REPORT.md 5 numbers ok'\n"
    "freshness:\n\t@echo 'freshness: README.md ok; docs/REPORT.md ok'\n"
)


def g10(tmp: Path, makefile: str, report: bool = True) -> sc.Result:
    files: Files = {"Makefile": makefile, "README.md": "# graderproof\n"}
    if report:
        files["docs/REPORT.md"] = "# Report\n"
    return sc.g10_claim_integrity(build(tmp, [("docs", files)]))


def test_g10_passes_when_both_tools_report_on_both_documents(tmp_path: Path) -> None:
    r = g10(tmp_path, GOOD_MAKE)
    assert r.ok, r.evidence
    assert "docs/REPORT.md 5 numbers ok" in r.evidence


@pytest.mark.parametrize(
    ("makefile", "report", "message"),
    [
        (GOOD_MAKE, False, "docs/REPORT.md missing"),
        (GOOD_MAKE.replace("@echo 'claimcheck", "@exit 1; echo '"), True, "make claimcheck failed"),
        (GOOD_MAKE.replace("; docs/REPORT.md ok'", "'"), True, "make freshness did not report on"),
        ("claimcheck:\n\t@echo not built yet; exit 1\n", True, "make claimcheck failed"),
    ],
)
def test_g10_fails(tmp_path: Path, makefile: str, report: bool, message: str) -> None:
    r = g10(tmp_path, makefile, report)
    assert not r.ok
    assert message in r.evidence


# =========================================================================== G11

REAL_VERIFY = "python3 tools/prereg.py verify"
NO_VERIFY = "true"  # a weakened target: G11's own checks must still catch every scenario
E0_SCORE: Files = {
    "artifacts/e0/results.json": dump({"schema": "graderproof.e0/1", "prereg": PREREG_E0})
}


def e0_run(confirmatory: Any = True, **change: Any) -> Files:
    summary: dict[str, Any] = {
        "schema": "graderproof.audit/1",
        "prereg": PREREG_E0,
        "model_store": "artifacts/model_calls/e0",
        **change,
    }
    if confirmatory is not None:
        summary["confirmatory"] = confirmatory
    return {
        "artifacts/model_calls/e0/requests/r1.json": dump({"items": ["opaque"]}),
        "artifacts/e0/summary.json": dump(summary),
        "artifacts/e0/tasks.jsonl": jsonl([{"task": "toybench:t1"}]),
    }


def audit_run(**change: Any) -> Files:
    summary = {
        "benchmark": "b1",
        "confirmatory": True,
        "prereg": PREREG_E1,
        "model_store": "artifacts/model_calls/b1",
        **change,
    }
    return {
        "artifacts/model_calls/b1/requests/r1.json": dump({"items": ["opaque"]}),
        "artifacts/audit/b1/summary.json": dump(summary),
    }


def g11_repo(tmp: Path, verify: str) -> Repo:
    repo = Repo(tmp / "repo")
    makefile = f"prereg-verify:\n\t{verify}\n"
    tool = (TOOLS / "prereg.py").read_text(encoding="utf-8")
    repo.commit("init", {"README.md": "x\n", "Makefile": makefile, "tools/prereg.py": tool})
    return repo


def freeze(repo: Repo, rel: str, text: str = "# Preregistration\n", commit: bool = True) -> None:
    repo.write({rel: text})
    prereg.freeze(repo.root / rel, repo=repo.root, now="2026-11-04T00:00:00Z")
    if commit:
        repo.commit(f"freeze {rel}")


def g11(tmp: Path, repo: Repo) -> sc.Result:
    return sc.g11_prereg_integrity(repo.ctx(tmp / "work"))


def g11_correct(tmp: Path, verify: str) -> Repo:
    repo = g11_repo(tmp, verify)
    freeze(repo, PREREG_E0)
    freeze(repo, PREREG_E1)
    repo.commit("e0 run", e0_run())
    repo.commit("audit", audit_run())
    repo.commit("e0 score", E0_SCORE)
    return repo


BOTH = pytest.mark.parametrize("verify", [REAL_VERIFY, NO_VERIFY])


@BOTH
def test_g11_passes_when_preregistrations_come_first(tmp_path: Path, verify: str) -> None:
    r = g11(tmp_path, g11_correct(tmp_path, verify))
    assert r.ok, r.evidence
    assert "2 preregistrations frozen; 3 confirmatory artifacts follow them" in r.evidence


@BOTH
def test_g11_reviewer_b3_e0_outputs_before_the_preregistration(tmp_path: Path, verify: str) -> None:
    """g11_e0order.py: audit outputs (no confirmatory flag), then the freeze, then e0-score."""
    repo = g11_repo(tmp_path, verify)
    repo.commit("e0 run", e0_run(confirmatory=None, prereg=None))
    freeze(repo, PREREG_E0)
    freeze(repo, PREREG_E1)
    repo.commit("audit", audit_run())
    results = {"prereg": PREREG_E0, "confirmatory": False}
    repo.commit("e0 score", {"artifacts/e0/results.json": dump(results)})
    r = g11(tmp_path, repo)
    assert not r.ok
    if verify == NO_VERIFY:
        assert "artifacts/e0/summary.json is not marked confirmatory" in r.evidence
    else:
        assert "make prereg-verify failed" in r.evidence
    problems = " | ".join(prereg.verify(repo.root))
    assert "was not committed before artifacts/e0/results.json" in problems


@BOTH
def test_g11_dates_e0_by_its_outputs_even_when_marked(tmp_path: Path, verify: str) -> None:
    repo = g11_repo(tmp_path, verify)
    repo.commit("e0 run", e0_run())
    freeze(repo, PREREG_E0)
    freeze(repo, PREREG_E1)
    repo.commit("audit", audit_run())
    repo.commit("e0 score", E0_SCORE)
    r = g11(tmp_path, repo)
    assert not r.ok
    if verify == NO_VERIFY:
        assert "prereg/0001-e0-tool-validity.md does not predate the data of" in r.evidence
    else:
        assert "make prereg-verify failed" in r.evidence


@BOTH
def test_g11_dates_e0_by_its_first_model_call(tmp_path: Path, verify: str) -> None:
    repo = g11_repo(tmp_path, verify)
    repo.commit("first call", {"artifacts/model_calls/e0/requests/r0.json": dump({"items": []})})
    freeze(repo, PREREG_E0)
    freeze(repo, PREREG_E1)
    repo.commit("e0 run", e0_run())
    repo.commit("audit", audit_run())
    repo.commit("e0 score", E0_SCORE)
    r = g11(tmp_path, repo)
    assert not r.ok
    assert verify == REAL_VERIFY or "artifacts/model_calls/e0" in r.evidence


@BOTH
def test_g11_dates_an_audit_by_its_named_model_store(tmp_path: Path, verify: str) -> None:
    repo = g11_repo(tmp_path, verify)
    freeze(repo, PREREG_E0)
    repo.commit("b1 calls", {"artifacts/model_calls/b1/requests/r0.json": dump({"items": []})})
    freeze(repo, PREREG_E1)
    repo.commit("e0 run", e0_run())
    repo.commit("audit", audit_run())
    repo.commit("e0 score", E0_SCORE)
    r = g11(tmp_path, repo)
    assert not r.ok
    assert verify == REAL_VERIFY or "prereg/0002-e1-e2-audit.md does not predate" in r.evidence


@BOTH
def test_g11_dates_data_moved_in_from_a_pilot(tmp_path: Path, verify: str) -> None:
    repo = g11_repo(tmp_path, verify)
    pilot = e0_run()["artifacts/e0/tasks.jsonl"]
    repo.commit("pilot", {"artifacts/pilot/tasks.jsonl": pilot})
    freeze(repo, PREREG_E0)
    freeze(repo, PREREG_E1)
    repo.commit("e0 run", {**e0_run(), "artifacts/pilot/tasks.jsonl": None})
    repo.commit("audit", audit_run())
    repo.commit("e0 score", E0_SCORE)
    r = g11(tmp_path, repo)
    assert not r.ok
    assert verify == REAL_VERIFY or "does not predate the data of artifacts/e0" in r.evidence


@BOTH
def test_g11_fails_when_a_preregistration_is_edited(tmp_path: Path, verify: str) -> None:
    repo = g11_correct(tmp_path, verify)
    repo.commit("edit", {PREREG_E0: "# Preregistration, thresholds lowered\n"})
    r = g11(tmp_path, repo)
    assert not r.ok
    assert verify == REAL_VERIFY or f"{PREREG_E0} has 2 commits" in r.evidence


@BOTH
def test_g11_fails_when_the_file_differs_from_its_frozen_hash(tmp_path: Path, verify: str) -> None:
    repo = g11_repo(tmp_path, verify)
    freeze(repo, PREREG_E0, commit=False)
    repo.commit("freeze, edited first", {PREREG_E0: "# edited after freezing\n"})
    freeze(repo, PREREG_E1)
    repo.commit("e0 run", e0_run())
    repo.commit("audit", audit_run())
    repo.commit("e0 score", E0_SCORE)
    r = g11(tmp_path, repo)
    assert not r.ok
    assert verify == REAL_VERIFY or "does not match its prereg/FROZEN.jsonl entry" in r.evidence


@BOTH
@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"prereg": "prereg/FROZEN.jsonl"}, "cites no frozen preregistration"),
        ({"prereg": "prereg/0009-missing.md"}, "cites no frozen preregistration"),
        ({"prereg": None}, "cites no frozen preregistration"),
        ({"prereg": [PREREG_E1]}, "cites no frozen preregistration"),
        ({"model_store": "runs/model_calls/b1"}, "is not a directory under artifacts/"),
        ({"model_store": "/abs/model_calls"}, "is not a directory under artifacts/"),
        ({"model_store": "artifacts/../runs"}, "is not a directory under artifacts/"),
    ],
)
def test_g11_checks_citations_and_model_stores(
    tmp_path: Path, verify: str, change: dict[str, Any], message: str
) -> None:
    repo = g11_correct(tmp_path, verify)
    repo.commit("bad citation", audit_run(**change))
    r = g11(tmp_path, repo)
    assert not r.ok
    assert verify == REAL_VERIFY or message in r.evidence


@BOTH
def test_g11_requires_the_e0_summary_to_say_confirmatory(tmp_path: Path, verify: str) -> None:
    repo = g11_correct(tmp_path, verify)
    repo.commit("unmark", {"artifacts/e0/summary.json": dump({"prereg": PREREG_E0})})
    r = g11(tmp_path, repo)
    assert not r.ok
    assert (
        verify == REAL_VERIFY
        or "artifacts/e0/summary.json is not marked confirmatory" in r.evidence
    )


@BOTH
def test_g11_fails_on_an_unreadable_summary(tmp_path: Path, verify: str) -> None:
    repo = g11_correct(tmp_path, verify)
    repo.commit("broken", {"artifacts/audit/b2/summary.json": "{not json"})
    r = g11(tmp_path, repo)
    assert not r.ok
    assert (
        verify == REAL_VERIFY or "artifacts/audit/b2/summary.json is not valid JSON" in r.evidence
    )


def test_g11_fails_on_empty_sets(tmp_path: Path) -> None:
    repo = g11_repo(tmp_path / "none", NO_VERIFY)
    assert "no preregistrations" in g11(tmp_path / "none", repo).evidence
    repo = g11_repo(tmp_path / "noart", NO_VERIFY)
    freeze(repo, PREREG_E0)
    assert "no confirmatory artifacts" in g11(tmp_path / "noart", repo).evidence
    repo = g11_repo(tmp_path / "real", REAL_VERIFY)
    assert "make prereg-verify failed" in g11(tmp_path / "real", repo).evidence


def test_g11_counts_a_preregistration_merged_from_a_branch_once(tmp_path: Path) -> None:
    repo = g11_repo(tmp_path, REAL_VERIFY)
    repo.git("checkout", "-q", "-b", "freeze-branch")
    freeze(repo, PREREG_E0)
    freeze(repo, PREREG_E1)
    repo.git("checkout", "-q", "-")
    repo.commit("main moves on", {"NOTES.md": "x\n"})
    repo.git("merge", "-q", "--no-ff", "--no-edit", "freeze-branch")
    repo.commit("e0 run", e0_run())
    repo.commit("audit", audit_run())
    repo.commit("e0 score", E0_SCORE)
    r = g11(tmp_path, repo)
    assert r.ok, r.evidence
