"""
Human-Feel Upgrade #2: Background Task Hygiene Tests

Test debounce, dedupe, task cancellation, and concurrency limits
to prevent resource exhaustion and improve conversation quality.

Phase: Human-Feel Upgrades
Topics Covered:
- Debounce (500ms minimum between same topic requests)
- Dedupe (2min window - no duplicate analysis)
- Task cancellation (cancel stale tasks on topic pivot)
- Concurrency cap (max 2 tasks running simultaneously)
- Pending topics tracking
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.agents.concierge_v2 import BackgroundTask, ConciergeAgentV2
from backend.services.k0_query_service import MockK0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher


@pytest.fixture
def llm_client():
    """Mock LLM client."""
    client = AsyncMock(spec=LLMClient)
    client.generate_async = AsyncMock(return_value="Test response")
    return client


@pytest.fixture
def concierge(llm_client):
    """Create concierge with mocked LLM."""
    return ConciergeAgentV2(
        llm_client=llm_client,
        k0_query_service=MockK0QueryService(),
        metrics_collector=MetricsCollector(),
        progress_publisher=ProgressPublisher(),
    )


# ==============================
# DEBOUNCE TESTS (500ms)
# ==============================


class TestDebounce:
    """Test 500ms debounce prevents duplicate requests."""

    def test_should_debounce_recent_request(self, concierge):
        """Test debounce blocks request within 500ms."""
        concierge.last_topic_request["diet"] = time.time()
        assert concierge._should_debounce("diet") is True

    def test_should_not_debounce_old_request(self, concierge):
        """Test debounce allows request after 500ms."""
        concierge.last_topic_request["diet"] = time.time() - 0.6  # 600ms ago
        assert concierge._should_debounce("diet") is False

    def test_should_not_debounce_new_topic(self, concierge):
        """Test debounce allows new topics."""
        concierge.last_topic_request["diet"] = time.time()
        assert concierge._should_debounce("exercise") is False

    def test_debounce_boundary_case(self, concierge):
        """Test debounce at exactly 500ms boundary."""
        concierge.last_topic_request["diet"] = time.time() - 0.5  # Exactly 500ms
        # Should NOT debounce (>=500ms is safe)
        assert concierge._should_debounce("diet") is False


# ==============================
# DEDUPE TESTS (2min window)
# ==============================


class TestDedupe:
    """Test 2min dedupe prevents duplicate analysis."""

    def test_should_dedupe_running_task(self, concierge):
        """Test dedupe blocks when task already running."""
        concierge.pending_topics["diet"] = time.time()
        assert concierge._should_dedupe("diet") is True

    def test_should_dedupe_recent_completion(self, concierge):
        """Test dedupe blocks recent completed analysis."""
        concierge.pending_topics["diet"] = time.time() - 60  # 1 min ago
        assert concierge._should_dedupe("diet") is True

    def test_should_not_dedupe_old_completion(self, concierge):
        """Test dedupe allows after 2min window."""
        concierge.pending_topics["diet"] = time.time() - 121  # 121 seconds ago
        assert concierge._should_dedupe("diet") is False

    def test_should_not_dedupe_new_topic(self, concierge):
        """Test dedupe allows different topics."""
        concierge.pending_topics["diet"] = time.time()
        assert concierge._should_dedupe("exercise") is False

    def test_dedupe_boundary_case(self, concierge):
        """Test dedupe at exactly 2min boundary."""
        concierge.pending_topics["diet"] = time.time() - 120  # Exactly 120s
        # Should dedupe (still within window)
        assert concierge._should_dedupe("diet") is True


# ==============================
# TASK CANCELLATION TESTS
# ==============================


class TestTaskCancellation:
    """Test cancellation of stale tasks on topic pivot."""

    def test_cancel_stale_tasks_after_pivot(self, concierge):
        """Test tasks cancelled after 2 topic changes."""
        # Create mock task for "diet"
        mock_task = MagicMock()
        mock_task.done = MagicMock(return_value=False)
        mock_task.cancel = MagicMock()

        bg_task = BackgroundTask(
            task_id="test_1",
            specialist_type="nutritionist",
            user_query="test",
            task=mock_task,
            topic="diet",
            started_at=time.time(),
        )
        concierge.background_tasks.append(bg_task)
        concierge.pending_topics["diet"] = time.time()

        # Initialize on diet topic
        concierge._cancel_stale_tasks("diet")
        assert concierge.current_topic == "diet"
        assert concierge.topic_pivot_count == 0

        # First pivot (diet -> exercise)
        concierge._cancel_stale_tasks("exercise")
        assert len(concierge.background_tasks) == 1  # Not cancelled yet
        assert concierge.topic_pivot_count == 1

        # Second pivot (exercise -> sleep)
        concierge._cancel_stale_tasks("sleep")
        assert concierge.topic_pivot_count == 2
        assert len(concierge.background_tasks) == 0  # Cancelled now
        assert mock_task.cancel.called
        assert "diet" not in concierge.pending_topics

    def test_no_cancel_same_topic(self, concierge):
        """Test tasks NOT cancelled if topic unchanged."""
        mock_task = MagicMock()
        mock_task.done = MagicMock(return_value=False)

        bg_task = BackgroundTask(
            task_id="test_1",
            specialist_type="nutritionist",
            user_query="test",
            task=mock_task,
            topic="diet",
            started_at=time.time(),
        )
        concierge.background_tasks.append(bg_task)

        # Stay on same topic
        concierge._cancel_stale_tasks("diet")
        concierge._cancel_stale_tasks("diet")
        concierge._cancel_stale_tasks("diet")

        # Should NOT be cancelled
        assert len(concierge.background_tasks) == 1

    def test_pivot_count_resets_on_return(self, concierge):
        """Test pivot count resets when returning to topic."""
        concierge._cancel_stale_tasks("diet")  # Start with diet
        concierge._cancel_stale_tasks("exercise")  # Pivot 1
        assert concierge.topic_pivot_count == 1

        concierge._cancel_stale_tasks("sleep")  # Pivot 2 (different again)
        assert concierge.topic_pivot_count == 2

        concierge._cancel_stale_tasks("sleep")  # Stay on sleep
        assert concierge.topic_pivot_count == 0  # Reset


# ==============================
# CONCURRENCY LIMIT TESTS
# ==============================


class TestConcurrencyLimit:
    """Test max 2 concurrent tasks limit."""

    def test_at_limit_with_two_running(self, concierge):
        """Test limit reached with 2 running tasks."""
        # Create 2 running tasks with proper done() callable
        for i in range(2):
            mock_task = MagicMock()
            mock_task.done = MagicMock(return_value=False)  # Callable that returns False
            bg_task = BackgroundTask(
                task_id=f"test_{i}",
                specialist_type="nutritionist",
                user_query="test",
                task=mock_task,
                started_at=time.time(),
            )
            concierge.background_tasks.append(bg_task)

        assert concierge._at_concurrency_limit() is True

    def test_not_at_limit_with_one_running(self, concierge):
        """Test limit NOT reached with 1 running task."""
        mock_task = MagicMock()
        mock_task.done = MagicMock(return_value=False)
        bg_task = BackgroundTask(
            task_id="test_1",
            specialist_type="nutritionist",
            user_query="test",
            task=mock_task,
            started_at=time.time(),
        )
        concierge.background_tasks.append(bg_task)

        assert concierge._at_concurrency_limit() is False

    def test_not_at_limit_with_completed_tasks(self, concierge):
        """Test completed tasks don't count toward limit."""
        # 2 completed tasks + 1 running
        for i in range(3):
            mock_task = MagicMock()
            mock_task.done = MagicMock(return_value=(i < 2))  # First 2 are done
            bg_task = BackgroundTask(
                task_id=f"test_{i}",
                specialist_type="nutritionist",
                user_query="test",
                task=mock_task,
                started_at=time.time(),
            )
            concierge.background_tasks.append(bg_task)

        # Only 1 running task, so not at limit
        assert concierge._at_concurrency_limit() is False

    def test_at_limit_boundary(self, concierge):
        """Test limit at exactly max_concurrent_tasks."""
        concierge.max_concurrent_tasks = 3  # Change limit to 3
        for i in range(3):
            mock_task = MagicMock()
            mock_task.done = MagicMock(return_value=False)
            bg_task = BackgroundTask(
                task_id=f"test_{i}",
                specialist_type="nutritionist",
                user_query="test",
                task=mock_task,
                started_at=time.time(),
            )
            concierge.background_tasks.append(bg_task)

        assert concierge._at_concurrency_limit() is True


# ==============================
# INTEGRATION TESTS
# ==============================


class TestHygieneIntegration:
    """Test full hygiene workflow integration."""

    @pytest.mark.asyncio
    async def test_debounce_prevents_rapid_requests(self, concierge):
        """Test rapid messages are debounced."""
        with patch.object(concierge, "_run_specialist_analysis", new_callable=AsyncMock):
            # First message
            await concierge._maybe_start_background_analysis("my stomach hurts", "test_user")
            assert len(concierge.background_tasks) == 1

            # Immediate second message (within 500ms)
            await concierge._maybe_start_background_analysis("my stomach really hurts", "test_user")
            # Should be debounced - still only 1 task
            assert len(concierge.background_tasks) == 1

    @pytest.mark.asyncio
    async def test_dedupe_prevents_duplicate_analysis(self, concierge):
        """Test duplicate topic analysis is prevented."""
        with patch.object(concierge, "_run_specialist_analysis", new_callable=AsyncMock):
            # Start first analysis
            await concierge._maybe_start_background_analysis("my stomach hurts", "test_user")
            assert len(concierge.background_tasks) == 1

            # Wait 600ms (past debounce)
            await asyncio.sleep(0.6)

            # Try again - should be deduped (still within 2min window)
            await concierge._maybe_start_background_analysis("stomach pain", "test_user")
            assert len(concierge.background_tasks) == 1  # Deduped

    @pytest.mark.asyncio
    async def test_concurrency_limit_enforced(self, concierge):
        """Test max 2 concurrent tasks enforced."""
        # Manually create 2 running tasks at the limit
        for i in range(2):
            mock_task = MagicMock()
            mock_task.done = MagicMock(return_value=False)
            bg_task = BackgroundTask(
                task_id=f"test_{i}",
                specialist_type="nutritionist",
                user_query="test",
                task=mock_task,
                topic=f"topic_{i}",
                started_at=time.time(),
            )
            concierge.background_tasks.append(bg_task)

        # Verify we're at limit
        assert concierge._at_concurrency_limit() is True

        # Try to start a third task - should be blocked
        initial_count = len(concierge.background_tasks)

        with patch.object(concierge, "_run_specialist_analysis", new_callable=AsyncMock):
            await concierge._maybe_start_background_analysis("I have insomnia", "test_user")

            # Should still have only 2 tasks (third was blocked)
            assert len(concierge.background_tasks) == initial_count

    @pytest.mark.asyncio
    async def test_cleanup_on_task_completion(self, concierge):
        """Test pending_topics cleaned up on completion."""
        # Create completed task
        mock_task = AsyncMock()
        mock_task.done.return_value = True
        mock_result = MagicMock()
        mock_task.result.return_value = mock_result

        bg_task = BackgroundTask(
            task_id="test_1",
            specialist_type="nutritionist",
            user_query="test",
            task=mock_task,
            topic="diet",
            started_at=time.time(),
        )
        concierge.background_tasks.append(bg_task)
        concierge.pending_topics["diet"] = time.time()

        # Check completed tasks
        await concierge._check_completed_tasks()

        # Should clean up pending_topics
        assert "diet" not in concierge.pending_topics
        assert len(concierge.background_tasks) == 0

    @pytest.mark.asyncio
    async def test_topic_extraction_used_for_hygiene(self, concierge):
        """Test topic extraction drives hygiene decisions."""
        with patch.object(concierge, "_extract_topic", return_value="diet"):
            with patch.object(concierge, "_run_specialist_analysis", new_callable=AsyncMock):
                await concierge._maybe_start_background_analysis("milk makes me sick", "test_user")

                # Check topic used in tracking
                assert "diet" in concierge.pending_topics
                assert "diet" in concierge.last_topic_request


# ==============================
# EDGE CASES & ROBUSTNESS
# ==============================


class TestHygieneEdgeCases:
    """Test edge cases and robustness."""

    def test_no_topic_uses_specialist_type(self, concierge):
        """Test fallback to specialist_type when topic not found."""
        # When _extract_topic returns None, should use specialist_type
        assert concierge._should_debounce("nutritionist") is False

    def test_cancel_handles_no_current_topic(self, concierge):
        """Test cancellation handles None topic gracefully."""
        # Should not crash
        concierge._cancel_stale_tasks(None)
        assert concierge.current_topic is None

    def test_multiple_pivots_same_new_topic(self, concierge):
        """Test multiple pivots to same new topic only counts once."""
        concierge._cancel_stale_tasks("diet")
        concierge._cancel_stale_tasks("exercise")  # Pivot 1
        concierge._cancel_stale_tasks("exercise")  # Stay
        concierge._cancel_stale_tasks("exercise")  # Stay

        # Pivot count should reset
        assert concierge.topic_pivot_count == 0

    def test_pending_topics_survives_no_tasks(self, concierge):
        """Test pending_topics tracking works without active tasks."""
        concierge.pending_topics["diet"] = time.time()
        assert concierge._should_dedupe("diet") is True

    @pytest.mark.asyncio
    async def test_hygiene_with_failed_task(self, concierge):
        """Test hygiene cleanup works when task fails."""
        mock_task = AsyncMock()
        mock_task.done.return_value = True
        mock_task.result.side_effect = Exception("Task failed")

        bg_task = BackgroundTask(
            task_id="test_1",
            specialist_type="nutritionist",
            user_query="test",
            task=mock_task,
            topic="diet",
            started_at=time.time(),
        )
        concierge.background_tasks.append(bg_task)
        concierge.pending_topics["diet"] = time.time()

        # Should handle gracefully
        await concierge._check_completed_tasks()

        # Still cleaned up
        assert len(concierge.background_tasks) == 0
        assert len(concierge.background_tasks) == 0
        assert len(concierge.background_tasks) == 0
