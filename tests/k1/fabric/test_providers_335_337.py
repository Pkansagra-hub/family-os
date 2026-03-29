"""
Integration tests for Epic 3.3.5-3.3.7:

  - 3.3.5 WorkflowProvider (DAG orchestration)
  - 3.3.6 ConciergeProvider (FSM routing)
  - 3.3.7 AgentProvider (M3 stub)

Tests follow the existing pattern from test_providers_331_332.py / _333_334.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.providers.agent_provider import (
    AgentExecutionError,
    AgentNotImplementedError,
    AgentProvider,
    AgentProviderError,
    AgentResult,
    AgentSpawnError,
)
from k1.fabric.providers.base_provider import CapabilityProvider, ProviderExecutionError
from k1.fabric.providers.concierge_provider import (
    ConciergeHandlerError,
    ConciergeProvider,
    ConciergeProviderError,
    ConciergeStateNotFoundError,
    ConciergeStateRequest,
    ConciergeStateResponse,
)
from k1.fabric.providers.workflow_provider import (
    DriftSeverity,
    RunManifest,
    SchemaDrift,
    WorkflowDepthExceededError,
    WorkflowNotFoundError,
    WorkflowProvider,
    WorkflowProviderError,
    WorkflowSchemaDriftError,
    WorkflowSpec,
    WorkflowStep,
    WorkflowValidationError,
)
from k1.fabric.types import (
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
    ProviderStatus,
)

# =========================================================================
# Helpers
# =========================================================================


def _request(
    capability_name: str = "workflow.run.test",
    params: Optional[Dict[str, Any]] = None,
    request_id: str = "req-1",
    trace_id: str = "trace-1",
    session_id: str = "sess-1",
) -> CapabilityRequest:
    return CapabilityRequest(
        request_id=request_id,
        capability_name=capability_name,
        params=params or {},
        caller="test",
        trace_id=trace_id,
        session_id=session_id,
    )


def _context(trace_id: str = "trace-1") -> ExecutionContext:
    return ExecutionContext(trace_id=trace_id)


def _config(
    provider_id: str = "test-provider",
    provider_type: str = "WORKFLOW",
    max_execution_ms: int = 60000,
) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        provider_type=provider_type,
        max_execution_ms=max_execution_ms,
    )


# =========================================================================
# Test doubles -- Workflow
# =========================================================================


class FakeWorkflowRegistry:
    """Test double for IWorkflowRegistry."""

    def __init__(
        self,
        specs: Optional[Dict[str, WorkflowSpec]] = None,
        error: Optional[Exception] = None,
    ):
        self._specs = dict(specs or {})
        self._error = error

    async def load(self, workflow_name: str) -> Optional[WorkflowSpec]:
        if self._error:
            raise self._error
        return self._specs.get(workflow_name)

    async def store(self, spec: WorkflowSpec) -> None:
        self._specs[spec.name] = spec


class FakeCapabilityLookup:
    """Test double for ICapabilityLookup.

    exists() checks capability presence only (version ignored).
    Drift detection uses get_version() separately.
    """

    def __init__(
        self,
        capabilities: Optional[Dict[str, str]] = None,
    ):
        # capability_name -> version
        self._caps = dict(capabilities or {})

    def exists(self, capability_name: str, version: Optional[str] = None) -> bool:
        # Check presence only; drift detection handles version mismatch.
        return capability_name in self._caps

    def get_version(self, capability_name: str) -> Optional[str]:
        return self._caps.get(capability_name)


class FakeOrchestrator:
    """Test double for IOrchestrator."""

    def __init__(
        self,
        result: Optional[CapabilityResult] = None,
        error: Optional[Exception] = None,
    ):
        self._result = result
        self._error = error
        self.executed_manifests: List[RunManifest] = []

    async def execute_workflow(
        self,
        manifest: RunManifest,
        context: ExecutionContext,
    ) -> CapabilityResult:
        self.executed_manifests.append(manifest)
        if self._error:
            raise self._error
        return self._result or CapabilityResult.success_result(
            request_id="req-1",
            data={"workflow_result": "done"},
            provider_id="test-provider",
            trace_id=manifest.trace_id,
        )


def _workflow_spec(
    name: str = "workflow.run.test",
    steps: Optional[List[WorkflowStep]] = None,
) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id="wf-1",
        name=name,
        version="1.0.0",
        steps=steps
        or [
            WorkflowStep(
                step_id="s1",
                capability="tool.execute.weather",
                params={"city": "London"},
            ),
        ],
    )


def _workflow_provider(
    registry: Optional[FakeWorkflowRegistry] = None,
    lookup: Optional[FakeCapabilityLookup] = None,
    orchestrator: Optional[FakeOrchestrator] = None,
    capability_names: Optional[List[str]] = None,
    max_depth: int = 3,
    current_depth: int = 0,
    provider_id: str = "wf-provider",
) -> WorkflowProvider:
    return WorkflowProvider(
        _config(provider_id=provider_id, provider_type="WORKFLOW"),
        workflow_registry=registry or FakeWorkflowRegistry(),
        capability_lookup=lookup or FakeCapabilityLookup({"tool.execute.weather": "1.0.0"}),
        orchestrator=orchestrator or FakeOrchestrator(),
        capability_names=capability_names or ["workflow.run.test"],
        max_depth=max_depth,
        current_depth=current_depth,
    )


# =========================================================================
# Test doubles -- Concierge
# =========================================================================


class FakeConciergeRouter:
    """Test double for IConciergeRouter."""

    def __init__(
        self,
        responses: Optional[Dict[str, ConciergeStateResponse]] = None,
        error: Optional[Exception] = None,
        states: Optional[List[str]] = None,
    ):
        self._responses = dict(responses or {})
        self._error = error
        self._states = list(states or ["greeting", "farewell", "interrupt_check"])
        self.routed_requests: List[ConciergeStateRequest] = []

    async def route(self, request: ConciergeStateRequest) -> ConciergeStateResponse:
        self.routed_requests.append(request)
        if self._error:
            raise self._error
        if request.state_name in self._responses:
            return self._responses[request.state_name]
        return ConciergeStateResponse(
            success=True,
            data={"state": request.state_name, "handled": True},
        )

    def known_states(self) -> List[str]:
        return list(self._states)


def _concierge_provider(
    router: Optional[FakeConciergeRouter] = None,
    capability_names: Optional[List[str]] = None,
    provider_id: str = "concierge",
) -> ConciergeProvider:
    return ConciergeProvider(
        _config(provider_id=provider_id, provider_type="CONCIERGE"),
        router=router or FakeConciergeRouter(),
        capability_names=capability_names
        or [
            "concierge.state.greeting",
            "concierge.state.farewell",
        ],
    )


# =========================================================================
# Test doubles -- Agent
# =========================================================================


class FakeAgentFactory:
    """Test double for IAgentFactory."""

    def __init__(
        self,
        result: Optional[AgentResult] = None,
        error: Optional[Exception] = None,
    ):
        self._result = result
        self._error = error
        self.spawn_calls: List[CapabilityRequest] = []

    async def spawn_and_execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> AgentResult:
        self.spawn_calls.append(request)
        if self._error:
            raise self._error
        return self._result or AgentResult(
            success=True,
            output={"response": "hello"},
            agent_id="agent-123",
            tokens_used=100,
            tool_calls=2,
        )


# =========================================================================
# 3.3.5 -- WorkflowProvider data types
# =========================================================================


class TestWorkflowDataTypes:
    """Test workflow data types: WorkflowStep, WorkflowSpec, SchemaDrift, RunManifest."""

    def test_workflow_step_frozen(self) -> None:
        step = WorkflowStep(step_id="s1", capability="test")
        with pytest.raises(AttributeError):
            step.step_id = "s2"  # type: ignore[misc]

    def test_workflow_spec_defaults(self) -> None:
        spec = WorkflowSpec()
        assert spec.workflow_id == ""
        assert spec.version == "1.0.0"
        assert spec.steps == []

    def test_workflow_spec_frozen(self) -> None:
        spec = WorkflowSpec(workflow_id="wf-1")
        with pytest.raises(AttributeError):
            spec.workflow_id = "wf-2"  # type: ignore[misc]

    def test_schema_drift_defaults(self) -> None:
        drift = SchemaDrift()
        assert drift.severity == DriftSeverity.NONE.value
        assert drift.auto_filled == []

    def test_run_manifest_defaults(self) -> None:
        manifest = RunManifest()
        assert manifest.depth == 0
        assert manifest.drifts == []

    def test_drift_severity_enum(self) -> None:
        assert DriftSeverity.NONE.value == "NONE"
        assert DriftSeverity.MINOR.value == "MINOR"
        assert DriftSeverity.MAJOR.value == "MAJOR"


# =========================================================================
# 3.3.5 -- WorkflowProvider construction
# =========================================================================


class TestWorkflowProviderConstruction:

    def test_basic_construction(self) -> None:
        provider = _workflow_provider()
        assert provider.provider_id == "wf-provider"
        assert provider.capabilities() == ["workflow.run.test"]

    def test_capabilities_returns_copy(self) -> None:
        provider = _workflow_provider()
        caps = provider.capabilities()
        caps.append("extra")
        assert provider.capabilities() == ["workflow.run.test"]

    def test_satisfies_protocol(self) -> None:
        provider: CapabilityProvider = _workflow_provider()
        assert hasattr(provider, "execute")
        assert hasattr(provider, "health_check")

    def test_repr(self) -> None:
        provider = _workflow_provider()
        r = repr(provider)
        assert "WorkflowProvider" in r
        assert "wf-provider" in r


# =========================================================================
# 3.3.5 -- WorkflowProvider.execute (happy path)
# =========================================================================


class TestWorkflowProviderExecute:

    async def test_successful_workflow_execution(self) -> None:
        """Full happy path: load -> validate -> manifest -> execute."""
        spec = _workflow_spec()
        registry = FakeWorkflowRegistry({"workflow.run.test": spec})
        lookup = FakeCapabilityLookup({"tool.execute.weather": "1.0.0"})
        orch = FakeOrchestrator()

        provider = _workflow_provider(registry=registry, lookup=lookup, orchestrator=orch)
        result = await provider.execute(
            _request(capability_name="workflow.run.test"),
            _context(),
            "trace-wf-1",
        )

        assert result.success is True
        assert result.data == {"workflow_result": "done"}
        assert len(orch.executed_manifests) == 1
        manifest = orch.executed_manifests[0]
        assert manifest.workflow_id == "wf-1"
        assert manifest.trace_id == "trace-wf-1"
        assert manifest.depth == 0

    async def test_manifest_has_content_hash(self) -> None:
        spec = _workflow_spec()
        registry = FakeWorkflowRegistry({"workflow.run.test": spec})
        lookup = FakeCapabilityLookup({"tool.execute.weather": "1.0.0"})
        orch = FakeOrchestrator()

        provider = _workflow_provider(registry=registry, lookup=lookup, orchestrator=orch)
        await provider.execute(_request(), _context(), "trace-hash")

        manifest = orch.executed_manifests[0]
        assert len(manifest.content_hash) == 64  # SHA-256 hex

    async def test_manifest_steps_have_resolved_versions(self) -> None:
        spec = _workflow_spec(
            steps=[
                WorkflowStep(step_id="s1", capability="tool.execute.weather"),
            ]
        )
        registry = FakeWorkflowRegistry({"workflow.run.test": spec})
        lookup = FakeCapabilityLookup({"tool.execute.weather": "2.1.0"})
        orch = FakeOrchestrator()

        provider = _workflow_provider(registry=registry, lookup=lookup, orchestrator=orch)
        await provider.execute(_request(), _context(), "trace")

        manifest = orch.executed_manifests[0]
        assert manifest.steps[0].version == "2.1.0"

    async def test_multi_step_workflow(self) -> None:
        steps = [
            WorkflowStep(step_id="s1", capability="tool.execute.a"),
            WorkflowStep(step_id="s2", capability="tool.execute.b", deps=["s1"]),
            WorkflowStep(step_id="s3", capability="tool.execute.c", deps=["s1", "s2"]),
        ]
        spec = _workflow_spec(steps=steps)
        registry = FakeWorkflowRegistry({"workflow.run.test": spec})
        lookup = FakeCapabilityLookup(
            {
                "tool.execute.a": "1.0.0",
                "tool.execute.b": "1.0.0",
                "tool.execute.c": "1.0.0",
            }
        )
        orch = FakeOrchestrator()

        provider = _workflow_provider(registry=registry, lookup=lookup, orchestrator=orch)
        result = await provider.execute(_request(), _context(), "trace-multi")
        assert result.success is True
        assert len(orch.executed_manifests[0].steps) == 3


# =========================================================================
# 3.3.5 -- WorkflowProvider.execute (error paths)
# =========================================================================


class TestWorkflowProviderErrors:

    async def test_workflow_not_found(self) -> None:
        registry = FakeWorkflowRegistry()  # empty
        provider = _workflow_provider(registry=registry)
        result = await provider.execute(_request(), _context(), "trace")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "workflow_error"

    async def test_missing_capabilities(self) -> None:
        spec = _workflow_spec(
            steps=[
                WorkflowStep(step_id="s1", capability="tool.execute.nonexistent"),
            ]
        )
        registry = FakeWorkflowRegistry({"workflow.run.test": spec})
        lookup = FakeCapabilityLookup()  # empty

        provider = _workflow_provider(registry=registry, lookup=lookup)
        result = await provider.execute(_request(), _context(), "trace")
        assert result.success is False
        assert "missing" in (result.error.message if result.error else "").lower()

    async def test_depth_exceeded(self) -> None:
        provider = _workflow_provider(current_depth=3, max_depth=3)
        result = await provider.execute(_request(), _context(), "trace")
        assert result.success is False
        assert result.error is not None
        assert "depth" in result.error.message.lower()

    async def test_major_schema_drift(self) -> None:
        steps = [
            WorkflowStep(step_id="s1", capability="tool.execute.weather", version="1.0.0"),
        ]
        spec = _workflow_spec(steps=steps)
        registry = FakeWorkflowRegistry({"workflow.run.test": spec})
        # Current version is 2.0.0 (major drift from 1.0.0)
        lookup = FakeCapabilityLookup({"tool.execute.weather": "2.0.0"})

        provider = _workflow_provider(registry=registry, lookup=lookup)
        result = await provider.execute(_request(), _context(), "trace-drift")
        assert result.success is False
        assert result.error is not None
        assert "drift" in result.error.message.lower()

    async def test_minor_schema_drift_continues(self) -> None:
        """Minor drift (same major, different minor) does not abort."""
        steps = [
            WorkflowStep(step_id="s1", capability="tool.execute.weather", version="1.0.0"),
        ]
        spec = _workflow_spec(steps=steps)
        registry = FakeWorkflowRegistry({"workflow.run.test": spec})
        # Current version is 1.2.0 (minor drift from 1.0.0)
        lookup = FakeCapabilityLookup({"tool.execute.weather": "1.2.0"})
        orch = FakeOrchestrator()

        provider = _workflow_provider(registry=registry, lookup=lookup, orchestrator=orch)
        result = await provider.execute(_request(), _context(), "trace")
        assert result.success is True  # minor drift does NOT abort
        manifest = orch.executed_manifests[0]
        assert len(manifest.drifts) == 1
        assert manifest.drifts[0].severity == DriftSeverity.MINOR.value

    async def test_orchestrator_failure_propagates(self) -> None:
        spec = _workflow_spec()
        registry = FakeWorkflowRegistry({"workflow.run.test": spec})
        lookup = FakeCapabilityLookup({"tool.execute.weather": "1.0.0"})
        orch = FakeOrchestrator(error=RuntimeError("DAG failed"))

        provider = _workflow_provider(registry=registry, lookup=lookup, orchestrator=orch)
        result = await provider.execute(_request(), _context(), "trace")
        # BaseProvider catches unexpected exceptions
        assert result.success is False
        assert "RuntimeError" in (result.error.message if result.error else "")


# =========================================================================
# 3.3.5 -- WorkflowProvider.health_check
# =========================================================================


class TestWorkflowProviderHealthCheck:

    async def test_healthy(self) -> None:
        provider = _workflow_provider()
        health = await provider.health_check()
        assert health.status == ProviderStatus.HEALTHY.value

    async def test_unhealthy_when_registry_fails(self) -> None:
        registry = FakeWorkflowRegistry(error=ConnectionError("db down"))
        provider = _workflow_provider(registry=registry)
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNHEALTHY.value


# =========================================================================
# 3.3.5 -- Workflow exceptions
# =========================================================================


class TestWorkflowExceptions:

    def test_workflow_provider_error_hierarchy(self) -> None:
        assert issubclass(WorkflowProviderError, ProviderExecutionError)
        assert issubclass(WorkflowNotFoundError, WorkflowProviderError)
        assert issubclass(WorkflowValidationError, WorkflowProviderError)
        assert issubclass(WorkflowDepthExceededError, WorkflowProviderError)
        assert issubclass(WorkflowSchemaDriftError, WorkflowProviderError)

    def test_workflow_not_found_error(self) -> None:
        err = WorkflowNotFoundError("p1", "workflow.run.missing")
        assert err.workflow_name == "workflow.run.missing"
        assert "not found" in str(err).lower()

    def test_workflow_validation_error(self) -> None:
        err = WorkflowValidationError("p1", ["cap.a", "cap.b"])
        assert err.missing_capabilities == ["cap.a", "cap.b"]
        assert "2 missing" in str(err)

    def test_workflow_depth_exceeded_error(self) -> None:
        err = WorkflowDepthExceededError("p1", 4, 3)
        assert err.depth == 4
        assert err.max_depth == 3

    def test_workflow_schema_drift_error(self) -> None:
        drifts = [SchemaDrift(capability="cap.a", severity=DriftSeverity.MAJOR.value)]
        err = WorkflowSchemaDriftError("p1", drifts)
        assert len(err.drifts) == 1


# =========================================================================
# 3.3.6 -- ConciergeProvider data types
# =========================================================================


class TestConciergeDataTypes:

    def test_state_request_frozen(self) -> None:
        req = ConciergeStateRequest(state_name="greeting")
        with pytest.raises(AttributeError):
            req.state_name = "farewell"  # type: ignore[misc]

    def test_state_response_defaults(self) -> None:
        resp = ConciergeStateResponse()
        assert resp.success is True
        assert resp.next_state is None

    def test_state_response_frozen(self) -> None:
        resp = ConciergeStateResponse(success=True)
        with pytest.raises(AttributeError):
            resp.success = False  # type: ignore[misc]


# =========================================================================
# 3.3.6 -- ConciergeProvider construction
# =========================================================================


class TestConciergeProviderConstruction:

    def test_basic_construction(self) -> None:
        provider = _concierge_provider()
        assert provider.provider_id == "concierge"
        assert "concierge.state.greeting" in provider.capabilities()

    def test_capabilities_returns_copy(self) -> None:
        provider = _concierge_provider()
        caps = provider.capabilities()
        caps.append("extra")
        assert len(provider.capabilities()) == 2

    def test_satisfies_protocol(self) -> None:
        provider: CapabilityProvider = _concierge_provider()
        assert hasattr(provider, "execute")

    def test_repr(self) -> None:
        r = repr(_concierge_provider())
        assert "ConciergeProvider" in r
        assert "concierge" in r


# =========================================================================
# 3.3.6 -- ConciergeProvider.execute
# =========================================================================


class TestConciergeProviderExecute:

    async def test_successful_state_routing(self) -> None:
        router = FakeConciergeRouter()
        provider = _concierge_provider(router=router)
        result = await provider.execute(
            _request(capability_name="concierge.state.greeting"),
            _context(),
            "trace-c1",
        )
        assert result.success is True
        assert result.data["state"] == "greeting"
        assert result.data["handled"] is True
        assert len(router.routed_requests) == 1
        assert router.routed_requests[0].state_name == "greeting"

    async def test_state_name_extraction(self) -> None:
        """concierge.state.interrupt_check -> interrupt_check."""
        router = FakeConciergeRouter()
        provider = _concierge_provider(
            router=router,
            capability_names=["concierge.state.interrupt_check"],
        )
        await provider.execute(
            _request(capability_name="concierge.state.interrupt_check"),
            _context(),
            "trace",
        )
        assert router.routed_requests[0].state_name == "interrupt_check"

    async def test_response_with_next_state(self) -> None:
        router = FakeConciergeRouter(
            responses={
                "greeting": ConciergeStateResponse(
                    success=True,
                    data={"message": "hello"},
                    next_state="listening",
                ),
            }
        )
        provider = _concierge_provider(router=router)
        result = await provider.execute(
            _request(capability_name="concierge.state.greeting"),
            _context(),
            "trace",
        )
        assert result.success is True
        assert result.data["next_state"] == "listening"
        assert result.data["message"] == "hello"

    async def test_handler_failure_response(self) -> None:
        router = FakeConciergeRouter(
            responses={
                "farewell": ConciergeStateResponse(
                    success=False,
                    error_message="session not active",
                ),
            }
        )
        provider = _concierge_provider(router=router)
        result = await provider.execute(
            _request(capability_name="concierge.state.farewell"),
            _context(),
            "trace",
        )
        assert result.success is False
        assert "session not active" in (result.error.message if result.error else "")

    async def test_handler_exception_returns_failure(self) -> None:
        router = FakeConciergeRouter(error=RuntimeError("handler crash"))
        provider = _concierge_provider(router=router)
        result = await provider.execute(
            _request(capability_name="concierge.state.greeting"),
            _context(),
            "trace",
        )
        # ConciergeHandlerError -> caught by BaseProvider
        assert result.success is False

    async def test_session_id_passed_through(self) -> None:
        router = FakeConciergeRouter()
        provider = _concierge_provider(router=router)
        await provider.execute(
            _request(capability_name="concierge.state.greeting", session_id="sess-42"),
            _context(),
            "trace",
        )
        assert router.routed_requests[0].session_id == "sess-42"


# =========================================================================
# 3.3.6 -- ConciergeProvider.health_check
# =========================================================================


class TestConciergeProviderHealthCheck:

    async def test_healthy(self) -> None:
        provider = _concierge_provider()
        health = await provider.health_check()
        assert health.status == ProviderStatus.HEALTHY.value

    async def test_unhealthy_on_router_error(self) -> None:
        class BrokenRouter:
            async def route(self, req: ConciergeStateRequest) -> ConciergeStateResponse:
                return ConciergeStateResponse()

            def known_states(self) -> List[str]:
                raise RuntimeError("router broken")

        provider = ConciergeProvider(
            _config(provider_id="c-broken", provider_type="CONCIERGE"),
            router=BrokenRouter(),  # type: ignore[arg-type]
        )
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNHEALTHY.value


# =========================================================================
# 3.3.6 -- Concierge exceptions
# =========================================================================


class TestConciergeExceptions:

    def test_concierge_exception_hierarchy(self) -> None:
        assert issubclass(ConciergeProviderError, ProviderExecutionError)
        assert issubclass(ConciergeStateNotFoundError, ConciergeProviderError)
        assert issubclass(ConciergeHandlerError, ConciergeProviderError)

    def test_state_not_found_error(self) -> None:
        err = ConciergeStateNotFoundError("p1", "unknown_state")
        assert err.state_name == "unknown_state"
        assert "unknown_state" in str(err)

    def test_handler_error(self) -> None:
        err = ConciergeHandlerError("p1", "greeting", "null pointer")
        assert err.state_name == "greeting"
        assert err.cause == "null pointer"


# =========================================================================
# 3.3.7 -- AgentProvider data types
# =========================================================================


class TestAgentDataTypes:

    def test_agent_result_defaults(self) -> None:
        r = AgentResult()
        assert r.success is True
        assert r.tokens_used == 0
        assert r.tool_calls == 0

    def test_agent_result_frozen(self) -> None:
        r = AgentResult(agent_id="a1")
        with pytest.raises(AttributeError):
            r.agent_id = "a2"  # type: ignore[misc]


# =========================================================================
# 3.3.7 -- AgentProvider construction
# =========================================================================


class TestAgentProviderConstruction:

    def test_stub_construction(self) -> None:
        provider = AgentProvider(
            _config(provider_id="agent-stub", provider_type="AGENT"),
            capability_names=["agent.execute.writer"],
        )
        assert provider.provider_id == "agent-stub"
        assert provider.capabilities() == ["agent.execute.writer"]

    def test_with_factory_construction(self) -> None:
        factory = FakeAgentFactory()
        provider = AgentProvider(
            _config(provider_id="agent-full", provider_type="AGENT"),
            agent_factory=factory,
            capability_names=["agent.execute.writer"],
        )
        assert provider.capabilities() == ["agent.execute.writer"]

    def test_satisfies_protocol(self) -> None:
        provider: CapabilityProvider = AgentProvider(
            _config(provider_type="AGENT"),
        )
        assert hasattr(provider, "execute")

    def test_capabilities_returns_copy(self) -> None:
        provider = AgentProvider(
            _config(provider_type="AGENT"),
            capability_names=["a", "b"],
        )
        caps = provider.capabilities()
        caps.append("c")
        assert len(provider.capabilities()) == 2

    def test_repr_stub(self) -> None:
        provider = AgentProvider(
            _config(provider_id="a1", provider_type="AGENT"),
        )
        r = repr(provider)
        assert "AgentProvider" in r
        assert "stub" in r

    def test_repr_active(self) -> None:
        provider = AgentProvider(
            _config(provider_id="a2", provider_type="AGENT"),
            agent_factory=FakeAgentFactory(),
        )
        r = repr(provider)
        assert "active" in r


# =========================================================================
# 3.3.7 -- AgentProvider.execute (stub M3)
# =========================================================================


class TestAgentProviderStub:

    async def test_stub_returns_failure(self) -> None:
        """M3 stub returns not_implemented failure."""
        provider = AgentProvider(
            _config(provider_id="agent-stub", provider_type="AGENT"),
            capability_names=["agent.execute.writer"],
        )
        result = await provider.execute(
            _request(capability_name="agent.execute.writer"),
            _context(),
            "trace-stub",
        )
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "agent_error"
        assert "stub" in result.error.message.lower() or "M3" in result.error.message

    async def test_stub_health_check_returns_unknown(self) -> None:
        provider = AgentProvider(
            _config(provider_id="agent-stub", provider_type="AGENT"),
        )
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNKNOWN.value
        assert "stub" in (health.error or "").lower()


# =========================================================================
# 3.3.7 -- AgentProvider.execute (M4 path with factory)
# =========================================================================


class TestAgentProviderWithFactory:

    async def test_successful_agent_execution(self) -> None:
        factory = FakeAgentFactory(
            result=AgentResult(
                success=True,
                output={"text": "empathetic response"},
                agent_id="agent-456",
                tokens_used=250,
                tool_calls=1,
            ),
        )
        provider = AgentProvider(
            _config(provider_id="agent-full", provider_type="AGENT"),
            agent_factory=factory,
            capability_names=["agent.execute.empathy_writer"],
        )
        result = await provider.execute(
            _request(capability_name="agent.execute.empathy_writer"),
            _context(),
            "trace-agent",
        )
        assert result.success is True
        assert result.data["output"] == {"text": "empathetic response"}
        assert result.data["agent_id"] == "agent-456"
        assert result.data["tokens_used"] == 250
        assert result.data["tool_calls"] == 1

    async def test_agent_failure_result(self) -> None:
        factory = FakeAgentFactory(
            result=AgentResult(
                success=False,
                error_message="LLM quota exceeded",
            ),
        )
        provider = AgentProvider(
            _config(provider_type="AGENT"),
            agent_factory=factory,
            capability_names=["agent.execute.writer"],
        )
        result = await provider.execute(_request(), _context(), "trace")
        assert result.success is False
        assert "quota" in (result.error.message if result.error else "").lower()

    async def test_factory_exception_returns_failure(self) -> None:
        factory = FakeAgentFactory(error=RuntimeError("spawn failed"))
        provider = AgentProvider(
            _config(provider_type="AGENT"),
            agent_factory=factory,
            capability_names=["agent.execute.writer"],
        )
        result = await provider.execute(_request(), _context(), "trace")
        assert result.success is False

    async def test_health_check_with_factory(self) -> None:
        factory = FakeAgentFactory()
        provider = AgentProvider(
            _config(provider_type="AGENT"),
            agent_factory=factory,
        )
        health = await provider.health_check()
        assert health.status == ProviderStatus.HEALTHY.value


# =========================================================================
# 3.3.7 -- Agent exceptions
# =========================================================================


class TestAgentExceptions:

    def test_agent_exception_hierarchy(self) -> None:
        assert issubclass(AgentProviderError, ProviderExecutionError)
        assert issubclass(AgentNotImplementedError, AgentProviderError)
        assert issubclass(AgentSpawnError, AgentProviderError)
        assert issubclass(AgentExecutionError, AgentProviderError)

    def test_agent_not_implemented_error(self) -> None:
        err = AgentNotImplementedError("p1")
        assert "stub" in str(err).lower() or "M3" in str(err)

    def test_agent_spawn_error(self) -> None:
        err = AgentSpawnError("p1", "empathy_writer", "template not found")
        assert err.agent_template == "empathy_writer"
        assert err.cause == "template not found"

    def test_agent_execution_error(self) -> None:
        err = AgentExecutionError("p1", "agent-123", "timeout")
        assert err.agent_id == "agent-123"
        assert err.cause == "timeout"


# =========================================================================
# Wiring: ProviderFactory registration for all 3 new providers
# =========================================================================


class TestProviderFactoryWiring:

    def test_register_workflow_provider(self) -> None:
        from k1.fabric.provider_resolution.provider_factory import ProviderFactory

        factory = ProviderFactory()
        registry = FakeWorkflowRegistry()
        lookup = FakeCapabilityLookup({"tool.execute.weather": "1.0.0"})
        orch = FakeOrchestrator()

        factory.register_handler(
            "WORKFLOW",
            lambda config: WorkflowProvider(
                config,
                workflow_registry=registry,
                capability_lookup=lookup,
                orchestrator=orch,
                capability_names=["workflow.run.test"],
            ),
        )
        provider = factory.create(_config(provider_type="WORKFLOW"))
        assert isinstance(provider, WorkflowProvider)

    def test_register_concierge_provider(self) -> None:
        from k1.fabric.provider_resolution.provider_factory import ProviderFactory

        factory = ProviderFactory()
        router = FakeConciergeRouter()

        factory.register_handler(
            "CONCIERGE",
            lambda config: ConciergeProvider(
                config,
                router=router,
                capability_names=["concierge.state.greeting"],
            ),
        )
        provider = factory.create(_config(provider_type="CONCIERGE"))
        assert isinstance(provider, ConciergeProvider)

    def test_register_agent_provider_stub(self) -> None:
        from k1.fabric.provider_resolution.provider_factory import ProviderFactory

        factory = ProviderFactory()
        factory.register_handler(
            "AGENT",
            lambda config: AgentProvider(
                config,
                capability_names=["agent.execute.writer"],
            ),
        )
        provider = factory.create(_config(provider_type="AGENT"))
        assert isinstance(provider, AgentProvider)


# =========================================================================
# Module exports
# =========================================================================


class TestModuleExports:

    def test_providers_init_exports_all_new(self) -> None:
        """All 3.3.5-3.3.7 symbols are accessible from providers package."""
        import k1.fabric.providers as pkg

        for name in [
            # Workflow
            "WorkflowProvider",
            "IWorkflowRegistry",
            "IOrchestrator",
            "ICapabilityLookup",
            "WorkflowSpec",
            "WorkflowStep",
            "RunManifest",
            "SchemaDrift",
            "DriftSeverity",
            "WorkflowProviderError",
            "WorkflowNotFoundError",
            "WorkflowValidationError",
            "WorkflowDepthExceededError",
            "WorkflowSchemaDriftError",
            # Concierge
            "ConciergeProvider",
            "IConciergeRouter",
            "ConciergeStateRequest",
            "ConciergeStateResponse",
            "ConciergeProviderError",
            "ConciergeStateNotFoundError",
            "ConciergeHandlerError",
            # Agent
            "AgentProvider",
            "IAgentFactory",
            "AgentResult",
            "AgentProviderError",
            "AgentNotImplementedError",
            "AgentSpawnError",
            "AgentExecutionError",
        ]:
            assert hasattr(pkg, name), f"Missing export: {name}"

    def test_all_prior_exports_still_present(self) -> None:
        """3.3.1-3.3.4 exports still work."""
        import k1.fabric.providers as pkg

        for name in [
            "CapabilityProvider",
            "BaseProvider",
            "MCPProvider",
            "WASMProvider",
            "BridgeProvider",
        ]:
            assert hasattr(pkg, name), f"Missing prior export: {name}"
