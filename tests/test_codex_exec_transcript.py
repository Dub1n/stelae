from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.smoke_harness import MCPToolCall, parse_codex_jsonl, summarize_tool_calls


def _tool_event(tool: str, operation: str, *, event_type: str, status: str | None = None) -> str:
    payload = {
        "type": event_type,
        "item": {
            "id": "call_1",
            "type": "mcp_tool_call",
            "tool": tool,
            "server": "stelae",
            "arguments": {"operation": operation},
        },
    }
    if status:
        payload["item"]["status"] = status
    return json.dumps(payload)


def test_parse_codex_jsonl_filters_blank_lines() -> None:
    lines = [
        _tool_event("workspace_fs_read", "read_file", event_type="item.started"),
        "",
        _tool_event("workspace_fs_read", "read_file", event_type="item.completed", status="completed"),
    ]
    events = parse_codex_jsonl("\n".join(lines))
    assert len(events) == 2


def test_summarize_tool_calls_returns_final_snapshot() -> None:
    events = [
        json.loads(_tool_event("manage_stelae", "install_server", event_type="item.started")),
        json.loads(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "call_1",
                        "type": "mcp_tool_call",
                        "tool": "manage_stelae",
                        "server": "stelae",
                        "status": "completed",
                        "arguments": {
                            "operation": "install_server",
                            "params": {"name": "qdrant", "target_name": "qdrant_smoke"},
                        },
                    },
                }
            )
        ),
    ]
    calls = summarize_tool_calls(events)
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call, MCPToolCall)
    assert call.status == "completed"
    assert call.tool == "manage_stelae"
    assert call.arguments["params"]["target_name"] == "qdrant_smoke"
