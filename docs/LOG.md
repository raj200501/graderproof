# Iteration log

History moved out of STATUS.md, newest first.

## 2026-11-12, goal_turn 6 (continued past midnight UTC)

- The open findings of the 5677b9f review were fixed by a workflow of implementers and adversarial verifiers (c647941): G5 drops reference-level flags and ties each adjudicated variant to its task, its flag, and the ledger's response hash; G14 fails on tracked third-party evidence; the 0.90 allowlist row is narrowed and every threshold comparison is tested against the artifact; adjudication provenance records the tool's own commit.
- The G12 review of the current HEAD runs on 2026-11-12, the first UTC day with an unused review run.
- The review of 2d87aaa returned BLOCK: the E4 mutation score before and after repair was not reported (B1), and G7 accepted audits citing any preregistration (B2). Both are addressed; its non-blocking issues are logged.
- E1/E2: 47 answers by audited model workers were ingested within the cap. HumanEval finished all four rounds and is the first complete confirmatory audit of a public benchmark; BFCL and tau2-bench continue.
- The first GitHub Actions run on main failed 7 tests that pass locally; D41 fixed the runner's interpreter location and the upstream HumanEval driver's start method without skipping a test (5373797, green on main). Fast check on 5373797: 9/14. RELEASE-READY 5373797.
- Release sprint (Raj's message, repeated on 2026-11-12): experiments paused; secrets scan clean; nothing under `private/` or `runs/` tracked now or in history; author and committer identities are Raj's GitHub noreply address, the Anthropic noreply address, and GitHub's; every email address in tracked files and history is a fictitious or benchmark placeholder. A four-lens audit workflow found that the public HumanEval task hashes reverse to task ids (by design, for G7) and that classical variant ids can be matched by regenerating the variants, which exposes the classical survivors (D43). The documents now say so; the sprint ended NOT-READY.
- D44: `tools/publish_rows.py` republished the HumanEval rows with keyed ids and no operator names, and G14 now checks every third-party audit for keyed rows (fresh clone) and for rows that republish from their private original (original checkout). The regeneration attack matches none of the public rows.
- Final README pass for first-time readers (D42): current gate state in the Status section, the HumanEval headline with its mean mutation score and validator agreement, a plain description of what a finding looks like on the synthetic demo, and one repeated limitation merged.

## 2026-11-11, goal_turn 6: E1 round 1 answered, text clipping found, release sprint

- Final fast check of goal_turn 5 on 4f53770: 9/14 (G5, G7, G8, G9, G12 fail).
- E1/E2 round 1: model-worker subagents answered the 17 requirement-extraction requests; all 17 transcripts passed the D24 audit. Workers reported cut task texts: the frozen code clips text bound for model requests, which hid every tau2-bench customer request. `tools/clip_audit.py` measured the cuts per store (none in HumanEval, E0, E4, or the demo). Nothing was ingested; D38 records the decision to amend prereg 0002 before any E1/E2 data. The amendment workflow was stopped in its read-only scope phase when the release sprint arrived.
- Release sprint: publication checks passed; README.md gained a pitch paragraph and a Status section; STATUS.md updated.
- Release sprint finished: RELEASE-READY e4daee8; Raj merged it into main and made the repository public.
- prereg 0003: the code change was scoped, implemented, and checked by an adversarial workflow (27d9349), then the amendment was frozen (22b8832). The E1/E2 worktree `/home/user/graderproof-e1-0003` holds new stores; round 1 rebuilt 24 extraction requests with no cut field.
- A session heartbeat (every 30 minutes) carries Raj's standing order.

## 2026-11-11, goal_turn 5: E0 complete, E4 on toybench, README and report

- E0 (prereg 0001) finished from the frozen worktree at 1629c30: the remaining review batches were answered by model-worker subagents and their transcripts audited, flags that were not detections were adjudicated (D34), and the preregistered scoring command was run; the labels were committed unchanged and match the hash committed in 7fab903 (a34b46a). H1 (recall at least 0.90) is not met and H2 (precision at least 0.90) is met; docs/E0_MISSES.md explains every miss (e43683f).
- E4 ran on toybench from the frozen E1 worktree, reusing E0's banked requirement answers (D36): repairs for every grader with a surviving variant and a generalization batch on fresh variants (da44920).
- README.md, docs/REPORT.md, the toybench grader card, and two figures are rendered from artifacts by `make report`; claimcheck, freshness, and citecheck pass (e43683f, c07ee5e). docs/REVIEW_LOG.md lists the non-blocking issues of the df55c18 review and what became of each.
- G1's evidence line now counts passed tests rather than all collected tests (5677b9f).
- Independent review run on 5677b9f (artifacts/review/).
- Model calls today: 36 single calls through the client wrapper, within the daily cap.

## 2026-11-04, goal_turns 3 and 4: review fixes, adapters, claim tooling, E0 and E1 under way

- Milestone review before the E0 freeze (763b03d): REVIEW: BLOCK with five blocking issues. Package fixes in 2d8058f (D24 to D28) and gate fixes in 51fe7b3 (D33), with the falsification scenarios ported as tests.
- E0 materials: 72 toybench tasks from an independent planting subagent and the SHA-256 of their labels (7fab903); prereg 0001 frozen (1629c30); the E0 audit started from a frozen worktree.
- Adapters merged for HumanEval (D29), BFCL V4 (D31), and tau2-bench v1.0.1 (D32); claim tooling merged (claimcheck, freshness, citecheck, report; D30).
- prereg 0002 frozen for E1 and E2 with its sample (f63b2d9); third-party model stores made private with hash manifests (D35); E3 and E6 runners built (cec7cbd).

## 2026-10-23, goal_turns 1 and 2: launch settings, M1, benchmark decisions

- Launch settings recorded (ALLOW_PUSH, CAP_SHARE 0.2), bubblewrap as the sandbox, and Claude Code subagents as the model backend (1ef9c3e).
- M1: the offline audit pipeline, the toybench adapter, and the offline demo with its golden output (85f4f22).
- Benchmark decisions D18 and D19 and survey notes (0e19aa8); model-proposed variants, item-level response reuse, and the preregistration chain (8bba7eb).

## 2026-10-23, goal_turn 0: bootstrap

Bootstrap from docs/BUILD_BRIEF.md section 10.1: brief copied and hashed, `make doctor` run, CLAUDE.md, heartbeat prompt, reviewer and citation-checker subagents, package scaffold with core data model, all make targets (unbuilt ones fail through tools/stub.py), tools/ship_check.py for G1 to G14, docs/PLAN.md.
