"""
Tests for QuarantineAutoReleaseJob — Issue 6.2.14.

Tests auto-release job functionality including:
- Signal release after retention period
- Batch processing
- Database updates for both tables
- Metrics emission
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.pipelines.p03.maintenance.quarantine_cleanup import (
    AutoReleaseResult,
    QuarantineAutoReleaseJob,
    create_auto_release_job,
)


class TestAutoReleaseResult:
    """Test AutoReleaseResult dataclass."""

    def test_result_creation(self) -> None:
        """Test AutoReleaseResult can be created."""
        result = AutoReleaseResult(
            signals_released=10,
            signals_failed=2,
            duration_ms=150.0,
            errors=["error1", "error2"],
        )

        assert result.signals_released == 10
        assert result.signals_failed == 2
        assert result.duration_ms == 150.0
        assert len(result.errors) == 2

    def test_result_defaults(self) -> None:
        """Test AutoReleaseResult default values."""
        result = AutoReleaseResult(
            signals_released=5,
            signals_failed=0,
            duration_ms=100.0,
        )

        assert result.errors == []

    def test_total_processed(self) -> None:
        """Test total_processed property."""
        result = AutoReleaseResult(
            signals_released=10,
            signals_failed=2,
            duration_ms=100.0,
        )

        assert result.total_processed == 12

    def test_success_rate_all_success(self) -> None:
        """Test success_rate when all succeed."""
        result = AutoReleaseResult(
            signals_released=10,
            signals_failed=0,
            duration_ms=100.0,
        )

        assert result.success_rate == 100.0

    def test_success_rate_partial(self) -> None:
        """Test success_rate with failures."""
        result = AutoReleaseResult(
            signals_released=8,
            signals_failed=2,
            duration_ms=100.0,
        )

        assert result.success_rate == 80.0

    def test_success_rate_no_processed(self) -> None:
        """Test success_rate when nothing processed."""
        result = AutoReleaseResult(
            signals_released=0,
            signals_failed=0,
            duration_ms=100.0,
        )

        assert result.success_rate == 100.0


class TestQuarantineAutoReleaseJob:
    """Test QuarantineAutoReleaseJob class."""

    def test_default_configuration(self) -> None:
        """Test job with default configuration."""
        job = QuarantineAutoReleaseJob()

        assert job.batch_size == 100
        assert job.JOB_NAME == "p03_quarantine_auto_release"
        assert job.DEFAULT_INTERVAL_SECONDS == 900

    def test_custom_configuration(self) -> None:
        """Test job with custom configuration."""
        job = QuarantineAutoReleaseJob(batch_size=50)

        assert job.batch_size == 50

    def test_create_job_config(self) -> None:
        """Test job config generation for scheduler."""
        config = QuarantineAutoReleaseJob.create_job_config()

        assert config["name"] == "p03_quarantine_auto_release"
        assert config["interval_seconds"] == 900
        assert config["enabled"] is True

    @pytest.mark.asyncio
    async def test_run_with_no_signals(self) -> None:
        """Test run when no signals ready for release."""
        job = QuarantineAutoReleaseJob()

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])  # No signals ready

        result = await job.run(connection=conn)

        assert result.signals_released == 0
        assert result.signals_failed == 0
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_run_releases_ready_signals(self) -> None:
        """Test run releases signals past auto_release_at."""
        job = QuarantineAutoReleaseJob()

        conn = AsyncMock()
        # First batch has signals, second is empty
        conn.fetch = AsyncMock(
            side_effect=[
                [
                    {
                        "quarantine_id": "q1",
                        "signal_id": "s1",
                        "space_id": "space_1",
                    },
                    {
                        "quarantine_id": "q2",
                        "signal_id": "s2",
                        "space_id": "space_1",
                    },
                ],
                [],  # No more signals
            ]
        )
        conn.execute = AsyncMock()

        result = await job.run(connection=conn)

        assert result.signals_released == 2
        assert result.signals_failed == 0
        # 2 signals * 2 updates each = 4 execute calls
        assert conn.execute.call_count == 4

    @pytest.mark.asyncio
    async def test_run_handles_release_failure(self) -> None:
        """Test run handles individual signal release failures."""
        job = QuarantineAutoReleaseJob()

        conn = AsyncMock()
        conn.fetch = AsyncMock(
            side_effect=[
                [
                    {"quarantine_id": "q1", "signal_id": "s1", "space_id": "sp1"},
                    {"quarantine_id": "q2", "signal_id": "s2", "space_id": "sp1"},
                ],
                [],
            ]
        )
        # First execute succeeds, second fails
        conn.execute = AsyncMock(
            side_effect=[
                None,  # q1 quarantine update
                None,  # q1 signal update
                Exception("DB error"),  # q2 quarantine update fails
            ]
        )

        result = await job.run(connection=conn)

        assert result.signals_released == 1
        assert result.signals_failed == 1
        assert len(result.errors) == 1
        assert "q2" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_batch_processing(self) -> None:
        """Test run processes in batches."""
        job = QuarantineAutoReleaseJob(batch_size=2)

        conn = AsyncMock()
        # 3 batches: 2, 2, empty
        conn.fetch = AsyncMock(
            side_effect=[
                [
                    {"quarantine_id": "q1", "signal_id": "s1", "space_id": "sp1"},
                    {"quarantine_id": "q2", "signal_id": "s2", "space_id": "sp1"},
                ],
                [
                    {"quarantine_id": "q3", "signal_id": "s3", "space_id": "sp1"},
                    {"quarantine_id": "q4", "signal_id": "s4", "space_id": "sp1"},
                ],
                [],
            ]
        )
        conn.execute = AsyncMock()

        result = await job.run(connection=conn)

        assert result.signals_released == 4
        assert conn.fetch.call_count == 3  # 3 fetch calls

    @pytest.mark.asyncio
    async def test_run_updates_quarantine_correctly(self) -> None:
        """Test run updates st_feedback_quarantine correctly."""
        job = QuarantineAutoReleaseJob()

        conn = AsyncMock()
        conn.fetch = AsyncMock(
            side_effect=[
                [{"quarantine_id": "q1", "signal_id": "s1", "space_id": "sp1"}],
                [],
            ]
        )
        conn.execute = AsyncMock()

        await job.run(connection=conn)

        # Check first execute call (quarantine update)
        first_call = conn.execute.call_args_list[0]
        sql = first_call[0][0]
        assert "st_feedback_quarantine" in sql
        assert "decision = $3" in sql or "decision =" in sql
        assert first_call[0][2] == "AUTO"  # reviewed_by
        assert first_call[0][3] == "RELEASE"  # decision

    @pytest.mark.asyncio
    async def test_run_updates_signals_correctly(self) -> None:
        """Test run updates st_feedback_signals correctly."""
        job = QuarantineAutoReleaseJob()

        conn = AsyncMock()
        conn.fetch = AsyncMock(
            side_effect=[
                [{"quarantine_id": "q1", "signal_id": "s1", "space_id": "sp1"}],
                [],
            ]
        )
        conn.execute = AsyncMock()

        await job.run(connection=conn)

        # Check second execute call (signal update)
        second_call = conn.execute.call_args_list[1]
        sql = second_call[0][0]
        assert "st_feedback_signals" in sql
        assert "quarantine_status" in sql
        assert second_call[0][1] == "RELEASED"

    @pytest.mark.asyncio
    async def test_run_single_success(self) -> None:
        """Test run_single releases specific signal."""
        job = QuarantineAutoReleaseJob()

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"quarantine_id": "q1", "signal_id": "s1"})
        conn.execute = AsyncMock()

        result = await job.run_single("q1", connection=conn)

        assert result is True
        assert conn.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_run_single_not_found(self) -> None:
        """Test run_single returns False if not found."""
        job = QuarantineAutoReleaseJob()

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)

        result = await job.run_single("nonexistent", connection=conn)

        assert result is False

    @pytest.mark.asyncio
    async def test_run_single_already_reviewed(self) -> None:
        """Test run_single returns False if already reviewed."""
        job = QuarantineAutoReleaseJob()

        conn = AsyncMock()
        # Query includes "decision IS NULL" filter
        conn.fetchrow = AsyncMock(return_value=None)

        result = await job.run_single("already_reviewed", connection=conn)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_pending_count(self) -> None:
        """Test get_pending_count returns correct count."""
        job = QuarantineAutoReleaseJob()

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"count": 15})

        count = await job.get_pending_count(connection=conn)

        assert count == 15

    @pytest.mark.asyncio
    async def test_get_pending_count_none(self) -> None:
        """Test get_pending_count returns 0 on None."""
        job = QuarantineAutoReleaseJob()

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)

        count = await job.get_pending_count(connection=conn)

        assert count == 0

    @pytest.mark.asyncio
    async def test_get_upcoming_count(self) -> None:
        """Test get_upcoming_count for scheduling."""
        job = QuarantineAutoReleaseJob()

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"count": 25})

        count = await job.get_upcoming_count(hours=24, connection=conn)

        assert count == 25

    @pytest.mark.asyncio
    async def test_metrics_emission_on_success(self) -> None:
        """Test metrics are emitted on successful run."""
        metrics = MagicMock()
        job = QuarantineAutoReleaseJob(metrics=metrics)

        conn = AsyncMock()
        conn.fetch = AsyncMock(
            side_effect=[
                [{"quarantine_id": "q1", "signal_id": "s1", "space_id": "sp1"}],
                [],
            ]
        )
        conn.execute = AsyncMock()

        await job.run(connection=conn)

        # Check released counter
        assert metrics.emit.called
        emit_call = metrics.emit.call_args
        assert emit_call[0][0] == "p03_quarantine_auto_released_total"
        assert emit_call[0][1] == 1.0

        # Check duration histogram
        assert metrics.observe.called

    @pytest.mark.asyncio
    async def test_metrics_emission_on_failures(self) -> None:
        """Test failure metrics are emitted."""
        metrics = MagicMock()
        job = QuarantineAutoReleaseJob(metrics=metrics)

        conn = AsyncMock()
        conn.fetch = AsyncMock(
            side_effect=[
                [{"quarantine_id": "q1", "signal_id": "s1", "space_id": "sp1"}],
                [],
            ]
        )
        conn.execute = AsyncMock(side_effect=Exception("DB error"))

        await job.run(connection=conn)

        # Check failure counter
        emit_calls = [call[0][0] for call in metrics.emit.call_args_list]
        assert "p03_quarantine_auto_release_failures_total" in emit_calls

    @pytest.mark.asyncio
    async def test_no_metrics_on_empty_run(self) -> None:
        """Test no release metrics when nothing released."""
        metrics = MagicMock()
        job = QuarantineAutoReleaseJob(metrics=metrics)

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])

        await job.run(connection=conn)

        # Only observe (duration) should be called, not emit
        assert not metrics.emit.called
        assert metrics.observe.called


class TestCreateAutoReleaseJob:
    """Test factory function."""

    def test_create_with_defaults(self) -> None:
        """Test factory with default parameters."""
        job = create_auto_release_job()

        assert isinstance(job, QuarantineAutoReleaseJob)
        assert job.batch_size == 100

    def test_create_with_custom_params(self) -> None:
        """Test factory with custom parameters."""
        metrics = MagicMock()
        tracer = MagicMock()
        job = create_auto_release_job(
            batch_size=50,
            metrics=metrics,
            tracer=tracer,
        )

        assert job.batch_size == 50
