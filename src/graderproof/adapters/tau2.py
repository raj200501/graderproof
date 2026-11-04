"""tau2-bench adapter: sierra-research/tau2-bench v1.0.1 as toybench ``data`` tasks (D18, D19).

tau2-bench (MIT, Copyright (c) 2025 Sierra Research) grades a customer-service agent by
replaying the tool calls of its conversation against a domain database. Following D19,
each base task of the airline, retail, and telecom domains becomes a toybench task
directory, so caching, sandboxing, requirement checks, and the trajectory operators are
shared::

    <domain>-<id>/
      task.toml                    kind = "data", third_party = true, [metadata]
      instruction.md               the domain policy and the customer's request, labeled
      solution/trajectory.json     the reference: the task's gold actions as tool calls
      solution/final_message.txt   the agent's last message (COMMUNICATE tasks only)
      support/run_solution.sh      runs tau2_driver.py simulate on the solution
      support/tau2_driver.py       a copy of graderproof.adapters.tau2_driver
      support/task.json            the task record without its evaluation criteria
      grader/grade.sh              runs tau2_driver.py grade (exit 0 iff the reward is 1.0)
      grader/tau2_driver.py        a copy of graderproof.adapters.tau2_driver
      grader/task.json             the task record, verbatim
      NOTICE.tau2-bench            tau2-bench's license notice for the copied data

Both scripts run :mod:`graderproof.adapters.tau2_driver` with the tau2 virtual
environment's Python inside the sandbox. They read two paths from the environment,
``GP_TAU2_ROOT`` (the pinned checkout) and ``GP_TAU2_PYTHON`` (the venv's ``python``),
which callers pass with ``ToybenchAdapter(extra_env=tau2_env(root, python))`` or
``graderproof audit --env``. Grading uses v1.0.1's deterministic reward components
only (DB, ENV_ASSERTION, ACTION, and the substring COMMUNICATE check); retail tasks
whose reward needs an LLM judge for NL assertions are left out and counted.

Usage::

    python -m graderproof.adapters.tau2 fetch runs/tau2/src
    python -m graderproof.adapters.tau2 venv runs/tau2/src runs/tau2/venv
    python -m graderproof.adapters.tau2 convert runs/tau2/src runs/tau2/tasks
    python -m graderproof.adapters.tau2 check runs/tau2/tasks --root runs/tau2/src \\
        --python runs/tau2/venv/bin/python --jobs 4

See docs/adapters/tau2.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from graderproof.adapters import tau2_driver as driver
from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.core import Determinism, Task, canonical_json, sha256_text
from graderproof.run import Runner
from graderproof.sandbox import Sandbox, best_sandbox

BENCHMARK = "tau2"
REPO_URL = "https://github.com/sierra-research/tau2-bench.git"
PINNED_TAG = "v1.0.1"
PINNED_COMMIT = "fc0055dc4e0a316c3f83133267fbd6faaa770992"
"""The commit the annotated tag ``v1.0.1`` (tag object ``b711c1e``) points to. The
checkout's CHANGELOG dates release 1.0.1 2026-07-15 and says its grading changes affect
only ``banking_knowledge``. D18 pins this version so E5 can re-grade released runs."""
LICENSE = "MIT"
COPYRIGHT = "Copyright (c) 2025 Sierra Research"
DOMAINS = ("airline", "retail", "telecom")
SPLIT = "base"
DOMAIN_DIR = "data/tau2/domains"
POLICY_FILES: dict[str, tuple[str, ...]] = {
    "airline": ("policy.md",),
    "retail": ("policy.md",),
    "telecom": ("main_policy.md", "tech_support_manual.md"),
}
"""Policy files per domain; telecom's agent gets the main policy and the manual tech
support policy (the ``telecom`` registry entry, not ``telecom-workflow``)."""
DATA_SHA256 = {
    "LICENSE": "e67c5aa0074dfcaefd3c3a1aedb94cb539234aecd15d5a972574e3200e6252fe",
    "uv.lock": "62d3a8c4807b89e85703b3c03f2c21048a2da9736ca83d9af6f61adc74ac5314",
    "data/tau2/domains/airline/tasks.json": (
        "ccd8ba737b4cc371415af70151187788f728d6108d0916e73bb4317b40542052"
    ),
    "data/tau2/domains/airline/split_tasks.json": (
        "b22ced4d9a9850ac9aea31c53bdcb6d6009058140bd9acc7db37c1d36222ba8b"
    ),
    "data/tau2/domains/airline/policy.md": (
        "10dc0525421521208be39cee235bba84a16e2bcba9899eb93d92cd81d2f62fc4"
    ),
    "data/tau2/domains/airline/db.json": (
        "1af9fea6e03ca7ca15a22bb3fcaf3e351393e3fc9070b6777947da8996f7531b"
    ),
    "data/tau2/domains/retail/tasks.json": (
        "8e03ebce7901bd6218e7a7dc3105faa9324091a68058f7fe61c65262868812e8"
    ),
    "data/tau2/domains/retail/split_tasks.json": (
        "ed0580ec52575b63fbf76568af42490da6ee7783ecb4aa81af46961291358f20"
    ),
    "data/tau2/domains/retail/policy.md": (
        "2c9652afbce57d6e087768d37cda64d31c53d50b3e3225cfdb791bac66466467"
    ),
    "data/tau2/domains/retail/db.json": (
        "413a65160adbdb5fde0ffc0015c49b6d70250b10c18128de169b597af7766765"
    ),
    "data/tau2/domains/telecom/tasks.json": (
        "37e562e1ae3242577407e1303b1548bc64e7ea68e37d36173e6747990ceaf8a4"
    ),
    "data/tau2/domains/telecom/split_tasks.json": (
        "605b488bb9a6acb3c7f4505240a855fdc8681d09aadb16a8f38b2efcfc5c3aec"
    ),
    "data/tau2/domains/telecom/main_policy.md": (
        "95943844a0cf11fdf0e2842b483b81d9f9338aa53235712ed131db075d086ed7"
    ),
    "data/tau2/domains/telecom/tech_support_manual.md": (
        "015a3ee49ec8c199c5e1a059c922081937b92cf3a5ea74fedbc4357816f389ba"
    ),
    "data/tau2/domains/telecom/db.toml": (
        "562d647ef9d7df8df91eafd8ee76036e707c8f9e32aaedc4a7fde06975aea2c0"
    ),
    "data/tau2/domains/telecom/user_db.toml": (
        "4886107ea0c16f8e16d74bef91cfb557de61822afe9361f5a9b241806aea2e4c"
    ),
}
"""SHA-256 of the files at :data:`PINNED_COMMIT` that conversion and grading read:
tasks, splits, policies, databases, the license, and the dependency lock file."""
DEFAULT_BASIS = ("DB", "COMMUNICATE")
"""v1.0.1's ``EvaluationCriteria.reward_basis`` default."""
TASK_TIMEOUT_S = 120
"""toybench's wall-clock limit for each of the two sandboxed processes (importing tau2
and loading a domain database takes a few seconds), with slack for a loaded machine."""
ENV_ROOT = "GP_TAU2_ROOT"
ENV_PYTHON = "GP_TAU2_PYTHON"
ENV_CROSSCHECK = "GP_TAU2_CROSSCHECK"
"""When set (to anything), the grader also runs v1.0.1's own ``evaluate_simulation`` and
reports its reward as ``crosscheck_reward``."""
DEFAULT_PYTHON = "python3.12"
"""tau2 v1.0.1 needs Python >=3.12,<3.14; the venv's base interpreter must be visible
inside the sandbox, so a system interpreter is preferred over a uv-managed one."""
SOLUTION_ENTRY = "run_solution.sh"
GRADER_ENTRY = "grade.sh"
TASK_FILE = "task.json"
NOTICE_FILE = "NOTICE.tau2-bench"
DRIVER_FILE = "tau2_driver.py"
DRIVER_SOURCE = Path(driver.__file__).read_text(encoding="utf-8")
INFO_MESSAGE = "Here is the information you asked for: {}."
CLOSING_MESSAGE = "Thank you for contacting us. Is there anything else I can help you with?"
REQUEST_FIELDS = (
    ("reason_for_call", "Reason for the call"),
    ("known_info", "What the customer knows"),
    ("unknown_info", "What the customer does not know"),
    ("task_instructions", "Instructions for the customer"),
)
"""``user_scenario.instructions`` fields shown in instruction.md, with their labels."""
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def domain_dir(source_root: Path, domain: str) -> Path:
    """The data directory of one domain in a checkout."""
    if domain not in DOMAINS:
        raise ValueError(f"unknown domain {domain!r}; expected one of {', '.join(DOMAINS)}")
    return source_root / DOMAIN_DIR / domain


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def base_tasks(source_root: Path, domain: str) -> list[dict[str, Any]]:
    """The task records of the ``base`` split of one domain, in the split file's order.

    Raises ValueError on a malformed record, a duplicate id, or a split id with no task.
    """
    d = domain_dir(source_root, domain)
    records = _read_json(d / "tasks.json")
    if isinstance(records, dict) and "tasks" in records:
        records = records["tasks"]
    by_id: dict[str, dict[str, Any]] = {}
    for n, record in enumerate(records if isinstance(records, list) else [None]):
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise ValueError(f"{d / 'tasks.json'}: record {n} is not a task with a string id")
        if record["id"] in by_id:
            raise ValueError(f"{d / 'tasks.json'}: duplicate task id {record['id']!r}")
        by_id[record["id"]] = record
    ids = _read_json(d / "split_tasks.json").get(SPLIT)
    if not isinstance(ids, list) or len(set(map(str, ids))) != len(ids):
        raise ValueError(f"{d / 'split_tasks.json'}: {SPLIT!r} is not a list of distinct ids")
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise ValueError(f"{d / 'split_tasks.json'}: no task for {SPLIT} id {missing[0]!r}")
    return [by_id[i] for i in ids]


def domain_policy(source_root: Path, domain: str) -> str:
    """The policy v1.0.1's environment gives the agent, composed as tau2 composes it."""
    d = domain_dir(source_root, domain)
    texts = [(d / name).read_text(encoding="utf-8") for name in POLICY_FILES[domain]]
    if domain == "telecom":
        main, tech = texts
        return (
            f"<main_policy>\n{main}\n</main_policy>\n"
            f"<tech_support_policy>\n{tech}\n</tech_support_policy>"
        )
    return texts[0]


def criteria(task: Mapping[str, Any]) -> dict[str, Any]:
    """A task's evaluation criteria (empty when it has none)."""
    return dict(task.get("evaluation_criteria") or {})


def reward_basis(task: Mapping[str, Any]) -> list[str]:
    """The reward components the task multiplies (v1.0.1's default when unset)."""
    if task.get("evaluation_criteria") is None:
        return []
    basis = criteria(task).get("reward_basis")
    return [str(b) for b in (DEFAULT_BASIS if basis is None else basis)]


def needs_judge(task: Mapping[str, Any]) -> bool:
    """Whether the reward needs an LLM judge: NL assertions in the basis and not empty."""
    return "NL_ASSERTION" in reward_basis(task) and bool(criteria(task).get("nl_assertions"))


def task_name(domain: str, original_id: str) -> str:
    """Directory name and toybench id of a task.

    ``<domain>-<id>`` for airline and retail (``airline-12``); telecom ids are long
    scenario strings, so ``telecom-`` plus the first 8 hex digits of their SHA-256.
    """
    if domain == "telecom":
        name = f"telecom-{sha256_text(original_id)[:8]}"
    else:
        name = f"{domain}-{original_id}"
    if not _SAFE_NAME.fullmatch(name):
        raise ValueError(f"task id {original_id!r} does not give a safe directory name")
    return name


def reference_calls(task: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The reference trajectory: the gold actions as ``{"tool", "args", "requestor"}``."""
    return [
        {
            "tool": str(a["name"]),
            "args": dict(a.get("arguments") or {}),
            "requestor": str(a.get("requestor") or "assistant"),
        }
        for a in criteria(task).get("actions") or []
    ]


def final_message(task: Mapping[str, Any]) -> str:
    """The reference final message: every ``communicate_info`` string verbatim, or a
    closing line when there is none."""
    info = [str(s) for s in criteria(task).get("communicate_info") or []]
    return INFO_MESSAGE.format(", ".join(info)) if info else CLOSING_MESSAGE


def record_sha256(task: Mapping[str, Any]) -> str:
    """SHA-256 of a task record's canonical JSON, to trace a task to its source."""
    return sha256_text(canonical_json(dict(task)))


def _request(task: Mapping[str, Any]) -> list[str]:
    instructions = (task.get("user_scenario") or {}).get("instructions")
    if isinstance(instructions, str):
        return [instructions.strip()]
    lines = []
    for key, label in REQUEST_FIELDS:
        value = (instructions or {}).get(key)
        if value:
            lines += [f"### {label}", "", str(value).strip(), ""]
    return lines[:-1]


def instruction(task: Mapping[str, Any], domain: str, policy: str) -> str:
    """The task text: what the agent is told (the policy) and what the customer wants."""
    communicate = "COMMUNICATE" in reward_basis(task)
    lines = [
        f"# tau2-bench {domain} task {task['id']}",
        "",
        f"This is task `{task['id']}` of the {domain} domain of tau2-bench {PINNED_TAG}. "
        "You are the customer service agent. Follow the domain policy below and handle "
        "the customer's request by calling the domain's tools.",
        "",
        "## What to submit",
        "",
        "`trajectory.json`: the tool calls in the order they are made, as a JSON list of "
        '`{"tool": <name>, "args": {<argument>: <value>}, "requestor": "assistant"}` '
        "objects. The calls run in that order against the live domain tools, so each call "
        "sees the effects of the calls before it.",
    ]
    if domain == "telecom":
        lines += [
            "",
            'A call with `"requestor": "user"` is an action the customer performs on '
            "their own phone with the user's tools, when the agent asks them to; "
            '`"assistant"` calls use the agent\'s tools.',
        ]
    if communicate:
        lines += [
            "",
            f"`{driver.FINAL_MESSAGE_FILE}`: the agent's last message to the customer, as "
            "plain text.",
        ]
    lines += [
        "",
        "The rest of the conversation (the customer's messages, the agent's other "
        "replies, and any confirmation the customer gives) is not part of the solution.",
        "",
        "## Domain policy",
        "",
        "The policy the agent is given, verbatim:",
        "",
        "<policy>",
        policy.rstrip("\n"),
        "</policy>",
        "",
        "## Customer request",
        "",
        "The customer's side of the task, as tau2-bench gives it to the simulated customer "
        "(it is written to the customer):",
        "",
        *_request(task),
        "",
        "## Source",
        "",
        f"tau2-bench {PINNED_TAG} ({REPO_URL.removesuffix('.git')}, commit "
        f"{PINNED_COMMIT}), {LICENSE} license, {COPYRIGHT}.",
        "",
    ]
    return "\n".join(lines)


def run_solution_script(domain: str, name: str) -> str:
    """``support/run_solution.sh`` of task ``name``: execute the solution's calls."""
    return _script(
        domain,
        name,
        f"Runs the solution of {name} (tau2-bench {PINNED_TAG}, {domain}): executes",
        "trajectory.json against a live environment and writes simulation.json,",
        ".gp/trajectory.json, and .gp/state.json to the working directory.",
        command=(
            f'simulate --root "${ENV_ROOT}" --domain {domain} --task "$here/{TASK_FILE}" '
            '--solution "$GP_SOLUTION_DIR" --out .'
        ),
    )


def grade_script(domain: str, name: str) -> str:
    """``grader/grade.sh`` of task ``name``: grade the simulation in the working directory."""
    return _script(
        domain,
        name,
        f"Grades simulation.json for {name} (tau2-bench {PINNED_TAG}, {domain}) with the",
        "v1.0.1 evaluators and no LLM call. Prints the reward as JSON; the exit status is",
        "0 iff the reward is 1.0.",
        command=(
            f'grade --root "${ENV_ROOT}" --domain {domain} --task "$here/{TASK_FILE}" '
            f"--simulation {driver.SIMULATION_FILE} ${{{ENV_CROSSCHECK}:+--crosscheck}}"
        ),
    )


def _script(domain: str, name: str, *comment: str, command: str) -> str:
    if domain not in DOMAINS or not _SAFE_NAME.fullmatch(name):
        raise ValueError(f"unsafe script parameters {domain!r}, {name!r}")
    header = "".join(f"# {line}\n" for line in comment)
    return (
        "#!/usr/bin/env bash\n"
        "# Generated by graderproof.adapters.tau2.\n"
        f"{header}"
        f"# {ENV_ROOT} is the tau2-bench checkout, {ENV_PYTHON} the python of its venv.\n"
        "set -eu\n"
        f': "${{{ENV_ROOT}:?{ENV_ROOT} is not set}}" "${{{ENV_PYTHON}:?{ENV_PYTHON} is not set}}"\n'
        'here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'export HOME="${TMPDIR:-/tmp}"\n'
        f'exec "${ENV_PYTHON}" -I "$here/{DRIVER_FILE}" {command}\n'
    )


def _toml_value(value: str | int | bool | Sequence[str]) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in value) + "]"


def task_toml(task: Mapping[str, Any], domain: str) -> str:
    """``task.toml`` for one task (toybench kind ``data``, third-party, pinned source)."""
    original = str(task["id"])
    top: dict[str, str | int | bool] = {
        "id": task_name(domain, original),
        "benchmark": BENCHMARK,
        "kind": "data",
        "third_party": True,
        "timeout_s": TASK_TIMEOUT_S,
    }
    tables: dict[str, dict[str, str | int | bool | Sequence[str]]] = {
        "solution": {"entry": SOLUTION_ENTRY},
        "grader": {"entry": GRADER_ENTRY},
        "metadata": {
            "benchmark": BENCHMARK,
            "domain": domain,
            "stratum": domain,
            "original_id": original,
            "source_repo": REPO_URL,
            "source_tag": PINNED_TAG,
            "source_commit": PINNED_COMMIT,
            "source_path": f"{DOMAIN_DIR}/{domain}/tasks.json",
            "record_sha256": record_sha256(task),
            "license": LICENSE,
            "reward_basis": reward_basis(task),
        },
    }
    lines = [f"{k} = {_toml_value(v)}" for k, v in top.items()]
    for name, table in tables.items():
        lines += ["", f"[{name}]", *(f"{k} = {_toml_value(v)}" for k, v in table.items())]
    return "\n".join(lines) + "\n"


def notice() -> str:
    """The license notice kept with every converted task (its data is copied verbatim)."""
    return (
        f"task.json, the policy text in instruction.md, and the reference trajectory are\n"
        f"taken from tau2-bench {PINNED_TAG} ({REPO_URL.removesuffix('.git')}, commit\n"
        f"{PINNED_COMMIT}), {LICENSE} license, {COPYRIGHT}.\n"
        "The MIT license text is in LICENSE at that commit.\n"
    )


def task_files(task: Mapping[str, Any], domain: str, policy: str) -> dict[str, str]:
    """Every file of one converted task, relative path to text."""
    name = task_name(domain, str(task["id"]))
    without_criteria = {k: v for k, v in task.items() if k != "evaluation_criteria"}
    files = {
        "task.toml": task_toml(task, domain),
        "instruction.md": instruction(task, domain, policy),
        NOTICE_FILE: notice(),
        f"solution/{driver.TRAJECTORY_FILE}": json.dumps(reference_calls(task), indent=2) + "\n",
        f"support/{SOLUTION_ENTRY}": run_solution_script(domain, name),
        f"support/{DRIVER_FILE}": DRIVER_SOURCE,
        f"support/{TASK_FILE}": json.dumps(without_criteria, indent=2, ensure_ascii=False) + "\n",
        f"grader/{GRADER_ENTRY}": grade_script(domain, name),
        f"grader/{DRIVER_FILE}": DRIVER_SOURCE,
        f"grader/{TASK_FILE}": json.dumps(dict(task), indent=2, ensure_ascii=False) + "\n",
    }
    if "COMMUNICATE" in reward_basis(task):
        files[f"solution/{driver.FINAL_MESSAGE_FILE}"] = final_message(task)
    return files


def write_task(task: Mapping[str, Any], domain: str, policy: str, out_dir: Path) -> Path:
    """Write one task directory under ``out_dir``, replacing an old copy; returns it."""
    task_dir = out_dir / task_name(domain, str(task["id"]))
    if task_dir.exists():
        shutil.rmtree(task_dir)
    for rel, text in task_files(task, domain, policy).items():
        path = task_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
        if rel.endswith((".sh", ".py")):
            path.chmod(0o755)
    return task_dir


@dataclass(frozen=True)
class DomainConversion:
    """What conversion did with one domain's base split."""

    domain: str
    base: int
    """Tasks in the base split."""
    converted: tuple[str, ...]
    """toybench ids written."""
    needs_judge: tuple[str, ...]
    """Original ids left out because their reward needs an LLM judge."""

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation."""
        return {
            "domain": self.domain,
            "base": self.base,
            "converted": list(self.converted),
            "needs_judge": list(self.needs_judge),
        }


@dataclass(frozen=True)
class Conversion:
    """The result of :func:`convert`."""

    domains: tuple[DomainConversion, ...]
    paths: tuple[Path, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation (without local paths)."""
        return {
            "benchmark": BENCHMARK,
            "source_repo": REPO_URL,
            "source_tag": PINNED_TAG,
            "source_commit": PINNED_COMMIT,
            "split": SPLIT,
            "domains": [d.to_dict() for d in self.domains],
        }


def convert(source_root: Path, out_dir: Path, domains: Sequence[str] = DOMAINS) -> Conversion:
    """Convert the base split of each domain into task directories under ``out_dir``.

    Tasks whose reward needs an LLM judge are left out and listed. Writes
    ``conversion.json`` beside the tasks. Raises FileExistsError if ``out_dir`` already
    holds task directories that this conversion would not write, because the toybench
    loader would pick them up too, and ValueError if two tasks get one name.
    """
    plan: list[tuple[str, dict[str, Any], str]] = []
    reports = []
    for domain in domains:
        tasks, policy = base_tasks(source_root, domain), domain_policy(source_root, domain)
        kept = [t for t in tasks if not needs_judge(t)]
        plan += [(domain, t, policy) for t in kept]
        reports.append(
            DomainConversion(
                domain,
                len(tasks),
                tuple(task_name(domain, str(t["id"])) for t in kept),
                tuple(str(t["id"]) for t in tasks if needs_judge(t)),
            )
        )
    names = [task_name(d, str(t["id"])) for d, t, _ in plan]
    if len(set(names)) != len(names):
        raise ValueError("two tasks map to one directory name")
    out_dir.mkdir(parents=True, exist_ok=True)
    stale = sorted(
        d.name for d in out_dir.iterdir() if (d / "task.toml").exists() and d.name not in names
    )
    if stale:
        raise FileExistsError(
            f"{out_dir} holds {len(stale)} task directories this conversion would not "
            f"write, for example {stale[0]}"
        )
    paths = tuple(write_task(t, d, policy, out_dir) for d, t, policy in plan)
    conversion = Conversion(tuple(reports), paths)
    (out_dir / "conversion.json").write_text(
        json.dumps(conversion.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    return conversion


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source(root: Path) -> None:
    """Raise ValueError unless every file in :data:`DATA_SHA256` matches its pinned hash."""
    bad = [
        rel
        for rel, digest in DATA_SHA256.items()
        if not (root / rel).is_file() or sha256_file(root / rel) != digest
    ]
    if bad:
        raise ValueError(f"{root}: {len(bad)} files differ from {PINNED_TAG}, first {bad[0]}")


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    proc = subprocess.run(["git", *args], capture_output=True, text=True, check=False, env=env)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[-500:]}")
    return proc


def source_commit(root: Path) -> str | None:
    """The commit checked out at ``root``, or None when it is not a git checkout."""
    proc = _git("-C", str(root), "rev-parse", "HEAD", check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def fetch(dest: Path) -> Path:
    """Shallow-clone tau2-bench into ``dest`` at :data:`PINNED_TAG` and verify it.

    Reuses an existing checkout. Checks that HEAD is :data:`PINNED_COMMIT` and that the
    pinned files match :data:`DATA_SHA256`. Runs no code from the repository.
    """
    if not (dest / ".git").exists():
        if dest.exists() and any(dest.iterdir()):
            raise FileExistsError(f"{dest} exists and is not a git checkout")
        _git("clone", "--quiet", "--depth", "1", "--branch", PINNED_TAG, REPO_URL, str(dest))
    if source_commit(dest) != PINNED_COMMIT:
        _git("-C", str(dest), "fetch", "--quiet", "--depth", "1", "origin", "tag", PINNED_TAG)
        _git("-C", str(dest), "checkout", "--quiet", "--detach", PINNED_COMMIT)
    head = source_commit(dest)
    if head != PINNED_COMMIT:
        raise RuntimeError(f"{dest}: HEAD is {head}, expected {PINNED_COMMIT}")
    verify_source(dest)
    return dest


def venv_commands(source_root: Path, venv: Path, python: str) -> list[list[str]]:
    """The commands that build the tau2 venv: the locked dependencies, not tau2 itself.

    tau2 is imported from the checkout by the driver, so nothing from the repository is
    built or run; bytecode is compiled ahead so each sandboxed run imports quickly.
    """
    sync = ["uv", "sync", "--frozen", "--no-dev", "--no-install-project", "--compile-bytecode"]
    return [
        ["uv", "venv", "--python", python, str(venv)],
        [*sync, "--project", str(source_root)],
        [str(venv / "bin" / "python"), "-I", "-m", "compileall", "-q", str(source_root / "src")],
    ]


def build_venv(source_root: Path, venv: Path, python: str | None = None) -> Path:
    """Create (or update) the tau2 venv with ``uv``; returns its ``python``.

    ``python`` defaults to :data:`DEFAULT_PYTHON` on PATH. Needs network access to PyPI.
    """
    interpreter = python or shutil.which(DEFAULT_PYTHON)
    if not interpreter:
        raise RuntimeError(f"{DEFAULT_PYTHON} not found; pass --python")
    commands = venv_commands(source_root, venv, interpreter)
    if (venv / "bin" / "python").exists():
        commands = commands[1:]
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(venv.absolute())}
    for cmd in commands:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd[:2])} failed: {proc.stderr.strip()[-500:]}")
    return venv / "bin" / "python"


def tau2_env(root: Path, python: Path, crosscheck: bool = False) -> dict[str, str]:
    """The ``extra_env`` the converted tasks need (absolute paths; the venv link is kept)."""
    env = {ENV_ROOT: str(root.absolute()), ENV_PYTHON: str(python.absolute())}
    if crosscheck:
        env[ENV_CROSSCHECK] = "1"
    return env


def grade_report(stdout: str) -> dict[str, Any]:
    """The grader's JSON report (its last JSON object line), or ``{}`` when there is none."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            report = json.loads(line)
        except ValueError:
            continue
        if isinstance(report, dict):
            return report
    return {}


@dataclass(frozen=True)
class ReferenceCheck:
    """How one task's grader treated the unmodified reference over repeated runs."""

    task_id: str
    domain: str
    determinism: Determinism
    reward: float | None
    """The reward of the last run (None when the grader printed no report)."""
    crosscheck_reward: float | None = None
    """v1.0.1 ``evaluate_simulation``'s reward of the last run, when cross-checked."""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation."""
        return {
            "task_id": self.task_id,
            "domain": self.domain,
            "determinism": self.determinism.value,
            "reward": self.reward,
            "crosscheck_reward": self.crosscheck_reward,
            "error": self.error,
        }


def _natural(task_id: str) -> tuple[str, int, str]:
    stem, _, tail = task_id.rpartition("-")
    return (stem, int(tail), "") if tail.isdigit() else (stem, -1, tail)


def check_references(
    tasks_dir: Path,
    env: Mapping[str, str],
    sandbox: Sandbox,
    repeat: int = 1,
    jobs: int = 1,
    cache_dir: Path | None = None,
) -> list[ReferenceCheck]:
    """Grade every converted reference ``repeat`` times (the :class:`Runner` precheck).

    ``env`` is the adapter's ``extra_env`` (:func:`tau2_env`). Tasks are third-party, so
    the Runner refuses a sandbox that does not isolate writes. Up to ``jobs`` tasks run at
    once. The result is ordered by domain and then by id.
    """
    adapter = ToybenchAdapter(extra_env=dict(env))
    runner = Runner(adapter, sandbox, cache_dir=cache_dir)

    def one(task: Task) -> ReferenceCheck:
        det, runs = runner.precheck(task, repeat)
        grade = runs[-1].grade
        report = grade_report(grade.stdout)
        error = str(report.get("error") or "")
        if not report and not grade.passed:
            error = (grade.stderr.strip() or "no report")[-300:]
        return ReferenceCheck(
            task.id,
            str(task.metadata.get("domain", "")),
            det,
            report.get("reward"),
            report.get("crosscheck_reward"),
            error,
        )

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        checks = list(pool.map(one, adapter.load(tasks_dir)))
    return sorted(checks, key=lambda c: (c.domain, _natural(c.task_id)))


def domain_summary(checks: Sequence[ReferenceCheck]) -> dict[str, dict[str, Any]]:
    """Per domain: tasks, references at reward 1.0 in every run, and the other ids."""
    out: dict[str, dict[str, Any]] = {}
    for c in checks:
        row = out.setdefault(c.domain, {"tasks": 0, "reward_1": 0, "failures": []})
        row["tasks"] += 1
        if c.determinism is Determinism.STABLE_PASS and c.reward == 1.0:
            row["reward_1"] += 1
        else:
            row["failures"].append(c.task_id)
    return out


def crosscheck_mismatches(checks: Sequence[ReferenceCheck]) -> list[str]:
    """Ids whose reward differs from v1.0.1's own ``evaluate_simulation`` reward."""
    return [c.task_id for c in checks if c.crosscheck_reward != c.reward]


def _cmd_check(args: argparse.Namespace) -> int:
    sandbox = best_sandbox()
    if sandbox is None:
        print("tau2: no write-isolating sandbox (bubblewrap) works here", file=sys.stderr)
        return 1
    commit = source_commit(args.root)
    if commit != PINNED_COMMIT:
        print(f"tau2: {args.root} is at {commit}, not {PINNED_COMMIT}", file=sys.stderr)
        return 1
    verify_source(args.root)
    env = tau2_env(args.root, args.python, args.crosscheck)
    checks = check_references(args.tasks, env, sandbox, args.repeat, args.jobs, args.cache)
    for c in checks:
        extra = f" crosscheck={c.crosscheck_reward}" if args.crosscheck else ""
        tail = f" error={c.error}" if c.error else ""
        print(f"{c.task_id} {c.determinism.value} reward={c.reward}{extra}{tail}")
    summary = domain_summary(checks)
    for domain, row in summary.items():
        failures = " ".join(row["failures"]) or "none"
        print(
            f"{domain}: {row['tasks']} tasks, {row['reward_1']} at reward 1.0; others: {failures}"
        )
    mismatches = crosscheck_mismatches(checks) if args.crosscheck else []
    if args.crosscheck:
        print("crosscheck mismatches: " + (" ".join(mismatches) or "none"))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        data = {"sandbox": sandbox.name, "repeat": args.repeat, "summary": summary}
        data["checks"] = [c.to_dict() for c in checks]
        args.json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    failed = any(row["failures"] for row in summary.values())
    return 0 if checks and not failed and not mismatches else 1


def _cmd_convert(args: argparse.Namespace) -> int:
    verify_source(args.src)
    conversion = convert(args.src, args.out)
    parts = []
    for d in conversion.domains:
        judge = f" ({len(d.needs_judge)} need an LLM judge)" if d.needs_judge else ""
        parts.append(f"{d.domain} {len(d.converted)} of {d.base}{judge}")
    print(f"converted {len(conversion.paths)} tau2 tasks into {args.out}: " + ", ".join(parts))
    return 0


def _cmd_fetch(args: argparse.Namespace) -> int:
    print(fetch(args.dest))
    return 0


def _cmd_venv(args: argparse.Namespace) -> int:
    print(build_venv(args.src, args.venv, args.python))
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "fetch": _cmd_fetch,
    "venv": _cmd_venv,
    "convert": _cmd_convert,
    "check": _cmd_check,
}


def parser() -> argparse.ArgumentParser:
    """The command line."""
    p = argparse.ArgumentParser(
        prog="python -m graderproof.adapters.tau2",
        description="Fetch tau2-bench v1.0.1, build its venv, convert its base tasks into "
        "toybench tasks, and check that every reference reaches reward 1.0.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    p_fetch = sub.add_parser("fetch", help="clone tau2-bench at the pinned tag and verify it")
    p_fetch.add_argument("dest", type=Path)
    p_venv = sub.add_parser("venv", help="build the tau2 venv from the checkout's uv.lock")
    p_venv.add_argument("src", type=Path, help="the pinned checkout")
    p_venv.add_argument("venv", type=Path)
    p_venv.add_argument("--python", help=f"base interpreter (default {DEFAULT_PYTHON})")
    p_convert = sub.add_parser("convert", help="write one toybench task directory per task")
    p_convert.add_argument("src", type=Path, help="the pinned checkout")
    p_convert.add_argument("out", type=Path)
    p_check = sub.add_parser("check", help="grade every converted reference under bubblewrap")
    p_check.add_argument("tasks", type=Path, help="directory of converted tasks")
    p_check.add_argument("--root", type=Path, required=True, help="the pinned checkout")
    p_check.add_argument("--python", type=Path, required=True, help="the tau2 venv's python")
    p_check.add_argument("--repeat", type=int, default=1, help="runs per reference")
    p_check.add_argument("--jobs", type=int, default=1, help="tasks run at once")
    p_check.add_argument("--cache", type=Path, help="Runner cache directory")
    p_check.add_argument("--crosscheck", action="store_true", help="also run evaluate_simulation")
    p_check.add_argument("--json", type=Path, help="write the results here")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """Command line; returns the exit status."""
    p = parser()
    args = p.parse_args(argv)
    if args.command == "check" and (args.repeat < 1 or args.jobs < 1):
        p.error("--repeat and --jobs must be at least 1")
    try:
        return COMMANDS[args.command](args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"tau2: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
