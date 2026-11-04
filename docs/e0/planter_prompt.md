# E0 planting prompt

The toybench tasks used for E0 (`toybench/tasks/`) and their labels were written by a Claude Code general-purpose subagent of the build session, launched on 2026-11-04 with the prompt below, verbatim. A first launch with nearly the same prompt on 2026-10-23 was stopped by Raj before it wrote any file (DECISIONS.md D22); it differed only in wording: it did not list `.claude/` among the forbidden paths, gave the scratch directory as an example rather than a requirement, and did not ask for "three times" in the reply.

What the planter could see, as disclosed in prereg/0001 (review item N19):

- `CLAUDE.md`, whose mission paragraph says that graderproof generates spec-violating and spec-preserving variants of each task's reference solution and runs the grader on them. It names no operator.
- Sections 3 and 5 of docs/BUILD_BRIEF.md: the research questions (including the list of weakness types it was asked to plant) and the experiment plan.
- `src/graderproof/adapters/toybench.py`, for the task format and execution order.

It was told not to read the variant operators, the validators, the requirement checks, the tests, the examples, or any other file, and not to run graderproof on its tasks.

Audit (2026-11-04, `tools/transcript_audit.py` over both launches' transcripts, allowing the three files above, `toybench/`, `private/toybench/`, and the planter's scratch directory): neither launch read, searched, or wrote a file outside those paths. The only other repository paths in their shell commands were directory listings of `private/` (to create `private/toybench/`), and one `git status` call in the second launch listed the names of changed files in the working tree; no command printed the content of any other file, and no command ran graderproof. The transcripts are not committed because they contain the labels.

The prompt:

````text
You are building the planted-ground-truth benchmark for graderproof's tool-validity study (E0). graderproof is a tool that tries to find weaknesses in benchmark graders by running them on modified versions of each task's reference solution. Your job is to write the tasks and plant known grader weaknesses so the tool can later be scored against your labels. You must work independently of the tool. (An earlier attempt at this job was interrupted before it wrote anything; start from scratch.)

## What you may and may not read

- You may read ONLY: `/home/user/graderproof/CLAUDE.md`, `/home/user/graderproof/docs/BUILD_BRIEF.md` (sections 3 and 5), and `/home/user/graderproof/src/graderproof/adapters/toybench.py` (the task format; read its module docstring and `load_one` to get the format right).
- You must NOT read anything under `src/graderproof/variants/`, `src/graderproof/validate.py`, `src/graderproof/spec.py`, `tests/`, `examples/`, `docs/research/`, `artifacts/`, `.claude/`, or any other file of the repository. Do not run graderproof's audit, demo, or variant generation on your tasks. Do not look at how the tool works; your weaknesses must reflect how real benchmark graders fail, not what the tool is good at.

## What to build

Write task directories under `/home/user/graderproof/toybench/tasks/<task-id>/` in the toybench format (task.toml, instruction.md, solution/, grader/, optional workspace/ and support/). Use these kinds: `script` (bash and python3 solutions that write files or print output), `module` (a Python function the grader imports; set `[solution] module`), and `trajectory` (a `solution/trajectory.json` list of `{"tool", "args"}` calls executed against `support/env.py` with `initial_state()` and a `TOOLS` dict of `fn(state, **args)`; the grader reads `.gp/state.json` and `.gp/trajectory.json`). Graders exit 0 to accept. Graders and solutions use only bash, coreutils, and the Python standard library (`python3`). Every task's reference solution must satisfy its instructions completely and must pass its own grader. Set `timeout_s` in every task.toml to a value appropriate for the task.

Make 72 tasks in three slices, mixing kinds roughly evenly (at least 20 of each kind overall), with varied, realistic topics (file processing, text and number formatting, small algorithms, data conversion, configuration editing, customer-support and booking tool flows, and so on):

1. **planted (32 tasks), slice "in_list":** each grader has exactly one planted weakness of one of these types (about 5 or 6 tasks per type):
   - `presence-not-content`: checks that an output exists or has the right keys or shape but not its content.
   - `exit-code-only`: accepts based on exit status or "ran without error" without checking the result.
   - `loose-matching`: matching looser than the instructions demand (substring, prefix, case-insensitive, regex too permissive, numeric tolerance too wide, partial set).
   - `outcome-only-process`: the instructions require a process (a step, an ordering, a confirmation, a backup, a log entry, not touching something), but the grader checks only the end result.
   - `brittle-parsing`: rejects valid answers because it parses or compares too strictly (exact whitespace, trailing newline, key order, number formatting, code fences around JSON, case where the instructions do not fix it, ordering the instructions leave free). This is a false-reject weakness.
   - `timing`: a grader decision depends on timing in a way the instructions do not justify (for example a time limit far tighter than the task needs, rejecting a correct but slower approach, or a check that passes only because of when it runs). Decide whether it causes false accepts or false rejects and label the direction.
   Record each weakness's direction: `accept` (the grader passes some solutions that violate the instructions) or `reject` (it fails some solutions that satisfy them).
2. **clean (32 tasks), slice "clean":** graders that check exactly what the instructions require: correct content, required steps, and nothing stricter than the instructions (accept any formatting the instructions leave open). Make the clean tasks as varied and realistic as the planted ones; a clean grader may be simple when the task is simple.
3. **extra (8 tasks), slice "extra":** weaknesses of types NOT in the list above, of your own choosing (for example grading against a file the solution itself can overwrite, treating a parse failure as a pass, checking only the first of several records, an off-by-one in a range check). Label the type and direction.

The weakness must be realistic and must not be signposted: no comments in graders or instructions that reveal it, no file or task names that hint at it, and planted graders must look as careful as clean ones. Instructions must state the requirements clearly enough that a careful reader can decide whether a given solution satisfies them. Keep each task small (a solution under about 40 lines, a grader under about 60 lines).

Task ids: short, neutral, kebab-case names (no numbers that encode the slice; do not group planted tasks together alphabetically).

## Labels (keep them private)

Write the labels to `/home/user/graderproof/private/toybench/labels.json` (the `private/` directory is git-ignored; create the subdirectory) as:
```json
{"schema": "graderproof.toybench_labels/1", "created_utc": "...", "tasks": {"<task-id>": {"planted": true, "slice": "in_list", "weakness_type": "loose-matching", "direction": "accept", "description": "one or two sentences: what the grader gets wrong and an example solution it misjudges"}, "<clean-id>": {"planted": false, "slice": "clean", "weakness_type": null, "direction": null, "description": "what the grader checks"}}}
```
Extra-slice tasks have `"planted": true, "slice": "extra"`. Every task directory must have exactly one label entry. Do not write labels, weakness types, or hints anywhere else (not in task files, not in commit messages, not in your final reply).

## Check your work

For every task: run the reference solution and its grader in a fresh temporary copy of the task (outside the repository, under /tmp/claude-0/-home-user-graderproof/1479d52b-6d58-5157-ac90-6d4b8d976454/scratchpad/e0check/) following the toybench execution order (copy workspace/, run the solution with cwd = workspace, then run the grader with cwd = workspace and `GP_SOLUTION_STDOUT` pointing to a file with the solution's stdout; for trajectory tasks, execute the calls yourself with a small script that loads support/env.py, then write `.gp/state.json` and `.gp/trajectory.json`). Run each reference three times; it must pass every time. For each planted task, also construct at least one concrete solution that demonstrates the weakness (a violating solution the grader wrongly accepts, or a valid solution it wrongly rejects) and confirm the grader misjudges it; for each clean task, confirm that one violating solution is rejected. Keep these demonstration solutions only in your scratch directory, never in the repository. No em dashes anywhere. Do not commit anything; do not modify any other file.

Reply only with: the number of tasks per kind and per slice (no ids, no weakness details), confirmation that every reference passes three times and every planted weakness was demonstrated, and the path of the labels file.
````
