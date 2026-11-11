goal_turn: 6
STATE: ACTIVE

# graderproof status

Updated 2026-11-11. History lives in docs/LOG.md.

## Gates (from `python tools/ship_check.py --fast`; only a full run counts)

Fast check on 4f53770 (2026-11-11, clean tree): **9/14**. G5, G7, G8, G9, and G12 fail.

| Gate | State | Evidence or blocker |
|---|---|---|
| G1 Build and tests | PASS | 593 tests pass (8 skipped); core line coverage above the 85% floor |
| G2 Static quality | PASS | ruff, ruff format, mypy --strict clean; every ignore has a reason |
| G3 CI parity | PASS | ci.yml runs `make ci` on 3.11 and 3.12; parts pass |
| G4 Offline demo | PASS | under `unshare -rn`, no ledger change, matches the golden output |
| G5 Tool validity | FAIL | preregistered negative result: E0 recall is below the 0.90 threshold (H1 not met); precision met it (H2). Only a new planted set under a new preregistration can retest it |
| G6 Validation integrity | PASS | headline variants all have two agreeing validations and a witness; agreement and exclusions reported |
| G7 Confirmatory audit | FAIL | E1/E2 not run; the first extraction round found the frozen code clips long task texts, so prereg 0002 needs an amendment before any E1/E2 data (D38) |
| G8 Repair | FAIL | E4 done on toybench; G8 needs E4 on the audited benchmarks, which waits for E1 |
| G9 Impact and cards | FAIL | E5 runner not built; toybench card only |
| G10 Claim integrity | PASS | claimcheck and freshness pass on README.md, docs/REPORT.md, and the card |
| G11 Preregistration | PASS | prereg 0001 and 0002 frozen and chained; confirmatory artifacts follow them |
| G12 Independent review | FAIL | review of 5677b9f is REVIEW: BLOCK (B1 to B6), all fixed in 4f53770; the next review run is allowed on 2026-11-12 (cap: one a day) |
| G13 Documentation | PASS | README.md follows section 11; docs/REPORT.md complete; citecheck verifies every reference |
| G14 Hygiene | PASS | secrets scan clean, cash 0, private/ untracked, tree clean |

## Now

Release sprint (Raj, 2026-11-11): the branch was checked for publication (secrets scan clean, nothing under private/ tracked, no third-party variants or witnesses tracked, no personal data beyond Raj's name and GitHub noreply address), lint, typecheck, tests, and the demo pass, and README.md now has a pitch and a Status section. E1/E2 is paused before its amendment: the 17 round-1 extraction answers exist but none is ingested, and the full-task-text change (prereg 0003, D38) is scoped but not yet written.

## Next three actions

1. Resume the amendment: implement the unclipped task text with a byte-identity test for existing requests, write and freeze prereg 0003, create the new frozen worktree, rebuild the round-1 requests, and ingest the 5 HumanEval answers if their hashes are unchanged.
2. Run the next independent review on the current HEAD (2026-11-12 or later, one a day) and log its non-blocking issues in docs/REVIEW_LOG.md (D7).
3. Continue E1/E2 under the daily cap, then E3, E4 on the audited benchmarks, E5 (runner still to build), E6, and the grader cards.

## Usage to date

- cash_usd = 0. Single calls through the client wrapper (ledger): 9 on 2026-10-23 (demo); 60 on 2026-11-04 (demo re-recording and E0); 36 on 2026-11-11 (E0 completion, adjudication, E4 on toybench), all within the daily cap at CAP_SHARE 0.2.
- Not in the ledger: 17 E1 round-1 extraction answers on 2026-11-11 (12 superseded by D38, 5 HumanEval held), all from audited model workers (D24). Counting them, 2026-11-11 used 53 of the 60 allowed calls.
- Review runs: one on 2026-11-04 (df55c18) and one on 2026-11-11 (5677b9f), each within the one-a-day cap.

## Needs Raj

1. **Before making the repository public, bring the work onto main.** `origin/main` still holds only the build brief (d32995c); all work is on `claude/affectionate-volta-z2bm3c`, which main can fast-forward to. Claude does not open pull requests or change repository settings (non-negotiable 8), so the merge, the default branch, and the visibility switch are yours. CI runs only on main, so its first run happens then.
2. **Claude backend.** The cloud environment sets `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_USE_CCR_V2`, which trip the billing guard, so no headless Claude subject or review runs can happen here (D2). Model work uses subagents instead (D17).
3. **Docker.** No Docker daemon here, so Terminal-Bench 2.0 is replaced by HumanEval (D18).
4. **References to check by hand** (scripted access blocked): the OpenAI SWE-bench Verified post (Cloudflare challenge). It is dropped from the docs unless you confirm it opens.
5. **Daily cap.** At CAP_SHARE 0.2 the wrapper allows 60 single calls a day, and E1/E2 with the amendment needs more than before (smaller batches for tau2-bench and BFCL), so the remaining experiments take several days of calls. The heartbeat is off, so each day's work starts when you send a message (or restart `/loop`).

## Changed this turn

- Release sprint: publication checks, README pitch and Status section, STATUS.md.
- E1/E2 round 1: 17 extraction answers by audited model workers, none ingested; the frozen code's text clipping found and measured (`tools/clip_audit.py`, `artifacts/e1/clip_audit_round1.json`); D38 records the decision to amend before any E1/E2 data.

## Blocked

Nothing.

## Backlog (suggestions for Raj, not ladder rungs)

- A `graderproof check` pre-commit mode that runs only the deterministic operators on a single changed task in under a minute, so benchmark authors get feedback before CI.
