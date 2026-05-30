"""M4.I6: Front deloading Iteration 1 prompt contract guards."""

from __future__ import annotations

from pathlib import Path

from k1.concierge.prompt.affect import AffectBand
from k1.concierge.prompt.builder import DynamicPromptBuilder
from k1.concierge.prompt.mode import PromptMode

ROOT = Path(__file__).resolve().parents[4]
WHITEBOARD = ROOT / "whiteboard_front_deloading.md"

COGNITIVE_WRITE_TOOL_NAMES = (
    "update_beliefs",
    "update_scoreboard",
    "update_clarifications",
    "update_narrative",
    "refine_affect",
    "promote_belief",
    "update_session_bundle",
)


def _whiteboard_text() -> str:
    return WHITEBOARD.read_text(encoding="utf-8")


def _fenced_text_after(text: str, marker: str) -> str:
    start = text.index(marker)
    fence_start = text.index("```text\n", start) + len("```text\n")
    fence_end = text.index("```", fence_start)
    return text[fence_start:fence_end]


def _iteration_target_prompt(text: str) -> str:
    return _fenced_text_after(text, "Iteration 1 target prompt template:")


def _iteration_actual_prompt(text: str) -> str:
    return _fenced_text_after(text, "Actual Iteration 1 prompt:")


def test_iteration_1_contract_does_not_name_front_cognitive_write_tools() -> None:
    text = _whiteboard_text()
    prompts = (_iteration_target_prompt(text), _iteration_actual_prompt(text))

    for prompt in prompts:
        for tool_name in COGNITIVE_WRITE_TOOL_NAMES:
            assert tool_name not in prompt
        assert "SectionUpdateClassifier" not in prompt
        assert "Hidden cognitive SessionState writes are not Front tools" in prompt
        assert "The completed-turn updater records hidden cognitive state" in prompt


def test_actual_iteration_1_prompt_preserves_m4i5_source_seating_order() -> None:
    prompt = _iteration_actual_prompt(_whiteboard_text())

    expected_order = [
        "== FRONT ROLE CONTRACT ==",
        "== FRONT SITUATION FRAME ==",
        "-- INJECT: ACTIVE ACTOR --",
        "-- INJECT: VISIBLE SPACE --",
        "-- INJECT: CONSCIENCE / POLICY --",
        "-- INJECT: NOW --",
        "-- INJECT: PLACE --",
        "-- INJECT: DYNAMIC IDENTITY CONTEXT --",
        "-- INJECT: REFERENCE PROFILE --",
        "-- INJECT: AFFECTIVE POSTURE --",
        "-- INJECT: INTERACTION PROFILE --",
        "-- INJECT: CONVERSATION STATE --",
        "-- INJECT: ACTIVE WORK --",
        "-- INJECT: MEMORY AND AUTHORITY BOUNDARY --",
        "== CURRENT EVENT ==",
        "== TOOL CONTRACT ==",
        "== RESPONSE BEHAVIOR ==",
    ]

    positions = [prompt.index(marker) for marker in expected_order]
    assert positions == sorted(positions)


def test_iteration_1_tool_contract_keeps_read_and_action_surface() -> None:
    prompt = _iteration_actual_prompt(_whiteboard_text())

    for tool_name in (
        "recall_memory",
        "summarize_context",
        "dispatch_task",
        "discover_capabilities",
        "invoke_capability",
    ):
        assert tool_name in prompt

    assert "Do not call, request, or simulate hidden state writes from Front" in prompt
    assert "Do not mutate beliefs_active, scoreboard, clarifications" in prompt
    assert "Do not invent state" in prompt


def test_runtime_prompt_text_no_longer_instructs_front_cognitive_writes() -> None:
    for mode in PromptMode:
        built = DynamicPromptBuilder().build(
            mode=mode,
            affect_band=AffectBand("neutral"),
            history_messages=[],
            all_tool_schemas=[],
            scenario_data={"open_gaps_list": "(none)"},
            affect_confidence=0.0,
            tier="HIGH",
        )
        prompt = built.system_prompt
        for tool_name in COGNITIVE_WRITE_TOOL_NAMES:
            assert tool_name not in prompt, (mode, tool_name)
        assert "SectionUpdateClassifier" not in prompt


def test_runtime_prompt_keeps_iteration_1_front_job_surface() -> None:
    prompt = (
        DynamicPromptBuilder()
        .build(
            mode=PromptMode.STANDARD,
            affect_band=AffectBand("neutral"),
            history_messages=[],
            all_tool_schemas=[],
            scenario_data={},
        )
        .system_prompt
    )

    expected_order = [
        "== FRONT ROLE CONTRACT ==",
        "== FRONT SITUATION FRAME ==",
        "-- INJECT: ACTIVE ACTOR --",
        "-- INJECT: VISIBLE SPACE --",
        "-- INJECT: CONSCIENCE / POLICY --",
        "-- INJECT: NOW --",
        "-- INJECT: PLACE --",
        "-- INJECT: DYNAMIC IDENTITY CONTEXT --",
        "-- INJECT: REFERENCE PROFILE --",
        "-- INJECT: AFFECTIVE POSTURE --",
        "-- INJECT: INTERACTION PROFILE --",
        "-- INJECT: CONVERSATION STATE --",
        "-- INJECT: ACTIVE WORK --",
        "-- INJECT: MEMORY AND AUTHORITY BOUNDARY --",
        "== CURRENT EVENT ==",
        "== TOOL CONTRACT ==",
        "== RESPONSE BEHAVIOR ==",
    ]
    positions = [prompt.index(marker) for marker in expected_order]
    assert positions == sorted(positions)

    assert "== STATE CONSUMPTION DISCIPLINE ==" in prompt
    assert "Hidden cognitive state mutation happens outside Front" in prompt
    assert "Hidden cognitive SessionState writes are not Front tools" in prompt
    assert "recall_memory" in prompt
    assert "dispatch_task" in prompt
    assert "discover_capabilities" in prompt
    assert "invoke_capability" in prompt
    assert "Live system-of-record state is always work" in prompt
