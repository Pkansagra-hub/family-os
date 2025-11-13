"""
Pytest configuration and fixtures for POC integration tests.

Provides mock objects and utilities for testing Concierge and other agents.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# ========================================================================
# Mock Factory Functions
# ========================================================================


class MockGroqClient:
    """
    Mock Groq client matching l5_infrastructure.groq_client.GroqClient interface.

    Provides async complete() method for testing Agent Factory and specialists.
    """

    def __init__(self, default_content: str = "Mock specialist response"):
        self.default_content = default_content
        self.call_count = 0

    async def complete(
        self,
        messages: list[dict],
        agent_type: str = "specialist",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 500,
        trace_id: Optional[str] = None,
    ) -> dict:
        """
        Mock LLM completion matching GroqClient.complete() signature.

        Returns:
            Response dict with 'content', 'tokens_used', 'finish_reason'
        """
        self.call_count += 1

        # Extract user message for context
        user_message = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        # Generate mock response based on agent_type
        if "healthcare" in agent_type.lower():
            content = "Your recovery is progressing well based on recent health metrics."
        elif "finance" in agent_type.lower():
            content = "Your budget shows expenses within normal range this month."
        elif "researcher" in agent_type.lower():
            content = "I found 3 relevant sources on this topic."
        elif "travel" in agent_type.lower():
            content = "I found 5 flights matching your criteria."
        elif "developer" in agent_type.lower():
            content = "Here's the code solution: def example(): pass"
        else:
            content = self.default_content

        return {
            "content": content,
            "tokens_used": 150,
            "finish_reason": "stop",
        }

    async def test_connection(self) -> bool:
        """Mock connection test."""
        return True


def create_mock_groq_client():
    """Create a mock Groq client for testing (legacy Anthropic-style)."""
    client = MagicMock()

    # Mock the async message creation
    async def mock_create_message(**kwargs):
        return MagicMock(
            content=[MagicMock(text='{"intent": "test", "specialist_type": "healthcare"}')]
        )

    client.messages.create = AsyncMock(side_effect=mock_create_message)
    return client


def create_mock_delta_bus():
    """Create a mock DeltaBus for testing."""
    bus = MagicMock()
    bus.publish = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.subscribe_once = AsyncMock()  # Returns Future that resolves with event
    return bus


def create_mock_mailbox():
    """Create a mock Mailbox for testing."""
    mailbox = MagicMock()
    mailbox.send = AsyncMock()
    mailbox.receive = AsyncMock()
    mailbox.send_to = AsyncMock()
    return mailbox


def create_mock_logger():
    """Create a mock logger for testing."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    logger.debug = MagicMock()
    logger.warning = MagicMock()
    return logger


# ========================================================================
# Test Envelope Builders
# ========================================================================


def create_test_envelope(
    content: str = "Test message",
    user_id: str = "test_user",
    session_id: str = "test_session",
    qos_band: str = "INTERACTIVE",
    envelope_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a test envelope (message wrapper).

    Args:
        content: Message content
        user_id: User ID
        session_id: Session ID
        qos_band: Quality of Service band (INTERACTIVE, STREAMING, BATCH)
        envelope_id: Optional envelope ID (auto-generated if not provided)

    Returns:
        Envelope dict with header and payload
    """
    return {
        "header": {
            "envelope_id": envelope_id or str(uuid.uuid4()),
            "cognitive_trace_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "session_id": session_id,
            "qos_band": qos_band,
        },
        "payload": {
            "content": content,
            "metadata": {
                "source": "test",
                "intent": None,
            },
        },
    }


# ========================================================================
# Pytest Fixtures
# ========================================================================


@pytest.fixture
def mock_groq_client():
    """Fixture: Mock Groq client matching GroqClient interface"""
    return MockGroqClient()


@pytest.fixture
def mock_delta_bus():
    """Fixture: Mock DeltaBus"""
    return create_mock_delta_bus()


@pytest.fixture
def mock_mailbox():
    """Fixture: Mock Mailbox"""
    return create_mock_mailbox()


@pytest.fixture
def mock_logger():
    """Fixture: Mock logger"""
    return create_mock_logger()


@pytest.fixture
def test_user_context():
    """Fixture: Test user context"""
    return {
        "user_id": "test_user_123",
        "preferences": {
            "communication_style": "technical",
            "detail_level": "comprehensive",
        },
        "history": [],
    }
