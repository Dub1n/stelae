from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

CATALOG_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "qdrant": {
        "descriptor": {
            "transport": "stdio",
            "command": "uvx",
            "args": ["mcp-server-qdrant", "--transport", "stdio"],
            "env": {
                "COLLECTION_NAME": "{{QDRANT_COLLECTION_NAME}}",
                "QDRANT_LOCAL_PATH": "{{QDRANT_LOCAL_PATH}}",
                "EMBEDDING_MODEL": "{{QDRANT_EMBEDDING_MODEL}}",
            },
            "options": {
                "hydratedFrom": "catalog_overrides",
            },
        },
        "env_defaults": {
            "QDRANT_LOCAL_PATH": "${STELAE_DIR}/var/qdrant",
            "QDRANT_COLLECTION_NAME": "your-qdrant-collection",
            "QDRANT_EMBEDDING_MODEL": "sentence-transformers/all-MiniLM-L6-v2",
        },
    }
}


def _deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in source.items():
        if isinstance(value, dict):
            child = target.setdefault(key, {})
            if isinstance(child, dict):
                _deep_merge(child, value)
            else:
                target[key] = deepcopy(value)
        else:
            target[key] = deepcopy(value)
    return target


def hydrate_descriptor(payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, str]]:
    name = str(payload.get("name") or "").strip().lower()
    override = CATALOG_OVERRIDES.get(name)
    if not override:
        return payload, {}

    descriptor_override = override.get("descriptor") or override
    env_defaults = override.get("env_defaults", {})

    hydrated = deepcopy(payload)
    _deep_merge(hydrated, descriptor_override)
    metadata = hydrated.setdefault("options", {})
    metadata.setdefault("hydrated", True)
    metadata.setdefault(
        "hydratedFrom",
        descriptor_override.get("options", {}).get("hydratedFrom", "catalog_overrides"),
    )
    return hydrated, env_defaults.copy()
