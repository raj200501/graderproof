"""Static grader smells ("grader lint", RQ6 and E6).

Each rule inspects the grader files and the task text of one task and reports a
smell with the lines that triggered it. Rules are heuristics meant for triage: a smell
is a reason to audit a grader first, never a finding by itself. The lint score is the
number of distinct smells.

Rules:

* ``existence-only``: an output file's existence is checked but its content is never
  read.
* ``exit-code-only``: a command's exit status is checked but its output never is.
* ``membership``: a key or substring is tested for presence (``"x" in y``,
  ``grep -q`` without ``-x``) instead of comparing the full value.
* ``loose-match``: prefix, suffix, case-insensitive, unanchored-pattern, partial-set,
  or tolerance comparisons.
* ``exact-text``: whole-text equality on raw output, or JSON parsing of raw output
  without stripping, which rejects harmless formatting differences.
* ``agent-writable-expected``: the grader compares against an expected-answer file that
  lives in the agent's workspace.
* ``outcome-only-process``: the task text requires a process (an order, a
  confirmation, a backup, a log, something not to touch) but the grader reads only
  final outputs or state.
* ``timing``: the grader's decision depends on wall-clock time.
* ``few-checks``: a function-level (module) grader compares fewer than five calls.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from graderproof.core import Task

PROCESS_RE = re.compile(
    r"\b(before|after|then|first|confirm\w*|backup|back up|log\w*|in order|order of|"
    r"do not (?:modify|change|touch|delete)|must not|never|without (?:changing|modifying))\b",
    re.I,
)
EXISTS_RE = re.compile(
    r"(?:\btest\s+-[efs]\s+|\[\s*-[efs]\s+|os\.path\.(?:exists|isfile)\(|\.(?:exists|is_file)\(\))"
)
READ_HINT_RE = re.compile(
    r"\b(cat|grep|diff|cmp|head|tail|wc|jq|read_text|read|open|json\.load|load|readlines|sort)\b"
)
MEMBERSHIP_RE = re.compile(r"[\"'][^\"']{1,60}[\"']\s+in\s+[\w.\[\]\"']+|\bgrep\s+-q\b(?!.*\s-x)")
LOOSE_RE = re.compile(
    r"(\.startswith\(|\.endswith\(|"
    r"\.lower\(\)|\.casefold\(\)|\bgrep\s+(?:-\w*i\w*\s+)|"
    r"\bissubset\(|\bany\(|abs\([^)]*\)\s*<|re\.search\()"
)
EXACT_RE = re.compile(
    r"(\[\s*\"\$\(cat [^)]*\)\"\s*=\s*|\[\s*\"\$actual\"\s*=\s*\"\$expected\"|"
    r"read_text\(\)\s*==|==\s*\w*\.read_text\(\)|json\.loads\((?:open|sys\.stdin|.*read\(\))|"
    r"\bcmp\b|\bdiff\b)"
)
TIMING_RE = re.compile(
    r"(time\.time\(\)|time\.monotonic\(\)|perf_counter\(\)|\bdate\s+\+%s|\$SECONDS|\btimeout\s+\d)"
)
EXIT_RE = re.compile(r"(\.returncode\b|\$\?|check=True|\bif\s+[^\n]*\bthen\b)")
OUTPUT_RE = re.compile(r"(\.stdout\b|capture_output|\$\(|GP_SOLUTION_STDOUT)")
EXPECTED_NAME_RE = re.compile(r"\b(expected|answer|golden|reference|solution)\w*\.\w+", re.I)
CALL_CHECK_RE = re.compile(r"\w+\([^()]*(?:\([^()]*\)[^()]*)*\)\s*(?:==|!=|is\b)")
FEW_CHECKS = 5


@dataclass(frozen=True)
class Smell:
    """One rule hit with the lines that triggered it."""

    rule: str
    detail: str
    lines: tuple[str, ...] = ()


@dataclass
class LintResult:
    """All smells for one task."""

    task_key: str
    smells: list[Smell] = field(default_factory=list)

    @property
    def score(self) -> int:
        """Number of distinct rules that fired."""
        return len({s.rule for s in self.smells})

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation."""
        return {
            "task": self.task_key,
            "score": self.score,
            "smells": [
                {"rule": s.rule, "detail": s.detail, "lines": list(s.lines)} for s in self.smells
            ],
        }


def _lines(files: Mapping[str, str], pattern: re.Pattern[str]) -> list[str]:
    out = []
    for path, text in sorted(files.items()):
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                out.append(f"{path}:{i}: {line.strip()[:120]}")
    return out


def _mentioned_outputs(files: Mapping[str, str]) -> set[str]:
    names: set[str] = set()
    for text in files.values():
        for m in EXISTS_RE.finditer(text):
            tail = text[m.end() : m.end() + 120]
            name = re.match(r"\s*[\"']?([\w./-]+\.\w+)", tail)
            if name:
                names.add(name.group(1))
            head = text[max(0, m.start() - 120) : m.start()]
            prior = re.findall(r"[\"']([\w./-]+\.\w+)[\"']", head)
            if prior:
                names.add(prior[-1])
    return names


def _code_files(task: Task) -> dict[str, str]:
    files = dict(task.environment.get("grader_files", {}))
    return {p: t for p, t in files.items() if p.endswith((".py", ".sh", ".bash"))} or files


def lint_task(task: Task) -> LintResult:
    """Run every rule on one task."""
    code = _code_files(task)
    all_text = "\n".join(code.values())
    result = LintResult(task.key)
    for name in sorted(_mentioned_outputs(code)):
        reads = [ln for ln in all_text.splitlines() if name in ln and not EXISTS_RE.search(ln)]
        if not reads:
            result.smells.append(
                Smell(
                    "existence-only",
                    f"{name} is checked for existence only",
                    tuple(_lines(code, re.compile(re.escape(name)))),
                )
            )
    if (
        EXIT_RE.search(all_text)
        and not OUTPUT_RE.search(all_text)
        and not READ_HINT_RE.search(all_text)
    ):
        result.smells.append(
            Smell("exit-code-only", "only exit statuses are checked", tuple(_lines(code, EXIT_RE)))
        )
    membership = _lines(code, MEMBERSHIP_RE)
    if membership:
        result.smells.append(
            Smell(
                "membership",
                "a key or substring is tested for presence, not compared in full",
                tuple(membership),
            )
        )
    loose = _lines(code, LOOSE_RE)
    if loose:
        result.smells.append(
            Smell(
                "loose-match", "substring, prefix, case-folded, or tolerant matching", tuple(loose)
            )
        )
    exact = _lines(code, EXACT_RE)
    if exact:
        result.smells.append(
            Smell("exact-text", "whole-text or raw-JSON comparison of output", tuple(exact))
        )
    workspace = set(task.environment.get("workspace_files", {}))
    writable = sorted(n for n in workspace if EXPECTED_NAME_RE.search(n) and n in all_text)
    if writable:
        result.smells.append(
            Smell(
                "agent-writable-expected",
                f"expected data read from the workspace: {writable}",
                tuple(_lines(code, re.compile("|".join(map(re.escape, writable))))),
            )
        )
    observes_process = re.search(
        r"\b(trajectory|log|logs|history|messages|calls|before|backup|bak|mtime|stat)\b",
        all_text,
        re.I,
    )
    if PROCESS_RE.search(task.instructions) and not observes_process:
        words = sorted({m.group(0).lower() for m in PROCESS_RE.finditer(task.instructions)})
        result.smells.append(
            Smell(
                "outcome-only-process",
                f"task text requires a process ({', '.join(words[:5])}) "
                "the grader does not observe",
            )
        )
    timing = _lines(code, TIMING_RE)
    if timing:
        result.smells.append(Smell("timing", "decision depends on wall-clock time", tuple(timing)))
    if task.environment.get("kind") == "module":
        checks = len(CALL_CHECK_RE.findall(all_text))
        if checks < FEW_CHECKS:
            result.smells.append(
                Smell("few-checks", f"{checks} function-call check(s) (fewer than {FEW_CHECKS})")
            )
    return result


def auc(scores: Sequence[float], positives: Sequence[bool]) -> float | None:
    """Mann-Whitney AUC: probability a positive outscores a negative (ties count half)."""
    pos = [s for s, p in zip(scores, positives, strict=True) if p]
    neg = [s for s, p in zip(scores, positives, strict=True) if not p]
    if not pos or not neg:
        return None
    wins = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    return wins / (len(pos) * len(neg))
