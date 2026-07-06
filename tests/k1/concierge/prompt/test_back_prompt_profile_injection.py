from __future__ import annotations

from k1.concierge.prompt.back_prompt import build_back_prompt


def test_back_prompt_injects_execution_profile_narrative_in_situational_context() -> None:
    block = "This task matches the 'Family Calendar' operating profile (calendar.v1)."
    prompt = build_back_prompt(
        task={"task_id": "task-1", "tier": "LOW", "action": "create event"},
        safety_band="AMBER",
        max_tool_calls=6,
        execution_profile_block=block,
    )

    assert block in prompt
    # Profile narrative lives in SITUATIONAL CONTEXT, before the protocol.
    assert prompt.index("== SITUATIONAL CONTEXT ==") < prompt.index(block)
    assert prompt.index(block) < prompt.index("== EXECUTION PROTOCOL ==")


def test_back_prompt_empty_execution_profile_renders_default_prose() -> None:
    prompt = build_back_prompt(
        task={"task_id": "task-1", "tier": "LOW", "action": "recall routine"},
        safety_band="AMBER",
        max_tool_calls=6,
        execution_profile_block="",
    )

    # Empty profile renders an explicit absence statement, not a blank.
    assert "No domain operating profile matched this task" in prompt
    assert "STEP 1 -- RESOLVE" in prompt
    assert "== TOOL REFERENCE ==" in prompt
