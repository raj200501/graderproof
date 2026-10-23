"""The one client wrapper for every model call (docs/BUILD_BRIEF.md section 8).

Requests are batched, content-addressed, and file-based (DECISIONS.md D17):

1. :meth:`ModelClient.batch` hashes ``(purpose, prompt_version, instructions, schema,
   items)``. If a response with that hash has been ingested, it is returned; a banked
   call is never re-run.
2. Otherwise, unless model calls are disabled (``GRADERPROOF_NO_MODEL_CALLS=1`` or
   ``GRADERPROOF_OFFLINE=1``), the request is written to ``<store>/requests/<hash>.json``
   and :class:`PendingResponseError` is raised.
3. A model backend (a Claude Code subagent, a local model runner, or headless Claude
   when its billing guard is clear) answers by writing
   ``<store>/responses/<hash>.json``.
4. :meth:`ModelClient.ingest` validates the response, enforces the daily caps from
   budget.toml (scaled by ``cap_share``), and appends a ledger line to
   ``artifacts/usage/ledger.jsonl``. Only then can :meth:`batch` return it.

``total_cost_usd`` reported by any backend is logged as ``plan_equivalent_usd``;
``cash_usd`` is always 0.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graderproof.core import canonical_json, sha256_text

KINDS = ("single_call", "agent_run", "review_run")
CAP_NAMES = {
    "single_call": "claude_single_calls_per_day",
    "agent_run": "claude_agent_runs_per_day",
    "review_run": "claude_review_runs_per_day",
}


class ModelCallBlockedError(RuntimeError):
    """A model call was needed while model calls are disabled."""


class PendingResponseError(RuntimeError):
    """A request was written and awaits a response from a model backend."""

    def __init__(self, request_hash: str, path: Path) -> None:
        super().__init__(f"model request {request_hash[:12]} pending at {path}")
        self.request_hash = request_hash
        self.path = path


class PendingWorkError(RuntimeError):
    """One or more requests across batches await responses."""

    def __init__(self, hashes: Sequence[str]) -> None:
        super().__init__(f"{len(hashes)} model requests pending")
        self.hashes = list(hashes)


class CapExceededError(RuntimeError):
    """Ingesting a response would exceed a daily cap."""


def utc_now() -> str:
    """Current UTC time, second precision, ``Z`` suffix."""
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def models_disabled(env: Mapping[str, str] | None = None) -> bool:
    """Whether the environment forbids model calls."""
    e = os.environ if env is None else env
    return e.get("GRADERPROOF_NO_MODEL_CALLS") == "1" or e.get("GRADERPROOF_OFFLINE") == "1"


def load_caps(budget_path: Path, env: Mapping[str, str] | None = None) -> dict[str, int]:
    """Effective daily caps: budget.toml values times the lower of cap_share and CAP_SHARE."""
    with budget_path.open("rb") as fh:
        caps = tomllib.load(fh)
    e = os.environ if env is None else env
    shares = [1.0]
    for raw in (caps.get("cap_share"), e.get("CAP_SHARE")):
        try:
            value = float(raw) if raw is not None else 1.0
        except (TypeError, ValueError):
            value = 1.0
        if 0.0 < value <= 1.0:
            shares.append(value)
    share = min(shares)
    return {kind: math.floor(int(caps[name]) * share) for kind, name in CAP_NAMES.items()}


@dataclass
class ModelClient:
    """File-based, content-addressed, capped model client."""

    store: Path
    ledger: Path
    budget: Path
    disabled: bool | None = None

    def __post_init__(self) -> None:
        if self.disabled is None:
            self.disabled = models_disabled()

    def request_hash(
        self,
        purpose: str,
        prompt_version: str,
        instructions: str,
        schema: Mapping[str, Any],
        items: Sequence[Mapping[str, Any]],
    ) -> str:
        """Content address of a request."""
        return sha256_text(
            canonical_json(
                {
                    "purpose": purpose,
                    "prompt_version": prompt_version,
                    "instructions": instructions,
                    "schema": dict(schema),
                    "items": [dict(i) for i in items],
                }
            )
        )

    def _ingested(self) -> set[str]:
        if not self.ledger.exists():
            return set()
        out = set()
        for line in self.ledger.read_text().splitlines():
            if line.strip():
                req = json.loads(line).get("request")
                if req:
                    out.add(str(req))
        return out

    def batch(
        self,
        purpose: str,
        prompt_version: str,
        instructions: str,
        schema: Mapping[str, Any],
        items: Sequence[Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Responses for ``items`` keyed by item ``id``; raises if not yet available."""
        h = self.request_hash(purpose, prompt_version, instructions, schema, items)
        response = self.store / "responses" / f"{h}.json"
        if response.exists() and h in self._ingested():
            data = json.loads(response.read_text())
            return {str(k): dict(v) for k, v in data["items"].items()}
        if self.disabled:
            raise ModelCallBlockedError(
                f"model call {purpose}/{h[:12]} needed but model calls are disabled"
            )
        request = self.store / "requests" / f"{h}.json"
        if not request.exists():
            request.parent.mkdir(parents=True, exist_ok=True)
            doc = {
                "schema": "graderproof.model_request/1",
                "hash": h,
                "purpose": purpose,
                "prompt_version": prompt_version,
                "instructions": instructions,
                "response_schema": dict(schema),
                "items": [dict(i) for i in items],
                "created_utc": utc_now(),
            }
            request.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        raise PendingResponseError(h, request)

    def item_key(
        self,
        purpose: str,
        prompt_version: str,
        instructions: str,
        schema: Mapping[str, Any],
        item: Mapping[str, Any],
    ) -> str:
        """Content address of one item under one prompt (independent of its batch)."""
        return sha256_text(
            canonical_json(
                {
                    "purpose": purpose,
                    "prompt_version": prompt_version,
                    "instructions": instructions,
                    "schema": dict(schema),
                    "item": dict(item),
                }
            )
        )

    def answered_items(self) -> dict[str, dict[str, Any]]:
        """Every ingested item response, keyed by :meth:`item_key`."""
        done = self._ingested()
        index: dict[str, dict[str, Any]] = {}
        for h in sorted(done):
            req_path = self.store / "requests" / f"{h}.json"
            resp_path = self.store / "responses" / f"{h}.json"
            if not req_path.exists() or not resp_path.exists():
                continue
            req = json.loads(req_path.read_text())
            resp = json.loads(resp_path.read_text())
            for item in req["items"]:
                key = self.item_key(
                    req["purpose"],
                    req["prompt_version"],
                    req["instructions"],
                    req.get("response_schema", {}),
                    item,
                )
                answer = resp["items"].get(str(item["id"]))
                if isinstance(answer, Mapping):
                    index[key] = dict(answer)
        return index

    def batch_items(
        self,
        purpose: str,
        prompt_version: str,
        instructions: str,
        schema: Mapping[str, Any],
        items: Sequence[Mapping[str, Any]],
        size: int,
    ) -> dict[str, dict[str, Any]]:
        """Responses for ``items``, reusing any item answered before in any batch.

        Unanswered items are batched (sorted by id, ``size`` per request); raises
        :class:`PendingWorkError` listing every new request when any is unanswered.
        """
        index = self.answered_items()
        out: dict[str, dict[str, Any]] = {}
        todo: list[Mapping[str, Any]] = []
        for item in items:
            key = self.item_key(purpose, prompt_version, instructions, schema, item)
            if key in index:
                out[str(item["id"])] = index[key]
            else:
                todo.append(item)
        pending: list[str] = []
        for chunk in chunks(todo, size):
            try:
                out.update(self.batch(purpose, prompt_version, instructions, schema, chunk))
            except PendingResponseError as exc:
                pending.append(exc.request_hash)
        if pending:
            raise PendingWorkError(pending)
        return out

    def pending(self) -> list[Path]:
        """Requests with no ingested response."""
        done = self._ingested()
        reqs = (
            sorted((self.store / "requests").glob("*.json"))
            if (self.store / "requests").exists()
            else []
        )
        return [r for r in reqs if r.stem not in done]

    def used_today(self, kind: str, today: str | None = None) -> int:
        """Ledger entries of ``kind`` dated today (UTC)."""
        day = today or utc_now()[:10]
        if not self.ledger.exists():
            return 0
        n = 0
        for line in self.ledger.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("kind") == kind and str(row.get("utc", ""))[:10] == day:
                    n += 1
        return n

    def ingest(self, request_hash: str, now: str | None = None) -> dict[str, Any]:
        """Validate a response, enforce the cap, and append its ledger line."""
        if request_hash in self._ingested():
            raise ValueError(f"{request_hash[:12]} already ingested")
        req_path = self.store / "requests" / f"{request_hash}.json"
        resp_path = self.store / "responses" / f"{request_hash}.json"
        request = json.loads(req_path.read_text())
        response = json.loads(resp_path.read_text())
        problems = validate_response(request, response)
        if problems:
            raise ValueError(f"response {request_hash[:12]} invalid: {problems[:3]}")
        stamp = now or utc_now()
        caps = load_caps(self.budget)
        if self.used_today("single_call", stamp[:10]) >= caps["single_call"]:
            raise CapExceededError(
                f"single_call cap {caps['single_call']} reached for {stamp[:10]}"
            )
        usage = response.get("usage") or {}
        row = {
            "utc": stamp,
            "kind": "single_call",
            "purpose": request["purpose"],
            "request": request_hash,
            "n_items": len(request["items"]),
            "backend": str(response.get("backend", "")),
            "model": str(response.get("model", "")),
            "tokens_in": usage.get("tokens_in"),
            "tokens_out": usage.get("tokens_out"),
            "wall_s": usage.get("wall_s"),
            "plan_equivalent_usd": usage.get("total_cost_usd"),
            "cash_usd": 0,
        }
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        return row


def validate_response(request: Mapping[str, Any], response: Mapping[str, Any]) -> list[str]:
    """Problems with a response relative to its request and response schema."""
    problems: list[str] = []
    if response.get("request") != request.get("hash"):
        problems.append("response.request does not match the request hash")
    if not response.get("backend") or not response.get("model"):
        problems.append("response must name its backend and model")
    items = response.get("items")
    if not isinstance(items, Mapping):
        return [*problems, "response.items must be an object keyed by item id"]
    ids = [str(i["id"]) for i in request["items"]]
    missing = [i for i in ids if i not in items]
    extra = [i for i in items if i not in ids]
    if missing:
        problems.append(f"missing items {missing[:3]}")
    if extra:
        problems.append(f"unexpected items {extra[:3]}")
    schema = request.get("response_schema", {})
    required = list(schema.get("required", []))
    enums: Mapping[str, Sequence[Any]] = schema.get("enums", {})
    for item_id in ids:
        value = items.get(item_id)
        if not isinstance(value, Mapping):
            continue
        for key in required:
            if key not in value:
                problems.append(f"item {item_id} lacks {key}")
        for key, allowed in enums.items():
            if key in value and value[key] not in allowed:
                problems.append(f"item {item_id} {key}={value[key]!r} not in {list(allowed)}")
    return problems


def chunks(items: Sequence[Mapping[str, Any]], size: int) -> list[list[Mapping[str, Any]]]:
    """Deterministic batches: items sorted by id, then cut into ``size`` pieces."""
    ordered = sorted(items, key=lambda i: str(i["id"]))
    return [list(ordered[i : i + size]) for i in range(0, len(ordered), size)]
