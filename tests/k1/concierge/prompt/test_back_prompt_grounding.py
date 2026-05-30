"""M2-E2: Back prompt consumes resolved temporal refs before date_calc."""

from __future__ import annotations

from k1.concierge.prompt.back_prompt import build_back_prompt


def _tomorrow_ref() -> dict[str, object]:
    return {
        "raw_text": "tomorrow",
        "normalized_label": "tomorrow",
        "resolution_kind": "window",
        "window": {
            "label": "tomorrow",
            "start_local": "2025-01-16T00:00:00+00:00",
            "end_local": "2025-01-17T00:00:00+00:00",
            "start_utc": "2025-01-16T00:00:00+00:00",
            "end_utc": "2025-01-17T00:00:00+00:00",
            "timezone": "UTC",
            "granularity": "day",
        },
        "instant_local": None,
        "recurrence_rule": None,
        "confidence": 1.0,
        "needs_clarification": False,
        "clarification_reason": None,
    }


def test_back_prompt_renders_resolved_temporal_refs_in_execution_grounding() -> None:
    prompt = build_back_prompt(
        task={
            "task_id": "task-m2",
            "tier": "LOW",
            "intents": [{"action": "check calendar", "params": {"date": "tomorrow"}}],
            "resolved_temporal_refs": {"tomorrow": _tomorrow_ref()},
        },
        max_tool_calls=4,
    )

    assert "== EXECUTION GROUNDING ==" in prompt
    assert "resolved_temporal_refs_typed:" in prompt
    assert "tomorrow (window)" in prompt
    assert "2025-01-16T00:00:00+00:00" in prompt
