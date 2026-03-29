"""
Tool Implementations -- Real SS-integrated tool execution functions
===================================================================

V2 Design Ref: Section 6.1 (Front tools), Section 6.2 (Back tools)

Each tool function:
  1. Accepts the LLM's tool call arguments (dict)
  2. Writes to REAL Session State sections via SessionStateManager
  3. Returns a ToolResult envelope

Front tools (9):  update_beliefs, update_scoreboard,
                  update_clarifications, update_narrative, refine_affect,
                  promote_belief, recall_memory, summarize_context,
                  dispatch_task

Back tools (7):   recall_memory (shared), discover_capabilities,
                  invoke_capability, batch_invoke_capabilities,
                  spawn_via_fabric, execute_workflow,
                  submit_result

IMPORTANT:
  - These are NOT stubs. They interact with real SessionState sections.
  - SessionStateManager is injected via ToolContext.
  - dispatch_task is intercepted by the FSM in production;
    here it returns structured results the FSM/handler will act on.
  - Back action tools (invoke_capability, spawn_via_fabric, execute_workflow)
    are K0 Fabric calls -- POC implementations return placeholder results
    since the actual Fabric is outside K1 scope. The TOOL INTERFACE is real.
"""

from __future__ import annotations

import inspect as _inspect
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from poc.k1_poc.sessionstate.ports.writer import BatchRequest, MutationRequest
from poc.k1_poc.task.complexity import ComplexityTier
from poc.k1_poc.task.dispatch import TaskDispatch
from poc.k1_poc.task.intent import TaskIntent
from poc.k1_poc.tools.result_protocol import ToolResult

logger = logging.getLogger(__name__)

# =========================================================================
# ToolContext -- injected dependency bag for tool functions
# =========================================================================


@dataclass
class ToolContext:
    """Dependencies injected into every tool function.

    Holds references to the SessionStateManager and any external
    services the tools need. Created once per ReAct loop invocation.

    Attributes:
        session_manager: The real SessionStateManager (M02) with all
            HOT/WARM sections, mutation guard, size tracking.
        cognitive_trace_id: Trace ID for the current turn. Threaded
            through all mutations for observability.
        actor: "front" | "back" -- which actor is executing.
        recall_fn: Optional callback for K0 long-term memory retrieval.
            Signature: (query: str, memory_types: list, max_results: int) -> list[dict]
            None in POC (recall_memory returns empty results).
        capability_fn: Optional callback for K0 capability registry.
            Signature: (intent: str, domain: str|None, constraints: dict|None) -> list[dict]
            None in POC.
        invoke_fn: Optional callback for K0 capability invocation.
            Signature: (name: str, params: dict, session_id: str|None) -> dict
            None in POC.
        fabric_fn: Optional callback for K0 agent fabric spawning.
            Signature: (agent_type: str, task: str, constraints: dict|None, ...) -> dict
            None in POC.
        workflow_fn: Optional callback for K0 workflow execution.
            Signature: (workflow_id: str, params: dict, timeout_ms: int) -> dict
            None in POC.
    """

    session_manager: Any  # SessionStateManager (avoid circular import)
    cognitive_trace_id: str = ""
    actor: str = "front"
    writer_port: Any = None  # IWriterPort -- M4 E4.2.1 write-path enforcement
    bundle_idempotency_cache: dict = None  # M4 E4.3.1 per-session dedup for update_session_bundle
    active_device_id: str | None = None  # M5 E5.5.6: device that triggered the current turn
    hil_coordinator: Any = None  # M6 E6.1.3: HILCoordinator for L2 invoke_capability blocking
    active_task_id: str | None = None  # M6 E6.1.3: task_id for per-task L2 checks
    recall_fn: Callable | None = None
    capability_fn: Callable | None = None
    invoke_fn: Callable | None = None
    fabric_fn: Callable | None = None
    workflow_fn: Callable | None = None
    capability_cache: dict | None = None  # Per-session cache for discover_capabilities results


# =========================================================================
# TOOL REGISTRY -- maps tool name -> implementation function
# =========================================================================

# Populated at module level after all functions are defined
TOOL_REGISTRY: dict[str, Callable[[dict, ToolContext], ToolResult]] = {}


def _register(name: str):
    """Decorator to register a tool implementation."""

    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        return fn

    return decorator


# =========================================================================
# COGNITIVE (6) -- Front only, all write to SS
# =========================================================================


@_register("update_beliefs")
def execute_update_beliefs(args: dict, ctx: ToolContext) -> ToolResult:
    """Store or update factual beliefs in beliefs_active section.

    Each belief is a subject-predicate-object triple with confidence.
    Routes writes through writer_port for MutationGuard preflight,
    SizeTracker update, and pressure management (M4 E4.2.3).
    """
    beliefs = args.get("beliefs", [])
    logger.info("tool:update_beliefs  count=%d actor=%s", len(beliefs), ctx.actor)
    if not beliefs:
        return ToolResult(
            tool_name="update_beliefs",
            status="error",
            error="beliefs array is required and must not be empty",
        )

    # Read-only access to check for existing SPO triples
    beliefs_section = ctx.session_manager.get_section("beliefs_active")
    writer_id = f"tool:{ctx.actor}"
    stored = 0
    updated = 0

    for belief in beliefs:
        subject = belief.get("subject", "")
        predicate = belief.get("predicate", "")
        obj = belief.get("object", "")
        confidence = belief.get("confidence", 1.0)

        if not subject or not predicate or not obj:
            continue

        # Check if a matching fact already exists (same SPO) -- read-only
        existing = None
        for fact in beliefs_section.find_by_subject(subject):
            if fact.predicate == predicate and fact.object == obj:
                existing = fact
                break

        if existing:
            # Update confidence via writer port
            req = MutationRequest.create(
                section="beliefs_active",
                operation="update_confidence",
                data={"id": existing.id, "confidence": confidence},
                writer_id=writer_id,
                cognitive_trace_id=ctx.cognitive_trace_id,
            )
            resp = ctx.writer_port.request_mutation(req)
            if not resp.approved:
                return ToolResult(
                    tool_name="update_beliefs",
                    status="error",
                    error=resp.reason,
                )
            updated += 1
        else:
            # Add new fact via writer port
            req = MutationRequest.create(
                section="beliefs_active",
                operation="add_fact",
                data={
                    "subject": subject,
                    "predicate": predicate,
                    "obj": obj,
                    "confidence": confidence,
                    "source": f"llm:{ctx.actor}",
                },
                writer_id=writer_id,
                cognitive_trace_id=ctx.cognitive_trace_id,
            )
            resp = ctx.writer_port.request_mutation(req)
            if not resp.approved:
                return ToolResult(
                    tool_name="update_beliefs",
                    status="error",
                    error=resp.reason,
                )
            stored += 1

    return ToolResult(
        tool_name="update_beliefs",
        status="ok",
        data={"stored": stored, "updated": updated},
    )


@_register("update_scoreboard")
def execute_update_scoreboard(args: dict, ctx: ToolContext) -> ToolResult:
    """Update the conversational scoreboard.

    Handles QUD push/pop, referent resolution, and topic shifts.
    Routes each sub-action through writer_port (M4 E4.2.3).
    """
    logger.info(
        "tool:update_scoreboard  qud_push=%s qud_pop=%s referents=%d topic_shift=%s",
        bool(args.get("qud_push")),
        args.get("qud_pop", False),
        len(args.get("referent_updates", {})),
        bool(args.get("topic_shift")),
    )

    writer_id = f"tool:{ctx.actor}"
    qud_push = args.get("qud_push")
    qud_pop = args.get("qud_pop", False)
    referent_updates = args.get("referent_updates", {})
    topic_shift = args.get("topic_shift")

    # Pop QUD if requested (before push, so push replaces it)
    if qud_pop:
        req = MutationRequest.create(
            section="scoreboard",
            operation="pop_question",
            data={},
            writer_id=writer_id,
            cognitive_trace_id=ctx.cognitive_trace_id,
        )
        resp = ctx.writer_port.request_mutation(req)
        if not resp.approved:
            return ToolResult(tool_name="update_scoreboard", status="error", error=resp.reason)

    # Push new QUD
    if qud_push:
        req = MutationRequest.create(
            section="scoreboard",
            operation="push_question",
            data={"text": qud_push, "asked_by": "user"},
            writer_id=writer_id,
            cognitive_trace_id=ctx.cognitive_trace_id,
        )
        resp = ctx.writer_port.request_mutation(req)
        if not resp.approved:
            return ToolResult(tool_name="update_scoreboard", status="error", error=resp.reason)

    # Update referents (pronoun -> resolved entity)
    for ref_text, entity_id in referent_updates.items():
        req = MutationRequest.create(
            section="scoreboard",
            operation="add_referent",
            data={
                "text": ref_text,
                "entity_id": entity_id,
                "entity_type": "resolved",
                "salience": 0.8,
            },
            writer_id=writer_id,
            cognitive_trace_id=ctx.cognitive_trace_id,
        )
        resp = ctx.writer_port.request_mutation(req)
        if not resp.approved:
            return ToolResult(tool_name="update_scoreboard", status="error", error=resp.reason)

    # Topic shift
    if topic_shift:
        req = MutationRequest.create(
            section="scoreboard",
            operation="push_topic",
            data={"name": topic_shift, "is_primary": True},
            writer_id=writer_id,
            cognitive_trace_id=ctx.cognitive_trace_id,
        )
        resp = ctx.writer_port.request_mutation(req)
        if not resp.approved:
            return ToolResult(tool_name="update_scoreboard", status="error", error=resp.reason)

    # Read-only access for response counts
    scoreboard = ctx.session_manager.get_section("scoreboard")
    return ToolResult(
        tool_name="update_scoreboard",
        status="ok",
        data={
            "qud_depth": len(scoreboard._qud_stack),
            "active_referents": len(scoreboard._referents),
        },
    )


@_register("update_clarifications")
def execute_update_clarifications(args: dict, ctx: ToolContext) -> ToolResult:
    """Record or resolve semantic gaps in user intent.

    Adds new gaps and resolves existing ones through writer_port (M4 E4.2.3).
    """
    gaps = args.get("gaps", [])
    resolved_gaps = args.get("resolved_gaps", [])
    logger.info(
        "tool:update_clarifications  new_gaps=%d resolve=%d",
        len(gaps),
        len(resolved_gaps),
    )

    writer_id = f"tool:{ctx.actor}"

    # Add new gaps via writer port
    for gap in gaps:
        gap_field = gap.get("field", "")
        question = gap.get("question", "")
        severity = gap.get("severity", "helpful")

        if not gap_field or not question:
            continue

        # Map severity to priority value
        priority_map = {
            "blocking": 2,  # ClarificationPriority.URGENT
            "helpful": 1,  # ClarificationPriority.HIGH
            "minor": 0,  # ClarificationPriority.NORMAL
        }
        priority_val = priority_map.get(severity, 0)

        req = MutationRequest.create(
            section="clarifications",
            operation="request",
            data={
                "agent_id": f"llm:{ctx.actor}",
                "question": question,
                "priority": priority_val,
                "related_entity": gap_field,
                "blocking": severity == "blocking",
            },
            writer_id=writer_id,
            cognitive_trace_id=ctx.cognitive_trace_id,
        )
        resp = ctx.writer_port.request_mutation(req)
        if not resp.approved:
            return ToolResult(tool_name="update_clarifications", status="error", error=resp.reason)

    # Resolve existing gaps -- read-only lookup then write via port
    clarifications = ctx.session_manager.get_section("clarifications")
    for field_name in resolved_gaps:
        for clar in clarifications.list_pending():
            if clar.related_entity == field_name:
                req = MutationRequest.create(
                    section="clarifications",
                    operation="answer",
                    data={
                        "clarification_id": clar.id,
                        "answer": f"Resolved: {field_name}",
                    },
                    writer_id=writer_id,
                    cognitive_trace_id=ctx.cognitive_trace_id,
                )
                resp = ctx.writer_port.request_mutation(req)
                if not resp.approved:
                    return ToolResult(
                        tool_name="update_clarifications",
                        status="error",
                        error=resp.reason,
                    )
                break

    # Count results -- read-only
    pending = clarifications.list_pending()
    open_gaps = len(pending)
    blocking_gaps = sum(1 for c in pending if c.is_blocking)

    return ToolResult(
        tool_name="update_clarifications",
        status="ok",
        data={
            "open_gaps": open_gaps,
            "blocking_gaps": blocking_gaps,
        },
    )


@_register("update_narrative")
def execute_update_narrative(args: dict, ctx: ToolContext) -> ToolResult:
    """Track conversation thread switches, resumptions, and closures.

    Routes writes through writer_port (M4 E4.2.3). Read-only section
    access for thread existence checks and response data.
    """
    narrative = ctx.session_manager.get_section("narrative_active")
    writer_id = f"tool:{ctx.actor}"

    action = args.get("action", "")
    thread_id = args.get("thread_id", "")
    summary = args.get("summary", "")

    if not action or not thread_id:
        return ToolResult(
            tool_name="update_narrative",
            status="error",
            error="action and thread_id are required",
        )

    if action == "switch":
        # Check if thread exists (read-only); if not, create it
        existing = narrative.get_thread(thread_id)
        if existing:
            req = MutationRequest.create(
                section="narrative_active",
                operation="switch_to",
                data={"thread_id": thread_id},
                writer_id=writer_id,
                cognitive_trace_id=ctx.cognitive_trace_id,
            )
        else:
            req = MutationRequest.create(
                section="narrative_active",
                operation="create_thread",
                data={
                    "title": thread_id,
                    "goal": summary or "",
                    "auto_switch": True,
                },
                writer_id=writer_id,
                cognitive_trace_id=ctx.cognitive_trace_id,
            )
        resp = ctx.writer_port.request_mutation(req)
        if not resp.approved:
            return ToolResult(tool_name="update_narrative", status="error", error=resp.reason)

    elif action == "resume":
        existing = narrative.get_thread(thread_id)
        if existing:
            req = MutationRequest.create(
                section="narrative_active",
                operation="switch_to",
                data={"thread_id": thread_id},
                writer_id=writer_id,
                cognitive_trace_id=ctx.cognitive_trace_id,
            )
        else:
            # Thread not yet opened -- auto-create (same as switch)
            req = MutationRequest.create(
                section="narrative_active",
                operation="create_thread",
                data={
                    "title": thread_id,
                    "goal": summary or "",
                    "auto_switch": True,
                },
                writer_id=writer_id,
                cognitive_trace_id=ctx.cognitive_trace_id,
            )
        resp = ctx.writer_port.request_mutation(req)
        if not resp.approved:
            return ToolResult(tool_name="update_narrative", status="error", error=resp.reason)

    elif action == "close":
        existing = narrative.get_thread(thread_id)
        if not existing:
            # Idempotent: thread never opened or already closed -- succeed
            primary = narrative._primary_thread
            active_thread = primary.title if primary else ""
            total_threads = len(narrative._thread_index)
            return ToolResult(
                tool_name="update_narrative",
                status="ok",
                data={
                    "active_thread": active_thread,
                    "total_threads": total_threads,
                    "note": "thread already closed or never opened",
                },
            )
        req = MutationRequest.create(
            section="narrative_active",
            operation="resolve_thread",
            data={"thread_id": thread_id},
            writer_id=writer_id,
            cognitive_trace_id=ctx.cognitive_trace_id,
        )
        resp = ctx.writer_port.request_mutation(req)
        if not resp.approved:
            return ToolResult(tool_name="update_narrative", status="error", error=resp.reason)
    else:
        return ToolResult(
            tool_name="update_narrative",
            status="error",
            error=f"Unknown action: {action}. Must be switch/resume/close.",
        )

    # Build response -- read-only
    primary = narrative._primary_thread
    active_thread = primary.title if primary else ""
    total_threads = len(narrative._thread_index)

    return ToolResult(
        tool_name="update_narrative",
        status="ok",
        data={
            "active_thread": active_thread,
            "total_threads": total_threads,
        },
    )


@_register("refine_affect")
def execute_refine_affect(args: dict, ctx: ToolContext) -> ToolResult:
    """Override Phase 1 emotion classification with LLM assessment.

    Routes update through writer_port (M4 E4.2.3). Read-only section
    access to capture previous emotion for observation.
    """
    affect = ctx.session_manager.get_section("affective_now")

    emotion = args.get("emotion", "")
    valence = args.get("valence")
    arousal = args.get("arousal")
    confidence = args.get("confidence", 0.8)
    logger.info(
        "tool:refine_affect  emotion=%s valence=%s arousal=%s confidence=%.2f",
        emotion,
        valence,
        arousal,
        confidence,
    )

    if not emotion or valence is None or arousal is None:
        return ToolResult(
            tool_name="refine_affect",
            status="error",
            error="emotion, valence, and arousal are required",
        )

    # Capture previous for observation (read-only)
    previous_emotion = affect._current_emotion

    # Apply via writer port
    req = MutationRequest.create(
        section="affective_now",
        operation="update",
        data={
            "emotion": emotion,
            "intensity": abs(valence),
            "valence": valence,
            "arousal": arousal,
            "confidence": confidence,
            "source": f"llm:{ctx.actor}",
        },
        writer_id=f"tool:{ctx.actor}",
        cognitive_trace_id=ctx.cognitive_trace_id,
    )
    resp = ctx.writer_port.request_mutation(req)
    if not resp.approved:
        return ToolResult(tool_name="refine_affect", status="error", error=resp.reason)

    return ToolResult(
        tool_name="refine_affect",
        status="ok",
        data={
            "previous_emotion": previous_emotion,
            "updated": True,
        },
    )


@_register("promote_belief")
def execute_promote_belief(args: dict, ctx: ToolContext) -> ToolResult:
    """Promote a belief to higher confidence.

    Finds the belief by ID (read-only) then routes write through
    writer_port (M4 E4.2.3).
    """
    # Read-only lookup for existence check and tier calculation
    beliefs = ctx.session_manager.get_section("beliefs_active")

    belief_id = args.get("belief_id", "")
    new_confidence = args.get("new_confidence")

    if not belief_id or new_confidence is None:
        return ToolResult(
            tool_name="promote_belief",
            status="error",
            error="belief_id and new_confidence are required",
        )

    # Get current fact (read-only)
    fact = beliefs.get_fact(belief_id)
    if not fact:
        return ToolResult(
            tool_name="promote_belief",
            status="error",
            error=f"Belief '{belief_id}' not found",
        )

    # Determine tier before promotion
    if fact.confidence >= 0.8:
        from_tier = "HOT"
    elif fact.confidence >= 0.5:
        from_tier = "WARM"
    else:
        from_tier = "COLD"

    # Apply confidence update via writer port
    req = MutationRequest.create(
        section="beliefs_active",
        operation="update_confidence",
        data={"id": belief_id, "confidence": new_confidence},
        writer_id=f"tool:{ctx.actor}",
        cognitive_trace_id=ctx.cognitive_trace_id,
    )
    resp = ctx.writer_port.request_mutation(req)
    if not resp.approved:
        return ToolResult(tool_name="promote_belief", status="error", error=resp.reason)

    return ToolResult(
        tool_name="promote_belief",
        status="ok",
        data={
            "promoted": True,
            "from_tier": from_tier,
        },
    )


# =========================================================================
# BUNDLE (1) -- Front only, batched writes to SS
# =========================================================================


@_register("update_session_bundle")
def execute_update_session_bundle(args: dict, ctx: ToolContext) -> ToolResult:
    """Write to multiple SS sections in a single tool call.

    Accepts an ordered list of mutations, an idempotency_key to prevent
    duplicate application on retry, and stop_on_rejection to control
    whether remaining mutations are cancelled on first failure.

    Routes through writer_port.batch_mutations for batch-level
    authorization, consistent trace ID, and aggregate result tracking
    (M4 E4.3.1 / E4.3.2 / E4.3.3).
    """
    mutations = args.get("mutations", [])
    idempotency_key = args.get("idempotency_key", "")
    stop_on_rejection = args.get("stop_on_rejection", True)

    logger.info(
        "tool:update_session_bundle  mutations=%d key=%s stop_on_reject=%s actor=%s",
        len(mutations),
        idempotency_key[:20] if idempotency_key else "(none)",
        stop_on_rejection,
        ctx.actor,
    )

    # Lazy-init idempotency cache on first use
    if ctx.bundle_idempotency_cache is None:
        ctx.bundle_idempotency_cache = {}

    # Idempotency check: return cached result without re-applying
    if idempotency_key and idempotency_key in ctx.bundle_idempotency_cache:
        logger.info(
            "tool:update_session_bundle  idempotency hit key=%s",
            idempotency_key[:20],
        )
        return ctx.bundle_idempotency_cache[idempotency_key]

    if not mutations:
        return ToolResult(
            tool_name="update_session_bundle",
            status="error",
            error="mutations array is required and must not be empty",
        )

    # Build BatchRequest from tool args (E4.3.2)
    writer_id = f"tool:{ctx.actor}"
    requests = []
    for m in mutations:
        section = m.get("section", "")
        operation = m.get("operation", "")
        data = m.get("data", {})
        if not section or not operation:
            return ToolResult(
                tool_name="update_session_bundle",
                status="error",
                error="Each mutation must have 'section' and 'operation'",
            )
        requests.append(
            MutationRequest.create(
                section=section,
                operation=operation,
                data=data,
                writer_id=writer_id,
                cognitive_trace_id=ctx.cognitive_trace_id,
            )
        )

    batch = BatchRequest.create(
        requests=requests,
        writer_id=writer_id,
        cognitive_trace_id=ctx.cognitive_trace_id,
        stop_on_rejection=stop_on_rejection,
    )
    result = ctx.writer_port.batch_mutations(batch)

    # Map BatchResult to ToolResult (E4.3.3)
    if result.applied_count == result.total_requests:
        status = "ok"
    elif result.applied_count == 0:
        status = "error"
    else:
        status = "partial"

    tool_result = ToolResult(
        tool_name="update_session_bundle",
        status=status,
        data={
            "applied": result.applied_count,
            "rejected": result.rejected_count,
            "cancelled": result.cancelled_count,
            "stopped_early": result.stopped_early,
            "details": [
                {
                    "section": r.section,
                    "status": r.status.value,
                    "reason": r.reason,
                }
                for r in result.responses
            ],
        },
    )

    # Cache for idempotency dedup
    if idempotency_key:
        ctx.bundle_idempotency_cache[idempotency_key] = tool_result

    return tool_result


# =========================================================================
# READ (2) -- recall_memory is shared (front + back)
# =========================================================================


@_register("recall_memory")
async def execute_recall_memory(args: dict, ctx: ToolContext) -> ToolResult:
    """Query K0 long-term memory for relevant context.

    Delegates to ctx.recall_fn if available (production).
    Returns empty results in POC when no recall_fn is wired.
    """
    query = args.get("query", "")
    memory_types = args.get("memory_types", ["episodic", "semantic", "procedural"])
    max_results = args.get("max_results", 5)
    logger.info(
        "tool:recall_memory  query=%s types=%s max=%d has_fn=%s",
        query[:80] if query else "(empty)",
        memory_types,
        max_results,
        ctx.recall_fn is not None,
    )

    if not query:
        return ToolResult(
            tool_name="recall_memory",
            status="error",
            error="query is required",
        )

    if ctx.recall_fn:
        try:
            result = ctx.recall_fn(query, memory_types, max_results)
            if _inspect.isawaitable(result):
                result = await result
            return ToolResult(
                tool_name="recall_memory",
                status="ok",
                data={
                    "memories": result,
                    "count": len(result),
                },
            )
        except Exception as e:
            return ToolResult(
                tool_name="recall_memory",
                status="error",
                error=str(e),
            )

    # POC: no K0 recall_fn wired -- return empty
    return ToolResult(
        tool_name="recall_memory",
        status="ok",
        data={
            "memories": [],
            "count": 0,
        },
    )


@_register("summarize_context")
def execute_summarize_context(args: dict, ctx: ToolContext) -> ToolResult:
    """Compress Session State sections to fit within token budget.

    Reads specified SS sections and produces a compressed text representation.
    This is a read-only operation -- no SS mutation.
    """
    sections = args.get("sections", [])
    target_tokens = args.get("target_tokens", 500)

    if not sections:
        return ToolResult(
            tool_name="summarize_context",
            status="error",
            error="sections array is required",
        )

    # Collect section data
    parts = []
    original_chars = 0

    for section_name in sections:
        try:
            section = ctx.session_manager.get_section(section_name)
            # Use get_metadata if available for a compact summary
            if hasattr(section, "get_metadata"):
                metadata = section.get_metadata()
                text = f"[{section_name}]: {metadata}"
            else:
                text = f"[{section_name}]: (section data)"
            parts.append(text)
            original_chars += len(text)
        except Exception:
            parts.append(f"[{section_name}]: (not found)")

    compressed = "\n".join(parts)

    # Rough token estimate (4 chars per token)
    original_tokens = original_chars // 4
    compressed_tokens = len(compressed) // 4

    # Truncate if exceeds target
    if compressed_tokens > target_tokens:
        max_chars = target_tokens * 4
        compressed = compressed[:max_chars] + "..."
        compressed_tokens = target_tokens

    return ToolResult(
        tool_name="summarize_context",
        status="ok",
        data={
            "compressed": compressed,
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
        },
    )


# =========================================================================
# CONTROL (1) -- Front only
# =========================================================================


@_register("dispatch_task")
def execute_dispatch_task(args: dict, ctx: ToolContext) -> ToolResult:
    """Dispatch a task to the background worker.

    The FSM intercepts this result and emits
    k1.orchestration.task.dispatch.v1 on the bus. The tool itself
    does NOT emit events -- it returns structured data for the handler.
    """
    intents = args.get("intents", [])
    urgency = str(args.get("urgency", "normal")).lower()
    reference_context = args.get("reference_context", {})
    depends_on = args.get("depends_on")
    safety_band = args.get("safety_band", "AMBER")

    # Gracefully handle LLM passing a description string instead of a task ID.
    # The LLM sometimes puts an action description in depends_on rather than
    # a task-xxx ID.  Strip it so TaskDispatch validation does not crash.
    if depends_on is not None and not depends_on.startswith("task-"):
        logger.warning(
            "tool:dispatch_task  depends_on is not a task ID, ignoring: %s",
            depends_on,
        )
        depends_on = None
    tier_raw = args.get("tier", "AUTO")
    # M10 E10.3.1: AUTO reads tier from SS control section
    if str(tier_raw).upper() == "AUTO" and ctx.session_manager is not None:
        try:
            control = ctx.session_manager.get_section("control")
            if control is not None and hasattr(control, "get_complexity_tier"):
                ss_tier = control.get_complexity_tier()
                if ss_tier:
                    tier_raw = ss_tier
                else:
                    tier_raw = "LOW"
                    logger.warning(
                        "tool:dispatch_task  no complexity_tier in SS, defaulting to LOW"
                    )
            else:
                tier_raw = "LOW"
        except Exception:
            logger.warning(
                "tool:dispatch_task  failed to read SS tier, defaulting to LOW",
                exc_info=True,
            )
            tier_raw = "LOW"
    elif str(tier_raw).upper() == "AUTO":
        tier_raw = "LOW"
        logger.warning("tool:dispatch_task  AUTO tier but no session_manager, defaulting to LOW")
    logger.info(
        "tool:dispatch_task  intents=%d urgency=%s tier=%s safety=%s",
        len(intents),
        urgency,
        tier_raw,
        safety_band,
    )

    urgency_aliases = {
        "high": "urgent",
        "low": "background",
    }
    urgency = urgency_aliases.get(urgency, urgency)

    if not intents:
        return ToolResult(
            tool_name="dispatch_task",
            status="error",
            error="intents array is required and must not be empty",
        )

    try:
        tier = ComplexityTier(str(tier_raw).upper())
    except ValueError:
        return ToolResult(
            tool_name="dispatch_task",
            status="error",
            error=f"invalid tier '{tier_raw}' (expected LOW, MEDIUM, or HIGH)",
        )

    normalized_intents: list[TaskIntent] = []
    try:
        for intent in intents:
            if isinstance(intent, dict):
                intent_data = dict(intent)
                raw_intent_urgency = str(intent_data.get("urgency", urgency)).lower()
                intent_data["urgency"] = urgency_aliases.get(
                    raw_intent_urgency,
                    raw_intent_urgency,
                )
                normalized_intents.append(TaskIntent.from_dict(intent_data))
            elif isinstance(intent, str):
                normalized_intents.append(TaskIntent(action=intent, params={}, urgency=urgency))
            else:
                raise ValueError("each intent must be an object or string")
    except (KeyError, ValueError) as exc:
        return ToolResult(
            tool_name="dispatch_task",
            status="error",
            error=f"invalid intents payload: {exc}",
        )

    dispatch = TaskDispatch(
        intents=normalized_intents,
        tier=tier,
        reference_context=reference_context,
        safety_band=safety_band,
        depends_on=depends_on,
    )
    dispatch_payload = dispatch.to_dict()
    for idx, intent_payload in enumerate(dispatch_payload.get("intents", [])):
        if idx < len(normalized_intents):
            intent_payload.setdefault("urgency", normalized_intents[idx].urgency)
    dispatch_payload["urgency"] = urgency

    return ToolResult(
        tool_name="dispatch_task",
        status="ok",
        data={
            "queued": True,
            "task_id": dispatch.task_id,
            # Stashed for the handler to emit as bus event
            "_dispatch": dispatch_payload,
        },
    )


# =========================================================================
# BACK -- READ (1 exclusive, recall_memory is shared above)
# =========================================================================


@_register("discover_capabilities")
async def execute_discover_capabilities(args: dict, ctx: ToolContext) -> ToolResult:
    """Query K0 capability registry.

    Delegates to ctx.capability_fn if available (production).
    Returns empty in POC when no capability_fn is wired.

    Results are cached per-session by (intent, domain) to avoid
    redundant lookups when the LLM calls discover_capabilities
    repeatedly with the same or similar parameters.
    """
    intent = args.get("intent", "")
    domain = args.get("domain")
    constraints = args.get("constraints")
    logger.info(
        "tool:discover_capabilities  intent=%s domain=%s has_fn=%s",
        intent[:80] if intent else "(empty)",
        domain,
        ctx.capability_fn is not None,
    )

    if not intent:
        return ToolResult(
            tool_name="discover_capabilities",
            status="error",
            error="intent is required",
        )

    # Per-session cache: avoid redundant capability lookups
    if ctx.capability_cache is None:
        ctx.capability_cache = {}
    cache_key = (intent.strip().lower(), (domain or "").strip().lower())
    if cache_key in ctx.capability_cache:
        logger.info(
            "tool:discover_capabilities  CACHE HIT intent=%s domain=%s",
            intent[:60],
            domain,
        )
        return ctx.capability_cache[cache_key]

    if ctx.capability_fn:
        try:
            result = ctx.capability_fn(intent, domain, constraints)
            if _inspect.isawaitable(result):
                result = await result
            # result may be a dict with capabilities/count/hint (new)
            # or a plain list (legacy wiring).
            if isinstance(result, dict):
                caps = result.get("capabilities", [])
                data = {
                    "capabilities": caps,
                    "count": len(caps),
                }
                if not caps and "hint" in result:
                    data["hint"] = result["hint"]
            else:
                # Legacy: result is a list of capability dicts
                caps = result if isinstance(result, list) else []
                data = {
                    "capabilities": caps,
                    "count": len(caps),
                }
            if not caps:
                logger.warning(
                    "discover_capabilities: no match for intent=%s domain=%s",
                    intent[:60],
                    domain,
                )
            tool_result = ToolResult(
                tool_name="discover_capabilities",
                status="ok",
                data=data,
            )
            ctx.capability_cache[cache_key] = tool_result
            return tool_result
        except Exception as e:
            return ToolResult(
                tool_name="discover_capabilities",
                status="error",
                error=str(e),
            )

    # POC: no capability registry -- return empty
    tool_result = ToolResult(
        tool_name="discover_capabilities",
        status="ok",
        data={
            "capabilities": [],
            "count": 0,
        },
    )
    ctx.capability_cache[cache_key] = tool_result
    return tool_result


# =========================================================================
# BACK -- ACTION (3)
# =========================================================================


@_register("invoke_capability")
async def execute_invoke_capability(args: dict, ctx: ToolContext) -> ToolResult:
    """Invoke a K0 capability by name.

    Delegates to ctx.invoke_fn if available (production).
    Returns a placeholder result in POC when no invoke_fn is wired.

    M6 E6.1.3: L2 defense-in-depth -- block side-effect invocations
    when a HITL sub-task is PENDING for this task_id.
    """
    capability_name = args.get("capability_name", "")
    params = args.get("params", {})
    session_id = args.get("session_id")

    # M6 E6.1.3: L2 side-effect blocking when HITL pending for this task.
    # validate_before_invoke exists on HILCoordinator but was never called.
    # Cognitive tools (update_beliefs, etc.) go through writer_port, NOT here.
    if ctx.hil_coordinator is not None and ctx.active_task_id:
        # Check if there's a pending HITL for this task (defense-in-depth).
        # Normal flow should never reach here while suspended (Back's loop
        # already terminated via submit_result), but stale/replayed calls
        # could arrive.
        pending_req = None
        try:
            pending_req = ctx.hil_coordinator.get_pending_request(ctx.active_task_id)
        except Exception:
            pass
        if pending_req is not None:
            logger.warning(
                "tool:invoke_capability BLOCKED (HITL pending) capability=%s task=%s",
                capability_name,
                ctx.active_task_id,
            )
            return ToolResult(
                tool_name="invoke_capability",
                status="blocked",
                error="HITL pending for task -- capability execution blocked",
                data={"reason": "block_needs_approval", "capability": capability_name},
            )
        # Also check capability contract via validate_before_invoke
        try:
            contract = {"name": capability_name, "has_side_effects": True, "safety_band": "AMBER"}
            decision = ctx.hil_coordinator.validate_before_invoke(
                task_id=ctx.active_task_id,
                capability_contract=contract,
            )
        except Exception:
            decision = "allow"
        if decision == "block_red":
            logger.warning(
                "tool:invoke_capability BLOCKED (RED) capability=%s task=%s",
                capability_name,
                ctx.active_task_id,
            )
            return ToolResult(
                tool_name="invoke_capability",
                status="blocked",
                error="RED safety band -- execution blocked entirely",
                data={"reason": "block_red", "capability": capability_name},
            )
        if decision == "block_needs_approval":
            logger.warning(
                "tool:invoke_capability BLOCKED (needs_approval) capability=%s task=%s",
                capability_name,
                ctx.active_task_id,
            )
            return ToolResult(
                tool_name="invoke_capability",
                status="blocked",
                error="Side effects require approval -- capability execution blocked",
                data={"reason": "block_needs_approval", "capability": capability_name},
            )

    logger.info(
        "tool:invoke_capability  capability=%s params_keys=%s has_fn=%s",
        capability_name,
        list(params.keys()),
        ctx.invoke_fn is not None,
    )

    if not capability_name:
        return ToolResult(
            tool_name="invoke_capability",
            status="error",
            error="capability_name is required",
        )

    start_ms = int(time.time() * 1000)

    if ctx.invoke_fn:
        try:
            invoke_result = ctx.invoke_fn(capability_name, params, session_id)
            if _inspect.isawaitable(invoke_result):
                invoke_result = await invoke_result
            duration = int(time.time() * 1000) - start_ms
            return ToolResult(
                tool_name="invoke_capability",
                status="ok",
                data={
                    "result": invoke_result,
                    "duration_ms": duration,
                    "status": "success",
                },
            )
        except Exception as e:
            duration = int(time.time() * 1000) - start_ms
            return ToolResult(
                tool_name="invoke_capability",
                status="error",
                error=str(e),
                data={"duration_ms": duration, "status": "error"},
            )

    # POC: no invoke_fn wired
    duration = int(time.time() * 1000) - start_ms
    return ToolResult(
        tool_name="invoke_capability",
        status="ok",
        data={
            "result": {"_poc": True, "capability": capability_name, "params": params},
            "duration_ms": duration,
            "status": "success",
        },
    )


@_register("batch_invoke_capabilities")
async def execute_batch_invoke_capabilities(args: dict, ctx: ToolContext) -> ToolResult:
    """Invoke multiple capabilities in a single tool call.

    Each invocation in the batch runs independently. This saves tool
    budget: 4 capability invocations cost only 1 tool call instead of 4.

    The implementation delegates to the same invoke_fn used by
    invoke_capability but processes all invocations in sequence.
    """
    invocations = args.get("invocations", [])
    if not invocations:
        return ToolResult(
            tool_name="batch_invoke_capabilities",
            status="error",
            error="invocations array is required and must not be empty",
        )

    logger.info(
        "tool:batch_invoke_capabilities  count=%d has_fn=%s",
        len(invocations),
        ctx.invoke_fn is not None,
    )

    results = []
    succeeded = 0
    failed = 0

    for inv in invocations:
        cap_name = inv.get("capability_name", "")
        params = inv.get("params", {})

        if not cap_name:
            results.append(
                {
                    "capability_name": cap_name,
                    "status": "error",
                    "error": "capability_name is required",
                    "result": None,
                }
            )
            failed += 1
            continue

        start_ms = int(time.time() * 1000)

        if ctx.invoke_fn:
            try:
                invoke_result = ctx.invoke_fn(cap_name, params, None)
                if _inspect.isawaitable(invoke_result):
                    invoke_result = await invoke_result
                duration = int(time.time() * 1000) - start_ms
                results.append(
                    {
                        "capability_name": cap_name,
                        "status": "success",
                        "result": invoke_result,
                        "duration_ms": duration,
                    }
                )
                succeeded += 1
            except Exception as e:
                duration = int(time.time() * 1000) - start_ms
                results.append(
                    {
                        "capability_name": cap_name,
                        "status": "error",
                        "error": str(e),
                        "duration_ms": duration,
                    }
                )
                failed += 1
        else:
            # POC: no invoke_fn wired
            duration = int(time.time() * 1000) - start_ms
            results.append(
                {
                    "capability_name": cap_name,
                    "status": "success",
                    "result": {"_poc": True, "capability": cap_name, "params": params},
                    "duration_ms": duration,
                }
            )
            succeeded += 1

    return ToolResult(
        tool_name="batch_invoke_capabilities",
        status="ok",
        data={
            "results": results,
            "total": len(invocations),
            "succeeded": succeeded,
            "failed": failed,
        },
    )


@_register("spawn_via_fabric")
def execute_spawn_via_fabric(args: dict, ctx: ToolContext) -> ToolResult:
    """Spawn a specialized agent via K0 Agent Fabric.

    Delegates to ctx.fabric_fn if available (production).
    Returns a placeholder result in POC when no fabric_fn is wired.
    """
    agent_type = args.get("agent_type", "")
    task = args.get("task", "")
    constraints = args.get("constraints")
    capabilities_needed = args.get("capabilities_needed")

    if not agent_type or not task:
        return ToolResult(
            tool_name="spawn_via_fabric",
            status="error",
            error="agent_type and task are required",
        )

    if ctx.fabric_fn:
        try:
            result = ctx.fabric_fn(agent_type, task, constraints, capabilities_needed)
            return ToolResult(
                tool_name="spawn_via_fabric",
                status="ok",
                data=result,
            )
        except Exception as e:
            return ToolResult(
                tool_name="spawn_via_fabric",
                status="error",
                error=str(e),
            )

    # POC: no fabric_fn wired
    agent_id = f"agent-{uuid.uuid4().hex[:12]}"
    return ToolResult(
        tool_name="spawn_via_fabric",
        status="ok",
        data={
            "agent_id": agent_id,
            "status": "spawned",
            "estimated_duration_ms": 5000,
        },
    )


@_register("execute_workflow")
def execute_execute_workflow(args: dict, ctx: ToolContext) -> ToolResult:
    """Execute a predefined workflow by ID.

    Delegates to ctx.workflow_fn if available (production).
    Returns a placeholder result in POC when no workflow_fn is wired.
    """
    workflow_id = args.get("workflow_id", "")
    params = args.get("params", {})
    timeout_ms = args.get("timeout_ms", 30000)

    if not workflow_id:
        return ToolResult(
            tool_name="execute_workflow",
            status="error",
            error="workflow_id is required",
        )

    if ctx.workflow_fn:
        try:
            result = ctx.workflow_fn(workflow_id, params, timeout_ms)
            return ToolResult(
                tool_name="execute_workflow",
                status="ok",
                data=result,
            )
        except Exception as e:
            return ToolResult(
                tool_name="execute_workflow",
                status="error",
                error=str(e),
            )

    # POC: no workflow_fn wired
    execution_id = f"exec-{uuid.uuid4().hex[:12]}"
    return ToolResult(
        tool_name="execute_workflow",
        status="ok",
        data={
            "execution_id": execution_id,
            "status": "completed",
            "result": {"_poc": True, "workflow": workflow_id, "params": params},
        },
    )


# =========================================================================
# BACK -- CONTROL (1)
# =========================================================================


@_register("submit_result")
def execute_submit_result(args: dict, ctx: ToolContext) -> ToolResult:
    """Submit task result back to Front via orchestrator.

    The FSM intercepts this and routes appropriately:
    - result_type="complete" -> k1.orchestration.task.complete.v1
    - result_type="needs_human" -> k1.orchestration.task.suspended.v1

    The tool itself does NOT emit events.
    """
    result_type = args.get("result_type", "")
    logger.info("tool:submit_result  result_type=%s", result_type)

    if result_type not in ("complete", "needs_human"):
        return ToolResult(
            tool_name="submit_result",
            status="error",
            error="result_type must be 'complete' or 'needs_human'",
        )

    weave_event_id = f"weave-{uuid.uuid4().hex[:12]}"

    # Stash the full submission for the handler
    submission: dict = {"result_type": result_type}

    if result_type == "complete":
        submission["final_answer"] = args.get("final_answer", "")
        submission["results"] = args.get("results", [])
        submission["artifacts_created"] = args.get("artifacts_created", [])
    else:
        submission["hil_type"] = args.get("hil_type", "provide_info")
        submission["question"] = args.get("question", "")
        submission["options"] = args.get("options", [])
        submission["side_effects"] = args.get("side_effects", "")

    return ToolResult(
        tool_name="submit_result",
        status="ok",
        data={
            "delivered": True,
            "weave_event_id": weave_event_id,
            "_submission": submission,
        },
    )


# =========================================================================
# DISPATCH HELPER -- execute any tool by name
# =========================================================================


async def execute_tool(
    tool_name: str,
    args: dict,
    ctx: ToolContext,
) -> ToolResult:
    """Execute a tool by name with the given arguments.

    Looks up the tool in TOOL_REGISTRY and calls it. If the tool function
    returns a coroutine (because it delegates to async callbacks like
    recall_fn, capability_fn, invoke_fn), the coroutine is awaited.

    Args:
        tool_name: Tool name (must match a registered tool).
        args: The LLM's tool call arguments (already parsed from JSON).
        ctx: ToolContext with session manager and service references.

    Returns:
        ToolResult envelope with status, data, and optional error.
    """
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        logger.error("execute_tool: unknown tool=%s", tool_name)
        return ToolResult(
            tool_name=tool_name,
            status="error",
            error=f"Unknown tool: {tool_name}",
        )

    try:
        result = fn(args, ctx)
        # Support async tool implementations transparently
        if _inspect.isawaitable(result):
            result = await result
        logger.debug(
            "execute_tool  tool=%s status=%s",
            tool_name,
            result.status,
        )
        return result
    except Exception as e:
        logger.exception("execute_tool FAILED  tool=%s error=%s", tool_name, e)
        return ToolResult(
            tool_name=tool_name,
            status="error",
            error=f"Tool execution failed: {e}",
        )
