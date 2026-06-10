"""GAP-P1-019 — Tests for ManifestAdmissionService (Epic 4.3).

Uses the real Epic 2 builder + domain catalog so admission is exercised
against production-shaped connector definitions.
"""

from __future__ import annotations

import dataclasses

import pytest

from k1.fabric.connectors.builder import build_connector_definition
from k1.fabric.connectors.definition import (
    CapabilityDefinition,
    ConnectorDefinition,
    InputFieldSpec,
)
from k1.fabric.connectors.domain_catalog import (
    DOMAIN_SERVICES,
    build_domain_corpus,
)
from k1.fabric.manifest_admission import (
    ManifestAdmissionRecord,
    ManifestAdmissionService,
)
from k1.fabric.stores.global_projection_store import GlobalProjectionStore

# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def store() -> GlobalProjectionStore:
    s = GlobalProjectionStore(db_path=":memory:")
    s.open()
    return s


@pytest.fixture
def service(store: GlobalProjectionStore) -> ManifestAdmissionService:
    return ManifestAdmissionService(store)


@pytest.fixture
def calendar_def() -> ConnectorDefinition:
    svc = DOMAIN_SERVICES["family"][0]  # calendar
    return build_connector_definition("family", svc)


# ══════════════════════════════════════════════════════════════════════
# TestValidAdmit
# ══════════════════════════════════════════════════════════════════════


class TestValidAdmit:
    def test_admit_returns_admitted(self, service, calendar_def):
        record = service.admit(calendar_def)
        assert isinstance(record, ManifestAdmissionRecord)
        assert record.admission_verdict == "admitted"
        assert record.connector_id == "family.calendar"
        assert record.capabilities_admitted_count >= 1
        assert record.reason is None

    def test_connector_written_to_store(self, service, store, calendar_def):
        service.admit(calendar_def)
        connector = store.get_connector("family.calendar")
        assert connector is not None
        assert connector.admission_verdict == "admitted"

    def test_capabilities_written(self, service, store, calendar_def):
        service.admit(calendar_def)
        caps = store.get_capabilities_by_connector("family.calendar")
        assert len(caps) == record_cap_count(calendar_def)

    def test_capability_type_index_seeded(self, service, store, calendar_def):
        """The typed resolver must be able to find admitted capabilities."""
        service.admit(calendar_def)
        rows = store.lookup_capability_by_type(
            domain="family",
            resource_family="calendar_event",
            operation_family="create",
            effect="write",
        )
        assert len(rows) >= 1
        assert any("create" in r["capability_name"] for r in rows)

    def test_capabilities_searchable_via_fts(self, service, store, calendar_def):
        service.admit(calendar_def)
        results = store.search_capabilities("calendar", top_k=10)
        assert len(results) >= 1


# ══════════════════════════════════════════════════════════════════════
# TestMissingFieldsReject
# ══════════════════════════════════════════════════════════════════════


class TestMissingFieldsReject:
    def test_missing_label_rejected(self, service, store, calendar_def):
        bad = dataclasses.replace(calendar_def, label="")
        record = service.admit(bad)
        assert record.admission_verdict == "rejected"
        assert "label" in (record.reason or "")
        # Connector NOT written
        assert store.get_connector("family.calendar") is None

    def test_empty_capabilities_rejected(self, service, store, calendar_def):
        bad = dataclasses.replace(calendar_def, capabilities=[])
        record = service.admit(bad)
        assert record.admission_verdict == "rejected"
        assert "capabilities" in (record.reason or "")

    def test_invalid_connector_type_rejected(self, service, calendar_def):
        bad = dataclasses.replace(calendar_def, connector_type="banana")
        record = service.admit(bad)
        assert record.admission_verdict == "rejected"
        assert "connector_type" in (record.reason or "")

    def test_bad_capability_naming_rejected(self, service):
        bad_cap = CapabilityDefinition(
            name="create",  # missing tool.{mode}. prefix
            action_name="create",
            invocation_mode="execute",
            effect="write",
            resource_kind="calendar_event",
            description="create",
        )
        definition = ConnectorDefinition(
            connector_id="family.bad",
            label="Bad",
            description="bad connector",
            provider_id="native.family.bad",
            resource_kinds=["calendar_event"],
            capabilities=[bad_cap],
        )
        record = service.admit(definition)
        assert record.admission_verdict == "rejected"
        assert "tool.execute." in (record.reason or "")

    def test_duplicate_capability_name_rejected(self, service):
        cap = CapabilityDefinition(
            name="tool.execute.family.dup.create",
            action_name="create",
            invocation_mode="execute",
            effect="write",
            resource_kind="thing",
            description="create thing",
        )
        definition = ConnectorDefinition(
            connector_id="family.dup",
            label="Dup",
            description="dup connector",
            provider_id="native.family.dup",
            resource_kinds=["thing"],
            capabilities=[cap, dataclasses.replace(cap)],
        )
        record = service.admit(definition)
        assert record.admission_verdict == "rejected"
        assert "duplicate" in (record.reason or "")


# ══════════════════════════════════════════════════════════════════════
# TestBatchAdmit
# ══════════════════════════════════════════════════════════════════════


class TestBatchAdmit:
    def test_admit_all_family_domain(self, service, store):
        corpus = build_domain_corpus("family")
        records = service.admit_all(corpus)
        assert len(records) == 10
        assert all(r.admission_verdict == "admitted" for r in records)
        # All 10 connectors present
        connectors = store.list_connectors()
        assert len(connectors) == 10

    def test_admit_all_seeds_searchable_catalog(self, service, store):
        corpus = build_domain_corpus("family")
        service.admit_all(corpus)
        assert store.count_capabilities() >= 40


# ══════════════════════════════════════════════════════════════════════
# TestPartialFailure
# ══════════════════════════════════════════════════════════════════════


class TestPartialFailure:
    def test_one_bad_does_not_block_rest(self, service, store, calendar_def):
        bad = dataclasses.replace(calendar_def, connector_id="family.bad", label="")
        good = build_connector_definition("family", DOMAIN_SERVICES["family"][1])  # tasks
        records = service.admit_all([bad, good])
        assert records[0].admission_verdict == "rejected"
        assert records[1].admission_verdict == "admitted"
        assert store.get_connector(good.connector_id) is not None


# ══════════════════════════════════════════════════════════════════════
# TestIdempotent
# ══════════════════════════════════════════════════════════════════════


class TestIdempotent:
    def test_admit_twice_no_error(self, service, store, calendar_def):
        r1 = service.admit(calendar_def)
        r2 = service.admit(calendar_def)
        assert r1.admission_verdict == "admitted"
        assert r2.admission_verdict == "admitted"
        # Still exactly the same capability count (no duplicates)
        caps = store.get_capabilities_by_connector("family.calendar")
        assert len(caps) == record_cap_count(calendar_def)


# ══════════════════════════════════════════════════════════════════════
# TestWithConstitution
# ══════════════════════════════════════════════════════════════════════


class TestWithConstitution:
    def test_constitution_written(self, service, store, calendar_def):
        service.admit(calendar_def)
        constitution = store.get_constitution("family.calendar")
        assert constitution is not None
        assert constitution.connector_id == "family.calendar"
        assert len(constitution.execution_phases) >= 1


# ══════════════════════════════════════════════════════════════════════
# TestWithOntology
# ══════════════════════════════════════════════════════════════════════


class TestWithOntology:
    def test_concept_aliases_seeded(self, service, store, calendar_def):
        service.admit(calendar_def)
        # The builder generates concept aliases from svc.id / label / resource kinds
        hits = store.resolve_concept("calendar event", domain="family")
        assert len(hits) >= 1

    def test_resource_connector_edge_seeded(self, service, store, calendar_def):
        service.admit(calendar_def)
        rows = store.get_concept_resource_family("calendar_event", domain="family")
        assert isinstance(rows, list)


# ══════════════════════════════════════════════════════════════════════
# TestReadOnlyConnector
# ══════════════════════════════════════════════════════════════════════


class TestReadOnlyConnector:
    def test_read_only_connector_admits(self, service, store):
        # analytics in enterprise domain is read-only (write_op=None)
        svc = DOMAIN_SERVICES["enterprise"][9]
        definition = build_connector_definition("enterprise", svc)
        record = service.admit(definition)
        assert record.admission_verdict == "admitted"
        caps = store.get_capabilities_by_connector(definition.connector_id)
        # Read-only → every capability is a read
        assert all(c.invocation_mode == "read" for c in caps)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def record_cap_count(definition: ConnectorDefinition) -> int:
    return len(definition.capabilities)
