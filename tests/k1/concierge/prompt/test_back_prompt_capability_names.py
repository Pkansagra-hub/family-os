from __future__ import annotations

from k1.concierge.prompt.back_prompt import build_back_prompt
from k1.concierge.prompt.mode import PromptMode
from k1.concierge.prompt.sections import MODE_SECTIONS, PROMPT_SECTIONS


def test_back_prompt_uses_registry_owned_capability_names() -> None:
    prompt = build_back_prompt(
        task={
            "task_id": "task-1",
            "tier": "LOW",
            "intents": [{"action": "create a calendar event and reminder"}],
            "safety_band": "AMBER",
        },
        safety_band="AMBER",
        max_tool_calls=6,
    )

    assert "invoke_capability(capability_name=<name>" in prompt
    assert "tool.execute.calendar.create_event" in prompt
    assert "tool.execute.reminders.create_reminder" in prompt
    assert "tool.execute.send_reminder" not in prompt
    assert "tool.execute.set_alarm" not in prompt
    assert "tool.execute.calendar.create_reminder" not in prompt


def test_back_prompt_describes_domain_agnostic_semantic_envelope() -> None:
    prompt = build_back_prompt(
        task={"task_id": "task-1", "tier": "LOW", "action": "schedule appointment"},
        safety_band="AMBER",
        max_tool_calls=6,
    )

    assert "semantic_context" in prompt
    assert "future_weave" in prompt
    assert "authority" in prompt
    assert "requires_external_authority" in prompt
    assert "Do NOT fabricate specialized requirements" in prompt


def test_prompts_route_existing_artifact_note_updates_without_domain_shortcuts() -> None:
    front_rules = PROMPT_SECTIONS["DISPATCH_RULES"]
    assert "Follow-up changes to existing artifacts" in front_rules
    assert "dispatch an UPDATE for that" in front_rules
    assert "Do NOT turn it into a generic search" in front_rules
    assert "general_context_to_add" in front_rules

    back_prompt = build_back_prompt(
        task={"task_id": "task-1", "tier": "LOW", "action": "update record notes"},
        safety_band="AMBER",
        max_tool_calls=6,
    )
    assert "add/attach/include/update notes" in back_prompt
    assert "Treat the target record as system-of-record work" in back_prompt
    assert "Do NOT search an unrelated domain" in back_prompt


def test_front_modes_include_native_intelligence_after_identity() -> None:
    native = PROMPT_SECTIONS["NATIVE_INTELLIGENCE"]
    assert "You are not a blank router" in native
    assert "broad general-world knowledge" in native
    assert "what you know" in native
    assert "general context, not verified instructions" in native

    for mode in PromptMode:
        keys = MODE_SECTIONS[mode]
        assert "NATIVE_INTELLIGENCE" in keys
        assert keys.index("NATIVE_INTELLIGENCE") == keys.index("IDENTITY") + 1


def test_back_prompt_marks_native_knowledge_as_general_provenance() -> None:
    prompt = build_back_prompt(
        task={"task_id": "task-1", "tier": "LOW", "action": "add general context"},
        safety_band="AMBER",
        max_tool_calls=6,
    )

    assert "Built-in knowledge" in prompt
    assert "source=model_general_knowledge" in prompt
    assert "guidance_scope=general" in prompt
    assert "Do not present model knowledge as verified instructions" in prompt


def test_back_prompt_never_asks_for_family_member_ids() -> None:
    prompt = build_back_prompt(
        task={
            "task_id": "task-1",
            "tier": "LOW",
            "intents": [{"action": "create task", "params": {"assignee": "Riley"}}],
        },
        safety_band="GREEN",
        max_tool_calls=6,
    )

    assert "FAMILY MEMBER REFERENCES" in prompt
    assert "Do NOT ask the user for a member ID" in prompt
    assert "Riley -> ``riley``" in prompt
