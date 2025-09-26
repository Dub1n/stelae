#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_PROXY = Path.home() / "dev" / "stelae" / "config" / "proxy.json"

def load_json(p: Path) -> Dict[str, Any]:
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"[reconciler] missing proxy config: {p}")
    except json.JSONDecodeError as e:
        sys.exit(f"[reconciler] invalid json in {p}: {e}")

def write_json_atomic(p: Path, data: Dict[str, Any]) -> None:
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=p.name, dir=str(p.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, p)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

def ensure_clients(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "clients" not in obj or not isinstance(obj["clients"], list):
        obj["clients"] = []
    return obj["clients"]

def stanza_exists(clients: List[Dict[str, Any]], name: str) -> bool:
    return any(c.get("name") == name for c in clients)

def build_stdio_client(name: str, command: str, args: Optional[List[str]], namespace: Optional[str]) -> Dict[str, Any]:
    stanza = {
        "name": name,
        "type": "stdio",
        "command": command,
    }
    if args:
        stanza["args"] = args
    if namespace:
        stanza["namespace"] = namespace
    return stanza

def build_http_client(name: str, url: str, namespace: Optional[str]) -> Dict[str, Any]:
    stanza = {
        "name": name,
        "type": "sse",
        "url": url,
    }
    if namespace:
        stanza["namespace"] = namespace
    return stanza

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promote an MCP into mcp-proxy (dry-run by default)."
    )
    parser.add_argument("--proxy", default=str(DEFAULT_PROXY), help="Path to proxy.json")
    parser.add_argument("--name", required=True, help="Client name to register (e.g., 'rg', 'fs', 'fetch')")
    parser.add_argument("--target", choices=["core", "strata"], default="core", help="Surface to promote into (metadata only for 'strata' currently)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stdio", action="store_true", help="Register a stdio client")
    mode.add_argument("--http", action="store_true", help="Register an SSE/HTTP client")
    parser.add_argument("--command", help="Binary path for stdio client")
    parser.add_argument("--args", nargs="*", help="Args for stdio client")
    parser.add_argument("--url", help="Endpoint URL for http/sse client")
    parser.add_argument("--namespace", help="Namespace for the client (optional)")
    parser.add_argument("--apply", action="store_true", help="Write changes (otherwise dry-run)")
    args = parser.parse_args()

    proxy_path = Path(args.proxy)
    cfg = load_json(proxy_path)
    clients = ensure_clients(cfg)

    if stanza_exists(clients, args.name):
        print(f"[reconciler] '{args.name}' already present. no changes.")
        sys.exit(0)

    if args.stdio:
        if not args.command:
            sys.exit("[reconciler] --stdio requires --command")
        new_client = build_stdio_client(args.name, args.command, args.args, args.namespace)
    else:
        if not args.url:
            sys.exit("[reconciler] --http requires --url")
        new_client = build_http_client(args.name, args.url, args.namespace)

    print("[reconciler] plan:")
    print(json.dumps(new_client, indent=2))

    if not args.apply:
        print("\n[dry-run] no writes performed. add --apply to persist.")
        return

    clients.append(new_client)
    write_json_atomic(proxy_path, cfg)
    print(f"[reconciler] wrote {proxy_path}. restart proxy to apply.")

if __name__ == "__main__":
    main()