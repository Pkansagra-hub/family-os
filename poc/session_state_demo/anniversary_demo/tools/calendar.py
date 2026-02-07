"""
Calendar & Reminder Tools Implementation
=========================================

Real tool implementations with mock calendar storage.
These tools are used in the Anniversary Demo to handle:
- Creating calendar events with visibility settings
- Scheduling reminders for the user
- Generating comprehensive trip summaries

All calendar events are logged but not synced to real calendars (demo mode).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class EventVisibility(Enum):
    """Visibility settings for calendar events."""

    DEFAULT = "default"
    PUBLIC = "public"
    PRIVATE = "private"


class ReminderStatus(Enum):
    """Status of a scheduled reminder."""

    SCHEDULED = "scheduled"
    SENT = "sent"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"


@dataclass
class CalendarEvent:
    """A calendar event."""

    event_id: str
    title: str
    start: str
    end: str
    location: Optional[str] = None
    notes: Optional[str] = None
    visibility: EventVisibility = EventVisibility.DEFAULT
    reminder_minutes: int = 30
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "start": self.start,
            "end": self.end,
            "location": self.location,
            "notes": self.notes,
            "visibility": self.visibility.value,
            "reminder_minutes": self.reminder_minutes,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Reminder:
    """A scheduled reminder."""

    reminder_id: str
    recipient: str
    message: str
    datetime_str: str
    status: ReminderStatus = ReminderStatus.SCHEDULED
    created_at: datetime = field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reminder_id": self.reminder_id,
            "recipient": self.recipient,
            "message": self.message,
            "datetime": self.datetime_str,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }


@dataclass
class TripSummary:
    """A comprehensive trip summary."""

    session_id: str
    generated_at: datetime
    accommodation: Optional[Dict[str, Any]] = None
    dining: List[Dict[str, Any]] = field(default_factory=list)
    activities: List[Dict[str, Any]] = field(default_factory=list)
    transportation: Optional[Dict[str, Any]] = None
    weather: Optional[Dict[str, Any]] = None
    family_arrangements: Optional[Dict[str, Any]] = None
    budget: Optional[Dict[str, Any]] = None
    reminders: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "generated_at": self.generated_at.isoformat(),
            "accommodation": self.accommodation,
            "dining": self.dining,
            "activities": self.activities,
            "transportation": self.transportation,
            "weather": self.weather,
            "family_arrangements": self.family_arrangements,
            "budget": self.budget,
            "reminders": self.reminders,
            "notes": self.notes,
        }

    def to_formatted_text(self) -> str:
        """Generate a human-readable formatted summary."""
        lines = [
            "=" * 60,
            "TRIP SUMMARY",
            "=" * 60,
            "",
        ]

        if self.accommodation:
            lines.extend(
                [
                    "ACCOMMODATION",
                    "-" * 40,
                    f"  Property: {self.accommodation.get('name', 'N/A')}",
                    f"  Location: {self.accommodation.get('location', 'N/A')}",
                    f"  Check-in: {self.accommodation.get('check_in', 'N/A')}",
                    f"  Nights: {self.accommodation.get('nights', 'N/A')}",
                    f"  Confirmation: {self.accommodation.get('confirmation', 'N/A')}",
                    f"  Cost: ${self.accommodation.get('cost', 0):.2f}",
                    "",
                ]
            )

        if self.dining:
            lines.extend(
                [
                    "DINING",
                    "-" * 40,
                ]
            )
            for reservation in self.dining:
                lines.extend(
                    [
                        f"  {reservation.get('name', 'N/A')}",
                        f"    Date: {reservation.get('date', 'N/A')} at {reservation.get('time', 'N/A')}",
                        f"    Party: {reservation.get('party_size', 'N/A')} guests",
                        f"    Confirmation: {reservation.get('confirmation', 'N/A')}",
                    ]
                )
                if reservation.get("special_requests"):
                    lines.append(f"    Notes: {', '.join(reservation['special_requests'])}")
                lines.append("")

        if self.activities:
            lines.extend(
                [
                    "ACTIVITIES",
                    "-" * 40,
                ]
            )
            for activity in self.activities:
                lines.extend(
                    [
                        f"  {activity.get('name', 'N/A')}",
                        f"    Date: {activity.get('date', 'N/A')} at {activity.get('time', 'N/A')}",
                        f"    Confirmation: {activity.get('confirmation', 'N/A')}",
                        f"    Cost: ${activity.get('cost', 0):.2f}",
                        "",
                    ]
                )

        if self.transportation:
            lines.extend(
                [
                    "TRANSPORTATION",
                    "-" * 40,
                    f"  Route: {self.transportation.get('origin', 'N/A')} -> {self.transportation.get('destination', 'N/A')}",
                    f"  Type: {self.transportation.get('route_type', 'N/A')}",
                    f"  Distance: {self.transportation.get('distance', 'N/A')} miles",
                    f"  Duration: {self.transportation.get('duration', 'N/A')} minutes",
                    "",
                ]
            )

        if self.weather:
            lines.extend(
                [
                    "WEATHER FORECAST",
                    "-" * 40,
                ]
            )
            for day, forecast in self.weather.items():
                lines.append(f"  {day}: {forecast}")
            lines.append("")

        if self.family_arrangements:
            lines.extend(
                [
                    "FAMILY ARRANGEMENTS",
                    "-" * 40,
                ]
            )
            if self.family_arrangements.get("childcare"):
                lines.append(f"  Childcare: {self.family_arrangements['childcare']}")
            if self.family_arrangements.get("check_ins"):
                for checkin in self.family_arrangements["check_ins"]:
                    lines.append(f"  Check-in: {checkin}")
            if self.family_arrangements.get("messages_sent"):
                lines.append(f"  Messages sent: {self.family_arrangements['messages_sent']}")
            lines.append("")

        if self.budget:
            lines.extend(
                [
                    "BUDGET",
                    "-" * 40,
                    f"  Total Budget: ${self.budget.get('total', 0):.2f}",
                    f"  Spent: ${self.budget.get('spent', 0):.2f}",
                    f"  Remaining: ${self.budget.get('remaining', 0):.2f}",
                    "",
                ]
            )

        if self.reminders:
            lines.extend(
                [
                    "REMINDERS SET",
                    "-" * 40,
                ]
            )
            for reminder in self.reminders:
                lines.append(
                    f"  {reminder.get('datetime', 'N/A')}: {reminder.get('message', 'N/A')}"
                )
            lines.append("")

        if self.notes:
            lines.extend(
                [
                    "NOTES",
                    "-" * 40,
                ]
            )
            for note in self.notes:
                lines.append(f"  - {note}")
            lines.append("")

        lines.extend(
            [
                "=" * 60,
                f"Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 60,
            ]
        )

        return "\n".join(lines)


# =============================================================================
# STORAGE (in-memory for demo)
# =============================================================================


class CalendarStore:
    """In-memory storage for calendar events and reminders."""

    _instance: Optional[CalendarStore] = None

    def __init__(self):
        self._events: Dict[str, CalendarEvent] = {}
        self._reminders: Dict[str, Reminder] = {}
        self._summaries: Dict[str, TripSummary] = {}

    @classmethod
    def get_instance(cls) -> CalendarStore:
        if cls._instance is None:
            cls._instance = CalendarStore()
        return cls._instance

    def add_event(self, event: CalendarEvent) -> None:
        self._events[event.event_id] = event

    def get_event(self, event_id: str) -> Optional[CalendarEvent]:
        return self._events.get(event_id)

    def get_all_events(self) -> List[CalendarEvent]:
        return list(self._events.values())

    def add_reminder(self, reminder: Reminder) -> None:
        self._reminders[reminder.reminder_id] = reminder

    def get_reminder(self, reminder_id: str) -> Optional[Reminder]:
        return self._reminders.get(reminder_id)

    def get_reminders_for(self, recipient: str) -> List[Reminder]:
        return [r for r in self._reminders.values() if r.recipient.lower() == recipient.lower()]

    def get_all_reminders(self) -> List[Reminder]:
        return list(self._reminders.values())

    def add_summary(self, summary: TripSummary) -> None:
        self._summaries[summary.session_id] = summary

    def get_summary(self, session_id: str) -> Optional[TripSummary]:
        return self._summaries.get(session_id)

    def clear(self) -> None:
        self._events.clear()
        self._reminders.clear()
        self._summaries.clear()


def _generate_event_id() -> str:
    """Generate a unique event ID."""
    return f"EVT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def _generate_reminder_id() -> str:
    """Generate a unique reminder ID."""
    return f"REM-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================


def create_calendar_event(
    title: str,
    start: str,
    end: str,
    location: Optional[str] = None,
    notes: Optional[str] = None,
    visibility: str = "default",
    reminder_minutes: int = 30,
) -> Dict[str, Any]:
    """
    Create a calendar event.

    Supports visibility settings for privacy control.
    In demo mode, events are logged but not synced to real calendars.
    """
    # Parse visibility
    try:
        event_visibility = EventVisibility(visibility.lower())
    except ValueError:
        event_visibility = EventVisibility.DEFAULT

    # Create event
    event = CalendarEvent(
        event_id=_generate_event_id(),
        title=title,
        start=start,
        end=end,
        location=location,
        notes=notes,
        visibility=event_visibility,
        reminder_minutes=reminder_minutes,
    )

    # Store event
    CalendarStore.get_instance().add_event(event)

    result = {
        "success": True,
        "event": event.to_dict(),
        "message": f"Calendar event '{title}' created",
    }

    # Add visibility note for private events
    if event_visibility == EventVisibility.PRIVATE:
        result["privacy_note"] = (
            "This event is marked PRIVATE and will not appear in shared calendars"
        )

    return result


def schedule_reminder(
    recipient: str,
    message: str,
    datetime_str: str,
) -> Dict[str, Any]:
    """
    Schedule a reminder for the user.

    Reminders are delivered at the specified time.
    In demo mode, reminders are logged but not actually triggered.
    """
    # Create reminder
    reminder = Reminder(
        reminder_id=_generate_reminder_id(),
        recipient=recipient,
        message=message,
        datetime_str=datetime_str,
    )

    # Store reminder
    CalendarStore.get_instance().add_reminder(reminder)

    return {
        "success": True,
        "reminder": reminder.to_dict(),
        "message": f"Reminder scheduled for {datetime_str}",
        "will_notify": recipient,
    }


def generate_trip_summary(
    session_id: str,
    accommodation: Optional[Dict[str, Any]] = None,
    dining: Optional[List[Dict[str, Any]]] = None,
    activities: Optional[List[Dict[str, Any]]] = None,
    transportation: Optional[Dict[str, Any]] = None,
    weather: Optional[Dict[str, Any]] = None,
    family_arrangements: Optional[Dict[str, Any]] = None,
    budget: Optional[Dict[str, Any]] = None,
    reminders: Optional[List[Dict[str, Any]]] = None,
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generate a comprehensive trip summary.

    Compiles all session data into a formatted summary that can be
    displayed to the user or exported.
    """
    # Create summary
    summary = TripSummary(
        session_id=session_id,
        generated_at=datetime.now(),
        accommodation=accommodation,
        dining=dining or [],
        activities=activities or [],
        transportation=transportation,
        weather=weather,
        family_arrangements=family_arrangements,
        budget=budget,
        reminders=reminders or [],
        notes=notes or [],
    )

    # Store summary
    CalendarStore.get_instance().add_summary(summary)

    return {
        "success": True,
        "summary": summary.to_dict(),
        "formatted_text": summary.to_formatted_text(),
    }


def get_demo_trip_summary() -> Dict[str, Any]:
    """
    Generate a demo trip summary with all the Anniversary Weekend details.

    This is a convenience function for the demo that creates a complete
    summary based on the demo scenario.
    """
    return generate_trip_summary(
        session_id="anniversary_weekend_demo",
        accommodation={
            "name": "Vineyard Inn",
            "location": "Sonoma, CA",
            "check_in": "Saturday",
            "nights": 2,
            "confirmation": "ACC-20260214-ABC123",
            "cost": 578.00,
        },
        dining=[
            {
                "name": "Della Santina's",
                "date": "Saturday",
                "time": "7:00 PM",
                "party_size": 2,
                "confirmation": "RES-20260214-XYZ789",
                "special_requests": ["50th birthday celebration", "shellfish allergy - IMPORTANT"],
            }
        ],
        activities=[
            {
                "name": "Couples Massage",
                "date": "Sunday",
                "time": "11:00 AM",
                "confirmation": "SPA-20260215-DEF456",
                "cost": 320.00,
            }
        ],
        transportation={
            "origin": "San Francisco",
            "destination": "Sonoma",
            "route_type": "scenic",
            "distance": 52.8,
            "duration": 85,
        },
        weather={
            "Saturday": "72F, sunny - perfect!",
            "Sunday": "60% chance of rain afternoon - indoor activities recommended",
        },
        family_arrangements={
            "childcare": "Emma watching Jake",
            "check_ins": ["Saturday 2:00 PM - Emma"],
            "messages_sent": 1,
        },
        budget={
            "total": 1750.00,
            "spent": 898.00,
            "remaining": 852.00,
        },
        reminders=[
            {"datetime": "Friday evening", "message": "Brief Emma on Jake-sitting instructions"},
        ],
        notes=[
            "Cover story: Tech Summit Napa on calendar",
            "Mike's shellfish allergy noted at restaurant",
            "Weather monitoring active",
        ],
    )


# =============================================================================
# TOOL FUNCTION MAP (for easy lookup by name)
# =============================================================================

CALENDAR_TOOLS = {
    "create_calendar_event": create_calendar_event,
    "schedule_reminder": schedule_reminder,
    "generate_trip_summary": generate_trip_summary,
}


def execute_calendar_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a calendar tool by name with given parameters."""
    tool_func = CALENDAR_TOOLS.get(tool_name)

    if not tool_func:
        return {
            "success": False,
            "error": f"Unknown calendar tool: {tool_name}",
            "available_tools": list(CALENDAR_TOOLS.keys()),
        }

    try:
        return tool_func(**params)
    except TypeError as e:
        return {
            "success": False,
            "error": f"Invalid parameters: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Tool execution failed: {e}",
        }
