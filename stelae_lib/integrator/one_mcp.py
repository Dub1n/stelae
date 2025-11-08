from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List


class OneMCPDiscoveryError(RuntimeError):
    pass


@dataclass
class DiscoveryResult:
    name: str
    description: str
    url: str
    score: float | None = None

    def to_entry(self, query: str | None = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.slug,
            "transport": "metadata",
            "description": self.description,
            "source": self.url,
            "options": {
                "sourceType": "1mcp-search",
                "originalName": self.name,
            },
            "tools": [],
        }
        if self.score is not None:
            payload["options"]["score"] = self.score
        if query:
            payload["options"]["query"] = query
        return payload

    @property
    def slug(self) -> str:
        base = self.name.strip().lower()
        if not base:
            base = "server"
        slug = "".join(ch if ch.isalnum() else "-" for ch in base)
        slug = slug.strip("-") or "server"
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug


class OneMCPDiscovery:
    def __init__(self, repo_path: Path | None = None) -> None:
        default = Path(os.getenv("ONE_MCP_DIR", str(Path.home() / "apps" / "vendor" / "1mcpserver")))
        self.repo_path = repo_path or default
        if not self.repo_path.exists():
            raise OneMCPDiscoveryError(f"1mcp repo not found at {self.repo_path}")
        self._ensure_path()
        try:
            self._backend = importlib.import_module("search_backend")
        except ModuleNotFoundError as exc:  # pragma: no cover - import guard
            raise OneMCPDiscoveryError("Unable to import search_backend from 1mcp repo") from exc

    def _ensure_path(self) -> None:
        repo_str = str(self.repo_path)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)

    def search(
        self,
        query: str,
        *,
        limit: int = 25,
        min_score: float | None = None,
    ) -> List[DiscoveryResult]:
        normalized_query = query.strip() or "mcp"
        matches: Iterable[Dict[str, Any]] = self._backend.search(normalized_query, top_k=limit)
        results: List[DiscoveryResult] = []
        for match in matches:
            score = match.get("score")
            if min_score is not None and score is not None and score < min_score:
                continue
            results.append(
                DiscoveryResult(
                    name=str(match.get("name") or "server"),
                    description=str(match.get("description") or ""),
                    url=str(match.get("url") or ""),
                    score=score,
                )
            )
        return results

