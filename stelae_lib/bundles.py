from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

from stelae_lib.config_overlays import BUNDLES_DIRNAME, config_home, ensure_parent, write_json
from stelae_lib.integrator.core import StelaeIntegratorService
from stelae_lib.integrator.runner import CommandRunner

ROOT = Path(__file__).resolve().parents[1]

BUNDLE_CATALOG_FILENAME = "catalog.json"
BUNDLE_INSTALL_FILENAME = "install.json"
INSTALL_STATE_FILENAME = "bundle_installs.json"
BUNDLE_DEFAULT_NAME = "bundle"


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


def _write_catalog_fragment(target: Path, payload: Mapping[str, Any], *, dry_run: bool) -> bool:
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if target.exists():
        try:
            if target.read_text(encoding="utf-8") == serialized:
                return False
        except OSError:
            pass
    if dry_run:
        return True
    ensure_parent(target)
    target.write_text(serialized, encoding="utf-8")
    return True


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
    bundle_root = config_home()
    bundle_files_changed_flag = bool(bundle_files_changed)
    fragment_path = catalog_fragment_path
    bundle_label = bundle_name or bundle.get("name") or BUNDLE_DEFAULT_NAME
    if fragment_path is None:
        fragment_path = bundle_root / BUNDLES_DIRNAME / str(bundle_label) / BUNDLE_CATALOG_FILENAME
    fragment_changed = _write_catalog_fragment(fragment_path, bundle, dry_run=dry_run)
    if fragment_changed:
        bundle_files_changed_flag = True
        emit(f"[bundle] {'Would write' if dry_run else 'Wrote'} catalog fragment → {fragment_path}")
    catalog_fragment_path = fragment_path

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
    needs_restart = (installed or overlay_updates or bundle_files_changed_flag) and not errors
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
