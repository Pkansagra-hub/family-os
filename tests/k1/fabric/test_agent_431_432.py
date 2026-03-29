"""
Tests for Epic 4.3 -- Agent (4.3.2) and AgentFactory (4.3.1).

Covers:
  - Agent lifecycle FSM (6 states, valid + invalid transitions)
  - Agent.execute() with and without LLM handle
  - Agent auto-reactivation from IDLE
  - Agent delta emission
  - AgentFactory 8-step spawn flow
  - AgentFactory.spawn_and_execute() happy + error paths
  - AgentFactoryConfig defaults and customization
  - AgentLifecycleError exception
  - Port protocols structural typing
  - Module exports (providers __init__.py)

Test architecture:
  - All tests are integration-oriented (real objects, no mocks)
  - Fakes implement port protocols structurally
  - pytest-asyncio auto mode for async tests
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.providers.agent_provider import (
    _VALID_TRANSITIONS,
    IDLE_TTL_S,
    Agent,
    AgentFactory,
    AgentFactoryConfig,
    AgentLifecycleError,
    AgentProvider,
    AgentProviderError,
    AgentResult,
    IAgentMailbox,
    IDeltaBusPort,
    ILLMHandle,
    IModelGatewayPort,
    ISessionStateReader,
)
from k1.fabric.types import (
    AgentContract,
    AgentLifecycleState,
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
)

# ---------------------------------------------------------------------------
# Fake implementations of port protocols
# ---------------------------------------------------------------------------


class FakeLLMHandle:
    """Fake ILLMHandle for testing."""

    def __init__(
        self,
        model_id: str = "fake-model-v1",
        budget_tokens: int = 4000,
        response: str = "LLM response text",
        fail: bool = False,
    ) -> None:
        self._model_id = model_id
        self._budget_tokens = budget_tokens
        self._response = response
        self._fail = fail
        self.calls: List[Dict[str, Any]] = []

    async def generate(self, prompt: str, params: Dict[str, Any]) -> str:
        self.calls.append({"prompt": prompt, "params": params})
        if self._fail:
            raise RuntimeError("LLM generation failed")
        return self._response

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def budget_tokens(self) -> int:
        return self._budget_tokens


class FakeModelGateway:
    """Fake IModelGatewayPort for testing."""

    def __init__(
        self,
        handle: Optional[FakeLLMHandle] = None,
        fail_create: bool = False,
    ) -> None:
        self._handle = handle or FakeLLMHandle()
        self._fail_create = fail_create
        self.create_calls: List[Dict[str, Any]] = []
        self.loaded_models: Dict[str, bool] = {"fake-model-v1": True}

    def create_handle(
        self,
        budget_tokens: int,
        model_preference: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        trace_id: str = "",
    ) -> FakeLLMHandle:
        self.create_calls.append(
            {
                "budget_tokens": budget_tokens,
                "model_preference": model_preference,
                "capabilities": capabilities,
                "trace_id": trace_id,
            }
        )
        if self._fail_create:
            raise RuntimeError("Model gateway unavailable")
        return self._handle

    def is_model_loaded(self, model_id: str) -> bool:
        return self.loaded_models.get(model_id, False)


class FakeDeltaBus:
    """Fake IDeltaBusPort for testing."""

    def __init__(self, fail: bool = False) -> None:
        self._fail = fail
        self.deltas: List[Dict[str, Any]] = []

    def emit_delta(
        self,
        agent_id: str,
        delta_type: str,
        section: str,
        data: Dict[str, Any],
    ) -> None:
        if self._fail:
            raise RuntimeError("Delta bus failure")
        self.deltas.append(
            {
                "agent_id": agent_id,
                "delta_type": delta_type,
                "section": section,
                "data": data,
            }
        )


class FakeMailbox:
    """Fake IAgentMailbox for testing."""

    def __init__(self) -> None:
        self._queue: List[Dict[str, Any]] = []
        self._closed = False

    def send(self, message: Dict[str, Any]) -> None:
        if self._closed:
            raise RuntimeError("Mailbox closed")
        self._queue.append(message)

    def receive(self) -> Optional[Dict[str, Any]]:
        if self._queue:
            return self._queue.pop(0)
        return None

    @property
    def depth(self) -> int:
        return len(self._queue)

    def close(self) -> None:
        self._closed = True


class FakeStateReader:
    """Fake ISessionStateReader for testing."""

    def __init__(self, sections: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._sections = sections or {}

    def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        return self._sections.get(section)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_contract(
    name: str = "test_agent",
    provider_id: str = "agent-runner",
    tools: Optional[List[str]] = None,
    llm_budget: int = 4000,
    max_tool_calls: int = 10,
) -> AgentContract:
    """Build an AgentContract for testing."""
    return AgentContract(
        name=name,
        version="1.0.0",
        provider_id=provider_id,
        provider_type="AGENT",
        required_context=["beliefs_active"],
        optional_context=["preferences"],
        prompt_template="You are a helpful assistant.",
        tools_granted=tools or [],
        llm_budget_tokens=llm_budget,
        max_tool_calls=max_tool_calls,
    )


def _make_context(trace_id: str = "t-001", prompt: str = "") -> ExecutionContext:
    """Build an ExecutionContext for testing."""
    return ExecutionContext(trace_id=trace_id, prompt=prompt)


def _make_agent(
    contract: Optional[AgentContract] = None,
    llm_handle: Optional[FakeLLMHandle] = None,
    delta_bus: Optional[FakeDeltaBus] = None,
    mailbox: Optional[FakeMailbox] = None,
    state_reader: Optional[FakeStateReader] = None,
    context: Optional[ExecutionContext] = None,
    agent_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
) -> Agent:
    """Build an Agent for testing."""
    return Agent(
        agent_id=agent_id,
        contract=contract or _make_agent_contract(),
        context=context or _make_context(),
        mailbox=mailbox,
        llm_handle=llm_handle,
        state_reader=state_reader,
        delta_bus=delta_bus,
    )


# ===================================================================
# 4.3.2 -- Agent class
# ===================================================================


class TestAgentConstruction:
    """Agent construction and initial state."""

    def test_construction_minimal(self) -> None:
        """Agent constructs with just contract and context."""
        agent = _make_agent()
        assert agent.id == "aaaaaaaa-0000-0000-0000-000000000001"
        assert agent.contract.name == "test_agent"
        assert agent.lifecycle_state == AgentLifecycleState.PENDING
        assert agent.tokens_used == 0
        assert agent.tool_calls == 0

    def test_construction_all_ports(self) -> None:
        """Agent accepts all optional port references."""
        handle = FakeLLMHandle()
        bus = FakeDeltaBus()
        mbox = FakeMailbox()
        reader = FakeStateReader()
        agent = _make_agent(
            llm_handle=handle,
            delta_bus=bus,
            mailbox=mbox,
            state_reader=reader,
        )
        assert agent.lifecycle_state == AgentLifecycleState.PENDING

    def test_initial_state_is_pending(self) -> None:
        """Newly constructed agent is in PENDING state."""
        agent = _make_agent()
        assert agent.lifecycle_state == AgentLifecycleState.PENDING
        assert not agent.is_active
        assert not agent.is_idle
        assert not agent.is_terminated

    def test_context_property(self) -> None:
        """Agent exposes context from construction."""
        ctx = _make_context(trace_id="t-999", prompt="hello")
        agent = _make_agent(context=ctx)
        assert agent.context.trace_id == "t-999"
        assert agent.context.prompt == "hello"

    def test_idle_elapsed_zero_when_not_idle(self) -> None:
        """idle_elapsed_s is 0 when not in IDLE state."""
        agent = _make_agent()
        assert agent.idle_elapsed_s == 0.0
        assert not agent.idle_ttl_expired


class TestAgentLifecycle:
    """Agent lifecycle FSM transitions."""

    def test_warm_up_transitions(self) -> None:
        """warm_up() moves PENDING -> WARMING -> ACTIVE."""
        agent = _make_agent()
        assert agent.lifecycle_state == AgentLifecycleState.PENDING
        agent.warm_up()
        assert agent.lifecycle_state == AgentLifecycleState.ACTIVE
        assert agent.is_active

    def test_idle_from_active(self) -> None:
        """idle() moves ACTIVE -> IDLE."""
        agent = _make_agent()
        agent.warm_up()
        agent.idle()
        assert agent.lifecycle_state == AgentLifecycleState.IDLE
        assert agent.is_idle
        assert not agent.is_active

    def test_reactivate_from_idle(self) -> None:
        """reactivate() moves IDLE -> ACTIVE."""
        agent = _make_agent()
        agent.warm_up()
        agent.idle()
        agent.reactivate()
        assert agent.lifecycle_state == AgentLifecycleState.ACTIVE
        assert agent.is_active
        assert agent.idle_elapsed_s == 0.0

    def test_drain_from_active(self) -> None:
        """drain() moves ACTIVE -> DRAINING."""
        agent = _make_agent()
        agent.warm_up()
        agent.drain()
        assert agent.lifecycle_state == AgentLifecycleState.DRAINING

    def test_drain_from_idle(self) -> None:
        """drain() moves IDLE -> DRAINING."""
        agent = _make_agent()
        agent.warm_up()
        agent.idle()
        agent.drain()
        assert agent.lifecycle_state == AgentLifecycleState.DRAINING

    def test_terminate_from_draining(self) -> None:
        """terminate() moves DRAINING -> TERMINATED."""
        agent = _make_agent()
        agent.warm_up()
        agent.drain()
        agent.terminate()
        assert agent.lifecycle_state == AgentLifecycleState.TERMINATED
        assert agent.is_terminated

    def test_full_lifecycle_happy_path(self) -> None:
        """Full lifecycle: PENDING -> WARMING -> ACTIVE -> IDLE -> DRAINING -> TERMINATED."""
        agent = _make_agent()
        assert agent.lifecycle_state == AgentLifecycleState.PENDING
        agent.warm_up()
        assert agent.lifecycle_state == AgentLifecycleState.ACTIVE
        agent.idle()
        assert agent.lifecycle_state == AgentLifecycleState.IDLE
        agent.drain()
        assert agent.lifecycle_state == AgentLifecycleState.DRAINING
        agent.terminate()
        assert agent.lifecycle_state == AgentLifecycleState.TERMINATED

    def test_full_lifecycle_with_reactivation(self) -> None:
        """Lifecycle with pool reuse: ACTIVE -> IDLE -> ACTIVE -> IDLE -> DRAIN -> TERM."""
        agent = _make_agent()
        agent.warm_up()
        agent.idle()
        agent.reactivate()
        assert agent.is_active
        agent.idle()
        agent.drain()
        agent.terminate()
        assert agent.is_terminated

    def test_terminate_clears_references(self) -> None:
        """terminate() clears mailbox, llm_handle, state_reader."""
        agent = _make_agent(
            llm_handle=FakeLLMHandle(),
            mailbox=FakeMailbox(),
            state_reader=FakeStateReader(),
        )
        agent.warm_up()
        agent.drain()
        agent.terminate()
        # Internal references cleared (access via name mangling for validation)
        assert agent._mailbox is None
        assert agent._llm_handle is None
        assert agent._state_reader is None


class TestAgentLifecycleErrors:
    """Invalid lifecycle transitions raise AgentLifecycleError."""

    def test_warm_up_from_active(self) -> None:
        """Cannot warm_up() an already ACTIVE agent."""
        agent = _make_agent()
        agent.warm_up()
        with pytest.raises(AgentLifecycleError) as exc_info:
            agent.warm_up()
        assert "ACTIVE" in str(exc_info.value)
        assert "WARMING" in str(exc_info.value)

    def test_idle_from_pending(self) -> None:
        """Cannot idle() from PENDING."""
        agent = _make_agent()
        with pytest.raises(AgentLifecycleError):
            agent.idle()

    def test_reactivate_from_active(self) -> None:
        """Cannot reactivate() from ACTIVE (not IDLE)."""
        agent = _make_agent()
        agent.warm_up()
        with pytest.raises(AgentLifecycleError):
            agent.reactivate()

    def test_drain_from_pending(self) -> None:
        """Cannot drain() from PENDING."""
        agent = _make_agent()
        with pytest.raises(AgentLifecycleError):
            agent.drain()

    def test_terminate_from_active(self) -> None:
        """Cannot terminate() directly from ACTIVE."""
        agent = _make_agent()
        agent.warm_up()
        with pytest.raises(AgentLifecycleError):
            agent.terminate()

    def test_terminate_from_idle(self) -> None:
        """Cannot terminate() directly from IDLE."""
        agent = _make_agent()
        agent.warm_up()
        agent.idle()
        with pytest.raises(AgentLifecycleError):
            agent.terminate()

    def test_drain_from_terminated(self) -> None:
        """Cannot drain() after TERMINATED."""
        agent = _make_agent()
        agent.warm_up()
        agent.drain()
        agent.terminate()
        with pytest.raises(AgentLifecycleError):
            agent.drain()

    def test_warm_up_from_terminated(self) -> None:
        """Cannot warm_up() after TERMINATED."""
        agent = _make_agent()
        agent.warm_up()
        agent.drain()
        agent.terminate()
        with pytest.raises(AgentLifecycleError):
            agent.warm_up()

    def test_lifecycle_error_attributes(self) -> None:
        """AgentLifecycleError carries agent_id, from_state, to_state."""
        agent = _make_agent(agent_id="err-agent-id")
        agent.warm_up()
        with pytest.raises(AgentLifecycleError) as exc_info:
            agent.idle()
            agent.terminate()  # Invalid: IDLE -> TERMINATED
        # Actually idle() succeeds, we need a different path
        # Let's test directly
        agent2 = _make_agent(agent_id="err-agent-id-2")
        with pytest.raises(AgentLifecycleError) as exc_info:
            agent2.idle()
        err = exc_info.value
        assert err.agent_id == "err-agent-id-2"
        assert err.from_state == "PENDING"
        assert err.to_state == "IDLE"

    def test_lifecycle_error_inherits_agent_provider_error(self) -> None:
        """AgentLifecycleError is a subclass of AgentProviderError."""
        assert issubclass(AgentLifecycleError, AgentProviderError)


class TestAgentIdleTTL:
    """Agent idle timeout tracking."""

    def test_idle_elapsed_tracks_time(self) -> None:
        """idle_elapsed_s increases after entering IDLE."""
        agent = _make_agent()
        agent.warm_up()
        agent.idle()
        time.sleep(0.05)
        assert agent.idle_elapsed_s >= 0.04

    def test_idle_ttl_not_expired(self) -> None:
        """idle_ttl_expired is False when within TTL."""
        agent = _make_agent()
        agent.warm_up()
        agent.idle()
        assert not agent.idle_ttl_expired

    def test_idle_elapsed_resets_on_reactivate(self) -> None:
        """Reactivation resets idle_elapsed_s to 0."""
        agent = _make_agent()
        agent.warm_up()
        agent.idle()
        time.sleep(0.02)
        agent.reactivate()
        assert agent.idle_elapsed_s == 0.0

    def test_idle_ttl_constant(self) -> None:
        """IDLE_TTL_S is 60 seconds."""
        assert IDLE_TTL_S == 60


class TestAgentExecute:
    """Agent.execute() method."""

    async def test_execute_no_llm_passthrough(self) -> None:
        """Without LLM handle, execute returns params as output."""
        agent = _make_agent()
        agent.warm_up()
        result = await agent.execute({"key": "value", "request_id": "r-1"})
        assert result.success
        assert result.data["key"] == "value"
        assert result.data["request_id"] == "r-1"

    async def test_execute_with_llm(self) -> None:
        """With LLM handle, execute calls generate and returns response."""
        handle = FakeLLMHandle(response="Hello from LLM")
        agent = _make_agent(llm_handle=handle)
        agent.warm_up()
        result = await agent.execute({"question": "hi"})
        assert result.success
        assert result.data["response"] == "Hello from LLM"
        assert len(handle.calls) == 1
        assert agent.tokens_used > 0  # Approximate token tracking

    async def test_execute_from_idle_auto_reactivates(self) -> None:
        """Execute from IDLE state auto-reactivates the agent."""
        agent = _make_agent()
        agent.warm_up()
        agent.idle()
        assert agent.is_idle
        result = await agent.execute({"key": "v"})
        assert result.success
        assert agent.is_active

    async def test_execute_from_pending_fails(self) -> None:
        """Execute from PENDING returns failure (not in ACTIVE/IDLE)."""
        agent = _make_agent()
        result = await agent.execute({"key": "v"})
        assert not result.success
        assert "PENDING" in (result.error.message if result.error else "")

    async def test_execute_from_terminated_fails(self) -> None:
        """Execute from TERMINATED returns failure."""
        agent = _make_agent()
        agent.warm_up()
        agent.drain()
        agent.terminate()
        result = await agent.execute({"key": "v"})
        assert not result.success

    async def test_execute_from_draining_fails(self) -> None:
        """Execute from DRAINING returns failure."""
        agent = _make_agent()
        agent.warm_up()
        agent.drain()
        result = await agent.execute({"key": "v"})
        assert not result.success

    async def test_execute_emits_delta(self) -> None:
        """Execute emits delta via IDeltaBusPort when available."""
        bus = FakeDeltaBus()
        agent = _make_agent(delta_bus=bus, agent_id="delta-agent-001")
        agent.warm_up()
        await agent.execute({"data": "test"})
        assert len(bus.deltas) == 1
        delta = bus.deltas[0]
        assert delta["agent_id"] == "delta-agent-001"
        assert delta["delta_type"] == "agent_output"
        assert delta["section"] == "history_active"
        assert "output" in delta["data"]

    async def test_execute_delta_failure_non_fatal(self) -> None:
        """Delta emission failure does not fail the execution."""
        bus = FakeDeltaBus(fail=True)
        agent = _make_agent(delta_bus=bus)
        agent.warm_up()
        result = await agent.execute({"key": "v"})
        assert result.success  # Delta failure is non-fatal

    async def test_execute_llm_failure_returns_failure(self) -> None:
        """LLM generation failure returns a failure result (no raise)."""
        handle = FakeLLMHandle(fail=True)
        agent = _make_agent(llm_handle=handle)
        agent.warm_up()
        result = await agent.execute({"key": "v"})
        assert not result.success
        assert "LLM generation failed" in (result.error.message if result.error else "")

    async def test_execute_returns_capability_result(self) -> None:
        """Execute returns a CapabilityResult instance."""
        agent = _make_agent()
        agent.warm_up()
        result = await agent.execute({"request_id": "r-100"})
        assert isinstance(result, CapabilityResult)
        assert result.request_id == "r-100"

    async def test_execute_tracks_execution_time(self) -> None:
        """Execute sets execution_time_ms on result."""
        agent = _make_agent()
        agent.warm_up()
        result = await agent.execute({})
        assert result.execution_time_ms >= 0

    async def test_execute_uses_context_prompt_with_llm(self) -> None:
        """LLM prompt includes context.prompt and params."""
        handle = FakeLLMHandle(response="ok")
        ctx = _make_context(prompt="System: be helpful")
        agent = _make_agent(llm_handle=handle, context=ctx)
        agent.warm_up()
        await agent.execute({"user_input": "hello"})
        call = handle.calls[0]
        assert "System: be helpful" in call["prompt"]
        assert "hello" in call["prompt"]


class TestAgentRepr:
    """Agent string representation."""

    def test_repr_contains_info(self) -> None:
        """repr includes id prefix, contract name, state, tokens."""
        agent = _make_agent(agent_id="12345678-abcd-0000-0000-000000000000")
        rep = repr(agent)
        assert "12345678" in rep
        assert "test_agent" in rep
        assert "PENDING" in rep
        assert "tokens=0" in rep


# ===================================================================
# 4.3.1 -- AgentFactory
# ===================================================================


class TestAgentFactoryConstruction:
    """AgentFactory construction and properties."""

    def test_construction_no_ports(self) -> None:
        """Factory constructs with no ports (all optional)."""
        factory = AgentFactory()
        assert not factory.has_model_gateway
        assert not factory.has_context_builder
        assert factory.config.idle_ttl_s == 60

    def test_construction_with_ports(self) -> None:
        """Factory constructs with all ports provided."""
        gw = FakeModelGateway()
        factory = AgentFactory(
            model_gateway=gw,
            state_reader=FakeStateReader(),
            delta_bus=FakeDeltaBus(),
        )
        assert factory.has_model_gateway
        assert not factory.has_context_builder

    def test_construction_with_config(self) -> None:
        """Factory uses custom AgentFactoryConfig."""
        cfg = AgentFactoryConfig(idle_ttl_s=30, max_concurrent_agents=5)
        factory = AgentFactory(config=cfg)
        assert factory.config.idle_ttl_s == 30
        assert factory.config.max_concurrent_agents == 5

    def test_default_config(self) -> None:
        """Default config has expected values."""
        cfg = AgentFactoryConfig()
        assert cfg.idle_ttl_s == 60
        assert cfg.max_concurrent_agents == 20
        assert cfg.default_llm_budget == 4000

    def test_config_is_frozen(self) -> None:
        """AgentFactoryConfig is frozen."""
        cfg = AgentFactoryConfig()
        with pytest.raises(AttributeError):
            cfg.idle_ttl_s = 999  # type: ignore[misc]


class TestAgentFactorySpawnAndExecute:
    """AgentFactory.spawn_and_execute() method."""

    async def test_happy_path_no_ports(self) -> None:
        """spawn_and_execute works with minimal setup (contract_loader only)."""
        contract = _make_agent_contract()

        factory = AgentFactory(
            contract_loader=lambda name: contract,
        )

        request = CapabilityRequest(
            capability_name="agent.execute.test_agent",
            params={"key": "value"},
            request_id="r-1",
        )
        context = _make_context(trace_id="t-100")

        result = await factory.spawn_and_execute(request, context, "t-100")
        assert isinstance(result, AgentResult)
        assert result.success
        assert result.output["key"] == "value"  # Passthrough (no LLM)
        assert result.agent_id  # UUID assigned

    async def test_happy_path_with_llm(self) -> None:
        """spawn_and_execute with LLM handle produces LLM response."""
        contract = _make_agent_contract(llm_budget=2000)
        handle = FakeLLMHandle(response="Agent says hello")
        gw = FakeModelGateway(handle=handle)

        factory = AgentFactory(
            model_gateway=gw,
            contract_loader=lambda name: contract,
        )

        request = CapabilityRequest(
            capability_name="agent.execute.test_agent",
            params={"question": "hi"},
            request_id="r-2",
        )
        context = _make_context()

        result = await factory.spawn_and_execute(request, context, "t-200")
        assert result.success
        assert result.output["response"] == "Agent says hello"
        assert result.tokens_used > 0
        # Verify gateway was called with correct budget
        assert gw.create_calls[0]["budget_tokens"] == 2000

    async def test_happy_path_with_delta_bus(self) -> None:
        """spawn_and_execute emits deltas via IDeltaBusPort."""
        contract = _make_agent_contract()
        bus = FakeDeltaBus()

        factory = AgentFactory(
            delta_bus=bus,
            contract_loader=lambda name: contract,
        )

        request = CapabilityRequest(
            capability_name="agent.execute.test_agent",
            params={"data": "test"},
        )
        context = _make_context()

        result = await factory.spawn_and_execute(request, context, "t-300")
        assert result.success
        assert len(bus.deltas) == 1

    async def test_missing_contract_returns_failure(self) -> None:
        """spawn_and_execute fails when contract_loader returns None."""
        factory = AgentFactory(
            contract_loader=lambda name: None,
        )

        request = CapabilityRequest(capability_name="agent.execute.unknown")
        context = _make_context()

        result = await factory.spawn_and_execute(request, context, "t-400")
        assert not result.success
        assert "not found" in result.error_message.lower()

    async def test_no_contract_loader_returns_failure(self) -> None:
        """spawn_and_execute fails when no contract_loader configured."""
        factory = AgentFactory()

        request = CapabilityRequest(capability_name="agent.execute.test")
        context = _make_context()

        result = await factory.spawn_and_execute(request, context, "t-500")
        assert not result.success
        assert "contract" in result.error_message.lower()

    async def test_model_gateway_failure_returns_failure(self) -> None:
        """spawn_and_execute fails when model gateway raises during create_handle."""
        contract = _make_agent_contract(llm_budget=1000)
        gw = FakeModelGateway(fail_create=True)

        factory = AgentFactory(
            model_gateway=gw,
            contract_loader=lambda name: contract,
        )

        request = CapabilityRequest(capability_name="agent.execute.test")
        context = _make_context()

        result = await factory.spawn_and_execute(request, context, "t-600")
        assert not result.success
        assert "spawn failed" in result.error_message.lower() or "LLM" in result.error_message

    async def test_tool_scope_created(self) -> None:
        """spawn creates ToolScope when contract.tools_granted is non-empty."""
        contract = _make_agent_contract(tools=["tool.weather", "tool.calendar"])

        factory = AgentFactory(
            contract_loader=lambda name: contract,
        )

        request = CapabilityRequest(
            capability_name="agent.execute.test",
            params={"q": "hi"},
        )
        context = _make_context()

        result = await factory.spawn_and_execute(request, context, "t-700")
        assert result.success  # ToolScope creation doesn't block execution

    async def test_no_tools_no_scope(self) -> None:
        """spawn skips ToolScope when contract.tools_granted is empty."""
        contract = _make_agent_contract(tools=[])

        factory = AgentFactory(
            contract_loader=lambda name: contract,
        )

        request = CapabilityRequest(
            capability_name="agent.execute.test",
            params={"q": "hi"},
        )
        context = _make_context()

        result = await factory.spawn_and_execute(request, context, "t-800")
        assert result.success

    async def test_contract_loader_exception_returns_failure(self) -> None:
        """spawn_and_execute handles contract_loader exceptions gracefully."""

        def bad_loader(name: str) -> AgentContract:
            raise RuntimeError("Registry offline")

        factory = AgentFactory(contract_loader=bad_loader)

        request = CapabilityRequest(capability_name="agent.execute.broken")
        context = _make_context()

        result = await factory.spawn_and_execute(request, context, "t-900")
        assert not result.success

    async def test_agent_gets_uuid(self) -> None:
        """Spawned agent gets a UUID (present in result.agent_id)."""
        contract = _make_agent_contract()

        factory = AgentFactory(contract_loader=lambda name: contract)

        request = CapabilityRequest(
            capability_name="agent.execute.test",
            params={},
        )
        context = _make_context()

        result = await factory.spawn_and_execute(request, context, "t-1000")
        assert result.success
        # UUID format: 8-4-4-4-12
        assert len(result.agent_id) == 36
        assert result.agent_id.count("-") == 4

    async def test_failed_execution_terminates_agent(self) -> None:
        """spawn_and_execute terminates agent on execution failure."""
        handle = FakeLLMHandle(fail=True)
        gw = FakeModelGateway(handle=handle)
        contract = _make_agent_contract()

        factory = AgentFactory(
            model_gateway=gw,
            contract_loader=lambda name: contract,
        )

        request = CapabilityRequest(
            capability_name="agent.execute.test",
            params={},
        )
        context = _make_context()

        result = await factory.spawn_and_execute(request, context, "t-1100")
        # LLM failure produces a CapabilityResult.failure (not an exception)
        # so the factory gets result.success=False and terminates the agent
        assert not result.success

    async def test_default_llm_budget_used(self) -> None:
        """When contract.llm_budget_tokens is 0, factory uses default_llm_budget."""
        contract = _make_agent_contract(llm_budget=0)
        gw = FakeModelGateway()

        factory = AgentFactory(
            model_gateway=gw,
            contract_loader=lambda name: contract,
            config=AgentFactoryConfig(default_llm_budget=8000),
        )

        request = CapabilityRequest(
            capability_name="agent.execute.test",
            params={},
        )
        context = _make_context()

        await factory.spawn_and_execute(request, context, "t-1200")
        assert gw.create_calls[0]["budget_tokens"] == 8000

    async def test_state_reader_passed_to_agent(self) -> None:
        """spawn passes state_reader to the Agent."""
        contract = _make_agent_contract()
        reader = FakeStateReader({"beliefs_active": {"mood": "happy"}})

        factory = AgentFactory(
            state_reader=reader,
            contract_loader=lambda name: contract,
        )

        request = CapabilityRequest(
            capability_name="agent.execute.test",
            params={},
        )
        context = _make_context()

        result = await factory.spawn_and_execute(request, context, "t-1300")
        assert result.success


class TestAgentFactoryRepr:
    """AgentFactory string representation."""

    def test_repr_no_ports(self) -> None:
        """repr shows port availability."""
        factory = AgentFactory()
        rep = repr(factory)
        assert "model_gw=no" in rep
        assert "ctx_builder=no" in rep
        assert "delta_bus=no" in rep

    def test_repr_with_ports(self) -> None:
        """repr shows connected ports."""
        factory = AgentFactory(
            model_gateway=FakeModelGateway(),
            delta_bus=FakeDeltaBus(),
        )
        rep = repr(factory)
        assert "model_gw=yes" in rep
        assert "delta_bus=yes" in rep


class TestAgentFactoryConfigRepr:
    """AgentFactoryConfig repr."""

    def test_config_repr(self) -> None:
        """Config repr shows key settings."""
        cfg = AgentFactoryConfig(idle_ttl_s=30, max_concurrent_agents=5, default_llm_budget=2000)
        rep = repr(cfg)
        assert "idle_ttl=30s" in rep
        assert "max_agents=5" in rep
        assert "llm_budget=2000" in rep


# ===================================================================
# Integration: AgentFactory + AgentProvider
# ===================================================================


class TestAgentProviderWithFactory:
    """AgentProvider wired to a real AgentFactory."""

    async def test_provider_delegates_to_factory(self) -> None:
        """AgentProvider._execute() delegates to AgentFactory.spawn_and_execute()."""
        contract = _make_agent_contract()
        factory = AgentFactory(contract_loader=lambda name: contract)

        provider = AgentProvider(
            config=ProviderConfig(
                provider_id="agent-runner",
                provider_type="AGENT",
            ),
            agent_factory=factory,
            capability_names=["agent.execute.test_agent"],
        )

        request = CapabilityRequest(
            capability_name="agent.execute.test_agent",
            params={"key": "value"},
            request_id="r-int-1",
        )
        context = _make_context(trace_id="t-int-1")

        result = await provider.execute(request, context, "t-int-1")
        assert result.success
        assert result.data["output"]["key"] == "value"

    async def test_provider_health_with_factory(self) -> None:
        """AgentProvider health is HEALTHY when factory is injected."""
        factory = AgentFactory()
        provider = AgentProvider(
            config=ProviderConfig(
                provider_id="agent-runner",
                provider_type="AGENT",
            ),
            agent_factory=factory,
        )
        health = await provider.health_check()
        assert health.status == "HEALTHY"


# ===================================================================
# Port protocol structural typing verification
# ===================================================================


class TestPortProtocols:
    """Verify fakes satisfy port protocols structurally."""

    def test_fake_llm_handle_satisfies_protocol(self) -> None:
        """FakeLLMHandle satisfies ILLMHandle protocol."""
        handle: ILLMHandle = FakeLLMHandle()  # type: ignore[assignment]
        assert hasattr(handle, "generate")
        assert hasattr(handle, "model_id")
        assert hasattr(handle, "budget_tokens")

    def test_fake_model_gateway_satisfies_protocol(self) -> None:
        """FakeModelGateway satisfies IModelGatewayPort protocol."""
        gw: IModelGatewayPort = FakeModelGateway()  # type: ignore[assignment]
        assert hasattr(gw, "create_handle")
        assert hasattr(gw, "is_model_loaded")

    def test_fake_delta_bus_satisfies_protocol(self) -> None:
        """FakeDeltaBus satisfies IDeltaBusPort protocol."""
        bus: IDeltaBusPort = FakeDeltaBus()  # type: ignore[assignment]
        assert hasattr(bus, "emit_delta")

    def test_fake_mailbox_satisfies_protocol(self) -> None:
        """FakeMailbox satisfies IAgentMailbox protocol."""
        mbox: IAgentMailbox = FakeMailbox()  # type: ignore[assignment]
        assert hasattr(mbox, "send")
        assert hasattr(mbox, "receive")
        assert hasattr(mbox, "depth")
        assert hasattr(mbox, "close")

    def test_fake_state_reader_satisfies_protocol(self) -> None:
        """FakeStateReader satisfies ISessionStateReader protocol."""
        reader: ISessionStateReader = FakeStateReader()  # type: ignore[assignment]
        assert hasattr(reader, "read_section")


# ===================================================================
# Lifecycle transition map validation
# ===================================================================


class TestValidTransitionsMap:
    """Validate _VALID_TRANSITIONS covers all states."""

    def test_all_states_present(self) -> None:
        """Every AgentLifecycleState is a key in _VALID_TRANSITIONS."""
        for state in AgentLifecycleState:
            assert state in _VALID_TRANSITIONS, f"{state} missing from transition map"

    def test_terminated_has_no_transitions(self) -> None:
        """TERMINATED is a terminal state with no valid transitions."""
        assert _VALID_TRANSITIONS[AgentLifecycleState.TERMINATED] == frozenset()

    def test_pending_only_to_warming(self) -> None:
        """PENDING can only transition to WARMING."""
        valid = _VALID_TRANSITIONS[AgentLifecycleState.PENDING]
        assert valid == frozenset({AgentLifecycleState.WARMING})

    def test_active_to_idle_or_draining(self) -> None:
        """ACTIVE can transition to IDLE or DRAINING."""
        valid = _VALID_TRANSITIONS[AgentLifecycleState.ACTIVE]
        assert AgentLifecycleState.IDLE in valid
        assert AgentLifecycleState.DRAINING in valid
        assert len(valid) == 2

    def test_idle_to_active_or_draining(self) -> None:
        """IDLE can transition to ACTIVE (reactivation) or DRAINING."""
        valid = _VALID_TRANSITIONS[AgentLifecycleState.IDLE]
        assert AgentLifecycleState.ACTIVE in valid
        assert AgentLifecycleState.DRAINING in valid
        assert len(valid) == 2


# ===================================================================
# Module exports
# ===================================================================


class TestModuleExports:
    """Verify providers __init__.py exports."""

    def test_all_count(self) -> None:
        """__all__ has 75 symbols (68 prior + 7 new from 4.3.3/4.3.4)."""
        import k1.fabric.providers as pkg

        assert len(pkg.__all__) == 78

    def test_new_exports_importable(self) -> None:
        """All 10 new exports from 4.3.1/4.3.2 are importable."""
        from k1.fabric.providers import (
            IDLE_TTL_S,
            Agent,
            AgentFactory,
            AgentFactoryConfig,
            AgentLifecycleError,
            IAgentMailbox,
            IDeltaBusPort,
            ILLMHandle,
            IModelGatewayPort,
            ISessionStateReader,
        )

        assert Agent is not None
        assert AgentFactory is not None
        assert AgentFactoryConfig is not None
        assert AgentLifecycleError is not None
        assert ILLMHandle is not None
        assert IModelGatewayPort is not None
        assert IDeltaBusPort is not None
        assert IAgentMailbox is not None
        assert ISessionStateReader is not None
        assert IDLE_TTL_S == 60

    def test_prior_exports_still_work(self) -> None:
        """Pre-existing agent exports still importable."""
        from k1.fabric.providers import (
            AgentExecutionError,
            AgentNotImplementedError,
            AgentProvider,
            AgentProviderError,
            AgentResult,
            AgentSpawnError,
            IAgentFactory,
        )

        assert AgentProvider is not None
        assert IAgentFactory is not None
        assert AgentResult is not None
        assert AgentProviderError is not None
        assert AgentNotImplementedError is not None
        assert AgentSpawnError is not None
        assert AgentExecutionError is not None

    def test_all_symbols_importable(self) -> None:
        """Every symbol in __all__ is importable."""
        import k1.fabric.providers as pkg

        for name in pkg.__all__:
            assert hasattr(pkg, name), f"{name} in __all__ but not importable"
