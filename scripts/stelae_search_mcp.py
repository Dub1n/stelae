#!/usr/bin/env python3
"""Minimal FastMCP server exposing canonical  tool."""

import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from mcp import types
from mcp.server import FastMCP

app = FastMCP(name="stelae-search")

ROOT = Path(os.getenv("STELAE_SEARCH_ROOT", ".")).resolve()
MAX_RESULTS = int(os.getenv("STELAE_SEARCH_MAX_RESULTS", "200"))
RG_BIN = os.getenv("STELAE_RG_BIN", "rg")


def _rg_available() -> bool:
    from shutil import which

    return which(RG_BIN) is not None


def _safe_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.name)


@app.tool(name="search", description="Search repository text/code within the allowed root.")
async def search(query: str, globs: Optional[List[str]] = None, max_results: int = 50) -> types.CallToolResult:
    max_results = max(1, min(max_results, MAX_RESULTS))
    globs = globs or []
    matches: List[dict] = []

    if _rg_available():
        cmd = [RG_BIN, "--vimgrep", "--no-ignore", "--hidden", "--max-count", "1", query, str(ROOT)]
        for g in globs:
            cmd.extend(["-g", g])
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        for line in result.stdout.splitlines():
            parts = line.split(":", 3)
            if len(parts) != 4:
                continue
            path_s, line_s, col_s, snippet = parts
            matches.append(
                {
                    "path": _safe_rel(Path(path_s)),
                    "line": int(line_s),
                    "col": int(col_s),
                    "text": snippet.strip(),
                }
            )
            if len(matches) >= max_results:
                break
    else:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        for root, _, files in os.walk(ROOT):
            for name in files:
                path = Path(root) / name
                if globs and not any(path.match(g) for g in globs):
                    continue
                try:
                    with path.open("r", errors="ignore") as fh:
                        for lineno, line in enumerate(fh, start=1):
                            match = pattern.search(line)
                            if match:
                                matches.append(
                                    {
                                        "path": _safe_rel(path),
                                        "line": lineno,
                                        "col": match.start() + 1,
                                        "text": line.strip(),
                                    }
                                )
                                break
                except Exception:
                    continue
                if len(matches) >= max_results:
                    break
            if len(matches) >= max_results:
                break

    structured = {"matches": matches, "count": len(matches)}
    summary_lines = [
        f"query: {query}",
        f"matches: {len(matches)}",
    ]
    if matches:
        preview = matches[: min(len(matches), 5)]
        rendered = "\n".join(
            f"- {item['path']}:{item['line']} — {item['text']}" for item in preview
        )
        summary_lines.append("sample:")
        summary_lines.append(rendered)
    summary = "\n".join(summary_lines)

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=summary)],
        structuredContent=structured,
    )


def run_server(transport: str = "stdio") -> None:
    app.run(transport)


if __name__ == "__main__":
    run_server()
