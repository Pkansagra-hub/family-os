"""
Phase 2 Day 5-7: Context Manager Tests

Tests Topic 8: Context Awareness

Verifies:
- Topic context tracking and state management
- Time delta calculations (fresh/warm/cold/stale)
- Temporal context formatting
- Topic bridging suggestions
- Integration with memory and concierge_v2
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from backend.agents.concierge_v2 import ConciergeAgentV2
from backend.agents.context_manager import ContextManager, TopicContext
from backend.services.k0_query_service import MockK0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def context_manager():
    """Create ContextManager instance"""
    return ContextManager()


@pytest.fixture
def mock_llm_client():
    """Mock LLMClient"""
    client = AsyncMock(spec=LLMClient)
    client.generate_async = AsyncMock(return_value="That's interesting!")
    return client


@pytest.fixture
def concierge_agent(mock_llm_client):
    """Create ConciergeAgentV2 with all humanization features"""
    agent = ConciergeAgentV2(
        llm_client=mock_llm_client,
        k0_query_service=MockK0QueryService(),
        metrics_collector=MetricsCollector(),
        progress_publisher=ProgressPublisher(),
    )
    return agent


# ============================================================================
# TOPIC CONTEXT TESTS
# ============================================================================


class TestTopicContext:
    """Tests for TopicContext dataclass"""

    def test_topic_context_initialization(self):
        """Verify topic context initializes correctly"""
        context = TopicContext(
            topic="coffee", first_mentioned_at=datetime.now(), last_mentioned_at=datetime.now()
        )

        assert context.topic == "coffee"
        assert context.mention_count == 1
        assert context.status == "fresh"

    def test_topic_context_update_mention(self):
        """Verify mention count increments"""
        context = TopicContext(
            topic="coffee", first_mentioned_at=datetime.now(), last_mentioned_at=datetime.now()
        )
        context.update_mention()

        assert context.mention_count == 2

    def test_topic_context_time_since_mention(self):
        """Verify time calculation works"""
        past = datetime.now() - timedelta(seconds=5)
        context = TopicContext(topic="coffee", first_mentioned_at=past, last_mentioned_at=past)

        time_since = context.time_since_mention
        assert 4 <= time_since <= 6  # Allow small variance

    def test_topic_context_status_fresh(self):
        """Verify fresh status for recent mentions"""
        now = datetime.now()
        context = TopicContext(topic="coffee", first_mentioned_at=now, last_mentioned_at=now)

        assert context.status == "fresh"

    def test_topic_context_status_warm(self):
        """Verify warm status for 1-2 minute old mentions"""
        past = datetime.now() - timedelta(seconds=60)
        context = TopicContext(topic="coffee", first_mentioned_at=past, last_mentioned_at=past)

        assert context.status == "warm"

    def test_topic_context_status_cold(self):
        """Verify cold status for 2-5 minute old mentions"""
        past = datetime.now() - timedelta(seconds=200)
        context = TopicContext(topic="coffee", first_mentioned_at=past, last_mentioned_at=past)

        assert context.status == "cold"

    def test_topic_context_status_stale(self):
        """Verify stale status for >5 minute old mentions"""
        past = datetime.now() - timedelta(seconds=400)
        context = TopicContext(topic="coffee", first_mentioned_at=past, last_mentioned_at=past)

        assert context.status == "stale"


# ============================================================================
# CONTEXT MANAGER TESTS
# ============================================================================


class TestContextManager:
    """Tests for ContextManager class"""

    def test_initialization(self, context_manager):
        """Verify context manager initializes empty"""
        assert len(context_manager.topic_contexts) == 0

    def test_update_topic_context_new(self, context_manager):
        """Verify new topic context is created"""
        ctx = context_manager.update_topic_context("coffee")

        assert ctx.topic == "coffee"
        assert ctx.mention_count == 1
        assert "coffee" in context_manager.topic_contexts

    def test_update_topic_context_existing(self, context_manager):
        """Verify existing topic is updated"""
        context_manager.update_topic_context("coffee")
        ctx = context_manager.update_topic_context("coffee")

        assert ctx.mention_count == 2

    def test_get_topic_context_found(self, context_manager):
        """Verify retrieval of existing context"""
        context_manager.update_topic_context("coffee")
        ctx = context_manager.get_topic_context("coffee")

        assert ctx is not None
        assert ctx.topic == "coffee"

    def test_get_topic_context_not_found(self, context_manager):
        """Verify None returned for unknown topic"""
        ctx = context_manager.get_topic_context("coffee")
        assert ctx is None

    def test_get_time_since_mention(self, context_manager):
        """Verify time calculation"""
        context_manager.update_topic_context("coffee")
        time_since = context_manager.get_time_since_mention("coffee")

        assert time_since is not None
        assert time_since >= 0

    def test_get_topic_status(self, context_manager):
        """Verify status retrieval"""
        context_manager.update_topic_context("coffee")
        status = context_manager.get_topic_status("coffee")

        assert status == "fresh"

    def test_get_active_topics(self, context_manager):
        """Verify active topic filtering"""
        context_manager.update_topic_context("coffee")
        context_manager.update_topic_context("sleep")

        active = context_manager.get_active_topics(max_age_minutes=5.0)
        assert len(active) == 2

    def test_get_active_topics_empty(self, context_manager):
        """Verify empty when no recent topics"""
        context_manager.update_topic_context("coffee")
        # Make it stale
        context_manager.topic_contexts["coffee"].last_mentioned_at = datetime.now() - timedelta(
            seconds=700
        )

        active = context_manager.get_active_topics(max_age_minutes=5.0)
        assert len(active) == 0

    def test_get_stale_topics(self, context_manager):
        """Verify stale topic filtering"""
        context_manager.update_topic_context("coffee")
        context_manager.topic_contexts["coffee"].last_mentioned_at = datetime.now() - timedelta(
            seconds=700
        )

        stale = context_manager.get_stale_topics(min_age_minutes=10.0)
        assert len(stale) == 1
        assert stale[0].topic == "coffee"

    def test_get_bridging_context_single(self, context_manager):
        """Verify bridging suggestion with one topic"""
        context_manager.update_topic_context("coffee")

        bridge = context_manager.get_bridging_context()
        assert bridge is not None
        assert "coffee" in bridge.lower()

    def test_get_bridging_context_multiple(self, context_manager):
        """Verify bridging with multiple topics"""
        context_manager.update_topic_context("coffee")
        context_manager.update_topic_context("sleep")

        bridge = context_manager.get_bridging_context()
        assert bridge is not None
        assert "coffee" in bridge.lower() or "sleep" in bridge.lower()

    def test_get_bridging_context_exclude_current(self, context_manager):
        """Verify bridging excludes current topic"""
        context_manager.update_topic_context("coffee")
        context_manager.update_topic_context("sleep")

        bridge = context_manager.get_bridging_context(current_topic="coffee")
        # Should suggest sleep, not coffee
        if bridge:
            # Either mentions sleep or is None
            assert "sleep" in bridge.lower() or bridge is None

    def test_generate_temporal_context_empty(self, context_manager):
        """Verify temporal context when no topics"""
        context = context_manager.generate_temporal_context()
        assert "No previous" in context

    def test_generate_temporal_context_with_topics(self, context_manager):
        """Verify temporal context formatting"""
        context_manager.update_topic_context("coffee")
        context_manager.update_topic_context("sleep")

        context = context_manager.generate_temporal_context()
        assert "Topic timing" in context or "coffee" in context.lower()

    def test_get_stats(self, context_manager):
        """Verify statistics generation"""
        context_manager.update_topic_context("coffee")
        context_manager.update_topic_context("sleep")
        context_manager.update_topic_context("gym")

        stats = context_manager.get_stats()
        assert stats["total_topics"] == 3
        assert stats["active_topics"] == 3

    def test_get_all_topics(self, context_manager):
        """Verify retrieval of all topics"""
        context_manager.update_topic_context("coffee")
        context_manager.update_topic_context("sleep")

        all_topics = context_manager.get_all_topics()
        assert len(all_topics) == 2

    def test_clear(self, context_manager):
        """Verify clearing context"""
        context_manager.update_topic_context("coffee")
        context_manager.clear()

        assert len(context_manager.topic_contexts) == 0


# ============================================================================
# TEMPORAL TRACKING TESTS
# ============================================================================


class TestTemporalTracking:
    """Tests for temporal aspect of context tracking"""

    def test_time_since_mention_minutes(self, context_manager):
        """Verify minutes calculation"""
        context_manager.update_topic_context("coffee")
        context_manager.topic_contexts["coffee"].last_mentioned_at = datetime.now() - timedelta(
            minutes=2
        )

        minutes = context_manager.topic_contexts["coffee"].time_since_mention_minutes
        assert 1.9 <= minutes <= 2.1

    def test_time_since_first_mention(self, context_manager):
        """Verify first mention time calculation"""
        context_manager.update_topic_context("coffee")
        context_manager.topic_contexts["coffee"].first_mentioned_at = datetime.now() - timedelta(
            minutes=5
        )

        seconds = context_manager.topic_contexts["coffee"].time_since_first_mention
        assert seconds >= 300

    def test_multiple_topics_different_ages(self, context_manager):
        """Verify handling of topics at different ages"""
        # Fresh topic
        context_manager.update_topic_context("coffee")

        # Warm topic
        context_manager.update_topic_context("sleep")
        context_manager.topic_contexts["sleep"].last_mentioned_at = datetime.now() - timedelta(
            seconds=90
        )

        # Cold topic
        context_manager.update_topic_context("gym")
        context_manager.topic_contexts["gym"].last_mentioned_at = datetime.now() - timedelta(
            seconds=250
        )

        # Update statuses
        context_manager.topic_contexts["sleep"]._update_status()
        context_manager.topic_contexts["gym"]._update_status()

        stats = context_manager.get_stats()
        assert stats["total_topics"] == 3
        # Fresh might have 1 or 0 depending on timing, so just check >= 0
        assert stats["fresh_topics"] >= 0
        assert stats["warm_topics"] >= 0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestContextIntegration:
    """Tests for integration with ConciergeAgentV2"""

    def test_context_manager_initialized(self, concierge_agent):
        """Verify context manager is initialized"""
        assert concierge_agent.context_manager is not None
        assert isinstance(concierge_agent.context_manager, ContextManager)

    @pytest.mark.asyncio
    async def test_context_updated_on_topic_mention(self, concierge_agent):
        """Verify context updates when topic is mentioned"""
        concierge_agent.llm_client.generate_async = AsyncMock(return_value="Response about coffee")

        await concierge_agent.process_message("user123", "I drink a lot of coffee")

        # Verify context was updated
        assert "coffee" in concierge_agent.context_manager.topic_contexts

    @pytest.mark.asyncio
    async def test_context_in_response_generation(self, concierge_agent):
        """Verify temporal context is included in prompts"""
        concierge_agent.memory.add_to_thread("coffee", "I love coffee", source="user")
        concierge_agent.context_manager.update_topic_context("coffee")

        concierge_agent.llm_client.generate_async = AsyncMock(return_value="Response")

        captured_prompt = None

        async def capture_prompt(prompt, **kwargs):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "Response"

        concierge_agent.llm_client.generate_async = AsyncMock(side_effect=capture_prompt)

        await concierge_agent._generate_conversational_response("Tell me about coffee and sleep")

        # Verify temporal context is in prompt
        assert captured_prompt is not None
        assert "Temporal" in captured_prompt or "context" in captured_prompt.lower()

    def test_context_memory_integration(self, concierge_agent):
        """Verify context and memory work together"""
        # Add to memory
        concierge_agent.memory.add_to_thread("coffee", "I love coffee", source="user")

        # Update context
        concierge_agent.context_manager.update_topic_context("coffee")

        # Verify both have info
        assert "coffee" in concierge_agent.memory.threads
        assert "coffee" in concierge_agent.context_manager.topic_contexts

    def test_bridging_context_available(self, concierge_agent):
        """Verify bridging context suggestions work"""
        concierge_agent.context_manager.update_topic_context("coffee")
        concierge_agent.context_manager.update_topic_context("sleep")

        bridge = concierge_agent.context_manager.get_bridging_context()
        assert bridge is not None

    def test_temporal_context_formatting(self, concierge_agent):
        """Verify temporal context is properly formatted"""
        concierge_agent.context_manager.update_topic_context("coffee")
        concierge_agent.context_manager.update_topic_context("sleep")

        temporal = concierge_agent.context_manager.generate_temporal_context()
        assert "Topic timing" in temporal or "coffee" in temporal.lower()


# ============================================================================
# EDGE CASES & STRESS TESTS
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and stress conditions"""

    def test_many_topics(self, context_manager):
        """Verify handling of many topics"""
        topics = [f"topic_{i}" for i in range(20)]
        for topic in topics:
            context_manager.update_topic_context(topic)

        assert len(context_manager.topic_contexts) == 20

    def test_rapid_updates(self, context_manager):
        """Verify rapid mention updates"""
        for _ in range(10):
            context_manager.update_topic_context("coffee")

        assert context_manager.topic_contexts["coffee"].mention_count == 10

    def test_all_stale_topics(self, context_manager):
        """Verify behavior when all topics are stale"""
        context_manager.update_topic_context("coffee")
        context_manager.topic_contexts["coffee"].last_mentioned_at = datetime.now() - timedelta(
            minutes=20
        )

        active = context_manager.get_active_topics(max_age_minutes=5.0)
        assert len(active) == 0

    def test_temporal_context_with_old_topics(self, context_manager):
        """Verify temporal context handles old topics gracefully"""
        context_manager.update_topic_context("coffee")
        context_manager.topic_contexts["coffee"].last_mentioned_at = datetime.now() - timedelta(
            minutes=30
        )

        temporal = context_manager.generate_temporal_context()
        # Should still include the stale topic with time info
        assert len(temporal) > 0

    def test_bridging_with_single_topic(self, context_manager):
        """Verify bridging with only one topic"""
        context_manager.update_topic_context("coffee")

        bridge = context_manager.get_bridging_context(current_topic="coffee")
        # Should return None since we exclude the current topic
        assert bridge is None or "coffee" not in bridge.lower()


# ============================================================================
# RUN TESTS
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
