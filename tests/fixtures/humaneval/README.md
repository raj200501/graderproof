# HumanEval recorded fixtures

Verbatim material from openai/human-eval (https://github.com/openai/human-eval) at commit
`b9453e8f1865df0a0057a1383767caa400acfbcf`, under the MIT License (`LICENSE` here,
Copyright (c) OpenAI). Copied from a git clone of that commit on 2026-11-04. The
contract tests in `tests/contract/test_humaneval.py` use these files offline.

| File | Source at the pinned commit | Integrity check in the tests |
|---|---|---|
| `HumanEval.sample.jsonl` | Lines 24, 33, 46, 51, and 52 of `data/HumanEval.jsonl.gz` (HumanEval/23, 32, 45, 50, 51), byte for byte | SHA-256 of the file |
| `execution.py.txt` | `human_eval/execution.py`, byte for byte, renamed so that ruff, mypy, and pytest skip it | git blob id `bcfd7c5d452e2dcbb1ea89317c47b9e0f1c2c4ca` |
| `LICENSE` | `LICENSE`, byte for byte | git blob id `4f14854c3243516f3de1487a60f14882874d7e3a` |

The five records cover all three prompt-length strata of the adapter, a prompt with an
import and a helper function that the test calls (HumanEval/32), a helper called by the
test with random inputs (HumanEval/50), floating-point results (HumanEval/32 and 45),
and a test containing a backslash escape (HumanEval/51). A git blob id can be checked
against the upstream repository with `git rev-parse <commit>:<path>`.
