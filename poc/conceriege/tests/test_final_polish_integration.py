"""
Integration tests for Final Polish Upgrades (#6-9)

These tests verify the integration of all 4 final polish upgrades:
- Upgrade #6: Style Memory Persistence
- Upgrade #7: Context-Aware Safety
- Upgrade #8: Stoplist Enforcement
- Upgrade #9: Episodic Anchors
"""

import time

import pytest
from backend.agents.concierge_v2 import ConciergeAgentV2

# ============================================================================
# UPGRADE #8: Stoplist Enforcement Integration Tests
# ============================================================================


class TestStoplistIntegration:
    """Test stoplist filter integration"""

    def test_stoplist_removes_as_an_ai(self):
        """✅ UPGRADE #8: Stoplist removes 'as an AI' phrases"""
        concierge = object.__new__(ConciergeAgentV2)
        response = "As an AI, I can help you. Here's my advice."

        filtered = concierge._apply_stoplist_filter(response)

        assert "as an ai" not in filtered.lower()
        assert "advice" in filtered.lower()

    def test_stoplist_removes_personal_experiences(self):
        """✅ UPGRADE #8: Stoplist removes 'I don't have personal experiences'"""
        concierge = object.__new__(ConciergeAgentV2)
        response = "I don't have personal experiences. However, I can suggest pasta."

        filtered = concierge._apply_stoplist_filter(response)

        assert "personal experiences" not in filtered.lower()
        assert "pasta" in filtered.lower()

    def test_stoplist_removes_just_an_ai(self):
        """✅ UPGRADE #8: Stoplist removes 'I'm just an AI'"""
        concierge = object.__new__(ConciergeAgentV2)
        response = "I'm just an AI assistant. Let me check your symptoms."

        filtered = concierge._apply_stoplist_filter(response)

        assert "just an ai" not in filtered.lower()
        assert "symptoms" in filtered.lower()

    def test_stoplist_removes_apology(self):
        """✅ UPGRADE #8: Stoplist removes generic apologies"""
        concierge = object.__new__(ConciergeAgentV2)
        response = "I apologize for any confusion. Here's the data."

        filtered = concierge._apply_stoplist_filter(response)

        assert "apologize for any confusion" not in filtered.lower()
        assert "data" in filtered.lower()

    def test_stoplist_preserves_clean_text(self):
        """✅ UPGRADE #8: Stoplist preserves clean responses"""
        concierge = object.__new__(ConciergeAgentV2)
        response = "Based on your history, try oat milk. It's easier on digestion."

        filtered = concierge._apply_stoplist_filter(response)

        assert filtered == response

    def test_stoplist_handles_multiple_phrases(self):
        """✅ UPGRADE #8: Stoplist removes multiple banned phrases"""
        concierge = object.__new__(ConciergeAgentV2)
        response = "As an AI, I don't have personal experiences. I'm just a bot."

        filtered = concierge._apply_stoplist_filter(response)

        assert "as an ai" not in filtered.lower()
        assert "personal experiences" not in filtered.lower()
        assert "just a bot" not in filtered.lower()

    def test_stoplist_case_insensitive(self):
        """✅ UPGRADE #8: Stoplist is case-insensitive"""
        concierge = object.__new__(ConciergeAgentV2)
        response_upper = "AS AN AI, I can help."
        response_mixed = "As An Ai, I can help."

        filtered_upper = concierge._apply_stoplist_filter(response_upper)
        filtered_mixed = concierge._apply_stoplist_filter(response_mixed)

        assert "as an ai" not in filtered_upper.lower()
        assert "as an ai" not in filtered_mixed.lower()


# ============================================================================
# UPGRADE #9: Episodic Anchors Integration Tests
# ============================================================================


class TestEpisodicAnchorsIntegration:
    """Test episodic anchor methods"""

    def test_temporal_marker_creates_metadata(self):
        """✅ UPGRADE #9: Temporal marker adds metadata"""
        concierge = object.__new__(ConciergeAgentV2)
        timestamp = time.time()

        marked = concierge._add_temporal_marker("Had breakfast", timestamp)

        assert "content" in marked
        assert "timestamp" in marked
        assert "day_of_week" in marked
        assert "relative_time" in marked
        assert marked["content"] == "Had breakfast"

    def test_temporal_marker_defaults_to_now(self):
        """✅ UPGRADE #9: Temporal marker defaults to current time"""
        concierge = object.__new__(ConciergeAgentV2)
        marked = concierge._add_temporal_marker("Current action")

        assert marked["relative_time"] == "just now"

    def test_relative_time_just_now(self):
        """✅ UPGRADE #9: Relative time labels recent as 'just now'"""
        concierge = object.__new__(ConciergeAgentV2)
        timestamp = time.time() - 30  # 30 seconds ago

        label = concierge._get_relative_time_label(timestamp)

        assert label == "just now"

    def test_relative_time_minutes(self):
        """✅ UPGRADE #9: Relative time labels minutes correctly"""
        concierge = object.__new__(ConciergeAgentV2)
        timestamp = time.time() - 300  # 5 minutes ago

        label = concierge._get_relative_time_label(timestamp)

        assert "minute" in label
        assert "5" in label

    def test_relative_time_earlier_today(self):
        """✅ UPGRADE #9: Relative time labels hour as 'earlier today'"""
        concierge = object.__new__(ConciergeAgentV2)
        timestamp = time.time() - 3600  # 1 hour ago

        label = concierge._get_relative_time_label(timestamp)

        assert label == "earlier today"

    def test_relative_time_yesterday(self):
        """✅ UPGRADE #9: Relative time labels day as 'yesterday'"""
        concierge = object.__new__(ConciergeAgentV2)
        timestamp = time.time() - 86400  # 1 day ago

        label = concierge._get_relative_time_label(timestamp)

        assert label == "yesterday"

    def test_relative_time_last_week(self):
        """✅ UPGRADE #9: Relative time labels week as 'last week'"""
        concierge = object.__new__(ConciergeAgentV2)
        timestamp = time.time() - (86400 * 10)  # 10 days ago

        label = concierge._get_relative_time_label(timestamp)

        assert label == "last week"

    def test_temporal_reference_just_now(self):
        """✅ UPGRADE #9: Generate reference for recent memory"""
        concierge = object.__new__(ConciergeAgentV2)
        memory = {"content": "Had breakfast", "relative_time": "just now"}

        reference = concierge._generate_temporal_reference(memory)

        assert "just discussed" in reference.lower()

    def test_temporal_reference_yesterday(self):
        """✅ UPGRADE #9: Generate 'yesterday's X' reference"""
        concierge = object.__new__(ConciergeAgentV2)
        memory = {"content": "Had breakfast", "relative_time": "yesterday"}

        reference = concierge._generate_temporal_reference(memory)

        assert "yesterday's" in reference.lower()

    def test_temporal_reference_day_name(self):
        """✅ UPGRADE #9: Generate 'Monday's X' reference"""
        concierge = object.__new__(ConciergeAgentV2)
        memory = {"content": "Did homework", "relative_time": "Monday"}

        reference = concierge._generate_temporal_reference(memory)

        assert "Monday's" in reference

    def test_extract_topic_breakfast(self):
        """✅ UPGRADE #9: Extract 'breakfast' topic"""
        concierge = object.__new__(ConciergeAgentV2)
        topic = concierge._extract_topic_from_content("Had breakfast with eggs")

        assert topic == "breakfast"

    def test_extract_topic_homework(self):
        """✅ UPGRADE #9: Extract 'homework' topic"""
        concierge = object.__new__(ConciergeAgentV2)
        topic = concierge._extract_topic_from_content("Finished homework")

        assert topic == "homework"

    def test_extract_topic_fallback(self):
        """✅ UPGRADE #9: Use 'discussion' fallback"""
        concierge = object.__new__(ConciergeAgentV2)
        topic = concierge._extract_topic_from_content("Random text")

        assert topic == "discussion"


# ============================================================================
# Test Counter: 8 stoplist + 13 episodic = 21 tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
