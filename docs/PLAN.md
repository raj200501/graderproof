# graderproof build plan

Milestones mapped to the Definition-of-Done gates (docs/BUILD_BRIEF.md section 6), the risks, environment-dependent fallbacks, and usage estimates. Written at bootstrap on 2026-10-23 from the `make doctor` output recorded in STATUS.md; revised as the environment or the evidence changes (revisions are dated below).

## Environment at bootstrap (from `make doctor`)

- Linux x86_64, 4 CPUs, 15.7 GiB RAM, no GPU, about 29 GiB free disk (floor 8 GiB).
- Python 3.11, 3.12, and 3.13 available; uv installed. Development venv uses 3.12; CI covers 3.11 and 3.12.
- Docker client present, **no Docker daemon**.
- `claude` CLI logged in, but **unusable**: the billing guard fires on `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_USE_CCR_V2`, which this cloud environment sets.
- **No local model runtime** (no Ollama, llama.cpp, or transformers yet).
- Sandbox: no bwrap; `unshare -rn` (user and network namespace) works.
- Free tiers not confirmed; `ALLOW_PUSH` unset.

## Milestones

| Milestone | Builds | Gates | Tag |
|---|---|---|---|
| M0 Bootstrap | brief copy and hash, doctor, CLAUDE.md, subagents, scaffold, Makefile, ship-check, plan | G2, G14 (partly) | |
| M1 Offline core | `adapters.toybench`, `run` (subprocess sandbox with resource limits, content-addressed cache, determinism pre-check), classical `variants.violating` operators for Python and shell, formatting `variants.preserving`, deterministic witness validator, `score` (stdlib bootstrap identical to ship-check), `graderproof audit` on toybench, recorded-fixture `make demo` with golden output | G1, G3, G4 | v0.1 |
| M2 Tool validity (E0) | toybench of at least 60 tasks planted by a separate subagent that has not read `variants/` or `validate/`; labels kept in `private/` with only their hash committed before the first run; second validator; E0 run, recall and precision with intervals, docs/E0_MISSES.md | G5, G6 (toybench part) | |
| M3 Public adapters | BFCL-style checkers (AST and executable), tau2-bench-style stateful tool use, inspect_evals deterministic scorers, Harbor/Terminal-Bench 2.0 (Docker) or a Docker-free substitute; recorded-fixture contract tests for each; docs/DATA.md | G1 (coverage) | |
| M4 Confirmatory audit (E1, E2) | power analysis; `prereg/0001-*` frozen before data; stratified sample with a fixed seed (at least 40 tasks per benchmark or all); E1 and E2 on at least 3 benchmarks with intervals and Holm correction | G6, G7, G11 | v0.5 |
| M5 Root causes, repair, lint (E3, E4, E6) | rule-based and model coders with agreement; repair synthesis and acceptance rules; one patch per task (third-party patches in `private/outbound/patches/` with a tracked MANIFEST); post-repair generalization batch; lint AUC | G8 | |
| M6 Impact and cards (E5) | re-grade public per-task artifacts (BFCL result files, tau2-bench trajectories); pass flips and rank changes with a paired bootstrap; grader cards (Markdown and JSON, aggregates only) | G9 | |
| M7 Claims, docs, review | port prereg chain, claimcheck, and freshness from raise-v1-public (Apache-2.0, with attribution); citecheck; `make report` figures; README per section 11; docs/REPORT.md (4,000 to 8,000 words); independent review; final sequence (section 10.6) | G10, G11, G12, G13 | v1.0 |

Order of work follows the critical path: M1 unblocks G1, G3, G4 and every later experiment; M2 must finish before any public audit so the tool's validity is known before it is used; the preregistration in M4 is frozen before any confirmatory data exists. Gate tooling for G10 to G13 (M7) can be built in parallel with experiments because it needs no model calls.

## Risks and fallbacks

| Risk | Effect | Fallback (recorded in DECISIONS.md before acting) |
|---|---|---|
| No Docker daemon | Harbor and Terminal-Bench 2.0 tasks cannot run | Choose and justify a Docker-free terminal or coding substitute before data collection; keep the Harbor adapter with recorded-fixture contract tests |
| Claude backend unusable (billing guard) | No headless Claude subjects, pipeline calls, or headless review | Reviewer and citation-checker subagents for small jobs; local open-weight model for bulk model calls; record in Needs Raj that running on Raj's machine with no guard variables enables the Claude arms |
| No local model runtime yet | Requirement-targeted variants and the model validator have no backend | Install a CPU runtime (llama.cpp or transformers) with a pinned model of at most 8B parameters, if the network policy allows the download and disk stays above the floor; otherwise use subagents for the handful of model validations and report reduced coverage |
| Model download blocked by network policy | Same as above | Subagents for small batches; restrict E0 and E1 model-based variants to what the budget allows; deterministic operators still run |
| No bwrap | Third-party graders cannot be write-restricted by bwrap | Try installing bubblewrap; otherwise `unshare -rn` plus a temporary workspace with credentials stripped; if write isolation is insufficient, run only this project's own generated tasks and add it to Needs Raj |
| Benchmark data licenses | Some data may not be redistributable | Commit only aggregates and hashes; record source, license, and retrieval date in docs/DATA.md |
| Flaky graders | Biased rates | Determinism pre-check with k runs on the reference; flaky tasks reported separately, never dropped silently |
| Gate tooling false passes | Shipping on a false PASS | Independent reviewer audits every gate implementation; empty sets fail; mutation tests for gates ported from raise-v1-public |

## Usage estimates (to be refined after M1)

- Claude plan: 0 calls while the billing guard fires. If Raj enables it: about 6 review runs in total and up to a few hundred single calls (batched 20 to 50 items) across E0, E1, E3.
- Local model (CPU, about 7B parameters at 4-bit): about 180 tasks (60 toybench plus 3 benchmarks of 40) need one batched requirement-extraction call and one batched variant-proposal call each, and about 1,800 variants need batched validation (20 to 50 per call). Roughly 450 calls of about 1,000 output tokens, a few hours of background CPU time at single-digit tokens per second.
- Subagents: reviewer at each milestone (about 8 runs, capped at 6 per day), citation checker once for related work.
- Cash: 0.

## Revisions

- 2026-10-23: initial plan at bootstrap.
- 2026-11-04: status after the restart. M1 is done (v0.1: offline demo, G1 to G4 and G14 pass in the fast check). Built ahead of their milestones: the E0 scorer, E4 repair synthesis and execution-based validation, E6 grader lint, E3 rule-based and model root-cause coders, and the preregistration chain. In progress: the HumanEval, BFCL, and tau2-bench adapters and the claim tooling (claimcheck, freshness, citecheck, report), each built and independently verified in its own worktree; the E0 planted set (independent planting agent); GitHub reference re-verification through git. Benchmarks are fixed in D18 (tau2-bench v1.0.1, BFCL V4 AST, HumanEval as the Terminal-Bench substitute, AgentDojo only if its adapter is ready before the E1 preregistration).
- 2026-11-04: usage estimate revised from the demo's actual consumption. A small task yields about 20 to 35 variants, so a 40-task benchmark needs roughly 1 requirement-extraction call per 8 tasks, 1 proposal call per 4 to 6 tasks, and 1 review call per 25 to 40 variants: about 35 to 60 single calls per benchmark, and about 75 for E0. With CAP_SHARE = 0.2 the daily cap is 60 single calls, so E0 takes about two days of cap and E1/E2 about three more; E3 model coding and the E4 generalization batch add a day. The model-call cap, not compute, is the binding constraint, so model work runs strictly in order (E0, then E1/E2, then E3 and E4) while code and documentation proceed in parallel.
