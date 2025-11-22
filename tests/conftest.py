import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from stelae_lib import config_overlays  # noqa: E402


@pytest.fixture(autouse=True)
def reset_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate config/state env between tests."""

    for var in (
        "STELAE_CONFIG_HOME",
        "STELAE_STATE_HOME",
        "STELAE_TOOL_OVERRIDES",
        "STELAE_TOOL_AGGREGATIONS",
        "STELAE_CUSTOM_TOOLS_CONFIG",
        "STELAE_DISCOVERY_PATH",
        "TOOL_OVERRIDES_PATH",
        "TOOL_SCHEMA_STATUS_PATH",
        "INTENDED_CATALOG_PATH",
        "LIVE_CATALOG_PATH",
        "LIVE_DESCRIPTORS_PATH",
    ):
        monkeypatch.delenv(var, raising=False)
    config_overlays.config_home.cache_clear()
    config_overlays.state_home.cache_clear()
