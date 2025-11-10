#!/usr/bin/env python3
"""MCP server + CLI wrapper for managing Docy documentation sources."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.request import urlopen

from mcp.server import FastMCP

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.config_overlays import config_home
from stelae_lib.docy_catalog import DocyCatalog

CATALOG_PATH = Path(os.getenv("STELAE_DOCY_CATALOG", ROOT / "config" / "docy_sources.json"))
URL_FILE_PATH = Path(os.getenv("STELAE_DOCY_URL_FILE", ROOT / ".docy.urls"))
DEFAULT_DISCOVERY_PATH = Path(
    os.getenv("STELAE_DISCOVERY_PATH") or (config_home() / "discovered_servers.json")
)
OPERATIONS = {"list_sources", "add_source", "remove_source", "sync_catalog", "import_from_manifest"}

app = FastMCP(
    name="docy-manager",
    instructions="Manage Docy documentation sources declaratively.",
)


def _parse_tags(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    if isinstance(value, str):
        return [segment.strip() for segment in value.split(",") if segment.strip()]
    raise ValueError("tags must be a list or comma-separated string")


def _is_http_url(value: str | None) -> bool:
    if not value:
        return False
    return value.startswith(("http://", "https://"))


def _load_manifest_payload(manifest_path: str | None, manifest_url: str | None) -> Any:
    if manifest_path:
        path = Path(manifest_path).expanduser()
        if not path.exists():
            raise ValueError(f"Manifest path '{path}' not found")
        return json.loads(path.read_text(encoding="utf-8"))
    if manifest_url:
        with urlopen(manifest_url) as handle:
            charset = handle.headers.get_content_charset() or "utf-8"
            data = handle.read().decode(charset)
        return json.loads(data)
    if DEFAULT_DISCOVERY_PATH.exists():
        return json.loads(DEFAULT_DISCOVERY_PATH.read_text(encoding="utf-8"))
    raise ValueError("manifest_path or manifest_url is required when the discovery cache is missing")


def _iter_manifest_sources(payload: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, dict):
                candidate = _candidate_from_entry(entry)
                if candidate:
                    yield candidate
        return
    if isinstance(payload, dict):
        resources = payload.get("resources")
        if isinstance(resources, list):
            for resource in resources:
                if isinstance(resource, dict):
                    candidate = _candidate_from_entry(resource)
                    if candidate:
                        yield candidate
        servers = payload.get("servers")
        if isinstance(servers, list):
            for server in servers:
                if isinstance(server, dict):
                    candidate = _candidate_from_entry(server)
                    if candidate:
                        yield candidate
                    server_resources = server.get("resources")
                    if isinstance(server_resources, list):
                        for resource in server_resources:
                            if isinstance(resource, dict):
                                nested = _candidate_from_entry(resource)
                                if nested:
                                    yield nested
        else:
            candidate = _candidate_from_entry(payload)
            if candidate:
                yield candidate


def _candidate_from_entry(entry: Dict[str, Any]) -> Dict[str, Any] | None:
    url_fields = ("url", "uri", "source", "homepage", "documentation", "docs")
    url: str | None = None
    for field in url_fields:
        value = entry.get(field)
        if isinstance(value, str) and _is_http_url(value.strip()):
            url = value.strip()
            break
    if not url:
        options = entry.get("options")
        if isinstance(options, dict):
            for field in url_fields:
                value = options.get(field)
                if isinstance(value, str) and _is_http_url(value.strip()):
                    url = value.strip()
                    break
    if not url:
        return None
    tags: list[str] = []
    raw_tags = entry.get("tags")
    if raw_tags is not None:
        try:
            tags = _parse_tags(raw_tags) or []
        except ValueError:
            tags = []
    elif isinstance(entry.get("options"), dict):
        try:
            tags = _parse_tags(entry["options"].get("tags")) or []
        except ValueError:
            tags = []
    title = entry.get("title") or entry.get("name") or entry.get("id")
    notes = entry.get("description")
    return {"url": url, "title": title, "notes": notes, "tags": tags}


def _execute(operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if operation not in OPERATIONS:
        raise ValueError(f"Unsupported operation '{operation}'")
    catalog = DocyCatalog.load(CATALOG_PATH)
    if operation == "list_sources":
        return {
            "sources": catalog.list_sources(),
            "catalogPath": str(CATALOG_PATH),
            "urlFile": str(URL_FILE_PATH),
        }
    if operation == "sync_catalog":
        lines = catalog.render_urls(URL_FILE_PATH)
        return {
            "status": "rendered",
            "lineCount": len(lines),
            "urlFile": str(URL_FILE_PATH),
        }
    if operation == "import_from_manifest":
        manifest_path = params.get("manifest_path")
        manifest_url = params.get("manifest_url")
        payload = _load_manifest_payload(manifest_path, manifest_url)
        candidates = list(_iter_manifest_sources(payload))
        if not candidates:
            raise ValueError("Manifest did not contain any HTTP resources to import")
        base_tags = _parse_tags(params.get("tags")) or []
        enabled = bool(params.get("enabled", True))
        refresh_hours = params.get("refresh_hours")
        refresh_value = int(refresh_hours) if refresh_hours is not None else None
        allow_update = bool(params.get("allow_update", True))
        dry_run = bool(params.get("dry_run"))
        stats = {"created": 0, "updated": 0, "skipped": 0}
        entries: List[Dict[str, Any]] = []
        for candidate in candidates:
            tags = base_tags + candidate.get("tags", [])
            # Deduplicate while preserving order
            seen: set[str] = set()
            merged_tags = []
            for tag in tags:
                if tag not in seen:
                    merged_tags.append(tag)
                    seen.add(tag)
            try:
                source, action = catalog.add_source(
                    url=candidate["url"],
                    title=candidate.get("title"),
                    tags=merged_tags,
                    notes=candidate.get("notes"),
                    enabled=enabled,
                    refresh_hours=refresh_value,
                    allow_update=allow_update,
                )
            except ValueError as exc:
                stats["skipped"] += 1
                entries.append(
                    {"url": candidate["url"], "status": "skipped", "reason": str(exc)}
                )
                continue
            if action == "created":
                stats["created"] += 1
            else:
                stats["updated"] += 1
            entries.append({"url": candidate["url"], "status": action, "id": source.id})
        render_info = {"status": "dry_run", "lineCount": 0}
        if not dry_run:
            catalog.save()
            if stats["created"] or stats["updated"]:
                lines = catalog.render_urls(URL_FILE_PATH)
                render_info = {"status": "rendered", "lineCount": len(lines)}
            else:
                render_info = {"status": "unchanged", "lineCount": 0}
        manifest_label = manifest_path or manifest_url or str(DEFAULT_DISCOVERY_PATH)
        return {
            "manifest": manifest_label,
            "summary": stats,
            "dryRun": dry_run,
            "render": render_info,
            "entries": entries,
        }

    dry_run = bool(params.get("dry_run"))

    if operation == "add_source":
        url = params.get("url")
        if not url:
            raise ValueError("add_source requires 'url'")
        entry, action = catalog.add_source(
            url=str(url),
            title=params.get("title"),
            source_id=params.get("id"),
            tags=_parse_tags(params.get("tags")),
            notes=params.get("notes"),
            enabled=params.get("enabled", True),
            refresh_hours=params.get("refresh_hours"),
            allow_update=bool(params.get("allow_update", False)),
        )
        render_info: Dict[str, Any] = {"status": "dry_run", "lineCount": 0}
        if not dry_run:
            catalog.save()
            lines = catalog.render_urls(URL_FILE_PATH)
            render_info = {"status": "rendered", "lineCount": len(lines)}
        return {
            "action": action,
            "source": entry.to_dict(),
            "dryRun": dry_run,
            "render": render_info,
        }

    if operation == "remove_source":
        identifier = params.get("id")
        url = params.get("url")
        if not identifier and not url:
            raise ValueError("remove_source requires 'id' or 'url'")
        removed = catalog.remove_source(source_id=identifier, url=url)
        render_info = {"status": "dry_run", "lineCount": 0}
        if not dry_run:
            catalog.save()
            lines = catalog.render_urls(URL_FILE_PATH)
            render_info = {"status": "rendered", "lineCount": len(lines)}
        return {
            "removed": removed.to_dict(),
            "dryRun": dry_run,
            "render": render_info,
        }

    raise ValueError(f"Unhandled operation '{operation}'")


@app.tool(name="manage_docy", description="Manage Docy documentation catalog (list/add/remove/sync).")
async def manage_docy(operation: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return _execute(operation, params or {})


def _run_cli(operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
    return _execute(operation, params)


def main() -> None:
    parser = argparse.ArgumentParser(description="Docy manager MCP server / CLI")
    parser.add_argument("--cli", action="store_true", help="Run a single operation and exit instead of starting the MCP server")
    parser.add_argument("--operation", choices=sorted(OPERATIONS), help="Operation to perform (required in CLI mode)")
    parser.add_argument("--params", help="JSON blob with operation parameters")
    parser.add_argument("--params-file", type=Path, help="Path to JSON file with operation parameters")
    args = parser.parse_args()
    if args.cli:
        if not args.operation:
            parser.error("--operation is required in --cli mode")
        raw_params: Dict[str, Any] = {}
        if args.params_file:
            raw_params = json.loads(args.params_file.read_text(encoding="utf-8"))
        elif args.params:
            raw_params = json.loads(args.params)
        result = _run_cli(args.operation, raw_params)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    app.run()


if __name__ == "__main__":
    main()
