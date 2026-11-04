"""tau2-bench v1.0.1 driver for graderproof's tau2 adapter; it runs inside the sandbox.

This file is copied into the ``support/`` and ``grader/`` directories of every converted
task and run as ``$GP_TAU2_PYTHON -I tau2_driver.py <command> --root $GP_TAU2_ROOT ...``.
It imports nothing from graderproof, only the standard library and tau2 from the pinned
checkout at ``--root`` (``<root>/src``, with ``TAU2_DATA_DIR=<root>/data``). Before
importing tau2 it turns off what could reach the network or the host: litellm's remote
model cost map (``LITELLM_LOCAL_MODEL_COST_MAP=True``) and ``.env`` loading
(``PYTHON_DOTENV_DISABLED=1``). No command calls a model.

Commands:

* ``simulate``: build the domain environment from the task's initial state, execute the
  solution's tool calls in order (each followed by its tool message from the live
  environment), and write ``simulation.json``, ``.gp/trajectory.json`` (the calls with
  their results or errors), and ``.gp/state.json`` (the final database state) to
  ``--out``.
* ``grade``: evaluate ``simulation.json`` with the v1.0.1 environment, action, and
  communicate evaluators, combined over the task's ``reward_basis`` as v1.0.1's
  ``evaluate_simulation`` does for ``EvaluationType.ALL``. Prints one JSON object and
  exits 0 iff the reward is 1.0 (1 for a lower reward, 2 on an error).
* ``replay``: ``simulate`` and ``grade`` in one process for a list of tool calls, for
  re-grading recorded trajectories; writes the simulation, state, and reward as JSON.
* ``policy``: print the domain policy the environment gives the agent.

Tasks whose reward needs an LLM judge (``NL_ASSERTION`` in ``reward_basis`` with
non-empty ``nl_assertions``) are refused, never judged.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import os
import random
import sys
import traceback
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

DESCRIPTION = "Run or grade tau2-bench v1.0.1 tool calls for graderproof (no model calls)."
TIMESTAMP = "2025-01-01T00:00:00"
"""Every simulation time field (tau2 reads the clock for these), so outputs repeat exactly."""
SIMULATION_ID = "graderproof-replay"
SIMULATION_FILE = "simulation.json"
TRAJECTORY_FILE = "trajectory.json"
FINAL_MESSAGE_FILE = "final_message.txt"
STATE_DIR = ".gp"
REQUESTORS = ("assistant", "user")
CHANGE_DEPTH = 2
"""State changes are listed per table, then per record or field; deeper values are whole."""
UUID_SEED = 0
"""Seed for ``uuid.uuid4`` while calls run (telecom makes new bill ids with it)."""
EXIT_ERROR = 2
LOG_FORMAT = "{level} | {name}:{function}:{line} - {message}"
"""tau2's log lines on stderr, without loguru's clock time, so stderr repeats too."""
MODULES = {
    "message": "tau2.data_model.message",
    "simulation": "tau2.data_model.simulation",
    "tasks": "tau2.data_model.tasks",
    "toolkit": "tau2.environment.toolkit",
    "registry": "tau2.registry",
    "env_eval": "tau2.evaluator.evaluator_env",
    "action_eval": "tau2.evaluator.evaluator_action",
    "comm_eval": "tau2.evaluator.evaluator_communicate",
    "nl_eval": "tau2.evaluator.evaluator_nl_assertions",
    "evaluator": "tau2.evaluator.evaluator",
}
"""The tau2 modules the driver uses, by short name."""


class NeedsJudgeError(RuntimeError):
    """The reward needs an LLM judge (non-empty NL assertions in the basis)."""


def offline_environment(root: Path) -> dict[str, str]:
    """Environment variables for tau2 here: the pinned data, no network or .env side effects."""
    return {
        "TAU2_DATA_DIR": str(root / "data"),
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "PYTHON_DOTENV_DISABLED": "1",
    }


def load_tau2(root: Path) -> SimpleNamespace:
    """Import tau2 from ``<root>/src`` and nowhere else, logging at WARNING to stderr."""
    os.environ.update(offline_environment(root))
    src = (root / "src").resolve()
    sys.path.insert(0, str(src))
    loguru = importlib.import_module("loguru")
    loguru.logger.remove()
    loguru.logger.add(sys.stderr, level="WARNING", format=LOG_FORMAT)
    modules = {name: importlib.import_module(path) for name, path in MODULES.items()}
    origin = Path(str(sys.modules["tau2"].__file__)).resolve()
    if not origin.is_relative_to(src):
        raise RuntimeError(f"tau2 was imported from {origin}, not from {src}")
    return SimpleNamespace(**modules)


def parse_calls(data: Any) -> list[dict[str, Any]]:
    """The solution's tool calls: a list of ``{"tool", "args", "requestor"}`` objects.

    ``args`` defaults to ``{}`` and ``requestor`` to ``"assistant"``; other keys are
    kept. Raises ValueError for anything tau2 cannot represent as a tool call.
    """
    if not isinstance(data, list):
        raise ValueError("the trajectory must be a JSON list of tool calls")
    calls = []
    for i, raw in enumerate(data):
        if not isinstance(raw, dict):
            raise ValueError(f"call {i} is not a JSON object")
        tool, args = raw.get("tool"), raw.get("args") or {}
        requestor = raw.get("requestor", "assistant")
        if not isinstance(tool, str) or not tool:
            raise ValueError(f"call {i}: tool must be a non-empty string")
        if not isinstance(args, dict):
            raise ValueError(f"call {i}: args must be a JSON object")
        if requestor not in REQUESTORS:
            raise ValueError(f"call {i}: requestor must be one of {', '.join(REQUESTORS)}")
        calls.append({**raw, "tool": tool, "args": args, "requestor": requestor})
    return calls


def changes(before: Any, after: Any, depth: int = CHANGE_DEPTH) -> Any:
    """What differs from ``before`` in ``after``, as a sparse copy of ``after``.

    Objects are compared key by key ``depth`` levels deep: unchanged keys are left out,
    removed keys map to None, and a changed value below ``depth`` (or a changed list or
    scalar) is given whole.
    """
    if depth <= 0 or not (isinstance(before, dict) and isinstance(after, dict)):
        return after
    out: dict[str, Any] = {}
    for key, value in after.items():
        if key not in before:
            out[key] = value
        elif before[key] != value:
            out[key] = changes(before[key], value, depth - 1)
    out.update({key: None for key in before if key not in after})
    return out


def parsed(content: Any) -> Any:
    """A tool message's content as JSON when it parses, else as given."""
    try:
        return json.loads(content)
    except (TypeError, ValueError):
        return content


@contextmanager
def seeded_uuid4(seed: int = UUID_SEED) -> Iterator[None]:
    """Make ``uuid.uuid4`` repeatable while the block runs."""
    rng, original = random.Random(seed), uuid.uuid4

    def fake() -> uuid.UUID:
        return uuid.UUID(int=rng.getrandbits(128), version=4)

    uuid.uuid4 = fake
    try:
        yield
    finally:
        uuid.uuid4 = original


def db_dump(toolkit: Any) -> Any:
    """A toolkit's database as JSON values, or None when it has none."""
    return None if toolkit is None or toolkit.db is None else toolkit.db.model_dump(mode="json")


def simulate(
    t: SimpleNamespace,
    task: Any,
    calls: Sequence[Mapping[str, Any]],
    domain: str,
    texts: Sequence[str] = (),
) -> tuple[Any, dict[str, Any], list[dict[str, Any]]]:
    """Execute ``calls`` in order in a live environment built from the task's initial state.

    Each call becomes an assistant or user message holding one tool call, followed by the
    environment's tool message; each non-blank text in ``texts`` then becomes an
    assistant message. Returns the simulation (``AGENT_STOP``), the final state (each
    database's hash as tau2 computes it and the records that changed), and the executed
    calls with their results or errors.
    """
    msg, init = t.message, task.initial_state
    history = list(init.message_history or []) if init is not None else []
    messages: list[Any] = list(history)
    log: list[dict[str, Any]] = []
    with seeded_uuid4():
        env = t.registry.registry.get_env_constructor(domain)()
        env.set_state(
            initialization_data=None if init is None else init.initialization_data,
            initialization_actions=None if init is None else init.initialization_actions,
            message_history=history,
        )
        before = (db_dump(env.tools), db_dump(env.user_tools))
        for i, call in enumerate(calls):
            who = call["requestor"]
            args = copy.deepcopy(dict(call["args"]))  # the log keeps the arguments as given
            tc = msg.ToolCall(id=f"call_{i}", name=call["tool"], arguments=args, requestor=who)
            cls = msg.UserMessage if who == "user" else msg.AssistantMessage
            messages.append(
                cls(role=who, tool_calls=[tc], turn_idx=len(messages), timestamp=TIMESTAMP)
            )
            reply = env.get_response(tc).model_copy(
                update={"turn_idx": len(messages), "timestamp": TIMESTAMP}
            )
            messages.append(reply)
            log.append({**call, ("error" if reply.error else "result"): parsed(reply.content)})
    for text in texts:
        if text.strip():
            messages.append(
                msg.AssistantMessage(
                    role="assistant", content=text, turn_idx=len(messages), timestamp=TIMESTAMP
                )
            )
    after = (db_dump(env.tools), db_dump(env.user_tools))
    hashes = (env.get_db_hash(), env.get_user_db_hash())
    state = {
        name: None if digest is None else {"hash": digest, "changed": changes(b, a)}
        for name, digest, b, a in zip(("db", "user_db"), hashes, before, after, strict=True)
    }
    simulation = t.simulation.SimulationRun(
        id=SIMULATION_ID,
        task_id=task.id,
        timestamp=TIMESTAMP,
        start_time=TIMESTAMP,
        end_time=TIMESTAMP,
        duration=0.0,
        termination_reason=t.simulation.TerminationReason.AGENT_STOP,
        messages=messages,
    )
    return simulation, state, log


def tool_types(t: SimpleNamespace, constructor: Callable[..., Any]) -> Any:
    """Tool name to tool type, collected as v1.0.1's ``evaluate_simulation`` does."""
    types: Any = None
    try:
        env = constructor(solo_mode=False)
        if env.tools is not None:
            types = t.toolkit.get_tool_types(env.tools)
        if env.user_tools is not None:
            user = t.toolkit.get_tool_types(env.user_tools)
            if types is None:
                types = user
            else:
                types.update(user)
    except Exception:  # v1.0.1 continues with what it has
        return types
    return types


def evaluate(
    t: SimpleNamespace, simulation: Any, task: Any, domain: str, strict: bool = True
) -> Any:
    """The RewardInfo of v1.0.1's ``evaluate_simulation`` for ``EvaluationType.ALL``.

    Half duplex, no solo mode, no environment kwargs; the environment, action,
    communicate, and (empty) NL-assertion evaluators are called directly and their
    rewards multiplied over ``reward_basis`` in v1.0.1's order. ``strict`` is
    ``strict_replay`` (True in live grading, False when re-grading recorded runs).
    Raises NeedsJudgeError instead of ever calling an LLM judge.
    """
    sim, rt = t.simulation, t.tasks.RewardType
    stops = {sim.TerminationReason.AGENT_STOP, sim.TerminationReason.USER_STOP}
    if simulation.termination_reason not in stops:
        reason = simulation.termination_reason.value
        note = f"Simulation terminated prematurely. Termination reason: {reason}"
        return sim.RewardInfo(reward=0.0, reward_basis=None, info={"note": note})
    criteria = task.evaluation_criteria
    if criteria is None:
        return sim.RewardInfo(
            reward=1.0, reward_basis=None, info={"note": "No evaluation criteria"}
        )
    basis = set(criteria.reward_basis)
    if rt.NL_ASSERTION in basis and criteria.nl_assertions:
        raise NeedsJudgeError(f"task {task.id} needs an LLM judge for its NL assertions")
    messages = simulation.messages
    constructor = t.registry.registry.get_env_constructor(domain)
    env_info = t.env_eval.EnvironmentEvaluator.calculate_reward(
        environment_constructor=constructor,
        task=task,
        full_trajectory=messages,
        solo_mode=False,
        env_kwargs={},
        strict_replay=strict,
    )
    action_info = t.action_eval.ActionEvaluator.calculate_reward(
        task=task, full_trajectory=messages, tool_types=tool_types(t, constructor)
    )
    comm = t.comm_eval.CommunicateEvaluator.calculate_reward(task=task, full_trajectory=messages)
    nl_info: Any = None
    if rt.NL_ASSERTION in basis:  # no assertions: 1.0 with no model call
        nl_info = t.nl_eval.NLAssertionsEvaluator.calculate_reward(
            task=task, full_trajectory=messages
        )
    evaluated = {rt.DB, rt.ENV_ASSERTION, rt.ACTION, rt.COMMUNICATE}
    if nl_info is not None:
        evaluated.add(rt.NL_ASSERTION)
    if basis - evaluated:
        raise ValueError(
            f"Task reward_basis includes {basis - evaluated} but these were not evaluated"
        )
    reward, breakdown = 1.0, {}
    parts = (
        ({rt.DB, rt.ENV_ASSERTION}, env_info),
        ({rt.ACTION}, action_info),
        ({rt.NL_ASSERTION}, nl_info),
        ({rt.COMMUNICATE}, comm),
    )
    for bases, info in parts:
        if basis & bases:
            if info.reward_breakdown is not None:
                breakdown.update(info.reward_breakdown)
            reward *= info.reward
    return sim.RewardInfo(
        reward=reward,
        db_check=env_info.db_check,
        env_assertions=env_info.env_assertions,
        action_checks=action_info.action_checks,
        nl_assertions=None if nl_info is None else nl_info.nl_assertions,
        communicate_checks=comm.communicate_checks,
        reward_basis=criteria.reward_basis,
        reward_breakdown=breakdown,
        info={
            "env": env_info.info,
            "nl": None if nl_info is None else nl_info.info,
            "communicate": comm.info,
            "action": action_info.info,
        },
    )


def replay(
    t: SimpleNamespace,
    task: Any,
    calls: Sequence[Mapping[str, Any]],
    domain: str,
    texts: Sequence[str] = (),
    strict: bool = True,
) -> tuple[Any, dict[str, Any], Any]:
    """Simulate ``calls`` (and final ``texts``) and grade the result.

    Returns the simulation, the final state, and the RewardInfo with its components.
    """
    simulation, state, _ = simulate(t, task, calls, domain, texts)
    return simulation, state, evaluate(t, simulation, task, domain, strict)


def reward_summary(info: Any, task_id: str, domain: str) -> dict[str, Any]:
    """The grader's JSON report: the reward, whether it is 1.0, and tau2's RewardInfo."""
    dump = info.model_dump(mode="json")
    return {
        "task_id": task_id,
        "domain": domain,
        "reward": dump["reward"],
        "passed": dump["reward"] == 1.0,
        "reward_info": dump,
    }


def simulation_json(simulation: Any) -> str:
    """A simulation as tau2 JSON, without the fields that are null."""
    return str(simulation.model_dump_json(exclude_none=True, indent=2)) + "\n"


def read_solution(solution: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """The checked calls of ``trajectory.json`` and the text of ``final_message.txt``, if any."""
    calls = parse_calls(json.loads((solution / TRAJECTORY_FILE).read_text(encoding="utf-8")))
    final = solution / FINAL_MESSAGE_FILE
    return calls, [final.read_text(encoding="utf-8")] if final.is_file() else []


def load_task(t: SimpleNamespace, path: Path) -> Any:
    """A tau2 Task from a JSON task record."""
    return t.tasks.Task.model_validate(json.loads(path.read_text(encoding="utf-8")))


def cmd_simulate(args: argparse.Namespace) -> int:
    """``simulate``: write the simulation, trajectory, and state for the solution."""
    calls, texts = read_solution(args.solution)
    t = load_tau2(args.root)
    simulation, state, log = simulate(t, load_task(t, args.task), calls, args.domain, texts)
    out = Path(args.out)
    (out / STATE_DIR).mkdir(parents=True, exist_ok=True)
    (out / SIMULATION_FILE).write_text(simulation_json(simulation), encoding="utf-8")
    (out / STATE_DIR / "trajectory.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    (out / STATE_DIR / "state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True), encoding="utf-8"
    )
    return 0


def cmd_grade(args: argparse.Namespace) -> int:
    """``grade``: print the reward report; 0 iff the reward is 1.0."""
    t = load_tau2(args.root)
    task = load_task(t, args.task)
    text = Path(args.simulation).read_text(encoding="utf-8")
    simulation = t.simulation.SimulationRun.model_validate_json(text)
    info = evaluate(t, simulation, task, args.domain, strict=not args.lenient)
    report = reward_summary(info, task.id, args.domain)
    if args.crosscheck:
        check = t.evaluator.evaluate_simulation(
            simulation=simulation,
            task=task,
            evaluation_type=t.evaluator.EvaluationType.ALL,
            solo_mode=False,
            domain=args.domain,
            strict_replay=not args.lenient,
        )
        report["crosscheck_reward"] = check.reward
    print(json.dumps(report))
    return 0 if report["passed"] else 1


def cmd_replay(args: argparse.Namespace) -> int:
    """``replay``: simulate and grade a list of calls; write all three results as JSON."""
    calls = parse_calls(json.loads(Path(args.calls).read_text(encoding="utf-8")))
    texts = [Path(p).read_text(encoding="utf-8") for p in args.text]
    t = load_tau2(args.root)
    task = load_task(t, args.task)
    simulation, state, info = replay(t, task, calls, args.domain, texts, not args.lenient)
    result = {
        "simulation": json.loads(simulation_json(simulation)),
        "state": state,
        "reward": reward_summary(info, task.id, args.domain),
    }
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    """``policy``: print the policy the domain environment gives the agent."""
    t = load_tau2(args.root)
    print(t.registry.registry.get_env_constructor(args.domain)().get_policy(), end="")
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "simulate": cmd_simulate,
    "grade": cmd_grade,
    "replay": cmd_replay,
    "policy": cmd_policy,
}


def parser() -> argparse.ArgumentParser:
    """The command line."""
    p = argparse.ArgumentParser(prog="tau2_driver.py", description=DESCRIPTION)
    sub = p.add_subparsers(dest="command", required=True)
    cmds = {name: sub.add_parser(name, help=fn.__doc__) for name, fn in COMMANDS.items()}
    for sp in cmds.values():
        sp.add_argument("--root", type=Path, required=True, help="tau2-bench v1.0.1 checkout")
        sp.add_argument("--domain", required=True, help="airline, retail, or telecom")
    for name in ("simulate", "grade", "replay"):
        cmds[name].add_argument("--task", type=Path, required=True, help="tau2 task JSON")
    cmds["simulate"].add_argument("--solution", type=Path, required=True)
    cmds["simulate"].add_argument("--out", type=Path, required=True)
    cmds["grade"].add_argument("--simulation", type=Path, required=True)
    cmds["replay"].add_argument("--calls", type=Path, required=True)
    cmds["replay"].add_argument("--text", action="append", default=[], help="assistant text")
    cmds["replay"].add_argument("--out", type=Path, required=True)
    for name in ("grade", "replay"):
        cmds[name].add_argument("--lenient", action="store_true", help="strict_replay=False")
    cmds["grade"].add_argument("--crosscheck", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command; any failure is reported and gives exit status 2."""
    args = parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except Exception as exc:  # every failure is an outcome to report, not a crash
        if args.command == "grade":
            print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "passed": False}))
        print(traceback.format_exc()[-4000:], file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover - run as a script inside the sandbox
    raise SystemExit(main())
