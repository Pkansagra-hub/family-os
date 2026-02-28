"""
poc.k1_poc.demo.iot_stubs -- Scripted IoT monitor stubs for the demo.

Turn-driven (not time-based) so the demo is deterministic and
reproducible.  Each stub fires a proactive envelope at the appropriate
storyline turn number.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from k1.bus.ports.bus import IBus
from poc.k1_poc.bus.builders import build_proactive_fill

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scripted IoT event definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScriptedIoTEvent:
    """One IoT event that fires at a specific demo turn."""

    turn: int
    monitor_type: str
    summary: str
    payload: Dict[str, Any]
    label: str = ""  # short name for timeline


# The events are keyed to storyline turns in demo_storyline.md.
# Early turns (2-4) provide ambient IoT context during short demos.
# Later turns (11, 13, 15, 17) are "proactive-only" storyline beats.

SCRIPTED_IOT_EVENTS: List[ScriptedIoTEvent] = [
    # --- Early demo ambient events (turns 2-4) ---
    ScriptedIoTEvent(
        turn=2,
        monitor_type="SECURITY",
        summary=(
            "Front door was locked automatically -- everyone's out "
            "or accounted for. All entry points secure."
        ),
        payload={
            "monitor": "SECURITY",
            "device": "front_door_lock",
            "status": "auto_locked",
            "all_secure": True,
        },
        label="door_auto_locked",
    ),
    ScriptedIoTEvent(
        turn=3,
        monitor_type="PACKAGE",
        summary=(
            "Package delivered! Amazon box on the front porch -- "
            "looks like Riley's new art supplies. Porch camera "
            "confirmed delivery at 3:12 PM."
        ),
        payload={
            "monitor": "PACKAGE",
            "device": "porch_camera",
            "carrier": "Amazon",
            "item_hint": "Riley's art supplies",
            "location": "front_porch",
            "confirmed_time": "15:12",
        },
        label="package_delivered",
    ),
    ScriptedIoTEvent(
        turn=4,
        monitor_type="HEALTH",
        summary=(
            "Nana Liz's 3 PM medication reminder sent. She confirmed "
            "she took her Amlodipine 5mg. All good!"
        ),
        payload={
            "monitor": "HEALTH",
            "device": "nana_tablet",
            "member": "Nana Liz",
            "medication": "Amlodipine 5mg",
            "status": "confirmed",
            "scheduled_time": "15:00",
        },
        label="nana_meds_confirmed",
    ),
    # --- Storyline mid-game events ---
    ScriptedIoTEvent(
        turn=11,
        monitor_type="LAUNDRY",
        summary=(
            "Washer's done. Jordan's scrubs are in there -- "
            "she'll need them for her 3pm shift. Want me to remind "
            "you to move them to the dryer, or should I hold this "
            "for Jordan when she wakes up?"
        ),
        payload={
            "monitor": "LAUNDRY",
            "device": "washer",
            "status": "cycle_complete",
            "item": "Jordan's scrubs",
            "urgency": "medium",
            "deadline": "14:30",
            "reason": "Jordan leaves for shift at 14:30, scrubs must be dry",
        },
        label="washer_done",
    ),
    ScriptedIoTEvent(
        turn=13,
        monitor_type="DOORBELL",
        summary=(
            "Someone's at the door -- looks like a package delivery. "
            "FedEx. I can see the box on the porch camera. Jordan's "
            "asleep, so I'm not sending her a notification. Want me "
            "to just log it?"
        ),
        payload={
            "monitor": "DOORBELL",
            "device": "ring_doorbell",
            "carrier": "FedEx",
            "location": "front_porch",
            "dnd_members": ["Jordan"],
        },
        label="doorbell_fedex",
    ),
    ScriptedIoTEvent(
        turn=15,
        monitor_type="WEAVE",
        summary=(
            "Two things, Alex:\n\n"
            "First -- Marcus got back to you. He said the Q4 deck is on "
            "the shared drive now, folder 'Orion-Assets.' He also flagged "
            "that the December numbers got revised upward -- you might "
            "want to update slide 7.\n\n"
            "Second -- it's Wednesday, and Nana Liz's 9am med reminder "
            "went off three hours ago but she hasn't confirmed she took "
            "it. This has happened twice before and she forgot both "
            "times. Want me to give her a call or send Jordan a message "
            "for when she wakes up?"
        ),
        payload={
            "monitor": "WEAVE",
            "threads": [
                {
                    "source": "email_monitor",
                    "from": "Marcus",
                    "subject": "Q4 revenue deck",
                    "action": "deck available in Orion-Assets",
                },
                {
                    "source": "med_reminder",
                    "member": "Nana Liz",
                    "medication": "Amlodipine 5mg",
                    "status": "unconfirmed",
                    "hours_overdue": 3,
                },
            ],
        },
        label="marcus_reply_and_nana_meds",
    ),
    ScriptedIoTEvent(
        turn=17,
        monitor_type="IOT_SEQUENCE",
        summary=(
            "Jordan's wake-up sequence fired:\n"
            "  12:15 -- Bedroom lights fade to 20% warm\n"
            "  12:18 -- Spotify 'Wake Up Slow' playlist\n"
            "  12:20 -- Smart kettle heating\n"
            "  12:25 -- Thermostat adjusting 68F -> 71F"
        ),
        payload={
            "monitor": "IOT_SEQUENCE",
            "sequence_name": "jordan_gentle_wake",
            "steps": [
                {"time": "12:15", "device": "bedroom_lights", "action": "fade_to_20pct"},
                {"time": "12:18", "device": "spotify", "action": "play_wake_up_slow"},
                {"time": "12:20", "device": "smart_kettle", "action": "heat_water"},
                {"time": "12:25", "device": "thermostat", "action": "adjust_68_to_71"},
            ],
        },
        label="jordan_wake_sequence",
    ),
]


# ---------------------------------------------------------------------------
# IoT stub manager
# ---------------------------------------------------------------------------


class IoTMonitorStub:
    """
    Manages scripted IoT events tied to storyline turns.

    Call ``check(turn)`` after each user input.  If one or more IoT
    events are registered for that turn number, the stub publishes
    proactive envelopes onto the bus and returns True so the
    interactive loop knows a proactive message was injected.
    """

    def __init__(self, bus: IBus) -> None:
        self._bus = bus
        self._events_by_turn: Dict[int, List[ScriptedIoTEvent]] = {}
        self._fired: set[int] = set()

        for evt in SCRIPTED_IOT_EVENTS:
            self._events_by_turn.setdefault(evt.turn, []).append(evt)

    @property
    def scheduled_turns(self) -> List[int]:
        """Turns that have IoT events."""
        return sorted(self._events_by_turn.keys())

    @property
    def fired_turns(self) -> set[int]:
        return set(self._fired)

    def has_event(self, turn: int) -> bool:
        return turn in self._events_by_turn and turn not in self._fired

    def check(self, turn: int) -> List[ScriptedIoTEvent]:
        """
        Publish any IoT events for *turn*.

        Returns the list of events fired (empty if none).
        Each event is published as a ``proactive.fill`` envelope.
        """
        if turn in self._fired or turn not in self._events_by_turn:
            return []

        events = self._events_by_turn[turn]
        fired: List[ScriptedIoTEvent] = []

        for evt in events:
            envelope = build_proactive_fill(
                payload={
                    "text": evt.summary,
                    "monitor_type": evt.monitor_type,
                    **evt.payload,
                },
            )
            self._bus.publish(envelope)
            logger.info(
                "IoT stub fired: turn=%d monitor=%s label=%s",
                turn,
                evt.monitor_type,
                evt.label,
            )
            fired.append(evt)

        self._fired.add(turn)
        return fired

    def reset(self) -> None:
        """Reset all fired state (for re-running the demo)."""
        self._fired.clear()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Additional storyline capability stubs
#
# NOTE: Most family capabilities (messaging, grocery, ride, swim bag, etc.)
# are now registered by family_capabilities.py via create_demo_registry().
# This list only contains storyline-specific overrides NOT covered there.
# The register function uses registry.has() to skip duplicates.
# ---------------------------------------------------------------------------

STORYLINE_CAPABILITIES: List[Dict[str, Any]] = [
    # smart_home uses a different name than smart_home_control in family_capabilities
    {
        "name": "tool.execute.smart_home",
        "domain": "iot",
        "description": "Control smart home devices (legacy name alias).",
        "parameters": {"device": "string", "action": "string", "value": "string"},
    },
]


async def _stub_handler(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generic stub handler -- returns a success dict with echoed params."""
    return {"status": "ok", "stub": True, "params": params}


async def _grocery_list_handler(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return the family's current grocery list."""
    return {
        "status": "ok",
        "success": True,
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
    }


async def _todo_list_handler(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return the family's current to-do list."""
    member = params.get("member", "alex").lower() if params else "alex"
    # Alex's current tasks
    alex_tasks = [
        {
            "id": 1,
            "task": "Review quarterly OKRs",
            "assigned": "Alex",
            "status": "pending",
            "due": "this week",
        },
        {
            "id": 2,
            "task": "Update 1:1 doc for manager",
            "assigned": "Alex",
            "status": "pending",
            "due": "Friday",
        },
        {
            "id": 3,
            "task": "Renew car registration",
            "assigned": "Alex",
            "status": "pending",
            "due": "March 1",
        },
        {
            "id": 4,
            "task": "Schedule Riley's annual checkup",
            "assigned": "Alex",
            "status": "pending",
            "due": "this month",
        },
        {
            "id": 5,
            "task": "Set up dentist appointment for Jordan",
            "assigned": "Alex",
            "status": "pending",
            "due": "this month",
        },
    ]
    # Jordan's current tasks
    jordan_tasks = [
        {
            "id": 1,
            "task": "Pick up dry cleaning",
            "assigned": "Jordan",
            "status": "pending",
            "due": "today",
        },
        {
            "id": 2,
            "task": "Refill Nana's prescription",
            "assigned": "Jordan",
            "status": "pending",
            "due": "today",
        },
        {
            "id": 3,
            "task": "Fix leaky kitchen faucet",
            "assigned": "Jordan",
            "status": "pending",
            "due": "weekend",
        },
        {
            "id": 4,
            "task": "Book vet appointment for Max",
            "assigned": "Jordan",
            "status": "pending",
            "due": "this week",
        },
    ]
    tasks = jordan_tasks if "jordan" in member else alex_tasks
    return {
        "status": "ok",
        "success": True,
        "member": member,
        "tasks": tasks,
        "total": len(tasks),
        "pending": len([t for t in tasks if t["status"] == "pending"]),
    }


_CAPABILITY_HANDLERS: Dict[str, Any] = {
    "tool.execute.get_grocery_list": _grocery_list_handler,
    "tool.execute.get_todo_list": _todo_list_handler,
}


def register_storyline_capabilities(registry: Any) -> int:
    """
    Register storyline-specific capability stubs onto *registry*.

    Returns the number of capabilities registered.
    """
    count = 0
    for cap in STORYLINE_CAPABILITIES:
        if not registry.has(cap["name"]):
            handler = _CAPABILITY_HANDLERS.get(cap["name"], _stub_handler)
            registry.register(cap, handler)
            count += 1
    return count
