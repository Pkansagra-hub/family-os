"""
Tests for Epic 5.2: Goal Completion Detection.

Issue 5.2.1: detect_arc_completion logic
Issue 5.2.2: Migration 0084 + INSERT $35 + assembler field
Issue 5.2.3: log_thread_completion observability
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.staging.idempotency import IdempotencyKeyGenerator
from k0.modules.consolidation.staging.truth_write_assembler import TruthWriteAssembler
from k0.modules.consolidation.truth_writer.layers.episodic import EpisodicLayerWriter
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.phase_outputs import EpisodeCluster
from k0.pipelines.p03.phases.r2_episodic_integrator import (
    detect_arc_completion,
    log_thread_completion,
)
from k0.pipelines.p03.staged_writes import LAYER_ST_EPI, StagedWrite

TEST_ULID = "01HXYZ123456789ABCDEFGHJKM"


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_uow():
    uow = MagicMock()
    uow.connection = AsyncMock()
    uow.connection.execute = AsyncMock(return_value="INSERT 0 1")
    return uow


@pytest.fixture
def episodic_writer():
    return EpisodicLayerWriter()


@pytest.fixture
def assembler():
    return TruthWriteAssembler(idempotency_gen=IdempotencyKeyGenerator(cycle_ulid=TEST_ULID))


def _make_event_state(event_id: str, thread_id: str = "", arc: str = "") -> P03EventState:
    state = P03EventState(event_id=event_id)
    state.narrative_thread_id = thread_id
    state.narrative_arc_position = arc
    state.timestamp = 1700000000000
    return state


def _make_cluster(cluster_id: str, event_ids: list) -> EpisodeCluster:
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


def _prior_episodes(*arcs: str) -> list[dict]:
    """Build a list of prior episode dicts with given arc positions."""
    return [
        {
            "episode_id": f"epi_prior_{i}",
            "narrative_arc_position": arc,
            "start_time_utc": 1699900000000 + i * 100000000,
            "end_time_utc": 1699903600000 + i * 100000000,
            "episode_summary": f"Prior episode {i}",
        }
        for i, arc in enumerate(arcs)
    ]


# ============================================================================
# Issue 5.2.1: detect_arc_completion
# ============================================================================


class TestDetectArcCompletion:
    """Tests for narrative arc completion detection."""

    def test_climax_after_exposition_and_rising(self):
        """CLIMAX after [EXPOSITION, RISING_ACTION] -> completed."""
        prior = _prior_episodes("EXPOSITION", "RISING_ACTION")
        assert detect_arc_completion("CLIMAX", prior) is True

    def test_resolution_after_exposition(self):
        """RESOLUTION after [EXPOSITION] -> completed (skipped rising/climax)."""
        prior = _prior_episodes("EXPOSITION")
        assert detect_arc_completion("RESOLUTION", prior) is True

    def test_resolution_after_rising_action(self):
        """RESOLUTION after [RISING_ACTION] -> completed."""
        prior = _prior_episodes("RISING_ACTION")
        assert detect_arc_completion("RESOLUTION", prior) is True

    def test_rising_action_not_completion(self):
        """RISING_ACTION is not a completion position."""
        prior = _prior_episodes("EXPOSITION")
        assert detect_arc_completion("RISING_ACTION", prior) is False

    def test_exposition_not_completion(self):
        """EXPOSITION is not a completion position."""
        prior = _prior_episodes("EXPOSITION")
        assert detect_arc_completion("EXPOSITION", prior) is False

    def test_climax_no_prior_episodes(self):
        """CLIMAX but no prior episodes -> not completed (no buildup)."""
        assert detect_arc_completion("CLIMAX", []) is False

    def test_climax_prior_only_climax(self):
        """CLIMAX with prior [CLIMAX] -> not completed (no buildup)."""
        prior = _prior_episodes("CLIMAX")
        assert detect_arc_completion("CLIMAX", prior) is False

    def test_climax_prior_only_resolution(self):
        """CLIMAX with prior [RESOLUTION] -> not completed."""
        prior = _prior_episodes("RESOLUTION")
        assert detect_arc_completion("CLIMAX", prior) is False

    def test_empty_current_arc(self):
        """Empty arc position -> not completed."""
        prior = _prior_episodes("EXPOSITION")
        assert detect_arc_completion("", prior) is False

    def test_none_arc_position_in_prior(self):
        """Prior episodes with None arc -> not considered buildup."""
        prior = [{"episode_id": "e1", "narrative_arc_position": None}]
        assert detect_arc_completion("CLIMAX", prior) is False


# ============================================================================
# Issue 5.2.1: P03EventState field
# ============================================================================


class TestEventStateField:
    """Test narrative_thread_completed field on P03EventState."""

    def test_default_false(self):
        state = P03EventState(event_id="e1")
        assert state.narrative_thread_completed is False

    def test_set_true(self):
        state = P03EventState(event_id="e1")
        state.narrative_thread_completed = True
        assert state.narrative_thread_completed is True


# ============================================================================
# Issue 5.2.2: Migration 0084
# ============================================================================


class TestMigration0084:

    def test_migration_module_importable(self):
        import importlib

        m = importlib.import_module("k0.db.alembic.versions.0084_st_epi_narrative_thread_completed")
        assert m.revision == "0084"
        assert m.down_revision == "0083"

    def test_migration_has_upgrade_downgrade(self):
        import importlib

        m = importlib.import_module("k0.db.alembic.versions.0084_st_epi_narrative_thread_completed")
        assert callable(m.upgrade)
        assert callable(m.downgrade)


# ============================================================================
# Issue 5.2.2: INSERT includes narrative_thread_completed
# ============================================================================


class TestEpisodicInsertCompletion:

    @pytest.mark.asyncio
    async def test_insert_sql_has_completed_column(self, episodic_writer, mock_uow):
        write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={
                "episode_id": "epi_001",
                "tenant_id": "t",
                "space_id": "s",
                "narrative_thread_completed": True,
            },
            phase="R2",
        )

        await episodic_writer.write([write], mock_uow)

        sql = mock_uow.connection.execute.call_args_list[0][0][0]
        assert "narrative_thread_completed" in sql

    @pytest.mark.asyncio
    async def test_insert_passes_35_params(self, episodic_writer, mock_uow):
        """INSERT should have 35 positional params now."""
        write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={
                "episode_id": "epi_001",
                "tenant_id": "t",
                "space_id": "s",
                "narrative_thread_completed": True,
            },
            phase="R2",
        )

        await episodic_writer.write([write], mock_uow)

        values = mock_uow.connection.execute.call_args_list[0][0][1:]
        assert len(values) == 35

    @pytest.mark.asyncio
    async def test_insert_completed_true(self, episodic_writer, mock_uow):
        write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={
                "episode_id": "epi_001",
                "tenant_id": "t",
                "space_id": "s",
                "narrative_thread_completed": True,
            },
            phase="R2",
        )

        await episodic_writer.write([write], mock_uow)

        values = mock_uow.connection.execute.call_args_list[0][0][1:]
        assert values[-1] is True

    @pytest.mark.asyncio
    async def test_insert_completed_default_false(self, episodic_writer, mock_uow):
        write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={
                "episode_id": "epi_001",
                "tenant_id": "t",
                "space_id": "s",
            },
            phase="R2",
        )

        await episodic_writer.write([write], mock_uow)

        values = mock_uow.connection.execute.call_args_list[0][0][1:]
        assert values[-1] is False


# ============================================================================
# Issue 5.2.2: Assembler includes narrative_thread_completed
# ============================================================================


class TestAssemblerCompletion:

    def test_record_data_has_completed_field(self, assembler):
        events = {"e1": _make_event_state("e1")}
        cluster = _make_cluster("epi_001", ["e1"])

        writes = assembler.assemble_epi_writes([cluster], events)
        data = writes[0].record_data

        assert "narrative_thread_completed" in data
        assert data["narrative_thread_completed"] is False


# ============================================================================
# Issue 5.2.3: log_thread_completion observability
# ============================================================================


class TestLogThreadCompletion:

    def test_emits_structured_log(self, caplog):
        """log_thread_completion emits INFO with structured extra."""
        prior = _prior_episodes("EXPOSITION", "RISING_ACTION")

        with caplog.at_level(logging.INFO, logger="k0.pipelines.p03.phases.r2_episodic_integrator"):
            log_thread_completion(
                thread_id="planning_birthday",
                tenant_id="family_abc",
                completed_episode_id="epi_004",
                current_arc_position="CLIMAX",
                current_start_time=1700500000000,
                prior_episodes=prior,
            )

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.message == "NARRATIVE_THREAD_COMPLETED"
        assert record.topic == "narrative.thread.completed.v1"
        assert record.thread_id == "planning_birthday"
        assert record.total_episodes == 3

    def test_episode_chain_chronological(self, caplog):
        """Episode chain should be sorted by start_time_utc ascending."""
        prior = [
            {
                "episode_id": "epi_B",
                "narrative_arc_position": "RISING_ACTION",
                "start_time_utc": 1700200000000,
                "end_time_utc": 1700203600000,
                "episode_summary": "B",
            },
            {
                "episode_id": "epi_A",
                "narrative_arc_position": "EXPOSITION",
                "start_time_utc": 1700000000000,
                "end_time_utc": 1700003600000,
                "episode_summary": "A",
            },
        ]

        with caplog.at_level(logging.INFO, logger="k0.pipelines.p03.phases.r2_episodic_integrator"):
            log_thread_completion(
                thread_id="t1",
                tenant_id="t",
                completed_episode_id="epi_C",
                current_arc_position="CLIMAX",
                current_start_time=1700400000000,
                prior_episodes=prior,
            )

        chain = caplog.records[0].episode_chain
        # epi_A (earliest) should be first, epi_C (current) should be last
        assert chain[0]["episode_id"] == "epi_A"
        assert chain[1]["episode_id"] == "epi_B"
        assert chain[2]["episode_id"] == "epi_C"

    def test_span_days_calculated(self, caplog):
        """span_days should reflect time from first to last episode."""
        # 3 days apart in ms
        prior = [
            {
                "episode_id": "epi_A",
                "narrative_arc_position": "EXPOSITION",
                "start_time_utc": 1700000000000,
                "end_time_utc": 1700003600000,
                "episode_summary": "A",
            },
        ]
        # current start = 3 days later
        current_start = 1700000000000 + 3 * 86_400_000

        with caplog.at_level(logging.INFO, logger="k0.pipelines.p03.phases.r2_episodic_integrator"):
            log_thread_completion(
                thread_id="t1",
                tenant_id="t",
                completed_episode_id="epi_B",
                current_arc_position="RESOLUTION",
                current_start_time=current_start,
                prior_episodes=prior,
            )

        assert caplog.records[0].span_days == 3.0
