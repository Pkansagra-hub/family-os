"""Phase 2.6, Epic 23 — Family tool definition taxonomy migration tests (GAP-P2-034).

Validates that all 6 family tool definitions declare domain_id + resource_families,
entity_types are canonical, can_reference has no stale values, and
register_definition_to_store() produces correct family_id in GPS.
"""

from __future__ import annotations

import pytest

from k1.fabric.manifest_translator import register_definition_to_store
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.chores.definition import CHORES_DEFINITION
from k1.tools.family.family_settings.definition import FAMILY_SETTINGS_DEFINITION
from k1.tools.family.reminders.definition import REMINDERS_DEFINITION
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION
from k1.tools.family.tasks.definition import TASKS_DEFINITION

ALL_DEFINITIONS = [
    CALENDAR_DEFINITION,
    TASKS_DEFINITION,
    REMINDERS_DEFINITION,
    CHORES_DEFINITION,
    SHOPPING_DEFINITION,
    FAMILY_SETTINGS_DEFINITION,
]


# ── 23.9.1 — All 6 have domain_id ─────────────────────────────────────


def test_all_6_definitions_have_domain_id():
    """Every DEFINITION sets domain_id='family'."""
    for d in ALL_DEFINITIONS:
        assert (
            d.domain_id == "family"
        ), f"{d.adapter_id}: expected domain_id='family', got {d.domain_id!r}"


# ── 23.9.2 — All 6 have resource_families ─────────────────────────────


def test_all_6_definitions_have_resource_families():
    """Every DEFINITION sets resource_families (non-empty list)."""
    for d in ALL_DEFINITIONS:
        assert d.resource_families, f"{d.adapter_id}: resource_families is empty or None"
        assert isinstance(d.resource_families, list)
        assert len(d.resource_families) >= 1


# ── 23.9.3 — resource_families values match taxonomy ──────────────────

EXPECTED_FAMILIES = {
    "calendar": ["event"],
    "tasks": ["task"],
    "reminders": ["reminder"],
    "chores": ["chore"],
    "shopping": ["item"],
    "family_settings": ["setting"],
}


def test_resource_families_values_match_taxonomy():
    """Each adapter's resource_families matches the Phase 2.6 taxonomy mapping."""
    for d in ALL_DEFINITIONS:
        expected = EXPECTED_FAMILIES.get(d.adapter_id)
        assert expected is not None, f"Unknown adapter: {d.adapter_id}"
        assert (
            d.resource_families == expected
        ), f"{d.adapter_id}: expected resource_families={expected}, got {d.resource_families}"


# ── 23.9.4 — resource_kinds still present ─────────────────────────────


def test_resource_kinds_still_present():
    """Old resource_kinds field not removed from any definition."""
    for d in ALL_DEFINITIONS:
        assert (
            d.resource_kinds is not None
        ), f"{d.adapter_id}: resource_kinds was removed — must coexist with resource_families"
        assert isinstance(d.resource_kinds, list)
        assert len(d.resource_kinds) >= 1, f"{d.adapter_id}: resource_kinds should be non-empty"


# ── 23.9.5 — entity_types are canonical ───────────────────────────────

EXPECTED_ENTITY_TYPES = {
    "calendar": "calendar_event",
    "tasks": "task",
    "reminders": "reminder",
    "chores": "chore",
    "shopping": "shopping_item",
    "family_settings": "family_setting",
}

STALE_ENTITY_TYPES = {"task_item", "chore_occurrence", ""}


def test_entity_types_are_canonical():
    """No definition uses stale entity_type values."""
    for d in ALL_DEFINITIONS:
        expected = EXPECTED_ENTITY_TYPES.get(d.adapter_id)
        assert expected is not None, f"Unknown adapter: {d.adapter_id}"
        assert (
            d.entity_type == expected
        ), f"{d.adapter_id}: expected entity_type={expected!r}, got {d.entity_type!r}"
        assert (
            d.entity_type not in STALE_ENTITY_TYPES
        ), f"{d.adapter_id}: entity_type={d.entity_type!r} is stale"


# ── 23.9.6 — entity_type matches tables_sql ───────────────────────────


def test_entity_type_in_tables_sql():
    """Each adapter's tables_sql references its entity_type or a closely related
    table name.  This is a smoke test — DDL files use plural table names
    (task_items, chore_occurrences) which are not identical to entity_type
    (task, chore), so we check for reasonable substring presence."""
    # Tasks: entity_type="task", DDL table="task_items" → "task" appears
    # Chores: entity_type="chore", DDL table="chore_occurrences" → "chore" appears
    # Others: entity_type matches DDL naming closely
    for d in ALL_DEFINITIONS:
        sql = (d.tables_sql or "").lower()
        et = (d.entity_type or "").lower()
        if not et or not sql:
            continue
        # The entity_type stem should appear somewhere in the DDL
        # (table names, column names, comments, etc.)
        assert (
            et in sql or et.rstrip("s") in sql
        ), f"{d.adapter_id}: entity_type={et!r} not found in tables_sql"


# ── 23.9.7 — can_reference has no stale entity_types ──────────────────


def test_can_reference_no_stale_entity_types():
    """No definition's can_reference contains 'task_item' or 'chore_occurrence'."""
    for d in ALL_DEFINITIONS:
        refs = d.can_reference or []
        assert "task_item" not in refs, f"{d.adapter_id}: can_reference contains stale 'task_item'"
        assert (
            "chore_occurrence" not in refs
        ), f"{d.adapter_id}: can_reference contains stale 'chore_occurrence'"

    # Verify all can_reference entries point to valid entity_types
    valid_types = {d.entity_type for d in ALL_DEFINITIONS if d.entity_type}
    for d in ALL_DEFINITIONS:
        for ref in d.can_reference or []:
            assert ref in valid_types, (
                f"{d.adapter_id}: can_reference entry {ref!r} does not match "
                f"any adapter's entity_type. Valid: {sorted(valid_types)}"
            )


# ── 23.9.8 — Family Settings has enrichment fields ────────────────────


def test_family_settings_has_enrichment_fields():
    """Family Settings (newest adapter) has entity_type, actor_scope, domain_tags set."""
    d = FAMILY_SETTINGS_DEFINITION
    assert d.entity_type == "family_setting"
    assert d.actor_scope == ["parent", "admin", "system"]
    assert d.domain_tags == ["configuration", "policy", "feature_flags"]
    assert d.resource_kinds == ["setting"]
    assert d.resource_families == ["setting"]
    assert d.domain_id == "family"


# ── 23.9.9 — register_definition produces family_id in GPS ────────────


def test_register_definition_produces_family_id():
    """After register_definition_to_store(), GPS capability rows have
    family_id matching resource_families[0]."""
    gps = GlobalProjectionStore(":memory:")
    gps.open()

    # Use calendar (has resource_families=["event"])
    count = register_definition_to_store(CALENDAR_DEFINITION, gps)
    assert count > 0

    caps = gps._db.execute(
        "SELECT capability_name, domain_id, family_id, resource_kind "
        "FROM capabilities WHERE connector_id = 'family.calendar'"
    ).fetchall()
    assert len(caps) == count
    for c in caps:
        assert c["domain_id"] == "family", f"Expected domain_id='family', got {c['domain_id']!r}"
        assert c["family_id"] == "event", (
            f"Expected family_id='event', got {c['family_id']!r} " f"for {c['capability_name']}"
        )
        assert c["resource_kind"] is not None  # still present

    # Verify connector_resource_families is populated (post-Epic-23,
    # definition.resource_families is set)
    crf = gps._db.execute(
        "SELECT family_id, is_primary FROM connector_resource_families "
        "WHERE connector_id = 'family.calendar'"
    ).fetchall()
    assert len(crf) >= 1, "connector_resource_families should be populated"
    family_ids = {r["family_id"] for r in crf}
    assert "event" in family_ids

    gps.close()
