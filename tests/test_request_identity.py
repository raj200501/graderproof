"""Request identity: the model-request builders still rebuild the banked requests.

A banked answer is served only for an identical request: a request's content address
covers its purpose, prompt version, instructions, schema, and items, and an item's key
covers the same with the one item. So a change to what the builders put into items
must leave every item whose fields were within the old limits byte-identical
(DECISIONS.md D38). These tests rebuild the E0 requirement, propose, and review
requests from tracked inputs (toybench/tasks and artifacts/e0/evidence) and compare
them with the banked request files of artifacts/model_calls/e0 and
artifacts/model_calls/e4-toybench; check that no item banked in those stores or in
examples/demo/model_store was cut, and rebuild every banked review item there from its
own fields; and pin the request hashes of one-item requests whose fields sit exactly
at the old limits.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.core import Task, Variant, VariantKind
from graderproof.models import ModelClient, chunks
from graderproof.rootcause import CodingItem, ModelCoder
from graderproof.spec import Outcome, Requirement
from graderproof.validate import ModelReviewer, RequirementExtractor, _clip
from graderproof.variants.model import ModelProposer

ROOT = Path(__file__).resolve().parent.parent

#: One batch_items call: purpose, prompt version, instructions, schema, items, batch size.
Call = tuple[str, str, str, dict[str, Any], list[dict[str, Any]], int]


class RecordingClient(ModelClient):
    """Records what each builder passes to batch_items, and answers nothing.

    This captures each builder's real purpose, prompt version, instructions, and inline
    schema, not copies of them kept in the test.
    """

    def __init__(self) -> None:
        nowhere = Path("/nonexistent")
        super().__init__(nowhere, nowhere / "ledger.jsonl", nowhere / "budget.toml", disabled=True)
        self.calls: list[Call] = []

    def batch_items(
        self,
        purpose: str,
        prompt_version: str,
        instructions: str,
        schema: Mapping[str, Any],
        items: Sequence[Mapping[str, Any]],
        size: int,
    ) -> dict[str, dict[str, Any]]:
        self.calls.append(
            (purpose, prompt_version, instructions, dict(schema), [dict(i) for i in items], size)
        )
        return {}

    def only(self) -> Call:
        """The single call recorded so far."""
        assert len(self.calls) == 1
        return self.calls[0]

    def request_names(self, call: Call) -> set[str]:
        """Content addresses of the requests ``call`` would write (file names in a store)."""
        purpose, version, instructions, schema, items, size = call
        return {
            self.request_hash(purpose, version, instructions, schema, chunk)
            for chunk in chunks(items, size)
        }

    def item_keys(self, call: Call) -> set[str]:
        """Item keys of every item in ``call`` (what replay serves answers by)."""
        purpose, version, instructions, schema, items, _ = call
        return {self.item_key(purpose, version, instructions, schema, i) for i in items}


@dataclass(frozen=True)
class Store:
    """The banked requests of one model store, grouped by purpose."""

    names: Mapping[str, set[str]]
    keys: Mapping[str, set[str]]
    ids: Mapping[str, set[str]]


def load_store(path: Path) -> Store:
    """Request file names, item keys, and item ids of a store, by purpose.

    Each file name is checked against the content address of the file's own fields, so
    comparing rebuilt hashes with file names compares rebuilt requests with banked ones.
    """
    client = RecordingClient()
    names: dict[str, set[str]] = {}
    keys: dict[str, set[str]] = {}
    ids: dict[str, set[str]] = {}
    for f in sorted((path / "requests").glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        purpose, version, instructions = doc["purpose"], doc["prompt_version"], doc["instructions"]
        schema, items = doc.get("response_schema", {}), doc["items"]
        assert f.stem == doc["hash"]
        assert f.stem == client.request_hash(purpose, version, instructions, schema, items)
        names.setdefault(purpose, set()).add(f.stem)
        keys.setdefault(purpose, set()).update(
            client.item_key(purpose, version, instructions, schema, i) for i in items
        )
        ids.setdefault(purpose, set()).update(str(i["id"]) for i in items)
    return Store(names, keys, ids)


@dataclass(frozen=True)
class E0Inputs:
    """What the E0 builders were given, rebuilt from tracked task and evidence files."""

    references: list[tuple[Task, Outcome]]
    requirements: list[tuple[Task, Sequence[Requirement]]]
    variants: list[tuple[Task, Variant]]


@pytest.fixture(scope="module")
def e0() -> E0Inputs:
    tasks = {t.key_hash: t for t in ToybenchAdapter().load(ROOT / "toybench" / "tasks")}
    references: list[tuple[Task, Outcome]] = []
    requirements: list[tuple[Task, Sequence[Requirement]]] = []
    variants: list[tuple[Task, Variant]] = []
    for path in sorted((ROOT / "artifacts" / "e0" / "evidence").glob("*.json")):
        ev = json.loads(path.read_text(encoding="utf-8"))
        task = tasks[ev["task_hash"]]
        references.append((task, Outcome.from_dict(ev["reference_outcome"])))
        requirements.append((task, [Requirement.from_dict(r) for r in ev["requirements"]]))
        for v in ev["variants"]:
            # from_dict checks the stored id against the variant's content address
            fields = {k: v[k] for k in ("id", "task_id", "kind", "operator", "diff", "files")}
            variants.append((task, Variant.from_dict(fields)))
    assert references and variants
    return E0Inputs(references, requirements, variants)


@pytest.fixture(scope="module")
def e0_store() -> Store:
    return load_store(ROOT / "artifacts" / "model_calls" / "e0")


@pytest.fixture(scope="module")
def e4_store() -> Store:
    return load_store(ROOT / "artifacts" / "model_calls" / "e4-toybench")


def test_e0_requirement_requests_rebuild_byte_identical(
    e0: E0Inputs, e0_store: Store, e4_store: Store
) -> None:
    rec = RecordingClient()
    RequirementExtractor(rec, batch_size=8).extract(e0.references)  # E0 extracted 8 per request
    rebuilt = rec.request_names(rec.only())
    assert rebuilt == e0_store.names["requirements"]
    # E4 on toybench reused E0's requirement requests unchanged (DECISIONS.md D36)
    assert rebuilt == e4_store.names["requirements"]


def test_e0_and_e4_propose_requests_rebuild_byte_identical(
    e0: E0Inputs, e0_store: Store, e4_store: Store
) -> None:
    rec = RecordingClient()
    ModelProposer(rec, batch_size=6).propose(e0.requirements)
    assert rec.request_names(rec.only()) == e0_store.names["propose"]
    # E4's round-2 generalization batch asked again for the repaired tasks only
    rec2 = RecordingClient()
    ModelProposer(rec2, batch_size=6, round=2).propose(e0.requirements)
    purpose, version, instructions, schema, items, size = rec2.only()
    repaired = [i for i in items if i["id"] in e4_store.ids["propose"]]
    assert len(repaired) == len(e4_store.ids["propose"])
    call = (purpose, version, instructions, schema, repaired, size)
    assert rec2.request_names(call) == e4_store.names["propose"]


def test_e0_review_items_rebuild_byte_identical(e0: E0Inputs, e0_store: Store) -> None:
    rec = RecordingClient()
    ModelReviewer(rec).review(e0.variants)
    # Review ran in rounds, each batching only its new items, so compare item keys:
    # replay serves answers by item key whatever batch an item was asked in.
    assert rec.item_keys(rec.only()) == e0_store.keys["review"]


def test_e0_inputs_are_within_the_old_limits(e0: E0Inputs) -> None:
    """The premise of the identity tests: no E0 field reached a limit of the old code."""
    rec = RecordingClient()
    RequirementExtractor(rec).extract(e0.references)
    ModelReviewer(rec).review(e0.variants)
    extraction, review = rec.calls[0][4], rec.calls[1][4]
    # A cut string is longer than its limit (the marker follows the kept prefix), so
    # checking what the builders send catches any input over an old limit.
    for it in extraction:
        out = it["reference_outcome"]
        assert len(it["task_text"]) <= 8000 and len(out["stdout"]) <= 2000
        assert all(len(t) <= 4000 for t in it["reference_solution"].values())
        assert all(len(t) <= 1000 for t in it["initial_workspace"].values())
        assert all(len(t) <= 2000 for t in out["files"].values())
    # The trajectory is still cut to its first 50 calls without a marker, so what is
    # sent cannot show a cut: check the inputs.
    assert all(len(outcome.trajectory) <= 50 for _, outcome in e0.references)
    for it in review:
        assert len(it["task_text"]) <= 4000 and len(it["modified_diff"]) <= 4000
        files = [*it["reference_solution"].values(), *it["modified_files"].values()]
        assert all(len(t) <= 4000 for t in files)


#: The marker :func:`graderproof.validate._clip` appends to a string it cuts.
CUT = re.compile(r"\n\[\.\.\. \d+ more chars\]$")

#: The tracked model stores: E0, E4 on toybench, and the offline demo.
PUBLIC_STORES = {
    "e0": ROOT / "artifacts" / "model_calls" / "e0",
    "e4-toybench": ROOT / "artifacts" / "model_calls" / "e4-toybench",
    "demo": ROOT / "examples" / "demo" / "model_store",
}


def cut_fields(value: Any, path: str = "") -> list[str]:
    """Paths of the strings in ``value`` that end with the cut marker."""
    if isinstance(value, str):
        return [path] if CUT.search(value) else []
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in cut_fields(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [p for v in value for p in cut_fields(v, f"{path}[]")]
    return []


@pytest.mark.parametrize("store", sorted(PUBLIC_STORES))
def test_banked_items_carry_no_cut_and_review_items_rebuild(store: str) -> None:
    """No item banked in a tracked store was cut, and each review item rebuilds as banked.

    With no marker, every marked field of an item is its input whole, and no limit went
    down, so the builders send the item unchanged (the trajectory is still cut at 50 calls
    with no marker, as before). Review items are rebuilt from their own fields because
    E4's fresh variants are not tracked; that is the check of E4's review requests.
    """
    assert CUT.search(_clip("ab", 1))  # the scan looks for the marker _clip writes
    reviewer = ModelReviewer(RecordingClient())
    n_items = n_review = 0
    for f in sorted((PUBLIC_STORES[store] / "requests").glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        for item in doc["items"]:
            n_items += 1
            assert cut_fields(item) == [], f.name
            if doc["purpose"] != "review":
                continue
            reference = item["reference_solution"]
            task = Task("rebuilt", "identity", item["task_text"], {}, reference, ["grade"])
            files = {**reference, **item["modified_files"]}
            variant = Variant("rebuilt", VariantKind.VIOLATING, "op", item["modified_diff"], files)
            assert {**reviewer.item(task, variant), "id": item["id"]} == item, f.name
            n_review += 1
    assert n_items > n_review > 0


def exactly(n: int, tag: str) -> str:
    """Deterministic text of exactly ``n`` characters, including a non-ASCII letter."""
    line = f"{tag}: café order 42, step 7\n"
    return (line * (n // len(line) + 1))[:n]


def test_requests_at_the_old_limits_keep_their_hashes() -> None:
    """Fields exactly at the old limits were never cut, so these requests must not change.

    The pinned hashes were computed with the code before task text stopped being clipped
    (src/graderproof at commit a4c4c88).
    """
    task = Task(
        "boundary",
        "identity",
        exactly(8000, "task"),
        {"kind": "script", "workspace_files": {"in.txt": exactly(1000, "workspace")}},
        {"solve.sh": exactly(4000, "solution")},
        ["bash", "grade.sh"],
    )
    reference = Outcome(
        files={"out.json": exactly(2000, "outcome")},
        stdout=exactly(2000, "stdout"),
        trajectory=tuple({"tool": "lookup", "args": {"n": i}} for i in range(50)),
        state={"orders": {"42": "refunded"}},
    )
    review_task = replace(task, instructions=exactly(4000, "task"))
    variant = Variant(
        "boundary",
        VariantKind.VIOLATING,
        "op",
        exactly(4000, "diff"),
        {"solve.sh": exactly(4000, "variant")},
    )
    coder_task = replace(
        task,
        instructions=exactly(6000, "task"),
        environment={"kind": "script", "grader_files": {"grade.py": exactly(6000, "grader")}},
    )
    witness = {"broken": [{"requirement": "R1", "text": "print ok", "failed": ["no ok"]}]}
    coding = CodingItem("boundary-item", coder_task, "accept", "op", exactly(6000, "diff"), witness)
    rec = RecordingClient()
    RequirementExtractor(rec).extract([(task, reference)])
    ModelReviewer(rec).review([(review_task, variant)])
    ModelCoder(rec).code([coding])
    [extracted], [reviewed], [coded] = (call[4] for call in rec.calls)
    assert extracted["task_text"] == task.instructions
    assert extracted["reference_outcome"]["files"] == reference.files
    assert reviewed["task_text"] == review_task.instructions
    assert reviewed["modified_diff"] == variant.diff
    assert reviewed["modified_files"] == variant.files
    assert coded["task_text"] == coder_task.instructions
    assert coded["grader_files"] == coder_task.environment["grader_files"]
    assert coded["diff_from_reference"] == coding.diff
    pins = {call[0]: rec.request_names(call) for call in rec.calls}
    assert pins == {
        "requirements": {"be9d1785f5323566fe7e27c98f9a7f31c367797d34bb2025c9feb415c6f1a947"},
        "review": {"0d622a58cc9ffecf432236d3da545238d14385570d87fd40de600a600796ad42"},
        "rootcause": {"04f2cf471496c8d006059f90215129c888ee4ac825a14e3e1408c226f23ae4b8"},
    }


def test_no_request_purpose_cuts_the_task_text() -> None:
    """The task text reaches every model request whole, however long it is."""
    text = exactly(40_000, "policy")
    task = Task(
        "long",
        "identity",
        text,
        {"kind": "script", "grader_files": {"grade.sh": "exit 0\n"}},
        {"solve.sh": "echo ok\n"},
        ["bash", "grade.sh"],
    )
    variant = Variant("long", VariantKind.VIOLATING, "op", "diff", {"solve.sh": "echo no\n"})
    requirement = Requirement("R1", "print ok", ({"type": "stdout_contains", "text": "ok"},))
    rec = RecordingClient()
    RequirementExtractor(rec).extract([(task, Outcome(stdout="ok\n"))])
    ModelReviewer(rec).review([(task, variant)])
    ModelProposer(rec).propose([(task, [requirement])])
    ModelCoder(rec).code([CodingItem("c", task, "accept", "op", "diff", None)])
    sent = {call[0]: [i["task_text"] for i in call[4]] for call in rec.calls}
    assert sent == {p: [text] for p in ("requirements", "review", "propose", "rootcause")}
