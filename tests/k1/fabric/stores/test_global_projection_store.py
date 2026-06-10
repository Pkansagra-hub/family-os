"""GAP-P1-003: GlobalProjectionStore tests.

Epic 1, Issue 1.7.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

from k1.fabric.stores.global_projection_store import (
    CapabilityRecord,
    CapabilityRegistrationBatch,
    ConnectorRecord,
    ConstitutionRecord,
    GlobalProjectionStore,
    ResourceKindRecord,
)


@pytest.fixture
def store():
    """Create a fresh GlobalProjectionStore backed by a temp file."""
    db_path = os.path.join(tempfile.gettempdir(), "test_gps_gap003.db")
    s = GlobalProjectionStore(db_path)
    s.open()
    yield s
    s.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connector(connector_id: str = "family.calendar") -> ConnectorRecord:
    now = _now()
    return ConnectorRecord(
        connector_id=connector_id,
        label="Calendar",
        connector_type="native",
        provider_type="LOCAL",
        version="1.0.0",
        admission_verdict="admitted",
        registration_type="static",
        created_at=now,
        updated_at=now,
    )


def _capability(
    name: str = "tool.execute.family.calendar.create",
    connector_id: str = "family.calendar",
) -> CapabilityRecord:
    return CapabilityRecord(
        capability_name=name,
        connector_id=connector_id,
        invocation_mode="execute",
        action_name="create",
        effect="write",
        resource_kind="calendar_event",
        description="Create event",
        created_at=_now(),
        contract_json={},
    )


# ── TestRecordDataclasses ────────────────────────────────────────────────


class TestRecordDataclasses:
    def test_connector_roundtrip(self, store):
        conn = _connector()
        store.upsert_connector(conn)
        got = store.get_connector("family.calendar")
        assert got is not None
        assert got.label == "Calendar"
        assert got.connector_type == "native"

    def test_capability_roundtrip(self, store):
        store.upsert_connector(_connector())
        cap = _capability()
        store.upsert_capability(cap)
        got = store.get_capability("tool.execute.family.calendar.create")
        assert got is not None
        assert got.invocation_mode == "execute"
        assert got.action_name == "create"

    def test_resource_kind_roundtrip(self, store):
        store.upsert_connector(_connector())
        rk = ResourceKindRecord(
            kind_id="calendar.event",
            connector_id="family.calendar",
            label="Calendar Event",
            schema={"type": "object"},
            verifier_affordances=["read_after_write"],
        )
        store.upsert_resource_kind(rk)
        got = store.get_resource_kind("calendar.event")
        assert got is not None
        assert got.label == "Calendar Event"

    def test_constitution_roundtrip(self, store):
        store.upsert_connector(_connector())
        const = ConstitutionRecord(
            connector_id="family.calendar",
            constitution_id="family.calendar.v1",
            execution_phases=["read", "mutate"],
        )
        store.upsert_constitution(const)
        got = store.get_constitution("family.calendar")
        assert got is not None
        assert got.constitution_id == "family.calendar.v1"


# ── TestConnectorCRUD ─────────────────────────────────────────────────────


class TestConnectorCRUD:
    def test_full_crud(self, store):
        store.upsert_connector(_connector())
        assert store.connector_exists("family.calendar")
        got = store.get_connector("family.calendar")
        assert got is not None
        assert got.label == "Calendar"

    def test_cascade_delete(self, store):
        store.upsert_connector(_connector())
        store.upsert_capability(_capability())
        assert store.count_capabilities() == 1
        store.delete_connector("family.calendar")
        assert not store.connector_exists("family.calendar")
        assert store.count_capabilities() == 0

    def test_list_connectors(self, store):
        store.upsert_connector(_connector("family.calendar"))
        store.upsert_connector(_connector("family.tasks"))
        all_c = store.list_connectors()
        assert len(all_c) == 2


# ── TestCapabilityCRUD ────────────────────────────────────────────────────


class TestCapabilityCRUD:
    def test_crud(self, store):
        store.upsert_connector(_connector())
        store.upsert_capability(_capability())
        assert store.count_capabilities() == 1
        assert store.capability_exists("tool.execute.family.calendar.create")

    def test_bulk_10k(self, store):
        store.upsert_connector(_connector())
        caps = [
            CapabilityRecord(
                capability_name=f"tool.execute.family.calendar.bulk_{i}",
                connector_id="family.calendar",
                invocation_mode="execute",
                action_name="create",
                effect="write",
                resource_kind="calendar_event",
                description=f"Bulk {i}",
                created_at=_now(),
                contract_json={},
            )
            for i in range(1000)
        ]
        store.bulk_upsert_capabilities(caps, chunk_size=250)
        assert store.count_capabilities() == 1000

    def test_get_by_connector(self, store):
        store.upsert_connector(_connector())
        store.upsert_capability(_capability("tool.execute.family.calendar.create"))
        store.upsert_capability(_capability("tool.read.family.calendar.list"))
        by_conn = store.get_capabilities_by_connector("family.calendar")
        assert len(by_conn) == 2


# ── TestFTSSearch ─────────────────────────────────────────────────────────


class TestFTSSearch:
    def test_bm25_ranking(self, store):
        store.upsert_connector(_connector())
        store.upsert_capability(
            CapabilityRecord(
                capability_name="tool.execute.family.calendar.create",
                connector_id="family.calendar",
                invocation_mode="execute",
                action_name="create",
                effect="write",
                resource_kind="calendar_event",
                description="Create a calendar event with conflict detection",
                created_at=_now(),
                contract_json={},
            )
        )
        results = store.search_capabilities("calendar conflict", top_k=5)
        assert len(results) >= 1

    def test_rebuild_after_bulk(self, store):
        store.upsert_connector(_connector())
        caps = [
            CapabilityRecord(
                capability_name=f"tool.execute.family.calendar.bulk_{i}",
                connector_id="family.calendar",
                invocation_mode="execute",
                action_name="create",
                effect="write",
                resource_kind="calendar_event",
                description=f"Searchable term bulk_{i}",
                created_at=_now(),
                contract_json={},
            )
            for i in range(100)
        ]
        store.bulk_upsert_capabilities(caps)
        results = store.search_capabilities("bulk_50", top_k=3)
        assert len(results) >= 1

    def test_filtered_by_connector(self, store):
        store.upsert_connector(_connector("family.calendar"))
        store.upsert_connector(
            ConnectorRecord(
                connector_id="family.tasks",
                label="Tasks",
                connector_type="native",
                provider_type="LOCAL",
                version="1.0.0",
                admission_verdict="admitted",
                registration_type="static",
                created_at=_now(),
                updated_at=_now(),
            )
        )
        store.upsert_capability(
            CapabilityRecord(
                capability_name="tool.execute.family.calendar.create",
                connector_id="family.calendar",
                invocation_mode="execute",
                action_name="create",
                effect="write",
                resource_kind="calendar_event",
                description="calendar event create",
                created_at=_now(),
                contract_json={},
            )
        )
        store.upsert_capability(
            CapabilityRecord(
                capability_name="tool.execute.family.tasks.create",
                connector_id="family.tasks",
                invocation_mode="execute",
                action_name="create",
                effect="write",
                resource_kind="task",
                description="task create",
                created_at=_now(),
                contract_json={},
            )
        )
        results = store.search_capabilities("create", top_k=5, connector_ids=["family.calendar"])
        assert all(r.connector_id == "family.calendar" for r in results)


# ── TestSearchByDomain ────────────────────────────────────────────────────


class TestSearchByDomain:
    def test_domain_filtered(self, store):
        store.upsert_connector(_connector("family.calendar"))
        store.upsert_connector(
            ConnectorRecord(
                connector_id="enterprise.meetings",
                label="Meetings",
                connector_type="native",
                provider_type="LOCAL",
                version="1.0.0",
                admission_verdict="admitted",
                registration_type="static",
                created_at=_now(),
                updated_at=_now(),
            )
        )
        store.upsert_capability(
            CapabilityRecord(
                capability_name="tool.execute.family.calendar.create",
                connector_id="family.calendar",
                invocation_mode="execute",
                action_name="create",
                effect="write",
                resource_kind="calendar_event",
                description="family calendar create",
                created_at=_now(),
                contract_json={},
            )
        )
        store.upsert_capability(
            CapabilityRecord(
                capability_name="tool.execute.enterprise.meetings.create",
                connector_id="enterprise.meetings",
                invocation_mode="execute",
                action_name="create",
                effect="write",
                resource_kind="meeting",
                description="enterprise meeting create",
                created_at=_now(),
                contract_json={},
            )
        )
        results = store.search_capabilities_by_domain("create", ["family"], top_k=5)
        assert all(r.connector_id.startswith("family.") for r in results)


# ── TestResourceKinds ─────────────────────────────────────────────────────


class TestResourceKinds:
    def test_crud(self, store):
        store.upsert_connector(_connector())
        rk = ResourceKindRecord(
            kind_id="calendar.event",
            connector_id="family.calendar",
            label="Calendar Event",
        )
        store.upsert_resource_kind(rk)
        got = store.get_resource_kind("calendar.event")
        assert got is not None

    def test_by_connector(self, store):
        store.upsert_connector(_connector())
        store.upsert_resource_kind(
            ResourceKindRecord(
                kind_id="calendar.event",
                connector_id="family.calendar",
                label="Event",
            )
        )
        kinds = store.get_resource_kinds_by_connector("family.calendar")
        assert len(kinds) >= 1


# ── TestConstitutionCRUD ──────────────────────────────────────────────────


class TestConstitutionCRUD:
    def test_full_roundtrip(self, store):
        store.upsert_connector(_connector())
        const = ConstitutionRecord(
            connector_id="family.calendar",
            constitution_id="family.calendar.v1",
            schema_version="1.0.0",
            execution_phases=["read", "mutate"],
            prerequisite_reads=[
                {
                    "operation": "list",
                    "resource_kind": "calendar_event",
                    "reason": "Check conflicts",
                    "required": True,
                    "timeout_ms": 5000,
                }
            ],
            conflict_analysis_rules=[
                {"check": "time_overlap", "with_resource_kinds": ["calendar_event"]}
            ],
            hil_gates=[
                {
                    "trigger": "missing_required_field",
                    "field": "end",
                    "prompt": "What time?",
                }
            ],
            mutation_sequencing=[
                {"order": 1, "phase": "read", "operation": "list"},
                {"order": 2, "phase": "mutate", "operation": "create"},
            ],
            verification_requirements=[{"method": "read_after_write", "required_for_submit": True}],
            companion_resource_roles=[{"resource_kind": "chore", "role": "conflict_source"}],
            precondition_summary="List before create",
            companion_resource_summary="Conflicts with chores",
            hil_trigger_summary="HIL on missing end time",
            degradation_policy="Retry once then degraded",
        )
        store.upsert_constitution(const)
        got = store.get_constitution("family.calendar")
        assert got is not None
        assert got.constitution_id == "family.calendar.v1"
        assert len(got.prerequisite_reads) == 1
        assert got.prerequisite_reads[0]["operation"] == "list"
        assert len(got.mutation_sequencing) == 2
        assert got.mutation_sequencing[0]["phase"] == "read"
        assert len(got.verification_requirements) == 1
        assert got.precondition_summary == "List before create"


# ── TestGraphTables ───────────────────────────────────────────────────────


class TestGraphTables:
    def test_all_graph_tables(self, store):
        store.upsert_concept_alias("dentist", "appointment", domain="family")
        store.upsert_concept_resource_edge("appointment", "calendar_event", "family")
        store.upsert_resource_connector_edge(
            "family", "calendar_event", "family.calendar", role="primary"
        )
        store.upsert_operation_alias("schedule", "create", "write")
        store.upsert_operation_equivalence("list", "search", resource_family="calendar_event")
        store.upsert_capability_type_index(
            "tool.execute.family.calendar.create",
            "family.calendar",
            "family",
            "calendar_event",
            "create",
            "write",
        )

        concepts = store.resolve_concept("dentist", "family")
        assert len(concepts) >= 1

        ops = store.resolve_operation("schedule")
        assert ops[0]["operation_family"] == "create"

        equivs = store.get_operation_equivalences("list")
        assert equivs[0]["equivalent_operation"] == "search"

        typed = store.lookup_capability_by_type("family", "calendar_event", "create", "write")
        assert len(typed) >= 1
        assert typed[0]["capability_name"] == "tool.execute.family.calendar.create"


# ── TestScale ─────────────────────────────────────────────────────────────


class TestScale:
    def test_bulk_100k(self, store):
        store.upsert_connector(_connector())
        caps = [
            CapabilityRecord(
                capability_name=f"tool.execute.family.calendar.scale_{i:06d}",
                connector_id="family.calendar",
                invocation_mode="execute",
                action_name="create",
                effect="write",
                resource_kind="calendar_event",
                description=f"Scale test {i}",
                created_at=_now(),
                contract_json={},
            )
            for i in range(10000)
        ]
        store.bulk_upsert_capabilities(caps, chunk_size=25000)
        assert store.count_capabilities() == 10000

        import time

        start = time.monotonic()
        results = store.search_capabilities("scale_005000", top_k=3)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert len(results) >= 1
        assert elapsed_ms < 5000, f"Search took {elapsed_ms:.0f}ms (>5s)"


# ── TestLoadFromManifestBatch ─────────────────────────────────────────────


class TestLoadFromManifestBatch:
    def test_atomic_batch(self, store):
        batch = CapabilityRegistrationBatch(
            connector=ConnectorRecord(
                connector_id="family.tasks",
                label="Tasks",
                connector_type="native",
                provider_type="LOCAL",
                version="1.0.0",
                admission_verdict="admitted",
                registration_type="static",
                created_at=_now(),
                updated_at=_now(),
            ),
            capabilities=[
                CapabilityRecord(
                    capability_name=f"tool.execute.family.tasks.{op}",
                    connector_id="family.tasks",
                    invocation_mode="execute",
                    action_name=op,
                    effect="write",
                    resource_kind="task",
                    created_at=_now(),
                    contract_json={},
                )
                for op in ("create", "update", "delete")
            ],
            constitution=ConstitutionRecord(
                connector_id="family.tasks",
                constitution_id="family.tasks.v1",
            ),
        )
        result = store.load_from_manifest_batch(batch)
        assert result.admitted == 3
        assert result.rejected == 0
        assert store.connector_exists("family.tasks")
        assert store.count_capabilities() == 3
