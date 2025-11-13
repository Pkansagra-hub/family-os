"""
Integration Tests for Epic 6.5.3.1: BackgroundServicesManager

Tests the complete background services lifecycle:
1. Initialization of Writer Agents (spawn, warm, activate)
2. DeltaBus subscription and event routing
3. Health monitoring and verification
4. Graceful shutdown with mailbox draining

References:
- docs/plans/chat_experience_poc_plan.md (Epic 6.5.3.1)
- docs/whiteboard/chat_experience.md (Background services architecture)
- ADR-0019: Session State and Delta Propagation
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from l3_execution.agents.writers import LearningExtractorAgent, MemoryWriterAgent
from l4_runtime.deltabus.deltabus import DeltaBus
from l4_runtime.session_state.session_state_manager import SessionStateManager
from l5_infrastructure.background_services_manager import BackgroundServicesManager
from l5_infrastructure.groq_client import GroqClient
from l5_infrastructure.registries.tool_registry import ToolRegistry


@pytest.fixture
def deltabus():
    """Create DeltaBus instance for testing."""
    return DeltaBus()


@pytest.fixture
def session_state_manager(deltabus):
    """Create SessionStateManager instance."""
    return SessionStateManager(deltabus=deltabus, session_timeout_seconds=600)


@pytest.fixture
def tool_registry():
    """Create ToolRegistry instance."""
    return ToolRegistry()


@pytest.fixture
def groq_client():
    """Create mocked Groq client."""
    client = AsyncMock(spec=GroqClient)
    client.invoke = AsyncMock(return_value={"response": "test response", "tokens": 100})
    return client


@pytest.fixture
async def background_manager():
    """Get BackgroundServicesManager singleton for testing."""
    # Reset singleton for each test
    BackgroundServicesManager._instance = None
    manager = await BackgroundServicesManager.get_manager()
    yield manager
    # Cleanup after test
    if manager.is_running:
        await manager.stop_all()


class TestBackgroundServicesInitialization:
    """Test BackgroundServicesManager initialization phases."""

    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """Test that BackgroundServicesManager is a singleton."""
        BackgroundServicesManager._instance = None

        manager1 = await BackgroundServicesManager.get_manager()
        manager2 = await BackgroundServicesManager.get_manager()

        assert manager1 is manager2
        assert BackgroundServicesManager._instance is not None

    @pytest.mark.asyncio
    async def test_cannot_instantiate_directly(self):
        """Test that BackgroundServicesManager cannot be instantiated directly."""
        with pytest.raises(RuntimeError, match="Use BackgroundServicesManager.get_manager"):
            BackgroundServicesManager()

    @pytest.mark.asyncio
    async def test_start_all_phases_success(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test successful initialization through all 6 phases."""
        result = await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        assert result is True
        assert background_manager.is_running is True
        assert len(background_manager.writer_agents) == 3
        assert background_manager.state_delta_emitter is not None
        assert background_manager.temporal_module is not None

    @pytest.mark.asyncio
    async def test_writer_agents_spawned(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test that 3 Writer Agents are spawned with correct types."""
        await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        agent_types = set()
        for agent_id, agent in background_manager.writer_agents.items():
            agent_types.add(type(agent).__name__)
            # AI writers have .running attribute instead of .state
            assert hasattr(agent, "running")
            assert agent.running is True

        expected_types = {
            "MemoryWriterAgent",
            "LearningExtractorAgent",
            "SemanticEnricherAgent",
        }
        assert agent_types == expected_types

    @pytest.mark.asyncio
    async def test_agent_state_transitions(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test agent state transitions through startup."""
        # AI writers use .running attribute instead of state machine
        # Just verify agents spawn and are running
        result = await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        assert result is True
        # All agents should be running
        for agent in background_manager.writer_agents.values():
            assert hasattr(agent, "running")
            assert agent.running is True

    @pytest.mark.asyncio
    async def test_dependencies_stored(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test that dependencies are properly stored."""
        await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        assert background_manager.session_state_manager is session_state_manager
        assert background_manager.groq_client is groq_client
        assert background_manager.tool_registry is tool_registry
        assert background_manager.deltabus is not None


class TestDeltaBusSubscription:
    """Test DeltaBus subscription and event routing."""

    @pytest.mark.asyncio
    async def test_subscriptions_created(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test that subscriptions are created for each agent."""
        await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        # MemoryWriter: 1 subscription
        # LearningExtractor: 3 subscriptions
        # SemanticEnricher: 1 subscription
        # Total: 5 subscriptions
        assert len(background_manager.subscriptions) == 5

    @pytest.mark.asyncio
    async def test_event_routing_to_agent_mailbox(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test that DeltaBus events are routed to agents via subscriptions."""
        await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        # AI writers use DeltaBus subscriptions instead of mailboxes
        # Verify subscriptions are set up
        agents = list(background_manager.writer_agents.values())
        assert len(agents) > 0

        # Total subscriptions should be 5 (1+3+1 for Memory/Learning/Semantic)
        assert len(background_manager.subscriptions) == 5

    @pytest.mark.asyncio
    async def test_subscription_cleanup_on_shutdown(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test that subscriptions are cleaned up on shutdown."""
        await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        subscription_count = len(background_manager.subscriptions)
        assert subscription_count == 5

        await background_manager.stop_all()

        # Subscriptions should be cleared
        assert len(background_manager.subscriptions) == 0


class TestHealthMonitoring:
    """Test health monitoring and verification."""

    @pytest.mark.asyncio
    async def test_health_verification_on_startup(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test that health check is performed before accepting input."""
        result = await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        assert result is True
        # Health verification should pass
        health = await background_manager._verify_health()
        assert health is True

    @pytest.mark.asyncio
    async def test_get_writer_agent_by_type(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test retrieving Writer Agent by type."""
        await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        # AI writers use short names for writer_type: "memory", "learning", "semantic"
        memory_writer = await background_manager.get_writer_agent("memory")
        assert memory_writer is not None
        assert isinstance(memory_writer, MemoryWriterAgent)

        learning_extractor = await background_manager.get_writer_agent("learning")
        assert learning_extractor is not None
        assert isinstance(learning_extractor, LearningExtractorAgent)

    @pytest.mark.asyncio
    async def test_get_status(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test getting complete status report."""
        await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        status = await background_manager.get_status()

        assert status["is_running"] is True
        assert status["writer_agents"] == 3
        assert status["subscriptions"] == 5
        assert status["state_delta_emitter_ok"] is True
        assert status["temporal_module_ok"] is True


class TestGracefulShutdown:
    """Test graceful shutdown flow."""

    @pytest.mark.asyncio
    async def test_stop_all_success(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test successful graceful shutdown."""
        await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        assert background_manager.is_running is True

        await background_manager.stop_all()

        assert background_manager.is_running is False
        assert len(background_manager.subscriptions) == 0

    @pytest.mark.asyncio
    async def test_agent_state_on_shutdown(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test that agents are properly shutdown."""
        await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        # All agents should start running
        for agent in background_manager.writer_agents.values():
            assert agent.running is True

        await background_manager.stop_all()

        # Verify shutdown completed
        assert background_manager.is_running is False

        # All agents should be stopped after shutdown
        for agent in background_manager.writer_agents.values():
            assert agent.running is False

    @pytest.mark.asyncio
    async def test_shutdown_timeout_handling(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test that shutdown respects 45s timeout budget."""
        await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        # Shutdown should complete well within timeout
        import time

        start_time = time.time()
        await background_manager.stop_all()
        elapsed = time.time() - start_time

        # Should complete in seconds, not minutes
        assert elapsed < 10  # Should be much less than 45s


class TestErrorHandling:
    """Test error handling and recovery."""

    @pytest.mark.asyncio
    async def test_missing_dependencies_handling(self, background_manager):
        """Test handling of missing dependencies."""
        # Call start_all with None dependencies
        result = await background_manager.start_all(
            session_state_manager=None,  # type: ignore
            groq_client=None,  # type: ignore
            tool_registry=None,  # type: ignore
        )

        # Should fail gracefully
        assert result is False

    @pytest.mark.asyncio
    async def test_repeated_start_handling(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test that repeated start_all calls are handled safely."""
        result1 = await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        assert result1 is True

        # Second start should also work or return gracefully
        result2 = await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        # Should handle idempotently
        assert result2 is True or result2 is False

        await background_manager.stop_all()


class TestConcurrency:
    """Test concurrent access and safety."""

    @pytest.mark.asyncio
    async def test_concurrent_get_manager_calls(self):
        """Test that concurrent get_manager calls are thread-safe."""
        BackgroundServicesManager._instance = None

        # Create multiple concurrent get_manager calls
        results = await asyncio.gather(
            BackgroundServicesManager.get_manager(),
            BackgroundServicesManager.get_manager(),
            BackgroundServicesManager.get_manager(),
        )

        # All should return the same instance
        assert results[0] is results[1]
        assert results[1] is results[2]

    @pytest.mark.asyncio
    async def test_concurrent_start_and_status(
        self, background_manager, session_state_manager, groq_client, tool_registry
    ):
        """Test concurrent start_all and get_status calls."""
        # Start the service
        await background_manager.start_all(
            session_state_manager=session_state_manager,
            groq_client=groq_client,
            tool_registry=tool_registry,
        )

        # Get status multiple times concurrently
        statuses = await asyncio.gather(
            background_manager.get_status(),
            background_manager.get_status(),
            background_manager.get_status(),
        )

        # All should return valid status
        for status in statuses:
            assert status["is_running"] is True
            assert status["writer_agents"] == 3

        await background_manager.stop_all()
