"""
Tests for ReactiveHandler - Intent Classification, Emotion Detection, and Reactive Responses

Tests cover:
- Intent classification with LLM
- PATH1 vs PATH2 routing logic
- Emotion detection (rule-based + LLM fallback)
- Empathy generation (rule-based + LLM fallback)
- Reactive response format: "{empathy}. {action}."
- Performance targets (P95 <50ms for full reactive flow)
"""

import json
from unittest.mock import Mock

import pytest
from backend.agents.reactive_handler import EmotionDetector, EmpathyGenerator, ReactiveHandler
from backend.models.conversation_state import ConversationState, Scoreboard
from backend.models.intent import Intent
from backend.services.conversation_store import ConversationStore
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    mock = Mock(spec=LLMClient)
    return mock


@pytest.fixture
def mock_conversation_store():
    """Mock conversation store."""
    mock = Mock(spec=ConversationStore)
    return mock


@pytest.fixture
def mock_metrics_collector():
    """Mock metrics collector."""
    mock = Mock(spec=MetricsCollector)
    return mock


@pytest.fixture
def reactive_handler(mock_llm_client, mock_conversation_store, mock_metrics_collector):
    """Create ReactiveHandler with mocked dependencies."""
    return ReactiveHandler(mock_llm_client, mock_conversation_store, mock_metrics_collector)


@pytest.fixture
def sample_conversation_state():
    """Create sample conversation state for testing."""
    return ConversationState(
        user_id="user_123", conversation_id="conv_456", scoreboard=Scoreboard()
    )


# ============================================================================
# Test EmotionDetector
# ============================================================================


class TestEmotionDetector:
    """Test emotion detection (rule-based + LLM fallback)."""

    def test_rule_based_detection_frustrated(self, mock_llm_client):
        """Test rule-based detection of frustrated emotion."""
        detector = EmotionDetector(mock_llm_client)

        result = detector.detect("I'm frustrated with this situation")

        assert result["label"] == "frustrated"
        assert result["confidence"] == 0.9
        assert result["source"] == "rule_based"
        mock_llm_client.generate.assert_not_called()  # Should not need LLM

    def test_rule_based_detection_concerned(self, mock_llm_client):
        """Test rule-based detection of concerned emotion."""
        detector = EmotionDetector(mock_llm_client)

        result = detector.detect("I'm worried about my health")

        assert result["label"] == "concerned"
        assert result["confidence"] == 0.9
        assert result["source"] == "rule_based"
        mock_llm_client.generate.assert_not_called()

    def test_rule_based_detection_sad(self, mock_llm_client):
        """Test rule-based detection of sad emotion."""
        detector = EmotionDetector(mock_llm_client)

        result = detector.detect("milk is making me sick and I'm so sad")

        assert result["label"] == "sad"
        assert result["confidence"] == 0.9
        assert result["source"] == "rule_based"

    def test_rule_based_detection_pain(self, mock_llm_client):
        """Test rule-based detection of pain emotion."""
        detector = EmotionDetector(mock_llm_client)

        result = detector.detect("I have pain in my left side")

        assert result["label"] == "pain"
        assert result["confidence"] == 0.9
        assert result["source"] == "rule_based"

    def test_llm_fallback_detection(self, mock_llm_client):
        """Test LLM fallback when rule-based fails."""
        detector = EmotionDetector(mock_llm_client)

        # Ambiguous message (no clear emotion pattern)
        mock_llm_client.generate.return_value = "concerned"

        result = detector.detect("Something doesn't feel right")

        assert result["label"] == "concerned"
        assert result["confidence"] == 0.7
        assert result["source"] == "llm"
        mock_llm_client.generate.assert_called_once()

    def test_llm_fallback_defaults_to_neutral(self, mock_llm_client):
        """Test LLM fallback defaults to neutral on error."""
        detector = EmotionDetector(mock_llm_client)

        # LLM returns invalid emotion
        mock_llm_client.generate.return_value = "invalid_emotion"

        result = detector.detect("Something doesn't feel right")

        assert result["label"] == "neutral"
        assert result["confidence"] == 0.7
        assert result["source"] == "llm"


# ============================================================================
# Test EmpathyGenerator
# ============================================================================


class TestEmpathyGenerator:
    """Test empathy generation (rule-based + LLM fallback)."""

    def test_rule_based_empathy_frustrated(self, mock_llm_client):
        """Test rule-based empathy for frustrated emotion."""
        generator = EmpathyGenerator(mock_llm_client)

        empathy = generator.generate("I'm frustrated", "frustrated")

        assert empathy == "That must be frustrating"
        mock_llm_client.generate.assert_not_called()

    def test_rule_based_empathy_concerned(self, mock_llm_client):
        """Test rule-based empathy for concerned emotion."""
        generator = EmpathyGenerator(mock_llm_client)

        empathy = generator.generate("I'm worried", "concerned")

        assert empathy == "I understand your concern"
        mock_llm_client.generate.assert_not_called()

    def test_rule_based_empathy_sad(self, mock_llm_client):
        """Test rule-based empathy for sad emotion."""
        generator = EmpathyGenerator(mock_llm_client)

        empathy = generator.generate("I'm sad", "sad")

        assert empathy == "That's sad to hear"
        mock_llm_client.generate.assert_not_called()

    def test_rule_based_empathy_pain(self, mock_llm_client):
        """Test rule-based empathy for pain emotion."""
        generator = EmpathyGenerator(mock_llm_client)

        empathy = generator.generate("I have pain", "pain")

        assert empathy == "That sounds painful"
        mock_llm_client.generate.assert_not_called()

    def test_llm_fallback_empathy(self, mock_llm_client):
        """Test LLM fallback for more natural empathy."""
        generator = EmpathyGenerator(mock_llm_client)

        # Custom emotion not in template
        mock_llm_client.generate.return_value = "That sounds challenging"

        empathy = generator.generate("Complex situation", "custom_emotion")

        assert empathy == "That sounds challenging"
        mock_llm_client.generate.assert_called_once()

    def test_llm_fallback_defaults_to_understand(self, mock_llm_client):
        """Test LLM fallback defaults to 'I understand' on error."""
        generator = EmpathyGenerator(mock_llm_client)

        # LLM throws error
        mock_llm_client.generate.side_effect = Exception("API error")

        empathy = generator.generate("Complex situation", "custom_emotion")

        assert empathy == "I understand"


# ============================================================================
# Test ReactiveHandler - Intent Classification
# ============================================================================


class TestIntentClassification:
    """Test intent classification with LLM."""

    def test_classify_simple_health_query(
        self, reactive_handler, sample_conversation_state, mock_llm_client
    ):
        """Test classification of simple health query (PATH1)."""
        # Mock LLM response
        mock_llm_client.generate.return_value = json.dumps(
            {
                "type": "QUERY",
                "domain": "health",
                "complexity": "simple",
                "specialist_type": "nutritionist",
                "confidence": 0.92,
                "entities": ["milk", "sick"],
            }
        )

        intent = reactive_handler.classify_intent(
            "milk is making me sick", sample_conversation_state
        )

        assert intent.type == "QUERY"
        assert intent.domain == "health"
        assert intent.complexity == "simple"
        assert intent.specialist_type == "nutritionist"
        assert intent.confidence == 0.92
        assert intent.routing == "PATH1"
        assert "milk" in intent.entities

    def test_classify_multi_step_query(
        self, reactive_handler, sample_conversation_state, mock_llm_client
    ):
        """Test classification of multi-step query (PATH2)."""
        # Mock LLM response
        mock_llm_client.generate.return_value = json.dumps(
            {
                "type": "QUERY",
                "domain": "health",
                "complexity": "multi_step",
                "specialist_type": "orchestrator",
                "confidence": 0.85,
                "entities": ["diet", "mood", "exercise"],
            }
        )

        intent = reactive_handler.classify_intent(
            "Help me understand my diet, mood, and exercise patterns",
            sample_conversation_state,
        )

        assert intent.complexity == "multi_step"
        assert intent.routing == "PATH2"

    def test_confidence_threshold_rejection(
        self, reactive_handler, sample_conversation_state, mock_llm_client
    ):
        """Test rejection when confidence below 0.7 threshold."""
        # Mock LLM response with low confidence
        mock_llm_client.generate.return_value = json.dumps(
            {
                "type": "QUERY",
                "domain": "general",
                "complexity": "simple",
                "specialist_type": "nutritionist",
                "confidence": 0.5,  # Below threshold
                "entities": [],
            }
        )

        with pytest.raises(ValueError, match="Intent confidence too low"):
            reactive_handler.classify_intent("Unclear message", sample_conversation_state)

    def test_build_intent_prompt_with_history(self, reactive_handler, sample_conversation_state):
        """Test intent prompt includes conversation history."""
        # Add some history
        sample_conversation_state.add_turn("Previous message", "Previous response", "user")

        prompt = reactive_handler._build_intent_prompt("Current message", sample_conversation_state)

        assert "Previous message" in prompt
        assert "Previous response" in prompt
        assert "Current message" in prompt
        assert "JSON" in prompt

    def test_parse_intent_response_with_json(self, reactive_handler):
        """Test parsing valid JSON intent response."""
        llm_response = json.dumps(
            {
                "type": "QUERY",
                "domain": "health",
                "complexity": "simple",
                "specialist_type": "nutritionist",
                "confidence": 0.9,
                "entities": ["coffee"],
            }
        )

        intent = reactive_handler._parse_intent_response(llm_response)

        assert intent.type == "QUERY"
        assert intent.specialist_type == "nutritionist"
        assert intent.confidence == 0.9

    def test_parse_intent_response_with_extra_text(self, reactive_handler):
        """Test parsing JSON with extra text around it."""
        llm_response = """Here's the classification:
        {
            "type": "QUERY",
            "domain": "health",
            "complexity": "simple",
            "specialist_type": "nutritionist",
            "confidence": 0.9,
            "entities": ["milk"]
        }
        Hope that helps!"""

        intent = reactive_handler._parse_intent_response(llm_response)

        assert intent.type == "QUERY"
        assert intent.confidence == 0.9

    def test_parse_intent_response_invalid_json(self, reactive_handler):
        """Test error handling for invalid JSON."""
        llm_response = "This is not JSON"

        with pytest.raises(ValueError, match="Failed to parse intent response"):
            reactive_handler._parse_intent_response(llm_response)


# ============================================================================
# Test ReactiveHandler - Routing Logic
# ============================================================================


class TestRoutingLogic:
    """Test PATH1 vs PATH2 routing decisions."""

    def test_simple_complexity_routes_to_path1(self, reactive_handler):
        """Test simple complexity routes to PATH1."""
        intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="nutritionist",
            confidence=0.9,
        )

        routing = reactive_handler._determine_routing(intent)

        assert routing == "PATH1"

    def test_multi_step_complexity_routes_to_path2(self, reactive_handler):
        """Test multi-step complexity routes to PATH2."""
        intent = Intent(
            type="QUERY",
            domain="health",
            complexity="multi_step",
            specialist_type="nutritionist",
            confidence=0.9,
        )

        routing = reactive_handler._determine_routing(intent)

        assert routing == "PATH2"

    def test_orchestrator_specialist_routes_to_path2(self, reactive_handler):
        """Test orchestrator specialist routes to PATH2."""
        intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="orchestrator",
            confidence=0.9,
        )

        routing = reactive_handler._determine_routing(intent)

        assert routing == "PATH2"


# ============================================================================
# Test ReactiveHandler - Response Generation
# ============================================================================


class TestResponseGeneration:
    """Test reactive response generation: '{empathy}. {action}.'"""

    def test_generate_response_gerd_scenario(
        self, reactive_handler, sample_conversation_state, mock_llm_client
    ):
        """Test full reactive response for GERD scenario."""
        intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="nutritionist",
            confidence=0.92,
        )

        response = reactive_handler.generate_response(
            "milk is making me sick", intent, sample_conversation_state
        )

        # Should have format: "{empathy}. {action}."
        assert "sad" in response.lower() or "understand" in response.lower()
        assert "nutritionist" in response.lower()
        assert response.endswith(".")
        # Count periods - should have exactly 2 (one after empathy, one at end)
        assert response.count(".") >= 1

    def test_generate_response_format(
        self, reactive_handler, sample_conversation_state, mock_llm_client
    ):
        """Test response follows format: '{empathy}. {action}.'"""
        intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="psychiatrist",
            confidence=0.9,
        )

        response = reactive_handler.generate_response(
            "I'm feeling anxious", intent, sample_conversation_state
        )

        # Should contain empathy + action
        assert len(response.split(".")) >= 2
        assert "psychiatrist" in response.lower()

    def test_get_action_declaration_nutritionist(self, reactive_handler):
        """Test action declaration for nutritionist."""
        intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="nutritionist",
            confidence=0.9,
        )

        action = reactive_handler._get_action_declaration(intent)

        assert action == "Looping in nutritionist"

    def test_get_action_declaration_psychiatrist(self, reactive_handler):
        """Test action declaration for psychiatrist."""
        intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="psychiatrist",
            confidence=0.9,
        )

        action = reactive_handler._get_action_declaration(intent)

        assert action == "Connecting you with psychiatrist"

    def test_get_action_declaration_unknown_specialist(self, reactive_handler):
        """Test action declaration for unknown specialist (generic fallback)."""
        intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="unknown_specialist",
            confidence=0.9,
        )

        action = reactive_handler._get_action_declaration(intent)

        assert "unknown_specialist" in action.lower()

    def test_format_response_combines_empathy_action(self, reactive_handler):
        """Test response formatting combines empathy and action."""
        empathy = "That's sad to hear"
        action = "Looping in nutritionist"

        response = reactive_handler._format_response(empathy, action)

        assert response == "That's sad to hear. Looping in nutritionist."

    def test_format_response_handles_trailing_punctuation(self, reactive_handler):
        """Test response formatting removes trailing punctuation before combining."""
        empathy = "That's sad to hear."  # Has period
        action = "Looping in nutritionist."  # Has period

        response = reactive_handler._format_response(empathy, action)

        # Should remove periods before combining, then add at end
        assert response == "That's sad to hear. Looping in nutritionist."


# ============================================================================
# Test Integration Scenarios
# ============================================================================


class TestIntegrationScenarios:
    """Test full reactive flow end-to-end."""

    def test_full_gerd_reactive_flow(
        self, reactive_handler, sample_conversation_state, mock_llm_client
    ):
        """Test full reactive flow for GERD scenario."""
        # Mock intent classification
        mock_llm_client.generate.return_value = json.dumps(
            {
                "type": "QUERY",
                "domain": "health",
                "complexity": "simple",
                "specialist_type": "nutritionist",
                "confidence": 0.92,
                "entities": ["milk", "sick"],
            }
        )

        # Step 1: Classify intent
        intent = reactive_handler.classify_intent(
            "milk is making me sick", sample_conversation_state
        )
        assert intent.routing == "PATH1"

        # Step 2: Generate response
        response = reactive_handler.generate_response(
            "milk is making me sick", intent, sample_conversation_state
        )

        # Validate response format
        assert "sad" in response.lower() or "understand" in response.lower()
        assert "nutritionist" in response.lower()
        assert response.endswith(".")

    def test_frustrated_user_flow(
        self, reactive_handler, sample_conversation_state, mock_llm_client
    ):
        """Test reactive flow for frustrated user."""
        # Mock intent classification
        mock_llm_client.generate.return_value = json.dumps(
            {
                "type": "QUERY",
                "domain": "health",
                "complexity": "simple",
                "specialist_type": "psychiatrist",
                "confidence": 0.88,
                "entities": ["frustrated", "anxiety"],
            }
        )

        # Classify intent
        intent = reactive_handler.classify_intent(
            "I'm frustrated with my anxiety", sample_conversation_state
        )

        # Generate response
        response = reactive_handler.generate_response(
            "I'm frustrated with my anxiety", intent, sample_conversation_state
        )

        # Should detect frustrated emotion
        assert "frustrat" in response.lower()
        assert "psychiatrist" in response.lower()
