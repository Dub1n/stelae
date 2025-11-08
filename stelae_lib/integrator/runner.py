from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass
class CommandResult:
    command: List[str]
    status: str
    output: str
    returncode: int | None


class CommandFailed(RuntimeError):
    def __init__(self, result: CommandResult):
        cmd = " ".join(result.command)
        super().__init__(f"Command '{cmd}' failed with exit code {result.returncode}")
        self.result = result


class CommandRunner:
    def __init__(self, cwd: Path):
        self.cwd = cwd

    def run(self, command: Sequence[str], *, env: dict[str, str] | None = None, dry_run: bool = False) -> CommandResult:
        cmd_list = list(command)
        if dry_run:
            return CommandResult(command=cmd_list, status="skipped", output="dry-run", returncode=None)
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        proc = subprocess.run(
            cmd_list,
            cwd=self.cwd,
            capture_output=True,
            text=True,
            env=merged_env,
            check=False,
        )
        output = "".join(filter(None, [proc.stdout, proc.stderr]))
        status = "ok" if proc.returncode == 0 else "failed"
        result = CommandResult(command=cmd_list, status=status, output=output, returncode=proc.returncode)
        if proc.returncode != 0:
            raise CommandFailed(result)
        return result

    def sequence(self, commands: Iterable[Sequence[str]], *, env: dict[str, str] | None = None, dry_run: bool = False) -> List[CommandResult]:
        results: List[CommandResult] = []
        for command in commands:
            results.append(self.run(command, env=env, dry_run=dry_run))
        return results

