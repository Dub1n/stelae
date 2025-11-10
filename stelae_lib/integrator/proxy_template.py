from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from stelae_lib.config_overlays import deep_merge, overlay_path_for
from stelae_lib.fileio import atomic_write


class ProxyTemplate:
    def __init__(self, base_path: Path, *, overlay_path: Path | None = None):
        self.base_path = base_path
        self.overlay_path = overlay_path or overlay_path_for(base_path)
        self.path = self.overlay_path or self.base_path
        self._base_text = base_path.read_text(encoding="utf-8") if base_path.exists() else "{}\n"
        try:
            self._base_data = json.loads(self._base_text) if self._base_text else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in template {base_path}: {exc}") from exc
        if not isinstance(self._base_data, dict):
            self._base_data = {}
        self._ensure_roots(self._base_data)

        self._overlay_text = (
            self.overlay_path.read_text(encoding="utf-8")
            if self.overlay_path and self.overlay_path.exists()
            else ""
        )
        if self._overlay_text:
            try:
                self._overlay_data: Dict[str, Any] = json.loads(self._overlay_text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in overlay template {self.overlay_path}: {exc}") from exc
        else:
            self._overlay_data = {}
        if not isinstance(self._overlay_data, dict):
            self._overlay_data = {}
        self._ensure_roots(self._overlay_data)

    def _ensure_roots(self, data: Dict[str, Any]) -> None:
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            data["mcpServers"] = {}

    def upsert(self, name: str, entry: Dict[str, Any], *, force: bool = False) -> bool:
        servers = self._overlay_data.setdefault("mcpServers", {})
        existing = servers.get(name)
        merged_existing = self.snapshot()["mcpServers"].get(name)
        if merged_existing and not force and merged_existing != entry:
            raise ValueError(f"Server '{name}' already exists; pass force to update")
        if merged_existing == entry:
            return False
        servers[name] = entry
        self._overlay_data["mcpServers"] = {key: servers[key] for key in sorted(servers)}
        return True

    def remove(self, name: str) -> bool:
        servers = self._overlay_data.setdefault("mcpServers", {})
        if name not in servers:
            return False
        del servers[name]
        self._overlay_data["mcpServers"] = {key: servers[key] for key in sorted(servers)}
        return True

    def render(self) -> str:
        merged = self.snapshot()
        return json.dumps(merged, indent=2, ensure_ascii=False) + "\n"

    def diff(self) -> str:
        target_text = json.dumps(self._overlay_data, indent=2, ensure_ascii=False) + "\n"
        before = self._overlay_text.splitlines(keepends=True)
        after = target_text.splitlines(keepends=True)
        if before == after:
            return ""
        import difflib

        return "".join(
            difflib.unified_diff(before, after, fromfile=str(self.path), tofile=str(self.path))
        )

    def write(self) -> None:
        text = json.dumps(self._overlay_data, indent=2, ensure_ascii=False) + "\n"
        if text == self._overlay_text:
            return
        atomic_write(self.path, text)
        self._overlay_text = text

    def snapshot(self) -> Dict[str, Any]:
        merged = deep_merge(self._base_data, self._overlay_data)
        return json.loads(json.dumps(merged, ensure_ascii=False))
