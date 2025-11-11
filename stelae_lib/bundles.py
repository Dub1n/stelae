from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable

from stelae_lib.config_overlays import deep_merge, load_json, overlay_path_for, write_json
from stelae_lib.integrator.core import StelaeIntegratorService
from stelae_lib.integrator.runner import CommandRunner

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_RESTART_COMMANDS: list[list[str]] = [
    ["make", "render-proxy"],
    [str(ROOT / "scripts" / "run_restart_stelae.sh"), "--keep-pm2", "--no-bridge", "--no-cloudflared"],
]


def load_bundle(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Bundle {path} must be a JSON object")
    data.setdefault("servers", [])
    if not isinstance(data["servers"], list):
        raise ValueError("bundle.servers must be an array")
    return data


def _apply_overlay(base_path: Path, addition: dict[str, Any], *, dry_run: bool) -> tuple[bool, Path]:
    overlay_path = overlay_path_for(base_path)
    existing = load_json(overlay_path, default={})
    merged = deep_merge(existing, addition)
    if merged == existing:
        return False, overlay_path
    if not dry_run:
        write_json(overlay_path, merged)
    return True, overlay_path


def install_bundle(
    bundle: dict[str, Any],
    *,
    server_filter: Iterable[str] | None = None,
    dry_run: bool = False,
    restart: bool = True,
    service_factory: Callable[[], StelaeIntegratorService] = StelaeIntegratorService,
    command_runner: CommandRunner | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    def emit(message: str) -> None:
        if log:
            log(message)

    filter_set = {name.strip() for name in (server_filter or []) if name and name.strip()}
    service = service_factory()
    if hasattr(service, "default_commands"):
        service.default_commands = []
    runner = command_runner or CommandRunner(ROOT)
    installed: list[str] = []
    skipped: list[str] = []
    errors: list[dict[str, Any]] = []
    for raw_descriptor in bundle.get("servers", []):
        if not isinstance(raw_descriptor, dict):
            continue
        name = str(raw_descriptor.get("name") or "").strip()
        if not name or (filter_set and name not in filter_set):
            if filter_set and name:
                emit(f"[bundle] Skipping '{name}' (filtered)")
            continue
        emit(f"[bundle] Installing '{name}'…")
        payload = {"descriptor": raw_descriptor, "dry_run": dry_run}
        result = service.run("install_server", payload)
        if result.get("status") != "ok":
            errors.append({"name": name, "error": result})
            emit(f"[bundle] ❌ '{name}' failed: {result}")
            continue
        details = result.get("details") or {}
        if not details.get("templateChanged") and not details.get("overridesChanged"):
            skipped.append(name)
            emit(f"[bundle] '{name}' already up to date")
        else:
            installed.append(name)
            emit(
                f"[bundle] ✅ '{details.get('server', name)}' updated "
                f"(template={details.get('templateChanged')}, overrides={details.get('overridesChanged')})"
            )
    overlay_updates: list[dict[str, Any]] = []
    overrides_payload = bundle.get("toolOverrides")
    if isinstance(overrides_payload, dict) and overrides_payload.get("servers"):
        changed, path = _apply_overlay(ROOT / "config" / "tool_overrides.json", overrides_payload, dry_run=dry_run)
        if changed:
            overlay_updates.append({"path": str(path), "dryRun": dry_run})
            emit(f"[bundle] Overlay updated → {path}")
    aggregations_payload = bundle.get("toolAggregations")
    if isinstance(aggregations_payload, dict) and aggregations_payload.get("aggregations"):
        changed, path = _apply_overlay(ROOT / "config" / "tool_aggregations.json", aggregations_payload, dry_run=dry_run)
        if changed:
            overlay_updates.append({"path": str(path), "dryRun": dry_run})
            emit(f"[bundle] Overlay updated → {path}")
    commands_run: list[list[str]] = []
    if restart and not dry_run and (installed or overlay_updates) and not errors:
        for command in DEFAULT_RESTART_COMMANDS:
            result = runner.run(command)
            commands_run.append(result.command if hasattr(result, "command") else list(command))
    return {
        "dryRun": dry_run,
        "installed": installed,
        "skipped": skipped,
        "overlays": overlay_updates,
        "commands": commands_run,
        "errors": errors,
    }
