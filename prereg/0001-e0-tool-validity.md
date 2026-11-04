# 0001 E0: tool validity on planted ground truth (toybench)

Status: confirmatory for gate G5 (docs/BUILD_BRIEF.md sections 5 and 6). Frozen on 2026-11-04; the chain entry in prereg/FROZEN.jsonl records the exact time, the file hash, and the parent commit. Decisions it relies on: DECISIONS.md D17, D22 to D28.

## Question

Does graderproof detect planted grader weaknesses, in both the false-accept and the false-reject direction, with recall and precision each at least 0.90 on a benchmark whose ground truth was written independently of the tool?

## Materials

- **toybench**: the 72 task directories in `toybench/tasks/` (24 script, 24 module, 24 trajectory), committed in 7fab903bf86e07165f09365bd48ed9ace26a54fb (tree `f8c673883da19387ea5662d73020c7ca51602f38`). They were written by an independent planting subagent; its prompt, what it could see, and an audit of its file access are in docs/e0/planter_prompt.md. Disclosure (review item N19): besides the toybench adapter (for the task format) and sections 3 and 5 of the brief (which contain the weakness list it was given), the planter could read CLAUDE.md, whose mission paragraph says that graderproof runs graders on spec-violating and spec-preserving variants of the reference solution. It did not read the variant operators, the validators, the requirement checks, the tests, or the examples, and it never ran graderproof. Slices, as specified to the planter:
  - `in_list` (32 tasks): one planted weakness per task, of the types in docs/BUILD_BRIEF.md section 3: presence-not-content, exit-code-only, loose-matching, outcome-only-process, brittle-parsing (false reject), and timing; each labeled with a direction, `accept` or `reject`.
  - `clean` (32 tasks): graders that check exactly what the instructions require.
  - `extra` (8 tasks): weakness types outside that list, chosen by the planter; reported beside G5 and not counted in it.
- **Labels**: written by the planter to `private/toybench/labels.json`. Their SHA-256 is committed in `toybench/labels.sha256` in the same commit 7fab903, which precedes this preregistration and every graderproof run on toybench. The labels file is committed as `toybench/labels.json` only after the run is complete, byte for byte unchanged; ship-check G5 verifies it against the committed hash. Before that commit, the only label information seen by the build session was the per-slice and per-direction task counts, used to check the file's structure.
- **Materials check** (before 7fab903): every task loads with the toybench adapter and every reference passed its own grader once under the bwrap sandbox. No variant was generated and no model was called on these tasks. The planter verified each reference three times and demonstrated each planted weakness with a concrete solution, which graderproof never sees.

## Tool, frozen

- **Code**: graderproof at the commit that adds this file. Its `src/graderproof/` tree is `c6d6ee4a541b5a709af0bb26630a6a55f22a9e0c` and its `uv.lock` blob is `735d0cdaae6ed1369e1534b811437d7d09e1cff3`. The run uses a detached git worktree checked out at that commit (D28), so development may continue elsewhere while it runs; every artifact's provenance records the package source fingerprint, the git commit, and `git_dirty`. No change to that worktree is allowed. A fix needed for an infrastructure failure (a sandbox crash, an unparseable model response that cannot be re-requested) is made only through a dated amendment file committed before the data it affects, and reported as a deviation.
- **Sandbox**: bwrap (write isolation, no network, home directory, `/tmp`, and every `private/` directory hidden). The audit refuses a confirmatory run in a sandbox without write isolation.
- **Command** (run from the frozen worktree, whose `artifacts/e0` and `artifacts/model_calls/e0` are links into the main checkout so that responses are banked and pushed as they arrive):

  ```
  graderproof audit toybench/tasks --adapter toybench --sandbox bwrap \
    --confirmatory --prereg prereg/0001-e0-tool-validity.md \
    --store artifacts/model_calls/e0 --ledger <main>/artifacts/usage/ledger.jsonl \
    --cache <main>/runs/cache-e0 --out artifacts/e0 --public-task-ids \
    --review-queue <main>/private/review_queue \
    --k 3 --confirm-runs 2 --seed 2026 --max-per-operator 6 --max-total 40 \
    --replicates 2000 --extract-batch 8 --propose-batch 6 --review-batch 40
  ```

  `<main>` is the main checkout. The execution cache directory is used only by this run.
- **Variants**: every classical violating and preserving operator in `graderproof.variants`, sampled at most 6 per operator and 40 per task with seed 2026 (preserving variants keep their reserved share), plus model proposals (`propose/v1`). Requirements: `requirements/v1`. Second validator: model review `review/v1`.
- **Model backend**: Claude Code `model-worker` subagents (alias sonnet) answering content-addressed request files through the client wrapper (D17), within the daily cap of 60 single calls (D15). Request items carry task key hashes, never task names (D24). After the run, every worker transcript is audited with `tools/transcript_audit.py`: a worker may read only its request file and write only its response file. A response from a worker that touched anything else is discarded and its request answered again by a new worker; the audit result is banked with the E0 artifacts.
- A variant counts only with two agreeing, independent validations (deterministic witness and model review) and a stable grader verdict; flagged verdicts are confirmed by 2 more runs. A task is scorable only when its grader passes the reference in all k = 3 runs (D26).

## Outcomes and definitions (D23)

- A task is **flagged** when graderproof reports a witness-backed false accept (a counted violating variant the grader accepts) or a witness-backed false reject (a counted preserving variant the grader rejects).
- A grader that rejects the reference or is flaky on it is reported separately (`reference_level`) and is never a flag or a detection: such planted tasks count as misses, such clean tasks count as unflagged.
- A planted task is **detected** when it is flagged in its planted direction: `accept` needs a false accept; `reject` needs a false reject.
- **Counted tasks**: the `in_list` and `clean` slices (64 tasks). The `extra` slice is scored the same way and reported separately.
- **Recall** = detected planted tasks / planted tasks, over counted tasks.
- **Precision** = detections / (detections + false positives), over counted tasks, where a false positive is a flag that is not a detection and was not adjudicated real.
- **Adjudication**: every counted flag that is not a detection (a flag on a clean task, or a planted task flagged only in the other direction) is reviewed by an independent reviewer subagent, which sees the task text, the grader, the flagged variant, and its witness, and rules only whether the witness validates: whether the flagged variant really breaks (for a false accept) or really keeps (for a false reject) the requirement the witness names, as the task text states it. It does not see the labels. A validating witness makes the flag a real weakness (`real: true`), reported separately and not a false positive; otherwise the flag is a false positive. Rulings and reasons are banked in `artifacts/e0/adjudication.json`; the build session does not overrule them. Precision without adjudication is reported beside it.
- **Intervals**: percentile bootstrap over counted tasks with B = 2000 and alpha = 0.05, seed 2026 for recall and 2027 for precision (`graderproof.stats`, the procedure ship-check recomputes). Exact Clopper-Pearson intervals for both are reported beside them as exploratory.
- Scoring command (from the frozen worktree, after the labels are copied unchanged to `toybench/labels.json`): `graderproof e0-score --audit artifacts/e0 --labels toybench/labels.json --labels-sha256 toybench/labels.sha256 --adjudication artifacts/e0/adjudication.json --out artifacts/e0/results.json --seed 2026 --replicates 2000`.

## Hypotheses and thresholds

- **H1**: recall is at least 0.90 (point estimate).
- **H2**: precision is at least 0.90 (point estimate).

These are the G5 thresholds. The 95% interval lower bounds are reported beside the point estimates; with 32 planted tasks the intervals are wide, and a lower bound below 0.90 is stated as a limitation.

## Secondary outcomes (exploratory)

Recall per weakness type and per task kind; detections in the extra slice; recall when reference-level flags on `timing` tasks are counted as detections; per-task mutation scores; validator agreement and the count of variants with an unsure verdict; which operators produced the detecting variants.

## Exclusions and stopping rule

- No task is excluded. A task whose grader rejects or is flaky on the reference is scored by the rules above.
- One run. When the daily model cap interrupts it, it resumes from the banked responses and the execution cache with the identical configuration.
- No re-run with a changed tool counts toward these hypotheses. If H1 or H2 fails, the result is reported as it is, with the same prominence; an improved tool would be evaluated on a newly planted set under a new preregistration.
- Every miss (counted and extra) is explained in `docs/E0_MISSES.md` after the run, from the evidence and the grader source.
