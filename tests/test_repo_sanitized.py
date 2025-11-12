import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_env_example_has_no_provider_specific_variables() -> None:
    content = _read(".env.example")
    assert "QDRANT_" not in content
    assert "/home/gabri" not in content
    assert "STELAE_CONFIG_HOME=${HOME}/.config/stelae" in content
    assert "PROXY_CONFIG=${STELAE_CONFIG_HOME}/proxy.json" in content


def test_cloudflared_samples_are_placeholder_only() -> None:
    for rel in ("ops/cloudflared.yml", "ops/cloudflared.yml.example"):
        text = _read(rel)
        assert "<your-" in text, f"{rel} should highlight placeholder values"
        assert "/home/gabri" not in text
        assert "mcp.infotopology.xyz" not in text


def test_tracked_configs_remain_placeholder_only() -> None:
    tracked = (
        "config/tool_overrides.json",
        "config/tool_aggregations.json",
        "config/proxy.template.json",
    )
    for rel in tracked:
        text = _read(rel)
        assert "/home/" not in text, f"{rel} should not bake absolute paths"


def test_proxy_template_only_lists_core_servers() -> None:
    data = json.loads(_read("config/proxy.template.json"))
    core = {"custom", "integrator", "one_mcp", "public_mcp_catalog", "tool_aggregator"}
    assert set(data["mcpServers"].keys()) == core


def test_tool_aggregations_template_contains_defaults() -> None:
    data = json.loads(_read("config/tool_aggregations.json"))
    names = {entry["name"] for entry in data.get("aggregations", [])}
    assert names == {"manage_docy_sources"}
    hidden_servers = {item["server"] for item in data.get("hiddenTools", [])}
    assert "facade" in hidden_servers


def test_tool_overrides_only_core_servers() -> None:
    data = json.loads(_read("config/tool_overrides.json"))
    servers = set(data.get("servers", {}).keys())
    expected = {"integrator", "one_mcp", "public_mcp_catalog", "tool_aggregator", "facade", "docy_manager"}
    assert servers == expected
    agg_tools = set(data["servers"]["tool_aggregator"]["tools"].keys())
    assert agg_tools == {"manage_docy_sources"}
