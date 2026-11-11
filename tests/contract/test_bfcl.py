"""Contract tests for the BFCL adapter (graderproof.adapters.bfcl and bfcl_driver).

Offline tests use five verbatim BFCL records (tests/fixtures/bfcl/, Apache-2.0, see
docs/adapters/bfcl.md) and verdicts that BFCL's real ``ast_checker`` gave on them
(tests/fixtures/bfcl/verdicts.json). A stand-in ``bfcl_eval`` package written by these
tests replays those verdicts, so the conversion, the grader scripts, and the driver run
end to end without third-party code. The live tests re-derive the recorded verdicts
with the real checker under bubblewrap; they run only when ``GP_BFCL_ROOT`` names the
pinned checkout's ``berkeley-function-call-leaderboard`` directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from graderproof.adapters import bfcl, bfcl_driver
from graderproof.adapters.bfcl import (
    BFCL_DIR,
    CATEGORIES,
    CHECKER_MODEL,
    DATA_DIR,
    PINNED_COMMIT,
    PYTHON_HINT,
    ReferenceCheck,
    bfcl_root,
    check_references,
    convert,
    data_paths,
    fetch,
    grader_data,
    instruction,
    main,
    read_records,
    reference_args,
    reference_calls,
    reference_value,
    summarize,
    task_files,
    task_toml,
    verify_checkout,
    with_python_hint,
)
from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.core import Determinism, Task
from graderproof.run import SandboxPolicyError
from graderproof.sandbox import BwrapSandbox, LocalSandbox, bwrap_works

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "bfcl"
FIXTURE_CATEGORIES = (
    "simple_python",
    "parallel",
    "parallel_multiple",
    "live_simple",
    "live_multiple",
)
RECORDING = json.loads((FIXTURES / "verdicts.json").read_text(encoding="utf-8"))
CASES: list[dict[str, Any]] = RECORDING["cases"]
LIVE_ROOT = os.environ.get("GP_BFCL_ROOT", "")

# A sandbox double for the stand-in checker, which is this file's own code. Third-party
# tasks need a write-isolating sandbox (Runner.check_policy), so it claims isolation.
TRUSTED_LOCAL = LocalSandbox(name="local-test", isolates_writes=True)

ENUMS = "from enum import Enum\n\n\nclass Language(Enum):\n    PYTHON = 'python'\n"
MODEL_CONFIG = """\
from dataclasses import dataclass

from bfcl_eval.model_handler.api_inference.gorilla import GorillaHandler


@dataclass
class ModelConfig:
    model_handler: object
    underscore_to_dot: bool = False


MODEL_CONFIG_MAPPING = {"gorilla-openfunctions-v2": ModelConfig(GorillaHandler)}
"""
REPLAY_CHECKER = """\
import hashlib
import json
from pathlib import Path

from bfcl_eval.constants.enums import Language
from bfcl_eval.constants.model_config import MODEL_CONFIG_MAPPING

RECORDED = json.loads((Path(__file__).parent / "recorded.json").read_text())


def ast_checker(func_description, model_output, possible_answer, language, test_category,
                model_name):
    if language is not Language.PYTHON:
        raise TypeError("language must be Language.PYTHON")
    MODEL_CONFIG_MAPPING[model_name.replace("_", "/")]
    key = json.dumps([func_description, model_output, possible_answer, test_category,
                      model_name], sort_keys=True)
    return RECORDED[hashlib.sha256(key.encode()).hexdigest()]
"""


def fixture_records() -> dict[str, tuple[dict[str, Any], dict[str, Any], str]]:
    """Fixture records by id: question entry, possible-answer entry, category."""
    out = {}
    for category in FIXTURE_CATEGORIES:
        for q, a in read_records(FIXTURES, category):
            out[str(q["id"])] = (q, a, category)
    return out


def replay_key(
    question: Mapping[str, Any],
    answer: Mapping[str, Any],
    category: str,
    calls: Sequence[Mapping[str, Any]],
) -> str:
    """The stand-in checker's key for the inputs BFCL's checker would receive."""
    decoded = [{c["tool"]: c.get("args") or {}} for c in calls]
    key = [question["function"], decoded, answer["ground_truth"], category, CHECKER_MODEL]
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()


def recorded_verdicts() -> dict[str, dict[str, Any]]:
    records = fixture_records()
    out = {}
    for case in CASES:
        q, a, category = records[case["id"]]
        verdict = {"valid": case["valid"], "error": [], "error_type": case["error_type"]}
        out[replay_key(q, a, category, case["trajectory"])] = verdict
    return out


def fake_root(base: Path, checker: str = REPLAY_CHECKER) -> Path:
    """A stand-in BFCL directory whose ``ast_checker`` replays the recorded verdicts."""
    root = base / BFCL_DIR
    files = {
        "bfcl_eval/__init__.py": "",
        "bfcl_eval/constants/__init__.py": "",
        "bfcl_eval/constants/enums.py": ENUMS,
        "bfcl_eval/constants/model_config.py": MODEL_CONFIG,
        "bfcl_eval/model_handler/__init__.py": "raise ImportError('handlers are not needed')\n",
        "bfcl_eval/eval_checker/__init__.py": "",
        "bfcl_eval/eval_checker/ast_eval/__init__.py": "",
        "bfcl_eval/eval_checker/ast_eval/ast_checker.py": checker,
        "bfcl_eval/eval_checker/ast_eval/recorded.json": json.dumps(recorded_verdicts()),
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def converted(out: Path) -> dict[str, Task]:
    convert(FIXTURES, out, FIXTURE_CATEGORIES)
    return {t.id: t for t in ToybenchAdapter().load(out)}


def trajectory_text(calls: Any) -> dict[str, str]:
    return {"trajectory.json": json.dumps(calls, indent=2) + "\n"}


@pytest.fixture
def clean_imports(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Undo the driver's in-process import changes (sys.path, sys.meta_path, modules)."""

    def drop() -> None:
        for name in [m for m in sys.modules if m.split(".")[0] == "bfcl_eval"]:
            del sys.modules[name]

    drop()
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    monkeypatch.setattr(sys, "dont_write_bytecode", sys.dont_write_bytecode)
    yield
    drop()


# ------------------------------------------------------------------ fetch and records


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    proc = subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    )
    return proc.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_fetch_and_verify_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    src = tmp_path / "gorilla"
    data = src / BFCL_DIR / DATA_DIR
    data.mkdir(parents=True)
    (data / "BFCL_v4_simple_python.json").write_text("{}\n")
    (src / "LICENSE").write_text("license\n")
    (src / "other").mkdir()
    (src / "other" / "big.txt").write_text("outside the sparse checkout\n")
    _git(src, "init", "-q")
    _git(src, "config", "uploadpack.allowFilter", "true")
    _git(src, "config", "uploadpack.allowAnySHA1InWant", "true")
    first = _commit(src, "first")
    shutil.rmtree(src / BFCL_DIR)
    second = _commit(src, "second, without BFCL data")
    url = src.as_uri()

    dest = tmp_path / "dest"
    root = fetch(dest, commit=first, url=url)
    assert root == dest / BFCL_DIR
    assert (root / DATA_DIR / "BFCL_v4_simple_python.json").is_file()
    assert (dest / "LICENSE").is_file() and not (dest / "other").exists()
    assert fetch(dest, commit=first, url=url) == root
    assert verify_checkout(dest, first) == root
    with pytest.raises(RuntimeError, match="expected"):
        verify_checkout(dest, second)
    with pytest.raises(RuntimeError, match="has no"):
        fetch(dest, commit=second, url=url)
    with pytest.raises(RuntimeError, match="failed"):
        fetch(tmp_path / "missing", commit="0" * 40, url=url)
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "file").write_text("x")
    with pytest.raises(FileExistsError):
        fetch(busy, commit=first, url=url)


def test_paths_and_records() -> None:
    assert bfcl_root(FIXTURES) == FIXTURES / BFCL_DIR
    assert bfcl_root(FIXTURES / BFCL_DIR) == FIXTURES / BFCL_DIR
    q_rel, a_rel = data_paths("live_simple")
    assert q_rel.as_posix() == "bfcl_eval/data/BFCL_v4_live_simple.json"
    assert a_rel.as_posix() == "bfcl_eval/data/possible_answer/BFCL_v4_live_simple.json"
    records = fixture_records()
    assert sorted(records) == sorted(c["id"] for c in CASES if c["case"] == "reference")
    assert {cat for _, _, cat in records.values()} == set(FIXTURE_CATEGORIES)
    with pytest.raises(ValueError, match="unknown category"):
        read_records(FIXTURES, "simple_java")


def _bfcl_tree(base: Path, questions: Sequence[Any], answers: Sequence[Any]) -> Path:
    q_rel, a_rel = data_paths("simple_python")
    for rel, rows in ((q_rel, questions), (a_rel, answers)):
        path = base / BFCL_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows) + "\n")
    return base


GOOD_Q = {
    "id": "simple_python_0",
    "question": [[{"role": "user", "content": "Call f."}]],
    "function": [{"name": "f", "parameters": {"type": "dict", "properties": {}}}],
}
GOOD_A = {"id": "simple_python_0", "ground_truth": [{"f": {}}]}


@pytest.mark.parametrize(
    ("questions", "answers", "message"),
    [
        ([GOOD_Q], [{**GOOD_A, "id": "simple_python_1"}], "one to one"),
        ([GOOD_Q, GOOD_Q], [GOOD_A], "one to one"),
        ([{**GOOD_Q, "id": "multiple_0"}], [{**GOOD_A, "id": "multiple_0"}], "unexpected"),
        ([{**GOOD_Q, "question": [{"role": "user"}]}], [GOOD_A], "question"),
        ([{**GOOD_Q, "function": [{"description": "x"}]}], [GOOD_A], "function"),
        ([GOOD_Q], [{**GOOD_A, "ground_truth": [{"f": {"a": 1}}]}], "ground_truth"),
        ([["not", "an", "object"]], [GOOD_A], "not a JSON object"),
    ],
)
def test_read_records_rejects_malformed_data(
    tmp_path: Path, questions: list[Any], answers: list[Any], message: str
) -> None:
    root = _bfcl_tree(tmp_path, questions, answers)
    with pytest.raises(ValueError, match=message):
        read_records(root, "simple_python")


def test_read_records_accepts_a_minimal_tree(tmp_path: Path) -> None:
    root = _bfcl_tree(tmp_path, [GOOD_Q], [GOOD_A])
    assert read_records(root, "simple_python") == [(GOOD_Q, GOOD_A)]


# ------------------------------------------------------------- reference construction


def test_reference_rules() -> None:
    doc = {
        "name": "f",
        "parameters": {
            "type": "dict",
            "required": ["a", "b", "c"],
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "float"},
                "c": {"type": "string"},
                "d": {"type": "string"},
                "e": {"type": "dict"},
                "g": {"type": "array", "items": {"type": "dict"}},
                "h": {"type": "array", "items": {"type": "integer"}},
                "k": {"type": "dict"},
            },
        },
    }
    params: dict[str, list[Any]] = {
        "a": [0, ""],  # required although the marker allows omission: kept
        "b": ["", 25.0],  # the marker is skipped when choosing the first value
        "c": [""],  # only the marker: the empty string itself
        "d": ["x", ""],  # optional and omittable: omitted
        "e": [{"k1": ["v", "w"], "k2": ["", 1], "k3": []}],  # a dict pattern
        "g": [[{"n": ["p"]}, {"n": ["q", ""]}]],  # a list of dict patterns
        "h": [[1, 2]],  # a plain list value
        "k": ["var_name"],  # a dict parameter answered with a string
        "z": ["undocumented"],  # not in the documentation and not omittable: kept
        "y": [],  # no acceptable value: omitted
    }
    assert reference_args(params, doc) == {
        "a": 0,
        "b": 25.0,
        "c": "",
        "e": {"k1": "v"},
        "g": [{"n": "p"}, {}],
        "h": [1, 2],
        "k": "var_name",
        "z": "undocumented",
    }
    assert reference_args({"a": [1, ""], "b": [2]}, None) == {"b": 2}
    assert reference_args({"a": [1]}, {"parameters": "odd"}) == {"a": 1}
    tuple_schema = {"type": "tuple", "items": {"type": "dict"}}
    assert reference_value([[{"x": [1]}]], tuple_schema) == [{"x": 1}]
    assert reference_value([[{"x": [1]}, 3]], tuple_schema) == [{"x": [1]}, 3]
    assert reference_value([[]], tuple_schema) == []
    assert reference_value([{"x": 1}], {"type": "dict"}) == {"x": 1}
    assert reference_value(["", ""], {"type": "string"}) == ""


def test_reference_calls_of_the_fixtures() -> None:
    expected = {c["id"]: c["trajectory"] for c in CASES if c["case"] == "reference"}
    for ident, (q, a, _) in fixture_records().items():
        assert reference_calls(q["function"], a["ground_truth"]) == expected[ident]
    unknown = reference_calls([], [{"g": {"x": ["", 1], "y": [2]}}])
    assert unknown == [{"tool": "g", "args": {"y": 2}}]


# ------------------------------------------------------------------ task directories


def test_instruction_and_hint() -> None:
    q, _, _ = fixture_records()["live_simple_165-98-0"]
    text = instruction(q)
    assert "### Message 1 (system)" in text and "### Message 2 (user)" in text
    assert "````text\n" + q["question"][0][1]["content"] + "\n````" in text
    assert "extractor.extract_information" in text and PYTHON_HINT in text
    assert "`trajectory.json`" in text
    hinted = with_python_hint(q["function"])
    assert hinted[0]["description"] == q["function"][0]["description"] + PYTHON_HINT
    assert PYTHON_HINT not in q["function"][0]["description"]
    assert with_python_hint([{"name": "f"}])[0]["description"] == PYTHON_HINT


def test_task_files(tmp_path: Path) -> None:
    q, a, category = fixture_records()["simple_python_94"]
    files = task_files(q, a, category, PINNED_COMMIT)
    assert sorted(files) == [
        "grader/bfcl_driver.py",
        "grader/bfcl_task.json",
        "grader/grade.sh",
        "instruction.md",
        "solution/trajectory.json",
        "support/run_solution.sh",
        "task.toml",
    ]
    assert files["grader/bfcl_driver.py"] == Path(bfcl_driver.__file__).read_text()
    data = json.loads(files["grader/bfcl_task.json"])
    assert data == grader_data(q, a, category, PINNED_COMMIT)
    assert data["function"] == q["function"] and data["ground_truth"] == a["ground_truth"]
    assert (data["model_name"], data["language"]) == (CHECKER_MODEL, "python")
    toml = task_toml(q, a, category, PINNED_COMMIT)
    assert files["task.toml"] == toml
    assert 'kind = "data"' in toml and "third_party = true" in toml
    assert "reference_from_grader_data = true" in toml


def test_convert_fixtures(tmp_path: Path) -> None:
    written = convert(FIXTURES, tmp_path / "tasks", FIXTURE_CATEGORIES)
    assert {c: [p.name for p in ps] for c, ps in written.items()} == {
        "simple_python": ["simple_python_94"],
        "parallel": ["parallel_29"],
        "parallel_multiple": ["parallel_multiple_26"],
        "live_simple": ["live_simple_165-98-0"],
        "live_multiple": ["live_multiple_144-56-0"],
    }
    adapter = ToybenchAdapter()
    tasks = {t.id: t for t in adapter.load(tmp_path / "tasks")}
    records = fixture_records()
    for ident, task in tasks.items():
        q, a, category = records[ident]
        assert task.key == f"bfcl:{ident}"
        assert task.environment["kind"] == "data"
        assert task.environment["solution_entry"] == "run_solution.sh"
        assert task.environment["third_party"] is True
        assert adapter.mutable_files(task) == {"trajectory.json": "trajectory"}
        meta = task.metadata
        assert meta["trusted_local"] is False and meta["benchmark"] == "bfcl"
        assert (meta["category"], meta["original_id"]) == (category, ident)
        assert (meta["source_commit"], meta["license"]) == (PINNED_COMMIT, "Apache-2.0")
        assert meta["reference_from_grader_data"] is True
        assert meta["source_path"].endswith(f"BFCL_v4_{category}.json")
        calls = json.loads(task.reference_solution["trajectory.json"])
        assert calls == reference_calls(q["function"], a["ground_truth"])
    # Converting again replaces the directories; a narrower conversion would leave strays.
    convert(FIXTURES, tmp_path / "tasks", FIXTURE_CATEGORIES)
    with pytest.raises(FileExistsError, match="does not write"):
        convert(FIXTURES, tmp_path / "tasks", ["parallel"])
    for bad in ([], ["parallel", "parallel"]):
        with pytest.raises(ValueError, match="distinct"):
            convert(FIXTURES, tmp_path / "other", bad)


def test_convert_refuses_another_commit(tmp_path: Path) -> None:
    copy = tmp_path / "gorilla"
    shutil.copytree(FIXTURES, copy)
    (copy / ".git").mkdir()
    (copy / ".git" / "HEAD").write_text("f" * 40 + "\n")
    with pytest.raises(ValueError, match="is at commit"):
        convert(copy, tmp_path / "tasks", ["parallel"])
    assert len(convert(copy, tmp_path / "tasks", ["parallel"], commit="f" * 40)["parallel"]) == 1


# --------------------------------------------------------- grading with recorded verdicts


def test_recorded_verdicts_replay_through_toybench(tmp_path: Path) -> None:
    tasks = converted(tmp_path / "tasks")
    root = fake_root(tmp_path / "fake")
    adapter = ToybenchAdapter(
        extra_env={"GP_BFCL_ROOT": str(root), "GP_BFCL_PYTHON": sys.executable}
    )
    for case in CASES:
        ex = adapter.execute(tasks[case["id"]], trajectory_text(case["trajectory"]), LocalSandbox())
        line = json.loads(ex.grade.stdout)
        assert (ex.grade.passed, line["valid"]) == (case["valid"], case["valid"]), case
        assert line["error_type"] == case["error_type"], case
        assert ex.grade.exit_status == (0 if case["valid"] else 1)
        assert [dict(c) for c in ex.outcome.trajectory] == case["trajectory"]
    task = tasks["parallel_29"]
    ex = adapter.execute(task, trajectory_text([{"tool": "f", "args": [1]}]), LocalSandbox())
    assert ex.grade.exit_status == 1
    assert json.loads(ex.grade.stdout)["error_type"] == bfcl_driver.WRONG_FORMAT
    unset = ToybenchAdapter(extra_env={"GP_BFCL_PYTHON": sys.executable})
    ex = unset.execute(task, task.reference_solution, LocalSandbox())
    assert ex.grade.exit_status == 2 and "GP_BFCL_ROOT is not set" in ex.grade.stderr


def break_reference(tasks_dir: Path, ident: str, case: str) -> None:
    """Replace a converted reference by a recorded case, to exercise a failing reference."""
    (calls,) = [c["trajectory"] for c in CASES if (c["id"], c["case"]) == (ident, case)]
    (tasks_dir / ident / "solution" / "trajectory.json").write_text(json.dumps(calls))


def test_check_references_and_summary(tmp_path: Path) -> None:
    converted(tmp_path / "tasks")
    env = {"GP_BFCL_ROOT": str(fake_root(tmp_path / "fake")), "GP_BFCL_PYTHON": sys.executable}
    checks = check_references(tmp_path / "tasks", TRUSTED_LOCAL, env, repeat=2)
    assert [c.category for c in checks] == list(FIXTURE_CATEGORIES)
    assert all(c.determinism is Determinism.STABLE_PASS and c.exit_status == 0 for c in checks)
    assert summarize(checks)[-1] == "all: 5 of 5 references pass"
    break_reference(tmp_path / "tasks", "live_multiple_144-56-0", "required perPage omitted")
    checks = check_references(tmp_path / "tasks", TRUSTED_LOCAL, env)
    failed = [c for c in checks if c.determinism is not Determinism.STABLE_PASS]
    assert [(c.task_id, c.determinism, c.exit_status) for c in failed] == [
        ("live_multiple_144-56-0", Determinism.STABLE_FAIL, 1)
    ]
    assert "missing_required" in failed[0].result
    lines = summarize(checks)
    assert "simple_python: 1 of 1 references pass" in lines
    assert "live_multiple: 0 of 1 references pass" in lines
    assert lines[-1] == "all: 4 of 5 references pass"
    assert any(line.startswith("  live_multiple_144-56-0 stable_fail exit 1") for line in lines)
    odd = ReferenceCheck("x_1", "elsewhere", Determinism.FLAKY, 1, "")
    assert summarize([odd])[0] == "elsewhere: 0 of 1 references pass"
    with pytest.raises(SandboxPolicyError):
        check_references(tmp_path / "tasks", LocalSandbox(), env)


# ---------------------------------------------------------------- the driver in-process


def _write_task_data(path: Path, ident: str, commit: str = PINNED_COMMIT) -> Path:
    q, a, category = fixture_records()[ident]
    path.write_text(json.dumps(grader_data(q, a, category, commit)))
    return path


def test_decode() -> None:
    assert bfcl_driver.decode([]) == []
    calls = [
        {"tool": "f", "args": {"x": 1}, "result": 2},
        {"tool": "g"},
        {"tool": "h", "args": None},
    ]
    assert bfcl_driver.decode(calls) == [{"f": {"x": 1}}, {"g": {}}, {"h": {}}]
    for bad, error_type in (
        ({"tool": "f"}, bfcl_driver.DECODER_FAILED),
        ([["f"]], bfcl_driver.DECODER_FAILED),
        ([{"tool": 3}], bfcl_driver.DECODER_FAILED),
        ([{"tool": "f", "args": "x=1"}], bfcl_driver.WRONG_FORMAT),
    ):
        with pytest.raises(bfcl_driver.DecodeError) as info:
            bfcl_driver.decode(bad)
        assert info.value.error_type == error_type


def test_checkout_commit(tmp_path: Path) -> None:
    root = tmp_path / "gorilla" / BFCL_DIR
    root.mkdir(parents=True)
    assert bfcl_driver.checkout_commit(root) is None
    (tmp_path / "gorilla" / ".git").mkdir()
    (tmp_path / "gorilla" / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    assert bfcl_driver.checkout_commit(root) is None
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("a" * 40 + "\n")
    assert bfcl_driver.checkout_commit(root) == "a" * 40


def test_handler_placeholders() -> None:
    hook = bfcl_driver.HandlerPlaceholders()
    assert hook.find_spec("json", None) is None
    assert hook.find_spec("bfcl_eval.model_handler_x", None) is None
    spec = hook.find_spec("bfcl_eval.model_handler.api_inference.claude", None)
    assert spec is not None and spec.submodule_search_locations == []
    module = hook.create_module(spec)
    hook.exec_module(module)
    handler = module.ClaudeHandler
    assert isinstance(handler, type) and handler.__module__ == spec.name
    with pytest.raises(AttributeError):
        _ = module.__file__


def test_grade_with_a_stub_checker() -> None:
    task = {
        "function": [],
        "ground_truth": [],
        "language": "python",
        "category": "c",
        "model_name": "m",
    }
    seen: list[tuple[Any, ...]] = []

    def checker(*args: Any) -> dict[str, Any]:
        seen.append(args)
        return {"valid": True, "error": [], "error_type": "simple_function_checker:unclear"}

    verdict = bfcl_driver.grade(task, [{"tool": "f", "args": {"a": 1}}], checker, str.upper)
    assert verdict == {"valid": True, "error_type": None, "error": []}
    assert seen == [([], [{"f": {"a": 1}}], [], "PYTHON", "c", "m")]
    bad = bfcl_driver.grade(task, "nope", checker, str.upper)
    assert bad["valid"] is False and bad["error_type"] == bfcl_driver.DECODER_FAILED


def test_read_task(tmp_path: Path) -> None:
    good = _write_task_data(tmp_path / "t.json", "parallel_29")
    assert bfcl_driver.read_task(good)["category"] == "parallel"
    with pytest.raises(bfcl_driver.SetupError, match="cannot read"):
        bfcl_driver.read_task(tmp_path / "missing.json")
    (tmp_path / "list.json").write_text("[]")
    with pytest.raises(bfcl_driver.SetupError, match="lacks"):
        bfcl_driver.read_task(tmp_path / "list.json")


def _main(argv: Sequence[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, Any, str]:
    status = bfcl_driver.main(list(argv))
    captured = capsys.readouterr()
    out = json.loads(captured.out) if captured.out.strip() else None
    return status, out, captured.err


def test_driver_main_verdicts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    clean_imports: None,
) -> None:
    task = _write_task_data(tmp_path / "task.json", "simple_python_94")
    monkeypatch.setenv("GP_BFCL_ROOT", str(fake_root(tmp_path / "fake")))
    traj = tmp_path / "trajectory.json"
    for case in (c for c in CASES if c["id"] == "simple_python_94"):
        traj.write_text(json.dumps(case["trajectory"]))
        status, out, _ = _main([str(task), str(traj)], capsys)
        assert status == (0 if case["valid"] else 1)
        assert (out["id"], out["valid"], out["error_type"]) == (
            "simple_python_94",
            case["valid"],
            case["error_type"],
        )
    assert "update_user_info" not in sys.modules["bfcl_eval.model_handler"].__dict__
    traj.write_text('[{"tool": "update_user_info", "args": {"user_id": 1}}]')
    status, out, _ = _main([str(task), str(traj)], capsys)
    assert status == 3 and out["error_type"] == "checker_exception"
    status, out, _ = _main([str(task), str(tmp_path / "absent.json")], capsys)
    assert status == 1 and out["error_type"] == bfcl_driver.DECODER_FAILED
    traj.write_text('{"tool": "update_user_info"')
    status, out, _ = _main([str(task), str(traj)], capsys)
    assert status == 1 and out["error_type"] == bfcl_driver.DECODER_FAILED
    with pytest.raises(bfcl_driver.SetupError, match="not from"):
        bfcl_driver.load_checker(fake_root(tmp_path / "second"))


def test_driver_main_setup_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    clean_imports: None,
) -> None:
    task = _write_task_data(tmp_path / "task.json", "parallel_29")
    traj = tmp_path / "trajectory.json"
    traj.write_text("[]")
    assert _main([str(task)], capsys)[0] == 2
    monkeypatch.delenv("GP_BFCL_ROOT", raising=False)
    status, out, err = _main([str(task), str(traj)], capsys)
    assert (status, out) == (2, None) and "GP_BFCL_ROOT is not set" in err
    monkeypatch.setenv("GP_BFCL_ROOT", str(tmp_path / "nothing"))
    status, _, err = _main([str(task), str(traj)], capsys)
    assert status == 2 and "has no" in err
    moved = fake_root(tmp_path / "moved")
    (tmp_path / "moved" / ".git").mkdir()
    (tmp_path / "moved" / ".git" / "HEAD").write_text("b" * 40 + "\n")
    monkeypatch.setenv("GP_BFCL_ROOT", str(moved))
    status, _, err = _main([str(task), str(traj)], capsys)
    assert status == 2 and "converted from" in err
    broken = fake_root(tmp_path / "broken", checker="raise RuntimeError('broken checker')\n")
    monkeypatch.setenv("GP_BFCL_ROOT", str(broken))
    status, _, err = _main([str(task), str(traj)], capsys)
    assert status == 2 and "broken checker" in err
    status, _, err = _main([str(tmp_path / "absent.json"), str(traj)], capsys)
    assert status == 2 and "cannot read task data" in err


# ------------------------------------------------------------------------ command line


def test_main_convert_and_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "tasks"
    cats = ",".join(FIXTURE_CATEGORIES)
    assert main(["convert", str(FIXTURES), str(out), "--categories", cats]) == 0
    printed = capsys.readouterr().out
    assert "parallel: 1 tasks" in printed and "converted 5 BFCL tasks" in printed
    assert main(["convert", str(FIXTURES), str(tmp_path / "all")]) == 1
    assert "bfcl:" in capsys.readouterr().err
    root = tmp_path / "src" / BFCL_DIR

    def fake_fetch(dest: Path, commit: str = PINNED_COMMIT, url: str = "") -> Path:
        assert commit == PINNED_COMMIT
        return dest / BFCL_DIR

    monkeypatch.setattr(bfcl, "fetch", fake_fetch)
    assert main(["fetch", str(tmp_path / "src")]) == 0
    assert f"GP_BFCL_ROOT={root.resolve()}" in capsys.readouterr().out


def test_main_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    converted(tmp_path / "tasks")
    root = fake_root(tmp_path / "fake")
    argv = ["check", str(tmp_path / "tasks"), "--root", str(root), "--python", sys.executable]
    monkeypatch.setattr(bfcl, "best_sandbox", lambda: TRUSTED_LOCAL)
    assert main(argv) == 0
    printed = capsys.readouterr().out
    assert "all: 5 of 5 references pass" in printed and "sandbox local-test" in printed
    break_reference(tmp_path / "tasks", "parallel_29", "second call dropped")
    assert main(argv) == 1
    assert "parallel: 0 of 1 references pass" in capsys.readouterr().out
    monkeypatch.setattr(bfcl, "best_sandbox", lambda: None)
    assert main(argv) == 1
    assert "no write-isolating sandbox" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main([*argv, "--repeat", "0"])


def test_categories_constant() -> None:
    assert len(CATEGORIES) == 8 and set(FIXTURE_CATEGORIES) <= set(CATEGORIES)
    assert all("java" not in c for c in CATEGORIES)


# --------------------------------------------------------------------------- live checks


live = pytest.mark.skipif(not LIVE_ROOT, reason="set GP_BFCL_ROOT to the pinned BFCL checkout")


@live
def test_live_fixtures_are_verbatim() -> None:
    root = Path(LIVE_ROOT)
    for path in sorted((FIXTURES / BFCL_DIR).rglob("*.json")):
        rel = path.relative_to(FIXTURES / BFCL_DIR)
        live_lines = set((root / rel).read_text(encoding="utf-8").splitlines())
        for line in path.read_text(encoding="utf-8").splitlines():
            assert line in live_lines, rel
    assert (FIXTURES / "LICENSE").read_bytes() == (root.parent / "LICENSE").read_bytes()


@live
def test_live_verdicts_match_recording(tmp_path: Path) -> None:
    if not bwrap_works():
        pytest.skip("bubblewrap does not work here")
    assert RECORDING["source_commit"] == PINNED_COMMIT
    assert RECORDING["checker_model"] == CHECKER_MODEL
    env = {"GP_BFCL_ROOT": LIVE_ROOT}
    if os.environ.get("GP_BFCL_PYTHON"):
        env["GP_BFCL_PYTHON"] = os.environ["GP_BFCL_PYTHON"]
    tasks = converted(tmp_path / "tasks")
    adapter = ToybenchAdapter(extra_env=env)
    for case in CASES:
        ex = adapter.execute(tasks[case["id"]], trajectory_text(case["trajectory"]), BwrapSandbox())
        line = json.loads(ex.grade.stdout)
        assert (ex.grade.passed, line["error_type"]) == (case["valid"], case["error_type"]), case
