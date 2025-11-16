from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

from stelae_lib import config_overlays
from stelae_lib.integrator.tool_aggregations import (
    ToolAggregationConfig,
    load_tool_aggregation_config,
)
from stelae_lib.integrator.tool_overrides import ToolOverridesStore


@dataclass(frozen=True)
class AggregationFixture:
    runtime_payload: Dict[str, Any]
    runtime_path: Path


_TOOL_OVERRIDES_CACHE: Dict[str, Any] | None = None
_STARTER_BUNDLE_CACHE: Dict[str, Any] | None = None
_STARTER_BUNDLE_AGGREGATIONS: ToolAggregationConfig | None = None


def build_sample_runtime(tmp_path: Path) -> AggregationFixture:
    config_root = tmp_path / "config-home"
    prev_config_home = os.environ.get("STELAE_CONFIG_HOME")
    os.environ["STELAE_CONFIG_HOME"] = str(config_root)
    config_overlays.config_home.cache_clear()
    config_overlays.state_home.cache_clear()

    try:
        repo_config = tmp_path / "config"
        repo_config.mkdir(parents=True, exist_ok=True)
        overrides_path = repo_config / "tool_overrides.json"
        overrides_path.write_text(json.dumps(_base_overrides(), indent=2), encoding="utf-8")

        aggregation_path = repo_config / "tool_aggregations.json"
        aggregation_path.write_text(json.dumps(_aggregation_payload(), indent=2), encoding="utf-8")

        overlay_path = config_root / "tool_overrides.local.json"
        runtime_path = config_root / "tool_overrides.json"
        overlay_path.parent.mkdir(parents=True, exist_ok=True)

        store = ToolOverridesStore(
            overrides_path,
            overlay_path=overlay_path,
            runtime_path=runtime_path,
            target="overlay",
        )
        config = load_tool_aggregation_config(aggregation_path)
        changed = config.apply_overrides(store)
        assert changed, "Expected aggregation config to update overrides"
        store.write()

        runtime_payload = json.loads(runtime_path.read_text(encoding="utf-8"))
        return AggregationFixture(runtime_payload=runtime_payload, runtime_path=runtime_path)
    finally:
        if prev_config_home is None:
            os.environ.pop("STELAE_CONFIG_HOME", None)
        else:
            os.environ["STELAE_CONFIG_HOME"] = prev_config_home
        config_overlays.config_home.cache_clear()
        config_overlays.state_home.cache_clear()


def _base_overrides() -> Dict[str, Any]:
    return {
        "schemaVersion": 2,
        "master": {"tools": {"*": {"annotations": {}}}},
        "servers": {
            "tool_aggregator": {
                "enabled": True,
                "tools": {
                    "doc_fetch_suite": {
                        "description": "Doc fetch aggregate (base)",
                        "enabled": True,
                        "inputSchema": {
                            "type": "object",
                            "required": ["operation"],
                            "properties": {
                                "operation": {
                                    "type": "string",
                                    "enum": [
                                        "fetch_document_links",
                                        "fetch_documentation_page",
                                    ],
                                }
                            },
                        },
                    }
                },
            },
            "docs": {
                "enabled": True,
                "tools": {
                    "fetch_document_links": {"enabled": True},
                    "fetch_documentation_page": {"enabled": True},
                },
            },
        },
    }


def _aggregation_payload() -> Dict[str, Any]:
    return {
        "schemaVersion": 1,
        "aggregations": [
            {
                "name": "doc_fetch_suite",
                "description": "Docy fetch helpers (overlay)",
                "inputSchema": {
                    "type": "object",
                    "required": ["operation"],
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": [
                                "fetch_document_links",
                                "fetch_documentation_page",
                            ],
                        }
                    },
                },
                "operations": [
                    {
                        "value": "fetch_document_links",
                        "downstreamTool": "fetch_document_links",
                    },
                    {
                        "value": "fetch_documentation_page",
                        "downstreamTool": "fetch_documentation_page",
                    },
                ],
                "hideTools": [
                    {
                        "server": "docs",
                        "tool": "fetch_document_links",
                        "reason": "Wrapped by doc_fetch_suite",
                    },
                    {
                        "server": "docs",
                        "tool": "fetch_documentation_page",
                        "reason": "Wrapped by doc_fetch_suite",
                    },
                ],
            }
        ],
    }


def load_tool_overrides() -> Dict[str, Any]:
    global _TOOL_OVERRIDES_CACHE
    if _TOOL_OVERRIDES_CACHE is None:
        path = Path("config/tool_overrides.json")
        _TOOL_OVERRIDES_CACHE = json.loads(path.read_text(encoding="utf-8"))
    return json.loads(json.dumps(_TOOL_OVERRIDES_CACHE, ensure_ascii=False))


def _load_starter_bundle_payload() -> Dict[str, Any]:
    global _STARTER_BUNDLE_CACHE
    if _STARTER_BUNDLE_CACHE is None:
        path = Path("config/bundles/starter_bundle.json")
        _STARTER_BUNDLE_CACHE = json.loads(path.read_text(encoding="utf-8"))
    return json.loads(json.dumps(_STARTER_BUNDLE_CACHE, ensure_ascii=False))


def get_starter_bundle_aggregation(name: str):
    global _STARTER_BUNDLE_AGGREGATIONS
    if _STARTER_BUNDLE_AGGREGATIONS is None:
        bundle = _load_starter_bundle_payload()
        payload = bundle.get("toolAggregations")
        if not isinstance(payload, Mapping):
            raise KeyError("starter bundle missing toolAggregations payload")
        _STARTER_BUNDLE_AGGREGATIONS = ToolAggregationConfig.from_data(payload)
    for aggregation in _STARTER_BUNDLE_AGGREGATIONS.aggregations:
        if aggregation.name == name:
            return aggregation
    raise KeyError(f"Aggregation '{name}' not found in starter bundle")


def get_tool_schema(server: str, tool: str, *, schema_key: str = "outputSchema") -> Dict[str, Any]:
    overrides = load_tool_overrides()
    server_block = overrides.get("servers", {}).get(server)
    if not isinstance(server_block, dict):
        raise KeyError(f"Server '{server}' not found in tool overrides")
    tool_block = server_block.get("tools", {}).get(tool)
    if not isinstance(tool_block, dict):
        raise KeyError(f"Tool '{tool}' not found under server '{server}'")
    schema = tool_block.get(schema_key)
    if not isinstance(schema, dict):
        raise KeyError(
            f"Schema '{schema_key}' missing for {server}.{tool}. "
            "Add one to config/tool_overrides.json so tests can validate structured responses."
        )
    return json.loads(json.dumps(schema, ensure_ascii=False))


def build_sample_from_schema(schema: Mapping[str, Any] | None) -> Any:
    if not isinstance(schema, Mapping):
        return schema
    if "const" in schema:
        return schema["const"]
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]
    if "anyOf" in schema:
        for candidate in schema["anyOf"]:
            sample = build_sample_from_schema(candidate)
            if sample is not None:
                return sample
    if "oneOf" in schema:
        return build_sample_from_schema(schema["oneOf"][0])
    if "allOf" in schema:
        merged: Dict[str, Any] = {}
        for fragment in schema["allOf"]:
            sample = build_sample_from_schema(fragment)
            if isinstance(sample, dict):
                merged.update(sample)
            elif sample is not None:
                return sample
        return merged

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((entry for entry in schema_type if entry != "null"), schema_type[0])

    if schema_type == "object" or "properties" in schema or "additionalProperties" in schema:
        result: Dict[str, Any] = {}
        properties = schema.get("properties")
        required = schema.get("required")
        keys: list[str] = []
        if isinstance(required, list) and required:
            keys = [key for key in required if isinstance(key, str)]
        elif isinstance(properties, Mapping):
            keys = [key for key in properties.keys()]
        for key in keys:
            subschema = properties.get(key) if isinstance(properties, Mapping) else None
            if isinstance(subschema, Mapping):
                result[key] = build_sample_from_schema(subschema)
            else:
                result[key] = "value"
        if not result:
            additional = schema.get("additionalProperties")
            if isinstance(additional, Mapping):
                result["example"] = build_sample_from_schema(additional)
            elif additional:
                result["example"] = "value"
        return result

    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, list) and items:
            sample_items = [build_sample_from_schema(items[0])]
        elif isinstance(items, Mapping):
            sample_items = [build_sample_from_schema(items)]
        else:
            sample_items = ["value"]
        min_items = schema.get("minItems")
        if isinstance(min_items, int):
            while len(sample_items) < min_items:
                sample_items.append(sample_items[-1])
        return sample_items

    if schema_type == "integer":
        default = schema.get("default")
        if isinstance(default, int):
            return default
        minimum = schema.get("minimum")
        if isinstance(minimum, int):
            return minimum
        return 1

    if schema_type == "number":
        default = schema.get("default")
        if isinstance(default, (int, float)):
            return default
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)):
            return minimum
        return 1.0

    if schema_type == "boolean":
        default = schema.get("default")
        if isinstance(default, bool):
            return default
        return True

    if schema_type == "null":
        return None

    # Strings and fallbacks
    default = schema.get("default")
    if isinstance(default, str):
        return default
    return "value"
