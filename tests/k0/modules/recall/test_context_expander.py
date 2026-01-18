"""
Unit Tests for GAP-001 Milestone 5: Context Expander

Tests for ContextExpander orchestrator:
- Full context expansion flow
- Integration of all sub-components
- LLM context formatting

Test Coverage:
- expand() with vector search
- expand_from_records() with pre-fetched data
- to_llm_context() formatting
- Timing metrics collection

GAP Reference: GAP_001 Section 6 (Rich LLM Context)
Milestone Reference: GAP_001_MILESTONE_5_CONTEXT_EXPANDER (Issue 5.4)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.embedding.union_index_searcher import SearchResult
from k0.modules.recall.context_expander import ContextExpander, ExpandedContext
from k0.modules.recall.related_context_fetcher import RelatedContext


class TestExpandedContext:
    """Tests for ExpandedContext dataclass."""

    def test_create_empty_context(self):
        """Test creating empty ExpandedContext."""
        context = ExpandedContext(query="test query")
        assert context.query == "test query"
        assert len(context.direct_results) == 0
        assert len(context.expanded_entities) == 0
        assert context.related_context is None

    def test_create_with_data(self):
        """Test creating ExpandedContext with full data."""
        results = [
            SearchResult(
                layer="st_epi",
                record_id="epi_1",
                score=0.95,
                tenant_id="t1",
                space_id="s1",
            )
        ]
        related = RelatedContext(
            episodes=[{"episode_id": "epi_2"}],
        )
        context = ExpandedContext(
            query="Where did Mom go?",
            direct_results=results,
            expanded_entities={"Mom", "Dad"},
            related_context=related,
            timing_ms={"total_ms": 50.0},
        )
        assert len(context.direct_results) == 1
        assert "Mom" in context.expanded_entities
        assert context.related_context is not None
        assert context.related_context.total_records == 1

    def test_to_llm_context(self):
        """Test converting ExpandedContext to LLM format."""
        results = [
            SearchResult(
                layer="st_epi",
                record_id="epi_1",
                score=0.95,
                tenant_id="t1",
                space_id="s1",
            )
        ]
        related = RelatedContext(
            episodes=[{"episode_id": "epi_2"}],
            patterns=[{"pattern_id": "sem_1"}],
        )
        context = ExpandedContext(
            query="Where did Mom go?",
            direct_results=results,
            expanded_entities={"Mom"},
            related_context=related,
        )

        llm_context = context.to_llm_context()

        assert llm_context["query"] == "Where did Mom go?"
        assert llm_context["match_count"] == 1
        assert len(llm_context["direct_matches"]) == 1
        assert llm_context["related_count"] == 2
        assert "related_episodes" in llm_context
        assert "actor_patterns" in llm_context

    def test_summary(self):
        """Test ExpandedContext summary."""
        related = RelatedContext(
            episodes=[{"episode_id": "epi_1"}],
        )
        context = ExpandedContext(
            query="test",
            direct_results=[
                SearchResult(
                    layer="st_epi", record_id="epi_1", score=0.9, tenant_id="t1", space_id="s1"
                )
            ],
            expanded_entities={"Mom", "Dad"},
            related_context=related,
            timing_ms={"total_ms": 75.0},
        )

        summary = context.summary()

        assert summary["query_len"] == 4
        assert summary["direct_results"] == 1
        assert summary["expanded_entities"] == 2
        assert summary["related_records"] == 1


class TestContextExpander:
    """Tests for ContextExpander orchestrator."""

    def test_init_default_config(self):
        """Test ContextExpander initialization with defaults."""
        expander = ContextExpander()
        assert expander.top_k == 10
        assert expander.max_hops == 1
        assert expander.min_edge_weight == 0.5
        assert expander.max_per_layer == 10

    def test_init_custom_config(self):
        """Test ContextExpander initialization with custom config."""
        expander = ContextExpander(
            top_k=5,
            max_hops=2,
            min_edge_weight=0.7,
            max_per_layer=15,
        )
        assert expander.top_k == 5
        assert expander.max_hops == 2
        assert expander.min_edge_weight == 0.7
        assert expander.max_per_layer == 15

    # =========================================================================
    # expand Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_expand_no_searcher(self):
        """Test expand returns empty context when no searcher provided."""
        expander = ContextExpander()
        mock_conn = AsyncMock()

        result = await expander.expand(
            query="Test query",
            embedding=[0.1] * 768,
            conn=mock_conn,
            searcher=None,  # No searcher
        )

        assert result.query == "Test query"
        assert len(result.direct_results) == 0

    @pytest.mark.asyncio
    async def test_expand_with_empty_results(self):
        """Test expansion with no vector search results."""
        expander = ContextExpander()

        # Mock searcher that returns empty results
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = []

        mock_conn = AsyncMock()

        result = await expander.expand(
            query="Unknown topic",
            embedding=[0.1] * 768,
            conn=mock_conn,
            searcher=mock_searcher,
        )

        assert len(result.direct_results) == 0
        assert "total_ms" in result.timing_ms

    # =========================================================================
    # expand_from_records Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_expand_from_records(self):
        """Test expansion from pre-fetched records."""
        expander = ContextExpander()

        records = [
            {
                "layer": "st_epi",
                "id": "epi_1",
                "score": 0.95,
                "participants_json": ["Mom"],
                "tenant_id": "t1",
                "space_id": "s1",
            }
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch.side_effect = [
            # Entity fetch for seeds
            [{"entity_id": "Mom", "entity_type": "PERSON", "display_name": "Mom"}],
            # Neighbors search
            [],
            # Related context (5 layers)
            [],
            [],
            [],
            [],
            [],
        ]

        result = await expander.expand_from_records(
            query="Pre-fetched query",
            records=records,
            conn=mock_conn,
        )

        assert result.query == "Pre-fetched query"
        assert len(result.direct_results) == 1
        assert "entity_extraction_ms" in result.timing_ms

    @pytest.mark.asyncio
    async def test_expand_from_records_empty(self):
        """Test expansion from empty records list."""
        expander = ContextExpander()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []

        result = await expander.expand_from_records(
            query="Empty",
            records=[],
            conn=mock_conn,
        )

        assert len(result.direct_results) == 0
