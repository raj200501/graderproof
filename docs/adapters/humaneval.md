# HumanEval adapter

`graderproof.adapters.humaneval` converts the HumanEval problems of
[openai/human-eval](https://github.com/openai/human-eval) into toybench task directories
of kind `module`, so that the toybench adapter loads and executes them with graderproof's
caching, sandboxing, requirement checks, and variant operators (DECISIONS.md D19).
HumanEval is the Docker-free substitute for Terminal-Bench 2.0, whose tasks need Docker
images that cannot run here (DECISIONS.md D18). The benchmark name is `humaneval`.

HumanEval was introduced in Chen et al., "Evaluating Large Language Models Trained on
Code" (2021, https://arxiv.org/abs/2107.03374; citecheck key `humaneval-2021`).

## Source and pinned version

| Item | Value |
|---|---|
| Repository | https://github.com/openai/human-eval (`git clone https://github.com/openai/human-eval.git`) |
| Pinned commit | `b9453e8f1865df0a0057a1383767caa400acfbcf`: the merge of pull request #70, which adds a deprecation notice to the README, committed 2026-10-16. It was the head of `master` when checked on 2026-11-04. |
| Data file | `data/HumanEval.jsonl.gz`, SHA-256 `b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef`, unchanged since the first commit (463c980, authored 2021-07-06) |
| Records | HumanEval/0 to HumanEval/163, each with `task_id`, `prompt`, `entry_point`, `canonical_solution`, `test` |
| Grading code | `human_eval/execution.py`, git blob `bcfd7c5d452e2dcbb1ea89317c47b9e0f1c2c4ca`, last changed in commit 37c4dd6 ("fix broken eval", 2025-01-16, merged 2025-01-17) |
| Retrieval | Cloned with git and verified on 2026-11-04. The benchmark survey first read the same commit on 2026-10-23. |

The adapter records the commit and the data SHA-256 as constants (`PINNED_COMMIT`,
`DATA_SHA256`). The upstream README marks the repository as deprecated and unmaintained,
so upstream fixes to graders are not expected.

## License and attribution

The repository, data included, is under the MIT License, Copyright (c) OpenAI. The
generated graders copy most of `human_eval/execution.py`, so the grader template in
`src/graderproof/adapters/humaneval.py` and every generated `grader/grade.py` carry the
full copyright and permission notice. The recorded fixtures in `tests/fixtures/humaneval/`
include upstream's `LICENSE`. Converted tasks are written under `runs/`, which git
ignores, so this repository does not redistribute the data beyond the five fixture
records.

## Commands

```
uv run python -m graderproof.adapters.humaneval fetch runs/humaneval/src
uv run python -m graderproof.adapters.humaneval convert runs/humaneval/src runs/humaneval/tasks
uv run python -m graderproof.adapters.humaneval check runs/humaneval/tasks --repeat 3 --cache runs/humaneval/cache
```

* `fetch DEST` makes a shallow clone, fetches the pinned commit if the clone lacks it,
  checks it out detached, and verifies `HEAD` and the data file's SHA-256. It runs no
  code from the repository. An existing checkout in `DEST` is reused.
* `convert SRC OUT` takes the checkout or the data file, verifies the SHA-256, and writes
  one task directory per problem. It refuses an `OUT` that already holds task
  directories of other problems, because the toybench loader would load them too.
* `check TASKS` grades every unmodified reference `--repeat` times through
  `graderproof.run.Runner.precheck` under bubblewrap, prints each task's determinism
  class and grader output, and exits 0 only if every reference passes on every run. It
  refuses to run without a write-isolating sandbox.

The Python functions are `fetch(dest)`, `convert(jsonl_gz_path, out_dir)` (returns the
task directories), and `check_references(tasks_dir, sandbox, repeat, cache_dir)`.

## Mapping

| HumanEval field | toybench task |
|---|---|
| `task_id` (`HumanEval/N`) | directory name and task id `HumanEval-N`; `metadata.original_id` |
| `prompt` | `instruction.md` (in a code fence); the start of `solution/solution.py` |
| `canonical_solution` | the rest of `solution/solution.py` |
| `test` | the `TEST` constant of `grader/grade.py`, verbatim |
| `entry_point` | `ENTRY_POINT` in `grader/grade.py`; `metadata.entry_point` |

`task.toml` holds `id`, `benchmark = "humaneval"`, `kind = "module"`,
`third_party = true`, `timeout_s = 20`, `[solution] module = "solution"`,
`[grader] entry = "grade.py"`, and `[metadata]` with `benchmark`, `original_id`,
`entry_point`, `source_repo`, `source_commit`, `source_path`, `source_sha256`,
`record_sha256` (SHA-256 of the record's canonical JSON, to trace a task to its source
record), `license = "MIT"`, `stratum`, and `prompt_chars`. Because `third_party` is true,
the Runner refuses any sandbox that does not isolate writes.

## Task text

`instruction.md` reads, for entry point `f`:

> Complete the Python function `f` below so that it does what its docstring describes.
>
> Write the complete program to the file `solution.py`. It must define `f` at module
> level. Start the file with the code below as given (its imports, any helper functions,
> and the signature and docstring of `f`), then write the body of `f`.

followed by the prompt in a Python code fence (longer than any run of backticks in the
prompt). A HumanEval sample is a completion that the harness appends to the prompt, so
the instruction asks for the prompt as given followed by the body. The helper functions
in a prompt matter: some tests call them, for example `poly` in HumanEval/32 and
`encode_shift` in HumanEval/50.

## Reference solution

`solution/solution.py` is `prompt + canonical_solution`, which is exactly the program
upstream checks for the canonical completion.

## Grading

`grader/grade.py` reproduces `check_correctness()` of `human_eval/execution.py` at the
pinned commit and uses the standard library only. It reads `solution.py` from the
working directory (UTF-8, no newline translation) as the program. A child process forked
from the grader then does what upstream's `unsafe_execute()` does: it changes into an
empty temporary directory, applies `reliability_guard()` (no memory limit, the upstream
default), swallows standard output and error and makes standard input raise on read, and
within 3.0 seconds executes the check program

    program + "\n" + test + "\n" + f"check({entry_point})"

in a fresh, empty globals dictionary. The result is `passed` if nothing was raised,
`timed out` if the time limit expired, and `failed: <exception>` for any other
`BaseException`, including `SystemExit`. If the child sends no result (for example it
called `os._exit`), the result is `timed out`, as upstream. 3.0 seconds is the `timeout`
default of upstream's `evaluate_functional_correctness()` and of its command line, and
the parent waits at most that plus one second, as upstream does.

The grader prints one JSON line, `{"task_id": ..., "passed": ..., "result": ...}` (the
fields of upstream's results file, with the result cut to 2000 characters for display),
and exits 0 exactly when the result is `passed`, which is what toybench counts as a
pass.

Changes to upstream's `check_correctness()` and `unsafe_execute()`:

1. The program comes from `solution.py` rather than from the strings `prompt` and
   `completion`. For a program that starts with the prompt, the check program is the
   same string. A missing or non-UTF-8 `solution.py` gives `failed: <error>`.
2. The child sends its result to the parent over a pipe instead of appending it to a
   `multiprocessing.Manager` list. The string is encoded as UTF-8 with the
   `surrogatepass` error handler, so every result string arrives unchanged, including
   exception messages with unpaired surrogates. The parent waits up to the time limit
   plus one second for the result, then until the same deadline for the child to exit,
   and kills it if it is still running.
3. The `fork` start method is named explicitly. It is the Linux default before Python
   3.14 (3.14 made `forkserver` the default), so the child starts as a copy of the
   grader, as upstream's child starts as a copy of the evaluation process on Linux.
4. `reliability_guard()` disables `help` through the `builtins` module, because a
   generated grader runs as `__main__`, whose `__builtins__` is a module rather than a
   dictionary.
5. Upstream's warning comment above the `exec` call is left out.

All other functions and classes (`time_limit`, `swallow_io`, `create_tempdir`,
`TimeoutException`, `WriteOnlyStringIO`, `redirect_stdin`, `chdir`, and the rest of
`reliability_guard`) have upstream's syntax trees. Two contract tests hold this in place:
one compares those syntax trees with the recorded upstream `execution.py`, and one runs
the recorded upstream `check_correctness()` under bubblewrap on the fixture references
and on wrong programs of every result kind (wrong answers, syntax errors, exceptions,
non-ASCII and unpaired-surrogate exception messages, `sys.exit`, `exit()`, `input()`,
printed output, `os._exit`, a loop past a shortened time limit, a missing helper
function, and a read of `solution.py` from the working directory), and requires the
same result strings from the generated graders. That test calls `check_correctness()`
from a driver that imports nothing else.

So a program that does not depend on the process it runs in gets the same result
string here as from upstream's `check_correctness()` on the same Python version.
Upstream's usual entry points, the function `evaluate_functional_correctness()` and the
`evaluate_functional_correctness` command, run checks in a process that differs from
the grader's in these ways:

* **Preloaded modules.** `human_eval/evaluation.py` imports numpy and tqdm, and the
  command also imports fire, before any check forks. The child inherits them, so a
  program can import them although `reliability_guard()` has run. The grader's child
  has only the standard-library modules the grader imports. Importing numpy calls
  `os.putenv`, which `reliability_guard()` disables, so a correct program that imports
  numpy gets `failed: 'NoneType' object is not callable` here and `passed` under
  upstream's command line. This was checked under bubblewrap on 2026-11-04 with the
  sandbox's `python3` and numpy 2.5.3. In the same check, `resource` (which the guard
  blocks on purpose, here and upstream) and `trace` were the only standard-library
  modules that could not be imported after the guard, so programs that use only the
  standard library are not affected.
* **Threads.** Upstream runs checks in a pool of 4 threads (the `n_workers` default)
  and forks each child from that multi-threaded process. The grader forks from a
  single-threaded process.
* **Hash seed and environment.** graderproof's sandbox sets `PYTHONHASHSEED=0` and
  scrubs the environment; upstream's child inherits the evaluation process's random
  hash seed and environment. A program whose result depends on the iteration order of
  a set of strings can be stable here and vary between upstream runs.
* **Call depth.** The program runs a few Python frames deeper or shallower than under
  upstream, which matters only for recursion within a few frames of the recursion
  limit.

The grader uses only the standard library, so it does not preload numpy. Preloading it
to match upstream's command line would be a separate, recorded decision.

## Strata

`metadata.stratum` is a sampling stratum by prompt length in characters:
`prompt-short` below 335, `prompt-medium` from 335 to 474, and `prompt-long` from 475.
Prompt length is a property of the task text only. On the pinned data file these cut
points split the 164 problems as evenly as three groups allow (55, 55, and 54 problems).
The cut points are constants, so a task's stratum never depends on which other tasks
were converted with it.

## Execution limits and environment

The grader runs as `python3` from the sandbox's scrubbed `PATH`, which is CPython 3.13
on this machine. toybench gives the grader process 20 seconds of wall-clock time, 41
seconds of CPU time, 4 GiB of address space, and a 256 MiB file size limit; these are
graderproof's sandbox limits, not HumanEval's. Under `BwrapSandbox` the root file system
is read-only, only the workspace is writable, `/tmp` is a fresh tmpfs, the home
directory is hidden, there is no network, and the environment is scrubbed of
credentials.

There are two time limits. `timeout_s = 20` in `task.toml` is graderproof's wall-clock
limit for the whole grader process. HumanEval's own limit, 3.0 seconds per check, is
inside `grade.py` and is the one that produces `timed out`. graderproof's `pre-delay`
operator, which scales a start delay to `timeout_s`, applies only to `script` tasks, so
it does not touch these `module` tasks.

graderproof's function-call probes (requirement checks) import `solution.py` with the
Python that runs graderproof (3.12 under the repository's `.python-version`), not with
the grader's `python3`.

## Tests

`tests/contract/test_humaneval.py` runs offline on recorded fixtures: five verbatim
records (HumanEval/23, 32, 45, 50, 51, which cover all three strata), upstream's
`execution.py`, and upstream's `LICENSE` (see `tests/fixtures/humaneval/README.md`). The
tests check the fixtures' SHA-256 and git blob ids, conversion and loading, the refusal
of malformed records (before anything is written), that each
reference passes its grader, that wrong solutions fail, the time limit, agreement with
upstream's `check_correctness()`, function-call probes, the Runner's sandbox policy, the
`check` command, `fetch` (with git replaced by a fake), and the command line. HumanEval
test code, canonical solutions, and upstream's `execution.py` are third-party code, so
the tests that run them use bubblewrap and are skipped where it does not work (for
example on CI runners without it); every other test runs no task code.

## Verification on the full data

Reproduce with the three commands above. `check` grades every reference through the
Runner under bubblewrap and lists every task that is not a stable pass, by id. Its output
is not yet banked under `artifacts/` by a committed script, so this document states no
result numbers (non-negotiable 1).

## Limitations

* HumanEval's tests are small (a handful of assertions per problem). That weakness is
  what graderproof measures; it is not a defect of the adapter.
* `reliability_guard()` is not a security boundary, as upstream's own docstring says. The
  solution runs in the same process as the check and could interfere with it, exactly as
  under upstream. graderproof relies on bubblewrap for isolation, and its variants come
  from the reference solution and the task text, never from an adversarial search.
* The 3-second limit is wall-clock time (`ITIMER_REAL`). A program close to the limit can
  pass on one run and time out on another under load; the Runner's determinism precheck
  reports such tasks as flaky rather than dropping them.
* The instruction does not state the time limit, as HumanEval's prompt does not. A
  correct program that takes longer than 3 seconds is rejected.
* A correct program that imports numpy is rejected here and accepted by upstream's
  command line (see Grading). A variant that adds such an import can therefore look like
  a false reject that HumanEval's own harness would not make.
* Results can depend on the interpreter version for programs that rely on
  version-specific behavior. Upstream was written for Python 3.7 or later; the graders
  run on the sandbox's `python3`.
* The instruction asks for the prompt as given, so an edit to a prompt's helper function
  or docstring counts as a violation of the stated task even when it does not change
  behavior. This matches HumanEval, where the prompt is fixed.
* The test code is embedded in `grader/grade.py` as the `TEST` constant, so a repair
  that strengthens HumanEval's own test edits that constant. A repair can instead run
  its own checker on the workspace before `grade.py`; because `grade.py` reads only
  `solution.py` from the working directory, it works unchanged behind such a wrapper.
* Only the original HumanEval tests are used. EvalPlus HumanEval+ would be a separate,
  exploratory comparison (D18).
* Task-level findings for HumanEval stay in `private/` (non-negotiable 14); only
  aggregates and hashes may be committed.
