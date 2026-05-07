"""
Tests for Epic 4.3.5 -- AgentProvider (full implementation).

Covers:
  - AgentProvider construction (full, stub backward compat)
  - AgentProvider._execute() with AgentFactory delegation
  - Template not found handling (AgentTemplateNotFoundError)
  - Model loading failure handling (model_loading_failure error code)
  - Tool scope violation handling (tool_scope_violation error code)
  - Execution timeout enforcement via asyncio.wait_for
  - Health check (stub, healthy, degraded)
  - Shutdown and clean resource disposal
  - Agent tracking (track_agent, untrack_agent, active_agent_count)
  - Timeout resolution (_resolve_timeout)
  - New exception classes (AgentTemplateNotFoundError, AgentTimeoutError)
  - DEFAULT_AGENT_TIMEOUT_MS constant
  - Module exports updated to 78

Test architecture:
  - All tests are integration-oriented (real objects, no mocks)
  - Fakes implement port protocols structurally
  - pytest-asyncio auto mode for async tests
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from k1.fabric.providers.agent_provider import (
    DEFAULT_AGENT_TIMEOUT_MS,
    Agent,
    AgentNotImplementedError,
    AgentPool,
    AgentProvider,
    AgentProviderError,
    AgentResult,
    AgentTemplateNotFoundError,
    AgentTimeoutError,
)
from k1.fabric.providers.base_provider import ProviderExecutionError
from k1.fabric.types import (
    AgentContract,
    AgentLifecycleState,
    CapabilityRequest,
    ExecutionContext,
    ProviderConfig,
    ProviderStatus,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeLLMHandle:
    """Fake ILLMHandle."""

    def __init__(self, model_id: str = "fake-v1", budget_tokens: int = 4000) -> None:
        self._model_id = model_id
        self._budget_tokens = budget_tokens

    async def generate(self, prompt: str, params: Dict[str, Any]) -> str:
        return "response"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def budget_tokens(self) -> int:
        return self._budget_tokens


class FakeModelGateway:
    """Fake IModelGatewayPort."""

    def __init__(self, *, fail_create: bool = False, fail_loaded: bool = False) -> None:
        self._fail_create = fail_create
        self._fail_loaded = fail_loaded

    def create_handle(
        self,
        budget_tokens: int = 4000,
        model_preference: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        trace_id: str = "",
    ) -> FakeLLMHandle:
        if self._fail_create:
            raise RuntimeError("Model creation failed")
        return FakeLLMHandle()

    async def is_model_loaded(self, model_id: str) -> bool:
        if self._fail_loaded:
            raise RuntimeError("Gateway unreachable")
        return True


class FakeDeltaBus:
    """Fake IDeltaBusPort."""

    def __init__(self) -> None:
        self.emitted: List[Dict[str, Any]] = []

    def emit_delta(
        self, agent_id: str, delta_type: str, section: str, data: Dict[str, Any]
    ) -> None:
        self.emitted.append(
            {"agent_id": agent_id, "delta_type": delta_type, "section": section, "data": data}
        )


class FakeStateReader:
    """Fake ISessionStateReader."""

    def read_section(self, section_name: str) -> Optional[Dict[str, Any]]:
        return {"key": "value"}

    def read_sections(self, names: List[str]) -> Dict[str, Any]:
        return {n: {"key": "value"} for n in names}

    def get_snapshot(self) -> Dict[str, Any]:
        return {}


class FakeAgentFactory:
    """Configurable fake for IAgentFactory protocol."""

    def __init__(
        self,
        *,
        result: Optional[AgentResult] = None,
        error: Optional[Exception] = None,
        delay_s: float = 0.0,
    ) -> None:
        self._result = result
        self._error = error
        self._delay_s = delay_s
        self.spawn_calls: List[CapabilityRequest] = []
        # Expose _model_gateway-like attribute for health checks
        self._model_gateway: Optional[FakeModelGateway] = None
        self.pool: Optional[AgentPool] = None

    async def spawn_and_execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> AgentResult:
        self.spawn_calls.append(request)
        if self._delay_s > 0:
            await asyncio.sleep(self._delay_s)
        if self._error is not None:
            raise self._error
        return self._result or AgentResult(
            success=True,
            output={"response": "hello"},
            agent_id="agent-001",
            tokens_used=100,
            tool_calls=2,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(
    provider_id: str = "agent-provider",
    provider_type: str = "AGENT",
) -> ProviderConfig:
    return ProviderConfig(provider_id=provider_id, provider_type=provider_type)


def _request(
    capability_name: str = "agent.execute.test",
    request_id: str = "req-001",
    params: Optional[Dict[str, Any]] = None,
) -> CapabilityRequest:
    return CapabilityRequest(
        capability_name=capability_name,
        request_id=request_id,
        params=params or {},
    )


def _context(trace_id: str = "trace-435") -> ExecutionContext:
    return ExecutionContext(trace_id=trace_id)


def _make_agent_contract(name: str = "test_agent") -> AgentContract:
    return AgentContract(
        name=name,
        version="1.0.0",
        domain=["test"],
        description="Test agent",
        capabilities=["agent.execute.test"],
        provider_type="AGENT",
        provider_id="agent-provider",
        tools_granted=["tool.search"],
        llm_budget_tokens=4000,
        max_execution_time_ms=30000,
    )


def _make_agent(
    agent_id: str = "agent-test-001",
    contract: Optional[AgentContract] = None,
    state: AgentLifecycleState = AgentLifecycleState.PENDING,
) -> Agent:
    c = contract or _make_agent_contract()
    agent = Agent(
        agent_id=agent_id,
        contract=c,
        context=_context(),
    )
    if state == AgentLifecycleState.ACTIVE:
        agent.warm_up()
    elif state == AgentLifecycleState.IDLE:
        agent.warm_up()
        agent.idle()
    return agent


# =========================================================================
# 4.3.5 -- New Exception Classes
# =========================================================================


class TestAgentTemplateNotFoundError:

    def test_attributes(self) -> None:
        err = AgentTemplateNotFoundError("p1", "agent.execute.missing")
        assert err.capability_name == "agent.execute.missing"
        assert "missing" in str(err)
        assert "template" in str(err).lower() or "not found" in str(err).lower()

    def test_is_agent_provider_error(self) -> None:
        assert issubclass(AgentTemplateNotFoundError, AgentProviderError)

    def test_not_retriable(self) -> None:
        err = AgentTemplateNotFoundError("p1", "x")
        assert err.retriable is False


class TestAgentTimeoutError:

    def test_attributes(self) -> None:
        err = AgentTimeoutError("p1", "agent-abc", 30000)
        assert err.agent_id == "agent-abc"
        assert err.timeout_ms == 30000
        assert "30000" in str(err)

    def test_is_agent_provider_error(self) -> None:
        assert issubclass(AgentTimeoutError, AgentProviderError)

    def test_retriable(self) -> None:
        err = AgentTimeoutError("p1", "a", 5000)
        assert err.retriable is True


class TestDefaultAgentTimeoutConstant:

    def test_value(self) -> None:
        assert DEFAULT_AGENT_TIMEOUT_MS == 30_000

    def test_positive(self) -> None:
        assert DEFAULT_AGENT_TIMEOUT_MS > 0


# =========================================================================
# 4.3.5 -- AgentProvider Construction
# =========================================================================


class TestAgentProviderConstruction435:

    def test_full_construction(self) -> None:
        factory = FakeAgentFactory()
        provider = AgentProvider(
            _config(),
            agent_factory=factory,
            capability_names=["agent.execute.writer"],
        )
        assert provider.provider_id == "agent-provider"
        assert provider.capabilities() == ["agent.execute.writer"]
        assert provider.agent_factory is factory
        assert provider.active_agent_count == 0

    def test_stub_construction_backward_compat(self) -> None:
        provider = AgentProvider(
            _config(provider_id="stub"),
            capability_names=["agent.execute.x"],
        )
        assert provider.agent_factory is None
        assert provider.capabilities() == ["agent.execute.x"]

    def test_default_timeout(self) -> None:
        provider = AgentProvider(_config())
        assert provider.default_timeout_ms == DEFAULT_AGENT_TIMEOUT_MS

    def test_custom_timeout(self) -> None:
        provider = AgentProvider(
            _config(),
            default_timeout_ms=5000,
        )
        assert provider.default_timeout_ms == 5000

    def test_capabilities_returns_copy(self) -> None:
        provider = AgentProvider(
            _config(),
            capability_names=["a", "b"],
        )
        caps = provider.capabilities()
        caps.append("c")
        assert len(provider.capabilities()) == 2

    def test_repr_stub(self) -> None:
        provider = AgentProvider(_config(provider_id="s1"))
        r = repr(provider)
        assert "AgentProvider" in r
        assert "stub" in r
        assert "tracked_agents=0" in r

    def test_repr_active(self) -> None:
        provider = AgentProvider(
            _config(provider_id="a1"),
            agent_factory=FakeAgentFactory(),
        )
        r = repr(provider)
        assert "active" in r
        assert "tracked_agents=0" in r


# =========================================================================
# 4.3.5 -- AgentProvider._execute (full path)
# =========================================================================


class TestAgentProviderExecuteSuccess:

    async def test_successful_execution(self) -> None:
        factory = FakeAgentFactory(
            result=AgentResult(
                success=True,
                output={"text": "empathetic reply"},
                agent_id="agent-456",
                tokens_used=250,
                tool_calls=1,
            ),
        )
        provider = AgentProvider(
            _config(),
            agent_factory=factory,
            capability_names=["agent.execute.empathy"],
        )
        result = await provider.execute(
            _request(capability_name="agent.execute.empathy"),
            _context(),
            "trace-ok",
        )
        assert result.success is True
        assert result.data["output"] == {"text": "empathetic reply"}
        assert result.data["agent_id"] == "agent-456"
        assert result.data["tokens_used"] == 250
        assert result.data["tool_calls"] == 1

    async def test_factory_receives_request(self) -> None:
        factory = FakeAgentFactory()
        provider = AgentProvider(
            _config(),
            agent_factory=factory,
            capability_names=["agent.execute.x"],
        )
        req = _request(capability_name="agent.execute.x", request_id="r99")
        await provider.execute(req, _context(), "t1")
        assert len(factory.spawn_calls) == 1
        assert factory.spawn_calls[0].request_id == "r99"


class TestAgentProviderExecuteStub:

    async def test_stub_returns_failure(self) -> None:
        provider = AgentProvider(
            _config(provider_id="stub"),
            capability_names=["agent.execute.x"],
        )
        result = await provider.execute(_request(), _context(), "trace")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "agent_error"

    async def test_stub_error_mentions_stub(self) -> None:
        provider = AgentProvider(_config(provider_id="stub"))
        result = await provider.execute(_request(), _context(), "t")
        assert "stub" in result.error.message.lower() or "M3" in result.error.message


# =========================================================================
# 4.3.5 -- Template Not Found
# =========================================================================


class TestAgentProviderTemplateNotFound:

    async def test_template_not_found_returns_failure(self) -> None:
        """When factory returns error mentioning 'contract not found'."""
        factory = FakeAgentFactory(
            result=AgentResult(
                success=False,
                error_message="Agent contract not found for 'agent.execute.missing'. "
                "No contract_loader configured or contract missing.",
            ),
        )
        provider = AgentProvider(
            _config(),
            agent_factory=factory,
            capability_names=["agent.execute.missing"],
        )
        result = await provider.execute(
            _request(capability_name="agent.execute.missing"),
            _context(),
            "trace",
        )
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "agent_error"
        assert (
            "template" in result.error.message.lower()
            or "not found" in result.error.message.lower()
        )

    async def test_template_not_found_not_retriable(self) -> None:
        factory = FakeAgentFactory(
            result=AgentResult(
                success=False,
                error_message="Agent contract not found for 'x'",
            ),
        )
        provider = AgentProvider(_config(), agent_factory=factory)
        result = await provider.execute(_request(), _context(), "t")
        assert result.error.retriable is False


# =========================================================================
# 4.3.5 -- Model Loading Failure
# =========================================================================


class TestAgentProviderModelFailure:

    async def test_llm_handle_failure_returns_model_loading_error(self) -> None:
        factory = FakeAgentFactory(
            result=AgentResult(
                success=False,
                error_message="Failed to spawn agent 'writer': LLM handle creation failed: timeout",
            ),
        )
        provider = AgentProvider(_config(), agent_factory=factory)
        result = await provider.execute(_request(), _context(), "t")
        assert result.success is False
        assert result.error.code == "model_loading_failure"

    async def test_model_loading_failure_is_retriable(self) -> None:
        factory = FakeAgentFactory(
            result=AgentResult(
                success=False,
                error_message="LLM handle allocation error",
            ),
        )
        provider = AgentProvider(_config(), agent_factory=factory)
        result = await provider.execute(_request(), _context(), "t")
        assert result.error.retriable is True


# =========================================================================
# 4.3.5 -- Tool Scope Violation
# =========================================================================


class TestAgentProviderToolScopeViolation:

    async def test_tool_scope_violation_returns_error(self) -> None:
        factory = FakeAgentFactory(
            result=AgentResult(
                success=False,
                error_message="ToolScope creation failed: tool 'hack' not allowed",
            ),
        )
        provider = AgentProvider(_config(), agent_factory=factory)
        result = await provider.execute(_request(), _context(), "t")
        assert result.success is False
        assert result.error.code == "tool_scope_violation"

    async def test_tool_scope_not_retriable(self) -> None:
        factory = FakeAgentFactory(
            result=AgentResult(
                success=False,
                error_message="ToolScope enforcement error",
            ),
        )
        provider = AgentProvider(_config(), agent_factory=factory)
        result = await provider.execute(_request(), _context(), "t")
        assert result.error.retriable is False


# =========================================================================
# 4.3.5 -- Execution Timeout
# =========================================================================


class TestAgentProviderTimeout:

    async def test_timeout_returns_failure(self) -> None:
        """Factory that sleeps longer than timeout."""
        factory = FakeAgentFactory(delay_s=0.5)
        provider = AgentProvider(
            _config(),
            agent_factory=factory,
            default_timeout_ms=100,  # 100ms << 500ms delay
        )
        result = await provider.execute(_request(), _context(), "t")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "agent_error"
        assert "100" in result.error.message or "deadline" in result.error.message.lower()

    async def test_timeout_is_retriable(self) -> None:
        factory = FakeAgentFactory(delay_s=0.5)
        provider = AgentProvider(
            _config(),
            agent_factory=factory,
            default_timeout_ms=50,
        )
        result = await provider.execute(_request(), _context(), "t")
        assert result.error.retriable is True

    async def test_request_level_timeout_override(self) -> None:
        """params['timeout_ms'] overrides default."""
        factory = FakeAgentFactory(delay_s=0.5)
        provider = AgentProvider(
            _config(),
            agent_factory=factory,
            default_timeout_ms=60_000,  # High default
        )
        result = await provider.execute(
            _request(params={"timeout_ms": 50}),
            _context(),
            "t",
        )
        assert result.success is False
        assert "50" in result.error.message or "deadline" in result.error.message.lower()

    async def test_no_timeout_when_within_budget(self) -> None:
        """Execution finishes within timeout."""
        factory = FakeAgentFactory(delay_s=0.0)
        provider = AgentProvider(
            _config(),
            agent_factory=factory,
            default_timeout_ms=5000,
        )
        result = await provider.execute(_request(), _context(), "t")
        assert result.success is True


# =========================================================================
# 4.3.5 -- Generic Agent Failure
# =========================================================================


class TestAgentProviderGenericFailure:

    async def test_generic_failure_result(self) -> None:
        factory = FakeAgentFactory(
            result=AgentResult(
                success=False,
                error_message="Agent ran out of memory",
            ),
        )
        provider = AgentProvider(_config(), agent_factory=factory)
        result = await provider.execute(_request(), _context(), "t")
        assert result.success is False
        assert result.error.code == "agent_execution_error"
        assert "memory" in result.error.message.lower()

    async def test_factory_exception_returns_failure(self) -> None:
        factory = FakeAgentFactory(error=RuntimeError("kaboom"))
        provider = AgentProvider(_config(), agent_factory=factory)
        result = await provider.execute(_request(), _context(), "t")
        assert result.success is False

    async def test_factory_exception_has_error_info(self) -> None:
        factory = FakeAgentFactory(error=ValueError("bad param"))
        provider = AgentProvider(_config(), agent_factory=factory)
        result = await provider.execute(_request(), _context(), "t")
        assert result.error is not None


# =========================================================================
# 4.3.5 -- Health Check
# =========================================================================


class TestAgentProviderHealthCheck:

    async def test_stub_returns_unknown(self) -> None:
        provider = AgentProvider(_config())
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNKNOWN.value
        assert (
            "stub" in (health.error or "").lower()
            or "no agent_factory" in (health.error or "").lower()
        )

    async def test_factory_present_returns_healthy(self) -> None:
        factory = FakeAgentFactory()
        provider = AgentProvider(_config(), agent_factory=factory)
        health = await provider.health_check()
        assert health.status == ProviderStatus.HEALTHY.value

    async def test_factory_with_gateway_returns_healthy(self) -> None:
        factory = FakeAgentFactory()
        factory._model_gateway = FakeModelGateway()
        provider = AgentProvider(_config(), agent_factory=factory)
        health = await provider.health_check()
        assert health.status == ProviderStatus.HEALTHY.value

    async def test_gateway_unreachable_returns_degraded(self) -> None:
        factory = FakeAgentFactory()
        factory._model_gateway = FakeModelGateway(fail_loaded=True)
        provider = AgentProvider(_config(), agent_factory=factory)
        health = await provider.health_check()
        assert health.status == ProviderStatus.DEGRADED.value
        assert "unreachable" in (health.error or "").lower()


# =========================================================================
# 4.3.5 -- Shutdown and Resource Disposal
# =========================================================================


class TestAgentProviderShutdown:

    def test_shutdown_no_agents(self) -> None:
        provider = AgentProvider(_config(), agent_factory=FakeAgentFactory())
        count = provider.shutdown()
        assert count == 0

    def test_shutdown_terminates_tracked_agents(self) -> None:
        provider = AgentProvider(_config(), agent_factory=FakeAgentFactory())
        agent = _make_agent(state=AgentLifecycleState.ACTIVE)
        provider.track_agent(agent)
        assert provider.active_agent_count == 1

        count = provider.shutdown()
        assert count == 1
        assert agent.is_terminated
        assert provider.active_agent_count == 0

    def test_shutdown_terminates_idle_agents(self) -> None:
        provider = AgentProvider(_config(), agent_factory=FakeAgentFactory())
        agent = _make_agent(state=AgentLifecycleState.IDLE)
        provider.track_agent(agent)

        count = provider.shutdown()
        assert count == 1
        assert agent.is_terminated

    def test_shutdown_multiple_agents(self) -> None:
        provider = AgentProvider(_config(), agent_factory=FakeAgentFactory())
        agents = [
            _make_agent(agent_id=f"a-{i}", state=AgentLifecycleState.ACTIVE) for i in range(5)
        ]
        for a in agents:
            provider.track_agent(a)

        count = provider.shutdown()
        assert count == 5
        assert all(a.is_terminated for a in agents)

    def test_shutdown_drains_factory_pool(self) -> None:
        pool = AgentPool()
        factory = FakeAgentFactory()
        factory.pool = pool
        provider = AgentProvider(_config(), agent_factory=factory)

        # Put an agent in pool
        agent = _make_agent(state=AgentLifecycleState.ACTIVE)
        pool.put(agent)

        provider.shutdown()
        assert pool.size() == 0

    def test_shutdown_tolerates_already_terminated(self) -> None:
        provider = AgentProvider(_config(), agent_factory=FakeAgentFactory())
        agent = _make_agent(state=AgentLifecycleState.ACTIVE)
        agent.drain()
        agent.terminate()
        provider.track_agent(agent)
        # Should not raise even though agent is already terminated
        count = provider.shutdown()
        # Already terminated agents may not increment count
        assert count >= 0


# =========================================================================
# 4.3.5 -- Agent Tracking
# =========================================================================


class TestAgentProviderTracking:

    def test_track_and_count(self) -> None:
        provider = AgentProvider(_config(), agent_factory=FakeAgentFactory())
        agent = _make_agent(state=AgentLifecycleState.ACTIVE)
        provider.track_agent(agent)
        assert provider.active_agent_count == 1

    def test_untrack(self) -> None:
        provider = AgentProvider(_config(), agent_factory=FakeAgentFactory())
        agent = _make_agent(agent_id="a1", state=AgentLifecycleState.ACTIVE)
        provider.track_agent(agent)
        provider.untrack_agent("a1")
        assert provider.active_agent_count == 0

    def test_untrack_nonexistent_no_error(self) -> None:
        provider = AgentProvider(_config(), agent_factory=FakeAgentFactory())
        provider.untrack_agent("nonexistent")
        assert provider.active_agent_count == 0

    def test_track_multiple(self) -> None:
        provider = AgentProvider(_config(), agent_factory=FakeAgentFactory())
        for i in range(3):
            provider.track_agent(_make_agent(agent_id=f"a-{i}", state=AgentLifecycleState.ACTIVE))
        assert provider.active_agent_count == 3


# =========================================================================
# 4.3.5 -- Timeout Resolution
# =========================================================================


class TestAgentProviderTimeoutResolution:

    def test_default_timeout(self) -> None:
        provider = AgentProvider(_config(), default_timeout_ms=15000)
        timeout = provider._resolve_timeout(_request())
        assert timeout == 15000

    def test_request_param_override(self) -> None:
        provider = AgentProvider(_config(), default_timeout_ms=30000)
        timeout = provider._resolve_timeout(_request(params={"timeout_ms": 5000}))
        assert timeout == 5000

    def test_request_param_zero_uses_default(self) -> None:
        provider = AgentProvider(_config(), default_timeout_ms=10000)
        timeout = provider._resolve_timeout(_request(params={"timeout_ms": 0}))
        assert timeout == 10000

    def test_request_param_negative_uses_default(self) -> None:
        provider = AgentProvider(_config(), default_timeout_ms=10000)
        timeout = provider._resolve_timeout(_request(params={"timeout_ms": -100}))
        assert timeout == 10000

    def test_request_param_string_uses_default(self) -> None:
        provider = AgentProvider(_config(), default_timeout_ms=10000)
        timeout = provider._resolve_timeout(_request(params={"timeout_ms": "fast"}))
        assert timeout == 10000

    def test_no_params_uses_default(self) -> None:
        provider = AgentProvider(_config(), default_timeout_ms=20000)
        timeout = provider._resolve_timeout(_request(params={}))
        assert timeout == 20000


# =========================================================================
# 4.3.5 -- Exception Hierarchy
# =========================================================================


class TestExceptionHierarchy435:

    def test_template_not_found_is_provider_error(self) -> None:
        assert issubclass(AgentTemplateNotFoundError, AgentProviderError)
        assert issubclass(AgentTemplateNotFoundError, ProviderExecutionError)

    def test_timeout_is_provider_error(self) -> None:
        assert issubclass(AgentTimeoutError, AgentProviderError)
        assert issubclass(AgentTimeoutError, ProviderExecutionError)

    def test_all_agent_errors_are_provider_execution_error(self) -> None:
        errors = [
            AgentTemplateNotFoundError,
            AgentTimeoutError,
            AgentNotImplementedError,
        ]
        for exc_cls in errors:
            assert issubclass(exc_cls, ProviderExecutionError)


# =========================================================================
# 4.3.5 -- Module Exports
# =========================================================================


class TestModuleExports435:

    def test_all_count(self) -> None:
        import k1.fabric.providers as pkg

        assert len(pkg.__all__) == 78

    def test_new_435_exports(self) -> None:
        import k1.fabric.providers as pkg

        new_exports = [
            "AgentTemplateNotFoundError",
            "AgentTimeoutError",
            "DEFAULT_AGENT_TIMEOUT_MS",
        ]
        for name in new_exports:
            assert name in pkg.__all__, f"{name} missing from __all__"

    def test_new_symbols_importable(self) -> None:
        from k1.fabric.providers import (
            DEFAULT_AGENT_TIMEOUT_MS,
            AgentTemplateNotFoundError,
            AgentTimeoutError,
        )

        assert DEFAULT_AGENT_TIMEOUT_MS > 0
        assert issubclass(AgentTemplateNotFoundError, AgentProviderError)
        assert issubclass(AgentTimeoutError, AgentProviderError)

    def test_all_symbols_importable(self) -> None:
        import k1.fabric.providers as pkg

        for name in pkg.__all__:
            obj = getattr(pkg, name, None)
            assert obj is not None, f"{name} not importable"

    def test_prior_exports_still_present(self) -> None:
        import k1.fabric.providers as pkg

        prior = [
            "AgentProvider",
            "AgentFactory",
            "Agent",
            "AgentPool",
            "AgentDelta",
            "DeltaEmitter",
            "AgentResult",
            "AgentSpawnError",
            "AgentExecutionError",
            "AgentNotImplementedError",
            "AgentLifecycleError",
            "AgentPoolConfig",
            "AgentPoolFullError",
            "DELTA_TOPIC_PATTERN",
            "DELTA_BATCH_WINDOW_MS",
            "IDLE_TTL_S",
        ]
        for name in prior:
            assert name in pkg.__all__, f"{name} missing from __all__"
