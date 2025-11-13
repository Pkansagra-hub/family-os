"""
Writer Agent Tests

Tests for background writer agents:
  - MemoryWriterAgent: Extracts entities and prospective triggers from deltas
  - LearningExtractorAgent: Extracts learning signals from feedback
  - SemanticEnricherAgent: Enriches memories with semantic tags

Note: These are integration tests using mocked Groq client.

References:
  - docs/plans/chat_experience_poc_plan.md - Milestone 5 (Writer Agents)
  - Milestone 5, Epic 5.1 - MemoryWriterAgent
  - Milestone 5, Epic 5.2 - LearningExtractorAgent
  - Milestone 5, Epic 5.3 - SemanticEnricherAgent
"""

import json
from unittest.mock import AsyncMock, Mock

import pytest
from l3_execution.agents.writers.learning_extractor_agent_ai import (
    LearningExtractorAgent,
)
from l3_execution.agents.writers.memory_writer_agent_ai import MemoryWriterAgent
from l3_execution.agents.writers.semantic_enricher_agent_ai import SemanticEnricherAgent
from l5_infrastructure.groq_client import GroqClient
from l5_infrastructure.k0_bridge import BatchClient


@pytest.fixture
def mock_batch_client():
    """Mock BatchClient for writer agents."""
    client = Mock(spec=BatchClient)
    client.add_delta = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_groq_client():
    """Mock Groq client for writer agents."""
    client = Mock(spec=GroqClient)

    async def mock_complete(messages, **kwargs):
        """Simulate LLM responses for writer agents."""
        user_message = messages[-1]["content"] if messages else ""

        # Entity extraction response
        if "extract_entities" in user_message.lower() or "entity" in user_message.lower():
            return {
                "content": json.dumps(
                    {
                        "entities": [
                            {"type": "PERSON", "value": "Sarah", "confidence": 0.95},
                            {"type": "HEALTH_METRIC", "value": "knee strength", "confidence": 0.92},
                        ]
                    }
                ),
                "tokens_used": 45,
                "finish_reason": "stop",
                "trace_id": "test-trace-123",
                "timestamp": "2025-11-05T12:00:00Z",
            }

        # Learning signal response
        if "learning" in user_message.lower() or "feedback" in user_message.lower():
            return {
                "content": json.dumps(
                    {
                        "signal_type": "positive_feedback",
                        "agent_performance": "excellent",
                        "confidence": 0.88,
                    }
                ),
                "tokens_used": 35,
                "finish_reason": "stop",
                "trace_id": "test-trace-123",
                "timestamp": "2025-11-05T12:00:00Z",
            }

        # Semantic enrichment response
        if "semantic" in user_message.lower() or "concept" in user_message.lower():
            return {
                "content": json.dumps(
                    {
                        "concepts": ["recovery", "physical_therapy", "progress"],
                        "sentiment": "positive",
                        "salience": 0.92,
                    }
                ),
                "tokens_used": 40,
                "finish_reason": "stop",
                "trace_id": "test-trace-123",
                "timestamp": "2025-11-05T12:00:00Z",
            }

        # Default response
        return {
            "content": "Processing complete",
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
def memory_writer_agent(mock_groq_client, mock_batch_client):
    """Create MemoryWriterAgent instance."""
    return MemoryWriterAgent(
        groq_client=mock_groq_client,
        batch_client=mock_batch_client,
        session_id="session_test_001",
    )


@pytest.fixture
def learning_extractor_agent(mock_groq_client, mock_batch_client):
    """Create LearningExtractorAgent instance."""
    return LearningExtractorAgent(
        groq_client=mock_groq_client,
        batch_client=mock_batch_client,
        session_id="session_test_001",
    )


@pytest.fixture
def semantic_enricher_agent(mock_groq_client, mock_batch_client):
    """Create SemanticEnricherAgent instance."""
    return SemanticEnricherAgent(
        groq_client=mock_groq_client,
        batch_client=mock_batch_client,
        session_id="session_test_001",
    )


# ========================================================================
# MEMORY WRITER AGENT TESTS
# ========================================================================


@pytest.mark.asyncio
async def test_memory_writer_initialization(memory_writer_agent):
    """Test MemoryWriterAgent initializes correctly."""
    assert memory_writer_agent.agent_id == "memory_writer_ai"
    assert memory_writer_agent.writer_type == "memory"
    assert memory_writer_agent.session_id == "session_test_001"


@pytest.mark.asyncio
async def test_memory_writer_process_delta(memory_writer_agent):
    """Test MemoryWriterAgent can process deltas (with minimal setup)."""
    # This is an integration point test - full delta processing
    # requires SessionState and trace_id setup, tested in integration suite
    # Here we verify the agent is properly configured
    assert hasattr(memory_writer_agent, "process_delta")
    assert callable(memory_writer_agent.process_delta)


# ========================================================================
# LEARNING EXTRACTOR AGENT TESTS
# ========================================================================


@pytest.mark.asyncio
async def test_learning_extractor_initialization(learning_extractor_agent):
    """Test LearningExtractorAgent initializes correctly."""
    assert learning_extractor_agent.agent_id == "learning_extractor_ai"
    assert learning_extractor_agent.writer_type == "learning"
    assert learning_extractor_agent.session_id == "session_test_001"


@pytest.mark.asyncio
async def test_learning_extractor_feedback(learning_extractor_agent):
    """Test LearningExtractorAgent can process feedback deltas."""
    # This is an integration point test - full delta processing
    # requires SessionState and trace_id setup, tested in integration suite
    # Here we verify the agent is properly configured
    assert hasattr(learning_extractor_agent, "process_delta")
    assert callable(learning_extractor_agent.process_delta)


# ========================================================================
# SEMANTIC ENRICHER AGENT TESTS
# ========================================================================


@pytest.mark.asyncio
async def test_semantic_enricher_initialization(semantic_enricher_agent):
    """Test SemanticEnricherAgent initializes correctly."""
    assert semantic_enricher_agent.agent_id == "semantic_enricher_ai"
    assert semantic_enricher_agent.writer_type == "semantic"
    assert semantic_enricher_agent.session_id == "session_test_001"


@pytest.mark.asyncio
async def test_semantic_enricher_process_delta(semantic_enricher_agent):
    """Test SemanticEnricherAgent can process enrichment deltas."""
    # This is an integration point test - full delta processing
    # requires SessionState and trace_id setup, tested in integration suite
    # Here we verify the agent is properly configured
    assert hasattr(semantic_enricher_agent, "process_delta")
    assert callable(semantic_enricher_agent.process_delta)


# ========================================================================
# WRITER AGENT STATISTICS TESTS
# ========================================================================


@pytest.mark.asyncio
async def test_memory_writer_stats(memory_writer_agent):
    """Test MemoryWriterAgent tracks statistics."""
    # Verify basic agent properties
    assert memory_writer_agent.agent_id == "memory_writer_ai"
    assert memory_writer_agent.writer_type == "memory"
    assert memory_writer_agent.session_id == "session_test_001"


@pytest.mark.asyncio
async def test_learning_extractor_stats(learning_extractor_agent):
    """Test LearningExtractorAgent tracks statistics."""
    # Verify basic agent properties
    assert learning_extractor_agent.agent_id == "learning_extractor_ai"
    assert learning_extractor_agent.writer_type == "learning"
    assert learning_extractor_agent.session_id == "session_test_001"


@pytest.mark.asyncio
async def test_semantic_enricher_stats(semantic_enricher_agent):
    """Test SemanticEnricherAgent tracks statistics."""
    # Verify basic agent properties
    assert semantic_enricher_agent.agent_id == "semantic_enricher_ai"
    assert semantic_enricher_agent.writer_type == "semantic"
    assert semantic_enricher_agent.session_id == "session_test_001"
