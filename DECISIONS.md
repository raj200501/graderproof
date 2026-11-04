# Decisions

Assumptions, interpretations, substitutions, and deviations, each dated and written before acting on it (non-negotiable 10). Newest last. Decision ids are stable and are cited by artifacts (for example `substitute_for.decision`).

## D1 (2026-10-23) No push without ALLOW_PUSH

`ALLOW_PUSH` is not set in this environment. The cloud harness designates a working branch, but docs/BUILD_BRIEF.md section 10.1 step 11 and non-negotiable 8 allow pushing only when `ALLOW_PUSH=1`. Commits stay local. Because this is an ephemeral cloud container, unpushed commits are lost if the container is reclaimed; this is listed under Needs Raj.

## D2 (2026-10-23) Claude backend unusable here

`make doctor` reports `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_USE_CCR_V2` set by the cloud environment, so the section 8 billing guard marks headless Claude unusable. No `claude -p` children are launched. Small pipeline jobs (reviews, citation checks) use Claude Code subagents, which the brief allows for a handful of calls; bulk model work needs a local open-weight model. Experiments that use Claude as a test subject are not possible in this environment (Needs Raj).

## D3 (2026-10-23) No Docker daemon

The Docker client is installed but no daemon runs. Harbor and Terminal-Bench 2.0 tasks cannot execute here. A Docker-free substitute for the terminal or coding benchmark will be chosen and justified in its own decision entry before any data collection, as G7 requires.

## D4 (2026-10-23) Sandbox fallback

No bwrap and no Docker. `unshare -rn` (unprivileged user and network namespace) works and is the network-isolation layer for now, combined with a temporary workspace and a scrubbed environment. Write isolation outside the workspace is not yet enforced by it; installing bubblewrap is the next attempt. Until a write-restricting sandbox works, only this project's own generated tasks (toybench) are executed.

## D5 (2026-10-23) Meaning of "core modules" in G1

Coverage is computed over every Python module under `src/graderproof/`, not only the `core` submodule. The only exclusions allowed are adapters that need external services, listed in `pyproject.toml` under `[tool.graderproof.coverage] external_adapters`, and each must have `tests/contract/test_<stem>.py` with recorded fixtures in `tests/fixtures/<stem>/`. ship-check also requires every package file to appear in coverage.json, so `omit` settings cannot hide files.

## D6 (2026-10-23) Empty sets fail

A gate whose property ranges over a set (preregistrations, confirmatory artifacts, headline variants, cited references, audited benchmarks) fails when the set is empty. This is stricter than a literal reading, never weaker.

## D7 (2026-10-23) Review diff rule and the review log

The reviewed commit may differ from HEAD only in `artifacts/review/`, `STATUS.md`, and `docs/LOG.md`, exactly as section 10.1 step 8 says. docs/REVIEW_LOG.md is outside that set, so the non-blocking issues of a review are added to docs/REVIEW_LOG.md before the next review, and the final review must find no non-blocking issue missing from the log.

## D8 (2026-10-23) Statistics procedure fixed in ship-check

Intervals are percentile bootstraps over tasks with `random.Random(seed)` as documented in tools/ship_check.py, so ship-check can recompute every banked interval exactly with the standard library. graderproof's `score` module will use the identical procedure and a test will assert the two agree. Where one artifact carries two intervals the second uses `seed + 1`.

## D9 (2026-10-23) Preregistrations are committed once

A file `prereg/NNNN-*.md` is committed exactly once, when frozen. Drafts live outside `prereg/` (in `runs/` or `private/`). ship-check fails G11 if any preregistration file has more than one commit.

## D10 (2026-10-23) Em dash rule scope

The no-em-dash rule (non-negotiable 12) is enforced by `make lint` on every tracked text file. Verbatim third-party material under `tests/fixtures/` and `third_party/` is exempt because it is not Claude's writing and must stay byte-exact for recorded-fixture tests.

## D11 (2026-10-23) Budget history check

`make budget` checks each past day against the base caps in budget.toml. `CAP_SHARE` lowers the caps the client wrapper enforces from the moment it is set, so applying it retroactively to days before it was set would misreport. Today's effective caps under `CAP_SHARE` are printed alongside.

## D12 (2026-10-23) goal_turn counting

`goal_turn` in STATUS.md counts every working turn of the build (heartbeat or goal), starting at 1 for the bootstrap turn.

## D13 (2026-10-23) Fast ship-check scope

`tools/ship_check.py --fast` skips only the `make ci` rerun for G3 and derives G3 from the lint, typecheck, test, and demo steps already run for G1, G2, and G4. Every other check runs as in the full mode. Its result never counts.

## D14 (2026-10-23) Push to the session branch (supersedes D1)

The session's stop hook asked for the unpushed commits to be pushed, and the cloud harness designates `claude/affectionate-volta-z2bm3c` as the working branch. The harness treats hook output as the user's feedback, and the container is ephemeral, so unpushed work would be lost. Commits are pushed to that branch on `origin` only, never force-pushed, never with tags, and no repository setting or visibility is changed, which keeps every other limit of section 10.1 step 11. If Raj wants local-only commits, unsetting the hook or saying so restores D1.

## D15 (2026-10-23) Raj's launch settings for this cloud session

Raj's goal message sets, for this Claude Code on the web session: `ALLOW_PUSH=1` (push every commit to the session's working branch `claude/affectionate-volta-z2bm3c`, never force-push, never push tags, never change repository settings) and `CAP_SHARE=0.2` (five projects share one Max plan). The variables are not present in the process environment, so they are treated as set: pushing follows the rule in section 10.1 step 11, and `cap_share = 0.2` is written to budget.toml, where the budget tool and the client wrapper take the lower of it and any `CAP_SHARE` in the environment. Effective daily caps are therefore 6 agent runs, 60 single calls, and 1 review run. This supersedes D1 and D14.

## D16 (2026-10-23) bubblewrap installed

`apt-get install bubblewrap` succeeded (bubblewrap 0.9.0). A probe confirmed a read-only root, a writable workspace only, no network, and a scrubbed environment. bwrap is now the preferred sandbox for third-party graders here; D4's restriction to project-generated tasks applies only on machines where neither Docker nor bwrap works. `make doctor` detects this per machine, and a fresh container needs the same install.

## D17 (2026-10-23) Claude Code subagents as the model backend for pipeline calls

With headless Claude blocked (D2), model-dependent pipeline steps (requirement extraction, requirement-targeted variant proposals, model validation, model root-cause coding) run as Claude Code subagents. To keep section 8's guarantees, every such call goes through the client wrapper as a file-based request: the wrapper writes a content-addressed request (prompt version, batched items) and only reads a response stored under the same hash, so a banked call is never re-run, and each request served counts as one `single_call` in the usage ledger against the effective cap of 60 per day. Batches hold 20 to 50 items. A local open-weight model on CPU remains an option for an independent second model where its speed allows.

## D18 (2026-10-23) Benchmarks for E1/E2 and the Docker-free substitute (before any data collection)

Chosen from the survey in docs/research/benchmarks_survey_2026-10-23.md. No E1/E2 data exists yet.

1. **tau2-bench at tag v1.0.1** (tool use). Deterministic reward components only: airline (50 base tasks, DB plus substring communicate), telecom (114 base tasks, env assertions and actions), retail (the 74 base tasks without NL assertions). v1.0.1 is the version every released text trajectory was graded with, so E5 can re-grade them. The 40 retail tasks with NL assertions need an LLM judge and are excluded (reported).
2. **BFCL V4, AST categories in Python** (function calling): simple_python, multiple, parallel, parallel_multiple, and the live_* Python categories, graded by `ast_checker` from bfcl-eval pinned to a commit. Public per-model outputs (HuanzhiMao/BFCL-Result, Apache-2.0) are an E5 candidate.
3. **AgentDojo** user tasks (tool use) with their deterministic `utility()` checks, if its adapter is ready before the E1 preregistration is frozen; otherwise E1 runs on the other three.
4. **Substitute for Terminal-Bench 2.0: HumanEval** (164 tasks, MIT) with its original unit-test grader. Terminal-Bench 2.0 cannot run here: there is no Docker daemon, all 89 tasks need prebuilt images, and Harbor has no container-free environment. HumanEval is the closest Docker-free coding benchmark whose grader is a test suite run against a reference solution, the setting graderproof's classical operators target. EvalPlus HumanEval+ may be run beside it as an exploratory comparison only.

Each benchmark is pinned to a commit or release recorded in docs/DATA.md with its license and retrieval date. Third-party graders run only under bwrap (D16). Task-level findings for these benchmarks stay in `private/` (non-negotiable 14).

## D19 (2026-10-23) Adapters convert to the toybench execution format

Each public benchmark adapter converts tasks into toybench task directories (generated under `runs/`, reproducible from a pinned checkout) and reuses the toybench execution path, so caching, sandboxing, requirement checks, and variant operators are shared. A new task kind `data` covers benchmarks whose solution is data (a tool-call list or a function call): `support/run_solution.sh` turns the solution files into an outcome in the workspace (`.gp/state.json`, `.gp/trajectory.json`), and the grader is a driver that calls the benchmark's own grading code from the pinned checkout. For BFCL there is no separate reference solution; the reference is built from the first acceptable value of every required argument in `possible_answer`, which is grader data, so requirement extraction is told to rely on the question and function documentation only.

## D20 (2026-10-23) Commits are authored as Raj

Raj asked that every commit count toward his GitHub contributions. This checkout sets `git config user.name "Raj Kashikar"` and `git config user.email "65059626+raj200501@users.noreply.github.com"` (repository level, so it overrides the container's global identity). No `GIT_AUTHOR_*` or `GIT_COMMITTER_*` variable is set here; if one appears, commits pass `--author="Raj Kashikar <65059626+raj200501@users.noreply.github.com>"` instead. Every commit keeps the `Co-Authored-By: Claude` and `Claude-Session` trailers. Existing commits are never rewritten or force-pushed. The first commit under this rule (8bba7eb) was verified with `git log -1 --format='%an <%ae>'`.

## D21 (2026-10-23) GitHub Actions runs only for main

Raj's private-repository Actions minutes are limited. `.github/workflows/ci.yml` runs only on pushes to `main`, pull requests into `main`, and manual `workflow_dispatch`; never on pushes to `claude/` branches and never on a schedule. It has a concurrency group with `cancel-in-progress: true` and `timeout-minutes: 10` on its job, and stays lean (setup, `make ci`, secrets scan; no model downloads or experiments). No other workflow is added. `make ci` is run locally and must pass before every push, so nothing that reaches GitHub fails. One push (8bba7eb) skipped this check at Raj's explicit request. G3 (CI parity) is unaffected: the workflow still runs `make ci` on Python 3.11 and 3.12.

## D22 (2026-11-04) Interrupted adapter and planting agents

Raj stopped the session on 2026-10-23 while three adapter agents (HumanEval, BFCL, tau2-bench) and the E0 planting agent were running. Their git worktrees kept partial, uncommitted work: a HumanEval adapter module with contract tests and fixtures, and BFCL fixtures. The planting agent wrote nothing (no `toybench/` directory, no labels). On restart the partial adapters are finished and verified from their worktrees rather than discarded; the planting agent is started again from scratch with the same instructions, because a partial planted set cannot be trusted to be complete or consistent with its labels.

## D23 (2026-11-04) E0 detection and adjudication rules (review N5)

A planted task counts as **detected** only through a witness-backed flag in its planted direction: a false accept for `accept` weaknesses, a false reject for `reject` weaknesses. A grader that rejects the reference or is flaky on it under graderproof's harness is reported separately and is never a detection, because the planter verified every reference with its own harness and a mismatch there is more likely an infrastructure difference than a found weakness. Such planted tasks count as misses; such clean tasks are not flags. Recall counting reference-level flags as detections for `timing` tasks is reported only as an exploratory line. **Adjudication** follows brief section 5 ("a flag on a clean task whose witness validates is adjudicated as a real weakness"): every flag that is not a detection is re-checked by an independent reviewer subagent that sees the task text, the grader, the flagged variant, and its witness, and rules only whether the witness validates (the variant really breaks, or really keeps, the requirement it names). A validating witness makes the flag a real weakness, reported separately and excluded from precision's false positives; a non-validating witness makes it a false positive. Precision without adjudication is reported beside it.

## D24 (2026-11-04) Keeping the E0 labels out of the model channel (review N8)

Model request items identify tasks by `task.key_hash`, never by name. The labels stay in `private/toybench/labels.json` during the run; the model-worker subagent has only Read and Write tools and is told to read only its request file. Compliance is audited, not assumed: after the run, every model-worker transcript is scanned for any read of a path other than its assigned request file, and a response from a worker that read anything else is discarded and re-requested. The audit result is banked with the E0 artifacts.

## D25 (2026-11-04) Execution cache keys and confirmatory provenance (review N4, N6)

Execution cache keys include a fingerprint of the graderproof package source, the sandbox backend and its version, the resource limits, and the adapter's `extra_env`, so a code or environment change never serves an old execution. Sandbox start failures are not cached. Confirmatory runs (`graderproof audit --confirmatory --prereg <file>`) refuse to start when the working tree has uncommitted changes under `src/`, `tools/`, `prereg/`, or the task directory, and record the package source fingerprint, the sandbox version, the model IDs that answered, and every path they used. E0 and each E1 benchmark use their own cache directory.

## D26 (2026-11-04) Scorable tasks and validator agreement (review N10, N12)

A task is scorable only when its grader passes the reference stably (`determinism = stable_pass`); rates, ship-check recomputation, and E4 survivor lists all use this one definition. Validator agreement is computed over variants whose validators all returned a label verdict (violating or preserving); variants with an `unsure` or evidence-free verdict are counted and reported separately and never count as agreement.

## D27 (2026-11-04) Response hashes for responses ingested before they were recorded

From this date, ingesting a model response records the SHA-256 of the response file in its ledger line, and the client refuses to serve a response whose bytes changed after ingestion (`ResponseChangedError`). Ledger lines written before this change (the demo fixtures recorded on 2026-10-23) carry no hash; their responses are served without the check rather than re-requested, because re-requesting would spend calls to re-create fixtures that are already committed and whose content is in git history. Every confirmatory run uses only responses ingested after this change, so every confirmatory response is hash-checked. The demo store was re-recorded on 2026-11-04 after model items switched to task key hashes (D24); the old fixtures stay in the store and the ledger because those calls happened.

## D28 (2026-11-04) E0 runs from a frozen worktree with private/ hidden

E0 runs from a detached git worktree checked out at the commit that freezes its preregistration, so development can continue in the main checkout while the run is in progress, and the run provably uses the frozen code. The E0 labels stay in the main checkout's `private/`, which a worktree does not contain, so the bwrap sandbox now hides the `private/` directory of both the checkout the package was loaded from and, for a git worktree, its main checkout (found through the worktree's `.git` file), in addition to the home directory and `/tmp`. A confirmatory run refuses a sandbox that does not isolate writes (`unshare` or `local`), so E0 runs only under bwrap here.

## D29 (2026-11-04) HumanEval graders preload numpy, as upstream's evaluation does

Upstream's usual evaluation path (`evaluate_functional_correctness()` in `human_eval/evaluation.py`) imports numpy before any check forks, so a checked program can import numpy even though `reliability_guard()` has disabled `os.putenv`, which numpy's import calls. The generated HumanEval grader first had only standard-library imports, so a correct program that imports numpy failed with `'NoneType' object is not callable` and a preserving variant adding such an import would have counted as a false reject that HumanEval's own harness does not make. The grader now imports numpy before it forks when numpy is installed (it is in this environment's sandbox interpreter), matching upstream's normal path; tqdm and fire, which upstream's entry points also load, are not preloaded, because a solution importing them is implausible and they are not installed here. The contract test now checks that a numpy program passes the grader exactly as it passes upstream's `check_correctness()` with numpy preloaded. This changes no data: no HumanEval audit has run.

## D30 (2026-11-04) How claimcheck reads numbers

`tools/claimcheck.py` (G10) treats every number in README.md, docs/REPORT.md, and any other document a report template renders as a result number unless it is backed by a registered claim (rendered by `make report` from an artifact) or falls in an excluded context. Interpretations made while building it, recorded before it is used on any result:

- An allowlist row (`docs/claims/allowlist.tsv`) covers a number only when a match of the row's context pattern contains the number and extends beyond it; a line that merely matches somewhere is not enough.
- Excluded contexts: fenced and inline code, link destinations, valid reference definitions and `[n]` references that have a definition, footnote labels, HTML character references that do not render a digit, numbered headings, version strings, hex strings with at least one letter, dates, and numbers after a reference word (section, rule, step, figure, table, line, and similar). A bare `3.12` is checked; it counts as a version only after a tool word (Python, uv, version, and similar), with a `v` prefix, or with three dotted parts.
- Failures by construction: an unclosed code fence (it would hide the rest of the file), digits outside ASCII 0 to 9, and HTML references that render a digit.
- `artifacts/figures/manifest.json` is written only once a figure exists or when the file already exists. freshness fails when a rendered document, a figure, or the manifest differs from what `make report` would produce now.
- Known blind spots, documented in docs/claims/README.md and kept in mind when writing: a number from 1900 to 2099 reads as a year, a heading starting with a dotted number is excluded, "line 14"-style references are excluded, and spelled-out numbers are not seen. Result counts are therefore always rendered from templates, never typed, whatever their value.

## D31 (2026-11-04) BFCL reference solutions and grader setup

BFCL has no reference solution; graderproof builds one from the possible answer, which lists acceptable values per parameter. Read literally ("omit a parameter whenever `""` is acceptable", "take the first listed value"), the rule in D19 would drop parameters that the function documentation marks as required, and those references would fail for reasons that are not grader weaknesses. The rule is therefore: a parameter is omitted only when it has no acceptable value, or when its acceptable values include `""` (BFCL's marker for "may be omitted") and the documentation does not list it as required; otherwise it takes the first acceptable value other than `""` (or `""` when that is the only one); dict-valued parameters are built the same way key by key. The grader driver calls BFCL's own `ast_checker` with `Language.PYTHON`, the task's category, and model name `gorilla-openfunctions-v2` (BFCL's own model, whose `underscore_to_dot` is false, so function names are compared as written). BFCL's `model_config.py`, which the checker imports, imports every vendor SDK through the model handlers; the driver runs the real `model_config.py` but registers empty placeholder modules for `bfcl_eval.model_handler`, so no vendor SDK is needed and the checker code itself is unmodified. A reference that fails its own grader under this setup stays in the sampling frame and is reported as reference-rejected (prereg 0002); the task ids of such references are kept in `private/` (non-negotiable 14).
