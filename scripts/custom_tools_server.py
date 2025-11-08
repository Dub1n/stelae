#!/usr/bin/env python3
"""Config-driven MCP server that exposes arbitrary scripts as tools.

Each tool is defined in config/custom_tools.json (override via
STELAE_CUSTOM_TOOLS_CONFIG). Every entry specifies the command to run plus
optional args, cwd, env, and timeout. Tool arguments are forwarded as JSON via
stdin (and mirrored in STELAE_TOOL_ARGS) so scripts can inspect them easily.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from mcp.server import FastMCP

CONFIG_PATH = Path(os.getenv("STELAE_CUSTOM_TOOLS_CONFIG", "config/custom_tools.json"))
DEFAULT_INPUT_MODE = "json"  # json (stdin+env) or none

app = FastMCP(
    name="stelae-custom",
    instructions="Custom Stelae tools backed by local scripts.",
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    command: str
    args: List[str]
    cwd: Path | None
    env: Dict[str, str]
    timeout: float | None
    input_mode: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolSpec":
        name = str(data["name"]).strip()
        description = str(data.get("description") or name)
        command = str(data["command"]).strip()
        args = [str(arg) for arg in data.get("args", [])]
        cwd_val = data.get("cwd")
        cwd = Path(cwd_val).resolve() if cwd_val else None
        env = {str(k): str(v) for k, v in (data.get("env") or {}).items()}
        timeout = data.get("timeout")
        if timeout is not None:
            timeout = float(timeout)
        input_mode = str(data.get("inputMode") or DEFAULT_INPUT_MODE).lower()
        if input_mode not in ("json", "none"):
            raise ValueError(f"Unsupported inputMode '{input_mode}' for tool {name}")
        if not name:
            raise ValueError("Tool name cannot be empty")
        if not command:
            raise ValueError(f"Tool {name} is missing a command")
        return cls(name, description, command, args, cwd, env, timeout, input_mode)

    def run(self, arguments: Dict[str, Any]) -> str:
        payload = json.dumps(arguments or {}, ensure_ascii=False)
        env = os.environ.copy()
        env.update(self.env)
        env["STELAE_TOOL_ARGS"] = payload
        stdin_data = payload if self.input_mode == "json" else None
        proc = subprocess.run(
            [self.command, *self.args],
            input=stdin_data,
            text=True,
            capture_output=True,
            cwd=self.cwd,
            env=env,
            timeout=self.timeout,
            check=False,
        )
        if proc.returncode != 0:
            snippet = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(
                f"{self.name} exited with {proc.returncode}: {snippet or 'no output'}"
            )
        output = proc.stdout.strip()
        return output or ""


def _load_specs() -> List[ToolSpec]:
    if not CONFIG_PATH.exists():
        return []
    try:
        spec = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {CONFIG_PATH}: {exc}") from exc
    tools = []
    for entry in spec.get("tools", []):
        try:
            tools.append(ToolSpec.from_dict(entry))
        except Exception as exc:
            raise SystemExit(f"Invalid tool entry {entry!r}: {exc}") from exc
    return tools


def _register_tools(specs: Iterable[ToolSpec]) -> None:
    for spec in specs:
        app.tool(name=spec.name, description=spec.description)(_make_runner(spec))


def _make_runner(spec: ToolSpec):
    async def _runner(**arguments: Any) -> str:
        return spec.run(arguments)

    return _runner


def main() -> None:
    specs = _load_specs()
    if not specs:
        app.logger.warning(
            "No custom tools configured; edit %s to register commands", CONFIG_PATH
        )
    _register_tools(specs)
    app.run()


if __name__ == "__main__":
    main()
