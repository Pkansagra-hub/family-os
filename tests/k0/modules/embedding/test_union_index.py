"""
Unit Tests for GAP-001 Milestone 4: FAISS Union Index

Tests for union index components:
- UnionIndexMetadata: Vector metadata tracking
- UnionIndexBuilder: Building index from truth layers
- UnionIndexSearcher: Cross-layer search
- UnionIndexManager: Lifecycle management

Test Coverage:
- Metadata add/get operations
- JSON serialization round-trip
- Builder layer queries
- Searcher filtering
- Manager persistence

GAP Reference: GAP_001 Section 6-7
Version: 1.0.0
"""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from k0.modules.embedding.union_index_metadata import UnionIndexMetadata, VectorMetadata

# =============================================================================
# VectorMetadata Tests
# =============================================================================


class TestVectorMetadata:
    """Tests for VectorMetadata dataclass."""

    def test_create_metadata(self):
        """Test creating VectorMetadata with all fields."""
        meta = VectorMetadata(
            layer="st_epi",
            record_id="epi_123",
            tenant_id="t1",
            space_id="s1",
            faiss_idx=0,
        )
        assert meta.layer == "st_epi"
        assert meta.record_id == "epi_123"
        assert meta.tenant_id == "t1"
        assert meta.space_id == "s1"
        assert meta.faiss_idx == 0

    def test_default_faiss_idx(self):
        """Test default faiss_idx is -1."""
        meta = VectorMetadata(
            layer="st_sem",
            record_id="sem_456",
            tenant_id="t1",
            space_id="s1",
        )
        assert meta.faiss_idx == -1


# =============================================================================
# UnionIndexMetadata Tests
# =============================================================================


class TestUnionIndexMetadata:
    """Tests for UnionIndexMetadata."""

    def test_create_empty_metadata(self):
        """Test creating empty metadata."""
        meta = UnionIndexMetadata()
        assert meta.total_vectors == 0
        assert len(meta.entries) == 0
        assert meta.layer_counts == {}
        assert meta.model_version == "ultrabert-v2.1.0"

    def test_add_single_entry(self):
        """Test adding a single entry."""
        meta = UnionIndexMetadata()
        entry = VectorMetadata(
            layer="st_epi",
            record_id="epi_123",
            tenant_id="t1",
            space_id="s1",
        )
        idx = meta.add(entry)

        assert idx == 0
        assert entry.faiss_idx == 0
        assert meta.total_vectors == 1
        assert meta.layer_counts["st_epi"] == 1
        assert len(meta.entries) == 1

    def test_add_multiple_entries(self):
        """Test adding entries from multiple layers."""
        meta = UnionIndexMetadata()

        # Add entries from different layers
        for i, layer in enumerate(["st_epi", "st_epi", "st_sem", "st_kg_dom"]):
            entry = VectorMetadata(
                layer=layer,
                record_id=f"{layer}_{i}",
                tenant_id="t1",
                space_id="s1",
            )
            idx = meta.add(entry)
            assert idx == i

        assert meta.total_vectors == 4
        assert meta.layer_counts["st_epi"] == 2
        assert meta.layer_counts["st_sem"] == 1
        assert meta.layer_counts["st_kg_dom"] == 1

    def test_get_valid_index(self):
        """Test getting entry by valid index."""
        meta = UnionIndexMetadata()
        entry = VectorMetadata(
            layer="st_epi",
            record_id="epi_123",
            tenant_id="t1",
            space_id="s1",
        )
        meta.add(entry)

        result = meta.get(0)
        assert result is not None
        assert result.layer == "st_epi"
        assert result.record_id == "epi_123"

    def test_get_invalid_index(self):
        """Test getting entry by invalid index returns None."""
        meta = UnionIndexMetadata()
        assert meta.get(0) is None
        assert meta.get(-1) is None
        assert meta.get(100) is None

    def test_search_results_to_layer_ids(self):
        """Test converting FAISS results to layer/id tuples."""
        meta = UnionIndexMetadata()

        # Add entries
        for i, layer in enumerate(["st_epi", "st_sem", "st_procedural"]):
            entry = VectorMetadata(
                layer=layer,
                record_id=f"rec_{i}",
                tenant_id="t1",
                space_id="s1",
            )
            meta.add(entry)

        # Simulate FAISS search results
        faiss_indices = [2, 0, 1]
        scores = [0.95, 0.85, 0.75]

        results = meta.search_results_to_layer_ids(faiss_indices, scores)

        assert len(results) == 3
        assert results[0] == ("st_procedural", "rec_2", 0.95)
        assert results[1] == ("st_epi", "rec_0", 0.85)
        assert results[2] == ("st_sem", "rec_1", 0.75)

    def test_get_layer_count(self):
        """Test getting count for specific layer."""
        meta = UnionIndexMetadata()

        for layer in ["st_epi", "st_epi", "st_sem"]:
            entry = VectorMetadata(
                layer=layer,
                record_id="rec_1",
                tenant_id="t1",
                space_id="s1",
            )
            meta.add(entry)

        assert meta.get_layer_count("st_epi") == 2
        assert meta.get_layer_count("st_sem") == 1
        assert meta.get_layer_count("st_social") == 0

    def test_to_json(self):
        """Test JSON serialization."""
        meta = UnionIndexMetadata(
            build_timestamp=1704067200000,
            model_version="ultrabert-v2.1.0",
        )

        entry = VectorMetadata(
            layer="st_epi",
            record_id="epi_123",
            tenant_id="t1",
            space_id="s1",
        )
        meta.add(entry)

        json_str = meta.to_json()
        data = json.loads(json_str)

        assert data["total_vectors"] == 1
        assert data["build_timestamp"] == 1704067200000
        assert data["model_version"] == "ultrabert-v2.1.0"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["layer"] == "st_epi"

    def test_from_json(self):
        """Test JSON deserialization."""
        json_str = json.dumps(
            {
                "entries": [
                    {
                        "layer": "st_sem",
                        "record_id": "sem_456",
                        "tenant_id": "t2",
                        "space_id": "s2",
                        "faiss_idx": 0,
                    }
                ],
                "layer_counts": {"st_sem": 1},
                "total_vectors": 1,
                "build_timestamp": 1704067200000,
                "model_version": "ultrabert-v2.1.0",
            }
        )

        meta = UnionIndexMetadata.from_json(json_str)

        assert meta.total_vectors == 1
        assert meta.build_timestamp == 1704067200000
        assert len(meta.entries) == 1
        assert meta.entries[0].layer == "st_sem"
        assert meta.entries[0].record_id == "sem_456"

    def test_json_round_trip(self):
        """Test JSON serialization round-trip."""
        original = UnionIndexMetadata(
            build_timestamp=int(time.time() * 1000),
        )

        for i, layer in enumerate(["st_epi", "st_sem", "st_social"]):
            entry = VectorMetadata(
                layer=layer,
                record_id=f"rec_{i}",
                tenant_id="t1",
                space_id="s1",
            )
            original.add(entry)

        # Round-trip
        json_str = original.to_json()
        restored = UnionIndexMetadata.from_json(json_str)

        assert restored.total_vectors == original.total_vectors
        assert restored.layer_counts == original.layer_counts
        assert restored.build_timestamp == original.build_timestamp
        assert len(restored.entries) == len(original.entries)

    def test_to_dict(self):
        """Test to_dict for logging."""
        meta = UnionIndexMetadata(build_timestamp=1704067200000)
        entry = VectorMetadata(
            layer="st_epi",
            record_id="epi_123",
            tenant_id="t1",
            space_id="s1",
        )
        meta.add(entry)

        d = meta.to_dict()
        assert d["total_vectors"] == 1
        assert d["build_timestamp"] == 1704067200000
        assert "st_epi" in d["layer_counts"]

    def test_repr(self):
        """Test string representation."""
        meta = UnionIndexMetadata(build_timestamp=1704067200000)
        entry = VectorMetadata(
            layer="st_epi",
            record_id="epi_123",
            tenant_id="t1",
            space_id="s1",
        )
        meta.add(entry)

        repr_str = repr(meta)
        assert "UnionIndexMetadata" in repr_str
        assert "total=1" in repr_str


# =============================================================================
# UnionIndexBuilder Tests
# =============================================================================


class TestUnionIndexBuilder:
    """Tests for UnionIndexBuilder."""

    @pytest.fixture
    def sample_vector_bytes(self):
        """Create sample 768-dim vector as bytes."""
        vec = np.random.randn(768).astype(np.float32)
        return vec.tobytes()

    @pytest.fixture
    def mock_conn(self, sample_vector_bytes):
        """Create mock asyncpg connection."""
        conn = AsyncMock()

        # Create mock rows for each layer
        mock_rows = [
            {
                "episode_id": "epi_1",
                "tenant_id": "t1",
                "space_id": "s1",
                "embedding_vector": sample_vector_bytes,
            },
            {
                "episode_id": "epi_2",
                "tenant_id": "t1",
                "space_id": "s1",
                "embedding_vector": sample_vector_bytes,
            },
        ]

        # Mock fetch to return different rows based on query
        async def mock_fetch(query, *args):
            if "st_epi" in query:
                return [
                    {
                        "episode_id": "epi_1",
                        "tenant_id": "t1",
                        "space_id": "s1",
                        "embedding_vector": sample_vector_bytes,
                    }
                ]
            elif "st_sem" in query:
                return [
                    {
                        "pattern_id": "sem_1",
                        "tenant_id": "t1",
                        "space_id": "s1",
                        "embedding_vector": sample_vector_bytes,
                    }
                ]
            return []

        conn.fetch = mock_fetch
        return conn

    @pytest.mark.asyncio
    async def test_build_empty_database(self):
        """Test building index from empty database."""
        from k0.modules.embedding.union_index_builder import UnionIndexBuilder

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])

        builder = UnionIndexBuilder()
        index, metadata = await builder.build(conn)

        assert metadata.total_vectors == 0
        assert index.ntotal == 0

    @pytest.mark.asyncio
    async def test_build_with_vectors(self, mock_conn):
        """Test building index with vectors."""
        from k0.modules.embedding.union_index_builder import UnionIndexBuilder

        builder = UnionIndexBuilder()
        index, metadata = await builder.build(mock_conn)

        # Should have vectors from st_epi and st_sem (our mock returns 1 each)
        assert metadata.total_vectors == 2
        assert index.ntotal == 2
        assert metadata.layer_counts.get("st_epi", 0) == 1
        assert metadata.layer_counts.get("st_sem", 0) == 1

    @pytest.mark.asyncio
    async def test_build_with_tenant_filter(self, sample_vector_bytes):
        """Test building with tenant filter."""
        from k0.modules.embedding.union_index_builder import UnionIndexBuilder

        conn = AsyncMock()

        # Track queries to verify tenant filter
        queries_executed = []

        async def mock_fetch(query, *args):
            queries_executed.append((query, args))
            return []

        conn.fetch = mock_fetch

        builder = UnionIndexBuilder()
        await builder.build(conn, tenant_id="test_tenant")

        # Verify tenant_id was in query parameters
        assert len(queries_executed) > 0
        for query, args in queries_executed:
            if args:
                assert "test_tenant" in args

    @pytest.mark.asyncio
    async def test_build_skips_invalid_vectors(self):
        """Test that invalid vector bytes are skipped."""
        from k0.modules.embedding.union_index_builder import UnionIndexBuilder

        conn = AsyncMock()

        # Return rows with wrong-sized vectors for ALL layers to avoid KeyError
        async def mock_fetch(query, *args):
            # Parse which layer is being queried and return appropriate pk column
            for layer, pk in [
                ("st_epi", "episode_id"),
                ("st_sem", "pattern_id"),
                ("st_procedural", "routine_id"),
                ("st_social", "relationship_id"),
                ("st_prospective", "intention_id"),
                ("st_kg_dom", "entity_id"),
            ]:
                if layer in query:
                    return [
                        {
                            pk: f"{layer}_1",
                            "tenant_id": "t1",
                            "space_id": "s1",
                            "embedding_vector": b"too_short",  # Invalid
                        }
                    ]
            return []

        conn.fetch = mock_fetch

        builder = UnionIndexBuilder()
        index, metadata = await builder.build(conn)

        # Should skip all invalid vectors
        assert metadata.total_vectors == 0
        assert index.ntotal == 0


# =============================================================================
# UnionIndexSearcher Tests
# =============================================================================


class TestUnionIndexSearcher:
    """Tests for UnionIndexSearcher."""

    @pytest.fixture
    def sample_index_and_metadata(self):
        """Create a sample FAISS index with metadata."""
        import faiss

        # Create 10 sample vectors
        vectors = np.random.randn(10, 768).astype(np.float32)
        faiss.normalize_L2(vectors)

        index = faiss.IndexFlatIP(768)
        index.add(vectors)

        # Create metadata
        metadata = UnionIndexMetadata(build_timestamp=int(time.time() * 1000))
        layers = ["st_epi", "st_sem", "st_procedural", "st_social", "st_prospective"]

        for i in range(10):
            layer = layers[i % len(layers)]
            entry = VectorMetadata(
                layer=layer,
                record_id=f"rec_{i}",
                tenant_id=f"t{i % 2}",  # Alternate between t0 and t1
                space_id="s1",
            )
            metadata.add(entry)

        return index, metadata, vectors

    def test_search_basic(self, sample_index_and_metadata):
        """Test basic search."""
        from k0.modules.embedding.union_index_searcher import UnionIndexSearcher

        index, metadata, vectors = sample_index_and_metadata
        searcher = UnionIndexSearcher(index, metadata)

        # Search with first vector (should find itself as top result)
        results = searcher.search(vectors[0], k=5)

        assert len(results) == 5
        assert results[0].score > 0.99  # Should be very similar
        assert results[0].record_id == "rec_0"

    def test_search_with_layer_filter(self, sample_index_and_metadata):
        """Test search with layer filter."""
        from k0.modules.embedding.union_index_searcher import UnionIndexSearcher

        index, metadata, vectors = sample_index_and_metadata
        searcher = UnionIndexSearcher(index, metadata)

        # Search only in st_epi
        results = searcher.search(
            vectors[0],
            k=10,
            layer_filter=["st_epi"],
        )

        # All results should be from st_epi
        for r in results:
            assert r.layer == "st_epi"

    def test_search_with_tenant_filter(self, sample_index_and_metadata):
        """Test search with tenant filter."""
        from k0.modules.embedding.union_index_searcher import UnionIndexSearcher

        index, metadata, vectors = sample_index_and_metadata
        searcher = UnionIndexSearcher(index, metadata)

        # Search only for tenant t0
        results = searcher.search(
            vectors[0],
            k=10,
            tenant_id="t0",
        )

        # All results should be from t0
        for r in results:
            assert r.tenant_id == "t0"

    def test_search_empty_index(self):
        """Test search on empty index."""
        import faiss

        from k0.modules.embedding.union_index_searcher import UnionIndexSearcher

        index = faiss.IndexFlatIP(768)
        metadata = UnionIndexMetadata()
        searcher = UnionIndexSearcher(index, metadata)

        query = np.random.randn(768).astype(np.float32)
        results = searcher.search(query, k=10)

        assert len(results) == 0

    def test_search_result_to_dict(self, sample_index_and_metadata):
        """Test SearchResult.to_dict()."""
        from k0.modules.embedding.union_index_searcher import UnionIndexSearcher

        index, metadata, vectors = sample_index_and_metadata
        searcher = UnionIndexSearcher(index, metadata)

        results = searcher.search(vectors[0], k=1)
        assert len(results) == 1

        d = results[0].to_dict()
        assert "layer" in d
        assert "record_id" in d
        assert "score" in d
        assert "tenant_id" in d
        assert "space_id" in d

    def test_searcher_properties(self, sample_index_and_metadata):
        """Test searcher properties."""
        from k0.modules.embedding.union_index_searcher import UnionIndexSearcher

        index, metadata, _ = sample_index_and_metadata
        searcher = UnionIndexSearcher(index, metadata)

        assert searcher.total_vectors == 10
        assert len(searcher.layer_counts) > 0
        assert searcher.build_timestamp > 0
        assert searcher.model_version == "ultrabert-v2.1.0"

    def test_get_stats(self, sample_index_and_metadata):
        """Test get_stats method."""
        from k0.modules.embedding.union_index_searcher import UnionIndexSearcher

        index, metadata, _ = sample_index_and_metadata
        searcher = UnionIndexSearcher(index, metadata)

        stats = searcher.get_stats()
        assert stats["total_vectors"] == 10
        assert stats["faiss_ntotal"] == 10
        assert "layer_counts" in stats


# =============================================================================
# UnionIndexManager Tests
# =============================================================================


class TestUnionIndexManager:
    """Tests for UnionIndexManager."""

    @pytest.fixture
    def temp_index_dir(self):
        """Create temporary directory for index files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_conn_with_vectors(self):
        """Create mock connection that returns vectors."""
        conn = AsyncMock()

        vec_bytes = np.random.randn(768).astype(np.float32).tobytes()

        async def mock_fetch(query, *args):
            if "st_epi" in query:
                return [
                    {
                        "episode_id": "epi_1",
                        "tenant_id": "t1",
                        "space_id": "s1",
                        "embedding_vector": vec_bytes,
                    }
                ]
            return []

        conn.fetch = mock_fetch
        return conn

    def test_manager_initialization(self, temp_index_dir):
        """Test manager initialization."""
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        manager = UnionIndexManager(temp_index_dir)

        assert not manager.is_loaded
        assert manager.needs_rebuild

    @pytest.mark.asyncio
    async def test_build_and_save(self, temp_index_dir, mock_conn_with_vectors):
        """Test building and saving index."""
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        manager = UnionIndexManager(temp_index_dir)
        searcher = await manager.build_and_save(mock_conn_with_vectors)

        assert manager.is_loaded
        assert searcher is not None
        assert searcher.total_vectors >= 1

        # Verify files exist
        index_path = Path(temp_index_dir) / "union_index.faiss"
        metadata_path = Path(temp_index_dir) / "union_index_metadata.json"
        assert index_path.exists()
        assert metadata_path.exists()

    @pytest.mark.asyncio
    async def test_load_from_disk(self, temp_index_dir, mock_conn_with_vectors):
        """Test loading index from disk."""
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        # First, build and save
        manager1 = UnionIndexManager(temp_index_dir)
        await manager1.build_and_save(mock_conn_with_vectors)
        original_total = manager1._metadata.total_vectors

        # Now load in new manager
        manager2 = UnionIndexManager(temp_index_dir)
        searcher = manager2.load()

        assert searcher is not None
        assert searcher.total_vectors == original_total

    def test_load_nonexistent(self, temp_index_dir):
        """Test loading when no index exists."""
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        manager = UnionIndexManager(temp_index_dir)
        searcher = manager.load()

        assert searcher is None

    def test_needs_rebuild_fresh_index(self, temp_index_dir):
        """Test needs_rebuild for fresh index."""
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        manager = UnionIndexManager(temp_index_dir, rebuild_interval_hours=6)

        # Create metadata with recent timestamp
        manager._metadata = UnionIndexMetadata(
            build_timestamp=int(time.time() * 1000),
        )

        assert not manager.needs_rebuild

    def test_needs_rebuild_old_index(self, temp_index_dir):
        """Test needs_rebuild for old index."""
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        manager = UnionIndexManager(temp_index_dir, rebuild_interval_hours=6)

        # Create metadata with old timestamp (7 hours ago)
        old_timestamp = int((time.time() - 7 * 3600) * 1000)
        manager._metadata = UnionIndexMetadata(build_timestamp=old_timestamp)

        assert manager.needs_rebuild

    @pytest.mark.asyncio
    async def test_delete_index(self, temp_index_dir, mock_conn_with_vectors):
        """Test deleting index files."""
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        manager = UnionIndexManager(temp_index_dir)
        await manager.build_and_save(mock_conn_with_vectors)

        # Delete
        result = manager.delete_index()

        assert result is True
        assert not manager.is_loaded

        # Verify files deleted
        index_path = Path(temp_index_dir) / "union_index.faiss"
        metadata_path = Path(temp_index_dir) / "union_index_metadata.json"
        assert not index_path.exists()
        assert not metadata_path.exists()

    @pytest.mark.asyncio
    async def test_get_stats(self, temp_index_dir, mock_conn_with_vectors):
        """Test get_stats method."""
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        manager = UnionIndexManager(temp_index_dir)
        await manager.build_and_save(mock_conn_with_vectors)

        stats = manager.get_stats()
        assert stats["is_loaded"] is True
        assert "total_vectors" in stats
        assert "build_timestamp" in stats


# =============================================================================
# Singleton Tests
# =============================================================================


class TestManagerSingleton:
    """Tests for manager singleton pattern."""

    def test_get_manager_creates_instance(self):
        """Test get_manager creates singleton."""
        from k0.modules.embedding.union_index_manager import get_manager, reset_manager

        reset_manager()

        with patch.dict("os.environ", {"FAISS_UNION_INDEX_DIR": "/tmp/test_faiss"}):
            manager = get_manager()
            assert manager is not None
            # Use Path comparison to handle Windows/Unix path differences
            assert Path(manager.index_dir).as_posix() == "/tmp/test_faiss"

        reset_manager()

    def test_get_manager_returns_same_instance(self):
        """Test get_manager returns same instance."""
        from k0.modules.embedding.union_index_manager import get_manager, reset_manager

        reset_manager()

        with patch.dict("os.environ", {"FAISS_UNION_INDEX_DIR": "/tmp/test_faiss2"}):
            manager1 = get_manager()
            manager2 = get_manager()
            assert manager1 is manager2

        reset_manager()

    def test_reset_manager(self):
        """Test reset_manager clears singleton."""
        from k0.modules.embedding.union_index_manager import get_manager, reset_manager

        reset_manager()

        with patch.dict("os.environ", {"FAISS_UNION_INDEX_DIR": "/tmp/test_faiss3"}):
            manager1 = get_manager()
            reset_manager()
            manager2 = get_manager()

            # After reset, should be new instance
            assert manager1 is not manager2

        reset_manager()


# =============================================================================
# Integration Tests
# =============================================================================


class TestUnionIndexIntegration:
    """Integration tests for full workflow."""

    @pytest.fixture
    def temp_index_dir(self):
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.mark.asyncio
    async def test_full_workflow(self, temp_index_dir):
        """Test complete build → save → load → search workflow."""
        from k0.modules.embedding.union_index_manager import UnionIndexManager

        # Create mock connection with real vectors
        vectors = np.random.randn(5, 768).astype(np.float32)

        conn = AsyncMock()

        async def mock_fetch(query, *args):
            if "st_epi" in query:
                return [
                    {
                        "episode_id": f"epi_{i}",
                        "tenant_id": "t1",
                        "space_id": "s1",
                        "embedding_vector": vectors[i].tobytes(),
                    }
                    for i in range(3)
                ]
            elif "st_sem" in query:
                return [
                    {
                        "pattern_id": f"sem_{i}",
                        "tenant_id": "t1",
                        "space_id": "s1",
                        "embedding_vector": vectors[3 + i].tobytes(),
                    }
                    for i in range(2)
                ]
            return []

        conn.fetch = mock_fetch

        # Build and save
        manager = UnionIndexManager(temp_index_dir)
        searcher = await manager.build_and_save(conn)

        assert searcher.total_vectors == 5
        assert searcher.layer_counts.get("st_epi", 0) == 3
        assert searcher.layer_counts.get("st_sem", 0) == 2

        # Load in new manager
        manager2 = UnionIndexManager(temp_index_dir)
        searcher2 = manager2.load()

        assert searcher2 is not None
        assert searcher2.total_vectors == 5

        # Search
        query = vectors[0]  # Should find epi_0 as top result
        results = searcher2.search(query, k=3)

        assert len(results) == 3
        assert results[0].record_id == "epi_0"
        assert results[0].score > 0.99
