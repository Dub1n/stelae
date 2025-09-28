#!/usr/bin/env python3
"""Run the connector probe, validate outputs, and persist the log."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _extract_tool_names(tools: Iterable[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    for tool in tools:
        name = tool.get("name")
        if isinstance(name, str):
            names.append(name)
    return sorted(names)


def _extract_tool_entries(payload: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    if not payload:
        return []
    entries = payload.get("tools", [])
    return [entry for entry in entries if isinstance(entry, dict)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate connector probe output")
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--probe",
        default=Path(__file__).with_name("chatgpt_connector_probe.py"),
        help="Path to chatgpt_connector_probe.py",
    )
    parser.add_argument(
        "--log-dir",
        default=Path(__file__).resolve().parent.parent / "logs",
        help="Directory where probe logs should be stored",
    )
    args = parser.parse_args()

    probe_path = Path(args.probe).resolve()
    sys.path.insert(0, str(probe_path.parent.parent.parent))
    from dev.debug.chatgpt_connector_probe import run_probe  # type: ignore

    log_dir = Path(args.log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%dT%H%M", time.gmtime())
    log_path = log_dir / f"probe-{timestamp}.log"

    lines: List[str] = []

    def sink(message: str) -> None:
        lines.append(message)

    result = asyncio.run(run_probe(args.server_url, args.timeout, output=sink))
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    init_payload = (result["initialize"]["result"].payload or {}).get("result", {})
    init_tools = _extract_tool_entries(init_payload)
    init_names = _extract_tool_names(init_tools)
    if init_names != ["fetch", "search"]:
        raise SystemExit(
            "Initialize catalog must contain exactly ['fetch', 'search']: "
            + json.dumps(init_tools, indent=2)
        )

    list_payload = (result["tools_list"]["result"].payload or {}).get("result", {})
    list_tools = _extract_tool_entries(list_payload)
    list_names = _extract_tool_names(list_tools)
    if list_names != ["fetch", "search"]:
        raise SystemExit(
            "tools/list catalog must contain exactly ['fetch', 'search']: "
            + json.dumps(list_tools, indent=2)
        )

    search_payload = (result["search"]["result"].payload or {}).get("result", {})
    hits = [hit for hit in search_payload.get("results", []) if isinstance(hit, dict)]
    if not hits:
        raise SystemExit("Search returned no results")
    missing_snippet = [hit for hit in hits if not hit.get("metadata", {}).get("snippet")]
    if missing_snippet:
        raise SystemExit(
            "Search results missing snippet metadata: " + json.dumps(missing_snippet, indent=2)
        )

    print(f"Connector probe succeeded. Log saved to {log_path}")


if __name__ == "__main__":
    main()
