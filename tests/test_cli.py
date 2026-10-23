"""Tests for graderproof.cli."""

from __future__ import annotations

import pytest

from graderproof import __version__
from graderproof.cli import COMMANDS, NOT_BUILT, build_parser, main


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "graderproof" in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_unbuilt_commands_say_so(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([command, "x", "--adapter", "toybench"]) == NOT_BUILT
    assert "not built yet" in capsys.readouterr().err


def test_parser_lists_every_command() -> None:
    help_text = build_parser().format_help()
    for command in COMMANDS:
        assert command in help_text
