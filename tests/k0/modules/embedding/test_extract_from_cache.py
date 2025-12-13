"""
Unit tests for M22: embedding.extract_from_cache

Tests for UltraBERT cache-based embedding extraction.

Contract: k0/contracts/modules/embedding.extract_from_cache.v1.yaml
ADR: ADR-K003 (Inline Embedding via UltraBERT)
"""

import asyncio
import uuid
from unittest.mock import Mock, patch

import pytest

from k0.modules.embedding import extract_from_cache


@pytest.fixture(autouse=True)
def reset_module_metrics():
    """Reset module metrics before each test."""
    extract_from_cache.reset_metrics()
    yield
    extract_from_cache.reset_metrics()


@pytest.fixture
def mock_envelope():
    """Standard test envelope with text."""
    return {
        "header": {
            "envelope_id": str(uuid.uuid4()),
            "tenant_id": "tenant_test",
            "space_id": "space_home",
        },
        "body": {"text": "Mom picked up the kids from school today!"},
        "metadata": {},
    }


@pytest.fixture
def mock_enriched():
    """Empty enriched data (M22 doesn't depend on prior modules)."""
    return {}


@pytest.fixture
def mock_context():
    """Mock execution context."""
    return Mock()


@pytest.fixture
def test_embedding():
    """768-dimensional test embedding vector."""
    return [0.1] * 768


# =============================================================================
# Test Class 1: Cache Hit Path
# =============================================================================


class TestCacheHitPath:
    """Test embedding extraction from UltraBERT cache."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_embedding(
        self, mock_envelope, mock_enriched, mock_context, test_embedding
    ):
        """Test successful cache hit returns embedding."""
        mock_result = Mock()
        mock_result.embedding = test_embedding

        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            result = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        assert result["embedding"] == test_embedding
        assert result["vector_dim"] == 768
        assert result["model_id"] == "ultrabert_v2.1.0"
        assert result["source"] == "cache_hit"
        assert result["embedding_id"] is not None
        assert isinstance(uuid.UUID(result["embedding_id"]), uuid.UUID)

        metrics = extract_from_cache.get_metrics()
        assert metrics["cache_hits"] == 1
        assert metrics["cache_misses_direct_call"] == 0

    @pytest.mark.asyncio
    async def test_cache_hit_generates_uuid(
        self, mock_envelope, mock_enriched, mock_context, test_embedding
    ):
        """Test that cache hit generates unique UUIDs."""
        mock_result = Mock()
        mock_result.embedding = test_embedding

        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            result1 = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)
            result2 = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        assert result1["embedding_id"] != result2["embedding_id"]

    @pytest.mark.asyncio
    async def test_cache_hit_preserves_embedding_length(
        self, mock_envelope, mock_enriched, mock_context
    ):
        """Test that cache hit preserves exact embedding dimensions."""
        mock_result = Mock()
        mock_result.embedding = [0.1] * 768

        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            result = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        assert len(result["embedding"]) == 768


# =============================================================================
# Test Class 2: Cache Miss / Direct Call Path
# =============================================================================


class TestCacheMissPath:
    """Test fallback to direct embedding call."""

    @pytest.mark.asyncio
    async def test_cache_miss_calls_get_embedding(
        self, mock_envelope, mock_enriched, mock_context, test_embedding
    ):
        """Test cache miss triggers direct get_embedding() call."""
        with (
            patch(
                "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
                return_value=None,
            ),
            patch(
                "k0.modules.embedding.extract_from_cache.get_embedding", return_value=test_embedding
            ) as mock_get_embedding,
        ):
            result = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        mock_get_embedding.assert_called_once_with("Mom picked up the kids from school today!")
        assert result["embedding"] == test_embedding
        assert result["source"] == "direct_call"
        assert result["embedding_id"] is not None

        metrics = extract_from_cache.get_metrics()
        assert metrics["cache_misses_direct_call"] == 1
        assert metrics["cache_hits"] == 0

    @pytest.mark.asyncio
    async def test_cache_miss_with_empty_embedding_attr(
        self, mock_envelope, mock_enriched, mock_context, test_embedding
    ):
        """Test cache result with None/empty embedding triggers fallback."""
        mock_result = Mock()
        mock_result.embedding = None

        with (
            patch(
                "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
                return_value=mock_result,
            ),
            patch(
                "k0.modules.embedding.extract_from_cache.get_embedding", return_value=test_embedding
            ),
        ):
            result = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        assert result["source"] == "direct_call"
        metrics = extract_from_cache.get_metrics()
        assert metrics["cache_misses_direct_call"] == 1

    @pytest.mark.asyncio
    async def test_cache_miss_with_no_embedding_attr(
        self, mock_envelope, mock_enriched, mock_context, test_embedding
    ):
        """Test cache result without embedding attribute triggers fallback."""
        mock_result = Mock(spec=[])  # No embedding attribute

        with (
            patch(
                "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
                return_value=mock_result,
            ),
            patch(
                "k0.modules.embedding.extract_from_cache.get_embedding", return_value=test_embedding
            ),
        ):
            result = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        assert result["source"] == "direct_call"


# =============================================================================
# Test Class 3: Failure Handling
# =============================================================================


class TestFailureHandling:
    """Test graceful degradation on failures."""

    @pytest.mark.asyncio
    async def test_ultrabert_unavailable_returns_failed(
        self, mock_envelope, mock_enriched, mock_context
    ):
        """Test UltraBERT unavailable returns source='failed'."""
        with (
            patch(
                "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
                return_value=None,
            ),
            patch("k0.modules.embedding.extract_from_cache.get_embedding", return_value=None),
        ):
            result = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        assert result["embedding"] is None
        assert result["embedding_id"] is None
        assert result["source"] == "failed"
        assert result["model_id"] == "ultrabert_v2.1.0"
        assert result["vector_dim"] == 768

        metrics = extract_from_cache.get_metrics()
        assert metrics["embedding_failures"] == 1

    @pytest.mark.asyncio
    async def test_empty_text_returns_no_text(self, mock_enriched, mock_context):
        """Test empty text input returns source='no_text'."""
        envelope = {"body": {"text": ""}}
        result = await extract_from_cache.run(envelope, mock_enriched, mock_context)

        assert result["embedding"] is None
        assert result["embedding_id"] is None
        assert result["source"] == "no_text"

        metrics = extract_from_cache.get_metrics()
        assert metrics["no_text_inputs"] == 1

    @pytest.mark.asyncio
    async def test_whitespace_text_returns_no_text(self, mock_enriched, mock_context):
        """Test whitespace-only text returns source='no_text'."""
        envelope = {"body": {"text": "   \n\t  "}}
        result = await extract_from_cache.run(envelope, mock_enriched, mock_context)

        assert result["source"] == "no_text"

    @pytest.mark.asyncio
    async def test_missing_body_returns_no_text(self, mock_enriched, mock_context):
        """Test envelope without body returns source='no_text'."""
        envelope = {"header": {}}
        result = await extract_from_cache.run(envelope, mock_enriched, mock_context)

        assert result["source"] == "no_text"

    @pytest.mark.asyncio
    async def test_missing_text_field_returns_no_text(self, mock_enriched, mock_context):
        """Test envelope without text field returns source='no_text'."""
        envelope = {"body": {}}
        result = await extract_from_cache.run(envelope, mock_enriched, mock_context)

        assert result["source"] == "no_text"


# =============================================================================
# Test Class 4: Contract Compliance
# =============================================================================


class TestContractCompliance:
    """Test module adheres to YAML contract."""

    @pytest.mark.asyncio
    async def test_output_schema_compliance(
        self, mock_envelope, mock_enriched, mock_context, test_embedding
    ):
        """Test output matches contract schema."""
        mock_result = Mock()
        mock_result.embedding = test_embedding

        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            result = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        # Contract requires these fields
        assert "embedding" in result
        assert "embedding_id" in result
        assert "vector_dim" in result
        assert "model_id" in result
        assert "source" in result

        # Type checks
        assert isinstance(result["embedding"], list)
        assert isinstance(result["embedding_id"], str)
        assert isinstance(result["vector_dim"], int)
        assert isinstance(result["model_id"], str)
        assert isinstance(result["source"], str)

    @pytest.mark.asyncio
    async def test_source_enum_values(
        self, mock_envelope, mock_enriched, mock_context, test_embedding
    ):
        """Test source field uses contract-defined enum values."""
        # Test cache_hit
        mock_result = Mock()
        mock_result.embedding = test_embedding
        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            result = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)
        assert result["source"] in ["cache_hit", "direct_call", "failed", "no_text"]

        # Test direct_call
        with (
            patch(
                "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
                return_value=None,
            ),
            patch(
                "k0.modules.embedding.extract_from_cache.get_embedding", return_value=test_embedding
            ),
        ):
            result = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)
        assert result["source"] in ["cache_hit", "direct_call", "failed", "no_text"]

    @pytest.mark.asyncio
    async def test_vector_dim_always_768(self, mock_envelope, mock_enriched, mock_context):
        """Test vector_dim is always 768 (contract requirement)."""
        # Test all paths
        paths = [
            ("cache_hit", lambda: Mock(embedding=[0.1] * 768), None),
            ("direct_call", lambda: None, [0.1] * 768),
            ("failed", lambda: None, None),
        ]

        for source_type, cache_result_fn, embedding in paths:
            with (
                patch(
                    "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
                    return_value=cache_result_fn(),
                ),
                patch(
                    "k0.modules.embedding.extract_from_cache.get_embedding", return_value=embedding
                ),
            ):
                result = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

            assert result["vector_dim"] == 768


# =============================================================================
# Test Class 5: Performance & Observability
# =============================================================================


class TestPerformanceObservability:
    """Test performance characteristics and metrics."""

    @pytest.mark.asyncio
    async def test_metrics_tracking(
        self, mock_envelope, mock_enriched, mock_context, test_embedding
    ):
        """Test metrics correctly track all paths."""
        # Cache hit
        mock_result = Mock()
        mock_result.embedding = test_embedding
        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        metrics = extract_from_cache.get_metrics()
        assert metrics["cache_hits"] == 1

        # Direct call
        with (
            patch(
                "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
                return_value=None,
            ),
            patch(
                "k0.modules.embedding.extract_from_cache.get_embedding", return_value=test_embedding
            ),
        ):
            await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        metrics = extract_from_cache.get_metrics()
        assert metrics["cache_misses_direct_call"] == 1

        # Failure
        with (
            patch(
                "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
                return_value=None,
            ),
            patch("k0.modules.embedding.extract_from_cache.get_embedding", return_value=None),
        ):
            await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        metrics = extract_from_cache.get_metrics()
        assert metrics["embedding_failures"] == 1

        # No text
        envelope = {"body": {"text": ""}}
        await extract_from_cache.run(envelope, mock_enriched, mock_context)

        metrics = extract_from_cache.get_metrics()
        assert metrics["no_text_inputs"] == 1

    @pytest.mark.asyncio
    async def test_metrics_reset(self, mock_envelope, mock_enriched, mock_context, test_embedding):
        """Test metrics can be reset."""
        mock_result = Mock()
        mock_result.embedding = test_embedding
        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        metrics = extract_from_cache.get_metrics()
        assert metrics["cache_hits"] == 1

        extract_from_cache.reset_metrics()
        metrics = extract_from_cache.get_metrics()
        assert metrics["cache_hits"] == 0

    @pytest.mark.asyncio
    async def test_latency_budget_compliance(
        self, mock_envelope, mock_enriched, mock_context, test_embedding
    ):
        """Test module completes within <1ms P95 latency budget (cache hit)."""
        import time

        mock_result = Mock()
        mock_result.embedding = test_embedding

        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            start = time.perf_counter()
            await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)
            elapsed_ms = (time.perf_counter() - start) * 1000

        # Cache hit should be <1ms (contract requirement)
        # Allow 5ms buffer for test overhead
        assert elapsed_ms < 5.0


# =============================================================================
# Test Class 6: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    @pytest.mark.asyncio
    async def test_very_long_text(self, mock_enriched, mock_context, test_embedding):
        """Test handling of very long text (>10KB)."""
        long_text = "A" * 10000
        envelope = {"body": {"text": long_text}}

        mock_result = Mock()
        mock_result.embedding = test_embedding
        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            result = await extract_from_cache.run(envelope, mock_enriched, mock_context)

        assert result["source"] == "cache_hit"
        assert result["embedding"] == test_embedding

    @pytest.mark.asyncio
    async def test_unicode_text(self, mock_enriched, mock_context, test_embedding):
        """Test handling of unicode text."""
        envelope = {"body": {"text": "Hello 世界 🌍 Здравствуй"}}

        mock_result = Mock()
        mock_result.embedding = test_embedding
        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            result = await extract_from_cache.run(envelope, mock_enriched, mock_context)

        assert result["source"] == "cache_hit"

    @pytest.mark.asyncio
    async def test_concurrent_execution(
        self, mock_envelope, mock_enriched, mock_context, test_embedding
    ):
        """Test multiple concurrent executions."""
        mock_result = Mock()
        mock_result.embedding = test_embedding

        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            tasks = [
                extract_from_cache.run(mock_envelope, mock_enriched, mock_context)
                for _ in range(10)
            ]
            results = await asyncio.gather(*tasks)

        assert len(results) == 10
        for result in results:
            assert result["source"] == "cache_hit"
            assert result["embedding"] == test_embedding

        # All should generate unique UUIDs
        embedding_ids = [r["embedding_id"] for r in results]
        assert len(set(embedding_ids)) == 10

    @pytest.mark.asyncio
    async def test_idempotency(self, mock_envelope, mock_enriched, mock_context, test_embedding):
        """Test module is idempotent (same input -> same type of output)."""
        mock_result = Mock()
        mock_result.embedding = test_embedding

        with patch(
            "k0.modules.embedding.extract_from_cache._get_full_analysis_result",
            return_value=mock_result,
        ):
            result1 = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)
            result2 = await extract_from_cache.run(mock_envelope, mock_enriched, mock_context)

        # Same output structure and type
        assert result1["source"] == result2["source"] == "cache_hit"
        assert result1["embedding"] == result2["embedding"]
        assert result1["vector_dim"] == result2["vector_dim"]
        assert result1["model_id"] == result2["model_id"]
        # UUIDs are different (expected for unique identifiers)
        assert result1["embedding_id"] != result2["embedding_id"]
