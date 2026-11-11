# Contributing

## Setup

```bash
make setup      # uv sync --locked (Python 3.11 or 3.12)
make doctor     # what this machine can run
make ci         # lint, typecheck, test, offline demo
```

## Rules that every change must keep

- **Numbers come from artifacts.** Every result number in README.md, docs/REPORT.md, cards, figures, and tables is produced by a committed script from a banked artifact under `artifacts/`. `make claimcheck` and `make freshness` enforce this.
- **Preregister before confirmatory runs.** Hypotheses, thresholds, sample sizes, and exclusions go in `prereg/NNNN-*.md` and are committed before any confirmatory data exists. A frozen preregistration is never edited; changes are new, dated amendment files.
- **Evidence for every flag.** A variant counts in a headline number only with two agreeing, independent validations and a witness derived from the task text, never from the grader.
- **Sandbox all third-party code.** Graders, task repositories, and agents run only inside the sandbox backends.
- **Responsible disclosure.** Task-level details for unpatched third-party tasks stay in `private/` (git-ignored).
- **Plain writing.** Precise, scoped claims, no hype words, no em dashes (`make lint` checks the last one).
- **Types and tests.** `mypy --strict` clean, `ruff` clean, and a test for every public function.

## Checks

`make ship-check` runs the full Definition of Done (14 gates) on a fresh clone. `python tools/ship_check.py --fast` is a quicker development check whose result does not count.
