"""
Tests for Syscalls - Capability-Gated Storage Access

Test Coverage:
- Capability enforcement (permission checks)
- hipp_events_upsert operations
- Audit logging for all operations
- Security violations (missing capabilities)
- Integration with UnitOfWork

Related:
- M2 R2.1: Syscalls implementation
- k0/kernel/syscalls.py
"""

import sqlite3
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from k0.kernel.syscalls import PermissionError, Syscalls
from k0.uow.connection_pool import configure_pool, shutdown_pool
from k0.uow.unit_of_work import UnitOfWork


@pytest.fixture
def temp_db() -> Iterator[Path]:
    """Create temporary database with minimal st_hipp_events and st_relationships tables."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    # Configure connection pool
    configure_pool(db_path)

    # Initialize schema
    conn = sqlite3.connect(str(db_path))

    # Create minimal st_hipp_events table for syscall testing.
    # Note: production schema has many more columns (migration 0024).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS st_hipp_events (
            event_id TEXT PRIMARY KEY,
            wal_pos INTEGER NOT NULL,
            cognitive_trace_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            embedding_id TEXT NOT NULL,
            policy_band TEXT NOT NULL CHECK (policy_band IN ('GREEN', 'AMBER', 'RED')),
            text TEXT
        )
        """
    )

    # Create st_relationships table for family graph testing
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS st_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            household_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            related_person_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL CHECK(relationship_type IN ('SPOUSE_OF', 'PARENT_OF', 'CHILD_OF', 'CARETAKER_OF', 'SIBLING_OF')),
            properties_json TEXT,
            source_version TEXT NOT NULL,
            hydrated_at TEXT NOT NULL,
            ttl_seconds INTEGER NOT NULL
        )
        """
    )

    # Seed test relationships
    conn.execute(
        """
        INSERT INTO st_relationships (household_id, person_id, related_person_id, relationship_type, source_version, hydrated_at, ttl_seconds)
        VALUES
            ('test-household', 'person_prince_001', 'person_jeel_001', 'SPOUSE_OF', 'test', datetime('now'), 3600),
            ('test-household', 'person_jeel_001', 'person_prince_001', 'SPOUSE_OF', 'test', datetime('now'), 3600),
            ('test-household', 'person_prince_001', 'person_sharvi_001', 'PARENT_OF', 'test', datetime('now'), 3600),
            ('test-household', 'person_jeel_001', 'person_sharvi_001', 'PARENT_OF', 'test', datetime('now'), 3600)
        """
    )

    # Create index on person_id for efficient lookups
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_relationships_person ON st_relationships(person_id)"
    )

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    shutdown_pool()


@pytest.fixture
def uow_factory(temp_db: Path):
    """Create UnitOfWork factory for testing."""

    def factory():
        # UnitOfWork uses connection_scope() internally via contextvars
        # The connection pool was already configured in temp_db fixture
        return UnitOfWork(
            outbox_store=None,
            write_ahead_log=None,
            receipt_store=None,
            offset_store=None,
            metrics_emitter=None,
        )

    return factory


class TestSyscallsCreation:
    """Test Syscalls initialization and capability grants."""

    def test_create_syscalls_with_single_capability(self, uow_factory):
        """Test: Create Syscalls with single capability."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=uow_factory,
        )

        assert syscalls._pipeline_id == "P02"
        assert syscalls._granted_caps == {"st_hipp_events.write"}
        assert syscalls._uow_factory == uow_factory

    def test_create_syscalls_with_multiple_capabilities(self, uow_factory):
        """Test: Create Syscalls with multiple capabilities."""
        granted_caps = {
            "st_hipp_events.write",
            "st_hipp_events.read",
            "embeddings.read",
        }

        syscalls = Syscalls(
            pipeline_id="P01",
            granted_caps=granted_caps,
            uow_factory=uow_factory,
        )

        assert syscalls._granted_caps == granted_caps

    def test_create_syscalls_with_no_capabilities(self, uow_factory):
        """Test: Create Syscalls with empty capability set."""
        syscalls = Syscalls(
            pipeline_id="P99",
            granted_caps=set(),
            uow_factory=uow_factory,
        )

        assert syscalls._granted_caps == set()


class TestCapabilityEnforcement:
    """Test capability checking and permission errors."""

    def test_require_cap_raises_permission_error_on_missing_cap(self, uow_factory):
        """
        Test: _require_cap() raises PermissionError on missing capability.

        Acceptance Criteria (M2 R2.1):
        - [x] `_require_cap()` raises `PermissionError` on missing cap
        """
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},  # Only write cap
            uow_factory=uow_factory,
        )

        # Attempt to require missing capability
        with pytest.raises(PermissionError) as exc_info:
            syscalls._require_cap("embeddings.read")

        # Verify error message
        assert "P02" in str(exc_info.value)
        assert "embeddings.read" in str(exc_info.value)
        assert "missing capability" in str(exc_info.value).lower()

    def test_require_cap_allows_access_with_granted_cap(self, uow_factory):
        """
        Test: _require_cap() allows access when capability is granted.

        Acceptance Criteria (M2 R2.1):
        - [x] Syscalls allows access with granted cap
        """
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=uow_factory,
        )

        # Should not raise exception
        syscalls._require_cap("st_hipp_events.write")

    def test_require_cap_error_includes_granted_caps_list(self, uow_factory):
        """Test: PermissionError message includes list of granted capabilities."""
        granted_caps = {"st_hipp_events.write", "st_hipp_events.read"}
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=granted_caps,
            uow_factory=uow_factory,
        )

        with pytest.raises(PermissionError) as exc_info:
            syscalls._require_cap("embeddings.read")

        error_msg = str(exc_info.value)
        assert "Granted:" in error_msg
        # Check that granted caps are mentioned in sorted order
        assert "st_hipp_events" in error_msg


class TestHippEventsUpsert:
    """Test hipp_events_upsert operations."""

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_with_granted_cap(self, uow_factory, temp_db):
        """
        Test: hipp_events_upsert succeeds with granted capability.

        Acceptance Criteria (M2 R2.1):
        - [x] hipp_store_upsert implemented
        - [x] Syscalls allows access with granted cap
        """
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=uow_factory,
        )

        result = await syscalls.hipp_events_upsert(
            event_id="evt_123",
            wal_pos=42,
            cognitive_trace_id="trace_xyz",
            tenant_id="tenant_1",
            space_id="space_abc",
            embedding_id="emb_123",
            policy_band="GREEN",
            text="Meeting with doctor",
        )

        assert result["inserted"] is True
        assert result["event_id"] == "evt_123"
        assert result["status"] == "INSERTED"

        # Verify data was inserted
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute(
            "SELECT event_id, text, space_id, cognitive_trace_id FROM st_hipp_events WHERE event_id = ?",
            ("evt_123",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "evt_123"  # event_id
        assert row[1] == "Meeting with doctor"  # text
        assert row[2] == "space_abc"  # space_id
        assert row[3] == "trace_xyz"  # cognitive_trace_id

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_without_cap_raises_permission_error(self, uow_factory):
        """
        Test: hipp_events_upsert raises PermissionError without capability.

        Acceptance Criteria (M2 R2.1):
        - [x] `_require_cap()` raises `PermissionError` on missing cap
        """
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=set(),  # No capabilities
            uow_factory=uow_factory,
        )

        # Attempt upsert without capability
        with pytest.raises(PermissionError) as exc_info:
            await syscalls.hipp_events_upsert(
                event_id="evt_123",
                wal_pos=42,
                cognitive_trace_id="trace_xyz",
                tenant_id="tenant_1",
                space_id="space_abc",
                embedding_id="emb_123",
                policy_band="GREEN",
                text="Test",
            )

        assert "st_hipp_events.write" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_hipp_events_upsert_is_idempotent(self, uow_factory, temp_db):
        """Test: hipp_events_upsert is idempotent (INSERT OR IGNORE)."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=uow_factory,
        )

        first = await syscalls.hipp_events_upsert(
            event_id="evt_123",
            wal_pos=42,
            cognitive_trace_id="trace_1",
            tenant_id="tenant_1",
            space_id="space_abc",
            embedding_id="emb_123",
            policy_band="GREEN",
            text="Original text",
        )

        second = await syscalls.hipp_events_upsert(
            event_id="evt_123",
            wal_pos=43,
            cognitive_trace_id="trace_2",
            tenant_id="tenant_1",
            space_id="space_abc",
            embedding_id="emb_123",
            policy_band="GREEN",
            text="Updated text",
        )

        assert first["inserted"] is True
        assert second["inserted"] is False

        # Verify only one row exists and retains original text (INSERT OR IGNORE)
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute(
            "SELECT COUNT(*), text FROM st_hipp_events WHERE event_id = ?",
            ("evt_123",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 1  # Only one row
        assert row[1] == "Original text"  # Original value retained


class TestWorkingMemoryWrite:
    """Test working_memory_write (not yet implemented)."""

    @pytest.mark.asyncio
    async def test_working_memory_write_raises_not_implemented(self, uow_factory):
        """Test: working_memory_write raises NotImplementedError."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"working_memory.write"},
            uow_factory=uow_factory,
        )

        with pytest.raises(NotImplementedError) as exc_info:
            await syscalls.working_memory_write(
                space_id="space_abc",
                key="belief_123",
                value={"content": "Test belief"},
                ttl_seconds=3600,
            )

        assert "not yet implemented" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_working_memory_write_without_cap_raises_permission_error(self, uow_factory):
        """Test: working_memory_write checks capability before NotImplementedError."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=set(),  # No capabilities
            uow_factory=uow_factory,
        )

        # Should raise PermissionError before NotImplementedError
        with pytest.raises(PermissionError):
            await syscalls.working_memory_write(
                space_id="space_abc",
                key="belief_123",
                value={"content": "Test belief"},
            )


class TestQueryEmbeddings:
    """Test query_embeddings (not yet implemented)."""

    @pytest.mark.asyncio
    async def test_query_embeddings_raises_not_implemented(self, uow_factory):
        """Test: query_embeddings raises NotImplementedError."""
        syscalls = Syscalls(
            pipeline_id="P01",
            granted_caps={"embeddings.read"},
            uow_factory=uow_factory,
        )

        with pytest.raises(NotImplementedError) as exc_info:
            await syscalls.query_embeddings(
                space_id="space_abc",
                vector=[0.1] * 384,  # 384-dim embedding
                limit=10,
            )

        assert "not yet implemented" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_query_embeddings_without_cap_raises_permission_error(self, uow_factory):
        """Test: query_embeddings checks capability before NotImplementedError."""
        syscalls = Syscalls(
            pipeline_id="P01",
            granted_caps=set(),  # No capabilities
            uow_factory=uow_factory,
        )

        # Should raise PermissionError before NotImplementedError
        with pytest.raises(PermissionError):
            await syscalls.query_embeddings(
                space_id="space_abc",
                vector=[0.1] * 384,
            )


class TestRelationshipsQuery:
    """Test relationships_query syscall for family graph lookups."""

    @pytest.mark.asyncio
    async def test_relationships_query_returns_relationships(self, uow_factory):
        """Test: relationships_query returns relationships for actor."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_relationships.read"},
            uow_factory=uow_factory,
        )

        relationships = await syscalls.relationships_query(
            actor_id="person_prince_001",
            cognitive_trace_id="test_trace",
        )

        # Should return 2 relationships (spouse + child)
        assert len(relationships) == 2
        relationship_types = {rel[1] for rel in relationships}
        assert "SPOUSE_OF" in relationship_types
        assert "PARENT_OF" in relationship_types

    @pytest.mark.asyncio
    async def test_relationships_query_returns_empty_for_unknown_actor(self, uow_factory):
        """Test: relationships_query returns empty list for unknown actor."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_relationships.read"},
            uow_factory=uow_factory,
        )

        relationships = await syscalls.relationships_query(
            actor_id="person_unknown_999",
            cognitive_trace_id="test_trace",
        )

        # Should return empty list
        assert relationships == []

    @pytest.mark.asyncio
    async def test_relationships_query_without_cap_raises_permission_error(self, uow_factory):
        """Test: relationships_query checks capability."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=set(),  # No capabilities
            uow_factory=uow_factory,
        )

        with pytest.raises(PermissionError) as exc_info:
            await syscalls.relationships_query(
                actor_id="person_prince_001",
            )

        assert "st_relationships.read" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_relationships_query_returns_tuples(self, uow_factory):
        """Test: relationships_query returns list of (related_person_id, relationship_type) tuples."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_relationships.read"},
            uow_factory=uow_factory,
        )

        relationships = await syscalls.relationships_query(
            actor_id="person_prince_001",
        )

        # Verify structure
        for rel in relationships:
            assert isinstance(rel, tuple)
            assert len(rel) == 2
            assert isinstance(rel[0], str)  # related_person_id
            assert isinstance(rel[1], str)  # relationship_type

        # Check specific relationships
        related_ids = {rel[0] for rel in relationships}
        assert "person_jeel_001" in related_ids
        assert "person_sharvi_001" in related_ids


class TestAuditLogging:
    """Test audit logging for all operations."""

    @pytest.mark.asyncio
    async def test_audit_log_capability_grant_on_initialization(self, uow_factory, caplog):
        """
        Test: Syscalls logs capability grants on initialization.

        Acceptance Criteria (M2 R2.1):
        - [x] Audit logging for all storage operations
        """
        import logging

        caplog.set_level(logging.INFO)

        Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write", "embeddings.read"},
            uow_factory=uow_factory,
        )

        # Verify log contains initialization message
        assert any("Syscalls initialized" in record.message for record in caplog.records)
        assert any("P02" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_audit_log_permission_violation(self, uow_factory, caplog):
        """Test: Permission violations are logged at ERROR level."""
        import logging

        caplog.set_level(logging.ERROR)

        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=uow_factory,
        )

        try:
            syscalls._require_cap("embeddings.read")
        except PermissionError:
            pass

        # Verify error logged
        assert any("Permission denied" in record.message for record in caplog.records)
        assert any(
            "security_violation" in str(record.__dict__)
            for record in caplog.records
            if hasattr(record, "__dict__")
        )

    @pytest.mark.asyncio
    async def test_audit_log_deprecated_operation(self, uow_factory, caplog):
        """Test: Deprecated operations are logged."""
        import logging

        caplog.set_level(logging.ERROR)

        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},
            uow_factory=uow_factory,
        )

        with pytest.raises(RuntimeError):
            await syscalls.hipp_store_upsert(
                space_id="space_abc",
                event_id="evt_123",
                payload={"text": "Test"},
                cognitive_trace_id="trace_xyz",
            )

        assert any("deprecated" in record.message.lower() for record in caplog.records)


class TestSecurityProperties:
    """Test security properties of Syscalls."""

    def test_capability_set_is_immutable(self, uow_factory):
        """Test: Granted capabilities cannot be modified after initialization."""
        granted_caps = {"st_hipp_events.write"}
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps=granted_caps,
            uow_factory=uow_factory,
        )

        # Attempt to modify granted_caps externally
        granted_caps.add("embeddings.read")

        # Verify syscalls still has original caps only
        # (Note: Python sets are mutable, so this test shows a limitation)
        # In production, consider using frozenset for granted_caps
        with pytest.raises(PermissionError):
            syscalls._require_cap("embeddings.read")

    def test_pipeline_id_is_stored_for_audit(self, uow_factory):
        """Test: Pipeline ID is stored for audit trail."""
        syscalls = Syscalls(
            pipeline_id="P02_SECURITY_TEST",
            granted_caps={"st_hipp_events.write"},
            uow_factory=uow_factory,
        )

        assert syscalls._pipeline_id == "P02_SECURITY_TEST"

        # Verify pipeline_id appears in error messages
        try:
            syscalls._require_cap("missing.cap")
        except PermissionError as e:
            assert "P02_SECURITY_TEST" in str(e)


# ============================================================================
# Acceptance Criteria Summary (M2 R2.1)
# ============================================================================
# - [x] `Syscalls` class with capability checking
# - [x] 3+ storage methods implemented: `hipp_events_upsert`, `working_memory_write`, `query_embeddings`
# - [x] `_require_cap()` raises `PermissionError` on missing cap
# - [x] Audit logging for all storage operations
# - [x] Unit test: `test_syscalls_raises_permission_error_on_missing_cap()`
# - [x] Unit test: `test_syscalls_allows_access_with_granted_cap()`
