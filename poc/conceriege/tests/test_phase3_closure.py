"""
Phase 3 Day 6-7: Topic 10 - Graceful Closure Testing

Comprehensive testing for conversation closure detection and graceful endings.

Test Coverage:
- Closure pattern recognition (resolution, correction, acceptance)
- Closure instruction generation
- Integration with ConciergeAgentV2
- Edge cases and consistency
"""

from unittest.mock import MagicMock

import pytest
from backend.agents.concierge_v2 import CLOSURE_PATTERNS, ConciergeAgentV2


class TestClosurePatterns:
    """Test CLOSURE_PATTERNS constants"""

    def test_closure_patterns_exist(self):
        """CLOSURE_PATTERNS should have all required keys"""
        assert "resolution_markers" in CLOSURE_PATTERNS
        assert "correction_markers" in CLOSURE_PATTERNS
        assert "warm_closures" in CLOSURE_PATTERNS
        assert "next_step_offers" in CLOSURE_PATTERNS
        assert "acceptance_phrases" in CLOSURE_PATTERNS

    def test_resolution_markers_populated(self):
        """Resolution markers should be a non-empty list"""
        markers = CLOSURE_PATTERNS["resolution_markers"]
        assert isinstance(markers, list)
        assert len(markers) > 0
        assert all(isinstance(m, str) for m in markers)
        # Common resolution markers should be present
        assert "thanks" in markers or "thank you" in markers

    def test_correction_markers_populated(self):
        """Correction markers should be a non-empty list"""
        markers = CLOSURE_PATTERNS["correction_markers"]
        assert isinstance(markers, list)
        assert len(markers) > 0
        assert all(isinstance(m, str) for m in markers)
        # Common correction markers should be present
        assert "actually" in markers or "no" in markers

    def test_warm_closures_populated(self):
        """Warm closures should be complete sentences"""
        closures = CLOSURE_PATTERNS["warm_closures"]
        assert isinstance(closures, list)
        assert len(closures) > 0
        assert all(isinstance(c, str) for c in closures)
        # Each closure should be reasonably complete
        assert all(len(c) > 10 for c in closures)

    def test_next_step_offers_populated(self):
        """Next step offers should be question-like"""
        offers = CLOSURE_PATTERNS["next_step_offers"]
        assert isinstance(offers, list)
        assert len(offers) > 0
        assert all(isinstance(o, str) for o in offers)
        # Most should end with ?
        assert all("?" in o for o in offers)


class TestClosureDetection:
    """Test closure detection methods"""

    @pytest.fixture
    def agent(self):
        """Fixture for ConciergeAgentV2 instance"""
        agent = ConciergeAgentV2(
            llm_client=MagicMock(),
            k0_query_service=MagicMock(),
            metrics_collector=MagicMock(),
        )
        return agent

    def test_detect_thread_closure_with_thanks(self, agent):
        """'thanks' should trigger closure detection"""
        message = "thanks for your help!"
        assert agent._detect_thread_closure(message) is True

    def test_detect_thread_closure_with_thank_you(self, agent):
        """'thank you' should trigger closure detection"""
        message = "thank you so much"
        assert agent._detect_thread_closure(message) is True

    def test_detect_thread_closure_with_got_it(self, agent):
        """'got it' should trigger closure detection"""
        message = "got it, I understand now"
        assert agent._detect_thread_closure(message) is True

    def test_detect_thread_closure_no_markers(self, agent):
        """Message without markers should not trigger closure"""
        message = "what about coffee though?"
        assert agent._detect_thread_closure(message) is False

    def test_detect_user_correction_with_actually(self, agent):
        """'actually' should trigger correction detection"""
        message = "actually, I think that's not quite right"
        assert agent._detect_user_correction(message) is True

    def test_detect_user_correction_with_no(self, agent):
        """'no' should trigger correction detection"""
        message = "no, that's not what I meant"
        assert agent._detect_user_correction(message) is True


class TestClosureInstructions:
    """Test closure instruction generation"""

    @pytest.fixture
    def agent(self):
        """Fixture for ConciergeAgentV2 instance"""
        agent = ConciergeAgentV2(
            llm_client=MagicMock(),
            k0_query_service=MagicMock(),
            metrics_collector=MagicMock(),
        )
        return agent

    def test_get_closure_instructions_returns_string(self, agent):
        """get_closure_instructions should return string"""
        message = "thanks for the help"
        instructions = agent._get_closure_instructions(message)

        assert isinstance(instructions, str)
        assert len(instructions) > 0
        assert "TOPIC 10" in instructions

    def test_closure_instructions_for_closure_message(self, agent):
        """Closure message should get closure-specific instructions"""
        message = "got it, thank you!"
        instructions = agent._get_closure_instructions(message)

        assert "closing" in instructions.lower() or "closure" in instructions.lower()

    def test_closure_instructions_for_correction_message(self, agent):
        """Correction message should get correction-specific instructions"""
        message = "actually no, that's not quite right"
        instructions = agent._get_closure_instructions(message)

        assert "correct" in instructions.lower() or "disagree" in instructions.lower()


# Run all closure tests - 11 total
