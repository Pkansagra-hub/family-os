"""
Phase 2 Memory Tracker Tests

Tests Topic 3: Memory & Continuity

Verifies:
- ConversationThread tracking and management
- UserDetail storage with confidence
- Memory context generation
- Natural memory references
- Thread status management
- Integration with ConciergeAgentV2
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from backend.agents.concierge_v2 import ConciergeAgentV2
from backend.agents.memory_tracker import ConversationThread, MemoryTracker, UserDetail
from backend.services.k0_query_service import MockK0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def memory_tracker():
    """Create MemoryTracker instance"""
    return MemoryTracker()


@pytest.fixture
def mock_llm_client():
    """Mock LLMClient"""
    client = AsyncMock(spec=LLMClient)
    client.generate_async = AsyncMock(return_value="That's interesting!")
    return client


@pytest.fixture
def concierge_agent(mock_llm_client):
    """Create ConciergeAgentV2 with all Phase 1 + Phase 2 features"""
    agent = ConciergeAgentV2(
        llm_client=mock_llm_client,
        k0_query_service=MockK0QueryService(),
        metrics_collector=MetricsCollector(),
        progress_publisher=ProgressPublisher(),
    )
    return agent


# ============================================================================
# CONVERSATION THREAD TESTS
# ============================================================================


class TestConversationThread:
    """Tests for ConversationThread dataclass"""

    def test_thread_initialization(self):
        """Verify thread initializes correctly"""
        thread = ConversationThread(topic="coffee")

        assert thread.topic == "coffee"
        assert thread.mentions == []
        assert thread.insights == []
        assert thread.status == "active"
        assert thread.mention_count == 0

    def test_thread_add_mention(self):
        """Verify mentions are tracked"""
        thread = ConversationThread(topic="coffee")
        thread.mentions.append("I drink 3 cups a day")

        assert len(thread.mentions) == 1
        assert "3 cups" in thread.mentions[0]

    def test_thread_add_insight(self):
        """Verify insights are tracked"""
        thread = ConversationThread(topic="coffee")
        thread.insights.append("Coffee triggers GERD")

        assert len(thread.insights) == 1
        assert "GERD" in thread.insights[0]

    def test_thread_status_transitions(self):
        """Verify status transitions work"""
        thread = ConversationThread(topic="coffee", status="active")
        assert thread.status == "active"

        thread.status = "resolved"
        assert thread.status == "resolved"

        thread.status = "deferred"
        assert thread.status == "deferred"


# ============================================================================
# USER DETAIL TESTS
# ============================================================================


class TestUserDetail:
    """Tests for UserDetail dataclass"""

    def test_detail_initialization(self):
        """Verify detail initializes with confidence"""
        detail = UserDetail(key="milk_hypothesis", value="Milk triggers GERD", confidence=0.9)

        assert detail.key == "milk_hypothesis"
        assert detail.value == "Milk triggers GERD"
        assert detail.confidence == 0.9

    def test_detail_default_confidence(self):
        """Verify default confidence is 0.8"""
        detail = UserDetail(key="test", value="test value")
        assert detail.confidence == 0.8

    def test_detail_timestamp(self):
        """Verify timestamps are set"""
        before = datetime.now()
        detail = UserDetail(key="test", value="test")
        after = datetime.now()

        assert before <= detail.first_mentioned <= after
        assert before <= detail.updated_at <= after


# ============================================================================
# MEMORY TRACKER TESTS
# ============================================================================


class TestMemoryTracker:
    """Tests for MemoryTracker class"""

    def test_initialization(self, memory_tracker):
        """Verify tracker initializes empty"""
        assert len(memory_tracker.threads) == 0
        assert len(memory_tracker.user_details) == 0

    def test_add_to_thread_creates_new(self, memory_tracker):
        """Verify new thread is created"""
        memory_tracker.add_to_thread("coffee", "I drink 3 cups daily", source="user")

        assert "coffee" in memory_tracker.threads
        assert len(memory_tracker.threads["coffee"].mentions) == 1
        assert memory_tracker.threads["coffee"].mention_count == 1

    def test_add_to_thread_updates_existing(self, memory_tracker):
        """Verify existing thread is updated"""
        memory_tracker.add_to_thread("coffee", "I love coffee", source="user")
        memory_tracker.add_to_thread("coffee", "3 cups daily", source="user")

        assert len(memory_tracker.threads["coffee"].mentions) == 2
        assert memory_tracker.threads["coffee"].mention_count == 2

    def test_add_agent_insight(self, memory_tracker):
        """Verify agent insights are added"""
        memory_tracker.add_to_thread("coffee", "Finding: coffee causes reflux", source="agent")

        assert len(memory_tracker.threads["coffee"].insights) == 1
        assert "reflux" in memory_tracker.threads["coffee"].insights[0]

    def test_store_detail_creates_new(self, memory_tracker):
        """Verify new detail is stored"""
        memory_tracker.store_detail("milk_hypothesis", "Milk triggers GERD", confidence=0.85)

        assert "milk_hypothesis" in memory_tracker.user_details
        assert memory_tracker.user_details["milk_hypothesis"].value == "Milk triggers GERD"
        assert memory_tracker.user_details["milk_hypothesis"].confidence == 0.85

    def test_store_detail_updates_existing(self, memory_tracker):
        """Verify detail updates work"""
        memory_tracker.store_detail("test_key", "old value", confidence=0.5)
        memory_tracker.store_detail("test_key", "new value", confidence=0.9)

        detail = memory_tracker.user_details["test_key"]
        assert detail.value == "new value"
        assert detail.confidence == 0.9

    def test_get_thread_history(self, memory_tracker):
        """Verify thread retrieval works"""
        memory_tracker.add_to_thread("sleep", "Can't sleep well", source="user")

        thread = memory_tracker.get_thread_history("sleep")
        assert thread is not None
        assert thread.topic == "sleep"

    def test_get_thread_history_not_found(self, memory_tracker):
        """Verify returns None for missing thread"""
        thread = memory_tracker.get_thread_history("nonexistent")
        assert thread is None

    def test_get_active_threads(self, memory_tracker):
        """Verify active thread filtering"""
        memory_tracker.add_to_thread("coffee", "I love coffee", source="user")
        memory_tracker.add_to_thread("sleep", "Poor sleep", source="user")

        memory_tracker.threads["coffee"].status = "resolved"

        active = memory_tracker.get_active_threads()
        assert len(active) == 1
        assert active[0].topic == "sleep"

    def test_get_resolved_threads(self, memory_tracker):
        """Verify resolved thread filtering"""
        memory_tracker.add_to_thread("coffee", "I love coffee", source="user")
        memory_tracker.threads["coffee"].status = "resolved"

        resolved = memory_tracker.get_resolved_threads()
        assert len(resolved) == 1
        assert resolved[0].topic == "coffee"

    def test_generate_memory_context_empty(self, memory_tracker):
        """Verify empty context when no memory"""
        context = memory_tracker.generate_memory_context()
        assert "No previous context" in context

    def test_generate_memory_context_with_threads(self, memory_tracker):
        """Verify context generation with threads"""
        memory_tracker.add_to_thread("coffee", "I drink 3 cups daily", source="user")
        memory_tracker.add_to_thread("sleep", "Poor sleep quality", source="user")

        context = memory_tracker.generate_memory_context()
        assert "Active topics:" in context
        assert "coffee" in context or "sleep" in context

    def test_generate_memory_context_with_details(self, memory_tracker):
        """Verify context includes user details"""
        memory_tracker.store_detail("gym_routine", "Prefers morning workouts", confidence=0.85)

        context = memory_tracker.generate_memory_context()
        assert "User details:" in context
        assert "gym_routine" in context

    def test_suggest_memory_reference_matches_topic(self, memory_tracker):
        """Verify memory suggestion for known topic"""
        memory_tracker.add_to_thread("coffee", "I drink coffee daily", source="user")

        suggestion = memory_tracker.suggest_memory_reference("Does coffee affect sleep?")
        assert suggestion is not None
        assert "coffee" in suggestion.lower()

    def test_suggest_memory_reference_no_match(self, memory_tracker):
        """Verify no suggestion for unknown topic"""
        suggestion = memory_tracker.suggest_memory_reference("How's the weather?")
        assert suggestion is None

    def test_suggest_memory_reference_with_insights(self, memory_tracker):
        """Verify suggestion includes insights when available"""
        memory_tracker.add_to_thread("coffee", "I love coffee", source="user")
        memory_tracker.add_to_thread("coffee", "Coffee triggers reflux 80%", source="agent")

        suggestion = memory_tracker.suggest_memory_reference("Does coffee affect me?")
        assert suggestion is not None
        assert "80%" in suggestion or "reflux" in suggestion

    def test_update_thread_status_resolution(self, memory_tracker):
        """Verify status updates to resolved"""
        memory_tracker.add_to_thread("coffee", "I love coffee", source="user")

        new_status = memory_tracker.update_thread_status("coffee", "Got it thanks!")
        assert new_status == "resolved"

    def test_update_thread_status_deferral(self, memory_tracker):
        """Verify status updates to deferred"""
        memory_tracker.add_to_thread("coffee", "I love coffee", source="user")

        new_status = memory_tracker.update_thread_status("coffee", "maybe later")
        assert new_status == "deferred"

    def test_update_thread_status_active(self, memory_tracker):
        """Verify status stays active for neutral messages"""
        memory_tracker.add_to_thread("coffee", "I love coffee", source="user")

        memory_tracker.update_thread_status("coffee", "Tell me more")
        # Status should not change (no resolution marker)
        assert memory_tracker.threads["coffee"].status == "active"

    def test_get_stats(self, memory_tracker):
        """Verify statistics generation"""
        memory_tracker.add_to_thread("coffee", "I love coffee", source="user")
        memory_tracker.add_to_thread("sleep", "Poor sleep", source="user")
        memory_tracker.store_detail("detail1", "High confidence", confidence=0.9)
        memory_tracker.store_detail("detail2", "Low confidence", confidence=0.3)

        stats = memory_tracker.get_stats()
        assert stats["total_threads"] == 2
        assert stats["active_threads"] == 2
        assert stats["user_details"] == 2
        assert stats["high_confidence_details"] == 1

    def test_clear_old_threads(self, memory_tracker):
        """Verify old threads are removed"""
        memory_tracker.add_to_thread("coffee", "I love coffee", source="user")

        # Manually set last_mentioned to past
        now = datetime.now()
        memory_tracker.threads["coffee"].last_mentioned = now - timedelta(minutes=70)

        removed = memory_tracker.clear_old_threads(max_age_minutes=60)
        assert removed == 1
        assert "coffee" not in memory_tracker.threads

    def test_topic_keywords_defined(self, memory_tracker):
        """Verify topic keywords are configured"""
        assert len(memory_tracker.TOPIC_KEYWORDS) >= 6
        assert "coffee" in memory_tracker.TOPIC_KEYWORDS
        assert "gerd" in memory_tracker.TOPIC_KEYWORDS
        assert "sleep" in memory_tracker.TOPIC_KEYWORDS


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestMemoryIntegration:
    """Tests for memory integration with ConciergeAgentV2"""

    def test_memory_initialized_in_concierge(self, concierge_agent):
        """Verify memory tracker is initialized"""
        assert concierge_agent.memory is not None
        assert isinstance(concierge_agent.memory, MemoryTracker)

    def test_extract_topic_coffee(self, concierge_agent):
        """Verify topic extraction for coffee"""
        topic = concierge_agent._extract_topic("I drink 3 cups of coffee daily")
        assert topic == "coffee"

    def test_extract_topic_gerd(self, concierge_agent):
        """Verify topic extraction for gerd"""
        topic = concierge_agent._extract_topic("My acid reflux is bad")
        assert topic == "gerd"

    def test_extract_topic_sleep(self, concierge_agent):
        """Verify topic extraction for sleep"""
        topic = concierge_agent._extract_topic("I can't sleep well at night")
        assert topic == "sleep"

    def test_extract_topic_gym(self, concierge_agent):
        """Verify topic extraction for gym"""
        topic = concierge_agent._extract_topic("I work out at the gym")
        assert topic == "gym"

    def test_extract_topic_milk(self, concierge_agent):
        """Verify topic extraction for milk"""
        topic = concierge_agent._extract_topic("Does milk cause problems?")
        assert topic == "milk"

    def test_extract_topic_stress(self, concierge_agent):
        """Verify topic extraction for stress"""
        topic = concierge_agent._extract_topic("I'm feeling anxious and stressed")
        assert topic == "stress"

    def test_extract_topic_not_found(self, concierge_agent):
        """Verify returns None for unknown topic"""
        topic = concierge_agent._extract_topic("How's the weather today?")
        assert topic is None

    @pytest.mark.asyncio
    async def test_process_message_updates_memory(self, concierge_agent):
        """Verify process_message updates memory"""
        concierge_agent.llm_client.generate_async = AsyncMock(
            return_value="That's interesting about coffee"
        )

        await concierge_agent.process_message("user123", "I drink a lot of coffee")

        # Verify memory was updated
        assert "coffee" in concierge_agent.memory.threads
        coffee_thread = concierge_agent.memory.threads["coffee"]
        assert len(coffee_thread.mentions) > 0

    @pytest.mark.asyncio
    async def test_memory_context_in_prompt(self, concierge_agent):
        """Verify memory context is included in prompts"""
        # Setup some memory
        concierge_agent.memory.add_to_thread("coffee", "I drink 3 cups daily", source="user")
        concierge_agent.memory.store_detail("coffee_gerd", "Coffee triggers GERD", confidence=0.9)

        # Mock LLM to capture prompt
        captured_prompt = None

        async def capture_prompt(prompt, **kwargs):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "That makes sense"

        concierge_agent.llm_client.generate_async = AsyncMock(side_effect=capture_prompt)

        await concierge_agent._generate_conversational_response("Does coffee really affect me?")

        # Verify memory context was in prompt
        assert captured_prompt is not None
        assert "coffee" in captured_prompt.lower() or "memory" in captured_prompt.lower()

    def test_memory_conversation_flow(self, concierge_agent):
        """Verify realistic memory conversation flow"""
        # Turn 1: User mentions coffee
        concierge_agent.memory.add_to_thread("coffee", "I love coffee", source="user")
        assert len(concierge_agent.memory.threads) == 1

        # Turn 2: Agent adds insight
        concierge_agent.memory.add_to_thread("coffee", "Coffee has 95mg caffeine", source="agent")
        assert len(concierge_agent.memory.threads["coffee"].insights) == 1

        # Turn 3: User mentions problem
        concierge_agent.memory.add_to_thread("coffee", "But it gives me heartburn", source="user")
        assert len(concierge_agent.memory.threads["coffee"].mentions) == 2

        # Turn 4: User resolves
        concierge_agent.memory.update_thread_status("coffee", "Got it, I'll cut back")
        assert concierge_agent.memory.threads["coffee"].status == "resolved"

    def test_multiple_topics_tracked(self, concierge_agent):
        """Verify multiple topics can be tracked simultaneously"""
        concierge_agent.memory.add_to_thread("coffee", "I drink 3 cups", source="user")
        concierge_agent.memory.add_to_thread("sleep", "Poor sleep", source="user")
        concierge_agent.memory.add_to_thread("gym", "Work out 3x/week", source="user")

        assert len(concierge_agent.memory.threads) == 3
        assert len(concierge_agent.memory.get_active_threads()) == 3


# ============================================================================
# TOPIC KEYWORDS TEST
# ============================================================================


class TestTopicKeywords:
    """Tests for topic keyword matching"""

    def test_all_topics_have_keywords(self):
        """Verify all topics have keywords"""
        tracker = MemoryTracker()
        required_topics = ["coffee", "gerd", "sleep", "gym", "milk", "stress"]

        for topic in required_topics:
            assert topic in tracker.TOPIC_KEYWORDS
            assert len(tracker.TOPIC_KEYWORDS[topic]) >= 3

    def test_keyword_matching_case_insensitive(self):
        """Verify keywords match case-insensitively"""
        tracker = MemoryTracker()
        tracker.add_to_thread("coffee", "COFFEE IS MY FAVORITE", source="user")

        suggestion = tracker.suggest_memory_reference("coffee")
        assert suggestion is not None


# ============================================================================
# RUN TESTS
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
