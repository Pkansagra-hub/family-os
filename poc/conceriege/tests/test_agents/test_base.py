"""
Tests for BaseAgent - Abstract Base Class for Specialist Agents

Tests cover:
- BaseAgent cannot be instantiated directly (abstract class)
- Task ID generation is unique
- Progress event emission works
- Progress callbacks work with async/sync
- get_capabilities() returns list
- Milestone structure validation
- Concrete subclass implementation
"""

import asyncio
from unittest.mock import Mock

import pytest
from backend.agents.base import BaseAgent, generate_ulid
from backend.models.analysis_result import AnalysisResult, Insight
from backend.models.conversation_state import ConversationState, Scoreboard
from backend.models.progress_event import ProgressEvent
from backend.services.k0_query_service import K0QueryService
from backend.services.metrics_collector import MetricsCollector

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_k0_service():
    """Mock K0 query service."""
    return Mock(spec=K0QueryService)


@pytest.fixture
def mock_metrics_collector():
    """Mock metrics collector."""
    return Mock(spec=MetricsCollector)


@pytest.fixture
def sample_conversation_state():
    """Create sample conversation state."""
    return ConversationState(
        user_id="user_123", conversation_id="conv_456", scoreboard=Scoreboard()
    )


# ============================================================================
# Concrete BaseAgent Implementation for Testing
# ============================================================================


class TestAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""

    async def analyze(self, query: str, user_id: str, context: ConversationState) -> AnalysisResult:
        """Test implementation of analyze method."""
        task_id = self._create_task_id()

        # Emit progress events
        await self.emit_progress(task_id, 1, 20, "Starting test analysis...")
        await asyncio.sleep(0.01)  # Simulate work

        await self.emit_progress(task_id, 2, 40, "Processing test data...")
        await asyncio.sleep(0.01)

        await self.emit_progress(task_id, 3, 60, "Finding test patterns...")
        await asyncio.sleep(0.01)

        await self.emit_progress(task_id, 4, 80, "Generating test insights...")
        await asyncio.sleep(0.01)

        await self.emit_progress(task_id, 5, 100, "Complete")

        # Return test result
        return AnalysisResult(
            specialist_type="test_agent",
            query=query,
            insights=[
                Insight(
                    summary="Test insight",
                    evidence=["Test evidence 1", "Test evidence 2"],
                    severity="strong",
                    confidence=0.9,
                )
            ],
            confidence=0.9,
            duration_ms=50,
        )

    def get_progress_milestones(self) -> list:
        """Test implementation of get_progress_milestones."""
        return [
            {"milestone": 1, "percent": 20, "message": "📊 Starting test..."},
            {"milestone": 2, "percent": 40, "message": "🔍 Processing test..."},
            {"milestone": 3, "percent": 60, "message": "🧠 Finding test patterns..."},
            {"milestone": 4, "percent": 80, "message": "💡 Generating test insights..."},
            {"milestone": 5, "percent": 100, "message": "✅ Test complete"},
        ]


@pytest.fixture
def test_agent(mock_k0_service, mock_metrics_collector):
    """Create TestAgent instance."""
    return TestAgent(
        agent_id="test_001",
        agent_type="test_agent",
        k0_query_service=mock_k0_service,
        metrics_collector=mock_metrics_collector,
    )


# ============================================================================
# Test BaseAgent Abstract Class
# ============================================================================


class TestBaseAgentAbstract:
    """Test that BaseAgent is abstract and cannot be instantiated."""

    def test_cannot_instantiate_base_agent_directly(self, mock_k0_service, mock_metrics_collector):
        """Test that BaseAgent cannot be instantiated (abstract class)."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseAgent(
                agent_id="base_001",
                agent_type="base",
                k0_query_service=mock_k0_service,
                metrics_collector=mock_metrics_collector,
            )

    def test_subclass_must_implement_analyze(self, mock_k0_service, mock_metrics_collector):
        """Test that subclass must implement analyze() method."""

        # Create incomplete subclass (missing analyze)
        class IncompleteAgent(BaseAgent):
            def get_progress_milestones(self):
                return []

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteAgent(
                agent_id="incomplete_001",
                agent_type="incomplete",
                k0_query_service=mock_k0_service,
                metrics_collector=mock_metrics_collector,
            )

    def test_subclass_must_implement_get_progress_milestones(
        self, mock_k0_service, mock_metrics_collector
    ):
        """Test that subclass must implement get_progress_milestones() method."""

        # Create incomplete subclass (missing get_progress_milestones)
        class IncompleteAgent(BaseAgent):
            async def analyze(self, query, user_id, context):
                return AnalysisResult(
                    specialist_type="incomplete", query=query, confidence=0.5, duration_ms=100
                )

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteAgent(
                agent_id="incomplete_001",
                agent_type="incomplete",
                k0_query_service=mock_k0_service,
                metrics_collector=mock_metrics_collector,
            )


# ============================================================================
# Test BaseAgent Initialization
# ============================================================================


class TestBaseAgentInit:
    """Test BaseAgent initialization."""

    def test_init_sets_attributes(self, test_agent, mock_k0_service, mock_metrics_collector):
        """Test that initialization sets all attributes correctly."""
        assert test_agent.agent_id == "test_001"
        assert test_agent.agent_type == "test_agent"
        assert test_agent.k0_query_service == mock_k0_service
        assert test_agent.metrics_collector == mock_metrics_collector
        assert test_agent._progress_callbacks == []

    def test_different_agents_have_different_ids(self, mock_k0_service, mock_metrics_collector):
        """Test that different agents have different IDs."""
        agent1 = TestAgent("agent_001", "test", mock_k0_service, mock_metrics_collector)
        agent2 = TestAgent("agent_002", "test", mock_k0_service, mock_metrics_collector)

        assert agent1.agent_id != agent2.agent_id


# ============================================================================
# Test Task ID Generation
# ============================================================================


class TestTaskIDGeneration:
    """Test task ID generation."""

    def test_create_task_id_returns_string(self, test_agent):
        """Test that _create_task_id() returns a string."""
        task_id = test_agent._create_task_id()
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    def test_task_ids_are_unique(self, test_agent):
        """Test that task IDs are unique."""
        task_ids = [test_agent._create_task_id() for _ in range(100)]

        # All IDs should be unique
        assert len(set(task_ids)) == 100

    def test_task_id_format(self, test_agent):
        """Test that task ID has expected format (timestamp_random)."""
        task_id = test_agent._create_task_id()

        # Should contain underscore separator
        assert "_" in task_id

        # Split into parts
        parts = task_id.split("_")
        assert len(parts) == 2

        # First part should be numeric timestamp
        timestamp_part = parts[0]
        assert timestamp_part.isdigit()

        # Second part should be random alphanumeric
        random_part = parts[1]
        assert len(random_part) == 10
        assert random_part.isalnum()

    def test_generate_ulid_function(self):
        """Test standalone generate_ulid() function."""
        ulid1 = generate_ulid()
        ulid2 = generate_ulid()

        # Should be unique
        assert ulid1 != ulid2

        # Should have correct format
        assert "_" in ulid1
        assert len(ulid1.split("_")) == 2


# ============================================================================
# Test Progress Event Emission
# ============================================================================


class TestProgressEventEmission:
    """Test progress event emission."""

    @pytest.mark.asyncio
    async def test_emit_progress_creates_event(self, test_agent):
        """Test that emit_progress creates ProgressEvent."""
        events = []

        def callback(event):
            events.append(event)

        test_agent.register_progress_callback(callback)

        await test_agent.emit_progress("task_123", 1, 20, "Starting analysis...")

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, ProgressEvent)
        assert event.task_id == "task_123"
        assert event.milestone == 1
        assert event.percent == 20
        assert event.message == "Starting analysis..."

    @pytest.mark.asyncio
    async def test_emit_progress_calls_multiple_callbacks(self, test_agent):
        """Test that emit_progress calls all registered callbacks."""
        events1 = []
        events2 = []

        test_agent.register_progress_callback(lambda e: events1.append(e))
        test_agent.register_progress_callback(lambda e: events2.append(e))

        await test_agent.emit_progress("task_123", 1, 20, "Test")

        assert len(events1) == 1
        assert len(events2) == 1

    @pytest.mark.asyncio
    async def test_emit_progress_supports_async_callbacks(self, test_agent):
        """Test that emit_progress supports async callbacks."""
        events = []

        async def async_callback(event):
            await asyncio.sleep(0.001)  # Simulate async work
            events.append(event)

        test_agent.register_progress_callback(async_callback)

        await test_agent.emit_progress("task_123", 1, 20, "Test")

        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_emit_progress_emits_all_milestones(self, test_agent):
        """Test that all 5 milestones are emitted during analysis."""
        events = []
        test_agent.register_progress_callback(lambda e: events.append(e))

        # Run full analysis (ignore result, just check events)
        await test_agent.analyze(
            "test query",
            "user_123",
            ConversationState("user_123", "conv_456", scoreboard=Scoreboard()),
        )

        # Should have 5 progress events
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


# ============================================================================
# Test get_capabilities()
# ============================================================================


class TestGetCapabilities:
    """Test get_capabilities() method."""

    def test_get_capabilities_returns_list(self, test_agent):
        """Test that get_capabilities returns a list."""
        capabilities = test_agent.get_capabilities()
        assert isinstance(capabilities, list)

    def test_get_capabilities_has_common_capabilities(self, test_agent):
        """Test that get_capabilities includes common capabilities."""
        capabilities = test_agent.get_capabilities()

        assert "analyze" in capabilities
        assert "progress_tracking" in capabilities
        assert "async_execution" in capabilities

    def test_subclass_can_override_capabilities(self, mock_k0_service, mock_metrics_collector):
        """Test that subclass can override get_capabilities."""

        class CustomAgent(TestAgent):
            def get_capabilities(self):
                base_caps = super().get_capabilities()
                return base_caps + ["custom_capability"]

        agent = CustomAgent("custom_001", "custom", mock_k0_service, mock_metrics_collector)

        capabilities = agent.get_capabilities()
        assert "custom_capability" in capabilities


# ============================================================================
# Test get_progress_milestones()
# ============================================================================


class TestGetProgressMilestones:
    """Test get_progress_milestones() method."""

    def test_get_progress_milestones_returns_list(self, test_agent):
        """Test that get_progress_milestones returns a list."""
        milestones = test_agent.get_progress_milestones()
        assert isinstance(milestones, list)

    def test_get_progress_milestones_has_5_milestones(self, test_agent):
        """Test that get_progress_milestones returns 5 milestones."""
        milestones = test_agent.get_progress_milestones()
        assert len(milestones) == 5

    def test_milestone_structure(self, test_agent):
        """Test that each milestone has correct structure."""
        milestones = test_agent.get_progress_milestones()

        for i, milestone in enumerate(milestones):
            # Each milestone should be a dict
            assert isinstance(milestone, dict)

            # Required fields
            assert "milestone" in milestone
            assert "percent" in milestone
            assert "message" in milestone

            # Correct values
            assert milestone["milestone"] == i + 1
            assert milestone["percent"] in [20, 40, 60, 80, 100]
            assert isinstance(milestone["message"], str)
            assert len(milestone["message"]) > 0

    def test_milestone_progression(self, test_agent):
        """Test that milestones progress correctly."""
        milestones = test_agent.get_progress_milestones()

        expected_percents = [20, 40, 60, 80, 100]
        actual_percents = [m["percent"] for m in milestones]

        assert actual_percents == expected_percents


# ============================================================================
# Test Concrete Implementation
# ============================================================================


class TestConcreteImplementation:
    """Test concrete TestAgent implementation."""

    @pytest.mark.asyncio
    async def test_analyze_returns_analysis_result(self, test_agent, sample_conversation_state):
        """Test that analyze() returns AnalysisResult."""
        result = await test_agent.analyze("test query", "user_123", sample_conversation_state)

        assert isinstance(result, AnalysisResult)
        assert result.specialist_type == "test_agent"
        assert result.query == "test query"
        assert len(result.insights) > 0

    @pytest.mark.asyncio
    async def test_analyze_emits_progress_events(self, test_agent, sample_conversation_state):
        """Test that analyze() emits progress events."""
        events = []
        test_agent.register_progress_callback(lambda e: events.append(e))

        # Run analysis (ignore result, just check events)
        await test_agent.analyze("test query", "user_123", sample_conversation_state)

        # Should emit 5 events
        assert len(events) == 5

        # All events should have same task_id
        task_ids = [e.task_id for e in events]
        assert len(set(task_ids)) == 1

    @pytest.mark.asyncio
    async def test_analyze_completes_successfully(self, test_agent, sample_conversation_state):
        """Test that analyze() completes successfully."""
        result = await test_agent.analyze("test query", "user_123", sample_conversation_state)

        # Should have insights
        assert len(result.insights) > 0

        # Should have confidence
        assert result.confidence > 0

        # Should have duration
        assert result.duration_ms > 0
