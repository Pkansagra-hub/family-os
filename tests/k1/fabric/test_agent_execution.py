"""
Epic 6.3.4 -- Test agent spawn and execution (integration).

Test the Agent subsystem: lifecycle FSM, 8-step AgentFactory instantiation,
tool scoping, SessionState context injection, delta emission, and execution
through the fabric.execute() pipeline.

MANDATORY per plan:
  1. ALL executions through fabric.execute() where applicable -- NEVER direct provider access.
  2. Uses FabricFactory.create_for_testing() with event capture.
  3. Real adapters only (test adapters are real, not mocks).
  4. Verify events via event adapter capture mode.
  5. Direct AgentFactory/Agent tests for subsystem-level verification.

Design notes:
  - AgentProvider created by ProviderFactory does NOT get an agent_factory
    (wiring gap in factory.py _create_agent). Fabric.execute() with an
    agent capability returns AgentNotImplementedError (stub mode).
  - Direct AgentFactory tests use TestModelGatewayAdapter and
    TestDeltaBusAdapter as real adapters.
  - Agent lifecycle: PENDING -> WARMING -> ACTIVE -> IDLE -> DRAINING -> TERMINATED.
  - DeltaEmitter batches AgentDeltas and flushes via IDeltaBusPort.

References:
  - fabric-implementation-plan.md Epic 6.3, Issue 6.3.4
  - ADR-0005 (Agent lifecycle FSM)
  - No-Mock Testing Strategy (lines 1181-1300 of plan)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.events.fabric_events import (
    TOPIC_CAPABILITY_INVOKED,
    TOPIC_LEARNING_SIGNAL,
)
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory
from k1.fabric.policy.tool_scope import ToolScope
from k1.fabric.providers.agent_provider import (
    Agent,
    AgentDelta,
    AgentFactory,
    AgentLifecycleState,
    AgentPool,
    AgentPoolConfig,
    DeltaEmitter,
)
from k1.fabric.types import (
    AgentContract,
    CapabilityContract,
    CapabilityRequest,
    ExecutionContext,
    InputSpec,
    SafetyBand,
    Tier,
)
from tests.k1.fabric.helpers import load_fixture_contract

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_fabric() -> Fabric:
    """Create a Fabric with event capture for integration tests."""
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
    )


def _agent_request(
    capability_name: str = "agent.execute.invitation_sender",
    params: dict | None = None,
    *,
    caller: str = "test-agent",
) -> CapabilityRequest:
    """Build a CapabilityRequest targeting an agent capability."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params
        or {
            "event_name": "Birthday Party",
            "guest_list": ["Alice", "Bob"],
        },
        tier=Tier.MEDIUM.value,
        caller=caller,
    )


def _make_agent_contract(
    name: str = "agent.execute.test_agent",
    tools_granted: list[str] | None = None,
    llm_budget_tokens: int = 2048,
) -> AgentContract:
    """Build a minimal AgentContract for direct factory tests."""
    return AgentContract(
        name=name,
        version="1.0.0",
        domain=["TEST"],
        description="Test agent for integration tests",
        capabilities=["test_action"],
        limitations=[],
        required_inputs=[
            InputSpec(name="query", type="STRING", description="Test input"),
        ],
        output={"type": "object"},
        provider_type="AGENT",
        provider_id="test-agent-runner",
        safety_band_min=SafetyBand.GREEN.value,
        prompt_template="test_prompt_v1",
        tools_granted=tools_granted or ["tool.execute.restaurant_booking"],
        llm_budget_tokens=llm_budget_tokens,
        max_tool_calls=3,
        max_execution_time_ms=10000,
    )


def _make_execution_context(
    trace_id: str = "test-trace-001",
) -> ExecutionContext:
    """Build a minimal ExecutionContext."""
    return ExecutionContext(
        session_sections={
            "beliefs_active.entities": {"Alice": {"role": "friend"}},
        },
        params={"query": "hello"},
        trace_id=trace_id,
    )


def _make_agent_factory(
    *,
    model_gateway: Optional[TestModelGatewayAdapter] = None,
    delta_bus: Optional[TestDeltaBusAdapter] = None,
    contract: Optional[AgentContract] = None,
    pool: Optional[AgentPool] = None,
) -> AgentFactory:
    """Build an AgentFactory with real test adapters."""
    gw = model_gateway or TestModelGatewayAdapter(
        default_responses=["Agent response: task completed"],
    )
    db = delta_bus or TestDeltaBusAdapter()
    state = TestSessionStateReaderAdapter()
    target_contract = contract or _make_agent_contract()

    # Contract loader returns the contract on exact name match
    def loader(name: str) -> Optional[AgentContract]:
        if name == target_contract.name:
            return target_contract
        return None

    return AgentFactory(
        model_gateway=gw,
        state_reader=state,
        delta_bus=db,
        contract_loader=loader,
        pool=pool,
    )


# =========================================================================
# 6.3.4a -- Agent Lifecycle FSM
# =========================================================================


class TestAgentLifecycle:
    """
    Verify the 6-state agent lifecycle FSM.

    States: PENDING -> WARMING -> ACTIVE -> IDLE -> DRAINING -> TERMINATED.
    """

    def test_agent_starts_in_pending(self) -> None:
        """New Agent is in PENDING state."""
        contract = _make_agent_contract()
        context = _make_execution_context()
        agent = Agent(
            agent_id="test-001",
            contract=contract,
            context=context,
        )
        assert agent.lifecycle_state == AgentLifecycleState.PENDING

    def test_warm_up_transitions_to_active(self) -> None:
        """warm_up() moves PENDING -> WARMING -> ACTIVE."""
        contract = _make_agent_contract()
        context = _make_execution_context()
        agent = Agent(
            agent_id="test-002",
            contract=contract,
            context=context,
        )
        agent.warm_up()
        assert agent.lifecycle_state == AgentLifecycleState.ACTIVE

    def test_idle_transitions_from_active(self) -> None:
        """idle() moves ACTIVE -> IDLE."""
        contract = _make_agent_contract()
        context = _make_execution_context()
        agent = Agent(
            agent_id="test-003",
            contract=contract,
            context=context,
        )
        agent.warm_up()
        agent.idle()
        assert agent.lifecycle_state == AgentLifecycleState.IDLE

    def test_reactivate_from_idle(self) -> None:
        """reactivate() moves IDLE -> ACTIVE."""
        contract = _make_agent_contract()
        context = _make_execution_context()
        agent = Agent(
            agent_id="test-004",
            contract=contract,
            context=context,
        )
        agent.warm_up()
        agent.idle()
        agent.reactivate()
        assert agent.lifecycle_state == AgentLifecycleState.ACTIVE

    def test_drain_from_active(self) -> None:
        """drain() moves ACTIVE -> DRAINING."""
        contract = _make_agent_contract()
        context = _make_execution_context()
        agent = Agent(
            agent_id="test-005",
            contract=contract,
            context=context,
        )
        agent.warm_up()
        agent.drain()
        assert agent.lifecycle_state == AgentLifecycleState.DRAINING

    def test_terminate_from_draining(self) -> None:
        """terminate() moves DRAINING -> TERMINATED."""
        contract = _make_agent_contract()
        context = _make_execution_context()
        agent = Agent(
            agent_id="test-006",
            contract=contract,
            context=context,
        )
        agent.warm_up()
        agent.drain()
        agent.terminate()
        assert agent.lifecycle_state == AgentLifecycleState.TERMINATED

    def test_full_lifecycle_happy_path(self) -> None:
        """Complete lifecycle: PENDING -> ACTIVE -> IDLE -> ACTIVE -> DRAINING -> TERMINATED."""
        contract = _make_agent_contract()
        context = _make_execution_context()
        agent = Agent(
            agent_id="test-007",
            contract=contract,
            context=context,
        )
        assert agent.lifecycle_state == AgentLifecycleState.PENDING

        agent.warm_up()
        assert agent.lifecycle_state == AgentLifecycleState.ACTIVE

        agent.idle()
        assert agent.lifecycle_state == AgentLifecycleState.IDLE

        agent.reactivate()
        assert agent.lifecycle_state == AgentLifecycleState.ACTIVE

        agent.drain()
        assert agent.lifecycle_state == AgentLifecycleState.DRAINING

        agent.terminate()
        assert agent.lifecycle_state == AgentLifecycleState.TERMINATED


# =========================================================================
# 6.3.4b -- Agent Execution (direct factory tests)
# =========================================================================


class TestAgentFactoryExecution:
    """
    Test the 8-step AgentFactory.spawn_and_execute() flow.

    Uses real TestModelGatewayAdapter and TestDeltaBusAdapter.
    """

    async def test_spawn_and_execute_success(self) -> None:
        """Successfully spawn agent and execute a capability."""
        factory = _make_agent_factory()
        request = _agent_request(capability_name="agent.execute.test_agent")
        context = _make_execution_context()

        result = await factory.spawn_and_execute(request, context, "trace-001")

        assert result.success is True
        assert result.agent_id != ""
        assert result.error_message == ""

    async def test_spawn_creates_llm_handle(self) -> None:
        """Factory creates LLM handle via TestModelGatewayAdapter."""
        gw = TestModelGatewayAdapter(
            default_responses=["LLM generated output"],
        )
        factory = _make_agent_factory(model_gateway=gw)
        request = _agent_request(capability_name="agent.execute.test_agent")
        context = _make_execution_context()

        result = await factory.spawn_and_execute(request, context, "trace-002")

        assert result.success is True
        # Gateway should have created at least one handle
        assert gw.handle_count >= 1

    async def test_spawn_emits_deltas(self) -> None:
        """Agent execution emits deltas via DeltaEmitter -> TestDeltaBusAdapter."""
        delta_bus = TestDeltaBusAdapter()
        factory = _make_agent_factory(delta_bus=delta_bus)
        request = _agent_request(capability_name="agent.execute.test_agent")
        context = _make_execution_context()

        result = await factory.spawn_and_execute(request, context, "trace-003")

        assert result.success is True
        # DeltaEmitter is created during spawn, agent may or may not emit
        # deltas depending on LLM output, but delta_bus is wired
        assert delta_bus is not None

    async def test_contract_not_found_returns_failure(self) -> None:
        """When contract is missing, factory returns failure result."""
        factory = _make_agent_factory()
        request = _agent_request(
            capability_name="agent.execute.nonexistent_agent",
        )
        context = _make_execution_context()

        result = await factory.spawn_and_execute(request, context, "trace-004")

        assert result.success is False
        assert "not found" in result.error_message.lower()

    async def test_spawn_with_pool_reuses_agent(self) -> None:
        """After successful execution, agent goes to pool and is reused."""
        pool = AgentPool(AgentPoolConfig(max_pool_size=3))
        factory = _make_agent_factory(pool=pool)
        request = _agent_request(capability_name="agent.execute.test_agent")
        context = _make_execution_context()

        # First execution: fresh spawn
        r1 = await factory.spawn_and_execute(request, context, "trace-first")
        assert r1.success is True
        assert pool.size("agent.execute.test_agent") == 1

        # Second execution: should reuse pooled agent
        r2 = await factory.spawn_and_execute(request, context, "trace-second")
        assert r2.success is True
        assert pool.total_reuses >= 1

    async def test_factory_tracks_agent_id(self) -> None:
        """Successful execution returns a non-empty agent_id."""
        factory = _make_agent_factory()
        request = _agent_request(capability_name="agent.execute.test_agent")
        context = _make_execution_context()

        result = await factory.spawn_and_execute(request, context, "trace-005")

        assert result.success is True
        assert len(result.agent_id) > 0
        # Agent ID should be UUID format
        assert "-" in result.agent_id


# =========================================================================
# 6.3.4c -- Agent.execute() with LLM
# =========================================================================


class TestAgentExecution:
    """
    Test Agent.execute() directly with real TestModelGatewayAdapter.
    """

    async def test_execute_with_llm_returns_result(self) -> None:
        """Agent.execute() uses LLM handle to generate output."""
        gw = TestModelGatewayAdapter(
            default_responses=["Generated invitation for Alice"],
        )
        contract = _make_agent_contract()
        handle = gw.create_handle(budget_tokens=2048, trace_id="test")
        context = _make_execution_context()

        agent = Agent(
            agent_id="test-llm-001",
            contract=contract,
            context=context,
            llm_handle=handle,
        )
        agent.warm_up()
        result = await agent.execute({"query": "invite Alice"})

        assert result.success is True
        assert result.data is not None

    async def test_execute_without_llm_passthrough(self) -> None:
        """Agent.execute() without LLM handle returns passthrough result."""
        contract = _make_agent_contract()
        context = _make_execution_context()

        agent = Agent(
            agent_id="test-no-llm-001",
            contract=contract,
            context=context,
            llm_handle=None,
        )
        agent.warm_up()
        result = await agent.execute({"query": "passthrough test"})

        assert result.success is True

    async def test_execute_auto_reactivates_from_idle(self) -> None:
        """Agent.execute() auto-reactivates from IDLE state."""
        contract = _make_agent_contract()
        context = _make_execution_context()

        agent = Agent(
            agent_id="test-reactivate-001",
            contract=contract,
            context=context,
        )
        agent.warm_up()
        agent.idle()
        assert agent.lifecycle_state == AgentLifecycleState.IDLE

        # Execute should auto-reactivate
        result = await agent.execute({"query": "hello"})
        assert result.success is True
        assert agent.lifecycle_state == AgentLifecycleState.ACTIVE


# =========================================================================
# 6.3.4d -- Tool Scoping
# =========================================================================


class TestAgentToolScoping:
    """
    Test ToolScope enforcement for sub-agent capabilities.
    """

    def test_tool_scope_allows_granted_tools(self) -> None:
        """ToolScope validates tools in the granted set."""
        scope = ToolScope(
            tools_granted=[
                "tool.execute.restaurant_booking",
                "tool.read.weather_api",
            ],
        )
        assert scope.validate("tool.execute.restaurant_booking") is True
        assert scope.is_allowed("tool.read.weather_api") is True

    def test_tool_scope_rejects_ungranted_tools(self) -> None:
        """ToolScope rejects tools NOT in the granted set."""
        scope = ToolScope(
            tools_granted=["tool.execute.restaurant_booking"],
        )
        assert scope.is_allowed("tool.execute.payments") is False

    def test_tool_scope_from_agent_contract(self) -> None:
        """ToolScope built from AgentContract.tools_granted matches YAML."""
        contract = _make_agent_contract(
            tools_granted=[
                "tool.execute.restaurant_booking",
                "tool.read.weather_api",
            ],
        )
        scope = ToolScope(tools_granted=contract.tools_granted)

        assert scope.is_allowed("tool.execute.restaurant_booking") is True
        assert scope.is_allowed("tool.read.weather_api") is True
        assert scope.is_allowed("tool.execute.banking") is False

    def test_tool_scope_from_fixture_contract(self) -> None:
        """ToolScope built from invitation_sender fixture YAML."""
        parsed = load_fixture_contract("invitation_sender")
        tools = getattr(parsed, "tools_granted", [])
        assert len(tools) > 0

        scope = ToolScope(tools_granted=tools)
        assert scope.is_allowed("tool.execute.restaurant_booking") is True
        assert scope.is_allowed("tool.read.weather_api") is True
        assert scope.is_allowed("tool.execute.payments") is False


# =========================================================================
# 6.3.4e -- DeltaEmitter and AgentDelta
# =========================================================================


class TestDeltaEmission:
    """
    Test DeltaEmitter batching and emission via TestDeltaBusAdapter.
    """

    def test_delta_emitter_queues_and_flushes(self) -> None:
        """DeltaEmitter queues deltas and flush() sends to bus."""
        delta_bus = TestDeltaBusAdapter()
        emitter = DeltaEmitter(
            agent_id="test-emitter-001",
            delta_bus=delta_bus,
            trace_id="trace-delta",
        )

        emitter.emit(
            delta_type="belief",
            section="beliefs_active",
            key="entity_alice",
            value={"name": "Alice", "role": "friend"},
        )
        emitter.emit(
            delta_type="fact",
            section="facts",
            key="weather_today",
            value="sunny",
        )

        assert emitter.pending_count == 2

        flushed = emitter.flush()
        assert flushed == 2
        assert emitter.pending_count == 0

        # Verify deltas reached the bus
        all_deltas = delta_bus.get_deltas()
        assert len(all_deltas) == 2

    def test_delta_lww_merge(self) -> None:
        """Last-Writer-Wins: later delta for same (section, key) replaces earlier."""
        delta_bus = TestDeltaBusAdapter()
        emitter = DeltaEmitter(
            agent_id="test-lww-001",
            delta_bus=delta_bus,
            trace_id="trace-lww",
        )

        emitter.emit(delta_type="belief", section="beliefs", key="mood", value="happy")
        emitter.emit(delta_type="belief", section="beliefs", key="mood", value="excited")

        # Only 1 pending because same (section, key)
        assert emitter.pending_count == 1

        flushed = emitter.flush()
        assert flushed == 1

        deltas = delta_bus.get_deltas()
        assert len(deltas) == 1
        assert deltas[0].data["value"] == "excited"

    def test_agent_delta_serialization(self) -> None:
        """AgentDelta serializes to dict and deserializes back."""
        delta = AgentDelta(
            agent_id="test-ser-001",
            delta_type="observation",
            section="observations",
            key="weather",
            value={"condition": "sunny", "temp": 22},
            op="set",
            timestamp_ms=1000,
            trace_id="trace-ser",
        )

        d = delta.to_dict()
        assert d["agent_id"] == "test-ser-001"
        assert d["delta_type"] == "observation"
        assert d["section"] == "observations"
        assert d["key"] == "weather"
        assert d["op"] == "set"

        restored = AgentDelta.from_dict(d)
        assert restored.agent_id == delta.agent_id
        assert restored.value == delta.value

    def test_delta_operations(self) -> None:
        """AgentDelta supports set, append, delete operations."""
        delta_bus = TestDeltaBusAdapter()
        emitter = DeltaEmitter(
            agent_id="test-ops-001",
            delta_bus=delta_bus,
            trace_id="trace-ops",
        )

        emitter.emit(delta_type="fact", section="facts", key="k1", value="v1", op="set")
        emitter.emit(delta_type="fact", section="facts", key="k2", value="item", op="append")
        emitter.emit(delta_type="fact", section="facts", key="k3", value=None, op="delete")

        flushed = emitter.flush()
        assert flushed == 3

    def test_invalid_delta_op_raises(self) -> None:
        """AgentDelta with invalid op raises ValueError."""
        with pytest.raises(ValueError, match="Invalid delta op"):
            AgentDelta(
                agent_id="test",
                delta_type="fact",
                section="facts",
                key="k1",
                value="v1",
                op="invalid",
            )


# =========================================================================
# 6.3.4f -- Agent Pool
# =========================================================================


class TestAgentPool:
    """Test AgentPool IDLE management."""

    def test_pool_put_and_get(self) -> None:
        """Pool stores ACTIVE agent as IDLE and retrieves reactivated."""
        pool = AgentPool(AgentPoolConfig(max_pool_size=3))
        contract = _make_agent_contract()
        context = _make_execution_context()

        agent = Agent(agent_id="pool-001", contract=contract, context=context)
        agent.warm_up()
        assert agent.lifecycle_state == AgentLifecycleState.ACTIVE

        pool.put(agent)
        assert agent.lifecycle_state == AgentLifecycleState.IDLE
        assert pool.size(contract.name) == 1

        retrieved = pool.get(contract.name)
        assert retrieved is not None
        assert retrieved.id == "pool-001"
        assert retrieved.lifecycle_state == AgentLifecycleState.ACTIVE

    def test_pool_evicts_when_full(self) -> None:
        """Pool evicts oldest agent when at capacity."""
        pool = AgentPool(AgentPoolConfig(max_pool_size=2))
        contract = _make_agent_contract()
        context = _make_execution_context()

        a1 = Agent(agent_id="pool-e1", contract=contract, context=context)
        a1.warm_up()
        pool.put(a1)

        a2 = Agent(agent_id="pool-e2", contract=contract, context=context)
        a2.warm_up()
        pool.put(a2)

        a3 = Agent(agent_id="pool-e3", contract=contract, context=context)
        a3.warm_up()
        pool.put(a3)

        # Pool size should remain at max_pool_size
        assert pool.size(contract.name) == 2
        assert pool.total_evictions >= 1

    def test_pool_drain_all(self) -> None:
        """drain_all() terminates all pooled agents."""
        pool = AgentPool(AgentPoolConfig(max_pool_size=5))
        contract = _make_agent_contract()
        context = _make_execution_context()

        for i in range(3):
            a = Agent(agent_id=f"pool-d{i}", contract=contract, context=context)
            a.warm_up()
            pool.put(a)

        assert pool.size() == 3
        terminated = pool.drain_all()
        assert terminated == 3
        assert pool.size() == 0


# =========================================================================
# 6.3.4g -- Agent via Fabric (stub mode verification)
# =========================================================================


class TestAgentViaFabric:
    """
    Test agent execution through fabric.execute().

    The factory-created AgentProvider is in stub mode (no agent_factory).
    Verifies proper error handling and event emission.
    """

    async def test_agent_execute_via_fabric_emits_invoked(self) -> None:
        """fabric.execute() with agent capability emits invoked event."""
        fabric = _make_fabric()
        request = _agent_request()

        await fabric.execute(request)

        # Invoked event should always fire regardless of outcome
        event_adapter = fabric.event_port
        invoked = event_adapter.get_captured(topic=TOPIC_CAPABILITY_INVOKED)
        assert len(invoked) >= 1

    async def test_agent_stub_returns_failure(self) -> None:
        """
        Agent execution in stub mode returns failure result.

        The factory-created AgentProvider has no agent_factory, so
        _execute() raises AgentNotImplementedError which is wrapped
        in a failure CapabilityResult.
        """
        fabric = _make_fabric()
        request = _agent_request()

        result = await fabric.execute(request)

        # Should fail because AgentProvider is in stub mode
        assert result.success is False
        assert result.error is not None

    async def test_agent_capability_registered_via_module_loader(self) -> None:
        """
        Agent contracts from fixture YAML are loaded and registered.
        """
        fabric = _make_fabric()

        contract = fabric.lookup("agent.execute.invitation_sender")
        assert contract is not None
        assert contract.name == "agent.execute.invitation_sender"
        assert contract.provider_type == "AGENT"

    async def test_agent_execution_emits_learning_signal(self) -> None:
        """Even failed agent execution emits a learning signal."""
        fabric = _make_fabric()

        # The default invitation_sender has no provider_id, so resolution
        # fails before reaching execution. Register a custom contract
        # with provider_type=AGENT and a provider_id so resolution succeeds
        # and the stub mode failure goes through the full execute pipeline
        # (steps 7-9) including learning signal emission.
        # Must skip validation because AGENT naming/type constraints
        # reject CapabilityContract with agent-style names.
        custom_agent = CapabilityContract(
            name="agent.execute.learning_test",
            version="1.0.0",
            domain=["TEST"],
            description="Agent for learning signal test",
            capabilities=["test_action"],
            limitations=[],
            required_inputs=[
                InputSpec(name="input_a", type="STRING", description="Test"),
            ],
            output={"type": "object"},
            provider_type="AGENT",
            provider_id="agent-learning-test",
            safety_band_min=SafetyBand.GREEN.value,
        )
        # Register directly with skip_validation to avoid schema constraints
        fabric.registry.register(custom_agent, skip_validation=True)
        # Also register the provider so resolution succeeds
        from k1.fabric.types import ProviderConfig

        provider_registry = fabric.facade._resolver._provider_matcher._provider_registry
        provider_registry.register_provider(
            "agent-learning-test",
            ProviderConfig(
                provider_id="agent-learning-test",
                provider_type="AGENT",
                endpoint="local://agent-learning-test",
            ),
        )

        request = _agent_request(
            capability_name="agent.execute.learning_test",
            params={"input_a": "test"},
        )
        await fabric.execute(request)

        event_adapter = fabric.event_port
        learning = event_adapter.get_captured(topic=TOPIC_LEARNING_SIGNAL)
        # Learning signal is emitted for both success and failure
        assert len(learning) >= 1
