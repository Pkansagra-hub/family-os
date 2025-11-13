"""
Integration tests for ProactiveAgent - SSE listener for K0 proactive ticks.

Tests SSE connection, event parsing, trigger handlers, reconnection logic.

Test scenarios:
  1. SSE connection establishment
  2. Trigger tick handling (notify_user, enrich_context, invoke_agent)
  3. Pattern tick handling
  4. Anomaly tick handling
  5. Reconnection on disconnect
  6. Graceful shutdown
  7. Statistics tracking

References:
  - Epic 4.2.1 - SSE Client Connection
  - Epic 4.2.2 - Proactive Trigger Handlers
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from l3_execution.agents.agent_base import AgentState
from l3_execution.agents.proactive_agent import ProactiveAgent


@pytest.fixture
def mock_groq_client():
    """Mock Groq client (not heavily used by ProactiveAgent)."""
    client = MagicMock()
    client.complete = AsyncMock(return_value={"content": "mock response"})
    return client


@pytest.fixture
def proactive_agent(mock_groq_client):
    """Create ProactiveAgent instance."""
    agent = ProactiveAgent(
        agent_id="proactive_001",
        session_id="session_test",
        groq_client=mock_groq_client,
        trace_id="trace_test",
        sse_url="http://localhost:8002/sse/stream",
    )
    return agent


@pytest.mark.asyncio
async def test_proactive_agent_initialization(proactive_agent):
    """Test ProactiveAgent initializes with correct properties."""
    assert proactive_agent.agent_id == "proactive_001"
    assert proactive_agent.agent_type == "proactive"
    assert proactive_agent.session_id == "session_test"
    assert proactive_agent.trace_id == "trace_test"
    assert proactive_agent.sse_url == "http://localhost:8002/sse/stream"
    assert proactive_agent.state == AgentState.PENDING
    assert proactive_agent.ticks_received == 0
    assert proactive_agent.trigger_ticks == 0
    assert proactive_agent.pattern_ticks == 0
    assert proactive_agent.anomaly_ticks == 0


@pytest.mark.asyncio
async def test_proactive_agent_lifecycle_active(proactive_agent):
    """Test ProactiveAgent transitions to ACTIVE and starts SSE listening."""
    # Mock health check to avoid actual network call
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        # Transition to WARMING
        await proactive_agent.transition_to(AgentState.WARMING)
        assert proactive_agent.state == AgentState.WARMING

    # Mock SSE connection to avoid actual network call
    with patch.object(proactive_agent, "_sse_listen_loop", new_callable=AsyncMock):
        # Transition to ACTIVE
        await proactive_agent.transition_to(AgentState.ACTIVE)
        assert proactive_agent.state == AgentState.ACTIVE

        # Verify SSE listening task started
        assert proactive_agent.sse_listen_task is not None


@pytest.mark.asyncio
async def test_trigger_tick_notify_user(proactive_agent):
    """Test _handle_trigger_tick with notify_user action - generates LLM response."""
    tick_data = {
        "trigger_id": "trigger_water_123",
        "time": "2025-11-05T14:30:00Z",
        "message": "Time to drink water!",
        "action": "notify_user",
        "metadata": {
            "daily_progress": "4/8",
        },
    }

    # Mock LLM call to return conversational notification
    mock_llm_response = {
        "content": "Hey! 💧 Just a friendly reminder to stay hydrated. You're doing great - 4 out of 8 glasses today! Time for another one?",
        "tokens": 25,
    }

    # Mock notification methods
    with patch.object(proactive_agent, "call_llm", new_callable=AsyncMock) as mock_llm:
        with patch.object(
            proactive_agent, "_stream_notification_to_user", new_callable=AsyncMock
        ) as mock_stream:
            with patch.object(
                proactive_agent, "_update_session_state_with_notification", new_callable=AsyncMock
            ):
                mock_llm.return_value = mock_llm_response

                await proactive_agent._handle_trigger_tick(tick_data)

                # Verify LLM was called with trigger context
                mock_llm.assert_called_once()
                call_args = mock_llm.call_args
                assert "Proactive reminder" in call_args.kwargs["user_input"]
                assert "Time to drink water!" in call_args.kwargs["user_input"]
                assert call_args.kwargs["temperature"] == 0.7

                # Verify notification streamed to user
                mock_stream.assert_called_once()
                notification_arg = mock_stream.call_args[0][0]
                assert "friendly reminder" in notification_arg
                assert "hydrated" in notification_arg

                # Verify metrics updated
                assert proactive_agent.trigger_ticks == 1


@pytest.mark.asyncio
async def test_trigger_tick_enrich_context(proactive_agent):
    """Test _handle_trigger_tick with enrich_context action."""
    tick_data = {
        "trigger_id": "trigger_context_456",
        "time": "2025-11-05T15:00:00Z",
        "message": "Context enrichment data",
        "action": "enrich_context",
        "metadata": {},
    }

    # Mock context enrichment method
    with patch.object(
        proactive_agent, "_enrich_session_context", new_callable=AsyncMock
    ) as mock_enrich:
        await proactive_agent._handle_trigger_tick(tick_data)

        # Verify context enrichment called
        mock_enrich.assert_called_once_with("trigger_context_456", tick_data)

        # Verify metrics updated
        assert proactive_agent.trigger_ticks == 1


@pytest.mark.asyncio
async def test_trigger_tick_invoke_agent(proactive_agent):
    """Test _handle_trigger_tick with invoke_agent action."""
    tick_data = {
        "trigger_id": "trigger_routine_789",
        "time": "2025-11-05T16:00:00Z",
        "message": "Execute routine task",
        "action": "invoke_agent",
        "metadata": {
            "agent_type": "routine",
        },
    }

    # Mock agent invocation method
    with patch.object(proactive_agent, "_invoke_agent", new_callable=AsyncMock) as mock_invoke:
        await proactive_agent._handle_trigger_tick(tick_data)

        # Verify agent invocation called
        mock_invoke.assert_called_once_with(
            "routine", "Execute routine task", "trigger_routine_789"
        )

        # Verify metrics updated
        assert proactive_agent.trigger_ticks == 1


@pytest.mark.asyncio
async def test_pattern_tick_handling(proactive_agent):
    """Test _handle_pattern_tick processes pattern detection events - generates LLM response."""
    tick_data = {
        "pattern_id": "pattern_milk_day",
        "pattern_name": "Milk Day",
        "confidence": 0.85,
        "message": "Looks like today is milk day based on your history",
        "suggestion": "Reminder to buy milk?",
    }

    # Mock LLM response
    mock_llm_response = {
        "content": "Hi! I noticed a pattern - looks like today might be milk day based on your shopping history (85% confidence). Want me to add milk to your shopping list?",
        "tokens": 30,
    }

    # Mock notification and session state methods
    with patch.object(proactive_agent, "call_llm", new_callable=AsyncMock) as mock_llm:
        with patch.object(
            proactive_agent, "_stream_notification_to_user", new_callable=AsyncMock
        ) as mock_stream:
            with patch.object(
                proactive_agent, "_update_session_state_with_pattern", new_callable=AsyncMock
            ):
                mock_llm.return_value = mock_llm_response

                await proactive_agent._handle_pattern_tick(tick_data)

                # Verify LLM was called with pattern context
                mock_llm.assert_called_once()
                call_args = mock_llm.call_args
                assert "Pattern detected" in call_args.kwargs["user_input"]
                assert call_args.kwargs["temperature"] == 0.7

                # Verify notification streamed with conversational content
                mock_stream.assert_called_once()
                notification_arg = mock_stream.call_args[0][0]
                assert "pattern" in notification_arg.lower()
                assert "milk" in notification_arg.lower()

                # Verify metrics updated
                assert proactive_agent.pattern_ticks == 1


@pytest.mark.asyncio
async def test_anomaly_tick_handling(proactive_agent):
    """Test _handle_anomaly_tick processes anomaly alerts - generates LLM response."""
    tick_data = {
        "anomaly_id": "anomaly_spending_123",
        "anomaly_type": "unusual_spending",
        "severity": "medium",
        "message": "Unusual spending detected",
        "details": "Large transaction: $500 at restaurant",
        "timestamp": "2025-11-05T18:45:00Z",
    }

    # Mock LLM response
    mock_llm_response = {
        "content": "Hey, I noticed something unusual - there was a $500 transaction at a restaurant today. That's higher than your typical spending. Just wanted to flag this in case you want to review it!",
        "tokens": 35,
    }

    # Mock notification and session state methods
    with patch.object(proactive_agent, "call_llm", new_callable=AsyncMock) as mock_llm:
        with patch.object(
            proactive_agent, "_stream_notification_to_user", new_callable=AsyncMock
        ) as mock_stream:
            with patch.object(
                proactive_agent, "_update_session_state_with_anomaly", new_callable=AsyncMock
            ):
                mock_llm.return_value = mock_llm_response

                await proactive_agent._handle_anomaly_tick(tick_data)

                # Verify LLM was called with anomaly context
                mock_llm.assert_called_once()
                call_args = mock_llm.call_args
                assert "Anomaly alert" in call_args.kwargs["user_input"]
                assert "medium severity" in call_args.kwargs["user_input"]
                assert call_args.kwargs["temperature"] == 0.5  # Lower for alerts

                # Verify notification streamed with conversational alert
                mock_stream.assert_called_once()
                notification_arg = mock_stream.call_args[0][0]
                assert "$500" in notification_arg
                assert "unusual" in notification_arg.lower()

                # Verify metrics updated
                assert proactive_agent.anomaly_ticks == 1


@pytest.mark.asyncio
async def test_parse_sse_event_trigger(proactive_agent):
    """Test SSE event parsing for trigger event."""
    # Simulate SSE event lines
    event_line = "event: prospective.trigger.fired"
    data_line = (
        'data: {"trigger_id": "test_trigger", "message": "Test message", "action": "notify_user"}'
    )

    # Mock trigger handler
    with patch.object(
        proactive_agent, "_handle_trigger_tick", new_callable=AsyncMock
    ) as mock_handler:
        # Parse event type
        await proactive_agent._parse_sse_event(event_line)
        # Parse data
        await proactive_agent._parse_sse_event(data_line)

        # Verify handler called with parsed data
        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0][0]
        assert call_args["trigger_id"] == "test_trigger"
        assert call_args["message"] == "Test message"
        assert call_args["action"] == "notify_user"


@pytest.mark.asyncio
async def test_parse_sse_event_pattern(proactive_agent):
    """Test SSE event parsing for pattern event."""
    event_line = "event: prospective.pattern.detected"
    data_line = (
        'data: {"pattern_id": "pattern_test", "pattern_name": "Test Pattern", "confidence": 0.9}'
    )

    # Mock pattern handler
    with patch.object(
        proactive_agent, "_handle_pattern_tick", new_callable=AsyncMock
    ) as mock_handler:
        await proactive_agent._parse_sse_event(event_line)
        await proactive_agent._parse_sse_event(data_line)

        # Verify handler called
        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0][0]
        assert call_args["pattern_id"] == "pattern_test"
        assert call_args["confidence"] == 0.9


@pytest.mark.asyncio
async def test_parse_sse_event_anomaly(proactive_agent):
    """Test SSE event parsing for anomaly event."""
    event_line = "event: prospective.anomaly.alert"
    data_line = (
        'data: {"anomaly_id": "anomaly_test", "severity": "high", "message": "Test anomaly"}'
    )

    # Mock anomaly handler
    with patch.object(
        proactive_agent, "_handle_anomaly_tick", new_callable=AsyncMock
    ) as mock_handler:
        await proactive_agent._parse_sse_event(event_line)
        await proactive_agent._parse_sse_event(data_line)

        # Verify handler called
        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0][0]
        assert call_args["anomaly_id"] == "anomaly_test"
        assert call_args["severity"] == "high"


@pytest.mark.asyncio
async def test_process_message_get_stats(proactive_agent):
    """Test process_message handles get_stats request."""
    # Set some metrics
    proactive_agent.ticks_received = 10
    proactive_agent.trigger_ticks = 5
    proactive_agent.pattern_ticks = 3
    proactive_agent.anomaly_ticks = 2

    message = {"type": "get_stats"}

    stats = await proactive_agent.process_message(message)

    # Verify stats returned
    assert stats["ticks_received"] == 10
    assert stats["trigger_ticks"] == 5
    assert stats["pattern_ticks"] == 3
    assert stats["anomaly_ticks"] == 2
    assert stats["state"] == AgentState.PENDING.value


@pytest.mark.asyncio
async def test_graceful_shutdown(proactive_agent):
    """Test ProactiveAgent gracefully shuts down SSE connection."""

    # Mock SSE listening task (needs to be an actual coroutine for await)
    async def mock_listen():
        await asyncio.sleep(0.01)

    proactive_agent.sse_listen_task = asyncio.create_task(mock_listen())

    # Mock SSE client
    mock_client = AsyncMock()
    proactive_agent.sse_client = mock_client

    # Transition to DRAINING
    await proactive_agent.transition_to(AgentState.DRAINING)

    # Verify shutdown signal set
    assert proactive_agent._shutdown_event.is_set()

    # Verify client closed
    mock_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_get_stats_method(proactive_agent):
    """Test get_stats() returns correct metrics."""
    # Set metrics
    proactive_agent.ticks_received = 15
    proactive_agent.trigger_ticks = 8
    proactive_agent.pattern_ticks = 4
    proactive_agent.anomaly_ticks = 3
    proactive_agent.reconnect_attempts = 2

    stats = proactive_agent.get_stats()

    assert stats["agent_id"] == "proactive_001"
    assert stats["agent_type"] == "proactive"
    assert stats["ticks_received"] == 15
    assert stats["trigger_ticks"] == 8
    assert stats["pattern_ticks"] == 4
    assert stats["anomaly_ticks"] == 3
    assert stats["reconnect_attempts"] == 2


@pytest.mark.asyncio
async def test_sse_event_skip_empty_lines(proactive_agent):
    """Test SSE parser skips empty lines and comments."""
    # Empty line
    await proactive_agent._parse_sse_event("")

    # Comment line
    await proactive_agent._parse_sse_event(": this is a comment")

    # Verify no ticks counted
    assert proactive_agent.ticks_received == 0


@pytest.mark.asyncio
async def test_sse_event_json_parse_error(proactive_agent):
    """Test SSE parser handles JSON parse errors gracefully."""
    event_line = "event: prospective.trigger.fired"
    invalid_data_line = "data: {invalid json}"

    # Parse event type
    await proactive_agent._parse_sse_event(event_line)

    # Parse invalid data (should log error, not crash)
    await proactive_agent._parse_sse_event(invalid_data_line)

    # Verify no ticks counted
    assert proactive_agent.ticks_received == 0


@pytest.mark.asyncio
async def test_anomaly_tick_severity_levels(proactive_agent):
    """Test anomaly tick handler generates appropriate LLM responses for different severities."""
    severities = ["low", "medium", "high", "critical"]

    for severity in severities:
        tick_data = {
            "anomaly_id": f"anomaly_{severity}",
            "anomaly_type": "test",
            "severity": severity,
            "message": f"Test {severity} anomaly",
            "details": "",
        }

        mock_llm_response = {
            "content": f"Alert: Test {severity} anomaly detected",
            "tokens": 10,
        }

        with patch.object(proactive_agent, "call_llm", new_callable=AsyncMock) as mock_llm:
            with patch.object(
                proactive_agent, "_stream_notification_to_user", new_callable=AsyncMock
            ) as mock_stream:
                with patch.object(
                    proactive_agent, "_update_session_state_with_anomaly", new_callable=AsyncMock
                ):
                    mock_llm.return_value = mock_llm_response

                    await proactive_agent._handle_anomaly_tick(tick_data)

                    # Verify LLM called with severity context
                    mock_llm.assert_called_once()
                    call_args = mock_llm.call_args
                    assert severity in call_args.kwargs["user_input"]
                    assert call_args.kwargs["temperature"] == 0.5

                    # Verify notification streamed
                    mock_stream.assert_called_once()
                    notification_arg = mock_stream.call_args[0][0]
                    assert severity in notification_arg.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
