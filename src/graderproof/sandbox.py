"""Sandboxed execution for solutions, graders, and checks.

Third-party code (graders, task repositories, benchmark scripts) never runs directly
on the host. Backends, in order of preference:

* :class:`DockerSandbox`: ``docker run --network none`` (needs a daemon and an image);
* :class:`BwrapSandbox`: bubblewrap with a read-only root, writable bind mounts only
  for the workspace, no network, private PID/IPC/UTS namespaces, a tmpfs ``/tmp``, and
  the home directory and the repository's private/ directory hidden;
* :class:`UnshareSandbox`: a user and network namespace (no network, but no write
  isolation), acceptable only for this project's own generated tasks;
* :class:`LocalSandbox`: no isolation, for project-generated tasks in tests only.

Every backend runs the child with a scrubbed environment (no tokens, API keys, SSH
agent, or cloud credentials; ``GIT_CONFIG_NOSYSTEM=1``, ``GIT_CONFIG_GLOBAL=/dev/null``)
and POSIX resource limits.
"""

from __future__ import annotations

import os
import resource
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


@dataclass(frozen=True)
class Limits:
    """Resource limits for one sandboxed process."""

    timeout_s: float = 60.0
    cpu_s: int = 120
    memory_mb: int = 4096
    file_size_mb: int = 256
    output_bytes: int = 200_000


@dataclass(frozen=True)
class ExecResult:
    """Outcome of one sandboxed process."""

    exit_status: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool
    backend: str


def scrubbed_env(home: Path, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """A minimal environment for untrusted children: no credentials of any kind."""
    env = {
        "PATH": SAFE_PATH,
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "TMPDIR": "/tmp",
    }
    if extra:
        env.update(extra)
    return env


def _limit_resources(limits: Limits) -> Callable[[], None]:
    def apply() -> None:  # pragma: no cover - runs in the forked child
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_s, limits.cpu_s))
        mem = limits.memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        fsize = limits.file_size_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return apply


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[truncated {len(text) - limit} chars]"


def execute(cmd: Sequence[str], env: Mapping[str, str], limits: Limits, backend: str) -> ExecResult:
    """Run a fully built command with limits and a timeout; never raises on child failure."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            list(cmd),
            env=dict(env),
            capture_output=True,
            timeout=limits.timeout_s,
            preexec_fn=_limit_resources(limits),
            check=False,
        )
        out = proc.stdout.decode("utf-8", errors="replace")
        err = proc.stderr.decode("utf-8", errors="replace")
        status, timed_out = proc.returncode, False
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", errors="replace")
        err = (exc.stderr or b"").decode("utf-8", errors="replace")
        status, timed_out = 124, True
    except OSError as exc:
        out, err, status, timed_out = "", f"could not start {cmd[0]}: {exc}", 127, False
    return ExecResult(
        exit_status=status,
        stdout=_truncate(out, limits.output_bytes),
        stderr=_truncate(err, limits.output_bytes),
        duration_s=time.monotonic() - start,
        timed_out=timed_out,
        backend=backend,
    )


def checkouts(repo: Path) -> list[Path]:
    """``repo`` and, when it is a git worktree, the main checkout it belongs to.

    A worktree's ``.git`` is a file reading ``gitdir: <main>/.git/worktrees/<name>``.
    """
    out = [repo]
    marker = repo / ".git"
    if marker.is_file():
        text = marker.read_text(encoding="utf-8", errors="replace").strip()
        if text.startswith("gitdir:"):
            gitdir = Path(text.split(":", 1)[1].strip())
            if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
                out.append(gitdir.parents[2])
    return out


def default_hidden(repo: Path | None = None) -> list[Path]:
    """Paths bwrap hides: the home directory and the repository's private/ directories.

    private/ holds unpublished findings and the E0 labels; sandboxed task code must
    never be able to read it, including when graderproof runs from a git worktree
    (such as the frozen E0 checkout) whose main checkout holds private/.
    ``repo`` defaults to the checkout this package was loaded from.
    """
    hidden = [Path.home()]
    root = Path(__file__).resolve().parents[2] if repo is None else repo
    for checkout in checkouts(root):
        if (checkout / "pyproject.toml").exists() and (checkout / "private").is_dir():
            hidden.append(checkout / "private")
    return hidden


class Sandbox(Protocol):
    """A way to run one command with a writable workspace and no network."""

    name: str
    isolates_writes: bool

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        writable: Sequence[Path],
        readonly: Sequence[Path] = (),
        env: Mapping[str, str] | None = None,
        limits: Limits | None = None,
    ) -> ExecResult:
        """Run ``argv`` in ``cwd``; only ``writable`` paths may be written."""
        ...


@dataclass
class BwrapSandbox:
    """bubblewrap: read-only root, writable workspace binds, no network."""

    name: str = "bwrap"
    isolates_writes: bool = True
    hidden: Sequence[Path] = field(default_factory=default_hidden)

    def command(
        self, argv: Sequence[str], cwd: Path, writable: Sequence[Path], readonly: Sequence[Path]
    ) -> list[str]:
        """The bwrap command line for ``argv``."""
        cmd = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc"]
        cmd += ["--tmpfs", "/tmp"]
        for h in self.hidden:
            if h.exists():
                cmd += ["--tmpfs", str(h)]
        for keep in python_roots():
            cmd += ["--ro-bind", str(keep), str(keep)]
        for r in readonly:
            cmd += ["--ro-bind", str(r), str(r)]
        for w in writable:
            cmd += ["--bind", str(w), str(w)]
        cmd += ["--unshare-net", "--unshare-pid", "--unshare-ipc", "--unshare-uts"]
        cmd += ["--die-with-parent", "--new-session", "--chdir", str(cwd), "--", *argv]
        return cmd

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        writable: Sequence[Path],
        readonly: Sequence[Path] = (),
        env: Mapping[str, str] | None = None,
        limits: Limits | None = None,
    ) -> ExecResult:
        """Run ``argv`` under bubblewrap."""
        lim = limits or Limits()
        cmd = self.command(argv, cwd, writable, readonly)
        return execute(cmd, scrubbed_env(cwd, env), lim, self.name)


@dataclass
class UnshareSandbox:
    """User and network namespace via ``unshare -rn``: no network, no write isolation."""

    name: str = "unshare-netns"
    isolates_writes: bool = False

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        writable: Sequence[Path],
        readonly: Sequence[Path] = (),
        env: Mapping[str, str] | None = None,
        limits: Limits | None = None,
    ) -> ExecResult:
        """Run ``argv`` in a fresh network namespace."""
        lim = limits or Limits()
        cmd = ["unshare", "-rn", "--", "sh", "-c", 'cd "$0" && exec "$@"', str(cwd), *argv]
        return execute(cmd, scrubbed_env(cwd, env), lim, self.name)


@dataclass
class LocalSandbox:
    """No isolation beyond a scrubbed environment and limits (tests and own tasks only)."""

    name: str = "local"
    isolates_writes: bool = False

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        writable: Sequence[Path],
        readonly: Sequence[Path] = (),
        env: Mapping[str, str] | None = None,
        limits: Limits | None = None,
    ) -> ExecResult:
        """Run ``argv`` in ``cwd`` directly."""
        lim = limits or Limits()
        cmd = ["sh", "-c", 'cd "$0" && exec "$@"', str(cwd), *argv]
        return execute(cmd, scrubbed_env(cwd, env), lim, self.name)


@dataclass
class DockerSandbox:
    """``docker run --network none`` in a task image."""

    image: str
    name: str = "docker"
    isolates_writes: bool = True

    def command(
        self, argv: Sequence[str], cwd: Path, writable: Sequence[Path], limits: Limits
    ) -> list[str]:
        """The docker command line for ``argv``."""
        cmd = ["docker", "run", "--rm", "--network", "none", "--memory", f"{limits.memory_mb}m"]
        cmd += ["--pids-limit", "512", "--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
        for w in writable:
            cmd += ["-v", f"{w}:{w}"]
        cmd += ["-w", str(cwd), self.image, *argv]
        return cmd

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        writable: Sequence[Path],
        readonly: Sequence[Path] = (),
        env: Mapping[str, str] | None = None,
        limits: Limits | None = None,
    ) -> ExecResult:
        """Run ``argv`` in a container with no network."""
        lim = limits or Limits()
        cmd = self.command(argv, cwd, [*writable, *readonly], lim)
        return execute(cmd, scrubbed_env(cwd), lim, self.name)


def python_roots() -> list[Path]:
    """Directories the current interpreter and virtualenv need, to keep them visible."""
    roots = {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()}
    roots.add(Path(sys.executable).resolve().parent)
    roots.add(Path(__file__).resolve().parent.parent)  # the package source (editable installs)
    return sorted(roots)


def bwrap_works() -> bool:
    """Whether bubblewrap can create the namespaces it needs here."""
    if not shutil.which("bwrap"):
        return False
    probe = subprocess.run(
        ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "--", "true"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


def unshare_works() -> bool:
    """Whether an unprivileged user and network namespace can be created."""
    if not shutil.which("unshare"):
        return False
    probe = subprocess.run(["unshare", "-rn", "true"], capture_output=True, check=False)
    return probe.returncode == 0


def best_sandbox(require_write_isolation: bool = True) -> Sandbox | None:
    """The strongest available host sandbox (Docker needs an image, so it is chosen per task)."""
    if bwrap_works():
        return BwrapSandbox()
    if not require_write_isolation and unshare_works():
        return UnshareSandbox()
    return None
