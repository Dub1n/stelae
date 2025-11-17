from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib import config_overlays
from stelae_lib.catalog.store import load_catalog_store
from stelae_lib.config_overlays import config_home


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_catalog_store_merges_fragments_and_bundles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config-home"
    core_payload = {
        "tool_overrides": {"servers": {"demo": {"tools": {"alpha": {"enabled": True}}}}},
        "tool_aggregations": {
            "aggregations": [
                {
                    "name": "demo_aggregate",
                    "description": "Demo aggregate",
                    "inputSchema": {"type": "object"},
                    "operations": [
                        {
                            "value": "ping",
                            "downstreamTool": "demo_tool",
                            "argumentMappings": [{"target": "operation", "value": "ping"}],
                        }
                    ],
                }
            ],
        },
        "hide_tools": [{"server": "demo", "tool": "alpha", "reason": "wrapped"}],
    }
    extras_payload = {
        "tool_overrides": {"servers": {"demo": {"tools": {"beta": {"enabled": False}}}}},
        "tool_aggregations": {
            "hiddenTools": [{"server": "demo", "tool": "legacy"}],
        },
    }
    bundle_payload = {
        "tool_aggregations": {
            "aggregations": [
                {
                    "name": "bundle_tool",
                    "description": "Bundle aggregate",
                    "inputSchema": {"type": "object"},
                    "operations": [
                        {
                            "value": "status",
                            "downstreamTool": "bundle_status",
                            "argumentMappings": [{"target": "operation", "value": "status"}],
                        }
                    ],
                }
            ],
        },
        "hide_tools": [{"server": "bundle", "tool": "shim"}],
    }
    bundle_two_payload = {
        "tool_aggregations": {
            "aggregations": [
                {
                    "name": "bundle_two_tool",
                    "description": "Second bundle aggregate",
                    "inputSchema": {"type": "object"},
                    "operations": [
                        {
                            "value": "status",
                            "downstreamTool": "bundle_two_status",
                            "argumentMappings": [{"target": "operation", "value": "status"}],
                        }
                    ],
                }
            ],
        },
    }
    duplicate_payload = {
        "tool_aggregations": {
            "aggregations": [
                {
                    "name": "bundle_duplicate",
                    "inputSchema": {"type": "object"},
                    "operations": [],
                }
            ]
        }
    }

    _write(config_dir / "catalog" / "core.json", core_payload)
    _write(config_dir / "catalog" / "extras.json", extras_payload)
    _write(config_dir / "bundles" / "bundle-one" / "catalog.json", bundle_payload)
    _write(config_dir / "catalog" / "bundles" / "bundle-two" / "catalog.json", bundle_two_payload)
    _write(config_dir / "catalog" / "bundles" / "bundle-one" / "catalog.json", duplicate_payload)

    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_dir))
    config_home.cache_clear()
    store = load_catalog_store()
    config_home.cache_clear()

    assert store.tool_overrides["servers"]["demo"]["tools"]["alpha"]["enabled"] is True
    assert store.tool_overrides["servers"]["demo"]["tools"]["beta"]["enabled"] is False

    aggregation_names = {entry["name"] for entry in store.tool_aggregations.get("aggregations", [])}
    assert {"demo_aggregate", "bundle_tool", "bundle_two_tool"}.issubset(aggregation_names)
    assert "bundle_duplicate" not in aggregation_names

    hidden_pairs = {(entry["server"], entry["tool"]) for entry in store.hide_tools}
    assert ("demo", "legacy") in hidden_pairs
    assert ("bundle", "shim") in hidden_pairs
    assert any(fragment.kind == "bundle" for fragment in store.fragments)


def test_catalog_store_uses_defaults_when_no_fragments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config-home"
    (config_dir / "catalog").mkdir(parents=True)

    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_dir))
    config_home.cache_clear()
    store = load_catalog_store()
    config_home.cache_clear()

    integrator = store.tool_overrides["servers"]["integrator"]
    assert integrator["enabled"] is True
    assert store.tool_aggregations.get("aggregations") == []
    assert store.fragments[0].kind == "embedded-defaults"


def test_catalog_store_respects_server_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config-home"
    (config_dir / "catalog").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_dir))
    monkeypatch.setenv("STELAE_ONE_MCP_VISIBLE", "false")
    monkeypatch.setenv("STELAE_FACADE_VISIBLE", "false")
    config_home.cache_clear()
    store = load_catalog_store()
    config_home.cache_clear()

    one_mcp = store.tool_overrides.get("servers", {}).get("one_mcp", {})
    assert one_mcp.get("enabled") is False
    facade = store.tool_overrides.get("servers", {}).get("facade", {})
    assert facade.get("enabled") is False
