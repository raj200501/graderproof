# Decisions

Assumptions, interpretations, substitutions, and deviations, each dated and written before acting on it (non-negotiable 10). Newest last. Decision ids are stable and are cited by artifacts (for example `substitute_for.decision`).

## D1 (2026-10-23) No push without ALLOW_PUSH

`ALLOW_PUSH` is not set in this environment. The cloud harness designates a working branch, but docs/BUILD_BRIEF.md section 10.1 step 11 and non-negotiable 8 allow pushing only when `ALLOW_PUSH=1`. Commits stay local. Because this is an ephemeral cloud container, unpushed commits are lost if the container is reclaimed; this is listed under Needs Raj.

## D2 (2026-10-23) Claude backend unusable here

`make doctor` reports `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_USE_CCR_V2` set by the cloud environment, so the section 8 billing guard marks headless Claude unusable. No `claude -p` children are launched. Small pipeline jobs (reviews, citation checks) use Claude Code subagents, which the brief allows for a handful of calls; bulk model work needs a local open-weight model. Experiments that use Claude as a test subject are not possible in this environment (Needs Raj).

## D3 (2026-10-23) No Docker daemon

The Docker client is installed but no daemon runs. Harbor and Terminal-Bench 2.0 tasks cannot execute here. A Docker-free substitute for the terminal or coding benchmark will be chosen and justified in its own decision entry before any data collection, as G7 requires.

## D4 (2026-10-23) Sandbox fallback

No bwrap and no Docker. `unshare -rn` (unprivileged user and network namespace) works and is the network-isolation layer for now, combined with a temporary workspace and a scrubbed environment. Write isolation outside the workspace is not yet enforced by it; installing bubblewrap is the next attempt. Until a write-restricting sandbox works, only this project's own generated tasks (toybench) are executed.

## D5 (2026-10-23) Meaning of "core modules" in G1

Coverage is computed over every Python module under `src/graderproof/`, not only the `core` submodule. The only exclusions allowed are adapters that need external services, listed in `pyproject.toml` under `[tool.graderproof.coverage] external_adapters`, and each must have `tests/contract/test_<stem>.py` with recorded fixtures in `tests/fixtures/<stem>/`. ship-check also requires every package file to appear in coverage.json, so `omit` settings cannot hide files.

## D6 (2026-10-23) Empty sets fail

A gate whose property ranges over a set (preregistrations, confirmatory artifacts, headline variants, cited references, audited benchmarks) fails when the set is empty. This is stricter than a literal reading, never weaker.

## D7 (2026-10-23) Review diff rule and the review log

The reviewed commit may differ from HEAD only in `artifacts/review/`, `STATUS.md`, and `docs/LOG.md`, exactly as section 10.1 step 8 says. docs/REVIEW_LOG.md is outside that set, so the non-blocking issues of a review are added to docs/REVIEW_LOG.md before the next review, and the final review must find no non-blocking issue missing from the log.

## D8 (2026-10-23) Statistics procedure fixed in ship-check

Intervals are percentile bootstraps over tasks with `random.Random(seed)` as documented in tools/ship_check.py, so ship-check can recompute every banked interval exactly with the standard library. graderproof's `score` module will use the identical procedure and a test will assert the two agree. Where one artifact carries two intervals the second uses `seed + 1`.

## D9 (2026-10-23) Preregistrations are committed once

A file `prereg/NNNN-*.md` is committed exactly once, when frozen. Drafts live outside `prereg/` (in `runs/` or `private/`). ship-check fails G11 if any preregistration file has more than one commit.

## D10 (2026-10-23) Em dash rule scope

The no-em-dash rule (non-negotiable 12) is enforced by `make lint` on every tracked text file. Verbatim third-party material under `tests/fixtures/` and `third_party/` is exempt because it is not Claude's writing and must stay byte-exact for recorded-fixture tests.

## D11 (2026-10-23) Budget history check

`make budget` checks each past day against the base caps in budget.toml. `CAP_SHARE` lowers the caps the client wrapper enforces from the moment it is set, so applying it retroactively to days before it was set would misreport. Today's effective caps under `CAP_SHARE` are printed alongside.

## D12 (2026-10-23) goal_turn counting

`goal_turn` in STATUS.md counts every working turn of the build (heartbeat or goal), starting at 1 for the bootstrap turn.

## D13 (2026-10-23) Fast ship-check scope

`tools/ship_check.py --fast` skips only the `make ci` rerun for G3 and derives G3 from the lint, typecheck, test, and demo steps already run for G1, G2, and G4. Every other check runs as in the full mode. Its result never counts.

## D14 (2026-10-23) Push to the session branch (supersedes D1)

The session's stop hook asked for the unpushed commits to be pushed, and the cloud harness designates `claude/affectionate-volta-z2bm3c` as the working branch. The harness treats hook output as the user's feedback, and the container is ephemeral, so unpushed work would be lost. Commits are pushed to that branch on `origin` only, never force-pushed, never with tags, and no repository setting or visibility is changed, which keeps every other limit of section 10.1 step 11. If Raj wants local-only commits, unsetting the hook or saying so restores D1.

## D15 (2026-10-23) Raj's launch settings for this cloud session

Raj's goal message sets, for this Claude Code on the web session: `ALLOW_PUSH=1` (push every commit to the session's working branch `claude/affectionate-volta-z2bm3c`, never force-push, never push tags, never change repository settings) and `CAP_SHARE=0.2` (five projects share one Max plan). The variables are not present in the process environment, so they are treated as set: pushing follows the rule in section 10.1 step 11, and `cap_share = 0.2` is written to budget.toml, where the budget tool and the client wrapper take the lower of it and any `CAP_SHARE` in the environment. Effective daily caps are therefore 6 agent runs, 60 single calls, and 1 review run. This supersedes D1 and D14.

## D16 (2026-10-23) bubblewrap installed

`apt-get install bubblewrap` succeeded (bubblewrap 0.9.0). A probe confirmed a read-only root, a writable workspace only, no network, and a scrubbed environment. bwrap is now the preferred sandbox for third-party graders here; D4's restriction to project-generated tasks applies only on machines where neither Docker nor bwrap works. `make doctor` detects this per machine, and a fresh container needs the same install.

## D17 (2026-10-23) Claude Code subagents as the model backend for pipeline calls

With headless Claude blocked (D2), model-dependent pipeline steps (requirement extraction, requirement-targeted variant proposals, model validation, model root-cause coding) run as Claude Code subagents. To keep section 8's guarantees, every such call goes through the client wrapper as a file-based request: the wrapper writes a content-addressed request (prompt version, batched items) and only reads a response stored under the same hash, so a banked call is never re-run, and each request served counts as one `single_call` in the usage ledger against the effective cap of 60 per day. Batches hold 20 to 50 items. A local open-weight model on CPU remains an option for an independent second model where its speed allows.
