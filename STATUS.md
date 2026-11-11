goal_turn: 5
STATE: ACTIVE

# graderproof status

Updated 2026-11-11. History lives in docs/LOG.md.

## Gates (from `python tools/ship_check.py --fast`; only a full run counts)

Fast check on 5677b9f (2026-11-11, run by the reviewer): **9/14**. G5, G7, G8, G9, and G12 fail.

| Gate | State | Evidence or blocker |
|---|---|---|
| G1 Build and tests | PASS | 591 tests pass (8 skipped); core line coverage above the 85% floor |
| G2 Static quality | PASS | ruff, ruff format, mypy --strict clean; every ignore has a reason |
| G3 CI parity | PASS | ci.yml runs `make ci` on 3.11 and 3.12; parts pass |
| G4 Offline demo | PASS | under `unshare -rn`, no ledger change, matches the golden output |
| G5 Tool validity | FAIL | preregistered negative result: E0 recall is below the 0.90 threshold (H1 not met); precision met it (H2). Reported in README.md and docs/REPORT.md; only a new planted set under a new preregistration can retest it |
| G6 Validation integrity | PASS | headline variants all have two agreeing validations and a witness; agreement and exclusions reported |
| G7 Confirmatory audit | FAIL | E1/E2 (prereg 0002) frozen with its sample; not run (several days of calls at the daily cap) |
| G8 Repair | FAIL | E4 done on toybench; G8 needs E4 on the audited benchmarks, which waits for E1 |
| G9 Impact and cards | FAIL | E5 runner not built; toybench card only |
| G10 Claim integrity | PASS | claimcheck and freshness pass on README.md, docs/REPORT.md, and the card |
| G11 Preregistration | PASS | prereg 0001 and 0002 frozen and chained; confirmatory artifacts follow them |
| G12 Independent review | FAIL | review of 5677b9f is REVIEW: BLOCK (B1 to B6); all six are addressed in the commit after it, which needs a new review (one review run a day) |
| G13 Documentation | PASS | README.md follows section 11; docs/REPORT.md complete (4000 to 8000 words); citecheck verifies every reference |
| G14 Hygiene | PASS | secrets scan clean, cash 0, private/ untracked, tree clean |

## Now

E0 is complete and scored as preregistered (prereg 0001), with one late-recorded deviation in the adjudication prompt that changes no ruling (D37): H2 (precision at least 0.90) holds, H1 (recall at least 0.90) does not; every miss is explained in docs/E0_MISSES.md. E4 on toybench is complete. README.md, docs/REPORT.md, and the toybench grader card are rendered from artifacts. The independent review of 5677b9f returned BLOCK with six issues (three wrong statements, one G5 gap, two preregistration reporting gaps); all are fixed in the following commit and recorded in CORRECTIONS.md. E1/E2 (prereg 0002) is frozen with its sample committed and has not run.

## Next three actions

1. Run the next independent review (`make review` through the reviewer subagent) on the corrected HEAD, and log its non-blocking issues in docs/REVIEW_LOG.md before the review after it (D7).
2. Run E1/E2 from `/home/user/graderproof-e1` with `runs/e1_round.sh <benchmark> <label>`, answering requests with model-worker subagents and auditing their transcripts, within the daily cap; then E3, E4 on the audited benchmarks, E5 (runner still to build), E6, and the grader cards.
3. A new planted set and preregistration to test the operators that E0's misses call for (post-write delays, CRLF and numeric-type preserving variants, list-element insertion, input tampering), with the adjudication prompt worded exactly as preregistered.

## Usage to date

- cash_usd = 0. Single calls through the client wrapper: 9 on 2026-10-23 (demo); 60 on 2026-11-04 (demo re-recording and E0); 36 on 2026-11-11 (E0 completion, adjudication, E4 on toybench), all within the daily cap at CAP_SHARE 0.2.
- Review runs: one on 2026-11-04 (df55c18) and one on 2026-11-11 (5677b9f), each within the one-a-day cap.
- Subagent runs outside the wrapper include the planters, the adapter, claim-tooling, and gate-fix agents, miss analysts, report-section writers, and milestone reviews.

## Needs Raj

1. **Before making the repository public, bring the work onto main.** `origin/main` still holds only the build brief (d32995c); all work is on `claude/affectionate-volta-z2bm3c`, which main can fast-forward to. Claude does not open pull requests or change repository settings (non-negotiable 8), so the merge, the default branch, and the visibility switch are yours. CI runs only on main, so its first run happens then.
2. **Claude backend.** The cloud environment sets `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_USE_CCR_V2`, which trip the billing guard, so no headless Claude subject or review runs can happen here (D2). Model work uses subagents instead (D17).
3. **Docker.** No Docker daemon here, so Terminal-Bench 2.0 is replaced by HumanEval (D18).
4. **References to check by hand** (scripted access blocked): the OpenAI SWE-bench Verified post (Cloudflare challenge). It is dropped from the docs unless you confirm it opens.
5. **Daily cap.** At CAP_SHARE 0.2 the wrapper allows 60 single calls a day, and E1/E2 needs about 100 more, so the remaining experiments take several days of calls. The heartbeat is off, so each day's work starts when you send a message (or restart `/loop`).

## Changed this turn

- E0 finished, adjudicated (D34), and scored as preregistered; labels committed unchanged; worker transcripts audited.
- E4 ran on toybench: repairs for every grader with a surviving variant, plus the generalization batch (D36).
- README.md, docs/REPORT.md, docs/cards/toybench.md, docs/E0_MISSES.md, docs/REVIEW_LOG.md, and two figures.
- Independent review of 5677b9f (BLOCK); its six blocking issues fixed, D37 recorded, CORRECTIONS.md entries added, G5 now checks the adjudication against the banked rulings.

## Blocked

Nothing.

## Backlog (suggestions for Raj, not ladder rungs)

- A `graderproof check` pre-commit mode that runs only the deterministic operators on a single changed task in under a minute, so benchmark authors get feedback before CI.
