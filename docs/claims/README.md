# Claims, figures, and generated documents

Every result number in README.md, docs/REPORT.md, and docs/cards/*.md comes from a banked artifact under `artifacts/`, through a committed script (non-negotiable 1). This directory holds the declarations that make that checkable. Gates G10 (`make claimcheck`, `make freshness`) and G13 (`make citecheck`) depend on it.

| File | Written by | Purpose |
|---|---|---|
| `spec.json` | hand | which number comes from which artifact, which template renders which document, which figures exist; it contains no result numbers |
| `registry.json` | `make report` | every claim resolved from its artifact, with the artifact's SHA-256 |
| `allowlist.tsv` | hand | design parameters (thresholds, caps, targets) that may appear without a claim marker |
| `../templates/*.md.in` | hand | the documents, with placeholders instead of numbers |

## Workflow

1. Bank the result as JSON under `artifacts/` (with provenance).
2. Declare each number a document shows as a claim in `spec.json`, and each chart as a figure.
3. Write or edit the template under `docs/templates/`, using `{{claim:KEY}}` and `{{figure:NAME}}`. Never edit README.md or docs/REPORT.md directly once they have a template; `make report` overwrites them and `make freshness` fails if they differ from the rendering.
4. Run `make report`, then `make claimcheck freshness citecheck`.
5. Commit the artifact, `spec.json`, the template, and everything `make report` wrote, together.

`make reproduce` runs `make report` and then `make freshness`. It does not rerun experiments.

## spec.json

```json
{
  "claims": {
    "e1.bfcl.fa": {
      "artifact": "artifacts/audit/bfcl/summary.json",
      "path": "e1.false_accept_task_rate.point",
      "format": "{:.2f}",
      "note": "E1 false-accept task rate, BFCL, point estimate"
    },
    "e1.bfcl.fa_lo": {"artifact": "artifacts/audit/bfcl/summary.json", "path": "e1.false_accept_task_rate.ci.0", "format": "{:.2f}"},
    "e1.bfcl.fa_hi": {"artifact": "artifacts/audit/bfcl/summary.json", "path": "e1.false_accept_task_rate.ci.-1", "format": "{:.2f}"},
    "e1.bfcl.n": {"artifact": "artifacts/audit/bfcl/summary.json", "path": "n_sampled", "format": "{:d}"},
    "e1.bfcl.headline_variants": {"artifact": "artifacts/audit/bfcl/variants.jsonl", "path": "|count:counted_in_headline=true", "format": "{:d}"}
  },
  "templates": {
    "README.md.in": "README.md",
    "REPORT.md.in": "docs/REPORT.md",
    "cards/*.md.in": "docs/cards/*.md",
    "example.md.in": null
  },
  "figures": {
    "headline": {
      "title": "Share of tasks whose grader accepts a broken solution",
      "alt": "False-accept task rate per benchmark with intervals",
      "axis_label": "false-accept task rate",
      "domain": [0, 1],
      "tick_format": "{:.0%}",
      "bars": [{"label": "BFCL", "value": "e1.bfcl.fa", "lo": "e1.bfcl.fa_lo", "hi": "e1.bfcl.fa_hi"}]
    }
  }
}
```

A top-level `comment` string is allowed; any other unknown field is an error.

### Claims

A claim key is letters and digits joined by single `.`, `_`, or `-` (`e1.bfcl.fa_lo`). The artifact is a `.json` file under `artifacts/`, or a `.jsonl` file, which is read as the list of its records (one JSON value per non-blank line). `note` is optional.

The path selects one value in the artifact:

| Path | Selects |
|---|---|
| `a.b.c` | key `c` of object `b` of object `a` |
| `rows.0.rate`, `ci.-1` | an integer component indexes a list; a negative index counts from the end |
| (empty) | the whole document |
| `tasks\|len` | the length of a list or object |
| `variants\|count:kind=violating` | how many objects in the list have `kind` equal to `violating` |

The value after `=` is read as JSON when it parses (`true`, `null`, `3`, `"3"`), otherwise as a plain string. Booleans never equal numbers. Keys that contain `.` or `|` cannot be addressed.

`format` is a Python format string with exactly one replacement field: `{:.2f}`, `{:.1%}`, `{:d}`, `{:,}`, or `{}`. The value must be a JSON number (not a boolean), and the formatted text must be a single number token, so `0.42`, `12.3%`, `-0.05`, and `1,234` work and `0.42 points` does not.

### Templates

Each key is a path under `docs/templates/` ending in `.md.in`; each value is the output path, ending in `.md`. One `*` in the file name of both maps a family: `cards/*.md.in` renders `docs/cards/bfcl.md` from `docs/templates/cards/bfcl.md.in`. The value `null` marks an example that is never rendered. A template that matches no entry, or more than one, is an error. A mapped template that does not exist yet is fine: with no template at all, `make report` says so and succeeds.

`{{claim:KEY}}` becomes `VALUE<!--claim:KEY-->` (the marker is invisible on GitHub) and `{{figure:NAME}}` becomes `![ALT](PATH)` with the path relative to the output document. A placeholder for an undeclared claim or figure, or a near miss such as `{{ claim:x }}`, is an error. So is a placeholder that does not render as a number token, such as `x{{claim:a}}` or `1{{claim:a}}`: keep it apart from letters and digits before it. Other `{{...}}` text, such as GitHub Actions expressions, is left alone. The output ends with a comment naming its template.

### Figures

`title` and `bars` are required; `alt` (default: the title), `axis_label`, `domain` (`[low, high]`, which must include 0 because bars grow from zero), and `tick_format` (a format string for axis ticks) are optional. Each bar has a `label` and the claim key of its `value`, and optionally `lo` and `hi` (both or neither) for an interval. Every plotted number is a declared claim, and the title, alt text, axis label, and bar labels may contain no unbacked number (the same rules as documents, including the allowlist; each string is checked as the middle of a line, so `^` anchors in a context regex do not apply). tools/svgchart.py draws horizontal bars with interval whiskers in neutral grays on a transparent background, readable on light and dark pages, with a tooltip per bar, and its output depends only on its inputs.

## What `make report` writes

- `docs/claims/registry.json`: `{KEY: {"value", "artifact", "path", "artifact_sha256"}}`.
- `docs/figures/NAME.svg` for every figure.
- `artifacts/figures/manifest.json`: `[{"path", "sha256", "generator"}]`, written when a figure exists or the file already does. ship-check compares the README's headline figure with it.
- every mapped template that exists, rendered to its output path.

Nothing is written unless every claim resolves, every figure draws, and every template renders.

## `make claimcheck`

It reads README.md, docs/REPORT.md, docs/cards/*.md, and any other existing output path in `templates`. A missing README.md or docs/REPORT.md fails. Every number token (digits with an optional sign, decimals, thousands commas, exponent, or `%`) must be one of:

1. **A claim:** immediately followed by `<!--claim:KEY-->`, where the registry value of KEY equals the token text exactly. A marker that follows no number, names an unknown key, or disagrees with the registry fails.
2. **In an excluded context** (the context must contain the whole token, so the `14,000` in `line 14,000` is checked):
   - a URL, the destination of a Markdown link or image, a reference-style link label (`[text][3]`), a shortcut reference whose label is defined in the same file (`[3]` with a line `[3]: https://...`), the label and destination of a link reference definition, a footnote label (`[^1]`), or an HTML character reference (`&#160;`; one that renders a digit, such as `&#51;`, fails);
   - an inline code span, or a fenced code block whose info string is `bash`, `sh`, `shell`, `console`, `toml`, `json`, `yaml`, or `text` (other fences, such as `python` or `mermaid`, are checked; a fence inside a list item may be indented and leaves the list open, so the next item's number is still a list marker);
   - a hex string of 7 or more characters with at least one letter (commit ids, hashes);
   - an ISO date or date-time (`2026-11-04`, `2026-11`, `2026-11-04T01:58:11Z`) or a year from 1900 to 2099;
   - a version: `v1.0`, three or more dotted parts (`0.11.32`), or a number after Python, uv, ruff, mypy, pytest, Docker, bubblewrap, Linux, Git, Terminal-Bench, version, or release (`Python 3.11 and 3.12`, `Terminal-Bench 2.0`);
   - an identifier with letters attached before it: `G7`, `E0`, `RQ3`, `k3`, `x86_64`, `SHA-256`, `pass@1`;
   - an ordered-list marker (`1.` at the start of a list item; a wrapped paragraph line that starts with `12.` is checked);
   - a numbered heading (`## 3. Results`, `### 3.2 Setup`, `## 0. Launch`; not `## 3 tasks` or `## 0.31 of tasks`);
   - an arXiv id (`2606.08960`);
   - a reference: section, rule, step, gate, figure, table, line, item, appendix, chapter, equation, or `§` followed by a number; the plural forms take lists and ranges (`sections 6 to 10`, `rules 1 and 11`).
3. **Allowlisted:** `allowlist.tsv` has a row with the exact token text, a context regex, and a reason. A match of the regex on the same line must contain the token and reach beyond it: `95% CI` covers the `95%` in "(95% CI 0.10 to 0.45)" but not the one in "95% of tasks" on the same line, and a regex that matches only the number itself covers nothing.

A line that ends with `<!-- claimcheck:ignore-line REASON -->` is exempt from the number check; claim markers on it are still checked. The reason is required, and the comment must end the line. The output counts exempt lines per document.

A fenced code block that is never closed fails, because it would turn the rest of the file into code. Digits outside 0-9 (fullwidth digits, other scripts) and character references that render a digit fail on every line, exempt lines included, because they would show a number that the token rule cannot see.

Watch for these, which are checked on purpose: numbers in table cells, HTML attributes, ordinary HTML comments, and link titles (`[x](url "title 3")`); a number with letters after it (`3x`, `7B`, `2nd`); a number in italics (`_0.42_`); the text of a link (`[5](url)`), a shortcut reference with no definition (`[6]`), and a line that only looks like a definition (`[Note]: the rate is 0.31`); paths in prose or link text (put them in backticks). Spelled-out numbers ("three tasks") are not detected, so write result numbers as digits through claims. `python3 tools/claimcheck.py --verbose` prints how every token was classified.

The confidence level of an interval is a design parameter, and `allowlist.tsv` already covers `95% CI`. Note that ship-check's first-screen interval pattern (`[lo, hi]`) does not see through claim markers, so state the level as `95% CI` on the README's first screen.

Known limits, so review `--verbose` output rather than trusting a pass: a count from 1900 to 2099 reads as a year, a heading that starts with a dotted number (`## 2.5 ...`) reads as a numbered heading, a number after a reference word (`line 14`) reads as a reference, and spelled-out numbers are not seen. Write every result through a claim, whatever its form.

Output: `claimcheck: <file> OK (<n> claims, <m> allowlisted)` per document, or each problem with its line, then `claimcheck: FAIL` and exit status 1.

## `make freshness`

Without writing anything, it rebuilds what `make report` would write and fails when:

- a claim no longer re-derives (artifact missing, path gone, format no longer applies);
- `registry.json` is missing a declared claim, holds an undeclared one, or differs in value, artifact, or path, or an artifact's SHA-256 differs from `artifact_sha256` (the artifact changed after the registry was built, even if the value did not);
- a `<!--claim:KEY-->` in a document follows a number other than the value re-derived now, follows no number, or names an undeclared key;
- a document with a template is not that template's current rendering, a figure is not what the artifacts give now, or the manifest does not list exactly the current figures and hashes;
- README.md or docs/REPORT.md is missing.

Output: `freshness: <file> OK (<n> live claims)` per document, or the problems, then `freshness: FAIL` and exit status 1. A number typed into both `registry.json` and a document passes `make claimcheck` but not `make freshness`, which is why G10 needs both.

## `make citecheck`

Offline, it validates `artifacts/citecheck.json` against the schema in `.claude/agents/citation-checker.md` (status `verified`, `mismatch`, or `unreachable`; `retrieved_utc` as `YYYY-MM-DDTHH:MM:SSZ`; `content_sha256` as 64 lowercase hex digits, or null with notes saying why; a verified entry needs a page title and a final URL), then requires every external http(s) URL in README.md, docs/REPORT.md, and docs/cards/*.md to have a `verified` entry with a page title whose `claimed.url` or `final_url` matches, ignoring a trailing slash. URLs of this repository (`github.com/raj200501/graderproof`) are skipped. URLs are found the same way as in tools/ship_check.py, including inside code blocks.

Output: `citecheck: <n> references verified in README.md and docs/REPORT.md`, where n counts the distinct URLs of those two documents as ship-check does (preceded by a line for the cards when there are any), or each unverified reference with its location and status, then `citecheck: FAIL` and exit status 1.
