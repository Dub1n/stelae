from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable

from stelae_lib.fileio import atomic_write
from .discovery import ToolInfo


class ToolOverridesStore:
    def __init__(self, path: Path):
        self.path = path
        self._original_text = path.read_text(encoding="utf-8") if path.exists() else json.dumps({"master": {"tools": {}}, "servers": {}}, indent=2) + "\n"
        try:
            self._data = json.loads(self._original_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in overrides {path}: {exc}") from exc
        self._ensure_roots()

    def _ensure_roots(self) -> None:
        self._data.setdefault("master", {})
        master = self._data["master"].setdefault("tools", {})
        master.setdefault("*", {"annotations": {}})
        self._data.setdefault("servers", {})

    def apply(self, server_name: str, tools: Iterable[ToolInfo], *, server_description: str | None, source: str | None) -> bool:
        changed = False
        master_tools: Dict[str, Dict[str, str]] = self._data.setdefault("master", {}).setdefault("tools", {})
        server_block = self._data.setdefault("servers", {}).setdefault(server_name, {"enabled": True, "tools": {}})
        tool_map: Dict[str, Dict[str, str]] = server_block.setdefault("tools", {})
        metadata = server_block.setdefault("metadata", {})

        if server_description and not metadata.get("description"):
            metadata["description"] = server_description
            changed = True
        if source and metadata.get("source") != source:
            metadata["source"] = source
            changed = True

        for tool in tools:
            master_entry = master_tools.setdefault(tool.name, {"name": tool.name})
            if "name" not in master_entry:
                master_entry["name"] = tool.name
                changed = True
            if tool.description and not master_entry.get("description"):
                master_entry["description"] = tool.description
                changed = True
            server_entry = tool_map.setdefault(tool.name, {"enabled": True})
            if tool.description and not server_entry.get("description"):
                server_entry["description"] = tool.description
                changed = True
        return changed

    def remove_server(self, server_name: str) -> bool:
        servers = self._data.setdefault("servers", {})
        if server_name not in servers:
            return False
        del servers[server_name]
        return True

    def render(self) -> str:
        return json.dumps(self._data, indent=2, ensure_ascii=False) + "\n"

    def diff(self) -> str:
        after = self.render().splitlines(keepends=True)
        before = self._original_text.splitlines(keepends=True)
        if before == after:
            return ""
        import difflib

        return "".join(difflib.unified_diff(before, after, fromfile=str(self.path), tofile=str(self.path)))

    def write(self) -> None:
        text = self.render()
        if text == self._original_text:
            return
        atomic_write(self.path, text)
        self._original_text = text

    def snapshot(self) -> dict:
        return json.loads(json.dumps(self._data, ensure_ascii=False))

