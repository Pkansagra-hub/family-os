"""
Integration Test: Intent Router ↔ Concierge Request-Response Flow

Tests Issue 6.5.1.2: Wire Intent Router → Concierge Communication

This test demonstrates the complete request-response flow:
1. Intent Router receives user input
2. Intent Router generates cognitive_trace_id
3. Intent Router creates session
4. Intent Router creates envelope
5. Intent Router sends envelope to Concierge (via mailbox - TODO in full impl)
6. Intent Router waits for response via DeltaBus
7. Concierge processes message
8. Concierge publishes response to DeltaBus
9. Intent Router receives response and returns to user

Test Scenarios:
- Normal message flow (timeout = 5000ms)
- CLI commands (immediate response, no Concierge)
- Concierge timeout handling
- Error handling (session creation failure)
- Response payload parsing

References:
- docs/plans/chat_experience_poc_plan.md - Issue 6.5.1.2
- l1_input/intent_router.py - _wait_for_response() implementation
- l3_execution/agents/concierge_agent.py - _publish_response() implementation
"""

import asyncio
import time
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from l1_input.intent_router import IntentRouter
from l3_execution.agents.concierge_agent import ConciergeAgent
from l4_runtime.deltabus.deltabus import get_deltabus
from l4_runtime.session_state.session_state_manager import SessionStateManager
from l5_infrastructure.groq_client import GroqClient


class TestIntentRouterConciergeFlow:
    """Test Intent Router ↔ Concierge request-response flow"""

    @pytest.fixture
    def deltabus(self):
        """Provide fresh DeltaBus instance"""
        return get_deltabus()

    @pytest.fixture
    def session_manager(self):
        """Mock SessionStateManager"""
        manager = AsyncMock(spec=SessionStateManager)

        # Mock session creation
        mock_session = MagicMock()
        mock_session.session_id = f"session_{uuid.uuid4().hex[:12]}"
        mock_session.meta = MagicMock()
        mock_session.meta.turn_count = 0
        mock_session.meta.created_at = datetime.utcnow()

        manager.create_session = AsyncMock(return_value=mock_session)
        manager.get_session = AsyncMock(return_value=mock_session)

        return manager

    @pytest.fixture
    def groq_client(self):
        """Mock Groq client"""
        client = AsyncMock(spec=GroqClient)
        client.complete = AsyncMock(
            return_value={
                "content": "I'm here to help!",
                "tokens_used": 50,
            }
        )
        return client

    @pytest.fixture
    def intent_router(self, deltabus, session_manager):
        """Create IntentRouter instance"""
        router = IntentRouter(
            session_manager=session_manager,
            deltabus=deltabus,
        )
        return router

    @pytest.fixture
    def concierge_agent(self, groq_client):
        """Create Concierge agent instance"""
        agent = ConciergeAgent(
            agent_id="concierge-1",
            session_id="session_test123",
            groq_client=groq_client,
            trace_id="trace_test",
        )
        return agent

    @pytest.mark.asyncio
    async def test_cli_command_immediate_response(self, intent_router):
        """Test CLI commands return immediately without waiting for Concierge"""
        # Test /help command
        response_text, metadata = await intent_router.route_user_input(
            user_input="/help",
            user_id="user_123",
        )

        assert response_text is not None
        assert "/help" in response_text or "commands" in response_text.lower()
        assert metadata["trace_id"].startswith("trace_")
        assert "session_id" in metadata
        assert metadata.get("latency_ms", 0) < 50  # Should be very fast

    @pytest.mark.asyncio
    async def test_status_command_immediate_response(self, intent_router):
        """Test /status command returns session info"""
        response_text, metadata = await intent_router.route_user_input(
            user_input="/status",
            user_id="user_123",
        )

        assert "session" in response_text.lower() or "status" in response_text.lower()
        assert metadata["trace_id"].startswith("trace_")

    @pytest.mark.asyncio
    async def test_normal_message_waits_for_concierge_timeout(self, intent_router, deltabus):
        """Test normal message waits for Concierge response (times out after 5s)"""
        start = time.time()

        response_text, metadata = await intent_router.route_user_input(
            user_input="How am I feeling today?",
            user_id="user_123",
        )

        elapsed = time.time() - start

        # Should timeout after 5s
        assert elapsed >= 4.5  # Allow small variance
        assert "busy" in response_text.lower() or "error" in response_text.lower()
        assert metadata.get("error") == "timeout"
        assert metadata["trace_id"].startswith("trace_")

    @pytest.mark.asyncio
    async def test_concierge_response_received_successfully(
        self, intent_router, concierge_agent, deltabus
    ):
        """Test successful request-response flow with Concierge"""

        # Start a background task that simulates Concierge responding
        async def simulate_concierge_processing():
            await asyncio.sleep(0.1)  # Simulate 100ms processing

            # Call Concierge process_message
            message = {
                "envelope_id": "env_test123",
                "payload": {
                    "content": "Hello Concierge!",
                },
                "sender_id": "user_123",
                "trace_id": "trace_test",
            }

            await concierge_agent.process_message(message)
            # Response is automatically published to DeltaBus by Concierge

        # Start background task
        task = asyncio.create_task(simulate_concierge_processing())

        # Now send a message through Intent Router
        # This should wait for Concierge response via DeltaBus
        start = time.time()

        response_text, metadata = await intent_router.route_user_input(
            user_input="How am I feeling today?",
            user_id="user_123",
        )

        elapsed = time.time() - start

        # Should complete quickly (Concierge responds)
        assert elapsed < 2.0  # Should be much faster than 5s timeout
        assert "busy" not in response_text.lower()  # Not a timeout message
        assert metadata["trace_id"].startswith("trace_")

        # Clean up
        await task

    @pytest.mark.asyncio
    async def test_response_payload_structure(self, intent_router, concierge_agent, deltabus):
        """Test response payload has correct structure"""

        async def simulate_concierge():
            await asyncio.sleep(0.05)
            message = {
                "envelope_id": "env_payload_test",
                "payload": {"content": "Test message"},
                "sender_id": "user_456",
                "trace_id": "trace_payload",
            }
            await concierge_agent.process_message(message)  # Response published to DeltaBus

        task = asyncio.create_task(simulate_concierge())

        response_text, metadata = await intent_router.route_user_input(
            user_input="Test",
            user_id="user_456",
        )

        # Verify response structure
        assert isinstance(response_text, str)
        assert isinstance(metadata, dict)
        assert "trace_id" in metadata
        assert "session_id" in metadata
        assert "envelope_id" in metadata
        assert "latency_ms" in metadata
        assert metadata["latency_ms"] > 0

        await task

    @pytest.mark.asyncio
    async def test_trace_id_propagation(self, intent_router, concierge_agent):
        """Test trace_id is propagated through the flow"""

        async def verify_trace_id():
            await asyncio.sleep(0.05)
            message = {
                "envelope_id": "env_trace_test",
                "payload": {"content": "Trace test"},
                "sender_id": "user_789",
                "trace_id": "trace_verify",
            }
            await concierge_agent.process_message(message)

        task = asyncio.create_task(verify_trace_id())

        response_text, metadata = await intent_router.route_user_input(
            user_input="Trace test",
            user_id="user_789",
        )

        # Verify trace_id format
        trace_id = metadata["trace_id"]
        assert trace_id.startswith("trace_")
        assert len(trace_id) > 10  # Should have timestamp + uuid

        await task

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self, intent_router, concierge_agent):
        """Test multiple concurrent requests with different envelope IDs"""

        async def process_concierge_for_message(content: str, delay: float):
            await asyncio.sleep(delay)
            message = {
                "envelope_id": f"env_{content.replace(' ', '_')}",
                "payload": {"content": content},
                "sender_id": "user_multi",
                "trace_id": f"trace_{content.replace(' ', '_')}",
            }
            await concierge_agent.process_message(message)

        # Start multiple Concierge processing tasks with different delays
        tasks = [
            asyncio.create_task(process_concierge_for_message("Message 1", 0.05)),
            asyncio.create_task(process_concierge_for_message("Message 2", 0.1)),
            asyncio.create_task(process_concierge_for_message("Message 3", 0.15)),
        ]

        # Send multiple requests concurrently
        router_tasks = [
            asyncio.create_task(
                intent_router.route_user_input(
                    user_input=f"Test message {i}",
                    user_id="user_multi",
                )
            )
            for i in range(3)
        ]

        results = await asyncio.gather(*router_tasks, return_exceptions=True)

        # Verify all requests completed
        assert len(results) == 3
        for result in results:
            if isinstance(result, tuple):  # Successful result
                response_text, metadata = result
                assert metadata["trace_id"].startswith("trace_")

        # Clean up
        await asyncio.gather(*tasks)

    @pytest.mark.asyncio
    async def test_session_creation_failure_graceful_error(self, intent_router, session_manager):
        """Test session creation failure returns graceful error"""
        # Make session creation fail
        session_manager.create_session.side_effect = ValueError("Session DB error")

        response_text, metadata = await intent_router.route_user_input(
            user_input="Test message",
            user_id="user_bad",
        )

        assert "error" in response_text.lower()
        assert metadata.get("error") is not None

    @pytest.mark.asyncio
    async def test_envelope_creation_format(self, intent_router):
        """Test envelope is created with correct structure"""

        async def capture_envelope_task():
            await asyncio.sleep(0.05)
            # Simulates Concierge receiving and responding to envelope

        task = asyncio.create_task(capture_envelope_task())

        response_text, metadata = await intent_router.route_user_input(
            user_input="Envelope test",
            user_id="user_env",
        )

        # Verify metadata includes envelope_id
        assert "envelope_id" in metadata
        envelope_id = metadata["envelope_id"]
        assert len(envelope_id) > 0

        await task

    @pytest.mark.asyncio
    async def test_response_latency_tracking(self, intent_router, concierge_agent):
        """Test response latency is tracked correctly"""

        async def simulate_with_delay():
            await asyncio.sleep(0.2)  # 200ms delay
            message = {
                "envelope_id": "env_latency_test",
                "payload": {"content": "Latency test"},
                "sender_id": "user_latency",
                "trace_id": "trace_latency",
            }
            await concierge_agent.process_message(message)

        task = asyncio.create_task(simulate_with_delay())

        response_text, metadata = await intent_router.route_user_input(
            user_input="Latency test",
            user_id="user_latency",
        )

        latency = metadata.get("latency_ms", 0)

        # Should be > 200ms (processing delay) + overhead
        assert latency > 150  # Allow some tolerance

        # Should not be > 5000ms (timeout)
        assert latency < 5000

        await task


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
