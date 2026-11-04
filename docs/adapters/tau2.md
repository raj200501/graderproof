# tau2-bench adapter

`graderproof.adapters.tau2` converts the base tasks of the airline, retail, and telecom
domains of [sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench)
into toybench task directories of kind `data` (DECISIONS.md D18, D19). tau2-bench grades
a customer-service agent by replaying the tool calls of its conversation against a
domain database and checking the result. The adapter turns each task's gold tool calls
into a reference solution and grades every solution with tau2-bench's own v1.0.1
evaluators inside bubblewrap, with no model call. The benchmark name is `tau2`.

The sandboxed half of the adapter is `graderproof.adapters.tau2_driver`, a standalone
module (standard library plus tau2) that is copied into every converted task.

## Source and pinned version

| Item | Value |
|---|---|
| Repository | https://github.com/sierra-research/tau2-bench (`git clone --depth 1 --branch v1.0.1 https://github.com/sierra-research/tau2-bench.git`) |
| Pinned tag | `v1.0.1`, an annotated tag (tag object `b711c1e`) on commit `fc0055dc4e0a316c3f83133267fbd6faaa770992`. The checkout's `CHANGELOG.md` dates release 1.0.1 2026-07-15 and states that its grading changes affect only `banking_knowledge`. |
| Files read | `data/tau2/domains/<domain>/` (`tasks.json`, `split_tasks.json`, the policies, the databases), `uv.lock`, and `LICENSE`. Their SHA-256 values are pinned in `DATA_SHA256`; `fetch`, `convert`, and `check` verify them. |
| Code run | `src/tau2` from the checkout, imported by the driver inside bubblewrap. Its dependencies come from the checkout's `uv.lock`. |
| Retrieval | Cloned with git and verified on 2026-11-04. |

D18 pins v1.0.1 so that E5 can re-grade released runs with the evaluator they were
scored with. The benchmark survey (docs/research/benchmarks_survey_2026-10-23.md,
section 1) describes the later 2.0.0 release and why it is not used.

## License and attribution

tau2-bench, data included, is under the MIT License, Copyright (c) 2025 Sierra Research
(`LICENSE` at the pinned commit). A converted task copies tau2-bench data verbatim (the
task record, the policy text, and the gold actions), so every task directory carries
`NOTICE.tau2-bench` with the attribution, and `instruction.md` ends with a source line.
The fixtures in `tests/fixtures/tau2/` include upstream's `LICENSE`. The checkout, the
virtual environment, and the converted tasks live under `runs/`, which git ignores, so
this repository redistributes only the four fixture records and the policy files under
`tests/fixtures/tau2/`.

## Commands

```
uv run python -m graderproof.adapters.tau2 fetch runs/tau2/src
uv run python -m graderproof.adapters.tau2 venv runs/tau2/src runs/tau2/venv
uv run python -m graderproof.adapters.tau2 convert runs/tau2/src runs/tau2/tasks
uv run python -m graderproof.adapters.tau2 check runs/tau2/tasks --root runs/tau2/src \
    --python runs/tau2/venv/bin/python --repeat 2 --jobs 4 --crosscheck \
    --cache runs/tau2/cache-check --json runs/tau2/check.json
```

* `fetch DEST` makes a shallow clone of the tag, fetches the tag again if `HEAD` is
  elsewhere, checks out the pinned commit detached, and verifies `HEAD` and the pinned
  files. It runs no code from the repository. An existing checkout is reused.
* `venv SRC VENV [--python P]` creates the venv with `uv venv` from `P` (default
  `python3.12` on `PATH`), installs exactly the locked runtime dependencies with
  `uv sync --frozen --no-dev --no-install-project --compile-bytecode`, and byte-compiles
  the checkout's `src/`. tau2 itself is neither built nor installed: the driver imports it
  from the checkout, so `GP_TAU2_ROOT` alone decides which tau2 code runs. This step needs
  network access to PyPI and runs no tau2 code. The base interpreter must be a system
  one, because bubblewrap hides the home directory and with it uv-managed interpreters.
  Byte-compiling matters because the sandbox root is read-only and graderproof sets
  `PYTHONDONTWRITEBYTECODE`; without it every sandboxed run compiles all of tau2 and its
  dependencies again, several times slower.
* `convert SRC OUT` verifies the pinned files and writes one task directory per kept task
  plus `conversion.json` (per domain: the base count, the converted ids, and the original
  ids left out because their reward needs an LLM judge). It refuses an `OUT` that holds
  task directories it would not write, because the toybench loader would load them too.
* `check TASKS --root SRC --python PY` checks that both paths are visible inside
  bubblewrap (see below), that the checkout is at the pinned commit, and that the pinned
  files match, then grades every unmodified reference `--repeat` times
  through `graderproof.run.Runner.precheck` with `ToybenchAdapter(extra_env=...)` and
  bubblewrap, `--jobs` tasks at a time. It prints each task's determinism class and
  reward, a per-domain summary that lists by id every task that is not a stable reward of
  1.0, and, with `--crosscheck`, the ids whose reward differs from tau2's own
  `evaluate_simulation`. `--json` writes the same results. The exit status is 0 only if
  every reference reaches 1.0 on every run and agrees with the cross-check.

The Python functions are `fetch(dest)`, `build_venv(source_root, venv, python)`,
`convert(source_root, out_dir)` (returns a `Conversion`), `check_references(tasks_dir,
env, sandbox, repeat, jobs, cache_dir)`, and `tau2_env(root, python, crosscheck)`, which
builds the `extra_env` mapping.

## Running converted tasks in graderproof

Both task scripts read two environment variables, which the caller passes through the
toybench adapter:

```
graderproof audit runs/tau2/tasks --sandbox bwrap \
    --env GP_TAU2_ROOT=/home/user/graderproof/runs/tau2/src \
    --env GP_TAU2_PYTHON=/home/user/graderproof/runs/tau2/venv/bin/python ...
```

or, in Python, `ToybenchAdapter(extra_env=tau2_env(root, python))`. Give absolute paths.
`GP_TAU2_PYTHON` must be the venv's own `bin/python` link, not the interpreter it points
to, or the venv's packages are not found. Both paths must also be visible inside the
sandbox: bubblewrap mounts an empty `/tmp` and hides the home directory (the `hidden`
list of `BwrapSandbox`), and the toybench adapter binds back only the task's own
directories, so the checkout and the venv must lie under neither. `runs/tau2/` qualifies
here because this repository is not under the home directory; on a machine where it is,
put them elsewhere. `check` refuses hidden paths with a message; `graderproof audit` does
not check them, and every execution would then fail. Setting `GP_TAU2_CROSSCHECK=1` as well makes the
grader also run v1.0.1's `evaluate_simulation` and print its reward. The tasks are
`third_party`, so the Runner refuses a sandbox that does not isolate writes. Each
execution starts two sandboxed processes that each import tau2 and load a domain database,
a few seconds each, so `timeout_s` is 120.

## Selection and ids

| Domain | Tasks taken | Left out | `reward_basis` of the kept tasks |
|---|---|---|---|
| airline | the 50 ids of `base` in `split_tasks.json` | none | `[DB, COMMUNICATE]` |
| retail | the 114 ids of `base` | the 40 with `NL_ASSERTION` in `reward_basis` and non-empty `nl_assertions` (74 kept) | `[DB, NL_ASSERTION]` with no assertions, or `[DB]` |
| telecom | the 114 ids of `base` (of the 2,285 tasks in `tasks.json`) | none | `[ENV_ASSERTION]` or `[ENV_ASSERTION, ACTION]` |

These counts are properties of the pinned data, as recorded in D18; `conversion.json`
lists the ids. Airline and retail tasks are named `<domain>-<id>` (`airline-7`). Telecom
ids are long scenario strings such as
`[mms_issue]bad_network_preference|user_abroad_roaming_disabled_on[PERSONA:None]`, so
telecom tasks are named `telecom-` plus the first 8 hex digits of the id's SHA-256; a
task keeps its name in any subset (the fixtures use the real names), and conversion
fails if two names collide. `[metadata] original_id` holds the tau2 id, and `domain` and
`stratum` hold the domain. The `mock` and `banking_knowledge` domains, the
`telecom-workflow` policy variant, telecom's other splits, and the voice task files are
not converted.

## Task layout

```
<name>/
  task.toml                    id, benchmark = "tau2", kind = "data", third_party = true,
                               timeout_s, [solution] entry, [grader] entry, [metadata]
  instruction.md               the task text (below)
  solution/trajectory.json     the reference tool calls
  solution/final_message.txt   the agent's last message (tasks with COMMUNICATE only)
  support/run_solution.sh      runs tau2_driver.py simulate
  support/tau2_driver.py       copy of src/graderproof/adapters/tau2_driver.py
  support/task.json            the task record without evaluation_criteria
  grader/grade.sh              runs tau2_driver.py grade
  grader/tau2_driver.py        copy of src/graderproof/adapters/tau2_driver.py
  grader/task.json             the task record, verbatim
  NOTICE.tau2-bench            attribution for the copied data
```

`[metadata]` holds `benchmark`, `domain`, `stratum`, `original_id`, `source_repo`,
`source_tag`, `source_commit`, `source_path`, `record_sha256` (SHA-256 of the record's
canonical JSON), `license`, and `reward_basis`. The scripts embed only the domain and
the task's safe name, never text from the task record. Because the driver is copied into
each task, a driver change changes every task's content hash, and the Runner's cache
does not serve executions made with an older driver.

## Task text

`instruction.md` states what is submitted, then the domain policy verbatim between
`<policy>` and `</policy>` lines, as tau2's LLM agent receives it in its system prompt
(airline and retail: `policy.md`; telecom: `main_policy.md` and `tech_support_manual.md`,
wrapped in `<main_policy>` and `<tech_support_policy>` tags exactly as tau2's environment
builds it, which a live test compares with the environment's own `get_policy()`), then
the customer's request: the `user_scenario.instructions` fields (reason for the call,
what the customer knows, what the customer does not know, and the instructions for the
customer), labeled as written to the simulated customer. It does not include the persona
(how the simulated customer behaves), the telecom `ticket` (used only in solo mode), the
`description` notes, the tool schemas, or anything from `evaluation_criteria` (gold
actions, environment assertions, `communicate_info`, `nl_assertions`); a test checks that
no NL assertion appears in the task text.

## Reference solution

* `trajectory.json` is `evaluation_criteria.actions` in order, each as
  `{"tool": name, "args": arguments, "requestor": requestor}`, with `"assistant"` when
  the action has no requestor (airline and retail actions omit it). `action_id`, `info`,
  and `compare_args` are grading data and are left out. The file uses two-space JSON
  indentation, as graderproof's trajectory operators write it. The driver and the
  operators keep any extra keys of a call.
* `final_message.txt` exists for tasks with `COMMUNICATE` in `reward_basis` (all of
  airline). It is `Here is the information you asked for: <strings>.` with the
  `communicate_info` strings joined by `, `, or a closing line when there are none. No
  `communicate_info` string of these tasks contains a comma, so v1.0.1's check (each
  string, lowercased, is a substring of an assistant message that is lowercased with its
  commas removed) finds every one.
* tau2's gold trajectories are not guaranteed correct: v1.0.1's environment evaluator
  logs and skips a gold action that raises. `check` grades every reference before any
  variant is considered.

## Solution run

`support/run_solution.sh` runs
`$GP_TAU2_PYTHON -I tau2_driver.py simulate --root $GP_TAU2_ROOT --domain <domain>
--task support/task.json --solution $GP_SOLUTION_DIR --out .` in the workspace:

1. It reads `trajectory.json` before importing tau2 and checks it: a JSON list of objects
   with a non-empty string `tool`, an object `args` (missing or null means `{}`), and
   `requestor` `assistant` or `user` (default `assistant`). Anything else is a malformed
   solution: exit status 2 and no simulation, so the grader rejects it.
2. It sets `TAU2_DATA_DIR=<root>/data`, `LITELLM_LOCAL_MODEL_COST_MAP=True` (litellm
   otherwise fetches its model cost map at import), and `PYTHON_DOTENV_DISABLED=1` (tau2
   and litellm call `load_dotenv()` at import), puts `<root>/src` first on `sys.path`, and
   checks that tau2 was imported from there. tau2's warnings go to stderr without
   timestamps. The script sets `HOME` to `$TMPDIR`, so no cache is written into the
   workspace.
3. It builds the environment with tau2's registry constructor for the domain, as live
   runs do, and calls `set_state` with the task's `initial_state` (initialization data,
   initialization actions, and message history).
4. Each call `i` becomes an assistant message (a user message for `"requestor": "user"`)
   holding `ToolCall(id="call_<i>", name, arguments, requestor)`, followed by the live
   environment's tool message from `get_response`. A failing call (an unknown tool, bad
   arguments, a policy error raised by the tool) gives an error tool message, as in a live
   run, and later calls still run.
5. A non-blank `final_message.txt` becomes a final assistant text message.
6. `simulation.json` is a tau2 `SimulationRun` with termination reason `agent_stop`, the
   task's message history followed by the new messages, a fixed timestamp
   (`2025-01-01T00:00:00`) in every time field, fixed ids, and null fields omitted. While
   the calls run, `uuid.uuid4` is seeded, because telecom creates new bill ids with it;
   outcomes then repeat exactly. `refuel_data`, the only tool that creates such a bill,
   does not return the id, so the grader's replay, which runs tau2's unseeded code,
   compares the same tool outputs.
7. `.gp/trajectory.json` lists each call as given plus `"result"` (the tool message
   content, parsed as JSON when it parses) or `"error"`.
8. `.gp/state.json` is `{"db": {"hash", "changed"}, "user_db": {"hash", "changed"} or
   null}`. `hash` is tau2's `get_db_hash()` (the value the DB check compares). `changed`
   holds what differs from the state right after initialization: per table, then per
   record (or per field of a nested object such as the telecom phone), with a changed list
   (telecom's tables are lists) or a deeper value given whole and a removed key mapped to
   null. The full airline and retail databases are several megabytes each, which would
   make every cached execution and every requirement-extraction request that large; given
   the fixed initial state, the changed records and the hash determine the final state.

The solution run gets `support/task.json`, the record without `evaluation_criteria`, so it
never sees grading data.

## Grading

`grader/grade.sh` runs `$GP_TAU2_PYTHON -I tau2_driver.py grade --root $GP_TAU2_ROOT
--domain <domain> --task grader/task.json --simulation simulation.json` in the
workspace. The driver loads the verbatim task record as a tau2 `Task` and
`simulation.json` as a `SimulationRun`, then computes what v1.0.1's
`evaluate_simulation(simulation, task, EvaluationType.ALL, solo_mode=False, domain)`
computes in a live run (half duplex, no environment kwargs, `strict_replay=True`), by
calling its evaluators directly in the same order:

* A termination reason other than `agent_stop` or `user_stop` gives reward 0; a task
  without evaluation criteria gives 1.
* `EnvironmentEvaluator`: a predicted environment replays the simulation's mutating calls
  (with `strict_replay`, a replayed call must return the recorded tool output) and a gold
  environment replays the gold actions. `DB` is 1 if the agent and user database hashes of
  both match; `ENV_ASSERTION` is the product of the environment assertions run on the
  predicted environment.
* `ActionEvaluator`: every gold action must match some call in the simulation, with the
  same name and equal values on `compare_args` or, when that is unset, on the argument
  names of the call itself. Order and extra calls are ignored.
* `CommunicateEvaluator`: the substring check described above.
* `NLAssertionsEvaluator` runs only when `NL_ASSERTION` is in `reward_basis` and the task
  has no assertions, where it returns 1 without a model call. A task with assertions is
  refused (`NeedsJudgeError`, exit status 2) instead of judged, so no code path reaches
  the LLM judge. Conversion leaves such tasks out.
* The reward is the product of the components in `reward_basis`, multiplied and merged
  into `reward_breakdown` in v1.0.1's order (environment, action, NL, communicate); a
  basis component that was not evaluated is an error, as in v1.0.1.

The grader prints one JSON object: `task_id`, `domain`, `reward`, `passed`, and
`reward_info` (tau2's `RewardInfo` as JSON), plus `crosscheck_reward` when
`GP_TAU2_CROSSCHECK` is set. The cross-check calls `evaluate_simulation` itself, which
for these tasks makes no model call either. The exit status is 0 iff the reward is 1.0,
1 for a lower reward, and 2 on an error (a missing or malformed `simulation.json`, a
strict-replay mismatch, a refused task), with `{"error": ..., "passed": false}` printed.

## Re-grading recorded tool calls (E5)

`replay(t, task, calls, domain, texts, strict)` in the driver simulates a list of tool
calls followed by assistant texts and grades the result in one process, returning the
simulation, the final state, and the `RewardInfo` with its components. From the command
line: `tau2_driver.py replay --root ROOT --domain D --task task.json --calls calls.json
[--text FILE]... [--lenient] --out result.json`, run with the tau2 venv's python inside
the sandbox. `--lenient` sets `strict_replay=False`, as `tau2 evaluate-trajs` does when it
re-grades. Replay re-executes the calls against the v1.0.1 tools, so tool outputs come
from the pinned code, not from the recording; to grade a recorded `SimulationRun` as it
is, use `tau2_driver.py grade --lenient --simulation FILE`.

## Tests

`tests/contract/test_tau2.py` runs offline on verbatim fixtures (see
`tests/fixtures/tau2/README.md`). It covers conversion and every generated file, loading
by `ToybenchAdapter`, the real shell scripts run with a stand-in interpreter that checks
the driver's arguments and serves driver outputs recorded from live runs, `check` and its
summaries, `fetch` against a local git repository, the venv commands, the command line,
and the driver's logic against a small fake of the tau2 API. Live tests, skipped unless
`GP_TAU2_ROOT` and `GP_TAU2_PYTHON` are set and bubblewrap works, run the real driver:
each fixture reference reaches reward 1.0 and dropping one mutating call gives 0, both in
agreement with `evaluate_simulation`; repeated runs give identical outcomes; each domain's
composed policy equals the environment's; and `replay` works. With `GP_TAU2_RECORD=1` the
live tests rewrite the recordings, and the offline tests refuse recordings made with a
different driver.

## Verification on the full data

Reproduce with the four commands above. `check` grades every reference through the Runner
under bubblewrap, cross-checks it against `evaluate_simulation`, and lists by id every
task that does not reach a stable reward of 1.0. Its output is not yet banked under
`artifacts/` by a committed script, so this document states no result numbers
(non-negotiable 1).

## Limitations

* **The conversation is not part of the solution.** The policies require conversational
  steps that are not tool calls. Airline and retail, for example, require the agent to
  list the action details and get the user's explicit confirmation ("yes") before a
  database write, and the customer's answers to the agent's questions shape which calls
  are right. The solution holds only tool calls (and, for airline, one final message), so:
  a process variant that skips or misplaces the confirmation cannot be expressed, because
  graderproof's trajectory operators edit tool calls and their arguments only; a
  requirement such as "confirm with the user before cancelling" has no observable witness
  in the outcome (requirement checks see the files, the trajectory, and the state) and
  cannot be validated; and the confirmation operator `traj-drop-confirmation` never fires,
  because no tool name in these references matches its pattern. Reordering calls only
  reorders tool calls; nothing records when the customer agreed. Process variants on these
  tasks therefore cover call order, dropped or repeated calls, and changed arguments.
* In telecom, calls with `"requestor": "user"` stand for actions the customer performs on
  their phone when the agent asks. Dropping or changing one models the agent failing to
  direct the customer (or the customer not following); the agent's instructions
  themselves are not represented.
* The reference final message holds only the `communicate_info` strings, or a closing
  line. A requirement about something else the agent must tell the customer fails on the
  reference, so it cannot be used.
* tau2's grader ignores read-only calls: the DB check replays only mutating calls, and
  `ACTION` is not in the airline or retail basis. Lookups the policy requires, such as
  authenticating the user before acting, are not graded there. This is tau2's design and
  the adapter keeps it; graderproof's measurement shows it where the task text requires
  the lookup.
* When `compare_args` is unset, the action check compares only the argument names the
  agent's call contains, so a call that omits an argument can still match; order and extra
  calls are ignored. The communicate check is a substring test after removing commas from
  the message.
* The state lists what changed and the database hashes. A requirement that a record stays
  unchanged is checked through the hash or `same_as_reference` on the state, not through a
  JSON pointer into the unchanged record.
* Grading replays mutating calls strictly. A tool whose output varied between the solution
  run and the grader's replay would make the grader exit with status 2; the Runner's
  precheck reports such a task as flaky or failing rather than dropping it.
* Only the base split of three domains is covered, in half-duplex text mode. Retail tasks
  whose reward needs an LLM judge are left out and counted, not approximated.
* Each sandboxed process imports all of tau2 (its package `__init__` imports the agents,
  the orchestrator, and litellm). The venv must be byte-compiled ahead, as `venv` does.
* Task-level findings for tau2-bench stay in `private/` (non-negotiable 14); only
  aggregates and hashes may be committed.
