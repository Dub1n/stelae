from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

from stelae_lib.config_overlays import (
    BUNDLES_DIRNAME,
    config_home,
    deep_merge,
    ensure_parent,
    load_json,
    overlay_path_for,
    write_json,
)
from stelae_lib.integrator.core import StelaeIntegratorService
from stelae_lib.integrator.runner import CommandRunner

ROOT = Path(__file__).resolve().parents[1]

BUNDLE_CATALOG_FILENAME = "catalog.json"
BUNDLE_INSTALL_FILENAME = "install.json"
INSTALL_STATE_FILENAME = "bundle_installs.json"


@dataclass(frozen=True)
class BundleArtifact:
    name: str
    payload: dict[str, Any]
    catalog_path: Path
    format: Literal["folder", "legacy"]
    source_dir: Path | None = None
    install_manifest: Mapping[str, Any] | None = None


@dataclass
class BundleSyncResult:
    destination: Path
    changed: bool


@dataclass
class InstallRefState:
    path: Path
    payload: dict[str, Any]
    dirty: bool = False

    def has(self, ref: str) -> bool:
        normalized = str(ref or "").strip()
        if not normalized:
            return False
        installs = self.payload.get("installs")
        return isinstance(installs, Mapping) and normalized in installs

    def register(
        self,
        ref: str,
        *,
        bundle: str | None,
        source: Path | None,
        description: str | None,
        dry_run: bool,
    ) -> bool:
        normalized = str(ref or "").strip()
        if not normalized:
            return False
        installs = self.payload.setdefault("installs", {})
        if not isinstance(installs, dict):
            installs = {}
            self.payload["installs"] = installs
        if normalized in installs:
            return False
        entry: dict[str, Any] = {
            "bundle": bundle,
            "registeredAt": datetime.now(timezone.utc).isoformat(),
        }
        if source:
            entry["source"] = str(source)
        if description:
            entry["description"] = description
        if dry_run:
            return True
        installs[normalized] = entry
        self.dirty = True
        return True

    def flush(self, *, dry_run: bool) -> None:
        if dry_run or not self.dirty:
            return
        write_json(self.path, self.payload)
        self.dirty = False

DEFAULT_RESTART_COMMANDS: list[list[str]] = [
    ["make", "render-proxy"],
    [str(ROOT / "scripts" / "run_restart_stelae.sh"), "--keep-pm2", "--no-bridge", "--no-cloudflared"],
]


def load_bundle(path: Path) -> BundleArtifact:
    resolved = path.resolve()
    if resolved.is_dir():
        return _load_bundle_from_dir(resolved)
    return _load_bundle_from_file(resolved)


def load_install_state(*, config_base: Path | None = None) -> InstallRefState:
    home = (config_base or config_home()).expanduser()
    path = home / INSTALL_STATE_FILENAME
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {"schemaVersion": 1, "installs": {}}
    if payload.get("schemaVersion") != 1:
        payload = {"schemaVersion": 1, "installs": payload.get("installs", {})}
    installs = payload.get("installs")
    if not isinstance(installs, dict):
        payload["installs"] = {}
    ensure_parent(path)
    return InstallRefState(path=path, payload=payload)


def sync_bundle_folder(
    source_dir: Path,
    bundle_name: str,
    *,
    dry_run: bool = False,
    config_base: Path | None = None,
) -> BundleSyncResult:
    home = (config_base or config_home()).expanduser()
    destination = home / BUNDLES_DIRNAME / bundle_name
    ensure_parent(destination)
    if dry_run:
        return BundleSyncResult(destination=destination, changed=False)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source_dir, destination)
    return BundleSyncResult(destination=destination, changed=True)


def _apply_overlay(base_path: Path, addition: dict[str, Any], *, dry_run: bool) -> tuple[bool, Path]:
    overlay_path = overlay_path_for(base_path)
    existing = load_json(overlay_path, default={})
    merged = deep_merge(existing, addition)
    if merged == existing:
        return False, overlay_path
    if not dry_run:
        write_json(overlay_path, merged)
    return True, overlay_path


def _merge_named_entries(
    existing: list[dict[str, Any]],
    additions: list[dict[str, Any]],
    *,
    key_func: Callable[[dict[str, Any]], str | None],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in additions:
        key = key_func(entry)
        if not key or key in seen:
            continue
        result.append(json.loads(json.dumps(entry, ensure_ascii=False)))
        seen.add(key)
    for entry in existing:
        key = key_func(entry)
        if not key or key in seen:
            continue
        result.append(json.loads(json.dumps(entry, ensure_ascii=False)))
        seen.add(key)
    return result


def _apply_tool_aggregations_overlay(
    base_path: Path,
    addition: dict[str, Any],
    *,
    dry_run: bool,
) -> tuple[bool, Path]:
    overlay_path = overlay_path_for(base_path)
    existing = load_json(overlay_path, default={})
    passthrough_keys = {
        key: value
        for key, value in addition.items()
        if key not in {"aggregations", "hiddenTools"}
    }
    merged = deep_merge(existing, passthrough_keys)
    existing_aggs = existing.get("aggregations", []) if isinstance(existing.get("aggregations"), list) else []
    addition_aggs = addition.get("aggregations", []) if isinstance(addition.get("aggregations"), list) else []
    merged["aggregations"] = _merge_named_entries(
        existing_aggs,
        addition_aggs,
        key_func=lambda entry: str(entry.get("name") or "").strip() or None,
    )
    existing_hidden = (
        existing.get("hiddenTools", []) if isinstance(existing.get("hiddenTools"), list) else []
    )
    addition_hidden = (
        addition.get("hiddenTools", []) if isinstance(addition.get("hiddenTools"), list) else []
    )
    merged["hiddenTools"] = _merge_named_entries(
        existing_hidden,
        addition_hidden,
        key_func=lambda entry: (
            f"{str(entry.get('server') or '').strip()}::{str(entry.get('tool') or '').strip()}"
            if entry.get("server") and entry.get("tool")
            else None
        ),
    )
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
    force: bool = False,
    service_factory: Callable[[], StelaeIntegratorService] = StelaeIntegratorService,
    command_runner: CommandRunner | None = None,
    log: Callable[[str], None] | None = None,
    catalog_fragment_path: Path | None = None,
    bundle_files_changed: bool = False,
    install_state: InstallRefState | None = None,
    install_manifest: Mapping[str, Any] | None = None,
    bundle_name: str | None = None,
    bundle_source: Path | None = None,
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
    install_refs_summary = {"registered": [], "skipped": []}
    seen_install_refs: set[str] = set()
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
        payload = {"descriptor": raw_descriptor, "dry_run": dry_run, "force": force}
        result = service.run("install_server", payload)
        if result.get("status") != "ok":
            errors.append({"name": name, "error": result})
            emit(f"[bundle] ❌ '{name}' failed: {result}")
            continue
        details = result.get("details") or {}
        template_changed = bool(details.get("templateChanged"))
        overrides_changed = bool(details.get("overridesChanged"))
        if not template_changed and not overrides_changed:
            skipped.append(name)
            emit(f"[bundle] '{name}' already up to date")
        else:
            installed.append(name)
            emit(
                f"[bundle] ✅ '{details.get('server', name)}' updated "
                f"(template={template_changed}, overrides={overrides_changed})"
            )

        _register_server_install_ref(
            descriptor=raw_descriptor,
            install_state=install_state,
            summary=install_refs_summary,
            seen=seen_install_refs,
            dry_run=dry_run,
            bundle_name=bundle_name,
            bundle_source=bundle_source,
            log=emit,
        )
    overlay_updates: list[dict[str, Any]] = []
    if catalog_fragment_path is None:
        overrides_payload = bundle.get("toolOverrides")
        if isinstance(overrides_payload, dict) and overrides_payload.get("servers"):
            changed, path = _apply_overlay(ROOT / "config" / "tool_overrides.json", overrides_payload, dry_run=dry_run)
            if changed:
                overlay_updates.append({"path": str(path), "dryRun": dry_run})
                emit(f"[bundle] Overlay updated → {path}")
        aggregations_payload = bundle.get("toolAggregations")
        if isinstance(aggregations_payload, dict) and aggregations_payload.get("aggregations"):
            changed, path = _apply_tool_aggregations_overlay(
                ROOT / "config" / "tool_aggregations.json",
                aggregations_payload,
                dry_run=dry_run,
            )
            if changed:
                overlay_updates.append({"path": str(path), "dryRun": dry_run})
                emit(f"[bundle] Overlay updated → {path}")
    else:
        emit(f"[bundle] Catalog fragment managed via {catalog_fragment_path}")
    if install_manifest:
        _register_manifest_refs(
            install_manifest,
            install_state=install_state,
            summary=install_refs_summary,
            seen=seen_install_refs,
            dry_run=dry_run,
            bundle_name=bundle_name,
            bundle_source=bundle_source,
            log=emit,
        )
    commands_run: list[list[str]] = []
    needs_restart = (installed or overlay_updates or bundle_files_changed) and not errors
    if restart and not dry_run and needs_restart:
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
        "installRefs": install_refs_summary,
    }


def _load_bundle_from_dir(directory: Path) -> BundleArtifact:
    catalog_path = directory / BUNDLE_CATALOG_FILENAME
    payload = _normalize_bundle_payload(_read_json(catalog_path))
    manifest_path = directory / BUNDLE_INSTALL_FILENAME
    install_manifest = _read_json(manifest_path) if manifest_path.exists() else None
    name = _bundle_name(payload, fallback=directory.name)
    return BundleArtifact(
        name=name,
        payload=payload,
        catalog_path=catalog_path,
        format="folder",
        source_dir=directory,
        install_manifest=install_manifest,
    )


def _load_bundle_from_file(path: Path) -> BundleArtifact:
    payload = _read_json(path)
    bundle_ref = payload.get("bundleRef") or payload.get("bundleFolder")
    if isinstance(bundle_ref, str) and bundle_ref.strip():
        target = (path.parent / bundle_ref).resolve()
        if not target.exists():
            raise FileNotFoundError(f"Bundle reference {bundle_ref} not found for {path}")
        return _load_bundle_from_dir(target)
    normalized = _normalize_bundle_payload(payload)
    name = _bundle_name(normalized, fallback=path.stem)
    return BundleArtifact(name=name, payload=normalized, catalog_path=path, format="legacy")


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Bundle {path} must be a JSON object")
    return data


def _normalize_bundle_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = json.loads(json.dumps(payload, ensure_ascii=False))
    data.setdefault("servers", [])
    if not isinstance(data["servers"], list):
        raise ValueError("bundle.servers must be an array")
    return data


def _bundle_name(payload: Mapping[str, Any], *, fallback: str) -> str:
    value = str(payload.get("name") or "").strip()
    return value or fallback


def _register_server_install_ref(
    *,
    descriptor: Mapping[str, Any],
    install_state: InstallRefState | None,
    summary: dict[str, list[str]],
    seen: set[str],
    dry_run: bool,
    bundle_name: str | None,
    bundle_source: Path | None,
    log: Callable[[str], None],
) -> None:
    if not install_state:
        return
    ref = str(descriptor.get("installRef") or "").strip()
    if not ref or ref in seen:
        return
    seen.add(ref)
    description = f"Server '{descriptor.get('name')}'"
    if install_state.has(ref):
        summary["skipped"].append(ref)
        log(f"[bundle] installRef already registered → {ref}")
        return
    if install_state.register(ref, bundle=bundle_name, source=bundle_source, description=description, dry_run=dry_run):
        summary["registered"].append(ref)
        log(f"[bundle] installRef registered → {ref}")


def _register_manifest_refs(
    manifest: Mapping[str, Any],
    *,
    install_state: InstallRefState | None,
    summary: dict[str, list[str]],
    seen: set[str],
    dry_run: bool,
    bundle_name: str | None,
    bundle_source: Path | None,
    log: Callable[[str], None],
) -> None:
    if not install_state:
        return
    entries = manifest.get("installRefs")
    if not isinstance(entries, Sequence):
        return
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        ref = str(entry.get("ref") or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        description = entry.get("description")
        if install_state.has(ref):
            summary["skipped"].append(ref)
            log(f"[bundle] installRef already registered → {ref}")
            continue
        if install_state.register(ref, bundle=bundle_name, source=bundle_source, description=description, dry_run=dry_run):
            summary["registered"].append(ref)
            log(f"[bundle] installRef registered → {ref}")
