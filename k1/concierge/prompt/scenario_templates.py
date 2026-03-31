"""
k1.concierge.prompt.scenario_templates -- Mode-specific scenario data templates.

V2 Design Ref: Section 6.1 (Scenario Data Templates)

Mode-specific payload data formatted by _extract_scenario_data() and
appended to the assembled prompt. These carry task results, HITL requests,
error details, and other context the LLM needs for a specific mode trigger.

Only modes with dynamic payload data have non-empty templates.
Empty-template modes derive all context from SS sections and chat history.

Exports:
  - SCENARIO_DATA_TEMPLATES: Mode -> format template string with {placeholders}
"""

from __future__ import annotations

from k1.concierge.prompt.mode import PromptMode

# =========================================================================
# SCENARIO_DATA_TEMPLATES -- Mode -> format template string
# =========================================================================
# DynamicPromptBuilder fills {placeholders} from envelope payload + SS data
# via _format_scenario_data(). Authoritative source: V2 Design Doc Section 6.1.
#
# 6 modes have non-empty templates: PRESENT, WEAVE, HITL_RELAY, HITL_RESOLVE,
# ERROR, CANCEL.
# 4 modes have empty templates: STANDARD, CLARIFY_ASK, CLARIFY_RESOLVE,
# INTERRUPT.

SCENARIO_DATA_TEMPLATES: dict[PromptMode, str] = {
    PromptMode.STANDARD: (
        "== YOUR FAMILY ==\n"
        "You are talking to: {active_member}\n"
        "{family_context}\n"
        "{async_results_context}"
    ),
    # Family context only. Memories come from recall_memory tool calls.
    # async_results_context is populated when background tasks completed
    # since the user's last turn -- Front should weave them naturally into
    # the response like a human saying "oh, about that thing you asked..."
    PromptMode.PRESENT: (
        "== TASK RESULT TO PRESENT ==\n"
        "Task: {task_description}\n"
        "Result: {task_result_summary}\n"
        "Artifacts created: {artifacts}\n"
        "Present this result naturally. Do not dispatch.\n"
        "Go directly to cognitive tools (if needed) then text response.\n"
    ),
    PromptMode.WEAVE: (
        "== ASYNC RESULTS ARRIVED ==\n"
        "Priority: {urgency_label}\n"
        "Emotional guidance: {emotional_context}\n"
        "While you were chatting with the user, {result_count} background "
        "task(s) completed:\n"
        "{results_summary}\n"
        "The user's last message was about: {current_thread}\n"
        "Respond to user's topic FIRST, then naturally transition to the "
        "async results.\n"
    ),
    PromptMode.HITL_RELAY: (
        "== WORKER NEEDS USER INPUT ==\n"
        "A background task is paused waiting for the user's answer.\n"
        "Here is the structured request (DO NOT show this to the user):\n"
        "  type: {hil_type}\n"
        "  question: {hil_question}\n"
        "  options: {hil_options}\n"
        "  side_effects: {hil_side_effects}\n\n"
        "YOUR JOB: Rephrase the above into a warm, natural question in YOUR voice.\n"
        "NEVER output the raw fields, brackets, labels, or structured data above.\n"
        "NEVER write '[HIL Request]', 'Type:', 'Question:', 'Options:', or 'Side effects:'.\n"
        "NEVER mention 'task suspended', 'worker', or internal system details.\n"
        "For approval: state what will happen and ask if they want to proceed.\n"
        "For selection: present choices conversationally, not as a numbered list.\n"
        "For clarification/escalation: ask naturally, as if you're curious.\n"
        "Match tone to affective_now. Respond with text only.\n"
    ),
    PromptMode.HITL_RESOLVE: (
        "== USER ANSWERED HITL QUESTION ==\n"
        "The suspended task: {suspended_task_summary}\n"
        "Original question: {original_question}\n"
        "User's answer: {user_answer}\n"
        "Parse their answer. Confirm to user what will happen.\n"
    ),
    PromptMode.ERROR: (
        "== TASK FAILED ==\n"
        "Task: {task_description}\n"
        "Reason: {failure_reason}\n"
        "Partial results: {partial_results}\n"
        "Explain gracefully. If partial results exist, present what WAS found.\n"
        "If transient, suggest trying again. If cancelled, just confirm.\n"
        "Do not show error codes.\n"
    ),
    PromptMode.CANCEL: (
        "== CANCELLATION ==\n"
        "Task to cancel: {task_id} ({task_action})\n"
        "Current status: {task_status}\n"
        "Confirm the cancellation. Close the narrative thread.\n"
        "If the task already completed despite the cancel, present results with "
        '"it actually went through" framing.\n'
    ),
    PromptMode.CLARIFY_ASK: "",
    # Clarification context comes from SS clarifications section directly.
    # Depth-specific block is injected separately via CLARIFY_DEPTH_BLOCKS.
    PromptMode.CLARIFY_RESOLVE: "",
    # User's answer is in messages array. SS clarifications shows what was asked.
    PromptMode.INTERRUPT: (
        "== YOUR FAMILY ==\n"
        "You are talking to: {active_member}\n"
        "{family_context}\n"
        "{async_results_context}"
    ),
    # Family context only. Memories come from recall_memory tool calls.
}
