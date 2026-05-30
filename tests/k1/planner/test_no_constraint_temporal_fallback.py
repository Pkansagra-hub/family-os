"""M1.5-E5: Planner no longer injects temporal data from constraints."""

from __future__ import annotations

from typing import Any, cast

from k1.orchestrator.types import PlanRequest
from k1.planner.stages.expand_service import ExpandService
from k1.planner.stages.sketch_service import SketchService
from k1.planner.types import RoughStep, SketchResult


def test_sketch_ignores_temporal_constraint_fallback() -> None:
    content = SketchService(
        cast(Any, object()),
        cast(Any, object()),
        cast(Any, object()),
    )._build_initial_messages(
        intent="Coordinate care task",
        constraints={"temporal": {"now": "SHOULD_NOT_RENDER", "device_tz": "NOPE"}},
    )[
        1
    ][
        "content"
    ]

    assert "SHOULD_NOT_RENDER" not in content
    assert "NOPE" not in content


def test_expand_ignores_temporal_constraint_fallback() -> None:
    request = PlanRequest(
        intent="Coordinate care task",
        trace_id="trace-001",
        constraints={"temporal": {"now_utc": "SHOULD_NOT_RENDER"}},
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

    assert "SHOULD_NOT_RENDER" not in content
