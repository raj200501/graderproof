"""Tests for graderproof.models (the client wrapper)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graderproof import models

BUDGET = """cash_usd = 0
claude_agent_runs_per_day = 30
claude_agent_max_turns = 40
claude_single_calls_per_day = 10
claude_review_runs_per_day = 6
local_model_max_params_b = 8
disk_floor_gb = 8
cap_share = 0.2
"""
SCHEMA = {"required": ["verdict"], "enums": {"verdict": ["a", "b"]}}


@pytest.fixture
def client(tmp_path: Path) -> models.ModelClient:
    (tmp_path / "budget.toml").write_text(BUDGET)
    return models.ModelClient(
        tmp_path / "store", tmp_path / "ledger.jsonl", tmp_path / "budget.toml", disabled=False
    )


def answer(client: models.ModelClient, h: str, items: dict[str, object], **extra: object) -> None:
    resp = {"request": h, "backend": "test", "model": "m", "items": items, **extra}
    path = client.store / "responses" / f"{h}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(resp))


def test_pending_then_ingest_then_served(client: models.ModelClient) -> None:
    items = [{"id": "x", "q": 1}, {"id": "y", "q": 2}]
    with pytest.raises(models.PendingResponseError) as exc:
        client.batch("p", "v1", "do it", SCHEMA, items)
    h = exc.value.request_hash
    assert exc.value.path.exists()
    assert client.pending() == [exc.value.path]
    answer(client, h, {"x": {"verdict": "a"}, "y": {"verdict": "b"}}, usage={"total_cost_usd": 0.5})
    with pytest.raises(models.PendingResponseError):
        client.batch("p", "v1", "do it", SCHEMA, items)  # not ingested yet
    row = client.ingest(h, now="2026-10-23T00:00:00Z")
    assert row["cash_usd"] == 0 and row["plan_equivalent_usd"] == 0.5 and row["n_items"] == 2
    assert client.batch("p", "v1", "do it", SCHEMA, items) == {
        "x": {"verdict": "a"},
        "y": {"verdict": "b"},
    }
    assert client.pending() == []
    with pytest.raises(ValueError, match="already ingested"):
        client.ingest(h)
    assert client.used_today("single_call", "2026-10-23") == 1
    assert client.used_today("single_call", "2026-10-24") == 0


def test_disabled_client_blocks(tmp_path: Path) -> None:
    c = models.ModelClient(tmp_path / "s", tmp_path / "l.jsonl", tmp_path / "b.toml", disabled=True)
    with pytest.raises(models.ModelCallBlockedError):
        c.batch("p", "v", "i", {}, [{"id": "a"}])
    assert c.pending() == []
    assert c.used_today("single_call") == 0


def test_invalid_response_rejected(client: models.ModelClient) -> None:
    with pytest.raises(models.PendingResponseError) as exc:
        client.batch("p", "v1", "i", SCHEMA, [{"id": "x"}])
    h = exc.value.request_hash
    answer(client, h, {"x": {"verdict": "zzz"}, "extra": {}})
    with pytest.raises(ValueError, match="invalid"):
        client.ingest(h)
    req = json.loads(exc.value.path.read_text())
    problems = models.validate_response(req, {"request": "other", "items": {}})
    text = " ".join(problems)
    assert "hash" in text and "backend" in text and "missing items" in text
    assert models.validate_response(req, {"request": h, "backend": "b", "model": "m", "items": []})
    assert "lacks verdict" in " ".join(
        models.validate_response(
            req, {"request": h, "backend": "b", "model": "m", "items": {"x": {}}}
        )
    )


def test_cap_enforced_with_cap_share(client: models.ModelClient) -> None:
    assert models.load_caps(client.budget, {})["single_call"] == 2
    assert models.load_caps(client.budget, {"CAP_SHARE": "0.1"})["single_call"] == 1
    assert models.load_caps(client.budget, {"CAP_SHARE": "bad"})["single_call"] == 2
    for i in range(3):
        with pytest.raises(models.PendingResponseError) as exc:
            client.batch("p", "v1", "i", SCHEMA, [{"id": f"x{i}"}])
        answer(client, exc.value.request_hash, {f"x{i}": {"verdict": "a"}})
        if i < 2:
            client.ingest(exc.value.request_hash, now="2026-10-23T01:00:00Z")
        else:
            with pytest.raises(models.CapExceededError):
                client.ingest(exc.value.request_hash, now="2026-10-23T02:00:00Z")


def test_helpers() -> None:
    assert models.models_disabled({"GRADERPROOF_OFFLINE": "1"})
    assert not models.models_disabled({})
    batches = models.chunks([{"id": "c"}, {"id": "a"}, {"id": "b"}], 2)
    assert [[i["id"] for i in b] for b in batches] == [["a", "b"], ["c"]]
    assert models.PendingWorkError(["a", "b"]).hashes == ["a", "b"]
    assert len(models.utc_now()) == 20


def test_batch_items_reuses_answers_across_batches(client: models.ModelClient) -> None:
    client.budget.write_text(BUDGET.replace("cap_share = 0.2", "cap_share = 1"))
    items = [{"id": "a"}, {"id": "b"}]
    with pytest.raises(models.PendingWorkError) as exc:
        client.batch_items("p", "v1", "i", SCHEMA, items, size=1)
    assert len(exc.value.hashes) == 2
    for h in exc.value.hashes:
        req = json.loads((client.store / "requests" / f"{h}.json").read_text())
        answer(client, h, {i["id"]: {"verdict": "a"} for i in req["items"]})
        client.ingest(h)
    more = [*items, {"id": "c"}]
    with pytest.raises(models.PendingWorkError) as exc2:
        client.batch_items("p", "v1", "i", SCHEMA, more, size=5)
    assert len(exc2.value.hashes) == 1
    req = json.loads((client.store / "requests" / f"{exc2.value.hashes[0]}.json").read_text())
    assert [i["id"] for i in req["items"]] == ["c"]
    answer(client, exc2.value.hashes[0], {"c": {"verdict": "b"}})
    client.ingest(exc2.value.hashes[0])
    out = client.batch_items("p", "v1", "i", SCHEMA, more, size=5)
    assert out == {"a": {"verdict": "a"}, "b": {"verdict": "a"}, "c": {"verdict": "b"}}
    (client.store / "responses" / f"{exc2.value.hashes[0]}.json").unlink()
    assert len(client.answered_items()) == 2
