from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Sequence

from stelae_lib.catalog_defaults import DEFAULT_TOOL_OVERRIDES
from stelae_lib.config_overlays import deep_merge
from stelae_lib.fileio import atomic_write
from .discovery import ToolInfo


class ToolOverridesStore:
    def __init__(
        self,
        base_path: Path,
        *,
        overlay_path: Path | None = None,
        runtime_path: Path | None = None,
        target: str = "overlay",
    ) -> None:
        if target not in {"base", "overlay", "runtime"}:
            raise ValueError("target must be 'base', 'overlay', or 'runtime'")
        if target == "runtime" and runtime_path is None:
            raise ValueError("runtime_path is required when target='runtime'")
        self.base_path = base_path
        self.overlay_path = overlay_path or base_path
        self.runtime_path = runtime_path
        self._target = target if not (target == "overlay" and self.overlay_path is None) else "base"
        self._schema_path = self.base_path.with_name("tool_overrides.schema.json")

        base_text = (
            self.base_path.read_text(encoding="utf-8")
            if self.base_path.exists()
            else json.dumps(DEFAULT_TOOL_OVERRIDES, indent=2, ensure_ascii=False) + "\n"
        )
        self._base_data = self._load_payload(base_text)
        overlay_text = (
            self.overlay_path.read_text(encoding="utf-8")
            if self.overlay_path and self.overlay_path.exists()
            else ""
        )
        self._overlay_data = self._load_payload(overlay_text) if overlay_text else {}

        self._legacy_global_tools: Dict[str, Dict[str, Any]] = {}
        self._legacy_master_tools: Dict[str, Dict[str, Any]] = {}
        self._ensure_roots(self._base_data)
        self._ensure_roots(self._overlay_data)

        if self._target == "base":
            self.path = self.base_path
            self._data = self._base_data
            self._original_text = base_text
        elif self._target == "runtime":
            self.path = runtime_path
            self._data = self._merged_payload()
            self._original_text = json.dumps(self._data, indent=2, ensure_ascii=False) + "\n"
        else:
            self.path = self.overlay_path
            self._data = self._overlay_data
            self._original_text = overlay_text or ""

    def _load_payload(self, text: str) -> Dict[str, Any]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in overrides {self.base_path}: {exc}") from exc
        if not isinstance(data, dict):
            return {}
        return data

    def _ensure_roots(self, data: Dict[str, Any]) -> None:
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

    def disable_tool(self, server_name: str, tool_name: str) -> bool:
        tool_block = self._ensure_tool_block(server_name, tool_name)
        if tool_block.get("enabled") is False:
            return False
        tool_block["enabled"] = False
        return True

    def update_tool_descriptor(
        self,
        server_name: str,
        tool_name: str,
        *,
        description: str | None = None,
        annotations: Dict[str, Any] | None = None,
        input_schema: Any | None = None,
        output_schema: Any | None = None,
        enabled: bool | None = None,
        name: str | None = None,
    ) -> bool:
        tool_block = self._ensure_tool_block(server_name, tool_name)
        changed = False
        if enabled is not None and tool_block.get("enabled") != enabled:
            tool_block["enabled"] = enabled
            changed = True
        if name and tool_block.get("name") != name:
            tool_block["name"] = name
            changed = True
        if description and tool_block.get("description") != description:
            tool_block["description"] = description
            changed = True
        if annotations:
            existing = tool_block.setdefault("annotations", {})
            if not isinstance(existing, dict):
                existing = {}
                tool_block["annotations"] = existing
            for key, value in annotations.items():
                if key not in existing or existing[key] != value:
                    existing[key] = value
                    changed = True
        if input_schema is not None:
            serialized = json.loads(json.dumps(input_schema))
            if tool_block.get("inputSchema") != serialized:
                tool_block["inputSchema"] = serialized
                changed = True
        if output_schema is not None:
            serialized = json.loads(json.dumps(output_schema))
            if isinstance(serialized, dict) and isinstance(serialized.get("type"), list):
                # Normalize permissive type arrays for MCP clients that reject them.
                serialized = dict(serialized, type="object")
            if tool_block.get("outputSchema") != serialized:
                tool_block["outputSchema"] = serialized
                changed = True
        return changed

    def apply(
        self,
        server_name: str,
        tools: Iterable[ToolInfo],
        *,
        server_description: str | None,
        source: str | None,
    ) -> bool:
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

    def render_merged(self) -> str:
        merged = self._merged_payload()
        return json.dumps(merged, indent=2, ensure_ascii=False) + "\n"

    def diff(self) -> str:
        after = self.render().splitlines(keepends=True)
        before = self._original_text.splitlines(keepends=True)
        if before == after:
            return ""
        import difflib

        return "".join(difflib.unified_diff(before, after, fromfile=str(self.path), tofile=str(self.path)))

    def write(self) -> None:
        text = self.render()
        if text != self._original_text:
            self._validate(self._data)
            atomic_write(self.path, text)
            self._original_text = text
        if self._target != "runtime" and self.runtime_path:
            self.export_runtime()

    def export_runtime(self, path: Path | None = None) -> None:
        target = path or self.runtime_path
        if not target:
            return
        payload = self._merged_payload()
        self._validate(payload)
        atomic_write(target, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    def _validate(self, payload: Dict[str, Any]) -> None:
        if not self._schema_path.exists():
            return
        try:
            import jsonschema  # type: ignore
        except ModuleNotFoundError:  # pragma: no cover
            return
        schema = json.loads(self._schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(payload, schema)

    def _merged_payload(self) -> Dict[str, Any]:
        merged = deep_merge(self._base_data, self._overlay_data)
        sanitized = _dedupe_schema_arrays(merged)
        self._prune_empty_servers(sanitized)
        return json.loads(json.dumps(sanitized, ensure_ascii=False))

    def _prune_empty_servers(self, payload: Dict[str, Any]) -> None:
        servers = payload.get("servers")
        if not isinstance(servers, dict):
            return
        empty: list[str] = []
        for name, fragment in servers.items():
            if not isinstance(fragment, dict):
                empty.append(name)
                continue
            tools = fragment.get("tools")
            if not isinstance(tools, dict) or not tools:
                empty.append(name)
        for name in empty:
            servers.pop(name, None)

    def snapshot(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self._data, ensure_ascii=False))

    def merged_snapshot(self) -> Dict[str, Any]:
        return self._merged_payload()


def _dedupe_schema_arrays(payload: Dict[str, Any]) -> Dict[str, Any]:
    def _walk(node: Any, parent_key: str | None = None) -> Any:
        if isinstance(node, dict):
            return {key: _walk(value, key) for key, value in node.items()}
        if isinstance(node, list):
            cleaned = [_walk(item, None) for item in node]
            if parent_key in {"enum", "required"}:
                cleaned = _dedupe_list(cleaned)
            return cleaned
        return node

    return _walk(payload)


def _dedupe_list(items: Sequence[Any]) -> list[Any]:
    deduped: list[Any] = []
    seen: set[str] = set()
    for item in items:
        marker = _stable_marker(item)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped


def _stable_marker(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    except TypeError:
        return repr(value)
