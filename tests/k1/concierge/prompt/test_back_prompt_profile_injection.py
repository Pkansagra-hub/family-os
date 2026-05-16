from __future__ import annotations

from k1.concierge.prompt.back_prompt import build_back_prompt


def test_back_prompt_injects_execution_profile_block_before_tool_rules() -> None:
    block = "== EXECUTION PROFILES ==\n- calendar.v1: Calendar guidance"
    prompt = build_back_prompt(
        task={"task_id": "task-1", "tier": "LOW", "action": "create event"},
        safety_band="AMBER",
        max_tool_calls=6,
        execution_profile_block=block,
    )

    assert block in prompt
    assert prompt.index("== EXECUTION PROFILES ==") < prompt.index("STEP 1 -- ORIENT")
    assert prompt.index("STEP 1 -- ORIENT") < prompt.index("== TOOL SELECTION RULES ==")


def test_back_prompt_empty_execution_profile_block_keeps_existing_shape() -> None:
    prompt = build_back_prompt(
        task={"task_id": "task-1", "tier": "LOW", "action": "recall routine"},
        safety_band="AMBER",
        max_tool_calls=6,
        execution_profile_block="",
    )

    assert "== EXECUTION PROFILES ==" not in prompt
    assert "STEP 1 -- ORIENT" in prompt
    assert "== TOOL SELECTION RULES ==" in prompt
