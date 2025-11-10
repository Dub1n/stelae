from __future__ import annotations

from pathlib import Path

from stelae_lib.config_overlays import load_layered_env, parse_env_file


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
