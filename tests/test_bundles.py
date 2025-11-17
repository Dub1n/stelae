from __future__ import annotations

from stelae_lib.bundles import _write_catalog_fragment


def test_write_catalog_fragment_updates_only_when_changed(tmp_path) -> None:
    target = tmp_path / "bundles" / "starter" / "catalog.json"
    payload = {"name": "starter", "servers": []}
    # First write should report changed.
    assert _write_catalog_fragment(target, payload, dry_run=False) is True
    # Second write with identical payload should be a no-op.
    assert _write_catalog_fragment(target, payload, dry_run=False) is False
    # Changing payload triggers a write.
    payload["servers"] = [{"name": "docs"}]
    assert _write_catalog_fragment(target, payload, dry_run=False) is True
