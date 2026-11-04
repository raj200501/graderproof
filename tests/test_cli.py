"""Tests for graderproof.cli."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from graderproof import __version__
from graderproof.cli import (
    BUILT,
    COMMANDS,
    NOT_BUILT,
    PENDING,
    build_parser,
    confirmatory_refusal,
    main,
    parse_env,
)

ROOT = Path(__file__).resolve().parent.parent


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "graderproof" in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


@pytest.mark.parametrize("command", sorted(set(COMMANDS) - BUILT))
def test_unbuilt_commands_say_so(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([command, "x"]) == NOT_BUILT
    assert "not built yet" in capsys.readouterr().err


def test_parser_lists_every_command() -> None:
    help_text = build_parser().format_help()
    for command in COMMANDS:
        assert command in help_text


def test_audit_unknown_adapter(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["audit", "x", "--adapter", "bfcl"]) == NOT_BUILT


def write_budget(path: Path) -> None:
    path.write_text(
        "cash_usd = 0\nclaude_agent_runs_per_day = 30\nclaude_agent_max_turns = 40\n"
        "claude_single_calls_per_day = 300\nclaude_review_runs_per_day = 6\n"
        "local_model_max_params_b = 8\ndisk_floor_gb = 8\n"
    )


def test_audit_pending_models_and_ingest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_budget(tmp_path / "b.toml")
    common = [
        "--store",
        str(tmp_path / "s"),
        "--ledger",
        str(tmp_path / "l.jsonl"),
        "--budget",
        str(tmp_path / "b.toml"),
    ]
    one = tmp_path / "bench"
    one.mkdir()
    (one / "g").symlink_to(ROOT / "examples" / "demo" / "greeting")
    rc = main(
        [
            "audit",
            str(one),
            "--sandbox",
            "local",
            "--cache",
            str(tmp_path / "c"),
            "--out",
            str(tmp_path / "o"),
            *common,
        ]
    )
    assert rc == PENDING
    assert "pending" in capsys.readouterr().out
    assert main(["models", "pending", *common]) == 0
    assert "1 pending" in capsys.readouterr().out
    req = next((tmp_path / "s" / "requests").glob("*.json"))
    data = json.loads(req.read_text())
    (tmp_path / "s" / "responses").mkdir()
    bad = {"request": data["hash"], "backend": "t", "model": "m", "items": {}}
    (tmp_path / "s" / "responses" / req.name).write_text(json.dumps(bad))
    assert main(["models", "ingest", *common]) == 1
    good = {**bad, "items": {i["id"]: {"requirements": []} for i in data["items"]}}
    (tmp_path / "s" / "responses" / req.name).write_text(json.dumps(good))
    assert main(["models", "ingest", *common]) == 0
    assert "ingested" in capsys.readouterr().out


def test_demo_command_and_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    golden = ROOT / "tests" / "golden" / "demo_output.txt"
    base = [
        "demo",
        "--tasks",
        str(ROOT / "examples" / "demo"),
        "--ledger",
        str(ROOT / "artifacts" / "usage" / "ledger.jsonl"),
        "--budget",
        str(ROOT / "budget.toml"),
    ]
    assert main([*base, "--check", str(golden)]) == 0
    assert capsys.readouterr().out == golden.read_text()
    wrong = tmp_path / "wrong.txt"
    wrong.write_text("nope\n")
    assert main([*base, "--check", str(wrong)]) == 1
    assert "differs" in capsys.readouterr().err
    empty = tmp_path / "tasks"
    empty.mkdir()
    (empty / "g").symlink_to(ROOT / "examples" / "demo" / "greeting")
    assert (
        main(
            [
                "demo",
                "--tasks",
                str(empty),
                "--ledger",
                str(tmp_path / "l"),
                "--budget",
                str(ROOT / "budget.toml"),
            ]
        )
        == 1
    )


def test_confirmatory_runs_need_a_prereg_and_a_clean_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prereg").mkdir()
    (tmp_path / "prereg" / "0001-x.md").write_text("frozen\n")
    (tmp_path / "notes.md").write_text("x\n")

    def ns(prereg: str | None) -> argparse.Namespace:
        return argparse.Namespace(prereg=prereg)

    assert "--prereg" in confirmatory_refusal(ns(None), [])
    assert "--prereg" in confirmatory_refusal(ns("notes.md"), [])
    assert "--prereg" in confirmatory_refusal(ns("prereg/0002-missing.md"), [])
    assert "uncommitted" in confirmatory_refusal(ns("prereg/0001-x.md"), ["src/a.py"])
    assert "sandbox" in confirmatory_refusal(ns("prereg/0001-x.md"), [], isolated=False)
    assert confirmatory_refusal(ns("prereg/0001-x.md"), []) == ""
    assert parse_env(["A=1", "B=x=y"]) == {"A": "1", "B": "x=y"}
    with pytest.raises(SystemExit):
        parse_env(["novalue"])
