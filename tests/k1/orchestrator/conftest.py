import json
import uuid
from pathlib import Path

import pytest

from k1.fabric.types import CapabilityResult
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import CommittedPlan, PlanStep, TaskEnvelope
from k1.orchestrator.workflows.workflow_types import (
    TriggerSpec,
    TriggerType,
    WorkflowSpec,
)


@pytest.fixture(scope="function")
async def orchestrator_standalone():
    """OrchestratorFactory.create_standalone() - all test adapters, no init()."""
    orchestrator = await OrchestratorFactory.create_standalone()
    yield orchestrator
    # Cleanup if needed


@pytest.fixture(scope="function")
async def orchestrator_for_testing():
    """OrchestratorFactory.create_for_testing() - test adapters + event capture."""
    orchestrator = await OrchestratorFactory.create_for_testing()
    yield orchestrator
    # Cleanup if needed


@pytest.fixture(scope="function")
async def orchestrator_with_ports(**overrides):
    """OrchestratorFactory.create_with_ports() - for mixing real + test adapters."""
    orchestrator = await OrchestratorFactory.create_with_ports(**overrides)
    yield orchestrator
    # Cleanup if needed


@pytest.fixture(scope="session")
def sample_task_envelope():
    """Returns valid TaskEnvelope for MEDIUM tier."""
    return TaskEnvelope(
        envelope_id=str(uuid.uuid4()),
        intent="test intent",
        context={},
        tier="MEDIUM",
        capabilities=["tool.calendar.search"],
        params={"tool.calendar.search": {"query": "test"}},
        constraints={},
        trace_id=str(uuid.uuid4()),
        caller_id="test",
        timeout_ms=30000,
    )


@pytest.fixture(scope="session")
def sample_committed_plan():
    """Returns valid CommittedPlan with 3 steps, 2 waves."""
    steps = [
        PlanStep(
            id="s1",
            capability="tool.calendar.search",
            params={"query": "test"},
            deps=[],
            prompt_template=None,
            tools_granted=None,
            output_schema=None,
            condition=None,
            is_optional=False,
            has_side_effects=False,
            compensation=None,
            timeout_ms=None,
            required_context=None,
        ),
        PlanStep(
            id="s2",
            capability="tool.email.send",
            params={"to": "test@example.com", "body": "test"},
            deps=["s1"],
            prompt_template=None,
            tools_granted=None,
            output_schema=None,
            condition=None,
            is_optional=False,
            has_side_effects=False,
            compensation=None,
            timeout_ms=None,
            required_context=None,
        ),
        PlanStep(
            id="s3",
            capability="tool.notification.send",
            params={"message": "done"},
            deps=["s2"],
            prompt_template=None,
            tools_granted=None,
            output_schema=None,
            condition=None,
            is_optional=False,
            has_side_effects=False,
            compensation=None,
            timeout_ms=None,
            required_context=None,
        ),
    ]
    return CommittedPlan(
        plan_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        intent="test intent",
        steps=steps,
        dependencies={"s2": ["s1"], "s3": ["s2"]},
        created_at=0.0,
        trace_id=str(uuid.uuid4()),
    )


@pytest.fixture(scope="session")
def sample_workflow_spec():
    """Returns valid WorkflowSpec with cron trigger."""
    return WorkflowSpec(
        workflow_id=str(uuid.uuid4()),
        name="test workflow",
        source_plan_id=str(uuid.uuid4()),
        version="1.0.0",
        trigger=TriggerSpec(
            type=TriggerType.CRON,
            schedule="0 9 * * 1",  # Every Monday 9am
            timezone="UTC",
        ),
        steps=[],  # Empty for test
        dependencies={},
        active=True,
    )


@pytest.fixture(scope="session")
def sample_capability_result():
    """Returns valid CapabilityResult with SUCCESS status."""
    return CapabilityResult(
        success=True,
        data={"events": []},
        error=None,
        duration_ms=100,
        trace_id=str(uuid.uuid4()),
    )


# Additional sample fixtures loaded from JSON files
@pytest.fixture(scope="session")
def sample_task_envelope_medium():
    """Returns MEDIUM tier TaskEnvelope with 2 capabilities from JSON."""
    fixture_path = Path(__file__).parent / "fixtures" / "task_envelope_medium.json"
    with open(fixture_path) as f:
        data = json.load(f)
    return TaskEnvelope(**data)


@pytest.fixture(scope="session")
def sample_task_envelope_high():
    """Returns HIGH tier TaskEnvelope requiring planning from JSON."""
    fixture_path = Path(__file__).parent / "fixtures" / "task_envelope_high.json"
    with open(fixture_path) as f:
        data = json.load(f)
    return TaskEnvelope(**data)


@pytest.fixture(scope="session")
def sample_committed_plan_linear():
    """Returns 3-step linear plan from JSON."""
    fixture_path = Path(__file__).parent / "fixtures" / "committed_plan_linear.json"
    with open(fixture_path) as f:
        data = json.load(f)
    # Convert steps to PlanStep objects
    data["steps"] = [PlanStep(**step) for step in data["steps"]]
    return CommittedPlan(**data)


@pytest.fixture(scope="session")
def sample_committed_plan_parallel():
    """Returns 5-step parallel plan from JSON."""
    fixture_path = Path(__file__).parent / "fixtures" / "committed_plan_parallel.json"
    with open(fixture_path) as f:
        data = json.load(f)
    # Convert steps to PlanStep objects
    data["steps"] = [PlanStep(**step) for step in data["steps"]]
    return CommittedPlan(**data)


@pytest.fixture(scope="session")
def sample_committed_plan_meta_agent():
    """Returns 2-step meta-agent plan from JSON."""
    fixture_path = Path(__file__).parent / "fixtures" / "committed_plan_meta_agent.json"
    with open(fixture_path) as f:
        data = json.load(f)
    # Convert steps to PlanStep objects
    data["steps"] = [PlanStep(**step) for step in data["steps"]]
    return CommittedPlan(**data)


@pytest.fixture(scope="session")
def sample_workflow_spec_cron():
    """Returns WorkflowSpec with daily cron trigger from JSON."""
    fixture_path = Path(__file__).parent / "fixtures" / "workflow_spec_cron.json"
    with open(fixture_path) as f:
        data = json.load(f)
    # Convert trigger and steps
    data["trigger"] = TriggerSpec(**data["trigger"])
    data["steps"] = [PlanStep(**step) for step in data["steps"]]
    return WorkflowSpec(**data)


@pytest.fixture(scope="session")
def sample_workflow_spec_event():
    """Returns WorkflowSpec with event trigger from JSON."""
    fixture_path = Path(__file__).parent / "fixtures" / "workflow_spec_event.json"
    with open(fixture_path) as f:
        data = json.load(f)
    # Convert trigger and steps
    data["trigger"] = TriggerSpec(**data["trigger"])
    data["steps"] = [PlanStep(**step) for step in data["steps"]]
    return WorkflowSpec(**data)


@pytest.fixture(scope="session")
def sample_interrupt_request():
    """Returns InterruptRequest(cancel) payload from JSON."""
    fixture_path = Path(__file__).parent / "fixtures" / "interrupt_request.json"
    with open(fixture_path) as f:
        data = json.load(f)
    from k1.orchestrator.types import InterruptRequest

    return InterruptRequest(**data)
