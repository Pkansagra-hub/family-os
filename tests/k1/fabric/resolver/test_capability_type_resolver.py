"""GAP-P1-018 — Tests for CapabilityTypeResolver.

Spec: Epic 3.5, 3.6.
"""

from __future__ import annotations

import pytest

from k1.fabric.resolver.capability_type_resolver import (
    UNIVERSAL_OPERATION_ALIASES,
    CapabilityTypeResolver,
    ResolvedIntentType,
)
from k1.fabric.resolver.request_frame import (
    RequestFrame,
    RequestFrameIntent,
)
from k1.fabric.resolver.resource_projection import (
    ResourceUniverse,
    ScopeProof,
)
from k1.fabric.stores.global_projection_store import ConnectorRecord, GlobalProjectionStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def global_store() -> GlobalProjectionStore:
    """In-memory GPS seeded with graph tables for calendar capabilities."""
    store = GlobalProjectionStore(db_path=":memory:")
    store.open()

    # Register the calendar connector
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

    # Seed concept aliases
    store.upsert_concept_alias("calendar", "calendar", domain="family")
    store.upsert_concept_alias("event", "calendar_event", domain="family")
    store.upsert_concept_alias("appointment", "calendar_event", domain="family")
    store.upsert_concept_alias("dentist", "calendar_event", domain="family")
    store.upsert_concept_alias("calendar_event", "calendar_event", domain="family")

    # Seed concept → resource_family edges
    store.upsert_concept_resource_edge("calendar", "calendar_event", "family")
    store.upsert_concept_resource_edge("calendar_event", "calendar_event", "family")

    # Seed operation aliases
    for alias, (op_family, effect) in UNIVERSAL_OPERATION_ALIASES.items():
        store.upsert_operation_alias(alias, op_family, effect)

    # Seed capability_type_index
    store.upsert_capability_type_index(
        capability_name="tool.read.family.calendar.list",
        connector_id="family.calendar",
        domain="family",
        resource_family="calendar_event",
        operation_family="list",
        effect="read",
    )
    store.upsert_capability_type_index(
        capability_name="tool.execute.family.calendar.create",
        connector_id="family.calendar",
        domain="family",
        resource_family="calendar_event",
        operation_family="create",
        effect="write",
    )
    store.upsert_capability_type_index(
        capability_name="tool.execute.family.calendar.update",
        connector_id="family.calendar",
        domain="family",
        resource_family="calendar_event",
        operation_family="update",
        effect="write",
    )
    store.upsert_capability_type_index(
        capability_name="tool.execute.family.calendar.delete",
        connector_id="family.calendar",
        domain="family",
        resource_family="calendar_event",
        operation_family="delete",
        effect="write",
    )

    return store


@pytest.fixture
def local_store() -> LocalProjectionStore:
    store = LocalProjectionStore(db_path=":memory:")
    store.open()
    return store


@pytest.fixture
def resolver(
    global_store: GlobalProjectionStore, local_store: LocalProjectionStore
) -> CapabilityTypeResolver:
    return CapabilityTypeResolver(global_store, local_store)


@pytest.fixture
def empty_universe() -> ResourceUniverse:
    return ResourceUniverse(
        universe_id="uni-empty",
        resource_candidates=[],
        person_candidates=[],
        unresolved=[],
        scope_proof=ScopeProof(
            scope_proof_id="scope-empty",
            actor_id="actor-a",
            space_id="space-1",
        ),
        completeness="unknown",
        freshness="unknown",
    )


# ══════════════════════════════════════════════════════════════════════
# TestOperationResolution
# ══════════════════════════════════════════════════════════════════════


class TestOperationResolution:
    """create → (create, write), list → (list, read), unknown → default."""

    def test_create_maps_to_create_write(self, resolver, empty_universe):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="Add dentist appointment",
                    domain="family",
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert len(results) == 1
        assert results[0].operation_family == "create"
        assert results[0].effect == "write"

    def test_list_maps_to_list_read(self, resolver, empty_universe):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="Show my calendar",
                    domain="family",
                    operation_hint="list",
                    resource_kind_hint="calendar_event",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert len(results) == 1
        assert results[0].operation_family == "list"
        assert results[0].effect == "read"

    def test_unknown_operation_defaults(self, resolver, empty_universe):
        """An operation not in any table defaults to (op_hint, read)."""
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="zargonize the widget",
                    operation_hint="zargonize",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert len(results) == 1
        assert results[0].operation_family == "zargonize"
        assert results[0].effect == "read"


# ══════════════════════════════════════════════════════════════════════
# TestConceptResolution
# ══════════════════════════════════════════════════════════════════════


class TestConceptResolution:
    """Exact concept_alias match, fallback to action text, no match → empty."""

    def test_exact_concept_alias_match(self, resolver, empty_universe):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="Add dentist appointment",
                    domain="family",
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert len(results) == 1
        assert results[0].resource_family is not None

    def test_action_text_extraction_fallback(self, resolver, empty_universe):
        """Even without resource_kind_hint, action text words can map to concepts."""
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="book a dentist appointment",
                    domain="family",
                    operation_hint="create",
                    resource_kind_hint=None,
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert len(results) == 1
        # "dentist" is a concept alias for "calendar_event"
        assert results[0].resource_family == "calendar_event"

    def test_no_match_empty_fallback(self, resolver, empty_universe):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="xyzzy plugh",
                    domain="unknown",
                    operation_hint="create",
                    resource_kind_hint=None,
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert len(results) == 1
        # No concept found, no resource_family
        assert results[0].resource_family is None


# ══════════════════════════════════════════════════════════════════════
# TestResourceFamilyMapping
# ══════════════════════════════════════════════════════════════════════


class TestResourceFamilyMapping:
    """concept→resource_family edge found, missing edge → direct, missing both → rk_hint."""

    def test_concept_to_resource_family_edge(self, resolver, empty_universe):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="add event",
                    domain="family",
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert results[0].resource_family == "calendar_event"

    def test_fallback_to_direct_concept(self, resolver, empty_universe, global_store):
        """If no concept_resource_edge but concept resolves as resource_family
        via lookup_capability_by_type, use it."""
        # Add a concept alias without a concept_resource_edge
        global_store.upsert_concept_alias("scheduler", "scheduler", domain="family")
        # Add capability type for this concept directly
        global_store.upsert_capability_type_index(
            capability_name="tool.read.family.scheduler.list",
            connector_id="family.scheduler",
            domain="family",
            resource_family="scheduler",
            operation_family="list",
            effect="read",
        )
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="list schedulers",
                    domain="family",
                    operation_hint="list",
                    resource_kind_hint="scheduler",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        # Should find scheduler as direct concept
        assert results[0].resource_family == "scheduler"

    def test_fallback_to_rk_hint(self, resolver, empty_universe):
        """If neither edge nor direct concept works, use rk_hint directly."""
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="operate on unknown_thing",
                    domain="family",
                    operation_hint="list",
                    resource_kind_hint="unknown_thing",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        # Falls back to rk_hint as resource_family
        assert results[0].resource_family == "unknown_thing"


# ══════════════════════════════════════════════════════════════════════
# TestTypedLookup
# ══════════════════════════════════════════════════════════════════════


class TestTypedLookup:
    """capability_type_index returns match, no match → empty fallback_capabilities."""

    def test_capability_type_index_match(self, resolver, empty_universe):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="Add event",
                    domain="family",
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert len(results[0].fallback_capabilities) >= 1
        cap_names = [c["capability_name"] for c in results[0].fallback_capabilities]
        assert "tool.execute.family.calendar.create" in cap_names

    def test_no_match_empty_fallback(self, resolver, empty_universe):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="zargonize widget",
                    domain="unknown",
                    operation_hint="create",
                    resource_kind_hint="widget",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert results[0].fallback_capabilities == []


# ══════════════════════════════════════════════════════════════════════
# TestConfidenceScoring
# ══════════════════════════════════════════════════════════════════════


class TestConfidenceScoring:
    """≥4 evidence → high, 2-3 → medium, 0-1 → low."""

    def test_high_confidence(self, resolver, empty_universe):
        """Create + calendar_event + family → high (4+ evidence edges)."""
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="Add dentist appointment to calendar",
                    domain="family",
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert results[0].confidence == "high"
        assert len(results[0].evidence) >= 4

    def test_medium_confidence(self, resolver, empty_universe):
        """Operation resolved + concept found but no resource_family edge → medium."""
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="list events",
                    domain="family",
                    operation_hint="list",
                    resource_kind_hint="calendar_event",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        # list + calendar_event in family domain → typed lookup finds match
        # Should have at least operation + concept → medium or high
        assert results[0].confidence in ("medium", "high")

    def test_low_confidence(self, resolver, empty_universe):
        """No concept resolution, no typed lookup → low."""
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="zargonize the frob",
                    domain="nowhere",
                    operation_hint="zargonize",
                    resource_kind_hint=None,
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert results[0].confidence == "low"
        assert len(results[0].evidence) <= 1


# ══════════════════════════════════════════════════════════════════════
# TestEndToEnd
# ══════════════════════════════════════════════════════════════════════


class TestEndToEnd:
    """Full resolution of a realistic intent through all 4 steps."""

    def test_create_calendar_event_resolves(self, resolver, empty_universe):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="Add dentist appointment for Riley next Monday at 3pm",
                    domain="family",
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert len(results) == 1
        assert results[0].resource_family == "calendar_event"
        assert results[0].operation_family == "create"
        assert results[0].effect == "write"
        assert results[0].confidence == "high"
        assert len(results[0].fallback_capabilities) >= 1
        assert any("create" in c["capability_name"] for c in results[0].fallback_capabilities)

    def test_multiple_intents(self, resolver, empty_universe):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="Add event",
                    domain="family",
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                ),
                RequestFrameIntent(
                    intent_id="i2",
                    action="List appointments",
                    domain="family",
                    operation_hint="list",
                    resource_kind_hint="calendar_event",
                ),
            ],
        )
        results = resolver.resolve(frame, empty_universe)
        assert len(results) == 2
        assert results[0].effect == "write"
        assert results[1].effect == "read"
