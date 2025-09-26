#!/usr/bin/env python3
"""Minimal FastMCP server exposing canonical  tool."""

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from mcp import types
from mcp.server import FastMCP



def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _configure_logger(debug_enabled: bool) -> logging.Logger:
    logger = logging.getLogger("stelae.search")
    logger.propagate = True

    for handler in list(logger.handlers):
        if getattr(handler, "_stelae_debug", False):
            logger.removeHandler(handler)

    if debug_enabled:
        for handler in list(logger.handlers):
            if isinstance(handler, logging.NullHandler):
                logger.removeHandler(handler)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[stelae-search] %(message)s"))
        handler._stelae_debug = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    else:
        if not any(isinstance(handler, logging.NullHandler) for handler in logger.handlers):
            logger.addHandler(logging.NullHandler())
        if logger.level == logging.NOTSET or logger.level < logging.INFO:
            logger.setLevel(logging.INFO)
    return logger

app = FastMCP(name="stelae-search")

DEBUG_ENABLED = _is_truthy(os.getenv("STELAE_SEARCH_DEBUG", ""))
LOGGER = _configure_logger(DEBUG_ENABLED)

ROOT = Path(os.getenv("STELAE_SEARCH_ROOT", ".")).resolve()
MAX_RESULTS = int(os.getenv("STELAE_SEARCH_MAX_RESULTS", "200"))
RG_BIN = os.getenv("STELAE_RG_BIN", "rg")
FETCH_MAX_BYTES = int(os.getenv("STELAE_FETCH_MAX_BYTES", "1048576"))



def _resolve_repo_path(rel_path: str) -> Path:
    candidate = (ROOT / rel_path).resolve() if not Path(rel_path).is_absolute() else Path(rel_path).resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError as exc:
        raise FileNotFoundError(rel_path) from exc
    return candidate


def _rg_available() -> bool:
    from shutil import which

    return which(RG_BIN) is not None


def _safe_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.name)


@app.tool(name="search", description="Deprecated; do not use this; call the mcp-grep search tool instead.")
async def search(query: str, globs: Optional[List[str]] = None, max_results: int = 50) -> types.CallToolResult:
    max_results = max(1, min(max_results, MAX_RESULTS))
    globs = globs or []
    matches: List[dict] = []
    truncated = False

    LOGGER.debug(
        "search start query=%r globs=%s max_results=%d root=%s",
        query,
        globs,
        max_results,
        ROOT,
    )
    search_start = time.perf_counter()

    use_rg = _rg_available()
    LOGGER.debug("ripgrep available=%s bin=%s", use_rg, RG_BIN)

    if use_rg:
        cmd = [RG_BIN, "--vimgrep", "--no-ignore", "--hidden", "--max-count", "1", query, str(ROOT)]
        for pattern in globs:
            cmd.extend(["-g", pattern])
        LOGGER.debug("executing ripgrep command=%s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.stderr:
            LOGGER.debug("ripgrep stderr=%s", result.stderr.strip())
        LOGGER.debug("ripgrep returncode=%s", result.returncode)
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
                truncated = True
                LOGGER.debug("max_results reached via ripgrep; stopping collection")
                break
    else:
        LOGGER.debug("ripgrep not available; using Python fallback")
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        for root, _, files in os.walk(ROOT):
            for name in files:
                path = Path(root) / name
                if globs and not any(path.match(g) for g in globs):
                    continue
                try:
                    with path.open("r", errors="ignore") as fh:
                        for lineno, line_text in enumerate(fh, start=1):
                            match = pattern.search(line_text)
                            if match:
                                matches.append(
                                    {
                                        "path": _safe_rel(path),
                                        "line": lineno,
                                        "col": match.start() + 1,
                                        "text": line_text.strip(),
                                    }
                                )
                                break
                except Exception as exc:  # pragma: no cover - defensive logging
                    LOGGER.debug("skipping file=%s error=%s", path, exc)
                    continue
                if len(matches) >= max_results:
                    truncated = True
                    LOGGER.debug("max_results reached via fallback; stopping collection")
                    break
            if truncated:
                break

    duration_ms = (time.perf_counter() - search_start) * 1000
    LOGGER.debug(
        "search completed matches=%d truncated=%s duration_ms=%.2f",
        len(matches),
        truncated,
        duration_ms,
    )

    structured = None
    results = []
    for match in matches:
        rel_path = match.get("path") or ""
        if not isinstance(rel_path, str) or not rel_path:
            continue
        line_no = match.get("line") or 1
        entry = {"id": f"repo:{rel_path}#L{line_no}", "title": rel_path, "url": f"stelae://repo/{rel_path}#L{line_no}"}
        snippet = match.get("text")
        if snippet:
            entry["metadata"] = {"snippet": snippet}
        results.append(entry)
        if len(results) >= max_results:
            break

    payload = json.dumps({"results": results}, ensure_ascii=False)
    return types.CallToolResult(content=[types.TextContent(type="text", text=payload)])



@app.tool(name="fetch", description="Connector-compliant fetch for search results.")
async def fetch(result_id: str) -> types.CallToolResult:
    result_id = result_id or ""
    remainder = result_id[len("repo:") :] if result_id.startswith("repo:") else result_id
    rel_path, _, line_part = remainder.partition("#L")
    line_number = int(line_part) if line_part.isdigit() else None
    try:
        disk_path = _resolve_repo_path(rel_path)
        text = disk_path.read_text(encoding="utf-8", errors="ignore")
        missing = False
    except (FileNotFoundError, OSError):
        text = ""
        missing = True
    if len(text) > FETCH_MAX_BYTES:
        text = text[:FETCH_MAX_BYTES]
    metadata = {}
    if line_number is not None:
        metadata["line"] = line_number
    if missing:
        metadata["error"] = "file not found"
    document = {
        "id": result_id,
        "title": rel_path,
        "text": text,
        "url": f"stelae://repo/{rel_path}",
        "metadata": metadata,
    }
    payload = json.dumps(document, ensure_ascii=False)
    return types.CallToolResult(content=[types.TextContent(type="text", text=payload)])


def run_server(transport: str = "stdio") -> None:
    app.run(transport)


if __name__ == "__main__":
    run_server()
