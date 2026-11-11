# Artifacts

Banked results with provenance (git SHA, config hash, model IDs and revisions, seeds, timestamps, environment, exact command lines, and usage). Every result number in the README, docs/REPORT.md, and the grader cards is produced from files here by a committed script.

- `usage/ledger.jsonl`: one line per model call (client wrapper).
- `review/`: independent reviews (`latest.json` is written only by the reviewer).
- `citecheck.json`: what the citation checker saw for each reference.

Task-level evidence for third-party tasks not yet fixed upstream is not stored here; it lives in the git-ignored `private/` directory, and only aggregates and hashes appear in this directory.
