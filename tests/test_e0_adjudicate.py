"""Tests for tools/e0_adjudicate.py (E0 adjudication of flags that are not detections)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import e0_adjudicate as adj
import pytest

from graderproof import audit, e0
from graderproof.core import sha256_text
from graderproof.models import ModelClient

LABELS: dict[str, dict[str, Any]] = {
    "a": {"planted": True, "slice": "in_list", "weakness_type": "w", "direction": "accept"},
    "c": {"planted": True, "slice": "in_list", "weakness_type": "w", "direction": "reject"},
    "e": {"planted": False, "slice": "clean", "weakness_type": None, "direction": None},
    "x": {"planted": True, "slice": "extra", "weakness_type": "w", "direction": "accept"},
}
BUDGET = (
    "cash_usd = 0\nclaude_agent_runs_per_day = 30\nclaude_agent_max_turns = 40\n"
    "claude_single_calls_per_day = 300\nclaude_review_runs_per_day = 6\n"
    "local_model_max_params_b = 8\ndisk_floor_gb = 8\n"
)
GIT = ("-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false")
# Variables that point git elsewhere, each with where it points inside another checkout.
REDIRECTS = {
    "GIT_DIR": ".git",
    "GIT_WORK_TREE": ".",
    "GIT_COMMON_DIR": ".git",
    "GIT_INDEX_FILE": ".git/index",
    "GIT_OBJECT_DIRECTORY": ".git/objects",
}
TOOL_KEYS = ("tool_git_sha", "tool_git_dirty", "tool_sha256")
GitRun = Callable[..., subprocess.CompletedProcess[bytes]]


def sha(data: bytes) -> str:
    """Hex SHA-256 of bytes."""
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> str:
    """Run git in the throwaway checkout ``repo``, never where a redirect points; return stdout."""
    env = {k: v for k, v in os.environ.items() if k not in REDIRECTS}
    proc = subprocess.run(
        ["git", "-C", str(repo), *GIT, *args], capture_output=True, text=True, check=True, env=env
    )
    return proc.stdout.strip()


def commit(repo: Path, files: dict[str, str]) -> str:
    """Write ``files`` into ``repo`` (a new checkout if missing), commit all, return HEAD."""
    if not (repo / ".git").exists():
        repo.mkdir(parents=True)
        git(repo, "init", "-q")
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c")
    return git(repo, "rev-parse", "HEAD")


def tool_repo(root: Path) -> tuple[Path, Path, str]:
    """A checkout under ``root`` with a committed tool file: (checkout, tool file, HEAD)."""
    repo = root / "repo"
    files = {"tools/t.py": "x = 1\n", "tools/other.py": "y = 1\n", ".gitignore": "ignored.py\n"}
    return repo, repo / "tools" / "t.py", commit(repo, files)


def tool_source(head: str, dirty: bool, data: bytes) -> dict[str, str | bool]:
    """What tool_provenance should report for a file that holds ``data``."""
    return {"tool_git_sha": head, "tool_git_dirty": dirty, "tool_sha256": sha(data)}


def after_first(git_run: GitRun, command: str, act: Callable[[], object]) -> GitRun:
    """``git_run``, doing ``act`` right after its first ``git <command>`` call returns."""
    done: list[bool] = []

    def wrapped(cwd: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
        proc = git_run(cwd, *args)
        if args[0] == command and not done:
            done.append(True)
            act()
        return proc

    return wrapped


def run_provenance(args: list[str]) -> dict[str, Any]:
    """Run the tool, check the keys every artifact carries, and return the source keys."""
    assert adj.main(args) == 0
    out = Path(args[args.index("--out") + 1])
    prov: dict[str, Any] = json.loads(out.read_text())["provenance"]
    base = audit.provenance(audit.AuditConfig(), {"tool": "tools/e0_adjudicate.py"})
    assert {k: v for k, v in prov.items() if k not in TOOL_KEYS} == base  # values unchanged
    assert set(prov) - set(base) == set(TOOL_KEYS)
    return {k: prov[k] for k in ("git_sha", "git_dirty", *TOOL_KEYS)}


def row(tid: str, fa: bool = False, fr: bool = False) -> dict[str, Any]:
    key = f"tasks:{tid}"
    flags = {"false_accept": fa, "false_reject": fr, "reference_rejected": False, "flaky": False}
    return {"task": key, "task_hash": sha256_text(key), "determinism": "stable_pass", **flags}


def var(vid: str, kind: str, passed: bool, counted: bool = True) -> dict[str, Any]:
    witness: dict[str, Any] | None = None
    if kind == "violating":
        witness = {"broken": [{"requirement": "R1", "detail": "x"}]}
    if kind == "preserving":
        witness = {"held": ["R1"]}
    return {
        "id": vid,
        "kind": kind,
        "grader_passed": passed,
        "counted_in_headline": counted,
        "diff": f"diff {vid}",
        "files": {"s.sh": vid},
        "witness": witness,
    }


def setup(tmp_path: Path) -> list[str]:
    audit, tasks = tmp_path / "e0", tmp_path / "tasks"
    (audit / "evidence").mkdir(parents=True)
    rows = [row("a", fa=True), row("c", fa=True), row("e", fr=True, fa=True), row("x", fa=True)]
    (audit / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    variants = {
        "a": [var("va", "violating", True)],
        "c": [var("vc", "violating", True), var("vk", "violating", False)],
        "e": [
            var("ve1", "violating", True),
            var("ve2", "preserving", False),
            var("ve3", "preserving", True),
            var("ve4", "violating", True, counted=False),
        ],
        "x": [var("vx", "violating", True)],
    }
    for r in rows:
        tid = r["task"].split(":")[1]
        reqs = [{"id": "R1", "text": "prints ok", "checks": []}]
        ev = {"requirements": reqs, "variants": variants[tid]}
        (audit / "evidence" / f"{r['task_hash']}.json").write_text(json.dumps(ev))
        d = tasks / tid
        (d / "solution").mkdir(parents=True)
        (d / "grader").mkdir()
        (d / "instruction.md").write_text(f"task {tid}")
        (d / "solution" / "s.sh").write_text("echo ok\n")
        (d / "grader" / "g.sh").write_text("true\n")
    (tmp_path / "labels.json").write_text(json.dumps({"tasks": LABELS}))
    (tmp_path / "budget.toml").write_text(BUDGET)
    args = ["--audit", str(audit), "--labels", str(tmp_path / "labels.json")]
    args += ["--tasks", str(tasks), "--store", str(tmp_path / "store")]
    args += ["--ledger", str(tmp_path / "ledger.jsonl"), "--budget", str(tmp_path / "budget.toml")]
    return [*args, "--out", str(audit / "adjudication.json")]


def test_helpers() -> None:
    ev = {"variants": [var("v1", "violating", True), var("v2", "preserving", False)]}
    both = adj.flagged_variants(ev, {"false_accept": True, "false_reject": True})
    assert [(v["id"], v["flag"]) for v in both] == [("v1", "false accept"), ("v2", "false reject")]
    assert [v["id"] for v in adj.flagged_variants(ev, {"false_reject": True})] == ["v2"]
    w = adj.witness_text(
        {"broken": [{"requirement": "R1"}], "held": ["R2"]}, {"R1": "a", "R2": "b"}
    )
    assert w == {
        "broken": [{"requirement": "R1", "requirement_text": "a"}],
        "held": [{"requirement": "R2", "requirement_text": "b"}],
    }
    assert adj.witness_text(None, {}) is None
    out = adj.rulings(
        {"t": ["v1", "v2"], "u": ["v3"], "z": []},
        {
            "v1": {"verdict": "does-not-validate", "reason": "fine"},
            "v2": {"verdict": "validates", "reason": "broken"},
            "v3": {"verdict": "does-not-validate", "reason": "fine"},
        },
    )
    assert out["t"]["real"] and out["t"]["reason"] == "broken"
    assert not out["u"]["real"] and out["u"]["reason"] == "fine"
    assert not out["z"]["real"] and "no counted" in out["z"]["reason"]


def test_adjudication_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = setup(tmp_path)
    assert adj.main(args) == adj.PENDING
    pending = [line.split()[1] for line in capsys.readouterr().out.splitlines()]
    assert len(pending) == 1
    req = json.loads(Path(pending[0]).read_text())
    ids = sorted(i["id"] for i in req["items"])
    assert ids == ["vc", "ve1", "ve2"]  # a is detected, x is extra, vk and ve3, ve4 not flags
    text = json.dumps(req)
    assert "planted" not in text and "in_list" not in text and "tasks:" not in text
    item = next(i for i in req["items"] if i["id"] == "ve2")
    assert item["flag"] == "false reject" and item["grader_files"] == {"g.sh": "true\n"}
    assert item["witness"]["held"][0]["requirement_text"] == "prints ok"
    verdicts = {"vc": "does-not-validate", "ve1": "does-not-validate", "ve2": "validates"}
    resp = {
        "request": req["hash"],
        "backend": "test",
        "model": "m",
        "items": {i: {"verdict": v, "reason": f"r-{i}"} for i, v in verdicts.items()},
    }
    client = ModelClient(tmp_path / "store", tmp_path / "ledger.jsonl", tmp_path / "budget.toml")
    (client.store / "responses").mkdir(parents=True, exist_ok=True)
    (client.store / "responses" / f"{req['hash']}.json").write_text(json.dumps(resp))
    client.ingest(req["hash"])
    assert adj.main(args) == 0
    doc = json.loads((tmp_path / "e0" / "adjudication.json").read_text())
    assert sorted(doc["tasks"]) == ["c", "e"]
    assert doc["tasks"]["e"]["real"] is True and doc["tasks"]["c"]["real"] is False
    assert doc["models"] == ["test:m"] and doc["prompt_version"] == "adjudicate/v1"
    rows = [json.loads(line) for line in (tmp_path / "e0" / "tasks.jsonl").read_text().splitlines()]
    scores = e0.task_scores(rows, LABELS, doc["tasks"])
    assert [s.task for s in scores if s.adjudicated_real] == ["e"]


def test_no_flags_writes_an_empty_file(tmp_path: Path) -> None:
    args = setup(tmp_path)
    rows = [row("a", fa=True), row("c", fr=True), row("e"), row("x")]
    (tmp_path / "e0" / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert adj.main(args) == 0
    doc = json.loads((tmp_path / "e0" / "adjudication.json").read_text())
    assert doc["tasks"] == {}


def test_tool_provenance_follows_the_checkout_that_holds_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, tool, head = tool_repo(tmp_path)
    assert adj.tool_provenance(tool) == tool_source(head, False, b"x = 1\n")
    tool.write_text("x = 2\n")  # unstaged change
    assert adj.tool_provenance(tool) == tool_source(head, True, b"x = 2\n")
    git(repo, "add", "-A")  # staged change
    assert adj.tool_provenance(tool) == tool_source(head, True, b"x = 2\n")
    tool.write_text("x = 1\n")  # staged change, undone on disk only
    assert adj.tool_provenance(tool) == tool_source(head, True, b"x = 1\n")
    tool.write_text("x = 2\n")
    head2 = commit(repo, {})
    assert adj.tool_provenance(tool) == tool_source(head2, False, b"x = 2\n")
    git(repo, "rm", "-q", "--cached", "tools/t.py")  # no longer tracked, bytes as committed
    assert adj.tool_provenance(tool) == tool_source(head2, True, b"x = 2\n")
    git(repo, "add", "tools/t.py")
    git(repo, "config", "status.showUntrackedFiles", "no")  # git status alone misses these
    for name in ("untracked.py", "ignored.py"):  # in the checkout, not in its HEAD
        (repo / "tools" / name).write_text("x = 2\n")
        assert adj.tool_provenance(repo / "tools" / name) == tool_source(head2, True, b"x = 2\n")
    (repo / "tools" / "other.py").write_text("y = 2\n")  # changes to other files do not count
    assert adj.tool_provenance(tool) == tool_source(head2, False, b"x = 2\n")
    plain = tmp_path / "plain" / "t.py"
    plain.parent.mkdir()
    plain.write_text("x = 1\n")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))  # tmp_path may be in a checkout
    assert adj.tool_provenance(plain) == tool_source("unknown", True, b"x = 1\n")


def test_tool_provenance_compares_the_bytes_with_the_commit_it_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """git status can call a changed file clean; its blob at the recorded commit cannot."""
    repo, tool, head = tool_repo(tmp_path)
    for flag in ("assume-unchanged", "skip-worktree"):  # git status skips flagged files
        git(repo, "update-index", f"--{flag}", "tools/t.py")
        tool.write_text("x = 3\n")
        assert adj.tool_provenance(tool) == tool_source(head, True, b"x = 3\n")
        tool.write_text("x = 1\n")
        git(repo, "update-index", f"--no-{flag}", "tools/t.py")
        assert adj.tool_provenance(tool) == tool_source(head, False, b"x = 1\n")
    tool.write_text("x = 3\n")  # a replacement ref lets a commit holding the edit stand in
    git(repo, "add", "tools/t.py")
    git(repo, "replace", head, git(repo, "commit-tree", git(repo, "write-tree"), "-m", "s"))
    assert adj.tool_provenance(tool) == tool_source(head, True, b"x = 3\n")
    git(repo, "replace", "-d", head)
    git(repo, "checkout", "-q", "HEAD", "--", "tools/t.py")
    assert adj.tool_provenance(tool) == tool_source(head, False, b"x = 1\n")
    real_git = adj._git
    edit = after_first(real_git, "status", lambda: tool.write_text("x = 9\n"))
    monkeypatch.setattr(adj, "_git", edit)  # an edit after the checks: hashed as compared
    assert adj.tool_provenance(tool) == tool_source(head, False, b"x = 1\n")
    assert tool.read_text() == "x = 9\n"
    tool.write_text("x = 4\n")
    race = after_first(real_git, "rev-parse", lambda: commit(repo, {}))
    monkeypatch.setattr(adj, "_git", race)  # the edit is committed just after HEAD is read
    assert adj.tool_provenance(tool) == tool_source(head, True, b"x = 4\n")
    assert git(repo, "rev-parse", "HEAD") != head  # the commit did land in between


def test_tool_provenance_leaves_the_index_alone(tmp_path: Path) -> None:
    """Others work in the checkout that holds the tool: git status must not take its lock."""
    repo, tool, head = tool_repo(tmp_path)
    os.utime(tool, (1_000_000_000, 1_000_000_000))  # stat data git status would refresh
    index = (repo / ".git" / "index").read_bytes()
    assert adj.tool_provenance(tool) == tool_source(head, False, b"x = 1\n")
    assert (repo / ".git" / "index").read_bytes() == index


@pytest.mark.parametrize(
    "names", [("GIT_DIR", "GIT_WORK_TREE"), *((n,) for n in REDIRECTS)], ids="+".join
)
def test_tool_provenance_ignores_variables_that_point_git_elsewhere(
    names: tuple[str, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, tool, head = tool_repo(tmp_path)
    other = tmp_path / "other"
    commit(other, {"tools/t.py": "x = 2\n", "o.txt": "o\n"})
    plain = tmp_path / "plain" / "t.py"
    plain.parent.mkdir()
    plain.write_text("x = 1\n")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))  # tmp_path may be in a checkout
    for name in names:  # as git sets some of them for hooks
        monkeypatch.setenv(name, str(other / REDIRECTS[name]))
    assert adj.tool_provenance(tool) == tool_source(head, False, b"x = 1\n")
    assert adj.tool_provenance(plain) == tool_source("unknown", True, b"x = 1\n")
    tool.write_text("x = 2\n")
    assert adj.tool_provenance(tool) == tool_source(head, True, b"x = 2\n")


def test_provenance_records_the_tool_source_beside_the_run_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review N2: the tool can run from one checkout while its file lives in another."""
    assert Path(adj.__file__).resolve() == adj.TOOL_FILE  # by default it describes itself
    args = setup(tmp_path)
    rows = [row("a", fa=True), row("c", fr=True), row("e"), row("x")]  # nothing to rule on
    (tmp_path / "e0" / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    frozen, main_repo = tmp_path / "frozen", tmp_path / "main"
    run_head = commit(frozen, {"README.md": "frozen worktree\n"})
    tool_head = commit(main_repo, {"tools/e0_adjudicate.py": "# the tool\n"})
    assert run_head != tool_head
    tool = main_repo / "tools" / "e0_adjudicate.py"
    monkeypatch.setattr(adj, "TOOL_FILE", tool)
    monkeypatch.setattr(audit, "utc_now", lambda: "2026-01-01T00:00:00Z")
    monkeypatch.chdir(frozen)
    want = {
        "git_sha": run_head,
        "git_dirty": False,
        **tool_source(tool_head, False, b"# the tool\n"),
    }
    assert run_provenance(args) == want
    (frozen / "tools").mkdir()
    (frozen / "tools" / "scratch.py").write_text("x = 1\n")  # the run checkout is dirty
    assert run_provenance(args) == {**want, "git_dirty": True}
    (frozen / "tools" / "scratch.py").unlink()
    tool.write_text("# the tool, edited\n")  # the tool is dirty when the run starts ...
    build_items = adj.build_items

    def revert_then_build(*a: Any) -> Any:
        git(main_repo, "checkout", "--", "tools/e0_adjudicate.py")  # ... and reverted mid-run
        return build_items(*a)

    monkeypatch.setattr(adj, "build_items", revert_then_build)
    edited = tool_source(tool_head, True, b"# the tool, edited\n")
    assert run_provenance(args) == {**want, **edited}
    assert tool.read_text() == "# the tool\n"
