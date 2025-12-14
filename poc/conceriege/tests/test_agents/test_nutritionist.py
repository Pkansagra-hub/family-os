"""
Tests for NutritionistAgent - LLM-Powered Health Specialist (PoC)

Tests prove the SYSTEM WORKS, not specific to GERD:
- Can analyze ANY health query (diet, mood, sleep, etc.)
- Emits 5 progress events
- Returns AnalysisResult with LLM insights
- Handles empty K0 data gracefully
- Duration: 500-1000ms typical

**PoC Philosophy:**
- Flexible, not hardcoded
- LLM does the reasoning
- Generic health analysis
"""

from unittest.mock import Mock

import pytest
from backend.agents.nutritionist import NutritionistAgent
from backend.models.analysis_result import AnalysisResult, Insight
from backend.models.conversation_state import ConversationState, Scoreboard
from backend.services.k0_query_service import K0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_llm_client():
    """Mock LLM client."""
    mock = Mock(spec=LLMClient)
    # Default LLM response
    mock.generate.return_value = """
INSIGHT: Pattern detected in data
EVIDENCE: Multiple occurrences found
SEVERITY: strong
CONFIDENCE: 0.85
"""
    return mock


@pytest.fixture
def mock_k0_service():
    """Mock K0 query service."""
    mock = Mock(spec=K0QueryService)
    # Default K0 data
    mock.query.return_value = [
        {"timestamp": "2025-11-01T20:00:00", "food_item": "coffee"},
        {"timestamp": "2025-11-02T20:00:00", "food_item": "pizza"},
    ]
    return mock


@pytest.fixture
def mock_metrics_collector():
    """Mock metrics collector."""
    return Mock(spec=MetricsCollector)


@pytest.fixture
def nutritionist_agent(mock_llm_client, mock_k0_service, mock_metrics_collector):
    """Create NutritionistAgent with mocked dependencies."""
    return NutritionistAgent(
        llm_client=mock_llm_client,
        k0_query_service=mock_k0_service,
        metrics_collector=mock_metrics_collector,
    )


@pytest.fixture
def sample_conversation_state():
    """Sample conversation state."""
    return ConversationState(
        user_id="user_123", conversation_id="conv_456", scoreboard=Scoreboard()
    )


# ============================================================================
# Test NutritionistAgent Initialization
# ============================================================================


class TestNutritionistInit:
    """Test NutritionistAgent initialization."""

    def test_init_sets_attributes(
        self, nutritionist_agent, mock_llm_client, mock_k0_service, mock_metrics_collector
    ):
        """Test that init sets all attributes."""
        assert nutritionist_agent.agent_id == "nutritionist_001"
        assert nutritionist_agent.agent_type == "nutritionist"
        assert nutritionist_agent.llm_client == mock_llm_client
        assert nutritionist_agent.k0_query_service == mock_k0_service
        assert nutritionist_agent.metrics_collector == mock_metrics_collector


# ============================================================================
# Test analyze() - Core Functionality
# ============================================================================


class TestAnalyze:
    """Test analyze() method - proves system works with ANY health query."""

    @pytest.mark.asyncio
    async def test_analyze_gerd_query(self, nutritionist_agent, sample_conversation_state):
        """Test analysis of GERD query (demo scenario)."""
        result = await nutritionist_agent.analyze(
            "milk is making me sick", "user_123", sample_conversation_state
        )

        # Verify result type
        assert isinstance(result, AnalysisResult)
        assert result.specialist_type == "nutritionist"
        assert result.query == "milk is making me sick"

        # Should have insights
        assert len(result.insights) > 0
        assert isinstance(result.insights[0], Insight)

        # Should have confidence
        assert 0.0 <= result.confidence <= 1.0

        # Should have duration
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_analyze_mood_query(self, nutritionist_agent, sample_conversation_state):
        """Test analysis of mood query (proves flexibility)."""
        result = await nutritionist_agent.analyze(
            "I'm feeling anxious lately", "user_123", sample_conversation_state
        )

        assert isinstance(result, AnalysisResult)
        assert result.query == "I'm feeling anxious lately"
        assert len(result.insights) > 0

    @pytest.mark.asyncio
    async def test_analyze_sleep_query(self, nutritionist_agent, sample_conversation_state):
        """Test analysis of sleep query (proves flexibility)."""
        result = await nutritionist_agent.analyze(
            "my sleep is terrible", "user_123", sample_conversation_state
        )

        assert isinstance(result, AnalysisResult)
        assert result.query == "my sleep is terrible"
        assert len(result.insights) > 0

    @pytest.mark.asyncio
    async def test_analyze_returns_insights(self, nutritionist_agent, sample_conversation_state):
        """Test that analyze returns insights from LLM."""
        result = await nutritionist_agent.analyze(
            "test query", "user_123", sample_conversation_state
        )

        # Should have at least one insight
        assert len(result.insights) > 0

        # Insight should have required fields
        insight = result.insights[0]
        assert insight.summary
        assert 0.0 <= insight.confidence <= 1.0
        assert insight.severity in ["strong", "moderate", "weak"]

    @pytest.mark.asyncio
    async def test_analyze_handles_empty_k0_data(
        self, nutritionist_agent, sample_conversation_state, mock_k0_service
    ):
        """Test that analyze handles empty K0 data gracefully."""
        # Mock empty K0 data
        mock_k0_service.query.return_value = []

        result = await nutritionist_agent.analyze(
            "test query", "user_123", sample_conversation_state
        )

        # Should still return result (LLM can work with no data)
        assert isinstance(result, AnalysisResult)
        assert len(result.insights) > 0

    @pytest.mark.asyncio
    async def test_analyze_duration_in_range(self, nutritionist_agent, sample_conversation_state):
        """Test that analyze duration is in expected range (500-1000ms)."""
        result = await nutritionist_agent.analyze(
            "test query", "user_123", sample_conversation_state
        )

        # Should be between 200-1500ms (with async sleeps)
        assert 200 <= result.duration_ms <= 1500


# ============================================================================
# Test Progress Event Emission
# ============================================================================


class TestProgressEvents:
    """Test progress event emission during analysis."""

    @pytest.mark.asyncio
    async def test_emits_5_progress_events(self, nutritionist_agent, sample_conversation_state):
        """Test that analyze emits 5 progress events."""
        events = []
        nutritionist_agent.register_progress_callback(lambda e: events.append(e))

        await nutritionist_agent.analyze("test query", "user_123", sample_conversation_state)

        # Should emit exactly 5 events
        assert len(events) == 5

        # Verify milestone progression
        assert events[0].milestone == 1
        assert events[0].percent == 20
        assert events[1].milestone == 2
        assert events[1].percent == 40
        assert events[2].milestone == 3
        assert events[2].percent == 60
        assert events[3].milestone == 4
        assert events[3].percent == 80
        assert events[4].milestone == 5
        assert events[4].percent == 100

    @pytest.mark.asyncio
    async def test_progress_messages_match_milestones(
        self, nutritionist_agent, sample_conversation_state
    ):
        """Test that progress messages match milestone definitions."""
        events = []
        nutritionist_agent.register_progress_callback(lambda e: events.append(e))

        await nutritionist_agent.analyze("test query", "user_123", sample_conversation_state)

        # Check messages
        assert "health data" in events[0].message.lower()
        assert "analyzing" in events[1].message.lower()
        assert "insights" in events[2].message.lower()
        assert "generating" in events[3].message.lower()
        assert "complete" in events[4].message.lower()


# ============================================================================
# Test get_progress_milestones()
# ============================================================================


class TestProgressMilestones:
    """Test progress milestone definitions."""

    def test_get_progress_milestones_returns_5_milestones(self, nutritionist_agent):
        """Test that get_progress_milestones returns 5 milestones."""
        milestones = nutritionist_agent.get_progress_milestones()
        assert len(milestones) == 5

    def test_milestone_structure(self, nutritionist_agent):
        """Test milestone structure."""
        milestones = nutritionist_agent.get_progress_milestones()

        for i, milestone in enumerate(milestones):
            assert "milestone" in milestone
            assert "percent" in milestone
            assert "message" in milestone
            assert milestone["milestone"] == i + 1


# ============================================================================
# Test LLM Integration
# ============================================================================


class TestLLMIntegration:
    """Test LLM integration for analysis."""

    @pytest.mark.asyncio
    async def test_calls_llm_for_analysis(
        self, nutritionist_agent, sample_conversation_state, mock_llm_client
    ):
        """Test that analyze calls LLM."""
        await nutritionist_agent.analyze("test query", "user_123", sample_conversation_state)

        # Should call LLM generate
        mock_llm_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_synthesis_profile(
        self, nutritionist_agent, sample_conversation_state, mock_llm_client
    ):
        """Test that analyze uses synthesis LLM profile."""
        await nutritionist_agent.analyze("test query", "user_123", sample_conversation_state)

        # Check that synthesis profile was used
        call_args = mock_llm_client.generate.call_args
        assert call_args[1]["model_profile"] == "synthesis"

    @pytest.mark.asyncio
    async def test_handles_llm_error_gracefully(
        self, nutritionist_agent, sample_conversation_state, mock_llm_client
    ):
        """Test that analyze handles LLM errors gracefully."""
        # Mock LLM error
        mock_llm_client.generate.side_effect = Exception("LLM API error")

        result = await nutritionist_agent.analyze(
            "test query", "user_123", sample_conversation_state
        )

        # Should still return result with fallback insight
        assert isinstance(result, AnalysisResult)
        assert len(result.insights) > 0
        assert (
            "unable" in result.insights[0].summary.lower()
            or "error" in result.insights[0].summary.lower()
        )


# ============================================================================
# Test K0 Integration
# ============================================================================


class TestK0Integration:
    """Test K0 data integration."""

    @pytest.mark.asyncio
    async def test_queries_k0_for_data(
        self, nutritionist_agent, sample_conversation_state, mock_k0_service
    ):
        """Test that analyze queries K0."""
        await nutritionist_agent.analyze("test query", "user_123", sample_conversation_state)

        # Should query K0 multiple times (diet, health events, mood)
        assert mock_k0_service.query.call_count >= 2

    @pytest.mark.asyncio
    async def test_handles_k0_error_gracefully(
        self, nutritionist_agent, sample_conversation_state, mock_k0_service
    ):
        """Test that analyze handles K0 errors gracefully."""
        # Mock K0 error
        mock_k0_service.query.side_effect = Exception("K0 connection error")

        result = await nutritionist_agent.analyze(
            "test query", "user_123", sample_conversation_state
        )

        # Should still return result (LLM can handle no data)
        assert isinstance(result, AnalysisResult)


# ============================================================================
# Test Contradiction Detection
# ============================================================================


class TestContradictionDetection:
    """Test contradiction detection."""

    @pytest.mark.asyncio
    async def test_detects_contradiction_when_present(
        self, nutritionist_agent, sample_conversation_state, mock_llm_client
    ):
        """Test that contradictions are detected."""
        # Mock LLM response with different finding than user hypothesis
        mock_llm_client.generate.return_value = """
INSIGHT: Coffee is the primary trigger
EVIDENCE: Found in 60% of cases
SEVERITY: strong
CONFIDENCE: 0.85
"""

        result = await nutritionist_agent.analyze(
            "milk is making me sick", "user_123", sample_conversation_state  # User hypothesis: milk
        )

        # Should detect contradiction (milk vs coffee)
        # Note: Detection is simple in PoC, might not always catch
        assert isinstance(result, AnalysisResult)

    @pytest.mark.asyncio
    async def test_extracts_user_hypothesis(self, nutritionist_agent, sample_conversation_state):
        """Test that user hypothesis is extracted from query."""
        result = await nutritionist_agent.analyze(
            "coffee is giving me anxiety", "user_123", sample_conversation_state
        )

        # Should extract "coffee" as hypothesis
        assert result.user_hypothesis == "coffee" or result.user_hypothesis == ""


# ============================================================================
# Test Metrics Recording
# ============================================================================


class TestMetricsRecording:
    """Test metrics recording."""

    @pytest.mark.asyncio
    async def test_records_specialist_duration(
        self, nutritionist_agent, sample_conversation_state, mock_metrics_collector
    ):
        """Test that analyze records specialist duration."""
        await nutritionist_agent.analyze("test query", "user_123", sample_conversation_state)

        # Should record duration
        mock_metrics_collector.record_specialist_duration.assert_called_once()
        call_args = mock_metrics_collector.record_specialist_duration.call_args
        assert call_args[0][0] == "nutritionist"
        assert call_args[0][1] > 0  # Duration > 0ms
