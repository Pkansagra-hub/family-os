"""
Test suite for P03 GDPR Erasure Service.

Tests the right-to-erasure implementation with three scopes:
ACTOR_DATA, ALL_MENTIONS, and FULL_PURGE.

Spec Reference: Dossier §6.21 GDPR Erasure
"""

from __future__ import annotations

import time

import pytest

from k0.pipelines.p03.erasure import (
    ERASURE_TABLE_ORDER,
    ErasureRequest,
    ErasureResult,
    ErasureScope,
    ErasureService,
    InMemoryErasureRepository,
    TombstoneMarker,
    create_erasure_request,
    create_erasure_service,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def repository() -> InMemoryErasureRepository:
    """Create a fresh in-memory repository."""
    return InMemoryErasureRepository()


@pytest.fixture
def service(repository: InMemoryErasureRepository) -> ErasureService:
    """Create an erasure service with the test repository."""
    return ErasureService(repository)


@pytest.fixture
def sample_request() -> ErasureRequest:
    """Create a sample erasure request."""
    return ErasureRequest(
        actor_id="user_123",
        tenant_id="tenant_1",
        space_id="space_1",
        scope=ErasureScope.ACTOR_DATA,
        requested_by="admin",
        reason="GDPR Article 17 request",
    )


# =============================================================================
# TEST CLASS: ErasureScope Enum
# =============================================================================


class TestErasureScope:
    """Tests for the ErasureScope enum."""

    def test_actor_data_scope(self):
        """Test ACTOR_DATA scope value."""
        assert ErasureScope.ACTOR_DATA.value == "ACTOR_DATA"

    def test_all_mentions_scope(self):
        """Test ALL_MENTIONS scope value."""
        assert ErasureScope.ALL_MENTIONS.value == "ALL_MENTIONS"

    def test_full_purge_scope(self):
        """Test FULL_PURGE scope value."""
        assert ErasureScope.FULL_PURGE.value == "FULL_PURGE"

    def test_scope_is_string_enum(self):
        """Test scope values are strings."""
        assert isinstance(ErasureScope.ACTOR_DATA.value, str)


# =============================================================================
# TEST CLASS: ErasureRequest Dataclass
# =============================================================================


class TestErasureRequest:
    """Tests for the ErasureRequest dataclass."""

    def test_request_creation(self):
        """Test creating a request with all fields."""
        request = ErasureRequest(
            actor_id="user_123",
            tenant_id="tenant_1",
            space_id="space_1",
            scope=ErasureScope.ACTOR_DATA,
            requested_by="admin",
            reason="GDPR request",
        )

        assert request.actor_id == "user_123"
        assert request.tenant_id == "tenant_1"
        assert request.scope == ErasureScope.ACTOR_DATA

    def test_request_has_auto_generated_id(self):
        """Test request gets auto-generated UUID."""
        request = ErasureRequest()
        assert request.request_id is not None
        assert len(request.request_id) == 36  # UUID format

    def test_request_has_timestamp(self):
        """Test request has current timestamp."""
        before = int(time.time() * 1000)
        request = ErasureRequest()
        after = int(time.time() * 1000)

        assert before <= request.requested_at <= after

    def test_request_to_dict(self, sample_request: ErasureRequest):
        """Test converting request to dictionary."""
        result = sample_request.to_dict()

        assert result["actor_id"] == "user_123"
        assert result["tenant_id"] == "tenant_1"
        assert result["scope"] == "ACTOR_DATA"
        assert result["requested_by"] == "admin"
        assert result["reason"] == "GDPR Article 17 request"

    def test_request_space_optional(self):
        """Test space_id is optional (None means all spaces)."""
        request = ErasureRequest(
            actor_id="user_123",
            tenant_id="tenant_1",
            scope=ErasureScope.FULL_PURGE,
            requested_by="admin",
            reason="Full purge",
        )

        assert request.space_id is None


# =============================================================================
# TEST CLASS: ErasureResult Dataclass
# =============================================================================


class TestErasureResult:
    """Tests for the ErasureResult dataclass."""

    def test_result_creation(self):
        """Test creating a result."""
        result = ErasureResult(request_id="req_123")

        assert result.request_id == "req_123"
        assert result.success is True
        assert result.records_erased == {}
        assert result.tombstones_created == 0

    def test_result_total_erased_property(self):
        """Test total_erased computed property."""
        result = ErasureResult(request_id="req_123")
        result.records_erased = {
            "st_epi": 10,
            "st_sem": 5,
            "st_kg_dom": 3,
        }

        assert result.total_erased == 18

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = ErasureResult(request_id="req_123")
        result.records_erased = {"st_epi": 10}
        result.tombstones_created = 2

        data = result.to_dict()

        assert data["request_id"] == "req_123"
        assert data["records_erased"]["st_epi"] == 10
        assert data["total_erased"] == 10
        assert data["tombstones_created"] == 2


# =============================================================================
# TEST CLASS: TombstoneMarker Dataclass
# =============================================================================


class TestTombstoneMarker:
    """Tests for the TombstoneMarker dataclass."""

    def test_tombstone_creation(self):
        """Test creating a tombstone marker."""
        tombstone = TombstoneMarker(
            event_id="evt_123",
            original_type="MEMORY_CREATED",
            erasure_request_id="req_456",
            erasure_scope="ACTOR_DATA",
        )

        assert tombstone.event_id == "evt_123"
        assert tombstone.original_type == "MEMORY_CREATED"

    def test_tombstone_has_timestamp(self):
        """Test tombstone has erased_at timestamp."""
        before = int(time.time() * 1000)
        tombstone = TombstoneMarker(
            event_id="evt_123",
            original_type="MEMORY_CREATED",
        )
        after = int(time.time() * 1000)

        assert before <= tombstone.erased_at <= after

    def test_tombstone_to_dict(self):
        """Test converting tombstone to dictionary."""
        tombstone = TombstoneMarker(
            event_id="evt_123",
            original_type="MEMORY_CREATED",
            erasure_request_id="req_456",
            erasure_scope="FULL_PURGE",
        )

        data = tombstone.to_dict()

        assert data["event_id"] == "evt_123"
        assert data["original_type"] == "MEMORY_CREATED"
        assert data["is_tombstone"] is True


# =============================================================================
# TEST CLASS: InMemoryErasureRepository
# =============================================================================


class TestInMemoryErasureRepository:
    """Tests for the in-memory erasure repository."""

    def test_repository_starts_empty(
        self,
        repository: InMemoryErasureRepository,
    ):
        """Test repository starts empty."""
        affected = repository.get_affected_event_ids(
            actor_id="user_123",
            tenant_id="tenant_1",
            space_id=None,
            scope=ErasureScope.ACTOR_DATA,
        )
        assert affected == []

    def test_add_and_erase_epi_record(
        self,
        repository: InMemoryErasureRepository,
    ):
        """Test adding and erasing from st_epi."""
        repository.add_epi_record(
            {
                "memory_id": "mem_001",
                "actor_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )

        erased = repository.erase_from_st_epi(
            actor_id="user_123",
            tenant_id="tenant_1",
            space_id="space_1",
            scope=ErasureScope.ACTOR_DATA,
        )

        assert erased == 1

    def test_erase_respects_tenant_isolation(
        self,
        repository: InMemoryErasureRepository,
    ):
        """Test erasure respects tenant boundaries."""
        repository.add_epi_record(
            {
                "memory_id": "mem_001",
                "actor_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )

        # Try to erase with different tenant
        erased = repository.erase_from_st_epi(
            actor_id="user_123",
            tenant_id="tenant_2",  # Different tenant
            space_id="space_1",
            scope=ErasureScope.ACTOR_DATA,
        )

        assert erased == 0

    def test_actor_data_scope_only_owned(
        self,
        repository: InMemoryErasureRepository,
    ):
        """Test ACTOR_DATA scope only erases owned records."""
        # Owned record
        repository.add_epi_record(
            {
                "memory_id": "mem_001",
                "actor_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )
        # Mentioned but not owned
        repository.add_epi_record(
            {
                "memory_id": "mem_002",
                "actor_id": "other_user",
                "subject_id": "user_123",  # Mentioned
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )

        erased = repository.erase_from_st_epi(
            actor_id="user_123",
            tenant_id="tenant_1",
            space_id="space_1",
            scope=ErasureScope.ACTOR_DATA,
        )

        # Only owned record should be erased
        assert erased == 1

    def test_all_mentions_scope_includes_mentions(
        self,
        repository: InMemoryErasureRepository,
    ):
        """Test ALL_MENTIONS scope erases owned and mentioned records."""
        # Owned record
        repository.add_epi_record(
            {
                "memory_id": "mem_001",
                "actor_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )
        # Mentioned as subject
        repository.add_epi_record(
            {
                "memory_id": "mem_002",
                "actor_id": "other_user",
                "subject_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )

        erased = repository.erase_from_st_epi(
            actor_id="user_123",
            tenant_id="tenant_1",
            space_id="space_1",
            scope=ErasureScope.ALL_MENTIONS,
        )

        assert erased == 2

    def test_full_purge_scope_includes_references(
        self,
        repository: InMemoryErasureRepository,
    ):
        """Test FULL_PURGE scope erases all related records."""
        # Add various related records
        repository.add_kg_edge_record(
            {
                "edge_id": "edge_001",
                "source_id": "user_123",
                "target_id": "entity_456",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )
        repository.add_kg_edge_record(
            {
                "edge_id": "edge_002",
                "source_id": "entity_789",
                "target_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )

        erased = repository.erase_from_st_kg_edges(
            actor_id="user_123",
            tenant_id="tenant_1",
            space_id="space_1",
            scope=ErasureScope.FULL_PURGE,
        )

        assert erased == 2

    def test_create_tombstone(
        self,
        repository: InMemoryErasureRepository,
    ):
        """Test creating tombstone for an event."""
        success = repository.create_tombstone_for_event(
            event_id="evt_123",
            original_type="MEMORY_CREATED",
            request_id="req_456",
            scope=ErasureScope.ACTOR_DATA,
        )

        assert success is True
        tombstones = repository.get_tombstones()
        assert len(tombstones) == 1
        assert tombstones[0].event_id == "evt_123"

    def test_get_affected_event_ids(
        self,
        repository: InMemoryErasureRepository,
    ):
        """Test getting affected event IDs."""
        repository.add_hipp_event(
            {
                "event_id": "evt_001",
                "actor_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )
        repository.add_hipp_event(
            {
                "event_id": "evt_002",
                "actor_id": "other_user",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )

        affected = repository.get_affected_event_ids(
            actor_id="user_123",
            tenant_id="tenant_1",
            space_id="space_1",
            scope=ErasureScope.ACTOR_DATA,
        )

        assert affected == ["evt_001"]

    def test_write_compliance_wal_entry(
        self,
        repository: InMemoryErasureRepository,
        sample_request: ErasureRequest,
    ):
        """Test writing compliance WAL entry."""
        result = ErasureResult(request_id=sample_request.request_id)

        entry_id = repository.write_compliance_wal_entry(sample_request, result)

        assert entry_id is not None
        entries = repository.get_wal_entries()
        assert len(entries) == 1
        assert entries[0]["type"] == "GDPR_ERASURE"


# =============================================================================
# TEST CLASS: ErasureService
# =============================================================================


class TestErasureService:
    """Tests for the ErasureService."""

    def test_execute_erasure_empty_repo(
        self,
        service: ErasureService,
        sample_request: ErasureRequest,
    ):
        """Test executing erasure on empty repository."""
        result = service.execute_erasure(sample_request)

        assert result.success is True
        assert result.total_erased == 0
        assert result.wal_entries_written == 1  # Compliance entry

    def test_execute_erasure_deletes_from_all_tables(
        self,
        repository: InMemoryErasureRepository,
        service: ErasureService,
        sample_request: ErasureRequest,
    ):
        """Test erasure cascades across all tables."""
        # Add records to multiple tables
        repository.add_epi_record(
            {
                "memory_id": "mem_001",
                "actor_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )
        repository.add_sem_record(
            {
                "memory_id": "sem_001",
                "actor_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )
        repository.add_kg_dom_record(
            {
                "entity_id": "ent_001",
                "actor_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )

        result = service.execute_erasure(sample_request)

        assert result.success is True
        assert result.records_erased.get("st_epi", 0) == 1
        assert result.records_erased.get("st_sem", 0) == 1
        assert result.records_erased.get("st_kg_dom", 0) == 1

    def test_execute_erasure_creates_tombstones(
        self,
        repository: InMemoryErasureRepository,
        service: ErasureService,
        sample_request: ErasureRequest,
    ):
        """Test erasure creates tombstones for events."""
        repository.add_hipp_event(
            {
                "event_id": "evt_001",
                "actor_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )

        result = service.execute_erasure(sample_request)

        assert result.tombstones_created == 1
        tombstones = repository.get_tombstones()
        assert len(tombstones) == 1

    def test_execute_erasure_writes_compliance_entry(
        self,
        repository: InMemoryErasureRepository,
        service: ErasureService,
        sample_request: ErasureRequest,
    ):
        """Test erasure writes compliance WAL entry."""
        result = service.execute_erasure(sample_request)

        assert result.wal_entries_written == 1
        assert result.compliance_record_id is not None
        entries = repository.get_wal_entries()
        assert len(entries) == 1

    def test_execute_erasure_all_spaces(
        self,
        repository: InMemoryErasureRepository,
        service: ErasureService,
    ):
        """Test erasure across all spaces when space_id is None."""
        # Add records in multiple spaces
        repository.add_epi_record(
            {
                "memory_id": "mem_001",
                "actor_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_1",
            }
        )
        repository.add_epi_record(
            {
                "memory_id": "mem_002",
                "actor_id": "user_123",
                "tenant_id": "tenant_1",
                "space_id": "space_2",
            }
        )

        request = ErasureRequest(
            actor_id="user_123",
            tenant_id="tenant_1",
            space_id=None,  # All spaces
            scope=ErasureScope.ACTOR_DATA,
            requested_by="admin",
            reason="GDPR request",
        )

        result = service.execute_erasure(request)

        assert result.records_erased.get("st_epi", 0) == 2

    def test_validate_request_valid(
        self,
        service: ErasureService,
        sample_request: ErasureRequest,
    ):
        """Test validation passes for valid request."""
        errors = service.validate_request(sample_request)
        assert errors == []

    def test_validate_request_missing_actor(
        self,
        service: ErasureService,
    ):
        """Test validation catches missing actor_id."""
        request = ErasureRequest(
            actor_id="",  # Missing
            tenant_id="tenant_1",
            scope=ErasureScope.ACTOR_DATA,
            requested_by="admin",
            reason="GDPR request",
        )

        errors = service.validate_request(request)

        assert "actor_id is required" in errors

    def test_validate_request_missing_reason(
        self,
        service: ErasureService,
    ):
        """Test validation catches missing reason."""
        request = ErasureRequest(
            actor_id="user_123",
            tenant_id="tenant_1",
            scope=ErasureScope.ACTOR_DATA,
            requested_by="admin",
            reason="",  # Missing
        )

        errors = service.validate_request(request)

        assert "reason is required for compliance" in errors

    def test_get_affected_tables(
        self,
        service: ErasureService,
    ):
        """Test getting affected tables for each scope."""
        # All scopes affect all tables
        tables = service.get_affected_tables(ErasureScope.ACTOR_DATA)
        assert tables == set(ERASURE_TABLE_ORDER)


# =============================================================================
# TEST CLASS: Factory Functions
# =============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_erasure_service(
        self,
        repository: InMemoryErasureRepository,
    ):
        """Test creating service via factory."""
        service = create_erasure_service(repository)
        assert isinstance(service, ErasureService)

    def test_create_erasure_request(self):
        """Test creating request via factory."""
        request = create_erasure_request(
            actor_id="user_123",
            tenant_id="tenant_1",
            scope=ErasureScope.ALL_MENTIONS,
            requested_by="admin",
            reason="Right to be forgotten",
            space_id="space_1",
        )

        assert request.actor_id == "user_123"
        assert request.scope == ErasureScope.ALL_MENTIONS
        assert request.space_id == "space_1"


# =============================================================================
# TEST CLASS: Constants
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_erasure_table_order(self):
        """Test table order includes expected tables."""
        expected = {
            "st_kg_edges",
            "st_kg_dom",
            "st_epi",
            "st_sem",
            "st_consolidation_audit",
        }
        assert set(ERASURE_TABLE_ORDER) == expected

    def test_erasure_table_order_foreign_keys_first(self):
        """Test edges are before entities (respects FK order)."""
        edges_idx = ERASURE_TABLE_ORDER.index("st_kg_edges")
        dom_idx = ERASURE_TABLE_ORDER.index("st_kg_dom")
        assert edges_idx < dom_idx
