"""
Epic 6.3.16 -- Test recursive creation prevention (meta-safety).

Exercises all 5 hard gates of MetaOperationValidator (4.5.5) through
the full BuildAgentHandler pipeline (4.5.2). Each gate produces a
CapabilityResult.failure with error_code="security_denied".

5 hard gates:
  Gate 1: Capability band -- caller < AMBER -> capability_band_denied
  Gate 2: Band escalation -- agent band > caller band -> band_escalation_denied
  Gate 3: Restricted domains -- META / SECURITY / ADMIN -> restricted_domain_denied
  Gate 4: Tool recursion -- tool.write.* in tools_granted -> tool_recursion_denied
  Gate 5: Agent depth -- provider_type=AGENT tool granted -> agent_depth_denied

Additional scenarios:
  - Multi-gate violation accumulates all reasons
  - Valid AMBER-band creation succeeds (positive control)
  - CRISIS-band caller can create RED agent (band ordering)

NO MOCKS. All test adapters are real implementations.

References:
  - fabric-implementation-plan.md Epic 6.3, Issue 6.3.16
  - ADR-K004 (Capability Fabric Adaptation)

Invariants verified:
  FAB-02 (contract compliance)
  FAB-09 (trace_id propagation through security denial)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.core.agent_builder import (
    BUILD_AGENT_CAPABILITY_NAME,
    AgentComposer,
    AgentSpecValidator,
    BuildAgentHandler,
)
from k1.fabric.events.event_emitter import EventEmitter
from k1.fabric.events.fabric_events import TOPIC_AGENT_CREATED
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory
from k1.fabric.policy.security_context import MetaOperationValidator
from k1.fabric.types import (
    AgentContract,
    Availability,
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    SafetyBand,
)
from tests.k1.fabric.helpers import (
    assert_capability_result_failure,
    assert_capability_result_success,
)

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Shared tool contracts (safely grantable read/execute tools)
# ---------------------------------------------------------------------------

TOOL_CHECK_VITALS = CapabilityContract(
    name="tool.read.check_vitals",
    version="1.0.0",
    domain=["HEALTH"],
    description="Read health vital signs from sensors",
    capabilities=["vitals_read"],
    limitations=[],
    required_inputs=[
        InputSpec(name="metric", type="STRING", description="Vital metric name"),
    ],
    output={"type": "object", "properties": {"value": {"type": "number"}}},
    provider_type="MCP",
    provider_id="mcp-health",
    safety_band_min=SafetyBand.GREEN.value,
    availability=Availability.ONLINE.value,
)

TOOL_LOG_ENTRY = CapabilityContract(
    name="tool.execute.log_entry",
    version="1.0.0",
    domain=["SYSTEM"],
    description="Write an entry to the activity log",
    capabilities=["log_write"],
    limitations=[],
    required_inputs=[
        InputSpec(name="entry", type="STRING", description="Log entry text"),
    ],
    output={"type": "object", "properties": {"logged": {"type": "boolean"}}},
    provider_type="MCP",
    provider_id="mcp-logger",
    safety_band_min=SafetyBand.GREEN.value,
    availability=Availability.ONLINE.value,
)

# A meta-tool (tool.write.*) used to trigger Gate 4 (recursion)
TOOL_WRITE_DATA = CapabilityContract(
    name="tool.write.store_data",
    version="1.0.0",
    domain=["DATA"],
    description="Write data to persistent storage",
    capabilities=["data_write"],
    limitations=[],
    required_inputs=[
        InputSpec(name="key", type="STRING", description="Storage key"),
    ],
    output={"type": "object", "properties": {"stored": {"type": "boolean"}}},
    provider_type="MCP",
    provider_id="mcp-storage",
    safety_band_min=SafetyBand.AMBER.value,
    availability=Availability.ONLINE.value,
)

# An AGENT-type contract used to trigger Gate 5 (agent depth)
AGENT_CHILD = AgentContract(
    name="agent.execute.child_agent",
    version="1.0.0",
    domain=["HELPER"],
    description="A pre-existing agent capability",
    required_inputs=[],
    output={"type": "object"},
    provider_type="AGENT",
    provider_id="child-agent-provider",
    safety_band_min=SafetyBand.AMBER.value,
    availability=Availability.ONLINE.value,
    prompt_template="child_prompt_v1",
    tools_granted=["tool.read.check_vitals"],
    llm_budget_tokens=1024,
    max_tool_calls=3,
    max_execution_time_ms=10000,
)


# ---------------------------------------------------------------------------
# Test harness (same pattern as 6.3.15)
# ---------------------------------------------------------------------------


class SafetyTestHarness:
    """
    Wires all Epic 4.5 components for security gate testing.

    Identical to MetaAgentTestHarness from 6.3.15 but focused
    on security denial paths.
    """

    def __init__(self) -> None:
        self.fabric: Fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )
        self.registry = self.fabric.registry  # type: ignore[assignment]
        self.event_port = self.fabric.event_port  # type: ignore[assignment]
        self.event_emitter: EventEmitter = self.fabric.event_emitter  # type: ignore[assignment]

        # Prompt system with test template
        self.prompt_system = TestPromptSystemAdapter()
        self.prompt_system.add_template(
            "health_summary_v1",
            "Summarize health for {patient}: {metrics}",
            variables=["patient", "metrics"],
        )
        self.prompt_system.add_template(
            "child_prompt_v1",
            "Child agent prompt: {task}",
            variables=["task"],
        )

        self.validator = AgentSpecValidator(
            registry=self.registry,
            prompt_system=self.prompt_system,
        )
        self.composer = AgentComposer(
            registry=self.registry,
            prompt_system=self.prompt_system,
        )
        self.security = MetaOperationValidator(registry=self.registry)
        self.build_handler = BuildAgentHandler(
            validator=self.validator,
            composer=self.composer,
            registry=self.registry,
            security=self.security,
            emitter=self.event_emitter,
        )

    def register_tools(self) -> None:
        """Register safe read/execute tools."""
        self.registry.register(TOOL_CHECK_VITALS)
        self.registry.register(TOOL_LOG_ENTRY)

    def register_write_tool(self) -> None:
        """Register a tool.write.* meta-tool (for gate 4 test)."""
        self.registry.register(TOOL_WRITE_DATA)

    def register_agent_tool(self) -> None:
        """Register an AGENT-type contract (for gate 5 test)."""
        self.registry.register(AGENT_CHILD, skip_validation=True)

    def clear_events(self) -> None:
        """Clear captured events."""
        self.event_port.clear_captured()


@pytest.fixture()
def harness() -> SafetyTestHarness:
    """Fully wired safety test harness."""
    return SafetyTestHarness()


# ---------------------------------------------------------------------------
# Request builders
# ---------------------------------------------------------------------------


def _build_request(
    *,
    params: Optional[Dict[str, Any]] = None,
    safety_band: str = "AMBER",
    trace_id: str = "safety-trace-001",
    session_id: str = "safety-session-001",
) -> CapabilityRequest:
    """Create a build_agent CapabilityRequest."""
    if params is None:
        params = _valid_params()
    return CapabilityRequest(
        capability_name=BUILD_AGENT_CAPABILITY_NAME,
        params=params,
        safety_band=safety_band,
        trace_id=trace_id,
        session_id=session_id,
        caller="orchestrator",
    )


def _valid_params(**overrides: Any) -> Dict[str, Any]:
    """Default valid params for building an agent (AMBER-safe)."""
    base: Dict[str, Any] = {
        "agent_name": "safety_test_agent",
        "description": "Agent created for safety gate testing",
        "tools_granted": ["tool.read.check_vitals", "tool.execute.log_entry"],
        "prompt_template": "health_summary_v1",
        "domain": ["HEALTH"],
    }
    base.update(overrides)
    return base


# ===================================================================
# 0. Positive control -- valid AMBER creation succeeds
# ===================================================================


class TestPositiveControl:
    """Baseline: valid AMBER-band creation through all 5 gates."""

    def test_amber_caller_creates_agent_successfully(self, harness: SafetyTestHarness) -> None:
        """AMBER caller with safe spec passes all 5 gates."""
        harness.register_tools()
        request = _build_request(safety_band="AMBER")
        result = harness.build_handler.execute(request)

        assert_capability_result_success(result)
        assert result.data is not None
        assert result.data["status"] == "registered"

    def test_red_caller_creates_amber_agent(self, harness: SafetyTestHarness) -> None:
        """RED caller can create AMBER agent (band >= AMBER, no escalation)."""
        harness.register_tools()
        request = _build_request(safety_band="RED")
        result = harness.build_handler.execute(request)
        assert_capability_result_success(result)

    def test_crisis_caller_creates_red_agent(self, harness: SafetyTestHarness) -> None:
        """CRISIS caller can create RED-band agent."""
        harness.register_tools()
        params = _valid_params(safety_band_min="RED")
        request = _build_request(params=params, safety_band="CRISIS")
        result = harness.build_handler.execute(request)
        assert_capability_result_success(result)


# ===================================================================
# 1. Gate 1: Capability band gate (caller < AMBER)
# ===================================================================


class TestGate1CapabilityBand:
    """GREEN caller cannot invoke build_agent (AMBER-band minimum)."""

    def test_green_caller_denied(self, harness: SafetyTestHarness) -> None:
        """GREEN caller -> security_denied with capability_band_denied."""
        harness.register_tools()
        request = _build_request(safety_band="GREEN")
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert result.error is not None
        assert "capability_band_denied" in result.error.message

    def test_green_caller_no_agent_registered(self, harness: SafetyTestHarness) -> None:
        """GREEN denial -> no agent in registry."""
        harness.register_tools()
        request = _build_request(safety_band="GREEN")
        harness.build_handler.execute(request)
        assert not harness.registry.contains("agent.execute.safety_test_agent")

    def test_green_caller_no_event_emitted(self, harness: SafetyTestHarness) -> None:
        """GREEN denial -> no agent.created event."""
        harness.register_tools()
        harness.clear_events()
        request = _build_request(safety_band="GREEN")
        harness.build_handler.execute(request)

        events = harness.event_port.get_captured(topic=TOPIC_AGENT_CREATED)
        assert len(events) == 0

    def test_green_caller_trace_id_in_failure(self, harness: SafetyTestHarness) -> None:
        """trace_id propagated even on security denial (FAB-09)."""
        harness.register_tools()
        request = _build_request(safety_band="GREEN", trace_id="trace-green-deny")
        result = harness.build_handler.execute(request)
        assert result.trace_id == "trace-green-deny"


# ===================================================================
# 2. Gate 2: Band escalation (agent band > caller band)
# ===================================================================


class TestGate2BandEscalation:
    """Agent safety_band_min cannot exceed caller band."""

    def test_amber_caller_red_spec_denied(self, harness: SafetyTestHarness) -> None:
        """AMBER caller creating RED agent -> band_escalation_denied."""
        harness.register_tools()
        params = _valid_params(safety_band_min="RED")
        request = _build_request(params=params, safety_band="AMBER")
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert result.error is not None
        assert "band_escalation_denied" in result.error.message

    def test_amber_caller_crisis_spec_denied(self, harness: SafetyTestHarness) -> None:
        """AMBER caller creating CRISIS agent -> band_escalation_denied."""
        harness.register_tools()
        params = _valid_params(safety_band_min="CRISIS")
        request = _build_request(params=params, safety_band="AMBER")
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert "band_escalation_denied" in result.error.message

    def test_red_caller_crisis_spec_denied(self, harness: SafetyTestHarness) -> None:
        """RED caller creating CRISIS agent -> band_escalation_denied."""
        harness.register_tools()
        params = _valid_params(safety_band_min="CRISIS")
        request = _build_request(params=params, safety_band="RED")
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert "band_escalation_denied" in result.error.message

    def test_same_band_allowed(self, harness: SafetyTestHarness) -> None:
        """AMBER caller creating AMBER agent -> allowed (same band)."""
        harness.register_tools()
        params = _valid_params(safety_band_min="AMBER")
        request = _build_request(params=params, safety_band="AMBER")
        result = harness.build_handler.execute(request)
        assert_capability_result_success(result)


# ===================================================================
# 3. Gate 3: Restricted domain gate (META/SECURITY/ADMIN)
# ===================================================================


class TestGate3RestrictedDomains:
    """Domains META, SECURITY, ADMIN are forbidden for created agents."""

    def test_meta_domain_denied(self, harness: SafetyTestHarness) -> None:
        """META domain -> restricted_domain_denied."""
        harness.register_tools()
        params = _valid_params(domain=["META"])
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert "restricted_domain_denied" in result.error.message

    def test_security_domain_denied(self, harness: SafetyTestHarness) -> None:
        """SECURITY domain -> restricted_domain_denied."""
        harness.register_tools()
        params = _valid_params(domain=["SECURITY"])
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert "restricted_domain_denied" in result.error.message

    def test_admin_domain_denied(self, harness: SafetyTestHarness) -> None:
        """ADMIN domain -> restricted_domain_denied."""
        harness.register_tools()
        params = _valid_params(domain=["ADMIN"])
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert "restricted_domain_denied" in result.error.message

    def test_mixed_domain_with_restricted_denied(self, harness: SafetyTestHarness) -> None:
        """Mix of valid + restricted domain -> denied."""
        harness.register_tools()
        params = _valid_params(domain=["HEALTH", "SECURITY"])
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert "restricted_domain_denied" in result.error.message

    def test_case_insensitive_domain_check(self, harness: SafetyTestHarness) -> None:
        """Lowercase 'meta' is also denied (case-insensitive check)."""
        harness.register_tools()
        params = _valid_params(domain=["meta"])
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert "restricted_domain_denied" in result.error.message


# ===================================================================
# 4. Gate 4: Tool grant recursion (tool.write.* blocked)
# ===================================================================


class TestGate4ToolRecursion:
    """tools_granted containing tool.write.* meta-tools are blocked."""

    def test_write_tool_in_grants_denied(self, harness: SafetyTestHarness) -> None:
        """tool.write.store_data in tools_granted -> tool_recursion_denied."""
        harness.register_tools()
        harness.register_write_tool()
        params = _valid_params(
            tools_granted=["tool.read.check_vitals", "tool.write.store_data"],
        )
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert "tool_recursion_denied" in result.error.message

    def test_build_agent_tool_itself_denied(self, harness: SafetyTestHarness) -> None:
        """Granting tool.write.build_agent to an agent -> tool_recursion_denied."""
        harness.register_tools()
        # Register build_agent tool itself (it's a tool.write.*)
        build_tool = CapabilityContract(
            name="tool.write.build_agent",
            version="1.0.0",
            domain=["META"],
            description="Build agent meta-capability",
            required_inputs=[],
            output={"type": "object"},
            provider_type="MCP",
            provider_id="build-agent-handler",
            safety_band_min=SafetyBand.AMBER.value,
            availability=Availability.ONLINE.value,
        )
        harness.registry.register(build_tool)
        params = _valid_params(
            tools_granted=["tool.read.check_vitals", "tool.write.build_agent"],
        )
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert "tool_recursion_denied" in result.error.message

    def test_read_and_execute_tools_allowed(self, harness: SafetyTestHarness) -> None:
        """tool.read.* and tool.execute.* are NOT blocked by gate 4."""
        harness.register_tools()
        request = _build_request()  # default uses read + execute tools
        result = harness.build_handler.execute(request)
        assert_capability_result_success(result)


# ===================================================================
# 5. Gate 5: Agent depth (provider_type=AGENT blocked)
# ===================================================================


class TestGate5AgentDepth:
    """tools_granted cannot contain provider_type=AGENT capabilities."""

    def test_agent_tool_in_grants_denied(self, harness: SafetyTestHarness) -> None:
        """Granting an AGENT capability -> agent_depth_denied."""
        harness.register_tools()
        harness.register_agent_tool()
        params = _valid_params(
            tools_granted=[
                "tool.read.check_vitals",
                "agent.execute.child_agent",
            ],
        )
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert "agent_depth_denied" in result.error.message

    def test_mcp_tools_not_affected_by_depth_gate(self, harness: SafetyTestHarness) -> None:
        """MCP tools pass gate 5 (only AGENT type blocked)."""
        harness.register_tools()
        request = _build_request()
        result = harness.build_handler.execute(request)
        assert_capability_result_success(result)


# ===================================================================
# 6. Multi-gate violations (compound failures)
# ===================================================================


class TestMultiGateViolations:
    """Specs that violate multiple gates accumulate all reasons."""

    def test_green_caller_with_restricted_domain(self, harness: SafetyTestHarness) -> None:
        """GREEN + META domain -> both gate 1 + gate 3 reasons."""
        harness.register_tools()
        params = _valid_params(domain=["META"])
        request = _build_request(params=params, safety_band="GREEN")
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        assert result.error is not None
        msg = result.error.message
        assert "capability_band_denied" in msg
        assert "restricted_domain_denied" in msg

    def test_green_caller_with_escalation_and_recursion(self, harness: SafetyTestHarness) -> None:
        """GREEN + RED spec + tool.write.* -> gates 1 + 2 + 4 reasons."""
        harness.register_tools()
        harness.register_write_tool()
        params = _valid_params(
            safety_band_min="RED",
            tools_granted=["tool.read.check_vitals", "tool.write.store_data"],
        )
        request = _build_request(params=params, safety_band="GREEN")
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        msg = result.error.message
        assert "capability_band_denied" in msg
        assert "band_escalation_denied" in msg
        assert "tool_recursion_denied" in msg

    def test_all_five_gates_violated(self, harness: SafetyTestHarness) -> None:
        """Spec violating all 5 gates -> all 5 reason strings present."""
        harness.register_tools()
        harness.register_write_tool()
        harness.register_agent_tool()
        params = _valid_params(
            domain=["SECURITY"],
            safety_band_min="CRISIS",
            tools_granted=[
                "tool.write.store_data",
                "agent.execute.child_agent",
            ],
        )
        request = _build_request(params=params, safety_band="GREEN")
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "security_denied")
        msg = result.error.message
        # All 5 gate violations
        assert "capability_band_denied" in msg
        assert "band_escalation_denied" in msg
        assert "restricted_domain_denied" in msg
        assert "tool_recursion_denied" in msg
        assert "agent_depth_denied" in msg

    def test_multi_violation_no_registration(self, harness: SafetyTestHarness) -> None:
        """Multi-gate failure -> no agent registered."""
        harness.register_tools()
        params = _valid_params(domain=["ADMIN"])
        request = _build_request(params=params, safety_band="GREEN")
        harness.build_handler.execute(request)
        assert not harness.registry.contains("agent.execute.safety_test_agent")

    def test_multi_violation_no_event(self, harness: SafetyTestHarness) -> None:
        """Multi-gate failure -> no agent.created event."""
        harness.register_tools()
        harness.clear_events()
        params = _valid_params(domain=["META"])
        request = _build_request(params=params, safety_band="GREEN")
        harness.build_handler.execute(request)

        events = harness.event_port.get_captured(topic=TOPIC_AGENT_CREATED)
        assert len(events) == 0
