# Data sources, licenses, and retrieval

Every dataset graderproof reads or produces, with its source, license, and retrieval date (non-negotiable 9). Third-party data is fetched by the adapters from pinned commits into the git-ignored `runs/` directory and is not redistributed, except small verbatim samples kept as contract-test fixtures under `tests/fixtures/`, which their licenses allow with attribution. Task-level findings about third-party tasks not yet fixed upstream are kept in the git-ignored `private/` directory (non-negotiable 14).

## Project-written data

| Data | Location | Origin | License |
|---|---|---|---|
| Demo tasks | `examples/demo/` | written for this project to exercise the pipeline | MIT (this repository) |
| toybench (E0 planted ground truth) | `toybench/tasks/`, labels `toybench/labels.json` | written by an independent planting agent for E0 (D22); synthetic tasks, not drawn from any benchmark | MIT (this repository) |
| Model requests and responses | `examples/demo/model_store/`, `artifacts/model_calls/` | graderproof's client wrapper; answered by Claude Code subagents (D17) | MIT (this repository) |

All toybench and demo results are results on synthetic, project-written tasks and are labeled as such wherever they appear (non-negotiable 4).

## Third-party benchmarks (D18)

Filled in when each adapter is merged, from the adapter's pinned constants and the citation record in `artifacts/citecheck.json`.

| Benchmark | Source | Pinned version | License | Retrieved | Used for |
|---|---|---|---|---|---|
| tau2-bench (airline, retail, telecom base tasks) | https://github.com/sierra-research/tau2-bench | tag v1.0.1, commit fc0055dc4e0a316c3f83133267fbd6faaa770992; 17 pinned file hashes in docs/adapters/tau2.md | MIT, Copyright (c) 2025 Sierra Research; the four fixture records under `tests/fixtures/tau2/` keep upstream's LICENSE | 2026-11-04 (git clone) | E1, E2, E5 |
| BFCL V4 (berkeley-function-call-leaderboard), eight Python AST categories | https://github.com/ShishirPatil/gorilla | commit 6ea57973c7a6097fd7c5915698c54c17c5b1b6c8; question-file hashes in docs/adapters/bfcl.md | Apache-2.0; the five fixture records under `tests/fixtures/bfcl/` keep upstream's LICENSE | 2026-11-04 (sparse git checkout) | E1, E2 |
| HumanEval | https://github.com/openai/human-eval | commit b9453e8f1865df0a0057a1383767caa400acfbcf; `data/HumanEval.jsonl.gz` SHA-256 b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef (docs/adapters/humaneval.md) | MIT, Copyright (c) OpenAI; generated graders and the five fixture records keep the notice | 2026-11-04 (git clone) | E1, E2 (Terminal-Bench substitute) |

## Released results used for impact (E5)

Filled in before the E5 analysis: the tau2-bench v1.0.1 text trajectories published by the tau2-bench maintainers (source listed in docs/research/benchmarks_survey_2026-10-23.md), with the license terms recorded when they are retrieved. Only aggregate pass rates and pass flips are published; trajectories are not redistributed.
