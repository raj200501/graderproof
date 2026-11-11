# Corrections

Every changed or withdrawn claim gets a dated entry here (non-negotiable 3): what was claimed, where, what changed, why, and the artifact behind the new claim.

## 2026-11-11: corrections after the independent review of 5677b9f

The review in `artifacts/review/latest.json` (REVIEW: BLOCK) found the following errors in README.md, docs/REPORT.md, and docs/cards/toybench.md as pushed in c07ee5e and 5677b9f. Each is corrected in the next commit; the new numbers are claims rendered from the named artifacts.

1. **Excluded variants (review B1).** The documents described every excluded E0 variant as one with disagreeing validators. The excluded count also includes variants that both validators labeled the other way (status `rejected`). The two parts are now reported separately (`e0.n_disagreed` and `e0.n_rejected`, from `artifacts/e0/tables.json`, `validation`).
2. **Exact recall interval (review B2).** docs/REPORT.md section 5.1 said the upper end of the exact recall interval is below the 0.90 threshold. It is above it (`artifacts/e0/results.json`, `exact_intervals.recall`). The sentence now says that the point estimate, the preregistered criterion, is below the threshold while both intervals reach above it. H1 is still not met.
3. **What E4 repaired (review B3, and non-blocking N1).** README.md and docs/REPORT.md said the E4 repairs fixed every toybench grader that accepted a broken solution. For one of the repaired graders, the E0 adjudicator had ruled the surviving variant's flag a false positive, so that repair enforces a requirement the task text does not state. The claim now reads "graders with a surviving violating variant" and names the exception (`e4.tb.adjudicated_not_real`). The documents also now say that the generalization batch is labeled by the same requirement checks the repairs graft, so it measures coverage of those checks, not an independent judgment.
4. **Adjudication wording (review B5).** docs/REPORT.md said E0 ran exactly as preregistered and that the adjudicator ruled only on the witness's requirement. The adjudication prompt also allowed another explicitly stated requirement (D37). No ruling used that clause and no number changes; the deviation is now reported in section 5.3.
5. **Secondary outcomes (review B6).** Three exploratory outcomes listed in prereg 0001 were not reported: detection by task kind, the operators behind the detecting variants, and recall with reference-level timing flags counted. They are now in docs/REPORT.md section 5.2, from `artifacts/e0/tables.json` and `artifacts/e0/results.json`.
