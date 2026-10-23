"""Tests for graderproof.sandbox."""

from __future__ import annotations

from pathlib import Path

import pytest

from graderproof import sandbox as sb


def test_scrubbed_env_has_no_credentials(tmp_path: Path) -> None:
    env = sb.scrubbed_env(tmp_path, {"EXTRA": "1"})
    assert env["HOME"] == str(tmp_path)
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["EXTRA"] == "1"
    assert not any(k for k in env if "TOKEN" in k or "KEY" in k or k.startswith("AWS"))


def test_local_sandbox_runs_and_captures(tmp_path: Path) -> None:
    res = sb.LocalSandbox().run(
        ["sh", "-c", "echo out; echo err >&2; pwd; exit 3"], tmp_path, [tmp_path]
    )
    assert res.exit_status == 3
    assert "out" in res.stdout
    assert str(tmp_path) in res.stdout
    assert "err" in res.stderr
    assert res.backend == "local"
    assert not res.timed_out


def test_timeout_and_truncation(tmp_path: Path) -> None:
    lim = sb.Limits(timeout_s=0.5, output_bytes=10)
    res = sb.LocalSandbox().run(
        ["sh", "-c", "echo 0123456789abcdef; sleep 5"], tmp_path, [tmp_path], limits=lim
    )
    assert res.timed_out
    assert res.exit_status == 124
    quick = sb.LocalSandbox().run(
        ["sh", "-c", "printf 0123456789abcdef"], tmp_path, [tmp_path], limits=lim
    )
    assert quick.stdout.startswith("0123456789")
    assert "truncated" in quick.stdout


def test_missing_program_is_reported(tmp_path: Path) -> None:
    res = sb.execute(["/nonexistent/program"], {}, sb.Limits(), "test")
    assert res.exit_status == 127
    assert "could not start" in res.stderr


def test_bwrap_command_shape(tmp_path: Path) -> None:
    cmd = sb.BwrapSandbox(hidden=[tmp_path]).command(["true"], tmp_path, [tmp_path], [Path("/ro")])
    assert cmd[:5] == ["bwrap", "--ro-bind", "/", "/", "--dev"]
    assert "--unshare-net" in cmd
    assert ["--bind", str(tmp_path), str(tmp_path)] == cmd[
        cmd.index("--bind") : cmd.index("--bind") + 3
    ]
    assert ["--ro-bind", "/ro", "/ro"] in [cmd[i : i + 3] for i in range(len(cmd))]
    assert cmd[-2:] == ["--", "true"]


@pytest.mark.skipif(not sb.bwrap_works(), reason="bubblewrap not usable here")
def test_bwrap_isolates_writes_and_network(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    script = (
        "echo ok > inside.txt; "
        "(echo x > /etc/gp-escape 2>/dev/null && echo ESCAPED) || echo ro; "
        "python3 -c 'import socket; socket.create_connection((\"1.1.1.1\", 80), timeout=2)' "
        "2>/dev/null && echo NET || echo nonet"
    )
    res = sb.BwrapSandbox().run(["sh", "-c", script], ws, [ws])
    assert (ws / "inside.txt").read_text() == "ok\n"
    assert "ro" in res.stdout and "ESCAPED" not in res.stdout
    assert "nonet" in res.stdout


@pytest.mark.skipif(not sb.unshare_works(), reason="user namespaces not usable here")
def test_unshare_has_no_network(tmp_path: Path) -> None:
    code = "import socket; socket.create_connection(('1.1.1.1', 80), timeout=2)"
    res = sb.UnshareSandbox().run(["python3", "-c", code], tmp_path, [tmp_path])
    assert res.exit_status != 0
    assert sb.UnshareSandbox().isolates_writes is False


def test_docker_command_shape(tmp_path: Path) -> None:
    cmd = sb.DockerSandbox(image="img:1").command(
        ["true"], tmp_path, [tmp_path], sb.Limits(memory_mb=64)
    )
    assert cmd[:6] == ["docker", "run", "--rm", "--network", "none", "--memory"]
    assert "img:1" in cmd and cmd[-1] == "true"
    assert f"{tmp_path}:{tmp_path}" in cmd


def test_docker_run_without_daemon_fails_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sb,
        "execute",
        lambda cmd, env, lim, backend: sb.ExecResult(1, "", cmd[0], 0.0, False, backend),
    )
    res = sb.DockerSandbox(image="img").run(["true"], tmp_path, [tmp_path])
    assert res.stderr == "docker"
    assert res.backend == "docker"


def test_python_roots_include_package_source() -> None:
    roots = sb.python_roots()
    assert any((r / "graderproof").is_dir() for r in roots)


def test_best_sandbox_preference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb, "bwrap_works", lambda: True)
    assert isinstance(sb.best_sandbox(), sb.BwrapSandbox)
    monkeypatch.setattr(sb, "bwrap_works", lambda: False)
    monkeypatch.setattr(sb, "unshare_works", lambda: True)
    assert sb.best_sandbox() is None
    assert isinstance(sb.best_sandbox(require_write_isolation=False), sb.UnshareSandbox)


def test_probes_without_binaries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("graderproof.sandbox.shutil.which", lambda name: None)
    assert sb.bwrap_works() is False
    assert sb.unshare_works() is False
