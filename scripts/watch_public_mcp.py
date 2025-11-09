# stelae/scripts/watch_public_mcp.py
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PUBLIC = os.environ.get("PUBLIC_BASE_URL", "https://mcp.infotopology.xyz").rstrip("/")
INTERVAL = int(os.environ.get("WATCH_INTERVAL", "60"))
THRESH = int(os.environ.get("FAIL_THRESHOLD", "3"))
CLOUD_FLARE_PM2 = os.environ.get("CF_PM2_NAME", "cloudflared")
ROOT = Path(__file__).resolve().parents[1]
PM2_ECOSYSTEM = Path(os.environ.get("PM2_ECOSYSTEM", str(ROOT / "ecosystem.config.js")))


def post_json(url, payload, timeout=12):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "stelae-watch/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"http {resp.status}")
        body = resp.read()
        return json.loads(body.decode("utf-8"))


def ok():
    # JSON-RPC initialize is a cheap sanity check
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    }
    res = post_json(f"{PUBLIC}/mcp", payload)
    return "result" in res or "jsonrpc" in res


def _pm2_status(name: str) -> str | None:
    try:
        result = subprocess.run(
            ["pm2", "jlist"],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired as exc:
        print(f"watchdog: pm2 jlist timed out after {exc.timeout}s", file=sys.stderr)
        return None
    except Exception as exc:  # pragma: no cover - diagnostic path
        print(f"watchdog: pm2 jlist failed: {exc}", file=sys.stderr)
        return None
    try:
        entries = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        print(f"watchdog: pm2 jlist returned invalid JSON: {exc}", file=sys.stderr)
        return None
    for entry in entries:
        if entry.get("name") == name:
            return entry.get("pm2_env", {}).get("status")
    return None


def _run_pm2(args: list[str], *, allow_error: bool = False, timeout: int = 45) -> bool:
    try:
        subprocess.run(["pm2", *args], check=not allow_error, timeout=timeout)
        return True
    except subprocess.TimeoutExpired as exc:
        print(f"watchdog: pm2 {' '.join(args)} timed out after {exc.timeout}s", file=sys.stderr)
    except subprocess.CalledProcessError as exc:
        if not allow_error:
            print(f"watchdog: pm2 {' '.join(args)} failed: {exc}", file=sys.stderr)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"watchdog: pm2 {' '.join(args)} raised: {exc}", file=sys.stderr)
    return False


def _start_pm2_app(name: str) -> None:
    _run_pm2(["start", str(PM2_ECOSYSTEM), "--only", name])


def _restart_pm2_app(name: str) -> None:
    _run_pm2(["restart", name, "--update-env"])


def _delete_pm2_app(name: str) -> None:
    _run_pm2(["delete", name], allow_error=True)


def ensure_pm2_app(name: str) -> None:
    status = _pm2_status(name)
    if not status:
        print(f"watchdog: pm2 ensure {name}: status=absent -> start", flush=True)
        _start_pm2_app(name)
        return
    if status != "online":
        print(f"watchdog: pm2 ensure {name}: status={status} -> delete+start", flush=True)
        _delete_pm2_app(name)
        _start_pm2_app(name)
        return
    print(f"watchdog: pm2 ensure {name}: status=online -> restart", flush=True)
    _restart_pm2_app(name)


def restart_cloudflared():
    print("watchdog: repairing cloudflared via pm2…", flush=True)
    ensure_pm2_app(CLOUD_FLARE_PM2)


def main():
    fails = 0
    print(
        f"watchdog: watching {PUBLIC}/mcp every {INTERVAL}s; threshold={THRESH}",
        flush=True,
    )
    while True:
        try:
            if ok():
                fails = 0
                print("watchdog: ok", flush=True)
            else:
                fails += 1
                print(f"watchdog: soft-fail {fails}/{THRESH}", flush=True)
        except Exception as e:
            fails += 1
            print(f"watchdog: error {fails}/{THRESH}: {e}", flush=True)
        if fails >= THRESH:
            restart_cloudflared()
            fails = 0
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
