"""
Tests for K0 Query Client

Unit and integration tests for:
- Query filter validation
- Query request formatting
- Response parsing
- Cache functionality
- Metrics tracking
"""

from l5_infrastructure.k0_bridge.k0_query_client import (
    K0QueryCache,
    K0QueryClient,
    Memory,
    QueryFilters,
)


class TestQueryFilters:
    """Test QueryFilters validation and serialization."""

    def test_filter_creation_with_defaults(self):
        """Test creating filters with defaults."""
        filters = QueryFilters()
        assert filters.time_range is None
        assert filters.tags is None
        assert filters.similarity_threshold == 0.5

    def test_filter_with_time_range(self):
        """Test filters with time range."""
        filters = QueryFilters(
            time_range={"start": 1000, "end": 2000},
        )
        is_valid, error = filters.validate()
        assert is_valid

    def test_filter_invalid_time_range(self):
        """Test validation of invalid time range."""
        filters = QueryFilters(
            time_range={"start": 2000, "end": 1000},  # Inverted
        )
        is_valid, error = filters.validate()
        assert not is_valid
        assert error is not None and ("start" in error.lower() or "end" in error.lower())

    def test_filter_missing_time_range_keys(self):
        """Test time range missing required keys."""
        filters = QueryFilters(
            time_range={"start": 1000},  # Missing 'end'
        )
        is_valid, error = filters.validate()
        assert not is_valid

    def test_filter_with_tags(self):
        """Test filters with tags."""
        filters = QueryFilters(tags=["health", "recovery"])
        is_valid, error = filters.validate()
        assert is_valid

    def test_filter_invalid_tags_type(self):
        """Test tags must be list."""
        # Create filter with invalid tags manually to test validation
        filters = QueryFilters()
        filters.tags = "health"  # type: ignore  # Intentionally wrong type
        is_valid, error = filters.validate()
        assert not is_valid

    def test_filter_similarity_threshold(self):
        """Test similarity threshold validation."""
        # Valid range [0.0, 1.0]
        filters = QueryFilters(similarity_threshold=0.7)
        is_valid, error = filters.validate()
        assert is_valid

        # Invalid: too high
        filters = QueryFilters(similarity_threshold=1.5)
        is_valid, error = filters.validate()
        assert not is_valid

        # Invalid: too low
        filters = QueryFilters(similarity_threshold=-0.1)
        is_valid, error = filters.validate()
        assert not is_valid

    def test_filter_to_dict(self):
        """Test filters to dict excludes None values."""
        filters = QueryFilters(
            tags=["health"],
            similarity_threshold=0.8,
        )
        data = filters.to_dict()
        assert "tags" in data
        assert "similarity_threshold" in data
        assert "time_range" not in data  # None values excluded


class TestMemory:
    """Test Memory data class."""

    def test_memory_creation(self):
        """Test creating Memory object."""
        memory = Memory(
            memory_id="mem_123",
            memory_type="episodic",
            content="Test content",
            timestamp=1728000000,
            relevance_score=0.95,
            fts_score=0.9,
            vector_score=0.95,
            kg_score=0.8,
            tags=["health"],
            provenance={"source": "fts"},
        )

        assert memory.memory_id == "mem_123"
        assert memory.relevance_score == 0.95

    def test_memory_to_dict(self):
        """Test converting Memory to dict."""
        memory = Memory(
            memory_id="mem_123",
            memory_type="episodic",
            content="Test",
            timestamp=1728000000,
            relevance_score=0.95,
            fts_score=None,
            vector_score=0.95,
            kg_score=None,
            tags=[],
            provenance={},
        )

        data = memory.to_dict()
        assert data["memory_id"] == "mem_123"
        assert data["vector_score"] == 0.95


class TestK0QueryCache:
    """Test query result caching."""

    def test_cache_set_and_get(self):
        """Test caching and retrieving results."""
        cache = K0QueryCache(ttl_seconds=60)
        filters = QueryFilters()

        memories = [
            Memory(
                memory_id="mem_1",
                memory_type="episodic",
                content="Test",
                timestamp=1728000000,
                relevance_score=0.9,
                fts_score=None,
                vector_score=None,
                kg_score=None,
                tags=[],
                provenance={},
            )
        ]

        cache.set("episodic", filters, 10, memories)

        # Should retrieve from cache
        cached = cache.get("episodic", filters, 10)
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].memory_id == "mem_1"

    def test_cache_expiration(self):
        """Test cache TTL expiration."""
        cache = K0QueryCache(ttl_seconds=0)  # Instant expiration
        filters = QueryFilters()
        memories = []

        cache.set("episodic", filters, 10, memories)

        # Should be expired
        import time

        time.sleep(0.01)
        cached = cache.get("episodic", filters, 10)
        assert cached is None

    def test_cache_different_keys(self):
        """Test cache with different queries."""
        cache = K0QueryCache(ttl_seconds=60)
        filters1 = QueryFilters(tags=["health"])
        filters2 = QueryFilters(tags=["recovery"])

        memories1 = [
            Memory(
                memory_id="mem_1",
                memory_type="episodic",
                content="Health",
                timestamp=1728000000,
                relevance_score=0.9,
                fts_score=None,
                vector_score=None,
                kg_score=None,
                tags=["health"],
                provenance={},
            )
        ]
        memories2 = [
            Memory(
                memory_id="mem_2",
                memory_type="episodic",
                content="Recovery",
                timestamp=1728000000,
                relevance_score=0.9,
                fts_score=None,
                vector_score=None,
                kg_score=None,
                tags=["recovery"],
                provenance={},
            )
        ]

        cache.set("episodic", filters1, 10, memories1)
        cache.set("episodic", filters2, 10, memories2)

        cached1 = cache.get("episodic", filters1, 10)
        cached2 = cache.get("episodic", filters2, 10)

        assert cached1 is not None and cached1[0].memory_id == "mem_1"
        assert cached2 is not None and cached2[0].memory_id == "mem_2"


class TestK0QueryClient:
    """Test K0 Query Client initialization and validation."""

    def test_client_initialization(self):
        """Test client initialization."""
        client = K0QueryClient()
        assert client.k0_base_url == "http://localhost:5201"
        assert client.timeout_seconds == 10.0
        assert client.max_retries == 3

    def test_client_custom_params(self):
        """Test client with custom parameters."""
        client = K0QueryClient(
            k0_base_url="http://localhost:5300",
            timeout_seconds=30.0,
            max_retries=5,
        )
        assert client.k0_base_url == "http://localhost:5300"
        assert client.timeout_seconds == 30.0
        assert client.max_retries == 5

    def test_client_stats_initial(self):
        """Test initial client statistics."""
        client = K0QueryClient()
        stats = client.get_stats()

        assert stats["query_count"] == 0
        assert stats["error_count"] == 0
        assert stats["cache_hits"] == 0

    def test_parse_response(self):
        """Test parsing K0 response."""
        client = K0QueryClient()

        response = {
            "status": "success",
            "memories": [
                {
                    "memory_id": "mem_1",
                    "content": "Test memory",
                    "timestamp": 1728000000,
                    "relevance_score": 0.95,
                    "scores": {
                        "fts_score": 0.9,
                        "vector_score": 0.95,
                        "kg_score": 0.8,
                    },
                    "tags": ["health", "recovery"],
                    "provenance": {"source": "fts+vector"},
                },
            ],
        }

        memories = client._parse_response(response, "episodic")

        assert len(memories) == 1
        assert memories[0].memory_id == "mem_1"
        assert memories[0].relevance_score == 0.95

    def test_parse_empty_response(self):
        """Test parsing empty K0 response."""
        client = K0QueryClient()
        response = {"status": "success", "memories": []}

        memories = client._parse_response(response, "episodic")
        assert len(memories) == 0

    def test_parse_malformed_response(self):
        """Test parsing malformed response."""
        client = K0QueryClient()
        response = {"status": "success", "memories": [{"incomplete": "data"}]}

        memories = client._parse_response(response, "episodic")
        # Should handle gracefully, returning empty or partial results
        assert isinstance(memories, list)
