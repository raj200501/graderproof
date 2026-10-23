goal_turn: 1
STATE: ACTIVE

# graderproof status

Updated 2026-10-23 (bootstrap). History lives in docs/LOG.md.

## Gates (from `python tools/ship_check.py --fast`; only a full run counts)

Pending the first fast check after the bootstrap commit.

## Now

Bootstrap (docs/BUILD_BRIEF.md section 10.1).

## Environment (`make doctor`, 2026-10-23)

- Linux x86_64, 4 CPUs, 15.7 GiB RAM, no GPU, 29.4 GiB free disk (floor 8 GiB).
- Python 3.11 and 3.12 present; uv 0.11.32; dev venv on 3.12.
- Docker: client yes, daemon no.
- Claude CLI: logged in, unusable (billing guard: `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_USE_CCR_V2`).
- Local models: none installed (no Ollama, llama.cpp, or transformers).
- Sandbox: `unshare -rn` (user and network namespace) with a temp workspace; no bwrap, no Docker.
- Free tiers: not confirmed. ALLOW_PUSH: not set. CAP_SHARE: not set.
- Backends usable now: none for model calls; subagents for small jobs.

## Next three actions

1. M1: `adapters.toybench` and the `run` subprocess sandbox (network off, temp workspace, scrubbed env, resource limits), with tests.
2. M1: classical violating operators and formatting preserving variants, deterministic witness validator, `score` with the ship-check bootstrap.
3. M1: recorded-fixture `make demo` with golden output (G4), then tag v0.1.

## Usage to date

- cash_usd = 0. Claude calls: 0. Local model calls: 0. Subagent runs: 0.

## Needs Raj

1. **Pushing.** This runs in an ephemeral cloud container and `ALLOW_PUSH` is not set, so commits stay local and are lost if the container is reclaimed. To keep them, set `ALLOW_PUSH=1` in the environment (or run on your own machine as section 0 describes).
2. **Claude backend.** The cloud environment sets `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_USE_CCR_V2`, which trip the billing guard, so no headless Claude subject or review runs can happen here. Running the build on your machine with those variables unset enables them.
3. **Docker.** No Docker daemon here, so Harbor and Terminal-Bench 2.0 tasks need a Docker-free substitute (to be decided in DECISIONS.md before data collection) unless you run on a machine with Docker.

## Blocked

Nothing yet.

## Backlog (suggestions for Raj, not ladder rungs)

- A `graderproof check` pre-commit mode that runs only the deterministic operators on a single changed task in under a minute, so benchmark authors get feedback before CI.
