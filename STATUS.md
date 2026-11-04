goal_turn: 3
STATE: ACTIVE

# graderproof status

Updated 2026-11-04 (restart after Raj's stop on 2026-10-23). History lives in docs/LOG.md.

## Gates (from `python tools/ship_check.py --fast`; only a full run counts)

Last fast check on 887bd70 (2026-10-23): **5/14**. A fresh check follows this turn's commit.

| Gate | State | Evidence or blocker |
|---|---|---|
| G1 Build and tests | PASS | full suite passes; package line coverage above the 85% floor |
| G2 Static quality | PASS | ruff, ruff format, mypy --strict clean; no bare ignores |
| G3 CI parity | PASS | ci.yml runs `make ci` on 3.11 and 3.12; parts pass |
| G4 Offline demo | PASS | under `unshare -rn`, no ledger change, matches golden |
| G5 Tool validity | FAIL | E0 not run (toybench not planted yet) |
| G6 Validation integrity | FAIL | no headline variants banked under artifacts/ |
| G7 Confirmatory audit | FAIL | adapters unfinished; no preregistration for E1/E2 |
| G8 Repair | FAIL | E4 not built |
| G9 Impact and cards | FAIL | E5 not built; no cards |
| G10 Claim integrity | FAIL | no docs/REPORT.md; claimcheck and freshness not built |
| G11 Preregistration | FAIL | prereg-verify built; no preregistrations yet |
| G12 Independent review | FAIL | no review yet |
| G13 Documentation | FAIL | README.md is still the brief; citecheck not built |
| G14 Hygiene | PASS | secrets scan clean, cash 0, private/ untracked, tree clean |

## Now

Restart: finish the three interrupted adapters (HumanEval, BFCL, tau2-bench), restart the E0 planting agent, and build the claim tooling (claimcheck, freshness, citecheck), in parallel and in separate worktrees (D22).

## Environment (`make doctor`, 2026-10-23; same container on 2026-11-04)

- Linux x86_64, 4 CPUs, 15.7 GiB RAM, no GPU, about 26 GiB free disk (floor 8 GiB).
- Python 3.11 and 3.12; uv; dev venv on 3.12. bubblewrap 0.9.0 installed (D16).
- Docker: client yes, daemon no (D3; Terminal-Bench substitute in D18).
- Claude CLI: logged in, unusable (billing guard: `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_USE_CCR_V2`); model calls go through file requests answered by Claude Code subagents (D17).
- Local models: none installed.
- Launch settings (D15): ALLOW_PUSH=1 (push to `claude/affectionate-volta-z2bm3c`), CAP_SHARE=0.2 (6 agent runs, 60 single calls, 1 review run per day).
- Commits are authored as Raj (D20). CI runs only for main (D21); `make ci` passes locally before every push.

## Next three actions

1. Merge the finished adapters; write docs/DATA.md entries (source, license, retrieval date) for each benchmark.
2. Plant toybench (E0), commit the tasks and the label hash, freeze prereg/0001 for E0, then run E0 through the model queue within the daily cap.
3. Build claimcheck, freshness, and citecheck; re-verify the GitHub-hosted references through git (the web pages return 403 here).

## Usage to date

- cash_usd = 0. Single calls through the client wrapper: 9 (2026-10-23: 1 requirements, 2 proposal, 6 review batches for the demo). Subagent runs outside the wrapper: 1 citation check, 1 benchmark survey, 3 adapter agents (stopped), 1 planting agent (stopped), 1 malformed-response fix.

## Needs Raj

1. **Claude backend.** The cloud environment sets `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_USE_CCR_V2`, which trip the billing guard, so no headless Claude subject or review runs can happen here (D2). Model work uses subagents instead (D17).
2. **Docker.** No Docker daemon here, so Terminal-Bench 2.0 is replaced by HumanEval (D18). Running on a machine with Docker would allow the original.
3. **References to check by hand** (scripted access blocked): the OpenAI SWE-bench Verified post (Cloudflare challenge). It is dropped from the docs unless you confirm it opens.

## Changed this turn

- Recorded D20 (commits authored as Raj), D21 (CI only for main), and D22 (interrupted agents).

## Blocked

Nothing.

## Backlog (suggestions for Raj, not ladder rungs)

- A `graderproof check` pre-commit mode that runs only the deterministic operators on a single changed task in under a minute, so benchmark authors get feedback before CI.
