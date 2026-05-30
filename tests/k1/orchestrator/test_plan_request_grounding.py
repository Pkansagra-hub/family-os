"""M1.5-E4: Orchestrator typed grounding payload propagation."""

from __future__ import annotations

from k1.orchestrator.types import PlanRequest, TaskEnvelope


def test_plan_request_round_trips_grounding_payload() -> None:
    request = PlanRequest(
        intent="Coordinate care task",
        trace_id="trace-001",
        grounding={"projection_id": "proj-1", "envelope_id": "env-1"},
    )

    restored = PlanRequest.from_dict(request.to_dict())

    assert restored.grounding == {"projection_id": "proj-1", "envelope_id": "env-1"}


def test_task_envelope_accepts_grounding_payload() -> None:
    envelope = TaskEnvelope(
        intent="Coordinate care task",
        trace_id="trace-001",
        tier="MEDIUM",
        capabilities=["test.capability"],
        grounding={"projection_id": "proj-1"},
    )

    assert envelope.grounding == {"projection_id": "proj-1"}
