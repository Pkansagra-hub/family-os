"""
Integration Tests for Issue 6.5.2.2: Dynamic Specialist Agent Spawning

Tests dynamic agent spawning, prompt generation, tool resolution, and agent lifecycle.

Coverage:
- Prompt generation via Groq with caching
- Tool resolution by agent type
- Agent spawning infrastructure
- Agent lifecycle state machine (WARMING → ACTIVE → IDLE → TERMINATED)
- Agent reuse within TTL (5 minutes)
- Agent respawn after TTL expiry
- Concurrent agent spawning for multiple types

References:
- docs/plans/issue_6_5_2_2_dynamic_specialist_spawning_plan.md
- ADR-0006a: Contract Net Protocol
"""

import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from l2_orchestration.orchestrator.orchestrator import (
    Orchestrator,
    TaskAnnouncement,
    TaskType,
)
from l4_runtime.session_state.session_state import AgentRecord, AgentState, SessionState
from l5_infrastructure.registries.prompt_registry import PromptRegistry, PromptTemplate
from l5_infrastructure.registries.tool_registry import ToolRegistry
from models.envelope import AgentSpawnRequest


@pytest.fixture
def tool_registry():
    """Create a ToolRegistry instance."""
    return ToolRegistry()


@pytest.fixture
def prompt_registry():
    """Create a PromptRegistry instance."""
    return PromptRegistry()


@pytest.fixture
def session_state():
    """Create a SessionState instance."""
    return SessionState(
        session_id=f"session_{uuid.uuid4().hex[:12]}",
        user_id="test_user",
        cognitive_trace_id=f"trace_{uuid.uuid4().hex[:12]}",
    )


@pytest.fixture
async def orchestrator(tool_registry, prompt_registry, session_state):
    """Create an Orchestrator instance with mocked Groq client."""
    # Create mock dependencies
    agent_registry = {}
    session_state_mock = MagicMock()
    session_state_mock.control = session_state.control
    agent_factory = MagicMock()
    mailbox_manager = MagicMock()

    # Initialize Orchestrator
    orch = Orchestrator(
        agent_registry=agent_registry,
        tool_registry=tool_registry,
        session_state=session_state_mock,
        agent_factory=agent_factory,
        mailbox_manager=mailbox_manager,
    )

    # Override tool_registry and prompt_registry
    orch.tool_registry = tool_registry
    orch.prompt_registry = prompt_registry

    # Mock Groq client
    groq_client_mock = MagicMock()

    async def mock_groq_complete(
        messages, agent_type="specialist", temperature=None, max_tokens=None
    ):
        """Mock Groq complete response with valid JSON."""
        response_text = json.dumps(
            {
                "system_prompt": f"You are a {agent_type} specialist agent. Execute tasks accurately.",
                "constraints": [
                    "Follow user instructions",
                    "Report errors clearly",
                    "Ask for clarification if ambiguous",
                ],
                "temperature": temperature or 0.7,
                "max_tokens": max_tokens or 1000,
            }
        )
        return {
            "content": response_text,
            "tokens_used": 150,
            "finish_reason": "stop",
        }

    # Wrap as AsyncMock so we can track call_count
    groq_client_mock.complete = AsyncMock(side_effect=mock_groq_complete)
    orch.groq_client = groq_client_mock

    yield orch


class TestDynamicPromptGeneration:
    """Test Suite: Dynamic Prompt Generation (Phase 1)"""

    async def test_generate_prompt_from_groq(self, orchestrator):
        """Verify prompt generation from Groq with proper format."""
        agent_type = "TicketBookingAgent"
        task_context = {
            "description": "Book a restaurant table for 2 people",
            "domain": "hospitality",
            "tools": ["web_search", "calendar_add"],
        }

        # Act
        prompt = await orchestrator._generate_agent_prompt(agent_type, task_context)

        # Assert
        assert prompt.agent_type == agent_type
        assert "specialist agent" in prompt.system_prompt.lower()
        assert len(prompt.constraints) >= 2
        # Orchestrator uses deterministic temperature (0.3) for consistent prompt generation
        assert prompt.temperature == 0.3
        assert prompt.max_tokens == 600

    async def test_prompt_generation_caching(self, orchestrator):
        """Verify generated prompts are cached and reused."""
        agent_type = "FlightSearchAgent"
        task_context = {"description": "Search for flights", "domain": "travel"}

        # Act: Generate prompt first time
        prompt1 = await orchestrator._generate_agent_prompt(agent_type, task_context)

        # Track Groq calls
        groq_call_count_before = orchestrator.groq_client.complete.call_count

        # Generate same prompt second time
        prompt2 = await orchestrator._generate_agent_prompt(agent_type, task_context)

        # Assert: Prompt cached, no new Groq call
        assert prompt1.system_prompt == prompt2.system_prompt
        assert orchestrator.groq_client.complete.call_count == groq_call_count_before

    async def test_prompt_generation_fallback_on_error(self, orchestrator):
        """Verify fallback prompt on Groq error."""
        agent_type = "HealthcareAgent"

        # Mock Groq to fail
        orchestrator.groq_client.complete = AsyncMock(side_effect=Exception("Groq API error"))

        # Act
        prompt = await orchestrator._generate_agent_prompt(
            agent_type, {"description": "Check symptoms"}
        )

        # Assert: Fallback prompt
        assert prompt.agent_type == agent_type
        assert "specialized agent" in prompt.system_prompt
        assert len(prompt.constraints) >= 1


class TestToolResolution:
    """Test Suite: Tool Resolution by Agent Type (Phase 2)"""

    def test_tools_for_ticket_booking_agent(self, tool_registry):
        """Verify tools available for TicketBookingAgent."""
        tools = tool_registry.get_tools_for_agent_type("TicketBookingAgent")

        assert len(tools) >= 3
        tool_names = [t.name for t in tools]
        assert "Web Search" in tool_names

    def test_tools_for_flight_search_agent(self, tool_registry):
        """Verify tools available for FlightSearchAgent."""
        tools = tool_registry.get_tools_for_agent_type("FlightSearchAgent")

        assert len(tools) >= 2
        tool_names = [t.name for t in tools]
        assert "Web Search" in tool_names

    def test_tools_for_healthcare_agent(self, tool_registry):
        """Verify tools available for HealthcareAgent."""
        tools = tool_registry.get_tools_for_agent_type("HealthcareAgent")

        assert len(tools) >= 1
        tool_names = [t.name for t in tools]
        assert "Web Search" in tool_names

    def test_fallback_tools_for_unknown_agent(self, tool_registry):
        """Verify fallback to generic tools for unknown agent type."""
        tools = tool_registry.get_tools_for_agent_type("UnknownAgent")

        # Should fallback to web_search
        assert len(tools) >= 1
        tool_names = [t.name for t in tools]
        assert "Web Search" in tool_names

    def test_tools_serializable(self, tool_registry):
        """Verify tools can be serialized to dict."""
        tools = tool_registry.get_tools_for_agent_type("TicketBookingAgent")

        for tool in tools:
            tool_dict = tool.to_dict()
            assert tool_dict["name"]
            assert tool_dict["description"]
            assert tool_dict["category"]


class TestAgentSpawning:
    """Test Suite: Agent Spawning Infrastructure (Phase 3)"""

    async def test_spawn_ticket_booking_agent(self, orchestrator):
        """Verify TicketBookingAgent spawning with prompt generation."""
        agent_type = "TicketBookingAgent"
        prompt = PromptTemplate(
            agent_type=agent_type,
            system_prompt="You are a ticket booking specialist.",
            tool_prompt_template="Available tools: web_search, calendar_add",
            context_prompt_template="User context: {{user_context}}",
            constraints=["Verify availability", "Collect information"],
            examples=[],
            temperature=0.7,
            max_tokens=1000,
        )
        tools = orchestrator.tool_registry.get_tools_for_agent_type(agent_type)

        # Act
        agent_id = await orchestrator._spawn_agent(
            agent_type=agent_type,
            prompt=prompt,
            tools=tools,
            task_context={"description": "Book a table"},
            session_id="session_123",
            trace_id="trace_456",
        )

        # Assert
        assert agent_id.startswith("TicketBookingAgent_")
        assert len(agent_id) > len("TicketBookingAgent_")

    async def test_infer_agent_type_from_task(self, orchestrator):
        """Verify agent type inference from task description."""
        task_announcement = TaskAnnouncement(
            task_id="task_001",
            task_type=TaskType.QUERY,
            required_tools=[],
            budget={"time_ms": 5000, "cost_credits": 10},
            deadline_ms=5000,
            user_context={},
            trace_id="trace_123",
            user_input="I need to book a restaurant table",
        )

        # Create mock task assignment
        task_assignment = MagicMock()
        task_assignment.task_announcement = task_announcement

        # Act
        agent_type = orchestrator._infer_agent_type(task_assignment)

        # Assert
        assert agent_type == "TicketBookingAgent"

    async def test_infer_agent_type_flight_search(self, orchestrator):
        """Verify agent type inference for flight search."""
        task_announcement = TaskAnnouncement(
            task_id="task_002",
            task_type=TaskType.QUERY,
            required_tools=[],
            budget={"time_ms": 5000, "cost_credits": 10},
            deadline_ms=5000,
            user_context={},
            trace_id="trace_124",
            user_input="Search for flights to New York",
        )

        task_assignment = MagicMock()
        task_assignment.task_announcement = task_announcement

        # Act
        agent_type = orchestrator._infer_agent_type(task_assignment)

        # Assert
        assert agent_type == "FlightSearchAgent"

    async def test_spawn_request_envelope(self, orchestrator):
        """Verify AgentSpawnRequest envelope creation."""
        agent_id = f"test_{uuid.uuid4().hex[:8]}"
        agent_type = "TicketBookingAgent"
        tools = orchestrator.tool_registry.get_tools_for_agent_type(agent_type)

        # Create envelope
        spawn_request = AgentSpawnRequest(
            agent_id=agent_id,
            agent_type=agent_type,
            system_prompt="Test system prompt",
            available_tools=[t.to_dict() for t in tools],
            task_context={"description": "Test task"},
            session_id="session_123",
            trace_id="trace_456",
            timestamp_ms=int(time.time() * 1000),
        )

        # Assert
        assert spawn_request.agent_id == agent_id
        assert spawn_request.agent_type == agent_type
        assert len(spawn_request.available_tools) >= 1


class TestAgentLifecycle:
    """Test Suite: Agent Lifecycle State Machine (Phase 4)"""

    def test_agent_record_creation(self):
        """Verify AgentRecord creation with initial state."""
        now_ms = int(time.time() * 1000)
        agent_record = AgentRecord(
            agent_id="agent_001",
            agent_type="TicketBookingAgent",
            state=AgentState.WARMING,
            spawned_at_ms=now_ms,
            last_active_ms=now_ms,
            idle_timeout_ms=300000,  # 5 minutes
        )

        assert agent_record.agent_id == "agent_001"
        assert agent_record.state == AgentState.WARMING
        assert agent_record.assigned_tasks == 0
        assert agent_record.completed_tasks == 0

    def test_agent_is_reusable_within_ttl(self):
        """Verify agent is reusable within TTL."""
        now_ms = int(time.time() * 1000)
        agent_record = AgentRecord(
            agent_id="agent_001",
            agent_type="TicketBookingAgent",
            state=AgentState.IDLE,
            spawned_at_ms=now_ms - 60000,  # 1 minute ago
            last_active_ms=now_ms - 30000,  # 30 seconds ago
            idle_timeout_ms=300000,  # 5 minutes
        )

        # Act
        is_reusable = agent_record.is_reusable(now_ms)

        # Assert
        assert is_reusable is True

    def test_agent_not_reusable_after_ttl_expiry(self):
        """Verify agent is not reusable after TTL expiry."""
        now_ms = int(time.time() * 1000)
        agent_record = AgentRecord(
            agent_id="agent_001",
            agent_type="TicketBookingAgent",
            state=AgentState.IDLE,
            spawned_at_ms=now_ms - 600000,  # 10 minutes ago
            last_active_ms=now_ms - 400000,  # 6.7 minutes ago (expired)
            idle_timeout_ms=300000,  # 5 minutes
        )

        # Act
        is_reusable = agent_record.is_reusable(now_ms)

        # Assert
        assert is_reusable is False

    def test_session_state_add_agent_to_roster(self, session_state):
        """Verify adding agent to session state roster."""
        now_ms = int(time.time() * 1000)
        agent_record = AgentRecord(
            agent_id="agent_001",
            agent_type="TicketBookingAgent",
            state=AgentState.WARMING,
            spawned_at_ms=now_ms,
            last_active_ms=now_ms,
        )

        # Act
        session_state.add_agent_to_roster(agent_record)

        # Assert
        retrieved = session_state.get_agent_from_roster("agent_001")
        assert retrieved is not None
        assert retrieved.agent_id == "agent_001"
        assert retrieved.agent_type == "TicketBookingAgent"

    def test_session_state_update_agent_state(self, session_state):
        """Verify updating agent state in roster."""
        now_ms = int(time.time() * 1000)
        agent_record = AgentRecord(
            agent_id="agent_001",
            agent_type="TicketBookingAgent",
            state=AgentState.WARMING,
            spawned_at_ms=now_ms,
            last_active_ms=now_ms,
        )
        session_state.add_agent_to_roster(agent_record)

        # Act: Transition to ACTIVE
        success = session_state.update_agent_state("agent_001", AgentState.ACTIVE, now_ms)

        # Assert
        assert success is True
        retrieved = session_state.get_agent_from_roster("agent_001")
        assert retrieved.state == AgentState.ACTIVE

    def test_session_state_cleanup_expired_agents(self, session_state):
        """Verify cleanup of expired agents from roster."""
        now_ms = int(time.time() * 1000)

        # Add active agent (should not be cleaned up)
        active_agent = AgentRecord(
            agent_id="agent_active",
            agent_type="TicketBookingAgent",
            state=AgentState.ACTIVE,
            spawned_at_ms=now_ms - 60000,
            last_active_ms=now_ms - 30000,
        )
        session_state.add_agent_to_roster(active_agent)

        # Add expired idle agent (should be cleaned up)
        expired_agent = AgentRecord(
            agent_id="agent_expired",
            agent_type="TicketBookingAgent",
            state=AgentState.IDLE,
            spawned_at_ms=now_ms - 600000,
            last_active_ms=now_ms - 400000,
            idle_timeout_ms=300000,
        )
        session_state.add_agent_to_roster(expired_agent)

        # Act
        removed_agents = session_state.cleanup_expired_agents(now_ms)

        # Assert
        assert "agent_expired" in removed_agents
        assert "agent_active" not in removed_agents
        assert session_state.get_agent_from_roster("agent_active") is not None
        assert session_state.get_agent_from_roster("agent_expired") is None


class TestConcurrentAgentSpawning:
    """Test Suite: Concurrent Agent Spawning"""

    async def test_spawn_multiple_agent_types_concurrently(self, orchestrator):
        """Verify multiple agents can be spawned concurrently."""
        agent_types = [
            "TicketBookingAgent",
            "FlightSearchAgent",
            "HealthcareAgent",
        ]

        # Act: Spawn agents concurrently
        spawn_tasks = []
        for agent_type in agent_types:
            prompt = PromptTemplate(
                agent_type=agent_type,
                system_prompt=f"You are a {agent_type}.",
                tool_prompt_template="Available tools",
                context_prompt_template="Context: {{user_context}}",
                constraints=[],
                examples=[],
                temperature=0.7,
                max_tokens=1000,
            )
            tools = orchestrator.tool_registry.get_tools_for_agent_type(agent_type)
            task = orchestrator._spawn_agent(
                agent_type=agent_type,
                prompt=prompt,
                tools=tools,
                task_context={"description": "Test task"},
                session_id="session_123",
                trace_id="trace_456",
            )
            spawn_tasks.append(task)

        agent_ids = await asyncio.gather(*spawn_tasks)

        # Assert
        assert len(agent_ids) == 3
        assert all(agent_id for agent_id in agent_ids)
        assert agent_ids[0].startswith("TicketBookingAgent_")
        assert agent_ids[1].startswith("FlightSearchAgent_")
        assert agent_ids[2].startswith("HealthcareAgent_")


class TestAgentReuse:
    """Test Suite: Agent Reuse and TTL Logic"""

    def test_agent_reuse_within_ttl_window(self, session_state):
        """Verify agents are reused if within TTL window."""
        now_ms = int(time.time() * 1000)

        # Create and add agent in IDLE state
        agent = AgentRecord(
            agent_id="agent_reuse_001",
            agent_type="TicketBookingAgent",
            state=AgentState.IDLE,
            spawned_at_ms=now_ms - 120000,  # 2 minutes ago
            last_active_ms=now_ms - 30000,  # 30 seconds ago (within 5 min TTL)
            idle_timeout_ms=300000,
        )
        session_state.add_agent_to_roster(agent)

        # Check reusability
        retrieved = session_state.get_agent_from_roster("agent_reuse_001")
        is_reusable = retrieved.is_reusable(now_ms)

        # Assert
        assert is_reusable is True

    def test_agent_reuse_after_ttl_expiry(self, session_state):
        """Verify agents are not reused after TTL expiry."""
        now_ms = int(time.time() * 1000)

        # Create and add agent in IDLE state (expired)
        agent = AgentRecord(
            agent_id="agent_expired_001",
            agent_type="TicketBookingAgent",
            state=AgentState.IDLE,
            spawned_at_ms=now_ms - 1200000,  # 20 minutes ago
            last_active_ms=now_ms - 600000,  # 10 minutes ago (expired)
            idle_timeout_ms=300000,  # 5 minutes
        )
        session_state.add_agent_to_roster(agent)

        # Check reusability
        retrieved = session_state.get_agent_from_roster("agent_expired_001")
        is_reusable = retrieved.is_reusable(now_ms)

        # Assert
        assert is_reusable is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
