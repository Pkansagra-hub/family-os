"""
k1.tools.mcp_servers.calendar.handlers -- Calendar tool handler functions.

Each handler maps to one MCP tool. Receives raw arguments dict from the
MCP server router, delegates to CalendarStorage, and returns a dict
matching the contract output schema.

Handler naming: matches the tool name suffix (list_events, create_event, delete_event).

Error handling: handlers raise ValueError for invalid input (caught by
the MCP server router and converted to JSON-RPC error responses).

References:
  - calendar_list_events.yaml, calendar_create_event.yaml, calendar_delete_event.yaml
  - fabric_developer_guide.md Section 4 step 3
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from k1.tools.mcp_servers.calendar.storage import CalendarStorage

logger = logging.getLogger(__name__)


class CalendarHandlers:
    """
    Handler implementations for calendar MCP tools.

    Each method corresponds to one tool contract. Methods receive
    a raw arguments dict (from MCP tools/call params.arguments)
    and return a dict matching the contract output schema.

    Args:
        storage: CalendarStorage instance for persistence.
    """

    __slots__ = ("_storage",)

    def __init__(self, storage: CalendarStorage) -> None:
        self._storage = storage

    async def list_events(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle tool.read.calendar.list_events.

        Required arguments:
            start_date (str): ISO 8601 date
            end_date (str): ISO 8601 date

        Optional arguments:
            max_results (int): default 50

        Returns:
            {"events": [...], "count": int}
        """
        start_date = arguments.get("start_date")
        end_date = arguments.get("end_date")

        if not start_date:
            raise ValueError("start_date is required")
        if not end_date:
            raise ValueError("end_date is required")

        max_results = int(arguments.get("max_results", 50))
        max_results = min(max_results, 200)

        events = await self._storage.list_events(
            start_date=start_date,
            end_date=end_date,
            max_results=max_results,
        )

        return {
            "events": [e.to_dict() for e in events],
            "count": len(events),
        }

    async def create_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle tool.write.calendar.create_event.

        Required arguments:
            title (str): Event title
            start_time (str): ISO 8601 datetime
            end_time (str): ISO 8601 datetime

        Optional arguments:
            location (str): Event location
            description (str): Event notes
            attendees (list[str]): Attendee names

        Returns:
            {"event_id": str, "status": "created" | "failed"}
        """
        title = arguments.get("title")
        start_time = arguments.get("start_time")
        end_time = arguments.get("end_time")

        if not title:
            raise ValueError("title is required")
        if not start_time:
            raise ValueError("start_time is required")
        if not end_time:
            raise ValueError("end_time is required")

        location = arguments.get("location")
        description = arguments.get("description")
        attendees = arguments.get("attendees")

        if attendees is not None and not isinstance(attendees, list):
            raise ValueError("attendees must be a list of strings")

        try:
            event = await self._storage.create_event(
                title=title,
                start_time=start_time,
                end_time=end_time,
                location=location,
                description=description,
                attendees=attendees,
            )
            return {
                "event_id": event.event_id,
                "status": "created",
            }
        except Exception as exc:
            logger.error("create_event failed: %s", exc)
            return {
                "event_id": "",
                "status": "failed",
            }

    async def delete_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle tool.write.calendar.delete_event.

        Required arguments:
            event_id (str): Event identifier

        Returns:
            {"event_id": str, "status": "deleted" | "not_found"}
        """
        event_id = arguments.get("event_id")

        if not event_id:
            raise ValueError("event_id is required")

        deleted = await self._storage.delete_event(event_id)
        return {
            "event_id": event_id,
            "status": "deleted" if deleted else "not_found",
        }
