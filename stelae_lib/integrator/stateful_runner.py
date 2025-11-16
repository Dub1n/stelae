from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from mcp import types

from .tool_aggregations import (
    AggregatedToolDefinition,
    AggregationStateDefinition,
    AggregatedToolRunner,
    StateMutationDefinition,
    StateOperationDefinition,
    StatePreloadDefinition,
    StateResponseDefinition,
    StateValueSource,
    ToolAggregationError,
)
from .tool_aggregations import _lookup_path  # reuse helper


_TEMPLATE_PATTERN = re.compile(r"\{\{([^}]+)\}\}")


def _render_template(value: Any, context: Mapping[str, str]) -> Any:
    """Recursively render `{{VAR}}` placeholders inside `value`."""

    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            return context.get(key, "")

        return _TEMPLATE_PATTERN.sub(repl, value)
    if isinstance(value, list):
        return [_render_template(item, context) for item in value]
    if isinstance(value, dict):
        return {k: _render_template(v, context) for k, v in value.items()}
    return value


class JsonStateStore:
    def __init__(
        self,
        definition: AggregationStateDefinition,
        *,
        context: Mapping[str, str],
        workspace_root: Path,
        state_root: Path,
    ) -> None:
        self._definition = definition
        self._context = context
        self._workspace_root = workspace_root
        self._state_root = state_root
        self._path = self._resolve_state_path(definition.path)
        self._fields = self._build_field_map(definition)
        rendered_defaults = _render_template(definition.defaults, context)
        self._data = self._load_state(rendered_defaults)
        self._dirty = False
        self.lock = asyncio.Lock()

    def _resolve_state_path(self, template: str) -> Path:
        rendered = _render_template(template, self._context)
        candidate = Path(rendered).expanduser().resolve()
        state_root = self._state_root.resolve()
        try:
            candidate.relative_to(state_root)
        except ValueError as exc:
            raise ToolAggregationError(
                f"State path {candidate} must live under {state_root}"
            ) from exc
        return candidate

    def _build_field_map(self, definition: AggregationStateDefinition) -> dict[str, dict[str, Any]]:
        fields: dict[str, dict[str, Any]] = {}
        for key, field_def in definition.fields.items():
            entry: dict[str, Any] = {
                "kind": field_def.kind,
                "max_length": field_def.max_length,
            }
            root_template = field_def.root or ("{{STELAE_DIR}}" if field_def.kind == "path" else None)
            if root_template:
                rendered_root = _render_template(root_template, self._context)
                entry["root"] = Path(rendered_root).expanduser().resolve()
            fields[key] = entry
        return fields

    def _load_state(self, defaults: Mapping[str, Any]) -> dict[str, Any]:
        if not self._path.exists():
            return {k: self._coerce_default(k, v) for k, v in defaults.items()}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
        return {k: self._coerce_default(k, v) for k, v in defaults.items()}

    def _coerce_default(self, key: str, value: Any) -> Any:
        field = self._fields.get(key)
        if field and field.get("kind") == "path" and isinstance(value, str):
            path = Path(value).expanduser().resolve()
            return str(path)
        if isinstance(value, list):
            return list(value)
        if isinstance(value, dict):
            return dict(value)
        return value

    def _state_value(self, key: str) -> Any:
        return self._data.get(key)

    def set_value(
        self,
        key: str,
        value: Any,
        *,
        as_path: bool = False,
        relative_to_current: bool = False,
        require_exists: bool = False,
    ) -> None:
        if as_path or self._fields.get(key, {}).get("kind") == "path":
            normalized = self._normalize_path(
                key,
                value,
                relative_to_current=relative_to_current,
                require_exists=require_exists,
            )
        else:
            normalized = value
        if self._data.get(key) != normalized:
            self._data[key] = normalized
            self._dirty = True

    def append_value(self, key: str, entry: dict[str, Any], *, max_length: int | None = None) -> None:
        items = self._data.get(key)
        if not isinstance(items, list):
            items = []
        items.insert(0, entry)
        limit = max_length or self._fields.get(key, {}).get("max_length")
        if isinstance(limit, int) and limit > 0:
            del items[limit:]
        self._data[key] = items
        self._dirty = True

    def mark_clean(self) -> None:
        self._dirty = False

    def get(self, key: str) -> Any:
        value = self._state_value(key)
        if isinstance(value, list):
            return list(value)
        if isinstance(value, dict):
            return dict(value)
        return value

    def _normalize_path(
        self,
        key: str,
        value: Any,
        *,
        relative_to_current: bool,
        require_exists: bool,
    ) -> str:
        candidate = Path(str(value)).expanduser()
        if relative_to_current and not candidate.is_absolute():
            current = self._state_value(key)
            base_path = Path(str(current or self._workspace_root)).expanduser()
            candidate = (base_path / candidate).resolve()
        else:
            candidate = candidate.resolve()
        root = self._fields.get(key, {}).get("root") or self._workspace_root
        if isinstance(root, Path):
            root_path = root.resolve()
            try:
                candidate.relative_to(root_path)
            except ValueError as exc:
                raise ToolAggregationError(
                    f"Path '{candidate}' must stay within {root_path}"
                ) from exc
        if require_exists and not candidate.exists():
            raise ToolAggregationError(f"Directory '{candidate}' does not exist")
        if not candidate.is_dir():
            raise ToolAggregationError(f"'{candidate}' is not a directory")
        return str(candidate)

    def needs_flush(self) -> bool:
        return self._dirty

    def flush(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        self._dirty = False


class StatefulAggregatedToolRunner(AggregatedToolRunner):
    def __init__(
        self,
        definition: AggregatedToolDefinition,
        proxy_call,
        *,
        fallback_timeout: float | None,
        context: Mapping[str, str],
        workspace_root: Path,
        state_root: Path,
    ) -> None:
        if not definition.state:
            raise ToolAggregationError("Stateful runner requires a state definition")
        super().__init__(definition, proxy_call, fallback_timeout=fallback_timeout)
        self._state_definition = definition.state
        self._store = JsonStateStore(
            definition.state,
            context=context,
            workspace_root=workspace_root,
            state_root=state_root,
        )

    async def dispatch(self, arguments: Mapping[str, Any] | None) -> Any:
        payload = arguments if isinstance(arguments, Mapping) else {}
        operation = self.definition.resolve_operation(payload)
        state_op = (
            self._state_definition.get_operation(operation.value)
            if self._state_definition
            else None
        )
        if not state_op:
            return await super().dispatch(payload)
        if state_op.mode == "state_only":
            async with self._store.lock:
                self._apply_preloads(state_op, payload)
                self._apply_mutations(state_op, payload, None)
                result = self._build_state_response(state_op, payload)
                needs_flush = self._store.needs_flush()
            if needs_flush:
                self._store.flush()
            return result
        async with self._store.lock:
            self._apply_preloads(state_op, payload)
        result = await super().dispatch(payload)
        async with self._store.lock:
            self._apply_mutations(state_op, payload, result)
            needs_flush = self._store.needs_flush()
        if needs_flush:
            self._store.flush()
        return result

    def _apply_preloads(self, state_op: StateOperationDefinition, payload: MutableMapping[str, Any]) -> None:
        for preload in state_op.preloads:
            value = self._store.get(preload.state_key)
            if value is None:
                continue
            if preload.only_if_missing and payload.get(preload.argument) not in (None, ""):
                continue
            payload[preload.argument] = value

    def _apply_mutations(
        self,
        state_op: StateOperationDefinition,
        payload: Mapping[str, Any],
        downstream_result: Any,
    ) -> None:
        for mutation in state_op.mutations:
            if mutation.action == "set" and mutation.source:
                value = self._resolve_source(mutation.source, payload, downstream_result)
                if value is None:
                    continue
                self._store.set_value(
                    mutation.key,
                    value,
                    as_path=mutation.as_path,
                    relative_to_current=mutation.relative_to_current,
                    require_exists=mutation.require_exists,
                )
            elif mutation.action == "append" and mutation.value_template:
                entry: dict[str, Any] = {}
                for field, source in mutation.value_template.items():
                    entry[field] = self._resolve_source(source, payload, downstream_result)
                self._store.append_value(mutation.key, entry, max_length=mutation.max_length)

    def _resolve_source(
        self,
        source: StateValueSource,
        payload: Mapping[str, Any],
        downstream_result: Any,
    ) -> Any:
        if source.source_type == "argument":
            return _lookup_path(payload, source.path or "")
        if source.source_type == "state":
            key = source.key or ""
            return self._store.get(key)
        return source.literal

    def _build_state_response(
        self,
        state_op: StateOperationDefinition,
        payload: Mapping[str, Any],
    ) -> Any:
        response = state_op.response
        if not response:
            return [types.TextContent(type="text", text="OK")]
        if response.mode == "history":
            history = self._store.get(response.key) or []
            max_items = None
            if response.max_argument:
                try:
                    requested = int(payload.get(response.max_argument) or 0)
                    if requested > 0:
                        max_items = requested
                except (TypeError, ValueError):
                    pass
            entries = history[:max_items] if isinstance(history, list) else []
            if not entries:
                text = "No command execution history."
                structured = {response.structured_field or "result": {"commands": []}}
            else:
                lines = ["Recent commands:"]
                structured_commands = []
                for idx, entry in enumerate(entries, 1):
                    cwd = entry.get("cwd", "")
                    cmd = entry.get("command", "")
                    lines.append(f"{idx}. [{cwd}] {cmd}")
                    structured_commands.append(entry)
                text = "\n".join(lines)
                structured = {
                    response.structured_field or "result": {"commands": structured_commands}
                }
            return [types.TextContent(type="text", text=text)], structured
        value = self._store.get(response.key)
        rendered_value = str(value) if value is not None else ""
        template = response.template or "{value}"
        text = template.format(value=rendered_value)
        structured = {response.structured_field or "result": rendered_value}
        return [types.TextContent(type="text", text=text)], structured
