from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Mapping, MutableMapping, Sequence

from stelae_lib.integrator.tool_overrides import ToolOverridesStore

ProxyCaller = Callable[[str, Dict[str, Any], float | None], Awaitable[Dict[str, Any]]]

DEFAULT_SELECTOR_FIELD = "operation"
DEFAULT_AGGREGATOR_SERVER = "tool_aggregator"
DEFAULT_TIMEOUT = 45.0
_SKIP = object()


class ToolAggregationError(ValueError):
    """Raised when declarative aggregation config cannot be satisfied."""


@dataclass(frozen=True)
class AggregationDefaults:
    selector_field: str = DEFAULT_SELECTOR_FIELD
    case_insensitive_selector: bool = True
    timeout_seconds: float | None = DEFAULT_TIMEOUT
    proxy_url: str | None = None
    server_name: str = DEFAULT_AGGREGATOR_SERVER

    @classmethod
    def from_data(cls, payload: Mapping[str, Any] | None) -> AggregationDefaults:
        if not isinstance(payload, Mapping):
            return cls()
        selector_field = str(payload.get("selectorField") or DEFAULT_SELECTOR_FIELD).strip() or DEFAULT_SELECTOR_FIELD
        case_insensitive = bool(payload.get("caseInsensitiveSelector", True))
        timeout_value = payload.get("timeoutSeconds")
        timeout_seconds = float(timeout_value) if isinstance(timeout_value, (int, float)) else DEFAULT_TIMEOUT
        proxy_url = str(payload.get("proxyURL") or payload.get("proxyUrl") or "").strip() or None
        server_name = str(payload.get("serverName") or DEFAULT_AGGREGATOR_SERVER).strip() or DEFAULT_AGGREGATOR_SERVER
        return cls(
            selector_field=selector_field,
            case_insensitive_selector=case_insensitive,
            timeout_seconds=timeout_seconds,
            proxy_url=proxy_url,
            server_name=server_name,
        )


@dataclass(frozen=True)
class HiddenTool:
    server: str
    tool: str
    reason: str | None = None

    @classmethod
    def from_data(cls, payload: Mapping[str, Any]) -> HiddenTool:
        server = str(payload.get("server") or "").strip()
        tool = str(payload.get("tool") or "").strip()
        if not server or not tool:
            raise ToolAggregationError("hiddenTools entries require non-empty 'server' and 'tool'")
        reason = str(payload.get("reason")) if payload.get("reason") else None
        return cls(server=server, tool=tool, reason=reason)


@dataclass(frozen=True)
class MappingRule:
    target: str
    source: str | None = None
    literal: Any | None = None
    default: Any | None = None
    required: bool = False
    allow_null: bool = True
    strip_if_null: bool = True

    @classmethod
    def from_data(cls, payload: Mapping[str, Any]) -> MappingRule:
        target = str(payload.get("target") or "").strip()
        if not target:
            raise ToolAggregationError("mapping rules require a 'target' path")
        source = payload.get("source")
        if source is None:
            source = payload.get("from")
        source_text = str(source).strip() if isinstance(source, str) else None
        literal = payload.get("value") if "value" in payload else payload.get("literal")
        default = payload.get("default")
        required = bool(payload.get("required", False))
        allow_null = bool(payload.get("allowNull", True))
        strip_if_null = bool(payload.get("stripIfNull", True))
        return cls(
            target=target,
            source=source_text,
            literal=literal,
            default=default,
            required=required,
            allow_null=allow_null,
            strip_if_null=strip_if_null,
        )

    def resolve(self, data: Mapping[str, Any], *, label: str) -> Any | object:
        value: Any | None
        if self.literal is not None:
            value = self.literal
        elif self.source is not None:
            value = _lookup_path(data, self.source)
        else:
            value = None

        if value is None:
            if self.default is not None:
                value = self.default
            elif self.required:
                source_label = self.source or self.target
                raise ToolAggregationError(
                    f"Aggregation '{label}' is missing required field '{source_label}'"
                )

        if value is None and (self.strip_if_null or not self.allow_null):
            if self.required:
                raise ToolAggregationError(
                    f"Aggregation '{label}' cannot accept null for '{self.source or self.target}'"
                )
            return _SKIP

        if value is None and not self.allow_null:
            return _SKIP

        return copy.deepcopy(value)


@dataclass(frozen=True)
class OperationMapping:
    value: str
    downstream_tool: str
    downstream_server: str | None = None
    argument_rules: Sequence[MappingRule] = field(default_factory=tuple)
    response_rules: Sequence[MappingRule] = field(default_factory=tuple)
    aliases: tuple[str, ...] = ()
    timeout_seconds: float | None = None
    description: str | None = None
    required_any_of: Sequence[tuple[str, ...]] = field(default_factory=tuple)

    @classmethod
    def from_data(cls, payload: Mapping[str, Any]) -> OperationMapping:
        raw_value = payload.get("value")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ToolAggregationError("operation mappings require a non-empty 'value'")
        downstream_tool = str(payload.get("downstreamTool") or "").strip()
        if not downstream_tool:
            raise ToolAggregationError(
                f"Operation '{raw_value}' must declare 'downstreamTool'"
            )
        downstream_server = (
            str(payload.get("downstreamServer") or "").strip() or None
        )
        argument_rules = tuple(
            MappingRule.from_data(item)
            for item in payload.get("argumentMappings", [])
            if isinstance(item, Mapping)
        )
        response_rules = tuple(
            MappingRule.from_data(item)
            for item in payload.get("responseMappings", [])
            if isinstance(item, Mapping)
        )
        aliases: tuple[str, ...] = tuple(
            str(item).strip()
            for item in payload.get("aliases", [])
            if isinstance(item, str) and item.strip()
        )
        timeout_value = payload.get("timeoutSeconds")
        timeout_seconds = (
            float(timeout_value)
            if isinstance(timeout_value, (int, float))
            else None
        )
        description = (
            str(payload.get("description")) if payload.get("description") else None
        )
        required_any_of: list[tuple[str, ...]] = []
        for group in payload.get("requireAnyOf", []) or []:
            if not isinstance(group, Sequence):
                continue
            members = tuple(
                str(item).strip()
                for item in group
                if isinstance(item, str) and item.strip()
            )
            if members:
                required_any_of.append(members)
        return cls(
            value=raw_value.strip(),
            downstream_tool=downstream_tool,
            downstream_server=downstream_server,
            argument_rules=argument_rules,
            response_rules=response_rules,
            aliases=aliases,
            timeout_seconds=timeout_seconds,
            description=description,
            required_any_of=tuple(required_any_of),
        )

    def matches(self, candidate: str, *, case_insensitive: bool) -> bool:
        if case_insensitive:
            target = self.value.lower()
            needle = candidate.lower()
            alias_set = {alias.lower() for alias in self.aliases}
        else:
            target = self.value
            needle = candidate
            alias_set = set(self.aliases)
        return needle == target or needle in alias_set

    def validate_requirements(self, payload: Mapping[str, Any], *, label: str) -> None:
        for group in self.required_any_of:
            if not group:
                continue
            if any(_lookup_path(payload, field) not in (None, "") for field in group):
                continue
            human = " or ".join(group)
            raise ToolAggregationError(
                f"Aggregation '{label}' requires at least one of ({human})"
            )


@dataclass(frozen=True)
class AggregatedToolDefinition:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any] | None
    annotations: Dict[str, Any] | None
    selector_field: str
    case_insensitive_selector: bool
    timeout_seconds: float | None
    proxy_url: str | None
    server: str
    operations: Sequence[OperationMapping]
    hidden_tools: Sequence[HiddenTool]

    @classmethod
    def from_data(
        cls,
        payload: Mapping[str, Any],
        defaults: AggregationDefaults,
    ) -> AggregatedToolDefinition:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ToolAggregationError("aggregations require a non-empty 'name'")
        description = str(payload.get("description") or "").strip()
        if not description:
            raise ToolAggregationError(f"Aggregation '{name}' is missing a description")
        input_schema = _normalize_schema(payload.get("inputSchema"))
        output_schema = _normalize_schema(payload.get("outputSchema"), allow_empty=True)
        annotations = (
            dict(payload.get("annotations"))
            if isinstance(payload.get("annotations"), Mapping)
            else None
        )
        selector = payload.get("selector")
        selector_field = defaults.selector_field
        case_insensitive = defaults.case_insensitive_selector
        if isinstance(selector, Mapping):
            selector_field = str(selector.get("field") or selector_field).strip() or selector_field
            case_insensitive = bool(
                selector.get("caseInsensitive", case_insensitive)
            )
        timeout_value = payload.get("timeoutSeconds")
        timeout_seconds = (
            float(timeout_value)
            if isinstance(timeout_value, (int, float))
            else defaults.timeout_seconds
        )
        proxy_url = (
            str(payload.get("proxyURL") or payload.get("proxyUrl") or "").strip()
            or defaults.proxy_url
        )
        server = str(payload.get("server") or payload.get("serverName") or defaults.server_name).strip() or defaults.server_name
        operations_payload = payload.get("operations")
        if not isinstance(operations_payload, list) or not operations_payload:
            raise ToolAggregationError(f"Aggregation '{name}' must declare at least one operation")
        operations: list[OperationMapping] = []
        for item in operations_payload:
            if not isinstance(item, Mapping):
                continue
            operations.append(OperationMapping.from_data(item))
        if not operations:
            raise ToolAggregationError(f"Aggregation '{name}' did not produce any valid operations")
        hidden_tools = tuple(
            HiddenTool.from_data(item)
            for item in payload.get("hideTools", [])
            if isinstance(item, Mapping)
        )
        return cls(
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            annotations=annotations,
            selector_field=selector_field,
            case_insensitive_selector=case_insensitive,
            timeout_seconds=timeout_seconds,
            proxy_url=proxy_url,
            server=server,
            operations=tuple(operations),
            hidden_tools=hidden_tools,
        )

    def resolve_operation(self, arguments: Mapping[str, Any]) -> OperationMapping:
        selector_value = _lookup_path(arguments, self.selector_field)
        if selector_value is None or not isinstance(selector_value, str):
            field = self.selector_field
            raise ToolAggregationError(
                f"Aggregation '{self.name}' requires field '{field}'"
            )
        for operation in self.operations:
            if operation.matches(selector_value, case_insensitive=self.case_insensitive_selector):
                return operation
        allowed = ", ".join(op.value for op in self.operations)
        raise ToolAggregationError(
            f"Aggregation '{self.name}' does not support operation '{selector_value}'. Allowed: {allowed}"
        )


@dataclass(frozen=True)
class ToolAggregationConfig:
    schema_version: int
    proxy_url: str | None
    defaults: AggregationDefaults
    aggregations: Sequence[AggregatedToolDefinition]
    hidden_tools: Sequence[HiddenTool]

    @classmethod
    def from_data(
        cls,
        payload: Mapping[str, Any],
    ) -> ToolAggregationConfig:
        schema_version = int(payload.get("schemaVersion") or 1)
        defaults = AggregationDefaults.from_data(payload.get("defaults"))
        proxy_url = (
            str(payload.get("proxyURL") or payload.get("proxyUrl") or "").strip()
            or defaults.proxy_url
        )
        aggregations_payload = payload.get("aggregations")
        if not isinstance(aggregations_payload, list) or not aggregations_payload:
            raise ToolAggregationError("config requires at least one aggregation entry")
        aggregations: list[AggregatedToolDefinition] = []
        for item in aggregations_payload:
            if not isinstance(item, Mapping):
                continue
            aggregations.append(AggregatedToolDefinition.from_data(item, defaults))
        if not aggregations:
            raise ToolAggregationError("no valid aggregations found in config")
        hidden_tools = tuple(
            HiddenTool.from_data(item)
            for item in payload.get("hiddenTools", [])
            if isinstance(item, Mapping)
        )
        return cls(
            schema_version=schema_version,
            proxy_url=proxy_url,
            defaults=defaults,
            aggregations=tuple(aggregations),
            hidden_tools=hidden_tools,
        )

    def all_hidden_tools(self) -> list[HiddenTool]:
        entries: list[HiddenTool] = list(self.hidden_tools)
        for aggregation in self.aggregations:
            entries.extend(aggregation.hidden_tools)
        return entries

    def apply_overrides(self, store: ToolOverridesStore) -> bool:
        changed = False
        for hidden in self.all_hidden_tools():
            if store.disable_tool(hidden.server, hidden.tool):
                changed = True
        for aggregation in self.aggregations:
            if store.update_tool_descriptor(
                aggregation.server,
                aggregation.name,
                description=aggregation.description,
                annotations=aggregation.annotations,
                input_schema=aggregation.input_schema,
                output_schema=aggregation.output_schema,
                enabled=True,
            ):
                changed = True
        return changed


class AggregatedToolRunner:
    """Runtime helper that dispatches aggregated tool calls via the proxy."""

    def __init__(
        self,
        definition: AggregatedToolDefinition,
        proxy_call: ProxyCaller,
        *,
        fallback_timeout: float | None = None,
    ) -> None:
        self.definition = definition
        self._proxy_call = proxy_call
        self._fallback_timeout = fallback_timeout

    async def dispatch(self, arguments: Mapping[str, Any] | None) -> Dict[str, Any]:
        payload = arguments if isinstance(arguments, Mapping) else {}
        operation = self.definition.resolve_operation(payload)
        operation.validate_requirements(
            payload,
            label=f"{self.definition.name}:{operation.value}",
        )
        request_args = _evaluate_rules(
            operation.argument_rules,
            payload,
            label=f"{self.definition.name}:{operation.value}",
        )
        timeout = operation.timeout_seconds or self.definition.timeout_seconds or self._fallback_timeout
        result = await self._proxy_call(operation.downstream_tool, request_args, timeout)
        if operation.response_rules:
            return _evaluate_rules(
                operation.response_rules,
                result,
                label=f"{self.definition.name}:{operation.value}:response",
            )
        return result


def load_tool_aggregation_config(
    path: Path,
    *,
    schema_path: Path | None = None,
) -> ToolAggregationConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    schema_candidate = schema_path or path.with_name("tool_aggregations.schema.json")
    _validate_schema(data, schema_candidate)
    return ToolAggregationConfig.from_data(data)


def _lookup_path(data: Mapping[str, Any], path: str) -> Any:
    if path in {"", ".", "$"}:
        return data
    parts = [part for part in path.split(".") if part]
    current: Any = data
    for part in parts:
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return None
    return current


def _assign_path(dest: MutableMapping[str, Any], path: str, value: Any) -> None:
    parts = [part for part in path.split(".") if part]
    if not parts:
        raise ToolAggregationError("mapping rule target must not be empty")
    cursor: MutableMapping[str, Any] = dest
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, MutableMapping):
            next_value = {}
            cursor[part] = next_value
        cursor = next_value  # type: ignore[assignment]
    cursor[parts[-1]] = copy.deepcopy(value)


def _evaluate_rules(
    rules: Sequence[MappingRule],
    data: Mapping[str, Any],
    *,
    label: str,
) -> Dict[str, Any]:
    if not rules:
        return copy.deepcopy(data if isinstance(data, Mapping) else {})
    result: Dict[str, Any] = {}
    for rule in rules:
        value = rule.resolve(data, label=label)
        if value is _SKIP:
            continue
        _assign_path(result, rule.target, value)
    return result


def _normalize_schema(raw: Any, *, allow_empty: bool = False) -> Dict[str, Any] | None:
    if raw is None:
        return None if allow_empty else {"type": "object"}
    if isinstance(raw, Mapping):
        return json.loads(json.dumps(raw))
    if allow_empty:
        return None
    return {"type": "object"}


def _validate_schema(data: Any, schema_path: Path) -> None:
    if not schema_path.exists():
        return
    try:
        import jsonschema  # type: ignore
    except ModuleNotFoundError:
        return
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)
