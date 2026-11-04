"""Contract tests for the tau2-bench adapter (graderproof.adapters.tau2 and its driver).

Offline tests use verbatim tau2-bench v1.0.1 records and policies from
tests/fixtures/tau2/src and driver outputs recorded from live runs in
tests/fixtures/tau2/recorded. The generated shell scripts run for real; only the tau2
interpreter is replaced by a stand-in that checks its arguments and serves the recorded
outputs. The driver's logic is tested against a small fake of the tau2 API.

Live tests run the real driver under bubblewrap. They are skipped unless GP_TAU2_ROOT
(the pinned checkout) and GP_TAU2_PYTHON (its venv's python) are set; with
GP_TAU2_RECORD=1 they also rewrite the recorded outputs.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from graderproof.adapters import Execution, language_of
from graderproof.adapters import tau2 as t2
from graderproof.adapters import tau2_driver as drv
from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.core import Determinism, Task, canonical_json
from graderproof.run import Runner, SandboxPolicyError
from graderproof.sandbox import BwrapSandbox, ExecResult, Limits, LocalSandbox, bwrap_works

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "tau2"
SRC = FIXTURES / "src"
RECORDED = FIXTURES / "recorded"
RECORD_SHA256 = {
    ("airline", "7"): "8c66a0f45bbb05bfd11a8444a417d26e091bb95dc9f7e309f20806cf49f17e2e",
    ("retail", "69"): "2febc257034c4c7d1010b67cff837d8da11ff4fb1d659b85b8784d4d4b16ea43",
    ("retail", "24"): "ce2a3c2855b166a49990d2f09a849cc37b0f7f849f3cb7338f209747972e4f97",
    (
        "telecom",
        "[mms_issue]bad_network_preference|user_abroad_roaming_disabled_on[PERSONA:None]",
    ): "6e83d87a80491c0f7fe0523985051061f9c7b0bbdcf474fe70569d3791e1ed83",
}
"""Canonical-JSON SHA-256 of each fixture record, taken from the pinned checkout."""
TELECOM_ID = "[mms_issue]bad_network_preference|user_abroad_roaming_disabled_on[PERSONA:None]"
TELECOM = t2.task_name("telecom", TELECOM_ID)
NAMES = ("airline-7", "retail-69", TELECOM)
DROPPED = {"airline-7": 3, TELECOM: 1}
"""The mutating call each live test drops: cancel_reservation and enable_roaming."""
LIVE_ROOT, LIVE_PYTHON = os.environ.get(t2.ENV_ROOT), os.environ.get(t2.ENV_PYTHON)
live = pytest.mark.skipif(
    not (LIVE_ROOT and LIVE_PYTHON and bwrap_works()),
    reason="needs GP_TAU2_ROOT, GP_TAU2_PYTHON, and bubblewrap",
)


def fixture_tasks(domain: str) -> list[dict[str, Any]]:
    """The fixture records of one domain."""
    data: list[dict[str, Any]] = json.loads(
        (SRC / t2.DOMAIN_DIR / domain / "tasks.json").read_text(encoding="utf-8")
    )
    return data


def record(domain: str, original_id: str) -> dict[str, Any]:
    """One fixture record by id."""
    return next(t for t in fixture_tasks(domain) if t["id"] == original_id)


AIRLINE, RETAIL, RETAIL_NL = record("airline", "7"), record("retail", "69"), record("retail", "24")
TELECOM_TASK = record("telecom", TELECOM_ID)


@pytest.fixture
def converted(tmp_path: Path) -> Path:
    """The fixture tasks converted into toybench task directories."""
    out = tmp_path / "tasks"
    t2.convert(SRC, out)
    return out


@pytest.fixture
def tasks(converted: Path) -> dict[str, Task]:
    """The converted tasks loaded by the toybench adapter."""
    return {t.id: t for t in ToybenchAdapter().load(converted)}


# ---------------------------------------------------------------------- fixtures


def test_fixtures_are_the_pinned_upstream_files() -> None:
    for (domain, original_id), digest in RECORD_SHA256.items():
        assert t2.record_sha256(record(domain, original_id)) == digest
    for rel in (
        "LICENSE",
        *(f"{t2.DOMAIN_DIR}/{d}/{f}" for d in t2.DOMAINS for f in t2.POLICY_FILES[d]),
    ):
        assert t2.sha256_file(SRC / rel) == t2.DATA_SHA256[rel], rel
    with pytest.raises(ValueError, match="files differ"):
        t2.verify_source(SRC)  # the fixture task files are subsets


# ------------------------------------------------------------------ task records


def test_base_tasks_follow_the_split_order() -> None:
    assert [t["id"] for t in t2.base_tasks(SRC, "retail")] == ["69", "24"]
    assert t2.base_tasks(SRC, "telecom") == [TELECOM_TASK]
    with pytest.raises(ValueError, match="unknown domain"):
        t2.domain_dir(SRC, "banking_knowledge")


def _domain(tmp_path: Path, records: Any, split: Any) -> Path:
    d = tmp_path / t2.DOMAIN_DIR / "airline"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tasks.json").write_text(json.dumps(records))
    (d / "split_tasks.json").write_text(json.dumps(split))
    return tmp_path


@pytest.mark.parametrize(
    ("records", "split", "message"),
    [
        ([{"id": 1}], {"base": []}, "string id"),
        ({"no": "tasks"}, {"base": []}, "string id"),
        ([{"id": "1"}, {"id": "1"}], {"base": ["1"]}, "duplicate task id"),
        ([{"id": "1"}], {"base": "1"}, "distinct ids"),
        ([{"id": "1"}], {"base": ["1", "1"]}, "distinct ids"),
        ([{"id": "1"}], {"base": ["2"]}, "no task for base id '2'"),
    ],
)
def test_base_tasks_rejects_malformed_files(
    tmp_path: Path, records: Any, split: Any, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        t2.base_tasks(_domain(tmp_path, records, split), "airline")


def test_base_tasks_accepts_a_tasks_object(tmp_path: Path) -> None:
    root = _domain(tmp_path, {"tasks": [{"id": "1"}, {"id": "2"}]}, {"base": ["2"]})
    assert t2.base_tasks(root, "airline") == [{"id": "2"}]


def test_domain_policy_is_composed_as_tau2_composes_it() -> None:
    d = SRC / t2.DOMAIN_DIR
    assert t2.domain_policy(SRC, "airline") == (d / "airline/policy.md").read_text()
    main = (d / "telecom/main_policy.md").read_text()
    tech = (d / "telecom/tech_support_manual.md").read_text()
    assert t2.domain_policy(SRC, "telecom") == (
        "<main_policy>\n"
        + main
        + "\n</main_policy>\n<tech_support_policy>\n"
        + tech
        + "\n</tech_support_policy>"
    )


def test_reward_basis_and_needs_judge() -> None:
    assert t2.reward_basis(AIRLINE) == ["DB", "COMMUNICATE"]
    assert t2.reward_basis(RETAIL) == ["DB", "NL_ASSERTION"]
    assert t2.reward_basis(TELECOM_TASK) == ["ENV_ASSERTION"]
    assert t2.reward_basis({"id": "x", "evaluation_criteria": {}}) == list(t2.DEFAULT_BASIS)
    assert t2.reward_basis({"id": "x", "evaluation_criteria": None}) == []
    assert t2.criteria({"id": "x"}) == {}
    assert [t2.needs_judge(t) for t in (AIRLINE, RETAIL, RETAIL_NL, TELECOM_TASK)] == [
        False,
        False,
        True,
        False,
    ]


def test_task_name() -> None:
    assert t2.task_name("airline", "12") == "airline-12"
    digest = hashlib.sha256(TELECOM_ID.encode()).hexdigest()
    assert f"telecom-{digest[:8]}" == TELECOM
    for bad in ("../x", "a b", "x\ny"):
        with pytest.raises(ValueError, match="safe directory name"):
            t2.task_name("retail", bad)


def test_reference_calls_are_the_gold_actions_in_order() -> None:
    calls = t2.reference_calls(AIRLINE)
    actions = AIRLINE["evaluation_criteria"]["actions"]
    assert [c["tool"] for c in calls] == [a["name"] for a in actions]
    assert [c["args"] for c in calls] == [a["arguments"] for a in actions]
    assert {c["requestor"] for c in calls} == {"assistant"}  # airline omits requestor
    telecom = t2.reference_calls(TELECOM_TASK)
    assert [(c["requestor"], c["tool"]) for c in telecom] == [
        ("user", "set_network_mode_preference"),
        ("assistant", "enable_roaming"),
    ]
    assert t2.reference_calls({"id": "x", "evaluation_criteria": {"actions": None}}) == []
    assert set(calls[0]) == {"tool", "args", "requestor"}  # no grading data such as action_id


def v101_communicated(info: str, message: str) -> bool:
    """v1.0.1's CommunicateEvaluator test for one string and one assistant message."""
    return info.lower() in message.lower().replace(",", "")


def test_final_message_satisfies_communicate_info() -> None:
    message = t2.final_message(AIRLINE)
    assert message == "Here is the information you asked for: 1628."
    many = {"id": "x", "evaluation_criteria": {"communicate_info": ["327", "1000", "1786"]}}
    assert all(v101_communicated(s, t2.final_message(many)) for s in ("327", "1000", "1786"))
    assert t2.final_message(RETAIL) == t2.CLOSING_MESSAGE


def test_instruction_labels_policy_and_request() -> None:
    policy = t2.domain_policy(SRC, "airline")
    text = t2.instruction(AIRLINE, "airline", policy)
    assert text.startswith("# tau2-bench airline task 7\n")
    assert "<policy>\n" + policy.rstrip("\n") + "\n</policy>" in text
    for label in ("## What to submit", "## Domain policy", "## Customer request", "## Source"):
        assert label in text
    request = AIRLINE["user_scenario"]["instructions"]
    for key in ("reason_for_call", "known_info", "task_instructions"):
        assert request[key].strip() in text
    assert "What the customer does not know" not in text  # unknown_info is null
    assert "`final_message.txt`" in text and '"requestor": "user"' not in text
    for assertion in AIRLINE["evaluation_criteria"]["nl_assertions"]:
        assert assertion not in text  # grading data never reaches the task text
    telecom = t2.instruction(TELECOM_TASK, "telecom", t2.domain_policy(SRC, "telecom"))
    assert '"requestor": "user"' in telecom and "final_message.txt" not in telecom
    plain = {"id": "9", "user_scenario": {"instructions": "  Cancel order 9.  "}}
    assert "## Customer request" in t2.instruction(plain, "retail", "P")
    assert "\nCancel order 9.\n" in t2.instruction(plain, "retail", "P")


def test_scripts_run_the_driver_with_the_pinned_paths() -> None:
    run = t2.run_solution_script("airline", "airline-7")
    grade = t2.grade_script("telecom", TELECOM)
    for script in (run, grade):
        assert script.startswith("#!/usr/bin/env bash\n")
        assert ': "${GP_TAU2_ROOT:?GP_TAU2_ROOT is not set}"' in script
        assert 'exec "$GP_TAU2_PYTHON" -I "$here/tau2_driver.py" ' in script
    assert 'simulate --root "$GP_TAU2_ROOT" --domain airline --task "$here/task.json" ' in run
    assert '--solution "$GP_SOLUTION_DIR" --out .' in run
    assert "--domain telecom" in grade and "${GP_TAU2_CROSSCHECK:+--crosscheck}" in grade
    with pytest.raises(ValueError, match="unsafe script parameters"):
        t2.grade_script("airline", "x\nrm -rf /")
    with pytest.raises(ValueError, match="unsafe script parameters"):
        t2.run_solution_script("mock", "mock-1")


def test_task_toml_fields() -> None:
    meta = tomllib.loads(t2.task_toml(TELECOM_TASK, "telecom"))
    assert {k: meta[k] for k in ("id", "benchmark", "kind", "third_party", "timeout_s")} == {
        "id": TELECOM,
        "benchmark": "tau2",
        "kind": "data",
        "third_party": True,
        "timeout_s": t2.TASK_TIMEOUT_S,
    }
    assert meta["solution"] == {"entry": "run_solution.sh"}
    assert meta["grader"] == {"entry": "grade.sh"}
    assert meta["metadata"] == {
        "benchmark": "tau2",
        "domain": "telecom",
        "stratum": "telecom",
        "original_id": TELECOM_ID,
        "source_repo": t2.REPO_URL,
        "source_tag": "v1.0.1",
        "source_commit": t2.PINNED_COMMIT,
        "source_path": "data/tau2/domains/telecom/tasks.json",
        "record_sha256": RECORD_SHA256[("telecom", TELECOM_ID)],
        "license": "MIT",
        "reward_basis": ["ENV_ASSERTION"],
    }


# ---------------------------------------------------------------------- convert


def test_convert_writes_every_kept_task(converted: Path) -> None:
    report = json.loads((converted / "conversion.json").read_text())
    assert report["source_commit"] == t2.PINNED_COMMIT
    assert {
        d["domain"]: (d["base"], d["converted"], d["needs_judge"]) for d in report["domains"]
    } == {
        "airline": (1, ["airline-7"], []),
        "retail": (2, ["retail-69"], ["24"]),
        "telecom": (1, [TELECOM], []),
    }
    assert sorted(p.name for p in converted.iterdir() if p.is_dir()) == sorted(NAMES)
    for name, task in (("airline-7", AIRLINE), ("retail-69", RETAIL), (TELECOM, TELECOM_TASK)):
        d = converted / name
        assert json.loads((d / "grader/task.json").read_text()) == task
        support = json.loads((d / "support/task.json").read_text())
        assert support == {k: v for k, v in task.items() if k != "evaluation_criteria"}
        driver_source = Path(drv.__file__).read_text(encoding="utf-8")
        assert (d / "grader/tau2_driver.py").read_text() == driver_source == t2.DRIVER_SOURCE
        assert (d / "support/tau2_driver.py").read_text() == driver_source
        trajectory = (d / "solution/trajectory.json").read_text()
        assert json.loads(trajectory) == t2.reference_calls(task)
        assert trajectory == json.dumps(t2.reference_calls(task), indent=2) + "\n"
        assert os.access(d / "support/run_solution.sh", os.X_OK)
        assert t2.COPYRIGHT in (d / t2.NOTICE_FILE).read_text()
    assert (converted / "airline-7/solution/final_message.txt").read_text() == t2.final_message(
        AIRLINE
    )
    assert not (converted / "retail-69/solution/final_message.txt").exists()


def test_conversion_to_dict_lists_paths_only_in_memory(tmp_path: Path) -> None:
    conversion = t2.convert(SRC, tmp_path, domains=("retail",))
    assert [p.name for p in conversion.paths] == ["retail-69"]
    assert "paths" not in conversion.to_dict()
    assert conversion.domains[0].to_dict()["needs_judge"] == ["24"]


def test_convert_refuses_stale_directories_and_name_collisions(
    converted: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (converted / "airline-99").mkdir()
    (converted / "airline-99" / "task.toml").write_text('id = "airline-99"\n')
    with pytest.raises(FileExistsError, match="airline-99"):
        t2.convert(SRC, converted)
    monkeypatch.setattr(t2, "task_name", lambda domain, original_id: "same")
    with pytest.raises(ValueError, match="one directory name"):
        t2.convert(SRC, tmp_path / "other")


def test_write_task_replaces_an_old_copy(tmp_path: Path) -> None:
    policy = t2.domain_policy(SRC, "retail")
    d = t2.write_task(RETAIL, "retail", policy, tmp_path)
    (d / "leftover.txt").write_text("old")
    assert t2.write_task(RETAIL, "retail", policy, tmp_path) == d
    assert not (d / "leftover.txt").exists()
    assert set(t2.task_files(RETAIL, "retail", policy)) == {
        str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()
    }


def test_converted_tasks_load_as_third_party_data_tasks(tasks: dict[str, Task]) -> None:
    assert sorted(tasks) == sorted(NAMES)
    airline = tasks["airline-7"]
    assert airline.benchmark == "tau2" and airline.key == "tau2:airline-7"
    assert airline.environment["kind"] == "data"
    assert airline.environment["third_party"] is True
    assert airline.metadata["trusted_local"] is False
    assert airline.metadata["stratum"] == "airline"
    assert airline.grading_entrypoint == ["bash", "grader/grade.sh"]
    assert ToybenchAdapter().mutable_files(airline) == {
        "trajectory.json": "trajectory",
        "final_message.txt": "text",
    }
    assert set(tasks[TELECOM].reference_solution) == {"trajectory.json"}
    assert language_of("trajectory.json") == "trajectory"


# ------------------------------------------------- recorded driver outputs (offline)

FAKE_PYTHON = r'''
"""Stand-in for the tau2 venv's python: checks the driver call, serves recorded outputs."""
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ["GP_TAU2_FAKE_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"argv": args, "cwd": os.getcwd(), "home": os.environ["HOME"]}) + "\n")
assert args[0] == "-I", args
driver, command, rest = Path(args[1]), args[2], args[3:]
assert driver.read_text() == Path(os.environ["GP_TAU2_FAKE_DRIVER"]).read_text()
opts, i = {}, 0
while i < len(rest):
    if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
        opts[rest[i]], i = rest[i + 1], i + 2
    else:
        opts[rest[i]], i = True, i + 1
assert opts["--root"] == os.environ["GP_TAU2_ROOT"], opts
task = json.loads(Path(opts["--task"]).read_text())
runs = json.loads(Path(os.environ["GP_TAU2_FAKE_RECORDINGS"]).read_text())
if command == "simulate":
    assert "evaluation_criteria" not in task and opts["--out"] == "."
    solution = Path(opts["--solution"])
    got = (solution / "trajectory.json").read_text()
    run = next(r for r in runs if r["solution"]["trajectory.json"] == got)
    outcome = run["execution"]["outcome"]
    Path(".gp").mkdir()
    Path("simulation.json").write_text(outcome["files"]["simulation.json"])
    Path(".gp/trajectory.json").write_text(json.dumps(outcome["trajectory"]))
    Path(".gp/state.json").write_text(json.dumps(outcome["state"]))
    sys.stdout.write(outcome["stdout"])
    sys.exit(outcome["exit_status"])
assert command == "grade" and "evaluation_criteria" in task, command
got = Path(opts["--simulation"]).read_text()
run = next(r for r in runs if r["execution"]["outcome"]["files"]["simulation.json"] == got)
grade = run["execution"]["grade"]
sys.stdout.write(grade["stdout"])
sys.exit(grade["exit_status"])
'''


def recordings(name: str) -> list[dict[str, Any]]:
    """The recorded live runs of one fixture task (reference first)."""
    data: dict[str, Any] = json.loads((RECORDED / f"{name}.json").read_text(encoding="utf-8"))
    assert data["task"] == name and data["source_commit"] == t2.PINNED_COMMIT
    # recorded with the shipped driver: re-record (see the module docstring) after a change
    assert data["driver_sha256"] == t2.sha256_file(Path(drv.__file__))
    runs: list[dict[str, Any]] = data["runs"]
    return runs


@dataclass
class IsolatingLocalSandbox(LocalSandbox):
    """LocalSandbox that claims write isolation, for the Runner's policy check in tests."""

    isolates_writes: bool = True


def stand_in(tmp_path: Path, name: str) -> dict[str, str]:
    """``extra_env`` for one task whose tau2 python is the recorded-output stand-in."""
    fake = tmp_path / "fake_python.py"
    fake.write_text(FAKE_PYTHON)
    wrapper = tmp_path / "python"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n')
    wrapper.chmod(0o755)
    runs = tmp_path / f"{name}.runs.json"
    runs.write_text(json.dumps(recordings(name)))
    return {
        **t2.tau2_env(tmp_path / "tau2-root", wrapper),
        "GP_TAU2_FAKE_LOG": str(tmp_path / "calls.jsonl"),
        "GP_TAU2_FAKE_DRIVER": drv.__file__,
        "GP_TAU2_FAKE_RECORDINGS": str(runs),
    }


@pytest.mark.parametrize("name", NAMES)
def test_scripts_reproduce_the_recorded_executions(
    tasks: dict[str, Task], tmp_path: Path, name: str
) -> None:
    task = tasks[name]
    adapter = ToybenchAdapter(extra_env=stand_in(tmp_path, name))
    for run in recordings(name):
        want = Execution.from_dict(run["execution"])
        got = adapter.execute(task, run["solution"], LocalSandbox())
        assert got.outcome.files == want.outcome.files
        assert list(got.outcome.trajectory) == list(want.outcome.trajectory)
        assert got.outcome.state == want.outcome.state
        assert (got.grade.passed, got.grade.stdout) == (want.grade.passed, want.grade.stdout)
        report = t2.grade_report(got.grade.stdout)
        assert report["passed"] is got.grade.passed
        assert report["reward"] == (1.0 if run["label"] == "reference" else 0.0)
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert [c["argv"][2] for c in calls] == ["simulate", "grade"] * len(recordings(name))
    assert all(c["home"] == "/tmp" for c in calls)  # caches stay out of the workspace


def test_recorded_reference_outcomes_have_the_documented_shape() -> None:
    for name in NAMES:
        ref = Execution.from_dict(recordings(name)[0]["execution"])
        assert set(ref.outcome.files) == {"simulation.json"}
        sim = json.loads(ref.outcome.files["simulation.json"])
        assert sim["termination_reason"] == "agent_stop" and sim["timestamp"] == drv.TIMESTAMP
        calls = t2.reference_calls(
            {"airline-7": AIRLINE, "retail-69": RETAIL, TELECOM: TELECOM_TASK}[name]
        )
        assert [
            {k: c[k] for k in ("tool", "args", "requestor")} for c in ref.outcome.trajectory
        ] == calls
        assert all(("result" in c) != ("error" in c) for c in ref.outcome.trajectory)
        state = ref.outcome.state
        assert state is not None and set(state) == {"db", "user_db"}
        assert state["db"]["hash"] and state["db"]["changed"]
        assert (state["user_db"] is None) == (name != TELECOM)
    airline = Execution.from_dict(recordings("airline-7")[0]["execution"])
    assert airline.outcome.state is not None
    changed = airline.outcome.state["db"]["changed"]["reservations"]
    assert {r: changed[r]["status"] for r in ("XEHM4B", "59XX6W")} == {
        "XEHM4B": "cancelled",
        "59XX6W": "cancelled",
    }


def test_runner_refuses_a_sandbox_without_write_isolation(tasks: dict[str, Task]) -> None:
    runner = Runner(ToybenchAdapter(), LocalSandbox())
    with pytest.raises(SandboxPolicyError, match="third-party"):
        runner.execute(tasks["airline-7"], tasks["airline-7"].reference_solution)


def test_check_references_with_recorded_outputs(converted: Path, tmp_path: Path) -> None:
    keep = tmp_path / "one"
    keep.mkdir()
    shutil.copytree(converted / "airline-7", keep / "airline-7")
    env = stand_in(tmp_path, "airline-7")
    checks = t2.check_references(keep, env, IsolatingLocalSandbox(), repeat=2, jobs=2)
    assert [c.to_dict() for c in checks] == [
        {
            "task_id": "airline-7",
            "domain": "airline",
            "determinism": "stable_pass",
            "reward": 1.0,
            "crosscheck_reward": 1.0,  # the recordings were made with the cross-check on
            "error": "",
        }
    ]
    assert t2.domain_summary(checks) == {"airline": {"tasks": 1, "reward_1": 1, "failures": []}}


class ScriptedSandbox:
    """A sandbox that answers the solution run with nothing and the grader as scripted."""

    name = "scripted"
    isolates_writes = True

    def __init__(self, grades: Mapping[str, tuple[int, str, str]]) -> None:
        self.grades = grades

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        writable: Sequence[Path],
        readonly: Sequence[Path] = (),
        env: Mapping[str, str] | None = None,
        limits: Limits | None = None,
    ) -> ExecResult:
        """Grade by the task id in grader/task.json; the solution run does nothing."""
        if not argv[-1].endswith("grade.sh"):
            return ExecResult(0, "", "", 0.0, False, self.name)
        task = json.loads((Path(argv[-1]).parent / "task.json").read_text())
        status, out, err = self.grades[task["id"]]
        return ExecResult(status, out, err, 0.0, False, self.name)


def test_check_references_reports_errors_and_orders_by_domain(converted: Path) -> None:
    sandbox = ScriptedSandbox(
        {
            "7": (0, json.dumps({"reward": 1.0, "passed": True, "crosscheck_reward": 1.0}), ""),
            "69": (2, json.dumps({"error": "ValueError: boom", "passed": False}), "trace"),
            TELECOM_ID: (1, "not json", "crashed\n"),
        }
    )
    checks = t2.check_references(converted, {}, sandbox)
    assert [(c.task_id, c.determinism, c.reward, c.error) for c in checks] == [
        ("airline-7", Determinism.STABLE_PASS, 1.0, ""),
        ("retail-69", Determinism.STABLE_FAIL, None, "ValueError: boom"),
        (TELECOM, Determinism.STABLE_FAIL, None, "crashed"),
    ]
    summary = t2.domain_summary(checks)
    assert summary["retail"] == {"tasks": 1, "reward_1": 0, "failures": ["retail-69"]}
    assert t2.crosscheck_mismatches(checks) == []
    assert t2.crosscheck_mismatches(
        [checks[0], t2.ReferenceCheck("x", "a", checks[0].determinism, 1.0, 0.0)]
    ) == ["x"]


def test_grade_report_reads_the_last_json_object() -> None:
    assert t2.grade_report('noise\n{"reward": 0.0}\n[1]\n') == {"reward": 0.0}
    assert t2.grade_report("") == {}
    assert t2.grade_report("[1, 2]\nnot json") == {}


def test_natural_order_of_ids() -> None:
    ids = ["airline-10", "airline-9", "telecom-ab12cd34", "airline-x"]
    assert sorted(ids, key=t2._natural) == [
        "airline-x",
        "airline-9",
        "airline-10",
        "telecom-ab12cd34",
    ]


def test_tau2_env_keeps_the_venv_link(tmp_path: Path) -> None:
    target = tmp_path / "base-python"
    target.write_text("")
    link = tmp_path / "venv-python"
    link.symlink_to(target)
    env = t2.tau2_env(Path("relative/root"), link)
    assert env == {
        "GP_TAU2_ROOT": str(Path("relative/root").absolute()),
        "GP_TAU2_PYTHON": str(link),
    }
    assert t2.tau2_env(tmp_path, link, crosscheck=True)["GP_TAU2_CROSSCHECK"] == "1"


# ----------------------------------------------------------- fetch, venv, verify


def _run(cwd: Path, *args: str) -> str:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


@pytest.fixture
def upstream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """A local git repository standing in for tau2-bench, with its tag and commit pinned."""
    repo = tmp_path / "upstream"
    shutil.copytree(SRC, repo)
    git = ("git", "-c", "user.name=t", "-c", "user.email=t@example.invalid")
    _run(repo, "git", "init", "--quiet")
    _run(repo, "git", "add", ".")
    _run(repo, *git, "commit", "--quiet", "-m", "pinned")
    _run(repo, *git, "tag", "-a", "v1.0.1", "-m", "tag")
    commit = _run(repo, "git", "rev-parse", "HEAD")
    (repo / "later.txt").write_text("later")
    _run(repo, "git", "add", ".")
    _run(repo, *git, "commit", "--quiet", "-m", "later")
    digests = {
        rel: t2.sha256_file(SRC / rel)
        for rel in (p.relative_to(SRC).as_posix() for p in SRC.rglob("*") if p.is_file())
    }
    monkeypatch.setattr(t2, "REPO_URL", repo.as_uri())
    monkeypatch.setattr(t2, "PINNED_COMMIT", commit)
    monkeypatch.setattr(t2, "DATA_SHA256", digests)
    return repo, commit


def test_fetch_clones_the_pinned_tag_and_reuses_a_checkout(
    upstream: tuple[Path, str], tmp_path: Path
) -> None:
    repo, commit = upstream
    dest = tmp_path / "clone"
    assert t2.fetch(dest) == dest
    assert t2.source_commit(dest) == commit
    later = _run(repo, "git", "rev-parse", "HEAD")
    _run(dest, "git", "fetch", "--quiet", "origin", "HEAD")
    _run(dest, "git", "checkout", "--quiet", "--detach", later)
    assert t2.fetch(dest) == dest  # moved back to the pinned commit
    assert t2.source_commit(dest) == commit
    t2.verify_source(dest)
    assert t2.source_commit(tmp_path) is None


def test_fetch_refusals(
    upstream: tuple[Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "file").write_text("x")
    with pytest.raises(FileExistsError, match="not a git checkout"):
        t2.fetch(busy)
    monkeypatch.setattr(t2, "DATA_SHA256", {"LICENSE": "0" * 64})
    with pytest.raises(ValueError, match=r"differ from v1\.0\.1"):
        t2.fetch(tmp_path / "clone")
    monkeypatch.setattr(t2, "PINNED_COMMIT", "0" * 40)
    with pytest.raises(RuntimeError, match="failed"):
        t2.fetch(tmp_path / "clone")


def test_fetch_reports_a_head_that_stays_wrong(
    upstream: tuple[Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    t2.fetch(tmp_path / "clone")
    monkeypatch.setattr(t2, "_git", lambda *a, **k: subprocess.CompletedProcess(a, 0, "abc\n", ""))
    with pytest.raises(RuntimeError, match="HEAD is abc"):
        t2.fetch(tmp_path / "clone")


def test_venv_commands_install_locked_dependencies_only() -> None:
    cmds = t2.venv_commands(Path("src"), Path("venv"), "/usr/bin/python3.12")
    assert cmds[0] == ["uv", "venv", "--python", "/usr/bin/python3.12", "venv"]
    assert cmds[1][:2] == ["uv", "sync"] and "--no-install-project" in cmds[1]
    assert {"--frozen", "--no-dev", "--compile-bytecode"} <= set(cmds[1])
    assert cmds[2] == ["venv/bin/python", "-I", "-m", "compileall", "-q", "src/src"]


def test_build_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[list[str], str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append((cmd, kwargs["env"]["UV_PROJECT_ENVIRONMENT"]))
        failing = cmd[0] == "uv" and cmd[1] == "sync" and os.environ.get("GP_TEST_FAIL")
        return subprocess.CompletedProcess(cmd, 1 if failing else 0, "", "no network")

    monkeypatch.setattr(subprocess, "run", fake_run)
    venv = tmp_path / "venv"
    assert t2.build_venv(tmp_path, venv, "/usr/bin/python3.12") == venv / "bin" / "python"
    assert [c[:2] for c, _ in seen] == [
        ["uv", "venv"],
        ["uv", "sync"],
        [str(venv / "bin/python"), "-I"],
    ]
    assert {e for _, e in seen} == {str(venv.absolute())}
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("")
    seen.clear()
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)
    t2.build_venv(tmp_path, venv)
    assert seen[0][0][:2] == ["uv", "sync"]  # an existing venv is reused
    monkeypatch.setenv("GP_TEST_FAIL", "1")
    with pytest.raises(RuntimeError, match="uv sync failed: no network"):
        t2.build_venv(tmp_path, venv)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="not found"):
        t2.build_venv(tmp_path, tmp_path / "other")


# --------------------------------------------------------------------- command line


def test_main_convert_fetch_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert t2.main(["convert", str(SRC), str(tmp_path / "out")]) == 1
    assert "files differ" in capsys.readouterr().err
    monkeypatch.setattr(t2, "verify_source", lambda root: None)
    assert t2.main(["convert", str(SRC), str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "converted 3 tau2 tasks" in out
    assert "airline 1 of 1, retail 1 of 2 (1 need an LLM judge), telecom 1 of 1" in out
    monkeypatch.setattr(t2, "fetch", lambda dest: dest)
    assert t2.main(["fetch", str(tmp_path / "x")]) == 0
    monkeypatch.setattr(t2, "build_venv", lambda src, venv, python: venv / "bin/python")
    assert t2.main(["venv", str(SRC), str(tmp_path / "v"), "--python", "/usr/bin/python3"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        str(tmp_path / "x"),
        str(tmp_path / "v/bin/python"),
    ]


def test_main_check(
    converted: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = ["check", str(converted), "--root", str(tmp_path), "--python", "/p", "--crosscheck"]
    monkeypatch.setattr(t2, "best_sandbox", lambda: None)
    assert t2.main(args) == 1
    assert "no write-isolating sandbox" in capsys.readouterr().err
    passing = (0, json.dumps({"reward": 1.0, "passed": True, "crosscheck_reward": 1.0}), "")
    sandbox = ScriptedSandbox({"7": passing, "69": passing, TELECOM_ID: passing})
    monkeypatch.setattr(t2, "best_sandbox", lambda: sandbox)
    assert t2.main(args) == 1
    assert "is at None, not" in capsys.readouterr().err
    monkeypatch.setattr(t2, "source_commit", lambda root: t2.PINNED_COMMIT)
    monkeypatch.setattr(t2, "verify_source", lambda root: None)
    report = tmp_path / "check" / "result.json"
    assert t2.main([*args, "--json", str(report), "--jobs", "2"]) == 0
    out = capsys.readouterr().out
    assert "airline-7 stable_pass reward=1.0 crosscheck=1.0" in out
    assert "telecom: 1 tasks, 1 at reward 1.0; others: none" in out
    assert "crosscheck mismatches: none" in out
    data = json.loads(report.read_text())
    assert data["summary"]["retail"] == {"tasks": 1, "reward_1": 1, "failures": []}
    assert [c["task_id"] for c in data["checks"]] == ["airline-7", "retail-69", TELECOM]
    sandbox.grades = {**sandbox.grades, "69": (1, json.dumps({"reward": 0.0, "passed": False}), "")}
    assert t2.main(args[:6]) == 1
    assert "retail: 1 tasks, 0 at reward 1.0; others: retail-69" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        t2.main([*args, "--repeat", "0"])


def test_module_runs_as_a_program(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "graderproof.adapters.tau2", "convert", str(SRC), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1 and "files differ from v1.0.1" in proc.stderr


# ------------------------------------------------------------- driver: pure helpers


def test_driver_parse_calls() -> None:
    calls = drv.parse_calls(
        [{"tool": "a"}, {"tool": "b", "args": None, "requestor": "user", "note": 1}]
    )
    assert calls == [
        {"tool": "a", "args": {}, "requestor": "assistant"},
        {"tool": "b", "args": {}, "requestor": "user", "note": 1},
    ]
    for bad, message in (
        ({}, "JSON list"),
        ([1], "not a JSON object"),
        ([{"tool": ""}], "non-empty string"),
        ([{"tool": "a", "args": [1]}], "args must be"),
        ([{"tool": "a", "requestor": "system"}], "requestor must be"),
    ):
        with pytest.raises(ValueError, match=message):
            drv.parse_calls(bad)


def test_driver_changes_are_sparse_to_the_record_level() -> None:
    before = {"orders": {"A": {"s": 1, "t": [1]}, "B": {"s": 1}, "C": {}}, "lines": [1, 2], "x": 1}
    after = {
        "orders": {"A": {"s": 2, "t": [1]}, "B": {"s": 1}, "D": {"s": 0}},
        "lines": [1, 3],
        "x": 1,
    }
    assert drv.changes(before, after) == {
        "orders": {"A": {"s": 2, "t": [1]}, "D": {"s": 0}, "C": None},
        "lines": [1, 3],
    }
    assert drv.changes(before, before) == {}
    assert drv.changes(1, 2) == 2
    assert drv.changes({"a": {"b": 1}}, {"a": {"b": 2}}, depth=1) == {"a": {"b": 2}}


def test_driver_small_helpers(tmp_path: Path) -> None:
    assert drv.parsed('{"a": 1}') == {"a": 1}
    assert drv.parsed("Error: no") == "Error: no"
    assert drv.parsed(None) is None
    env = drv.offline_environment(Path("/r"))
    assert env == {
        "TAU2_DATA_DIR": "/r/data",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "PYTHON_DOTENV_DISABLED": "1",
    }
    original = uuid.uuid4
    with drv.seeded_uuid4():
        first = [uuid.uuid4() for _ in range(3)]
    with drv.seeded_uuid4():
        second = [uuid.uuid4() for _ in range(3)]
    assert first == second and len(set(first)) == 3 and first[0].version == 4
    assert uuid.uuid4 is original
    assert drv.db_dump(None) is None
    assert drv.db_dump(SimpleNamespace(db=None)) is None
    (tmp_path / "trajectory.json").write_text('[{"tool": "a"}]')
    assert drv.read_solution(tmp_path) == (
        [{"tool": "a", "args": {}, "requestor": "assistant"}],
        [],
    )
    (tmp_path / "final_message.txt").write_text("Bye.")
    assert drv.read_solution(tmp_path)[1] == ["Bye."]


def test_driver_parser() -> None:
    args = drv.parser().parse_args(
        ["grade", "--root", "/r", "--domain", "airline", "--task", "t.json", "--simulation", "s"]
    )
    assert (args.command, args.root, args.lenient, args.crosscheck) == (
        "grade",
        Path("/r"),
        False,
        False,
    )
    replay = ["replay", "--root", "/r", "--domain", "d", "--task", "t", "--calls", "c"]
    args = drv.parser().parse_args(
        [*replay, "--out", "o", "--text", "a", "--text", "b", "--lenient"]
    )
    assert (args.text, args.lenient) == (["a", "b"], True)
    with pytest.raises(SystemExit):
        drv.parser().parse_args(["policy", "--root", "/r"])


def test_driver_main_reports_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(root: Path) -> SimpleNamespace:
        raise ModuleNotFoundError("No module named 'loguru'")

    monkeypatch.setattr(drv, "load_tau2", broken)
    common = ["--root", str(tmp_path), "--domain", "airline", "--task", str(tmp_path / "t.json")]
    assert drv.main(["grade", *common, "--simulation", "simulation.json"]) == drv.EXIT_ERROR
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "error": "ModuleNotFoundError: No module named 'loguru'",
        "passed": False,
    }
    (tmp_path / "trajectory.json").write_text('{"not": "a list"}')
    assert drv.main(["simulate", *common, "--solution", str(tmp_path), "--out", "."]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "the trajectory must be a JSON list" in captured.err


# ---------------------------------------------------------- driver: fake tau2 API


def plain(value: Any) -> Any:
    """JSON values from fake model objects, enums, and containers."""
    if isinstance(value, Obj):
        return value.model_dump()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {plain(k): plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


class Obj:
    """Stand-in for a tau2 pydantic model: keyword fields, copies, and dumps."""

    def __init__(self, **fields: Any) -> None:
        self.__dict__.update(fields)

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)

    def model_copy(self, update: Mapping[str, Any]) -> Obj:
        return type(self)(**{**self.__dict__, **update})

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        out: dict[str, Any] = plain(dict(self.__dict__))
        return out

    def model_dump_json(self, exclude_none: bool = False, indent: int | None = None) -> str:
        data = self.model_dump()
        return json.dumps(
            {k: v for k, v in data.items() if v is not None or not exclude_none}, indent=indent
        )


class Reward(Enum):
    DB = "DB"
    ENV_ASSERTION = "ENV_ASSERTION"
    ACTION = "ACTION"
    COMMUNICATE = "COMMUNICATE"
    NL_ASSERTION = "NL_ASSERTION"
    OTHER = "OTHER"


class Stop(Enum):
    USER_STOP = "user_stop"
    AGENT_STOP = "agent_stop"
    MAX_STEPS = "max_steps"


class SimRun(Obj):
    """Fake SimulationRun with tau2's JSON loading."""

    @classmethod
    def model_validate_json(cls, text: str) -> SimRun:
        data = json.loads(text)
        data["termination_reason"] = Stop(data["termination_reason"])
        data["messages"] = [Obj(**m) for m in data["messages"]]
        return cls(**data)


class FakeTask:
    """Fake Task with tau2's dict loading."""

    @staticmethod
    def model_validate(data: Mapping[str, Any]) -> Obj:
        crit = data.get("evaluation_criteria")
        if crit is not None:
            crit = Obj(
                reward_basis=[Reward(b) for b in crit.get("reward_basis", ["DB", "COMMUNICATE"])],
                nl_assertions=crit.get("nl_assertions"),
            )
        init = data.get("initial_state")
        if init is not None:
            init = Obj(
                **{
                    k: init.get(k)
                    for k in ("initialization_data", "initialization_actions", "message_history")
                }
            )
        return Obj(id=data["id"], initial_state=init, evaluation_criteria=crit)


class FakeDB:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return copy.deepcopy(self.data)


class FakeEnv:
    """A shop: ``cancel`` (assistant) closes an order, ``toggle`` (user) flips a phone flag,
    ``new_id`` returns a uuid4; anything else is an unknown tool."""

    instances: ClassVar[list[FakeEnv]] = []

    def __init__(self, solo_mode: bool = False, user: bool = True) -> None:
        self.tools: Any = SimpleNamespace(db=FakeDB({"orders": {"A": {"status": "open"}}}))
        self.user_tools: Any = None
        if user:
            self.user_tools = SimpleNamespace(db=FakeDB({"phone": {"airplane": True}}))
        self.state_args: dict[str, Any] = {}
        FakeEnv.instances.append(self)

    def set_state(self, **kwargs: Any) -> None:
        self.state_args = kwargs

    def get_response(self, tc: Obj) -> Obj:
        error, content = False, json.dumps({"ok": True})
        if tc.name == "cancel" and tc.requestor == "assistant":
            self.tools.db.data["orders"][tc.arguments["order"]]["status"] = "cancelled"
        elif tc.name == "toggle" and tc.requestor == "user" and self.user_tools is not None:
            self.user_tools.db.data["phone"]["airplane"] = False
        elif tc.name == "new_id":
            content = str(uuid.uuid4())
        else:
            error, content = True, f"Error: Tool '{tc.name}' not found."
        return Obj(
            id=tc.id,
            role="tool",
            content=content,
            requestor=tc.requestor,
            error=error,
            turn_idx=None,
            timestamp="now",
        )

    def get_db_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.tools.db.data).encode()).hexdigest()

    def get_user_db_hash(self) -> str | None:
        if self.user_tools is None:
            return None
        return hashlib.sha256(canonical_json(self.user_tools.db.data).encode()).hexdigest()

    def get_policy(self) -> str:
        return "Be kind.\n"


def fake_tau2(
    rewards: Mapping[str, float], seen: list[tuple[str, dict[str, Any]]]
) -> SimpleNamespace:
    """A namespace shaped like load_tau2's: evaluators return the given component rewards."""

    def evaluator(part: str, keys: Sequence[Reward]) -> Any:
        def calculate_reward(**kwargs: Any) -> Obj:
            seen.append((part, kwargs))
            r = rewards[part]
            return Obj(
                reward=r,
                reward_breakdown={k: r for k in keys}
                if part != "env"
                else {Reward.DB: r, Reward.ENV_ASSERTION: 1.0},
                db_check={"db_match": r == 1.0},
                env_assertions=[],
                action_checks=[],
                communicate_checks=[],
                nl_assertions=[],
                info={"part": part},
            )

        return SimpleNamespace(calculate_reward=calculate_reward)

    def tool_types(kit: Any) -> dict[str, str]:
        if kit.db.data.get("broken"):
            raise ValueError("no types")
        return {"cancel": "write"} if "orders" in kit.db.data else {"toggle": "write"}

    def evaluate_simulation(**kwargs: Any) -> Obj:
        seen.append(("crosscheck", kwargs))
        return Obj(reward=0.5)

    registry = SimpleNamespace(get_env_constructor=lambda domain: FakeEnv)
    return SimpleNamespace(
        message=SimpleNamespace(ToolCall=Obj, AssistantMessage=Obj, UserMessage=Obj),
        simulation=SimpleNamespace(SimulationRun=SimRun, TerminationReason=Stop, RewardInfo=Obj),
        tasks=SimpleNamespace(Task=FakeTask, RewardType=Reward),
        toolkit=SimpleNamespace(get_tool_types=tool_types),
        registry=SimpleNamespace(registry=registry),
        env_eval=SimpleNamespace(EnvironmentEvaluator=evaluator("env", [Reward.DB])),
        action_eval=SimpleNamespace(ActionEvaluator=evaluator("action", [Reward.ACTION])),
        comm_eval=SimpleNamespace(CommunicateEvaluator=evaluator("comm", [Reward.COMMUNICATE])),
        nl_eval=SimpleNamespace(NLAssertionsEvaluator=evaluator("nl", [Reward.NL_ASSERTION])),
        evaluator=SimpleNamespace(
            evaluate_simulation=evaluate_simulation, EvaluationType=SimpleNamespace(ALL="all")
        ),
    )


ALL_ONE = {"env": 1.0, "action": 1.0, "comm": 1.0, "nl": 1.0}


def shop_task(basis: Sequence[str] | None = ("DB", "COMMUNICATE"), nl: Sequence[str] = ()) -> Obj:
    data: dict[str, Any] = {"id": "shop-1", "initial_state": {"initialization_actions": [{"f": 1}]}}
    data["evaluation_criteria"] = (
        None if basis is None else {"reward_basis": list(basis), "nl_assertions": list(nl)}
    )
    return FakeTask.model_validate(data)


def test_driver_simulate_builds_messages_state_and_log() -> None:
    t = fake_tau2(ALL_ONE, [])
    calls = drv.parse_calls(
        [
            {"tool": "cancel", "args": {"order": "A"}, "id": "kept"},
            {"tool": "toggle", "requestor": "user"},
            {"tool": "new_id"},
            {"tool": "nope"},
        ]
    )
    sim, state, log = drv.simulate(t, shop_task(), calls, "shop", ["  ", "Done."])
    env = FakeEnv.instances[-1]
    assert env.state_args == {
        "initialization_data": None,
        "initialization_actions": [{"f": 1}],
        "message_history": [],
    }
    roles = [(m.role, getattr(m, "tool_calls", None) is not None) for m in sim.messages]
    calls_then_text = [("assistant", True), ("tool", False), ("user", True), ("tool", False)]
    calls_then_text += [("assistant", True), ("tool", False)] * 2 + [("assistant", False)]
    assert roles == calls_then_text
    assert [m.turn_idx for m in sim.messages] == list(range(9))
    assert {m.timestamp for m in sim.messages} == {drv.TIMESTAMP}
    assert sim.messages[0].tool_calls[0].model_dump() == {
        "id": "call_0",
        "name": "cancel",
        "arguments": {"order": "A"},
        "requestor": "assistant",
    }
    assert sim.messages[-1].content == "Done."
    assert (sim.termination_reason, sim.task_id, sim.duration) == (Stop.AGENT_STOP, "shop-1", 0.0)
    assert log[0] == {
        "tool": "cancel",
        "args": {"order": "A"},
        "requestor": "assistant",
        "id": "kept",
        "result": {"ok": True},
    }
    assert log[3]["error"] == "Error: Tool 'nope' not found." and "result" not in log[3]
    with drv.seeded_uuid4():
        assert log[2]["result"] == str(uuid.uuid4())  # the same seeded sequence
    assert state == {
        "db": {"hash": env.get_db_hash(), "changed": {"orders": {"A": {"status": "cancelled"}}}},
        "user_db": {"hash": env.get_user_db_hash(), "changed": {"phone": {"airplane": False}}},
    }
    t.registry.registry.get_env_constructor = lambda domain: lambda: FakeEnv(user=False)
    task = FakeTask.model_validate({"id": "x", "initial_state": None, "evaluation_criteria": None})
    _, state, _ = drv.simulate(t, task, [], "shop")
    assert state["user_db"] is None and state["db"]["changed"] == {}
    assert FakeEnv.instances[-1].state_args["initialization_actions"] is None


def _evaluate(
    rewards: Mapping[str, float], task: Obj, stop: Stop = Stop.USER_STOP, strict: bool = True
) -> tuple[Any, list[tuple[str, dict[str, Any]]]]:
    seen: list[tuple[str, dict[str, Any]]] = []
    t = fake_tau2(rewards, seen)
    sim = SimRun(termination_reason=stop, messages=["m"])
    return drv.evaluate(t, sim, task, "shop", strict), seen


def test_driver_evaluate_multiplies_the_basis_in_v101_order() -> None:
    info, seen = _evaluate({**ALL_ONE, "comm": 0.0}, shop_task())
    assert info.reward == 0.0
    assert [p for p, _ in seen] == ["env", "action", "comm"]  # no NL evaluator off the basis
    assert info.reward_breakdown == {
        Reward.DB: 1.0,
        Reward.ENV_ASSERTION: 1.0,
        Reward.COMMUNICATE: 0.0,
    }
    assert info.reward_basis == [Reward.DB, Reward.COMMUNICATE]
    assert info.info == {
        "env": {"part": "env"},
        "nl": None,
        "communicate": {"part": "comm"},
        "action": {"part": "action"},
    }
    env_kwargs = seen[0][1]
    assert (env_kwargs["solo_mode"], env_kwargs["env_kwargs"], env_kwargs["strict_replay"]) == (
        False,
        {},
        True,
    )
    assert env_kwargs["full_trajectory"] == ["m"]
    assert seen[1][1]["tool_types"] == {"cancel": "write", "toggle": "write"}
    info, seen = _evaluate({**ALL_ONE, "action": 0.0}, shop_task(["ENV_ASSERTION"]), strict=False)
    assert info.reward == 1.0 and seen[0][1]["strict_replay"] is False  # action is off the basis
    info, seen = _evaluate({**ALL_ONE, "nl": 0.5}, shop_task(["DB", "NL_ASSERTION"]))
    assert info.reward == 0.5 and [p for p, _ in seen] == ["env", "action", "comm", "nl"]
    assert info.nl_assertions == [] and info.info["nl"] == {"part": "nl"}


def test_driver_evaluate_early_exits_and_refusals() -> None:
    info, seen = _evaluate(ALL_ONE, shop_task(), stop=Stop.MAX_STEPS)
    assert (info.reward, info.reward_basis, seen) == (0.0, None, [])
    assert info.info == {"note": "Simulation terminated prematurely. Termination reason: max_steps"}
    info, seen = _evaluate(ALL_ONE, shop_task(None), stop=Stop.AGENT_STOP)
    assert (info.reward, info.info, seen) == (1.0, {"note": "No evaluation criteria"}, [])
    with pytest.raises(drv.NeedsJudgeError, match="LLM judge"):
        _evaluate(ALL_ONE, shop_task(["DB", "NL_ASSERTION"], nl=["Agent is polite."]))
    with pytest.raises(ValueError, match="not evaluated"):
        _evaluate(ALL_ONE, shop_task(["DB", "OTHER"]))


def test_driver_tool_types_follows_v101() -> None:
    t = fake_tau2(ALL_ONE, [])
    assert drv.tool_types(t, lambda solo_mode: FakeEnv(user=False)) == {"cancel": "write"}

    def only_user(solo_mode: bool) -> FakeEnv:
        env = FakeEnv()
        env.tools = None  # an environment without agent tools
        return env

    assert drv.tool_types(t, only_user) == {"toggle": "write"}

    def broken_user(solo_mode: bool) -> FakeEnv:
        env = FakeEnv()
        env.user_tools = SimpleNamespace(db=FakeDB({"broken": True}))
        return env

    assert drv.tool_types(t, broken_user) == {"cancel": "write"}  # kept from before the error

    def failing(solo_mode: bool) -> FakeEnv:
        raise ValueError("no env")

    assert drv.tool_types(t, failing) is None


def test_driver_replay_and_reward_summary() -> None:
    t = fake_tau2(ALL_ONE, [])
    sim, state, info = drv.replay(
        t,
        shop_task(),
        [{"tool": "cancel", "args": {"order": "A"}, "requestor": "assistant"}],
        "shop",
    )
    assert info.reward == 1.0 and state["db"]["changed"]
    summary = drv.reward_summary(info, "shop-1", "shop")
    assert {k: summary[k] for k in ("task_id", "domain", "reward", "passed")} == {
        "task_id": "shop-1",
        "domain": "shop",
        "reward": 1.0,
        "passed": True,
    }
    assert summary["reward_info"]["reward_breakdown"] == {
        "DB": 1.0,
        "ENV_ASSERTION": 1.0,
        "COMMUNICATE": 1.0,
    }
    assert json.loads(drv.simulation_json(sim))["task_id"] == "shop-1"


@pytest.fixture
def faked(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Make the driver's commands use the fake tau2 API."""
    seen: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(drv, "load_tau2", lambda root: fake_tau2(ALL_ONE, seen))
    return seen


def test_driver_commands_with_the_fake_api(
    tmp_path: Path, faked: list[tuple[str, dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"id": "shop-1", "evaluation_criteria": {"reward_basis": ["DB"]}}))
    sol = tmp_path / "solution"
    sol.mkdir()
    (sol / "trajectory.json").write_text(json.dumps([{"tool": "cancel", "args": {"order": "A"}}]))
    (sol / "final_message.txt").write_text("Done.")
    out = tmp_path / "ws"
    common = ["--root", str(tmp_path), "--domain", "shop", "--task", str(task)]
    assert drv.main(["simulate", *common, "--solution", str(sol), "--out", str(out)]) == 0
    sim = json.loads((out / "simulation.json").read_text())
    assert sim["messages"][-1]["content"] == "Done."
    assert json.loads((out / ".gp/trajectory.json").read_text())[0]["result"] == {"ok": True}
    assert json.loads((out / ".gp/state.json").read_text())["db"]["changed"]
    sim_path = str(out / "simulation.json")
    assert drv.main(["grade", *common, "--simulation", sim_path, "--crosscheck", "--lenient"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["reward"], report["passed"], report["crosscheck_reward"]) == (1.0, True, 0.5)
    cross = dict(faked)["crosscheck"]
    assert (cross["evaluation_type"], cross["solo_mode"], cross["strict_replay"]) == (
        "all",
        False,
        False,
    )
    sim["termination_reason"] = "max_steps"
    (out / "simulation.json").write_text(json.dumps(sim))
    assert drv.main(["grade", *common, "--simulation", sim_path]) == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False
    text = tmp_path / "text.txt"
    text.write_text("Bye.")
    result = tmp_path / "replay.json"
    calls = str(sol / "trajectory.json")
    assert (
        drv.main(["replay", *common, "--calls", calls, "--text", str(text), "--out", str(result)])
        == 0
    )
    replayed = json.loads(result.read_text())
    assert set(replayed) == {"simulation", "state", "reward"}
    assert (
        replayed["reward"]["passed"] is True
        and replayed["simulation"]["messages"][-1]["content"] == "Bye."
    )
    assert drv.main(["policy", "--root", str(tmp_path), "--domain", "shop"]) == 0
    assert capsys.readouterr().out == "Be kind.\n"


def test_driver_load_tau2_imports_only_from_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src"
    for module in drv.MODULES.values():
        parts = module.split(".")
        for i in range(1, len(parts)):
            package = src.joinpath(*parts[:i])
            package.mkdir(parents=True, exist_ok=True)
            (package / "__init__.py").touch()
        src.joinpath(*parts[:-1], parts[-1] + ".py").touch()
    (src / "loguru.py").write_text(
        "class _Logger:\n"
        "    def __init__(self):\n        self.sinks = ['default']\n"
        "    def remove(self):\n        self.sinks = []\n"
        "    def add(self, sink, level, format):\n        self.sinks.append(level)\n"
        "logger = _Logger()\n"
    )
    for key in drv.offline_environment(tmp_path):
        monkeypatch.setenv(key, "before")
    monkeypatch.setattr(sys, "path", list(sys.path))
    before = set(sys.modules)
    try:
        t = drv.load_tau2(tmp_path)
        assert set(vars(t)) == set(drv.MODULES)
        assert Path(t.message.__file__).resolve() == (src / "tau2/data_model/message.py").resolve()
        assert sys.modules["loguru"].logger.sinks == ["WARNING"]
        assert os.environ["TAU2_DATA_DIR"] == str(tmp_path / "data")
        assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
        with pytest.raises(RuntimeError, match="was imported from"):
            drv.load_tau2(tmp_path / "elsewhere")
    finally:
        for name in set(sys.modules) - before:
            del sys.modules[name]


# ------------------------------------------------------------------------- live


def _live_env(crosscheck: bool = True) -> dict[str, str]:
    assert LIVE_ROOT and LIVE_PYTHON
    return t2.tau2_env(Path(LIVE_ROOT), Path(LIVE_PYTHON), crosscheck)


@pytest.fixture
def live_runs(tasks: dict[str, Task]) -> Iterator[dict[str, list[dict[str, Any]]]]:
    """Each fixture task's reference and one dropped mutating call, run for real."""
    adapter = ToybenchAdapter(extra_env=_live_env())
    runner = Runner(adapter, BwrapSandbox())
    out: dict[str, list[dict[str, Any]]] = {}
    for name in NAMES:
        task = tasks[name]
        variants = [("reference", dict(task.reference_solution))]
        if name in DROPPED:
            calls = json.loads(task.reference_solution["trajectory.json"])
            del calls[DROPPED[name]]
            dropped = {
                **task.reference_solution,
                "trajectory.json": json.dumps(calls, indent=2) + "\n",
            }
            variants.append((f"dropped call {DROPPED[name]}", dropped))
        out[name] = [
            {
                "label": label,
                "solution": solution,
                "execution": runner.execute(task, solution).to_dict(),
            }
            for label, solution in variants
        ]
    if os.environ.get("GP_TAU2_RECORD") == "1":
        RECORDED.mkdir(exist_ok=True)
        for name, runs in out.items():
            data = {
                "task": name,
                "source_commit": t2.PINNED_COMMIT,
                "driver_sha256": t2.sha256_file(Path(drv.__file__)),
                "runs": runs,
            }
            (RECORDED / f"{name}.json").write_text(
                json.dumps(data, indent=1, sort_keys=True) + "\n"
            )
    yield out


@live
def test_live_references_pass_and_dropped_calls_fail(
    live_runs: dict[str, list[dict[str, Any]]],
) -> None:
    for name, runs in live_runs.items():
        for run in runs:
            grade = Execution.from_dict(run["execution"]).grade
            report = t2.grade_report(grade.stdout)
            want = 1.0 if run["label"] == "reference" else 0.0
            assert (report["reward"], report["crosscheck_reward"], grade.passed) == (
                want,
                want,
                want == 1.0,
            ), (name, run["label"], grade.stderr[-2000:])
    airline = Execution.from_dict(live_runs["airline-7"][1]["execution"]).grade
    assert t2.grade_report(airline.stdout)["reward_info"]["reward_breakdown"] == {
        "DB": 0.0,
        "COMMUNICATE": 1.0,
    }


@live
def test_live_runs_are_repeatable(tasks: dict[str, Task]) -> None:
    adapter = ToybenchAdapter(extra_env=_live_env(crosscheck=False))
    task = tasks[TELECOM]
    first, second = (
        adapter.execute(task, task.reference_solution, BwrapSandbox()) for _ in range(2)
    )
    assert first.outcome.to_dict() == second.outcome.to_dict()
    assert first.grade.stdout == second.grade.stdout


@live
@pytest.mark.parametrize("domain", t2.DOMAINS)
def test_live_policy_matches_the_instruction(domain: str, tmp_path: Path) -> None:
    assert LIVE_ROOT and LIVE_PYTHON
    cmd = [LIVE_PYTHON, "-I", drv.__file__, "policy", "--root", LIVE_ROOT, "--domain", domain]
    res = BwrapSandbox().run(cmd, cwd=tmp_path, writable=[tmp_path], limits=Limits(timeout_s=120))
    assert res.exit_status == 0, res.stderr[-2000:]
    assert res.stdout == t2.domain_policy(SRC, domain)


@live
def test_live_replay_command(tmp_path: Path) -> None:
    assert LIVE_ROOT and LIVE_PYTHON
    (tmp_path / "task.json").write_text(json.dumps(AIRLINE))
    (tmp_path / "calls.json").write_text(json.dumps(t2.reference_calls(AIRLINE)))
    (tmp_path / "text.txt").write_text(t2.final_message(AIRLINE))
    cmd = [LIVE_PYTHON, "-I", drv.__file__, "replay", "--root", LIVE_ROOT, "--domain", "airline"]
    cmd += [
        "--task",
        "task.json",
        "--calls",
        "calls.json",
        "--text",
        "text.txt",
        "--out",
        "out.json",
    ]
    res = BwrapSandbox().run(cmd, cwd=tmp_path, writable=[tmp_path], limits=Limits(timeout_s=120))
    assert res.exit_status == 0, res.stderr[-2000:]
    result = json.loads((tmp_path / "out.json").read_text())
    assert result["reward"]["reward"] == 1.0
    assert result["state"]["db"]["changed"]["reservations"]["XEHM4B"]["status"] == "cancelled"
