"""
Epic 6.3.15 -- Test meta-agent creation workflow (integration).

End-to-end via FabricFactory.create_for_testing():
  (1) Register tool contracts + prompt template
  (2) DiscoverCapabilitiesHandler returns contracts
  (3) FindPromptsHandler returns matching templates
  (4) BuildAgentHandler creates agent -> success + status="registered"
  (5) Registry.lookup finds created agent
  (6) k1.fabric.agent.created.v1 event emitted
  (7) Created agent registered with lifecycle metadata
  (8) AgentResponsePayload accessible from result

Additional scenarios:
  - Ephemeral cleanup via Registry.remove_expired_agents()
  - Duplicate name rejection
  - Tool validation failure (grant non-existent tool)
  - Prompt validation failure (unknown template)

NO MOCKS. All test adapters are real implementations.

References:
  - fabric-implementation-plan.md Epic 6.3, Issue 6.3.15
  - ADR-K004 (Capability Fabric Adaptation)

Invariants verified:
  FAB-02 (contract compliance)
  FAB-03 (statelessness between agent executions)
  FAB-07 (tool scoping)
  FAB-09 (trace_id propagation through build+execute)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.core.agent_builder import (
    BUILD_AGENT_CAPABILITY_NAME,
    BUILD_AGENT_PROVIDER_ID,
    AgentComposer,
    AgentSpecValidator,
    BuildAgentHandler,
)
from k1.fabric.core.discovery_tools import (
    DISCOVER_CAPABILITIES_NAME,
    FIND_PROMPTS_NAME,
    DiscoverCapabilitiesHandler,
    FindPromptsHandler,
)
from k1.fabric.core.registry import EVENT_CAPABILITY_UNREGISTERED, CapabilityRegistry
from k1.fabric.events.event_emitter import EventEmitter
from k1.fabric.events.fabric_events import TOPIC_AGENT_CREATED
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory
from k1.fabric.policy.security_context import MetaOperationValidator
from k1.fabric.types import (
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
# Shared tool contracts
# ---------------------------------------------------------------------------

TOOL_SEND_MESSAGE = CapabilityContract(
    name="tool.execute.send_message",
    version="1.0.0",
    domain=["COMMUNICATION"],
    description="Send a message to a family member",
    capabilities=["message_send"],
    limitations=[],
    required_inputs=[
        InputSpec(name="recipient", type="STRING", description="Recipient name"),
        InputSpec(name="message", type="STRING", description="Message body"),
    ],
    output={"type": "object", "properties": {"sent": {"type": "boolean"}}},
    provider_type="MCP",
    provider_id="mcp-messaging",
    safety_band_min=SafetyBand.GREEN.value,
    availability=Availability.ONLINE.value,
)

TOOL_CHECK_VITALS = CapabilityContract(
    name="tool.read.check_vitals",
    version="1.0.0",
    domain=["HEALTH"],
    description="Read health vital signs from sensors",
    capabilities=["vitals_read"],
    limitations=["no_historical"],
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

ALL_TOOLS = [TOOL_SEND_MESSAGE, TOOL_CHECK_VITALS, TOOL_LOG_ENTRY]


# ---------------------------------------------------------------------------
# Fabric + handler wiring helper
# ---------------------------------------------------------------------------


class MetaAgentTestHarness:
    """
    Wires all Epic 4.5 components with real adapters.

    Contains:
      - Full Fabric (via FabricFactory.create_for_testing)
      - DiscoverCapabilitiesHandler (4.5.3)
      - FindPromptsHandler (4.5.3)
      - BuildAgentHandler (4.5.2)
      - AgentSpecValidator (4.5.1)
      - AgentComposer (4.5.4)
      - MetaOperationValidator (4.5.5)
      - EventEmitter (4.5.7)
      - TestPromptSystemAdapter (5.2.6)
    """

    def __init__(self) -> None:
        self.fabric: Fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )
        self.registry: CapabilityRegistry = self.fabric.registry  # type: ignore[assignment]
        self.event_port: LocalEventAdapter = self.fabric.event_port  # type: ignore[assignment]
        self.event_emitter: EventEmitter = self.fabric.event_emitter  # type: ignore[assignment]

        # Prompt system adapter (5.2.6) -- pre-loaded with test template
        self.prompt_system = TestPromptSystemAdapter()
        self.prompt_system.add_template(
            "health_summary_v1",
            "Summarize health for {patient}: {metrics}",
            variables=["patient", "metrics"],
        )

        # 4.5.1: AgentSpecValidator (uses real registry + prompt system)
        self.validator = AgentSpecValidator(
            registry=self.registry,
            prompt_system=self.prompt_system,
        )

        # 4.5.4: AgentComposer (uses real registry + prompt system)
        self.composer = AgentComposer(
            registry=self.registry,
            prompt_system=self.prompt_system,
        )

        # 4.5.5: MetaOperationValidator (uses real registry)
        self.security = MetaOperationValidator(registry=self.registry)

        # 4.5.2: BuildAgentHandler (all 5 real deps)
        self.build_handler = BuildAgentHandler(
            validator=self.validator,
            composer=self.composer,
            registry=self.registry,
            security=self.security,
            emitter=self.event_emitter,
        )

        # 4.5.3: Discovery tools (use retrieval engine from Fabric)
        retrieval_engine = self.fabric.retrieval._retrieval_engine  # type: ignore[attr-defined]
        self.discover_handler = DiscoverCapabilitiesHandler(retrieval=retrieval_engine)
        self.find_prompts_handler = FindPromptsHandler(retrieval=retrieval_engine)

    def register_tools(self) -> None:
        """Register all 3 tool contracts in the registry."""
        for tool in ALL_TOOLS:
            self.registry.register(tool)

    def clear_events(self) -> None:
        """Clear captured events for clean assertions."""
        self.event_port.clear_captured()


@pytest.fixture()
def harness() -> MetaAgentTestHarness:
    """Fully wired meta-agent test harness."""
    return MetaAgentTestHarness()


def _build_request(
    *,
    params: Optional[Dict[str, Any]] = None,
    safety_band: str = "AMBER",
    trace_id: str = "meta-trace-001",
    session_id: str = "meta-session-001",
) -> CapabilityRequest:
    """Create a build_agent CapabilityRequest."""
    if params is None:
        params = _valid_build_params()
    return CapabilityRequest(
        capability_name=BUILD_AGENT_CAPABILITY_NAME,
        params=params,
        safety_band=safety_band,
        trace_id=trace_id,
        session_id=session_id,
        caller="orchestrator",
    )


def _valid_build_params(**overrides: Any) -> Dict[str, Any]:
    """Default valid params for building an agent."""
    base: Dict[str, Any] = {
        "agent_name": "test_agent",
        "description": "Test agent for vitals checking",
        "tools_granted": ["tool.read.check_vitals", "tool.execute.log_entry"],
        "prompt_template": "health_summary_v1",
        "domain": ["HEALTH"],
    }
    base.update(overrides)
    return base


def _discover_request(
    intent: str = "health monitoring",
    domain: Optional[List[str]] = None,
    **kwargs: Any,
) -> CapabilityRequest:
    """Create a discover_capabilities CapabilityRequest."""
    return CapabilityRequest(
        capability_name=DISCOVER_CAPABILITIES_NAME,
        params={
            "intent": intent,
            "domain": domain or ["HEALTH"],
            **kwargs,
        },
        caller="planner",
    )


def _find_prompts_request(
    intent: str = "health summary",
    **kwargs: Any,
) -> CapabilityRequest:
    """Create a find_prompts CapabilityRequest."""
    return CapabilityRequest(
        capability_name=FIND_PROMPTS_NAME,
        params={"intent": intent, **kwargs},
        caller="planner",
    )


# ===================================================================
# 1. Tool registration + discovery
# ===================================================================


class TestToolRegistrationAndDiscovery:
    """Register tool contracts and verify via discovery handler."""

    def test_register_three_tools(self, harness: MetaAgentTestHarness) -> None:
        """3 tool contracts register successfully in Registry."""
        harness.register_tools()
        assert harness.registry.contains("tool.execute.send_message")
        assert harness.registry.contains("tool.read.check_vitals")
        assert harness.registry.contains("tool.execute.log_entry")

    def test_discover_returns_registered_health_tools(self, harness: MetaAgentTestHarness) -> None:
        """DiscoverCapabilitiesHandler returns registered HEALTH tools."""
        harness.register_tools()
        request = _discover_request(intent="health", domain=["HEALTH"])
        result = harness.discover_handler.execute(request)
        assert_capability_result_success(result)
        assert result.data is not None
        # Should contain at least the HEALTH-domain tool
        capabilities = result.data.get("capabilities", [])
        health_names = [
            (
                c.get("contract", {}).get("name", "")
                if isinstance(c, dict) and "contract" in c
                else c.get("name", "")
            )
            for c in capabilities
        ]
        assert "tool.read.check_vitals" in health_names

    def test_discover_returns_all_matching_fields(self, harness: MetaAgentTestHarness) -> None:
        """Discovered capabilities include required contract fields."""
        harness.register_tools()
        request = _discover_request(intent="send message", domain=["COMMUNICATION"])
        result = harness.discover_handler.execute(request)
        assert_capability_result_success(result)
        assert result.data is not None
        caps = result.data.get("capabilities", [])
        if caps:
            cap = caps[0]
            # Result is wrapped: {"contract": {...}, "score": ...}
            inner = cap.get("contract", cap) if isinstance(cap, dict) else cap
            assert "name" in inner
            assert "version" in inner or "domain" in inner

    def test_discover_missing_intent_fails(self, harness: MetaAgentTestHarness) -> None:
        """Missing intent param produces failure result."""
        harness.register_tools()
        request = CapabilityRequest(
            capability_name=DISCOVER_CAPABILITIES_NAME,
            params={"domain": ["HEALTH"]},
            caller="planner",
        )
        result = harness.discover_handler.execute(request)
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"


# ===================================================================
# 2. Prompt discovery
# ===================================================================


class TestPromptDiscovery:
    """FindPromptsHandler returns matching templates from Fabric retrieval."""

    def test_find_prompts_basic_execution(self, harness: MetaAgentTestHarness) -> None:
        """FindPromptsHandler executes without error."""
        request = _find_prompts_request(intent="health summary")
        result = harness.find_prompts_handler.execute(request)
        # May return empty if no prompt contracts are loaded via YAML,
        # but execution itself should succeed
        assert_capability_result_success(result)

    def test_find_prompts_missing_intent_fails(self, harness: MetaAgentTestHarness) -> None:
        """Missing intent param produces failure."""
        request = CapabilityRequest(
            capability_name=FIND_PROMPTS_NAME,
            params={},
            caller="planner",
        )
        result = harness.find_prompts_handler.execute(request)
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"


# ===================================================================
# 3. Build agent -- happy path
# ===================================================================


class TestBuildAgentHappyPath:
    """BuildAgentHandler creates agent successfully through full pipeline."""

    def test_build_agent_success(self, harness: MetaAgentTestHarness) -> None:
        """Build agent with valid spec -> CapabilityResult.success, status=registered."""
        harness.register_tools()
        request = _build_request()
        result = harness.build_handler.execute(request)

        assert_capability_result_success(result)
        assert result.data is not None
        assert result.data["status"] == "registered"
        assert result.data["agent_name"] == "agent.execute.test_agent"
        assert result.data["errors"] == []

    def test_build_agent_registered_in_registry(self, harness: MetaAgentTestHarness) -> None:
        """Created agent is findable via Registry.lookup()."""
        harness.register_tools()
        request = _build_request()
        harness.build_handler.execute(request)

        contract = harness.registry.lookup("agent.execute.test_agent")
        assert contract is not None
        assert getattr(contract, "provider_type", "") == "AGENT"
        assert getattr(contract, "name", "") == "agent.execute.test_agent"

    def test_build_agent_name_prefix_auto_applied(self, harness: MetaAgentTestHarness) -> None:
        """agent_name without prefix gets agent.execute. prepended."""
        harness.register_tools()
        params = _valid_build_params(agent_name="my_helper")
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_success(result)
        assert result.data is not None
        assert result.data["agent_name"] == "agent.execute.my_helper"

    def test_build_agent_with_full_prefix(self, harness: MetaAgentTestHarness) -> None:
        """agent_name already prefixed with agent.execute. is kept as-is."""
        harness.register_tools()
        params = _valid_build_params(agent_name="agent.execute.my_helper")
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_success(result)
        assert result.data is not None
        assert result.data["agent_name"] == "agent.execute.my_helper"

    def test_build_agent_trace_id_propagated(self, harness: MetaAgentTestHarness) -> None:
        """trace_id from request propagated to result (FAB-09)."""
        harness.register_tools()
        request = _build_request(trace_id="trace-fab09-check")
        result = harness.build_handler.execute(request)

        assert_capability_result_success(result)
        assert result.trace_id == "trace-fab09-check"

    def test_build_agent_provider_id(self, harness: MetaAgentTestHarness) -> None:
        """Result provider_id is build_agent_handler."""
        harness.register_tools()
        request = _build_request()
        result = harness.build_handler.execute(request)

        assert_capability_result_success(result)
        assert result.provider_id == BUILD_AGENT_PROVIDER_ID

    def test_build_agent_custom_budgets(self, harness: MetaAgentTestHarness) -> None:
        """Custom budget params accepted and agent created."""
        harness.register_tools()
        params = _valid_build_params(
            llm_budget_tokens=4096,
            max_tool_calls=5,
            max_execution_time_ms=15000,
        )
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)
        assert_capability_result_success(result)


# ===================================================================
# 4. Agent created event (4.5.7)
# ===================================================================


class TestAgentCreatedEvent:
    """Verify k1.fabric.agent.created.v1 event emission."""

    def test_agent_created_event_emitted(self, harness: MetaAgentTestHarness) -> None:
        """build_agent emits k1.fabric.agent.created.v1 event."""
        harness.register_tools()
        harness.clear_events()
        request = _build_request(trace_id="trace-event-001")
        harness.build_handler.execute(request)

        events = harness.event_port.get_captured(topic=TOPIC_AGENT_CREATED)
        assert len(events) >= 1, f"Expected agent.created event, got: {events}"

    def test_agent_created_event_payload_fields(self, harness: MetaAgentTestHarness) -> None:
        """Agent created event contains all required payload fields (4.5.7)."""
        harness.register_tools()
        harness.clear_events()
        request = _build_request(
            trace_id="trace-event-002",
            session_id="session-event-002",
        )
        harness.build_handler.execute(request)

        events = harness.event_port.get_captured(topic=TOPIC_AGENT_CREATED)
        assert len(events) >= 1
        _, payload = events[0]

        # Required fields per 4.5.7
        assert payload["agent_name"] == "agent.execute.test_agent"
        assert payload["created_by"] == "orchestrator"
        assert "tool.read.check_vitals" in payload["tools_granted"]
        assert "tool.execute.log_entry" in payload["tools_granted"]
        assert payload["domain"] == ["HEALTH"]
        assert payload["prompt_template"] == "health_summary_v1"
        assert payload["cognitive_trace_id"] == "trace-event-002"
        assert payload["session_id"] == "session-event-002"

    def test_agent_created_event_ephemeral_flag(self, harness: MetaAgentTestHarness) -> None:
        """Event payload includes ephemeral flag (default True)."""
        harness.register_tools()
        harness.clear_events()
        harness.build_handler.execute(_build_request())

        events = harness.event_port.get_captured(topic=TOPIC_AGENT_CREATED)
        _, payload = events[0]
        assert payload["ephemeral"] is True


# ===================================================================
# 5. Registry lifecycle tracking (4.5.6)
# ===================================================================


class TestRegistryLifecycleTracking:
    """Verify register_created_agent() and lifecycle metadata."""

    def test_agent_recorded_as_created(self, harness: MetaAgentTestHarness) -> None:
        """Created agent tracked via is_created_agent()."""
        harness.register_tools()
        harness.build_handler.execute(_build_request())
        assert harness.registry.is_created_agent("agent.execute.test_agent")

    def test_created_agents_list(self, harness: MetaAgentTestHarness) -> None:
        """list_created_agents() includes the newly built agent."""
        harness.register_tools()
        harness.build_handler.execute(_build_request())
        agents = harness.registry.list_created_agents()
        names = [a.name for a in agents]
        assert "agent.execute.test_agent" in names

    def test_remove_expired_session_scoped_agents(self, harness: MetaAgentTestHarness) -> None:
        """Ephemeral+session_scoped agents removed by remove_expired_agents()."""
        harness.register_tools()
        request = _build_request(session_id="session-expire-001")
        harness.build_handler.execute(request)

        # Verify agent exists
        assert harness.registry.is_created_agent("agent.execute.test_agent")

        # Expire session-scoped agents
        count, names = harness.registry.remove_expired_agents("session-expire-001")
        assert count >= 1
        assert "agent.execute.test_agent" in names

        # Agent should no longer be in created agents list
        assert not harness.registry.is_created_agent("agent.execute.test_agent")

    def test_expire_emits_unregistered_event(self, harness: MetaAgentTestHarness) -> None:
        """remove_expired_agents emits capability.unregistered event via registry."""
        harness.register_tools()
        harness.build_handler.execute(_build_request(session_id="session-expire-evt"))
        harness.clear_events()
        harness.registry.remove_expired_agents("session-expire-evt")

        events = harness.event_port.get_captured(topic=EVENT_CAPABILITY_UNREGISTERED)
        assert len(events) >= 1
        _, payload = events[0]
        assert payload["name"] == "agent.execute.test_agent"

    def test_non_session_agents_not_expired(self, harness: MetaAgentTestHarness) -> None:
        """Agent with session_scoped=False survives remove_expired_agents()."""
        harness.register_tools()
        params = _valid_build_params(
            agent_name="persistent_agent",
            session_scoped=False,
        )
        request = _build_request(params=params, session_id="session-persist")
        harness.build_handler.execute(request)

        count, _ = harness.registry.remove_expired_agents("session-persist")
        assert count == 0
        assert harness.registry.is_created_agent("agent.execute.persistent_agent")


# ===================================================================
# 6. Duplicate name rejection
# ===================================================================


class TestDuplicateNameRejection:
    """Register same agent name twice -> error."""

    def test_duplicate_agent_name_rejected(self, harness: MetaAgentTestHarness) -> None:
        """Second build with same name fails."""
        harness.register_tools()
        request1 = _build_request()
        result1 = harness.build_handler.execute(request1)
        assert_capability_result_success(result1)

        # Second attempt with same name
        request2 = _build_request(trace_id="trace-dup-002")
        result2 = harness.build_handler.execute(request2)

        # Should fail due to registry version conflict or duplicate
        assert result2.success is False
        assert result2.error is not None

    def test_different_agent_names_succeed(self, harness: MetaAgentTestHarness) -> None:
        """Two agents with different names both succeed."""
        harness.register_tools()
        params1 = _valid_build_params(agent_name="agent_alpha")
        params2 = _valid_build_params(agent_name="agent_beta")

        result1 = harness.build_handler.execute(_build_request(params=params1))
        result2 = harness.build_handler.execute(_build_request(params=params2))

        assert_capability_result_success(result1)
        assert_capability_result_success(result2)
        assert harness.registry.contains("agent.execute.agent_alpha")
        assert harness.registry.contains("agent.execute.agent_beta")


# ===================================================================
# 7. Tool validation failure (4.5.1)
# ===================================================================


class TestToolValidationFailure:
    """Grant non-existent tool -> AgentSpecValidationError."""

    def test_nonexistent_tool_rejected(self, harness: MetaAgentTestHarness) -> None:
        """tools_granted referencing unknown tool fails validation."""
        harness.register_tools()
        params = _valid_build_params(
            tools_granted=["tool.execute.nonexistent_tool"],
        )
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "validation_failed")

    def test_mix_valid_and_invalid_tools_rejected(self, harness: MetaAgentTestHarness) -> None:
        """Mix of valid + invalid tools still fails."""
        harness.register_tools()
        params = _valid_build_params(
            tools_granted=[
                "tool.read.check_vitals",  # valid
                "tool.execute.does_not_exist",  # invalid
            ],
        )
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "validation_failed")

    def test_no_agent_registered_on_validation_failure(self, harness: MetaAgentTestHarness) -> None:
        """Agent is NOT registered in registry when validation fails."""
        harness.register_tools()
        params = _valid_build_params(
            tools_granted=["tool.execute.nonexistent"],
        )
        request = _build_request(params=params)
        harness.build_handler.execute(request)

        assert not harness.registry.contains("agent.execute.test_agent")


# ===================================================================
# 8. Prompt validation failure
# ===================================================================


class TestPromptValidationFailure:
    """Unknown prompt template -> validation error."""

    def test_unknown_template_rejected(self, harness: MetaAgentTestHarness) -> None:
        """Referencing non-existent prompt_template fails validation."""
        harness.register_tools()
        params = _valid_build_params(
            prompt_template="nonexistent_prompt_v99",
        )
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)

        assert_capability_result_failure(result, "validation_failed")

    def test_no_agent_registered_on_prompt_failure(self, harness: MetaAgentTestHarness) -> None:
        """Agent NOT registered when prompt validation fails."""
        harness.register_tools()
        params = _valid_build_params(prompt_template="ghost_template")
        request = _build_request(params=params)
        harness.build_handler.execute(request)

        assert not harness.registry.contains("agent.execute.test_agent")


# ===================================================================
# 9. Input parsing failures (BuildAgentError)
# ===================================================================


class TestInputParsingFailure:
    """Missing required inputs -> build_failed error."""

    def test_missing_agent_name(self, harness: MetaAgentTestHarness) -> None:
        """Missing agent_name param -> build_failed."""
        params = _valid_build_params()
        del params["agent_name"]
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)
        assert_capability_result_failure(result, "build_failed")

    def test_missing_description(self, harness: MetaAgentTestHarness) -> None:
        """Missing description param -> build_failed."""
        params = _valid_build_params()
        del params["description"]
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)
        assert_capability_result_failure(result, "build_failed")

    def test_missing_tools_granted(self, harness: MetaAgentTestHarness) -> None:
        """Missing tools_granted param -> build_failed."""
        params = _valid_build_params()
        del params["tools_granted"]
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)
        assert_capability_result_failure(result, "build_failed")

    def test_missing_prompt_template(self, harness: MetaAgentTestHarness) -> None:
        """Missing prompt_template param -> build_failed."""
        params = _valid_build_params()
        del params["prompt_template"]
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)
        assert_capability_result_failure(result, "build_failed")

    def test_missing_domain(self, harness: MetaAgentTestHarness) -> None:
        """Missing domain param -> build_failed."""
        params = _valid_build_params()
        del params["domain"]
        request = _build_request(params=params)
        result = harness.build_handler.execute(request)
        assert_capability_result_failure(result, "build_failed")

    def test_empty_params(self, harness: MetaAgentTestHarness) -> None:
        """Completely empty params -> build_failed."""
        request = _build_request(params={})
        result = harness.build_handler.execute(request)
        assert_capability_result_failure(result, "build_failed")


# ===================================================================
# 10. Statelessness (FAB-03)
# ===================================================================


class TestStatelessness:
    """Sequential build_agent calls are independent (FAB-03)."""

    def test_sequential_builds_independent(self, harness: MetaAgentTestHarness) -> None:
        """Two sequential builds produce independent agents."""
        harness.register_tools()
        params1 = _valid_build_params(agent_name="agent_one")
        params2 = _valid_build_params(agent_name="agent_two")

        result1 = harness.build_handler.execute(_build_request(params=params1))
        result2 = harness.build_handler.execute(_build_request(params=params2))

        assert_capability_result_success(result1)
        assert_capability_result_success(result2)
        assert result1.data["agent_name"] != result2.data["agent_name"]

    def test_failure_does_not_pollute_next_success(self, harness: MetaAgentTestHarness) -> None:
        """Failed build does not affect subsequent successful build."""
        harness.register_tools()

        # First: fail (bad tools)
        bad_params = _valid_build_params(
            agent_name="bad_agent",
            tools_granted=["tool.execute.doesnt_exist"],
        )
        result_fail = harness.build_handler.execute(_build_request(params=bad_params))
        assert result_fail.success is False

        # Second: succeed
        good_params = _valid_build_params(agent_name="good_agent")
        result_ok = harness.build_handler.execute(_build_request(params=good_params))
        assert_capability_result_success(result_ok)
        assert result_ok.data["agent_name"] == "agent.execute.good_agent"


# ===================================================================
# 11. Trace ID propagation (FAB-09)
# ===================================================================


class TestTraceIdPropagation:
    """trace_id flows from request through result and events."""

    def test_trace_id_in_result(self, harness: MetaAgentTestHarness) -> None:
        """Result carries request's trace_id."""
        harness.register_tools()
        request = _build_request(trace_id="trace-fab09-result")
        result = harness.build_handler.execute(request)
        assert result.trace_id == "trace-fab09-result"

    def test_trace_id_in_event(self, harness: MetaAgentTestHarness) -> None:
        """Agent created event carries request's trace_id."""
        harness.register_tools()
        harness.clear_events()
        request = _build_request(trace_id="trace-fab09-event")
        harness.build_handler.execute(request)

        events = harness.event_port.get_captured(topic=TOPIC_AGENT_CREATED)
        assert len(events) >= 1
        _, payload = events[0]
        assert payload["cognitive_trace_id"] == "trace-fab09-event"

    def test_unique_trace_ids_per_request(self, harness: MetaAgentTestHarness) -> None:
        """Different requests have different trace_ids in events."""
        harness.register_tools()
        harness.clear_events()

        harness.build_handler.execute(
            _build_request(
                params=_valid_build_params(agent_name="agent_a"),
                trace_id="trace-a",
            )
        )
        harness.build_handler.execute(
            _build_request(
                params=_valid_build_params(agent_name="agent_b"),
                trace_id="trace-b",
            )
        )

        events = harness.event_port.get_captured(topic=TOPIC_AGENT_CREATED)
        trace_ids = {p["cognitive_trace_id"] for _, p in events}
        assert "trace-a" in trace_ids
        assert "trace-b" in trace_ids
