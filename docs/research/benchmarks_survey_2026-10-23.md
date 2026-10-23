# Benchmark research for graderproof adapters

> Research notes written by a survey subagent on 2026-10-23 from shallow clones and public listings (no third-party code was run). Kept as the basis for the adapter and benchmark decisions in DECISIONS.md D18; claims here are leads to verify, not results.


Research date: 2026-10-23. Scope: a Docker-free, model-free grader audit (Python 3.12, bubblewrap, network to GitHub/PyPI/HF).
Method: shallow or blobless clones under this directory, plus JSON reads with `python3 -I`. **No third-party code was run.**
Everything below is from files, commits and URLs I opened. Statements marked **UNVERIFIED** are inference that I could not check.

Local clones (all under `research/`):

| Dir | Repo | Commit read |
|---|---|---|
| `tau2-bench/` | sierra-research/tau2-bench (HEAD) | `cc1df47baa1544a34bb8c8e5c4ca72ad223b96a2` (2026-10-22) |
| `tau2-bench-v1.0.1/` | same, tag `v1.0.1` | `fc0055dc4e0a316c3f83133267fbd6faaa770992` (2026-07-16) |
| `gorilla/` (sparse: `berkeley-function-call-leaderboard`) | ShishirPatil/gorilla | `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` (2026-03-23) |
| `BFCL-Result/` (blobless) | HuanzhiMao/BFCL-Result | `cadd76a8dc62984e7bf15ecaf358f070bae745cc` (2026-09-07) |
| `harbor/` | harbor-framework/harbor (laude-institute/harbor redirects here) | `bfc6c005e9a572ba22fd7e2d3b414bf014ae1ab0` (2026-10-22), v0.24.0 |
| `terminal-bench-2/` | harbor-framework/terminal-bench-2 | `2fd12b88aafdd04a52c298e3940bcb189f9766d6` (2026-04-29) |
| `inspect_evals/` | UKGovernmentBEIS/inspect_evals | `6a96ec57a8f00997e7d7b10364031bbae530bbb0` (2026-10-21) |
| `agentdojo/` (blobless) | ethz-spylab/agentdojo | `089ed468cf3ed0322acc66b0211f26d9d90dbf60` (2026-06-02), pkg 0.1.35 |
| `human-eval/` | openai/human-eval | `b9453e8f1865df0a0057a1383767caa400acfbcf` (2026-10-16) |
| `evalplus/` | evalplus/evalplus | `26d6d00bb1fd0fa37f39c99d5290da67891d1c5e` (2025-10-02) |
| `evalplus.github.io/` (blobless) | evalplus/evalplus.github.io | `87418456d3a8c2bc6265f24ff91d2dd0e7993f4b` (2024-12-26) |
| `bigcodebench/` | bigcode-project/bigcodebench | `09dd993f46c3fbf3a799465bb96d524edcb0b199` (2025-10-15) |

Downloaded data (never executed): `dl_tau2/` (two released tau2 trajectory files plus the leaderboard manifest), `dl_evalplus/` (HumanEval+ v0.1.10, MBPP+ v0.2.0), `dl_tb2/` (one TB2 leaderboard trial `result.json`), `s3/keys.tsv` (full key listing of the tau2 public S3 bucket).

---

## 1. tau2-bench

**License:** MIT ("Copyright (c) 2025 Sierra Research"), `LICENSE`; `pyproject.toml` `license = "MIT"`.
**Versions:** `pyproject.toml` at HEAD reads `version = "2.0.0"`, with CHANGELOG `[Unreleased]` entries after it. Tags: `v1.0.1` → `fc0055dc…`, `v2.0.0` → `989d3285ae669e49503324bdb9981bf14fccedeb`, `pre-v1.0.1` → `b51a6d69…`, `v0.1.3` → `5ba9e3e5…`.
Requires Python `>=3.12,<3.14`.

### Important version split (read this first)
- **2.0.0 (2026-10-19) changed scoring.** Communication checks became LLM-judged by default (`CommunicateScoring`, judge `gpt-5.5`). The NL-assertion judge became `gpt-5.4-mini-2026-03-17`. English retail and telecom runs swap in 50 "reviewed replacement" tasks per domain from `data/tau2/multilingual/en/{retail,telecom}_tasks_en.json` (same IDs). Name and ID lookups now fold case and accents. CHANGELOG: "No flag combination reproduces 1.0.1 inputs exactly".
- **Every released text trajectory set was graded with 1.x.** To re-grade them faithfully, use tag **`v1.0.1`**. `data/tau2/domains/{airline,retail,telecom,mock}/tasks.json` are byte-identical between `v1.0.1` and HEAD, and so are `db.json`, `db.toml` and `user_db.toml`. What changed in 2.0 is the evaluator code and the language-pack overlay.
- At HEAD you can still get deterministic communicate checks with `CommunicateScoring(scorer="substring")` (CLI `--communicate-scorer substring`), but HEAD's English retail and telecom use the replacement tasks.

### Task files per domain (paths relative to the repo)
| Domain | Tasks file | Split file (`base` = official set) | DB | Policy |
|---|---|---|---|---|
| airline | `data/tau2/domains/airline/tasks.json` (50) | `split_tasks.json`: base 50, train 30, test 20 | `db.json` | `policy.md` |
| retail | `data/tau2/domains/retail/tasks.json` (114) | base 114, train 74, test 40 | `db.json` | `policy.md` |
| telecom | `data/tau2/domains/telecom/tasks.json` (**2285** = `tasks_full.json`) | base **114**, small 20, train 74, test 40, full 2285 | `db.toml` (agent), `user_db.toml` (user device) | `main_policy.md`, `tech_support_manual.md` (+ workflow variants) |
| mock | `data/tau2/domains/mock/tasks.json` (10) | base 10 | `db.json`, `user_db.json` | `policy.md` |
| banking_knowledge (new in 1.0) | `data/tau2/domains/banking_knowledge/tasks.json` (97) |; | `db.json` + 698 docs |; |

Domain code lives in `src/tau2/domains/<domain>/{environment.py,tools.py,data_model.py,user_tools.py}`. HEAD also has `intake` (200 tasks, voice-oriented). 2.0 frozen 50-task subsets are in `data/tau2/task_subsets/*_50.json`, used by `data/tau2/benchmarks/text.json`.

### Task format (`src/tau2/data_model/tasks.py`)
Top-level keys: `id`, `description`, `user_scenario` (persona plus `instructions{task_instructions, domain, reason_for_call, known_info, unknown_info}`), `initial_state` (`initialization_data`, `initialization_actions` [env function calls on `user` or `assistant` env], `message_history`), `evaluation_criteria`. Telecom tasks also carry `ticket`.
`evaluation_criteria`:
- `actions`: list of `Action{action_id, requestor ("assistant"|"user"), name, arguments, info, compare_args}`. This is the gold tool-call sequence.
- `env_assertions`: list of `EnvAssertion{env_type, func_name, arguments, assert_value, message}`.
- `communicate_info`: list of strings.
- `nl_assertions`: list of natural-language strings.
- `reward_basis`: subset of `DB, ENV_ASSERTION, ACTION, COMMUNICATE, NL_ASSERTION`. Defaults to `[DB, COMMUNICATE]` when absent.

Observed `reward_basis` on the base splits (identical at v1.0.1 and HEAD):
- airline 50: all `[DB, COMMUNICATE]`. 43 tasks have actions (7 have zero). Only 6 have `communicate_info`. All 50 carry `nl_assertions`, but NL is **not** in the basis.
- retail 114: 112 `[DB, NL_ASSERTION]`, 2 `[DB]`. **40 tasks actually have `nl_assertions`, so they need an LLM judge.** 36 have `communicate_info`, which is not scored because it is not in the basis.
- telecom 114: 94 `[ENV_ASSERTION]`, 20 `[ACTION, ENV_ASSERTION]`. All 114 have actions and env_assertions; no NL or communicate fields. Full set of 2285: 2253 `[ENV_ASSERTION]`, 32 `[ACTION, ENV_ASSERTION]`. Gold action requestors are mostly `user` (10,927 user vs 2,288 assistant across the full set).
- mock 10: mixed (6 use the default basis).

### Reward computation
- Entry point: `evaluate_simulation(simulation, task, evaluation_type, solo_mode, domain, mode, env_kwargs, strict_replay)` in `src/tau2/evaluator/evaluator.py`. HEAD adds keyword-only `communicate_scoring` and `customer_language`. With `EvaluationType.ALL` it computes these components and returns the **product** of those in `reward_basis`:
  - `EnvironmentEvaluator.calculate_reward` (`evaluator_env.py`). It builds a *predicted* env by replaying every mutating tool call in the trajectory (`Environment.set_state`, `src/tau2/environment/environment.py`), and a *gold* env by running `evaluation_criteria.actions` through `make_tool_call`. DB reward = SHA-256 hash equality of the agent DB **and** the user DB (`get_db_hash`, `tau2/utils/utils.py:get_dict_hash`). ENV_ASSERTION reward = product of `run_env_assertion` on the predicted env. Replay skips non-mutating tools and unknown (hallucinated) tool names. In strict mode it raises if a replayed mutating call returns different content from the recorded `ToolMessage`. `strict_replay=False` is used for re-grading.
  - `ActionEvaluator.calculate_reward` (`evaluator_action.py`): every gold action must match *some* predicted tool call. Matching uses `Action.compare_with_tool_call`: same name, and argument equality on `compare_args` (or on all of the tool call's args when `compare_args` is None). Order and extra calls are ignored.
  - `CommunicateEvaluator.calculate_reward` (`evaluator_communicate.py`). At v1.0.1: case-insensitive substring of each `communicate_info` string in any assistant text message, with commas stripped from the message. At HEAD: semantic LLM judge by default, substring optional.
  - `NLAssertionsEvaluator.calculate_reward` (`evaluator_nl_assertions.py`): **LLM** via `tau2.utils.llm_utils.generate` (v1.0.1 `gpt-4.1-2025-04-14` at temperature 0). Returns 1.0 when `nl_assertions` is empty.
- Termination reasons other than `AGENT_STOP` or `USER_STOP` give reward 0.
- Re-grading CLI: `tau2 evaluate-trajs [--fresh-tasks] <results.json>` → `src/tau2/scripts/evaluate_trajectories.py:compute_simulation_rewards`. It uses `strict_replay=False`, the task definitions embedded in the results file (or `--fresh-tasks`), and a banking read-allowlist.

### Deterministic vs LLM
- Deterministic: DB hash, env assertions, action match, v1.0.1 communicate substring.
- LLM: NL assertions (retail: 40 tasks), HEAD semantic communicate (airline: the 6 tasks with `communicate_info`), the user simulator (only needed to *generate* trajectories), and the optional reviewers and judges (`review_llm_judge*.py`, `hallucination_reviewer.py`, `auth_classifier.py`), which are not part of the reward.
- Model-free gradeable base tasks: **airline 50 (v1.0.1)**, **telecom 114 (or 2285)**, **retail 74** (the 114 minus the 40 with NL assertions), **mock 10**. Total ≈ 248 tasks, or 2,400+ counting telecom-full.

### Building a gold trajectory and grading it with no LLM (v1.0.1 data model, `src/tau2/data_model/message.py`, `simulation.py`)
1. Load the task. Construct the env with `tau2.domains.<d>.environment.get_environment(solo_mode=False)`, then `set_state(initial_state.initialization_data, initialization_actions, message_history or [])`.
2. For each gold `Action`, emit an `AssistantMessage(role="assistant", tool_calls=[ToolCall(id=k, name, arguments, requestor="assistant")])`, or a `UserMessage(role="user", tool_calls=[...requestor="user"])` when `requestor == "user"` (telecom device actions). Follow each call with `ToolMessage(id=k, role="tool", content=env.get_response(tool_call).content, requestor=...)`. Running the call against a live env yields the content that strict replay expects.
3. For tasks with COMMUNICATE in the basis, add an `AssistantMessage` whose text contains each `communicate_info` string.
4. Wrap the messages in `SimulationRun(id, task_id, start_time, end_time, duration, termination_reason=AGENT_STOP, messages=...)`.
5. Grade with no LLM. Call `EnvironmentEvaluator`, `ActionEvaluator` and `CommunicateEvaluator` directly and multiply the components in `reward_basis`. Alternatively call `evaluate_simulation(..., EvaluationType.ALL)` only for tasks without `NL_ASSERTION` + non-empty `nl_assertions`. For the 40 retail NL tasks, either skip them, monkey-patch `NLAssertionsEvaluator.evaluate_nl_assertions` with a fixed oracle, or reuse the recorded verdicts (see the released results below).
   - Gold correctness is not guaranteed. The env evaluator logs and swallows exceptions from gold actions (`logger.warning("Error in golden actions…")`), so graderproof should check that the gold trajectory scores 1.0 before mutating it.
   - Mutation surface: DB-hash equality is order-insensitive for reads and ignores read-only calls entirely. Action matching ignores order and extra calls and honours `compare_args`. Communicate is substring with commas stripped. These are natural places to probe for false accepts.

### Python dependencies
- Core (`pyproject.toml`): rich, tabulate, fastapi, uvicorn, pandas, psutil, loguru, docstring-parser, litellm (`>=1.80.15,<1.82.7`), tenacity, deepdiff, addict, PyYAML, toml, python-dotenv, typer, requests, numpy, httpx.
- The deterministic path (`evaluator_env`, `evaluator_action`, v1.0.1 `evaluator_communicate`, `environment/*`, `domains/<d>/*`, `data_model/*`) imports pydantic, loguru, deepdiff, python-dotenv, pandas (in `data_model/simulation.py`), toml, PyYAML and addict. `elevenlabs` is a guarded optional import.
- `src/tau2/evaluator/evaluator.py` imports `evaluator_nl_assertions` → `utils/llm_utils.py` → **litellm**. `src/tau2/registry.py` imports agents and the user simulator. Importing those modules needs litellm installed even when no call is made. I did not test whether a plain install imports cleanly (**UNVERIFIED**). CI installs `--extra dev --extra live --extra knowledge` plus portaudio and ffmpeg (`.github/workflows/tests.yml`).
- Sandbox notes:
  - Set `TAU2_DATA_DIR` for non-editable installs (`tau2/utils/utils.py`).
  - `utils.py` runs `git rev-parse HEAD` via subprocess for metadata.
  - `load_dotenv()` runs at import.
  - litellm may fetch its model-cost map over the network at import unless `LITELLM_LOCAL_MODEL_COST_MAP=True`. This is general litellm behaviour I did not verify here (**UNVERIFIED**).

### Released per-task results and trajectories (re-gradable)
1. **In the repo:** `data/tau2/results/final/*.json` (54 files, 577 MB). These are the original paper runs (June 2025 task sets, tau2 0.1.x), 4 trials each, user simulator gpt-4.1-2025-04-14.
   - Models: claude-3-7-sonnet-20250219, gpt-4.1-2025-04-14, gpt-4.1-mini-2025-04-14, o4-mini-2025-04-16.
   - Domains: airline, retail, telecom, plus telecom ablations (`telecom-workflow`, `no-user`, `op`, `no-user-op`).
   - `results/final/README.md` warns that these predate the v1.0.0 task fixes. Airline (29 tasks differ) and retail (114) fail current task verification; telecom is unchanged. Each file embeds its own `tasks`, so the files can be re-graded against the embedded tasks.
2. **Public S3 bucket** (listable, no auth): `https://sierra-tau-bench-public.s3.us-west-2.amazonaws.com/submissions/<submission>/trajectories/<file>.json`. Manifest: `.../submissions/manifest.json` (29 text, 27 voice, 16 legacy, 3 voice-v2, 6 voice-v2-domain submissions). The leaderboard web app points here (`web/leaderboard/.env.example`, `.github/workflows/deploy-leaderboard.yml`); per-submission metadata is in `web/leaderboard/public/submissions/<name>/submission.json`.
   - **Text trajectories matching current (v1.0.1) base tasks.** All have `methodology.tau2_bench_version: "1.0.1"`, user simulator gpt-5.2, 4 trials, airline + retail + telecom (+ banking_knowledge):
     - claude-opus-4-5 (`claude-opus-4-5_sierra_2026-02-26`)
     - claude-sonnet-4-5 (`claude-sonnet-4-5_sierra_2026-02-26`)
     - gpt-5.2 high (`gpt-5-2_sierra_2026-02-26`)
     - gpt-5.2 none (`gpt-5-2-none_sierra_2026-02-26`)
     - gemini-3-pro (`gemini-3-pro_sierra_2026-03-02`, files `geminipro-{airline,retail,telecom}.json`)
     - gemini-3-flash (`gemini-3-flash_sierra_2026-03-02`)
     - glm-5 (`glm-5-think_sierra_2026-03-02`)
     - qwen3.5-397b-a17b (`qwen3.5-397b-a17b-think_sierra_2026-03-02`)

     That is **8 models × 3 domains**, 15–95 MB per file. The embedded `info.git_commit` in the files I opened is `7324fb57cb6819e77937c79964db916f5b068e31`.
   - **Older text trajectories** (tau2 0.1.3, user sim gpt-4.1 or gpt-5): claude-3-7-sonnet, gpt-4.1, gpt-4.1-mini, o4-mini (same files as in-repo), gpt-5 (`gpt-5_sierra_2025-08-09`), qwen3-max ×2 (`qwen3-max_qwen_2025-10-30`, `_2026-01-23`), and toolorchestra (nvidia, 1 trial). Several are marked `trajectories_available: false` in submission.json, but the files are on S3.
   - Banking-knowledge-only trajectories exist for more models (claude-opus-4-6/4-7/4-8/5, gpt-5.5, grok-4-fast/4-5, kimi-k3, qwen3-8-max, inkling, …). Voice submissions hold tens of thousands of audio and tick files.
   - **Format** (checked on `dl_tau2/opus45_airline.json` and `dl_tau2/gpt52_retail.json`): top-level `{timestamp, info, tasks, simulations}`.
     - `info` has `git_commit, num_trials, seed (300), agent_info.llm, user_info.llm, environment_info.domain_name`.
     - Each simulation has `{id, task_id, trial, termination_reason, messages[...], reward_info{reward, db_check, env_assertions, action_checks, nl_assertions, communicate_checks, reward_basis, reward_breakdown}}`.
     - Opus-4.5 airline: 200 sims (50 × 4), 168 with reward 1.
     - GPT-5.2 retail: 456 sims, 372 with reward 1. 160 sims carry recorded NL verdicts (`nl_assertions[{nl_assertion, met, justification}]`), i.e. 40 NL tasks × 4.

     So the retail NL component can be "re-graded" by reusing the recorded verdicts with no model call.
   - Re-grade path: `tau2 evaluate-trajs` at `v1.0.1`. It replays the recorded tool calls, so no LLM is needed except for retail NL.

---

## 2. BFCL (gorilla / berkeley-function-call-leaderboard)

**Version:** **BFCL V4** (CHANGELOG: "[Jul 17, 2025] #1019 BFCL V4 release"). Data files are named `BFCL_v4_*.json`. PyPI package `bfcl-eval`, latest **2026.3.23** (calendar versions; the version comes from git tags matching `vYYYY.MM.DD`).
**License:** Apache-2.0 (`gorilla/LICENSE`; `pyproject.toml` `license = {text = "Apache 2.0"}`; data README front-matter `license: apache-2.0`).
**Data last changed:** commit `f7cf7359b7ac615a0b294831c5ba2bc95ee4a000` (2025-12-16, "#1266 Multiple Dataset Fix"). The only later evaluator change is `cf12f01` (2026-03-03: colons → underscores when executing multi-turn calls).

### Data (`berkeley-function-call-leaderboard/bfcl_eval/data/`)
- One JSON object per line.
- Question format: `{"id", "question": [[{"role","content"}...]] (turns), "function": [JSON-schema-like defs, "type":"dict"]}`.
- Answers: `possible_answer/BFCL_v4_<cat>.json`, format `{"id", "ground_truth": [ {func_name: {param: [acceptable values...]}} , ...]}`. `""` in the list means "optional, may be omitted". Lists hold alternative accepted values, e.g. `"unit": ["units", ""]`.

Entry counts (non-blank lines):

| Category | Entries | Answers |
|---|---|---|
| simple_python | 400 | 400 |
| simple_java | 100 | 100 |
| simple_javascript | 50 | 50 |
| multiple | 200 | 200 |
| parallel | 200 | 200 |
| parallel_multiple | 200 | 200 |
| live_simple | 258 | 258 |
| live_multiple | 1053 | 1053 |
| live_parallel | 16 | 16 |
| live_parallel_multiple | 24 | 24 |
| irrelevance | 240 |; (pass = no call decoded) |
| live_irrelevance | 884 |; |
| live_relevance | 16 |; (pass = some call decoded) |
| multi_turn_base / miss_func / miss_param / long_context | 200 each | 200 each (list of per-turn lists of call strings, e.g. `"cd(folder='document')"`) |
| memory (kv / vector / rec_sum use the same 155) | 155 | 155 (answer strings) |
| web_search (base / no_snippet) | 100 | 100 (answer strings) |
| format_sensitivity | 10 |; |

AST categories total 2,501 non-live + live entries with answers.

### AST checker
- File `bfcl_eval/eval_checker/ast_eval/ast_checker.py`, function `ast_checker(func_description, model_output, possible_answer, language: Language, test_category: str, model_name: str) -> {"valid": bool, "error": [...], "error_type": str}`.
  - Dispatch: "parallel" in the category → `parallel_function_checker_no_order`; "multiple" → `multiple_function_checker`; otherwise `simple_function_checker` (which requires exactly one call).
  - `model_output` is the decoded form `[{func_name: {arg: value}}]`.
  - Type checks (`type_checker`, nested list and dict checkers) and string normalisation (`standardize_string`) are what make "spec-preserving" variants accept or reject.
- Caller: `bfcl_eval/eval_checker/eval_runner.py:_evaluate_single_ast_entry`. It first calls `handler.decode_ast(raw, ReturnFormat, has_tool_call_tag)`.
  - Prompting models: `model_handler/utils.py:ast_parse` uses Python `ast` on strings like `"[f(a=1)]"`.
  - FC models: the raw result is a list of `{name: json-args-string}`.
  - Java and JS: tree-sitter (`model_handler/parser/{java,js}_parser.py`).
- Coupling: `ast_checker.py` imports `constants.model_config.MODEL_CONFIG_MAPPING`, which imports every model handler (openai, anthropic, cohere, mistralai, google-genai, …), only to look up `underscore_to_dot` in `convert_func_name`. The checker plus `type_convertor/*.py`, `constants/enums.py` and `constants/type_mappings.py` is ~1,400 lines of pure Python. It is easy to vendor (Apache-2.0) with a shim for that one flag; otherwise install `bfcl-eval` with its heavy dependencies.

### Executable categories
- The old `exec_simple/multiple/parallel/parallel_multiple`, `rest` and `sql` sets were **retired** (CHANGELOG 2025-04-09, #943). They now sit in `data/unused_datasets/`. `rest` needed real APIs and keys.
- **Multi-turn** (800 entries) executes model and ground-truth call strings with `eval()` (`multi_turn_eval/multi_turn_utils.py:execute_multi_turn_func_call`) against local simulated backends in `multi_turn_eval/func_source_code/` (GorillaFileSystem, MathAPI, MessageAPI, TwitterAPI/posting_api, TicketAPI, TradingBot, TravelAPI, VehicleControl). These need **no network**; RNGs are seeded from the scenario. `gorilla_file_system.py` stamps `datetime.now()` into `_last_modified` (I did not check whether state comparison ignores it, **UNVERIFIED**). Checker: `multi_turn_checker.py:multi_turn_checker(decoded_results, ground_truth, test_entry, test_category, model_name)`. It compares backend instance state and requires ground-truth execution results to be a subset of the model's. Running `eval()` on model strings needs the sandbox.
- Agentic: `web_search` needs network (`serpapi.GoogleSearch`, `requests`) plus a SERPAPI key. `memory_vector` needs `sentence-transformers` and `faiss-cpu` (model download from HF). The scorer for both is `agentic_eval/agentic_checker.py:agentic_checker` (normalised substring of an answer string), which is deterministic.

### Dependencies
`pyproject.toml` lists requests, tqdm, numpy==1.26.4, pandas, huggingface_hub, pydantic, python-dotenv, tree_sitter==0.21.3, tree-sitter-java/-javascript, openai, mistralai, anthropic, cohere, typer, tabulate, datamodel-code-generator, google-genai, qwen-agent, mpmath, tenacity, writer-sdk, overrides, boto3, bs4, html2text, rank_bm25, google-search-results, sentence-transformers, faiss-cpu, networkx, filelock. `requires-python >=3.10`.
- numpy 1.26.4 has no prebuilt cp313 wheels, but cp312 wheels exist, so Python 3.12 should be fine (**UNVERIFIED** install).

### Public per-model, per-task results: YES
- **`https://github.com/HuanzhiMao/BFCL-Result`** (Apache-2.0; README: "hosts all model responses used to generate the BFCL leaderboard, together with their evaluation scores"; maintained by a BFCL author, "NOT actively monitored").
  - 22 dated snapshots `2024-07-06` … `2025-12-16`; 119,332 files.
  - Latest snapshot `2025-12-16/` has **109 model directories** (FC and prompting variants), including claude-opus-4-5-20251101(-FC), claude-sonnet-4-5, gpt-5.2-2025-12-11(-FC), gpt-4.1, o3, gemini-3-pro-preview, grok-4, qwen3 and many open models.
  - Layout: `result/<model>/{non_live,live,multi_turn,agentic}/BFCL_v4_<cat>_result.json`. Each line is `{id, result, input_token_count, output_token_count, latency[, inference_log]}`; `result` is the raw model output in handler format.
  - Scores: `score/<model>/<group>/BFCL_v4_<cat>_score.json`. The first line is `{"accuracy","correct_count","total_count"}`; later lines cover **failed entries only**, with `error`, `error_type`, `model_result_raw`, `model_result_decoded` and `possible_answer`. Pass = id absent.
  - Aggregates: `score/data_*.csv`.
  - Data alignment: the snapshot date equals the last data-fix commit date (2025-12-16). Whether the snapshot was graded with the post-fix data is **UNVERIFIED**; re-grading with the current checker will reveal any drift.
- Hugging Face `gorilla-llm/Berkeley-Function-Calling-Leaderboard` (sha `61fc0608…`, Apache-2.0) still contains **V3** files only (`BFCL_v3_*.json`). It is stale relative to GitHub. Use the GitHub data.
- inspect_evals `bfcl` clones gorilla at a pinned commit (see §4).

---

## 3. Terminal-Bench 2.0 / Harbor

**Harbor:** `harbor-framework/harbor` (the `laude-institute/harbor` URL resolves to the same HEAD), Apache-2.0, v0.24.0, Python >=3.12.

### Task directory format (`src/harbor/models/task/paths.py`, `config.py`)
```
<task>/
  instruction.md          # prompt given to the agent
  task.toml               # config (below)
  trajectory.json         # optional ATIF prior context
  environment/Dockerfile  # or docker-compose.yaml / singularity-compose.yaml ...
  solution/solve.sh       # oracle; copied to /solution by the OracleAgent (solve.bat on Windows)
  tests/test.sh           # verifier; copied to /tests after the agent runs (test.bat on Windows)
  README.md, .gitignore   # optional
```
Multi-step tasks use `steps/<name>/…`.
- `task.toml` (TaskConfig default `schema_version = "1.4"`; TB2 tasks use `"1.1"`):
  - `[task]` name/description/keywords/authors
  - `[metadata]` difficulty, category, tags, expert/junior time estimates
  - `[verifier]` `timeout_sec`, `env`, `user`, `environment_mode`, network policy
  - `[agent]` `timeout_sec`, `user`, network policy
  - `[environment]` `docker_image` (prebuilt image), `build_timeout_sec`, `os`, `cpus`, `memory_mb`, `storage_mb`, `gpus`, `gpu_types`, `tpu`, `allow_internet`, `network_mode`/`allowed_hosts`, `mcp_servers`, `env`, `workdir`, `healthcheck`, `skills_dir`
  - `[solution.env]`, `artifacts`, `steps`, `multi_step_reward_strategy`
- In-container paths (`src/harbor/models/trial/paths.py`): `/logs/agent`, `/logs/verifier`, `/logs/artifacts`, `/tests`, `/solution`.
- **Reward file:** the verifier must write `/logs/verifier/reward.txt` (a single number) or `/logs/verifier/reward.json` (a dict of finite numbers). JSON takes precedence (`src/harbor/verifier/verifier.py`); the result is `VerifierResult(rewards=…)`. TB2 `test.sh` scripts run pytest with `--ctrf /logs/verifier/ctrf.json` and then `echo 1|0 > /logs/verifier/reward.txt`.
- Environments (`src/harbor/environments/`): docker, podman, singularity, apple-container, kata, and many clouds (daytona, e2b, modal, runloop, gke, ec2, …). **There is no local or no-container environment type** (`models/environment_type.py`).

### Where TB2 tasks live
- Git: `https://github.com/harbor-framework/terminal-bench-2` (HEAD `2fd12b88…`, Apache-2.0 LICENSE, 89 tasks).
- Harbor's `registry.json` entry `terminal-bench` version `2.0` lists 89 tasks pinned to `git_commit_id 69671fbaac6d67a7ef0dfec016cc38a64ef7a77c` (`git_url https://github.com/laude-institute/terminal-bench-2.git`). Between that pin and HEAD only task.toml/README/.gitignore metadata changed, plus `install-windows-3.11/tests/test_outputs.py`, `overfull-hbox/solution/solve.sh` and `rstan-to-pystan/solution/solve.sh`. **The LICENSE file was added after the pin.**
- Harbor now defaults to **Harbor Hub** as the registry (`docs-mintlify/datasets/registries.mdx`). HF mirrors: `harborframework/terminal-bench-2.0` (apache-2.0, sha `f2e8c75e…`), plus `terminal-bench-2.1` and `terminal-bench-3.0`.
- Some tasks ship the reference implementation as an encrypted tarball that solve.sh decrypts with a hard-coded password (e.g. `adaptive-rejection-sampler/environment/protected.tar.gz.enc`).

### Docker-free feasibility: NO for 40+ tasks
- Survey of all 89 `task.toml` files (`tb2_survey.json`):
  - every task sets `docker_image` (e.g. `alexgshaw/<task>:20251031` on Docker Hub, which is not reachable here) and `allow_internet = true`; `gpus = 0`;
  - base images: python:3.13-slim-bookworm 41, ubuntu:24.04 40, other debian/python 8;
  - 82/89 `test.sh` scripts `apt-get install curl` and `curl … astral.sh/uv … | sh`, then run `uvx -p 3.13 pytest …`.

  So verifiers assume root, apt, network and Python 3.13.
- 21 tasks have Dockerfiles with no `RUN` line. Of those, roughly 6–8 look host-runnable after rewriting test.sh (e.g. `cancel-async-tasks`, `code-from-image`, `regex-log`, `schemelike-metacircular-eval`, `sqlite-db-truncate`, `sparql-university`). Rewriting the verifier means auditing a modified grader, though, and that is well short of 40 tasks.

### Published job outputs / per-task results: YES (cannot be re-graded without Docker)
- HF dataset **`harborframework/terminal-bench-2-leaderboard`** (apache-2.0, sha `572b2614…`, last modified 2026-05-15). README: "SUBMISSIONS CLOSED" as of May 14, pending a new process.
  - `submissions/terminal-bench/2.0/<agent>__<model>/` holds **75 submissions** (e.g. Terminus2__Claude-Opus-4.6, Droid__GPT-5.3-Codex, Forge__GPT-5.4, Gemini_CLI__Gemini-3.1-Pro-Preview, …), each with `metadata.yaml` and Harbor job folders. Each trial folder has `config.json`, `result.json` (`verifier_result.rewards.reward`, `task_checksum`, `task_id{git_url,git_commit_id=69671fba…,path}`), `agent/trajectory.json` (ATIF), `verifier/{reward.txt,ctrf.json,test-stdout.txt}`, and sometimes `exception.txt`.
  - At least 5 trials per task are required. Per-test pass/fail (ctrf) is included.
  - Re-grading needs the post-agent container state, which is not stored; you would have to replay the agent's commands inside the Docker image.
- `harborframework/parity-experiments` (100k+ files under `adapters/`) also exists. I did not inspect it.

---

## 4. inspect_evals (UKGovernmentBEIS/inspect_evals)

**License:** MIT ("Copyright (c) 2024 UK AI Security Institute"). HEAD `6a96ec57…`. Each eval lists its sandbox needs in `src/inspect_evals/<eval>/eval.yaml`.
All of these still need a model to *produce* trajectories. The question here is whether the *scorer* is deterministic and whether the task needs Docker.

| Eval | Path | Scorer (deterministic?) | Docker? | Data source / license | Size |
|---|---|---|---|---|---|
| **AgentDojo** | `src/inspect_evals/agentdojo/` (ported code; v "2-A") | `scorer.py:user_task_scorer` / `injection_task_scorer`. Calls each task's Python `utility(model_output, pre_env, post_env, traces)` and `security(...)`. Pure Python, deterministic. Every task has `ground_truth(pre_env) -> [ToolCall]`. | Only `workspace_plus` tasks (`REQUIRES_SANDBOX = True`; use `-T with_sandbox_tasks=no`) | Inline Python + `data/suites/*/environment.yaml`. Upstream ethz-spylab/agentdojo is **MIT** | 97 non-sandbox user tasks (banking 16, slack 21 incl. 4 combined, travel 20, workspace 40 incl. 7 combined) + 2 workspace_plus; 1,014 samples including injections |
| **BFCL** | `src/inspect_evals/bfcl/` (v "8-B") | AST and multi-turn state checks, no model grader | No | git-clones gorilla at a pinned commit (`external_assets: git_clone … state: pinned`), Apache-2.0 | 4,981 default samples (V1–V3 cats); web_search +200 needs SERPAPI; memory +465 |
| **tau2 (Inspect port)** | `src/inspect_evals/tau2/` (v "4-A") | `airline_scorer` and `retail_scorer` = `db_match` + `score_communicated_info` (substring); `telecom_scorer`. All deterministic. **The retail port drops NL_ASSERTION**, so it does not match upstream v1.0.1 retail | No | Vendored tau2 data, MIT | airline 50, retail 114, telecom 114, banking 97 |
| **Mind2Web** | `src/inspect_evals/mind2web/` | `scorer.py`: element accuracy / operation F1 / step SR on offline action prediction (multiple-choice over candidate elements). Deterministic | No | HF `osunlp/Multimodal-Mind2Web` (license `openrail`) @ `1b4c6a8c…` + `osunlp/Mind2Web` `scores_all_data.pkl` (cc-by-4.0) @ `17ece8eb…` | 7,775 samples |
| AgentThreatBench | `src/inspect_evals/agent_threat_bench/` | Deterministic utility/security rules (`scorer.py`) | No | `data/*.json` in-repo | only 24 samples (too small) |

Not suitable: AgentHarm (`agentharm`, LLM semantic judge). GAIA, AssistantBench, BrowseComp, OSWorld, cybench and similar need Docker sandboxes and/or a browser. HumanEval and MBPP in inspect default to `sandbox="docker"` (`humaneval.py:67`, `mbpp.py:140`).

**AgentDojo upstream gives re-gradable per-task results.** `ethz-spylab/agentdojo/runs/` (MIT) holds 29 pipeline directories with 36,679 files: claude-3-7-sonnet-20250219, claude-3-5-sonnet ×2, claude-3-opus/sonnet/haiku, gpt-4o-2024-05-13 (+4 defenses), gpt-4o-mini, gpt-4-turbo, gpt-4-0125, gpt-3.5-turbo, gemini-1.5-pro/flash ×2, gemini-2.0-flash ×2, command-r(+), Llama-3-70b, Llama-3.3-70B, Meta-SecAlign-70B.
- Layout: `runs/<pipeline>/<suite>/user_task_<n>/none/none.json` (utility-only run) and `.../important_instructions/injection_task_<m>.json`.
- File format: `{suite_name, pipeline_name, user_task_id, injection_task_id, attack_type, injections, messages[...tool_calls...], error, utility, security, duration}`. Newer runs add `benchmark_version` (e.g. `"v1.2.1"` for Meta-SecAlign-70B); older ones omit it (presumably v1, **UNVERIFIED**).
- Re-grade: replay the recorded `tool_calls` against `load_and_inject_default_environment` for the matching benchmark version (suites `default_suites/v1`, `v1_1`, `v1_1_1`, `v1_1_2`, `v1_2`, `v1_2_1`, `v1_2_2`), then call `utility(...)`.
- Reference trajectory: `agent_pipeline/ground_truth_pipeline.py:GroundTruthPipeline` runs `task.ground_truth(env)`. `TaskSuite.check()` (`task_suite/task_suite.py`) verifies that ground truth passes utility.
- Upstream deps: openai, pydantic[email], docstring-parser, tenacity, langchain, anthropic, cohere, pyyaml, click, deepdiff, rich, python-dotenv, google-genai (imports only; no calls needed). The inspect port needs only `pydantic[email]` and `deepdiff` on top of inspect_ai.
- `docs/results-table.html` lists utility per model (e.g. claude-3-7-sonnet 88.66% utility on the 97 tasks).

---

## 5. Docker-free coding substitutes

### HumanEval (openai/human-eval)
- License MIT. Data: `data/HumanEval.jsonl.gz` (164 tasks; fields `task_id, prompt, entry_point, canonical_solution, test`). HF mirror `openai/openai_humaneval` (MIT).
- The repo README now says "**Deprecated and unmaintained**". Requirements: tqdm, fire, numpy.
- Grader: `human_eval/execution.py:check_correctness(problem, completion, timeout)` builds `prompt + completion + "\n" + test + "\n" + f"check({entry_point})"` and `exec`s it in a `multiprocessing.Process` with `reliability_guard()` and a timeout. Result is `passed` / `failed: …` / `timed out`.
  - The README says the `exec` line is commented out, but at this HEAD it is **uncommented** (line 50).
- The test is a `check(candidate)` function full of `assert`s. Typically 7–10 asserts, so it is weak; that makes it a good false-accept target.
- Reference solutions: `canonical_solution` for all 164 tasks.
- Public per-model samples: the repo ships only `example_samples.jsonl`. See MultiPL-E below.

### EvalPlus (HumanEval+ / MBPP+)
- License Apache-2.0 (code; HF `evalplus/humanevalplus` and `evalplus/mbppplus` cards: apache-2.0). PyPI `evalplus` 0.3.1.
- Data is downloaded from GitHub releases by `evalplus/data/utils.py:get_dataset_metadata`:
  - `https://github.com/evalplus/humanevalplus_release/releases/download/v0.1.10/HumanEvalPlus.jsonl.gz` (`HUMANEVAL_PLUS_VERSION = "v0.1.10"`): **164 tasks**, about 972 plus-inputs per task (median).
  - `https://github.com/evalplus/mbppplus_release/releases/download/v0.2.0/MbppPlus.jsonl.gz` (`MBPP_PLUS_VERSION = "v0.2.0"`): **378 tasks**, about 105 plus-inputs per task (median).
  - Fields: `task_id, prompt, entry_point, canonical_solution, base_input, plus_input, atol, contract` (+ `test` for HumanEval+, `assertion` for MBPP+). Both files are downloaded in `dl_evalplus/`.
  - "mini" and "noextreme" variants also exist.
- Grader: `evalplus/evaluate.py`.
  - `get_groundtruth` runs `canonical_solution` on all inputs to get expected outputs and reference times.
  - `check_correctness` → `evalplus/eval/__init__.py:untrusted_check` runs the candidate on `base_input` and then `plus_input` in a subprocess (`unsafe_execute`, `reliability_guard`). It compares outputs with `atol` / `is_floats` handling.
  - Per-input time limit = `max(4.0 s, 4.0 × gt_time)` (`DEFAULT_MIN_TIME_LIMIT`, `DEFAULT_GT_TIME_LIMIT_FACTOR` in `evalplus/config.py`). That is **timing-dependent**, which is a flakiness risk inside bwrap.
  - Reports `base` and `plus` status separately.
- Heavy install deps (`setup.cfg`): openai, anthropic, transformers, datasets, google-generativeai, boto3, ollama, tree_sitter, … They are only needed for codegen; the evaluator path needs numpy, wget, multipledispatch, appdirs, tempdir and termcolor (**UNVERIFIED** minimal set).
- No Docker is required (a Dockerfile is offered). Reference solutions are present.
- Public per-model samples: `evalplus.github.io/results.json` holds **aggregate pass@1 only**; `results/evalperf/*.brief.json` covers EvalPerf. I could not list GitHub release assets (the GitHub API and web UI are blocked by this session's proxy), so **whether EvalPlus releases raw LLM samples is UNVERIFIED**.

### Other candidates
- **MultiPL-E completions** (HF `bigcode/MultiPL-E-completions`, sha `999e282f…`, no license in the card, **UNVERIFIED** license). It has per-problem `completions`, `programs`, `stdouts`, `stderrs`, `exit_codes`, `statuses` for each model and config.
  - Python: 23 HumanEval configs (codegen-16B-mono, davinci, cushman001, chatgpt, codegeex, santacoder, replit, starcoder, bigcode_15b checkpoints, …) and 7 MBPP configs.
  - HumanEval here is **161 problems** with MultiPL-E's "reworded" Python tests, not the original `check()`.
  - These are public, per-sample, pass/fail-labelled samples suitable for re-grading, although the models are old (2022–2023 era).
- **BigCodeBench** (bigcode-project/bigcodebench, Apache-2.0; HF `bigcode/bigcodebench` apache-2.0, splits v0.1.0–**v0.1.4**; `BIGCODEBENCH_VERSION = "v0.1.4"`). 1,140 tasks (Hard subset 148, `bigcode/bigcodebench-hard`), unittest-based, `canonical_solution` present.
  - Local evaluation needs about 73 pinned libraries (`Requirements/requirements-eval.txt`: pandas, matplotlib, sklearn, …), so the environment is heavy but possible without Docker.
  - README says pre-generated samples are attached to release `v0.2.4` as `sanitized_samples_calibrated.zip`, but that exact download URL returned **404**. The asset name may differ; **UNVERIFIED**.
  - `bigcode/bigcodebench-solve-rate` and `bigcode/bigcodebench-results` exist on HF (per-task solve rates and leaderboard aggregates; per-model per-task content not inspected).

---

## Recommendation

**Most feasible for a Docker-free, model-free audit (40+ tasks each):**
1. **tau2-bench, pinned to `v1.0.1`** (tool use, multi-turn, stateful). Gold actions → constructed trajectory → deterministic env/action/communicate graders.
   - Use airline 50, telecom 114 (2,285 available) and retail-74, the deterministic subset; the 40 retail NL tasks need an LLM, so skip them or use recorded verdicts. Also mock 10.
   - It has the richest **public per-task trajectories**: 8 models × airline/retail/telecom × 4 trials on the current task set (S3), plus older paper runs. Re-grading needs no model.
2. **BFCL V4 AST categories** (tool-call syntax and arguments). 2,500 AST entries with possible answers, plus 800 multi-turn with local backends.
   - The checker is pure Python and easily vendored.
   - The best **public per-task results**: BFCL-Result `2025-12-16/` has raw outputs and failure lists for 109 model configs.
3. **AgentDojo user tasks** (tool use, 97 tasks without Docker). Python `ground_truth()` serves as the reference, with deterministic `utility()` checks.
   - **Public per-task runs** cover ~20 models (`runs/`). Pin the matching benchmark version when re-grading.
4. **HumanEval / HumanEval+ / MBPP+** as the Terminal-Bench substitute. 164 / 164 / 378 tasks, canonical solutions included, test-execution graders. HumanEval's weak tests versus HumanEval+'s many inputs make a natural pair for false-accept comparison.
   - Public per-task samples: only MultiPL-E's (old models, 161 reworded problems). EvalPlus raw samples are unverified.

**Not feasible:** Terminal-Bench 2.0. All 89 tasks need their Docker images plus root, apt and network in the verifier. Its leaderboard trials (HF `harborframework/terminal-bench-2-leaderboard`, 75 submissions) are public but cannot be re-graded without containers.

**Public per-task results suited to re-grading, ranked:**
1. BFCL-Result (109 models)
2. tau2 S3 trajectories (8 current-task-set models + 8 legacy)
3. AgentDojo `runs/` (~29 pipelines)
4. MultiPL-E completions (old code models)
5. TB2 leaderboard (results only, not re-gradable here)

## Not verified
- That tau2 / bfcl-eval / evalplus / agentdojo install and import cleanly on Python 3.12 inside bwrap (no third-party code was run).
- litellm's import-time network fetch; BFCL `_last_modified` timestamps in multi-turn state comparison.
- Which data revision produced BFCL-Result `2025-12-16`; the benchmark version of the older AgentDojo runs; trial counts in the gemini tau2 files.
- EvalPlus or BigCodeBench release-asset sample archives (GitHub releases API and web UI blocked; one guessed BigCodeBench URL returned 404); the MultiPL-E-completions license.
