"""M5 PlanStep activity_profile serialization tests."""

from __future__ import annotations

from k1.fabric.types import FabricPlanStep
from k1.orchestrator.types import PlanStep


def test_plan_step_activity_profile_round_trips() -> None:
    step = PlanStep(
        id="s1",
        capability="tool.execute.calendar.create_event",
        activity_profile="calendar.v1",
    )

    restored = PlanStep.from_dict(step.to_dict())

    assert restored.activity_profile == "calendar.v1"


def test_plan_step_omits_empty_activity_profile() -> None:
    step = PlanStep(id="s1", capability="tool.execute.calendar.create_event")

    assert "activity_profile" not in step.to_dict()


def test_plan_step_from_fabric_accepts_activity_profile_extension() -> None:
    fabric_step = FabricPlanStep(
        id="s1",
        capability="tool.execute.calendar.create_event",
        prompt_template="calendar_activity_v1",
    )

    step = PlanStep.from_fabric(
        fabric_step,
        activity_profile="calendar.v1",
    )

    assert step.prompt_template == "calendar_activity_v1"
    assert step.activity_profile == "calendar.v1"
