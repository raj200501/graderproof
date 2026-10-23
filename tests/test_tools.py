"""Tests for the repository tools under tools/ (doctor, scans, budget, review, ship-check)."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import budget
import doctor
import pytest
import review
import secrets_scan
import ship_check
import stub
import style_check

EM_DASH = chr(0x2014)


def git_repo(tmp_path: Path) -> Path:
    """An empty git repository with one commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    env = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "a.txt").write_text("a\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), *env, "commit", "-qm", "one"], check=True)
    return repo


def commit_all(repo: Path, message: str) -> str:
    env = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), *env, "commit", "-qm", message], check=True)
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


# ---------------------------------------------------------------- doctor


def test_billing_guard_names_variables_and_api_key_helper(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"apiKeyHelper": "/bin/echo"}))
    env = {"ANTHROPIC_API_KEY": "x", "CLAUDE_CODE_USE_BEDROCK": "1", "HOME": "/root"}
    hits = doctor.billing_guard_triggers(env, [settings, tmp_path / "missing.json"])
    assert "ANTHROPIC_API_KEY" in hits
    assert "CLAUDE_CODE_USE_BEDROCK" in hits
    assert any("apiKeyHelper" in h for h in hits)
    assert doctor.billing_guard_triggers({"HOME": "/root"}, []) == []


def test_billing_guard_ignores_empty_values_and_bad_settings(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert doctor.billing_guard_triggers({"ANTHROPIC_BASE_URL": ""}, [bad]) == []


def test_recommended_local_params_never_exceeds_cap() -> None:
    assert doctor.recommended_local_params_b(64.0, 8.0) == 8.0
    assert doctor.recommended_local_params_b(8.0, 8.0) == 5.0
    assert doctor.recommended_local_params_b(2.0, 8.0) == 0.0


def test_fallbacks_describe_missing_backends() -> None:
    report: dict[str, Any] = {
        "docker": {"daemon": False},
        "claude": {"usable": False, "billing_guard_triggers": ["ANTHROPIC_BASE_URL"]},
        "local_models": {"usable": False},
        "sandbox": {"best": None, "docker": False},
        "free_tiers": {"confirmed": False},
        "downloads_allowed": False,
    }
    text = " ".join(doctor.fallbacks(report))
    for needle in (
        "Docker",
        "ANTHROPIC_BASE_URL",
        "local model",
        "No sandbox",
        "Free tiers",
        "disk",
    ):
        assert needle in text


# ---------------------------------------------------------------- secrets scan


def test_secret_patterns_match_known_formats() -> None:
    aws = "AKIA" + "Q" * 16
    gh = "ghp_" + "a1" * 18
    key_block = "-----BEGIN " + "RSA PRIVATE KEY-----"
    text = f"x = '{aws}'\ny = {gh}\n{key_block}\nplain line\n"
    hits = secrets_scan.scan_text("f.py", text, {})
    assert "f.py:1 aws-access-key-id" in hits
    assert "f.py:2 github-token" in hits
    assert "f.py:3 private-key-block" in hits
    assert not any(h.startswith("f.py:4") for h in hits)


def test_env_secret_values_are_found_but_not_printed() -> None:
    value = "s3cr3t-" + "v" * 20
    env = {"MY_API_TOKEN": value, "GIT_CONFIG_KEY_0": "x" * 30, "TOKEN_FILE": "y" * 30}
    secrets = secrets_scan.secret_env_values(env)
    assert list(secrets) == ["MY_API_TOKEN"]
    hits = secrets_scan.scan_text("cfg", f"token: {value}\n", secrets)
    assert hits == ["cfg:1 value-of-$MY_API_TOKEN"]
    assert value not in " ".join(hits)


def test_scan_repo_tracked_env_file_and_history(tmp_path: Path) -> None:
    repo = git_repo(tmp_path)
    (repo / ".env").write_text("A=1\n")
    leaked = "AKIA" + "Z" * 16
    (repo / "old.txt").write_text(leaked + "\n")
    commit_all(repo, "two")
    (repo / "old.txt").write_text("clean\n")
    commit_all(repo, "three")
    found = secrets_scan.scan(repo, {}, history=True)
    assert any("tracked-env-file" in f for f in found)
    assert any(f.startswith("history:") and "aws-access-key-id" in f for f in found)
    assert not any("aws" in f for f in secrets_scan.scan(repo, {}, history=False))
    assert secrets_scan.decode(b"\0binary") is None
    assert secrets_scan.dedupe(["a", "b", "a"]) == ["a", "b"]


# ---------------------------------------------------------------- budget

CAPS: dict[str, Any] = {
    "cash_usd": 0,
    "claude_agent_runs_per_day": 2,
    "claude_agent_max_turns": 5,
    "claude_single_calls_per_day": 3,
    "claude_review_runs_per_day": 1,
    "local_model_max_params_b": 8,
    "disk_floor_gb": 8,
}


def test_budget_ok_with_no_usage() -> None:
    cash, per_day, violations = budget.evaluate(CAPS, [], [])
    assert cash == 0
    assert per_day == {}
    assert violations == []


def test_budget_flags_cash_caps_and_turns() -> None:
    ledger = [
        {"utc": "2026-10-23T01:00:00Z", "kind": "agent_run", "turns": 9},
        {"utc": "2026-10-23T02:00:00Z", "kind": "agent_run", "turns": 1},
        {"utc": "2026-10-23T03:00:00Z", "kind": "agent_run", "turns": 1},
        {"utc": "2026-10-24T03:00:00Z", "kind": "single_call", "cash_usd": 0.5},
    ]
    reviews = [{"utc": "2026-10-23T05:00:00Z"}, {"utc": "2026-10-23T06:00:00Z"}]
    cash, per_day, violations = budget.evaluate({**CAPS, "cash_usd": 1}, ledger, reviews)
    assert cash == 0.5
    assert per_day["2026-10-23"] == Counter({"agent_run": 3, "review_run": 2})
    text = " | ".join(violations)
    assert "cash_usd is 1" in text
    assert "cash spent 0.5" in text
    assert "9 turns" in text
    assert "agent_run 3 > claude_agent_runs_per_day" in text
    assert "review_run 2 > claude_review_runs_per_day" in text


def test_cap_share_only_lowers() -> None:
    assert budget.cap_share({}) == 1.0
    assert budget.cap_share({"CAP_SHARE": "0.5"}) == 0.5
    assert budget.cap_share({"CAP_SHARE": "2"}) == 1.0
    assert budget.cap_share({"CAP_SHARE": "abc"}) == 1.0
    assert budget.cap_share({}, {"cap_share": 0.2}) == 0.2
    assert budget.cap_share({"CAP_SHARE": "0.1"}, {"cap_share": 0.2}) == 0.1
    assert budget.cap_share({"CAP_SHARE": "0.9"}, {"cap_share": 0.2}) == 0.2
    assert budget.cap_share({}, {"cap_share": 5}) == 1.0
    eff = budget.effective_caps(CAPS, 0.5)
    assert eff["claude_single_calls_per_day"] == 1


def test_read_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "x.jsonl"
    assert budget.read_jsonl(p) == []
    p.write_text('{"a": 1}\n\n{"a": 2}\n')
    assert budget.read_jsonl(p) == [{"a": 1}, {"a": 2}]


# ---------------------------------------------------------------- review


def good_review(sha: str) -> dict[str, Any]:
    return {
        "schema": review.SCHEMA,
        "reviewed_commit": sha,
        "reviewed_at_utc": "2026-10-23T00:00:00Z",
        "verdict": "SHIP",
        "blocking": [],
        "non_blocking": [{"id": "N1", "title": "nit"}],
        "final_line": "REVIEW: SHIP",
    }


def test_review_validate_accepts_ship_with_allowed_diff(tmp_path: Path) -> None:
    repo = git_repo(tmp_path)
    reviewed = review.git(repo, "rev-parse", "HEAD")[1]
    (repo / "STATUS.md").write_text("s\n")
    (repo / "artifacts" / "review").mkdir(parents=True)
    (repo / "artifacts" / "review" / "latest.json").write_text("{}")
    commit_all(repo, "status only")
    assert review.validate(good_review(reviewed), repo) == []


def test_review_validate_rejects_code_changes_and_inconsistency(tmp_path: Path) -> None:
    repo = git_repo(tmp_path)
    reviewed = review.git(repo, "rev-parse", "HEAD")[1]
    (repo / "code.py").write_text("x = 1\n")
    commit_all(repo, "code")
    problems = review.validate(good_review(reviewed), repo)
    assert any("outside the allowed paths" in p for p in problems)
    bad = {
        **good_review(reviewed),
        "verdict": "SHIP",
        "blocking": [{"id": "B1", "title": "t"}],
        "final_line": "REVIEW: BLOCK",
        "schema": "x",
    }
    text = " | ".join(review.validate(bad, repo))
    assert "schema" in text
    assert "SHIP with open blocking" in text
    assert "missing location" in text
    assert "final_line" in text
    assert review.validate({**good_review("nothex"), "blocking": None}, repo)
    block_empty = {**good_review(reviewed), "verdict": "BLOCK", "final_line": "REVIEW: BLOCK"}
    assert any("no blocking issues" in p for p in review.validate(block_empty, repo))
    assert review.diff_allowed(["artifacts/review/x.json", "docs/LOG.md", "src/a.py"]) == [
        "src/a.py"
    ]


def test_headless_review_refused_under_billing_guard() -> None:
    ok, why = review.headless_available({"ANTHROPIC_API_KEY": "x"})
    assert not ok
    assert "billing guard" in why


# ---------------------------------------------------------------- style and stub


def test_style_check_finds_em_dashes(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(f"ok\nbad {EM_DASH} here\n")
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "b.md").write_text(EM_DASH)
    (tmp_path / "c.bin").write_bytes(b"\0" + EM_DASH.encode())
    hits = style_check.find_em_dashes(tmp_path, ["a.md", "tests/fixtures/b.md", "c.bin", "gone"])
    assert hits == ["a.md:2"]


def test_stub_always_fails(capsys: pytest.CaptureFixture[str]) -> None:
    assert stub.main(["stub.py", "demo", "G4"]) == 1
    assert "not built yet" in capsys.readouterr().err


# ---------------------------------------------------------------- ship-check


def test_bootstrap_ci_is_deterministic_and_brackets_point() -> None:
    values = [True] * 30 + [False] * 10
    stat = ship_check.mean_of(values)
    a = ship_check.bootstrap_ci(len(values), stat, seed=7, replicates=500)
    b = ship_check.bootstrap_ci(len(values), stat, seed=7, replicates=500)
    assert a == b
    assert a is not None
    assert a[0] <= 0.75 <= a[1]
    assert ship_check.bootstrap_ci(0, stat, 1, 10) is None
    assert ship_check.bootstrap_ci(3, lambda idx: None, 1, 10) is None


def test_ratio_and_close() -> None:
    assert ship_check.ratio(1, 0) is None
    assert ship_check.ratio(1, 4) == 0.25
    assert ship_check.close(0.25, 0.25)
    assert not ship_check.close("0.25", 0.25)
    assert ship_check.close_ci([0.1, 0.2], (0.1, 0.2))
    assert not ship_check.close_ci([0.1], (0.1, 0.2))
    assert not ship_check.close_ci([0.1, 0.2], None)


def test_headings_and_sections_skip_code_fences() -> None:
    md = "# Title\n\n## Quickstart\n```bash\n# not a heading\n```\n## Key results\nx\n### Sub\ny\n"
    assert ship_check.headings(md) == ["title", "quickstart", "key results", "sub"]
    assert "x" in ship_check.section(md, "key results")
    assert "y" in ship_check.section(md, "key results")
    assert ship_check.section(md, "absent") == ""


def test_makefile_ci_target_check(tmp_path: Path) -> None:
    mk = tmp_path / "Makefile"
    mk.write_text("ci: lint typecheck test demo ## all\n")
    assert ship_check.makefile_ci_problems(mk) == ""
    mk.write_text("ci: lint test\n")
    assert "typecheck" in ship_check.makefile_ci_problems(mk)
    mk.write_text("all:\n")
    assert "no ci target" in ship_check.makefile_ci_problems(mk)


def test_bare_type_ignores(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    marker = "# type" + ": ignore"  # split so this file does not trip the scan itself
    (tmp_path / "src" / "m.py").write_text(
        f"a = 1  {marker}[x]  # reason given\nb = 2  {marker}\nc = 3  {marker}[y]\n"
    )
    assert ship_check.bare_type_ignores(tmp_path) == ["src/m.py:2", "src/m.py:3"]


def test_junit_counts(tmp_path: Path) -> None:
    p = tmp_path / "junit.xml"
    assert ship_check.junit_counts(p) is None
    p.write_text('<testsuites><testsuite name="p" tests="5" failures="1" errors="0" skipped="2">')
    assert ship_check.junit_counts(p) == {"tests": 5, "failures": 1, "errors": 0, "skipped": 2}


def test_readme_that_is_the_brief_fails(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("# graderproof\nbrief\n")
    (tmp_path / "docs" / "BUILD_BRIEF.md").write_text("# graderproof\nbrief\n")
    assert "still the build brief" in ship_check.readme_problems(tmp_path)
    (tmp_path / "README.md").write_text(f"# graderproof {EM_DASH} x\n")
    assert "em dash" in ship_check.readme_problems(tmp_path)


def test_report_word_count_and_sections(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    assert "missing" in ship_check.report_problems(tmp_path)
    heads = "\n".join(f"## {s}\ntext" for s in ship_check.REPORT_SECTIONS)
    (tmp_path / "docs" / "REPORT.md").write_text(heads)
    assert "words" in ship_check.report_problems(tmp_path)
    (tmp_path / "docs" / "REPORT.md").write_text("## Abstract\n")
    assert "lacks sections" in ship_check.report_problems(tmp_path)


def test_citecheck_requires_verified_entries(tmp_path: Path) -> None:
    (tmp_path / "artifacts").mkdir()
    urls = ["https://arxiv.org/abs/1", "https://example.org/x"]
    assert "missing" in ship_check.citecheck_problems(tmp_path, urls)
    entries = [
        {
            "claimed": {"url": "https://arxiv.org/abs/1"},
            "final_url": "https://arxiv.org/abs/1/",
            "status": "verified",
            "retrieved_utc": "2026-10-23T00:00:00Z",
            "page_title": "t",
        },
        {"claimed": {"url": "https://example.org/x"}, "status": "unreachable"},
    ]
    (tmp_path / "artifacts" / "citecheck.json").write_text(json.dumps({"entries": entries}))
    assert "example.org" in ship_check.citecheck_problems(tmp_path, urls)
    assert ship_check.citecheck_problems(tmp_path, urls[:1]) == ""


def test_cited_urls_exclude_own_repo(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "see https://arxiv.org/abs/2. and https://github.com/raj200501/graderproof/x\n"
    )
    assert ship_check.cited_urls(tmp_path) == ["https://arxiv.org/abs/2"]


def test_git_history_helpers(tmp_path: Path) -> None:
    repo = git_repo(tmp_path)
    first = review.git(repo, "rev-parse", "HEAD")[1]
    (repo / "b.txt").write_text("b\n")
    second = commit_all(repo, "b")
    assert ship_check.first_commit(repo, "a.txt") == first
    assert ship_check.first_commit(repo, "b.txt") == second
    assert ship_check.first_commit(repo, "none.txt") is None
    assert ship_check.strictly_before(repo, first, second)
    assert not ship_check.strictly_before(repo, second, second)
    assert ship_check.earliest_commit(repo, ["b.txt", "a.txt"]) == first
    assert ship_check.earliest_commit(repo, []) is None
    assert ship_check.commits_touching(repo, "b.txt") == [second]


def test_manifest_verification(tmp_path: Path) -> None:
    repo = git_repo(tmp_path)
    assert ship_check.verify_manifest(repo)["present"] is False
    patch = repo / "private" / "outbound" / "patches" / "t.patch"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff\n")
    man = repo / "outbound" / "patches" / "MANIFEST.json"
    man.parent.mkdir(parents=True)
    rows = [
        {"path": "private/outbound/patches/t.patch", "sha256": ship_check.sha256_file(patch)},
        {"path": "private/outbound/patches/gone.patch", "sha256": "0" * 64},
        {"path": "elsewhere.patch", "sha256": "0" * 64},
    ]
    man.write_text(json.dumps({"files": rows}))
    subprocess.run(["git", "-C", str(repo), "add", "outbound"], check=True)
    result = ship_check.verify_manifest(repo)
    assert result["present"] is True
    assert "private/outbound/patches/t.patch" in result["entries"]
    assert any("gone.patch: missing" in p for p in result["problems"])
    assert any("not under private" in p for p in result["problems"])


def test_card_leak_detects_task_ids(tmp_path: Path) -> None:
    adir = tmp_path / "bench"
    adir.mkdir()
    h = ship_check.sha256_text("bench:task-7")
    (adir / "tasks.jsonl").write_text(json.dumps({"task_hash": h, "flaky": False}) + "\n")
    variant = {"task_hash": h, "kind": "violating", "counted_in_headline": True}
    (adir / "variants.jsonl").write_text(json.dumps({**variant, "grader_passed": True}) + "\n")
    assert ship_check.card_leak("bench", {"rate": 0.1}, "aggregate only", adir) == ""
    assert "flagged task" in ship_check.card_leak("bench", {}, "see task-7", adir)
    assert ship_check.card_leak("bench", {"fixed_upstream_tasks": ["task-7"]}, "task-7", adir) == ""
    assert "task-level keys" in ship_check.card_leak("bench", {"tasks": []}, "", adir)


def test_task_indicators_exclude_flaky_and_uncounted(tmp_path: Path) -> None:
    adir = tmp_path / "b"
    adir.mkdir()
    rows = [{"task_hash": "a", "flaky": False}, {"task_hash": "b", "flaky": True}]
    (adir / "tasks.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    unstable = {"task_hash": "a", "counted_in_headline": True, "grader_passed": None}
    vs = [
        {**unstable, "kind": "preserving"},
        {**unstable, "kind": "violating"},
        {
            "task_hash": "a",
            "kind": "preserving",
            "counted_in_headline": True,
            "grader_passed": False,
        },
        {
            "task_hash": "a",
            "kind": "violating",
            "counted_in_headline": False,
            "grader_passed": True,
        },
        {"task_hash": "b", "kind": "violating", "counted_in_headline": True, "grader_passed": True},
    ]
    (adir / "variants.jsonl").write_text("\n".join(json.dumps(v) for v in vs) + "\n")
    result = ship_check.task_indicators(adir)
    assert not isinstance(result, str)
    kept, fa, fr = result
    assert [t["task_hash"] for t in kept] == ["a"]
    assert fa == [False]
    assert fr == [True]
    assert ship_check.task_indicators(tmp_path / "none") == "tasks.jsonl missing or empty"


def test_one_line_and_tail() -> None:
    assert ship_check.one_line("a\n b", 10) == "a b"
    assert ship_check.one_line("x" * 20, 10) == "xxxxxxx..."
    assert ship_check.tail("one\nwarning: UV_NATIVE_TLS x\ntwo\n") == "two"
    assert ship_check.tail("") == "(no output)"
