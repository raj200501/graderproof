"""Tests for variant generation (violating and preserving operators)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.core import VariantKind
from graderproof.sandbox import LocalSandbox
from graderproof.variants import Context, Generator, Operator, unified_diff
from graderproof.variants import preserving as pres
from graderproof.variants import pysource as ps
from graderproof.variants import violating as viol
from graderproof.variants.wrap import REWRITES, transform_source, wrap_entry

V, P = VariantKind.VIOLATING, VariantKind.PRESERVING

PY = '''"""Doc."""
import os


def f(xs, n):
    """Docstring."""
    total = 0
    for x in xs:
        if x > n and x != 3:
            total = total + x * 2
    return total  # result


def g():
    return None
'''
SH = """#!/usr/bin/env bash
set -euo pipefail
# comment
n=$(wc -l < data.txt)
echo "count" > out.txt
echo "$n" >> out.txt 2>&1
cat <<'EOF2'
inside heredoc 5
EOF2
if [ -f x ]; then
  echo 7
fi
"""
TRAJ = json.dumps(
    [
        {"tool": "get_order", "args": {"order_id": "A1"}},
        {"tool": "confirm_with_user", "args": {"message": "ok?"}},
        {"tool": "refund", "args": {"order_id": "A1", "amount": 5, "full": True}},
        {"tool": "send_receipt", "args": {"order_id": "A1"}},
        {"tool": "log_note", "args": {"text": "done"}},
    ]
)


def ctx(**kw: object) -> Context:
    base: dict[str, object] = {
        "languages": {"m.py": "python", "s.sh": "shell", "trajectory.json": "trajectory"}
    }
    base.update(kw)
    return Context(**base)  # type: ignore[arg-type]  # test helper passes heterogeneous overrides


def ops(fn: Operator, files: dict[str, str], c: Context | None = None) -> list[str]:
    return [p.operator for p in fn(files, c or ctx())]


def test_python_operators_produce_compiling_single_edits() -> None:
    files = {"m.py": PY}
    for op in viol.PYTHON_OPERATORS:
        props = list(op(files, ctx()))
        assert props, op.__name__
        for p in props:
            assert p.kind is VariantKind.VIOLATING
            assert ps.compiles(p.files["m.py"])
            assert p.files["m.py"] != PY
            assert "# result" in p.files["m.py"] or p.operator == "py-stmt-delete"
    deletes = list(viol.py_statement_delete(files, ctx()))
    assert not any('"""Docstring."""' not in p.files["m.py"] for p in deletes)
    names = {p.operator for p in viol.py_constant(files, ctx())}
    assert names == {"py-constant"}
    assert any(
        p.operator == "py-target-file"
        for p in viol.py_constant({"m.py": "open('out.txt')\n"}, ctx())
    )


def test_python_operators_skip_unparsable_and_other_languages() -> None:
    assert ops(viol.py_compare, {"m.py": "def (:\n"}) == []
    assert ops(viol.py_compare, {"s.sh": "x < y"}) == []


def test_shell_operators() -> None:
    files = {"s.sh": SH}
    lines = viol.shell_command_lines(SH)
    assert all("inside heredoc" not in SH.splitlines()[i] for i in lines)
    assert all(not SH.splitlines()[i].startswith(("#", "set ", "if", "fi")) for i in lines)
    assert "sh-line-delete" in ops(viol.sh_line_delete, files)
    consts = list(viol.sh_constant(files, ctx()))
    assert consts and all("2>&1" in p.files["s.sh"] for p in consts)
    targets = list(viol.sh_target_file(files, ctx()))
    assert any("out.txt.wrong" in p.files["s.sh"] for p in targets)
    assert not any("/dev/" in p.description for p in targets)
    partial = list(viol.sh_partial_output(files, ctx()))
    assert any("| head -n 1 >" in p.files["s.sh"] for p in partial)
    assert viol._retarget('"a b"') == '"a b.wrong"'
    assert viol.bash_parses("echo hi\n") and not viol.bash_parses("if then fi (\n")


def test_trajectory_operators() -> None:
    files = {"trajectory.json": TRAJ}
    drops = list(viol.traj_drop_call(files, ctx()))
    assert {p.operator for p in drops} == {"traj-drop-call", "traj-drop-confirmation"}
    reorder = list(viol.traj_reorder_dependent(files, ctx()))
    assert reorder and all(p.kind is VariantKind.VIOLATING for p in reorder)
    args = list(viol.traj_argument(files, ctx()))
    descs = " ".join(p.description for p in args)
    assert "5 -> 6" in descs and "True -> False" in descs and "'A1' -> 'A1-x'" in descs
    assert viol._changed([1]) is None and viol._changed(1.5) == 2.5
    assert list(viol.traj_drop_call({"trajectory.json": "not json"}, ctx())) == []
    swaps = list(pres.traj_swap_independent(files, ctx()))
    assert all(p.kind is VariantKind.PRESERVING for p in swaps)
    assert any("4" in p.description for p in swaps)
    extra = list(pres.traj_add_readonly(files, ctx()))
    assert extra and json.loads(extra[0].files["trajectory.json"])[0]["tool"] == "get_order"


def test_rename_locals_keeps_params_and_globals() -> None:
    props = list(pres.py_rename_locals({"m.py": PY}, ctx()))
    assert len(props) == 1
    new = props[0].files["m.py"]
    assert "total_gp" in new and "def f(xs, n)" in new and "x_gp" in new
    assert ps.compiles(new)
    assert (
        list(pres.py_rename_locals({"m.py": "def h():\n    a = 1\n    return eval('a')\n"}, ctx()))
        == []
    )
    nested = "def h():\n    a = 1\n    def k():\n        return a\n    return k()\n"
    assert list(pres.py_rename_locals({"m.py": nested}, ctx())) == []


def test_echo_printf() -> None:
    props = list(pres.sh_echo_printf({"s.sh": 'echo "hello there" > a.txt\necho $x\n'}, ctx()))
    assert len(props) == 1
    assert props[0].files["s.sh"].startswith("printf '%s\\n' \"hello there\" > a.txt")


def test_output_formats_plans() -> None:
    c = ctx(
        languages={"solve.sh": "shell"},
        entry="solve.sh",
        outputs=["a.txt", "b.json"],
        json_outputs=["b.json"],
        stdout_json=True,
        stdout_nonempty=True,
    )
    props = list(pres.output_formats({"solve.sh": "echo hi\n"}, c))
    names = {p.operator for p in props}
    assert names == {
        "out-trailing-newline",
        "out-trailing-spaces",
        "out-json-key-order",
        "out-json-indent",
        "out-json-float",
        "stdout-trailing-newline",
        "stdout-json-key-order",
        "stdout-code-fence",
    }
    for p in props:
        assert p.files["_gp_orig_solve.sh"] == "echo hi\n"
        assert viol.bash_parses(p.files["solve.sh"])
        assert ps.compiles(p.files["_gp_transform.py"])
    assert list(pres.output_formats({"solve.sh": "x"}, ctx(kind="module", entry="solve.sh"))) == []
    pyc = ctx(languages={"solve.py": "python"}, entry="solve.py", outputs=["a.txt"])
    pyprops = list(pres.output_formats({"solve.py": "print(1)\n"}, pyc))
    assert all(ps.compiles(p.files["solve.py"]) for p in pyprops)
    assert pres.json_like('{"a": 1}') and not pres.json_like("1") and not pres.json_like("{")


def run_wrapped(
    tmp_path: Path, op: str, outputs: list[str], solve: str, entry: str = "solve.sh"
) -> tuple[str, dict[str, str]]:
    task_dir = tmp_path / "bench" / "t"
    (task_dir / "solution").mkdir(parents=True)
    (task_dir / "grader").mkdir()
    (task_dir / "task.toml").write_text(
        f'id = "t"\nkind = "script"\n[solution]\nentry = "{entry}"\n[grader]\nentry = "grade.sh"\n'
    )
    (task_dir / "instruction.md").write_text("x")
    (task_dir / "solution" / entry).write_text(solve)
    (task_dir / "grader" / "grade.sh").write_text("exit 0\n")
    task = ToybenchAdapter().load(tmp_path / "bench")[0]
    files = wrap_entry(task.reference_solution, entry, op, outputs)
    ex = ToybenchAdapter().execute(task, files, LocalSandbox())
    return ex.outcome.stdout, dict(ex.outcome.files)


def test_wrapped_transforms_execute(tmp_path: Path) -> None:
    solve = (
        'printf \'{"a": 1, "b": [2]}\\n\' > d.json\n'
        'printf "x\\ny\\n" > t.txt\n'
        'echo \'{"k": 1, "z": 2}\'\n'
    )
    out, files = run_wrapped(tmp_path / "1", "out-json-key-order", ["d.json"], solve)
    assert list(json.loads(files["d.json"])) == ["b", "a"]
    out, files = run_wrapped(tmp_path / "2", "out-json-float", ["d.json"], solve)
    assert json.loads(files["d.json"])["a"] == 1.0 and "1.0" in files["d.json"]
    out, files = run_wrapped(tmp_path / "3", "out-trailing-newline", ["t.txt"], solve)
    assert files["t.txt"] == "x\ny"
    out, files = run_wrapped(tmp_path / "4", "out-trailing-spaces", ["t.txt"], solve)
    assert files["t.txt"] == "x  \ny  \n"
    out, _ = run_wrapped(tmp_path / "5", "stdout-code-fence", [], solve)
    assert out.startswith("```json\n") and out.endswith("```\n")
    out, _ = run_wrapped(tmp_path / "6", "stdout-json-key-order", [], solve)
    assert list(json.loads(out)) == ["z", "k"]
    out, _ = run_wrapped(tmp_path / "7", "stdout-trailing-newline", [], solve)
    assert not out.endswith("\n")
    out, files = run_wrapped(tmp_path / "8", "out-json-indent", ["d.json"], solve)
    assert '    "a"' in files["d.json"]
    out, _ = run_wrapped(
        tmp_path / "9", "stdout-code-fence", [], "print('{\"q\": 1}')\n", entry="solve.py"
    )
    assert out.startswith("```json")


def test_output_mutations_and_delay(tmp_path: Path) -> None:
    c = ctx(
        languages={"solve.sh": "shell"}, entry="solve.sh", outputs=["t.txt"], stdout_nonempty=True
    )
    names = [p.operator for p in viol.output_mutations({"solve.sh": "echo hi\n"}, c)]
    assert names == [
        "out-extra-line",
        "out-drop-last-line",
        "stdout-extra-line",
        "stdout-drop-last-line",
    ]
    assert all(p.kind is VariantKind.VIOLATING for p in viol.output_mutations({"solve.sh": "x"}, c))
    assert (
        list(viol.output_mutations({"solve.sh": "x"}, ctx(kind="module", entry="solve.sh"))) == []
    )
    assert pres.harmless_delay(2) == 0.0
    assert pres.harmless_delay(4) == 1.0
    assert pres.harmless_delay(60) == 3.0
    solve = 'printf "a\\nb\\n" > t.txt\necho one; echo two\n'
    out, files = run_wrapped(tmp_path / "x1", "out-extra-line", ["t.txt"], solve)
    assert files["t.txt"] == "a\nb\nextra\n"
    out, files = run_wrapped(tmp_path / "x2", "out-drop-last-line", ["t.txt"], solve)
    assert files["t.txt"] == "a\n"
    out, _ = run_wrapped(tmp_path / "x3", "stdout-extra-line", [], solve)
    assert out == "one\ntwo\nextra\n"
    out, _ = run_wrapped(tmp_path / "x4", "stdout-drop-last-line", [], solve)
    assert out == "one\n"
    dc = ctx(languages={"solve.sh": "shell"}, entry="solve.sh", timeout_s=4.0)
    delayed = [
        p for p in pres.output_formats({"solve.sh": "echo hi\n"}, dc) if p.operator == "pre-delay"
    ]
    assert len(delayed) == 1 and "sleep 1.0" in delayed[0].files["solve.sh"]
    consts = list(viol.py_constant({"m.py": "x = 'hello'\n"}, ctx()))
    assert {p.files["m.py"] for p in consts} == {"x = ''\n", "x = 'hellox'\n", "x = 'hell'\n"}


def test_generator_sampling_is_deterministic_and_bounded() -> None:
    files = {"m.py": PY, "s.sh": SH, "trajectory.json": TRAJ}
    gen = Generator(operators=[*viol.ALL, *pres.ALL], max_per_operator=2, max_total=10, seed=3)
    a = gen.variants("t", files, ctx())
    b = gen.variants("t", files, ctx())
    assert [v.id for v in a] == [v.id for v in b]
    assert len(a) == 10
    counts: dict[str, int] = {}
    for v in a:
        counts[v.operator] = counts.get(v.operator, 0) + 1
        assert v.diff
    assert max(counts.values()) <= 2
    assert gen.variants("other", files, ctx()) != a
    assert unified_diff({"a": "x\n"}, {"a": "y\n"}).startswith("--- a/a")


def test_sampling_keeps_a_share_for_preserving_variants() -> None:
    files = {"m.py": PY, "s.sh": SH, "trajectory.json": TRAJ}
    ops = [*viol.ALL, *pres.ALL]
    everything = Generator(operators=ops, max_per_operator=2, max_total=10_000, seed=3)
    available = [v for v in everything.variants("t", files, ctx()) if v.kind is P]
    viol_available = [v for v in everything.variants("t", files, ctx()) if v.kind is V]
    assert len(viol_available) > 9 and available
    small = Generator(operators=ops, max_per_operator=2, max_total=9, seed=3)
    picked = small.variants("t", files, ctx())
    assert len(picked) == 9
    assert sum(v.kind is P for v in picked) == min(len(available), 3)


def test_output_rewrites_never_name_their_operator() -> None:
    for op in REWRITES:
        if op == "none":
            continue
        source = transform_source(op, ["a.txt"])
        assert op not in source and "violat" not in source and "preserv" not in source
        compile(source, "transform.py", "exec")
        wrapped = wrap_entry({"s.sh": "echo hi > a.txt\n"}, "s.sh", op, ["a.txt"])
        assert all(op not in text for text in wrapped.values())
    with pytest.raises(ValueError):
        transform_source("no-such-rewrite", [])
