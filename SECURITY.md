# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub's private vulnerability reporting for this repository ("Security" tab, "Report a vulnerability"). Do not open a public issue. You will get an acknowledgement, and a fix or a written assessment, before anything is disclosed.

## Scope

graderproof runs third-party graders, task repositories, and benchmark scripts. It is designed to run them only inside a sandbox: Docker with `--network none` when available, otherwise an OS sandbox (bubblewrap, `sandbox-exec`, or a user and network namespace) with writes limited to a temporary workspace and credentials removed from the environment. Reports about sandbox escapes, credential exposure, or the tool running untrusted code outside its sandbox are in scope.

## Grader weaknesses found by graderproof

Task-level findings about third-party benchmarks that are not yet fixed upstream are kept out of this repository (they live in a git-ignored `private/` directory). Only aggregate statistics and hashes are published. Disclosure to benchmark maintainers is handled by the repository owner, never automatically.
