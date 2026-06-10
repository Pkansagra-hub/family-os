"""GAP-P1-004: LocalProjectionStore tests.

Epic 1, Issue 1.7.
"""

from __future__ import annotations

import pytest

from k1.fabric.stores.local_projection_store import LocalProjectionStore


@pytest.fixture
def store():
    """Create a fresh in-memory LocalProjectionStore."""
    s = LocalProjectionStore(":memory:")
    s.open()
    yield s
    s.close()


# ── TestConnectedResources ────────────────────────────────────────────────


class TestConnectedResources:
    def test_upsert_and_get(self, store):
        resource = {
            "resource_id": "res_cal_001",
            "actor_id": "actor_riley",
            "resource_kind": "calendar_event",
            "connector_id": "family.calendar",
            "label": "Riley's Calendar",
            "status": "active",
            "permissions": "read_write",
        }
        store.upsert_connected_resource(resource)
        got = store.get_connected_resource("res_cal_001")
        assert got is not None
        assert got["label"] == "Riley's Calendar"

    def test_list_by_actor(self, store):
        store.upsert_connected_resource(
            {
                "resource_id": "res_cal_001",
                "actor_id": "actor_riley",
                "resource_kind": "calendar_event",
                "connector_id": "family.calendar",
                "label": "Cal",
            }
        )
        store.upsert_connected_resource(
            {
                "resource_id": "res_task_001",
                "actor_id": "actor_riley",
                "resource_kind": "task",
                "connector_id": "family.tasks",
                "label": "Tasks",
            }
        )
        all_res = store.list_connected_resources("actor_riley")
        assert len(all_res) == 2

    def test_filter_by_kind(self, store):
        store.upsert_connected_resource(
            {
                "resource_id": "res_cal_001",
                "actor_id": "actor_riley",
                "resource_kind": "calendar_event",
                "connector_id": "family.calendar",
                "label": "Cal",
            }
        )
        store.upsert_connected_resource(
            {
                "resource_id": "res_task_001",
                "actor_id": "actor_riley",
                "resource_kind": "task",
                "connector_id": "family.tasks",
                "label": "Tasks",
            }
        )
        filtered = store.list_connected_resources("actor_riley", resource_kind="task")
        assert len(filtered) == 1
        assert filtered[0]["resource_kind"] == "task"


# ── TestHouseholdMembers ──────────────────────────────────────────────────


class TestHouseholdMembers:
    def test_upsert_and_get(self, store):
        store.upsert_household_member(
            {"person_id": "person_riley", "label": "Riley", "role": "child"}
        )
        got = store.get_household_member("person_riley")
        assert got is not None
        assert got["label"] == "Riley"


# ── TestAliasIndex ────────────────────────────────────────────────────────


class TestAliasIndex:
    def test_resolve_exact(self, store):
        store.upsert_connected_resource(
            {
                "resource_id": "res_cal_001",
                "actor_id": "actor_riley",
                "resource_kind": "calendar_event",
                "connector_id": "family.calendar",
                "label": "Riley's Calendar",
            }
        )
        store.rebuild_alias_index("actor_riley", "space_default")
        results = store.resolve_alias("riley's calendar", "actor_riley")
        assert len(results) >= 1

    def test_fuzzy_resolve(self, store):
        store.upsert_household_member(
            {"person_id": "person_riley", "label": "Riley", "role": "child"}
        )
        store.rebuild_alias_index("actor_riley", "space_default")
        results = store.fuzzy_resolve_alias("Ril", "actor_riley", entity_type="person")
        assert len(results) >= 1

    def test_not_found(self, store):
        results = store.resolve_alias("nonexistent", "actor_riley")
        assert len(results) == 0


# ── TestProjectionSnapshots ───────────────────────────────────────────────


class TestProjectionSnapshots:
    def test_upsert_and_get_fresh(self, store):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        store.upsert_projection_snapshot(
            {
                "resource_id": "res_cal_001",
                "snapshot": {"events": []},
                "captured_at": now,
            }
        )
        snap = store.get_fresh_snapshot("res_cal_001", max_age_seconds=3600)
        assert snap is not None
        assert snap["snapshot"] == {"events": []}

    def test_stale_snapshot(self, store):
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        store.upsert_projection_snapshot(
            {
                "resource_id": "res_cal_001",
                "snapshot": {"events": []},
                "captured_at": old,
            }
        )
        snap = store.get_fresh_snapshot("res_cal_001", max_age_seconds=60)
        assert snap is None  # stale — older than 60s

    def test_missing(self, store):
        assert store.get_fresh_snapshot("nonexistent") is None
