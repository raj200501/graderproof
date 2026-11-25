goal_turn: 8
STATE: ACTIVE

# graderproof status

Updated 2026-11-25. History lives in docs/LOG.md.

## Gates (from `python tools/ship_check.py --fast`; only a full run counts)

Fast check on 654a849 (2026-11-25, in the fresh container after the D47 recovery): **9/14**. G5, G7, G8, G9, and G12 fail. GitHub Actions CI is green on main (D41).

| Gate | State | Evidence or blocker |
|---|---|---|
| G1 Build and tests | PASS | 714 tests pass (8 skipped); core line coverage above the 85% floor |
| G2 Static quality | PASS | ruff, ruff format, mypy --strict clean; every ignore has a reason |
| G3 CI parity | PASS | ci.yml runs `make ci` on 3.11 and 3.12; parts pass |
| G4 Offline demo | PASS | under `unshare -rn`, no ledger change, matches the golden output |
| G5 Tool validity | FAIL | preregistered negative result: E0 recall is below the 0.90 threshold (H1 not met); precision met it (H2). Only a new planted set under a new preregistration can retest it |
| G6 Validation integrity | PASS | every headline variant of E0 and HumanEval has two agreeing validations and a witness; agreement and exclusions reported |
| G7 Confirmatory audit | FAIL | E1/E2 complete on HumanEval (1 of 3 benchmarks, prereg 0003); BFCL and tau2-bench under way |
| G8 Repair | FAIL | E4 done on toybench; HumanEval has graders with surviving variants and needs E4 (its generalization batch needs more calls than one day's remainder) |
| G9 Impact and cards | FAIL | E5 runner not built; toybench card only |
| G10 Claim integrity | PASS | claimcheck and freshness pass on README.md, docs/REPORT.md, and the card |
| G11 Preregistration | PASS | prereg 0001, 0002, and 0003 frozen and chained; confirmatory artifacts follow them |
| G12 Independent review | FAIL | review of 2d87aaa (2026-11-12) is REVIEW: BLOCK (B1, B2), both fixed in 12ea1da; the gate reads a review of an older commit as INVALID; next review 2026-11-13 |
| G13 Documentation | PASS | README.md follows section 11; docs/REPORT.md complete; citecheck verifies every reference |
| G14 Hygiene | PASS | secrets scan clean, cash 0, private/ untracked, no third-party evidence under artifacts/ (c647941), third-party rows keyed (D44), tree clean |

## Now

The cloud build container was reclaimed between 2026-11-13 and 2026-11-25, taking everything git does not track (D47). Every reported result is intact. The HumanEval private original rows are restored from git history, and the HumanEval public rows are republished under a new key, so G14 passes again here. The tau2-bench and BFCL audits cannot resume from their lost banked answers. Neither had produced an outcome, and both restart under a dated amendment with fresh stores, together with the SEC-3 sandbox hardening. The README now has a plain "why this matters" section, a roadmap labeled as plans, and a repository map. The next independent review (G12) can run on any day with an unused review run.

## Next three actions

1. Write and freeze the amendment that restarts E1/E2 on tau2-bench and BFCL under new stores, with the SEC-3 sandbox change (unprivileged child, home directories and `/run` hidden, tested), before any of their data exists. Then run their rounds under the daily cap with `tools/e1_round.sh` and `tools/e1_worker_audit.sh`.
2. G12: the next independent review of HEAD, logging every non-blocking issue in docs/REVIEW_LOG.md.
3. Then E3 and E4 (HumanEval needs a decision, since its private evidence is lost, D47 point 4), the E5 runner, E6, and the grader cards.

## Usage to date

- cash_usd = 0. Single calls through the client wrapper (ledger): 9 on 2026-10-23 (demo); 60 on 2026-11-04 (demo re-recording and E0); 41 on 2026-11-11 (36 for E0 completion, adjudication, and E4 on toybench, plus the 5 HumanEval extraction requests of the first prereg 0003 round, which the ledger dates by request time), all within the daily cap at CAP_SHARE 0.2.
- Not in the ledger: 17 E1 round-1 extraction answers on 2026-11-11, all from audited model workers (D24) and all superseded by the amendment (D38, D39). Counting them, 2026-11-11 used 58 of the 60 allowed calls.
- 2026-11-12: one review run (of 2d87aaa); 58 single calls in the ledger, 11 of them BFCL answers ingested at 03:32 UTC, plus 2 incomplete answers set aside and re-asked. That is 60 of the 60 allowed, so no more calls until 2026-11-13.
- Review runs: one on 2026-11-04 (df55c18) and one on 2026-11-11 (5677b9f), each within the one-a-day cap.

## Needs Raj

0. **Durable private storage.** Everything under `private/` and `runs/` is lost whenever the cloud container is reclaimed. That is how the E1/E2 model stores of tau2-bench and BFCL and the HumanEval evidence were lost (D47). A durable copy kept outside the container, or an environment with persistent storage, would prevent it.
1. **Claude backend.** The cloud environment sets `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_USE_CCR_V2`, which trip the billing guard, so no headless Claude subject or review runs can happen here (D2). Model work uses subagents instead (D17).
2. **Docker.** No Docker daemon here, so Terminal-Bench 2.0 is replaced by HumanEval (D18).
3. **References to check by hand** (scripted access blocked): the OpenAI SWE-bench Verified post (Cloudflare challenge). It is dropped from the docs unless you confirm it opens.
4. **Daily cap.** At CAP_SHARE 0.2 the wrapper allows 60 single calls a day, and E1/E2 with the amendment needs more than before (smaller batches for tau2-bench and BFCL), so the remaining experiments take several days of calls. Since Raj's message of 2026-11-11, a session heartbeat runs every 30 minutes, within the cap, and pushes verified steps; main is updated at each RELEASE-READY point (fast-forward or plain merge, never force).

5. **Third-party disclosure history (D43, D44).** HEAD's public HumanEval rows now carry keyed ids and no operator names, so they no longer expose any variant. The earlier rows, in history since 12ea1da, identify their tasks and let anyone regenerate the classical variants the graders accepted (evidence in `private/disclosure/2026-11-12-humaneval-ids.md`); model-proposed variants and witnesses were never exposed. Withdrawing the earlier rows needs a history rewrite, which only you can authorize.

## Changed this turn

- Fresh container (D47): bubblewrap reinstalled; HumanEval private original restored from history and its public rows republished under a new key; the E1 round scripts committed under `tools/`; README.md, docs/REPORT.md, and CORRECTIONS.md say that tau2-bench and BFCL are paused; README.md gained "Why this matters", "Roadmap", and "Repository map".

- E1/E2 on HumanEval completed under prereg 0003 and reported (README.md, docs/REPORT.md section 5.6); the review of 2d87aaa banked and its two blocking issues fixed (12ea1da).
- CI on GitHub fixed without skipping a test (D41): the interpreter lives outside the sandbox-hidden $HOME, and the upstream HumanEval driver pins fork. Green on main at 5373797.
- README and report honesty fixes from the audit's README lens. The HumanEval headline gives the preregistered median and IQR of the per-task mutation score, from `artifacts/e1/tables.json` (`tools/e1_tables.py --check`, D46). It also gives the E2 null with its exact interval and its thin base of preserving variants, the E4 caveat beside the numbers, an accurate review-process claim, and corrected related work (CORRECTIONS.md).
- Keyed public rows (D44): `tools/publish_rows.py` publishes third-party variant rows with HMAC-keyed ids, no operator names, and a fixed order, and records `PUBLIC_ROWS.json`. G14 now fails on a third-party row published any other way, and in the original checkout it checks that the rows republish from their private original. The HumanEval rows are republished, the original is kept under `private/`, and the regeneration attack now matches none of the public rows.
- Release sprint of 2026-11-12: a publication-safety audit (secrets, third-party task details, personal data, README honesty) found that the public HumanEval rows identify their tasks and, through reproducible variant ids, the classical variants its graders accepted (D43). README.md, docs/REPORT.md section 7.2, artifacts/README.md, and docs/DATA.md now say so (CORRECTIONS.md). The report's abstract now states the HumanEval finding. Sprint result: NOT-READY until HEAD carries keyed ids.
- Final README pass (D42): the Status section gives the current gate state, the HumanEval headline carries its mean mutation score and validator agreement, the quickstart describes what a finding looks like on the synthetic demo, and a repeated limitation is merged. No claim, gate, or check changed.

## Blocked

Nothing.

## Backlog (suggestions for Raj, not ladder rungs)

- From the release audit (docs/LOG.md, 2026-11-12): widen `make secrets-scan` (more credential shapes, commit messages, history file names, a personal-data rule), and render the README's gate list from a banked fast-check artifact.

- A maintainer-side check for disclosures: with the key for one benchmark (sent privately with a disclosure draft), `tools/publish_rows.py` could confirm that each public keyed row matches the private evidence, so a maintainer can check a finding against this repository without the repository revealing it.

- A `graderproof check` pre-commit mode that runs only the deterministic operators on a single changed task in under a minute, so benchmark authors get feedback before CI.
