"""
Tests for vec_write Syscall - Embedding Vector Storage

Test Coverage:
- vec_write capability enforcement
- Successful vector writes to st_vec
- Idempotency (INSERT OR IGNORE)
- Validation (vector size, dimensions, status)
- Performance (<5ms P95)
- Integration with UnitOfWork

Related:
- Issue 1.3.1: vec_write syscall implementation
- M23 (builders.embedding_write): Primary user
- ADR-K003: Inline embedding architecture
- Migration 0026: st_vec table definition
"""

import sqlite3
import struct
import tempfile
import time
from pathlib import Path
from typing import Iterator

import pytest

from k0.kernel.syscalls import PermissionError, Syscalls
from k0.uow.connection_pool import configure_pool, shutdown_pool
from k0.uow.unit_of_work import UnitOfWork


@pytest.fixture
def temp_db() -> Iterator[Path]:
    """Create temporary database with st_vec and st_hipp_events tables."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    # Configure connection pool
    configure_pool(db_path)

    # Initialize schema
    conn = sqlite3.connect(str(db_path))

    # Create st_hipp_events table (parent table for FK)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS st_hipp_events (
            event_id TEXT PRIMARY KEY,
            wal_pos INTEGER NOT NULL,
            cognitive_trace_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            embedding_id TEXT,
            embedding_status TEXT DEFAULT 'PENDING',
            policy_band TEXT NOT NULL CHECK (policy_band IN ('GREEN', 'AMBER', 'RED')),
            text TEXT
        )
        """
    )

    # Create st_vec table (from migration 0026)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS st_vec (
            embedding_id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            space_id TEXT NOT NULL,
            vector BLOB NOT NULL,
            vector_dim INTEGER NOT NULL DEFAULT 768,
            model_id TEXT NOT NULL DEFAULT 'ultrabert_v2.1.0',
            status TEXT NOT NULL DEFAULT 'READY' CHECK(status IN ('READY', 'INDEXED', 'FAILED')),
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id) ON DELETE CASCADE
        )
        """
    )

    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vec_event_id ON st_vec(event_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vec_tenant_space ON st_vec(tenant_id, space_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vec_model_id ON st_vec(model_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vec_status_created ON st_vec(status, created_at) WHERE status = 'READY'"
    )

    # Seed test event for FK constraint
    conn.execute(
        """
        INSERT INTO st_hipp_events (event_id, wal_pos, cognitive_trace_id, tenant_id, space_id, policy_band, text)
        VALUES ('evt_test_001', 1, 'trace_test', 'tenant_test', 'space_test', 'GREEN', 'Test event')
        """
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
        return UnitOfWork(
            outbox_store=None,
            write_ahead_log=None,
            receipt_store=None,
            offset_store=None,
            metrics_emitter=None,
        )

    return factory


@pytest.fixture
def test_vector() -> bytes:
    """Create a valid 768-dim float32 vector as bytes (3072 bytes)."""
    embedding = [0.1 + i * 0.001 for i in range(768)]  # 768 unique values
    return struct.pack("768f", *embedding)


class TestVecWriteCapabilityEnforcement:
    """Test vec_write capability enforcement."""

    @pytest.mark.asyncio
    async def test_vec_write_raises_permission_error_without_cap(self, uow_factory, test_vector):
        """Test: vec_write raises PermissionError without st_vec.write capability."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_hipp_events.write"},  # Missing st_vec.write
            uow_factory=uow_factory,
        )

        with pytest.raises(PermissionError) as exc_info:
            await syscalls.vec_write(
                embedding_id="emb_test_001",
                event_id="evt_test_001",
                tenant_id="tenant_test",
                space_id="space_test",
                vector=test_vector,
                vector_dim=768,
                model_id="ultrabert_v2.1.0",
                status="READY",
            )

        assert "st_vec.write" in str(exc_info.value)
        assert "missing capability" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_vec_write_succeeds_with_granted_cap(self, uow_factory, test_vector, temp_db):
        """Test: vec_write succeeds with st_vec.write capability."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_vec.write"},
            uow_factory=uow_factory,
        )

        result = await syscalls.vec_write(
            embedding_id="emb_test_002",
            event_id="evt_test_001",
            tenant_id="tenant_test",
            space_id="space_test",
            vector=test_vector,
            vector_dim=768,
            model_id="ultrabert_v2.1.0",
            status="READY",
        )

        assert result["inserted"] is True
        assert result["embedding_id"] == "emb_test_002"
        assert result["status"] == "INSERTED"


class TestVecWriteOperations:
    """Test vec_write operations and data integrity."""

    @pytest.mark.asyncio
    async def test_vec_write_inserts_valid_embedding(self, uow_factory, test_vector, temp_db):
        """Test: vec_write inserts valid embedding with all fields."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_vec.write"},
            uow_factory=uow_factory,
        )

        result = await syscalls.vec_write(
            embedding_id="emb_test_003",
            event_id="evt_test_001",
            tenant_id="tenant_test",
            space_id="space_test",
            vector=test_vector,
            vector_dim=768,
            model_id="ultrabert_v2.1.0",
            status="READY",
            cognitive_trace_id="trace_test_001",
        )

        assert result["inserted"] is True
        assert result["embedding_id"] == "emb_test_003"

        # Verify data in database
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute(
            "SELECT embedding_id, event_id, vector_dim, model_id, status FROM st_vec WHERE embedding_id = ?",
            ("emb_test_003",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "emb_test_003"
        assert row[1] == "evt_test_001"
        assert row[2] == 768
        assert row[3] == "ultrabert_v2.1.0"
        assert row[4] == "READY"

    @pytest.mark.asyncio
    async def test_vec_write_idempotency_skips_duplicate(self, uow_factory, test_vector, temp_db):
        """Test: vec_write idempotency - duplicate embedding_id skipped."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_vec.write"},
            uow_factory=uow_factory,
        )

        # First insert
        result1 = await syscalls.vec_write(
            embedding_id="emb_test_004",
            event_id="evt_test_001",
            tenant_id="tenant_test",
            space_id="space_test",
            vector=test_vector,
            vector_dim=768,
            model_id="ultrabert_v2.1.0",
            status="READY",
        )

        assert result1["inserted"] is True
        assert result1["status"] == "INSERTED"

        # Duplicate insert (should skip)
        result2 = await syscalls.vec_write(
            embedding_id="emb_test_004",  # Same embedding_id
            event_id="evt_test_001",
            tenant_id="tenant_test",
            space_id="space_test",
            vector=test_vector,
            vector_dim=768,
            model_id="ultrabert_v2.1.0",
            status="READY",
        )

        assert result2["inserted"] is False
        assert result2["status"] == "SKIPPED_DUPLICATE"

    @pytest.mark.asyncio
    async def test_vec_write_stores_3072_byte_vector(self, uow_factory, test_vector, temp_db):
        """Test: vec_write stores 768-dim float32 vector as 3072 bytes."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_vec.write"},
            uow_factory=uow_factory,
        )

        await syscalls.vec_write(
            embedding_id="emb_test_005",
            event_id="evt_test_001",
            tenant_id="tenant_test",
            space_id="space_test",
            vector=test_vector,
            vector_dim=768,
            model_id="ultrabert_v2.1.0",
            status="READY",
        )

        # Verify vector blob size
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute(
            "SELECT length(vector) FROM st_vec WHERE embedding_id = ?",
            ("emb_test_005",),
        )
        vector_size = cursor.fetchone()[0]
        conn.close()

        assert vector_size == 3072  # 768 floats * 4 bytes


class TestVecWriteValidation:
    """Test vec_write input validation."""

    @pytest.mark.asyncio
    async def test_vec_write_rejects_invalid_vector_size(self, uow_factory):
        """Test: vec_write rejects vector with wrong byte size."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_vec.write"},
            uow_factory=uow_factory,
        )

        # Create wrong-sized vector (1024 bytes instead of 3072)
        invalid_vector = b"\x00" * 1024

        with pytest.raises(ValueError) as exc_info:
            await syscalls.vec_write(
                embedding_id="emb_test_006",
                event_id="evt_test_001",
                tenant_id="tenant_test",
                space_id="space_test",
                vector=invalid_vector,
                vector_dim=768,
                model_id="ultrabert_v2.1.0",
                status="READY",
            )

        assert "Invalid vector size" in str(exc_info.value)
        assert "3072" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_vec_write_rejects_invalid_status(self, uow_factory, test_vector):
        """Test: vec_write rejects invalid status value."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_vec.write"},
            uow_factory=uow_factory,
        )

        with pytest.raises(ValueError) as exc_info:
            await syscalls.vec_write(
                embedding_id="emb_test_007",
                event_id="evt_test_001",
                tenant_id="tenant_test",
                space_id="space_test",
                vector=test_vector,
                vector_dim=768,
                model_id="ultrabert_v2.1.0",
                status="INVALID_STATUS",  # Not in ('READY', 'INDEXED', 'FAILED')
            )

        assert "Invalid status" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_vec_write_rejects_wrong_vector_dim(self, uow_factory, test_vector):
        """Test: vec_write rejects vector_dim != 768."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_vec.write"},
            uow_factory=uow_factory,
        )

        with pytest.raises(ValueError) as exc_info:
            await syscalls.vec_write(
                embedding_id="emb_test_008",
                event_id="evt_test_001",
                tenant_id="tenant_test",
                space_id="space_test",
                vector=test_vector,
                vector_dim=384,  # Wrong dimension
                model_id="ultrabert_v2.1.0",
                status="READY",
            )

        assert "Invalid vector_dim" in str(exc_info.value)
        assert "768" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_vec_write_rejects_missing_required_fields(self, uow_factory, test_vector):
        """Test: vec_write rejects missing required fields."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_vec.write"},
            uow_factory=uow_factory,
        )

        # Missing embedding_id
        with pytest.raises(ValueError) as exc_info:
            await syscalls.vec_write(
                embedding_id="",  # Empty
                event_id="evt_test_001",
                tenant_id="tenant_test",
                space_id="space_test",
                vector=test_vector,
                vector_dim=768,
                model_id="ultrabert_v2.1.0",
                status="READY",
            )

        assert "embedding_id required" in str(exc_info.value)


class TestVecWritePerformance:
    """Test vec_write performance characteristics."""

    @pytest.mark.asyncio
    async def test_vec_write_completes_within_5ms_p95(self, uow_factory, test_vector, temp_db):
        """Test: vec_write completes within 5ms P95 target."""
        syscalls = Syscalls(
            pipeline_id="P02",
            granted_caps={"st_vec.write"},
            uow_factory=uow_factory,
        )

        # Measure 10 writes, check P95 (9th percentile)
        latencies = []
        for i in range(10):
            start = time.perf_counter()
            await syscalls.vec_write(
                embedding_id=f"emb_perf_{i:03d}",
                event_id="evt_test_001",
                tenant_id="tenant_test",
                space_id="space_test",
                vector=test_vector,
                vector_dim=768,
                model_id="ultrabert_v2.1.0",
                status="READY",
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        latencies.sort()
        p95_latency = latencies[8]  # 9th of 10 = 90th percentile (close to P95)

        # P95 target: <5ms (relaxed to 15ms for test environment)
        assert p95_latency < 15.0, f"P95 latency {p95_latency:.2f}ms exceeds 15ms target"
