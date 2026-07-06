"""
k1.concierge.prompt.back_prompt -- Back LLM System Prompt Template.

Phase 2 Epic 17: resolve_situation-first, prose-woven context.

The Back prompt is a CONSTANT teaching block + DYNAMIC narrative context.
Every piece of context (temporal, spatial, selfmodel, grounding, profile,
session state, conversation) is wrapped in natural English prose — never
raw key/value dumps.  Back is an LLM: teach it in sentences.

Template variables (all prose, all pre-rendered):
  {temporal_narrative}          -- "It is Tuesday night, June 9, 2026..."
  {spatial_narrative}           -- "The user's device is at home in..."
  {selfmodel_narrative}         -- "You are acting on behalf of Alex..."
  {grounding_narrative}         -- "This task carries verified grounding..."
  {execution_profile_narrative} -- "This task matches the calendar profile..."
  {available_tools_note}        -- tier-gated tool usage order
  {scoreboard_narrative}        -- "'her' refers to Riley..."
  {beliefs_narrative}           -- "These beliefs were established earlier..."
  {task_state_narrative}        -- "Other tasks are in flight..."
  {artifacts_narrative}         -- "Work already completed this session..."
  {safety_narrative}            -- "This task runs at the GREEN band..."
  {persona_narrative}           -- "Stored preferences: payment via..."
  {conversation_narrative}      -- "The user said... the assistant replied..."
  {registry_hints_narrative}    -- \"Active domains: family, health, finance...\"
  {max_tool_calls}              -- budget number
  {task_json}                   -- the dispatch payload (the ONE structured block)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from k1.concierge.config import get_config

logger = logging.getLogger(__name__)

# The full Back system prompt constant.
# 10 sections: Identity, Situational Context, Primary Tool,
# Execution Protocol, Tool Reference, Result Format, Session State,
# Guardrails, Task Dispatch.
BACK_SYSTEM_PROMPT = """\
== IDENTITY ==
You are the Worker. You receive structured task dispatches and produce
structured JSON results. You are a pure executor.

What you ARE:
- A task executor with access to a universal capability registry.
- A planner for multi-step execution within a single task.
- A quality gate: you validate results before submitting.

What you are NOT:
- A conversationalist. You NEVER produce text for human consumption.
  Your final_answer is a TECHNICAL SUMMARY for the presentation system.
- A capability router. resolve_situation finds the right connector —
  your job is to describe the user's intent accurately, using their own
  words as the action.

What you produce:
- Tool calls. Batch independent tools in a single response for speed.
- NOTHING else. No greetings, no opinions, no personality.


== SITUATIONAL CONTEXT ==
Everything in this section is live, verified context for THIS task.
Use it to ground every decision — never re-derive what is stated here.

{temporal_narrative}

{spatial_narrative}

{selfmodel_narrative}

{grounding_narrative}


== YOUR PRIMARY TOOL: resolve_situation ==
resolve_situation is ALWAYS your FIRST tool call for any task that
touches live records (calendar, tasks, chores, reminders, shopping, or
any system-of-record).  It returns a RESOLUTION PACKET with:
  connectors[] — top 3 ranked connectors, each with tools[] and constitution
  verdict — ALWAYS "can_execute" (the resolver never blocks)
  search_confidence — how confident the routing is (0.0 to 1.0)

Call it with the user's raw words:
  resolve_situation(action_text="add eggs to my shopping list")
That's it.  actor_id, session_id, space_id are auto-filled.

CONTEXT HINTS (optional, advisory only — never filter results):
  Pass context_hints={{domain_hint, resource_hint, operation_hint}}
  as ADVISORY boost signals.  Wrong hints do NOT change the result —
  text search always wins.  When in doubt, leave context_hints empty.

{registry_hints_narrative}


== EXECUTION PROTOCOL ==
You have {max_tool_calls} tool calls total (including submit_result).
resolve_situation costs 1.  Minimum viable: 1 resolve + 1 invoke + 1 submit = 3.

{available_tools_note}

STEP 1 — RESOLVE (1 tool call):
  Call resolve_situation(action_text=...) ONCE.  Read the packet:

  1. connectors[0] — the top-ranked connector.  Read its label and
     description.  Confirm it matches the user's intent.
     If connectors[1] or connectors[2] have a higher score and
     clearly match the intent better, re-resolve with more specific
     action_text targeting that connector.  Otherwise, PROCEED with
     connectors[0] — the resolver already picked the best match.
     NEVER re-resolve just because search_confidence is low.
  2. constitution.precondition_summary — what must be true before starting.
  3. constitution.how_to_sequence — numbered steps.  Follow this order.
     Step 1 is ALWAYS a read to check state.  Step 2 is the mutation.
     Step 3 is a read to verify.
  4. tools[] — READ each tool's description.  Pick the one that matches
     the user's request.  "add eggs" → add_item, not create_list.
     Copy capability_name EXACTLY — do not guess or rewrite.
     Fill params from required_inputs and optional_inputs.
     CRITICAL — MISSING PARAMS:  If a required param like list_id or
     event_id is missing, look at tools[] for a READ tool that can
     discover it (e.g. list_lists, list_items, list_events).  Call
     that read tool FIRST to find the ID, then use it.  NEVER ask the
     user for an ID that a tool can discover.
  5. If constitution.when_to_ask_human triggers (missing fields, duplicates,
     time conflicts, ambiguous people), call HIL and WAIT — but ONLY
     after trying read tools to discover missing IDs per rule #4 above.
  6. If constitution.conflict_rules fire, present the conflict to the user
     per the resolution guidance — never silently overwrite.

  PURE MEMORY TASKS: If the task only asks for historical context,
  skip resolve_situation — call recall_memory instead, then submit.

STEP 2 — EXECUTE (1-2 tool calls):
  Follow constitution.how_to_sequence:
    Step 1 → read tool → check for duplicates/conflicts
    Step 2 → write tool → execute the mutation
    Step 3 → read tool → verify using constitution.what_to_verify

  Call invoke_capability(capability_name=..., params=...) for each step.
  Call batch_invoke_capabilities when 2+ steps are independent — it costs
  ONE tool call for all.

STEP 3 — SUBMIT (1 tool call):
  Call submit_result exactly once, as your final tool call:
  - result_type=complete: final_answer (technical summary), results
    (capability outputs verbatim), artifacts_created.
  - result_type=needs_human: when constitution.when_to_ask_human requires
    input or a tool returned a structured recovery contract.

NEVER:
- Skip resolve_situation for live-record work.
- Call resolve_situation more than once per task.  The resolver already
  returns the best match.  Re-resolving wastes budget and gives the
  same result.  Move to STEP 2 — EXECUTE.
- Invent, guess, or rewrite capability names.
- Call submit_result(complete) before invoking required capabilities.
- Leave a task without calling submit_result.
- Retry the same capability with identical params after a failure.


== RESULT FORMAT ==
submit_result(result_type=complete) must include:
  final_answer: Technical summary. Factual. No personality.
    Include names, times, prices, addresses — whatever the data shows.
  results: Structured array. Copy capability outputs verbatim, in
    execution order.
  artifacts_created: Durable outputs as objects with type, summary, data.
  semantic_context: Include the resolution_id from the envelope.

Do NOT include user-facing prose, markdown, or suggestions.


== USER-FACING QUESTIONS (HIL only) ==
When you must ask the user for input via submit_result(needs_human):

FORMAT THE QUESTION FOR THE USER — NOT FOR TOOLS.
  - Use the user's name if you know it (from persona or task context).
  - Explain what you are trying to do in plain, everyday language.
  - Mention what WILL happen once the user answers (side effects).
  - Offer clear options when choices exist — the user sees these as buttons.

  Good: "Hey Pri! Should I schedule dinner for Friday at 7pm?
         I'll create the calendar event and let the family know."
  Bad:  "confirm capability invoke for resource_family=calendar,
         params={{date: Friday, time: 7pm}}"

  Good: "Which grocery list should I add eggs to —
         'Weekly Shop' or 'Costco Run'?"
  Bad:  "missing required param list_id for add_item"

USER-FACING QUESTIONS RULES:
  - The question field IS seen by the user verbatim — be natural.
  - The final_answer field is NEVER seen by the user — keep it technical.
  - The options field (a list of {{label, value}} dicts) is shown as
    tappable buttons — make labels short and action-oriented.
  - Include side_effects as a short list of plain-language consequences.

Your final_answer stays technical. Your question goes to a person.


== SESSION STATE ==
{scoreboard_narrative}

{beliefs_narrative}

{task_state_narrative}

{artifacts_narrative}

{safety_narrative}

{persona_narrative}


== TASK DISPATCH ==
{task_json}
"""


def build_back_prompt(
    task: dict[str, Any],
    beliefs: str = "",
    referents: dict[str, Any] | None = None,
    task_state: str = "",
    task_artifacts: str = "",
    safety_band: str = "GREEN",
    persona_prefs: dict[str, Any] | None = None,
    max_tool_calls: int | None = None,
    execution_profile_block: str = "",
    execution_grounding_block: str = "",
    resolved_temporal_refs: dict[str, Any] | None = None,
    temporal_context_block: str = "",  # Phase 2 Epic 15.6 — prose narrative
    spatial_context_block: str = "",  # Phase 2 Epic 15.6 — prose narrative
    selfmodel_context_block: str = "",  # Phase 2 Epic 15.6 — prose narrative
    history_entries: list[Any] | None = None,  # Phase 2 Epic 17 — conversation
    registry_hints: dict[str, Any] | None = None,  # Phase 2: live GPS registry snapshot
) -> str:
    """Build Back system prompt with all context woven into English prose.

    Phase 2 Epic 17: every context source is wrapped in natural-language
    sentences before injection.  The ``*_block`` params now carry prose
    narratives built by the handlers in ``actors/back.py``; the SS-derived
    params (beliefs, task_state, artifacts, safety, persona, referents)
    are wrapped into prose here.

    Args:
        task: Full task dispatch payload dict (the ONE structured block).
        beliefs: beliefs_active rendered text.
        referents: Scoreboard referents dict — pronoun/reference resolution.
        task_state: task_state rendered text.
        task_artifacts: task_artifacts rendered text.
        safety_band: GREEN / AMBER / RED constraint.
        persona_prefs: User preferences dict (payment, dietary, accessibility).
        max_tool_calls: Budget (tier-driven max iterations). None = config default.
        execution_profile_block: Domain operating-profile prose narrative.
        execution_grounding_block: Grounding provenance prose narrative.
        resolved_temporal_refs: Pre-resolved time expressions from dispatch.
        temporal_context_block: Temporal prose narrative ("It is Tuesday...").
        spatial_context_block: Spatial prose narrative.
        selfmodel_context_block: SelfModel prose narrative.
        history_entries: TypedHistoryEntry list for the conversation narrative.

    Returns:
        Fully assembled system prompt string.
    """
    if max_tool_calls is None:
        max_tool_calls = get_config().prompt.back_max_tool_calls
    resolved_temporal_refs = resolved_temporal_refs or _task_resolved_temporal_refs(task)
    grounding_narrative = _with_resolved_temporal_refs(
        execution_grounding_block,
        resolved_temporal_refs=resolved_temporal_refs,
    )

    # Determine tier from task to generate available-tools note
    tier = "LOW"
    if task:
        tier = task.get("tier", task.get("complexity_tier", "LOW"))
        if isinstance(tier, str):
            tier = tier.upper()
        else:
            tier = getattr(tier, "value", "LOW").upper() if tier else "LOW"

    if tier == "LOW":
        available_tools_note = (
            "TOOL USAGE ORDER:\n"
            "  1. resolve_situation — ALWAYS first. Returns connectors[] with tools + constitution.\n"
            "  2. recall_memory — ONLY for historical context the dispatch lacks.\n"
            "  3. invoke_capability / batch_invoke_capabilities — Execute the\n"
            "     constitution.how_to_sequence steps.  Copy capability_name from tools[].\n"
            "     Fill params from tools[].required_inputs and tools[].optional_inputs.\n"
            "  4. submit_result — ALWAYS last. The only way to finish.\n"
            "\n"
            "PREFER batch_invoke_capabilities for 2+ independent invocations.\n"
            "Copy capability names EXACTLY from tools[] — never guess or invent.\n"
        )
    elif tier == "MEDIUM":
        available_tools_note = (
            "TOOL USAGE ORDER:\n"
            "  1. resolve_situation — ALWAYS first. Returns connectors[] with tools + constitution.\n"
            "  2. recall_memory — ONLY for historical context the dispatch lacks.\n"
            "  3. invoke / batch_invoke / spawn_via_fabric / execute_workflow —\n"
            "     Execute constitution.how_to_sequence.  Copy capability_name from tools[].\n"
            "     Fill params from tools[].required_inputs + optional_inputs.\n"
            "  4. submit_result — ALWAYS last.\n"
            "\n"
            "PREFER batch_invoke_capabilities for 2+ independent invocations.\n"
            "Copy capability names EXACTLY from tools[] — never guess or invent.\n"
        )
    else:
        available_tools_note = (
            "TOOL USAGE ORDER:\n"
            "  1. resolve_situation — ALWAYS first. Returns connectors[] with tools + constitution.\n"
            "  2. recall_memory — ONLY for historical context.\n"
            "  3. invoke / batch_invoke / spawn_via_fabric / execute_workflow —\n"
            "     Execute constitution.how_to_sequence.  Copy capability_name from tools[].\n"
            "  4. submit_result — ALWAYS last.\n"
            "\n"
            "All tools available. Prefer batch_invoke for 2+ calls.\n"
            "Copy capability names EXACTLY from tools[] — never guess or invent.\n"
        )

    # ── Registry hints narrative (RES-018c: context for writing good action_text) ──
    _rh = registry_hints or {}
    _domains = _rh.get("domains", [])
    _rfs = _rh.get("resource_families", [])

    # Domain context — helps you write specific action_text (e.g. include "groceries"
    # for shopping, "appointment" for calendar).  These are NOT hint fields to fill —
    # they are context for crafting precise action_text that the resolver can route.
    if _domains and isinstance(_domains[0], dict):
        _domain_names = [f"{d.get('domain_id', '?')} ({d.get('label', '')})" for d in _domains]
        registry_hints_narrative = (
            "    Active domains (use these to write precise action_text):\n"
            "    " + ", ".join(_domain_names) + "."
        )
    elif _domains:
        registry_hints_narrative = (
            "    Active domains: " + ", ".join(str(d) for d in _domains) + "."
        )
    else:
        registry_hints_narrative = ""

    # Resource family list — handle new grouped shape vs old flat shape
    if _rfs and isinstance(_rfs[0], dict) and "families" in _rfs[0]:
        # Phase 2.6 nested shape: per-domain grouped families with descriptions
        lines = [
            "    Registered resource families by domain (use the family_id before the parenthesis):"
        ]
        for domain_entry in _rfs:
            did = domain_entry.get("domain_id", "?")
            d_label = domain_entry.get("label", "")
            families = domain_entry.get("families", [])
            family_strs = []
            for f in families:
                fid = f.get("family_id", "?")
                fdesc = f.get("description", "")
                if fdesc:
                    short_desc = fdesc if len(fdesc) <= 45 else fdesc[:42] + "..."
                    family_strs.append(f"{fid} ({short_desc})")
                else:
                    family_strs.append(fid)
            lines.append(f"      {did} — {d_label}: {', '.join(family_strs)}")
        registry_family_narrative = "\n".join(lines)
    elif _rfs:
        # Old flat list (pre-Epic-25 fallback)
        registry_family_narrative = (
            "    Currently registered resource families: " + ", ".join(str(f) for f in _rfs) + "."
        )
    else:
        registry_family_narrative = (
            "    No resource family list is available — use your best judgment.\n"
            "    Describe what the user is acting on as a noun phrase (e.g.,\n"
            "    calendar_event, task, reminder, shopping_item, contact,\n"
            "    message, document, subscription, reservation)."
        )

    prompt = BACK_SYSTEM_PROMPT.format(
        task_json=json.dumps(_strip_task_for_prompt(task), indent=2),
        temporal_narrative=_or_default(
            temporal_context_block,
            "The current date and time were not resolved for this task. If "
            "timing matters, resolve it through capability reads — do not guess.",
        ),
        spatial_narrative=_or_default(
            spatial_context_block,
            "The user's location is unknown for this task.",
        ),
        selfmodel_narrative=_or_default(
            selfmodel_context_block,
            "No user profile is attached to this task — act strictly on the " "dispatch contents.",
        ),
        grounding_narrative=_or_default(
            grounding_narrative,
            "No grounding references accompany this task.",
        ),
        available_tools_note=available_tools_note,
        scoreboard_narrative=_scoreboard_narrative(referents),
        beliefs_narrative=_beliefs_narrative(beliefs),
        task_state_narrative=_task_state_narrative(task_state),
        artifacts_narrative=_artifacts_narrative(task_artifacts),
        safety_narrative=_safety_narrative(safety_band),
        persona_narrative=_persona_narrative(persona_prefs),
        registry_hints_narrative=registry_hints_narrative,
        registry_family_narrative=registry_family_narrative,
        max_tool_calls=max_tool_calls,
    )
    task_action = (
        task.get("action", task.get("intents", [{}])[0].get("action", "unknown"))
        if task
        else "unknown"
    )
    logger.info(
        "build_back_prompt  task=%s safety=%s budget=%d beliefs_len=%d prompt_len=%d",
        task_action,
        safety_band,
        max_tool_calls,
        len(beliefs),
        len(prompt),
    )
    return prompt


# =========================================================================
# Phase 2 Epic 17 — Prose narrative wrappers
# =========================================================================
# Every SS-derived value is wrapped in natural-language sentences before
# template injection.  Empty/missing data renders an explicit one-line
# statement rather than a blank — Back should never have to infer absence.


def _or_default(text: str, default: str) -> str:
    stripped = (text or "").strip()
    return stripped if stripped else default


def _strip_task_for_prompt(task: dict[str, Any]) -> dict[str, Any]:
    """Return a lean copy of the task dispatch for the Back prompt.

    The full task payload carries ~5 KB of grounding projection JSON
    (temporal windows, spatial context, freshness metadata, execution
    profiles) that duplicates the prose already rendered in SITUATIONAL
    CONTEXT.  We keep only the fields the Back LLM needs to understand
    the task: intents, tier, budget, and a one-line reason.
    """
    if not task:
        return {}
    stripped: dict[str, Any] = {
        "task_id": task.get("task_id", ""),
        "tier": task.get("tier", "LOW"),
        "budget_hint": task.get("budget_hint", 8),
        "safety_band": task.get("safety_band", "GREEN"),
    }
    # Keep intents but drop the bloat inside each intent (only action, params,
    # resource_family, operation_hint survive)
    raw_intents = task.get("intents", [])
    clean_intents: list[dict[str, Any]] = []
    for intent in raw_intents:
        if isinstance(intent, dict):
            clean: dict[str, Any] = {}
            for key in ("action", "params", "resource_family", "operation_hint"):
                if key in intent:
                    clean[key] = intent[key]
            if clean:
                clean_intents.append(clean)
    stripped["intents"] = clean_intents
    # Keep only the reason from reference_context
    rc = task.get("reference_context", {})
    if isinstance(rc, dict) and rc.get("reason"):
        stripped["reference_context"] = {"reason": rc["reason"]}
    return stripped


def _scoreboard_narrative(referents: dict[str, Any] | None) -> str:
    """Render scoreboard referents as reference-resolution prose."""
    if not referents:
        return "No pronoun or reference resolution is active — interpret the " "dispatch literally."
    pairs: list[str] = []
    for key, value in referents.items():
        if isinstance(value, dict):
            label = str(
                value.get("display_name")
                or value.get("name")
                or value.get("id")
                or json.dumps(value, sort_keys=True)
            )
        else:
            label = str(value)
        pairs.append(f"'{key}' refers to {label}")
    return (
        "When the dispatch or the conversation uses these references, "
        "resolve them as follows: " + "; ".join(pairs) + "."
    )


def _beliefs_narrative(beliefs: str) -> str:
    text = (beliefs or "").strip()
    if not text or "no beliefs" in text.lower():
        return "No stored beliefs are active for this session."
    return (
        "These beliefs about the user and household were established in "
        "earlier turns. When the dispatch contradicts a high-confidence "
        "belief (confidence 0.8 or above), prefer the belief:\n" + text
    )


def _task_state_narrative(task_state: str) -> str:
    text = (task_state or "").strip()
    if not text or "no active tasks" in text.lower():
        return "This task stands alone — no other in-flight tasks depend on it."
    return (
        "Other tasks are currently in flight in this session. Coordinate "
        "with them — do not duplicate their work:\n" + text
    )


def _artifacts_narrative(task_artifacts: str) -> str:
    text = (task_artifacts or "").strip()
    if not text or "no artifacts" in text.lower():
        return "Nothing has been completed yet in this session."
    return (
        "Work already completed earlier in this session is listed below. "
        "If it already answers the task, submit immediately — do NOT redo "
        "it:\n" + text
    )


def _safety_narrative(safety_band: str) -> str:
    band = (safety_band or "GREEN").strip().upper()
    if band == "RED":
        return (
            "This task runs at the RED safety band: restricted execution. "
            "Only explicitly allowed operations may run; anything uncertain "
            "or irreversible must end in submit_result(needs_human)."
        )
    if band == "AMBER":
        return (
            "This task runs at the AMBER safety band: heightened caution. "
            "Prefer reversible actions, double-check targets before any "
            "write, and surface anything ambiguous to a human."
        )
    return (
        "This task runs at the GREEN safety band: standard execution. "
        "Reads are unrestricted; writes follow normal capability contracts."
    )


def _persona_narrative(persona_prefs: dict[str, Any] | None) -> str:
    prefs = persona_prefs or {}
    if not prefs:
        return "No stored payment, dietary, or accessibility preferences."
    parts: list[str] = []
    payment = prefs.get("payment_method")
    if payment:
        parts.append(f"payment via {payment}")
    dietary = prefs.get("dietary")
    if dietary:
        parts.append(f"dietary requirements: {dietary}")
    accessibility = prefs.get("accessibility")
    if accessibility:
        parts.append(f"accessibility needs: {accessibility}")
    for key, value in prefs.items():
        if key in ("payment_method", "dietary", "accessibility"):
            continue
        parts.append(f"{key}: {value}")
    if not parts:
        return "No stored payment, dietary, or accessibility preferences."
    return (
        "Stored execution preferences — honor these without re-asking: "
        + "; ".join(str(p) for p in parts)
        + "."
    )


def _conversation_narrative(
    history_entries: list[Any] | None,
    *,
    limit: int = 10,
    max_chars: int = 400,
) -> str:
    """Render recent conversation as a prose transcript.

    Includes the triggering utterance (last user message) emphasised at
    the end so Back knows exactly which request produced the dispatch.
    """
    if not history_entries:
        return (
            "No prior conversation is attached — the task dispatch below "
            "is your only statement of what the user wants."
        )
    relevant = [
        entry
        for entry in history_entries
        if getattr(entry, "entry_type", "") in ("user", "final", "hitl_response")
    ]
    recent = relevant[-limit:]
    if not recent:
        return (
            "No prior conversation is attached — the task dispatch below "
            "is your only statement of what the user wants."
        )
    lines = [
        "Here is what has happened between the user and the assistant so "
        "far in this conversation:"
    ]
    for entry in recent:
        text = str(getattr(entry, "text", "") or "").strip()
        if not text:
            continue
        if len(text) > max_chars:
            text = text[:max_chars] + "\u2026"
        entry_type = getattr(entry, "entry_type", "")
        if entry_type == "user":
            lines.append(f'  The user said: "{text}"')
        elif entry_type == "hitl_response":
            lines.append(f'  The user answered a question: "{text}"')
        else:
            lines.append(f'  The assistant replied: "{text}"')
    last_user = next(
        (
            entry
            for entry in reversed(recent)
            if getattr(entry, "entry_type", "") in ("user", "hitl_response")
        ),
        None,
    )
    if last_user is not None:
        trigger = str(getattr(last_user, "text", "") or "").strip()
        if len(trigger) > max_chars:
            trigger = trigger[:max_chars] + "\u2026"
        if trigger:
            lines.append(f'The task below was dispatched because the user asked: "{trigger}"')
    return "\n".join(lines)


def _task_resolved_temporal_refs(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(task, dict):
        return None
    refs = task.get("resolved_temporal_refs")
    return refs if isinstance(refs, dict) else None


def _with_resolved_temporal_refs(
    execution_grounding_block: str,
    *,
    resolved_temporal_refs: dict[str, Any] | None,
) -> str:
    """Append pre-resolved time expressions to the grounding narrative as prose."""
    block = (execution_grounding_block or "").strip()
    if not resolved_temporal_refs:
        return block
    sentences = [
        f"'{raw_text}' means {_render_temporal_ref(value)}"
        for raw_text, value in resolved_temporal_refs.items()
    ]
    prose = (
        "The dispatcher already resolved these time expressions for you — "
        "use them exactly as given, do not re-derive them: " + "; ".join(sentences) + "."
    )
    return f"{block}\n{prose}" if block else prose


def _render_temporal_ref(value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)
    label = str(value.get("normalized_label") or value.get("raw_text") or "resolved")
    kind = str(value.get("resolution_kind") or "")
    if value.get("needs_clarification"):
        return f"{label} ({kind or 'ambiguous'})"
    window = value.get("window")
    if isinstance(window, dict):
        compact = {
            key: window.get(key)
            for key in ("start_local", "end_local", "start_utc", "end_utc", "timezone")
            if window.get(key) is not None
        }
        return f"{label} ({kind or 'window'}) {json.dumps(compact, sort_keys=True)}"
    instant = value.get("instant_local")
    if instant:
        return f"{label} ({kind or 'instant'}) {instant}"
    return json.dumps(value, sort_keys=True)
