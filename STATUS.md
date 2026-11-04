goal_turn: 3
STATE: ACTIVE

# graderproof status

Updated 2026-11-04 04:00 UTC. History lives in docs/LOG.md.

## Gates (from `python tools/ship_check.py --fast`; only a full run counts)

Fast check on a27b76e (2026-11-04): **5/14**.

| Gate | State | Evidence or blocker |
|---|---|---|
| G1 Build and tests | PASS | full suite passes; package line coverage above the 85% floor |
| G2 Static quality | PASS | ruff, ruff format, mypy --strict clean; every ignore has a reason |
| G3 CI parity | PASS | ci.yml runs `make ci` on 3.11 and 3.12; parts pass |
| G4 Offline demo | PASS | under `unshare -rn`, no ledger change, matches the re-recorded golden output |
| G5 Tool validity | FAIL | E0 running under prereg 0001; 8 review batches left (daily cap) |
| G6 Validation integrity | FAIL | no headline variants banked until E0 completes |
| G7 Confirmatory audit | FAIL | three adapters merged or nearly (HumanEval, BFCL; tau2 finishing); prereg 0002 not frozen |
| G8 Repair | FAIL | E4 runner built; waits for E1 survivors |
| G9 Impact and cards | FAIL | E5 not run; no cards |
| G10 Claim integrity | FAIL | claimcheck and freshness merged; no docs/REPORT.md yet |
| G11 Preregistration | FAIL | prereg 0001 frozen (chain verifies); no confirmatory artifact yet |
| G12 Independent review | FAIL | last review is BLOCK on df55c18; its five blocking issues are fixed in 2d8058f (package) and in the gate-fix worktree (ship-check) |
| G13 Documentation | FAIL | README.md is still the brief; citecheck merged |
| G14 Hygiene | PASS | secrets scan clean, cash 0, private/ untracked, tree clean |

## Now

E0 (prereg 0001, frozen at 1629c30) runs from the frozen worktree `/home/user/graderproof-e0` (D28): extraction, proposals, the classical-variant reviews, and 4 of 12 batches for the model-proposed variants are answered; 8 review batches wait for the daily cap (reset 00:00 UTC). Every model-worker transcript passed the D24 audit. `tools/e0_adjudicate.py` (D34) is ready for the step after the audit.

E1/E2 (prereg 0002, frozen at f63b2d9) runs from `/home/user/graderproof-e1`: all three adapters are merged (HumanEval D29, BFCL D31, tau2-bench D32), the sample is committed and reproduces exactly, and round 1 has produced 17 extraction requests (tau2 7, BFCL 5, HumanEval 5). Their model stores are private with public hash manifests (D35). The gate fixes for review B1 to B5 are merged (D33). The released tau2 trajectories for E5 are downloaded (git-ignored, hashes in `runs/e5/sources.json`).

## Next three actions

1. After the cap resets: the last 8 E0 review batches, then finish the E0 audit, `tools/e0_adjudicate.py`, `graderproof e0-score`, commit `toybench/labels.json` unchanged, and write docs/E0_MISSES.md; then the 17 E1 extraction calls and the E1 proposal batches.
2. Build the E5 runner (released tau2 trajectories: repaired pass = original pass on the recorded run and the grafted checks on the replayed outcome) and the grader-card and report templates, while the audits wait on the cap. The E3 and E6 runners are built (cec7cbd).
3. Run the milestone review once E0 is banked (one review run a day).

## Usage to date

- cash_usd = 0. Single calls through the client wrapper: 9 on 2026-10-23 (demo); 60 on 2026-11-04 (5 demo re-recording, 55 E0), which is the daily cap at CAP_SHARE 0.2.
- Subagent runs outside the wrapper: 1 citation check, 1 benchmark survey, 2 planting runs, 6 adapter runs (3 stopped, 3 resumed), 1 claim-tooling run, 1 gate-fix run, 1 milestone review.

## Needs Raj

1. **Claude backend.** The cloud environment sets `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_USE_CCR_V2`, which trip the billing guard, so no headless Claude subject or review runs can happen here (D2). Model work uses subagents instead (D17).
2. **Docker.** No Docker daemon here, so Terminal-Bench 2.0 is replaced by HumanEval (D18).
3. **References to check by hand** (scripted access blocked): the OpenAI SWE-bench Verified post (Cloudflare challenge). It is dropped from the docs unless you confirm it opens.
4. **Daily cap.** At CAP_SHARE 0.2 the wrapper allows 60 single calls a day. E0 needs about 64 and E1/E2 about 100 more, so the remaining experiments take several days of calls. The heartbeat is off, so each day's work starts when you send a message (or restart `/loop`).

## Changed this turn

- Fixed the pre-E0 review findings in the package (2d8058f), re-recorded the demo, recorded D27 and D28.
- Committed the toybench tasks and the label hash (7fab903), froze prereg 0001 (1629c30), and started E0.
- Merged the HumanEval adapter (D29: numpy preload), the claim tooling (D30), and the BFCL adapter (D31).

## Blocked

Nothing.

## Backlog (suggestions for Raj, not ladder rungs)

- A `graderproof check` pre-commit mode that runs only the deterministic operators on a single changed task in under a minute, so benchmark authors get feedback before CI.
