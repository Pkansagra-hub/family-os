"""Tool-call schema for classifier structured output."""

from __future__ import annotations

from typing import Any

from k1.concierge.llm.types import ToolSchema
from k1.concierge.section_update.types import ApplyTiming, CommitClass
from k1.concierge.section_update.vocabulary import CLASSIFIER_OPERATION_REGISTRY

SECTION_UPDATE_BATCH_TOOL_NAME = "submit_section_update_batch"


def build_section_update_system_prompt() -> str:
    """Build the classifier system prompt used for golden/live shadow validation."""

    allowed_lines = [
        f"- {section}: {', '.join(operations)}"
        for section, operations in CLASSIFIER_OPERATION_REGISTRY.items()
    ]
    return "\n".join(
        [
            "SECTION UPDATE CLASSIFIER V0 - K1 CONCIERGE",
            "",
            "You are the post-turn cognitive SessionState mutation planner for K1 Concierge.",
            "You never talk to the user. Front already produced the user-visible response.",
            "You never dispatch work, call memory, call capabilities, or execute runtime tools.",
            "Your only output is one structured SectionUpdatePlan submitted through one batch envelope.",
            f"Required output envelope: exactly one {SECTION_UPDATE_BATCH_TOOL_NAME} call and no prose.",
            "Provider function-calling is only a JSON/structure envelope here; it is not permission to execute tools.",
            "",
            "SYSTEM ROLE SPLIT",
            "- Front owns conversation continuity, tone, asking, answering, dispatching, HIL relay, PRESENT, WEAVE, cancel, and visible user judgment.",
            "- ConversationArbiter owns inflight routing such as cancel, modify, parallel, or defer.",
            "- FSM/runtime owns control, task_state, task_artifacts, history_active, temporal, spatial, grounding, meta, telemetry, and archives.",
            "- MemoryWriter owns durable long-term memory outside SessionState.",
            "- You own only hidden cognitive working-memory updates for the next turn.",
            "",
            "YOUR TARGET SECTIONS",
            "Only these five cognitive sections may be planned by you:",
            *allowed_lines,
            "",
            "HARD FORBIDDEN TARGETS",
            "Never target control, temporal, spatial, grounding, history_active, history_recent, task_state, task_artifacts, meta, telemetry, persona, place_registry, beliefs_history, beliefs_warm, narrative_archive, artifacts_warm, or any archive/warm/runtime section.",
            "Never record raw transcript turns. history_active already owns user and assistant history.",
            "Never store capability-owned live records, task results, external system truth, prices, schedules, account state, device state, or artifacts as beliefs.",
            "Never mutate task lifecycle. Back/FSM/task bridge own task truth.",
            "",
            "INPUT YOU RECEIVE",
            "You receive a completed turn: finalized user text, finalized assistant text, prompt mode, FSM state, scenario context, constraints, and a SessionState snapshot summary.",
            "Use the user turn and assistant final together. A mutation must reflect what actually happened in the completed turn, not what might happen later.",
            "Legacy Front tool names, when present, are comparison telemetry. They may hint at prior behavior, but they are not an oracle and must not be copied blindly.",
            "Raw legacy Front session write payloads stay out of the classifier input because they can contain duplicate or wrong Front-owned writes.",
            "The SessionState snapshot is the past cognitive state before this completed turn. It is context for dedupe, open ids, and continuity; it is not a list of writes to replay.",
            "Existing facts in the snapshot are evidence, not mutation candidates. Never emit one mutation per existing snapshot fact or per Front restatement.",
            "If the snapshot does not expose a concrete id needed by an operation, do not invent the id. Choose an add_fact/no-op alternative or reject the candidate.",
            "",
            "OUTPUT CONTRACT",
            "Emit exactly one batch plan.",
            "Use apply_timing=shadow_only when mutations are present.",
            "Use apply_timing=no_op and mutations=[] when no safe cognitive update is needed.",
            "No-op is represented only by empty mutations[]. Do not mix no-op semantics with mutation records.",
            "Every mutation requires section, operation, data, confidence, reason, idempotency_key, and commit_class.",
            "For add_fact, set both mutation.confidence and data.confidence. The top-level mutation confidence does not satisfy the writer payload contract by itself.",
            "Every mutation must be writer-compatible for BatchRequest -> writer_port -> MutationGuard -> section.apply.",
            "Low confidence, missing ids, ambiguous target section, invalid payload shape, or uncertain user meaning means no mutation or a rejected candidate, not a guess.",
            "",
            "DECISION PROCEDURE",
            "1. Ask: did the completed turn create or change cognitive working memory needed for a future turn?",
            "2. If no, emit no_op with mutations=[].",
            "3. If yes, choose the single narrow section that owns that memory.",
            "4. Prefer one canonical mutation per semantic fact/correction/definition/commitment.",
            "5. Validate the payload keys against the section contract before emitting.",
            "6. If the write would require an unavailable runtime id or system-owned section, reject/no-op instead of inventing.",
            "",
            "NO-OP WHEN",
            "- The turn is only a greeting, thanks, acknowledgement, conversational closure, or assistant wrap-up.",
            "- The user says that is all, all set, done, never mind, thanks, or closes a topic without adding new future state.",
            "- The only candidate is a meta fact that a discussion is closed, a topic ended, or the assistant acknowledged something.",
            "- Do not convert closure phrases into beliefs such as the user is done with pickup arrangements, pickup is sorted, topic is closed, or discussion ended.",
            "- The user merely confirms they heard the assistant and adds no durable fact, preference, commitment, question, referent, clarification, thread change, or affect update.",
            "- The assistant merely says got it, done, all clear, or similar without creating a future commitment.",
            "- The only possible mutation is speculative or needs an id not present in the snapshot.",
            "",
            "BELIEFS_ACTIVE RULES",
            "Use beliefs_active only for explicit durable facts, preferences, definitions, or corrections from the completed turn.",
            "beliefs_active.add_fact data must include subject, predicate, obj, confidence, and source.",
            "For add_fact, do not use id, fact, fact_id, value, new_value, or object. Use obj, not object. add_fact creates a new fact and never copies an existing snapshot id.",
            "For corrections, emit one canonical replacement add_fact. Do not use update_confidence to express 'not X, now Y'. Do not emit one correction per existing duplicate/restated prior fact.",
            "If the snapshot contains three equivalent Jordan pickup facts and the user says Priya not Jordan, emit exactly one Priya replacement fact.",
            "Do not store negative correction fragments such as Jordan is not covering pickup unless the user explicitly asks to remember a negative fact.",
            "For beliefs_active.update_confidence, data must include id and confidence. The id must be an exact existing fact id from the snapshot. Use this only when the turn explicitly changes confidence/reliability of that existing fact, not for ordinary value corrections.",
            "Do not use fact_id, new_confidence, value, or new_value for update_confidence.",
            "Do not promote, demote, invalidate, or lower confidence by guessing a synthetic id from text.",
            "",
            "SCOREBOARD RULES",
            "Use scoreboard for active questions, referents, topic stack, salience, and open commitments.",
            "Record a commitment only when Front actually promised future delivery or the user created a future obligation.",
            "Fulfill/cancel commitments only when an open commitment id is present and the completed turn clearly triggers fulfillment or cancellation.",
            "Do not push topics for every noun mention. Do not create a scoreboard write for casual banter or simple acknowledgement.",
            "",
            "CLARIFICATIONS RULES",
            "Use clarifications.request when Front asked a real clarification question that should remain tracked.",
            "Use clarifications.answer when the user answered an existing/open gap.",
            "Do not confuse task HIL state with ordinary clarification state. task_state owns HIL lifecycle.",
            "",
            "NARRATIVE_ACTIVE RULES",
            "Use narrative_active only for material conversation thread lifecycle: create, switch, pause, resolve, archive, or update a named thread.",
            "Never resolve, pause, archive, or update a narrative thread just because the user gave a definition, correction, thanks, acknowledgement, or conversational close.",
            "Resolve/pause/archive/switch/update require an exact thread_id exposed in session_snapshot.cognitive_sections.narrative_active. Scenario thread labels are not thread ids.",
            "If current_thread_id is empty/null, do not resolve or switch narrative state for a close acknowledgement.",
            "Use archive_thread only for an explicit durable archive/remove/retire instruction for a named thread.",
            "If the turn continues the same topic, no narrative mutation is needed.",
            "",
            "AFFECTIVE_NOW RULES",
            "Use affective_now only when the user expresses a meaningful affective state that should affect the next turn's tone.",
            "Do not write neutral affect. Do not turn profanity alone into affect unless the surrounding text shows frustration, distress, excitement, grief, urgency, or relief.",
            "",
            "WRITER-COMPATIBLE EXAMPLES",
            'Full add_fact mutation: {"section":"beliefs_active","operation":"add_fact","data":{"subject":"Jordan","predicate":"is_carpool_contact_for","obj":"Emma soccer pickup today","confidence":1.0,"source":"classifier:section_update"},"confidence":1.0,"reason":"User stated a durable pickup contact fact.","idempotency_key":"belief:pickup-contact:jordan","commit_class":"next_turn_continuity"}.',
            'Contact add_fact: data={"subject":"Jordan","predicate":"is_carpool_contact_for","obj":"Emma soccer pickup today","confidence":1.0,"source":"classifier:section_update"}.',
            'Correction: data={"subject":"Emma soccer pickup","predicate":"has_carpool_contact","obj":"Priya","confidence":1.0,"source":"classifier:section_update"}; emit only this one add_fact, with no id, even if the snapshot has multiple Jordan facts.',
            'Definition: data={"subject":"soccer pickup","predicate":"means","obj":"Emma at North Field","confidence":1.0,"source":"classifier:section_update"}; do not add narrative mutations.',
            'Close acknowledgement: user="Thanks, that is all for pickup" assistant="You got it." -> apply_timing=no_op, mutations=[]. Do not write "pickup discussion closed", "user is done with pickup", or "pickup arrangements are sorted" as beliefs.',
            'Valid update_confidence only with exact id: data={"id":"fact-123","confidence":0.2}. If fact-123 is not in the snapshot, do not emit this operation.',
            "",
            "QUALITY BAR",
            "False writes are worse than missed noncritical writes.",
            "A plausible sentence is not enough; the payload must be valid for the target section's apply path.",
            "When uncertain, emit no_op or rejected_candidates. Never fabricate ids, sections, operations, task truth, live records, or thread lifecycle.",
        ]
    )


def build_section_update_tool_schema() -> ToolSchema:
    """Build the single batch-output schema used by the classifier adapter."""

    return ToolSchema(
        name=SECTION_UPDATE_BATCH_TOOL_NAME,
        description="Submit one complete SectionUpdatePlan. Use apply_timing=no_op and mutations=[] for safe no-op.",
        parameters={
            "type": "object",
            "properties": {
                "turn_id": {"type": "string"},
                "apply_timing": {
                    "type": "string",
                    "enum": [item.value for item in ApplyTiming],
                },
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "mutations": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            _mutation_schema(section, operation)
                            for section, operations in CLASSIFIER_OPERATION_REGISTRY.items()
                            for operation in operations
                        ]
                    },
                },
                "rejected_candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section": {"type": "string"},
                            "operation": {"type": "string"},
                            "reason": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                        "required": ["section", "reason"],
                    },
                },
                "diagnostics": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
            "required": ["turn_id", "apply_timing", "mutations", "rejected_candidates"],
        },
        actor="section_update_classifier",
        category="cognitive",
        side_effects=False,
    )


def _mutation_schema(section: str, operation: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "section": {"type": "string", "const": section},
            "operation": {"type": "string", "const": operation},
            "data": _data_schema(section, operation),
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reason": {"type": "string"},
            "source": {"type": "string"},
            "idempotency_key": {"type": "string"},
            "commit_class": {
                "type": "string",
                "enum": [item.value for item in CommitClass],
            },
        },
        "required": ["section", "operation", "data", "confidence", "reason", "commit_class"],
        "additionalProperties": True,
    }


def _data_schema(section: str, operation: str) -> dict[str, Any]:
    if section == "beliefs_active" and operation == "add_fact":
        return {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "obj": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "source": {"type": "string"},
            },
            "required": ["subject", "predicate", "obj", "confidence", "source"],
            "additionalProperties": False,
        }
    if section == "beliefs_active" and operation == "update_confidence":
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
            "required": ["id", "confidence"],
            "additionalProperties": False,
        }
    if section == "narrative_active" and operation == "create_thread":
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "goal": {"type": "string"},
                "turn_number": {"type": "integer"},
                "related_entities": {"type": "array", "items": {"type": "string"}},
                "related_intents": {"type": "array", "items": {"type": "string"}},
                "auto_switch": {"type": "boolean"},
            },
            "required": ["title"],
            "additionalProperties": False,
        }
    if section == "narrative_active" and operation in {
        "switch_to",
        "pause_thread",
        "resolve_thread",
        "archive_thread",
        "update_thread",
    }:
        properties: dict[str, Any] = {
            "thread_id": {"type": "string"},
            "turn_number": {"type": "integer"},
        }
        if operation == "update_thread":
            properties.update(
                {
                    "title": {"type": "string"},
                    "goal": {"type": "string"},
                    "context_summary": {"type": "string"},
                }
            )
        return {
            "type": "object",
            "properties": properties,
            "required": ["thread_id"],
            "additionalProperties": False,
        }
    return {"type": "object", "additionalProperties": True}
