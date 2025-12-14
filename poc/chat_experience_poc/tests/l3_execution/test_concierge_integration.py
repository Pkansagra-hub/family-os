"""
Integration Tests for ConciergeAgent (AI Agent Pattern)

Tests verify that Concierge:
  - Uses Prompt Registry for system prompts
  - Uses Groq client for LLM reasoning
  - Uses Template Engine for prompt merging
  - Classifies intents via LLM (no hardcoded logic)
  - Routes to specialists with simulated responses
  - Handles meta-intents directly

Note: These are integration tests using REAL Prompt Registry + Template Engine.
Groq client is mocked to avoid API costs during testing.

References:
  - docs/plans/chat_experience_poc_plan.md - Epic 4.1
  - .github/instructions/testing-requirements.instructions.md
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Import Concierge
from l3_execution.agents.concierge_agent import ConciergeAgent
from l5_infrastructure.groq_client import GroqClient


@pytest.fixture
def mock_groq_client():
    """
    Mock Groq client that simulates LLM responses.

    Returns different responses based on input to test different intent types.
    """
    client = Mock(spec=GroqClient)

    async def mock_complete(messages, **kwargs):
        """Simulate LLM response based on user input."""
        user_message = messages[-1]["content"] if messages else ""

        # Classification responses
        if "Classify the following user message" in user_message:
            if "hey" in user_message.lower() or "hi" in user_message.lower():
                return {
                    "content": json.dumps(
                        {
                            "intent_type": "meta",
                            "intent_subtype": "GREETING",
                            "confidence": 0.95,
                            "reasoning": "User is greeting",
                        }
                    ),
                    "tokens_used": 50,
                    "finish_reason": "stop",
                    "trace_id": "test-trace-123",
                    "timestamp": "2025-11-05T12:00:00Z",
                }
            elif "knee" in user_message.lower() or "recovery" in user_message.lower():
                return {
                    "content": json.dumps(
                        {
                            "intent_type": "query",
                            "intent_subtype": "HEALTH_QUERY",
                            "specialist_type": "healthcare",
                            "confidence": 0.92,
                            "reasoning": "Health-related query",
                        }
                    ),
                    "tokens_used": 55,
                    "finish_reason": "stop",
                    "trace_id": "test-trace-123",
                    "timestamp": "2025-11-05T12:00:00Z",
                }
            elif "plan" in user_message.lower():
                return {
                    "content": json.dumps(
                        {
                            "intent_type": "planning",
                            "intent_subtype": "PLANNING_REQUEST",
                            "confidence": 0.90,
                            "reasoning": "Complex planning request",
                        }
                    ),
                    "tokens_used": 52,
                    "finish_reason": "stop",
                    "trace_id": "test-trace-123",
                    "timestamp": "2025-11-05T12:00:00Z",
                }

        # Meta-intent responses (conversational)
        if "hey" in user_message.lower() or "hi" in user_message.lower():
            return {
                "content": "Hey there! I'm here to help you with health tracking, finances, or anything else. What's on your mind?",
                "tokens_used": 30,
                "finish_reason": "stop",
                "trace_id": "test-trace-123",
                "timestamp": "2025-11-05T12:00:00Z",
            }

        # Specialist responses
        if "knee" in user_message.lower() or "recovery" in user_message.lower():
            return {
                "content": "Based on your PT schedule, you're making great progress on your knee recovery! Your last session was focused on strengthening exercises, and you've completed 8 out of 12 prescribed sessions.",
                "tokens_used": 45,
                "finish_reason": "stop",
                "trace_id": "test-trace-123",
                "timestamp": "2025-11-05T12:00:00Z",
            }

        # Default response
        return {
            "content": "I can help you with that!",
            "tokens_used": 10,
            "finish_reason": "stop",
            "trace_id": "test-trace-123",
            "timestamp": "2025-11-05T12:00:00Z",
        }

    client.complete = AsyncMock(side_effect=mock_complete)
    client.get_stats = Mock(
        return_value={
            "token_count": 0,
            "request_count": 0,
            "error_count": 0,
            "average_tokens_per_request": 0,
        }
    )

    return client


@pytest.fixture
def concierge_agent(mock_groq_client):
    """Create ConciergeAgent instance with mocked Groq client."""
    return ConciergeAgent(
        agent_id="concierge-test-001",
        session_id="session-test-001",
        groq_client=mock_groq_client,
        trace_id="test-trace-123",
    )


# ========================================================================
# TEST 1: Initialization
# ========================================================================


@pytest.mark.asyncio
async def test_concierge_initialization(concierge_agent):
    """Test that Concierge initializes correctly."""
    assert concierge_agent.agent_id == "concierge-test-001"
    assert concierge_agent.agent_type == "concierge"
    assert concierge_agent.session_id == "session-test-001"
    assert concierge_agent.state.value == "pending"

    # Check Concierge-specific metrics initialized
    assert concierge_agent.concierge_metrics["meta_intents_handled"] == 0
    assert concierge_agent.concierge_metrics["specialists_routed"] == 0
    assert concierge_agent.concierge_metrics["planner_routed"] == 0


# ========================================================================
# TEST 2: Lifecycle Transition
# ========================================================================


@pytest.mark.asyncio
async def test_concierge_lifecycle_active(concierge_agent):
    """Test Concierge transitions to ACTIVE state."""
    await concierge_agent.transition_to(concierge_agent.state.__class__.ACTIVE)

    assert concierge_agent.state.value == "active"
    assert len(concierge_agent.state_history) == 2  # PENDING → ACTIVE


# ========================================================================
# TEST 3: Meta-Intent Classification (LLM-based)
# ========================================================================


@pytest.mark.asyncio
async def test_meta_intent_classification(concierge_agent):
    """Test that meta-intents (greetings) are classified via LLM."""
    message = {
        "payload": {"content": "hey what's up?"},
        "sender_id": "user-001",
        "trace_id": "test-trace-123",
    }

    response = await concierge_agent.process_message(message)

    # Verify response
    assert response["status"] == "success"
    assert response["intent"] == "meta"
    assert response["intent_subtype"] == "GREETING"
    assert "Hey there" in response["content"] or "help" in response["content"].lower()

    # Verify metrics
    assert concierge_agent.concierge_metrics["meta_intents_handled"] == 1


# ========================================================================
# TEST 4: Query-Intent Classification + Specialist Routing (LLM-based)
# ========================================================================


@pytest.mark.asyncio
async def test_query_intent_specialist_routing(concierge_agent):
    """Test that health queries are classified and routed to specialist."""
    message = {
        "payload": {"content": "How's my knee recovery going?"},
        "sender_id": "user-001",
        "trace_id": "test-trace-123",
    }

    response = await concierge_agent.process_message(message)

    # Verify response
    assert response["status"] == "success"
    assert response["intent"] == "query"
    assert response["specialist_type"] == "healthcare"
    assert (
        "⏳ Querying" in response["feedback_message"]
        or "specialist" in response["feedback_message"].lower()
    )
    assert "recovery" in response["content"].lower() or "progress" in response["content"].lower()

    # Verify metrics
    assert concierge_agent.concierge_metrics["specialists_routed"] == 1


# ========================================================================
# TEST 5: Planning-Intent Classification (LLM-based)
# ========================================================================


@pytest.mark.asyncio
async def test_planning_intent_routing(concierge_agent):
    """Test that planning requests are classified and routed to planner."""
    message = {
        "payload": {"content": "Plan a trip to Hawaii with my family"},
        "sender_id": "user-001",
        "trace_id": "test-trace-123",
    }

    response = await concierge_agent.process_message(message)

    # Verify response
    assert response["status"] == "success"
    assert response["intent"] == "planning"
    assert "plan" in response["content"].lower() or "step" in response["content"].lower()

    # Verify metrics
    assert concierge_agent.concierge_metrics["planner_routed"] == 1


# ========================================================================
# TEST 6: Time Query (Simple Meta-Intent)
# ========================================================================


@pytest.mark.asyncio
async def test_time_query_meta_intent(concierge_agent):
    """Test that time queries are handled without LLM (fast response)."""

    # Mock intent classification to return TIME_QUERY
    async def mock_classify_intent(user_input):
        return {
            "intent_type": "meta",
            "intent_subtype": "TIME_QUERY",
            "confidence": 1.0,
            "reasoning": "Time query",
        }

    with patch.object(concierge_agent, "_classify_intent", mock_classify_intent):
        message = {
            "payload": {"content": "What time is it?"},
            "sender_id": "user-001",
            "trace_id": "test-trace-123",
        }

        response = await concierge_agent.process_message(message)

        # Verify response
        assert response["status"] == "success"
        assert response["intent"] == "meta"
        assert response["intent_subtype"] == "TIME_QUERY"
        assert ":" in response["content"]  # Time format (HH:MM)


# ========================================================================
# TEST 7: Error Handling (Empty Message)
# ========================================================================


@pytest.mark.asyncio
async def test_empty_message_handling(concierge_agent):
    """Test that empty messages are handled gracefully."""
    message = {
        "payload": {"content": ""},
        "sender_id": "user-001",
        "trace_id": "test-trace-123",
    }

    response = await concierge_agent.process_message(message)

    # Verify error response
    assert response["status"] == "error"
    assert "Empty message" in response["content"]


# ========================================================================
# TEST 8: Statistics
# ========================================================================


@pytest.mark.asyncio
async def test_concierge_statistics(concierge_agent):
    """Test that Concierge tracks statistics correctly."""
    # Process a few messages
    messages = [
        {"payload": {"content": "hey"}, "sender_id": "user-001", "trace_id": "test-1"},
        {
            "payload": {"content": "How's my knee?"},
            "sender_id": "user-001",
            "trace_id": "test-2",
        },
        {
            "payload": {"content": "Plan a trip"},
            "sender_id": "user-001",
            "trace_id": "test-3",
        },
    ]

    for msg in messages:
        await concierge_agent.process_message(msg)

    # Get stats
    stats = concierge_agent.get_concierge_stats()

    # Verify metrics
    assert stats["meta_intents_handled"] == 1
    assert stats["specialists_routed"] == 1
    assert stats["planner_routed"] == 1
    assert stats["llm_calls"] > 0  # At least classification calls


# ========================================================================
# INTEGRATION TEST: Full Workflow
# ========================================================================


@pytest.mark.asyncio
async def test_full_concierge_workflow(concierge_agent):
    """
    Integration test: Full Concierge workflow from PENDING to ACTIVE.

    Workflow:
      1. Initialize Concierge (PENDING)
      2. Transition to ACTIVE
      3. Process greeting (meta-intent)
      4. Process health query (specialist routing)
      5. Verify all metrics and state
    """
    # Step 1: Verify initial state
    assert concierge_agent.state.value == "pending"

    # Step 2: Transition to ACTIVE
    await concierge_agent.transition_to(concierge_agent.state.__class__.ACTIVE)
    assert concierge_agent.state.value == "active"

    # Step 3: Process greeting
    greeting_msg = {
        "payload": {"content": "hi there!"},
        "sender_id": "user-001",
        "trace_id": "test-trace-123",
    }
    greeting_response = await concierge_agent.process_message(greeting_msg)

    assert greeting_response["status"] == "success"
    assert greeting_response["intent"] == "meta"
    assert concierge_agent.concierge_metrics["meta_intents_handled"] == 1

    # Step 4: Process health query
    health_msg = {
        "payload": {"content": "How's my recovery going?"},
        "sender_id": "user-001",
        "trace_id": "test-trace-123",
    }
    health_response = await concierge_agent.process_message(health_msg)

    assert health_response["status"] == "success"
    assert health_response["intent"] == "query"
    assert health_response["specialist_type"] == "healthcare"
    assert concierge_agent.concierge_metrics["specialists_routed"] == 1

    # Step 5: Verify final state
    stats = concierge_agent.get_concierge_stats()
    assert stats["current_state"] == "active"
    assert stats["messages_received"] == 0  # No actual mailbox in POC
    assert stats["llm_calls"] >= 2  # Classification + responses


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
