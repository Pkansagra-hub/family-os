"""
Unit Tests for GAP-001 Milestone 5: Entity Graph Expander

Tests for EntityGraphExpander component:
- Graph traversal via st_kg_edges
- Entity fetching from st_kg_dom
- Edge weight filtering
- Hop distance tracking

Test Coverage:
- Single entity expansion
- Multiple entity expansion
- Edge weight threshold filtering
- Max neighbors limiting
- Empty entity set handling

GAP Reference: GAP_001 Section 6 (Rich LLM Context)
Milestone Reference: GAP_001_MILESTONE_5_CONTEXT_EXPANDER (Issue 5.2)
"""

from unittest.mock import AsyncMock

import pytest

from k0.modules.recall.entity_graph_expander import (
    EntityGraphExpander,
    ExpandedEntity,
    ExpansionResult,
)


class TestExpandedEntity:
    """Tests for ExpandedEntity dataclass."""

    def test_create_expanded_entity(self):
        """Test creating ExpandedEntity with all fields."""
        entity = ExpandedEntity(
            entity_id="Dad",
            canonical_name="Dad",
            entity_type="PERSON",
            hop_distance=1,
            via_edge_type="SPOUSE",
            edge_weight=0.9,
        )
        assert entity.entity_id == "Dad"
        assert entity.canonical_name == "Dad"
        assert entity.entity_type == "PERSON"
        assert entity.hop_distance == 1
        assert entity.via_edge_type == "SPOUSE"
        assert entity.edge_weight == 0.9

    def test_to_dict(self):
        """Test converting ExpandedEntity to dict."""
        entity = ExpandedEntity(
            entity_id="Mom",
            canonical_name="Mom",
            hop_distance=0,
        )
        d = entity.to_dict()
        assert d["entity_id"] == "Mom"
        assert d["hop_distance"] == 0


class TestExpansionResult:
    """Tests for ExpansionResult dataclass."""

    def test_create_empty_result(self):
        """Test creating empty ExpansionResult."""
        result = ExpansionResult()
        assert len(result.entities) == 0
        assert result.seed_count == 0
        assert result.expanded_count == 0

    def test_create_with_entities(self):
        """Test creating ExpansionResult with data."""
        entity = ExpandedEntity(
            entity_id="Dad",
            canonical_name="Dad",
            entity_type="PERSON",
            hop_distance=1,
        )
        result = ExpansionResult(
            entities=[entity],
            seed_count=1,
            expanded_count=1,
        )
        assert len(result.entities) == 1
        assert result.seed_count == 1

    def test_get_all_entity_ids(self):
        """Test getting all entity IDs."""
        result = ExpansionResult(
            entities=[
                ExpandedEntity(entity_id="Mom", canonical_name="Mom", hop_distance=0),
                ExpandedEntity(entity_id="Dad", canonical_name="Dad", hop_distance=1),
            ]
        )
        ids = result.get_all_entity_ids()
        assert ids == {"Mom", "Dad"}

    def test_get_seed_ids(self):
        """Test getting only seed entity IDs."""
        result = ExpansionResult(
            entities=[
                ExpandedEntity(entity_id="Mom", canonical_name="Mom", hop_distance=0),
                ExpandedEntity(entity_id="Dad", canonical_name="Dad", hop_distance=1),
            ]
        )
        ids = result.get_seed_ids()
        assert ids == {"Mom"}

    def test_get_neighbor_ids(self):
        """Test getting only neighbor entity IDs."""
        result = ExpansionResult(
            entities=[
                ExpandedEntity(entity_id="Mom", canonical_name="Mom", hop_distance=0),
                ExpandedEntity(entity_id="Dad", canonical_name="Dad", hop_distance=1),
            ]
        )
        ids = result.get_neighbor_ids()
        assert ids == {"Dad"}


class TestEntityGraphExpander:
    """Tests for EntityGraphExpander."""

    def test_init_default_config(self):
        """Test EntityGraphExpander initialization with defaults."""
        expander = EntityGraphExpander()
        assert expander.max_hops == 1
        assert expander.min_edge_weight == 0.5
        assert expander.max_neighbors == 20

    def test_init_custom_config(self):
        """Test EntityGraphExpander initialization with custom config."""
        expander = EntityGraphExpander(
            max_hops=2,
            min_edge_weight=0.7,
            max_neighbors=10,
        )
        assert expander.max_hops == 2
        assert expander.min_edge_weight == 0.7
        assert expander.max_neighbors == 10

    # =========================================================================
    # _fetch_entities Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fetch_entities_success(self):
        """Test fetching entities from st_kg_dom."""
        expander = EntityGraphExpander()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {"entity_id": "Mom", "canonical_name": "Mom", "entity_type": "PERSON"},
            {"entity_id": "Dad", "canonical_name": "Dad", "entity_type": "PERSON"},
        ]

        entities = await expander._fetch_entities(["Mom", "Dad"], mock_conn, None)

        assert len(entities) == 2
        assert entities[0]["entity_id"] == "Mom"
        assert entities[1]["entity_id"] == "Dad"

    @pytest.mark.asyncio
    async def test_fetch_entities_empty_list(self):
        """Test fetching with empty entity list."""
        expander = EntityGraphExpander()
        mock_conn = AsyncMock()

        entities = await expander._fetch_entities([], mock_conn, None)
        assert entities == []

    # =========================================================================
    # _find_neighbors Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_find_neighbors_success(self):
        """Test finding neighbors via st_kg_edges."""
        expander = EntityGraphExpander(min_edge_weight=0.5)

        mock_conn = AsyncMock()

        # First call: edge query returns neighbors
        # Second call: fetch neighbor entities
        mock_conn.fetch.side_effect = [
            # Edge query results
            [
                {"edge_type": "SPOUSE", "edge_weight": 0.95, "neighbor_id": "Dad"},
                {"edge_type": "PARENT", "edge_weight": 0.9, "neighbor_id": "Child"},
            ],
            # Entity fetch for neighbors
            [
                {"entity_id": "Dad", "canonical_name": "Dad", "entity_type": "PERSON"},
                {"entity_id": "Child", "canonical_name": "Child", "entity_type": "PERSON"},
            ],
        ]

        neighbors, edge_types = await expander._find_neighbors({"Mom"}, mock_conn, None)

        assert len(neighbors) == 2
        assert "SPOUSE" in edge_types
        assert "PARENT" in edge_types

    @pytest.mark.asyncio
    async def test_find_neighbors_empty_seeds(self):
        """Test finding neighbors with empty seed set."""
        expander = EntityGraphExpander()
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []

        neighbors, edge_types = await expander._find_neighbors(set(), mock_conn, None)

        # Empty seeds should return empty results
        assert len(neighbors) == 0

    # =========================================================================
    # expand Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_expand_single_hop(self):
        """Test single-hop expansion from seed entities."""
        expander = EntityGraphExpander(max_hops=1)

        mock_conn = AsyncMock()

        mock_conn.fetch.side_effect = [
            # _fetch_entities for seeds
            [{"entity_id": "Mom", "canonical_name": "Mom", "entity_type": "PERSON"}],
            # _find_neighbors edge query
            [{"edge_type": "SPOUSE", "edge_weight": 0.9, "neighbor_id": "Dad"}],
            # _fetch_entities for neighbors
            [{"entity_id": "Dad", "canonical_name": "Dad", "entity_type": "PERSON"}],
        ]

        result = await expander.expand({"Mom"}, mock_conn)

        assert result.seed_count == 1
        assert result.expanded_count == 1
        assert len(result.entities) == 2  # Mom + Dad
        assert result.get_seed_ids() == {"Mom"}
        assert result.get_neighbor_ids() == {"Dad"}

    @pytest.mark.asyncio
    async def test_expand_empty_seeds(self):
        """Test expansion with empty seed set."""
        expander = EntityGraphExpander()
        mock_conn = AsyncMock()

        result = await expander.expand(set(), mock_conn)

        assert len(result.entities) == 0
        assert result.seed_count == 0
        assert result.expanded_count == 0

    @pytest.mark.asyncio
    async def test_expand_no_neighbors(self):
        """Test expansion when entity has no neighbors."""
        expander = EntityGraphExpander()

        mock_conn = AsyncMock()
        mock_conn.fetch.side_effect = [
            # _fetch_entities for seeds
            [{"entity_id": "Isolated", "canonical_name": "Isolated", "entity_type": "PERSON"}],
            # _find_neighbors edge query returns empty
            [],
        ]

        result = await expander.expand({"Isolated"}, mock_conn)

        assert result.seed_count == 1
        assert result.expanded_count == 0
        assert result.get_seed_ids() == {"Isolated"}
