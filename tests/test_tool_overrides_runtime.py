import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_manifest(url: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    data = resp.read()
                    return json.loads(data)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"manifest endpoint {url} not ready: {last_error}")


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=2.0) as resp:
        return json.loads(resp.read())


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        return json.loads(resp.read())


def test_manifest_and_tools_list_respect_overrides(tmp_path: Path) -> None:
    repo_root = Path.home() / "apps" / "mcp-proxy"
    binary_path = tmp_path / "mcp-proxy-test"
    subprocess.run(
        ["go", "build", "-o", str(binary_path), "."],
        cwd=repo_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    overrides = {
        "schemaVersion": 2,
        "master": {
            "tools": {
                "*": {
                    "annotations": {"openWorldHint": True}
                }
            }
        },
        "servers": {
            "facade": {
                "tools": {
                    "search": {
                        "name": "stelae_search",
                        "description": "Search across configured MCP servers.",
                    },
                    "fetch": {
                        "description": "Fetch a cached document by id.",
                    },
                }
            }
        },
    }
    overrides_path = tmp_path / "overrides.json"
    overrides_path.write_text(json.dumps(overrides), encoding="utf-8")

    config = {
        "mcpProxy": {
            "baseURL": base_url,
            "addr": f"127.0.0.1:{port}",
            "name": "test-proxy",
            "version": "1.0.0",
            "type": "streamable-http"
        },
        "manifest": {
            "name": "test",
            "version": "1.0.0",
            "description": "test manifest",
            "sseEndpoint": "/stream",
            "serverName": "test",
            "toolOverridesPath": str(overrides_path)
        },
        "mcpServers": {}
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    process = subprocess.Popen(
        [str(binary_path), "--config", str(config_path)],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        manifest_url = f"{base_url}/.well-known/mcp/manifest.json"
        manifest = _wait_for_manifest(manifest_url)

        tool_names = {tool["name"] for tool in manifest.get("tools", [])}
        assert "stelae_search" in tool_names
        assert "search" not in tool_names

        search_tool = next(tool for tool in manifest["tools"] if tool["name"] == "stelae_search")
        assert search_tool.get("description") == "Search across configured MCP servers."

        tools_list = _fetch_json(f"{base_url}/tools/list")
        listed_names = {tool["name"] for tool in tools_list.get("tools", [])}
        assert "stelae_search" in listed_names

        rpc_response = _post_json(
            f"{base_url}/mcp",
            {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {
                    "name": "stelae_search",
                    "arguments": {"query": "status"}
                }
            },
        )
        assert rpc_response.get("id") == "1"
        assert "result" in rpc_response
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
