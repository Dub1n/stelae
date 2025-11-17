import os

import pytest


@pytest.fixture(autouse=True)
def clear_stelae_env(monkeypatch: pytest.MonkeyPatch):
    """Prevent host STELAE_* env vars from leaking into tests."""

    for key in [
        "STELAE_CONFIG_HOME",
        "STELAE_STATE_HOME",
        "STELAE_ENV_FILE",
        "STELAE_CUSTOM_TOOLS_CONFIG",
        "STELAE_TOOL_OVERRIDES",
        "STELAE_TOOL_AGGREGATIONS",
        "TOOL_OVERRIDES_PATH",
        "TOOL_SCHEMA_STATUS_PATH",
        "STELAE_DISCOVERY_PATH",
        "INTENDED_CATALOG_PATH",
        "LIVE_CATALOG_PATH",
    ]:
        if key in os.environ:
            monkeypatch.delenv(key, raising=False)
