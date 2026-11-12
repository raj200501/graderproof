# Artifacts

Banked results with provenance (git SHA, config hash, model IDs and revisions, seeds, timestamps, environment, exact command lines, and usage). Every result number in the README, docs/REPORT.md, and the grader cards is produced from files here by a committed script.

- `usage/ledger.jsonl`: one line per model call (client wrapper).
- `review/`: independent reviews (`latest.json` is written only by the reviewer).
- `citecheck.json`: what the citation checker saw for each reference.

Task-level evidence for third-party tasks not yet fixed upstream (witnesses, grader output, model calls) is not stored here; it lives in the git-ignored `private/` directory. The per-task audit rows here identify their tasks. Third-party variant rows carry keyed ids and no operator names (`tools/publish_rows.py`, `PUBLIC_ROWS.json`), so they cannot be matched to regenerated variants; an earlier version of the HumanEval rows in the history could be (D43, D44, CORRECTIONS.md).
