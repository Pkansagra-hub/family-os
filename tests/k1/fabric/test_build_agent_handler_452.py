"""
Tests for BuildAgentHandler (4.5.2) -- tool.write.build_agent MCP Tool.

Tests the 8-step execute() pipeline for dynamic agent creation:
  Step 1: Input parsing and structural validation
  Step 2: AgentSpecValidator semantic validation (4.5.1)
  Step 3: SecurityContext meta-operation policy (4.5.5)
  Step 4: AgentComposer contract composition (4.5.4)
  Step 5: Registry.register() (2.2.2)
  Step 6: Registry.register_created_agent() (4.5.6)
  Step 7: EventEmitter.emit_agent_created() (4.5.7)
  Step 8: CapabilityResult success/failure

Test infrastructure:
  Real adapters for all Protocol dependencies (NO MOCKS).
  TestAgentComposer -- builds real CapabilityContract instances
  TestSecurityGate -- configurable allow/deny with call tracking
  TestRegistryForBuild -- wraps real contains() + tracks register calls
  TestEmitterForBuild -- captures all emit_agent_created calls

References:
  - fabric-implementation-plan.md Epic 4.5, Issue 4.5.2
  - k1/contracts/tools/build_agent.yaml (contract definition)

Naming: test_build_agent_handler_452.py (issue number suffix).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import pytest

from k1.fabric.core.agent_builder import (
    ALLOWED_CONTEXT_SECTIONS,
    BUILD_AGENT_CAPABILITY_NAME,
    BUILD_AGENT_PROVIDER_ID,
    DEFAULT_LLM_BUDGET_TOKENS,
    DEFAULT_MAX_EXECUTION_TIME_MS,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_SAFETY_BAND,
    AgentSpecValidator,
    BuildAgentError,
    BuildAgentHandler,
)
from k1.fabric.types import CapabilityContract, CapabilityRequest

# ===================================================================
# Test Adapters (real behavior, NO MOCKS)
# ===================================================================


@dataclass(frozen=True)
class _SecurityGateResult:
    """Result object satisfying SecurityGateLike return contract."""

    allowed: bool = True
    reasons: List[str] = field(default_factory=list)


class TestSecurityGate:
    """
    Test adapter for SecurityGateLike protocol.

    Configurable allow/deny behavior with call tracking.
    """

    def __init__(
        self,
        *,
        allowed: bool = True,
        reasons: Optional[List[str]] = None,
    ) -> None:
        self._allowed = allowed
        self._reasons = reasons or []
        self.calls: List[Dict[str, Any]] = []

    def validate_meta_operation(
        self, request_band: str, agent_spec: Dict[str, Any]
    ) -> _SecurityGateResult:
        self.calls.append(
            {
                "request_band": request_band,
                "agent_spec": dict(agent_spec),
            }
        )
        return _SecurityGateResult(
            allowed=self._allowed,
            reasons=list(self._reasons),
        )


class TestAgentBuilder:
    """
    Test adapter for AgentBuilderInstanceLike protocol.

    Builder pattern: each method returns self for chaining.
    build() returns a real CapabilityContract.
    """

    def __init__(
        self,
        name: str,
        description: str,
        domain: List[str],
        *,
        build_error: Optional[str] = None,
    ) -> None:
        self._name = name
        self._description = description
        self._domain = list(domain)
        self._build_error = build_error
        self.tools: List[str] = []
        self.prompt: str = ""
        self.context_required: List[str] = []
        self.context_optional: Optional[List[str]] = None
        self.llm_tokens: int = 8192
        self.max_tool_calls: int = 10
        self.max_execution_ms: int = 30000
        self.safety_band: str = "GREEN"
        self.ephemeral: bool = True
        self.session_scoped: bool = True

    def add_tool(self, tool_name: str) -> "TestAgentBuilder":
        self.tools.append(tool_name)
        return self

    def set_prompt(self, template_name: str) -> "TestAgentBuilder":
        self.prompt = template_name
        return self

    def set_context(
        self,
        required: List[str],
        optional: Optional[List[str]] = None,
    ) -> "TestAgentBuilder":
        self.context_required = list(required)
        self.context_optional = list(optional) if optional else None
        return self

    def set_budget(
        self,
        llm_tokens: int = 8192,
        max_tool_calls: int = 10,
        max_execution_ms: int = 30000,
    ) -> "TestAgentBuilder":
        self.llm_tokens = llm_tokens
        self.max_tool_calls = max_tool_calls
        self.max_execution_ms = max_execution_ms
        return self

    def set_safety_band(self, band: str = "GREEN") -> "TestAgentBuilder":
        self.safety_band = band
        return self

    def set_lifecycle(
        self,
        ephemeral: bool = True,
        session_scoped: bool = True,
    ) -> "TestAgentBuilder":
        self.ephemeral = ephemeral
        self.session_scoped = session_scoped
        return self

    def build(self) -> CapabilityContract:
        if self._build_error:
            raise ValueError(self._build_error)
        return CapabilityContract(
            name=self._name,
            version="1.0.0",
            domain=self._domain,
            description=self._description,
            provider_type="AGENT",
            safety_band_min=self.safety_band,
        )


class TestAgentComposer:
    """
    Test adapter for ComposerLike protocol.

    Returns TestAgentBuilder instances that produce real CapabilityContract.
    """

    def __init__(self, *, build_error: Optional[str] = None) -> None:
        self._build_error = build_error
        self.compose_calls: List[Dict[str, Any]] = []
        self.last_builder: Optional[TestAgentBuilder] = None

    def compose_agent(
        self,
        name: str,
        description: str,
        domain: List[str],
    ) -> TestAgentBuilder:
        self.compose_calls.append(
            {
                "name": name,
                "description": description,
                "domain": domain,
            }
        )
        builder = TestAgentBuilder(
            name=name,
            description=description,
            domain=domain,
            build_error=self._build_error,
        )
        self.last_builder = builder
        return builder


class TestRegistryForBuild:
    """
    Test adapter for RegistryForBuildLike protocol.

    Pre-populated known tools for contains(). Tracks register() and
    register_created_agent() calls.
    """

    def __init__(
        self,
        *,
        known_tools: Optional[List[str]] = None,
        register_error: Optional[Exception] = None,
    ) -> None:
        self._known: Set[str] = set(known_tools) if known_tools else set()
        self._register_error = register_error
        self.registered: List[Any] = []
        self.created_agents: List[Dict[str, Any]] = []

    def contains(self, name: str) -> bool:
        return name in self._known

    def register(
        self,
        contract: Any,
        *,
        skip_validation: bool = False,
    ) -> None:
        if self._register_error:
            raise self._register_error
        self.registered.append(
            {
                "contract": contract,
                "skip_validation": skip_validation,
            }
        )
        name = getattr(contract, "name", "")
        if name:
            self._known.add(name)

    def register_created_agent(
        self,
        contract: Any,
        ephemeral: bool,
        created_by: str,
        session_scoped: bool,
    ) -> None:
        self.created_agents.append(
            {
                "contract": contract,
                "ephemeral": ephemeral,
                "created_by": created_by,
                "session_scoped": session_scoped,
            }
        )


class TestEmitterForBuild:
    """
    Test adapter for EmitterForBuildLike protocol.

    Captures all emit_agent_created calls for assertion.
    """

    def __init__(self) -> None:
        self.created_events: List[Dict[str, Any]] = []

    def emit_agent_created(
        self,
        agent_name: str,
        created_by: str,
        tools_granted: List[str],
        domain: List[str],
        prompt_template: str,
        ephemeral: bool,
        session_id: str,
        trace_id: str,
    ) -> None:
        self.created_events.append(
            {
                "agent_name": agent_name,
                "created_by": created_by,
                "tools_granted": tools_granted,
                "domain": domain,
                "prompt_template": prompt_template,
                "ephemeral": ephemeral,
                "session_id": session_id,
                "trace_id": trace_id,
            }
        )


# ===================================================================
# Test Fixtures
# ===================================================================

# Pre-registered tools for the test registry
KNOWN_TOOLS = [
    "tool.execute.send_message",
    "tool.read.check_vitals",
    "tool.execute.log_entry",
]


@pytest.fixture()
def registry() -> TestRegistryForBuild:
    """Registry with 3 pre-registered tools."""
    return TestRegistryForBuild(known_tools=KNOWN_TOOLS)


@pytest.fixture()
def security() -> TestSecurityGate:
    """Security gate that allows all operations."""
    return TestSecurityGate(allowed=True)


@pytest.fixture()
def composer() -> TestAgentComposer:
    """Composer that builds valid contracts."""
    return TestAgentComposer()


@pytest.fixture()
def emitter() -> TestEmitterForBuild:
    """Event emitter that captures calls."""
    return TestEmitterForBuild()


@pytest.fixture()
def validator(registry: TestRegistryForBuild) -> AgentSpecValidator:
    """Real AgentSpecValidator using the test registry."""
    return AgentSpecValidator(registry=registry)


@pytest.fixture()
def handler(
    validator: AgentSpecValidator,
    composer: TestAgentComposer,
    registry: TestRegistryForBuild,
    security: TestSecurityGate,
    emitter: TestEmitterForBuild,
) -> BuildAgentHandler:
    """Fully wired BuildAgentHandler with all test adapters."""
    return BuildAgentHandler(
        validator=validator,
        composer=composer,
        registry=registry,
        security=security,
        emitter=emitter,
    )


def _make_request(
    *,
    params: Optional[Dict[str, Any]] = None,
    safety_band: str = "AMBER",
    trace_id: str = "test-trace-001",
    session_id: str = "test-session-001",
    request_id: str = "test-request-001",
    caller: str = "orchestrator",
) -> CapabilityRequest:
    """Factory for CapabilityRequest with sensible defaults."""
    if params is None:
        params = _valid_params()
    return CapabilityRequest(
        capability_name=BUILD_AGENT_CAPABILITY_NAME,
        params=params,
        safety_band=safety_band,
        trace_id=trace_id,
        session_id=session_id,
        request_id=request_id,
        caller=caller,
    )


def _valid_params(**overrides: Any) -> Dict[str, Any]:
    """Create valid params for build_agent tool."""
    base = {
        "agent_name": "health_checker",
        "description": "Agent that checks health vitals",
        "tools_granted": ["tool.read.check_vitals", "tool.execute.log_entry"],
        "prompt_template": "health_summary_v1",
        "domain": ["HEALTH", "WELLNESS"],
    }
    base.update(overrides)
    return base


# ===================================================================
# Tests: BuildAgentError
# ===================================================================


class TestBuildAgentError:
    """Tests for BuildAgentError exception (4.5.2)."""

    def test_stores_errors(self) -> None:
        err = BuildAgentError(["error1", "error2"])
        assert err.errors == ["error1", "error2"]

    def test_is_exception(self) -> None:
        err = BuildAgentError(["fail"])
        assert isinstance(err, Exception)

    def test_message_format(self) -> None:
        err = BuildAgentError(["a", "b", "c"])
        assert "3 error(s)" in str(err)
        assert "a; b; c" in str(err)


# ===================================================================
# Tests: Constants
# ===================================================================


class TestBuildAgentConstants:
    """Tests for 4.5.2 constants."""

    def test_capability_name(self) -> None:
        assert BUILD_AGENT_CAPABILITY_NAME == "tool.write.build_agent"

    def test_provider_id(self) -> None:
        assert BUILD_AGENT_PROVIDER_ID == "build_agent_handler"

    def test_defaults(self) -> None:
        assert DEFAULT_LLM_BUDGET_TOKENS == 8192
        assert DEFAULT_MAX_TOOL_CALLS == 10
        assert DEFAULT_MAX_EXECUTION_TIME_MS == 30000
        assert DEFAULT_SAFETY_BAND == "GREEN"


# ===================================================================
# Tests: Happy Path (full flow)
# ===================================================================


class TestHappyPath:
    """Tests for successful agent creation through all 8 steps."""

    def test_successful_creation(self, handler: BuildAgentHandler) -> None:
        request = _make_request()
        result = handler.execute(request)
        assert result.success is True
        assert result.data is not None

    def test_success_result_data_keys(self, handler: BuildAgentHandler) -> None:
        result = handler.execute(_make_request())
        assert result.data is not None
        assert result.data["agent_name"] == "agent.execute.health_checker"
        assert result.data["status"] == "registered"
        assert result.data["errors"] == []

    def test_trace_id_propagated(self, handler: BuildAgentHandler) -> None:
        result = handler.execute(_make_request(trace_id="my-trace"))
        assert result.trace_id == "my-trace"

    def test_request_id_propagated(self, handler: BuildAgentHandler) -> None:
        result = handler.execute(_make_request(request_id="req-42"))
        assert result.request_id == "req-42"

    def test_agent_name_prefix_added(self, handler: BuildAgentHandler) -> None:
        """Bare agent_name gets 'agent.execute.' prefix."""
        result = handler.execute(_make_request())
        assert result.data is not None
        assert result.data["agent_name"] == "agent.execute.health_checker"

    def test_agent_name_prefix_preserved(self, handler: BuildAgentHandler) -> None:
        """agent_name already with prefix is not double-prefixed."""
        params = _valid_params(agent_name="agent.execute.health_checker")
        result = handler.execute(_make_request(params=params))
        assert result.data is not None
        assert result.data["agent_name"] == "agent.execute.health_checker"

    def test_duration_ms_positive(self, handler: BuildAgentHandler) -> None:
        result = handler.execute(_make_request())
        assert result.duration_ms >= 0

    def test_provider_id_set(self, handler: BuildAgentHandler) -> None:
        result = handler.execute(_make_request())
        assert result.provider_id == BUILD_AGENT_PROVIDER_ID


# ===================================================================
# Tests: Step 1 -- Input Parsing
# ===================================================================


class TestStep1InputParsing:
    """Tests for _parse_inputs (Step 1: structural validation)."""

    def test_missing_agent_name(self, handler: BuildAgentHandler) -> None:
        params = _valid_params()
        del params["agent_name"]
        result = handler.execute(_make_request(params=params))
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "build_failed"
        assert "agent_name" in result.error.message

    def test_missing_description(self, handler: BuildAgentHandler) -> None:
        params = _valid_params()
        del params["description"]
        result = handler.execute(_make_request(params=params))
        assert result.success is False
        assert "description" in result.error.message

    def test_missing_tools_granted(self, handler: BuildAgentHandler) -> None:
        params = _valid_params()
        del params["tools_granted"]
        result = handler.execute(_make_request(params=params))
        assert result.success is False
        assert "tools_granted" in result.error.message

    def test_missing_prompt_template(self, handler: BuildAgentHandler) -> None:
        params = _valid_params()
        del params["prompt_template"]
        result = handler.execute(_make_request(params=params))
        assert result.success is False
        assert "prompt_template" in result.error.message

    def test_missing_domain(self, handler: BuildAgentHandler) -> None:
        params = _valid_params()
        del params["domain"]
        result = handler.execute(_make_request(params=params))
        assert result.success is False
        assert "domain" in result.error.message

    def test_missing_multiple_fields(self, handler: BuildAgentHandler) -> None:
        result = handler.execute(_make_request(params={}))
        assert result.success is False
        assert result.error is not None
        # All 5 required fields flagged
        msg = result.error.message
        assert "agent_name" in msg
        assert "description" in msg
        assert "tools_granted" in msg
        assert "prompt_template" in msg
        assert "domain" in msg

    def test_empty_string_rejected(self, handler: BuildAgentHandler) -> None:
        params = _valid_params(agent_name="", description="")
        result = handler.execute(_make_request(params=params))
        assert result.success is False
        assert "agent_name" in result.error.message

    def test_wrong_type_rejected(self, handler: BuildAgentHandler) -> None:
        params = _valid_params(agent_name=123, domain="not_a_list")
        result = handler.execute(_make_request(params=params))
        assert result.success is False
        assert result.error.code == "build_failed"


# ===================================================================
# Tests: Step 2 -- Spec Validation
# ===================================================================


class TestStep2SpecValidation:
    """Tests for AgentSpecValidator.validate_or_raise (Step 2)."""

    def test_invalid_name_pattern_rejected(
        self,
        handler: BuildAgentHandler,
    ) -> None:
        """Agent name with uppercase is rejected by validator."""
        params = _valid_params(agent_name="INVALID_NAME")
        result = handler.execute(_make_request(params=params))
        assert result.success is False
        assert result.error.code == "validation_failed"

    def test_unknown_tools_rejected(
        self,
        handler: BuildAgentHandler,
    ) -> None:
        """Tools not in registry are rejected by validator."""
        params = _valid_params(tools_granted=["nonexistent.tool"])
        result = handler.execute(_make_request(params=params))
        assert result.success is False
        assert result.error.code == "validation_failed"
        assert "Unknown tools" in result.error.message

    def test_validation_errors_in_message(
        self,
        handler: BuildAgentHandler,
    ) -> None:
        """Validation error details propagated to result."""
        params = _valid_params(domain=[])
        result = handler.execute(_make_request(params=params))
        assert result.success is False
        assert "domain" in result.error.message.lower()

    def test_out_of_range_budget_rejected(
        self,
        handler: BuildAgentHandler,
    ) -> None:
        """Budget values outside allowed range rejected by validator."""
        params = _valid_params(llm_budget_tokens=1)
        result = handler.execute(_make_request(params=params))
        assert result.success is False
        assert result.error.code == "validation_failed"


# ===================================================================
# Tests: Step 3 -- Security Gate
# ===================================================================


class TestStep3SecurityGate:
    """Tests for SecurityContext.validate_meta_operation (Step 3)."""

    def test_security_denied(
        self,
        validator: AgentSpecValidator,
        composer: TestAgentComposer,
        registry: TestRegistryForBuild,
        emitter: TestEmitterForBuild,
    ) -> None:
        """Security gate denial produces failure result."""
        gate = TestSecurityGate(
            allowed=False,
            reasons=["band_denied: GREEN < AMBER"],
        )
        handler = BuildAgentHandler(
            validator=validator,
            composer=composer,
            registry=registry,
            security=gate,
            emitter=emitter,
        )
        result = handler.execute(_make_request())
        assert result.success is False
        assert result.error.code == "security_denied"

    def test_security_denied_error_code(
        self,
        validator: AgentSpecValidator,
        composer: TestAgentComposer,
        registry: TestRegistryForBuild,
        emitter: TestEmitterForBuild,
    ) -> None:
        gate = TestSecurityGate(allowed=False, reasons=["blocked"])
        handler = BuildAgentHandler(
            validator=validator,
            composer=composer,
            registry=registry,
            security=gate,
            emitter=emitter,
        )
        result = handler.execute(_make_request())
        assert result.error.code == "security_denied"

    def test_security_reasons_in_message(
        self,
        validator: AgentSpecValidator,
        composer: TestAgentComposer,
        registry: TestRegistryForBuild,
        emitter: TestEmitterForBuild,
    ) -> None:
        gate = TestSecurityGate(
            allowed=False,
            reasons=["reason_one", "reason_two"],
        )
        handler = BuildAgentHandler(
            validator=validator,
            composer=composer,
            registry=registry,
            security=gate,
            emitter=emitter,
        )
        result = handler.execute(_make_request())
        assert "reason_one" in result.error.message
        assert "reason_two" in result.error.message

    def test_security_gate_receives_band(
        self,
        handler: BuildAgentHandler,
        security: TestSecurityGate,
    ) -> None:
        """Security gate receives caller's safety band."""
        handler.execute(_make_request(safety_band="RED"))
        assert len(security.calls) == 1
        assert security.calls[0]["request_band"] == "RED"


# ===================================================================
# Tests: Step 4 -- Composition
# ===================================================================


class TestStep4Composition:
    """Tests for AgentComposer contract composition (Step 4)."""

    def test_composer_called_with_spec(
        self,
        handler: BuildAgentHandler,
        composer: TestAgentComposer,
    ) -> None:
        handler.execute(_make_request())
        assert len(composer.compose_calls) == 1
        call = composer.compose_calls[0]
        assert call["name"] == "agent.execute.health_checker"
        assert call["description"] == "Agent that checks health vitals"
        assert call["domain"] == ["HEALTH", "WELLNESS"]

    def test_tools_added_individually(
        self,
        handler: BuildAgentHandler,
        composer: TestAgentComposer,
    ) -> None:
        handler.execute(_make_request())
        builder = composer.last_builder
        assert builder is not None
        assert builder.tools == [
            "tool.read.check_vitals",
            "tool.execute.log_entry",
        ]

    def test_builder_budget_set(
        self,
        handler: BuildAgentHandler,
        composer: TestAgentComposer,
    ) -> None:
        params = _valid_params(
            llm_budget_tokens=4096,
            max_tool_calls=5,
            max_execution_time_ms=15000,
        )
        handler.execute(_make_request(params=params))
        builder = composer.last_builder
        assert builder is not None
        assert builder.llm_tokens == 4096
        assert builder.max_tool_calls == 5
        assert builder.max_execution_ms == 15000

    def test_compose_build_error_causes_failure(
        self,
        validator: AgentSpecValidator,
        registry: TestRegistryForBuild,
        security: TestSecurityGate,
        emitter: TestEmitterForBuild,
    ) -> None:
        """Composer build() error produces failure result."""
        bad_composer = TestAgentComposer(build_error="composition failed")
        handler = BuildAgentHandler(
            validator=validator,
            composer=bad_composer,
            registry=registry,
            security=security,
            emitter=emitter,
        )
        result = handler.execute(_make_request())
        assert result.success is False
        assert result.error.code == "internal_error"
        assert "composition failed" in result.error.message

    def test_prompt_set_on_builder(
        self,
        handler: BuildAgentHandler,
        composer: TestAgentComposer,
    ) -> None:
        handler.execute(_make_request())
        builder = composer.last_builder
        assert builder is not None
        assert builder.prompt == "health_summary_v1"


# ===================================================================
# Tests: Step 5 -- Registration
# ===================================================================


class TestStep5Registration:
    """Tests for Registry.register() (Step 5)."""

    def test_register_called(
        self,
        handler: BuildAgentHandler,
        registry: TestRegistryForBuild,
    ) -> None:
        handler.execute(_make_request())
        assert len(registry.registered) == 1

    def test_register_skip_validation_false(
        self,
        handler: BuildAgentHandler,
        registry: TestRegistryForBuild,
    ) -> None:
        handler.execute(_make_request())
        assert registry.registered[0]["skip_validation"] is False

    def test_register_error_causes_failure(
        self,
        validator: AgentSpecValidator,
        composer: TestAgentComposer,
        security: TestSecurityGate,
        emitter: TestEmitterForBuild,
    ) -> None:
        bad_registry = TestRegistryForBuild(
            known_tools=KNOWN_TOOLS,
            register_error=RuntimeError("duplicate"),
        )
        bad_validator = AgentSpecValidator(registry=bad_registry)
        handler = BuildAgentHandler(
            validator=bad_validator,
            composer=composer,
            registry=bad_registry,
            security=security,
            emitter=emitter,
        )
        result = handler.execute(_make_request())
        assert result.success is False
        assert result.error.code == "internal_error"
        assert "duplicate" in result.error.message


# ===================================================================
# Tests: Step 6 -- Created Agent Tracking
# ===================================================================


class TestStep6CreatedAgentTracking:
    """Tests for Registry.register_created_agent() (Step 6)."""

    def test_register_created_agent_called(
        self,
        handler: BuildAgentHandler,
        registry: TestRegistryForBuild,
    ) -> None:
        handler.execute(_make_request())
        assert len(registry.created_agents) == 1

    def test_created_by_is_orchestrator(
        self,
        handler: BuildAgentHandler,
        registry: TestRegistryForBuild,
    ) -> None:
        handler.execute(_make_request())
        assert registry.created_agents[0]["created_by"] == "orchestrator"

    def test_lifecycle_metadata_matches(
        self,
        handler: BuildAgentHandler,
        registry: TestRegistryForBuild,
    ) -> None:
        params = _valid_params(ephemeral=False, session_scoped=False)
        handler.execute(_make_request(params=params))
        agent = registry.created_agents[0]
        assert agent["ephemeral"] is False
        assert agent["session_scoped"] is False


# ===================================================================
# Tests: Step 7 -- Event Emission
# ===================================================================


class TestStep7EventEmission:
    """Tests for EventEmitter.emit_agent_created() (Step 7)."""

    def test_emit_agent_created_called(
        self,
        handler: BuildAgentHandler,
        emitter: TestEmitterForBuild,
    ) -> None:
        handler.execute(_make_request())
        assert len(emitter.created_events) == 1

    def test_event_payload_complete(
        self,
        handler: BuildAgentHandler,
        emitter: TestEmitterForBuild,
    ) -> None:
        handler.execute(_make_request())
        event = emitter.created_events[0]
        assert event["agent_name"] == "agent.execute.health_checker"
        assert event["created_by"] == "orchestrator"
        assert event["tools_granted"] == [
            "tool.read.check_vitals",
            "tool.execute.log_entry",
        ]
        assert event["domain"] == ["HEALTH", "WELLNESS"]
        assert event["prompt_template"] == "health_summary_v1"
        assert event["ephemeral"] is True

    def test_session_id_in_event(
        self,
        handler: BuildAgentHandler,
        emitter: TestEmitterForBuild,
    ) -> None:
        handler.execute(_make_request(session_id="sess-42"))
        assert emitter.created_events[0]["session_id"] == "sess-42"

    def test_trace_id_in_event(
        self,
        handler: BuildAgentHandler,
        emitter: TestEmitterForBuild,
    ) -> None:
        handler.execute(_make_request(trace_id="trace-99"))
        assert emitter.created_events[0]["trace_id"] == "trace-99"


# ===================================================================
# Tests: Default Values
# ===================================================================


class TestDefaultValues:
    """Tests for optional input defaults."""

    def test_default_required_context(
        self,
        handler: BuildAgentHandler,
        security: TestSecurityGate,
    ) -> None:
        """Omitted required_context defaults to all 6 sections."""
        handler.execute(_make_request())
        spec = security.calls[0]["agent_spec"]
        assert set(spec["required_context"]) == set(ALLOWED_CONTEXT_SECTIONS)

    def test_default_budgets(
        self,
        handler: BuildAgentHandler,
        security: TestSecurityGate,
    ) -> None:
        handler.execute(_make_request())
        spec = security.calls[0]["agent_spec"]
        assert spec["llm_budget_tokens"] == 8192
        assert spec["max_tool_calls"] == 10
        assert spec["max_execution_time_ms"] == 30000

    def test_default_safety_band(
        self,
        handler: BuildAgentHandler,
        security: TestSecurityGate,
    ) -> None:
        handler.execute(_make_request())
        spec = security.calls[0]["agent_spec"]
        assert spec["safety_band_min"] == "GREEN"

    def test_default_lifecycle(
        self,
        handler: BuildAgentHandler,
        security: TestSecurityGate,
    ) -> None:
        handler.execute(_make_request())
        spec = security.calls[0]["agent_spec"]
        assert spec["ephemeral"] is True
        assert spec["session_scoped"] is True

    def test_custom_optionals_override_defaults(
        self,
        handler: BuildAgentHandler,
        security: TestSecurityGate,
    ) -> None:
        params = _valid_params(
            required_context=["beliefs_active"],
            llm_budget_tokens=4096,
            safety_band_min="AMBER",
            max_tool_calls=5,
            max_execution_time_ms=15000,
            ephemeral=False,
            session_scoped=False,
        )
        handler.execute(_make_request(params=params))
        spec = security.calls[0]["agent_spec"]
        assert spec["required_context"] == ["beliefs_active"]
        assert spec["llm_budget_tokens"] == 4096
        assert spec["safety_band_min"] == "AMBER"
        assert spec["max_tool_calls"] == 5
        assert spec["max_execution_time_ms"] == 15000
        assert spec["ephemeral"] is False
        assert spec["session_scoped"] is False


# ===================================================================
# Tests: Error Handling
# ===================================================================


class TestErrorHandling:
    """Tests for exception handling in execute()."""

    def test_unexpected_exception_caught(
        self,
        validator: AgentSpecValidator,
        registry: TestRegistryForBuild,
        security: TestSecurityGate,
        emitter: TestEmitterForBuild,
    ) -> None:
        """Unexpected exception from composer is caught gracefully."""
        composer = TestAgentComposer(build_error="kaboom")
        handler = BuildAgentHandler(
            validator=validator,
            composer=composer,
            registry=registry,
            security=security,
            emitter=emitter,
        )
        result = handler.execute(_make_request())
        assert result.success is False
        assert result.error.code == "internal_error"

    def test_build_agent_error_returns_build_failed(
        self,
        handler: BuildAgentHandler,
    ) -> None:
        """BuildAgentError from Step 1 returns 'build_failed' code."""
        result = handler.execute(_make_request(params={}))
        assert result.error.code == "build_failed"

    def test_spec_validation_error_returns_validation_failed(
        self,
        handler: BuildAgentHandler,
    ) -> None:
        """AgentSpecValidationError from Step 2 returns 'validation_failed'."""
        params = _valid_params(domain=[])
        result = handler.execute(_make_request(params=params))
        assert result.error.code == "validation_failed"

    def test_no_event_on_failure(
        self,
        handler: BuildAgentHandler,
        emitter: TestEmitterForBuild,
    ) -> None:
        """No event emitted when build fails."""
        result = handler.execute(_make_request(params={}))
        assert result.success is False
        assert len(emitter.created_events) == 0

    def test_no_registration_on_security_denial(
        self,
        validator: AgentSpecValidator,
        composer: TestAgentComposer,
        registry: TestRegistryForBuild,
        emitter: TestEmitterForBuild,
    ) -> None:
        """No registry calls when security denies."""
        gate = TestSecurityGate(allowed=False, reasons=["denied"])
        handler = BuildAgentHandler(
            validator=validator,
            composer=composer,
            registry=registry,
            security=gate,
            emitter=emitter,
        )
        handler.execute(_make_request())
        assert len(registry.registered) == 0
        assert len(registry.created_agents) == 0
        assert len(emitter.created_events) == 0


# ===================================================================
# Tests: Step Ordering
# ===================================================================


class TestStepOrdering:
    """Tests that steps execute in correct order with short-circuit."""

    def test_step1_blocks_step2(self, handler: BuildAgentHandler) -> None:
        """Input parsing failure prevents spec validation."""
        result = handler.execute(_make_request(params={}))
        assert result.error.code == "build_failed"

    def test_step2_blocks_step3(
        self,
        handler: BuildAgentHandler,
        security: TestSecurityGate,
    ) -> None:
        """Spec validation failure prevents security check."""
        params = _valid_params(domain=[])
        handler.execute(_make_request(params=params))
        assert len(security.calls) == 0

    def test_step3_blocks_step4(
        self,
        validator: AgentSpecValidator,
        composer: TestAgentComposer,
        registry: TestRegistryForBuild,
        emitter: TestEmitterForBuild,
    ) -> None:
        """Security denial prevents composition."""
        gate = TestSecurityGate(allowed=False, reasons=["no"])
        handler = BuildAgentHandler(
            validator=validator,
            composer=composer,
            registry=registry,
            security=gate,
            emitter=emitter,
        )
        handler.execute(_make_request())
        assert len(composer.compose_calls) == 0


# ===================================================================
# Tests: Statelessness
# ===================================================================


class TestStatelessness:
    """Tests that handler is stateless across calls."""

    def test_independent_calls(self, handler: BuildAgentHandler) -> None:
        """Two calls produce independent results."""
        result1 = handler.execute(_make_request(request_id="r1", trace_id="t1"))
        result2 = handler.execute(_make_request(request_id="r2", trace_id="t2"))
        assert result1.request_id == "r1"
        assert result2.request_id == "r2"
        assert result1.trace_id == "t1"
        assert result2.trace_id == "t2"

    def test_failure_does_not_affect_next(
        self,
        handler: BuildAgentHandler,
    ) -> None:
        """A failed call does not prevent subsequent success."""
        fail_result = handler.execute(_make_request(params={}))
        assert fail_result.success is False

        ok_result = handler.execute(_make_request())
        assert ok_result.success is True


# ===================================================================
# Tests: Repr
# ===================================================================


class TestRepr:
    """Tests for BuildAgentHandler.__repr__."""

    def test_repr_format(self, handler: BuildAgentHandler) -> None:
        r = repr(handler)
        assert "BuildAgentHandler(" in r
        assert "validator=" in r
        assert "composer=" in r
        assert "registry=" in r
