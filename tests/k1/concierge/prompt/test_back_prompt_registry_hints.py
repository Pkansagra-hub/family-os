"""Phase 2.6, Epic 25 — Registry hints narrative tests (GAP-P2-036).

Validates that build_back_prompt() produces per-domain grouped family
lists with descriptions from the new taxonomy dict shape, and falls
back gracefully to the old flat-list shape.
"""

from __future__ import annotations

from k1.concierge.prompt.back_prompt import build_back_prompt

# ── Helpers ──────────────────────────────────────────────────────────


def _minimal_task() -> dict:
    return {"task_id": "t1", "action": "test", "intents": [{"action": "test"}]}


NEW_SHAPE_HINTS = {
    "domains": [
        {
            "domain_id": "family",
            "label": "Family & Household",
            "description": "Parenting, chores, calendar",
        },
        {
            "domain_id": "health",
            "label": "Health & Wellness",
            "description": "Medical records, prescriptions",
        },
    ],
    "resource_families": [
        {
            "domain_id": "family",
            "label": "Family & Household",
            "families": [
                {
                    "family_id": "event",
                    "label": "Events",
                    "description": "Calendar events and appointments",
                },
                {"family_id": "task", "label": "Tasks", "description": "To-do items and homework"},
                {
                    "family_id": "chore",
                    "label": "Chores",
                    "description": "Recurring household duties",
                },
            ],
        },
        {
            "domain_id": "health",
            "label": "Health & Wellness",
            "families": [
                {
                    "family_id": "prescription",
                    "label": "Prescriptions",
                    "description": "Medications and refills",
                },
                {
                    "family_id": "vital",
                    "label": "Vital Signs",
                    "description": "Blood pressure, heart rate",
                },
            ],
        },
    ],
}

OLD_SHAPE_HINTS = {
    "domains": ["family", "health"],
    "resource_families": ["event", "task", "chore"],
}


# ── 25.6.1 — Grouped families in prompt ──────────────────────────────


def test_prompt_includes_grouped_families():
    """Prompt contains 'family — Family & Household: event, task, chore'
    grouped format when new dict shape provided."""
    prompt = build_back_prompt(_minimal_task(), registry_hints=NEW_SHAPE_HINTS)
    assert "Registered resource families by domain" in prompt
    assert "family — Family & Household:" in prompt
    assert "health — Health & Wellness:" in prompt
    assert "event" in prompt
    assert "task" in prompt
    assert "chore" in prompt
    assert "prescription" in prompt


# ── 25.6.2 — Family descriptions in prompt ───────────────────────────


def test_prompt_includes_family_descriptions():
    """Prompt contains description text alongside family IDs."""
    prompt = build_back_prompt(_minimal_task(), registry_hints=NEW_SHAPE_HINTS)
    assert "Calendar events" in prompt
    assert "To-do items" in prompt
    assert "Recurring household" in prompt


# ── 25.6.3 — Fallback to flat list ───────────────────────────────────


def test_prompt_falls_back_to_flat_list():
    """Old flat resource_families list still renders correctly."""
    prompt = build_back_prompt(_minimal_task(), registry_hints=OLD_SHAPE_HINTS)
    assert "Currently registered resource families:" in prompt
    assert "event, task, chore" in prompt
    # Should NOT have the grouped header
    assert "Registered resource families by domain:" not in prompt


# ── 25.6.4 — None registry_hints is graceful ────────────────────────


def test_prompt_no_registry_hints_graceful():
    """registry_hints=None → fallback text, no crash."""
    prompt = build_back_prompt(_minimal_task(), registry_hints=None)
    assert "No domain list is available" in prompt
    assert "No resource family list is available" in prompt


# ── 25.6.5 — Domain list from new shape ──────────────────────────────


def test_prompt_domain_list_from_new_shape():
    """domains as list of dicts renders 'family (Family & Household)' format
    with domain_id first, label in parentheses."""
    prompt = build_back_prompt(_minimal_task(), registry_hints=NEW_SHAPE_HINTS)
    assert "family (Family & Household)" in prompt
    assert "health (Health & Wellness)" in prompt
    assert "use the short code before the parenthesis" in prompt.lower()


# ── 25.6.6 — Placeholder rename verified ────────────────────────────


def test_prompt_placeholder_rename():
    """The new {registry_family_narrative} works; old placeholder name is gone."""
    from k1.concierge.prompt.back_prompt import BACK_SYSTEM_PROMPT

    assert "{registry_family_narrative}" in BACK_SYSTEM_PROMPT
    assert "{registry_resource_families_narrative}" not in BACK_SYSTEM_PROMPT
    assert "{registry_hints_narrative}" in BACK_SYSTEM_PROMPT


# ── 25.6.7 — Token budget ────────────────────────────────────────────


def test_prompt_registry_narrative_token_budget():
    """Registry hints are filtered to active-only domains and families.
    An in-memory GPS with no connectors shows zero domains — the prompt
    is lean and the total stays well under 30K chars."""
    from k1.fabric.stores.global_projection_store import GlobalProjectionStore
    from k1.kernel.service import KernelService

    gps = GlobalProjectionStore(":memory:")
    gps.open()
    hints = KernelService._build_registry_hints(gps)
    prompt = build_back_prompt(_minimal_task(), registry_hints=hints)
    gps.close()

    # Total prompt should stay well under any reasonable budget
    assert len(prompt) < 30000, f"Total prompt too long: {len(prompt)} chars"
    # The prompt is valid even with zero active connectors (empty GPS)
    assert "use the short code" in prompt.lower()
    assert "No resource family list" in prompt


# ── 25.6.8 — Empty hints dict is graceful ────────────────────────────


def test_prompt_empty_hints_dict_graceful():
    """Empty dict → fallback text for both domains and families."""
    prompt = build_back_prompt(_minimal_task(), registry_hints={})
    assert "No domain list is available" in prompt
    assert "No resource family list is available" in prompt
