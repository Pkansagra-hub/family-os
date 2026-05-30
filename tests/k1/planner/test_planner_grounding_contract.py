"""Focused E5 tests for typed planner grounding inputs."""

from __future__ import annotations

from typing import Any, cast

from k1.grounding.factory import GroundingFactory
from k1.grounding.serialization import projection_to_dict
from k1.orchestrator.types import PlanRequest
from k1.planner.stages.sketch_service import SketchService
from k1.planner.types import RoughStep, SketchResult


async def _projection_dict() -> dict:
    bundle = GroundingFactory.create_standalone()
    projection = await bundle.service.build_projection("s1", consumer="planner", turn_id="t1")
    return projection_to_dict(projection)


def _sketch_result() -> SketchResult:
    return SketchResult(
        rough_steps=[RoughStep(intent="Find appointment availability", suggested_capability=None)],
        capability_candidates=[],
        rationale="SKETCH rationale",
    )


async def test_sketch_uses_typed_grounding_not_temporal_constraints() -> None:
    grounding = await _projection_dict()
    svc = SketchService(cast(Any, object()), cast(Any, object()), cast(Any, object()))

    messages = svc._build_initial_messages(
        intent="Book time with the care team",
        constraints={
            "safety_band": "GREEN",
            "temporal": {"now": "SHOULD_NOT_RENDER", "device_tz": "SHOULD_NOT_RENDER"},
        },
        grounding=grounding,
    )

    user_content = messages[1]["content"]
    assert "== PLANNING GROUNDING ==" in user_content
    assert "SHOULD_NOT_RENDER" not in user_content


async def test_expand_uses_typed_grounding_not_temporal_constraints() -> None:
    grounding = await _projection_dict()
    from k1.planner.stages.expand_service import ExpandService

    svc = ExpandService(cast(Any, object()), cast(Any, object()))
    request = PlanRequest(
        intent="Book time with the care team",
        trace_id="trace-001",
        constraints={"temporal": {"now_utc": "SHOULD_NOT_RENDER"}},
        grounding=grounding,
    )

    user_content = svc._build_initial_messages(_sketch_result(), request)[1]["content"]
    assert "== PLANNING GROUNDING ==" in user_content
    assert "SHOULD_NOT_RENDER" not in user_content
