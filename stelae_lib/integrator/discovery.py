from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

from stelae_lib.fileio import atomic_write, load_json

VALID_TRANSPORTS = {"stdio", "http", "streamable-http", "metadata"}
TRANSPORT_ALIASES = {
    "sse": "http",
    "https": "http",
    "streamable_http": "streamable-http",
    "streamable": "streamable-http",
    "meta": "metadata",
}


def _normalize_transport(value: str) -> str:
    key = (value or "stdio").strip().lower()
    mapped = TRANSPORT_ALIASES.get(key, key)
    if mapped not in VALID_TRANSPORTS:
        raise ValueError(f"Unsupported transport '{value}' (expected one of {sorted(VALID_TRANSPORTS)})")
    return mapped


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y"}:
            return True
        if lowered in {"0", "false", "no", "n"}:
            return False
    raise ValueError(f"Cannot interpret boolean value from {value!r}")


def _coerce_list(values: Iterable[Any] | None) -> List[str]:
    if not values:
        return []
    result: List[str] = []
    for item in values:
        result.append(str(item))
    return result


def _coerce_dict(values: Dict[str, Any] | None) -> Dict[str, str]:
    if not values:
        return {}
    return {str(k): str(v) for k, v in values.items()}


@dataclass(frozen=True)
class ToolInfo:
    name: str
    description: str | None = None

    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> "ToolInfo":
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Tool entry missing name")
        description = data.get("description")
        if description is not None:
            description = str(description)
        return cls(name=name, description=description)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description}


@dataclass
class DiscoveryEntry:
    name: str
    transport: str
    command: str | None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: Dict[str, str] = field(default_factory=dict)
    description: str | None = None
    source: str | None = None
    tools: List[ToolInfo] = field(default_factory=list)
    requires_auth: bool = False
    options: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> "DiscoveryEntry":
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Discovered server is missing a name")
        transport = _normalize_transport(str(data.get("transport") or "stdio"))
        command = data.get("command")
        if command is not None:
            command = str(command)
        args = _coerce_list(data.get("args"))
        env = _coerce_dict(data.get("env"))
        url = data.get("url")
        if url is not None:
            url = str(url)
        headers = _coerce_dict(data.get("headers"))
        description = data.get("description")
        if description is not None:
            description = str(description)
        source = data.get("source")
        if source is not None:
            source = str(source)
        tool_entries = data.get("tools") or []
        tools: List[ToolInfo] = []
        for raw_tool in tool_entries:
            try:
                tools.append(ToolInfo.from_data(raw_tool))
            except Exception:
                continue
        requires_auth = _coerce_bool(data.get("requiresAuth")) if data.get("requiresAuth") is not None else False
        options = data.get("options") or {}
        if not isinstance(options, dict):
            raise ValueError("options must be an object when provided")
        return cls(
            name=name,
            transport=transport,
            command=command,
            args=args,
            env=env,
            url=url,
            headers=headers,
            description=description,
            source=source,
            tools=tools,
            requires_auth=requires_auth,
            options=options,
            raw=data,
        )

    def validation_errors(self) -> List[str]:
        errors: List[str] = []
        if self.transport == "metadata":
            errors.append("metadata entry requires transport/command before installation")
        if self.transport == "stdio" and not self.command:
            errors.append("stdio transport requires a command")
        if self.transport not in {"stdio", "metadata"} and not (self.url or self.command):
            errors.append(f"{self.transport} transport requires url or command")
        return errors

    def to_summary(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "transport": self.transport,
            "description": self.description,
            "source": self.source,
            "requiresAuth": self.requires_auth,
            "tools": [tool.to_dict() for tool in self.tools],
            "issues": self.validation_errors(),
        }

    def to_proxy_entry(self) -> Dict[str, Any]:
        errors = self.validation_errors()
        if errors:
            raise ValueError(f"Cannot build proxy entry for {self.name}: {', '.join(errors)}")
        if self.transport == "metadata":
            raise ValueError(f"Entry {self.name} is metadata-only; update transport/command before installation")
        entry: Dict[str, Any] = {"type": self.transport}
        if self.transport == "stdio" or not self.url:
            entry["command"] = self.command
            if self.args:
                entry["args"] = self.args
            if self.env:
                entry["env"] = self.env
        else:
            entry["url"] = self.url
            if self.headers:
                entry["headers"] = self.headers
        if self.options:
            entry["options"] = self.options
        return entry

    def to_dict(self) -> Dict[str, Any]:
        data = json.loads(json.dumps(self.raw, ensure_ascii=False))
        data.setdefault("name", self.name)
        data.setdefault("transport", self.transport)
        return data


class DiscoveryStore:
    def __init__(self, path: Path):
        self.path = path
        self._entries: List[DiscoveryEntry] | None = None
        self._raw_text = path.read_text(encoding="utf-8") if path.exists() else "[]\n"

    @property
    def text(self) -> str:
        return self._raw_text

    def _load(self) -> List[DiscoveryEntry]:
        data = load_json(self.path, default=[])
        if not isinstance(data, list):
            raise ValueError(f"Discovery file {self.path} must contain an array of servers")
        entries: List[DiscoveryEntry] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                entries.append(DiscoveryEntry.from_data(entry))
            except Exception:
                continue
        return entries

    def entries(self) -> List[DiscoveryEntry]:
        if self._entries is None:
            self._entries = self._load()
        return list(self._entries)

    def get(self, name: str) -> DiscoveryEntry:
        target = name.strip().lower()
        for entry in self.entries():
            if entry.name.lower() == target:
                return entry
        raise KeyError(f"No discovered server named '{name}'")

    def refresh_from(self, source_path: Path) -> Dict[str, Any]:
        if not source_path.exists():
            raise FileNotFoundError(f"Discovery source {source_path} does not exist")
        payload = source_path.read_text(encoding="utf-8")
        json.loads(payload)
        atomic_write(self.path, payload if payload.endswith("\n") else payload + "\n")
        self._entries = None
        self._raw_text = payload
        return {
            "path": str(self.path),
            "source": str(source_path),
            "bytes": len(payload.encode("utf-8")),
        }
