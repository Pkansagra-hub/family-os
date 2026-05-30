"""M1.5-E4: EXPAND uses PlanRequest.grounding as typed planner source."""

from __future__ import annotations

from typing import Any, cast

from k1.grounding.factory import GroundingFactory
from k1.grounding.serialization import projection_to_dict
from k1.orchestrator.types import PlanRequest
from k1.planner.stages.expand_service import ExpandService
from k1.planner.types import RoughStep, SketchResult


async def test_expand_prompt_renders_planning_grounding_from_plan_request() -> None:
    bundle = GroundingFactory.create_standalone()
    projection = await bundle.service.build_projection("s1", consumer="planner", turn_id="t1")
    request = PlanRequest(
        intent="Coordinate care task",
        trace_id="trace-001",
        grounding=projection_to_dict(projection),
    )
    sketch = SketchResult(
        rough_steps=[RoughStep(intent="Find available slot", suggested_capability=None)],
        capability_candidates=[],
        rationale="test",
    )

    content = ExpandService(cast(Any, object()), cast(Any, object()))._build_initial_messages(
        sketch,
        request,
    )[1]["content"]

    assert "== PLANNING GROUNDING ==" in content
    assert projection.envelope_id in content
