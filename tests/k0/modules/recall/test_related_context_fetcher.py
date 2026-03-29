"""
Unit Tests for GAP-001 Milestone 5: Related Context Fetcher

Tests for RelatedContextFetcher component:
- Fetching related records from each truth layer
- Entity matching via different column types
- Result aggregation

Test Coverage:
- Fetch episodes (participants_json containment)
- Fetch patterns (actor_id matching)
- Fetch routines (actor_id matching)
- Fetch relationships (actor_a_id OR actor_b_id)
- Fetch intentions (actor_id + status filter)

GAP Reference: GAP_001 Section 6 (Rich LLM Context)
Milestone Reference: GAP_001_MILESTONE_5_CONTEXT_EXPANDER (Issue 5.3)
"""

from unittest.mock import AsyncMock

import pytest

from k0.modules.recall.related_context_fetcher import (
    RelatedContext,
    RelatedContextFetcher,
)


class TestRelatedContext:
    """Tests for RelatedContext dataclass."""

    def test_create_empty_context(self):
        """Test creating empty RelatedContext."""
        context = RelatedContext()
        assert len(context.episodes) == 0
        assert len(context.patterns) == 0
        assert len(context.routines) == 0
        assert len(context.relationships) == 0
        assert len(context.intentions) == 0
        assert context.total_records == 0

    def test_create_with_records(self):
        """Test creating RelatedContext with data."""
        context = RelatedContext(
            episodes=[{"episode_id": "epi_1"}],
            patterns=[{"pattern_id": "sem_1"}, {"pattern_id": "sem_2"}],
            relationships=[{"relationship_id": "rel_1"}],
        )
        assert len(context.episodes) == 1
        assert len(context.patterns) == 2
        assert len(context.relationships) == 1
        assert context.total_records == 4

    def test_to_dict(self):
        """Test converting RelatedContext to dictionary."""
        context = RelatedContext(
            episodes=[{"episode_id": "epi_1"}],
            patterns=[{"pattern_id": "sem_1"}],
        )
        result = context.to_dict()

        assert "related_episodes" in result
        assert "actor_patterns" in result
        assert "routines" in result
        assert "relationships" in result
        assert "active_intentions" in result
        assert len(result["related_episodes"]) == 1

    def test_summary(self):
        """Test RelatedContext summary."""
        context = RelatedContext(
            episodes=[{"episode_id": "epi_1"}],
            patterns=[{"pattern_id": "sem_1"}, {"pattern_id": "sem_2"}],
        )
        summary = context.summary()

        assert summary["episodes"] == 1
        assert summary["patterns"] == 2
        assert summary["total"] == 3


class TestRelatedContextFetcher:
    """Tests for RelatedContextFetcher."""

    def test_init_default_config(self):
        """Test RelatedContextFetcher initialization with defaults."""
        fetcher = RelatedContextFetcher()
        assert fetcher.max_per_layer == 10
        assert fetcher.recency_days == 30

    def test_init_custom_config(self):
        """Test RelatedContextFetcher initialization with custom config."""
        fetcher = RelatedContextFetcher(max_per_layer=5, recency_days=7)
        assert fetcher.max_per_layer == 5
        assert fetcher.recency_days == 7

    # =========================================================================
    # _fetch_episodes Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fetch_episodes_success(self):
        """Test fetching related episodes."""
        fetcher = RelatedContextFetcher()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {
                "episode_id": "epi_1",
                "embedding_text": "Family dinner",
                "participants_json": ["Mom", "Dad"],
                "started_at": None,
                "ended_at": None,
                "primary_location": "Home",
                "confidence": 0.9,
                "source_texts_json": None,
            },
        ]

        episodes = await fetcher._fetch_episodes(["Mom", "Dad"], mock_conn, None, set())

        assert len(episodes) == 1
        assert episodes[0]["episode_id"] == "epi_1"

    @pytest.mark.asyncio
    async def test_fetch_episodes_excludes_ids(self):
        """Test that excluded IDs are filtered out."""
        fetcher = RelatedContextFetcher()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {"episode_id": "epi_1", "embedding_text": "Event 1"},
            {"episode_id": "epi_2", "embedding_text": "Event 2"},
        ]

        episodes = await fetcher._fetch_episodes(
            ["Mom"], mock_conn, None, {"epi_1"}  # Exclude epi_1
        )

        # Only epi_2 should be returned
        assert len(episodes) == 1
        assert episodes[0]["episode_id"] == "epi_2"

    # =========================================================================
    # _fetch_patterns Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fetch_patterns_success(self):
        """Test fetching semantic patterns."""
        fetcher = RelatedContextFetcher()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {
                "pattern_id": "sem_1",
                "pattern_type": "PREFERENCE",
                "pattern_name": "Likes coffee",
                "embedding_text": "Prefers dark roast coffee",
                "actor_id": "Mom",
                "observation_count": 5,
                "confidence": 0.85,
                "source_texts_json": None,
            },
        ]

        patterns = await fetcher._fetch_patterns(["Mom"], mock_conn, None, set())

        assert len(patterns) == 1
        assert patterns[0]["pattern_id"] == "sem_1"

    # =========================================================================
    # _fetch_routines Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fetch_routines_success(self):
        """Test fetching procedural routines."""
        fetcher = RelatedContextFetcher()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {
                "routine_id": "proc_1",
                "routine_name": "Morning coffee",
                "embedding_text": "Makes coffee at 7am",
                "actor_id": "Dad",
                "execution_count": 30,
                "source_texts_json": None,
            },
        ]

        routines = await fetcher._fetch_routines(["Dad"], mock_conn, None, set())

        assert len(routines) == 1
        assert routines[0]["routine_id"] == "proc_1"

    # =========================================================================
    # _fetch_relationships Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fetch_relationships_success(self):
        """Test fetching social relationships."""
        fetcher = RelatedContextFetcher()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {
                "relationship_id": "rel_1",
                "actor_a_id": "Mom",
                "actor_b_id": "Dad",
                "relationship_type": "SPOUSE",
                "embedding_text": "Married couple",
                "strength": 0.95,
                "source_texts_json": None,
            },
        ]

        relationships = await fetcher._fetch_relationships(["Mom"], mock_conn, None, set())

        assert len(relationships) == 1
        assert relationships[0]["relationship_id"] == "rel_1"

    # =========================================================================
    # _fetch_intentions Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fetch_intentions_success(self):
        """Test fetching active intentions."""
        fetcher = RelatedContextFetcher()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {
                "intention_id": "int_1",
                "intention_description": "Plan vacation",
                "embedding_text": "Planning summer vacation",
                "actor_id": "Mom",
                "status": "ACTIVE",
                "target_date": None,
                "source_texts_json": None,
            },
        ]

        intentions = await fetcher._fetch_intentions(["Mom"], mock_conn, None, set())

        assert len(intentions) == 1
        assert intentions[0]["intention_id"] == "int_1"

    # =========================================================================
    # fetch Tests (Integration)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fetch_all_layers(self):
        """Test fetching from all layers at once."""
        fetcher = RelatedContextFetcher(max_per_layer=5)

        mock_conn = AsyncMock()

        # Configure mock to return different data for each layer
        mock_conn.fetch.side_effect = [
            # Episodes
            [{"episode_id": "epi_1", "embedding_text": "Family dinner"}],
            # Patterns
            [{"pattern_id": "sem_1", "embedding_text": "Coffee preference"}],
            # Routines
            [{"routine_id": "proc_1", "embedding_text": "Morning routine"}],
            # Relationships
            [{"relationship_id": "rel_1", "embedding_text": "Spouse relationship"}],
            # Intentions
            [{"intention_id": "int_1", "embedding_text": "Vacation plan"}],
        ]

        context = await fetcher.fetch({"Mom", "Dad"}, mock_conn)

        assert context.total_records == 5
        assert len(context.episodes) == 1
        assert len(context.patterns) == 1
        assert len(context.routines) == 1
        assert len(context.relationships) == 1
        assert len(context.intentions) == 1

    @pytest.mark.asyncio
    async def test_fetch_empty_entities(self):
        """Test fetching with empty entity set."""
        fetcher = RelatedContextFetcher()
        mock_conn = AsyncMock()

        context = await fetcher.fetch(set(), mock_conn)

        assert context.total_records == 0
        # fetch should not call any queries
        mock_conn.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_handles_query_errors(self):
        """Test that fetch handles query errors gracefully."""
        fetcher = RelatedContextFetcher()

        mock_conn = AsyncMock()
        mock_conn.fetch.side_effect = Exception("Database error")

        context = await fetcher.fetch({"Mom"}, mock_conn)

        # Should return empty context on error
        assert context.total_records == 0

    @pytest.mark.asyncio
    async def test_fetch_with_tenant_filter(self):
        """Test fetching with tenant filter."""
        fetcher = RelatedContextFetcher()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []

        await fetcher.fetch({"Mom"}, mock_conn, tenant_id="tenant_123")

        # Verify tenant_id was passed to queries
        # (checking that queries were called)
        assert mock_conn.fetch.called
