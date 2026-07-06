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
import re
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from k1.concierge.ports import IDispatchPort
from k1.concierge.task.complexity import ComplexityTier
from k1.concierge.task.dispatch import TaskDispatch
from k1.concierge.task.intent import TaskIntent
from k1.concierge.tools.recovery_contract import recovery_for_unsatisfied_contract
from k1.concierge.tools.result_protocol import ToolResult
from k1.fabric.types import CapabilityRequest

if TYPE_CHECKING:
    # E4.M1.3: HILCoordinatorLike import removed -- the L2 HIL enforcement
    # block in `execute_invoke_capability` was deleted in favour of the
    # fabric-level capability gate (E3), which guards every invocation
    # uniformly regardless of caller.
    from k1.sessionstate.ports.writer import IWriterPort

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
            Signature: ``(query: str, memory_types: list, max_results: int)
            -> list[dict]``. Production wires this via
            ``RecallMemoryAdapter`` (k1/concierge/adapters/recall_memory.py)
            which in turn calls ``IBridgeClient.query`` against the K0
            recall endpoint. The selfmodel handle wraps this in a
            ``RecallCitationWrapper`` after factory wiring (P3.5 install).
            ``None`` only in test contexts that build a bare ToolContext.
        dispatch: ``IDispatchPort`` (Fabric LOW + Orchestrator MED/HIGH).
            Production wires this via ``FabricDispatchAdapter``. The Back
            tools ``invoke_capability``, ``batch_invoke_capabilities``,
            ``spawn_via_fabric`` and ``execute_workflow`` all route
            ``CapabilityRequest``s through ``dispatch.dispatch_direct``.
            When ``None`` and ``allow_dispatch_passthrough=False`` (M17.E1.I1
            default) the tools refuse to run and return a clear
            ``dispatch_not_wired`` error. When the flag is True the legacy
            POC fallback returns synthetic ``{"_poc": True, ...}`` data
            (used by some test fixtures).

    Note: Earlier drafts of this dataclass exposed ``invoke_fn``,
    ``fabric_fn`` and ``workflow_fn`` as separate callable slots. They
    were collapsed into the unified ``dispatch: IDispatchPort`` port and
    no longer exist as attributes; the Back-actor tools route through
    ``dispatch.dispatch_direct`` with capability_name prefixes
    ``tool.*`` / ``agent.*`` / ``workflow.*``.
    """

    session_manager: Any  # SessionStateManager (avoid circular import)
    cognitive_trace_id: str = ""
    actor: str = "front"
    writer_port: "IWriterPort | None" = None  # M4 E4.2.1 write-path enforcement
    bundle_idempotency_cache: dict = None  # M4 E4.3.1 per-session dedup for update_session_bundle
    active_device_id: str | None = None  # M5 E5.5.6: device that triggered the current turn
    # E4.M1.3: `hil_coordinator` field removed -- replaced by the fabric
    # capability gate (E3). `active_task_id` is preserved for telemetry /
    # future per-task observability use.
    active_task_id: str | None = None  # M6 E6.1.3: task_id for per-task L2 checks
    active_execution_profiles: list[dict[str, Any]] | None = None
    session_id: str = ""  # bound session id -- fallback for invoke_capability
    safety_band: str = "GREEN"  # bound task safety band for Fabric CapabilityRequest
    dispatch: IDispatchPort | None = None  # P4B.3: typed IDispatchPort (Fabric + Orchestrator)
    recall_fn: Callable | None = None
    capability_cache: dict | None = None  # Per-session cache for discover_capabilities results
    # M17.E1.I1: hard-fail (False, default) vs legacy POC fallback (True)
    # when ``dispatch`` is None for back-actor capability tools.
    allow_dispatch_passthrough: bool = False
    # Phase 2: actor identity for resolve_situation / capability routing.
    # Set from the task's grounding metadata (identity_ref) by the back_handler.
    active_principal_id: str | None = None


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


def _tool_trace_id(ctx: ToolContext) -> str:
    trace_id = str(getattr(ctx, "cognitive_trace_id", "") or "")
    if trace_id:
        return trace_id
    trace_id = f"tool-{uuid.uuid4().hex[:12]}"
    ctx.cognitive_trace_id = trace_id
    return trace_id


_FABRIC_SAFETY_BANDS = frozenset({"GREEN", "AMBER", "RED", "CRISIS"})
_TASK_SAFETY_BANDS = frozenset({"GREEN", "AMBER", "RED"})


def _normalize_safety_band(
    value: Any,
    *,
    default: str = "GREEN",
    allowed: frozenset[str] = _FABRIC_SAFETY_BANDS,
) -> str:
    band = str(value or "").upper()
    if band in allowed:
        return band
    fallback = str(default or "GREEN").upper()
    return fallback if fallback in allowed else "GREEN"


def _context_safety_band(ctx: ToolContext) -> str:
    return _normalize_safety_band(getattr(ctx, "safety_band", "GREEN"), default="GREEN")


def _member_id_alias(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


def _task_text_assignee_alias(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    for pattern in (
        r"\bfor\s+([A-Za-z][A-Za-z _-]{1,40})$",
        r"\bto\s+([A-Za-z][A-Za-z _-]{1,40})\s+to\b",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate:
                return str(_member_id_alias(candidate))
    return ""


def _normalize_capability_params(capability_name: str, params: Any) -> dict[str, Any]:
    normalized = dict(params) if isinstance(params, dict) else {}
    if capability_name == "tool.execute.tasks.create_task":
        if not normalized.get("title"):
            for title_key in ("description", "content", "task", "task_title", "name", "summary"):
                if normalized.get(title_key):
                    normalized["title"] = normalized[title_key]
                    break
        if normalized.get("assigned_to"):
            normalized["assigned_to"] = _member_id_alias(normalized["assigned_to"])
        if not normalized.get("assigned_to") and normalized.get("assignee"):
            normalized["assigned_to"] = _member_id_alias(normalized["assignee"])
        if not normalized.get("assigned_to"):
            assignee = _task_text_assignee_alias(normalized.get("title"))
            if assignee:
                normalized["assigned_to"] = assignee
    if capability_name in {
        "tool.execute.reminders.create_reminder",
        "tool.read.reminders.list_reminders",
    }:
        if normalized.get("recipient"):
            normalized["recipient"] = _member_id_alias(normalized["recipient"])
    return normalized


def _contract_cache_key(capability_name: str) -> tuple[str, str]:
    return ("capability_contract", capability_name)


def _contract_name(contract: Any) -> str:
    if isinstance(contract, dict):
        return str(contract.get("name") or "")
    return str(getattr(contract, "name", "") or "")


def _input_specs_to_prompt_schema(specs: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in specs or []:
        to_dict = getattr(spec, "to_dict", None)
        if callable(to_dict):
            out.append(dict(to_dict()))
        else:
            out.append(
                {
                    "name": str(getattr(spec, "name", "") or ""),
                    "type": str(getattr(spec, "type", "") or ""),
                    "description": str(getattr(spec, "description", "") or ""),
                }
            )
    return out


def _capability_prompt_schema(contract: Any) -> dict[str, Any]:
    return {
        "required_inputs": _input_specs_to_prompt_schema(getattr(contract, "required_inputs", ())),
        "optional_inputs": _input_specs_to_prompt_schema(getattr(contract, "optional_inputs", ())),
        "capabilities": list(getattr(contract, "capabilities", ()) or ()),
        "output": dict(getattr(contract, "output", {}) or {}),
        "safety_band_min": str(getattr(contract, "safety_band_min", "") or ""),
    }


async def _lookup_capability_contract(ctx: ToolContext, capability_name: str) -> Any | None:
    exact = await _lookup_capability_contract_exact(ctx, capability_name)
    if exact is not None:
        return exact

    dispatch = ctx.dispatch
    if dispatch is None or not hasattr(dispatch, "discover_capabilities"):
        return None
    try:
        retrieval = await dispatch.discover_capabilities(
            intent=capability_name,
            domain=None,
            top_k=25,
            safety_band=_context_safety_band(ctx),
        )
    except Exception:
        logger.debug("capability schema lookup failed for %s", capability_name, exc_info=True)
        return None
    capabilities = getattr(retrieval, "capabilities", [])
    if not isinstance(capabilities, (list, tuple)):
        return None
    for scored in capabilities:
        contract = getattr(scored, "contract", None)
        if _contract_name(contract) == capability_name:
            ctx.capability_cache[_contract_cache_key(capability_name)] = contract
            return contract
    return None


async def _lookup_capability_contract_exact(
    ctx: ToolContext,
    capability_name: str,
) -> Any | None:
    if not capability_name:
        return None
    if ctx.capability_cache is None:
        ctx.capability_cache = {}
    cached = ctx.capability_cache.get(_contract_cache_key(capability_name))
    if cached is not None and _contract_name(cached) == capability_name:
        return cached
    dispatch = ctx.dispatch
    if dispatch is None:
        return None
    for lookup_name in ("lookup_capability", "lookup"):
        lookup = getattr(dispatch, lookup_name, None)
        if not callable(lookup):
            continue
        try:
            contract = lookup(capability_name)
            if _inspect.isawaitable(contract):
                contract = await contract
        except Exception:
            logger.debug(
                "capability exact lookup failed via %s for %s",
                lookup_name,
                capability_name,
                exc_info=True,
            )
            continue
        if _contract_name(contract) == capability_name:
            ctx.capability_cache[_contract_cache_key(capability_name)] = contract
            return contract
    return None


async def _bind_capability_for_back_action(
    *,
    ctx: ToolContext,
    action: str,
    domain: Any,
    capability_name: str,
    params: dict[str, Any],
    session_id: str,
) -> CapabilityBindingResult | None:
    from k1.concierge.react.capability_routing import (
        CapabilityBindingRequest,
        bind_capability,
    )

    dispatch = ctx.dispatch
    if (
        ctx.actor != "back"
        or not ctx.active_task_id
        or dispatch is None
        or not hasattr(dispatch, "discover_capabilities")
    ):
        return None

    binding = await bind_capability(
        CapabilityBindingRequest(
            action=action or capability_name,
            domain=str(domain) if domain else None,
            params=params,
            candidate_capability_name=capability_name,
            session_id=session_id,
            trace_id=_tool_trace_id(ctx),
            safety_band=_context_safety_band(ctx),
            actor=ctx.actor,
        ),
        dispatch.discover_capabilities,
        lambda name: _lookup_capability_contract_exact(ctx, name),
    )
    if binding.status == "needs_discovery" and not binding.candidates:
        return None
    return binding


def _binding_failure_payload(
    binding: CapabilityBindingResult,
    *,
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "duration_ms": duration_ms,
        "status": binding.status,
        "capability_name": binding.capability_name,
        "params": dict(binding.params),
        "candidates": [dict(candidate) for candidate in binding.candidates],
        "recovery": dict(binding.recovery) if binding.recovery else None,
        "binding": binding.to_dict(),
        "retryable": False,
    }


def _binding_failure_tool_result(
    tool_name: str,
    binding: CapabilityBindingResult,
    *,
    duration_ms: int,
) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        status="error",
        error=f"capability_binding_{binding.status}",
        data=_binding_failure_payload(binding, duration_ms=duration_ms),
    )


def _optional_metadata_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _request_prompt_metadata(
    *,
    binding: CapabilityBindingResult | None,
    contract: Any | None,
    params: dict[str, Any],
    ctx: ToolContext,
) -> tuple[str | None, dict[str, Any] | None]:
    prompt_template = binding.prompt_template if binding is not None else None
    activity_profile = binding.activity_profile if binding is not None else None
    context_override = dict(binding.context_override) if binding is not None else {}

    if prompt_template is None and contract is not None:
        prompt_template = _optional_metadata_str(getattr(contract, "prompt_template", None))
    if activity_profile is None and contract is not None:
        activity_profile = _optional_metadata_str(getattr(contract, "activity_profile", None))
    if activity_profile:
        context_override.setdefault("activity_profile", activity_profile)

    execution_profiles = getattr(ctx, "active_execution_profiles", None)
    if execution_profiles:
        context_override.setdefault(
            "execution_profiles",
            [dict(profile) for profile in execution_profiles if isinstance(profile, dict)],
        )

    if prompt_template or context_override:
        context_override.setdefault("prompt_variables", dict(params))
    return prompt_template, context_override or None


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
    safety_band = _normalize_safety_band(
        args.get("safety_band", "GREEN"),
        default="GREEN",
        allowed=_TASK_SAFETY_BANDS,
    )

    # Gracefully handle LLM passing a description string instead of a task ID.
    # The LLM sometimes puts an action description in depends_on rather than
    # a task-xxx ID.  Strip it so TaskDispatch validation does not crash.
    if depends_on is not None and not depends_on.startswith("task-"):
        logger.warning(
            "tool:dispatch_task  depends_on is not a task ID, ignoring: %s",
            depends_on,
        )
        depends_on = None
    # P3.4c: Tier is derived from explicit planning signals. A bundled
    # multi-intent request can still be a simple Back task when each action
    # is directly executable by capability tools. The legacy `tier` arg is
    # silently ignored. AUTO-from-SS path has been removed (no SS read on
    # dispatch).
    #
    # Optional `complexity` arg lets callers explicitly escalate to HIGH
    # tier (planner-routed) when planning signals are present. Without
    # `complexity="HIGH"`, behaviour is unchanged: needs_plan -> MEDIUM,
    # else LOW. This is the LLM's only way to reach HIGH tier from the
    # dispatch tool surface.
    explicit_plan = bool(args.get("plan", False))
    explicit_complexity = str(args.get("complexity", "") or "").upper()
    explicit_high = explicit_complexity == "HIGH"
    needs_plan = explicit_plan or explicit_high or depends_on is not None
    if explicit_high:
        tier = ComplexityTier.HIGH
    elif needs_plan:
        tier = ComplexityTier.MEDIUM
    else:
        tier = ComplexityTier.LOW
    tier_raw = tier.value
    logger.info(
        "tool:dispatch_task  intents=%d urgency=%s tier=%s plan=%s safety=%s",
        len(intents),
        urgency,
        tier_raw,
        needs_plan,
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
        # tier already a ComplexityTier from plan derivation above; legacy
        # path retained for safety in case future callers pass tier_raw differently.
        if not isinstance(tier, ComplexityTier):  # pragma: no cover
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
    # P3.4c: surface derived plan flag on the dispatch payload.
    dispatch_payload["plan"] = needs_plan

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

    Delegates to ctx.dispatch.discover_capabilities() if available.

    Results are cached per-session by (intent, domain) to avoid
    redundant lookups when the LLM calls discover_capabilities
    repeatedly with the same or similar parameters.
    """
    intent = args.get("intent", "")
    domain = args.get("domain")
    constraints = args.get("constraints")
    names: list[str] | None = args.get("names")

    # ── Phase 2 Epic 16.7: Batch names fast-path ──────────────────
    # When Back knows exact companion tool names (from constitution or
    # a prior resolve_situation), skip semantic search entirely and
    # use O(1) exact lookup for each name.  One call returns all schemas.
    if names:
        logger.info(
            "tool:discover_capabilities  names=%d",
            len(names),
        )
        caps: list[dict[str, Any]] = []
        for name in names:
            contract = await _lookup_capability_contract_exact(ctx, name)
            if contract is None:
                continue
            cap_dict: dict[str, Any] = {
                "name": name,
                "description": getattr(contract, "description", "") or "",
                "domain": contract.domain[0] if contract.domain else "",
                "domains": list(contract.domain) if contract.domain else [],
                "score": 1.0,  # deterministic exact match
            }
            cap_dict["prompt_template"] = str(getattr(contract, "prompt_template", "") or "")
            cap_dict["activity_profile"] = str(getattr(contract, "activity_profile", "") or "")
            cap_dict["tool_instructions"] = str(getattr(contract, "tool_instructions", "") or "")
            cap_dict["limitations"] = list(getattr(contract, "limitations", ()) or ())
            cap_dict["schema"] = _capability_prompt_schema(contract)
            caps.append(cap_dict)

        return ToolResult(
            tool_name="discover_capabilities",
            status="ok",
            data={"capabilities": caps, "count": len(caps)},
        )

    # ── Existing semantic search path ─────────────────────────────
    logger.info(
        "tool:discover_capabilities  intent=%s domain=%s has_fn=%s",
        intent[:80] if intent else "(empty)",
        domain,
        ctx.dispatch is not None,
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

    # M2: K1 Fabric port path (preferred)
    if ctx.dispatch is not None:
        try:
            caps: list[dict[str, Any]] = []
            seen_names: set[str] = set()

            async def _collect(domain_filter: Any) -> None:
                retrieval = await ctx.dispatch.discover_capabilities(
                    intent=intent,
                    domain=domain_filter,
                    top_k=10,
                    safety_band=_context_safety_band(ctx),
                )
                for sc in retrieval.capabilities:
                    contract = sc.contract
                    name = contract.name if contract else ""
                    if name and name in seen_names:
                        continue
                    if name:
                        seen_names.add(name)
                    if contract is not None:
                        ctx.capability_cache[_contract_cache_key(contract.name)] = contract
                    cap_dict = {
                        "name": name,
                        "description": contract.description if contract else "",
                        "domain": contract.domain[0] if contract and contract.domain else "",
                        "domains": list(contract.domain) if contract else [],
                        "score": sc.score,
                    }
                    if contract is not None:
                        cap_dict["prompt_template"] = str(
                            getattr(contract, "prompt_template", "") or ""
                        )
                        cap_dict["activity_profile"] = str(
                            getattr(contract, "activity_profile", "") or ""
                        )
                        cap_dict["tool_instructions"] = str(
                            getattr(contract, "tool_instructions", "") or ""
                        )
                        cap_dict["limitations"] = list(getattr(contract, "limitations", ()) or ())
                        cap_dict["schema"] = _capability_prompt_schema(contract)
                    caps.append(cap_dict)

            if domain:
                await _collect([domain])
            await _collect(None)

            data = {"capabilities": caps, "count": len(caps)}
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

    # No fabric_port — return empty
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


# =========================================================================
# BACK -- resolve_situation (Phase 2 Epic 16.3)
# =========================================================================


@_register("resolve_situation")
async def execute_resolve_situation(args: dict, ctx: ToolContext) -> ToolResult:
    """Resolve a task situation through Fabric's situated resolver.

    RES-001b (2026-06-16): Back's PRIMARY tool.  Auto-fills identity fields
    (actor_id, space_id, session_id) from ToolContext so the LLM only
    provides ``action_text`` (raw user utterance) and optional
    ``context_hints`` (advisory boost signals — NEVER hard filters).

    Delegates to ``ctx.dispatch.resolve_situation(payload)`` — never
    imports Fabric directly.
    """
    action_text = args.get("action_text", "")
    if not action_text or not isinstance(action_text, str):
        return ToolResult(
            tool_name="resolve_situation",
            status="error",
            error="action_text is required and must be a non-empty string",
        )

    if ctx.dispatch is None:
        return ToolResult(
            tool_name="resolve_situation",
            status="error",
            error="dispatch not wired — resolve_situation unavailable",
        )

    # Auto-fill identity from context (LLM never sees these)
    sm = ctx.session_manager
    actor_id = (
        getattr(ctx, "active_principal_id", None)
        or getattr(sm, "principal_id", None)
        or getattr(sm, "active_principal_id", None)
        or getattr(getattr(sm, "session", None), "principal_id", None)
        or "unknown"
    )
    space_id = getattr(ctx, "active_space_id", None) or "family:default"
    session_id = ctx.session_id or getattr(sm, "session_id", "") or "unknown"

    context_hints = args.get("context_hints") or {}
    if not isinstance(context_hints, dict):
        context_hints = {}

    payload: dict[str, Any] = {
        "action_text": action_text,
        "context_hints": context_hints,
        "actor_id": str(actor_id),
        "space_id": str(space_id),
        "session_id": str(session_id),
        "tier": getattr(ctx, "active_task_tier", None) or "MEDIUM",
        "safety_band": _context_safety_band(ctx),
    }

    # Optional overrides the LLM may provide
    for key in (
        "disclosure_phase",
        "freshness_policy",
        "prompt_budget_tokens",
        "idempotency_keys",
    ):
        value = args.get(key)
        if value is not None:
            payload[key] = value

    logger.info(
        "tool:resolve_situation  actor=%s space=%s action_text_len=%d",
        actor_id,
        space_id,
        len(action_text),
    )

    try:
        result = await ctx.dispatch.resolve_situation(payload)
        return ToolResult(
            tool_name="resolve_situation",
            status="ok",
            data=result,
        )
    except Exception as exc:
        logger.error("tool:resolve_situation failed: %s", exc, exc_info=True)
        return ToolResult(
            tool_name="resolve_situation",
            status="error",
            error=str(exc),
        )


# =========================================================================
# BACK -- ACTION (3)
# =========================================================================


@_register("invoke_capability")
async def execute_invoke_capability(args: dict, ctx: ToolContext) -> ToolResult:
    """Invoke a K0 capability by name.

    Delegates to ctx.dispatch.dispatch_direct() if available.

    M6 E6.1.3: L2 defense-in-depth -- block side-effect invocations
    when a HITL sub-task is PENDING for this task_id.
    """
    capability_name = args.get("capability_name", "")
    params = _normalize_capability_params(capability_name, args.get("params", {}))
    # session_id: prefer LLM-provided arg, fall back to context-bound session
    session_id = args.get("session_id") or ctx.session_id

    # E4.M1.3: legacy `ctx.hil_coordinator` L2 blocking removed. The fabric
    # capability gate (E3) now enforces HIL pre-execution for every
    # invocation regardless of caller, so this defense-in-depth is no
    # longer this tool's responsibility.

    logger.info(
        "tool:invoke_capability  capability=%s params_keys=%s has_fn=%s",
        capability_name,
        list(params.keys()),
        ctx.dispatch is not None,
    )

    if not capability_name:
        return ToolResult(
            tool_name="invoke_capability",
            status="error",
            error="capability_name is required",
        )
    start_ms = int(time.time() * 1000)

    # M13.E1.I3 -- Front-actor defense-in-depth: only whitelisted
    # read-only / safe capabilities may be invoked directly from Front.
    # Side-effecting / safety-sensitive acts must go through Back via
    # `dispatch_task`. The policy gate enforces the same rule first;
    # this is a belt-and-suspenders check for callers that bypass the
    # gate (e.g. test harnesses).
    if ctx.actor == "front":
        from k1.concierge.tools.schemas_front import FRONT_READ_CAPABILITY_WHITELIST

        if capability_name not in FRONT_READ_CAPABILITY_WHITELIST:
            logger.warning(
                "front_invoke_capability_denied capability=%s "
                "(not in FRONT_READ_CAPABILITY_WHITELIST)",
                capability_name,
            )
            return ToolResult(
                tool_name="invoke_capability",
                status="error",
                error=(
                    f"capability '{capability_name}' is not allowed for the "
                    f"Front actor; route via dispatch_task instead"
                ),
            )

    binding = await _bind_capability_for_back_action(
        ctx=ctx,
        action=str(args.get("action") or args.get("intent") or capability_name),
        domain=args.get("domain"),
        capability_name=capability_name,
        params=params,
        session_id=session_id or "",
    )
    if binding is not None:
        if binding.status != "bound" or not binding.capability_name:
            duration = int(time.time() * 1000) - start_ms
            return _binding_failure_tool_result(
                "invoke_capability",
                binding,
                duration_ms=duration,
            )
        capability_name = binding.capability_name
        params = _normalize_capability_params(capability_name, binding.params)

    contract = await _lookup_capability_contract(ctx, capability_name)
    if contract is not None:
        recovery = recovery_for_unsatisfied_contract(
            contract=contract,
            params=params,
            retry_tool="invoke_capability",
            retry_args={
                "capability_name": capability_name,
                "params": params,
                "session_id": session_id or "",
            },
        )
        if recovery is not None:
            duration = int(time.time() * 1000) - start_ms
            return ToolResult(
                tool_name="invoke_capability",
                status="error",
                error="capability_params_incomplete",
                data={
                    "duration_ms": duration,
                    "status": "needs_human",
                    "capability_name": capability_name,
                    "schema": _capability_prompt_schema(contract),
                    "params": params,
                    "recovery": recovery.to_dict(),
                },
            )

    # M2: K1 Fabric port path (preferred)
    if ctx.dispatch is not None:
        try:
            prompt_template, context_override = _request_prompt_metadata(
                binding=binding,
                contract=contract,
                params=params,
                ctx=ctx,
            )
            k1_request = CapabilityRequest(
                capability_name=capability_name,
                params=params,
                prompt_template=prompt_template,
                context_override=context_override,
                session_id=session_id or "",
                trace_id=_tool_trace_id(ctx),
                caller="concierge",
                caller_id=f"concierge.{ctx.actor}",
                safety_band=_context_safety_band(ctx),
            )
            k1_result = await ctx.dispatch.dispatch_direct(k1_request)
            duration = int(time.time() * 1000) - start_ms
            return ToolResult(
                tool_name="invoke_capability",
                status="ok" if k1_result.success else "error",
                error=k1_result.error.message if k1_result.error else None,
                data={
                    "result": k1_result.data or {},
                    "duration_ms": duration,
                    "status": "success" if k1_result.success else "error",
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

    # No dispatch port wired
    duration = int(time.time() * 1000) - start_ms
    if not getattr(ctx, "allow_dispatch_passthrough", False):
        # M17.E1.I1: hard-fail when no IDispatchPort is wired in
        # production. Mirrors the M16.E1.I3 ``allow_planner_passthrough``
        # gate. Setting ``allow_dispatch_passthrough=True`` on the
        # ToolContext (or via KernelConfig in tests) restores the legacy
        # POC stub below.
        return ToolResult(
            tool_name="invoke_capability",
            status="error",
            error=(
                "dispatch_not_wired: ToolContext.dispatch is None and "
                "allow_dispatch_passthrough=False. Wire an IDispatchPort "
                "(FabricDispatchAdapter) or enable the passthrough flag."
            ),
            data={"duration_ms": duration, "status": "error"},
        )
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

    The implementation delegates to fabric_port.execute() for each
    invocation in sequence.
    """
    invocations = args.get("invocations", [])
    if not invocations:
        return ToolResult(
            tool_name="batch_invoke_capabilities",
            status="error",
            error="invocations array is required and must not be empty",
        )

    logger.info(
        "tool:batch_invoke_capabilities  count=%d has_fabric=%s",
        len(invocations),
        ctx.dispatch is not None,
    )

    # M17.E1.I1: hard-fail when no IDispatchPort is wired in production.
    if ctx.dispatch is None and not getattr(ctx, "allow_dispatch_passthrough", False):
        return ToolResult(
            tool_name="batch_invoke_capabilities",
            status="error",
            error=(
                "dispatch_not_wired: ToolContext.dispatch is None and "
                "allow_dispatch_passthrough=False."
            ),
        )

    results = []
    succeeded = 0
    failed = 0
    session_id = ctx.session_id or ""
    safety_band = _context_safety_band(ctx)

    for inv in invocations:
        cap_name = inv.get("capability_name", "")
        params = _normalize_capability_params(cap_name, inv.get("params", {}))

        if not cap_name:
            results.append(
                {
                    "capability_name": cap_name,
                    "status": "error",
                    "error": "capability_name is required",
                    "result": None,
                    "retryable": False,
                }
            )
            failed += 1
            continue

        start_ms = int(time.time() * 1000)

        binding = await _bind_capability_for_back_action(
            ctx=ctx,
            action=str(inv.get("action") or inv.get("intent") or cap_name),
            domain=inv.get("domain"),
            capability_name=cap_name,
            params=params,
            session_id=session_id,
        )
        if binding is not None:
            if binding.status != "bound" or not binding.capability_name:
                duration = int(time.time() * 1000) - start_ms
                results.append(
                    {
                        "capability_name": cap_name,
                        "status": "error",
                        "error": f"capability_binding_{binding.status}",
                        "duration_ms": duration,
                        "binding": binding.to_dict(),
                        "candidates": [dict(candidate) for candidate in binding.candidates],
                        "recovery": dict(binding.recovery) if binding.recovery else None,
                        "retryable": False,
                    }
                )
                failed += 1
                continue
            cap_name = binding.capability_name
            params = _normalize_capability_params(cap_name, binding.params)

        contract = await _lookup_capability_contract(ctx, cap_name)
        prompt_template, context_override = _request_prompt_metadata(
            binding=binding,
            contract=contract,
            params=params,
            ctx=ctx,
        )

        if ctx.dispatch is not None:
            try:
                k1_request = CapabilityRequest(
                    capability_name=cap_name,
                    params=params,
                    prompt_template=prompt_template,
                    context_override=context_override,
                    session_id=session_id,
                    trace_id=_tool_trace_id(ctx),
                    caller="concierge",
                    caller_id=f"concierge.{ctx.actor}",
                    safety_band=safety_band,
                )
                k1_result = await ctx.dispatch.dispatch_direct(k1_request)
                duration = int(time.time() * 1000) - start_ms
                results.append(
                    {
                        "capability_name": cap_name,
                        "status": "success" if k1_result.success else "error",
                        "result": k1_result.data or {},
                        "error": (
                            (k1_result.error.message if k1_result.error else "")
                            if not k1_result.success
                            else ""
                        ),
                        "retryable": bool(
                            getattr(k1_result.error, "retriable", False)
                            if k1_result.error
                            else False
                        ),
                        "duration_ms": duration,
                    }
                )
                if k1_result.success:
                    succeeded += 1
                else:
                    failed += 1
            except Exception as e:
                duration = int(time.time() * 1000) - start_ms
                results.append(
                    {
                        "capability_name": cap_name,
                        "status": "error",
                        "error": str(e),
                        "duration_ms": duration,
                        "retryable": True,
                    }
                )
                failed += 1
        else:
            # No dispatch port wired
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

    all_failed = failed > 0 and succeeded == 0
    return ToolResult(
        tool_name="batch_invoke_capabilities",
        status="error" if all_failed else "ok",
        error="batch_invoke_all_failed" if all_failed else None,
        data={
            "results": results,
            "total": len(invocations),
            "succeeded": succeeded,
            "failed": failed,
            "retryable": any(
                bool(result.get("retryable"))
                for result in results
                if isinstance(result, dict) and result.get("status") == "error"
            ),
        },
    )


@_register("spawn_via_fabric")
async def execute_spawn_via_fabric(args: dict, ctx: ToolContext) -> ToolResult:
    """Spawn a specialized agent via K0 Agent Fabric.

    Delegates to ctx.dispatch.dispatch_direct() if available.
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

    # M2: K1 Fabric port path (preferred)
    if ctx.dispatch is not None:
        try:
            k1_request = CapabilityRequest(
                capability_name=f"agent.{agent_type}",
                params={
                    "task": task,
                    "constraints": constraints,
                    "capabilities_needed": capabilities_needed,
                },
                trace_id=_tool_trace_id(ctx),
                caller="concierge",
                caller_id=f"concierge.{ctx.actor}",
            )
            k1_result = await ctx.dispatch.dispatch_direct(k1_request)
            return ToolResult(
                tool_name="spawn_via_fabric",
                status="ok" if k1_result.success else "error",
                error=k1_result.error.message if k1_result.error else None,
                data=k1_result.data or {},
            )
        except Exception as e:
            return ToolResult(
                tool_name="spawn_via_fabric",
                status="error",
                error=str(e),
            )

    # No dispatch port wired
    if not getattr(ctx, "allow_dispatch_passthrough", False):
        # M17.E1.I2: hard-fail mirrors invoke_capability gate.
        return ToolResult(
            tool_name="spawn_via_fabric",
            status="error",
            error=(
                "dispatch_not_wired: ToolContext.dispatch is None and "
                "allow_dispatch_passthrough=False."
            ),
        )
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
async def execute_execute_workflow(args: dict, ctx: ToolContext) -> ToolResult:
    """Execute a predefined workflow by ID.

    Delegates to ctx.dispatch.dispatch_direct() if available.
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

    # M2: K1 Fabric port path (preferred)
    if ctx.dispatch is not None:
        try:
            k1_request = CapabilityRequest(
                capability_name=f"workflow.{workflow_id}",
                params=params,
                timeout_ms=timeout_ms,
                trace_id=_tool_trace_id(ctx),
                caller="concierge",
                caller_id=f"concierge.{ctx.actor}",
            )
            k1_result = await ctx.dispatch.dispatch_direct(k1_request)
            return ToolResult(
                tool_name="execute_workflow",
                status="ok" if k1_result.success else "error",
                error=k1_result.error.message if k1_result.error else None,
                data=k1_result.data or {},
            )
        except Exception as e:
            return ToolResult(
                tool_name="execute_workflow",
                status="error",
                error=str(e),
            )

    # No dispatch port wired
    if not getattr(ctx, "allow_dispatch_passthrough", False):
        # M17.E1.I3: hard-fail mirrors invoke_capability gate.
        return ToolResult(
            tool_name="execute_workflow",
            status="error",
            error=(
                "dispatch_not_wired: ToolContext.dispatch is None and "
                "allow_dispatch_passthrough=False."
            ),
        )
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
        for key in (
            "confidence",
            "blockers",
            "suggested_next_action",
            "semantic_context",
            "presentation_guidance",
        ):
            if key in args:
                submission[key] = args.get(key)
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
