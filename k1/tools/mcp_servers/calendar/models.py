"""
k1.tools.mcp_servers.calendar.models -- Calendar data models.

Frozen dataclasses for calendar events. Immutable after construction.
All timestamps are ISO 8601 strings (no timezone awareness per Phase 1 scope).

References:
  - calendar_create_event.yaml (output schema)
  - calendar_list_events.yaml (output schema)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class CalendarEvent:
    """
    A single calendar event.

    Immutable record stored in and retrieved from CalendarStorage.
    Field names match the contract output schema.

    Attributes:
        event_id: Unique identifier (UUID).
        title: Event title (required).
        start_time: ISO 8601 datetime string (required).
        end_time: ISO 8601 datetime string (required).
        location: Optional venue or address.
        description: Optional notes or details.
        attendees: Tuple of attendee names (immutable).
        created_at: ISO 8601 datetime of creation.
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    start_time: str = ""
    end_time: str = ""
    location: Optional[str] = None
    description: Optional[str] = None
    attendees: Tuple[str, ...] = field(default_factory=tuple)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary matching contract output schema."""
        result: Dict[str, Any] = {
            "event_id": self.event_id,
            "title": self.title,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }
        if self.location is not None:
            result["location"] = self.location
        else:
            result["location"] = ""
        if self.description is not None:
            result["description"] = self.description
        else:
            result["description"] = ""
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CalendarEvent:
        """Create CalendarEvent from a dictionary."""
        attendees_raw = data.get("attendees", ())
        if isinstance(attendees_raw, list):
            attendees_raw = tuple(attendees_raw)
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            title=data.get("title", ""),
            start_time=data.get("start_time", ""),
            end_time=data.get("end_time", ""),
            location=data.get("location"),
            description=data.get("description"),
            attendees=attendees_raw,
            created_at=data.get("created_at", ""),
        )
