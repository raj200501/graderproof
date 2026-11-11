goal_turn: 5
STATE: ACTIVE

# graderproof status

Updated 2026-11-11. History lives in docs/LOG.md.

## Gates (from `python tools/ship_check.py --fast`; only a full run counts)

Fast check on da44920 (2026-11-11, before docs/REPORT.md was committed): **6/14**. The rows below give the state after this turn's commits; the final fast check is recorded in docs/LOG.md.

| Gate | State | Evidence or blocker |
|---|---|---|
| G1 Build and tests | PASS | 585 tests pass (8 skipped); core line coverage above the 85% floor |
| G2 Static quality | PASS | ruff, ruff format, mypy --strict clean; every ignore has a reason |
| G3 CI parity | PASS | ci.yml runs `make ci` on 3.11 and 3.12; parts pass |
| G4 Offline demo | PASS | under `unshare -rn`, no ledger change, matches the golden output |
| G5 Tool validity | FAIL | preregistered negative result: E0 recall is below the 0.90 threshold (H1 not met); precision met it (H2). Reported in README.md and docs/REPORT.md; a new planted set under a new preregistration is the only way to retest |
| G6 Validation integrity | PASS | headline variants all have two agreeing validations and a witness; agreement and exclusions reported |
| G7 Confirmatory audit | FAIL | E1/E2 (prereg 0002) frozen with its sample; not run (needs several days of calls at the daily cap) |
| G8 Repair | FAIL | E4 done on toybench; G8 needs E4 on the audited benchmarks, which waits for E1 |
| G9 Impact and cards | FAIL | E5 runner not built; toybench card only |
| G10 Claim integrity | expected PASS | docs/REPORT.md committed; claimcheck and freshness pass on README.md, docs/REPORT.md, and the card |
| G11 Preregistration | PASS | prereg 0001 and 0002 frozen and chained; confirmatory artifacts follow them |
| G12 Independent review | FAIL | review of df55c18 was BLOCK (fixed since); its non-blocking issues are now in docs/REVIEW_LOG.md; today's review pending |
| G13 Documentation | expected PASS | README.md follows section 11; docs/REPORT.md complete; citecheck verifies every reference |
| G14 Hygiene | PASS on a clean tree | secrets scan clean, cash 0, private/ untracked |

## Now

E0 is complete and scored as preregistered (prereg 0001): H2 (precision at least 0.90) holds, H1 (recall at least 0.90) does not; every miss is explained in docs/E0_MISSES.md. E4 on toybench is complete (repairs and the generalization batch). README.md, docs/REPORT.md, and the toybench grader card are rendered from artifacts by `make report`. E1/E2 (prereg 0002) is frozen with its sample committed and has not run: at the daily cap of 60 single calls it needs several days.

## Next three actions

1. Run E1/E2 from `/home/user/graderproof-e1` with `runs/e1_round.sh <benchmark> <label>` (17 extraction requests are built), answering requests with model-worker subagents and auditing their transcripts, within the daily cap.
2. Then E3 (`tools/e3_rootcause.py`), E4 on the audited benchmarks, E5 (runner still to build; trajectories downloaded), E6 (`tools/e6_lint.py`), grader cards, and the README and report sections for them.
3. A new planted set and preregistration to test the operators that E0's misses call for (post-write delays, CRLF and numeric-type preserving variants, list-element insertion, input tampering).

## Usage to date

- cash_usd = 0. Single calls through the client wrapper: 9 on 2026-10-23 (demo); 60 on 2026-11-04 (demo re-recording and E0); 36 on 2026-11-11 (E0 completion, adjudication, E4 on toybench), all within the daily cap at CAP_SHARE 0.2.
- Subagent runs outside the wrapper include the planters, the adapter, claim-tooling, and gate-fix agents, miss analysts, report-section writers, and milestone reviews.

## Needs Raj

1. **Claude backend.** The cloud environment sets `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_USE_CCR_V2`, which trip the billing guard, so no headless Claude subject or review runs can happen here (D2). Model work uses subagents instead (D17).
2. **Docker.** No Docker daemon here, so Terminal-Bench 2.0 is replaced by HumanEval (D18).
3. **References to check by hand** (scripted access blocked): the OpenAI SWE-bench Verified post (Cloudflare challenge). It is dropped from the docs unless you confirm it opens.
4. **Daily cap.** At CAP_SHARE 0.2 the wrapper allows 60 single calls a day. E0 needs about 64 and E1/E2 about 100 more, so the remaining experiments take several days of calls. The heartbeat is off, so each day's work starts when you send a message (or restart `/loop`).

## Changed this turn

- E0 finished, adjudicated (D34), and scored as preregistered; labels committed unchanged; worker transcripts audited.
- E4 ran on toybench: repairs for every grader with a surviving variant, plus the generalization batch (D36).
- README.md, docs/REPORT.md, docs/cards/toybench.md, docs/E0_MISSES.md, and two figures, all rendered from artifacts.

## Blocked

Nothing.

## Backlog (suggestions for Raj, not ladder rungs)

- A `graderproof check` pre-commit mode that runs only the deterministic operators on a single changed task in under a minute, so benchmark authors get feedback before CI.
