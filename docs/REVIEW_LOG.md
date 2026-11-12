# Review log

Non-blocking issues raised by independent reviews (gate G12, docs/BUILD_BRIEF.md section 6), with what became of each. Blocking issues and full evidence are in `artifacts/review/history/`.

## Review of 2d87aaa20e8c (2026-11-12, BLOCK)

Blocking issues: B1 (the E4 mutation score before and after repair was not reported) is fixed by claims from artifacts/e0/tables.json in docs/REPORT.md section 5.5, README.md, and the toybench card; B2 (G7 accepted audits that cite any preregistration) is fixed in tools/ship_check.py with falsification tests.

| Id | Issue | Status |
|---|---|---|
| N1 | The E4 generalization test is not independent of the repair: both use the same requirement checks | Open (unchanged): disclosed beside the numbers in README.md and docs/REPORT.md section 5.5; the report now calls the batch the stronger test rather than the test that matters. |
| N2 | Previous N18 is still open: no gate checks artifacts/ for task-level evidence from third-party benchmarks | Open: G14 does not yet fail on third-party model request or response files committed under artifacts/model_calls/<benchmark>-0003/ (only MANIFEST.json belongs there, D35). |
| N3 | 'Hid every tau2-bench customer request' overstates the clip audit: 27 of 40 tau2 items lost the whole customer request, 13 kept part of it | Fixed: README.md and docs/REPORT.md now say the cut hit every tau2-bench task text and, in most, the customer request. |
| N4 | prereg 0003 says no grader verdict existed before the amendment, but the prereg 0002 round 1 graded every sampled reference on 2026-11-04 | Acknowledged: prereg 0003 cannot be edited after its freeze; every sampled reference was graded once under prereg 0002 on 2026-11-04, the amendment does not touch reference runs, and the 0003 worktree regraded them in new caches, so nothing was reused. |
| N5 | D37 reports only the false-accept clause; the adjudication prompt's false-reject branch is also broader than prereg 0001 | Open: D37 covers only the false-accept branch of the adjudication prompt; the false-reject branch is also broader than prereg 0001, and no ruling relied on it. |
| N6 | The E4 toybench summary cites no preregistration, so prereg-verify does not date it | Open: the E4 toybench summary has no prereg field; its provenance (f63b2d9, clean) matches prereg 0002. |
| N7 | artifacts/e0/tables.json is never regenerated or compared, so the claims that read it are not re-derived from the rows | Open: no target regenerates artifacts/e0/tables.json and compares it; it regenerates byte-identically today. |
| N8 | Model calls that are answered but never ingested are outside the ledger and the cap enforced in code | Open: answers made but never ingested sit outside the ledger; STATUS.md counts them, and every day stayed within the cap. |
| N9 | Docs disagree on whether E1/E2 has started, and the report does not yet label prereg 0003 as a deviation | Fixed: docs/REPORT.md and README.md now say E1/E2 is under way with no results yet. |
| N10 | The toybench card's plain-language rate labels count the two adjudicated false positives | Open: the toybench card counts the two adjudicated false positives in its plain-language task-level rates. |
| N11 | G5's 'every miss explained' check is a token match on the task id | Open: G5 checks only that each miss is named in docs/E0_MISSES.md; each miss has its own explained section today. |
| N12 | The tsv-transpose patch notes do not say its flag was adjudicated a false positive | Open: the tsv-transpose patch notes do not mention the adjudication; README.md and docs/REPORT.md do. |
| N13 | Checks not completed within the time box | To cover in the next review. |

## Review of 5677b9f639c9 (2026-11-11, BLOCK)

Blocking issues B1 to B6 are fixed in the commit after 5677b9f: corrected wording and new claims for B1 to B3 and B6, a G5 check of the adjudication against the banked rulings for B4, and D37 with a CORRECTIONS.md entry for B5. Residuals of B4 found later are fixed in c647941: each adjudicated variant must belong to its task and to that task's flag, and each banked adjudicate response must match the ledger's recorded hash.

| Id | Issue | Status |
|---|---|---|
| N1 | The E4 generalization test is not independent of the repair: both use the same requirement checks | Disclosed in README.md and docs/REPORT.md section 5.5 (the batch measures coverage of the grafted checks). Open: an independent generalization check needs a judge other than the grafted requirements. |
| N2 | The adjudication's provenance names the frozen E0 commit, but the adjudication tool did not exist at that commit | Fixed in c647941: `tools/e0_adjudicate.py` also records the tool's own commit, whether the tool file differs from its blob at that commit, and its SHA-256. The banked E0 adjudication predates the fix and lacks these keys. |
| N3 | D36 was committed in the same commit as the E4 data | Acknowledged as a process slip; the copied requests are byte-identical to E0's, so no result changes. |
| N4 | The claimcheck allowlist for 0.90 accepts comparison words, which let B2 through | Partly fixed in c647941: the 0.90 row accepts only threshold phrases (a strict narrowing), and `tests/test_e0_tables.py` checks every sentence that compares a result with the threshold against the artifact. The comparison words are still typed, because claims render only numbers. |
| N5 | G5 e0_scores does not drop flags on tasks whose reference is rejected or flaky | Fixed in c647941: G5 drops flags on tasks whose grader rejects or is flaky on the reference, as prereg 0001 says. The audit-table recomputation already excluded them and no E0 task has one, so no result changes. |
| N6 | Previous N18 is still open: no gate checks artifacts/ for task-level evidence from third-party benchmarks | Fixed in c647941: G14 fails on tracked third-party evidence under artifacts/, found by path and by content, and on audit summaries that record evidence outside private/. |
| N7 | The materials check ran the toybench adapter and graders before the labels hash was committed | Disclosed in prereg 0001; no action needed. |
| N8 | Checks not completed within the time box | To cover in the next review. |

## Review of df55c18ed112 (2026-11-04, BLOCK)

Blocking issues B1 to B5 were fixed in 51fe7b3 (gates, D33) and 2d8058f (package).

| Id | Issue | Status |
|---|---|---|
| N1 | Operator name reaches the model reviewer through wrapper variants; the test that should catch it is vacuous | Fixed in 2d8058f: output rewrites no longer name their operator (`src/graderproof/variants/wrap.py`). |
| N2 | Host-side workspace snapshot follows symlinks planted by sandboxed code; a dangling symlink crashes the audit | Fixed in 2d8058f: workspace snapshots and probe and trajectory reads never follow symbolic links. |
| N3 | An invalid regex in a model-extracted requirement crashes the audit | Fixed in 2d8058f: uncompilable regex checks are dropped when requirements are parsed. |
| N4 | Execution cache keys omit code, sandbox, limits, and adapter environment; cached failures persist across fixes | Fixed in 2d8058f: cache keys cover the package source, sandbox version, limits, and extra environment; sandbox start failures are not cached (D25). |
| N5 | E0 credits rejected or flaky references as reject-direction detections and allows witness-free 'real' adjudications | Fixed in 2d8058f: detection is a witness-backed flag in the planted direction, and reference-level flags are reported separately (D23). |
| N6 | Draft freeze list and run provenance do not pin the code that produces E0 | Fixed: E0 ran from a detached worktree at the preregistration commit (D28), and provenance records `git_dirty` and the package fingerprint (2d8058f). |
| N7 | e0-score: no labels hash check, string 'false' read as adjudicated real, unvalidated slices, recall hidden when precision is undefined | Fixed in 2d8058f: `graderproof e0-score` checks the labels against `toybench/labels.sha256` and validates slices; G5 recomputes the score (51fe7b3). |
| N8 | Raw task keys and an unrestricted model-worker Read tool are possible label channels in E0 | Fixed in 2d8058f: model items carry task key hashes, never names (D24), and `tools/transcript_audit.py` audits every worker transcript. |
| N9 | Uniform max_total sampling can drop the few preserving variants that would detect a false-reject weakness | Fixed in 2d8058f: sampling reserves a share of the per-task cap for preserving variants. |
| N10 | G7 recomputation and score.aggregate disagree on tasks whose reference is rejected | Fixed in 51fe7b3 (D33): G7 counts only stable-pass tasks as scorable, as `score.aggregate` does. |
| N11 | Percentile bootstrap degenerates at 1.0, so the draft's lower-bound caveat never triggers | Mitigated in 2d8058f: exact Clopper-Pearson intervals are reported beside the bootstrap intervals; the percentile bootstrap itself is the preregistered method (D8). |
| N12 | Agreement rate counts two unsure or no-evidence verdicts as agreement | Fixed in 2d8058f and 51fe7b3: agreement is computed only over label verdicts, and an unsure verdict is never agreement (D26). |
| N13 | Ledger stamps ingest time, not call time, and stores no response hash | Fixed in 2d8058f: ingest records the request time and the response SHA-256, and a changed response is refused (D27). |
| N14 | G2 weakening check misses inline '# mypy: ignore-errors' and per-module overrides | Fixed in 51fe7b3: G2 catches inline and per-module ways of weakening mypy --strict. |
| N15 | No tests exercise gate functions G5 to G11 | Fixed in 51fe7b3: the falsification scenarios are tests in `tests/test_gates.py`. |
| N16 | Reviewed commit fails make lint but was pushed | Fixed: `make ci` runs before every push. |
| N17 | Validator disagreements are not written to private/review_queue/ | Fixed in 2d8058f: disagreeing variants are written to `private/review_queue/`. |
| N18 | Evidence defaults to <out>/evidence, and no gate catches task-level evidence for third-party tasks under artifacts/ | Partly fixed: third-party evidence now defaults to `private/evidence/<benchmark>` (`src/graderproof/cli.py`); no gate yet checks `artifacts/` for task-level third-party evidence. |
| N19 | Draft says the planter saw no description of the tool, but subagents receive CLAUDE.md | Fixed in 2d8058f: `docs/e0/planter_prompt.md` records what the planter could see, including the mission paragraph of CLAUDE.md, and its file-access audit; disclosed in prereg 0001 and in the report limitations. |
| N20 | A task's own [metadata] can override trusted_local and bypass the write-isolation policy | Fixed in 2d8058f: third-party tasks cannot claim `trusted_local`. |
| N21 | HEAD moved during the review; new modules are unreviewed | Process note: later reviews are run against a fixed HEAD recorded as `reviewed_commit`. |
