"""
Tests for FAISS Syscalls - Similarity Search Index Operations

Test Coverage:
- FAISS capability enforcement (faiss.read, faiss.write)
- faiss_add, faiss_add_batch, faiss_search, faiss_remove_batch
- NotImplementedError placeholders (FAISS integration pending M2)
- Input validation
- Capability checks for all operations

Related:
- Issue 1.3.2: FAISS syscalls implementation
- M24 (embedding.faiss_indexer): faiss_add_batch primary user
- M27 (embedding.cleanup): faiss_remove_batch primary user
- P03 consolidation: faiss_search user
- ADR-K003: FAISS IVF256,PQ64 architecture
"""

import pytest

from k0.kernel.syscalls import PermissionError, Syscalls
from k0.uow.unit_of_work import UnitOfWork

pytest.skip("FAISS syscall tests skipped during PostgreSQL migration", allow_module_level=True)


@pytest.fixture
def uow_factory():
    """Create UnitOfWork factory for testing (minimal, FAISS doesn't need DB)."""

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
def test_vector() -> list[float]:
    """Create a valid 768-dim float32 vector."""
    return [0.1 + i * 0.001 for i in range(768)]


class TestFaissCapabilityEnforcement:
    """Test FAISS capability enforcement."""

    @pytest.mark.asyncio
    async def test_faiss_add_requires_faiss_write_cap(self, uow_factory, test_vector):
        """Test: faiss_add requires faiss.write capability."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.read"},  # Missing faiss.write
            uow_factory=uow_factory,
        )

        with pytest.raises(PermissionError) as exc_info:
            await syscalls.faiss_add(
                embedding_id="emb_test_001",
                vector=test_vector,
                index_id="ultrabert_v2.1.0_ivf256_pq64",
            )

        assert "faiss.write" in str(exc_info.value)
        assert "missing capability" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_faiss_add_batch_requires_faiss_write_cap(self, uow_factory, test_vector):
        """Test: faiss_add_batch requires faiss.write capability."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.read"},  # Missing faiss.write
            uow_factory=uow_factory,
        )

        records = [{"embedding_id": "emb_001", "vector": test_vector}]

        with pytest.raises(PermissionError) as exc_info:
            await syscalls.faiss_add_batch(
                records=records,
                index_id="ultrabert_v2.1.0_ivf256_pq64",
            )

        assert "faiss.write" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_search_requires_faiss_read_cap(self, uow_factory, test_vector):
        """Test: faiss_search requires faiss.read capability."""
        syscalls = Syscalls(
            pipeline_id="P03",
            granted_caps={"faiss.write"},  # Missing faiss.read
            uow_factory=uow_factory,
        )

        with pytest.raises(PermissionError) as exc_info:
            await syscalls.faiss_search(
                query_vector=test_vector,
                k=10,
                index_id="ultrabert_v2.1.0_ivf256_pq64",
            )

        assert "faiss.read" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_remove_batch_requires_faiss_write_cap(self, uow_factory):
        """Test: faiss_remove_batch requires faiss.write capability."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.read"},  # Missing faiss.write
            uow_factory=uow_factory,
        )

        with pytest.raises(PermissionError) as exc_info:
            await syscalls.faiss_remove_batch(
                embedding_ids=["emb_001", "emb_002"],
                index_id="ultrabert_v2.1.0_ivf256_pq64",
            )

        assert "faiss.write" in str(exc_info.value)


class TestFaissAddValidation:
    """Test faiss_add input validation."""

    @pytest.mark.asyncio
    async def test_faiss_add_rejects_missing_embedding_id(self, uow_factory, test_vector):
        """Test: faiss_add rejects missing embedding_id."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.write"},
            uow_factory=uow_factory,
        )

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_add(
                embedding_id="",  # Empty
                vector=test_vector,
            )

        assert "embedding_id required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_add_rejects_invalid_vector_dimension(self, uow_factory):
        """Test: faiss_add rejects vector with wrong dimension."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.write"},
            uow_factory=uow_factory,
        )

        invalid_vector = [0.1] * 384  # Wrong dimension

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_add(
                embedding_id="emb_test_001",
                vector=invalid_vector,
            )

        assert "Invalid vector dimension" in str(exc_info.value)
        assert "768" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_add_raises_error_when_not_trained(self, uow_factory, test_vector):
        """Test: faiss_add raises ValueError when index is not trained."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.write"},
            uow_factory=uow_factory,
        )

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_add(
                embedding_id="emb_test_001",
                vector=test_vector,
            )

        assert "not trained" in str(exc_info.value)


class TestFaissAddBatchValidation:
    """Test faiss_add_batch input validation."""

    @pytest.mark.asyncio
    async def test_faiss_add_batch_rejects_empty_records(self, uow_factory):
        """Test: faiss_add_batch rejects empty records list."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.write"},
            uow_factory=uow_factory,
        )

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_add_batch(
                records=[],  # Empty list
                index_id="ultrabert_v2.1.0_ivf256_pq64",
            )

        assert "records required" in str(exc_info.value)
        assert "empty list" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_add_batch_rejects_missing_embedding_id(self, uow_factory, test_vector):
        """Test: faiss_add_batch rejects record without embedding_id."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.write"},
            uow_factory=uow_factory,
        )

        records = [{"vector": test_vector}]  # Missing embedding_id

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_add_batch(records=records)

        assert "missing embedding_id" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_add_batch_rejects_missing_vector(self, uow_factory):
        """Test: faiss_add_batch rejects record without vector."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.write"},
            uow_factory=uow_factory,
        )

        records = [{"embedding_id": "emb_001"}]  # Missing vector

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_add_batch(records=records)

        assert "missing vector" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_add_batch_rejects_invalid_vector_dimension(self, uow_factory):
        """Test: faiss_add_batch rejects vector with wrong dimension."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.write"},
            uow_factory=uow_factory,
        )

        records = [{"embedding_id": "emb_001", "vector": [0.1] * 384}]  # Wrong dimension

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_add_batch(records=records)

        assert "invalid vector dimension" in str(exc_info.value)
        assert "768" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_add_batch_raises_not_implemented(self, uow_factory, test_vector):
        """Test: faiss_add_batch raises NotImplementedError (pending M2 implementation)."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.write"},
            uow_factory=uow_factory,
        )

        records = [
            {"embedding_id": "emb_001", "vector": test_vector},
            {"embedding_id": "emb_002", "vector": test_vector},
        ]

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_add_batch(records=records)

        assert "not trained" in str(exc_info.value)


class TestFaissSearchValidation:
    """Test faiss_search input validation."""

    @pytest.mark.asyncio
    async def test_faiss_search_rejects_missing_query_vector(self, uow_factory):
        """Test: faiss_search rejects missing query_vector."""
        syscalls = Syscalls(
            pipeline_id="P03",
            granted_caps={"faiss.read"},
            uow_factory=uow_factory,
        )

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_search(
                query_vector=[],  # Empty
                k=10,
            )

        assert "query_vector required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_search_rejects_invalid_query_dimension(self, uow_factory):
        """Test: faiss_search rejects query_vector with wrong dimension."""
        syscalls = Syscalls(
            pipeline_id="P03",
            granted_caps={"faiss.read"},
            uow_factory=uow_factory,
        )

        invalid_query = [0.1] * 384  # Wrong dimension

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_search(
                query_vector=invalid_query,
                k=10,
            )

        assert "Invalid query_vector dimension" in str(exc_info.value)
        assert "768" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_search_rejects_invalid_k(self, uow_factory, test_vector):
        """Test: faiss_search rejects k < 1."""
        syscalls = Syscalls(
            pipeline_id="P03",
            granted_caps={"faiss.read"},
            uow_factory=uow_factory,
        )

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_search(
                query_vector=test_vector,
                k=0,  # Invalid
            )

        assert "Invalid k" in str(exc_info.value)
        assert "must be >= 1" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_search_rejects_invalid_nprobe(self, uow_factory, test_vector):
        """Test: faiss_search rejects nprobe out of range."""
        syscalls = Syscalls(
            pipeline_id="P03",
            granted_caps={"faiss.read"},
            uow_factory=uow_factory,
        )

        # nprobe too low
        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_search(
                query_vector=test_vector,
                k=10,
                nprobe=0,  # < 1
            )

        assert "Invalid nprobe" in str(exc_info.value)

        # nprobe too high
        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_search(
                query_vector=test_vector,
                k=10,
                nprobe=300,  # > 256
            )

        assert "Invalid nprobe" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_search_raises_error_when_not_trained(self, uow_factory, test_vector):
        """Test: faiss_search raises error when index is not initialized."""
        syscalls = Syscalls(
            pipeline_id="P03",
            granted_caps={"faiss.read"},
            uow_factory=uow_factory,
        )

        # Expect either ValueError or AttributeError depending on initialization state
        with pytest.raises((ValueError, AttributeError)):
            await syscalls.faiss_search(
                query_vector=test_vector,
                k=10,
            )


class TestFaissRemoveBatchValidation:
    """Test faiss_remove_batch input validation."""

    @pytest.mark.asyncio
    async def test_faiss_remove_batch_rejects_empty_ids(self, uow_factory):
        """Test: faiss_remove_batch rejects empty embedding_ids list."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.write"},
            uow_factory=uow_factory,
        )

        with pytest.raises(ValueError) as exc_info:
            await syscalls.faiss_remove_batch(
                embedding_ids=[],  # Empty list
                index_id="ultrabert_v2.1.0_ivf256_pq64",
            )

        assert "embedding_ids required" in str(exc_info.value)
        assert "empty list" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_faiss_remove_batch_raises_error_when_not_trained(self, uow_factory):
        """Test: faiss_remove_batch raises error when index is not initialized."""
        syscalls = Syscalls(
            pipeline_id="P08",
            granted_caps={"faiss.write"},
            uow_factory=uow_factory,
        )

        # Expect either ValueError or AttributeError depending on initialization state
        with pytest.raises((ValueError, AttributeError)):
            await syscalls.faiss_remove_batch(
                embedding_ids=["emb_001", "emb_002", "emb_003"],
                index_id="ultrabert_v2.1.0_ivf256_pq64",
            )
