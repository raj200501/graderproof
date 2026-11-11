"""Tests for tools/transcript_audit.py."""

from __future__ import annotations

import json
from pathlib import Path

import transcript_audit as ta


def transcript(tmp_path: Path, name: str, calls: list[tuple[str, dict[str, str]]]) -> Path:
    lines = [json.dumps({"message": {"content": "plain text"}}), "not json"]
    for tool, inp in calls:
        content = [{"type": "tool_use", "name": tool, "input": inp}, {"type": "text"}]
        lines.append(json.dumps({"message": {"content": content}}))
    path = tmp_path / f"{name}.jsonl"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_clean_and_dirty_transcripts(tmp_path: Path) -> None:
    repo = "/r"
    allow = ["/r/store/requests/a.json", "/r/store/responses/a.json"]
    clean = transcript(
        tmp_path,
        "clean",
        [
            ("Read", {"file_path": "/r/store/requests/a.json"}),
            ("Write", {"file_path": "/r/store/responses/a.json"}),
        ],
    )
    result = ta.audit(clean, repo, allow)
    assert result["clean"] and result["tool_calls"] == {"Read": 1, "Write": 1}
    dirty = transcript(
        tmp_path,
        "dirty",
        [
            ("Read", {"file_path": "/r/private/labels.json"}),
            ("Grep", {"pattern": "x"}),
            ("Glob", {"pattern": "*", "path": "/r/store/requests/a.json"}),
            ("Bash", {"command": "cat /r/private/labels.json /r/store/requests/a.json"}),
        ],
    )
    result = ta.audit(dirty, repo, allow)
    assert not result["clean"]
    assert set(result["outside_allowed"]) == {
        "Read /r/private/labels.json",
        "Grep <cwd>",
        "Bash /r/private/labels.json",
    }
    flags = [x for a in allow for x in ("--allow", a)]
    assert ta.main([str(clean), "--repo", repo, *flags]) == 0
    assert ta.main([str(dirty), "--repo", repo, "--allow", allow[0]]) == 1
