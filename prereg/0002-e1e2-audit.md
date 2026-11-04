# 0002 E1 and E2: confirmatory grader audit on three public benchmarks

Status: confirmatory for gates G6, G7, and G11 (docs/BUILD_BRIEF.md sections 5 and 6). Frozen on 2026-11-04; the chain entry in prereg/FROZEN.jsonl records the exact time, the file hash, and the parent commit. Secondary analyses E3 to E6 are preregistered at the end; anything not listed here is exploratory. Decisions it relies on: DECISIONS.md D8, D15 to D19, D23 to D33.

## Questions

- **E1**: on what share of tasks does each benchmark's grader accept at least one validated spec-violating variant of the reference solution (task-level false accept)?
- **E2**: on what share of tasks does it reject at least one validated spec-preserving variant (task-level false reject)?

## Benchmarks (chosen in D18 before any data collection)

| Benchmark | Category | Version | Converted tasks | Strata |
|---|---|---|---|---|
| tau2-bench, airline, retail, and telecom base tasks without LLM-judged assertions | tool-use | tag v1.0.1, commit fc0055dc4e0a316c3f83133267fbd6faaa770992 (D32) | 238 | domain |
| BFCL V4, the eight Python AST categories | function-calling | gorilla commit 6ea57973c7a6097fd7c5915698c54c17c5b1b6c8 (D31) | 2351 | category |
| HumanEval, substitute for Terminal-Bench 2.0 (D18) | coding | human-eval commit b9453e8f1865df0a0057a1383767caa400acfbcf (D29) | 164 | prompt length: `prompt-short` below 335 characters, `prompt-medium` 335 to 474, `prompt-long` 475 or more |

Tasks are converted by each adapter's `fetch` and `convert` commands from the pinned commits into the git-ignored `runs/<benchmark>/tasks/`; conversion is deterministic (docs/adapters/). The sampling frame of each benchmark is its converted tasks minus the contract-test fixture tasks listed in `prereg/0002-exclude.txt` (SHA-256 `82fb9bf01866ae6f8e1c5110b1d5e5f806860de0c884a738cfa6b0183d4e4925`), which were used to build and test the adapters. A task whose reference fails its own grader stays in the frame; it is reported as reference-rejected and is not scorable (D26).

## Sample

- 40 tasks per benchmark, by stratified random sampling without replacement: stratum quotas proportional to the frame with largest-remainder rounding, then uniform sampling within each stratum with `random.Random(f"{benchmark}:2027")` over the sorted task ids (`tools/sample.py`). Command: `python3 tools/sample.py --bench tau2=runs/tau2/tasks --bench bfcl=runs/bfcl/tasks --bench humaneval=runs/humaneval/tasks --n 40 --seed 2027 --exclude prereg/0002-exclude.txt --out prereg/0002-sample.json --materialize runs/e1`.
- The sample is committed with this file as `prereg/0002-sample.json`, SHA-256 `7f56987c8e9dc4081893176b4b2e66867e4e04923acfc2d8244b81dc1b9f9410`. Each audit refuses to run unless its tasks are exactly that benchmark's sampled tasks (`--sample`).
- **Power** (`artifacts/prereg/power_e1e2.json`, SHA-256 `02a3cf9245bb995217ccf7674f8f2b5772742cb276bade4758432ca9ba2e37bf`, from `tools/power.py --m 3`): at n = 40 and the least favourable Holm level alpha / 3, the exact one-sided test of a false-accept rate above 0.10 rejects from 9 flagged tasks and has power 0.89 against a true rate of 0.30; the test of a false-reject rate above 0.05 rejects from 6 flagged tasks and has power 0.84 against a true rate of 0.20. The worst-case half-width of a 95% proportion interval at n = 40 is 0.15. A benchmark with fewer than 40 scorable tasks has less power; this is reported, and no task is replaced.

## Dry run

Before freezing, the audit command was run once per benchmark on three excluded fixture tasks (disjoint from the frame) with a scratch store and cache and no model calls, only to confirm that each adapter's sandbox environment works through `graderproof audit`. Nothing from the dry run is used.

## Tool, frozen

- **Code**: graderproof at the commit that adds this file; its `src/graderproof/` tree is `ba2581db003f3211bf25c310362fd7fcc500f979` and its `uv.lock` blob is `735d0cdaae6ed1369e1534b811437d7d09e1cff3`. As for E0 (D28), the audits run from a detached git worktree at that commit, so development may continue elsewhere; provenance records the package source fingerprint, the commit, and `git_dirty`. E4 (below) runs from the same worktree. A fix for an infrastructure failure is made only through a dated amendment committed before the data it affects.
- **Configuration**: the E0 configuration (prereg 0001) with the E1 seed: classical violating and preserving operators sampled at most 6 per operator and 40 per task, model proposals `propose/v1`, requirements `requirements/v1`, model review `review/v1`, k = 3 reference runs, 2 confirmation runs for every flagged verdict, B = 2000 bootstrap replicates, sandbox bwrap. Model backend: Claude Code `model-worker` subagents (alias sonnet) through the client wrapper within the daily cap (D15, D17); every worker transcript is audited with `tools/transcript_audit.py` as for E0 (D24), and a response from a worker that touched another file is discarded and answered again.
- **Batch sizes** keep each request file near the size E0's workers handled: tau2 extract 6, propose 6, review 15; BFCL extract 8, propose 6, review 25; HumanEval extract 8, propose 6, review 40. Batch size changes no prompt.
- **Commands** (from the frozen worktree, where `runs/e1/<benchmark>/` holds links to the sampled task directories and `artifacts/audit/<benchmark>` and `artifacts/model_calls/<benchmark>` are links into the main checkout `<main>`; common flags `--adapter toybench --sandbox bwrap --confirmatory --prereg prereg/0002-e1e2-audit.md --sample prereg/0002-sample.json --ledger <main>/artifacts/usage/ledger.jsonl --review-queue <main>/private/review_queue --k 3 --confirm-runs 2 --seed 2027 --max-per-operator 6 --max-total 40 --replicates 2000`):
  - `graderproof audit runs/e1/tau2 --category tool-use --env GP_TAU2_ROOT=<main>/runs/tau2/src --env GP_TAU2_PYTHON=<main>/runs/tau2/venv/bin/python --store artifacts/model_calls/tau2 --cache <main>/runs/cache-tau2 --out artifacts/audit/tau2 --evidence <main>/private/evidence/tau2 --extract-batch 6 --propose-batch 6 --review-batch 15`
  - `graderproof audit runs/e1/bfcl --category function-calling --env GP_BFCL_ROOT=<main>/runs/bfcl/src/berkeley-function-call-leaderboard --env GP_BFCL_PYTHON=/usr/bin/python3.12 --store artifacts/model_calls/bfcl --cache <main>/runs/cache-bfcl --out artifacts/audit/bfcl --evidence <main>/private/evidence/bfcl --extract-batch 8 --propose-batch 6 --review-batch 25`
  - `graderproof audit runs/e1/humaneval --category coding --substitute-for terminal-bench-2.0=D18 --store artifacts/model_calls/humaneval --cache <main>/runs/cache-humaneval --out artifacts/audit/humaneval --evidence <main>/private/evidence/humaneval --extract-batch 8 --propose-batch 6 --review-batch 40`
- **Disclosure**: these are third-party tasks not fixed upstream, so public artifacts carry task hashes only; task ids, surviving variants, and witnesses stay in `private/` (non-negotiable 14).

## Outcomes and definitions

- A variant counts only with two agreeing, independent validations (deterministic witness and model review), a witness, and a stable grader verdict over the confirmation runs (G6). Variants whose validators disagree, including any `unsure` model verdict, are excluded and listed in the private review queue.
- **Scorable task**: the grader passes the reference in all k = 3 runs (`stable_pass`, D26). Tasks whose grader rejects the reference or is flaky on it are reported separately and excluded from both rate denominators.
- **E1 false accept (task level)**: the grader accepts at least one counted violating variant.
- **E2 false reject (task level)**: the grader rejects at least one counted preserving variant.
- **Rates**: share of scorable tasks with a false accept (E1) or false reject (E2), with percentile task bootstrap intervals, B = 2000, alpha = 0.05, seed 2027 for E1 and 2028 for E2 (`graderproof.stats`; ship-check recomputes them).
- **Per-task mutation score**: killed counted violating variants over counted violating variants, reported per benchmark as a distribution (median and interquartile range).

## Hypotheses (confirmatory; Holm across the three benchmarks at family-wise alpha = 0.05, separately for each family)

- **H1** (one per benchmark): the task-level false-accept rate exceeds 0.10. Exact one-sided binomial test of the number of scorable tasks with a false accept.
- **H2** (one per benchmark): the task-level false-reject rate exceeds 0.05. Same test.

Directions are not presumed: a benchmark where H1 or H2 is not rejected is reported, with the same prominence and its interval, as evidence that its grader is mostly adequate in that direction.

## Secondary analyses (preregistered)

- **E3 root causes**: every counted surviving violating variant and every counted wrongly rejected preserving variant is coded into the section 3 taxonomy by the rule-based coder and by the model coder (`graderproof.rootcause`, prompt `rootcause/v1`). Report the code distribution per benchmark, raw agreement, and Cohen's kappa; disagreements are listed, not resolved by the build session.
- **E4 repair** (`graderproof repair`, from the frozen worktree): every scorable task with a surviving violating variant gets a repair attempt that grafts checks for the broken requirements onto the original grader. A repair is accepted only if the patched grader passes the reference k = 3 times, still accepts every counted preserving variant it accepted, rejects every target, and is deterministic. Report repaired, unrepairable (with reason), and rejected repairs, and mutation score before and after. **Generalization**: a fresh batch on the repaired tasks (variant seed 3027, model proposal round 2); report the share of fresh surviving violating variants the repair catches and the number of repair-induced false rejects. toybench (E0) tasks with surviving variants are repaired the same way, with the E0 audit seed 2026 (generalization seed 3026); their patches are public (`outbound/patches/`), third-party patches stay private with hashes in `outbound/patches/MANIFEST.json` (G8).
- **E5 impact** (tau2-bench): the released tau2-bench v1.0.1 text trajectories of the eight models listed in docs/research/benchmarks_survey_2026-10-23.md (claude-opus-4-5, claude-sonnet-4-5, gpt-5.2 high, gpt-5.2 none, gemini-3-pro, gemini-3-flash, glm-5, qwen3.5-397b-a17b; four trials each), restricted to the sampled tau2 tasks, are re-graded with the original grader (tau2's own evaluation with `strict_replay=False`, as in tau2's re-grading script) and with the repaired grader (the accepted E4 repair where one exists, else the original). Rows are `{model, task_hash, trial, original_pass, repaired_pass}`. Report each model's pass rate before and after; **pass flips** = rows that pass originally and fail after repair, over rows that pass originally; **rank changes** = model pairs whose ordering by pass rate differs between the two gradings. Intervals: task bootstrap over distinct task hashes, B = 2000, seed 2029 for pass flips and 2030 for rank changes. The share of rows where the original-grader replay matches the published reward is reported as a check. Trajectories are not redistributed (docs/DATA.md records source and terms).
- **E6 lint**: AUC of the `graderproof.lint` score for predicting a per-task mutation score below 0.8, over all scorable audited tasks of the three benchmarks with a defined mutation score, with a task bootstrap interval (B = 2000, seed 2031). **H6**: the AUC exceeds 0.5 (the interval excludes 0.5).

## Stopping rule and deviations

One audit per benchmark. When the daily model cap interrupts a run, it resumes from the banked responses and the execution cache with the identical configuration. No sampled task is replaced or dropped. Every preregistered outcome is reported. Any change after freezing is a dated amendment file that cites this one, committed before the data it affects, and reported as a deviation.
