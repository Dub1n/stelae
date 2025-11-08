from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from stelae_lib.fileio import atomic_write


class ProxyTemplate:
    def __init__(self, path: Path):
        self.path = path
        self._original_text = path.read_text(encoding="utf-8") if path.exists() else ""
        try:
            self._data = json.loads(self._original_text) if self._original_text else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in template {path}: {exc}") from exc
        if "mcpServers" not in self._data:
            self._data["mcpServers"] = {}

    def upsert(self, name: str, entry: Dict[str, Any], *, force: bool = False) -> bool:
        servers = self._data.setdefault("mcpServers", {})
        existing = servers.get(name)
        if existing and not force and existing != entry:
            raise ValueError(f"Server '{name}' already exists; pass force to update")
        changed = existing != entry
        servers[name] = entry
        self._data["mcpServers"] = {key: servers[key] for key in sorted(servers)}
        return changed

    def remove(self, name: str) -> bool:
        servers = self._data.setdefault("mcpServers", {})
        if name not in servers:
            return False
        del servers[name]
        self._data["mcpServers"] = {key: servers[key] for key in sorted(servers)}
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

    def snapshot(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self._data, ensure_ascii=False))

