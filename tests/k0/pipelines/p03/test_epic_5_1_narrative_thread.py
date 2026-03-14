"""
Tests for Epic 5.1: Cross-Episode Thread Matching.

Issue 5.1.1: Migration 0083 (narrative columns on st_epi)
Issue 5.1.2: R7 truth writer persists narrative columns
Issue 5.1.3: find_thread_continuations query
Issue 5.1.4: continuation_of_episode_id
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.staging.idempotency import IdempotencyKeyGenerator
from k0.modules.consolidation.staging.truth_write_assembler import TruthWriteAssembler
from k0.modules.consolidation.truth_writer.layers.episodic import EpisodicLayerWriter
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.phase_outputs import EpisodeCluster
from k0.pipelines.p03.phases.r2_episodic_integrator import find_thread_continuations
from k0.pipelines.p03.staged_writes import LAYER_ST_EPI, StagedWrite

# ============================================================================
# Fixtures
# ============================================================================

TEST_ULID = "01HXYZ123456789ABCDEFGHJKM"


@pytest.fixture
def mock_uow():
    """Create mock UnitOfWork with async connection."""
    uow = MagicMock()
    uow.connection = AsyncMock()
    uow.connection.execute = AsyncMock(return_value="INSERT 0 1")
    return uow


@pytest.fixture
def episodic_writer():
    return EpisodicLayerWriter()


@pytest.fixture
def idempotency_gen():
    return IdempotencyKeyGenerator(cycle_ulid=TEST_ULID)


@pytest.fixture
def assembler(idempotency_gen):
    return TruthWriteAssembler(idempotency_gen=idempotency_gen)


def _make_event_state(event_id: str, thread_id: str = "", arc: str = "") -> P03EventState:
    """Create P03EventState with narrative fields."""
    state = P03EventState(event_id=event_id)
    state.narrative_thread_id = thread_id
    state.narrative_arc_position = arc
    state.timestamp = 1700000000000
    return state


def _make_cluster(cluster_id: str, event_ids: list) -> EpisodeCluster:
    """Create test EpisodeCluster."""
    return EpisodeCluster(
        cluster_id=cluster_id,
        member_event_ids=event_ids,
        temporal_start=1700000000000,
        temporal_end=1700003600000,
        location_hint="home",
        participants_json='["mom"]',
        activity_type="meal",
        cohesion_score=0.85,
        title="Family Dinner",
        summary="Had dinner with family",
    )


# ============================================================================
# Issue 5.1.1: Migration Structure Tests
# ============================================================================


class TestMigration0083:
    """Verify migration module exists and has correct structure."""

    def test_migration_module_importable(self):
        import importlib

        m = importlib.import_module("k0.db.alembic.versions.0083_st_epi_narrative_columns")
        assert m.revision == "0083"
        assert m.down_revision == "0082"

    def test_migration_has_upgrade_downgrade(self):
        import importlib

        m = importlib.import_module("k0.db.alembic.versions.0083_st_epi_narrative_columns")
        assert callable(m.upgrade)
        assert callable(m.downgrade)


# ============================================================================
# Issue 5.1.2: Assembler — narrative columns in record_data
# ============================================================================


class TestAssemblerNarrativeColumns:
    """Test that TruthWriteAssembler populates narrative columns."""

    def test_single_thread_dominant(self, assembler):
        """All events same thread -> dominant = that thread."""
        events = {
            "e1": _make_event_state("e1", thread_id="planning_birthday"),
            "e2": _make_event_state("e2", thread_id="planning_birthday"),
            "e3": _make_event_state("e3", thread_id="planning_birthday"),
        }
        cluster = _make_cluster("epi_001", ["e1", "e2", "e3"])

        writes = assembler.assemble_epi_writes([cluster], events)
        data = writes[0].record_data

        assert data["narrative_thread_id"] == "planning_birthday"
        assert json.loads(data["narrative_thread_ids_json"]) == ["planning_birthday"]

    def test_mixed_threads_majority_wins(self, assembler):
        """Multiple threads -> majority vote selects dominant."""
        events = {
            "e1": _make_event_state("e1", thread_id="planning_birthday"),
            "e2": _make_event_state("e2", thread_id="planning_birthday"),
            "e3": _make_event_state("e3", thread_id="grocery_trip"),
        }
        cluster = _make_cluster("epi_001", ["e1", "e2", "e3"])

        writes = assembler.assemble_epi_writes([cluster], events)
        data = writes[0].record_data

        assert data["narrative_thread_id"] == "planning_birthday"
        all_threads = json.loads(data["narrative_thread_ids_json"])
        assert set(all_threads) == {"planning_birthday", "grocery_trip"}

    def test_no_narrative_events_null(self, assembler):
        """Events with no thread_id -> all narrative columns None."""
        events = {
            "e1": _make_event_state("e1"),
            "e2": _make_event_state("e2"),
        }
        cluster = _make_cluster("epi_001", ["e1", "e2"])

        writes = assembler.assemble_epi_writes([cluster], events)
        data = writes[0].record_data

        assert data["narrative_thread_id"] is None
        assert data["narrative_thread_ids_json"] is None
        assert data["narrative_arc_position"] is None

    def test_arc_position_majority(self, assembler):
        """Arc position uses majority vote."""
        events = {
            "e1": _make_event_state("e1", thread_id="t1", arc="EXPOSITION"),
            "e2": _make_event_state("e2", thread_id="t1", arc="RISING_ACTION"),
            "e3": _make_event_state("e3", thread_id="t1", arc="EXPOSITION"),
        }
        cluster = _make_cluster("epi_001", ["e1", "e2", "e3"])

        writes = assembler.assemble_epi_writes([cluster], events)
        data = writes[0].record_data

        assert data["narrative_arc_position"] == "EXPOSITION"

    def test_continuation_of_episode_id_default_none(self, assembler):
        """continuation_of_episode_id defaults to None."""
        events = {"e1": _make_event_state("e1", thread_id="t1")}
        cluster = _make_cluster("epi_001", ["e1"])

        writes = assembler.assemble_epi_writes([cluster], events)
        data = writes[0].record_data

        assert data["continuation_of_episode_id"] is None

    def test_no_event_states_still_works(self, assembler):
        """Cluster with no matching event states -> NULL narrative."""
        cluster = _make_cluster("epi_001", ["e1", "e2"])

        writes = assembler.assemble_epi_writes([cluster], {})
        data = writes[0].record_data

        assert data["narrative_thread_id"] is None
        assert data["narrative_thread_ids_json"] is None


# ============================================================================
# Issue 5.1.2: Episodic Writer — INSERT includes narrative columns
# ============================================================================


class TestEpisodicInsertNarrative:
    """Test INSERT SQL includes narrative columns."""

    @pytest.mark.asyncio
    async def test_insert_sql_has_narrative_columns(self, episodic_writer, mock_uow):
        """INSERT SQL should include narrative_thread_id columns."""
        write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={
                "episode_id": "epi_001",
                "tenant_id": "tenant_abc",
                "space_id": "space_xyz",
                "narrative_thread_id": "planning_birthday",
                "narrative_thread_ids_json": '["planning_birthday"]',
                "narrative_arc_position": "EXPOSITION",
                "continuation_of_episode_id": "epi_prev_001",
            },
            phase="R2",
        )

        await episodic_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args_list[0]
        sql = call_args[0][0]

        assert "narrative_thread_id" in sql
        assert "narrative_thread_ids_json" in sql
        assert "narrative_arc_position" in sql
        assert "continuation_of_episode_id" in sql

    @pytest.mark.asyncio
    async def test_insert_passes_narrative_params(self, episodic_writer, mock_uow):
        """INSERT should pass narrative values as params $31-$34."""
        write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={
                "episode_id": "epi_001",
                "tenant_id": "tenant_abc",
                "space_id": "space_xyz",
                "narrative_thread_id": "planning_birthday",
                "narrative_thread_ids_json": '["planning_birthday"]',
                "narrative_arc_position": "EXPOSITION",
                "continuation_of_episode_id": "epi_prev_001",
            },
            phase="R2",
        )

        await episodic_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args_list[0]
        values = call_args[0][1:]

        assert "planning_birthday" in values
        assert '["planning_birthday"]' in values
        assert "EXPOSITION" in values
        assert "epi_prev_001" in values

    @pytest.mark.asyncio
    async def test_insert_null_narrative(self, episodic_writer, mock_uow):
        """INSERT with no narrative data passes None for all 4."""
        write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={
                "episode_id": "epi_001",
                "tenant_id": "tenant_abc",
                "space_id": "space_xyz",
            },
            phase="R2",
        )

        await episodic_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args_list[0]
        values = call_args[0][1:]

        # Last 5 params: narrative cols (4x None) + completion (False)
        assert values[-5:] == (None, None, None, None, False)


# ============================================================================
# Issue 5.1.2: Episodic Writer — REINFORCE merges narrative threads
# ============================================================================


class TestEpisodicReinforceNarrative:
    """Test REINFORCE UPDATE merges narrative thread_ids."""

    @pytest.mark.asyncio
    async def test_reinforce_sql_has_narrative_merge(self, episodic_writer, mock_uow):
        """REINFORCE SQL should include narrative thread merging."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        write = StagedWrite.update(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={
                "episode_id": "epi_001",
                "tenant_id": "tenant_abc",
                "space_id": "space_xyz",
                "additional_event_ids": ["e3"],
                "additional_event_count": 1,
                "new_start_time_utc": 1700000000000,
                "new_end_time_utc": 1700003600000,
                "narrative_thread_id": "planning_birthday",
                "narrative_thread_ids_json": '["planning_birthday"]',
            },
            phase="R6",
            expected_version=1,
        )

        await episodic_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args_list[0]
        sql = call_args[0][0]

        assert "narrative_thread_ids_json" in sql
        assert "narrative_thread_id" in sql

    @pytest.mark.asyncio
    async def test_reinforce_passes_12_params(self, episodic_writer, mock_uow):
        """REINFORCE should pass 12 params (10 original + 2 narrative)."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        write = StagedWrite.update(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={
                "episode_id": "epi_001",
                "tenant_id": "t",
                "space_id": "s",
                "additional_event_ids": ["e3"],
                "narrative_thread_ids_json": '["planning_birthday"]',
                "narrative_thread_id": "planning_birthday",
            },
            phase="R6",
            expected_version=1,
        )

        await episodic_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args_list[0]
        values = call_args[0][1:]
        assert len(values) == 12

    @pytest.mark.asyncio
    async def test_reinforce_null_narrative(self, episodic_writer, mock_uow):
        """REINFORCE without narrative data passes None for narrative params."""
        mock_uow.connection.execute.return_value = "UPDATE 1"

        write = StagedWrite.update(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={
                "episode_id": "epi_001",
                "tenant_id": "t",
                "space_id": "s",
                "additional_event_ids": ["e3"],
            },
            phase="R6",
            expected_version=1,
        )

        await episodic_writer.write([write], mock_uow)

        call_args = mock_uow.connection.execute.call_args_list[0]
        values = call_args[0][1:]
        # Last 2 params are narrative (None, None)
        assert values[-2:] == (None, None)


# ============================================================================
# Issue 5.1.3: find_thread_continuations
# ============================================================================


class TestFindThreadContinuations:
    """Test cross-episode thread matching query."""

    @pytest.mark.asyncio
    async def test_empty_thread_id_returns_empty(self):
        """Empty thread_id should return empty list without querying."""
        conn = AsyncMock()
        result = await find_thread_continuations(conn, "t1", "", "epi_001")
        assert result == []
        conn.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_thread_id_returns_empty(self):
        """None-like thread_id returns empty list."""
        conn = AsyncMock()
        result = await find_thread_continuations(conn, "t1", "", "epi_001")
        assert result == []

    @pytest.mark.asyncio
    async def test_query_returns_matching_episodes(self):
        """Should return episodes with same thread_id."""
        mock_row = {
            "episode_id": "epi_prior_001",
            "narrative_arc_position": "RISING_ACTION",
            "start_time_utc": 1699900000000,
            "end_time_utc": 1699903600000,
            "episode_summary": "Started planning party",
        }
        conn = AsyncMock()
        conn.fetch = AsyncMock(
            return_value=[
                MagicMock(
                    **{
                        "__iter__": lambda s: iter(mock_row.items()),
                        "keys": lambda s: mock_row.keys(),
                        "values": lambda s: mock_row.values(),
                        "__getitem__": lambda s, k: mock_row[k],
                    }
                )
            ]
        )

        # Use a simpler approach - mock the fetch to return dict-like rows
        class DictRow(dict):
            pass

        conn.fetch = AsyncMock(return_value=[DictRow(mock_row)])

        result = await find_thread_continuations(conn, "tenant_1", "planning_birthday", "epi_new")

        assert len(result) == 1
        assert result[0]["episode_id"] == "epi_prior_001"
        assert result[0]["narrative_arc_position"] == "RISING_ACTION"

    @pytest.mark.asyncio
    async def test_query_excludes_current_episode(self):
        """SQL should exclude the current episode_id."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])

        await find_thread_continuations(conn, "tenant_1", "planning_birthday", "epi_current")

        call_args = conn.fetch.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]

        assert "episode_id != $3" in sql
        assert params[2] == "epi_current"

    @pytest.mark.asyncio
    async def test_query_filters_active_only(self):
        """SQL should filter to ACTIVE archival_status only."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])

        await find_thread_continuations(conn, "tenant_1", "planning_birthday", "epi_current")

        sql = conn.fetch.call_args[0][0]
        assert "archival_status = 'ACTIVE'" in sql

    @pytest.mark.asyncio
    async def test_query_orders_by_most_recent(self):
        """SQL should ORDER BY start_time_utc DESC."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])

        await find_thread_continuations(conn, "tenant_1", "planning_birthday", "epi_current")

        sql = conn.fetch.call_args[0][0]
        assert "ORDER BY start_time_utc DESC" in sql

    @pytest.mark.asyncio
    async def test_query_limits_to_10(self):
        """SQL should LIMIT 10."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])

        await find_thread_continuations(conn, "tenant_1", "planning_birthday", "epi_current")

        sql = conn.fetch.call_args[0][0]
        assert "LIMIT 10" in sql
