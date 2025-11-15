from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from stelae_lib import config_overlays
from stelae_lib.integrator.tool_aggregations import load_tool_aggregation_config
from stelae_lib.integrator.tool_overrides import ToolOverridesStore


@dataclass(frozen=True)
class AggregationFixture:
    runtime_payload: Dict[str, Any]
    runtime_path: Path


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
