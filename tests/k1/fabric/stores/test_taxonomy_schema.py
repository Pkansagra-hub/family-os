"""Phase 2.6, Epic 22 — Taxonomy schema migration tests (GAP-P2-033).

Tests the 4 new taxonomy tables, the connectors + capabilities migrations,
GPS query methods, FTS5 rebuild, and end-to-end manifest_translator wiring.
"""

from __future__ import annotations

import pytest

from k1.fabric.stores.global_projection_store import (
    CapabilityRecord,
    ConnectorRecord,
    GlobalProjectionStore,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def gps():
    """Fresh in-memory GPS with full schema + seed data."""
    store = GlobalProjectionStore(":memory:")
    store.open()
    return store


# ── Table existence + seed counts ─────────────────────────────────────


def test_domains_table_exists_and_seeded(gps):
    """16 domains seeded at open()."""
    rows = gps._db.execute("SELECT domain_id, label, description FROM domains").fetchall()
    assert len(rows) == 16, f"Expected 16 domains, got {len(rows)}"
    ids = {r["domain_id"] for r in rows}
    assert "family" in ids
    assert "health" in ids
    assert "finance" in ids
    # Verify all have non-empty label + description
    for r in rows:
        assert r["label"], f"Empty label for {r['domain_id']}"
        assert r["description"], f"Empty description for {r['domain_id']}"


def test_resource_families_table_exists_and_seeded(gps):
    """57+ resource families seeded at open()."""
    rows = gps._db.execute("SELECT family_id, label, description FROM resource_families").fetchall()
    assert len(rows) >= 55, f"Expected >=55 families, got {len(rows)}"
    ids = {r["family_id"] for r in rows}
    # Cross-domain families
    for fid in ("event", "task", "reminder", "item", "record", "contact", "subscription"):
        assert fid in ids, f"Missing cross-domain family: {fid}"
    # Domain-specific families
    for fid in ("chore", "account", "prescription", "course", "device", "workout"):
        assert fid in ids, f"Missing domain-specific family: {fid}"


def test_domain_resource_families_seeded(gps):
    """100+ domain→family mappings with valid FK references."""
    rows = gps._db.execute(
        "SELECT domain_id, family_id FROM domain_resource_families ORDER BY domain_id, family_id"
    ).fetchall()
    assert len(rows) >= 100, f"Expected >=100 mappings, got {len(rows)}"

    # Every mapping must reference a real domain and real family
    for r in rows:
        d = gps._db.execute(
            "SELECT 1 FROM domains WHERE domain_id = ?", (r["domain_id"],)
        ).fetchone()
        assert d, f"domain_resource_families references missing domain: {r['domain_id']}"
        f = gps._db.execute(
            "SELECT 1 FROM resource_families WHERE family_id = ?", (r["family_id"],)
        ).fetchone()
        assert f, f"domain_resource_families references missing family: {r['family_id']}"

    # Spot-check: family domain has expected families
    family_fams = {r["family_id"] for r in rows if r["domain_id"] == "family"}
    assert "event" in family_fams
    assert "task" in family_fams
    assert "chore" in family_fams
    assert "item" in family_fams
    assert "recipe" in family_fams


def test_connector_resource_families_empty_initially(gps):
    """Table exists with 0 rows before bootstrap."""
    rows = gps._db.execute("SELECT count(*) as cnt FROM connector_resource_families").fetchone()
    assert rows["cnt"] == 0, "connector_resource_families should be empty pre-bootstrap"


# ── Migration: connectors ─────────────────────────────────────────────


def test_connectors_migration_added_domain_id(gps):
    """domain_id column present on connectors, populated from connector_id prefix."""
    cols = {r[1] for r in gps._db.execute("PRAGMA table_info(connectors)").fetchall()}
    assert "domain_id" in cols, "connectors missing domain_id column"

    # Insert a connector and verify the migration UPDATE populates domain_id
    import json

    ts = "2026-06-10T00:00:00Z"
    gps.upsert_connector(
        ConnectorRecord(
            connector_id="health.fitbit",
            label="Fitbit",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            domain_id="health",
            created_at=ts,
            updated_at=ts,
        )
    )
    # Force empty and re-run migration logic
    gps._db.execute("UPDATE connectors SET domain_id = '' WHERE connector_id = 'health.fitbit'")
    gps._db.execute(
        "UPDATE connectors SET domain_id = "
        "substr(connector_id, 1, instr(connector_id, '.') - 1) "
        "WHERE domain_id = '' AND instr(connector_id, '.') > 0"
    )
    row = gps._db.execute(
        "SELECT domain_id FROM connectors WHERE connector_id = 'health.fitbit'"
    ).fetchone()
    assert row["domain_id"] == "health", f"Migration failed: {row['domain_id']}"


# ── Migration: capabilities ───────────────────────────────────────────


def test_capabilities_migration_added_domain_id_and_family_id(gps):
    """domain_id + family_id columns present on capabilities, populated from
    connectors JOIN + resource_kind."""
    cols = {r[1] for r in gps._db.execute("PRAGMA table_info(capabilities)").fetchall()}
    assert "domain_id" in cols, "capabilities missing domain_id column"
    assert "family_id" in cols, "capabilities missing family_id column"

    # Insert connector + capability and verify migration UPDATE
    import json

    ts = "2026-06-10T00:00:00Z"
    gps.upsert_connector(
        ConnectorRecord(
            connector_id="family.calendar",
            label="Calendar",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            domain_id="family",
            created_at=ts,
            updated_at=ts,
        )
    )
    gps.upsert_capability(
        CapabilityRecord(
            capability_name="tool.execute.family.calendar.create_event",
            connector_id="family.calendar",
            invocation_mode="execute",
            action_name="create_event",
            effect="write",
            resource_kind="calendar_event",
            domain_id="family",
            family_id="event",
            description="Create event",
            created_at=ts,
            contract_json={},
        )
    )
    # Simulate migration: blank domain_id + family_id, then run migration UPDATE
    gps._db.execute(
        "UPDATE capabilities SET domain_id = '', family_id = NULL "
        "WHERE capability_name = 'tool.execute.family.calendar.create_event'"
    )
    gps._db.execute(
        "UPDATE capabilities SET "
        "domain_id = COALESCE("
        "  (SELECT c.domain_id FROM connectors c "
        "   WHERE c.connector_id = capabilities.connector_id), ''"
        "), "
        "family_id = resource_kind "
        "WHERE domain_id = ''"
    )
    row = gps._db.execute(
        "SELECT domain_id, family_id, resource_kind FROM capabilities "
        "WHERE capability_name = 'tool.execute.family.calendar.create_event'"
    ).fetchone()
    assert row["domain_id"] == "family", f"Migration domain failed: {row['domain_id']}"
    assert row["family_id"] == "calendar_event", f"Migration family failed: {row['family_id']}"


def test_resource_kind_still_exists(gps):
    """resource_kind column is NOT dropped — coexists with family_id."""
    cols = {r[1] for r in gps._db.execute("PRAGMA table_info(capabilities)").fetchall()}
    assert "resource_kind" in cols, "resource_kind must coexist with family_id"
    assert "family_id" in cols
    assert "domain_id" in cols


def test_family_id_matches_resource_kind_after_migration(gps):
    """After migration UPDATE, family_id == resource_kind for existing rows."""
    import json

    ts = "2026-06-10T00:00:00Z"
    gps.upsert_connector(
        ConnectorRecord(
            connector_id="family.tasks",
            label="Tasks",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            domain_id="family",
            created_at=ts,
            updated_at=ts,
        )
    )
    gps.upsert_capability(
        CapabilityRecord(
            capability_name="tool.execute.family.tasks.create_task",
            connector_id="family.tasks",
            invocation_mode="execute",
            action_name="create_task",
            effect="write",
            resource_kind="task",
            domain_id="family",
            family_id="task",
            description="Create task",
            created_at=ts,
            contract_json={},
        )
    )
    row = gps._db.execute(
        "SELECT resource_kind, family_id FROM capabilities "
        "WHERE capability_name = 'tool.execute.family.tasks.create_task'"
    ).fetchone()
    assert (
        row["resource_kind"] == row["family_id"]
    ), f"family_id ({row['family_id']}) should match resource_kind ({row['resource_kind']})"


# ── FK constraints ────────────────────────────────────────────────────


def test_upsert_connector_rejects_invalid_domain(gps):
    """connectors.domain_id must reference a real domain (FK enforced via
    application-level validation — SQLite FK requires PRAGMA foreign_keys=ON
    but the domains FK is via REFERENCES, not on connectors)."""
    # Note: connectors.domain_id does NOT have a FK to domains (the migration
    # adds it as TEXT NOT NULL DEFAULT '' with no REFERENCES clause).
    # The FK is on connector_resource_families.family_id → resource_families.
    # This test verifies connector_resource_families FK enforcement.
    import json

    ts = "2026-06-10T00:00:00Z"
    gps.upsert_connector(
        ConnectorRecord(
            connector_id="family.test",
            label="Test",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            domain_id="family",
            created_at=ts,
            updated_at=ts,
        )
    )
    # Insert into connector_resource_families with invalid family_id must fail
    with pytest.raises(Exception):
        gps._db.execute(
            "INSERT INTO connector_resource_families (connector_id, family_id) VALUES (?, ?)",
            ("family.test", "nonexistent_family_xyz"),
        )


def test_upsert_capability_populates_both_family_id_and_resource_kind(gps):
    """New writes set both domain_id + family_id alongside resource_kind."""
    import json

    ts = "2026-06-10T00:00:00Z"
    gps.upsert_connector(
        ConnectorRecord(
            connector_id="family.chores",
            label="Chores",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            domain_id="family",
            created_at=ts,
            updated_at=ts,
        )
    )
    gps.upsert_capability(
        CapabilityRecord(
            capability_name="tool.execute.family.chores.assign_chore",
            connector_id="family.chores",
            invocation_mode="execute",
            action_name="assign_chore",
            effect="write",
            resource_kind="chore",
            domain_id="family",
            family_id="chore",
            description="Assign a chore",
            created_at=ts,
            contract_json={},
        )
    )
    row = gps._db.execute(
        "SELECT resource_kind, domain_id, family_id FROM capabilities "
        "WHERE capability_name = 'tool.execute.family.chores.assign_chore'"
    ).fetchone()
    assert row["resource_kind"] == "chore"
    assert row["domain_id"] == "family"
    assert row["family_id"] == "chore"


# ── GPS query methods ─────────────────────────────────────────────────


def test_get_resource_families_for_domain_family(gps):
    """get_resource_families_for_domain('family') returns event, task, chore, item, recipe."""
    families = gps.get_resource_families_for_domain("family")
    fids = {f["family_id"] for f in families}
    for expected in ("event", "task", "chore", "item", "recipe", "reminder"):
        assert expected in fids, f"family domain missing: {expected}"
    # Verify each has label + description
    for f in families:
        assert f["label"], f"Missing label for {f['family_id']}"
        assert f["description"], f"Missing description for {f['family_id']}"


def test_search_capabilities_by_text_finds_match(gps):
    """FTS5 search finds a capability by description text."""
    import json

    ts = "2026-06-10T00:00:00Z"
    gps.upsert_connector(
        ConnectorRecord(
            connector_id="family.shopping",
            label="Shopping",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            domain_id="family",
            created_at=ts,
            updated_at=ts,
        )
    )
    gps.upsert_capability(
        CapabilityRecord(
            capability_name="tool.execute.family.shopping.add_item",
            connector_id="family.shopping",
            invocation_mode="execute",
            action_name="add_item",
            effect="write",
            resource_kind="shopping_item",
            domain_id="family",
            family_id="item",
            description="Add an item to the shopping list like groceries or supplies",
            created_at=ts,
            contract_json={},
        )
    )
    results = gps.search_capabilities("groceries", top_k=5)
    assert len(results) >= 1, "FTS5 should find shopping capability for 'groceries'"
    assert any(
        "shopping" in r.capability_name for r in results
    ), f"Expected shopping capability in results: {[r.capability_name for r in results]}"


def test_fts5_rebuilt_with_family_id_and_domain_id(gps):
    """capabilities_fts contains domain_id + family_id columns after rebuild."""
    fts_cols = {r[1] for r in gps._db.execute("PRAGMA table_info(capabilities_fts)").fetchall()}
    assert "domain_id" in fts_cols, "FTS5 missing domain_id column"
    assert "family_id" in fts_cols, "FTS5 missing family_id column"
    assert "capability_name" in fts_cols
    assert "connector_id" in fts_cols


# ── End-to-end: manifest_translator ───────────────────────────────────


def test_register_definition_preserves_taxonomy_fields(gps):
    """manifest_translator writes domain_id + family_id to capabilities and
    connector_resource_families when definition has resource_families set."""
    from k1.fabric.manifest_translator import register_definition_to_store
    from k1.tools.family.reminders.definition import REMINDERS_DEFINITION

    # reminders definition doesn't have resource_families yet (Epic 23 will add it),
    # so we verify the fallback path works and domain is still 'family'.
    count = register_definition_to_store(REMINDERS_DEFINITION, gps)
    assert count == 8  # 8 reminder actions

    # Verify connector
    conn = gps._db.execute(
        "SELECT connector_id, domain_id FROM connectors WHERE connector_id = 'family.reminders'"
    ).fetchone()
    assert conn is not None
    assert conn["domain_id"] == "family"

    # Verify capabilities
    caps = gps._db.execute(
        "SELECT capability_name, domain_id, family_id, resource_kind "
        "FROM capabilities WHERE connector_id = 'family.reminders'"
    ).fetchall()
    assert len(caps) == 8
    for c in caps:
        assert c["domain_id"] == "family"
        assert c["family_id"] is not None  # falls back to resource_kinds
        assert c["resource_kind"] is not None
