"""Tests for graderproof.spec."""

from __future__ import annotations

from typing import Any

import pytest

from graderproof.spec import (
    Outcome,
    Requirement,
    evaluate,
    holds,
    json_pointer,
    load_requirements,
    normalize,
    parse_json,
    probe_key,
    probes_of,
)

OUT = Outcome(
    files={
        "a.txt": "hello world\n",
        "d.json": '{"x": {"y": [1, 2]}, "s": "ok"}',
        "n.txt": "a\n\nb\n",
    },
    stdout='```json\n{"status": "ok"}\n```\n',
    exit_status=0,
    trajectory=(
        {"tool": "get", "args": {"id": "A"}},
        {"tool": "confirm", "args": {}},
        {"tool": "refund", "args": {"id": "A", "amount": 4}},
    ),
    state={"orders": {"A": {"status": "refunded"}}},
    probes={},
)


def check(**c: Any) -> bool:
    return evaluate(c, OUT, OUT).passed


def test_file_checks() -> None:
    assert check(type="file_exists", path="a.txt")
    assert not check(type="file_exists", path="b.txt")
    assert check(type="file_absent", path="b.txt")
    assert not check(type="file_absent", path="a.txt")
    assert check(type="file_equals", path="a.txt", text="hello world", normalize="strip")
    assert not check(type="file_equals", path="a.txt", text="hello world")
    assert check(type="file_equals", path="a.txt", text="hello world  ", normalize="trailing_ws")
    assert check(type="file_contains", path="a.txt", text="world")
    assert not check(type="file_contains", path="a.txt", text="moon")
    assert check(type="file_regex", path="a.txt", pattern=r"^hello\b")
    assert not check(type="file_regex", path="a.txt", pattern=r"^world")
    assert check(type="file_lines", path="n.txt", count=2)
    assert not check(type="file_lines", path="missing", count=2)


def test_json_checks() -> None:
    assert check(type="file_json", path="d.json", pointer="/x/y/1", equals=2)
    assert not check(type="file_json", path="d.json", pointer="/x/z", equals=2)
    assert not check(type="file_json", path="a.txt", pointer="/x", equals=1)
    assert not check(type="stdout_json", pointer="/status", equals="ok")
    assert check(type="stdout_json", pointer="/status", equals="ok", lenient=True)
    assert json_pointer({"a/b": {"~": 1}}, "/a~1b/~0") == 1
    assert json_pointer([1, 2], "") == [1, 2]
    with pytest.raises(KeyError):
        json_pointer([1], "/5")
    with pytest.raises(KeyError):
        json_pointer(3, "/a")
    assert parse_json(' {"a": 1} ', lenient=False) == {"a": 1}


def test_stdout_and_exit_checks() -> None:
    assert check(type="stdout_contains", text="status")
    assert not check(type="stdout_contains", text="nope")
    assert check(type="stdout_regex", pattern=r"^```json$")
    assert not check(type="stdout_regex", pattern=r"^nope$")
    assert check(type="exit_code", code=0)
    timed = Outcome(exit_status=0, timed_out=True)
    assert not evaluate({"type": "exit_code", "code": 0}, timed).passed


def test_trajectory_and_state_checks() -> None:
    assert check(type="trajectory_includes", tool="refund", args={"amount": 4})
    assert not check(type="trajectory_includes", tool="refund", args={"amount": 5})
    assert check(type="trajectory_excludes", tool="delete")
    assert not check(type="trajectory_excludes", tool="confirm")
    assert check(type="trajectory_before", first={"tool": "confirm"}, then={"tool": "refund"})
    assert not check(type="trajectory_before", first={"tool": "refund"}, then={"tool": "confirm"})
    assert check(type="state_equals", pointer="/orders/A/status", equals="refunded")
    assert not check(type="state_equals", pointer="/orders/B", equals=1)


def test_call_and_differential_checks() -> None:
    probe = {"function": "f", "args": [2], "kwargs": {}}
    key = probe_key(probe)
    ref = Outcome(
        probes={key: {"ok": True, "value": 4}}, stdout="x", files={"o": "1"}, state={"a": 1}
    )
    good = Outcome(
        probes={key: {"ok": True, "value": 4}}, stdout="x\n", files={"o": "1"}, state={"a": 1}
    )
    bad = Outcome(probes={key: {"ok": False, "error": "boom"}}, stdout="y")
    c_eq = {"type": "call", "probe": probe, "equals": 4}
    c_ref = {"type": "call", "probe": probe, "matches_reference": True}
    assert evaluate(c_eq, good).passed
    assert not evaluate(c_eq, bad).passed
    assert evaluate(c_ref, good, ref).passed
    assert not evaluate(c_ref, bad, ref).passed
    assert not evaluate(c_ref, good, Outcome()).passed
    assert not evaluate(c_eq, Outcome()).passed
    with pytest.raises(ValueError):
        evaluate(c_ref, good, None)
    same = {"type": "same_as_reference", "target": "stdout", "normalize": "strip"}
    assert evaluate(same, good, ref).passed
    assert not evaluate(same, bad, ref).passed
    assert evaluate({"type": "same_as_reference", "target": "file:o"}, good, ref).passed
    assert evaluate({"type": "same_as_reference", "target": "state"}, good, ref).passed
    with pytest.raises(ValueError):
        evaluate({"type": "same_as_reference", "target": "nope"}, good, ref)
    with pytest.raises(ValueError):
        evaluate(same, good, None)
    with pytest.raises(ValueError):
        evaluate({"type": "unknown"}, good)


def test_requirement_round_trip_and_probes() -> None:
    probe = {"function": "f", "args": [1]}
    req = Requirement("R1", "f(1) works", ({"type": "call", "probe": probe, "equals": 2},), "test")
    again = Requirement.from_dict(req.to_dict())
    assert again == req
    assert probes_of([req, req]) == [probe]
    ok, results = holds(req, Outcome(probes={probe_key(probe): {"ok": True, "value": 2}}))
    assert ok and results[0].passed
    assert load_requirements({"requirements": [req.to_dict()]}) == [req]
    with pytest.raises(ValueError):
        Requirement("R2", "x", ())
    with pytest.raises(ValueError):
        Requirement("R3", "x", ({"type": "bogus"},))


def test_outcome_round_trip_and_normalize() -> None:
    assert Outcome.from_dict(OUT.to_dict()) == OUT
    assert Outcome.from_dict(Outcome().to_dict()).state is None
    assert normalize("a  \nb \n\n", "trailing_ws") == "a\nb"
    assert normalize(" a ", "none") == " a "
