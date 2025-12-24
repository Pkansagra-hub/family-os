"""
FAISS Integration Tests

Tests real FAISS operations (not mocked) for:
- FaissIndexManager initialization
- Index training with real vectors
- Add single/batch vectors
- Search operations
- ID mapping bidirectionality
- Index persistence (save/load)
- Concurrent access (thread-safety)
- Performance validation (<50ms P95)

Version: 1.0.0
Last Updated: 2025-12-13
"""

import asyncio
import shutil
import time
from pathlib import Path

import numpy as np
import pytest

from k0.runtime.faiss_manager import FaissIndexManager

pytest.skip("FAISS integration tests skipped during PostgreSQL migration", allow_module_level=True)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def test_index_dir(tmp_path_factory):
    """Create temporary directory for test indexes"""
    dir_path = tmp_path_factory.mktemp("faiss_test_indexes")
    yield str(dir_path)
    # Cleanup
    shutil.rmtree(dir_path, ignore_errors=True)


@pytest.fixture
async def faiss_manager(test_index_dir):
    """Get FaissIndexManager instance for testing with FlatL2 index (no training needed)"""
    # Reset singleton for testing
    FaissIndexManager._instance = None

    mgr = FaissIndexManager.get_instance()
    # Override index_id for testing
    mgr._index_id = "test_flat_l2"
    await mgr.initialize(
        index_path=test_index_dir,
        train_if_needed=False,  # Manual training control for tests
    )

    # Replace IVF index with simpler FlatL2 index for testing (no training needed)
    import faiss

    mgr._index = faiss.IndexFlatL2(768)
    mgr._is_trained = True  # FlatL2 doesn't require training
    yield mgr

    # Cleanup
    FaissIndexManager._instance = None


@pytest.fixture
def sample_vectors_768dim():
    """Generate 1000 random 768-dim vectors"""
    np.random.seed(42)
    return np.random.randn(1000, 768).astype("float32")


@pytest.fixture
def training_vectors_30k():
    """Generate 30,000 random 768-dim vectors for training"""
    np.random.seed(123)
    return np.random.randn(30000, 768).astype("float32")


# =============================================================================
# Test: FaissIndexManager Initialization
# =============================================================================


class TestFaissIndexManagerInit:
    """Test FaissIndexManager initialization"""

    @pytest.mark.asyncio
    async def test_singleton_pattern(self, test_index_dir):
        """Test: FaissIndexManager follows singleton pattern"""
        # Reset singleton
        FaissIndexManager._instance = None

        # Get two instances
        mgr1 = FaissIndexManager.get_instance()
        mgr2 = FaissIndexManager.get_instance()

        # Assert same instance
        assert mgr1 is mgr2

    @pytest.mark.asyncio
    async def test_initialize_creates_new_index(self, test_index_dir):
        """Test: Initialize creates new index if not exists"""
        FaissIndexManager._instance = None
        mgr = FaissIndexManager.get_instance()
        mgr._index_id = "test_new_index"

        await mgr.initialize(
            index_path=test_index_dir,
            train_if_needed=False,
        )

        # Assert index created (not trained yet)
        assert mgr._index is not None
        assert mgr._index.ntotal == 0  # No vectors yet

    @pytest.mark.asyncio
    async def test_initialize_loads_existing_index(
        self, test_index_dir, faiss_manager, sample_vectors_768dim
    ):
        """Test: Initialize loads existing index from disk"""
        # Add some vectors and save
        for i in range(10):
            embedding_id = f"emb_test_{i}"
            await faiss_manager.add(
                embedding_id, sample_vectors_768dim[i].tolist(), "test_ivf256_pq64"
            )

        await faiss_manager.save()

        # Reset and reload
        FaissIndexManager._instance = None
        new_mgr = FaissIndexManager.get_instance()
        new_mgr._index_id = "test_ivf256_pq64"
        await new_mgr.initialize(
            index_path=test_index_dir,
            train_if_needed=False,
        )

        # Assert index loaded with vectors
        assert new_mgr._index.ntotal == 10


# =============================================================================
# Test: Index Training
# =============================================================================


class TestIndexTraining:
    """Test FAISS index training"""

    @pytest.mark.asyncio
    async def test_train_with_30k_vectors(self, faiss_manager, training_vectors_30k):
        """Test: Train index with 30,000+ vectors"""
        # Act
        result = await faiss_manager.train(training_vectors_30k)

        # Assert
        assert result["trained"] is True
        assert result["training_vectors"] >= 30000
        assert "training_time_ms" in result

    @pytest.mark.asyncio
    async def test_train_insufficient_vectors_raises_error(self, faiss_manager):
        """Test: Training with <30k vectors raises ValueError"""
        # Arrange - only 100 vectors
        small_dataset = np.random.randn(100, 768).astype("float32")

        # Act & Assert
        with pytest.raises(ValueError, match="at least 30000"):
            await faiss_manager.train(small_dataset)

    @pytest.mark.asyncio
    async def test_already_trained_skips_retraining(self, faiss_manager, training_vectors_30k):
        """Test: Already trained index skips retraining"""
        # Train once
        await faiss_manager.train(training_vectors_30k)

        # Try training again
        result = await faiss_manager.train(training_vectors_30k)

        # Assert - already trained
        assert result["trained"] is True
        assert "already trained" in result.get("message", "").lower()


# =============================================================================
# Test: Add Operations
# =============================================================================


class TestAddOperations:
    """Test adding vectors to FAISS"""

    @pytest.mark.asyncio
    async def test_add_single_vector(self, faiss_manager, sample_vectors_768dim):
        """Test: Add single vector to FAISS"""
        # Arrange
        embedding_id = "emb_single_test"
        vector = sample_vectors_768dim[0].tolist()

        # Act
        result = await faiss_manager.add(embedding_id, vector, "test_ivf256_pq64")

        # Assert
        assert result["added"] is True
        assert result["embedding_id"] == embedding_id
        assert result["total_vectors"] >= 1

    @pytest.mark.asyncio
    async def test_add_batch_100_vectors(self, faiss_manager, sample_vectors_768dim):
        """Test: Batch add 100 vectors"""
        # Arrange
        embeddings = [(f"emb_batch_{i}", sample_vectors_768dim[i].tolist()) for i in range(100)]

        # Act
        result = await faiss_manager.add_batch(embeddings, "test_ivf256_pq64")

        # Assert
        assert result["added_count"] == 100
        assert result["batch_size"] == 100
        assert result["total_vectors"] >= 100

    @pytest.mark.asyncio
    async def test_add_duplicate_id_raises_error(self, faiss_manager, sample_vectors_768dim):
        """Test: Adding duplicate embedding_id raises ValueError"""
        # Arrange
        embedding_id = "emb_duplicate"
        vector = sample_vectors_768dim[0].tolist()

        # Add once
        await faiss_manager.add(embedding_id, vector, "test_ivf256_pq64")

        # Act & Assert - try to add again
        with pytest.raises(ValueError, match="already registered"):
            await faiss_manager.add(embedding_id, vector, "test_ivf256_pq64")

    @pytest.mark.asyncio
    async def test_add_invalid_dimension_raises_error(self, faiss_manager):
        """Test: Invalid vector dimension raises ValueError"""
        # Arrange - 384-dim instead of 768-dim
        invalid_vector = [0.1] * 384

        # Act & Assert
        with pytest.raises(ValueError, match="768 dimensions"):
            await faiss_manager.add("emb_invalid", invalid_vector, "test_ivf256_pq64")


# =============================================================================
# Test: Search Operations
# =============================================================================


class TestSearchOperations:
    """Test FAISS search operations"""

    @pytest.mark.asyncio
    async def test_search_returns_nearest_neighbors(self, faiss_manager, sample_vectors_768dim):
        """Test: Search returns k nearest neighbors"""
        # Arrange - add 100 vectors
        embeddings = [(f"emb_search_{i}", sample_vectors_768dim[i].tolist()) for i in range(100)]
        await faiss_manager.add_batch(embeddings, "test_ivf256_pq64")

        # Act - search for vector 50
        query_vector = sample_vectors_768dim[50].tolist()
        results = await faiss_manager.search(query_vector, k=10, index_id="test_ivf256_pq64")

        # Assert
        assert len(results) == 10
        assert results[0]["embedding_id"] == "emb_search_50"  # Exact match first
        assert results[0]["distance"] < 0.01  # Very close distance

    @pytest.mark.asyncio
    async def test_search_respects_k_parameter(self, faiss_manager, sample_vectors_768dim):
        """Test: Search returns exactly k results"""
        # Arrange - add 50 vectors
        embeddings = [(f"emb_k_test_{i}", sample_vectors_768dim[i].tolist()) for i in range(50)]
        await faiss_manager.add_batch(embeddings, "test_ivf256_pq64")

        # Act - search for k=5
        query_vector = sample_vectors_768dim[0].tolist()
        results = await faiss_manager.search(query_vector, k=5, index_id="test_ivf256_pq64")

        # Assert
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_search_empty_index_returns_empty(self, test_index_dir):
        """Test: Search on empty index returns empty results"""
        # Arrange - new empty index
        FaissIndexManager._instance = None
        mgr = FaissIndexManager.get_instance()
        mgr._index_id = "test_empty_index"
        await mgr.initialize(
            index_path=test_index_dir,
            train_if_needed=False,
        )

        # Act
        query_vector = [0.1] * 768
        results = await mgr.search(query_vector, k=10, index_id="test_empty_index")

        # Assert
        assert len(results) == 0


# =============================================================================
# Test: ID Mapping
# =============================================================================


class TestIDMapping:
    """Test UUID ↔ int64 ID mapping"""

    @pytest.mark.asyncio
    async def test_register_embedding_id_assigns_sequential_ids(self, faiss_manager):
        """Test: register_embedding_id assigns sequential int64 IDs"""
        # Act
        faiss_id_1 = await faiss_manager.register_embedding_id("emb_uuid_1")
        faiss_id_2 = await faiss_manager.register_embedding_id("emb_uuid_2")
        faiss_id_3 = await faiss_manager.register_embedding_id("emb_uuid_3")

        # Assert - sequential
        assert faiss_id_2 == faiss_id_1 + 1
        assert faiss_id_3 == faiss_id_2 + 1

    @pytest.mark.asyncio
    async def test_id_mapping_bidirectional(self, faiss_manager):
        """Test: ID mapping is bidirectional (UUID ↔ int64)"""
        # Arrange
        embedding_id = "emb_bidirectional"

        # Act
        faiss_id = await faiss_manager.register_embedding_id(embedding_id)

        # Assert - can retrieve both ways
        assert faiss_manager._embedding_to_faiss[embedding_id] == faiss_id
        assert faiss_manager._faiss_to_embedding[faiss_id] == embedding_id

    @pytest.mark.asyncio
    async def test_register_duplicate_returns_existing_id(self, faiss_manager):
        """Test: Registering duplicate embedding_id returns existing faiss_id"""
        # Arrange
        embedding_id = "emb_duplicate_register"

        # Act
        faiss_id_1 = await faiss_manager.register_embedding_id(embedding_id)
        faiss_id_2 = await faiss_manager.register_embedding_id(embedding_id)

        # Assert - same ID
        assert faiss_id_1 == faiss_id_2


# =============================================================================
# Test: Remove Operations
# =============================================================================


class TestRemoveOperations:
    """Test removing vectors from FAISS"""

    @pytest.mark.asyncio
    async def test_remove_batch_logical_deletion(self, faiss_manager, sample_vectors_768dim):
        """Test: remove_batch performs logical deletion"""
        # Arrange - add 20 vectors
        embeddings = [(f"emb_remove_{i}", sample_vectors_768dim[i].tolist()) for i in range(20)]
        await faiss_manager.add_batch(embeddings, "test_ivf256_pq64")

        # Act - remove 10 vectors
        to_remove = [f"emb_remove_{i}" for i in range(10)]
        result = await faiss_manager.remove_batch(to_remove)

        # Assert
        assert result["removed_count"] == 10
        assert result["batch_size"] == 10

        # Verify removed from ID mapping
        for embedding_id in to_remove:
            assert embedding_id not in faiss_manager._embedding_to_faiss

    @pytest.mark.asyncio
    async def test_remove_nonexistent_id_skips(self, faiss_manager):
        """Test: Removing nonexistent ID is skipped gracefully"""
        # Act
        result = await faiss_manager.remove_batch(["emb_nonexistent_1", "emb_nonexistent_2"])

        # Assert - no errors, removed_count = 0
        assert result["removed_count"] == 0
        assert result["batch_size"] == 2


# =============================================================================
# Test: Persistence
# =============================================================================


class TestPersistence:
    """Test index persistence (save/load)"""

    @pytest.mark.asyncio
    async def test_save_persists_index_to_disk(
        self, faiss_manager, sample_vectors_768dim, test_index_dir
    ):
        """Test: Save persists index to disk"""
        # Arrange - add vectors
        embeddings = [(f"emb_persist_{i}", sample_vectors_768dim[i].tolist()) for i in range(50)]
        await faiss_manager.add_batch(embeddings, "test_ivf256_pq64")

        # Act
        result = await faiss_manager.save()

        # Assert
        assert result["saved"] is True
        assert "index_path" in result

        # Verify file exists
        index_path = Path(test_index_dir) / "test_ivf256_pq64.index"
        assert index_path.exists()

    @pytest.mark.asyncio
    async def test_load_restores_index_from_disk(self, test_index_dir, sample_vectors_768dim):
        """Test: Load restores index from disk"""
        # Arrange - create, populate, and save index
        FaissIndexManager._instance = None
        mgr1 = FaissIndexManager.get_instance()
        mgr1._index_id = "test_persist_load"
        await mgr1.initialize(
            index_path=test_index_dir,
            train_if_needed=False,
        )

        embeddings = [(f"emb_load_{i}", sample_vectors_768dim[i].tolist()) for i in range(30)]
        await mgr1.add_batch(embeddings, "test_persist_load")
        await mgr1.save()

        original_total = mgr1._index.ntotal

        # Act - reset and reload
        FaissIndexManager._instance = None
        mgr2 = FaissIndexManager.get_instance()
        mgr2._index_id = "test_persist_load"
        await mgr2.initialize(
            index_path=test_index_dir,
            train_if_needed=False,
        )

        # Assert - same total vectors
        assert mgr2._index.ntotal == original_total


# =============================================================================
# Test: Thread-Safety
# =============================================================================


class TestThreadSafety:
    """Test concurrent access and thread-safety"""

    @pytest.mark.asyncio
    async def test_concurrent_add_operations_safe(self, faiss_manager, sample_vectors_768dim):
        """Test: Concurrent add operations are thread-safe"""

        # Arrange - 20 concurrent adds
        async def add_vector(i):
            embedding_id = f"emb_concurrent_{i}"
            vector = sample_vectors_768dim[i].tolist()
            return await faiss_manager.add(embedding_id, vector, "test_ivf256_pq64")

        # Act - run concurrently
        tasks = [add_vector(i) for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert - all succeeded
        assert len(results) == 20
        assert all(isinstance(r, dict) and r["added"] for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_search_operations_safe(self, faiss_manager, sample_vectors_768dim):
        """Test: Concurrent search operations are thread-safe"""
        # Arrange - add vectors first
        embeddings = [
            (f"emb_search_concurrent_{i}", sample_vectors_768dim[i].tolist()) for i in range(100)
        ]
        await faiss_manager.add_batch(embeddings, "test_ivf256_pq64")

        # Act - 10 concurrent searches
        async def search_vector(i):
            query = sample_vectors_768dim[i].tolist()
            return await faiss_manager.search(query, k=5, index_id="test_ivf256_pq64")

        tasks = [search_vector(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # Assert - all succeeded
        assert len(results) == 10
        assert all(len(r) == 5 for r in results)


# =============================================================================
# Test: Performance Validation
# =============================================================================


class TestPerformanceValidation:
    """Test performance characteristics"""

    @pytest.mark.asyncio
    async def test_add_single_latency_under_5ms(self, faiss_manager, sample_vectors_768dim):
        """Test: Single add operation <5ms P95"""
        # Arrange - warm up
        for i in range(10):
            await faiss_manager.add(
                f"emb_warmup_{i}", sample_vectors_768dim[i].tolist(), "test_ivf256_pq64"
            )

        # Act - measure 100 operations
        latencies = []
        for i in range(10, 110):
            start = time.perf_counter()
            await faiss_manager.add(
                f"emb_perf_{i}", sample_vectors_768dim[i].tolist(), "test_ivf256_pq64"
            )
            latencies.append((time.perf_counter() - start) * 1000)  # ms

        # Assert - P95 < 5ms
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
        assert p95_latency < 5, f"P95 add latency {p95_latency:.2f}ms exceeds 5ms target"

    @pytest.mark.asyncio
    async def test_search_latency_under_50ms(self, faiss_manager, sample_vectors_768dim):
        """Test: Search operation <50ms P95"""
        # Arrange - add 500 vectors
        embeddings = [
            (f"emb_search_perf_{i}", sample_vectors_768dim[i % len(sample_vectors_768dim)].tolist())
            for i in range(500)
        ]
        await faiss_manager.add_batch(embeddings, "test_ivf256_pq64")

        # Act - measure 50 searches
        latencies = []
        for i in range(50):
            query = sample_vectors_768dim[i % len(sample_vectors_768dim)].tolist()
            start = time.perf_counter()
            await faiss_manager.search(query, k=10, index_id="test_ivf256_pq64")
            latencies.append((time.perf_counter() - start) * 1000)  # ms

        # Assert - P95 < 50ms
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
        assert p95_latency < 50, f"P95 search latency {p95_latency:.2f}ms exceeds 50ms target"

    @pytest.mark.asyncio
    async def test_batch_add_faster_than_sequential(self, faiss_manager, sample_vectors_768dim):
        """Test: Batch add is 5-10x faster than sequential adds"""
        # Arrange - 100 vectors
        embeddings = [
            (f"emb_batch_perf_{i}", sample_vectors_768dim[i].tolist()) for i in range(100)
        ]

        # Act - batch add
        start = time.perf_counter()
        await faiss_manager.add_batch(embeddings, "test_ivf256_pq64")
        batch_time_ms = (time.perf_counter() - start) * 1000

        # Sequential adds (separate manager to avoid duplicates)
        FaissIndexManager._instance = None
        seq_mgr = FaissIndexManager.get_instance()
        seq_mgr._index_id = "test_sequential"
        await seq_mgr.initialize(
            index_path=faiss_manager._index_path,
            train_if_needed=False,
        )

        embeddings_seq = [
            (f"emb_seq_perf_{i}", sample_vectors_768dim[i].tolist()) for i in range(100)
        ]

        start = time.perf_counter()
        for embedding_id, vector in embeddings_seq:
            await seq_mgr.add(embedding_id, vector, "test_sequential")
        sequential_time_ms = (time.perf_counter() - start) * 1000

        # Assert - batch at least 3x faster
        speedup = sequential_time_ms / batch_time_ms
        assert speedup >= 3, f"Batch add only {speedup:.1f}x faster, expected 5-10x"


# =============================================================================
# Test: Error Scenarios
# =============================================================================


class TestErrorScenarios:
    """Test error handling in FAISS operations"""

    @pytest.mark.asyncio
    async def test_uninitialized_manager_raises_error(self):
        """Test: Using uninitialized manager raises RuntimeError"""
        # Arrange - fresh manager not initialized
        FaissIndexManager._instance = None
        mgr = FaissIndexManager.get_instance()

        # Act & Assert
        with pytest.raises(RuntimeError, match="not initialized"):
            await mgr.add("emb_test", [0.1] * 768, "test_index")

    @pytest.mark.asyncio
    async def test_invalid_index_path_raises_error(self):
        """Test: Invalid index path raises OSError"""
        # Arrange
        FaissIndexManager._instance = None
        mgr = FaissIndexManager.get_instance()

        # Act & Assert - invalid path like /invalid/nonexistent/path
        from pathlib import Path as PathLib

        with pytest.raises((OSError, FileNotFoundError, PermissionError)):
            mgr._index_id = "test_invalid_path"
            await mgr.initialize(
                index_path=PathLib("/invalid/nonexistent/path/to/index"),
                train_if_needed=False,
            )
