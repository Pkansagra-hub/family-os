"""
R4 Entity Merger Tests — Epic 4.4.7

Spec Reference: M4_EXECUTION.md, Issue 4.4.7

Tests for EntityMerger:
1. test_merge_validates_entities_exist — Error if entity missing
2. test_merge_validates_not_already_merged — Error if already merged
3. test_merge_validates_same_type — Error if types differ
4. test_merge_selects_primary_with_more_history — Swaps if needed
5. test_merge_cascades_kg_edges — source/target updated
6. test_merge_cascades_hipp_events — entities_json updated
7. test_merge_cascades_epi — entity_ids array updated
8. test_merge_cascades_all_seven_tables — All tables updated
9. test_merge_archives_secondary — archival_status=MERGED
10. test_merge_logs_for_undo — st_entity_merges record created
11. test_reverse_merge_restores — Secondary restored to ACTIVE
12. test_reverse_merge_fails_if_already_reversed — Error on double undo
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from k0.modules.consolidation.algorithms.entity_merger import (
    CascadeCounts,
    EntityMerger,
    EntitySnapshot,
    MergeResult,
    get_entity_merger,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def merger() -> EntityMerger:
    """Create fresh merger instance."""
    return EntityMerger()


@pytest.fixture
def primary_entity() -> dict:
    """Create mock primary entity row."""
    return {
        "entity_id": "ent_john_smith",
        "canonical_name": "John Smith",
        "entity_type": "PERSON",
        "properties": {"nickname": "Johnny"},
        "observation_count": 10,
        "archival_status": "ACTIVE",
    }


@pytest.fixture
def secondary_entity() -> dict:
    """Create mock secondary entity row (fewer observations)."""
    return {
        "entity_id": "ent_j_smith",
        "canonical_name": "J. Smith",
        "entity_type": "PERSON",
        "properties": {"email": "j.smith@example.com"},
        "observation_count": 3,
        "archival_status": "ACTIVE",
    }


@pytest.fixture
def secondary_entity_more_history() -> dict:
    """Create mock secondary entity with MORE observations."""
    return {
        "entity_id": "ent_j_smith",
        "canonical_name": "J. Smith",
        "entity_type": "PERSON",
        "properties": {"email": "j.smith@example.com"},
        "observation_count": 20,  # More than primary
        "archival_status": "ACTIVE",
    }


@pytest.fixture
def mock_db_conn(primary_entity: dict, secondary_entity: dict) -> AsyncMock:
    """Create mock database connection with entity data."""
    conn = AsyncMock()

    # fetchrow returns different entities based on ID
    async def mock_fetchrow(query: str, *args):
        if "st_kg_dom" in query:
            entity_id = args[0] if args else None
            if entity_id == "ent_john_smith":
                return primary_entity
            elif entity_id == "ent_j_smith":
                return secondary_entity
        elif "st_entity_merges" in query:
            # No merge record by default
            return None
        return None

    conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)
    conn.fetch = AsyncMock(return_value=[])

    # execute returns row count
    conn.execute = AsyncMock(return_value="UPDATE 5")

    return conn


# =============================================================================
# Test Validation
# =============================================================================


class TestMergeValidation:
    """Tests for merge validation."""

    @pytest.mark.asyncio
    async def test_merge_validates_entities_exist(
        self, merger: EntityMerger, mock_db_conn: AsyncMock
    ):
        """Should fail if entity doesn't exist."""
        # Make primary not found
        mock_db_conn.fetchrow = AsyncMock(return_value=None)

        result = await merger.merge_entities(
            primary_entity_id="ent_not_exists",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_merge_validates_not_already_merged(
        self,
        merger: EntityMerger,
        mock_db_conn: AsyncMock,
        primary_entity: dict,
        secondary_entity: dict,
    ):
        """Should fail if entity already merged."""
        # Make secondary already merged
        merged_secondary = {**secondary_entity, "archival_status": "MERGED"}

        async def mock_fetchrow(query: str, *args):
            if args and args[0] == "ent_john_smith":
                return primary_entity
            elif args and args[0] == "ent_j_smith":
                return merged_secondary
            return None

        mock_db_conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)

        result = await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result.success is False
        assert "already merged" in result.error.lower()

    @pytest.mark.asyncio
    async def test_merge_validates_same_type(
        self,
        merger: EntityMerger,
        mock_db_conn: AsyncMock,
        primary_entity: dict,
        secondary_entity: dict,
    ):
        """Should fail if entity types differ."""
        # Make secondary a different type
        different_type = {**secondary_entity, "entity_type": "ORGANIZATION"}

        async def mock_fetchrow(query: str, *args):
            if args and args[0] == "ent_john_smith":
                return primary_entity
            elif args and args[0] == "ent_j_smith":
                return different_type
            return None

        mock_db_conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)

        result = await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result.success is False
        assert "types don't match" in result.error.lower() or "type" in result.error.lower()


# =============================================================================
# Test Primary Selection
# =============================================================================


class TestPrimarySelection:
    """Tests for primary entity selection based on history."""

    @pytest.mark.asyncio
    async def test_merge_selects_primary_with_more_history(
        self,
        merger: EntityMerger,
        mock_db_conn: AsyncMock,
        primary_entity: dict,
        secondary_entity_more_history: dict,
    ):
        """Should swap primary/secondary if secondary has more history."""

        # Secondary has observation_count=20, primary has 10
        async def mock_fetchrow(query: str, *args):
            if "st_kg_dom" in query:
                if args and args[0] == "ent_john_smith":
                    return primary_entity  # obs_count=10
                elif args and args[0] == "ent_j_smith":
                    return secondary_entity_more_history  # obs_count=20
            return None

        mock_db_conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)

        result = await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result.success is True
        # The secondary (with more history) should become primary
        assert result.primary_entity_id == "ent_j_smith"
        assert result.secondary_entity_id == "ent_john_smith"

    @pytest.mark.asyncio
    async def test_merge_keeps_primary_when_more_history(
        self,
        merger: EntityMerger,
        mock_db_conn: AsyncMock,
        primary_entity: dict,
        secondary_entity: dict,
    ):
        """Should keep primary when it has more history."""
        result = await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result.success is True
        # Primary (obs_count=10) has more than secondary (obs_count=3)
        assert result.primary_entity_id == "ent_john_smith"
        assert result.secondary_entity_id == "ent_j_smith"


# =============================================================================
# Test Cascade Updates
# =============================================================================


class TestCascadeUpdates:
    """Tests for cascade updates across tables."""

    @pytest.mark.asyncio
    async def test_merge_cascades_kg_edges(self, merger: EntityMerger, mock_db_conn: AsyncMock):
        """Cascade should update st_kg_edges source and target."""
        result = await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result.success is True

        # Verify execute was called with kg_edges updates
        calls = mock_db_conn.execute.call_args_list
        kg_edge_calls = [c for c in calls if "st_kg_edges" in str(c)]
        assert len(kg_edge_calls) >= 2  # source and target

    @pytest.mark.asyncio
    async def test_merge_cascades_hipp_events(self, merger: EntityMerger, mock_db_conn: AsyncMock):
        """Cascade should update st_hipp_events JSON."""
        result = await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result.success is True

        # Verify execute was called with hipp_events update
        calls = mock_db_conn.execute.call_args_list
        hipp_calls = [c for c in calls if "st_hipp_events" in str(c)]
        assert len(hipp_calls) >= 1

    @pytest.mark.asyncio
    async def test_merge_cascades_epi(self, merger: EntityMerger, mock_db_conn: AsyncMock):
        """Cascade should update st_epi entity_ids array."""
        result = await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result.success is True

        # Verify execute was called with st_epi update
        calls = mock_db_conn.execute.call_args_list
        epi_calls = [c for c in calls if "st_epi" in str(c)]
        assert len(epi_calls) >= 1

    @pytest.mark.asyncio
    async def test_merge_cascades_all_seven_tables(
        self, merger: EntityMerger, mock_db_conn: AsyncMock
    ):
        """Cascade should update all 7 tables."""
        result = await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result.success is True

        # Check cascade counts
        counts = result.cascade_counts
        assert counts.kg_edges_source == 5  # Mocked "UPDATE 5"
        assert counts.kg_edges_target == 5
        assert counts.hipp_events == 5
        assert counts.epi == 5
        assert counts.sem == 5
        assert counts.social == 5
        assert counts.procedural == 5
        assert counts.vec == 5

        # Total should be sum of all
        assert counts.total == 40  # 8 tables * 5 rows each


# =============================================================================
# Test Archival
# =============================================================================


class TestArchival:
    """Tests for secondary entity archival."""

    @pytest.mark.asyncio
    async def test_merge_archives_secondary(self, merger: EntityMerger, mock_db_conn: AsyncMock):
        """Merge should mark secondary entity as MERGED."""
        result = await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result.success is True

        # Verify UPDATE st_kg_dom with archival_status = 'MERGED'
        calls = mock_db_conn.execute.call_args_list
        archive_calls = [c for c in calls if "archival_status" in str(c) and "MERGED" in str(c)]
        assert len(archive_calls) >= 1


# =============================================================================
# Test Audit Logging
# =============================================================================


class TestAuditLogging:
    """Tests for merge audit logging."""

    @pytest.mark.asyncio
    async def test_merge_logs_for_undo(self, merger: EntityMerger, mock_db_conn: AsyncMock):
        """Merge should create st_entity_merges record."""
        result = await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result.success is True
        assert result.merge_id is not None

        # Verify INSERT into st_entity_merges
        calls = mock_db_conn.execute.call_args_list
        merge_log_calls = [c for c in calls if "st_entity_merges" in str(c)]
        assert len(merge_log_calls) >= 1


# =============================================================================
# Test Reverse Merge
# =============================================================================


class TestReverseMerge:
    """Tests for merge undo functionality."""

    @pytest.mark.asyncio
    async def test_reverse_merge_restores(self, merger: EntityMerger, mock_db_conn: AsyncMock):
        """Reverse merge should restore secondary to ACTIVE."""
        # Mock merge record
        merge_record = {
            "merge_id": "merge_123",
            "primary_entity_id": "ent_john_smith",
            "secondary_entity_id": "ent_j_smith",
            "reversed_at": None,  # Not yet reversed
        }

        async def mock_fetchrow(query: str, *args):
            if "st_entity_merges" in query:
                return merge_record
            return None

        mock_db_conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)

        result = await merger.reverse_merge(
            merge_id="merge_123",
            reversed_by="test_user",
            db_conn=mock_db_conn,
        )

        assert result is True

        # Verify secondary entity restored to ACTIVE
        calls = mock_db_conn.execute.call_args_list
        restore_calls = [c for c in calls if "archival_status" in str(c) and "ACTIVE" in str(c)]
        assert len(restore_calls) >= 1

    @pytest.mark.asyncio
    async def test_reverse_merge_fails_if_already_reversed(
        self, merger: EntityMerger, mock_db_conn: AsyncMock
    ):
        """Reverse merge should fail if already reversed."""
        # Mock already-reversed merge record
        merge_record = {
            "merge_id": "merge_123",
            "primary_entity_id": "ent_john_smith",
            "secondary_entity_id": "ent_j_smith",
            "reversed_at": 1234567890,  # Already reversed
        }

        mock_db_conn.fetchrow = AsyncMock(return_value=merge_record)

        with pytest.raises(ValueError) as exc_info:
            await merger.reverse_merge(
                merge_id="merge_123",
                reversed_by="test_user",
                db_conn=mock_db_conn,
            )

        assert "already reversed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_reverse_merge_fails_if_not_found(
        self, merger: EntityMerger, mock_db_conn: AsyncMock
    ):
        """Reverse merge should fail if merge record not found."""
        mock_db_conn.fetchrow = AsyncMock(return_value=None)

        with pytest.raises(ValueError) as exc_info:
            await merger.reverse_merge(
                merge_id="merge_not_exists",
                reversed_by="test_user",
                db_conn=mock_db_conn,
            )

        assert "not found" in str(exc_info.value).lower()


# =============================================================================
# Test Merge History
# =============================================================================


class TestMergeHistory:
    """Tests for merge history queries."""

    @pytest.mark.asyncio
    async def test_get_merge_history(self, merger: EntityMerger, mock_db_conn: AsyncMock):
        """Should return merge history for entity."""
        mock_db_conn.fetch = AsyncMock(
            return_value=[
                {
                    "merge_id": "merge_1",
                    "primary_entity_id": "ent_john_smith",
                    "secondary_entity_id": "ent_j_smith",
                    "merged_at": 1234567890,
                    "reversed_at": None,
                },
            ]
        )

        history = await merger.get_merge_history(
            entity_id="ent_john_smith",
            db_conn=mock_db_conn,
        )

        assert len(history) == 1
        assert history[0]["merge_id"] == "merge_1"


# =============================================================================
# Test Factory Function
# =============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_get_entity_merger(self):
        """Factory should return configured instance."""
        merger = get_entity_merger()
        assert isinstance(merger, EntityMerger)


# =============================================================================
# Test Data Classes
# =============================================================================


class TestDataClasses:
    """Tests for data classes."""

    def test_entity_snapshot_to_dict(self):
        """EntitySnapshot should serialize to dict."""
        snapshot = EntitySnapshot(
            entity_id="ent_123",
            canonical_name="Test Entity",
            entity_type="PERSON",
            properties={"key": "value"},
            observation_count=5,
            archival_status="ACTIVE",
        )
        d = snapshot.to_dict()

        assert d["entity_id"] == "ent_123"
        assert d["canonical_name"] == "Test Entity"
        assert d["entity_type"] == "PERSON"
        assert d["properties"] == {"key": "value"}
        assert d["observation_count"] == 5
        assert d["archival_status"] == "ACTIVE"

    def test_entity_snapshot_from_dict(self):
        """EntitySnapshot should deserialize from dict."""
        data = {
            "entity_id": "ent_123",
            "canonical_name": "Test Entity",
            "entity_type": "PERSON",
            "properties": {"key": "value"},
            "observation_count": 5,
            "archival_status": "ACTIVE",
        }
        snapshot = EntitySnapshot.from_dict(data)

        assert snapshot.entity_id == "ent_123"
        assert snapshot.canonical_name == "Test Entity"

    def test_cascade_counts_total(self):
        """CascadeCounts should calculate total."""
        counts = CascadeCounts(
            kg_edges_source=1,
            kg_edges_target=2,
            hipp_events=3,
            epi=4,
            sem=5,
            social=6,
            procedural=7,
            vec=8,
        )
        assert counts.total == 36  # 1+2+3+4+5+6+7+8

    def test_cascade_counts_to_dict(self):
        """CascadeCounts should serialize to dict."""
        counts = CascadeCounts(kg_edges_source=5, kg_edges_target=3)
        d = counts.to_dict()

        assert d["kg_edges_source"] == 5
        assert d["kg_edges_target"] == 3
        assert "total" in d

    def test_merge_result_to_dict(self):
        """MergeResult should serialize to dict."""
        result = MergeResult(
            merge_id="merge_123",
            primary_entity_id="ent_a",
            secondary_entity_id="ent_b",
            cascade_counts=CascadeCounts(),
            success=True,
        )
        d = result.to_dict()

        assert d["merge_id"] == "merge_123"
        assert d["success"] is True


# =============================================================================
# Test Metrics
# =============================================================================


class TestMetrics:
    """Tests for metrics tracking."""

    @pytest.mark.asyncio
    async def test_metrics_updated_on_merge(self, merger: EntityMerger, mock_db_conn: AsyncMock):
        """Metrics should track merge operations."""
        await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        metrics = merger.metrics
        assert metrics.total_merges == 1
        assert metrics.successful_merges == 1
        assert metrics.failed_merges == 0

    @pytest.mark.asyncio
    async def test_metrics_updated_on_failure(self, merger: EntityMerger, mock_db_conn: AsyncMock):
        """Metrics should track failed merges."""
        mock_db_conn.fetchrow = AsyncMock(return_value=None)

        await merger.merge_entities(
            primary_entity_id="ent_not_exists",
            secondary_entity_id="ent_j_smith",
            merge_reason="Test merge",
            initiated_by="test_user",
            db_conn=mock_db_conn,
        )

        metrics = merger.metrics
        assert metrics.total_merges == 1
        assert metrics.successful_merges == 0
        assert metrics.failed_merges == 1
