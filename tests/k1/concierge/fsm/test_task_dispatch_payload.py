"""Task dispatch payload compatibility tests."""

from __future__ import annotations

from k1.concierge.fsm.controller import _task_dispatch_from_payload


def test_task_dispatch_payload_ignores_legacy_temporal_clarification_keys() -> None:
    dispatch = _task_dispatch_from_payload(
        {
            "task_id": "task-legacy-temporal",
            "intents": [
                {
                    "action": "add event to calendar",
                    "params": {"title": "dentist", "time": "tomorrow 1:30 PM"},
                }
            ],
            "tier": "LOW",
            "safety_band": "GREEN",
            "requires_temporal_clarification": True,
            "temporal_clarification_reasons": {"tomorrow": "ambiguous"},
            "resolved_temporal_refs": {"tomorrow": {"resolution_kind": "ambiguous"}},
        }
    )

    payload = dispatch.to_dict()

    assert not hasattr(dispatch, "requires_temporal_clarification")
    assert not hasattr(dispatch, "temporal_clarification_reasons")
    assert "requires_temporal_clarification" not in payload
    assert "temporal_clarification_reasons" not in payload
    assert payload["resolved_temporal_refs"] == {
        "tomorrow": {"resolution_kind": "ambiguous"}
    }