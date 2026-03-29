"""
poc.k1_poc.demo.smith_family -- Smith family demo profile, devices, and preloaded memories.

Matches the "One Ordinary Day" storyline in demo_storyline.md.
"""

from __future__ import annotations

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Family profile (same shape as demo_config.DEMO_FAMILY_PROFILE)
# ---------------------------------------------------------------------------

SMITH_FAMILY_PROFILE: Dict[str, Any] = {
    "family_name": "Smith",
    "location": "Denton, Texas",
    "members": [
        {
            "name": "Alex",
            "relation": "parent",
            "age": 38,
            "occupation": "Software engineer",
            "preferences": {
                "office_temp_f": 72,
                "stress_eating": True,
                "dinner_no_screens": True,
            },
        },
        {
            "name": "Jordan",
            "relation": "parent",
            "age": 36,
            "occupation": "Pediatric nurse",
            "preferences": {
                "dietary": "shellfish allergy",
                "sleep_temp_f": 68,
                "wake_buffer_hours": 2.5,
                "wake_style": "gentle",
            },
        },
        {
            "name": "Riley",
            "relation": "child",
            "age": 8,
            "grade": "3rd",
            "preferences": {
                "motivation_style": "mission",
                "bedtime_routine": {
                    "bath": "20:00",
                    "story": "20:20",
                    "lights_out": "20:40",
                },
            },
        },
        {
            "name": "Nana Liz",
            "relation": "grandparent",
            "age": 67,
            "preferences": {
                "interface": "simplified",
                "medication": {
                    "name": "Amlodipine",
                    "dose": "5mg",
                    "time": "09:00",
                },
            },
        },
    ],
    "default_payment": "visa_ending_4242",
    "dietary_restrictions": ["shellfish allergy (Jordan)"],
    "accessibility_needs": ["simplified interface (Nana Liz)"],
    "preferred_language": "en",
    "timezone": "America/Chicago",
    "grocery_store": "Tom Thumb",
    "grocery_deadline": "10:00",
    "grocery_delivery_window": "16:00-18:00",
    "dinner_dnd_window": "18:00-19:00",
}

# ---------------------------------------------------------------------------
# Device registry -- identity determined by originating device
# ---------------------------------------------------------------------------

DEVICE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "alex_phone": {
        "member": "Alex",
        "device_type": "iPhone",
        "label": "Alex's phone (primary)",
        "access_level": "full_adult",
    },
    "alex_laptop": {
        "member": "Alex",
        "device_type": "MacBook",
        "label": "Alex's laptop (work)",
        "access_level": "full_adult",
    },
    "jordan_phone": {
        "member": "Jordan",
        "device_type": "Android",
        "label": "Jordan's phone (primary)",
        "access_level": "full_adult",
    },
    "nana_ipad": {
        "member": "Nana Liz",
        "device_type": "iPad",
        "label": "Nana Liz's iPad (simplified)",
        "access_level": "limited",
    },
    "kitchen_hub": {
        "member": "shared",
        "device_type": "Hub",
        "label": "Kitchen Hub",
        "access_level": "family_shared",
    },
}

# Riley has NO device -- parents relay her requests.
# Identity shortcuts for interactive mode
MEMBER_TO_DEFAULT_DEVICE: Dict[str, str] = {
    "alex": "alex_phone",
    "jordan": "jordan_phone",
    "nana": "nana_ipad",
    "hub": "kitchen_hub",
}


def resolve_member(device_id: str) -> str:
    """Return the family member name for a device id."""
    entry = DEVICE_REGISTRY.get(device_id)
    if entry is None:
        return "unknown"
    return entry["member"]


# ---------------------------------------------------------------------------
# Session config (tone, formality, verbosity)
# ---------------------------------------------------------------------------

SMITH_SESSION_CONFIG: Dict[str, Any] = {
    "tone": "warm",
    "formality": "casual",
    "verbosity": "concise",
}

# ---------------------------------------------------------------------------
# Preloaded K0 memories -- MOVED to preloaded_memories.py (single source of truth)
# Import from: poc.k1_poc.demo.preloaded_memories
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Storyline turns (for auto-play mode)
# ---------------------------------------------------------------------------

STORYLINE_TURNS: List[Dict[str, Any]] = [
    {
        "turn": 1,
        "time": "06:02",
        "device": "alex_phone",
        "text": "What's today look like?",
    },
    {
        "turn": 2,
        "time": "06:04",
        "device": "alex_phone",
        "text": "Yeah send her the reminder. And what about Jordan, when should I wake her?",
    },
    {
        "turn": 3,
        "time": "06:08",
        "device": "alex_phone",
        "text": (
            "Perfect, do it. Oh, and Riley's right here -- she's freaking out "
            "about this dinosaur project. It's due Friday and we haven't even started."
        ),
    },
    {
        "turn": 4,
        "time": "07:15",
        "device": "alex_phone",
        "text": (
            "Add Riley's missions to the calendar. And I need to make the "
            "grocery list -- we're out of milk, and we need stuff for Riley's "
            "lunch this week. Oh and something healthy for my lunch today, "
            "I've been eating garbage."
        ),
    },
    {
        "turn": 5,
        "time": "07:18",
        "device": "alex_phone",
        "text": "Add avocados and those crackers Jordan likes. That's it, place the order.",
    },
    {
        "turn": 6,
        "time": "07:19",
        "device": "alex_phone",
        "text": "Yep, confirmed.",
    },
    {
        "turn": 7,
        "time": "09:05",
        "device": "alex_laptop",
        "text": "Start a meeting notes doc for my 9 o'clock standup.",
    },
    {
        "turn": 8,
        "time": "09:15",
        "device": "alex_laptop",
        "text": (
            "Add to yesterday: finished the API integration tests. Today: prep "
            "Orion demo slides, run through demo flow once. Blockers: need the "
            "Q4 revenue numbers from Marcus before 1pm."
        ),
    },
    {
        "turn": 9,
        "time": "09:17",
        "device": "alex_laptop",
        "text": (
            "Yeah, message him. Say I need the Q4 revenue deck by 1pm for the "
            "Orion demo. Be professional but make it clear it's urgent."
        ),
    },
    {
        "turn": 10,
        "time": "09:18",
        "device": "alex_laptop",
        "text": "Send.",
    },
    {
        "turn": 12,
        "time": "11:25",
        "device": "alex_phone",
        "text": "I'll do it in 10 minutes. Remind me.",
    },
    {
        "turn": 14,
        "time": "11:48",
        "device": "alex_phone",
        "text": "Yeah just log it. Also -- crud, I forgot the laundry. Can you add 5 more minutes to that reminder?",
    },
    {
        "turn": 16,
        "time": "12:12",
        "device": "alex_phone",
        "text": "Call Nana Liz. And set a reminder for me to check the Orion deck at 12:30.",
    },
    {
        "turn": 18,
        "time": "12:35",
        "device": "jordan_phone",
        "text": "I'm up. What'd I miss?",
    },
]
