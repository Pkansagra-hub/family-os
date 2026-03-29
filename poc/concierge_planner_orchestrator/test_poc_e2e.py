"""
POC E2E Tests -- Concierge -> Planner -> Orchestrator
======================================================

Tests the full pipeline with real Google Gemini LLM calls.

These are integration tests that hit the real LLM API.
They validate that:
  - Concierge correctly classifies complexity via LLM
  - Planner builds valid DAGs from discovered capabilities
  - Orchestrator executes DAG through Fabric
  - Pipeline end-to-end produces results

Requires:
  GOOGLE_API_KEY environment variable set.

Run:
  python -m pytest poc/concierge_planner_orchestrator/test_poc_e2e.py -v -s
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Load env for API key
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "chat_experience_poc" / ".env")
load_dotenv(Path(__file__).parent.parent.parent / ".env")


# Skip all tests if no API key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
pytestmark = pytest.mark.skipif(
    not GOOGLE_API_KEY,
    reason="GOOGLE_API_KEY not set -- skipping LLM integration tests",
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(scope="module")
def llm_client():
    """Create a real SimpleLLMClient."""
    from poc.session_state_demo.llm_client import SimpleLLMClient

    return SimpleLLMClient(
        api_key=GOOGLE_API_KEY,
        model="gemini-2.5-flash",
    )


@pytest.fixture(scope="module")
def capabilities():
    """Load real capability catalog from YAML contracts."""
    from poc.concierge_planner_orchestrator.discovery import load_capability_catalog

    caps = load_capability_catalog(Path("k1/contracts/tools"))
    assert len(caps) > 0, "No capabilities loaded"
    return caps


@pytest.fixture(scope="module")
def fabric_container():
    """Create real Fabric with test adapters."""
    from k1.fabric.factory import FabricFactory

    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir="k1/contracts",
    )


@pytest.fixture(scope="module")
def concierge(llm_client):
    """Create Concierge with real LLM."""
    from poc.concierge_planner_orchestrator.concierge import Concierge

    return Concierge(llm_client=llm_client)


@pytest.fixture(scope="module")
def planner(llm_client):
    """Create Planner with real LLM."""
    from poc.concierge_planner_orchestrator.planner import Planner

    return Planner(llm_client=llm_client)


@pytest.fixture(scope="module")
def orchestrator(fabric_container):
    """Create Orchestrator with real Fabric."""
    from poc.concierge_planner_orchestrator.orchestrator import Orchestrator

    return Orchestrator(fabric=fabric_container.facade)


@pytest.fixture(scope="module")
def pipeline(fabric_container):
    """Create full pipeline."""
    from poc.concierge_planner_orchestrator.pipeline import Pipeline

    return Pipeline.create(
        api_key=GOOGLE_API_KEY or "",
        fabric=fabric_container.facade,
        contracts_dir=Path("k1/contracts/tools"),
    )


# ============================================================
# Concierge Tests (Real LLM Classification)
# ============================================================


class TestConciergeClassification:
    """Test Concierge classifies user input via real Gemini."""

    @pytest.mark.asyncio
    async def test_classify_simple_weather_as_low(self, concierge):
        """Simple single-domain request should be LOW or MEDIUM."""
        envelope = await concierge.classify("What's the weather in London?")
        assert envelope.tier.value in ("LOW", "MEDIUM")
        assert envelope.intent  # Non-empty intent
        assert any(
            d.upper() in ("WEATHER", "GENERAL") for d in envelope.domains
        ), f"Expected WEATHER domain, got {envelope.domains}"

    @pytest.mark.asyncio
    async def test_classify_multi_domain_as_high(self, concierge):
        """Multi-domain multi-step request should be HIGH."""
        envelope = await concierge.classify(
            "Get the weather forecast for London, find me a spaghetti recipe, "
            "and create a note with the meal plan and weather summary."
        )
        assert (
            envelope.tier.value == "HIGH"
        ), f"Expected HIGH for multi-domain request, got {envelope.tier.value}"
        assert len(envelope.domains) >= 2, f"Expected multiple domains, got {envelope.domains}"

    @pytest.mark.asyncio
    async def test_classify_returns_valid_envelope(self, concierge):
        """Classification always produces a valid TaskEnvelope."""
        envelope = await concierge.classify("Search for pasta recipes")
        assert envelope.user_input == "Search for pasta recipes"
        assert envelope.intent  # Non-empty
        assert isinstance(envelope.domains, list)
        assert envelope.trace_id  # Non-empty


# ============================================================
# Discovery Tests (Real Contract Loading)
# ============================================================


class TestDiscovery:
    """Test capability discovery from real YAML contracts."""

    def test_load_capabilities(self, capabilities):
        """Should load multiple capabilities from contracts."""
        assert len(capabilities) >= 9  # At least 9 user-facing tools
        names = [c["name"] for c in capabilities]
        assert "tool.read.weather_forecast" in names
        assert "tool.read.recipe_search" in names
        assert "tool.write.notes_create" in names

    def test_filter_by_domain(self, capabilities):
        """Domain filter should narrow results."""
        from poc.concierge_planner_orchestrator.discovery import (
            filter_capabilities_by_domain,
        )

        weather_caps = filter_capabilities_by_domain(capabilities, ["WEATHER"])
        assert len(weather_caps) >= 1
        assert all("WEATHER" in [d.upper() for d in c.get("domain", [])] for c in weather_caps)

    def test_capabilities_have_required_fields(self, capabilities):
        """Each capability should have name, description, required_inputs."""
        for cap in capabilities:
            assert "name" in cap and cap["name"]
            assert "description" in cap and cap["description"]
            assert "required_inputs" in cap


# ============================================================
# Planner Tests (Real LLM DAG Building)
# ============================================================


class TestPlannerDagBuilding:
    """Test Planner builds valid DAGs via real Gemini."""

    @pytest.mark.asyncio
    async def test_planner_builds_weather_recipe_plan(self, planner, capabilities):
        """Planner should build a multi-step DAG for weather + recipe request."""
        from poc.concierge_planner_orchestrator.types import PlanRequest

        plan_request = PlanRequest(
            intent="get weather and find recipes",
            user_input="Get the weather in London and find me a spaghetti recipe",
            domains=["WEATHER", "RECIPES"],
            available_capabilities=capabilities,
            trace_id="test-trace-1",
        )

        plan = await planner.build_plan(plan_request)

        assert len(plan.steps) >= 2, f"Expected at least 2 steps, got {len(plan.steps)}"
        assert plan.reasoning, "Plan should have reasoning"

        # All steps should reference real capabilities
        valid_names = {c["name"] for c in capabilities}
        for step in plan.steps:
            assert (
                step.capability_name in valid_names
            ), f"Step '{step.step_id}' uses invalid capability '{step.capability_name}'"
            assert step.step_id, "Step must have an ID"

    @pytest.mark.asyncio
    async def test_planner_builds_dag_with_dependencies(self, planner, capabilities):
        """Planner should create dependencies between steps when needed."""
        from poc.concierge_planner_orchestrator.types import PlanRequest

        plan_request = PlanRequest(
            intent="search recipes then create meal plan and save as note",
            user_input=(
                "Search for chicken recipes, create a meal plan for 4 people, "
                "and save the meal plan as a note."
            ),
            domains=["RECIPES", "NOTES"],
            available_capabilities=capabilities,
            trace_id="test-trace-2",
        )

        plan = await planner.build_plan(plan_request)

        assert len(plan.steps) >= 2, f"Expected at least 2 steps, got {len(plan.steps)}"

        # At least one step should have dependencies
        steps_with_deps = [s for s in plan.steps if s.depends_on]
        assert len(steps_with_deps) >= 1, (
            f"Expected at least 1 step with dependencies, got 0. "
            f"Steps: {[(s.step_id, s.capability_name, s.depends_on) for s in plan.steps]}"
        )

    @pytest.mark.asyncio
    async def test_planner_produces_acyclic_graph(self, planner, capabilities):
        """Planner DAG must be acyclic."""
        from poc.concierge_planner_orchestrator.types import PlanRequest

        plan_request = PlanRequest(
            intent="weather recipe and notes",
            user_input="Get weather for London, find Italian recipes, create a note with both",
            domains=["WEATHER", "RECIPES", "NOTES"],
            available_capabilities=capabilities,
            trace_id="test-trace-3",
        )

        plan = await planner.build_plan(plan_request)

        # Verify acyclicity using Planner's own validator
        from poc.concierge_planner_orchestrator.planner import Planner

        assert Planner._is_acyclic(plan.steps), "Plan DAG contains cycles"

    @pytest.mark.asyncio
    async def test_planner_only_uses_available_capabilities(self, planner):
        """Planner must not hallucinate capabilities not in the list."""
        from poc.concierge_planner_orchestrator.types import PlanRequest

        # Give a very limited set
        limited_caps = [
            {
                "name": "tool.read.weather_forecast",
                "description": "Get weather forecast for a location",
                "domain": ["WEATHER"],
                "required_inputs": [
                    {"name": "location", "type": "STRING", "description": "City name"},
                ],
                "optional_inputs": [],
            }
        ]

        plan_request = PlanRequest(
            intent="get weather",
            user_input="What's the weather in Paris?",
            domains=["WEATHER"],
            available_capabilities=limited_caps,
            trace_id="test-trace-4",
        )

        plan = await planner.build_plan(plan_request)

        for step in plan.steps:
            assert (
                step.capability_name == "tool.read.weather_forecast"
            ), f"Planner used unavailable capability: {step.capability_name}"


# ============================================================
# Orchestrator Tests (DAG execution through Fabric)
# ============================================================


class TestOrchestratorExecution:
    """Test Orchestrator executes DAGs via real Fabric."""

    @pytest.mark.asyncio
    async def test_orchestrator_executes_simple_plan(self, orchestrator):
        """Orchestrator should execute a plan with one step."""
        from poc.concierge_planner_orchestrator.types import CommittedPlan, PlanStep

        plan = CommittedPlan(
            intent="get weather",
            steps=[
                PlanStep(
                    step_id="s1",
                    capability_name="tool.read.weather_forecast",
                    params={"location": "London"},
                    depends_on=[],
                    description="Get London weather",
                ),
            ],
            trace_id="test-orch-1",
        )

        result = await orchestrator.execute_plan(plan)
        assert len(result.step_results) == 1
        # Note: with test adapters the execution may fail at provider level
        # but the orchestrator flow itself should complete
        assert result.step_results[0].step_id == "s1"

    @pytest.mark.asyncio
    async def test_orchestrator_executes_dag_with_deps(self, orchestrator):
        """Orchestrator should respect dependencies in DAG execution."""
        from poc.concierge_planner_orchestrator.types import CommittedPlan, PlanStep

        plan = CommittedPlan(
            intent="weather then notes",
            steps=[
                PlanStep(
                    step_id="s1",
                    capability_name="tool.read.weather_forecast",
                    params={"location": "London"},
                    depends_on=[],
                    description="Get weather",
                ),
                PlanStep(
                    step_id="s2",
                    capability_name="tool.read.recipe_search",
                    params={"query": "spaghetti"},
                    depends_on=[],
                    description="Search recipes",
                ),
                PlanStep(
                    step_id="s3",
                    capability_name="tool.write.notes_create",
                    params={"title": "Plan", "content": "Weather + Recipes"},
                    depends_on=["s1", "s2"],
                    description="Create note (depends on s1 + s2)",
                ),
            ],
            trace_id="test-orch-2",
        )

        result = await orchestrator.execute_plan(plan)
        assert len(result.step_results) == 3
        # All 3 steps should have been attempted
        step_ids = [sr.step_id for sr in result.step_results]
        assert "s1" in step_ids
        assert "s2" in step_ids
        assert "s3" in step_ids

    @pytest.mark.asyncio
    async def test_orchestrator_handles_empty_plan(self, orchestrator):
        """Orchestrator returns failure for empty plan."""
        from poc.concierge_planner_orchestrator.types import CommittedPlan

        plan = CommittedPlan(intent="empty", steps=[], trace_id="test-orch-3")
        result = await orchestrator.execute_plan(plan)
        assert not result.success


# ============================================================
# Full Pipeline Tests (End-to-End with Real LLM)
# ============================================================


class TestFullPipeline:
    """End-to-end tests with real LLM classification, planning, and execution."""

    @pytest.mark.asyncio
    async def test_pipeline_high_tier_multi_domain(self, pipeline):
        """Full pipeline for a HIGH-tier multi-domain request."""
        result = await pipeline.run("Get the weather in London and find me a spaghetti recipe")

        assert "envelope" in result
        assert "orchestrator_result" in result
        assert "response" in result

        # Concierge should have classified
        env = result["envelope"]
        assert env["tier"] in ("MEDIUM", "HIGH")
        assert env["intent"]  # Non-empty

        # Orchestrator should have executed steps
        orch = result["orchestrator_result"]
        assert len(orch["steps"]) >= 2, f"Expected at least 2 steps, got {len(orch['steps'])}"

        # Concierge should have synthesized a response
        assert result["response"], "Response should not be empty"
        assert len(result["response"]) > 10, "Response should be substantive"

    @pytest.mark.asyncio
    async def test_pipeline_produces_llm_response(self, pipeline):
        """Pipeline should produce a natural language response via LLM."""
        result = await pipeline.run("Search for pasta recipes")

        response = result.get("response", "")
        assert response, "Response should not be empty"
        # The response should be natural language, not raw JSON
        assert len(response) > 20

    @pytest.mark.asyncio
    async def test_pipeline_envelope_has_classification(self, pipeline):
        """Pipeline envelope should contain LLM classification."""
        result = await pipeline.run("What events do I have on my calendar?")

        env = result["envelope"]
        assert "tier" in env
        assert "intent" in env
        assert "domains" in env
        assert env["tier"] in ("LOW", "MEDIUM", "HIGH")


# ============================================================
# Planner Validation Tests (Non-LLM, structural)
# ============================================================


class TestPlannerValidation:
    """Structural validation tests that don't need LLM."""

    def test_is_acyclic_valid_dag(self):
        """Valid DAG should pass acyclicity check."""
        from poc.concierge_planner_orchestrator.planner import Planner
        from poc.concierge_planner_orchestrator.types import PlanStep

        steps = [
            PlanStep(step_id="s1", capability_name="a", depends_on=[]),
            PlanStep(step_id="s2", capability_name="b", depends_on=[]),
            PlanStep(step_id="s3", capability_name="c", depends_on=["s1", "s2"]),
        ]
        assert Planner._is_acyclic(steps)

    def test_is_acyclic_detects_cycle(self):
        """Cyclic graph should be detected."""
        from poc.concierge_planner_orchestrator.planner import Planner
        from poc.concierge_planner_orchestrator.types import PlanStep

        steps = [
            PlanStep(step_id="s1", capability_name="a", depends_on=["s2"]),
            PlanStep(step_id="s2", capability_name="b", depends_on=["s1"]),
        ]
        assert not Planner._is_acyclic(steps)

    def test_is_acyclic_single_node(self):
        """Single node with no deps is acyclic."""
        from poc.concierge_planner_orchestrator.planner import Planner
        from poc.concierge_planner_orchestrator.types import PlanStep

        steps = [PlanStep(step_id="s1", capability_name="a", depends_on=[])]
        assert Planner._is_acyclic(steps)

    def test_is_acyclic_complex_dag(self):
        """Complex DAG with 5 nodes should pass."""
        from poc.concierge_planner_orchestrator.planner import Planner
        from poc.concierge_planner_orchestrator.types import PlanStep

        steps = [
            PlanStep(step_id="s1", capability_name="a", depends_on=[]),
            PlanStep(step_id="s2", capability_name="b", depends_on=[]),
            PlanStep(step_id="s3", capability_name="c", depends_on=["s1"]),
            PlanStep(step_id="s4", capability_name="d", depends_on=["s2"]),
            PlanStep(step_id="s5", capability_name="e", depends_on=["s3", "s4"]),
        ]
        assert Planner._is_acyclic(steps)


# ============================================================
# Type Tests (Non-LLM, structural)
# ============================================================


class TestTypes:
    """Test domain types are properly constructed."""

    def test_task_envelope_frozen(self):
        """TaskEnvelope should be immutable."""
        from poc.concierge_planner_orchestrator.types import TaskEnvelope

        env = TaskEnvelope(user_input="test", intent="test")
        with pytest.raises(Exception):
            env.user_input = "modified"  # type: ignore

    def test_committed_plan_frozen(self):
        """CommittedPlan should be immutable."""
        from poc.concierge_planner_orchestrator.types import CommittedPlan

        plan = CommittedPlan(intent="test")
        with pytest.raises(Exception):
            plan.intent = "modified"  # type: ignore

    def test_orchestrator_result_properties(self):
        """OrchestratorResult should compute failed/successful steps."""
        from poc.concierge_planner_orchestrator.types import (
            OrchestratorResult,
            StepResult,
        )

        result = OrchestratorResult(
            success=False,
            step_results=[
                StepResult(step_id="s1", success=True),
                StepResult(step_id="s2", success=False, error="timeout"),
                StepResult(step_id="s3", success=True),
            ],
        )
        assert len(result.successful_steps) == 2
        assert len(result.failed_steps) == 1
        assert result.failed_steps[0].step_id == "s2"
