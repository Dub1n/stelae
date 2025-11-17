from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.config_overlays import (
    config_home,
    ensure_bundle_catalog,
    ensure_config_home_scaffold,
    ensure_overlay_from_defaults,
    load_layered_env,
    parse_env_file,
    server_enabled,
    state_home,
)


def test_parse_env_file_handles_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.env"
    assert parse_env_file(missing) == {}


def test_load_layered_env_merges_layers(tmp_path: Path, monkeypatch) -> None:
    fallback = tmp_path / ".env.example"
    fallback.write_text(
        "SHARED=from_example\n"
        "EXPAND=${SHARED}/suffix\n",
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SHARED=from_env\n"
        "LOCAL_ONLY=value\n"
        "CHAIN=${EXPAND}:${LOCAL_ONLY}\n",
        encoding="utf-8",
    )
    overlay = tmp_path / ".env.local"
    overlay.write_text("LOCAL_ONLY=override\n", encoding="utf-8")
    monkeypatch.setenv("PROCESS_ONLY", "proc")

    values = load_layered_env(
        env_file=env_file,
        fallback_file=fallback,
        overlay_file=overlay,
        include_process_env=True,
    )

    assert values["SHARED"] == "from_env"
    assert values["EXPAND"] == "from_env/suffix"
    assert values["CHAIN"] == "from_env/suffix:override"
    assert values["PROCESS_ONLY"] == "proc"


def test_load_layered_env_allows_unresolved(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CF_PUBLIC_HOSTNAME=${HOST}\nCF_TUNNEL_UUID=${UUID}\n",
        encoding="utf-8",
    )

    values = load_layered_env(
        env_file=env_file,
        include_process_env=False,
        allow_unresolved=True,
    )

    assert values["CF_PUBLIC_HOSTNAME"] == ""
    assert values["CF_TUNNEL_UUID"] == ""


def test_ensure_config_scaffolding_creates_placeholders(monkeypatch, tmp_path: Path) -> None:
    config_root = tmp_path / "config-home"
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_root))
    config_home.cache_clear()
    state_home.cache_clear()

    ensure_config_home_scaffold()
    catalog_core = config_root / "catalog" / "core.json"
    bundles_placeholder = config_root / "bundles" / ".placeholder.json"
    assert json.loads(catalog_core.read_text(encoding="utf-8")) == {}
    assert json.loads(bundles_placeholder.read_text(encoding="utf-8")) == {}

    bundle_stub = ensure_bundle_catalog("starter_bundle")
    assert bundle_stub == config_root / "bundles" / "starter_bundle" / "catalog.json"
    assert json.loads(bundle_stub.read_text(encoding="utf-8")) == {}

    config_home.cache_clear()
    state_home.cache_clear()


def test_materialize_overlay_from_defaults(monkeypatch, tmp_path: Path) -> None:
    config_root = tmp_path / "config-home"
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_root))
    config_home.cache_clear()
    state_home.cache_clear()

    target = ensure_overlay_from_defaults(Path("config/demo.json"), {"value": 1})
    assert target == config_root / "demo.local.json"
    assert json.loads(target.read_text(encoding="utf-8")) == {"value": 1}

    target.write_text(json.dumps({"value": 2}), encoding="utf-8")
    ensure_overlay_from_defaults(Path("config/demo.json"), {"value": 3})
    assert json.loads(target.read_text(encoding="utf-8")) == {"value": 2}


def test_server_enabled_uses_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STELAE_ONE_MCP_VISIBLE", "false")
    monkeypatch.setenv("STELAE_FACADE_VISIBLE", "0")
    assert server_enabled("one_mcp") is False
    assert server_enabled("facade") is False
    assert server_enabled("integrator") is True
