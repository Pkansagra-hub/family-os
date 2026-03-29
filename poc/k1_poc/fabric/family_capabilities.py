"""
poc.k1_poc.fabric.family_capabilities -- Family-Domain Capability Definitions + Handlers.

Comprehensive capability set for a family operating system. Covers the
domains a real household needs: messaging, reminders, todo/grocery lists,
chores, school, health, finance, transport, and smart home control.

Each mock handler returns deterministic, realistic data without calling
external APIs. Handlers follow the same contract as demo_capabilities:
    async (params: dict) -> dict with keys: success, data, artifact_type, duration_ms

Capability naming convention:
    tool.execute.<domain>_<action>   e.g. tool.execute.send_message

All capabilities are registered into the CapabilityRegistry by
register_family_capabilities().
"""

from __future__ import annotations

import hashlib
from typing import Any

# =========================================================================
# Deterministic ID helper (same pattern as demo_capabilities)
# =========================================================================


def _deterministic_id(prefix: str, seed: str) -> str:
    h = hashlib.md5(seed.encode(), usedforsecurity=False).hexdigest()[:8]
    return f"{prefix}-{h}"


# =========================================================================
# Capability definitions -- organized by domain
# =========================================================================

FAMILY_CAPABILITIES: list[dict[str, Any]] = [
    # ------------------------------------------------------------------
    # MESSAGING / NOTIFICATIONS (4)
    # ------------------------------------------------------------------
    {
        "name": "tool.execute.send_message",
        "description": (
            "Send a text message, SMS, or notification to a family member. "
            "Supports direct messages, reminders, and alerts via the family "
            "messaging channel."
        ),
        "required_inputs": ["recipient", "message"],
        "optional_inputs": ["urgency", "channel", "schedule_time"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "messaging",
    },
    {
        "name": "tool.execute.send_group_message",
        "description": (
            "Send a message or announcement to multiple family members or "
            "the entire family group chat."
        ),
        "required_inputs": ["recipients", "message"],
        "optional_inputs": ["urgency", "channel"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "messaging",
    },
    {
        "name": "tool.execute.send_reminder",
        "description": (
            "Send a reminder notification to a family member about a task, "
            "event, appointment, or action item. Supports scheduled delivery."
        ),
        "required_inputs": ["recipient", "reminder_text"],
        "optional_inputs": ["deliver_at", "repeat", "urgency", "context"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "messaging",
    },
    {
        "name": "tool.execute.send_notification",
        "description": (
            "Push a notification to a family member's device. For alerts, "
            "status updates, IoT events, and informational nudges."
        ),
        "required_inputs": ["recipient", "title", "body"],
        "optional_inputs": ["category", "priority", "action_url"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "messaging",
    },
    # ------------------------------------------------------------------
    # TODO / LISTS (4)
    # ------------------------------------------------------------------
    {
        "name": "tool.execute.get_todo_list",
        "description": (
            "Retrieve the family or personal to-do list. Shows pending tasks, "
            "assigned members, and due dates."
        ),
        "required_inputs": [],
        "optional_inputs": ["member", "category", "status"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "productivity",
    },
    {
        "name": "tool.execute.add_todo_item",
        "description": (
            "Add a new item to the family or personal to-do list. "
            "Supports assigning to a member and setting due dates."
        ),
        "required_inputs": ["title"],
        "optional_inputs": ["assigned_to", "due_date", "priority", "category"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "productivity",
    },
    {
        "name": "tool.execute.complete_todo_item",
        "description": "Mark a to-do list item as completed.",
        "required_inputs": ["item_id"],
        "optional_inputs": ["completed_by"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "productivity",
    },
    {
        "name": "tool.execute.get_grocery_list",
        "description": (
            "Get the current grocery shopping list with items, quantities, "
            "store info, and delivery window."
        ),
        "required_inputs": [],
        "optional_inputs": ["store", "category"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "shopping",
    },
    {
        "name": "tool.execute.add_grocery_item",
        "description": (
            "Add an item to the family grocery list. Supports quantity, "
            "store preference, and aisle hints."
        ),
        "required_inputs": ["item"],
        "optional_inputs": ["quantity", "store", "aisle", "notes"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "shopping",
    },
    {
        "name": "tool.execute.grocery_order",
        "description": (
            "Place a grocery delivery or pickup order from the current list " "or specified items."
        ),
        "required_inputs": ["items"],
        "optional_inputs": ["store", "delivery_window", "budget"],
        "has_side_effects": True,
        "estimated_cost": "varies",
        "domain": "shopping",
    },
    # ------------------------------------------------------------------
    # CHORES / HOUSEHOLD (3)
    # ------------------------------------------------------------------
    {
        "name": "tool.execute.get_chore_schedule",
        "description": (
            "Get the family chore schedule showing who does what and when. "
            "Includes daily, weekly, and rotating chore assignments."
        ),
        "required_inputs": [],
        "optional_inputs": ["member", "day", "week"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "household",
    },
    {
        "name": "tool.execute.assign_chore",
        "description": (
            "Assign a chore or household task to a family member. "
            "Supports one-time or recurring assignments."
        ),
        "required_inputs": ["chore", "assigned_to"],
        "optional_inputs": ["due_date", "recurring", "notes"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "household",
    },
    {
        "name": "tool.execute.log_chore_complete",
        "description": "Mark a household chore as completed by a family member.",
        "required_inputs": ["chore_id", "completed_by"],
        "optional_inputs": ["notes"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "household",
    },
    # ------------------------------------------------------------------
    # SCHOOL / EDUCATION (3)
    # ------------------------------------------------------------------
    {
        "name": "tool.execute.get_school_schedule",
        "description": (
            "Get the school schedule, upcoming events, and activities for "
            "a child. Includes class times, after-school activities, and "
            "school events."
        ),
        "required_inputs": ["child"],
        "optional_inputs": ["date", "week"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "school",
    },
    {
        "name": "tool.execute.check_homework",
        "description": (
            "Check homework status for a child. Shows pending assignments, "
            "due dates, and completion status."
        ),
        "required_inputs": ["child"],
        "optional_inputs": ["subject", "due_date"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "school",
    },
    {
        "name": "tool.execute.school_pickup_status",
        "description": (
            "Check or update school pickup/dropoff status. Shows who is "
            "picking up, ETA, and carpool info."
        ),
        "required_inputs": ["child"],
        "optional_inputs": ["action", "pickup_person", "time"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "school",
    },
    # ------------------------------------------------------------------
    # HEALTH / MEDICAL (4)
    # ------------------------------------------------------------------
    {
        "name": "tool.execute.medication_reminder",
        "description": (
            "Set or check medication reminders for a family member. "
            "Tracks doses, schedules, and confirmation status."
        ),
        "required_inputs": ["member"],
        "optional_inputs": ["medication", "action", "time"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "health",
    },
    {
        "name": "tool.execute.schedule_appointment",
        "description": (
            "Schedule a medical, dental, or veterinary appointment. "
            "Handles doctor visits, checkups, and specialist referrals."
        ),
        "required_inputs": ["member", "type", "preferred_date"],
        "optional_inputs": ["provider", "reason", "preferred_time", "insurance"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "health",
    },
    {
        "name": "tool.execute.pharmacy_refill",
        "description": ("Request a prescription refill at the pharmacy for a family member."),
        "required_inputs": ["member", "medication"],
        "optional_inputs": ["pharmacy", "delivery", "urgent"],
        "has_side_effects": True,
        "estimated_cost": "varies",
        "domain": "health",
    },
    {
        "name": "tool.execute.vet_appointment",
        "description": (
            "Schedule a veterinary appointment for a family pet. "
            "Handles checkups, vaccinations, and sick visits."
        ),
        "required_inputs": ["pet", "reason"],
        "optional_inputs": ["preferred_date", "preferred_time", "vet_clinic"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "health",
    },
    # ------------------------------------------------------------------
    # TRANSPORT / LOGISTICS (3)
    # ------------------------------------------------------------------
    {
        "name": "tool.execute.ride_request",
        "description": ("Request a ride via ride-share or taxi service for a family member."),
        "required_inputs": ["destination"],
        "optional_inputs": ["pickup", "time", "member", "service"],
        "has_side_effects": True,
        "estimated_cost": "varies",
        "domain": "transport",
    },
    {
        "name": "tool.execute.package_tracking",
        "description": (
            "Track a package delivery. Check delivery status, ETA, "
            "and carrier info for incoming orders."
        ),
        "required_inputs": ["tracking_id"],
        "optional_inputs": ["carrier"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "logistics",
    },
    {
        "name": "tool.execute.carpool_coordinate",
        "description": (
            "Coordinate carpool logistics for school, activities, or events. "
            "Shows schedule, drivers, and passenger assignments."
        ),
        "required_inputs": ["event"],
        "optional_inputs": ["date", "children", "drivers"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "transport",
    },
    # ------------------------------------------------------------------
    # SMART HOME / IoT (4)
    # ------------------------------------------------------------------
    {
        "name": "tool.execute.smart_home_control",
        "description": (
            "Control smart home devices: lights, thermostat, locks, "
            "appliances, speakers, cameras, and other IoT devices."
        ),
        "required_inputs": ["device", "action"],
        "optional_inputs": ["value", "room", "schedule"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "iot",
    },
    {
        "name": "tool.execute.set_timer",
        "description": (
            "Set a timer or alarm. For cooking, naps, laundry, homework, " "or any timed activity."
        ),
        "required_inputs": ["duration_or_time", "label"],
        "optional_inputs": ["member", "notify", "iot_sequence"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "iot",
    },
    {
        "name": "tool.execute.nap_timer",
        "description": (
            "Set a nap/wake timer with optional IoT integration "
            "(lights, music, thermostat sequence)."
        ),
        "required_inputs": ["member", "duration"],
        "optional_inputs": ["wake_sequence", "do_not_disturb"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "iot",
    },
    {
        "name": "tool.execute.home_security_status",
        "description": (
            "Check home security status: door locks, cameras, alarm system, " "and recent alerts."
        ),
        "required_inputs": [],
        "optional_inputs": ["zone", "action"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "iot",
    },
    # ------------------------------------------------------------------
    # FAMILY COORDINATION / CALENDAR (3)
    # ------------------------------------------------------------------
    {
        "name": "tool.execute.family_calendar",
        "description": (
            "View, add, or update the family calendar. Shows events, "
            "appointments, school activities, and scheduled activities "
            "for all family members."
        ),
        "required_inputs": [],
        "optional_inputs": ["member", "date", "range_days", "action", "event"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "family",
    },
    {
        "name": "tool.execute.meal_planner",
        "description": (
            "Plan family meals for the week. Shows planned meals, "
            "dietary preferences, and links to grocery list."
        ),
        "required_inputs": [],
        "optional_inputs": ["date", "meal_type", "dietary_needs", "servings"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "family",
    },
    {
        "name": "tool.execute.family_budget",
        "description": (
            "Check family budget status, spending categories, and upcoming "
            "bills. Track expenses and set spending limits."
        ),
        "required_inputs": [],
        "optional_inputs": ["category", "period", "action"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "finance",
    },
    # ------------------------------------------------------------------
    # SWIM BAG / ACTIVITY PREP (1) -- storyline-specific
    # ------------------------------------------------------------------
    {
        "name": "tool.execute.swim_bag_check",
        "description": (
            "Send a reminder to check swim bag or activity bag contents "
            "for a family member (child). Verifies items are packed."
        ),
        "required_inputs": ["member", "items"],
        "optional_inputs": ["activity", "deadline"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "family",
    },
]


# =========================================================================
# Mock handlers -- deterministic, realistic family data
# =========================================================================


async def mock_send_message(params: dict[str, Any]) -> dict[str, Any]:
    recipient = params.get("recipient", "unknown")
    message = params.get("message", "")
    channel = params.get("channel", "family_chat")
    msg_id = _deterministic_id("MSG", f"{recipient}-{message[:20]}")
    return {
        "success": True,
        "data": {
            "message_id": msg_id,
            "recipient": recipient,
            "channel": channel,
            "status": "delivered",
            "delivered_at": "2026-02-24T09:15:00Z",
        },
        "artifact_type": "message",
        "duration_ms": 120,
    }


async def mock_send_group_message(params: dict[str, Any]) -> dict[str, Any]:
    recipients = params.get("recipients", [])
    message = params.get("message", "")
    msg_id = _deterministic_id("GRP", f"{len(recipients)}-{message[:20]}")
    return {
        "success": True,
        "data": {
            "message_id": msg_id,
            "recipients": recipients,
            "channel": "family_group",
            "status": "delivered",
            "delivered_count": len(recipients),
        },
        "artifact_type": "message",
        "duration_ms": 150,
    }


async def mock_send_reminder(params: dict[str, Any]) -> dict[str, Any]:
    recipient = params.get("recipient") or params.get("recipients", "unknown")
    text = params.get("reminder_text") or params.get("text") or params.get("message", "")
    reminder_id = _deterministic_id("REM", f"{recipient}-{text[:20]}")
    return {
        "success": True,
        "data": {
            "reminder_id": reminder_id,
            "recipient": recipient,
            "text": text,
            "status": "scheduled",
            "deliver_at": params.get("deliver_at", "now"),
        },
        "artifact_type": "reminder",
        "duration_ms": 90,
    }


async def mock_send_notification(params: dict[str, Any]) -> dict[str, Any]:
    recipient = params.get("recipient", "unknown")
    title = params.get("title", "")
    notif_id = _deterministic_id("NTF", f"{recipient}-{title[:20]}")
    return {
        "success": True,
        "data": {
            "notification_id": notif_id,
            "recipient": recipient,
            "title": title,
            "status": "pushed",
        },
        "artifact_type": "notification",
        "duration_ms": 80,
    }


async def mock_get_todo_list(params: dict[str, Any]) -> dict[str, Any]:
    member = params.get("member")
    items = [
        {
            "id": "todo-001",
            "title": "Schedule Riley's dentist appointment",
            "assigned_to": "Alex",
            "due": "2026-02-26",
            "status": "pending",
            "priority": "medium",
        },
        {
            "id": "todo-002",
            "title": "Fix bathroom faucet",
            "assigned_to": "Alex",
            "due": "2026-03-01",
            "status": "pending",
            "priority": "low",
        },
        {
            "id": "todo-003",
            "title": "Submit insurance claim",
            "assigned_to": "Jordan",
            "due": "2026-02-28",
            "status": "pending",
            "priority": "high",
        },
        {
            "id": "todo-004",
            "title": "Order Riley's birthday cake",
            "assigned_to": "Alex",
            "due": "2026-03-10",
            "status": "pending",
            "priority": "medium",
        },
        {
            "id": "todo-005",
            "title": "Book summer camp registration",
            "assigned_to": "Jordan",
            "due": "2026-03-15",
            "status": "pending",
            "priority": "high",
        },
    ]
    if member:
        items = [i for i in items if i["assigned_to"].lower() == member.lower()]
    return {
        "success": True,
        "data": {"items": items, "total": len(items)},
        "artifact_type": None,
        "duration_ms": 60,
    }


async def mock_add_todo_item(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title", "Untitled")
    item_id = _deterministic_id("TODO", title)
    return {
        "success": True,
        "data": {
            "item_id": item_id,
            "title": title,
            "assigned_to": params.get("assigned_to"),
            "due_date": params.get("due_date"),
            "status": "pending",
        },
        "artifact_type": "todo_item",
        "duration_ms": 70,
    }


async def mock_complete_todo_item(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "item_id": params.get("item_id", "unknown"),
            "status": "completed",
            "completed_by": params.get("completed_by", "system"),
        },
        "artifact_type": None,
        "duration_ms": 50,
    }


async def mock_get_grocery_list(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "store": "New Seasons Market",
            "delivery_window": "Wednesday 4-6pm",
            "order_deadline": "10am Wednesday",
            "items": [
                {"item": "Milk (whole, half-gallon)", "qty": 1, "aisle": "dairy"},
                {"item": "Dave's Killer Bread (thin-sliced)", "qty": 1, "aisle": "bakery"},
                {"item": "Bananas", "qty": 1, "aisle": "produce"},
                {"item": "Apples (Honeycrisp)", "qty": 4, "aisle": "produce"},
                {"item": "Baby carrots", "qty": 1, "aisle": "produce"},
                {"item": "String cheese (for Riley)", "qty": 1, "aisle": "dairy"},
                {"item": "Turkey deli slices", "qty": 1, "aisle": "deli"},
                {"item": "Whole wheat wraps", "qty": 1, "aisle": "bakery"},
                {"item": "Avocados", "qty": 2, "aisle": "produce"},
                {"item": "Greek yogurt (plain, 32oz)", "qty": 1, "aisle": "dairy"},
                {"item": "Eggs (free-range dozen)", "qty": 1, "aisle": "dairy"},
                {"item": "Mary's Gone Crackers (Everything)", "qty": 1, "aisle": "snacks"},
                {"item": "Peet's Decaf Coffee (Nana Liz)", "qty": 1, "aisle": "beverages"},
                {"item": "Dish soap", "qty": 1, "aisle": "household"},
            ],
            "total_items": 14,
        },
        "artifact_type": None,
        "duration_ms": 80,
    }


async def mock_add_grocery_item(params: dict[str, Any]) -> dict[str, Any]:
    item = params.get("item", "unknown")
    return {
        "success": True,
        "data": {
            "item": item,
            "quantity": params.get("quantity", 1),
            "added": True,
            "list_total": 15,
        },
        "artifact_type": None,
        "duration_ms": 50,
    }


async def mock_grocery_order(params: dict[str, Any]) -> dict[str, Any]:
    items = params.get("items", [])
    order_id = _deterministic_id("ORD", str(len(items)))
    return {
        "success": True,
        "data": {
            "order_id": order_id,
            "store": params.get("store", "New Seasons Market"),
            "items_count": len(items) if isinstance(items, list) else 0,
            "delivery_window": params.get("delivery_window", "Wednesday 4-6pm"),
            "status": "confirmed",
        },
        "artifact_type": "order",
        "duration_ms": 200,
    }


async def mock_get_chore_schedule(params: dict[str, Any]) -> dict[str, Any]:
    member = params.get("member")
    chores = [
        {
            "chore": "Unload dishwasher",
            "assigned_to": "Riley",
            "frequency": "daily",
            "day": "daily",
        },
        {
            "chore": "Take out trash",
            "assigned_to": "Alex",
            "frequency": "Tuesday, Friday",
            "day": "tue,fri",
        },
        {
            "chore": "Vacuum living room",
            "assigned_to": "Jordan",
            "frequency": "weekly",
            "day": "Saturday",
        },
        {"chore": "Feed Luna (dog)", "assigned_to": "Riley", "frequency": "daily", "day": "daily"},
        {
            "chore": "Water plants",
            "assigned_to": "Nana Liz",
            "frequency": "Wednesday, Sunday",
            "day": "wed,sun",
        },
        {
            "chore": "Laundry",
            "assigned_to": "rotating",
            "frequency": "Mon, Wed, Fri",
            "day": "mon,wed,fri",
        },
    ]
    if member:
        chores = [c for c in chores if c["assigned_to"].lower() == member.lower()]
    return {
        "success": True,
        "data": {"chores": chores, "total": len(chores)},
        "artifact_type": None,
        "duration_ms": 60,
    }


async def mock_assign_chore(params: dict[str, Any]) -> dict[str, Any]:
    chore = params.get("chore", "")
    chore_id = _deterministic_id("CHR", chore)
    return {
        "success": True,
        "data": {
            "chore_id": chore_id,
            "chore": chore,
            "assigned_to": params.get("assigned_to", "unassigned"),
            "status": "assigned",
        },
        "artifact_type": "chore_assignment",
        "duration_ms": 70,
    }


async def mock_log_chore_complete(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "chore_id": params.get("chore_id", "unknown"),
            "completed_by": params.get("completed_by", "unknown"),
            "status": "completed",
        },
        "artifact_type": None,
        "duration_ms": 50,
    }


async def mock_get_school_schedule(params: dict[str, Any]) -> dict[str, Any]:
    child = params.get("child", "Riley")
    return {
        "success": True,
        "data": {
            "child": child,
            "school": "Maple Grove Elementary",
            "schedule": [
                {"time": "07:45", "event": "Drop-off"},
                {"time": "08:00-08:45", "event": "Morning Meeting / Literacy"},
                {"time": "08:45-09:30", "event": "Math"},
                {"time": "09:30-10:15", "event": "Science / Social Studies"},
                {"time": "10:15-10:30", "event": "Snack Break"},
                {"time": "10:30-11:15", "event": "Specials (Art/Music/PE)"},
                {"time": "11:15-11:45", "event": "Lunch"},
                {"time": "11:45-12:30", "event": "Reading / Writing Workshop"},
                {"time": "12:30-13:00", "event": "Recess"},
                {"time": "13:00-14:00", "event": "Project Time"},
                {"time": "14:00-14:30", "event": "Pack-up / Dismissal"},
            ],
            "after_school": "Swim practice 3:30-4:30pm (Tue, Thu)",
            "upcoming_events": [
                {"date": "2026-02-27", "event": "Science Fair project due"},
                {"date": "2026-03-03", "event": "Parent-Teacher conference"},
            ],
        },
        "artifact_type": None,
        "duration_ms": 100,
    }


async def mock_check_homework(params: dict[str, Any]) -> dict[str, Any]:
    child = params.get("child", "Riley")
    return {
        "success": True,
        "data": {
            "child": child,
            "assignments": [
                {
                    "subject": "Math",
                    "title": "Chapter 7 worksheet",
                    "due": "2026-02-25",
                    "status": "completed",
                },
                {
                    "subject": "Reading",
                    "title": "Charlotte's Web ch. 10-12",
                    "due": "2026-02-25",
                    "status": "in_progress",
                },
                {
                    "subject": "Science",
                    "title": "Science Fair poster board",
                    "due": "2026-02-27",
                    "status": "not_started",
                },
            ],
            "completed_today": 1,
            "pending": 2,
        },
        "artifact_type": None,
        "duration_ms": 80,
    }


async def mock_school_pickup_status(params: dict[str, Any]) -> dict[str, Any]:
    child = params.get("child", "Riley")
    return {
        "success": True,
        "data": {
            "child": child,
            "pickup_time": "14:30",
            "pickup_person": "Alex",
            "method": "carpool",
            "carpool_driver": "Alex (today)",
            "eta_minutes": None,
            "status": "scheduled",
        },
        "artifact_type": None,
        "duration_ms": 60,
    }


async def mock_medication_reminder(params: dict[str, Any]) -> dict[str, Any]:
    member = params.get("member", "unknown")
    medication = params.get("medication", "daily medication")
    reminder_id = _deterministic_id("MED", f"{member}-{medication}")
    return {
        "success": True,
        "data": {
            "reminder_id": reminder_id,
            "member": member,
            "medication": medication,
            "status": "reminder_set",
            "next_dose": "09:00",
            "confirmed": False,
        },
        "artifact_type": "medication_reminder",
        "duration_ms": 90,
    }


async def mock_schedule_appointment(params: dict[str, Any]) -> dict[str, Any]:
    member = params.get("member", "unknown")
    appt_type = params.get("type", "checkup")
    appt_id = _deterministic_id("APT", f"{member}-{appt_type}")
    return {
        "success": True,
        "data": {
            "appointment_id": appt_id,
            "member": member,
            "type": appt_type,
            "provider": params.get("provider", "Dr. Chen"),
            "date": params.get("preferred_date", "2026-03-05"),
            "time": params.get("preferred_time", "10:00"),
            "status": "confirmed",
        },
        "artifact_type": "appointment",
        "duration_ms": 200,
    }


async def mock_pharmacy_refill(params: dict[str, Any]) -> dict[str, Any]:
    member = params.get("member", "unknown")
    medication = params.get("medication", "unknown")
    refill_id = _deterministic_id("RX", f"{member}-{medication}")
    return {
        "success": True,
        "data": {
            "refill_id": refill_id,
            "member": member,
            "medication": medication,
            "pharmacy": params.get("pharmacy", "Walgreens"),
            "status": "processing",
            "estimated_ready": "2-3 hours",
        },
        "artifact_type": "prescription",
        "duration_ms": 150,
    }


async def mock_vet_appointment(params: dict[str, Any]) -> dict[str, Any]:
    pet = params.get("pet", "Luna")
    reason = params.get("reason", "checkup")
    appt_id = _deterministic_id("VET", f"{pet}-{reason}")
    return {
        "success": True,
        "data": {
            "appointment_id": appt_id,
            "pet": pet,
            "reason": reason,
            "clinic": params.get("vet_clinic", "Happy Paws Veterinary"),
            "date": params.get("preferred_date", "2026-03-07"),
            "time": params.get("preferred_time", "14:00"),
            "status": "confirmed",
        },
        "artifact_type": "appointment",
        "duration_ms": 180,
    }


async def mock_ride_request(params: dict[str, Any]) -> dict[str, Any]:
    destination = params.get("destination", "unknown")
    ride_id = _deterministic_id("RIDE", destination)
    return {
        "success": True,
        "data": {
            "ride_id": ride_id,
            "destination": destination,
            "pickup": params.get("pickup", "home"),
            "eta_minutes": 8,
            "driver": "Maria G.",
            "vehicle": "Toyota Camry (Silver)",
            "status": "driver_assigned",
        },
        "artifact_type": "ride",
        "duration_ms": 300,
    }


async def mock_package_tracking(params: dict[str, Any]) -> dict[str, Any]:
    tracking_id = params.get("tracking_id", "unknown")
    return {
        "success": True,
        "data": {
            "tracking_id": tracking_id,
            "carrier": params.get("carrier", "FedEx"),
            "status": "out_for_delivery",
            "eta": "Today by 5:00 PM",
            "last_location": "Local distribution center",
            "signed_required": False,
        },
        "artifact_type": None,
        "duration_ms": 120,
    }


async def mock_carpool_coordinate(params: dict[str, Any]) -> dict[str, Any]:
    event = params.get("event", "school")
    return {
        "success": True,
        "data": {
            "event": event,
            "schedule": [
                {"day": "Monday", "driver": "Alex", "children": ["Riley", "Emma S."]},
                {
                    "day": "Tuesday",
                    "driver": "Sarah M.",
                    "children": ["Riley", "Emma S.", "Jack M."],
                },
                {"day": "Wednesday", "driver": "Alex", "children": ["Riley", "Emma S."]},
                {
                    "day": "Thursday",
                    "driver": "Tom P.",
                    "children": ["Riley", "Emma S.", "Liam P."],
                },
                {"day": "Friday", "driver": "Alex", "children": ["Riley", "Emma S."]},
            ],
            "next_driver": "Alex (Wednesday)",
        },
        "artifact_type": None,
        "duration_ms": 100,
    }


async def mock_smart_home_control(params: dict[str, Any]) -> dict[str, Any]:
    device = params.get("device", "unknown")
    action = params.get("action", "status")
    return {
        "success": True,
        "data": {
            "device": device,
            "action": action,
            "room": params.get("room", "living_room"),
            "status": "executed",
            "current_state": f"{device} {action} complete",
        },
        "artifact_type": None,
        "duration_ms": 80,
    }


async def mock_set_timer(params: dict[str, Any]) -> dict[str, Any]:
    label = params.get("label", "timer")
    timer_id = _deterministic_id("TMR", label)
    return {
        "success": True,
        "data": {
            "timer_id": timer_id,
            "label": label,
            "duration": params.get("duration_or_time", "30 minutes"),
            "status": "running",
        },
        "artifact_type": "timer",
        "duration_ms": 50,
    }


async def mock_nap_timer(params: dict[str, Any]) -> dict[str, Any]:
    member = params.get("member", "unknown")
    timer_id = _deterministic_id("NAP", member)
    return {
        "success": True,
        "data": {
            "timer_id": timer_id,
            "member": member,
            "duration": params.get("duration", "90 minutes"),
            "wake_sequence": params.get("wake_sequence", "gentle"),
            "do_not_disturb": params.get("do_not_disturb", True),
            "status": "active",
        },
        "artifact_type": "timer",
        "duration_ms": 100,
    }


async def mock_home_security_status(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "alarm_status": "armed_home",
            "doors": {"front": "locked", "back": "locked", "garage": "closed"},
            "cameras": {"front_porch": "online", "backyard": "online", "garage": "online"},
            "recent_alerts": [],
            "last_check": "2026-02-24T08:00:00Z",
        },
        "artifact_type": None,
        "duration_ms": 90,
    }


async def mock_family_calendar(params: dict[str, Any]) -> dict[str, Any]:
    member = params.get("member")
    events = [
        {"time": "07:45", "event": "Riley school drop-off", "member": "Alex"},
        {"time": "09:00", "event": "Team standup", "member": "Alex"},
        {"time": "09:00", "event": "Nana Liz medication reminder", "member": "Nana Liz"},
        {"time": "10:00", "event": "Grocery order deadline", "member": "Alex"},
        {"time": "14:30", "event": "Riley school pickup", "member": "Alex"},
        {"time": "15:00", "event": "Jordan shift starts", "member": "Jordan"},
        {"time": "15:30", "event": "Riley swim practice", "member": "Riley"},
        {"time": "18:00", "event": "Family dinner", "member": "everyone"},
    ]
    if member:
        events = [
            e for e in events if e["member"].lower() == member.lower() or e["member"] == "everyone"
        ]
    return {
        "success": True,
        "data": {
            "date": params.get("date", "2026-02-24"),
            "events": events,
            "total": len(events),
        },
        "artifact_type": None,
        "duration_ms": 80,
    }


async def mock_meal_planner(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "week_of": "2026-02-24",
            "meals": [
                {"day": "Monday", "dinner": "Chicken stir-fry with rice", "prep_time": "30min"},
                {
                    "day": "Tuesday",
                    "dinner": "Pasta with marinara (Riley's pick)",
                    "prep_time": "25min",
                },
                {"day": "Wednesday", "dinner": "Fish tacos", "prep_time": "35min"},
                {"day": "Thursday", "dinner": "Leftover night", "prep_time": "10min"},
                {
                    "day": "Friday",
                    "dinner": "Pizza night (order from Vincenzo's)",
                    "prep_time": "0min",
                },
            ],
            "dietary_notes": "Riley: no mushrooms. Nana Liz: low sodium.",
        },
        "artifact_type": None,
        "duration_ms": 70,
    }


async def mock_family_budget(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "month": "February 2026",
            "budget_total": 6500,
            "spent_so_far": 4820,
            "remaining": 1680,
            "categories": [
                {"category": "Groceries", "budget": 800, "spent": 620, "remaining": 180},
                {"category": "Dining out", "budget": 300, "spent": 195, "remaining": 105},
                {"category": "Gas/Transport", "budget": 250, "spent": 180, "remaining": 70},
                {"category": "Kids activities", "budget": 400, "spent": 350, "remaining": 50},
                {"category": "Utilities", "budget": 350, "spent": 340, "remaining": 10},
                {"category": "Healthcare", "budget": 200, "spent": 85, "remaining": 115},
            ],
            "upcoming_bills": [
                {"bill": "Mortgage", "due": "2026-03-01", "amount": 2200},
                {"bill": "Car insurance", "due": "2026-03-05", "amount": 185},
            ],
        },
        "artifact_type": None,
        "duration_ms": 100,
    }


async def mock_swim_bag_check(params: dict[str, Any]) -> dict[str, Any]:
    member = params.get("member", "Riley")
    items = params.get("items", ["swimsuit", "towel", "goggles"])
    return {
        "success": True,
        "data": {
            "member": member,
            "items_checked": items,
            "all_packed": True,
            "reminder_sent": True,
            "status": "reminder_delivered",
        },
        "artifact_type": "reminder",
        "duration_ms": 90,
    }


# =========================================================================
# Handler map -- maps capability name to async handler
# =========================================================================

FAMILY_HANDLERS: dict[str, Any] = {
    # Messaging
    "tool.execute.send_message": mock_send_message,
    "tool.execute.send_group_message": mock_send_group_message,
    "tool.execute.send_reminder": mock_send_reminder,
    "tool.execute.send_notification": mock_send_notification,
    # Todo / Lists
    "tool.execute.get_todo_list": mock_get_todo_list,
    "tool.execute.add_todo_item": mock_add_todo_item,
    "tool.execute.complete_todo_item": mock_complete_todo_item,
    "tool.execute.get_grocery_list": mock_get_grocery_list,
    "tool.execute.add_grocery_item": mock_add_grocery_item,
    "tool.execute.grocery_order": mock_grocery_order,
    # Chores
    "tool.execute.get_chore_schedule": mock_get_chore_schedule,
    "tool.execute.assign_chore": mock_assign_chore,
    "tool.execute.log_chore_complete": mock_log_chore_complete,
    # School
    "tool.execute.get_school_schedule": mock_get_school_schedule,
    "tool.execute.check_homework": mock_check_homework,
    "tool.execute.school_pickup_status": mock_school_pickup_status,
    # Health
    "tool.execute.medication_reminder": mock_medication_reminder,
    "tool.execute.schedule_appointment": mock_schedule_appointment,
    "tool.execute.pharmacy_refill": mock_pharmacy_refill,
    "tool.execute.vet_appointment": mock_vet_appointment,
    # Transport
    "tool.execute.ride_request": mock_ride_request,
    "tool.execute.package_tracking": mock_package_tracking,
    "tool.execute.carpool_coordinate": mock_carpool_coordinate,
    # Smart Home / IoT
    "tool.execute.smart_home_control": mock_smart_home_control,
    "tool.execute.set_timer": mock_set_timer,
    "tool.execute.nap_timer": mock_nap_timer,
    "tool.execute.home_security_status": mock_home_security_status,
    # Family Coordination
    "tool.execute.family_calendar": mock_family_calendar,
    "tool.execute.meal_planner": mock_meal_planner,
    "tool.execute.family_budget": mock_family_budget,
    # Activity prep
    "tool.execute.swim_bag_check": mock_swim_bag_check,
}


def register_family_capabilities(registry: Any) -> int:
    """Register all family capabilities into the CapabilityRegistry.

    Skips capabilities already registered (idempotent).

    Args:
        registry: CapabilityRegistry instance.

    Returns:
        Number of newly registered capabilities.
    """
    count = 0
    for cap in FAMILY_CAPABILITIES:
        name = cap["name"]
        if not registry.has(name):
            handler = FAMILY_HANDLERS.get(name)
            if handler:
                registry.register(cap, handler)
                count += 1
    return count
