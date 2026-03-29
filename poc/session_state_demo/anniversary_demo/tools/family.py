"""
Family Tools Implementation
===========================

Real tool implementations with mock message delivery.
These tools are used in the Anniversary Demo to handle:
- Sending messages to family members
- Scheduling automated check-ins
- Retrieving stored family member information

All messages are logged but not actually sent (demo mode).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class MessagePriority(Enum):
    """Priority levels for family messages."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MessageStatus(Enum):
    """Status of a family message."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class CheckinStatus(Enum):
    """Status of a scheduled check-in."""

    SCHEDULED = "scheduled"
    SENT = "sent"
    RESPONDED = "responded"
    NO_RESPONSE = "no_response"
    CANCELLED = "cancelled"


@dataclass
class FamilyMessage:
    """A message sent to a family member."""

    message_id: str
    to: str
    subject: str
    content: str
    priority: MessagePriority
    status: MessageStatus
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "to": self.to,
            "subject": self.subject,
            "content": self.content,
            "priority": self.priority.value,
            "status": self.status.value,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }


@dataclass
class ScheduledCheckin:
    """A scheduled check-in with a family member."""

    checkin_id: str
    target: str
    scheduled_datetime: str
    message: str
    notify_user_on_response: bool
    status: CheckinStatus = CheckinStatus.SCHEDULED
    response: Optional[str] = None
    response_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkin_id": self.checkin_id,
            "target": self.target,
            "scheduled_datetime": self.scheduled_datetime,
            "message": self.message,
            "notify_user_on_response": self.notify_user_on_response,
            "status": self.status.value,
            "response": self.response,
            "response_at": self.response_at.isoformat() if self.response_at else None,
        }


@dataclass
class FamilyMember:
    """Information about a family member."""

    name: str
    relationship: str
    age: Optional[int] = None
    contact: Dict[str, str] = field(default_factory=dict)
    schedule: List[Dict[str, str]] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    health: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "relationship": self.relationship,
            "age": self.age,
            "contact": self.contact,
            "schedule": self.schedule,
            "preferences": self.preferences,
            "health": self.health,
            "notes": self.notes,
        }


# =============================================================================
# MOCK DATA FOR ANNIVERSARY DEMO
# =============================================================================

MOCK_FAMILY_MEMBERS = {
    "Mike": FamilyMember(
        name="Mike",
        relationship="husband",
        age=50,
        contact={
            "phone": "(555) 123-4567",
            "email": "mike@family.com",
        },
        schedule=[
            {"day": "weekdays", "activity": "Work", "time": "9am-6pm"},
            {"day": "Saturday", "activity": "Golf (sometimes)", "time": "morning"},
        ],
        preferences={
            "relaxation": "high priority - stressed from work",
            "travel_style": "scenic routes preferred",
            "wine": "red wines, especially Pinot Noir",
            "food": "Italian cuisine favorite",
        },
        health={
            "allergies": ["shellfish"],
            "dietary": "No shellfish - mild allergy",
        },
        notes=[
            "50th birthday coming up",
            "Needs relaxation - work stress",
            "Loves wine country",
        ],
    ),
    "Emma": FamilyMember(
        name="Emma",
        relationship="daughter",
        age=16,
        contact={
            "phone": "(555) 123-4568",
            "email": "emma@family.com",
        },
        schedule=[
            {"day": "weekdays", "activity": "School", "time": "8am-3pm"},
            {"day": "Saturday", "activity": "Free", "time": "all day"},
            {"day": "Sunday", "activity": "Homework", "time": "afternoon"},
        ],
        preferences={
            "communication": "prefers text messages",
            "responsibility": "mature for her age",
        },
        health={},
        notes=[
            "Can watch Jake for the weekend",
            "Responsible and reliable",
            "Has driver's permit",
        ],
    ),
    "Jake": FamilyMember(
        name="Jake",
        relationship="son",
        age=12,
        contact={
            "phone": "(555) 123-4569",  # Kid's phone
        },
        schedule=[
            {"day": "weekdays", "activity": "School", "time": "8am-3pm"},
            {"day": "Saturday", "activity": "Soccer practice", "time": "9am"},
            {"day": "Sunday", "activity": "Free", "time": "all day"},
        ],
        preferences={
            "activities": "soccer, video games",
            "food": "pizza, tacos",
        },
        health={
            "allergies": [],
        },
        notes=[
            "Soccer practice Saturday 9am",
            "Emma can supervise",
            "Needs structure and activities",
        ],
    ),
    "Sarah": FamilyMember(
        name="Sarah",
        relationship="self (user)",
        age=48,
        contact={
            "phone": "(555) 123-4560",
            "email": "sarah@family.com",
        },
        schedule=[],
        preferences={
            "planning": "detail-oriented",
            "surprises": "loves planning surprises",
        },
        health={},
        notes=[
            "Planning Mike's 50th birthday surprise",
            "Primary FamilyOS user",
        ],
    ),
}


# =============================================================================
# MESSAGE & CHECKIN STORAGE (in-memory for demo)
# =============================================================================


class FamilyMessageStore:
    """In-memory storage for family messages."""

    _instance: Optional[FamilyMessageStore] = None

    def __init__(self):
        self._messages: Dict[str, FamilyMessage] = {}
        self._checkins: Dict[str, ScheduledCheckin] = {}

    @classmethod
    def get_instance(cls) -> FamilyMessageStore:
        if cls._instance is None:
            cls._instance = FamilyMessageStore()
        return cls._instance

    def add_message(self, message: FamilyMessage) -> None:
        self._messages[message.message_id] = message

    def get_message(self, message_id: str) -> Optional[FamilyMessage]:
        return self._messages.get(message_id)

    def get_messages_to(self, recipient: str) -> List[FamilyMessage]:
        return [m for m in self._messages.values() if m.to.lower() == recipient.lower()]

    def add_checkin(self, checkin: ScheduledCheckin) -> None:
        self._checkins[checkin.checkin_id] = checkin

    def get_checkin(self, checkin_id: str) -> Optional[ScheduledCheckin]:
        return self._checkins.get(checkin_id)

    def get_checkins_for(self, target: str) -> List[ScheduledCheckin]:
        return [c for c in self._checkins.values() if c.target.lower() == target.lower()]

    def get_all_messages(self) -> List[FamilyMessage]:
        return list(self._messages.values())

    def get_all_checkins(self) -> List[ScheduledCheckin]:
        return list(self._checkins.values())

    def clear(self) -> None:
        self._messages.clear()
        self._checkins.clear()


def _generate_message_id() -> str:
    """Generate a unique message ID."""
    return f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def _generate_checkin_id() -> str:
    """Generate a unique check-in ID."""
    return f"CHK-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================


def send_family_message(
    to: str,
    subject: str,
    content: str,
    priority: str = "normal",
) -> Dict[str, Any]:
    """
    Send a message to a family member.

    In demo mode, messages are logged but not actually sent.
    Returns confirmation of the message being queued.
    """
    # Validate recipient exists
    recipient = None
    for name, member in MOCK_FAMILY_MEMBERS.items():
        if name.lower() == to.lower():
            recipient = member
            break

    if not recipient:
        return {
            "success": False,
            "error": f"Family member '{to}' not found",
            "available_members": list(MOCK_FAMILY_MEMBERS.keys()),
        }

    # Parse priority
    try:
        msg_priority = MessagePriority(priority.lower())
    except ValueError:
        msg_priority = MessagePriority.NORMAL

    # Create message
    message = FamilyMessage(
        message_id=_generate_message_id(),
        to=recipient.name,
        subject=subject,
        content=content,
        priority=msg_priority,
        status=MessageStatus.SENT,
        sent_at=datetime.now(),
    )

    # For demo, immediately mark as delivered
    message.status = MessageStatus.DELIVERED
    message.delivered_at = datetime.now()

    # Store message
    FamilyMessageStore.get_instance().add_message(message)

    return {
        "success": True,
        "message": message.to_dict(),
        "delivery_note": f"Message delivered to {recipient.name} via {recipient.contact.get('phone', 'app notification')}",
        "demo_mode": True,
        "demo_note": "In demo mode: message logged but not actually sent",
    }


def schedule_family_checkin(
    target: str,
    datetime_str: str,
    message: str,
    notify_user_on_response: bool = True,
) -> Dict[str, Any]:
    """
    Schedule an automated check-in message to a family member.

    The check-in will be sent at the specified time and optionally
    notify the user when the family member responds.
    """
    # Validate target exists
    target_member = None
    for name, member in MOCK_FAMILY_MEMBERS.items():
        if name.lower() == target.lower():
            target_member = member
            break

    if not target_member:
        return {
            "success": False,
            "error": f"Family member '{target}' not found",
            "available_members": list(MOCK_FAMILY_MEMBERS.keys()),
        }

    # Create scheduled check-in
    checkin = ScheduledCheckin(
        checkin_id=_generate_checkin_id(),
        target=target_member.name,
        scheduled_datetime=datetime_str,
        message=message,
        notify_user_on_response=notify_user_on_response,
        status=CheckinStatus.SCHEDULED,
    )

    # Store check-in
    FamilyMessageStore.get_instance().add_checkin(checkin)

    result = {
        "success": True,
        "checkin": checkin.to_dict(),
        "scheduled_for": datetime_str,
        "target": target_member.name,
        "will_notify_on_response": notify_user_on_response,
    }

    # Add helpful context about the target
    if target_member.contact.get("phone"):
        result["delivery_method"] = f"Text message to {target_member.contact['phone']}"

    return result


def get_family_member_info(
    name: str,
    info_type: str = "all",
) -> Dict[str, Any]:
    """
    Get stored information about a family member.

    Can retrieve all info or specific types: contact, schedule, preferences, health.
    """
    # Find family member
    member = None
    for member_name, member_data in MOCK_FAMILY_MEMBERS.items():
        if member_name.lower() == name.lower():
            member = member_data
            break

    if not member:
        return {
            "success": False,
            "error": f"Family member '{name}' not found",
            "available_members": list(MOCK_FAMILY_MEMBERS.keys()),
        }

    # Get full info or specific type
    if info_type == "all":
        return {
            "success": True,
            "member": member.to_dict(),
        }

    # Specific info types
    info_map = {
        "contact": {
            "name": member.name,
            "relationship": member.relationship,
            "contact": member.contact,
        },
        "schedule": {
            "name": member.name,
            "schedule": member.schedule,
        },
        "preferences": {
            "name": member.name,
            "preferences": member.preferences,
        },
        "health": {
            "name": member.name,
            "health": member.health,
            "allergies": member.health.get("allergies", []),
        },
    }

    if info_type in info_map:
        return {
            "success": True,
            "info_type": info_type,
            "info": info_map[info_type],
        }

    return {
        "success": False,
        "error": f"Unknown info type: {info_type}",
        "available_types": ["all", "contact", "schedule", "preferences", "health"],
    }


# =============================================================================
# HELPER FUNCTIONS FOR DEMO
# =============================================================================


def compose_weekend_instructions(
    emergency_contacts: Dict[str, str],
    jake_schedule: List[Dict[str, str]],
    hotel_info: Dict[str, str],
    house_rules: List[str],
) -> str:
    """
    Compose comprehensive weekend instructions for Emma.

    This is used to generate the content for Turn 21 in the demo.
    """
    lines = [
        "Hi Emma!",
        "",
        "Here are the instructions for watching Jake this weekend:",
        "",
        "== EMERGENCY CONTACTS ==",
    ]

    for contact_name, contact_info in emergency_contacts.items():
        lines.append(f"- {contact_name}: {contact_info}")

    lines.extend(
        [
            "",
            "== JAKE'S SCHEDULE ==",
        ]
    )

    for item in jake_schedule:
        lines.append(
            f"- {item.get('day', 'TBD')}: {item.get('activity', '')} at {item.get('time', '')}"
        )

    lines.extend(
        [
            "",
            "== HOTEL CONTACT (emergencies only) ==",
            f"- Hotel: {hotel_info.get('name', 'TBD')}",
            f"- Phone: {hotel_info.get('phone', 'TBD')}",
            f"- Address: {hotel_info.get('address', 'TBD')}",
            "",
            "== HOUSE RULES ==",
        ]
    )

    for rule in house_rules:
        lines.append(f"- {rule}")

    lines.extend(
        [
            "",
            "Text me if you need anything! Love you!",
            "- Mom",
        ]
    )

    return "\n".join(lines)


def simulate_checkin_response(checkin_id: str, response: str) -> Dict[str, Any]:
    """
    Simulate a family member responding to a check-in.

    Used for demo purposes to show the notification flow.
    """
    store = FamilyMessageStore.get_instance()
    checkin = store.get_checkin(checkin_id)

    if not checkin:
        return {
            "success": False,
            "error": f"Check-in {checkin_id} not found",
        }

    checkin.status = CheckinStatus.RESPONDED
    checkin.response = response
    checkin.response_at = datetime.now()

    return {
        "success": True,
        "checkin": checkin.to_dict(),
        "notification_sent": checkin.notify_user_on_response,
    }


# =============================================================================
# TOOL FUNCTION MAP (for easy lookup by name)
# =============================================================================

FAMILY_TOOLS = {
    "send_family_message": send_family_message,
    "schedule_family_checkin": schedule_family_checkin,
    "get_family_member_info": get_family_member_info,
}


def execute_family_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a family tool by name with given parameters."""
    tool_func = FAMILY_TOOLS.get(tool_name)

    if not tool_func:
        return {
            "success": False,
            "error": f"Unknown family tool: {tool_name}",
            "available_tools": list(FAMILY_TOOLS.keys()),
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
