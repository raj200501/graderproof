# BFCL adapter

`graderproof.adapters.bfcl` converts the Python AST categories of the Berkeley Function
Calling Leaderboard (BFCL V4, the `berkeley-function-call-leaderboard` directory of
[ShishirPatil/gorilla](https://github.com/ShishirPatil/gorilla)) into toybench task
directories of kind `data`. The toybench adapter then loads and executes them with
graderproof's caching, sandboxing, requirement checks, and variant operators
(DECISIONS.md D18, D19). Every grader calls BFCL's own `ast_checker` from a pinned
checkout. The benchmark name is `bfcl`.

## Source and pinned version

| Item | Value |
|---|---|
| Repository | https://github.com/ShishirPatil/gorilla (`git clone` works; the github.com web pages may return 403 here) |
| Pinned commit | `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` (`PINNED_COMMIT`): the head of the default branch when checked with `git ls-remote` on 2026-11-04, and the commit the benchmark survey read on 2026-10-23 (docs/research/benchmarks_survey_2026-10-23.md, which dates it 2026-03-23, the date of bfcl-eval 2026.3.23) |
| Data | `bfcl_eval/data/BFCL_v4_<category>.json` (questions and function documentation) and `bfcl_eval/data/possible_answer/BFCL_v4_<category>.json` (possible answers), one JSON object per line |
| Grading code | `bfcl_eval/eval_checker/ast_eval/ast_checker.py`, SHA-256 `2aae7a68461a8f76c0be3894c8901b66b56967a1989d3ab066051e3fb97f1538`; it reads one flag from `bfcl_eval/constants/model_config.py`, SHA-256 `ec72b8499f140c9d870cebc909c895facb3cb26febc2d9146c8f1dfdea7bdcbc` |
| Retrieval | Fetched with `fetch` and verified (`HEAD` equals the pin) on 2026-11-04 |

Categories (`CATEGORIES`) and the SHA-256 of each question file at the pin:

| Category | Entries | Question file SHA-256 |
|---|---|---|
| `simple_python` | 400 | `82dd63ba502eb2520c6b5d1d9a5c4b590e03ff261565175561f6228a367d1991` |
| `multiple` | 200 | `aef168155ebd74b7ac2401198b201343bc7d16d7a3d7e0d4e6d8ee82c6969b2a` |
| `parallel` | 200 | `19f51a82eff42e5d62541aa500115a056eb78f437c2ba1f10415fd7c8e5dda84` |
| `parallel_multiple` | 200 | `8863ea8433239f55c5f016154cf0830853c89f693c6ea270396a2fa121960579` |
| `live_simple` | 258 | `1af2ac87dca47556db7b7e37e51e28b459a38b594e3c7b3c792b4903598ca0c4` |
| `live_multiple` | 1053 | `fd8ccfad4d911420d0e3341dbe2fff77d1d341da934248b9bb2bda24ab3a10c8` |
| `live_parallel` | 16 | `6c26e9fdc3350cf596e6d1ea9c179cbff834761bccf562f4141ed29a839ca421` |
| `live_parallel_multiple` | 24 | `21d4b9319c1faac431e22757b367ea28917fe467364c3a4b17f16ec06d4f6e79` |

Each question file has a possible-answer file with the same ids. Java, JavaScript,
irrelevance and relevance, multi-turn, agentic, and format-sensitivity categories are out
of scope.

## License and attribution

The gorilla repository, BFCL data included, is under the Apache License 2.0 (`LICENSE`
at the repository root; `license = { "text" = "Apache 2.0" }` in BFCL's `pyproject.toml`;
`license: apache-2.0` in the data README). There is no NOTICE file at the pinned commit.
`tests/fixtures/bfcl/` holds five records copied byte for byte from the pinned data
files together with upstream's `LICENSE`. Converted tasks are written under `runs/`,
which git ignores, so this repository redistributes no other BFCL data. No BFCL code is
copied: the grader driver (`src/graderproof/adapters/bfcl_driver.py`) is graderproof
code that imports BFCL's checker from the checkout at run time. The one BFCL string the
adapter reproduces is the Python hint appended to function descriptions (`PYTHON_HINT`,
from `_get_language_specific_hint` in `bfcl_eval/utils.py`).

## Commands

```
uv run python -m graderproof.adapters.bfcl fetch runs/bfcl/src
uv run python -m graderproof.adapters.bfcl convert runs/bfcl/src runs/bfcl/tasks
uv run python -m graderproof.adapters.bfcl check runs/bfcl/tasks \
    --root runs/bfcl/src/berkeley-function-call-leaderboard \
    --python /usr/bin/python3.12 --repeat 3 --cache runs/bfcl/cache
```

* `fetch DEST` makes a shallow, blobless, sparse checkout of the pinned commit (only
  `berkeley-function-call-leaderboard` and the top-level files, `LICENSE` among them),
  verifies `HEAD`, and prints the BFCL directory and the matching `GP_BFCL_ROOT=` line.
  It reuses an existing checkout in `DEST` and refuses a non-empty `DEST` that is not a
  git checkout. It runs no code from the repository.
* `convert SRC OUT [--categories a,b]` reads the JSON data of the gorilla checkout (or of
  its BFCL directory) and writes one task directory per entry, named by the BFCL id,
  directly under `OUT`. It refuses a checkout whose detached `HEAD` is not the pin, and an
  `OUT` that already holds task directories this conversion does not write, because the
  toybench loader would load them too.
* `check TASKS --root BFCL_DIR [--python PY] [--repeat N] [--cache DIR]` grades every
  unmodified reference `N` times through `graderproof.run.Runner.precheck` with
  `ToybenchAdapter(extra_env=...)` under bubblewrap, and prints, per category, how many
  references pass stably and every other task with its grader output. It exits 0 only if
  every reference passes on every run, and refuses to run without a write-isolating
  sandbox.

The Python functions are `fetch(dest)`, `verify_checkout(dest)`,
`convert(source_root, out_dir, categories=CATEGORIES)` (returns the task directories by
category), `check_references(tasks_dir, sandbox, env, repeat, cache_dir)`, and
`summarize(checks)`.

## Environment for graders

Graders read two variables, which `ToybenchAdapter(extra_env=...)` passes into the
sandbox (`graderproof audit --env KEY=VALUE`):

| Variable | Meaning |
|---|---|
| `GP_BFCL_ROOT` | the `berkeley-function-call-leaderboard` directory of the pinned checkout, for example `/home/user/graderproof/runs/bfcl/src/berkeley-function-call-leaderboard` |
| `GP_BFCL_PYTHON` | the interpreter that runs the checker; default `python3` from the sandbox `PATH`. Use a fixed interpreter outside the home directory, which bubblewrap hides, for example `/usr/bin/python3.12` |

No separate virtual environment is needed: the driver and the parts of BFCL it imports use
the standard library only (see Grading).

## Mapping

| BFCL field | toybench task |
|---|---|
| `id` | directory name and task id; `metadata.original_id` |
| `question` (turns of `{role, content}` messages) | `instruction.md`, verbatim |
| `function` (function documentation) | `instruction.md` with the Python hint; `grader/bfcl_task.json` verbatim |
| `ground_truth` of the possible answer | `grader/bfcl_task.json` verbatim; the source of `solution/trajectory.json` |
| category (file name) | `metadata.category` (the sampling stratum); the checker's `test_category` |

`task.toml` holds `id`, `benchmark = "bfcl"`, `kind = "data"`, `third_party = true`,
`timeout_s = 20`, `[solution] entry = "run_solution.sh"`, `[grader] entry = "grade.sh"`,
and `[metadata]` with `benchmark`, `category`, `original_id`, `source_repo`,
`source_commit`, `source_path`, `answer_path`, `record_sha256` (SHA-256 of the canonical
JSON of the question and possible-answer entries), `license = "Apache-2.0"`,
`reference_from_grader_data = true`, `reference_source = "possible_answer"`, and
`checker_model`. Because `third_party` is true, the Runner refuses any sandbox that does
not isolate writes.

The other files of a task are `support/run_solution.sh`, which copies
`solution/trajectory.json` to `.gp/trajectory.json` in the workspace (toybench records it
as the outcome's trajectory), and the grader: `grader/grade.sh`, `grader/bfcl_driver.py`
(a copy of the driver module), and `grader/bfcl_task.json`.

## Task text

`instruction.md` has a short opening line ("Answer the request below by calling one or
more of the functions documented after it."), then every message of the question in
order, under a heading with its role and inside a code fence longer than any run of
backticks in the message, then the function documentation as indented JSON, and finally
the answer format: a JSON list in `trajectory.json` with one
`{"tool": "<function name>", "args": {...}}` object per call.

The function documentation is what BFCL's inference loader gives a model for Python
categories: each description ends with " Note that the provided function is in Python 3
syntax." Handler-specific presentation is not reproduced (the system prompt of prompting
models, or the conversion of the documentation to a vendor tool schema).

## Reference solution

BFCL has no reference solution, so the reference is built from the possible answer, which
is grader data. Requirement extraction must therefore rely on the task text only (D19).
For every expected call `{name: {param: [acceptable values]}}` of `ground_truth`, in order,
the reference has one call `{"tool": name, "args": args}`, where for each parameter:

1. The parameter is omitted when it has no acceptable value, or when its acceptable
   values include `""` (BFCL's marker for "may be omitted") and the function
   documentation does not list it in `required`.
2. Otherwise its value is the first acceptable value other than `""`, or `""` itself when
   that is the only acceptable value.
3. For a parameter the documentation types as `dict`, or as an `array` or `tuple` of
   `dict` items, an acceptable value is a pattern that maps each key to its acceptable
   values (the form BFCL's `dict_checker` and `list_dict_checker` read). The reference
   value applies rule 2 to every key of the chosen pattern and omits the keys whose
   acceptable values include `""` or are empty.

Rule 1 keeps a documented `required` parameter even when its possible answer carries the
omission marker, because BFCL's checker rejects any call without a required parameter;
rule 2 skips the marker, because `""` is not a value of a non-string type. A literal reading
("omit every parameter whose acceptable values include `""`", "take the first listed
value") would make such references fail for reasons that are not grader weaknesses. The
recorded fixture `live_multiple_144-56-0` (`perPage`, required, acceptable values
`["", 100]`) shows both effects with the real checker.

## Grading

`grader/grade.sh` runs `"${GP_BFCL_PYTHON:-python3}" -I grader/bfcl_driver.py
grader/bfcl_task.json .gp/trajectory.json` in the workspace. The driver:

1. reads `bfcl_task.json` (id, category, `language = "python"`, model name, source
   commit, function documentation, ground truth);
2. checks that `GP_BFCL_ROOT` is set and, when its checkout has a detached `.git/HEAD`,
   that it is the commit the task was converted from;
3. imports `ast_checker` and `Language` from `GP_BFCL_ROOT` (see below) and checks that
   the module came from there;
4. decodes the calls `[{"tool", "args"}]` into BFCL's decoded format `[{name: args}]`: a
   missing or null `args` means no arguments, as in toybench trajectories, and other keys
   are ignored. A file that is missing or not JSON, or calls that are not a list of
   objects with a string `tool`, are invalid with BFCL's `ast_decoder:decoder_failed`;
   `args` that are not an object are invalid with `ast_decoder:decoder_wrong_output_format`,
   the condition of BFCL's `is_function_calling_format_output`;
5. calls `ast_checker(function, decoded, ground_truth, Language.PYTHON, category,
   model_name)`, the call BFCL's `_evaluate_single_ast_entry` makes after decoding.

It prints one JSON line `{"id", "valid", "error_type", "error"}` (the error list as JSON
text, cut to 2000 characters; `error_type` is null when valid) and exits 0 when valid,
1 when invalid, 2 on a setup error (task data, `GP_BFCL_ROOT`, commit mismatch, or the
import), and 3 when the checker raises. BFCL's evaluation does not catch exceptions from
`ast_checker`; graderproof counts any nonzero exit as a rejection.

The model name is `gorilla-openfunctions-v2` (`CHECKER_MODEL`), BFCL's own model. The
checker uses the model name only in `convert_func_name`, which replaces dots in expected
function names by underscores when the model's `underscore_to_dot` is true. It is false
for this model at the pinned commit, so names are compared as written in the
documentation, which is what a decoded solution in the task's terms contains.

`ast_checker.py` imports `bfcl_eval.constants.model_config` for that flag, and
`model_config.py` imports every model handler, which import the vendor SDKs (openai,
anthropic, google-genai, cohere, mistralai, boto3, qwen_agent, and others). The driver
runs BFCL's real `model_config.py` but installs an import hook that serves every module
under `bfcl_eval.model_handler` as a placeholder whose public attributes are empty
classes. `MODEL_CONFIG_MAPPING` is therefore built by BFCL's own code with its real flags,
no handler or SDK code is imported, and no other BFCL module is replaced. The remaining
imports (`ast_checker.py`, `constants/enums.py`, `constants/type_mappings.py`, and the
Java and JavaScript type converters) use the standard library only.

## Verification and contract tests

`check` is the reference check: it grades every converted reference in the sandbox and
lists every task whose grader does not pass it stably. At the pinned commit a small number
of references fail because their possible answers cannot be satisfied by any call: an
empty list of acceptable values for a required parameter, or a possible answer that
requires a parameter the documentation does not declare. graderproof's precheck reports
such tasks as rejecting the reference, and they are not scorable (D26). Task-level
findings stay in `private/` (non-negotiable 14).

`tests/contract/test_bfcl.py` runs offline. It converts the five fixture records
(`simple_python_94`, `parallel_29`, `parallel_multiple_26`, `live_simple_165-98-0`,
`live_multiple_144-56-0`), which cover the simple, multiple, and parallel checker paths,
a `dict` parameter, a list of `dict` items, dotted function names, optional parameters,
system messages, and non-ASCII text. `tests/fixtures/bfcl/verdicts.json` holds the
verdicts that BFCL's checker at the pin gave, under bubblewrap, on the references and on
hand-written changes to them. A stand-in `bfcl_eval` package written by the tests replays
those verdicts, so the scripts and the driver run end to end without third-party code.
Two live tests run only when `GP_BFCL_ROOT` is set. One checks that the fixture lines and
`LICENSE` appear verbatim in the checkout; the other, which also needs bubblewrap,
re-derives every recorded verdict with the real checker:

```
GP_BFCL_ROOT=$PWD/runs/bfcl/src/berkeley-function-call-leaderboard \
GP_BFCL_PYTHON=/usr/bin/python3.12 uv run pytest tests/contract/test_bfcl.py -k live
```

## Limitations

* Only the decoded-call interface is audited. BFCL decodes raw model output first (Python
  call syntax for prompting models, JSON argument strings for function-calling models),
  and weaknesses of those decoders are out of scope. JSON cannot express Python tuples;
  BFCL's checker turns tuples into lists anyway.
* The reference comes from grader data, so it is not independent evidence that a task is
  well posed, and graderproof's requirement extraction must not read the grader
  directory.
* Verdicts are those for a model whose function names keep their dots. For a model with
  `underscore_to_dot` true, BFCL compares against underscored names; that setting is not
  modeled.
* The placeholder hook relies on the checker not using handler classes, which holds at the
  pinned commit. A later BFCL version needs this checked again before the pin moves.
* toybench parses `.gp/trajectory.json` in the host process. A variant whose
  `trajectory.json` is not valid JSON would make that parse fail before the outcome is
  recorded; the built-in trajectory operators always write valid JSON.
* A checkout without `.git` (for example from a release archive) is not checked against
  the task's source commit by the driver.
