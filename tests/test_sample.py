"""Tests for tools/sample.py (stratified sampling for E1/E2)."""

from __future__ import annotations

import json
from pathlib import Path

import sample


def make_bench(root: Path, strata: dict[str, int]) -> None:
    for s, k in strata.items():
        for i in range(k):
            d = root / f"{s}-{i}"
            d.mkdir(parents=True)
            (d / "task.toml").write_text(
                f'id = "{s}-{i}"\nkind = "data"\n[metadata]\ndomain = "{s}"\n'
            )


def test_quotas_largest_remainder() -> None:
    assert sample.quotas({"a": 50, "b": 114, "c": 74}, 40) == {"a": 8, "b": 19, "c": 13}
    assert sum(sample.quotas({"a": 1, "b": 1, "c": 1}, 2).values()) == 2
    assert sample.quotas({"a": 3}, 10) == {"a": 3}


def test_sample_is_deterministic_and_stratified(tmp_path: Path) -> None:
    make_bench(tmp_path / "b", {"air": 50, "tel": 114, "ret": 74})
    strata = sample.task_strata(tmp_path / "b")
    first = sample.stratified_sample(strata, 40, "tau2:2027")
    assert first == sample.stratified_sample(strata, 40, "tau2:2027")
    assert first != sample.stratified_sample(strata, 40, "tau2:2028")
    assert len(first) == 40 and len(set(first)) == 40
    assert sum(1 for t in first if t.startswith("tel")) == 19


def test_main_writes_sample_and_links(tmp_path: Path) -> None:
    make_bench(tmp_path / "b", {"x": 5, "y": 5})
    (tmp_path / "plain").mkdir()
    (tmp_path / "plain" / "t1").mkdir()
    (tmp_path / "plain" / "t1" / "task.toml").write_text('id = "t1"\n')
    excl = tmp_path / "excl.txt"
    excl.write_text("bench:x-0\n")
    out = tmp_path / "s.json"
    argv = ["--bench", f"bench={tmp_path / 'b'}", "--bench", f"plain={tmp_path / 'plain'}"]
    argv += ["--n", "4", "--seed", "1", "--exclude", str(excl), "--out", str(out)]
    argv += ["--materialize", str(tmp_path / "e1")]
    assert sample.main(argv) == 0
    data = json.loads(out.read_text())
    b = data["benchmarks"]["bench"]
    assert b["frame"] == 9 and b["excluded"] == ["x-0"] and len(b["tasks"]) == 4
    assert "x-0" not in b["tasks"]
    assert data["benchmarks"]["plain"]["strata"] == {"all": {"frame": 1, "sampled": 1}}
    links = sorted(p.name for p in (tmp_path / "e1" / "bench").iterdir())
    assert links == sorted(b["tasks"])
    assert sample.main(argv) == 0  # existing links are kept
