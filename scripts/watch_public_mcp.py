# stelae/scripts/watch_public_mcp.py
#!/usr/bin/env python3
import os
import time
import subprocess
import json
import sys
import urllib.request

PUBLIC = os.environ.get("PUBLIC_BASE_URL", "https://mcp.infotopology.xyz").rstrip("/")
INTERVAL = int(os.environ.get("WATCH_INTERVAL", "60"))
THRESH = int(os.environ.get("FAIL_THRESHOLD", "3"))
CLOUD_FLARE_PM2 = os.environ.get("CF_PM2_NAME", "cloudflared")


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


def restart_cloudflared():
    print("watchdog: restarting cloudflared via pm2…", flush=True)
    try:
        subprocess.run(["pm2", "restart", CLOUD_FLARE_PM2], check=True)
    except Exception as e:
        print(f"watchdog: pm2 restart failed: {e}", file=sys.stderr)


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
