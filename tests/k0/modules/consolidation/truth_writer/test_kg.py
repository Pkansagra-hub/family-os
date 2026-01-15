"""
Tests for KGLayerWriter — Issue 5.2.8

Tests for st_kg_dom (entities) and st_kg_edges (edges) layer write operations.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.truth_writer.layers.kg import (
    EdgeWriteData,
    EntityAction,
    EntityWriteData,
    KGLayerWriter,
    create_kg_writer,
)
from k0.pipelines.p03.staged_writes import LAYER_ST_KG_DOM, LAYER_ST_KG_EDGES, StagedWrite

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_uow():
    """Create mock UnitOfWork with async connection."""
    uow = MagicMock()
    uow.connection = AsyncMock()
    uow.connection.execute = AsyncMock(return_value="INSERT 0 1")
    return uow


@pytest.fixture
def kg_writer():
    """Create a KGLayerWriter."""
    return KGLayerWriter()


# ─────────────────────────────────────────────────────────────────
# Entity Fixtures
# ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_entity_insert():
    """Create a sample INSERT StagedWrite for st_kg_dom."""
    return StagedWrite.insert(
        layer=LAYER_ST_KG_DOM,
        record_id="entity_001",
        data={
            "entity_id": "entity_001",
            "tenant_id": "tenant_abc",
            "space_id": "space_xyz",
            "entity_type": "PERSON",
            "canonical_name": "Alice Smith",
            "attributes_json": '{"age": 30, "occupation": "engineer"}',
            "embedding": b"\x00\x01\x02\x03",
            "confidence": 0.95,
            "valid_from_ms": 1700000000000,
            "source_events_json": '["ev_001", "ev_002"]',
        },
        phase="R4",
    )


@pytest.fixture
def sample_entity_extend():
    """Create a sample EXTEND UPDATE StagedWrite for st_kg_dom."""
    return StagedWrite.update(
        layer=LAYER_ST_KG_DOM,
        record_id="entity_001",
        data={
            "_action": EntityAction.EXTEND,
            "new_attributes_json": '{"city": "NYC"}',
            "new_events_json": '["ev_003"]',
        },
        phase="R4",
        expected_version=1,
    )


@pytest.fixture
def sample_entity_evolve():
    """Create a sample EVOLVE UPDATE StagedWrite for st_kg_dom."""
    return StagedWrite.update(
        layer=LAYER_ST_KG_DOM,
        record_id="entity_001",
        data={
            "_action": EntityAction.EVOLVE,
        },
        phase="R4",
        expected_version=1,
    )


@pytest.fixture
def sample_entity_archive():
    """Create a sample ARCHIVE StagedWrite for st_kg_dom."""
    return StagedWrite.archive(
        layer=LAYER_ST_KG_DOM,
        record_id="entity_001",
        reason="low_confidence",
        phase="R6",
    )


@pytest.fixture
def sample_entity_tombstone():
    """Create a sample TOMBSTONE StagedWrite for st_kg_dom."""
    return StagedWrite.tombstone(
        layer=LAYER_ST_KG_DOM,
        record_id="entity_001",
        phase="R6",
    )


# ─────────────────────────────────────────────────────────────────
# Edge Fixtures
# ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_edge_insert():
    """Create a sample INSERT StagedWrite for st_kg_edges."""
    return StagedWrite.insert(
        layer=LAYER_ST_KG_EDGES,
        record_id="edge_001",
        data={
            "edge_id": "edge_001",
            "tenant_id": "tenant_abc",
            "space_id": "space_xyz",
            "source_entity_id": "entity_001",
            "target_entity_id": "entity_002",
            "relation_type": "KNOWS",
            "confidence": 0.9,
            "valid_from_ms": 1700000000000,
            "attributes_json": '{"since": "2020"}',
        },
        phase="R4",
    )


@pytest.fixture
def sample_causes_edge():
    """Create a sample CAUSES edge with precedence_ratio."""
    return StagedWrite.insert(
        layer=LAYER_ST_KG_EDGES,
        record_id="edge_causes_001",
        data={
            "edge_id": "edge_causes_001",
            "tenant_id": "tenant_abc",
            "space_id": "space_xyz",
            "source_entity_id": "entity_001",
            "target_entity_id": "entity_002",
            "relation_type": "CAUSES",
            "confidence": 0.85,
            "precedence_ratio": 0.72,  # Granger causality
            "attributes_json": '{"lag_ms": 5000}',
        },
        phase="R4",
    )


@pytest.fixture
def sample_edge_update():
    """Create a sample UPDATE StagedWrite for st_kg_edges."""
    return StagedWrite.update(
        layer=LAYER_ST_KG_EDGES,
        record_id="edge_001",
        data={
            "confidence": 0.95,
            "new_attributes_json": '{"verified": true}',
        },
        phase="R4",
        expected_version=1,
    )


@pytest.fixture
def sample_edge_archive():
    """Create a sample ARCHIVE StagedWrite for st_kg_edges."""
    return StagedWrite.archive(
        layer=LAYER_ST_KG_EDGES,
        record_id="edge_001",
        reason="low_confidence",
        phase="R6",
    )


@pytest.fixture
def sample_edge_tombstone():
    """Create a sample TOMBSTONE StagedWrite for st_kg_edges."""
    return StagedWrite.tombstone(
        layer=LAYER_ST_KG_EDGES,
        record_id="edge_001",
        phase="R6",
    )


# ============================================================================
# Factory Tests
# ============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_kg_writer_returns_instance(self):
        """Factory should return a KGLayerWriter instance."""
        writer = create_kg_writer()
        assert isinstance(writer, KGLayerWriter)

    def test_layers_property(self, kg_writer):
        """Layers property should return both layer names."""
        assert kg_writer.layers == (LAYER_ST_KG_DOM, LAYER_ST_KG_EDGES)

    def test_constants_defined(self, kg_writer):
        """Writer constants should be defined."""
        assert kg_writer.EXTEND_BOOST == 1.1


# ============================================================================
# EntityWriteData Tests
# ============================================================================


class TestEntityWriteData:
    """Tests for EntityWriteData dataclass."""

    def test_create_with_all_fields(self):
        """Should create with all fields."""
        data = EntityWriteData(
            entity_id="entity_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
            entity_type="PERSON",
            canonical_name="Alice Smith",
            attributes_json='{"key": "value"}',
            embedding=b"\x00\x01\x02",
            confidence=0.9,
            valid_from_ms=1700000000000,
            valid_to_ms=1800000000000,
            source_events_json='["ev_001"]',
        )
        assert data.entity_id == "entity_001"
        assert data.entity_type == "PERSON"
        assert data.embedding is not None
        assert data.valid_to_ms is not None

    def test_create_with_defaults(self):
        """Should create with default values."""
        data = EntityWriteData(
            entity_id="entity_002",
            tenant_id="tenant_abc",
            space_id="space_xyz",
        )
        assert data.entity_type == "UNKNOWN"
        assert data.canonical_name == ""
        assert data.attributes_json == "{}"
        assert data.embedding is None
        assert data.confidence == 1.0
        assert data.valid_to_ms is None
        assert data.source_events_json == "[]"


# ============================================================================
# EdgeWriteData Tests
# ============================================================================


class TestEdgeWriteData:
    """Tests for EdgeWriteData dataclass."""

    def test_create_with_all_fields(self):
        """Should create with all fields."""
        data = EdgeWriteData(
            edge_id="edge_001",
            tenant_id="tenant_abc",
            space_id="space_xyz",
            source_entity_id="entity_001",
            target_entity_id="entity_002",
            relation_type="KNOWS",
            confidence=0.9,
            valid_from_ms=1700000000000,
            valid_to_ms=1800000000000,
            precedence_ratio=0.72,
            attributes_json='{"since": "2020"}',
        )
        assert data.edge_id == "edge_001"
        assert data.source_entity_id == "entity_001"
        assert data.target_entity_id == "entity_002"
        assert data.precedence_ratio == 0.72

    def test_create_with_defaults(self):
        """Should create with default values."""
        data = EdgeWriteData(
            edge_id="edge_002",
            tenant_id="tenant_abc",
            space_id="space_xyz",
            source_entity_id="entity_001",
            target_entity_id="entity_002",
        )
        assert data.relation_type == "RELATED_TO"
        assert data.confidence == 1.0
        assert data.valid_to_ms is None
        assert data.precedence_ratio is None
        assert data.attributes_json == "{}"


# ============================================================================
# EntityAction Tests
# ============================================================================


class TestEntityAction:
    """Tests for EntityAction enum."""

    def test_extend_action(self):
        """EXTEND action should have correct value."""
        assert EntityAction.EXTEND == "EXTEND"
        assert EntityAction.EXTEND.value == "EXTEND"

    def test_evolve_action(self):
        """EVOLVE action should have correct value."""
        assert EntityAction.EVOLVE == "EVOLVE"
        assert EntityAction.EVOLVE.value == "EVOLVE"


# ============================================================================
# Entity INSERT Tests
# ============================================================================


class TestEntityInsert:
    """Tests for entity INSERT operation."""

    @pytest.mark.asyncio
    async def test_insert_entity(self, kg_writer, mock_uow, sample_entity_insert):
        """Should insert new entity."""
        result = await kg_writer.write([sample_entity_insert], mock_uow)

        assert result.writes_attempted == 1
        assert result.writes_succeeded == 1
        assert result.writes_failed == 0
        assert result.layer == "kg"
        mock_uow.connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_entity_with_embedding(self, kg_writer, mock_uow):
        """Should insert entity with binary embedding."""
        write = StagedWrite.insert(
            layer=LAYER_ST_KG_DOM,
            record_id="entity_emb",
            data={
                "entity_id": "entity_emb",
                "tenant_id": "tenant",
                "space_id": "space",
                "embedding": b"\x00\x01\x02\x03\x04\x05",
            },
            phase="R4",
        )

        result = await kg_writer.write([write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        # Embedding should be passed as bytes
        assert b"\x00\x01\x02\x03\x04\x05" in call_args[0]

    @pytest.mark.asyncio
    async def test_insert_entity_minimal(self, kg_writer, mock_uow):
        """Should insert with minimal required fields."""
        write = StagedWrite.insert(
            layer=LAYER_ST_KG_DOM,
            record_id="entity_min",
            data={
                "entity_id": "entity_min",
                "tenant_id": "tenant",
                "space_id": "space",
            },
            phase="R4",
        )

        result = await kg_writer.write([write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        assert "ON CONFLICT (entity_id) DO NOTHING" in call_args[0][0]


# ============================================================================
# Entity UPDATE Tests
# ============================================================================


class TestEntityUpdate:
    """Tests for entity UPDATE operation."""

    @pytest.mark.asyncio
    async def test_update_entity_extend(self, kg_writer, mock_uow, sample_entity_extend):
        """Should extend entity with new attributes."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        result = await kg_writer.write([sample_entity_extend], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "attributes_json || " in sql
        assert "source_events_json || " in sql
        assert "LEAST(confidence *" in sql  # Confidence boost

    @pytest.mark.asyncio
    async def test_update_entity_evolve(self, kg_writer, mock_uow, sample_entity_evolve):
        """Should mark entity as superseded (set valid_to)."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        result = await kg_writer.write([sample_entity_evolve], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "valid_to = $1" in sql

    @pytest.mark.asyncio
    async def test_update_entity_version_conflict(self, kg_writer, mock_uow, sample_entity_extend):
        """Should fail on version conflict."""
        mock_uow.connection.execute.return_value = "UPDATE 0"

        result = await kg_writer.write([sample_entity_extend], mock_uow)

        assert result.writes_succeeded == 0
        assert result.writes_failed == 1
        assert "entity_001" in result.failed_ids

    @pytest.mark.asyncio
    async def test_update_entity_default_action(self, kg_writer, mock_uow):
        """Should default to EXTEND for unknown action."""
        write = StagedWrite.update(
            layer=LAYER_ST_KG_DOM,
            record_id="entity_001",
            data={
                "_action": "UNKNOWN",
                "new_attributes_json": '{"x": 1}',
            },
            phase="R4",
            expected_version=1,
        )
        mock_uow.connection.execute.return_value = "UPDATE 1"

        result = await kg_writer.write([write], mock_uow)

        assert result.writes_succeeded == 1


# ============================================================================
# Entity ARCHIVE Tests
# ============================================================================


class TestEntityArchive:
    """Tests for entity ARCHIVE operation."""

    @pytest.mark.asyncio
    async def test_archive_entity(self, kg_writer, mock_uow, sample_entity_archive):
        """Should archive entity."""
        result = await kg_writer.write([sample_entity_archive], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "archival_status = 'ARCHIVED'" in sql
        assert "archived_reason = $2" in sql


# ============================================================================
# Entity TOMBSTONE Tests
# ============================================================================


class TestEntityTombstone:
    """Tests for entity TOMBSTONE operation."""

    @pytest.mark.asyncio
    async def test_tombstone_entity(self, kg_writer, mock_uow, sample_entity_tombstone):
        """Should tombstone entity for GDPR deletion."""
        result = await kg_writer.write([sample_entity_tombstone], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "canonical_name = ''" in sql
        assert "attributes_json = '{}'" in sql
        assert "embedding = NULL" in sql
        assert "source_events_json = '[]'" in sql
        assert "archival_status = 'TOMBSTONE'" in sql
        assert "gdpr_deletion" in sql


# ============================================================================
# Edge INSERT Tests
# ============================================================================


class TestEdgeInsert:
    """Tests for edge INSERT operation."""

    @pytest.mark.asyncio
    async def test_insert_edge(self, kg_writer, mock_uow, sample_edge_insert):
        """Should insert new edge."""
        result = await kg_writer.write([sample_edge_insert], mock_uow)

        assert result.writes_attempted == 1
        assert result.writes_succeeded == 1
        assert result.layer == "kg"
        mock_uow.connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_causes_edge_with_precedence(
        self, kg_writer, mock_uow, sample_causes_edge
    ):
        """Should insert CAUSES edge with precedence_ratio."""
        result = await kg_writer.write([sample_causes_edge], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        # precedence_ratio should be passed
        args = call_args[0]
        assert 0.72 in args  # precedence_ratio value

    @pytest.mark.asyncio
    async def test_insert_edge_minimal(self, kg_writer, mock_uow):
        """Should insert with minimal required fields."""
        write = StagedWrite.insert(
            layer=LAYER_ST_KG_EDGES,
            record_id="edge_min",
            data={
                "edge_id": "edge_min",
                "tenant_id": "tenant",
                "space_id": "space",
                "source_entity_id": "e1",
                "target_entity_id": "e2",
            },
            phase="R4",
        )

        result = await kg_writer.write([write], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        assert "ON CONFLICT (edge_id) DO NOTHING" in call_args[0][0]


# ============================================================================
# Edge UPDATE Tests
# ============================================================================


class TestEdgeUpdate:
    """Tests for edge UPDATE operation."""

    @pytest.mark.asyncio
    async def test_update_edge(self, kg_writer, mock_uow, sample_edge_update):
        """Should update edge confidence/attributes."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        result = await kg_writer.write([sample_edge_update], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "confidence = COALESCE($1, confidence)" in sql
        assert "attributes_json || " in sql

    @pytest.mark.asyncio
    async def test_update_edge_version_conflict(self, kg_writer, mock_uow, sample_edge_update):
        """Should fail on version conflict."""
        mock_uow.connection.execute.return_value = "UPDATE 0"

        result = await kg_writer.write([sample_edge_update], mock_uow)

        assert result.writes_succeeded == 0
        assert result.writes_failed == 1
        assert "edge_001" in result.failed_ids


# ============================================================================
# Edge ARCHIVE Tests
# ============================================================================


class TestEdgeArchive:
    """Tests for edge ARCHIVE operation."""

    @pytest.mark.asyncio
    async def test_archive_edge(self, kg_writer, mock_uow, sample_edge_archive):
        """Should archive edge."""
        result = await kg_writer.write([sample_edge_archive], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "archival_status = 'ARCHIVED'" in sql


# ============================================================================
# Edge TOMBSTONE Tests
# ============================================================================


class TestEdgeTombstone:
    """Tests for edge TOMBSTONE operation."""

    @pytest.mark.asyncio
    async def test_tombstone_edge(self, kg_writer, mock_uow, sample_edge_tombstone):
        """Should tombstone edge for GDPR deletion."""
        result = await kg_writer.write([sample_edge_tombstone], mock_uow)

        assert result.writes_succeeded == 1
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "attributes_json = '{}'" in sql
        assert "archival_status = 'TOMBSTONE'" in sql
        assert "gdpr_deletion" in sql


# ============================================================================
# Merge Tracking Tests
# ============================================================================


class TestMergeTracking:
    """Tests for entity merge tracking."""

    @pytest.mark.asyncio
    async def test_track_merge(self, kg_writer, mock_uow):
        """Should track entity merge."""
        await kg_writer.track_merge(
            mock_uow,
            source_id="entity_old",
            target_id="entity_new",
            merge_reason="duplicate",
        )

        mock_uow.connection.execute.assert_called_once()
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "st_entity_merges" in sql
        assert "ON CONFLICT (source_entity_id, target_entity_id) DO NOTHING" in sql
        assert "entity_old" in call_args[0]
        assert "entity_new" in call_args[0]
        assert "duplicate" in call_args[0]


# ============================================================================
# Mixed Operations Tests
# ============================================================================


class TestMixedOperations:
    """Tests for mixed entity and edge operations."""

    @pytest.mark.asyncio
    async def test_mixed_entity_and_edge_writes(
        self, kg_writer, mock_uow, sample_entity_insert, sample_edge_insert
    ):
        """Should handle both entity and edge writes."""
        result = await kg_writer.write([sample_entity_insert, sample_edge_insert], mock_uow)

        assert result.writes_attempted == 2
        assert result.writes_succeeded == 2
        assert mock_uow.connection.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_entities(self, kg_writer, mock_uow):
        """Should process multiple entity writes."""
        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_KG_DOM,
                record_id=f"entity_{i:03d}",
                data={
                    "entity_id": f"entity_{i:03d}",
                    "tenant_id": "tenant",
                    "space_id": "space",
                    "entity_type": "ITEM",
                },
                phase="R4",
            )
            for i in range(5)
        ]

        result = await kg_writer.write(writes, mock_uow)

        assert result.writes_attempted == 5
        assert result.writes_succeeded == 5

    @pytest.mark.asyncio
    async def test_multiple_edges(self, kg_writer, mock_uow):
        """Should process multiple edge writes."""
        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_KG_EDGES,
                record_id=f"edge_{i:03d}",
                data={
                    "edge_id": f"edge_{i:03d}",
                    "tenant_id": "tenant",
                    "space_id": "space",
                    "source_entity_id": "e1",
                    "target_entity_id": f"e{i}",
                },
                phase="R4",
            )
            for i in range(5)
        ]

        result = await kg_writer.write(writes, mock_uow)

        assert result.writes_attempted == 5
        assert result.writes_succeeded == 5


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_continues_on_entity_failure(self, kg_writer, mock_uow):
        """Should continue processing after entity failure."""
        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_KG_DOM,
                record_id="entity_001",
                data={
                    "entity_id": "entity_001",
                    "tenant_id": "t",
                    "space_id": "s",
                },
                phase="R4",
            ),
            StagedWrite.insert(
                layer=LAYER_ST_KG_DOM,
                record_id="entity_002",
                data={
                    "entity_id": "entity_002",
                    "tenant_id": "t",
                    "space_id": "s",
                },
                phase="R4",
            ),
        ]

        mock_uow.connection.execute.side_effect = [
            "INSERT 0 1",
            Exception("DB error"),
        ]

        result = await kg_writer.write(writes, mock_uow)

        assert result.writes_succeeded == 1
        assert result.writes_failed == 1
        assert "entity_002" in result.failed_ids

    @pytest.mark.asyncio
    async def test_continues_on_edge_failure(self, kg_writer, mock_uow):
        """Should continue processing after edge failure."""
        writes = [
            StagedWrite.insert(
                layer=LAYER_ST_KG_EDGES,
                record_id="edge_001",
                data={
                    "edge_id": "edge_001",
                    "tenant_id": "t",
                    "space_id": "s",
                    "source_entity_id": "e1",
                    "target_entity_id": "e2",
                },
                phase="R4",
            ),
            StagedWrite.insert(
                layer=LAYER_ST_KG_EDGES,
                record_id="edge_002",
                data={
                    "edge_id": "edge_002",
                    "tenant_id": "t",
                    "space_id": "s",
                    "source_entity_id": "e1",
                    "target_entity_id": "e3",
                },
                phase="R4",
            ),
        ]

        mock_uow.connection.execute.side_effect = [
            Exception("DB error"),
            "INSERT 0 1",
        ]

        result = await kg_writer.write(writes, mock_uow)

        assert result.writes_succeeded == 1
        assert result.writes_failed == 1
        assert "edge_001" in result.failed_ids

    @pytest.mark.asyncio
    async def test_ignores_other_layers(self, kg_writer, mock_uow):
        """Should ignore writes for other layers."""
        from k0.pipelines.p03.staged_writes import LAYER_ST_EPI

        other_layer_write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="ep_001",
            data={"episode_id": "ep_001", "tenant_id": "t", "space_id": "s"},
            phase="R7",
        )

        result = await kg_writer.write([other_layer_write], mock_uow)

        assert result.writes_attempted == 0
        assert result.writes_succeeded == 0
        mock_uow.connection.execute.assert_not_called()


# =============================================================================
# TEST: Intent Signal Special Fields
# =============================================================================


class TestIntentSignalEntityUpdates:
    """Tests for intent signal special field handling in entity updates."""

    @pytest.mark.asyncio
    async def test_query_boost_entity_increments_query_count(
        self, kg_writer: KGLayerWriter, mock_uow
    ) -> None:
        """query_count_increment triggers atomic increment on st_kg_dom."""
        query_boost_write = StagedWrite.update(
            layer=LAYER_ST_KG_DOM,
            record_id="entity_001",
            data={
                "entity_id": "entity_001",
                "query_count_increment": 1,
                "last_queried_at": 1700000000000,
                "updated_at": 1700000000000,
            },
            phase="R6",
            expected_version=0,
        )

        await kg_writer.write([query_boost_write], mock_uow)

        # Verify SQL uses atomic increment
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "query_count = COALESCE(query_count, 0) + $1" in sql
        assert "last_queried_at" in sql
        # Verify parameters
        assert call_args[0][1] == 1  # increment value
        assert call_args[0][2] == 1700000000000  # last_queried_at

    @pytest.mark.asyncio
    async def test_milestone_append_entity(self, kg_writer: KGLayerWriter, mock_uow) -> None:
        """milestone_append triggers JSON array append on st_kg_dom."""
        milestone_write = StagedWrite.update(
            layer=LAYER_ST_KG_DOM,
            record_id="entity_001",
            data={
                "entity_id": "entity_001",
                "milestone_append": {
                    "milestone_type": "FIRST_MEETING",
                    "description": "First time meeting",
                    "source_event_id": "evt_123",
                    "recorded_at_ms": 1700000000000,
                },
                "updated_at": 1700000000000,
            },
            phase="R6",
            expected_version=0,
        )

        await kg_writer.write([milestone_write], mock_uow)

        # Verify SQL uses JSON append
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "milestones_json" in sql
        assert "COALESCE" in sql
        assert "jsonb" in sql.lower()

    @pytest.mark.asyncio
    async def test_query_boost_skips_version_check(
        self, kg_writer: KGLayerWriter, mock_uow
    ) -> None:
        """query_boost does not require version check (low priority update)."""
        query_boost_write = StagedWrite.update(
            layer=LAYER_ST_KG_DOM,
            record_id="entity_001",
            data={
                "entity_id": "entity_001",
                "query_count_increment": 1,
                "last_queried_at": 1700000000000,
            },
            phase="R6",
            expected_version=0,
        )

        await kg_writer.write([query_boost_write], mock_uow)

        # Verify SQL does NOT include version check
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "version =" not in sql.lower()


class TestIntentSignalEdgeUpdates:
    """Tests for intent signal special field handling in edge updates."""

    @pytest.mark.asyncio
    async def test_query_boost_edge_increments_query_count(
        self, kg_writer: KGLayerWriter, mock_uow
    ) -> None:
        """query_count_increment triggers atomic increment on st_kg_edges."""
        query_boost_write = StagedWrite.update(
            layer=LAYER_ST_KG_EDGES,
            record_id="edge_001",
            data={
                "edge_id": "edge_001",
                "query_count_increment": 1,
                "last_queried_at": 1700000000000,
                "updated_at": 1700000000000,
            },
            phase="R6",
            expected_version=0,
        )

        await kg_writer.write([query_boost_write], mock_uow)

        # Verify SQL uses atomic increment
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "query_count = COALESCE(query_count, 0) + $1" in sql
        assert "st_kg_edges" in sql

    @pytest.mark.asyncio
    async def test_query_boost_edge_skips_version_check(
        self, kg_writer: KGLayerWriter, mock_uow
    ) -> None:
        """Edge query_boost does not require version check."""
        query_boost_write = StagedWrite.update(
            layer=LAYER_ST_KG_EDGES,
            record_id="edge_001",
            data={
                "edge_id": "edge_001",
                "query_count_increment": 1,
                "last_queried_at": 1700000000000,
            },
            phase="R6",
            expected_version=0,
        )

        await kg_writer.write([query_boost_write], mock_uow)

        # Verify SQL does NOT include version check
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "version =" not in sql.lower()

    @pytest.mark.asyncio
    async def test_standard_edge_update_still_works(
        self, kg_writer: KGLayerWriter, mock_uow, sample_edge_update
    ) -> None:
        """Standard edge updates still work as expected."""
        await kg_writer.write([sample_edge_update], mock_uow)

        # Verify standard update SQL
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "confidence" in sql
        assert "version = version + 1" in sql
