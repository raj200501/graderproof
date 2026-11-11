#!/usr/bin/env python3
"""Environment doctor for graderproof (`make doctor`).

Detects Docker, GPU, RAM, free disk, the `claude` CLI and its login, Ollama and
other local-model runtimes, OS sandboxes, and confirmed free-tier keys. It then
derives which model backends and execution sandboxes are usable and which
fallbacks apply (docs/BUILD_BRIEF.md section 8).

It never prints the value of any environment variable, only whether a variable
is set. It never calls a model. With `--apply-caps` it may lower (never raise)
`local_model_max_params_b` in budget.toml to fit available RAM.

Stdlib only, so it runs before `make setup`.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent

# Section 8 billing guard: any of these present means Claude children are refused.
GUARD_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")
GUARD_PREFIX = "CLAUDE_CODE_USE_"
FREE_TIER_VARS = ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "GITHUB_MODELS_TOKEN")


def _run(cmd: list[str], timeout: float = 15.0) -> tuple[int, str]:
    """Run a command and return (exit code, combined output); -1 if it cannot start."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def billing_guard_triggers(env: dict[str, str], settings_paths: list[Path]) -> list[str]:
    """Return the names (never values) of everything that trips the billing guard."""
    hits = [v for v in GUARD_VARS if env.get(v)]
    hits += sorted(k for k in env if k.startswith(GUARD_PREFIX) and env[k])
    for path in settings_paths:
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("apiKeyHelper"):
            hits.append(f"apiKeyHelper in {path}")
    return hits


def settings_files() -> list[Path]:
    """Claude Code settings files that could configure an apiKeyHelper."""
    home = Path.home()
    return [
        home / ".claude" / "settings.json",
        home / ".claude" / "settings.local.json",
        REPO / ".claude" / "settings.json",
        REPO / ".claude" / "settings.local.json",
    ]


def mem_gb() -> float:
    """Total RAM in GiB (Linux /proc/meminfo, else sysctl on macOS)."""
    try:
        text = Path("/proc/meminfo").read_text()
        m = re.search(r"MemTotal:\s+(\d+) kB", text)
        if m:
            return int(m.group(1)) / 1024 / 1024
    except OSError:
        pass
    code, out = _run(["sysctl", "-n", "hw.memsize"])
    return int(out) / 1024**3 if code == 0 and out.isdigit() else 0.0


def load_budget() -> dict[str, Any]:
    path = REPO / "budget.toml"
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def recommended_local_params_b(ram_gb: float, cap: float) -> float:
    """Largest local model (billions of params, 4-bit) that fits RAM, never above the cap.

    Rule of thumb: about 0.75 GiB per billion parameters at 4-bit quantization,
    plus 4 GiB headroom for the OS, the grader sandbox, and the test suite.
    """
    fit = max(0.0, (ram_gb - 4.0) / 0.75)
    return float(min(cap, int(fit)))


def detect() -> dict[str, Any]:
    """Collect the environment report."""
    env = dict(os.environ)
    report: dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpus": os.cpu_count(),
        "ram_gb": round(mem_gb(), 1),
    }
    usage = shutil.disk_usage(REPO)
    report["free_disk_gb"] = round(usage.free / 1024**3, 1)

    pythons = {}
    for ver in ("3.11", "3.12"):
        exe = shutil.which(f"python{ver}")
        pythons[ver] = bool(exe)
    report["pythons"] = pythons
    report["uv"] = _run(["uv", "--version"])[1] if shutil.which("uv") else None

    docker: dict[str, Any] = {"client": bool(shutil.which("docker"))}
    if docker["client"]:
        code, out = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=20)
        docker["daemon"] = code == 0
        docker["server_version"] = out if code == 0 else None
    else:
        docker["daemon"] = False
    report["docker"] = docker

    gpu = None
    if shutil.which("nvidia-smi"):
        code, out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
        gpu = out if code == 0 else None
    report["gpu"] = gpu

    claude: dict[str, Any] = {"cli": bool(shutil.which("claude"))}
    if claude["cli"]:
        claude["version"] = _run(["claude", "--version"])[1].splitlines()[0:1]
        code, out = _run(["claude", "auth", "status"], timeout=30)
        try:
            status = json.loads(out) if code == 0 else {}
        except ValueError:
            status = {}
        claude["logged_in"] = bool(status.get("loggedIn"))
        claude["auth_method"] = status.get("authMethod")
    triggers = billing_guard_triggers(env, settings_files())
    claude["billing_guard_triggers"] = triggers
    claude["nested_session_markers"] = [
        k for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT") if env.get(k)
    ]
    claude["usable"] = bool(claude["cli"] and claude.get("logged_in") and not triggers)
    report["claude"] = claude

    local: dict[str, Any] = {
        "ollama_cli": bool(shutil.which("ollama")),
        "llama_cpp": bool(shutil.which("llama-cli") or shutil.which("llama-server")),
    }
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as resp:
            local["ollama_server"] = resp.status == 200
    except OSError:
        local["ollama_server"] = False
    code, _ = _run([sys.executable, "-c", "import transformers, torch"], timeout=60)
    local["transformers"] = code == 0
    local["usable"] = bool(local["ollama_server"] or local["llama_cpp"] or local["transformers"])
    report["local_models"] = local

    sandbox: dict[str, Any] = {
        "docker": docker["daemon"],
        "bwrap": bool(shutil.which("bwrap")),
        "sandbox_exec": bool(shutil.which("sandbox-exec")),
    }
    if shutil.which("unshare"):
        code, _ = _run(["unshare", "-rn", "true"])
        sandbox["unshare_netns"] = code == 0
    else:
        sandbox["unshare_netns"] = False
    if sandbox["docker"]:
        sandbox["best"] = "docker --network none"
    elif sandbox["bwrap"]:
        sandbox["best"] = "bwrap"
    elif sandbox["sandbox_exec"]:
        sandbox["best"] = "sandbox-exec"
    elif sandbox["unshare_netns"]:
        sandbox["best"] = "unshare -rn (user + network namespace) with a temp workspace"
    else:
        sandbox["best"] = None
    report["sandbox"] = sandbox

    confirmed = env.get("FREE_TIER_KEYS_CONFIRMED") == "1"
    report["free_tiers"] = {
        "confirmed": confirmed,
        "present": [v for v in FREE_TIER_VARS if env.get(v)] if confirmed else [],
    }
    report["allow_push"] = env.get("ALLOW_PUSH") == "1"
    report["cap_share"] = env.get("CAP_SHARE")

    budget = load_budget()
    cap = float(budget.get("local_model_max_params_b", 8))
    report["local_model_max_params_b"] = {
        "budget": cap,
        "recommended": recommended_local_params_b(report["ram_gb"], cap),
    }
    floor = float(budget.get("disk_floor_gb", 8))
    report["disk_floor_gb"] = floor
    report["downloads_allowed"] = report["free_disk_gb"] > floor
    report["fallbacks"] = fallbacks(report)
    return report


def fallbacks(r: dict[str, Any]) -> list[str]:
    """Plain-language consequences of what is missing."""
    out: list[str] = []
    if not r["docker"]["daemon"]:
        out.append(
            "No Docker daemon: Harbor/Terminal-Bench tasks cannot run; use a Docker-free "
            "substitute benchmark recorded in DECISIONS.md before data collection."
        )
    if not r["claude"]["usable"]:
        why = ", ".join(r["claude"]["billing_guard_triggers"]) or "CLI missing or not logged in"
        out.append(
            f"Claude backend unusable ({why}): no headless Claude subject or pipeline runs; "
            "use the reviewer/citation subagents for small jobs and local models for bulk."
        )
    if not r["local_models"]["usable"]:
        out.append(
            "No local model runtime: install one (Ollama, llama.cpp, or transformers) "
            "within the disk floor before model-dependent steps."
        )
    if r["sandbox"]["best"] is None:
        out.append("No sandbox: only this project's own generated tasks may run (section 8).")
    elif not r["sandbox"]["docker"]:
        out.append(f"Sandbox fallback: {r['sandbox']['best']}.")
    if not r["free_tiers"]["confirmed"]:
        out.append("Free tiers ignored (FREE_TIER_KEYS_CONFIRMED is not 1).")
    if not r["downloads_allowed"]:
        out.append("Free disk is at or below the floor: no downloads.")
    return out


def apply_caps(report: dict[str, Any]) -> bool:
    """Lower local_model_max_params_b in budget.toml if RAM requires it. Never raises it."""
    rec = report["local_model_max_params_b"]["recommended"]
    cur = report["local_model_max_params_b"]["budget"]
    path = REPO / "budget.toml"
    if rec >= cur or not path.exists():
        return False
    text = path.read_text()
    new = re.sub(
        r"^(local_model_max_params_b\s*=\s*)[0-9.]+",
        lambda m: f"{m.group(1)}{int(rec)}",
        text,
        count=1,
        flags=re.M,
    )
    path.write_text(new)
    return True


def render(r: dict[str, Any]) -> str:
    yes = {True: "yes", False: "no"}
    lines = [
        "graderproof doctor",
        f"  os            {r['os']} ({r['machine']}), python {r['python']}",
        f"  cpus / ram    {r['cpus']} / {r['ram_gb']} GiB",
        f"  free disk     {r['free_disk_gb']} GiB (floor {r['disk_floor_gb']})",
        f"  pythons       3.11 {yes[r['pythons']['3.11']]}, 3.12 {yes[r['pythons']['3.12']]}",
        f"  uv            {r['uv']}",
        f"  docker        client {yes[r['docker']['client']]}, daemon {yes[r['docker']['daemon']]}",
        f"  gpu           {r['gpu'] or 'none'}",
        f"  claude cli    {yes[r['claude']['cli']]}, logged in "
        f"{yes[bool(r['claude'].get('logged_in'))]}, usable {yes[r['claude']['usable']]}",
        f"  billing guard {', '.join(r['claude']['billing_guard_triggers']) or 'clear'}",
        f"  local models  ollama server {yes[r['local_models']['ollama_server']]}, llama.cpp "
        f"{yes[r['local_models']['llama_cpp']]}, transformers "
        f"{yes[r['local_models']['transformers']]}",
        f"  sandbox       {r['sandbox']['best'] or 'NONE'}",
        f"  free tiers    {'confirmed' if r['free_tiers']['confirmed'] else 'not confirmed'}"
        f" {r['free_tiers']['present']}",
        f"  allow push    {yes[r['allow_push']]}; CAP_SHARE {r['cap_share'] or 'unset'}",
        f"  local cap     {r['local_model_max_params_b']['budget']}B (fits RAM: "
        f"{r['local_model_max_params_b']['recommended']}B)",
        "fallbacks:",
    ]
    lines += [f"  - {f}" for f in r["fallbacks"]] or ["  - none"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", type=Path, help="also write the report as JSON to this path")
    ap.add_argument("--apply-caps", action="store_true", help="lower RAM-bound caps in budget.toml")
    args = ap.parse_args(argv)
    report = detect()
    if args.apply_caps and apply_caps(report):
        print("doctor: lowered local_model_max_params_b in budget.toml to fit RAM")
    print(render(report))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
