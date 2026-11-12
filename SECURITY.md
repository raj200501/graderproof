# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub's private vulnerability reporting for this repository ("Security" tab, "Report a vulnerability"). Do not open a public issue. You will get an acknowledgement, and a fix or a written assessment, before anything is disclosed.

## Scope

graderproof runs third-party graders, task repositories, and benchmark scripts. It is designed to run them only inside a sandbox: Docker with `--network none` when available, otherwise an OS sandbox (bubblewrap, `sandbox-exec`, or a user and network namespace) with writes limited to a temporary workspace and credentials removed from the environment. Reports about sandbox escapes, credential exposure, or the tool running untrusted code outside its sandbox are in scope.

## Grader weaknesses found by graderproof

Task-level evidence about third-party benchmarks that are not yet fixed upstream (the variants, their witnesses, the grader output, and the model calls) is kept out of this repository; it lives in a git-ignored `private/` directory. What is published is aggregate statistics and one row per audited task, with counts and flags. Variant rows carry keyed ids and no operator names (`tools/publish_rows.py`), and an earlier version of the HumanEval rows, still in the history, used plain content hashes (DECISIONS.md D43 and D44). Disclosure to benchmark maintainers is handled by the repository owner, never automatically.
