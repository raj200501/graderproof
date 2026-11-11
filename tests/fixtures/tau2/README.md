# tau2-bench recorded fixtures

Material from sierra-research/tau2-bench (https://github.com/sierra-research/tau2-bench)
at tag `v1.0.1`, commit `fc0055dc4e0a316c3f83133267fbd6faaa770992`, under the MIT License
(`src/LICENSE`, Copyright (c) 2025 Sierra Research). Copied from a shallow clone of that
tag on 2026-11-04. The contract tests in `tests/contract/test_tau2.py` use these files
offline.

## `src/`: a miniature checkout

| File | Source at the pinned commit | Integrity check in the tests |
|---|---|---|
| `LICENSE` | `LICENSE`, byte for byte | SHA-256 equals `DATA_SHA256["LICENSE"]` in the adapter |
| `data/tau2/domains/airline/policy.md` | same path, byte for byte | SHA-256 equals the adapter's pinned hash |
| `data/tau2/domains/retail/policy.md` | same path, byte for byte | SHA-256 equals the adapter's pinned hash |
| `data/tau2/domains/telecom/main_policy.md` | same path, byte for byte | SHA-256 equals the adapter's pinned hash |
| `data/tau2/domains/telecom/tech_support_manual.md` | same path, byte for byte | SHA-256 equals the adapter's pinned hash |
| `data/tau2/domains/airline/tasks.json` | task `7` of `tasks.json` | canonical-JSON SHA-256 of the record |
| `data/tau2/domains/retail/tasks.json` | tasks `69` and `24` of `tasks.json` | canonical-JSON SHA-256 of each record |
| `data/tau2/domains/telecom/tasks.json` | base task 21, `[mms_issue]bad_network_preference\|user_abroad_roaming_disabled_on[PERSONA:None]` | canonical-JSON SHA-256 of the record |
| `data/tau2/domains/*/split_tasks.json` | written here: `{"base": [...]}` with the ids above | none (not upstream data) |

The task records are upstream's JSON values, re-serialized with two-space indentation.
The canonical JSON of a record (sorted keys, no whitespace, UTF-8) hashes to the value
in `RECORD_SHA256` in the test module, which was computed from the pinned checkout.

The four tasks cover each domain: airline 7 has a `communicate_info` string and reads
before three writes (`[DB, COMMUNICATE]`); retail 69 has `NL_ASSERTION` in its reward
basis but no assertions, so it is gradable with no model; retail 24 has NL assertions
and must be left out by conversion; telecom base task 21 has one user-requested and one
assistant-requested call (`[ENV_ASSERTION]`).

## `recorded/`: live driver outputs

One file per converted fixture task (`airline-7.json`, `retail-69.json`,
`telecom-1b3ddc08.json`). Each holds the pinned commit, the SHA-256 of
`src/graderproof/adapters/tau2_driver.py` that produced it, and a list of runs. A run is
the solution files given to the task and the resulting `Execution` (workspace files,
trajectory, final state, and the grader's output and exit status) from
`graderproof.run.Runner` with `ToybenchAdapter` and `BwrapSandbox`, with the cross-check
against tau2's own `evaluate_simulation` turned on. The first run is the reference; for
airline 7 and the telecom task a second run drops one mutating call.

Re-record after any change to the driver (the offline tests refuse recordings made with
another driver):

    GP_TAU2_ROOT=/home/user/graderproof/runs/tau2/src \
    GP_TAU2_PYTHON=/home/user/graderproof/runs/tau2/venv/bin/python \
    GP_TAU2_RECORD=1 uv run --frozen pytest tests/contract/test_tau2.py -k live
