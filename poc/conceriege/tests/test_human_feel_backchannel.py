"""
UPGRADE #3: Tests for Backchannel & Timing (Human-Feel Improvements)

Covers:
- Backchannel detection (idle + tasks running)
- Backchannel cooldown (prevents spam)
- Backchannel message variety
- Short-then-expand timing pattern
- Quick acknowledgment selection
- Timing tracking updates
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.agents.concierge_v2 import ConciergeAgentV2
from backend.services.k0_query_service import MockK0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher


@pytest.fixture
def llm_client():
    """Mock LLM client."""
    client = AsyncMock(spec=LLMClient)
    client.generate_async = AsyncMock(return_value="Test response")
    client.chat = AsyncMock(return_value="Test response")
    return client


@pytest.fixture
def agent(llm_client):
    """Create ConciergeAgentV2 instance for testing"""
    return ConciergeAgentV2(
        llm_client=llm_client,
        k0_query_service=MockK0QueryService(),
        metrics_collector=MetricsCollector(),
        progress_publisher=ProgressPublisher(),
    )


# ============================================================================
# BACKCHANNEL DETECTION TESTS
# ============================================================================


def test_should_show_backchannel_when_idle_and_tasks_running(agent):
    """Should show backchannel when user idle >1.2s AND tasks running"""
    # Simulate user idle for 2 seconds
    agent.last_user_message_time = time.time() - 2.0
    agent.last_response_time = time.time() - 5.0  # No recent backchannel

    # Add running background task
    mock_task = MagicMock()
    mock_task.task.done.return_value = False
    agent.background_tasks.append(mock_task)

    assert agent._should_show_backchannel() is True


def test_should_not_show_backchannel_when_not_idle(agent):
    """Should NOT show backchannel when user just sent message (<1.2s ago)"""
    # User just sent message (0.5s ago)
    agent.last_user_message_time = time.time() - 0.5
    agent.last_response_time = time.time() - 5.0

    # Add running task
    mock_task = MagicMock()
    mock_task.task.done.return_value = False
    agent.background_tasks.append(mock_task)

    assert agent._should_show_backchannel() is False


def test_should_not_show_backchannel_when_no_tasks_running(agent):
    """Should NOT show backchannel when no background tasks running"""
    # User idle for 2 seconds
    agent.last_user_message_time = time.time() - 2.0
    agent.last_response_time = time.time() - 5.0

    # No running tasks (all completed)
    mock_task = MagicMock()
    mock_task.task.done.return_value = True
    agent.background_tasks.append(mock_task)

    assert agent._should_show_backchannel() is False


def test_backchannel_cooldown_prevents_spam(agent):
    """Should NOT show backchannel if shown recently (3s cooldown)"""
    # User idle for 2 seconds
    agent.last_user_message_time = time.time() - 2.0

    # But backchannel shown 1 second ago (within 3s cooldown)
    agent.last_response_time = time.time() - 1.0

    # Add running task
    mock_task = MagicMock()
    mock_task.task.done.return_value = False
    agent.background_tasks.append(mock_task)

    assert agent._should_show_backchannel() is False


def test_backchannel_allowed_after_cooldown(agent):
    """Should allow backchannel after 3-second cooldown"""
    # User idle for 2 seconds
    agent.last_user_message_time = time.time() - 2.0

    # Last backchannel was 4 seconds ago (past 3s cooldown)
    agent.last_response_time = time.time() - 4.0

    # Add running task
    mock_task = MagicMock()
    mock_task.task.done.return_value = False
    agent.background_tasks.append(mock_task)

    assert agent._should_show_backchannel() is True


def test_backchannel_with_empty_background_tasks(agent):
    """Should NOT show backchannel when background_tasks list is empty"""
    # User idle for 2 seconds
    agent.last_user_message_time = time.time() - 2.0
    agent.last_response_time = time.time() - 5.0

    # No tasks at all
    agent.background_tasks = []

    assert agent._should_show_backchannel() is False


def test_backchannel_with_multiple_running_tasks(agent):
    """Should show backchannel when ANY task is running"""
    # User idle for 2 seconds
    agent.last_user_message_time = time.time() - 2.0
    agent.last_response_time = time.time() - 5.0

    # Mix of completed and running tasks
    completed_task = MagicMock()
    completed_task.task.done.return_value = True

    running_task1 = MagicMock()
    running_task1.task.done.return_value = False

    running_task2 = MagicMock()
    running_task2.task.done.return_value = False

    agent.background_tasks = [completed_task, running_task1, running_task2]

    assert agent._should_show_backchannel() is True


# ============================================================================
# BACKCHANNEL MESSAGE VARIETY TESTS
# ============================================================================


def test_get_backchannel_message_returns_valid_message(agent):
    """Should return one of 8 valid backchannel messages"""
    valid_messages = [
        "one sec...",
        "hmm...",
        "let me check that...",
        "pulling some dots together...",
        "looking into it...",
        "gimme a moment...",
        "checking...",
        "hold on...",
    ]

    message = agent._get_backchannel_message()
    assert message in valid_messages


def test_backchannel_message_variety(agent):
    """Should produce variety across multiple calls (probabilistic test)"""
    messages = [agent._get_backchannel_message() for _ in range(20)]
    unique_messages = set(messages)

    # With 20 calls, should get at least 4 unique messages (statistical likelihood)
    assert len(unique_messages) >= 4


def test_backchannel_messages_all_lowercase(agent):
    """All backchannel messages should be lowercase for natural feel"""
    for _ in range(10):
        message = agent._get_backchannel_message()
        assert message == message.lower()


def test_backchannel_messages_end_with_ellipsis(agent):
    """All backchannel messages should end with '...' for natural feel"""
    for _ in range(10):
        message = agent._get_backchannel_message()
        assert message.endswith("...")


# ============================================================================
# SHORT-THEN-EXPAND TIMING PATTERN TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_respond_with_timing_includes_quick_ack(agent):
    """Should include quick acknowledgment at start"""
    valid_acks = [
        "got it",
        "okay",
        "right",
        "makes sense",
        "gotcha",
        "understood",
        "yep",
        "sure",
        "good question",
        "let me think",
        "hmm",
        "interesting",
        "great question",
    ]

    async def mock_generate():
        return "detailed response here"

    response = await agent._respond_with_timing(
        "test message", mock_generate, delay_range=(0.0, 0.01)
    )

    # Response should start with one of the quick acks
    first_word = response.split(".")[0].strip()
    assert first_word in valid_acks


@pytest.mark.asyncio
async def test_respond_with_timing_has_delay(agent):
    """Should have noticeable delay between ack and detail (400-900ms)"""

    async def mock_generate():
        return "detailed response"

    start_time = time.time()
    _ = await agent._respond_with_timing("test message", mock_generate, delay_range=(0.4, 0.9))
    elapsed = time.time() - start_time

    # Should take at least 0.4 seconds (minimum delay)
    assert elapsed >= 0.4
    assert elapsed <= 1.0  # Max delay + execution overhead


@pytest.mark.asyncio
async def test_respond_with_timing_combines_ack_and_detail(agent):
    """Should combine quick ack with detailed response"""

    async def mock_generate():
        return "this is the detailed explanation"

    response = await agent._respond_with_timing(
        "test message", mock_generate, delay_range=(0.0, 0.01)
    )

    # Should have format: "{ack}. {detail}"
    assert ". " in response
    parts = response.split(". ", 1)
    assert len(parts) == 2
    assert parts[1] == "this is the detailed explanation"


@pytest.mark.asyncio
async def test_question_specific_acks(agent):
    """Should use question-specific acks for questions"""
    question_acks = ["good question", "let me think", "hmm", "interesting", "great question"]

    async def mock_generate():
        return "answer here"

    # Test multiple times to catch question-specific acks
    found_question_ack = False
    for _ in range(20):
        response = await agent._respond_with_timing(
            "why does this happen?", mock_generate, delay_range=(0.0, 0.01)
        )
        first_word = response.split(".")[0].strip()
        if first_word in question_acks:
            found_question_ack = True
            break

    # With 20 attempts, should find at least one question-specific ack
    assert found_question_ack


@pytest.mark.asyncio
async def test_respond_with_timing_custom_delay_range(agent):
    """Should respect custom delay range"""

    async def mock_generate():
        return "response"

    start_time = time.time()
    _ = await agent._respond_with_timing("test", mock_generate, delay_range=(0.1, 0.2))
    elapsed = time.time() - start_time

    # Should be within custom range (0.1-0.2s + overhead)
    assert elapsed >= 0.1
    assert elapsed <= 0.3


# ============================================================================
# TIMING TRACKING INTEGRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_process_message_updates_last_user_message_time(agent):
    """process_message should update last_user_message_time"""
    # Mock LLM response
    with patch.object(
        agent.llm_client, "generate_async", new=AsyncMock(return_value="mock response")
    ):
        before_time = time.time()
        await agent.process_message("user123", "test message")
        after_time = time.time()

        # last_user_message_time should be set between before and after
        assert agent.last_user_message_time >= before_time
        assert agent.last_user_message_time <= after_time


@pytest.mark.asyncio
async def test_process_message_updates_last_response_time(agent):
    """process_message should update last_response_time after responding"""
    # Mock LLM response
    with patch.object(
        agent.llm_client, "generate_async", new=AsyncMock(return_value="mock response")
    ):
        before_time = time.time()
        await agent.process_message("user123", "test message")
        after_time = time.time()

        # last_response_time should be set between before and after
        assert agent.last_response_time >= before_time
        assert agent.last_response_time <= after_time


@pytest.mark.asyncio
async def test_timing_tracking_persists_across_messages(agent):
    """Timing tracking should persist across multiple messages"""
    # Mock LLM response
    with patch.object(
        agent.llm_client, "generate_async", new=AsyncMock(return_value="mock response")
    ):
        # First message
        await agent.process_message("user123", "first message")
        first_message_time = agent.last_user_message_time

        # Small delay
        await asyncio.sleep(0.1)

        # Second message
        await agent.process_message("user123", "second message")
        second_message_time = agent.last_user_message_time

        # Times should be different and second should be later
        assert second_message_time > first_message_time


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


def test_backchannel_at_exact_threshold(agent):
    """Backchannel at exactly 1.2s threshold should NOT show (< check)"""
    # User idle for exactly 1.2 seconds (use slightly less to avoid FP precision issues)
    agent.last_user_message_time = time.time() - 1.1999
    agent.last_response_time = time.time() - 5.0

    # Add running task
    mock_task = MagicMock()
    mock_task.task.done.return_value = False
    agent.background_tasks.append(mock_task)

    # Should NOT show (requires > 1.2s, not >=)
    assert agent._should_show_backchannel() is False


def test_backchannel_just_over_threshold(agent):
    """Backchannel just over 1.2s threshold should show"""
    # User idle for 1.21 seconds (just over threshold)
    agent.last_user_message_time = time.time() - 1.21
    agent.last_response_time = time.time() - 5.0

    # Add running task
    mock_task = MagicMock()
    mock_task.task.done.return_value = False
    agent.background_tasks.append(mock_task)

    assert agent._should_show_backchannel() is True


def test_user_idle_threshold_default_value(agent):
    """user_idle_threshold should default to 1.2 seconds"""
    assert agent.user_idle_threshold == 1.2


@pytest.mark.asyncio
async def test_respond_with_timing_with_exception_in_generate(agent):
    """Should handle exceptions in generate_fn gracefully"""

    async def failing_generate():
        raise ValueError("test error")

    with pytest.raises(ValueError):
        await agent._respond_with_timing("test", failing_generate, delay_range=(0.0, 0.01))


@pytest.mark.asyncio
async def test_respond_with_timing_with_empty_response(agent):
    """Should handle empty detailed response"""

    async def empty_generate():
        return ""

    response = await agent._respond_with_timing("test", empty_generate, delay_range=(0.0, 0.01))

    # Should still have quick ack even if detail is empty
    assert len(response) > 0
    assert ". " in response
    assert ". " in response
    assert ". " in response
