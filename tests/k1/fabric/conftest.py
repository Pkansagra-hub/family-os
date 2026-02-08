"""
Test infrastructure for k1.fabric -- conftest.py (Epic 6.1.1).

Provides pytest fixtures for the Capability Fabric test suite.
ALL fixtures use real adapters via FabricFactory. NO MOCKS.

Fixture tiers:
  fabric_standalone   -- FabricFactory.create_standalone() (zero-config)
  fabric_for_testing  -- FabricFactory.create_for_testing() (event capture)
  registry            -- Empty CapabilityRegistry with real validator + event port
  sample_*_contract   -- Pre-built contract dataclasses (valid against schemas)

References:
  - fabric-implementation-plan.md Milestone 6, Epic 6.1.1
  - No-Mock Testing Strategy (lines 1181-1300)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory
from k1.fabric.types import (
    AgentContract,
    Availability,
    CapabilityContract,
    InputSpec,
    PlanStep,
    PromptContract,
    SafetyBand,
    TriggerSpec,
    VariableSpec,
    WorkflowContract,
)

# ---------------------------------------------------------------------------
# Fixtures directory (YAML sample contracts)
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fabric instance fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fabric_standalone() -> Fabric:
    """
    Fully wired Fabric using FabricFactory.create_standalone().

    All test adapters, no external dependencies, no event capture.
    Suitable for unit tests that do not need event assertions.
    Uses an empty contracts directory to avoid scanning production contracts.
    """
    return FabricFactory.create_standalone(
        contracts_dir=str(FIXTURES_DIR),
    )


@pytest.fixture()
def fabric_for_testing() -> Fabric:
    """
    Fully wired Fabric using FabricFactory.create_for_testing().

    Test adapters with event capture mode enabled on LocalEventAdapter.
    Suitable for integration tests that assert on emitted events.
    Uses an empty contracts directory to avoid scanning production contracts.
    """
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
    )


# ---------------------------------------------------------------------------
# Subsystem fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> CapabilityRegistry:
    """
    Empty CapabilityRegistry with real ContractValidator and LocalEventAdapter.

    Provides a clean registry for tests that focus on registration,
    lookup, versioning, or metrics without needing the full Fabric.
    """
    validator = ContractValidator()
    event_port = LocalEventAdapter(capture_mode=True)
    return CapabilityRegistry(validator=validator, event_port=event_port)  # type: ignore[arg-type]


@pytest.fixture()
def event_adapter() -> LocalEventAdapter:
    """
    Standalone LocalEventAdapter in capture mode.

    Useful for tests that need to inspect events without a full Fabric.
    """
    return LocalEventAdapter(capture_mode=True)


# ---------------------------------------------------------------------------
# Sample contract fixtures (pre-built dataclasses)
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_tool_contract() -> CapabilityContract:
    """
    Sample tool contract: restaurant_booking (MCP, FOOD domain, GREEN).

    A realistic tool contract for booking restaurant reservations.
    Valid against tool_contract.schema.json.
    """
    return CapabilityContract(
        name="tool.execute.restaurant_booking",
        version="1.0.0",
        domain=["FOOD", "SOCIAL"],
        description="Book a restaurant reservation via OpenTable integration",
        capabilities=["restaurant_search", "reservation_create", "reservation_cancel"],
        limitations=["no_international", "no_same_day_cancellation"],
        required_inputs=[
            InputSpec(name="restaurant_name", type="STRING", description="Name of the restaurant"),
            InputSpec(name="date", type="DATE", description="Reservation date (YYYY-MM-DD)"),
            InputSpec(name="party_size", type="NUMBER", description="Number of guests"),
        ],
        optional_inputs=[
            InputSpec(name="time_preference", type="STRING", description="Preferred time slot"),
        ],
        required_context=["beliefs_active.entities"],
        optional_context=["beliefs_active.preferences"],
        output={
            "type": "object",
            "properties": {"confirmation_id": {"type": "string"}, "status": {"type": "string"}},
            "required": ["confirmation_id", "status"],
        },
        provider_type="MCP",
        provider_id="mcp-opentable",
        provider_endpoint="mcp://local/opentable",
        safety_band_min=SafetyBand.GREEN.value,
        cost_per_call=0.05,
        avg_latency_ms=200,
        max_latency_ms=2000,
        availability=Availability.ONLINE.value,
    )


@pytest.fixture()
def sample_tool_contract_weather() -> CapabilityContract:
    """
    Sample tool contract: weather_api (WASM, WEATHER domain, GREEN).

    A realistic tool contract for weather forecasting.
    Valid against tool_contract.schema.json.
    """
    return CapabilityContract(
        name="tool.read.weather_api",
        version="1.2.0",
        domain=["WEATHER", "PLANNING"],
        description="Get weather forecast for a location using OpenWeatherMap",
        capabilities=["current_weather", "forecast_5day"],
        limitations=["no_historical_data", "limited_to_cities"],
        required_inputs=[
            InputSpec(name="location", type="STRING", description="City name or coordinates"),
        ],
        optional_inputs=[
            InputSpec(
                name="units", type="STRING", description="Temperature units (metric/imperial)"
            ),
        ],
        output={
            "type": "object",
            "properties": {"temperature": {"type": "number"}, "condition": {"type": "string"}},
            "required": ["temperature", "condition"],
        },
        provider_type="WASM",
        provider_id="wasm-weather",
        provider_endpoint="wasm://sandbox/weather",
        safety_band_min=SafetyBand.GREEN.value,
        cost_per_call=0.01,
        avg_latency_ms=50,
        max_latency_ms=500,
        availability=Availability.ONLINE.value,
    )


@pytest.fixture()
def sample_agent_contract() -> AgentContract:
    """
    Sample agent contract: invitation_sender (AGENT, SOCIAL domain, GREEN).

    A realistic agent contract for drafting and sending event invitations.
    Valid against agent_contract.schema.json.
    """
    return AgentContract(
        name="agent.execute.invitation_sender",
        version="1.0.0",
        domain=["SOCIAL", "COMMUNICATION"],
        description="Draft and send personalized event invitations to guests",
        capabilities=["draft_invitation", "personalize_message", "send_invitation"],
        limitations=["no_physical_mail", "max_100_recipients"],
        required_inputs=[
            InputSpec(name="event_name", type="STRING", description="Name of the event"),
            InputSpec(name="guest_list", type="ARRAY[STRING]", description="List of guest names"),
        ],
        optional_inputs=[
            InputSpec(name="tone", type="STRING", description="Message tone (formal/casual)"),
        ],
        required_context=["beliefs_active.entities", "beliefs_active.relationships"],
        optional_context=["beliefs_active.preferences"],
        output={
            "type": "object",
            "properties": {"invitations_sent": {"type": "number"}, "status": {"type": "string"}},
            "required": ["invitations_sent", "status"],
        },
        provider_type="AGENT",
        provider_id="local-invitation-sender",
        safety_band_min=SafetyBand.GREEN.value,
        cost_per_call=0.15,
        avg_latency_ms=3000,
        max_latency_ms=15000,
        availability=Availability.ONLINE.value,
        prompt_template="invitation_drafter_v1",
        tools_granted=["tool.execute.restaurant_booking", "tool.read.weather_api"],
        llm_budget_tokens=4096,
        max_tool_calls=5,
        max_execution_time_ms=30000,
    )


@pytest.fixture()
def sample_agent_contract_health() -> AgentContract:
    """
    Sample agent contract: health_summarizer (AGENT, HEALTH domain, AMBER).

    A health-focused agent with higher safety band.
    Valid against agent_contract.schema.json.
    """
    return AgentContract(
        name="agent.execute.health_summarizer",
        version="2.0.0",
        domain=["HEALTH", "WELLNESS"],
        description="Summarize health metrics and provide wellness insights",
        capabilities=["health_summary", "trend_analysis", "recommendation"],
        limitations=["no_diagnosis", "no_prescription"],
        required_inputs=[
            InputSpec(
                name="time_range",
                type="STRING",
                description="Time range for summary (e.g. 7d, 30d)",
            ),
        ],
        required_context=["beliefs_active.health_metrics"],
        optional_context=["beliefs_active.goals"],
        output={
            "type": "object",
            "properties": {"summary": {"type": "string"}, "trends": {"type": "array"}},
            "required": ["summary"],
        },
        provider_type="AGENT",
        provider_id="local-health-summarizer",
        safety_band_min=SafetyBand.AMBER.value,
        cost_per_call=0.20,
        avg_latency_ms=5000,
        max_latency_ms=20000,
        availability=Availability.ONLINE.value,
        prompt_template="health_summary_v2",
        tools_granted=["tool.read.weather_api"],
        llm_budget_tokens=8192,
        max_tool_calls=3,
        max_execution_time_ms=30000,
    )


@pytest.fixture()
def sample_prompt_contract() -> PromptContract:
    """
    Sample prompt contract: invitation_drafter_v1 (SOCIAL domain).

    A realistic prompt template for invitation drafting.
    Valid against prompt_contract.schema.json.
    """
    return PromptContract(
        name="invitation_drafter_v1",
        version="1.0.0",
        domain=["SOCIAL", "COMMUNICATION"],
        description="Draft personalized event invitations with appropriate tone and detail",
        intent_match=["send invitation", "invite guests", "plan event"],
        variables=[
            VariableSpec(
                name="event_name", type="STRING", required=True, description="Name of the event"
            ),
            VariableSpec(
                name="guest_names", type="ARRAY", required=True, description="List of guest names"
            ),
            VariableSpec(
                name="event_date", type="DATE", required=True, description="Date of the event"
            ),
            VariableSpec(
                name="tone",
                type="STRING",
                required=False,
                default="casual",
                description="Message tone",
            ),
            VariableSpec(
                name="venue", type="STRING", required=False, description="Event venue name"
            ),
        ],
        template_file="k1/prompts/agents/invitation_drafter_v1.txt",
        max_tokens=2048,
        output_format="TEXT",
        compatible_agents=["agent.execute.invitation_sender"],
        compatible_tools=[],
    )


@pytest.fixture()
def sample_workflow_contract() -> WorkflowContract:
    """
    Sample workflow contract: weekly_health_check (HEALTH domain, cron trigger).

    A realistic scheduled workflow with a 2-step DAG.
    Valid against workflow_contract.schema.json.
    """
    return WorkflowContract(
        name="workflow.run.weekly_health_check",
        version="1.0.0",
        domain=["HEALTH", "WELLNESS"],
        description="Weekly automated health metrics collection and summary generation",
        source_plan_id="plan-health-check-001",
        trigger=TriggerSpec(
            type="cron",
            schedule="0 8 * * MON",
            timezone="America/Los_Angeles",
        ),
        steps=[
            PlanStep(
                id="s1",
                capability="tool.read.weather_api",
                params={"location": "San Francisco"},
            ),
            PlanStep(
                id="s2",
                capability="agent.execute.health_summarizer",
                params={"time_range": "7d"},
                deps=["s1"],
            ),
        ],
        dependencies={"s2": ["s1"]},
        max_depth=3,
        allows_sub_workflows=True,
        safety_band_min=SafetyBand.GREEN.value,
        avg_latency_ms=8000,
        active=True,
    )
