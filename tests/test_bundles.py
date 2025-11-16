from __future__ import annotations

from stelae_lib.bundles import _merge_named_entries


def test_merge_named_entries_prefers_additions() -> None:
    existing = [
        {"name": "scrapling_fetch_suite", "description": "old"},
        {"name": "custom_suite", "description": "custom"},
    ]
    additions = [
        {"name": "scrapling_fetch_suite", "description": "new"},
        {"name": "memory_suite", "description": "memory"},
    ]

    merged = _merge_named_entries(existing, additions, key_func=lambda entry: entry.get("name"))

    assert [entry["name"] for entry in merged] == [
        "scrapling_fetch_suite",
        "memory_suite",
        "custom_suite",
    ]
    assert merged[0]["description"] == "new"


def test_merge_named_entries_handles_hidden_tools() -> None:
    existing = [
        {"server": "docs", "tool": "fetch_document_links", "reason": "old"},
    ]
    additions = [
        {"server": "docs", "tool": "fetch_document_links", "reason": "new"},
        {"server": "mem", "tool": "legacy", "reason": "custom"},
    ]

    merged = _merge_named_entries(
        existing,
        additions,
        key_func=lambda entry: f"{entry.get('server')}::{entry.get('tool')}"
        if entry.get("server") and entry.get("tool")
        else None,
    )

    assert merged[0]["reason"] == "new"
    assert merged[1]["server"] == "mem"
