"""verticals.family.smith — Smith family profile, the M13 production seed.

Replaces ``poc.k1_poc.demo.smith_family`` + ``poc.k1_poc.demo.preloaded_memories``.
"""

from __future__ import annotations

from verticals.family.profile import FamilyMember, FamilyMemoryEntry, FamilyProfile

# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------
_MEMBERS = [
    FamilyMember(
        actor_id="alex",
        name="Alex",
        relation="parent",
        age=38,
        device_ids=["alex_phone", "alex_laptop"],
        occupation="Software engineer",
        access_level="full_adult",
        preferences={
            "office_temp_f": 72,
            "stress_eating": True,
            "dinner_no_screens": True,
        },
    ),
    FamilyMember(
        actor_id="jordan",
        name="Jordan",
        relation="parent",
        age=36,
        device_ids=["jordan_phone"],
        occupation="Pediatric nurse",
        access_level="full_adult",
        preferences={
            "dietary": "shellfish allergy",
            "sleep_temp_f": 68,
            "wake_buffer_hours": 2.5,
            "wake_style": "gentle",
        },
    ),
    FamilyMember(
        actor_id="riley",
        name="Riley",
        relation="child",
        age=8,
        device_ids=[],
        grade="3rd",
        access_level="child",
        preferences={
            "motivation_style": "mission",
            "bedtime_routine": {
                "bath": "20:00",
                "story": "20:20",
                "lights_out": "20:40",
            },
        },
    ),
    FamilyMember(
        actor_id="nana_liz",
        name="Nana Liz",
        relation="grandparent",
        age=67,
        device_ids=["nana_ipad"],
        access_level="limited",
        preferences={
            "interface": "simplified",
            "medication": {
                "name": "Amlodipine",
                "dose": "5mg",
                "time": "09:00",
            },
        },
    ),
]

# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------
_DEVICES = {
    "alex_phone": {
        "member_actor_id": "alex",
        "device_type": "iPhone",
        "label": "Alex's phone (primary)",
        "access_level": "full_adult",
    },
    "alex_laptop": {
        "member_actor_id": "alex",
        "device_type": "MacBook",
        "label": "Alex's laptop (work)",
        "access_level": "full_adult",
    },
    "jordan_phone": {
        "member_actor_id": "jordan",
        "device_type": "Android",
        "label": "Jordan's phone (primary)",
        "access_level": "full_adult",
    },
    "nana_ipad": {
        "member_actor_id": "nana_liz",
        "device_type": "iPad",
        "label": "Nana Liz's iPad (simplified)",
        "access_level": "limited",
    },
    "kitchen_hub": {
        "member_actor_id": "shared",
        "device_type": "Hub",
        "label": "Kitchen Hub",
        "access_level": "family_shared",
    },
}

# ---------------------------------------------------------------------------
# Preloaded memories (19 entries — drawn from preloaded_memories.py)
# ---------------------------------------------------------------------------
_MEMORIES = [
    FamilyMemoryEntry(
        memory_type="episodic",
        content=(
            "Last Tuesday, Riley's swim bag was left at school. "
            "Jordan had to drive back. Riley cried for 20 minutes."
        ),
        source="Session 2 weeks ago",
        tags=["riley", "swim", "bag", "school", "forgot"],
        actor_id="riley",
    ),
    FamilyMemoryEntry(
        memory_type="episodic",
        content=(
            "Alex's last client demo (Meridian Corp) went over time by 25 min "
            "because slides weren't ready. Alex was stressed for 3 days after."
        ),
        source="Session 6 weeks ago",
        tags=["alex", "demo", "slides", "stress", "work"],
        actor_id="alex",
    ),
    FamilyMemoryEntry(
        memory_type="semantic",
        content=(
            "Jordan prefers to be woken no later than 12:30pm before a 3pm shift "
            "-- needs 2.5 hours to eat, shower, commute."
        ),
        source="Learned from 14 sessions",
        tags=["jordan", "wake", "shift", "schedule"],
        actor_id="jordan",
    ),
    FamilyMemoryEntry(
        memory_type="semantic",
        content=(
            "Riley does best on homework when it's framed as a 'mission' "
            "with rewards. Sticker chart on fridge."
        ),
        source="Learned from 8 sessions",
        tags=["riley", "homework", "mission", "motivation"],
        actor_id="riley",
    ),
    FamilyMemoryEntry(
        memory_type="semantic",
        content=(
            "Nana Liz's doctor changed her BP meds to Amlodipine 5mg on Jan 15. "
            "She has trouble remembering the new pill vs. the old one."
        ),
        source="Session 3 weeks ago",
        tags=["nana_liz", "nana", "medication", "amlodipine", "bp"],
        actor_id="nana_liz",
    ),
    FamilyMemoryEntry(
        memory_type="semantic",
        content=(
            "Alex stress-eats when anxious about work. Jordan has asked "
            "FamilyOS to subtly suggest healthy options instead."
        ),
        source="Session from Jordan, private",
        tags=["alex", "eating", "stress", "health", "private"],
        actor_id="alex",
    ),
    FamilyMemoryEntry(
        memory_type="procedural",
        content=(
            "Wednesday grocery delivery from Tom Thumb arrives 4-6pm. "
            "Order must be placed by 10am."
        ),
        source="Routine, confirmed 11 times",
        tags=["grocery", "wednesday", "tom_thumb", "delivery"],
    ),
    FamilyMemoryEntry(
        memory_type="procedural",
        content=(
            "Riley's bedtime routine: 8pm bath, 8:20 story, 8:40 lights out. "
            "Deviation causes next-day irritability."
        ),
        source="Confirmed 23 times",
        tags=["riley", "bedtime", "routine", "bath"],
        actor_id="riley",
    ),
    FamilyMemoryEntry(
        memory_type="semantic",
        content=(
            "Alex and Jordan have a rule: no screens at dinner table. "
            "FamilyOS should not interrupt between 6-7pm unless URGENT."
        ),
        source="Set explicitly",
        tags=["dinner", "dnd", "screens", "family_rule"],
    ),
    FamilyMemoryEntry(
        memory_type="semantic",
        content=(
            "Shellfish allergy -- Jordan. Severity: moderate. "
            "EpiPen location: kitchen drawer left of sink."
        ),
        source="Medical profile",
        tags=["jordan", "allergy", "shellfish", "epipen", "medical"],
        actor_id="jordan",
    ),
    FamilyMemoryEntry(
        memory_type="procedural",
        content=(
            "Nana Liz takes Amlodipine 5mg every morning at 9:00am. "
            "Confirm dose taken via simplified iPad interface."
        ),
        source="Medical routine",
        tags=["nana_liz", "nana", "medication", "amlodipine", "morning"],
        actor_id="nana_liz",
    ),
    FamilyMemoryEntry(
        memory_type="semantic",
        content="Default payment method is Visa ending 4242.",
        source="Settings",
        tags=["payment", "visa", "default"],
    ),
    FamilyMemoryEntry(
        memory_type="semantic",
        content="Family timezone is America/Chicago. Located in Denton, Texas.",
        source="Settings",
        tags=["location", "timezone", "denton", "texas"],
    ),
    FamilyMemoryEntry(
        memory_type="episodic",
        content=(
            "Riley has a dinosaur diorama project due Friday. "
            "Started Monday after a tearful meltdown."
        ),
        source="Recent",
        tags=["riley", "school", "project", "dinosaur"],
        actor_id="riley",
    ),
    FamilyMemoryEntry(
        memory_type="procedural",
        content="Active todo list: pick up dry cleaning, schedule Riley's dentist appointment.",
        source="Shared todo",
        tags=["todo", "errands", "shared"],
    ),
    FamilyMemoryEntry(
        memory_type="procedural",
        content="Active grocery list: milk, avocados, Jordan's preferred crackers, Riley's lunch items.",
        source="Shared grocery list",
        tags=["grocery", "list", "shared"],
    ),
    FamilyMemoryEntry(
        memory_type="semantic",
        content="Alex prefers office temperature at 72F when working from home.",
        source="Learned preference",
        tags=["alex", "temperature", "office"],
        actor_id="alex",
    ),
    FamilyMemoryEntry(
        memory_type="semantic",
        content="Jordan sleeps best at 68F. Bedroom should cool overnight.",
        source="Learned preference",
        tags=["jordan", "sleep", "temperature"],
        actor_id="jordan",
    ),
    FamilyMemoryEntry(
        memory_type="semantic",
        content=(
            "Nana Liz uses the simplified interface on the iPad. "
            "Large text, limited options, voice-first."
        ),
        source="Accessibility setting",
        tags=["nana_liz", "nana", "accessibility", "simplified"],
        actor_id="nana_liz",
    ),
]

# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
SMITH_PROFILE = FamilyProfile(
    family_name="Smith",
    space_id="family:smith",
    location="Denton, Texas",
    timezone="America/Chicago",
    members=_MEMBERS,
    devices=_DEVICES,
    memories=_MEMORIES,
    session_config={
        "tone": "warm",
        "formality": "casual",
        "verbosity": "concise",
    },
    dietary_restrictions=["shellfish allergy (Jordan)"],
    accessibility_needs=["simplified interface (Nana Liz)"],
    preferred_language="en",
)

__all__ = ["SMITH_PROFILE"]
