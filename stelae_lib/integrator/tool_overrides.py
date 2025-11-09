from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

from stelae_lib.fileio import atomic_write
from .discovery import ToolInfo


class ToolOverridesStore:
    def __init__(self, path: Path):
        self.path = path
        self._schema_path = self.path.with_name("tool_overrides.schema.json")
        default_text = json.dumps(
            {
                "schemaVersion": 2,
                "master": {"tools": {"*": {"annotations": {}}}},
                "servers": {},
            },
            indent=2,
        )
        self._original_text = path.read_text(encoding="utf-8") if path.exists() else default_text + "\n"
        try:
            self._data = json.loads(self._original_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in overrides {path}: {exc}") from exc
        self._legacy_global_tools: Dict[str, Dict[str, Any]] = {}
        self._legacy_master_tools: Dict[str, Dict[str, Any]] = {}
        self._ensure_roots()

    def _ensure_roots(self) -> None:
        data = self._data
        if not isinstance(data, dict):
            data.clear()
        schema_version = data.get("schemaVersion")
        if not isinstance(schema_version, int) or schema_version < 2:
            data["schemaVersion"] = 2
        else:
            data["schemaVersion"] = schema_version

        master = data.setdefault("master", {})
        tools = master.setdefault("tools", {})
        wildcard = tools.get("*")
        if not isinstance(wildcard, dict):
            wildcard = {"annotations": {}}
            tools["*"] = wildcard
        wildcard.setdefault("annotations", {})

        self._legacy_master_tools = {}
        for key in list(tools.keys()):
            if key == "*":
                continue
            value = tools.pop(key)
            if isinstance(value, dict):
                self._legacy_master_tools[key] = value

        legacy_tools = data.pop("tools", None)
        self._legacy_global_tools = legacy_tools if isinstance(legacy_tools, dict) else {}

        servers = data.setdefault("servers", {})
        for fragment in servers.values():
            if not isinstance(fragment, dict):
                continue
            fragment.setdefault("tools", {})
            metadata = fragment.get("metadata")
            if metadata is not None and not isinstance(metadata, dict):
                fragment["metadata"] = {}
        
    def _ensure_tool_block(self, server_name: str, tool_name: str) -> Dict[str, Any]:
        servers = self._data.setdefault("servers", {})
        server_block = servers.setdefault(server_name, {"enabled": True, "tools": {}})
        server_block.setdefault("tools", {})
        tool_map = server_block["tools"]
        tool_block = tool_map.setdefault(tool_name, {"enabled": True})
        if not isinstance(tool_block, dict):
            tool_block = {"enabled": True}
            tool_map[tool_name] = tool_block
        if self._promote_legacy_overrides(tool_name, tool_block):
            server_block["tools"][tool_name] = tool_block
        return tool_block

    def _promote_legacy_overrides(self, tool_name: str, dest: Dict[str, Any]) -> bool:
        changed = False
        for pool in (self._legacy_master_tools, self._legacy_global_tools):
            block = pool.pop(tool_name, None)
            if isinstance(block, dict):
                changed |= self._merge_tool_data(dest, block)
        return changed

    def _merge_tool_data(self, dest: Dict[str, Any], src: Dict[str, Any]) -> bool:
        changed = False
        for key, value in src.items():
            if value is None or key in {"enabled"}:
                if key not in dest:
                    dest[key] = value
                    changed = True
                continue
            if key in {"inputSchema", "outputSchema", "annotations"}:
                if key == "annotations":
                    existing = dest.setdefault("annotations", {})
                    if not isinstance(existing, dict):
                        existing = {}
                        dest["annotations"] = existing
                    for ann_key, ann_val in value.items():
                        if ann_key not in existing:
                            existing[ann_key] = ann_val
                            changed = True
                elif key not in dest:
                    dest[key] = json.loads(json.dumps(value))
                    changed = True
                continue
            if key not in dest:
                dest[key] = value
                changed = True
        return changed

    def apply(self, server_name: str, tools: Iterable[ToolInfo], *, server_description: str | None, source: str | None) -> bool:
        changed = False
        server_block = self._data.setdefault("servers", {}).setdefault(server_name, {"enabled": True, "tools": {}})
        tool_map: Dict[str, Dict[str, Any]] = server_block.setdefault("tools", {})
        metadata = server_block.setdefault("metadata", {})

        if server_description and not metadata.get("description"):
            metadata["description"] = server_description
            changed = True
        if source and metadata.get("source") != source:
            metadata["source"] = source
            changed = True

        for tool in tools:
            server_entry = tool_map.setdefault(tool.name, {"enabled": True})
            if self._promote_legacy_overrides(tool.name, server_entry):
                changed = True
            if tool.description and not server_entry.get("description"):
                server_entry["description"] = tool.description
                changed = True
        return changed

    def ensure_schema(self, server_name: str, tool_name: str, key: str, schema: Any) -> bool:
        if not server_name or not tool_name or not schema:
            return False
        if key not in {"inputSchema", "outputSchema"}:
            return False
        tool_block = self._ensure_tool_block(server_name, tool_name)
        if key in tool_block:
            return False
        tool_block[key] = json.loads(json.dumps(schema))
        return True

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
        self._validate()
        atomic_write(self.path, text)
        self._original_text = text

    def _validate(self) -> None:
        if not self._schema_path.exists():
            return
        try:
            import jsonschema  # type: ignore
        except ModuleNotFoundError:  # pragma: no cover - optional dep at runtime
            return
        schema = json.loads(self._schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(self._data, schema)

    def snapshot(self) -> dict:
        return json.loads(json.dumps(self._data, ensure_ascii=False))
