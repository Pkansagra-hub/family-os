"""Canonical preloaded memories for K1 demo.

This is the single source of truth for demo memory data (M19.1.3).
Previously embedded in smith_family.py; extracted for independent
evolution and clean kernel seed_memories injection.
"""

from __future__ import annotations

from typing import Any, Dict, List

PRELOADED_MEMORIES: List[Dict[str, Any]] = [
    {
        "type": "episodic",
        "content": (
            "Last Tuesday, Riley's swim bag was left at school. "
            "Jordan had to drive back. Riley cried for 20 minutes."
        ),
        "source": "Session 2 weeks ago",
        "tags": ["riley", "swim", "bag", "school", "forgot"],
    },
    {
        "type": "episodic",
        "content": (
            "Alex's last client demo (Meridian Corp) went over time by "
            "25 min because slides weren't ready. Alex was stressed for 3 days after."
        ),
        "source": "Session 6 weeks ago",
        "tags": ["alex", "demo", "slides", "stress", "work"],
    },
    {
        "type": "semantic",
        "content": (
            "Jordan prefers to be woken no later than 12:30pm before a "
            "3pm shift -- needs 2.5 hours to eat, shower, commute."
        ),
        "source": "Learned from 14 sessions",
        "tags": ["jordan", "wake", "shift", "schedule"],
    },
    {
        "type": "semantic",
        "content": (
            "Riley does best on homework when it's framed as a 'mission' "
            "with rewards. Sticker chart on fridge."
        ),
        "source": "Learned from 8 sessions",
        "tags": ["riley", "homework", "mission", "motivation"],
    },
    {
        "type": "semantic",
        "content": (
            "Nana Liz's doctor changed her BP meds to Amlodipine 5mg on "
            "Jan 15. She has trouble remembering the new pill vs. the old one."
        ),
        "source": "Session 3 weeks ago",
        "tags": ["nana", "medication", "amlodipine", "bp"],
    },
    {
        "type": "semantic",
        "content": (
            "Alex stress-eats when anxious about work. Jordan has asked "
            "FamilyOS to subtly suggest healthy options instead."
        ),
        "source": "Session from Jordan, private",
        "tags": ["alex", "eating", "stress", "health", "private"],
    },
    {
        "type": "procedural",
        "content": (
            "Wednesday grocery delivery from New Seasons Market arrives "
            "between 4-6pm. Order must be placed by 10am."
        ),
        "source": "Routine, confirmed 11 times",
        "tags": ["grocery", "wednesday", "new_seasons", "delivery"],
    },
    {
        "type": "procedural",
        "content": (
            "Riley's bedtime routine: 8pm bath, 8:20 story, 8:40 lights "
            "out. Deviation causes next-day irritability."
        ),
        "source": "Confirmed 23 times",
        "tags": ["riley", "bedtime", "routine", "bath"],
    },
    {
        "type": "semantic",
        "content": (
            "Alex and Jordan have a rule: no screens at dinner table. "
            "FamilyOS should not interrupt between 6-7pm unless URGENT."
        ),
        "source": "Set explicitly",
        "tags": ["dinner", "dnd", "screens", "family_rule"],
    },
    {
        "type": "semantic",
        "content": (
            "Shellfish allergy -- Jordan. Severity: moderate. "
            "EpiPen location: kitchen drawer left of sink."
        ),
        "source": "Medical profile",
        "tags": ["jordan", "allergy", "shellfish", "epipen", "medical"],
    },
    # --- Agenda / Todo / Schedule memories ---
    {
        "type": "procedural",
        "content": (
            "Monday agenda: Riley school drop-off 7:45am, Alex standup 9am, "
            "grocery list review 10am, Riley swim practice pickup 4pm, "
            "family dinner 6pm."
        ),
        "source": "Weekly planner, confirmed",
        "tags": ["monday", "agenda", "schedule", "todo", "riley", "alex"],
    },
    {
        "type": "procedural",
        "content": (
            "Tuesday agenda: Jordan dentist 10am, Alex client call 2pm, "
            "Riley homework help 4:30pm, taco Tuesday dinner 6pm."
        ),
        "source": "Weekly planner, confirmed",
        "tags": ["tuesday", "agenda", "schedule", "todo", "jordan", "alex", "riley"],
    },
    {
        "type": "procedural",
        "content": (
            "Wednesday agenda: grocery order by 10am (New Seasons), "
            "Alex deep-work block 9am-12pm, Riley art class 3:30pm, "
            "grocery delivery 4-6pm, Jordan night shift starts 3pm."
        ),
        "source": "Weekly planner, confirmed",
        "tags": ["wednesday", "agenda", "schedule", "todo", "alex", "riley", "jordan", "grocery"],
    },
    {
        "type": "procedural",
        "content": (
            "Thursday agenda: Alex team retrospective 10am, Riley piano "
            "lesson 4pm, Nana Liz video call 5pm, pizza night 6:30pm."
        ),
        "source": "Weekly planner, confirmed",
        "tags": ["thursday", "agenda", "schedule", "todo", "alex", "riley", "nana"],
    },
    {
        "type": "procedural",
        "content": (
            "Friday agenda: Riley show-and-tell at school, Alex half-day "
            "(off after 1pm), family movie night 7pm."
        ),
        "source": "Weekly planner, confirmed",
        "tags": ["friday", "agenda", "schedule", "todo", "riley", "alex"],
    },
    {
        "type": "procedural",
        "content": (
            "Weekend agenda: Saturday -- Riley soccer 9am, park playdate "
            "11am, errands afternoon. Sunday -- family brunch 10am, "
            "meal prep 3pm, Riley school prep 6pm."
        ),
        "source": "Weekly planner, confirmed",
        "tags": ["saturday", "sunday", "weekend", "agenda", "schedule", "todo", "riley"],
    },
    {
        "type": "semantic",
        "content": (
            "Alex's standing to-do list: review quarterly OKRs, update "
            "1:1 doc for manager, renew car registration (due March 1), "
            "schedule Riley's annual checkup."
        ),
        "source": "Alex's personal list, 3 sessions ago",
        "tags": ["alex", "todo", "tasks", "okrs", "car", "checkup"],
    },
    {
        "type": "semantic",
        "content": (
            "Jordan's standing to-do list: pick up dry cleaning, refill "
            "Nana's prescription, fix leaky kitchen faucet, book vet "
            "appointment for Max."
        ),
        "source": "Jordan's personal list, last session",
        "tags": ["jordan", "todo", "tasks", "dry_cleaning", "prescription", "faucet", "vet"],
    },
    # --- Grocery list / shopping ---
    {
        "type": "semantic",
        "content": (
            "Current grocery list (New Seasons Market, for Wednesday order): "
            "milk (whole, half-gallon), bread (Dave's Killer Bread, thin-sliced), "
            "bananas, apples (Honeycrisp), baby carrots, string cheese "
            "(for Riley's lunch), turkey deli slices, whole wheat wraps, "
            "avocados (2), Greek yogurt (plain, 32oz), eggs (free-range dozen), "
            "Jordan's crackers (Mary's Gone Crackers, Everything flavor), "
            "Nana Liz's decaf coffee (Peet's), dish soap."
        ),
        "source": "Running list, updated 2 sessions ago",
        "tags": [
            "grocery",
            "list",
            "shopping",
            "new_seasons",
            "items",
            "milk",
            "bread",
            "fruit",
            "lunch",
            "riley",
        ],
    },
]
