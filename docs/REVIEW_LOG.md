# Review log

Non-blocking issues raised by independent reviews (gate G12, docs/BUILD_BRIEF.md section 6), with what became of each. Blocking issues and full evidence are in `artifacts/review/history/`.

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
