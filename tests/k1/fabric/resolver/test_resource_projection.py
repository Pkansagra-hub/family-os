"""GAP-P1-017 — Tests for resource projection (Contract B).

Spec: Epic 3.4, 3.6.
"""

from __future__ import annotations

import pytest

from k1.fabric.resolver.request_frame import PersonRef, RequestFrame, ResourceRef
from k1.fabric.resolver.resource_projection import (
    ResolveResourcesService,
    ResourceCandidate,
    ResourceUniverse,
    UnresolvedRef,
)
from k1.fabric.stores.global_projection_store import ConnectorRecord, GlobalProjectionStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def global_store() -> GlobalProjectionStore:
    """In-memory GPS with a connector admitted."""
    store = GlobalProjectionStore(db_path=":memory:")
    store.open()
    store.upsert_connector(
        ConnectorRecord(
            connector_id="family.calendar",
            label="Family Calendar",
            connector_type="native",
            provider_type="LOCAL",
            admission_verdict="admitted",
            registration_type="static",
            version="1.0.0",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )
    )
    return store


@pytest.fixture
def local_store() -> LocalProjectionStore:
    """In-memory LPS with a household member, connected resource, and alias."""
    store = LocalProjectionStore(db_path=":memory:")
    store.open()
    # Add actor_id explicitly since the store doesn't carry it in constructor
    actor_id = "actor-a"
    # Add a household member
    store.upsert_household_member(
        {
            "person_id": "person-riley",
            "label": "Riley",
            "role": "child",
            "linked_resource_ids": {"calendar": "res-cal-riley"},
        }
    )
    # Add a connected resource
    store.upsert_connected_resource(
        {
            "resource_id": "res-cal-riley",
            "actor_id": actor_id,
            "label": "Riley's Calendar",
            "resource_kind": "calendar_event",
            "connector_id": "family.calendar",
            "permissions": "read_write",
            "freshness_state": "fresh",
            "status": "active",
        }
    )
    # Build alias index from connected resources
    store.rebuild_alias_index(actor_id, "space-1")
    # Also add a direct alias for fuzzy/ambiguous tests
    store.upsert_alias_index(actor_id, "Riley", "person-riley", "person")
    return store


@pytest.fixture
def service(
    global_store: GlobalProjectionStore, local_store: LocalProjectionStore
) -> ResolveResourcesService:
    return ResolveResourcesService(global_store, local_store)


# ══════════════════════════════════════════════════════════════════════
# TestResolvePerson
# ══════════════════════════════════════════════════════════════════════


class TestResolvePerson:
    """exact alias match, fuzzy match, not_found, ambiguous (>1 match)."""

    def test_exact_alias_match(self, service):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
            person_refs=[PersonRef(raw="Riley", confidence="high")],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        assert len(universe.person_candidates) == 1
        assert universe.person_candidates[0].person_id == "person-riley"
        assert universe.person_candidates[0].resolved is True

    def test_fuzzy_match(self, service, local_store):
        """Fuzzy alias should match via LIKE."""
        local_store.upsert_alias_index("actor-a", "Riley", "person-riley", "person")
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
            person_refs=[PersonRef(raw="Ril", confidence="medium")],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        assert len(universe.person_candidates) == 1

    def test_not_found(self, service):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
            person_refs=[PersonRef(raw="Zargon", confidence="low")],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        assert len(universe.person_candidates) == 0
        assert len(universe.unresolved) >= 1
        assert any(u.reason == "not_found" for u in universe.unresolved)

    def test_ambiguous_multiple_matches(self, service, local_store):
        """Two aliases → ambiguous."""
        local_store.upsert_alias_index("actor-a", "morgan", "person-m1", "person")
        local_store.upsert_alias_index("actor-a", "morgan", "person-m2", "person")
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
            person_refs=[PersonRef(raw="morgan", confidence="medium")],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        unresolved_persons = [u for u in universe.unresolved if u.entity_type == "person"]
        assert len(unresolved_persons) >= 1
        assert unresolved_persons[0].reason == "ambiguous"

    def test_needs_resolution_false_skipped(self, service):
        """PersonRef with needs_resolution=False is skipped entirely."""
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
            person_refs=[PersonRef(raw="Riley", confidence="high", needs_resolution=False)],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        assert len(universe.person_candidates) == 0


# ══════════════════════════════════════════════════════════════════════
# TestResolveResource
# ══════════════════════════════════════════════════════════════════════


class TestResolveResource:
    """needs_resolution → connector_id, direct candidates, stale, permission exclusions."""

    def test_needs_resolution_true_gets_connector_id(self, service):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
            resource_refs=[ResourceRef(raw="Riley's Calendar", confidence="medium")],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        assert len(universe.resource_candidates) >= 1
        assert universe.resource_candidates[0].connector_id == "family.calendar"

    def test_needs_resolution_false_direct_candidate(self, service):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
            resource_refs=[
                ResourceRef(
                    raw="some_calendar",
                    resource_kind_hint="calendar_event",
                    confidence="medium",
                    needs_resolution=False,
                ),
            ],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        assert len(universe.resource_candidates) >= 1
        # Direct candidate has empty connector_id
        assert universe.resource_candidates[0].connector_id == ""
        assert universe.resource_candidates[0].resource_kind == "calendar_event"

    def test_not_found_resource(self, service):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
            resource_refs=[ResourceRef(raw="nonexistent_list", confidence="low")],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        unresolved_res = [u for u in universe.unresolved if u.entity_type == "resource"]
        assert len(unresolved_res) >= 1
        assert unresolved_res[0].reason == "not_found"

    def test_readonly_with_write_intent_excluded(self, service, local_store):
        """Read-only resource + write intent → permission_denied."""
        local_store.upsert_connected_resource(
            {
                "resource_id": "res-read-only",
                "actor_id": "actor-a",
                "label": "Read-only list",
                "resource_kind": "task",
                "connector_id": "enterprise.tasks",
                "permissions": "read_only",
                "freshness_state": "fresh",
                "status": "active",
            }
        )
        local_store.upsert_alias_index("actor-a", "Read-only list", "res-read-only", "resource")

        from k1.fabric.resolver.request_frame import RequestFrameIntent

        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="update task",
                    operation_hint="update",
                ),
            ],
            resource_refs=[ResourceRef(raw="Read-only list", confidence="medium")],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        unresolved_res = [u for u in universe.unresolved if u.entity_type == "resource"]
        assert any(u.reason == "permission_denied" for u in unresolved_res)


# ══════════════════════════════════════════════════════════════════════
# TestUniverseCompleteness
# ══════════════════════════════════════════════════════════════════════


class TestUniverseCompleteness:
    """all resolved → complete, some unresolved → partial, all stale → stale."""

    def test_all_resolved_complete(self, service):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
            person_refs=[PersonRef(raw="Riley", confidence="high")],
            resource_refs=[ResourceRef(raw="Riley's Calendar", confidence="medium")],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        assert universe.completeness == "complete"
        assert universe.freshness == "fresh"

    def test_some_unresolved_partial(self, service):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
            person_refs=[PersonRef(raw="Zargon", confidence="low")],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        assert universe.completeness in ("partial", "unknown")

    def test_scope_proof_exists(self, service):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
            person_refs=[PersonRef(raw="Riley", confidence="high")],
        )
        universe = service.resolve(frame, "actor-a", "space-1")
        assert universe.scope_proof.actor_id == "actor-a"
        assert universe.scope_proof.space_id == "space-1"
        assert len(universe.scope_proof.projection_sources) >= 1
