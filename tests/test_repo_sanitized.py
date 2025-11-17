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
    assert "STELAE_STATE_HOME=${STELAE_CONFIG_HOME}/.state" in content
    assert "STELAE_ENV_FILE=${STELAE_CONFIG_HOME}/.env" in content
    assert "PROXY_CONFIG=${STELAE_STATE_HOME}/proxy.json" in content
    assert "STELAE_TOOL_OVERRIDES=${STELAE_CONFIG_HOME}/tool_overrides.json" in content
    assert "STELAE_TOOL_AGGREGATIONS=${STELAE_CONFIG_HOME}/tool_aggregations.json" in content
    assert "TOOL_OVERRIDES_PATH=${STELAE_STATE_HOME}/tool_overrides.json" in content
    assert "TOOL_SCHEMA_STATUS_PATH=${STELAE_STATE_HOME}/tool_schema_status.json" in content


def test_cloudflared_samples_are_placeholder_only() -> None:
    for rel in ("ops/cloudflared.yml", "ops/cloudflared.yml.example"):
        text = _read(rel)
        assert "<your-" in text, f"{rel} should highlight placeholder values"
        assert "/home/gabri" not in text
        assert "mcp.infotopology.xyz" not in text


def test_tracked_configs_remain_placeholder_only() -> None:
    tracked = ("config/proxy.template.json",)
    for rel in tracked:
        text = _read(rel)
        assert "/home/" not in text, f"{rel} should not bake absolute paths"
    removed = [
        "config/tool_overrides.json",
        "config/tool_aggregations.json",
        "config/custom_tools.json",
        "config/discovered_servers.json",
        "config/tool_schema_status.json",
    ]
    for rel in removed:
        assert not (ROOT / rel).exists(), f"{rel} should no longer be tracked"


def test_proxy_template_only_lists_core_servers() -> None:
    data = json.loads(_read("config/proxy.template.json"))
    core = {"custom", "integrator", "one_mcp", "public_mcp_catalog", "tool_aggregator"}
    assert set(data["mcpServers"].keys()) == core
