# Amendment to prereg 0002: model requests carry the full task text

Amends: 0002 (prereg/0002-e1e2-audit.md)

- **Date**: 2026-11-11.
- **Original**: `prereg/0002-e1e2-audit.md`, frozen 2026-11-04T03:17:13Z with SHA-256 3e0bcbb077720a53d7781b244aefc7809795582bd363053ca0e5cca9e8d6ac3f (`prereg/FROZEN.jsonl`). It is not edited.
- **Status**: a change to the confirmatory E1/E2 procedure and to the secondary analyses built on it, committed and frozen before any data it affects, under the rule in prereg 0002 that an infrastructure fix needs a dated amendment committed before the data it affects. It is reported as a deviation in `docs/REPORT.md`, and recorded in `DECISIONS.md` as D38 (the decision), D39 (its scope), and D40 (the limits and E3 batch sizes).

## What was found

prereg 0002 runs the E0 configuration from a detached worktree at its own commit (f63b2d9, code tree of 75e8e87). In that code, text bound for model requests is cut at fixed lengths. `graderproof.validate` marks a cut with `[... N more chars]`: the task text at 8000 characters in requirement-extraction requests and at 4000 in review requests, reference outcome files at 2000, and reference solution files, changed files, and diffs in review requests at 4000. `graderproof.rootcause` slices the task text, the grader files, and the diff at 6000 characters with no marker.

The first E1 round built 17 requirement-extraction requests on 2026-11-04 (7 tau2-bench, 5 BFCL, 5 HumanEval). On 2026-11-11 model-worker subagents answered them, and every transcript passed the D24 file-access audit, but several workers reported cut task texts. `tools/clip_audit.py` measured the cuts in every model store (`artifacts/e1/clip_audit_round1.json`, counts and lengths only): every tau2-bench task text was cut, so the customer scenario, which follows the domain policy, never reached the extractor; most tau2-bench reference outcome files were cut; a few BFCL task texts lost part of their function documentation. No field was cut in any HumanEval request, nor in any request of the E0, E4, or demo stores, so the E0 and E4 results are unaffected. Under the frozen code, review requests would also have cut every tau2-bench task text and many BFCL task texts, and the E3 coder would have cut every E1 grader.

The decision was made from the request files and the workers' reports of truncation. No answer was ingested, read, or used, and no E1/E2 data exists: no ingested model answer, no variant, no grader verdict, and no score.

## Changes

1. **Code** (`src/graderproof/validate.py`, `src/graderproof/rootcause.py`, committed in 27d9349, the parent of the commit that freezes this amendment; `src/graderproof` tree c10e726c518392c32a5f144e20b25d08be91477a, `uv.lock` blob 735d0cdaae6ed1369e1534b811437d7d09e1cff3, unchanged from prereg 0002):
   - No task text is cut in any model request (requirement extraction, model proposal, review, root cause).
   - Reference outcome files in extraction requests keep up to 32000 characters instead of 2000.
   - Reference solution files, changed files, and diffs in review requests, and grader files and diffs in root-cause requests, keep up to 32000 characters instead of 4000 (review) or 6000 (root cause); every cut is marked.
   - Unchanged, because none binds in the E1 sample: the 4000-character limit on reference solution files in extraction requests, the 1000-character limit on workspace files, the 2000-character limit on reference stdout, and the first 50 trajectory calls.
   - Prompt versions, instructions, and schemas are unchanged, so every request whose fields fit the old limits is byte-identical to the frozen code's. `tests/test_request_identity.py` rebuilds the banked E0 and E4 requests and checks their hashes, and `make demo` replays the demo store unchanged.
2. **Batch sizes.** Whole tau2-bench task texts are long, so its requests carry fewer items: `--extract-batch 3 --propose-batch 3 --review-batch 6` (was 6, 6, 15). BFCL uses `--review-batch 15` (was 25), with `--extract-batch 8 --propose-batch 6` unchanged. HumanEval is unchanged (8, 6, 40). E3 root-cause requests use `tools/e3_rootcause.py --batch 3` for tau2-bench, `--batch 6` for BFCL, and `--batch 10` for HumanEval; the tool now has no default batch size. The sizes come from a dry run on the excluded fixture tasks and from the measured item sizes, as in prereg 0002, so that the largest request stays near the size the model workers have handled; batch size changes how items are grouped into calls, not what an item contains.
3. **Where the audit runs.** From a detached worktree at the commit that freezes this amendment (`/home/user/graderproof-e1-0003`), not from the worktree at f63b2d9. E3, E4, and E6 on the audited benchmarks, and E5, run from the same worktree.
4. **Stores, caches, and citation.** All three benchmarks use new model stores `artifacts/model_calls/<benchmark>-0003`, which link into `private/model_calls/<benchmark>-0003` (D35), new execution caches `runs/cache-<benchmark>-0003`, and new private evidence directories `private/evidence/<benchmark>-0003`; E3 model-coder stores are `artifacts/model_calls/e3-<benchmark>-0003`, linked the same way. Audits pass `--prereg prereg/0003-e1e2-full-task-text.md`, so E1/E2 artifacts and the E3, E4, and E6 artifacts built on them cite this amendment, which cites prereg 0002. The full commands are those of prereg 0002 with these values substituted for `--prereg`, `--store`, `--cache`, `--evidence`, and the batch flags.
5. **Answers already made.** All 17 round-1 answers are superseded and never ingested, including the 5 HumanEval ones, so that every E1/E2 answer comes from the amended code and postdates this amendment. They stay unused in the old private stores.

Everything else in prereg 0002 is unchanged: research questions, hypotheses H1 and H2 with their null rates, tests, Holm correction, intervals and seeds, the committed sample and its exclusions, the per-task operator caps, the reference and confirmation runs, the model backend and its audit, the secondary analyses E3 to E6 and their outcomes, and the stopping rules.

## Why the change cannot bias the results

It is made before any E1/E2 outcome exists, so it cannot be tuned to one. It gives the extractor, the model reviewer, and the E3 coder the inputs that prereg 0002 and the method describe, requirements and reviews judged against the task text, and removes an information loss that fell mostly on tau2-bench. Its cost is more model calls for tau2-bench and BFCL, which lengthens the run under the daily cap and changes no analysis.
