"""Focused E4 grounding propagation tests for Concierge dispatch payloads."""

from __future__ import annotations

from k1.concierge.task.dispatch import TaskDispatch, TaskIntent


def test_task_dispatch_round_trips_grounding_fields_and_reference_context() -> None:
    dispatch = TaskDispatch(
        intents=[TaskIntent(action="search", params={})],
        grounding_envelope_id="env-1",
        temporal_anchor_id="ta-1",
        spatial_context_id="unknown",
        resolved_temporal_refs={"tomorrow": "2026-05-22"},
        resolved_spatial_refs={"unknown": "Unknown place"},
        grounding={"projection_id": "proj-1"},
    )

    payload = dispatch.to_dict()
    restored = TaskDispatch.from_dict(payload)

    assert payload["grounding_envelope_id"] == "env-1"
    assert payload["resolved_temporal_refs"] == {"tomorrow": "2026-05-22"}
    assert payload["grounding"] == {"projection_id": "proj-1"}
    assert restored.reference_context["grounding_envelope_id"] == "env-1"
    assert restored.reference_context["grounding"]["spatial_context_id"] == "unknown"
