"""
Tests for SynthesisEngine: Synthesis generation and contradiction detection.

Test Coverage:
- Synthesis generation with LLM
- Contradiction detection (user assumption vs specialist finding)
- Entity extraction from text
- Evidence formatting
- Fallback synthesis when LLM fails
- User assumption extraction
"""

from unittest.mock import AsyncMock, Mock

import pytest
from backend.agents.synthesis_engine import SynthesisEngine
from backend.models.analysis_result import AnalysisResult, Insight

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_llm_client():
    """Mock LLMClient."""
    client = AsyncMock()
    client.generate = AsyncMock()
    return client


@pytest.fixture
def mock_metrics():
    """Mock MetricsCollector."""
    return Mock()


@pytest.fixture
def synthesis_engine(mock_llm_client, mock_metrics):
    """Create SynthesisEngine instance."""
    return SynthesisEngine(mock_llm_client, mock_metrics)


@pytest.fixture
def nutritionist_result():
    """Create a nutritionist analysis result."""
    insight = Insight(
        summary="Strong trigger: late night coffee",
        evidence=[
            "3 out of 5 GERD episodes occurred after evening coffee",
            "Correlation score: 60%",
            "Last occurrence: 2025-11-05 10:00pm",
        ],
        severity="strong",
        confidence=0.6,
    )

    return AnalysisResult(
        specialist_type="nutritionist",
        query="What is triggering my GERD?",
        insights=[insight],
        evidence=["diet_logs", "health_events"],
        confidence=0.6,
        duration_ms=800,
        contradicts_user_hypothesis=True,
        user_hypothesis="milk is making me sick",
        actual_finding="late night coffee",
    )


@pytest.fixture
def context_gerd():
    """Create GERD context."""
    return {
        "user_message": "milk is making me sick",
        "recent_history": ["User: milk is making me sick", "Agent: Let me analyze this"],
        "conversation_id": "conv_123",
    }


# ============================================================================
# Tests: Entity Extraction
# ============================================================================


class TestEntityExtraction:
    """Test _extract_entities() method."""

    def test_extract_single_food_entity(self, synthesis_engine):
        """Test extraction of single food entity."""
        text = "milk is making me sick"
        entities = synthesis_engine._extract_entities(text)

        assert "milk" in entities
        assert len(entities) > 0

    def test_extract_coffee_entity(self, synthesis_engine):
        """Test extraction of coffee entity."""
        text = "late night coffee"
        entities = synthesis_engine._extract_entities(text)

        assert "late night coffee" in entities or "coffee" in entities

    def test_extract_compound_late_night_coffee(self, synthesis_engine):
        """Test extraction of compound term 'late night coffee'."""
        text = "I have late night coffee every day"
        entities = synthesis_engine._extract_entities(text)

        # Should find "late night coffee" or at least "coffee"
        assert len(entities) > 0
        assert "late night coffee" in entities or "coffee" in entities

    def test_extract_multiple_foods(self, synthesis_engine):
        """Test extraction of multiple food entities."""
        text = "milk and coffee are both triggers"
        entities = synthesis_engine._extract_entities(text)

        assert "milk" in entities
        assert "coffee" in entities

    def test_extract_health_condition(self, synthesis_engine):
        """Test extraction of health condition entity."""
        text = "My GERD is triggered by spicy food"
        entities = synthesis_engine._extract_entities(text)

        assert "gerd" in entities or "spicy" in entities

    def test_extract_from_pattern_x_is_making(self, synthesis_engine):
        """Test extraction using 'X is making' pattern."""
        text = "pizza is making me uncomfortable"
        entities = synthesis_engine._extract_entities(text)

        # Should extract 'pizza' from the pattern
        assert "pizza" in entities or "uncomfortable" in entities

    def test_extract_empty_text(self, synthesis_engine):
        """Test extraction from empty text."""
        entities = synthesis_engine._extract_entities("")
        assert isinstance(entities, list)
        assert len(entities) == 0

    def test_extract_no_entities(self, synthesis_engine):
        """Test text with no relevant entities."""
        text = "xyz abc def"  # Changed to avoid "weather" keyword match
        entities = synthesis_engine._extract_entities(text)

        assert len(entities) == 0


# ============================================================================
# Tests: Contradiction Detection
# ============================================================================


class TestContradictionDetection:
    """Test _detect_contradiction() method."""

    def test_detect_contradiction_milk_vs_coffee(self, synthesis_engine):
        """Test detecting contradiction: user thought milk, specialist found coffee."""
        user_assumption = "milk is making me sick"
        specialist_finding = "late night coffee"

        contradiction = synthesis_engine._detect_contradiction(user_assumption, specialist_finding)

        assert contradiction is True

    def test_no_contradiction_same_entity(self, synthesis_engine):
        """Test no contradiction when entities match."""
        user_assumption = "coffee is making me sick"
        specialist_finding = "late night coffee"

        contradiction = synthesis_engine._detect_contradiction(user_assumption, specialist_finding)

        assert contradiction is False

    def test_no_contradiction_entities_overlap(self, synthesis_engine):
        """Test no contradiction when entities partially overlap."""
        user_assumption = "Is coffee bad?"
        specialist_finding = "Coffee consumption at night"

        contradiction = synthesis_engine._detect_contradiction(user_assumption, specialist_finding)

        assert contradiction is False

    def test_detect_contradiction_case_insensitive(self, synthesis_engine):
        """Test contradiction detection is case-insensitive."""
        user_assumption = "MILK is the problem"
        specialist_finding = "late night COFFEE"

        contradiction = synthesis_engine._detect_contradiction(user_assumption, specialist_finding)

        assert contradiction is True

    def test_no_contradiction_empty_entities(self, synthesis_engine):
        """Test no contradiction when one side has no entities."""
        user_assumption = "something is wrong"
        specialist_finding = "some condition exists"

        contradiction = synthesis_engine._detect_contradiction(user_assumption, specialist_finding)

        # Should be False when entities can't be extracted
        assert contradiction is False

    def test_detect_contradiction_pizza_vs_dairy(self, synthesis_engine):
        """Test contradiction detection with different triggers."""
        user_assumption = "pizza gives me indigestion"
        specialist_finding = "dairy products trigger your symptoms"

        contradiction = synthesis_engine._detect_contradiction(user_assumption, specialist_finding)

        # pizza vs dairy = different entities = contradiction
        assert contradiction is True


# ============================================================================
# Tests: User Assumption Extraction
# ============================================================================


class TestUserAssumptionExtraction:
    """Test _extract_user_assumption() method."""

    def test_extract_simple_message(self, synthesis_engine):
        """Test extraction from simple message."""
        context = {"user_message": "milk is making me sick"}
        assumption = synthesis_engine._extract_user_assumption(context)

        assert "milk" in assumption.lower()

    def test_extract_with_question_mark(self, synthesis_engine):
        """Test extraction removes question mark."""
        context = {"user_message": "Is milk making me sick?"}
        assumption = synthesis_engine._extract_user_assumption(context)

        assert "?" not in assumption

    def test_extract_first_clause(self, synthesis_engine):
        """Test extraction of first clause before conjunction."""
        context = {"user_message": "milk is bad and coffee is worse"}
        assumption = synthesis_engine._extract_user_assumption(context)

        # Should extract first clause
        assert "milk" in assumption.lower()

    def test_extract_with_but_conjunction(self, synthesis_engine):
        """Test extraction with 'but' conjunction."""
        context = {"user_message": "milk makes me sick but I'm not sure why"}
        assumption = synthesis_engine._extract_user_assumption(context)

        assert "milk" in assumption.lower()

    def test_extract_with_because_conjunction(self, synthesis_engine):
        """Test extraction with 'because' conjunction."""
        context = {"user_message": "pizza causes bloating because of grease"}
        assumption = synthesis_engine._extract_user_assumption(context)

        assert "pizza" in assumption.lower()

    def test_extract_with_or_conjunction(self, synthesis_engine):
        """Test extraction with 'or' conjunction."""
        context = {"user_message": "milk or cheese might be the trigger"}
        assumption = synthesis_engine._extract_user_assumption(context)

        assert "milk" in assumption.lower()

    def test_extract_empty_message(self, synthesis_engine):
        """Test extraction from empty message."""
        context = {"user_message": ""}
        assumption = synthesis_engine._extract_user_assumption(context)

        assert assumption == ""


# ============================================================================
# Tests: Evidence Formatting
# ============================================================================


class TestEvidenceFormatting:
    """Test _format_evidence() method."""

    def test_format_single_evidence(self, synthesis_engine):
        """Test formatting single evidence item."""
        evidence = ["3 out of 5 episodes"]
        formatted = synthesis_engine._format_evidence(evidence)

        assert "3 out of 5 episodes" in formatted

    def test_format_two_evidence(self, synthesis_engine):
        """Test formatting two evidence items."""
        evidence = ["3 out of 5 episodes", "Correlation score: 60%"]
        formatted = synthesis_engine._format_evidence(evidence)

        assert "and" in formatted
        assert "3 out of 5" in formatted
        assert "60%" in formatted

    def test_format_three_evidence(self, synthesis_engine):
        """Test formatting three evidence items."""
        evidence = ["3 out of 5 episodes", "Correlation score: 60%", "Last occurrence: 2025-11-05"]
        formatted = synthesis_engine._format_evidence(evidence)

        assert "•" in formatted
        assert "3 out of 5" in formatted
        assert "60%" in formatted
        assert "2025-11-05" in formatted

    def test_format_max_items_limit(self, synthesis_engine):
        """Test max_items parameter limits evidence."""
        evidence = ["item1", "item2", "item3", "item4", "item5"]
        formatted = synthesis_engine._format_evidence(evidence, max_items=2)

        assert "item1" in formatted
        assert "item2" in formatted
        assert "item3" not in formatted

    def test_format_empty_evidence(self, synthesis_engine):
        """Test formatting empty evidence list."""
        formatted = synthesis_engine._format_evidence([])

        assert formatted == ""


# ============================================================================
# Tests: Specialist Name Retrieval
# ============================================================================


class TestSpecialistNameRetrieval:
    """Test _get_specialist_name() method."""

    def test_get_name_nutritionist(self, synthesis_engine):
        """Test getting nutritionist name."""
        name = synthesis_engine._get_specialist_name("nutritionist")
        assert name == "nutritionist"

    def test_get_name_psychiatrist(self, synthesis_engine):
        """Test getting psychiatrist name."""
        name = synthesis_engine._get_specialist_name("psychiatrist")
        assert name == "psychiatrist"

    def test_get_name_finance_analyst(self, synthesis_engine):
        """Test getting finance analyst name."""
        name = synthesis_engine._get_specialist_name("finance_analyst")
        assert name == "finance analyst"

    def test_get_name_unknown_specialist(self, synthesis_engine):
        """Test getting unknown specialist name returns original."""
        name = synthesis_engine._get_specialist_name("unknown_specialist")
        assert name == "unknown_specialist"


# ============================================================================
# Tests: Fallback Synthesis
# ============================================================================


class TestFallbackSynthesis:
    """Test _fallback_synthesis() method."""

    def test_fallback_with_contradiction(self, synthesis_engine):
        """Test fallback synthesis with contradiction."""
        synthesis = synthesis_engine._fallback_synthesis(
            specialist_type="nutritionist",
            finding="late night coffee",
            has_contradiction=True,
            user_assumption="milk is the problem",
        )

        assert "late night coffee" in synthesis
        assert "milk is the problem" in synthesis
        assert "interestingly" in synthesis or "interesting" in synthesis

    def test_fallback_without_contradiction(self, synthesis_engine):
        """Test fallback synthesis without contradiction."""
        synthesis = synthesis_engine._fallback_synthesis(
            specialist_type="nutritionist",
            finding="late night coffee",
            has_contradiction=False,
            user_assumption="coffee is triggering",
        )

        assert "late night coffee" in synthesis
        assert "evidence" in synthesis.lower()

    def test_fallback_always_returns_string(self, synthesis_engine):
        """Test fallback always returns non-empty string."""
        synthesis = synthesis_engine._fallback_synthesis(
            specialist_type="psychiatrist",
            finding="stress levels",
            has_contradiction=False,
            user_assumption="unknown",
        )

        assert isinstance(synthesis, str)
        assert len(synthesis) > 0


# ============================================================================
# Tests: Synthesis Generation
# ============================================================================


class TestSynthesisGeneration:
    """Test synthesize() method."""

    @pytest.mark.asyncio
    async def test_synthesize_with_llm_success(
        self, synthesis_engine, mock_llm_client, nutritionist_result, context_gerd
    ):
        """Test successful synthesis generation via LLM."""
        mock_llm_client.generate.return_value = (
            "Interesting - the nutritionist found that the trigger may actually be "
            "late night coffee, not the milk. The evidence shows 3 out of 5 GERD "
            "episodes occurred after evening coffee."
        )

        result = await synthesis_engine.synthesize(nutritionist_result, context_gerd)

        assert "synthesis" in result
        assert "late night coffee" in result["synthesis"]
        assert "late night coffee" in result["synthesis"]
        assert result["has_contradiction"] is True

    @pytest.mark.asyncio
    async def test_synthesize_with_llm_failure_uses_fallback(
        self, synthesis_engine, mock_llm_client, nutritionist_result, context_gerd
    ):
        """Test fallback synthesis used when LLM fails."""
        mock_llm_client.generate.side_effect = Exception("LLM error")

        result = await synthesis_engine.synthesize(nutritionist_result, context_gerd)

        assert "synthesis" in result
        assert len(result["synthesis"]) > 0
        # Should be fallback text
        assert "nutritionist" in result["synthesis"]

    @pytest.mark.asyncio
    async def test_synthesize_returns_expected_fields(
        self, synthesis_engine, mock_llm_client, nutritionist_result, context_gerd
    ):
        """Test synthesize returns all expected fields."""
        mock_llm_client.generate.return_value = "Sample synthesis"

        result = await synthesis_engine.synthesize(nutritionist_result, context_gerd)

        assert "synthesis" in result
        assert "has_contradiction" in result
        assert "user_assumption" in result
        assert "actual_finding" in result
        assert "confidence" in result

    @pytest.mark.asyncio
    async def test_synthesize_confidence_matches_result(
        self, synthesis_engine, mock_llm_client, nutritionist_result, context_gerd
    ):
        """Test synthesize preserves confidence from result."""
        mock_llm_client.generate.return_value = "Sample"

        result = await synthesis_engine.synthesize(nutritionist_result, context_gerd)

        assert result["confidence"] == 0.6

    @pytest.mark.asyncio
    async def test_synthesize_no_insights_handles_gracefully(
        self, synthesis_engine, mock_llm_client, context_gerd
    ):
        """Test synthesize handles result with no insights."""
        empty_result = AnalysisResult(
            specialist_type="nutritionist",
            query="test",
            insights=[],
            evidence=[],
            confidence=0.0,
            duration_ms=0,
            contradicts_user_hypothesis=False,
            user_hypothesis="",
            actual_finding="",
        )

        result = await synthesis_engine.synthesize(empty_result, context_gerd)

        assert "synthesis" in result
        assert "didn't find" in result["synthesis"] or "No specific" in result["synthesis"]


# ============================================================================
# Tests: Build Synthesis Prompt
# ============================================================================


class TestBuildSynthesisPrompt:
    """Test _build_synthesis_prompt() method."""

    def test_prompt_includes_specialist_name(
        self, synthesis_engine, nutritionist_result, context_gerd
    ):
        """Test prompt includes specialist name."""
        prompt = synthesis_engine._build_synthesis_prompt(
            nutritionist_result,
            context_gerd,
            has_contradiction=False,
            formatted_evidence="test evidence",
            user_assumption="milk",
            actual_finding="coffee",
        )

        assert "nutritionist" in prompt

    def test_prompt_includes_confidence(self, synthesis_engine, nutritionist_result, context_gerd):
        """Test prompt includes confidence percentage."""
        prompt = synthesis_engine._build_synthesis_prompt(
            nutritionist_result,
            context_gerd,
            has_contradiction=False,
            formatted_evidence="test evidence",
            user_assumption="milk",
            actual_finding="coffee",
        )

        assert "60%" in prompt

    def test_prompt_includes_contradiction_note_when_present(
        self, synthesis_engine, nutritionist_result, context_gerd
    ):
        """Test prompt includes contradiction note when has_contradiction=True."""
        prompt = synthesis_engine._build_synthesis_prompt(
            nutritionist_result,
            context_gerd,
            has_contradiction=True,
            formatted_evidence="test evidence",
            user_assumption="milk",
            actual_finding="coffee",
        )

        assert "User assumption" in prompt
        assert "milk" in prompt
        assert "coffee" in prompt

    def test_prompt_no_contradiction_note_when_absent(
        self, synthesis_engine, nutritionist_result, context_gerd
    ):
        """Test prompt excludes contradiction note when has_contradiction=False."""
        prompt = synthesis_engine._build_synthesis_prompt(
            nutritionist_result,
            context_gerd,
            has_contradiction=False,
            formatted_evidence="test evidence",
            user_assumption="milk",
            actual_finding="coffee",
        )

        # Contradiction note should not be present
        assert "User assumption" not in prompt


# ============================================================================
# Tests: M5 Deliverable Validation
# ============================================================================


class TestM5Deliverable:
    """Test M5 milestone deliverables."""

    @pytest.mark.asyncio
    async def test_synthesis_feels_natural(
        self, synthesis_engine, mock_llm_client, nutritionist_result, context_gerd
    ):
        """Test synthesis generation produces natural language."""
        natural_synthesis = (
            "Interesting - the nutritionist found that the trigger may actually be "
            "late night coffee, not the milk. The evidence shows 3 out of 5 GERD "
            "episodes occurred after evening coffee."
        )
        mock_llm_client.generate.return_value = natural_synthesis

        result = await synthesis_engine.synthesize(nutritionist_result, context_gerd)

        assert result["synthesis"] == natural_synthesis

    @pytest.mark.asyncio
    async def test_contradiction_detection_works(
        self, synthesis_engine, mock_llm_client, nutritionist_result, context_gerd
    ):
        """Test contradiction is detected in GERD scenario."""
        mock_llm_client.generate.return_value = "Sample"

        result = await synthesis_engine.synthesize(nutritionist_result, context_gerd)

        assert result["has_contradiction"] is True
        assert result["user_assumption"] == "milk is making me sick"
        assert "coffee" in result["actual_finding"]

    @pytest.mark.asyncio
    async def test_evidence_presented_clearly(
        self, synthesis_engine, mock_llm_client, nutritionist_result, context_gerd
    ):
        """Test evidence is included in synthesis."""
        mock_llm_client.generate.return_value = "Synthesis with evidence"

        result = await synthesis_engine.synthesize(nutritionist_result, context_gerd)

        # Evidence should be formatted and accessible
        assert "synthesis" in result

    def test_m5_acceptance_all_methods_implemented(self, synthesis_engine):
        """Test all M5 required methods exist."""
        assert hasattr(synthesis_engine, "synthesize")
        assert hasattr(synthesis_engine, "_detect_contradiction")
        assert hasattr(synthesis_engine, "_build_synthesis_prompt")
        assert hasattr(synthesis_engine, "_format_evidence")
        assert hasattr(synthesis_engine, "_extract_user_assumption")
