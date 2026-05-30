"""M1.5-E4: TaskDispatch grounding propagation fields."""

from __future__ import annotations

from k1.concierge.task.dispatch import TaskDispatch, TaskIntent


def test_dispatch_serializes_grounding_fields_and_mirrors_reference_context() -> None:
    dispatch = TaskDispatch(
        intents=[TaskIntent(action="do_work", params={})],
        grounding_envelope_id="env-1",
        temporal_anchor_id="ta-1",
        spatial_context_id="unknown",
        resolved_temporal_refs={"tomorrow": "2026-05-22"},
        resolved_spatial_refs={"unknown": "Unknown place"},
    )

    payload = dispatch.to_dict()
    restored = TaskDispatch.from_dict(payload)

    assert restored.grounding_envelope_id == "env-1"
    assert restored.resolved_temporal_refs == {"tomorrow": "2026-05-22"}
    reference_context = restored.reference_context
    assert reference_context is not None
    assert reference_context["temporal_anchor_id"] == "ta-1"
    assert reference_context["grounding"]["spatial_context_id"] == "unknown"
