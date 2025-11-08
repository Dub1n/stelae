from __future__ import annotations

import difflib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .discovery import DiscoveryEntry, DiscoveryStore
from .one_mcp import OneMCPDiscovery, OneMCPDiscoveryError
from .proxy_template import ProxyTemplate
from .runner import CommandFailed, CommandRunner
from .tool_overrides import ToolOverridesStore
from stelae_lib.fileio import atomic_write

ENV_PATTERN = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")


@dataclass
class IntegratorResponse:
    status: str
    details: Dict[str, Any] = field(default_factory=dict)
    files_updated: List[Dict[str, Any]] = field(default_factory=list)
    commands_run: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "details": self.details,
            "files_updated": self.files_updated,
            "commands_run": self.commands_run,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def _diff_text(path: Path, before: str, after: str) -> str:
    if before == after:
        return ""
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )


def _parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key.strip()] = raw_value.strip().strip('"')
    return values


class StelaeIntegratorService:
    def __init__(
        self,
        *,
        root: Path | None = None,
        discovery_path: Path | None = None,
        template_path: Path | None = None,
        overrides_path: Path | None = None,
        env_files: Sequence[Path] | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.discovery_path = discovery_path or self.root / "config" / "discovered_servers.json"
        self.template = ProxyTemplate(template_path or self.root / "config" / "proxy.template.json")
        self.overrides = ToolOverridesStore(overrides_path or self.root / "config" / "tool_overrides.json")
        self.discovery_store = DiscoveryStore(self.discovery_path)
        # Load .env.example first so concrete .env overrides placeholder values.
        env_candidates = env_files or [self.root / ".env.example", self.root / ".env"]
        values: Dict[str, str] = {}
        for candidate in env_candidates:
            values.update(_parse_env_file(candidate))
        for key, value in os.environ.items():
            if isinstance(key, str) and isinstance(value, str):
                values.setdefault(key, value)
        self.env_values = values
        self.command_runner = command_runner or CommandRunner(self.root)
        self.default_commands: List[List[str]] = [
            ["make", "render-proxy"],
            [str(self.root / "scripts" / "run_restart_stelae.sh"), "--full"],
        ]
        self._one_mcp: OneMCPDiscovery | None = None

    def dispatch(self, operation: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        params = params or {}
        op = operation.strip().lower()
        handler = {
            "list_discovered_servers": self._list_discovered_servers,
            "install_server": self._install_server,
            "remove_server": self._remove_server,
            "refresh_discovery": self._refresh_discovery,
            "run_reconciler": self._run_reconciler,
            "discover_servers": self._discover_servers,
        }.get(op)
        if not handler:
            raise ValueError(f"Unsupported operation '{operation}'")
        response = handler(params)
        return response.to_dict()

    # operations -----------------------------------------------------------------
    def _list_discovered_servers(self, params: Dict[str, Any]) -> IntegratorResponse:
        entries = [entry.to_summary() for entry in self.discovery_store.entries()]
        return IntegratorResponse(
            status="ok",
            details={"servers": entries, "path": str(self.discovery_path)},
        )

    def _refresh_discovery(self, params: Dict[str, Any]) -> IntegratorResponse:
        source_path = params.get("source_path")
        if source_path:
            source = Path(source_path)
        else:
            source = self._guess_discovery_source()
            if not source:
                raise ValueError("source_path not provided and ONE_MCP_DIR/discovered_servers.json not found")
        before = self.discovery_path.read_text(encoding="utf-8") if self.discovery_path.exists() else ""
        info = self.discovery_store.refresh_from(source)
        after = self.discovery_path.read_text(encoding="utf-8")
        files = [
            {
                "path": str(self.discovery_path),
                "changed": before != after,
                "dryRun": False,
                "diff": _diff_text(self.discovery_path, before, after),
            }
        ]
        return IntegratorResponse(status="ok", details=info, files_updated=files)

    def _discover_servers(self, params: Dict[str, Any]) -> IntegratorResponse:
        query = str(params.get("query") or "").strip()
        limit = max(1, int(params.get("limit") or 25))
        min_score = params.get("min_score")
        min_score_val = float(min_score) if min_score is not None else None
        append = bool(params.get("append", True))
        dry_run = bool(params.get("dry_run"))
        discovery = self._get_one_mcp_discovery()
        results = discovery.search(query, limit=limit, min_score=min_score_val)
        if not results:
            return IntegratorResponse(
                status="ok",
                details={"query": query, "results": 0},
                warnings=["No results returned from 1mcp search"],
            )
        base_entries = [] if not append else self._load_discovery_data()
        entries_by_name: Dict[str, Dict[str, Any]] = {}
        for entry in base_entries:
            if isinstance(entry, dict) and entry.get("name"):
                entries_by_name[entry["name"]] = entry
        added = 0
        for result in results:
            payload = result.to_entry(query or None)
            existing = entries_by_name.get(payload["name"])
            if existing and existing.get("transport") != "metadata":
                continue
            entries_by_name[payload["name"]] = payload
            added += 1
        ordered = sorted(entries_by_name.values(), key=lambda item: item.get("name", ""))
        files = self._persist_discovery_data(ordered, dry_run=dry_run)
        details = {
            "query": query,
            "limit": limit,
            "results": len(results),
            "added": added,
            "dryRun": dry_run,
            "minScore": min_score_val,
        }
        return IntegratorResponse(status="ok", details=details, files_updated=files)

    def _install_server(self, params: Dict[str, Any]) -> IntegratorResponse:
        name = params.get("name") or params.get("server")
        descriptor = params.get("descriptor")
        dry_run = bool(params.get("dry_run"))
        force = bool(params.get("force"))
        options_override = params.get("options")
        if descriptor:
            if not isinstance(descriptor, dict):
                raise ValueError("descriptor must be an object when provided")
            entry = DiscoveryEntry.from_data(descriptor)
        else:
            if not name:
                raise ValueError("install_server requires 'name' or 'descriptor'")
            entry = self.discovery_store.get(str(name))
        if options_override:
            if not isinstance(options_override, dict):
                raise ValueError("options override must be an object")
            entry.options.update({str(k): v for k, v in options_override.items()})
        target_name = str(params.get("target_name") or entry.name).strip()
        if not target_name:
            raise ValueError("target_name cannot be empty")
        self._validate_entry(entry)
        proxy_entry = entry.to_proxy_entry()
        template_changed = self.template.upsert(target_name, proxy_entry, force=force)
        overrides_changed = self.overrides.apply(
            target_name,
            entry.tools,
            server_description=entry.description,
            source=entry.source,
        )
        files: List[Dict[str, Any]] = []
        if template_changed:
            files.append(
                {
                    "path": str(self.template.path),
                    "changed": True,
                    "dryRun": dry_run,
                    "diff": self.template.diff(),
                }
            )
        if overrides_changed:
            files.append(
                {
                    "path": str(self.overrides.path),
                    "changed": True,
                    "dryRun": dry_run,
                    "diff": self.overrides.diff(),
                }
            )
        commands: List[Dict[str, Any]] = []
        if not dry_run:
            if template_changed:
                self.template.write()
            if overrides_changed:
                self.overrides.write()
        should_restart = not dry_run and (template_changed or overrides_changed or bool(params.get("force_restart")))
        if should_restart:
            commands = self._run_commands(dry_run=dry_run)
        details = {
            "server": target_name,
            "dryRun": dry_run,
            "templateChanged": template_changed,
            "overridesChanged": overrides_changed,
            "toolsSeeded": len(entry.tools),
        }
        response = IntegratorResponse(status="ok", details=details, files_updated=files, commands_run=commands)
        self._reload_template_overrides()
        return response

    def _remove_server(self, params: Dict[str, Any]) -> IntegratorResponse:
        name = params.get("name")
        dry_run = bool(params.get("dry_run"))
        if not name:
            raise ValueError("remove_server requires 'name'")
        removed_template = self.template.remove(str(name))
        removed_overrides = self.overrides.remove_server(str(name))
        if not removed_template and not removed_overrides:
            raise ValueError(f"Server '{name}' not found in template or overrides")
        files: List[Dict[str, Any]] = []
        if removed_template:
            files.append(
                {
                    "path": str(self.template.path),
                    "changed": True,
                    "dryRun": dry_run,
                    "diff": self.template.diff(),
                }
            )
        if removed_overrides:
            files.append(
                {
                    "path": str(self.overrides.path),
                    "changed": True,
                    "dryRun": dry_run,
                    "diff": self.overrides.diff(),
                }
            )
        if not dry_run:
            if removed_template:
                self.template.write()
            if removed_overrides:
                self.overrides.write()
        commands: List[Dict[str, Any]] = []
        if not dry_run:
            commands = self._run_commands(dry_run=False)
        details = {
            "server": name,
            "templateChanged": removed_template,
            "overridesChanged": removed_overrides,
            "dryRun": dry_run,
        }
        response = IntegratorResponse(status="ok", details=details, files_updated=files, commands_run=commands)
        self._reload_template_overrides()
        return response

    def _run_reconciler(self, params: Dict[str, Any]) -> IntegratorResponse:
        dry_run = bool(params.get("dry_run"))
        commands = self._run_commands(dry_run=dry_run)
        return IntegratorResponse(status="ok", details={"dryRun": dry_run}, commands_run=commands)

    # helpers -------------------------------------------------------------------
    def _get_one_mcp_discovery(self) -> OneMCPDiscovery:
        if self._one_mcp is None:
            try:
                self._one_mcp = OneMCPDiscovery()
            except OneMCPDiscoveryError as exc:  # pragma: no cover - environment specific
                raise ValueError(str(exc)) from exc
        return self._one_mcp

    def _run_commands(self, dry_run: bool) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if dry_run:
            for cmd in self.default_commands:
                results.append({"command": cmd, "status": "skipped", "output": "dry-run", "returncode": None})
            return results
        try:
            executed = self.command_runner.sequence(self.default_commands)
        except CommandFailed as exc:
            results.append(
                {
                    "command": exc.result.command,
                    "status": exc.result.status,
                    "output": exc.result.output,
                    "returncode": exc.result.returncode,
                }
            )
            raise
        for result in executed:
            results.append(
                {
                    "command": result.command,
                    "status": result.status,
                    "output": result.output,
                    "returncode": result.returncode,
                }
            )
        return results

    def _validate_entry(self, entry: DiscoveryEntry) -> None:
        if entry.transport == "stdio" or not entry.url:
            if not entry.command:
                raise ValueError("stdio descriptor missing command")
            self._validate_command(entry.command)
            for arg in entry.args:
                self._validate_placeholders(arg)
        else:
            self._validate_placeholders(entry.url or "")
        for value in entry.env.values():
            self._validate_placeholders(value)

    def _validate_placeholders(self, value: str) -> None:
        for match in ENV_PATTERN.finditer(value or ""):
            key = match.group(1)
            if key not in self.env_values:
                raise ValueError(f"Placeholder {{{{{key}}}}} not present in environment/.env")

    def _validate_command(self, command: str) -> None:
        if ENV_PATTERN.search(command):
            self._validate_placeholders(command)
            return
        if command.startswith(".") or command.startswith("/") or command.startswith("~") or "/" in command:
            path = Path(command).expanduser()
            if not path.exists():
                raise FileNotFoundError(f"Command path {path} does not exist")
            return
        if shutil.which(command) is None:
            raise FileNotFoundError(f"Command '{command}' not found in PATH")

    def _guess_discovery_source(self) -> Path | None:
        base = self.env_values.get("ONE_MCP_DIR") or os.getenv("ONE_MCP_DIR")
        if not base:
            return None
        candidate = Path(base) / "discovered_servers.json"
        if candidate.exists():
            return candidate
        return None

    def _reload_template_overrides(self) -> None:
        self.template = ProxyTemplate(self.template.path)
        self.overrides = ToolOverridesStore(self.overrides.path)

    def _load_discovery_data(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(self.discovery_store.text)
        except json.JSONDecodeError:
            return []

    def _persist_discovery_data(self, data: List[Dict[str, Any]], *, dry_run: bool) -> List[Dict[str, Any]]:
        before = self.discovery_store.text
        rendered = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        diff = _diff_text(self.discovery_path, before, rendered)
        files = [
            {
                "path": str(self.discovery_path),
                "changed": before != rendered,
                "dryRun": dry_run,
                "diff": diff,
            }
        ]
        if not dry_run and before != rendered:
            atomic_write(self.discovery_path, rendered)
            self.discovery_store = DiscoveryStore(self.discovery_path)
        return files
