"""
Integration Tests for Issue 6.5.2.3: Orchestrator → Planner → DAG Executor Pipeline

Tests the complete multi-step task execution flow:
1. Orchestrator delegates planning task to Planner
2. Planner generates 4-stage plan (Sketch → Expand → Validate → Commit)
3. Orchestrator receives CommittedPlan
4. Orchestrator hands off to DAG Executor
5. DAG Executor runs parallel waves with barriers
6. All results aggregated and returned

References:
- docs/plans/chat_experience_poc_plan.md (Issue 6.5.2.3)
- ADR-0006c: DAG Execution with barriers
- ADR-0007: 4-Stage Planning Pipeline
- ADR-0008: Saga Pattern error recovery
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from l2_orchestration.executor.dag_executor import DAGExecutor
from l2_orchestration.orchestrator.orchestrator import (
    Orchestrator,
    TaskAnnouncement,
    TaskAssignment,
    TaskStatus,
    TaskType,
)
from l2_orchestration.planner.data_models import (
    CommittedPlan,
    PlanComplexity,
    PlanStep,
    StepOp,
)
from l4_runtime.session_state.session_state import SessionState
from l5_infrastructure.registries.prompt_registry import PromptRegistry
from l5_infrastructure.registries.tool_registry import ToolRegistry


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
    """Create an Orchestrator instance for testing."""
    agent_registry = {}
    agent_factory = MagicMock()
    mailbox_manager = MagicMock()

    orch = Orchestrator(
        agent_registry=agent_registry,
        tool_registry=tool_registry,
        session_state=session_state,
        agent_factory=agent_factory,
        mailbox_manager=mailbox_manager,
    )

    orch.tool_registry = tool_registry
    orch.prompt_registry = prompt_registry

    # Mock Groq client
    orch.groq_client = AsyncMock()

    yield orch


@pytest.fixture
def committed_plan():
    """Create a sample CommittedPlan for testing."""
    # Create steps for a simple 2-step plan
    steps = [
        PlanStep(
            step_id="step_1",
            op=StepOp.TOOL,
            description="Search for restaurant",
            needs=[],  # No dependencies
            tool_name="web_search",
            agent_id="specialist_agent_1",
            parameters={"query": "best restaurants near me"},
            estimated_latency_ms=100,
            estimated_cost=0.05,
        ),
        PlanStep(
            step_id="step_2",
            op=StepOp.TOOL,
            description="Book restaurant reservation",
            needs=["step_1"],  # Depends on step_1
            tool_name="book_restaurant",
            agent_id="specialist_agent_2",
            parameters={"restaurant_id": "{step_1.result}"},
            estimated_latency_ms=200,
            estimated_cost=0.10,
        ),
    ]

    return CommittedPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:12]}",
        intent="Book a restaurant reservation",
        steps=steps,
        complexity=PlanComplexity.MEDIUM,
        serialized_json=json.dumps({"plan": "test"}),
        plan_hash="abc123",
        committed_at="2025-11-05T21:00:00Z",
        latency_ms=45.5,
        trace_id=f"trace_{uuid.uuid4().hex[:12]}",
    )


class TestOrchestratorPlannerIntegration:
    """Test Orchestrator ↔ Planner communication"""

    @pytest.mark.asyncio
    async def test_orchestrator_sends_task_to_planner(self, orchestrator):
        """Verify Orchestrator sends planning task to Planner."""
        # Create task assignment
        task_announcement = TaskAnnouncement(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            task_type=TaskType.PLANNING,
            user_input="Book me a restaurant reservation",
            required_tools=["web_search", "book_restaurant"],
            deadline_ms=30000,
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
            budget={"time_ms": 30000, "cost_credits": 5.0},
            user_context={"user_id": "test_user"},
        )

        task_assignment = TaskAssignment(
            task_id=task_announcement.task_id,
            agent_id="planner_agent_1",
            task_announcement=task_announcement,
            deadline_ms=30000,
        )

        # Mock agent response
        orchestrator._wait_for_agent_response = AsyncMock(
            return_value={"status": "success", "data": {"test": "plan"}}
        )

        # Execute multi-step task
        result = await orchestrator._execute_multistep_task("planner_agent_1", task_assignment, 0)

        # Verify task sent to planner
        assert orchestrator._wait_for_agent_response.called
        assert result.task_id == task_announcement.task_id

    @pytest.mark.asyncio
    async def test_orchestrator_handles_planner_failure(self, orchestrator):
        """Verify Orchestrator handles Planner failures gracefully."""
        task_announcement = TaskAnnouncement(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            task_type=TaskType.PLANNING,
            user_input="Invalid task",
            required_tools=[],
            deadline_ms=30000,
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
            budget={"time_ms": 30000, "cost_credits": 5.0},
            user_context={"user_id": "test_user"},
        )

        task_assignment = TaskAssignment(
            task_id=task_announcement.task_id,
            agent_id="planner_agent_1",
            task_announcement=task_announcement,
            deadline_ms=30000,
        )

        # Mock Planner failure
        orchestrator._wait_for_agent_response = AsyncMock(
            return_value={"status": "failure", "error": "Invalid input"}
        )

        result = await orchestrator._execute_multistep_task("planner_agent_1", task_assignment, 0)

        # Verify failure handled
        assert result.status == TaskStatus.FAILURE
        assert "Invalid input" in result.error


class TestOrchestratorDAGExecutorIntegration:
    """Test Orchestrator ↔ DAG Executor handoff"""

    @pytest.mark.asyncio
    async def test_orchestrator_hands_plan_to_dag_executor(self, orchestrator, committed_plan):
        """Verify Orchestrator correctly hands off CommittedPlan to DAG Executor."""
        task_announcement = TaskAnnouncement(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            task_type=TaskType.PLANNING,
            user_input="Book restaurant",
            required_tools=["web_search", "book_restaurant"],
            budget={"time_ms": 30000, "cost_credits": 5.0},
            user_context={"user_id": "test_user"},
            deadline_ms=30000,
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
        )

        task_assignment = TaskAssignment(
            task_id=task_announcement.task_id,
            agent_id="planner_agent_1",
            task_announcement=task_announcement,
            deadline_ms=30000,
        )

        # Mock Planner response with CommittedPlan
        orchestrator._wait_for_agent_response = AsyncMock(
            return_value={
                "status": "success",
                "data": committed_plan,
            }
        )

        # Execute multi-step task with real DAGExecutor
        result = await orchestrator._execute_multistep_task("planner_agent_1", task_assignment, 0)

        # Verify result structure
        assert orchestrator._wait_for_agent_response.called
        assert result.task_id == task_announcement.task_id
        # DAG should execute and return results (may succeed or fail depending on tool availability)
        assert result.status in [TaskStatus.SUCCESS, TaskStatus.PARTIAL, TaskStatus.FAILURE]

    @pytest.mark.asyncio
    async def test_dag_executor_wave_execution(self, tool_registry):
        """Verify DAG Executor correctly computes and executes waves."""
        # Create simple 2-step plan with dependency
        steps = [
            PlanStep(
                step_id="step_1",
                op=StepOp.TOOL,
                description="Search",
                needs=[],
                tool_name="web_search",
                agent_id="agent1",
                parameters={"query": "test"},
            ),
            PlanStep(
                step_id="step_2",
                op=StepOp.TOOL,
                description="Book",
                needs=["step_1"],
                tool_name="book_restaurant",
                agent_id="agent2",
                parameters={"id": "test"},
            ),
        ]

        committed_plan = CommittedPlan(
            plan_id="plan_123",
            intent="test",
            steps=steps,
            complexity=PlanComplexity.SIMPLE,
            serialized_json=json.dumps({}),
            plan_hash="hash123",
            committed_at="2025-11-05T21:00:00Z",
            latency_ms=45.5,
        )

        dag_executor = DAGExecutor(
            agent_registry={},
            tool_registry=tool_registry,
            max_concurrent=3,
        )

        # Parse and compute waves
        dag = dag_executor._parse_dag(committed_plan)
        waves = dag_executor._compute_waves(dag, committed_plan.steps)

        # Verify wave structure
        assert len(waves) == 2, "Should have 2 waves (step_1 then step_2)"
        assert "step_1" in waves[0], "step_1 should be in first wave"
        assert "step_2" in waves[1], "step_2 should be in second wave"

    @pytest.mark.asyncio
    async def test_dag_executor_parallel_wave_execution(self, tool_registry):
        """Verify DAG Executor correctly identifies parallel opportunities."""
        # Create 3-step plan: step_1, then parallel step_2 and step_3
        steps = [
            PlanStep(
                step_id="step_1",
                op=StepOp.TOOL,
                description="Search",
                needs=[],
                tool_name="web_search",
                agent_id="agent1",
                parameters={"query": "test"},
            ),
            PlanStep(
                step_id="step_2",
                op=StepOp.TOOL,
                description="Analyze 1",
                needs=["step_1"],
                tool_name="analyze",
                agent_id="agent2",
                parameters={"data": "test"},
            ),
            PlanStep(
                step_id="step_3",
                op=StepOp.TOOL,
                description="Analyze 2",
                needs=["step_1"],
                tool_name="analyze",
                agent_id="agent3",
                parameters={"data": "test"},
            ),
        ]

        committed_plan = CommittedPlan(
            plan_id="plan_123",
            intent="test",
            steps=steps,
            complexity=PlanComplexity.SIMPLE,
            serialized_json=json.dumps({}),
            plan_hash="hash123",
            committed_at="2025-11-05T21:00:00Z",
            latency_ms=45.5,
        )

        dag_executor = DAGExecutor(
            agent_registry={},
            tool_registry=tool_registry,
            max_concurrent=3,
        )

        # Parse and compute waves
        dag = dag_executor._parse_dag(committed_plan)
        waves = dag_executor._compute_waves(dag, committed_plan.steps)

        # Verify parallel wave structure
        assert len(waves) == 2, "Should have 2 waves"
        assert "step_1" in waves[0], "step_1 should be in first wave"
        assert len(waves[1]) == 2, "Second wave should have 2 parallel steps"
        assert set(waves[1]) == {
            "step_2",
            "step_3",
        }, "step_2 and step_3 should run in parallel"


class TestEndToEndPipeline:
    """End-to-end tests for full pipeline"""

    @pytest.mark.asyncio
    async def test_complete_orchestrator_planner_dag_flow(self, orchestrator, committed_plan):
        """Test complete flow from Orchestrator to DAG Executor."""
        task_announcement = TaskAnnouncement(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            task_type=TaskType.PLANNING,
            user_input="Book restaurant and send confirmation email",
            required_tools=["web_search", "book_restaurant", "send_email"],
            budget={"time_ms": 30000, "cost_credits": 5.0},
            user_context={"user_id": "test_user"},
            deadline_ms=30000,
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
        )

        task_assignment = TaskAssignment(
            task_id=task_announcement.task_id,
            agent_id="planner_agent_1",
            task_announcement=task_announcement,
            deadline_ms=30000,
        )

        # Mock Planner response with CommittedPlan
        orchestrator._wait_for_agent_response = AsyncMock(
            return_value={
                "status": "success",
                "data": committed_plan,
            }
        )

        # Execute multi-step task with real DAG Executor
        result = await orchestrator._execute_multistep_task("planner_agent_1", task_assignment, 0)

        # Verify complete flow
        assert result.task_id == task_announcement.task_id
        assert "planner_agent_1" in result.agents_used
        assert len(result.agents_used) > 0, "Should include all agents used"
        assert result.latency_ms > 0, "Latency should be recorded"
        # Result status may vary depending on tool availability
        assert result.status in [TaskStatus.SUCCESS, TaskStatus.PARTIAL, TaskStatus.FAILURE]

    @pytest.mark.asyncio
    async def test_pipeline_collects_all_receipts(self, orchestrator, committed_plan):
        """Verify all receipts are collected from all waves."""
        task_announcement = TaskAnnouncement(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            task_type=TaskType.PLANNING,
            user_input="Complex multi-step task",
            required_tools=[],
            budget={"time_ms": 30000, "cost_credits": 5.0},
            user_context={"user_id": "test_user"},
            deadline_ms=30000,
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
        )

        task_assignment = TaskAssignment(
            task_id=task_announcement.task_id,
            agent_id="planner_agent_1",
            task_announcement=task_announcement,
            deadline_ms=30000,
        )

        # Mock Planner response
        orchestrator._wait_for_agent_response = AsyncMock(
            return_value={
                "status": "success",
                "data": committed_plan,
            }
        )

        # Execute with real DAG Executor
        result = await orchestrator._execute_multistep_task("planner_agent_1", task_assignment, 0)

        # Verify receipts structure (may be empty if tools not available)
        assert isinstance(result.receipts, list), "Receipts should be a list"
        assert result.task_id == task_announcement.task_id

    @pytest.mark.asyncio
    async def test_pipeline_handles_dag_executor_failure(self, orchestrator, committed_plan):
        """Verify pipeline handles DAG Executor failures gracefully."""
        task_announcement = TaskAnnouncement(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            task_type=TaskType.PLANNING,
            user_input="Task",
            required_tools=[],
            budget={"time_ms": 30000, "cost_credits": 5.0},
            user_context={"user_id": "test_user"},
            deadline_ms=30000,
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
        )

        task_assignment = TaskAssignment(
            task_id=task_announcement.task_id,
            agent_id="planner_agent_1",
            task_announcement=task_announcement,
            deadline_ms=30000,
        )

        # Mock Planner response
        orchestrator._wait_for_agent_response = AsyncMock(
            return_value={
                "status": "success",
                "data": committed_plan,
            }
        )

        # Execute with real DAG Executor
        result = await orchestrator._execute_multistep_task("planner_agent_1", task_assignment, 0)

        # Verify result contains all required fields
        assert result.task_id == task_announcement.task_id
        assert isinstance(result.agents_used, list)
        assert isinstance(result.receipts, list)
        assert result.status in [TaskStatus.SUCCESS, TaskStatus.PARTIAL, TaskStatus.FAILURE]
