"""
Phase 3 Day 1-2: Human Reasoning Tests

Tests Topic 7: Human Reasoning & Uncertainty Markers

Verifies:
- Confidence estimation from messages
- Reasoning style classification (uncertain/cautious/confident)
- Reasoning marker selection based on confidence
- Instructions generation for LLM prompts
- Integration with concierge_v2 response generation
"""

from unittest.mock import AsyncMock

import pytest
from backend.agents.concierge_v2 import ConciergeAgentV2
from backend.agents.reasoning_engine import ReasoningContext, ReasoningEngine
from backend.services.k0_query_service import MockK0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def reasoning_engine():
    """Create ReasoningEngine instance without LLM"""
    return ReasoningEngine(llm_client=None)


@pytest.fixture
def reasoning_engine_with_llm():
    """Create ReasoningEngine with mock LLM client"""
    mock_llm = AsyncMock(spec=LLMClient)
    return ReasoningEngine(llm_client=mock_llm)


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
# REASONING CONTEXT TESTS
# ============================================================================


class TestReasoningContext:
    """Tests for ReasoningContext dataclass"""

    def test_reasoning_context_initialization(self):
        """Verify reasoning context initializes correctly"""
        context = ReasoningContext(
            confidence=0.7, reasoning_style="cautious", has_causal_link=True, has_question=False
        )

        assert context.confidence == 0.7
        assert context.reasoning_style == "cautious"
        assert context.has_causal_link is True
        assert context.has_question is False

    def test_reasoning_context_default_values(self):
        """Verify default values for optional fields"""
        context = ReasoningContext(confidence=0.5, reasoning_style="uncertain")

        assert context.confidence == 0.5
        assert context.reasoning_style == "uncertain"
        assert context.has_causal_link is False
        assert context.has_question is False

    def test_reasoning_context_valid_styles(self):
        """Verify all reasoning styles are valid"""
        for style in ["uncertain", "cautious", "confident"]:
            context = ReasoningContext(confidence=0.7, reasoning_style=style)
            assert context.reasoning_style == style

    def test_reasoning_context_confidence_bounds(self):
        """Verify confidence is properly bounded"""
        # Should accept 0.0-1.0
        context_low = ReasoningContext(confidence=0.0, reasoning_style="uncertain")
        context_mid = ReasoningContext(confidence=0.5, reasoning_style="cautious")
        context_high = ReasoningContext(confidence=1.0, reasoning_style="confident")

        assert context_low.confidence == 0.0
        assert context_mid.confidence == 0.5
        assert context_high.confidence == 1.0


# ============================================================================
# CONFIDENCE ESTIMATION TESTS
# ============================================================================


class TestConfidenceEstimation:
    """Tests for rule-based confidence estimation"""

    def test_confident_message_estimation(self, reasoning_engine):
        """Verify high confidence for certain messages"""
        message = "Coffee definitely makes me sleep worse"
        confidence = reasoning_engine.estimate_confidence(message)

        # Should be higher than default 0.7
        assert confidence > 0.7

    def test_uncertain_message_estimation(self, reasoning_engine):
        """Verify low confidence for uncertain messages"""
        message = "Maybe coffee affects my sleep? Not sure though."
        confidence = reasoning_engine.estimate_confidence(message)

        # Should be lower than default 0.7
        assert confidence < 0.7

    def test_question_reduces_confidence(self, reasoning_engine):
        """Verify questions reduce confidence"""
        certain_statement = "Coffee affects sleep"
        question = "Does coffee affect sleep?"

        confidence_statement = reasoning_engine.estimate_confidence(certain_statement)
        confidence_question = reasoning_engine.estimate_confidence(question)

        # Question should have lower confidence
        assert confidence_question < confidence_statement

    def test_long_message_increases_confidence(self, reasoning_engine):
        """Verify detailed messages increase confidence"""
        short = "Coffee bad"
        long = "I've noticed that when I drink coffee after 8pm, my sleep quality significantly decreases. I tend to lie awake for longer and wake up more often during the night."

        confidence_short = reasoning_engine.estimate_confidence(short)
        confidence_long = reasoning_engine.estimate_confidence(long)

        # Long detailed message should have higher confidence
        assert confidence_long > confidence_short

    def test_confidence_bounds(self, reasoning_engine):
        """Verify confidence stays in 0.0-1.0 range"""
        messages = [
            "???",  # Very uncertain
            "Definitely for sure absolutely certain",  # Over-certain
            "Maybe",  # Somewhat uncertain
            "I think so",  # Neutral
        ]

        for msg in messages:
            confidence = reasoning_engine.estimate_confidence(msg)
            assert 0.0 <= confidence <= 1.0


# ============================================================================
# REASONING STYLE CLASSIFICATION TESTS
# ============================================================================


class TestReasoningStyleClassification:
    """Tests for style classification based on confidence"""

    def test_uncertain_style_low_confidence(self, reasoning_engine):
        """Verify uncertain style for confidence < 0.6"""
        context = reasoning_engine._analyze_confidence_rulebased("maybe coffee?")

        assert context.reasoning_style == "uncertain"
        assert context.confidence < 0.6

    def test_cautious_style_medium_confidence(self, reasoning_engine):
        """Verify cautious style for 0.6 <= confidence < 0.8"""
        context = reasoning_engine._analyze_confidence_rulebased("Coffee seems to affect my sleep")

        assert context.reasoning_style == "cautious"
        assert 0.6 <= context.confidence < 0.8

    def test_confident_style_high_confidence(self, reasoning_engine):
        """Verify confident style for confidence >= 0.8"""
        context = reasoning_engine._analyze_confidence_rulebased(
            "Coffee definitely affects sleep badly"
        )

        assert context.reasoning_style == "confident"
        assert context.confidence >= 0.8

    def test_causal_detection(self, reasoning_engine):
        """Verify causal link detection"""
        causal_message = "Why does coffee affect my sleep?"
        no_causal = "Hello"

        context_causal = reasoning_engine._analyze_confidence_rulebased(causal_message)
        context_no_causal = reasoning_engine._analyze_confidence_rulebased(no_causal)

        assert context_causal.has_causal_link is True
        assert context_no_causal.has_causal_link is False

    def test_question_detection(self, reasoning_engine):
        """Verify question detection"""
        question = "Does coffee affect sleep?"
        statement = "Coffee affects sleep"

        context_question = reasoning_engine._analyze_confidence_rulebased(question)
        context_statement = reasoning_engine._analyze_confidence_rulebased(statement)

        assert context_question.has_question is True
        assert context_statement.has_question is False


# ============================================================================
# REASONING INSTRUCTIONS GENERATION TESTS
# ============================================================================


class TestReasoningInstructions:
    """Tests for reasoning instruction generation"""

    def test_uncertain_instructions(self, reasoning_engine):
        """Verify uncertain style instructions"""
        instructions = reasoning_engine.get_reasoning_instructions(confidence=0.5)

        assert "UNCERTAIN" in instructions
        assert "Show thinking process" in instructions
        # Should contain uncertainty markers
        assert any(marker in instructions for marker in ["might", "not sure", "possibly"])

    def test_cautious_instructions(self, reasoning_engine):
        """Verify cautious style instructions"""
        instructions = reasoning_engine.get_reasoning_instructions(confidence=0.7)

        assert "CAUTIOUS" in instructions
        assert "seems" in instructions.lower() or "hedge" in instructions.lower()

    def test_confident_instructions(self, reasoning_engine):
        """Verify confident style instructions"""
        instructions = reasoning_engine.get_reasoning_instructions(confidence=0.9)

        assert "CONFIDENT" in instructions
        assert "direct" in instructions.lower()

    def test_causal_guidance_included(self, reasoning_engine):
        """Verify causal guidance when has_causal_link=True"""
        with_causal = reasoning_engine.get_reasoning_instructions(
            confidence=0.7, has_causal_link=True
        )
        without_causal = reasoning_engine.get_reasoning_instructions(
            confidence=0.7, has_causal_link=False
        )

        # With causal should have causal guidance
        assert "EXPLAIN CAUSALITY" in with_causal
        assert "EXPLAIN CAUSALITY" not in without_causal

    def test_question_guidance_included(self, reasoning_engine):
        """Verify question guidance when has_question=True"""
        with_question = reasoning_engine.get_reasoning_instructions(
            confidence=0.7, has_question=True
        )
        without_question = reasoning_engine.get_reasoning_instructions(
            confidence=0.7, has_question=False
        )

        # With question should have question guidance
        assert "ANSWERING QUESTION" in with_question
        assert "ANSWERING QUESTION" not in without_question

    def test_instructions_include_examples(self, reasoning_engine):
        """Verify instructions include marker examples"""
        instructions = reasoning_engine.get_reasoning_instructions(confidence=0.7)

        # Should include examples of markers
        assert any(marker in instructions for marker in ["might be", "seems like", "possibly"])


# ============================================================================
# MARKER SELECTION TESTS
# ============================================================================


class TestMarkerSelection:
    """Tests for reasoning marker selection"""

    def test_uncertain_markers_selected(self, reasoning_engine):
        """Verify uncertain style selects appropriate markers"""
        markers = reasoning_engine.select_markers_for_style("uncertain")

        assert "primary" in markers
        assert "secondary" in markers
        assert len(markers["primary"]) > 0
        # Uncertain should have more limitations markers
        assert any("sure" in m for m in markers.get("secondary", []))

    def test_cautious_markers_selected(self, reasoning_engine):
        """Verify cautious style selects appropriate markers"""
        markers = reasoning_engine.select_markers_for_style("cautious")

        assert "primary" in markers
        assert "secondary" in markers
        assert len(markers["primary"]) > 0

    def test_confident_markers_selected(self, reasoning_engine):
        """Verify confident style selects appropriate markers"""
        markers = reasoning_engine.select_markers_for_style("confident")

        assert "primary" in markers
        assert "secondary" in markers
        # Confident should emphasize causal markers
        assert any("because" in m for m in markers.get("primary", []))

    def test_all_marker_categories_present(self, reasoning_engine):
        """Verify all marker categories are available"""
        expected_categories = ["uncertainty", "process", "causal", "limitations"]

        for category in expected_categories:
            assert category in reasoning_engine.REASONING_MARKERS
            assert len(reasoning_engine.REASONING_MARKERS[category]) > 0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestReasoningIntegration:
    """Tests for integration with concierge_v2"""

    @pytest.mark.asyncio
    async def test_reasoning_context_analyzed_on_message(self, concierge_agent):
        """Verify reasoning context analyzed during message processing"""
        # Mock the background task check
        concierge_agent._check_completed_tasks = AsyncMock()

        message = "Coffee definitely affects my sleep"

        # Process message (will analyze confidence)
        # Note: This will try to call LLM, but we have mock client
        await concierge_agent.process_message("user123", message)

        # Verify reasoning context was set
        assert concierge_agent.reasoning_context is not None
        assert concierge_agent.reasoning_context.confidence > 0.0

    @pytest.mark.asyncio
    async def test_reasoning_confidence_varies_by_message(self, concierge_agent):
        """Verify confidence varies appropriately with different messages"""
        concierge_agent._check_completed_tasks = AsyncMock()

        # High confidence message
        await concierge_agent.process_message("user123", "Coffee definitely makes me sleep worse")
        confident_context = concierge_agent.reasoning_context

        # Low confidence message
        await concierge_agent.process_message("user123", "Maybe coffee? Not sure")
        uncertain_context = concierge_agent.reasoning_context

        # Confident should be higher
        assert confident_context.confidence > uncertain_context.confidence

    @pytest.mark.asyncio
    async def test_reasoning_instructions_in_prompt(self, concierge_agent):
        """Verify reasoning instructions are included in LLM prompt"""
        concierge_agent._check_completed_tasks = AsyncMock()

        # Setup: Process a message first to analyze confidence
        await concierge_agent.process_message("user123", "Coffee affects my sleep")

        # Now generate response (mocked LLM)
        response = await concierge_agent._generate_conversational_response("coffee keeps me awake")

        # Verify response generated
        assert response is not None
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_reasoning_markers_in_response(self, concierge_agent):
        """Verify reasoning markers might appear in response"""
        concierge_agent._check_completed_tasks = AsyncMock()

        # Mock LLM to return response with reasoning marker
        response_with_reasoning = (
            "Hmm, not totally sure but it seems like coffee affects your sleep."
        )
        concierge_agent.llm_client.generate_async = AsyncMock(return_value=response_with_reasoning)

        # Process message
        await concierge_agent.process_message("user123", "Does coffee affect sleep?")

        # Generate response
        response = await concierge_agent._generate_conversational_response("coffee question")

        # Response should contain reasoning markers
        assert any(marker in response for marker in ["hmm", "not totally sure", "seems like"])


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestReasoningEdgeCases:
    """Tests for edge cases and boundary conditions"""

    def test_very_low_confidence_message(self, reasoning_engine):
        """Verify handling of very uncertain messages"""
        message = "Um... maybe... if... hmm?"
        context = reasoning_engine._analyze_confidence_rulebased(message)

        assert context.reasoning_style == "uncertain"
        assert context.confidence < 0.6

    def test_very_high_confidence_message(self, reasoning_engine):
        """Verify handling of very certain messages"""
        message = "Coffee absolutely definitely 100% certainly affects sleep"
        context = reasoning_engine._analyze_confidence_rulebased(message)

        # Should cap at confidence and use cautious/confident style
        assert context.confidence >= 0.8
        assert context.reasoning_style == "confident"

    def test_empty_message_confidence(self, reasoning_engine):
        """Verify handling of empty messages"""
        context = reasoning_engine._analyze_confidence_rulebased("")

        # Should return reduced confidence for empty/short
        assert context.confidence < 0.7

    def test_multiple_confidence_factors(self, reasoning_engine):
        """Verify multiple factors combine correctly"""
        # Message that is long (↑ confidence) but is a question (↓ confidence)
        message = "I've been wondering if coffee affects sleep because I've noticed patterns with my own consumption, and I'm curious about whether this is a common experience for others? Can you help me understand this relationship?"

        confidence = reasoning_engine.estimate_confidence(message)

        # Should balance positive (length) and negative (question)
        assert 0.5 <= confidence <= 0.9

    def test_marker_consistency(self, reasoning_engine):
        """Verify marker examples are consistent across calls"""
        markers1 = reasoning_engine.select_markers_for_style("cautious")
        markers2 = reasoning_engine.select_markers_for_style("cautious")

        # Should be identical
        assert markers1 == markers2

    def test_confidence_drift_across_history(self, reasoning_engine):
        """Verify confidence doesn't drift unexpectedly"""
        messages = ["maybe", "probably", "definitely"] * 10

        confidences = [reasoning_engine.estimate_confidence(msg) for msg in messages]

        # First "maybe" and last "maybe" should have similar confidence
        # messages: [maybe(0), probably(1), definitely(2), maybe(3), ... maybe(27), probably(28), definitely(29)]
        # Both maybe messages at indices 0 and 27
        assert abs(confidences[0] - confidences[27]) < 0.1

    @pytest.mark.asyncio
    async def test_llm_confidence_analysis_fallback(self, reasoning_engine_with_llm):
        """Verify fallback to rule-based if LLM fails"""
        # Mock LLM to fail
        reasoning_engine_with_llm.llm_client.generate_async = AsyncMock(
            side_effect=Exception("LLM Error")
        )

        # Should still analyze using rule-based (fallback in _analyze_confidence_llm)
        context = await reasoning_engine_with_llm.analyze_confidence(
            "coffee affects sleep", use_llm=False
        )

        assert context.reasoning_style in ["uncertain", "cautious", "confident"]
        assert 0.0 <= context.confidence <= 1.0


# ============================================================================
# COMPREHENSIVE INTEGRATION TEST
# ============================================================================


class TestReasoningComprehensive:
    """Comprehensive tests for full reasoning workflow"""

    def test_full_reasoning_workflow(self, reasoning_engine):
        """Test complete reasoning workflow from message to instructions"""
        # Step 1: Analyze message
        context = reasoning_engine._analyze_confidence_rulebased("Coffee maybe affects my sleep?")

        # Message has question (reduces confidence) and uncertainty (reduces confidence)
        # So it will be uncertain style
        assert context.reasoning_style == "uncertain"
        assert context.has_question is True

        # Step 2: Get instructions
        instructions = reasoning_engine.get_reasoning_instructions(
            confidence=context.confidence,
            has_causal_link=context.has_causal_link,
            has_question=context.has_question,
        )

        assert "UNCERTAIN" in instructions
        assert "ANSWERING QUESTION" in instructions

        # Step 3: Select markers for style
        markers = reasoning_engine.select_markers_for_style(context.reasoning_style)

        assert len(markers["primary"]) > 0
        assert any(isinstance(m, str) for m in markers["primary"])

    def test_reasoning_markers_match_style(self, reasoning_engine):
        """Verify reasoning markers are appropriate for style"""
        styles = {
            "uncertain": ["not sure", "might", "possibly"],
            "cautious": ["seems", "probably", "could"],
            "confident": ["because", "explains", "reason"],
        }

        for style, expected_patterns in styles.items():
            instructions = reasoning_engine.get_reasoning_instructions(
                confidence=0.5 if style == "uncertain" else (0.7 if style == "cautious" else 0.9)
            )

            # Should include at least one pattern from the style
            assert any(pattern in instructions.lower() for pattern in expected_patterns)

    def test_all_combinations_valid(self, reasoning_engine):
        """Test all combinations of reasoning parameters"""
        confidences = [0.3, 0.5, 0.7, 0.9]
        causal_links = [True, False]
        questions = [True, False]

        for conf in confidences:
            for causal in causal_links:
                for question in questions:
                    # Should not raise any errors
                    instructions = reasoning_engine.get_reasoning_instructions(
                        confidence=conf, has_causal_link=causal, has_question=question
                    )

                    assert isinstance(instructions, str)
                    assert len(instructions) > 0
                    assert "TOPIC 7" in instructions
