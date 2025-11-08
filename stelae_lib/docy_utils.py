"""Shared Docy helpers (source model + file utilities)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

_slug_pattern = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    slug = _slug_pattern.sub("-", text.lower()).strip("-")
    return slug or "source"


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


@dataclass
class DocySource:
    id: str
    url: str
    title: str | None = None
    tags: List[str] = field(default_factory=list)
    notes: str | None = None
    enabled: bool = True
    refresh_hours: int | None = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocySource":
        tags = data.get("tags") or []
        if not isinstance(tags, list):
            raise ValueError("tags must be a list of strings")
        return cls(
            id=str(data["id"]).strip(),
            url=str(data["url"]).strip(),
            title=(str(data["title"]).strip() or None) if data.get("title") else None,
            tags=[str(tag).strip() for tag in tags if str(tag).strip()],
            notes=(str(data["notes"]).strip() or None) if data.get("notes") else None,
            enabled=bool(data.get("enabled", True)),
            refresh_hours=int(data["refresh_hours"]) if data.get("refresh_hours") is not None else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "tags": list(self.tags),
            "notes": self.notes,
            "enabled": self.enabled,
        }
        if self.refresh_hours is not None:
            data["refresh_hours"] = self.refresh_hours
        return data
