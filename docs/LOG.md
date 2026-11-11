# Iteration log

History moved out of STATUS.md, newest first.

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
