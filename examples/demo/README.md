# Demo tasks (toybench format)

Five small, project-written tasks used by `make demo` and the tests. They are not the E0 toybench study set: their grader weaknesses were written by hand to exercise the pipeline, and they are never pooled with E0 results.

| Task | Kind | Grader design |
|---|---|---|
| word-stats | script (Python) | checks only that the keys exist (presence instead of content) |
| classify | module (Python) | tests three inputs only (loose coverage) |
| status-json | script (shell) | compares printed JSON byte for byte (brittle parsing) |
| refund | trajectory (tool use) | checks the final state only, ignoring the required confirmation step |
| greeting | script (shell) | checks the exact required content; meant as the control with no weakness |

The greeting grader was written to have no weakness, but the demo flags a false reject on it: the grader counts lines with `wc -l`, so a `hello.txt` whose only line lacks a final newline is rejected although it satisfies the task text. That brittleness was not planted on purpose; graderproof found it, and it is kept as is because it shows the kind of defect the tool exists to catch.
