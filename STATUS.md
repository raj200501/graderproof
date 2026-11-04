goal_turn: 3
STATE: ACTIVE

# graderproof status

Updated 2026-11-04 03:30 UTC. History lives in docs/LOG.md.

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

E0 (prereg 0001, frozen at 1629c30) runs from the frozen worktree `/home/user/graderproof-e0` (D28). Done: requirement extraction (9 calls), proposals (12), reviews of the classical variants (30), and 4 of 12 review batches for the model-proposed variants. Every model-worker transcript passed the D24 audit. The rest of round 3 waits for the single-call cap to reset at 00:00 UTC.

In parallel: HumanEval, BFCL, and the claim tooling are merged (D29 to D31); the tau2-bench adapter and the gate fixes for review issues B1 to B5 are finishing in their worktrees.

## Next three actions

1. After the cap resets: answer the last 8 E0 review batches, finish the audit (confirmation runs), score with `graderproof e0-score`, run the independent adjudication of flags that are not detections, commit `toybench/labels.json` unchanged, and write docs/E0_MISSES.md.
2. Merge tau2-bench and the gate fixes; freeze prereg 0002 (E1/E2) with the committed sample and the banked power calculation; start E1/E2 from a frozen worktree.
3. Re-run the milestone review once E0 is banked and the gate fixes are merged.

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
