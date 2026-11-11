# graderproof: operating notes for Claude

After any compaction or restart, re-read CLAUDE.md, STATUS.md, and sections 6 to 10 of docs/BUILD_BRIEF.md before acting.

## Mission

graderproof measures how often an agent-benchmark grader accepts a broken solution (false accept) or rejects a correct one (false reject). For each task with a reference solution and a grading command it generates validated spec-violating variants (mutation testing) and validated spec-preserving variants (metamorphic testing), runs the grader on them in a sandbox, scores per-task mutation scores and false-accept and false-reject indicators with task-clustered intervals, explains the root causes, synthesizes repairs that catch surviving violating variants without rejecting valid ones, and shows how published results change once graders are repaired. The full specification is docs/BUILD_BRIEF.md (immutable; its hash is in docs/BUILD_BRIEF.sha256). The Definition of Done is the 14 gates in its section 6, checked only by `make ship-check`.

## Non-negotiables (docs/BUILD_BRIEF.md section 9, verbatim)

These hold on every turn.

1. **No fabricated or hand-typed numbers.** Every result number (a measured rate, count of outcomes, estimate, interval, or test statistic) in README.md, docs/REPORT.md, other results documents, figures, and tables is produced by a committed script from a banked artifact under `artifacts/`. Design parameters, thresholds, caps, dates, versions, and the text of docs/BUILD_BRIEF.md are not result numbers. `make claimcheck` enforces this and `make freshness` re-derives every live number.
2. **Preregister before confirmatory runs.** Hypotheses, metrics, analysis plan, thresholds, sample sizes, exclusions, and stopping rules go in `prereg/NNNN-*.md`, committed and hashed before any confirmatory data exists. A needed change is a new, dated amendment file that cites the original, is committed before any data it affects, and is reported as a deviation; the original is never edited. Anything not preregistered is labeled exploratory.
3. **Publish failures beside successes.** Null and negative results get the same prominence as positive ones. Every changed or withdrawn claim gets a dated entry in CORRECTIONS.md.
4. **Label synthetic and mock data everywhere.** Synthetic, procedurally generated, or mock results are never presented as model results or real-world results.
5. **$0 cash, with caps enforced in code** (section 8).
6. **Secrets stay in the environment.** Never write keys or tokens to files, logs, artifacts, or command lines. `make secrets-scan` runs in CI and in ship-check.
7. **Defensive scope only.** Mock tools and disposable sandboxes. No real credentials, real systems, or harmful payloads. Build nothing that helps an agent evade graders, monitors, or safety measures beyond what the measurement strictly requires.
8. **No outbound actions.** Never send email, open issues or pull requests, post, publish packages, datasets, or sites, or contact anyone. Pushing is allowed only under section 10.1 step 11. Prepare drafts in `outbound/` for Raj to review and send.
9. **Respect licenses and terms.** Record the source, license, and retrieval date of all third-party data in docs/DATA.md. Do not redistribute what a license does not allow. Add a canary string to any dataset meant for release.
10. **The brief is immutable.** Never edit docs/BUILD_BRIEF.md. Record deviations, substitutions, and interpretations in DECISIONS.md, with a reason, before acting on them.
11. **Verified citations only.** Never cite from memory. Open and check every reference (title, authors, year, URL) once and bank what you saw in `artifacts/citecheck.json` (retrieval date, final URL, page title, content hash); `make citecheck` validates that file offline, so ship-check never needs the network. If a site blocks scripted access, use the arXiv, DOI, or another official copy, and never work around bot protection. If nothing opens, drop the reference and list it under "Needs Raj" for a manual check.
12. **Plain writing.** Precise, scoped claims. No hype words such as "revolutionary", "groundbreaking", or "state of the art". No em dashes anywhere (Raj's style rule).
13. **Honest progress.** Never pass a gate by weakening its check. If a gate cannot pass, say so in STATUS.md and keep working on what can.
14. **Responsible disclosure.** Task-level details for unpatched third-party tasks (surviving variants and their witnesses) live only in `private/`, which is git-ignored; commit only their hashes. Aggregate statistics may be public. Disclosure drafts and patches go in `outbound/` for Raj. Claude never contacts maintainers.
15. **No adversarial agent search.** Variants come from the reference solution and the task text, never from agents trying to beat the grader. This keeps every finding attributable and avoids building a kit for gaming benchmarks.

## State files

- `STATUS.md`: line 1 `goal_turn: N`, line 2 `STATE: ACTIVE | BLOCKED ON RAJ | LADDER COMPLETE`; gate table, Now, next three actions, usage, Needs Raj, Blocked, backlog. Under 200 lines; history goes to docs/LOG.md.
- `DECISIONS.md`: every assumption, interpretation, substitution, or deviation, dated, with a reason, written before acting on it.
- `CORRECTIONS.md`: dated entry for every changed or withdrawn claim.
- `docs/PLAN.md`: milestones mapped to gates, risks, fallbacks, usage estimates.
- `docs/LOG.md`: iteration history moved out of STATUS.md.
- `budget.toml`: usage caps. Lower only, never raise. `cash_usd = 0` always.
- `prereg/`: frozen preregistrations (never edited; amendments are new files).
- `artifacts/`: banked results with provenance. `artifacts/review/latest.json` is written only by the reviewer.
- `private/` and `runs/`: git-ignored. Task-level evidence for unpatched third-party tasks lives only in `private/`.
- `outbound/`: drafts and patches for Raj to review and send. Claude never sends them.
- `.claude/loop.md`: the heartbeat prompt. `.claude/agents/`: reviewer and citation-checker subagents.

## Commands

| Command | What it does |
|---|---|
| `make setup` | `uv sync` the dev environment |
| `make doctor` | detect Docker, GPU, RAM, disk, claude CLI, local models, sandboxes, free tiers |
| `make test` | pytest with line coverage (writes coverage.json) |
| `make lint` / `make typecheck` | ruff check, ruff format --check, style rules / mypy --strict |
| `make ci` | lint, typecheck, test, offline demo (what CI runs) |
| `make demo` | offline demo from recorded fixtures, compared with its golden output |
| `make prereg-verify` | preregistration chain and ordering checks |
| `make claimcheck` / `make freshness` | every result number traces to an artifact / re-derive live numbers |
| `make citecheck` | validate artifacts/citecheck.json offline |
| `make secrets-scan` | scan tracked files for secrets |
| `make budget` | cash and cap usage from artifacts/usage/ledger.jsonl |
| `make review` | validate and print the latest independent review |
| `make report` / `make reproduce` | figures and docs/REPORT.md from artifacts / rerun every figure |
| `make ship-check` | `tools/ship_check.py`, all 14 gates on a fresh clone (`--fast` does not count) |

## Working rules for this repository

- One Loop Protocol iteration (section 10.2) per heartbeat: orient with `python tools/ship_check.py --fast`, choose one thing, build it test-first, verify, bank, record, commit.
- Model calls go only through the graderproof client wrapper (caps, ledger, cache). Never `--bare`. `total_cost_usd` is logged as `plan_equivalent_usd`, never as cash.
- Third-party code and subject agents run only inside a sandbox (Docker `--network none`, else bwrap or `unshare -rn` with a temp workspace and credentials stripped).
- Push only if `ALLOW_PUSH=1` is set, only to `origin`, never force-push, never push tags, never change repository settings.
- No em dashes in any file Claude writes. docs/BUILD_BRIEF.md is exempt only because it is immutable.
