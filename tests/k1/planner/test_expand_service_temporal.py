"""Tests for EXPAND temporal context boundaries."""

from __future__ import annotations

from k1.orchestrator.types import PlanRequest
from k1.planner.stages.expand_service import EXPAND_TOOL_DEFINITIONS, ExpandService
from k1.planner.types import RoughStep, SketchResult


def test_query_session_context_tool_does_not_offer_control() -> None:
    tool = [t for t in EXPAND_TOOL_DEFINITIONS if t["function"]["name"] == "query_session_context"][
        0
    ]
    desc = tool["function"]["parameters"]["properties"]["sections"]["description"]
    assert "'temporal'" in desc
    assert "'control'" not in desc


def test_expand_initial_message_ignores_legacy_temporal_constraints() -> None:
    svc = ExpandService(llm_port=object(), tool_router=object())  # type: ignore[arg-type]
    sketch = SketchResult(
        rough_steps=[RoughStep(intent="create reminder")],
        rationale="test",
        capability_candidates=[],
    )
    request = PlanRequest(
        intent="remind me tomorrow",
        trace_id="trace-1",
        constraints={
            "temporal": {
                "anchor_id": "anchor-1",
                "now_utc": "2025-03-09T09:30:00+00:00",
                "timezone": "America/Los_Angeles",
                "today": {
                    "start_local": "2025-03-09T00:00:00-08:00",
                    "end_local": "2025-03-10T00:00:00-07:00",
                },
                "tomorrow": {
                    "start_local": "2025-03-10T00:00:00-07:00",
                    "end_local": "2025-03-11T00:00:00-07:00",
                },
                "resolved_expressions": [{"raw_text": "tomorrow", "normalized_label": "tomorrow"}],
            }
        },
    )

    user_message = svc._build_initial_messages(sketch, request)[1]["content"]
    assert "anchor_id: anchor-1" not in user_message
    assert "today: 2025-03-09T00:00:00-08:00 -> 2025-03-10T00:00:00-07:00" not in user_message
    assert "tomorrow: tomorrow" not in user_message
    assert "== PLANNING GROUNDING ==" not in user_message
    assert "Current time:" not in user_message
