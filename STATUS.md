goal_turn: 2
STATE: ACTIVE

# graderproof status

Updated 2026-10-23 (bootstrap). History lives in docs/LOG.md.

## Gates (from `python tools/ship_check.py --fast`; only a full run counts)

Fast check on b28b8f1 (2026-10-23): **3/14**.

| Gate | State | Evidence or blocker |
|---|---|---|
| G1 Build and tests | PASS | 53 tests; core line coverage over 3 package files above the 85% floor |
| G2 Static quality | PASS | ruff, ruff format, mypy --strict clean; no bare ignores |
| G3 CI parity | FAIL | ci.yml ok; `make ci` fails at `demo` (not built) |
| G4 Offline demo | FAIL | `make demo` not built |
| G5 Tool validity | FAIL | E0 not run |
| G6 Validation integrity | FAIL | no headline variants |
| G7 Confirmatory audit | FAIL | no audits |
| G8 Repair | FAIL | E4 not run |
| G9 Impact and cards | FAIL | E5 not run, no cards |
| G10 Claim integrity | FAIL | no docs/REPORT.md; claimcheck and freshness not built |
| G11 Preregistration | FAIL | prereg-verify not built; no preregistrations |
| G12 Independent review | FAIL | no review yet |
| G13 Documentation | FAIL | README.md is still the brief |
| G14 Hygiene | PASS | secrets scan clean, cash 0, private/ untracked, tree clean |

## Now

Bootstrap done (docs/BUILD_BRIEF.md section 10.1). Next iteration starts M1 for G4 (the next failing gate on the critical path; G3 follows from it).

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

1. M1: `adapters.toybench` and the `run` subprocess sandbox (network off, temp workspace, scrubbed env, resource limits), with tests; try installing bubblewrap for write isolation (D4).
2. M1: classical violating operators and formatting preserving variants, deterministic witness validator, `score` with the ship-check bootstrap.
3. M1: recorded-fixture `make demo` with golden output (G4), then tag v0.1.

## Usage to date

- cash_usd = 0. Claude calls: 0. Local model calls: 0. Subagent runs: 0.

## Needs Raj

1. **Pushing.** `ALLOW_PUSH` is not set, but the session stop hook asked for a push, so commits now go to `claude/affectionate-volta-z2bm3c` on origin (D14; no force-push, no tags). Say so if you want local-only commits instead.
2. **Claude backend.** The cloud environment sets `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_USE_CCR_V2`, which trip the billing guard, so no headless Claude subject or review runs can happen here. Running the build on your machine with those variables unset enables them.
3. **Docker.** No Docker daemon here, so Harbor and Terminal-Bench 2.0 tasks need a Docker-free substitute (to be decided in DECISIONS.md before data collection) unless you run on a machine with Docker.

## Changed this turn

- Bootstrap: brief copied and hashed, doctor, CLAUDE.md, heartbeat prompt, subagents, scaffold, Makefile, CI, ship-check (G1 to G14), plan, decisions D1 to D13.
- Fixed a ship-check bug found on its first run (G3 parsed uv's stderr warning as YAML).

## Blocked

Nothing yet.

## Backlog (suggestions for Raj, not ladder rungs)

- A `graderproof check` pre-commit mode that runs only the deterministic operators on a single changed task in under a minute, so benchmark authors get feedback before CI.
