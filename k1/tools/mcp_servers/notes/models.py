"""
k1.tools.mcp_servers.notes.models -- Note data models.

Frozen dataclasses for note storage. Immutable after construction.

References:
  - notes_list.yaml, notes_create.yaml, notes_search.yaml
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class Note:
    """
    A single note with title, content, and optional tags.

    Matches the output schemas across all notes contracts.
    """

    note_id: str = ""
    title: str = ""
    content: str = ""
    tags: Tuple[str, ...] = ()
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.note_id:
            object.__setattr__(self, "note_id", str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict matching contract output schema."""
        return {
            "note_id": self.note_id,
            "title": self.title,
            "content": self.content,
            "tags": list(self.tags),
            "created_at": self.created_at,
        }

    def to_summary(self) -> Dict[str, Any]:
        """Summary dict for list responses (no content)."""
        return {
            "note_id": self.note_id,
            "title": self.title,
            "tags": list(self.tags),
            "created_at": self.created_at,
        }

    def to_search_result(self, snippet: str = "") -> Dict[str, Any]:
        """Search result dict with content snippet."""
        return {
            "note_id": self.note_id,
            "title": self.title,
            "snippet": snippet or self.content[:100],
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Note":
        """Construct from dict."""
        tags = data.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        return cls(
            note_id=data.get("note_id", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            tags=tuple(tags),
            created_at=data.get("created_at", ""),
        )
