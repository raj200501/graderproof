"""Tests for tools/e3_rootcause.py (E3 root-cause coding)."""

from __future__ import annotations

import json
from pathlib import Path

import e3_rootcause as e3
import pytest

from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.models import ModelClient

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo"
BUDGET = (
    "cash_usd = 0\nclaude_agent_runs_per_day = 30\nclaude_agent_max_turns = 40\n"
    "claude_single_calls_per_day = 300\nclaude_review_runs_per_day = 6\n"
    "local_model_max_params_b = 8\ndisk_floor_gb = 8\n"
)


def test_e3_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tasks = ToybenchAdapter().load(DEMO)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    req = {"id": "R1", "text": "prints ok", "checks": [{"type": "stdout_contains", "text": "ok"}]}
    survivor = {
        "id": "vid1",
        "kind": "violating",
        "counted_in_headline": True,
        "grader_passed": True,
        "operator": "py-return-none",
        "diff": "-return x\n+return None\n",
        "witness": {"broken": [{"requirement": "R1"}]},
    }
    rejected = {**survivor, "id": "vid2", "kind": "preserving", "grader_passed": False}
    rejected["operator"], rejected["witness"] = "out-trailing-newline", {"held": ["R1"]}
    killed = {**survivor, "id": "vid3", "grader_passed": False}
    docs = {
        tasks[0].key_hash: {
            "determinism": "stable_pass",
            "requirements": [req],
            "variants": [survivor, rejected, killed],
        },
        tasks[1].key_hash: {"determinism": "flaky", "requirements": [], "variants": []},
    }
    for h, doc in docs.items():
        (evidence / f"{h}.json").write_text(json.dumps(doc))
    (tmp_path / "budget.toml").write_text(BUDGET)
    store, ledger = tmp_path / "store", tmp_path / "ledger.jsonl"
    args = ["--name", "demo", "--tasks", str(DEMO), "--evidence", str(evidence)]
    args += [
        "--store",
        str(store),
        "--ledger",
        str(ledger),
        "--budget",
        str(tmp_path / "budget.toml"),
    ]
    args += ["--out", str(tmp_path / "out"), "--private", str(tmp_path / "private")]
    assert e3.main(args) == e3.PENDING
    pending = [line.split()[1] for line in capsys.readouterr().out.splitlines()]
    assert len(pending) == 1
    request = json.loads(Path(pending[0]).read_text())
    ids = sorted(i["id"] for i in request["items"])
    assert ids == sorted(["vid1", "vid2", f"{tasks[1].key_hash}:reference"])
    answers = {i: {"code": "loose-matching", "reason": "r"} for i in ids}
    client = ModelClient(store, ledger, tmp_path / "budget.toml")
    (store / "responses").mkdir(parents=True, exist_ok=True)
    resp = {"request": request["hash"], "backend": "test", "model": "m", "items": answers}
    (store / "responses" / f"{request['hash']}.json").write_text(json.dumps(resp))
    client.ingest(request["hash"])
    assert e3.main(args) == 0
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    rows = [json.loads(x) for x in (tmp_path / "private" / "codes.jsonl").read_text().splitlines()]
    assert summary["n_items"] == 3 and len(rows) == 3
    assert summary["model_codes"] == {"loose-matching": 3}
    assert summary["by_direction"] == {"accept": 1, "reject": 2}
    assert summary["agreement"]["n"] == 3 and summary["models"] == ["test:m"]
    assert "vid1" not in (tmp_path / "out" / "summary.json").read_text()
