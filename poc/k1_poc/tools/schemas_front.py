"""
Front Tool Schemas -- 9 Tools for the Concierge Voice
======================================================

V2 Design Ref: Section 6.1 (Front LLM tool schemas)

Tool categories:
  Cognitive (6): update_beliefs, update_scoreboard, update_clarifications,
                 update_narrative, refine_affect, promote_belief
  Read (2):      recall_memory, summarize_context
  Control (1):   dispatch_task

All schemas use the provider-agnostic ToolSchema from M03.
The Gemini adapter converts these to FunctionDeclaration format.
"""

from __future__ import annotations

from poc.k1_poc.llm.types import ToolSchema

# ===================================================================
# COGNITIVE (6)
# ===================================================================

UPDATE_BELIEFS_SCHEMA = ToolSchema(
    name="update_beliefs",
    description=(
        "Create or correct factual beliefs from the conversation. Call when user "
        "states facts, preferences, constraints, or corrections. Each belief is a "
        "subject-predicate-object triple with confidence. Examples: "
        "('user', 'prefers', 'Italian food', 0.9), "
        "('trip', 'has_dates', 'June 15-17', 1.0), "
        "('budget', 'is', 'under $600/night', 0.8)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "beliefs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "predicate": {"type": "string"},
                        "object": {"type": "string"},
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                    },
                    "required": ["subject", "predicate", "object", "confidence"],
                },
                "minItems": 1,
                "description": "One or more belief triples to store.",
            },
        },
        "required": ["beliefs"],
    },
    returns={
        "type": "object",
        "properties": {
            "stored": {"type": "integer", "description": "Number of beliefs stored"},
            "updated": {"type": "integer", "description": "Number of existing beliefs updated"},
        },
    },
    actor="front",
    category="cognitive",
    side_effects=True,
)

UPDATE_SCOREBOARD_SCHEMA = ToolSchema(
    name="update_scoreboard",
    description=(
        "Update the conversational scoreboard: Question Under Discussion (QUD), "
        "referent resolution, salience map, and topic shifts. Call when the user "
        "changes topic, uses pronouns that need resolution, or asks a new question. "
        "Phase 1 (UltraBERT) sets initial intents and entities; this tool REFINES them."
    ),
    parameters={
        "type": "object",
        "properties": {
            "qud_push": {
                "type": "string",
                "description": "New Question Under Discussion to push on stack. Null if no new question.",
            },
            "qud_pop": {
                "type": "boolean",
                "description": "Pop the current QUD (question answered). Default false.",
                "default": False,
            },
            "referent_updates": {
                "type": "object",
                "description": (
                    "Map of pronoun/reference -> resolved entity. "
                    "E.g. {'it': 'Vineyard Inn', 'there': 'Napa Valley'}."
                ),
                "additionalProperties": {"type": "string"},
            },
            "topic_shift": {
                "type": "string",
                "description": "New topic if user shifted conversation. Null if same topic.",
            },
        },
        "required": [],
    },
    returns={
        "type": "object",
        "properties": {
            "qud_depth": {"type": "integer"},
            "active_referents": {"type": "integer"},
        },
    },
    actor="front",
    category="cognitive",
    side_effects=True,
)

UPDATE_CLARIFICATIONS_SCHEMA = ToolSchema(
    name="update_clarifications",
    description=(
        "Record semantic gaps detected in user intent. Call when user's request "
        "is ambiguous, underspecified, or contradicts existing beliefs. "
        "Each gap has a field (what's missing), a question (what to ask), "
        "and severity (how blocking it is)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "gaps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "description": "What information is missing",
                        },
                        "question": {
                            "type": "string",
                            "description": "Natural language question to resolve it",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["blocking", "helpful", "minor"],
                        },
                    },
                    "required": ["field", "question", "severity"],
                },
            },
            "resolved_gaps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Field names of previously recorded gaps that are now resolved.",
            },
        },
        "required": [],
    },
    returns={
        "type": "object",
        "properties": {
            "open_gaps": {"type": "integer"},
            "blocking_gaps": {"type": "integer"},
        },
    },
    actor="front",
    category="cognitive",
    side_effects=True,
)

UPDATE_NARRATIVE_SCHEMA = ToolSchema(
    name="update_narrative",
    description=(
        "Track conversation thread switches and resumptions. Call when user "
        "changes topic (switch), returns to a previous topic (resume), "
        "or finishes a topic (close). Maintains narrative_active section."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["switch", "resume", "close"],
                "description": "What happened to the narrative thread.",
            },
            "thread_id": {
                "type": "string",
                "description": (
                    "Identifier for the thread "
                    "(e.g. 'hotel_booking', 'gym_discussion', 'weather')."
                ),
            },
            "summary": {
                "type": "string",
                "description": "Brief summary of thread state at switch/close point.",
            },
        },
        "required": ["action", "thread_id"],
    },
    returns={
        "type": "object",
        "properties": {
            "active_thread": {"type": "string"},
            "total_threads": {"type": "integer"},
        },
    },
    actor="front",
    category="cognitive",
    side_effects=True,
)

REFINE_AFFECT_SCHEMA = ToolSchema(
    name="refine_affect",
    description=(
        "Override Phase 1 (UltraBERT) emotion classification with LLM's "
        "assessment. Call when you detect emotional signals that the "
        "deterministic classifier missed: sarcasm, irony, mixed emotions, "
        "subtle frustration, excitement masked as calm, etc."
    ),
    parameters={
        "type": "object",
        "properties": {
            "emotion": {
                "type": "string",
                "description": (
                    "Primary emotion label " "(joy, frustration, anxiety, excitement, calm, etc.)"
                ),
            },
            "valence": {
                "type": "number",
                "minimum": -1.0,
                "maximum": 1.0,
                "description": "-1.0 negative to +1.0 positive",
            },
            "arousal": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "0.0 calm to 1.0 excited",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "How confident in this override",
            },
            "reason": {
                "type": "string",
                "description": "Why you're overriding Phase 1's classification",
            },
        },
        "required": ["emotion", "valence", "arousal", "confidence"],
    },
    returns={
        "type": "object",
        "properties": {
            "previous_emotion": {"type": "string"},
            "updated": {"type": "boolean"},
        },
    },
    actor="front",
    category="cognitive",
    side_effects=True,
)

PROMOTE_BELIEF_SCHEMA = ToolSchema(
    name="promote_belief",
    description=(
        "Promote a low-confidence or WARM-tier belief to HOT/high-confidence. "
        "Call when conversation confirms a previously uncertain belief. "
        "MEDIUM and HIGH tier only."
    ),
    parameters={
        "type": "object",
        "properties": {
            "belief_id": {
                "type": "string",
                "description": "ID of the belief to promote",
            },
            "new_confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "reason": {
                "type": "string",
                "description": "Why this belief is now confirmed",
            },
        },
        "required": ["belief_id", "new_confidence"],
    },
    returns={
        "type": "object",
        "properties": {
            "promoted": {"type": "boolean"},
            "from_tier": {"type": "string"},
        },
    },
    actor="front",
    category="cognitive",
    side_effects=True,
)

# ===================================================================
# READ (2)
# ===================================================================

RECALL_MEMORY_SCHEMA = ToolSchema(
    name="recall_memory",
    description=(
        "Query K0 long-term memory for relevant context. Returns past experiences, "
        "preferences, facts, schedules, agendas, routines, and family knowledge "
        "from previous sessions. THIS IS YOUR PRIMARY INFORMATION SOURCE. "
        "Use for ANY information lookup: agenda, calendar, schedule, to-do items, "
        "appointments, routines, preferences, past events, medical info, family rules, "
        "contacts, allergies, habits. "
        "Examples: 'what's on my agenda', 'what restaurant did we like', "
        "'Riley's bedtime routine', 'Jordan's schedule', 'grocery delivery day'. "
        "Front uses for conversational context. Back uses for task-specific data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language memory query",
            },
            "memory_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["episodic", "semantic", "procedural"],
                },
                "description": "Which memory stores to search. Default: all.",
            },
            "max_results": {
                "type": "integer",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["query"],
    },
    returns={
        "type": "object",
        "properties": {
            "memories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "type": {"type": "string"},
                        "relevance": {"type": "number"},
                        "timestamp": {"type": "string"},
                    },
                },
            },
            "count": {"type": "integer"},
        },
    },
    actor="both",
    category="read",
    side_effects=False,
)

SUMMARIZE_CONTEXT_SCHEMA = ToolSchema(
    name="summarize_context",
    description=(
        "Compress Session State sections to fit within token budget. "
        "Call when the system prompt is too large. Returns compressed version "
        "of specified sections. This is a token management tool, not a user-facing tool."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "SS section names to compress " "(e.g. ['beliefs_active', 'history_active'])"
                ),
            },
            "target_tokens": {
                "type": "integer",
                "description": "Target token count for compressed output",
            },
        },
        "required": ["sections", "target_tokens"],
    },
    returns={
        "type": "object",
        "properties": {
            "compressed": {
                "type": "string",
                "description": "Compressed text representation",
            },
            "original_tokens": {"type": "integer"},
            "compressed_tokens": {"type": "integer"},
        },
    },
    actor="front",
    category="read",
    side_effects=False,
)

# ===================================================================
# CONTROL (1)
# ===================================================================

DISPATCH_TASK_SCHEMA = ToolSchema(
    name="dispatch_task",
    description=(
        "Dispatch a task to the background worker for execution. Use when the user "
        "wants something DONE (search, book, create, schedule, send, draft, etc.). "
        "Do NOT call for pure conversation, emotional support, or clarification. "
        "The FSM intercepts this tool call and emits k1.orchestration.task.dispatch.v1 "
        "on the bus. The tool itself returns immediately with {queued: true}. "
        "For multi-intent messages (including sequential ones), call dispatch_task "
        "ONCE with all intents in the intents array ordered logically. "
        "Only use depends_on with a task-ID from a previous dispatch_task result."
    ),
    parameters={
        "type": "object",
        "properties": {
            "intents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "What to do (natural language or capability name)",
                        },
                        "params": {
                            "type": "object",
                            "description": (
                                "Structured parameters extracted from " "conversation and beliefs"
                            ),
                        },
                        "domain": {
                            "type": "string",
                            "description": (
                                "Domain hint: travel, health, productivity, "
                                "finance, creative, shopping, family, etc."
                            ),
                        },
                    },
                    "required": ["action"],
                },
                "minItems": 1,
                "description": (
                    "One or more intents to execute. Independent intents are "
                    "bundled. Sequential intents use depends_on."
                ),
            },
            "urgency": {
                "type": "string",
                "enum": ["normal", "urgent", "background"],
                "default": "normal",
            },
            "reference_context": {
                "type": "object",
                "description": (
                    "Resolved references for the Back worker. Front resolves pronouns and "
                    "references using its 20-entry history view and passes resolved values "
                    "here. E.g. {'the hotel': 'Vineyard Inn', 'it': 'restaurant search'}."
                ),
                "additionalProperties": {"type": "string"},
            },
            "depends_on": {
                "type": "string",
                "description": (
                    "Task ID (e.g. 'task-a1b2c3d4') returned by a PREVIOUS "
                    "dispatch_task call. Use ONLY when this dispatch must wait "
                    "for a prior task's result. Must start with 'task-'. "
                    "For multiple intents in one request, bundle them in the "
                    "intents array instead -- do NOT use depends_on."
                ),
            },
        },
        "required": ["intents"],
    },
    returns={
        "type": "object",
        "properties": {
            "queued": {"type": "boolean"},
            "task_id": {"type": "string"},
        },
    },
    actor="front",
    category="control",
    side_effects=False,  # Tool itself does not mutate -- FSM emits the event
)

# ===================================================================
# Aggregated list -- all 10 Front tools
# ===================================================================

FRONT_TOOL_SCHEMAS: list[ToolSchema] = [
    # Cognitive
    UPDATE_BELIEFS_SCHEMA,
    UPDATE_SCOREBOARD_SCHEMA,
    UPDATE_CLARIFICATIONS_SCHEMA,
    UPDATE_NARRATIVE_SCHEMA,
    REFINE_AFFECT_SCHEMA,
    PROMOTE_BELIEF_SCHEMA,
    # Read
    RECALL_MEMORY_SCHEMA,
    SUMMARIZE_CONTEXT_SCHEMA,
    # Control
    DISPATCH_TASK_SCHEMA,
]
