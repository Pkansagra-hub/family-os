"""
Shared ReAct Loop -- react_loop() and ReactResult
==================================================

V2 Design Ref: Section 7.5 (react_loop implementation), 7.4 (ReactResult)

One implementation for both Front and Back actors. Differences are:
  1. Termination: Front=text-without-tools (L1), Back=submit_result (L2)
  2. tool_choice on iteration 0: Front="required", Back="auto"
  3. Text-without-tools: Front=terminal, Back="thinking aloud" (continues)
  4. Cancellation: Front=always False, Back=checks FSMTurnState
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from k1.concierge.config import get_config
from k1.concierge.llm.types import (
    ConciergeModelResponse,
    FinishReason,
    ModelMessage,
    StreamChunk,
    ToolCallResult,
    ToolSchema,
)
from k1.concierge.llm.types import tool_result_to_message as _tool_result_to_msg
from k1.concierge.llm.validator import LLMOutputValidator, ValidationResult
from k1.concierge.react.capability_routing import (
    context_read_gap_requires_dispatch,
    has_dispatch_tool,
    latest_user_text,
    synthesize_dispatch_task,
)
from k1.concierge.react.control import BackControlEvent, ReactLoopEvent
from k1.concierge.task.parallel_safety import classify_tool_batch
from k1.concierge.tools.dispatcher import ToolDispatcher, hash_tool_arguments
from k1.concierge.tools.recovery_contract import ask_human_recovery_from_tool_data
from k1.concierge.tools.result_protocol import ToolResult
from k1.diagnostics.prompt_dumps import (
    PROMPT_DUMP_ROOT,
    prompt_dump_dir,
    prompt_dump_segment,
)
from k1.model_hub.ports import IModelHubPort
from k1.model_hub.types import (
    CapabilityType,
    ChatPayload,
    ChatResult,
    HubChunk,
    HubRequest,
    HubResponse,
    ReasonResult,
    RequestConstraints,
    ResponseMetadata,
    StructuredResult,
    TokenUsage,
    ToolCallPayload,
    ToolCallResultSet,
)
from k1.model_hub.types import FinishReason as K1FinishReason
from k1.model_hub.types import Message as K1Message
from k1.model_hub.types import ToolCallResult as K1ToolCallResult
from k1.model_hub.types import ToolDefinition as K1ToolDefinition

logger = logging.getLogger(__name__)

_PROMPT_DUMP_DIR = PROMPT_DUMP_ROOT


def _dump_k1_message(message: K1Message) -> dict[str, Any]:
    """Serialize a hub-canonical message for prompt/request probes."""
    payload: dict[str, Any] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id
    if message.name:
        payload["name"] = message.name
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "name": call.name,
                "arguments": call.arguments,
            }
            for call in message.tool_calls
        ]
    return payload


def _dump_k1_tool(tool: K1ToolDefinition) -> dict[str, Any]:
    """Serialize a hub-canonical tool definition for prompt/request probes."""
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
    }


def _dump_hub_payload(payload: Any) -> dict[str, Any]:
    """Serialize the HubRequest payload sent to Model Hub."""
    if isinstance(payload, ToolCallPayload):
        return {
            "type": "ToolCallPayload",
            "system_prompt": payload.system_prompt or "",
            "messages": [_dump_k1_message(message) for message in payload.messages],
            "tools": [_dump_k1_tool(tool) for tool in payload.tools],
            "tool_choice": payload.tool_choice,
            "parallel_tool_calls": payload.parallel_tool_calls,
        }
    if isinstance(payload, ChatPayload):
        return {
            "type": "ChatPayload",
            "system_prompt": payload.system_prompt or "",
            "messages": [_dump_k1_message(message) for message in payload.messages],
        }
    return {"type": type(payload).__name__, "repr": repr(payload)}


def _provider_mapping_preview(payload: Any) -> dict[str, Any]:
    """Describe how the hub payload maps into Gemini/Vertex fields."""
    preview = {
        "provider_family": "vertex/google-genai",
        "system_prompt": "GenerateContentConfig.system_instruction",
        "messages": "client.models.generate_content(..., contents=[...])",
        "max_tokens": "GenerateContentConfig.max_output_tokens",
        "temperature": "GenerateContentConfig.temperature",
    }
    if isinstance(payload, ToolCallPayload):
        preview.update(
            {
                "tools": "GenerateContentConfig.tools[].function_declarations",
                "tool_choice": "GenerateContentConfig.tool_config.function_calling_config",
            }
        )
    return preview


def _resolve_reasoning_effort(actor: str, override: str | None) -> str | None:
    if override is None:
        return None
    if override != "auto":
        return override
    if actor == "back":
        return "medium"
    if actor == "front":
        return "low"
    return None


def _write_llm_request_dump(
    *,
    actor: str,
    scenario: str,
    iteration: int,
    request: HubRequest,
    use_streaming: bool,
    force_text: bool,
) -> None:
    """Persist the exact HubRequest before it reaches Model Hub."""
    if actor not in {"front", "back"}:
        return
    try:
        dump_dir = prompt_dump_dir(
            _PROMPT_DUMP_DIR,
            session_id=request.session_id,
            actor=actor,
        )
        dump_dir.mkdir(parents=True, exist_ok=True)
        timestamp_ms = int(time.time() * 1000)
        payload = {
            "timestamp_ms": timestamp_ms,
            "actor": actor,
            "scenario": scenario,
            "iteration": iteration,
            "trace_id": request.trace_id,
            "request_id": request.request_id,
            "session_id": request.session_id,
            "capability": request.capability.value,
            "use_streaming": use_streaming,
            "force_text": force_text,
            "constraints": {
                "max_tokens": request.constraints.max_tokens,
                "timeout_ms": request.constraints.timeout_ms,
                "priority": request.constraints.priority.value,
                "temperature": request.constraints.temperature,
                "provider_preference": request.constraints.provider_preference,
                "consumer_id": request.constraints.consumer_id,
                "reasoning_effort": request.constraints.reasoning_effort,
            },
            "payload": _dump_hub_payload(request.payload),
            "provider_mapping_preview": _provider_mapping_preview(request.payload),
        }
        trace_slug = prompt_dump_segment(request.trace_id or actor, default=actor)
        stem = f"{actor}_llm_request_iter{iteration}_{trace_slug}_{timestamp_ms}"
        stamped_path = dump_dir / f"{stem}.json"
        latest_path = dump_dir / f"{actor}_llm_request_latest.json"
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        stamped_path.write_text(serialized, encoding="utf-8")
        latest_path.write_text(serialized, encoding="utf-8")
        if actor == "front" and iteration == 0:
            first_stem = f"front_llm_first_call_{trace_slug}_{timestamp_ms}"
            (dump_dir / f"{first_stem}.json").write_text(serialized, encoding="utf-8")
            (dump_dir / "front_llm_first_call_latest.json").write_text(
                serialized,
                encoding="utf-8",
            )
        logger.info(
            "react_loop: %s LLM request dump written iter=%d file=%s latest=%s",
            actor,
            iteration,
            stamped_path,
            latest_path,
        )
    except Exception:
        logger.warning("react_loop: LLM request dump failed", exc_info=True)


def _write_front_llm_first_call_dump(
    *,
    actor: str,
    scenario: str,
    iteration: int,
    request: HubRequest,
    use_streaming: bool,
    force_text: bool,
) -> None:
    """Compatibility wrapper for the original first-Front probe."""
    if actor != "front" or iteration != 0:
        return
    _write_llm_request_dump(
        actor=actor,
        scenario=scenario,
        iteration=iteration,
        request=request,
        use_streaming=use_streaming,
        force_text=force_text,
    )


# =========================================================================
# K1 ↔ POC Type Conversion Helpers (M1 E1.5 — minimal-diff bridge layer)
# =========================================================================


def _to_k1_messages(msgs: list[ModelMessage]) -> list[K1Message]:
    """Convert POC ModelMessages to K1 Messages for HubRequest payloads."""
    out: list[K1Message] = []
    for m in msgs:
        tc = None
        if m.tool_calls:
            tc = [
                K1ToolCallResult(id=c.id, name=c.name, arguments=c.arguments) for c in m.tool_calls
            ]
        out.append(
            K1Message(
                role=m.role,
                content=m.content,
                tool_call_id=m.tool_call_id,
                name=m.name,
                tool_calls=tc,
            )
        )
    return out


def _to_k1_tools(tools: list[ToolSchema]) -> list[K1ToolDefinition]:
    """Convert POC ToolSchemas to K1 ToolDefinitions for HubRequest payloads."""
    return [
        K1ToolDefinition(name=t.name, description=t.description, parameters=t.parameters)
        for t in tools
    ]


def _unwrap_response(hub_resp: HubResponse) -> ConciergeModelResponse:
    """Convert K1 HubResponse back to POC ConciergeModelResponse.

    Allows all existing response field access (response.text,
    response.has_tool_calls, etc.) to remain unchanged.
    """
    result = hub_resp.result
    text = getattr(result, "text", "")
    tool_calls: list[ToolCallResult] = []
    json_output = None
    thought_text = ""

    if isinstance(result, ToolCallResultSet):
        tool_calls = [
            ToolCallResult(
                id=tc.id,
                name=tc.name,
                arguments=(
                    json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
                ),
            )
            for tc in result.tool_calls
        ]
    elif isinstance(result, StructuredResult):
        json_output = result.json_output
    elif isinstance(result, ReasonResult):
        thought_text = result.thinking

    m = hub_resp.metadata
    fr = (
        m.finish_reason.value
        if isinstance(m.finish_reason, K1FinishReason)
        else str(m.finish_reason)
    )
    return ConciergeModelResponse(
        text=text,
        tool_calls=tool_calls,
        json_output=json_output,
        thought_text=thought_text,
        tokens_in=m.usage.prompt_tokens,
        tokens_out=m.usage.completion_tokens,
        latency_ms=m.latency_ms,
        model_id=m.model_id,
        finish_reason=fr,
    )


def _unwrap_chunk(hub_chunk: HubChunk) -> StreamChunk:
    """Convert K1 HubChunk to POC StreamChunk for on_stream callbacks.

    HubChunk has fields ``content``, ``done``, ``metadata``, ``tool_calls``
    (see ``k1/model_hub/types.py``). The concierge ``StreamChunk`` has a
    richer ``chunk_type`` taxonomy (``text_delta``/``tool_call_delta``/
    ``done``), so we derive chunk_type from the HubChunk shape:

    - ``done=True``                → build a full ConciergeModelResponse
    - ``tool_calls`` non-empty     → ``tool_call_delta`` with first call
    - otherwise (text present)     → ``text_delta`` with ``content``
    """
    if hub_chunk.done:
        # Build a synthetic HubResponse so we can reuse _unwrap_response.
        tool_calls = hub_chunk.tool_calls or []
        if tool_calls:
            result: Any = ToolCallResultSet(text=hub_chunk.content, tool_calls=tool_calls)
        elif hub_chunk.thought:
            result = ReasonResult(text=hub_chunk.content, thinking=hub_chunk.thought)
        else:
            result = ChatResult(text=hub_chunk.content)
        metadata = hub_chunk.metadata
        if metadata is None:
            # Synthesize a minimal metadata block. _unwrap_response reads
            # finish_reason, model_id, usage.* and latency_ms.
            metadata = ResponseMetadata(
                request_id="",
                model_id="",
                provider_id="",
                usage=TokenUsage(),
                cost_usd=0.0,
                latency_ms=0,
                cache_hit=False,
                capability=CapabilityType.CHAT,
                trace_id="",
                finish_reason=(K1FinishReason.TOOL_CALLS if tool_calls else K1FinishReason.STOP),
            )
        hub_resp = HubResponse(result=result, metadata=metadata)
        return StreamChunk(chunk_type="done", response=_unwrap_response(hub_resp))

    if hub_chunk.thought:
        return StreamChunk(chunk_type="thought_delta", thought_text=hub_chunk.thought)

    if hub_chunk.tool_calls:
        tc = hub_chunk.tool_calls[0]
        return StreamChunk(
            chunk_type="tool_call_delta",
            tool_call_partial=ToolCallResult(id=tc.id, name=tc.name, arguments=tc.arguments),
        )

    return StreamChunk(chunk_type="text_delta", text=hub_chunk.content)


# =========================================================================
# Max iterations constants (Epic 5.5)
# Kept as module-level constants for backward compatibility.
# Runtime code reads from get_config().react.* and get_config().prompt.*
# =========================================================================

DEFAULT_FRONT_MAX_ITERATIONS: int = 6
DEFAULT_BACK_MAX_ITERATIONS: int = 10


# ---- M3 E3.4.4: Config-backed accessors replace hardcoded dicts ----
# DEPRECATED: Use get_config().prompt.max_iterations instead.
# These remain importable for backward compatibility but delegate to config.
def get_mode_max_iterations() -> dict[str, int]:
    """Return per-mode iteration limits from config (single source of truth)."""
    return dict(get_config().prompt.max_iterations)


def get_crisis_max_iterations() -> dict[str, int]:
    """Return per-mode crisis iteration limits from config."""
    return dict(get_config().prompt.crisis_iterations)


# Backward-compat aliases -- lazy-evaluated via get_config() at import time.
# NOTE: These are snapshots taken at import; prefer the functions above.
# TODO: Remove in M8 when all consumers migrate to get_config().
MODE_MAX_ITERATIONS: dict[str, int] = {
    "STANDARD": 6,
    "CLARIFY_ASK": 3,
    "CLARIFY_RESOLVE": 5,
    "HITL_RELAY": 1,
    "HITL_RESOLVE": 3,
    "PRESENT": 3,
    "WEAVE": 3,
    "CANCEL": 3,
    "INTERRUPT": 6,
    "ERROR": 2,
}

CRISIS_MAX_ITERATIONS: dict[str, int] = {
    "STANDARD": 4,
    "CLARIFY_ASK": 2,
    "CLARIFY_RESOLVE": 4,
    "HITL_RELAY": 1,
    "HITL_RESOLVE": 2,
    "PRESENT": 2,
    "WEAVE": 2,
    "CANCEL": 2,
    "INTERRUPT": 4,
    "ERROR": 2,
}

# Fallback messages (V2 Section 7.5, 7.6)
# Kept as module-level constants for backward compatibility.
FRONT_DEGENERATE_FALLBACK: str = "Let me think about that for a moment."
FRONT_BUDGET_FALLBACK: str = "Let me get back to you on that."


# =========================================================================
# ReactResult dataclass (Epic 5.1.2)
# =========================================================================


@dataclass
class ReactResult:
    """Return value from react_loop().

    status values:
      - "complete":         Front: text response emitted.
                            Back: submit_result(result_type="complete") called.
      - "suspended":        Back only: submit_result(result_type="needs_human").
                            HITL pending.
            - "cancelled":        cancellation_check() returned True between iterations.
            - "budget_exhausted": max_iterations reached without termination.
            - "loop_degenerate":  empty/malformed output triggered terminal guard.
            - "missing_submit_result": Back exhausted without submit_result.
    """

    status: str
    text: str | None = None  # Front: final response text. Back: None.
    data: dict | None = None  # Back: submit_result() arguments. Front: None.
    dispatched_tasks: list[dict] = field(default_factory=list)  # L3: dispatch_task calls
    parallel_tool_calls: int = 0  # M3 E3.7.4: count of parallel-executed tool calls
    sequential_tool_calls: int = 0  # M3 E3.7.4: count of sequential-executed tool calls
    iteration_durations_ms: list[int] = field(default_factory=list)  # Per-iteration wall-clock ms
    loop_events: list[dict[str, Any]] = field(default_factory=list)


# =========================================================================
# _resolve_tool_choice helper (Epic 5.1.5)
# =========================================================================


def _resolve_tool_choice(
    iteration: int, actor: str, tools: list[ToolSchema]
) -> str:  # noqa: ARG001 -- signature retained for caller stability
    """Determine tool_choice for this iteration.

    Policy: always ``"auto"``. The model decides whether to call a tool or
    respond with text. Forcing ``"required"`` on iteration 0 produces
    spurious tool calls on simple greetings or low-stakes turns where text
    is the right output. The Front prompt continues to instruct the model
    on when tools are appropriate; this matches the wider production
    pattern of trusting model judgment over hard kernel gating.
    """
    return "auto"


# =========================================================================
# _result_to_dict helper
# =========================================================================


def _result_to_dict(result: ToolResult) -> dict[str, Any]:
    """Convert a ToolResult to a dict for tool_result_to_message.

    For errors, returns error info dict. For success, returns result.data.
    """
    if result.is_error():
        payload = {"error": result.error, "tool": result.tool_name}
        if result.data:
            payload.update(result.data)
        return payload
    return result.data


_BACK_AUTHORITY_TOOL_NAMES = {
    "invoke_capability",
    "batch_invoke_capabilities",
    "execute_workflow",
    "spawn_via_fabric",
}


def _json_object(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _has_discovery_candidates(payload: dict[str, Any]) -> bool:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    count = data.get("count")
    capabilities = data.get("capabilities")
    return (isinstance(count, int) and count > 0) or bool(capabilities)


def _authority_payload_succeeded(payload: dict[str, Any]) -> bool:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if payload.get("error") or data.get("error"):
        return False
    status = str(data.get("status") or "").lower()
    if status in {"error", "failed", "failure"}:
        return False
    total = data.get("total")
    succeeded = data.get("succeeded")
    failed = data.get("failed")
    if isinstance(total, int) and total > 0:
        return isinstance(succeeded, int) and succeeded > 0
    if isinstance(failed, int) and failed > 0 and not succeeded:
        return False
    return True


def _seed_back_capability_state(messages: list[ModelMessage]) -> tuple[bool, bool]:
    candidates_seen = False
    authority_attempted = False
    for message in messages:
        if message.role != "tool":
            continue
        name = str(message.name or "")
        if name == "discover_capabilities":
            candidates_seen = candidates_seen or _has_discovery_candidates(
                _json_object(message.content)
            )
        elif name in _BACK_AUTHORITY_TOOL_NAMES:
            authority_attempted = authority_attempted or _authority_payload_succeeded(
                _json_object(message.content)
            )
    return candidates_seen, authority_attempted


def _seed_back_tool_names(messages: list[ModelMessage]) -> set[str]:
    names: set[str] = set()
    for message in messages:
        if message.role == "tool" and message.name:
            names.add(str(message.name))
    return names


@dataclass(frozen=True)
class _CollectionMutationPlan:
    adapter: str
    read_capability: str
    write_capability: str
    output_field: str
    id_param: str
    record_id_field: str = "id"


@dataclass(frozen=True)
class _CollectionReadPlan:
    adapter: str
    read_capability: str
    output_field: str


@dataclass(frozen=True)
class _ContractPlanExecution:
    submit_args: dict[str, Any]
    tool_calls: int


def _seed_back_discovery_payloads(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool" and message.name == "discover_capabilities":
            payload = _json_object(message.content)
            if _has_discovery_candidates(payload):
                payloads.append(payload)
    return payloads


def _discovered_capabilities(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    capabilities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in payloads:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        for capability in data.get("capabilities") or []:
            if not isinstance(capability, dict):
                continue
            name = str(capability.get("name") or "")
            if name and name in seen:
                continue
            if name:
                seen.add(name)
            capabilities.append(capability)
    return capabilities


def _capability_schema(capability: dict[str, Any]) -> dict[str, Any]:
    schema = capability.get("schema")
    return schema if isinstance(schema, dict) else {}


def _capability_kinds(capability: dict[str, Any]) -> set[str]:
    schema = _capability_schema(capability)
    return {
        str(kind)
        for kind in schema.get("capabilities") or []
        if kind and not str(kind).startswith("adapter:")
    }


def _adapter_key(capability: dict[str, Any]) -> str:
    schema = _capability_schema(capability)
    for marker in schema.get("capabilities") or []:
        marker_text = str(marker)
        if marker_text.startswith("adapter:"):
            return marker_text.split(":", 1)[1]
    domains = capability.get("domains")
    if isinstance(domains, list) and len(domains) > 1:
        return str(domains[1])
    name_parts = str(capability.get("name") or "").split(".")
    if len(name_parts) >= 3 and name_parts[0] == "tool":
        return name_parts[2]
    return ""


def _required_input_names(capability: dict[str, Any]) -> list[str]:
    schema = _capability_schema(capability)
    names: list[str] = []
    for field_spec in schema.get("required_inputs") or []:
        if isinstance(field_spec, dict):
            name = str(field_spec.get("name") or "")
            if name:
                names.append(name)
    return names


def _array_output_fields(capability: dict[str, Any]) -> list[str]:
    schema = _capability_schema(capability)
    output = schema.get("output") if isinstance(schema.get("output"), dict) else {}
    properties = output.get("properties") if isinstance(output.get("properties"), dict) else {}
    fields: list[str] = []
    for field_name, field_schema in properties.items():
        if isinstance(field_schema, dict) and field_schema.get("type") == "array":
            fields.append(str(field_name))
    return fields


def _identity_input_name(capability: dict[str, Any]) -> str:
    required = _required_input_names(capability)
    if len(required) != 1:
        return ""
    name = required[0]
    if name == "id" or name.endswith("_id"):
        return name
    return ""


def _score(capability: dict[str, Any]) -> float:
    try:
        return float(capability.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _build_collection_mutation_plans(
    discovery_payloads: list[dict[str, Any]],
) -> list[_CollectionMutationPlan]:
    capabilities = _discovered_capabilities(discovery_payloads)
    reads_by_adapter: dict[str, dict[str, Any]] = {}
    mutations_by_adapter: dict[str, dict[str, Any]] = {}

    for capability in capabilities:
        adapter = _adapter_key(capability)
        if not adapter:
            continue
        kinds = _capability_kinds(capability)
        array_outputs = _array_output_fields(capability)
        if "read" in kinds and not _required_input_names(capability) and array_outputs:
            current = reads_by_adapter.get(adapter)
            if current is None or _score(capability) > _score(current):
                reads_by_adapter[adapter] = capability
            continue
        if kinds.isdisjoint({"write", "delete"}):
            continue
        if not _identity_input_name(capability):
            continue
        current = mutations_by_adapter.get(adapter)
        if current is None or _score(capability) > _score(current):
            mutations_by_adapter[adapter] = capability

    plans: list[_CollectionMutationPlan] = []
    for adapter, mutation in mutations_by_adapter.items():
        read = reads_by_adapter.get(adapter)
        if read is None:
            continue
        output_fields = _array_output_fields(read)
        id_param = _identity_input_name(mutation)
        if not output_fields or not id_param:
            continue
        plans.append(
            _CollectionMutationPlan(
                adapter=adapter,
                read_capability=str(read.get("name") or ""),
                write_capability=str(mutation.get("name") or ""),
                output_field=output_fields[0],
                id_param=id_param,
            )
        )
    return plans


def _build_collection_read_plans(
    discovery_payloads: list[dict[str, Any]],
) -> list[_CollectionReadPlan]:
    capabilities = _discovered_capabilities(discovery_payloads)
    reads_by_adapter: dict[str, dict[str, Any]] = {}

    for capability in capabilities:
        adapter = _adapter_key(capability)
        if not adapter:
            continue
        kinds = _capability_kinds(capability)
        output_fields = _array_output_fields(capability)
        if "read" not in kinds or _required_input_names(capability) or not output_fields:
            continue
        current = reads_by_adapter.get(adapter)
        if current is None or _score(capability) > _score(current):
            reads_by_adapter[adapter] = capability

    plans: list[_CollectionReadPlan] = []
    for adapter, read in reads_by_adapter.items():
        output_fields = _array_output_fields(read)
        if not output_fields:
            continue
        plans.append(
            _CollectionReadPlan(
                adapter=adapter,
                read_capability=str(read.get("name") or ""),
                output_field=output_fields[0],
            )
        )
    return plans


def _records_from_list_result(result: ToolResult, output_field: str) -> list[dict[str, Any]]:
    if not result.is_ok():
        return []
    data = result.data if isinstance(result.data, dict) else {}
    payload = data.get("result") if isinstance(data.get("result"), dict) else data
    records = payload.get(output_field)
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _record_id(record: dict[str, Any], plan: _CollectionMutationPlan) -> str:
    value = record.get(plan.record_id_field)
    if value is None:
        value = record.get(plan.id_param)
    return str(value or "")


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _collection_plan_answer(plan_results: list[dict[str, Any]]) -> str:
    total = sum(int(result.get("total", 0)) for result in plan_results)
    succeeded = sum(int(result.get("succeeded", 0)) for result in plan_results)
    failed = sum(int(result.get("failed", 0)) for result in plan_results)
    labels = sorted({str(result.get("adapter") or "records") for result in plan_results})
    label = ", ".join(labels) if labels else "records"
    if total == 0:
        return f"No matching {label} were found."
    if failed:
        return f"Processed {succeeded} of {total} {label}; {failed} failed."
    return f"Processed {succeeded} {label}."


def _collection_read_answer(plan_results: list[dict[str, Any]]) -> str:
    total = sum(int(result.get("count", 0)) for result in plan_results)
    failed = sum(1 for result in plan_results if result.get("status") != "success")
    labels = sorted({str(result.get("adapter") or "records") for result in plan_results})
    label = ", ".join(labels) if labels else "records"
    if failed:
        return f"Fetched live {label}; {failed} read request(s) failed."
    if total == 0:
        return f"No matching live {label} were found."
    return f"Fetched {total} live {label}."


async def _execute_collection_read_plan(
    *,
    discovery_payloads: list[dict[str, Any]],
    tool_dispatcher: ToolDispatcher,
    messages: list[ModelMessage],
    trace_id: str,
) -> _ContractPlanExecution | None:
    plans = _build_collection_read_plans(discovery_payloads)
    if not plans:
        return None

    tool_calls = 0
    plan_results: list[dict[str, Any]] = []
    for plan in plans[:4]:
        read_call = ToolCallResult(
            id=f"kernel-plan-read-{uuid.uuid4().hex[:8]}",
            name="invoke_capability",
            arguments={"capability_name": plan.read_capability, "params": {}},
        )
        read_result = await tool_dispatcher.dispatch(read_call)
        tool_calls += 1
        messages.append(_tool_result_to_msg(read_call, _result_to_dict(read_result)))
        records = _records_from_list_result(read_result, plan.output_field)
        data = read_result.data if isinstance(read_result.data, dict) else {}
        plan_results.append(
            {
                "adapter": plan.adapter.replace("_", " "),
                "read_capability": plan.read_capability,
                "output_field": plan.output_field,
                "status": "success" if read_result.is_ok() else "error",
                "count": len(records),
                "result": data.get("result") if isinstance(data.get("result"), dict) else data,
                "error": read_result.error or "",
            }
        )

    submit_args = {
        "result_type": "complete",
        "final_answer": _collection_read_answer(plan_results),
        "results": plan_results,
        "artifacts_created": [],
    }
    submit_call = ToolCallResult(
        id=f"kernel-plan-submit-{uuid.uuid4().hex[:8]}",
        name="submit_result",
        arguments=submit_args,
    )
    submit_result = await tool_dispatcher.dispatch(submit_call)
    tool_calls += 1
    messages.append(_tool_result_to_msg(submit_call, _result_to_dict(submit_result)))
    if submit_result.is_error():
        logger.warning(
            "react_loop: contract read plan submit failed error=%s trace=%s",
            submit_result.error,
            trace_id[:8] if trace_id else "",
        )
        return None
    logger.info(
        "react_loop: contract read plan executed plans=%d trace=%s",
        len(plan_results),
        trace_id[:8] if trace_id else "",
    )
    return _ContractPlanExecution(submit_args=submit_args, tool_calls=tool_calls)


async def _execute_collection_mutation_plan(
    *,
    discovery_payloads: list[dict[str, Any]],
    tool_dispatcher: ToolDispatcher,
    messages: list[ModelMessage],
    trace_id: str,
) -> _ContractPlanExecution | None:
    plans = _build_collection_mutation_plans(discovery_payloads)
    if not plans:
        return None

    tool_calls = 0
    plan_results: list[dict[str, Any]] = []
    for plan in plans[:1]:
        list_call = ToolCallResult(
            id=f"kernel-plan-list-{uuid.uuid4().hex[:8]}",
            name="invoke_capability",
            arguments={"capability_name": plan.read_capability, "params": {}},
        )
        list_result = await tool_dispatcher.dispatch(list_call)
        tool_calls += 1
        messages.append(_tool_result_to_msg(list_call, _result_to_dict(list_result)))
        records = _records_from_list_result(list_result, plan.output_field)
        invocations = [
            {
                "capability_name": plan.write_capability,
                "params": {plan.id_param: record_id},
            }
            for record_id in (_record_id(record, plan) for record in records)
            if record_id
        ]
        summary = {
            "adapter": plan.adapter.replace("_", " "),
            "read_capability": plan.read_capability,
            "write_capability": plan.write_capability,
            "total": len(invocations),
            "succeeded": 0,
            "failed": 0,
            "results": [],
        }
        if invocations:
            for chunk in _chunked(invocations, 8):
                batch_call = ToolCallResult(
                    id=f"kernel-plan-batch-{uuid.uuid4().hex[:8]}",
                    name="batch_invoke_capabilities",
                    arguments={"invocations": chunk},
                )
                batch_result = await tool_dispatcher.dispatch(batch_call)
                tool_calls += 1
                messages.append(_tool_result_to_msg(batch_call, _result_to_dict(batch_result)))
                batch_data = batch_result.data if isinstance(batch_result.data, dict) else {}
                summary["succeeded"] = int(summary["succeeded"]) + int(
                    batch_data.get("succeeded", 0)
                )
                summary["failed"] = int(summary["failed"]) + int(batch_data.get("failed", 0))
                summary["results"].extend(batch_data.get("results") or [])
        plan_results.append(summary)

    submit_args = {
        "result_type": "complete",
        "final_answer": _collection_plan_answer(plan_results),
        "results": plan_results,
        "artifacts_created": [],
    }
    submit_call = ToolCallResult(
        id=f"kernel-plan-submit-{uuid.uuid4().hex[:8]}",
        name="submit_result",
        arguments=submit_args,
    )
    submit_result = await tool_dispatcher.dispatch(submit_call)
    tool_calls += 1
    messages.append(_tool_result_to_msg(submit_call, _result_to_dict(submit_result)))
    if submit_result.is_error():
        logger.warning(
            "react_loop: contract collection plan submit failed error=%s trace=%s",
            submit_result.error,
            trace_id[:8] if trace_id else "",
        )
        return None
    logger.info(
        "react_loop: contract collection plan executed plans=%d trace=%s",
        len(plan_results),
        trace_id[:8] if trace_id else "",
    )
    return _ContractPlanExecution(submit_args=submit_args, tool_calls=tool_calls)


def _recovery_to_suspended_data(recovery: dict[str, Any]) -> dict[str, Any]:
    return {
        "result_type": "needs_human",
        "hil_type": str(recovery.get("hil_type") or "clarification"),
        "question": str(
            recovery.get("question")
            or "I need one more detail before I can keep going. What should I use?"
        ),
        "options": list(recovery.get("options") or []),
        "side_effects": list(recovery.get("side_effects") or []),
        "missing_fields": list(recovery.get("missing_fields") or []),
        "recovery": recovery,
    }


# =========================================================================
# Streaming helper (Epic 2.1)
# =========================================================================


async def _streaming_generate(
    model: IModelHubPort,
    request: HubRequest,
    on_stream: Callable[[StreamChunk], Awaitable[None]],
) -> ConciergeModelResponse:
    """Call model.stream_execute(), forward chunks, return final response.

    Consumes the async iterator from stream_execute(), converts each
    K1 HubChunk to POC StreamChunk, forwards to the on_stream callback,
    and returns the completed ConciergeModelResponse (unwrapped from
    the final "done" chunk's HubResponse).

    Falls back to model.execute() if stream_execute() is not available
    or raises an error.
    """

    async def _execute_fallback() -> ConciergeModelResponse:
        fallback_response = _unwrap_response(await model.execute(request))
        if fallback_response.thought_text:
            await on_stream(
                StreamChunk(
                    chunk_type="thought_delta",
                    thought_text=fallback_response.thought_text,
                )
            )
        return fallback_response

    try:
        response: ConciergeModelResponse | None = None
        async for hub_chunk in model.stream_execute(request):
            chunk = _unwrap_chunk(hub_chunk)
            if chunk.chunk_type == "done":
                response = chunk.response
            else:
                await on_stream(chunk)

        if response is None:
            logger.warning("stream_execute ended without done chunk, falling back")
            return await _execute_fallback()

        return response

    except (NotImplementedError, AttributeError):
        logger.info("stream_execute not available, falling back to execute()")
        return await _execute_fallback()
    except Exception as exc:
        logger.warning("stream_execute failed (%s), falling back to execute()", exc)
        return await _execute_fallback()


# =========================================================================
# react_loop (Epic 5.1.3, 5.1.4)
# =========================================================================


async def react_loop(
    actor: str,
    system_prompt: str,
    messages: list[ModelMessage],
    tools: list[ToolSchema],
    max_iterations: int,
    model: IModelHubPort,
    tool_dispatcher: ToolDispatcher,
    on_text_response: Callable[[str], Awaitable[None]],
    cancellation_check: Callable[[], Awaitable[bool]],
    trace_id: str = "",
    session_id: str = "",
    scenario: str = "",
    validator: LLMOutputValidator | None = None,
    on_stream: Callable[[StreamChunk], Awaitable[None]] | None = None,
    control_queue: asyncio.Queue[BackControlEvent] | None = None,
    completed_tool_call_ids: set[str] | None = None,
    completed_tool_arg_keys: set[str] | None = None,
    reasoning_effort: str | None = "auto",
) -> ReactResult:
    """Shared ReAct loop for both Front and Back actors.

    Termination:
      Front (L1): text response with NO tool calls -> final response.
                  NOTE: on_text_response is NOT called inside the loop.
                  The caller (front_handler) emits response.final AFTER
                  emitting task dispatches, ensuring correct FSM ordering.
      Back (L2):  submit_result() tool call -> structured result
                  (text-without-tool-calls from Back = "thinking aloud", continues)

    ITEM #13: tool_choice="required" on Front iteration 0 forces a tool call.
    ITEM #14: cancellation_check at top of each iteration.
    ITEM #19: Back text-without-tools = "thinking aloud", NOT terminal.

    Args:
        actor: "front" or "back"
        system_prompt: Built by DynamicPromptBuilder (M08/M09)
        messages: Chat history + current user input. MUTATED in-place.
        tools: Actor-specific tool schemas
        max_iterations: Front: mode+affect driven. Back: tier driven.
        model: LLM adapter (M03)
        tool_dispatcher: Validates + executes tool calls (M04, async)
        on_text_response: Unused by react_loop -- kept for interface
            compatibility. front_handler calls it after task dispatches.
        cancellation_check: Check if task/turn is cancelled.
        trace_id: End-to-end trace ID for observability.
        session_id: Session scope for prompt/request diagnostics.
        scenario: Mode/scenario label for observability.

    Returns:
        ReactResult with status, text, data, and dispatched_tasks.
    """
    dispatched_tasks: list[dict] = []
    last_text_with_tools: str | None = None  # Track text from mixed (text+tools) responses
    # M3 E3.7.4: Parallel safety observability counters
    _parallel_count = 0
    _sequential_count = 0
    _iteration_durations: list[int] = []  # Per-iteration wall-clock ms
    original_tools = tools  # Preserve original list; tools may be cleared on degenerate retry
    _degenerate_retry_active = False  # Track if we're in a degenerate retry
    _front_turn_text = latest_user_text(messages) if actor == "front" else ""
    (
        _back_capability_candidates_seen,
        _back_authority_tool_attempted,
    ) = (
        _seed_back_capability_state(messages) if actor == "back" else (False, False)
    )
    _back_discovery_payloads = _seed_back_discovery_payloads(messages) if actor == "back" else []
    _back_tool_names_seen = _seed_back_tool_names(messages) if actor == "back" else set()
    _loop_events: list[dict[str, Any]] = []
    _completed_tool_call_ids = set(completed_tool_call_ids or set())
    _completed_tool_arg_keys = set(completed_tool_arg_keys or set())
    _request_reasoning_effort = _resolve_reasoning_effort(actor, reasoning_effort)
    _retryable_error_counts: dict[str, int] = {}
    _tool_name_counts: dict[str, int] = {}  # name-only spin guard (Front)
    _back_capability_spin_nudge_sent = False
    _empty_response_count = 0
    _invalid_schema_count = 0
    effective_max_iterations = max_iterations
    hard_max_iterations = max(1, max_iterations + 1)

    def _record_loop_event(
        event_type: str,
        iteration: int,
        payload: dict[str, Any] | None = None,
    ) -> None:
        _loop_events.append(
            ReactLoopEvent(
                event_type=event_type,
                actor=actor,
                scenario=scenario,
                iteration=iteration,
                trace_id=trace_id,
                payload=payload or {},
            ).to_dict()
        )

    def _make_result(
        status: str,
        *,
        text: str | None = None,
        data: dict | None = None,
    ) -> ReactResult:
        return ReactResult(
            status=status,
            text=text,
            data=data,
            dispatched_tasks=dispatched_tasks,
            parallel_tool_calls=_parallel_count,
            sequential_tool_calls=_sequential_count,
            iteration_durations_ms=_iteration_durations,
            loop_events=list(_loop_events),
        )

    def _tool_key(tc: Any) -> str:
        return (
            f"{getattr(tc, 'name', '')}:{hash_tool_arguments(getattr(tc, 'arguments', {}) or {})}"
        )

    def _is_completed_duplicate(tc: Any) -> bool:
        return _tool_key(tc) in _completed_tool_arg_keys

    def _is_retryable_error(result: ToolResult) -> bool:
        if not result.is_error():
            return False
        data = result.data if isinstance(result.data, dict) else {}
        if "retryable" in data:
            return bool(data.get("retryable"))
        error = (result.error or "").lower()
        if "tool_timeout" in error or "tool_exception" in error:
            return True
        terminal = (
            "not allowed",
            "budget exhausted",
            "invalid arguments",
            "capability_binding_",
            "batch_invoke_all_failed",
            "side-effect tools blocked",
            "submit_result(complete) rejected",
            "needs_human_without_authority_attempt",
        )
        return bool(error) and not any(marker in error for marker in terminal)

    def _capability_binding_repair_message(result: ToolResult) -> str:
        data = result.data if isinstance(result.data, dict) else {}
        candidates = data.get("candidates") or []
        names = [
            str(candidate.get("name") or "")
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("name")
        ]
        recovery = data.get("recovery") if isinstance(data.get("recovery"), dict) else {}
        rejected = str(recovery.get("rejected_name") or "") if recovery else ""
        rejected_text = f" Rejected name: {rejected}." if rejected else ""
        candidate_text = ", ".join(names[:8]) if names else "none returned"
        return (
            "The last capability invocation failed during registry binding."
            f"{rejected_text} Do not retry the same capability name with the "
            "same parameters. Use an exact capability name from the registry "
            f"candidates if one fits: {candidate_text}. If no candidate fits, "
            "call submit_result with result_type='needs_human'."
        )

    def _control_message(event: BackControlEvent) -> ModelMessage:
        payload = event.to_dict()
        return ModelMessage(
            role="user",
            content="BACK_CONTROL_EVENT\n" + json.dumps(payload, sort_keys=True, default=str),
        )

    def _back_progress_nudge(*, empty_response: bool) -> str:
        if _back_authority_tool_attempted:
            return (
                "You already invoked an authority capability. Now call "
                "submit_result to deliver that actual result. Do NOT write "
                "conversational text."
            )
        if "discover_capabilities" in _back_tool_names_seen:
            if _back_capability_candidates_seen:
                return (
                    "Discovery returned viable capability candidates, but you have not "
                    "invoked an authority capability yet. Inspect the discovered schemas "
                    "and call invoke_capability or batch_invoke_capabilities with the "
                    "exact registry-owned name. Do NOT call discover_capabilities or "
                    "recall_memory again for the same task. Ask the user only if every "
                    "candidate is unsuitable or required inputs are missing."
                )
            return (
                "Discovery returned no viable capability candidates for this live or "
                "external task. Do NOT call discover_capabilities again for the same "
                "intent, and do NOT claim completion. Call submit_result with "
                "result_type='needs_human', hil_type='clarification' or 'escalate', "
                "and a concise question explaining what capability, source, or user "
                "detail is needed."
            )
        if "recall_memory" in _back_tool_names_seen or "summarize_context" in _back_tool_names_seen:
            return (
                "You already checked memory/context. Call submit_result with "
                "result_type='complete' using the memory/context findings, or say "
                "not found if there were no relevant results. Do NOT invent a live "
                "system-of-record action."
            )
        if empty_response:
            return (
                "Your last response was empty. Continue working on the task: use "
                "recall_memory for memory/context lookup, or discover and invoke "
                "capabilities for live system-of-record work. If you cannot make "
                "progress, call submit_result with result_type='needs_human'."
            )
        return "Continue working. Use tool calls, not conversational text."

    def _drain_control_events(iteration: int) -> bool:
        nonlocal effective_max_iterations
        if control_queue is None:
            return False
        cancel_requested = False
        drained_parameter_updates = 0
        while True:
            try:
                event = control_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            event.received_at_iteration = iteration
            event_type = str(event.event_type or "").lower()
            _record_loop_event(event_type, iteration, event.to_dict())
            if event_type == "cancel":
                cancel_requested = True
                continue
            messages.append(_control_message(event))
            if event_type == "parameter_update":
                drained_parameter_updates += 1
        if drained_parameter_updates and iteration >= effective_max_iterations - 1:
            if effective_max_iterations < hard_max_iterations:
                effective_max_iterations += 1
                _record_loop_event(
                    "parameter_update_extra_iteration",
                    iteration,
                    {"effective_max_iterations": effective_max_iterations},
                )
            else:
                _record_loop_event(
                    "cannot_apply_parameter_update",
                    iteration,
                    {"reason": "hard_cap_reached"},
                )
        return cancel_requested

    def _front_policy_dispatch(reason: str) -> ReactResult | None:
        if actor != "front":
            return None
        if not _front_turn_text or dispatched_tasks:
            return None
        if not has_dispatch_tool(original_tools):
            return None
        task_entry = synthesize_dispatch_task(_front_turn_text, reason)
        dispatched_tasks.append(task_entry)
        logger.warning(
            "react_loop: front capability routing guard synthesized dispatch " "reason=%s trace=%s",
            reason,
            trace_id[:8] if trace_id else "",
        )
        return _make_result("complete", text="")

    # Per-iteration LLM call timeout (prevents hangs from API stalls)
    _iter_timeout_s: float = get_config().llm.default_timeout_ms / 1000.0
    # M6 E6.2 (C03): Per-tool dispatch timeout -- prevents a hung tool call
    # from blocking the whole ReAct loop indefinitely.  On timeout we
    # synthesize an error ToolResult so the LLM gets a real observation.
    _raw_tool_timeout = getattr(get_config().react, "tool_timeout_ms", 30_000)
    try:
        _tool_timeout_s: float = max(0.001, float(_raw_tool_timeout) / 1000.0)
    except (TypeError, ValueError):
        # Defensive: if config is mocked/non-numeric, use sane default
        _tool_timeout_s = 30.0

    # HIL-aware override: invoke_capability may block while awaiting human
    # approval (capability_gate_timeout_ms = 120 s by default).  Use
    # max(tool_timeout, hil_timeout + 30 s) so the gate can resolve before
    # the react loop cancels the tool call.
    _raw_hil_timeout = getattr(get_config(), "hil_capability_gate_timeout_ms", 120_000)
    try:
        _hil_tool_timeout_s: float = max(_tool_timeout_s, float(_raw_hil_timeout) / 1000.0 + 30.0)
    except (TypeError, ValueError):
        _hil_tool_timeout_s = max(_tool_timeout_s, 150.0)

    # Hoist _run_tool outside the loop to avoid re-creating the closure
    async def _run_tool(tc: Any) -> tuple[Any, ToolResult]:
        if _is_completed_duplicate(tc):
            tool_name = getattr(tc, "name", "unknown")
            _record_loop_event(
                "tool_already_completed",
                -1,
                {
                    "tool_name": tool_name,
                    "call_id": getattr(tc, "id", "") or "",
                    "args_hash": hash_tool_arguments(getattr(tc, "arguments", {}) or {}),
                },
            )
            return tc, ToolResult(
                tool_name=tool_name,
                status="ok",
                data={
                    "already_completed": True,
                    "tool_name": tool_name,
                    "call_id": getattr(tc, "id", "") or "",
                },
            )
        _effective_timeout = (
            _hil_tool_timeout_s
            if getattr(tc, "name", "") in ("invoke_capability", "batch_invoke_capabilities")
            else _tool_timeout_s
        )
        try:
            result = await asyncio.wait_for(
                tool_dispatcher.dispatch(tc), timeout=_effective_timeout
            )
        except asyncio.TimeoutError:
            tool_name = getattr(tc, "name", "unknown")
            logger.error(
                "react_loop: tool TIMED OUT tool=%s (timeout=%.1fs) "
                "actor=%s trace=%s -- synthesizing error result",
                tool_name,
                _effective_timeout,
                actor,
                trace_id[:8] if trace_id else "",
            )
            result = ToolResult(
                tool_name=tool_name,
                status="error",
                data={"retryable": True, "timeout_ms": int(_effective_timeout * 1000)},
                error=f"tool_timeout after {_effective_timeout:.1f}s",
            )
            if hasattr(tool_dispatcher, "record_timeout"):
                try:
                    tool_dispatcher.record_timeout(
                        tc,
                        timeout_ms=int(_effective_timeout * 1000),
                    )
                except Exception:
                    logger.exception("react_loop: failed to record tool timeout")
        return tc, result

    logger.info(
        "react_loop START: actor=%s max_iter=%d tools=%d scenario=%s trace=%s",
        actor,
        max_iterations,
        len(tools),
        scenario,
        trace_id[:8] if trace_id else "",
    )

    for iteration in range(hard_max_iterations):
        if iteration >= effective_max_iterations:
            break
        _iter_start = time.monotonic()

        # ---- RESTORE TOOLS AFTER DEGENERATE RETRY ----
        # If the previous iteration was a degenerate retry (tools=[]),
        # restore the original tool list so the loop can resume normally.
        if _degenerate_retry_active:
            tools = original_tools
            _degenerate_retry_active = False
            logger.debug(
                "react_loop: restored %d tools after degenerate retry",
                len(tools),
            )

        # ---- CANCELLATION CHECK (ITEM #14) ----
        if await cancellation_check():
            return _make_result("cancelled")

        if _drain_control_events(iteration):
            _record_loop_event("cancel", iteration, {"source": "control_queue"})
            return _make_result("cancelled")

        # ---- BUILD REQUEST ----
        # On the last iteration for Front, strip tools to force text-only
        # output. Without this, the model may keep calling tools and
        # exhaust the budget without ever producing a text response.
        # tools may already be [] from a degenerate retry (see below).
        is_last = iteration == effective_max_iterations - 1
        force_text = (is_last and actor == "front") or not tools
        # For Back on the last iteration, nudge it to call submit_result
        # with whatever partial results it has, rather than exhausting budget.
        force_submit = is_last and actor == "back" and tools
        effective_tools = [] if force_text else tools

        if force_submit:
            _record_loop_event(
                "last_iteration_submit",
                iteration,
                {"max_iterations": effective_max_iterations},
            )
            messages.append(
                ModelMessage(
                    role="user",
                    content=(
                        "You are on your LAST iteration. You MUST call "
                        "submit_result now with whatever results you have "
                        "gathered so far. Summarize your findings in "
                        "final_answer. Use result_type='complete' only when "
                        "the task is actually done; use result_type='needs_human' "
                        "with hil_type='clarification' when required details are missing."
                    ),
                )
            )
            logger.info(
                "react_loop: iter=%d LAST ITERATION (back) -- nudging submit_result",
                iteration,
            )

        if force_text and tools:
            _record_loop_event(
                "forced_text",
                iteration,
                {"max_iterations": effective_max_iterations},
            )
            logger.info(
                "react_loop: iter=%d LAST ITERATION -- forcing text-only (no tools)",
                iteration,
            )

        # Build K1 HubRequest (bridge translates to POC adapter internally)
        _cap = (
            CapabilityType.CHAT
            if force_text
            else (CapabilityType.TOOL_CALL if tools else CapabilityType.CHAT)
        )
        _tc = "none" if force_text else _resolve_tool_choice(iteration, actor, tools)
        _k1_msgs = _to_k1_messages(messages)
        # Ensure at least one message for payload validation
        if not _k1_msgs and system_prompt:
            _k1_msgs = [K1Message(role="system", content=system_prompt)]
        if _cap == CapabilityType.TOOL_CALL and effective_tools:
            _payload = ToolCallPayload(
                messages=_k1_msgs,
                tools=_to_k1_tools(effective_tools),
                tool_choice=_tc,
                system_prompt=system_prompt,
            )
        else:
            _payload = ChatPayload(
                messages=_k1_msgs,
                system_prompt=system_prompt,
            )
        request = HubRequest(
            capability=_cap,
            payload=_payload,
            constraints=RequestConstraints(
                max_tokens=65535,
                consumer_id=f"concierge.{actor}",
                reasoning_effort=_request_reasoning_effort,
            ),
            trace_id=trace_id or f"concierge-{actor}-{iteration}",
            session_id=session_id,
        )

        # ---- LLM CALL (streaming whenever a stream sink is provided) ----
        # Front's final answer is usually force_text=True, so streaming must
        # stay enabled for CHAT requests too; otherwise the user sees the
        # reasoning and final text arrive as one lump.
        use_streaming = on_stream is not None

        _write_llm_request_dump(
            actor=actor,
            scenario=scenario,
            iteration=iteration,
            request=request,
            use_streaming=use_streaming,
            force_text=force_text,
        )

        try:
            if use_streaming:
                response = await asyncio.wait_for(
                    _streaming_generate(model, request, on_stream),
                    timeout=_iter_timeout_s,
                )
            else:
                response = _unwrap_response(
                    await asyncio.wait_for(
                        model.execute(request),
                        timeout=_iter_timeout_s,
                    )
                )
                if response.thought_text and on_stream is not None:
                    await on_stream(
                        StreamChunk(
                            chunk_type="thought_delta",
                            thought_text=response.thought_text,
                        )
                    )
        except asyncio.TimeoutError:
            logger.error(
                "react_loop: LLM call TIMED OUT on iter=%d actor=%s "
                "(timeout=%.1fs) -- aborting. trace=%s",
                iteration,
                actor,
                _iter_timeout_s,
                trace_id[:8] if trace_id else "",
            )
            _iter_dur = int((time.monotonic() - _iter_start) * 1000)
            _iteration_durations.append(_iter_dur)
            fallback = get_config().react.front_degenerate_fallback if actor == "front" else ""
            return _make_result(
                "complete" if actor == "front" else "missing_submit_result",
                text=fallback if actor == "front" else None,
                data={"error_code": "REACT_MISSING_SUBMIT_RESULT"} if actor == "back" else None,
            )

        logger.info(
            "react_loop: iter=%d actor=%s has_text=%s has_tools=%s finish=%s "
            "streamed=%s text=%s",
            iteration,
            actor,
            response.has_text,
            response.has_tool_calls,
            response.finish_reason,
            use_streaming,
            (response.text or "")[:60],
        )

        # ---- LLM ERROR: bail immediately instead of wasting iterations ----
        if response.finish_reason == FinishReason.ERROR:
            logger.error(
                "react_loop: LLM returned ERROR on iter=%d actor=%s -- aborting loop "
                "(check model name, API key, or quota)",
                iteration,
                actor,
            )
            if actor != "front":
                return _make_result(
                    "missing_submit_result",
                    data={"error_code": "LLM_ERROR"},
                )
            fallback = get_config().react.front_degenerate_fallback
            return _make_result("complete", text=fallback)

        # ---- VALIDATION (Epic 4.1) ----
        if validator is not None and response.has_tool_calls:
            avail_names = (
                frozenset(t.name for t in effective_tools) if effective_tools else frozenset()
            )
            vr: ValidationResult = validator.validate(
                response,
                actor=actor,
                iteration=iteration,
                available_tool_names=avail_names,
            )
            if not vr.valid:
                if vr.fixed_response is not None:
                    response = vr.fixed_response
                    logger.info(
                        "react_loop: validation fixed response, " "stripped %d -> %d tool calls",
                        len(vr.fixed_response.tool_calls) + len(vr.issues),
                        len(vr.fixed_response.tool_calls),
                    )
                else:
                    _invalid_schema_count += 1
                    _record_loop_event(
                        "schema_repair",
                        iteration,
                        {"issues": list(vr.issues), "fixed": False},
                    )
                    if _invalid_schema_count >= 3:
                        _record_loop_event(
                            "degenerate_loop",
                            iteration,
                            {"reason": "repeated_invalid_schema"},
                        )
                        return _make_result(
                            "loop_degenerate",
                            data={"error_code": "REACT_LOOP_DEGENERATE"},
                        )
                    # No salvageable tool calls -- treat as degenerate
                    logger.warning(
                        "react_loop: validation failed, no fix possible: %s",
                        "; ".join(vr.issues),
                    )
                    if actor == "front":
                        return _make_result(
                            "complete",
                            text=get_config().react.front_degenerate_fallback,
                        )
                    # Back actor: inject feedback so the model knows WHY its
                    # call was rejected and what it must do before submit_result.
                    messages.append(
                        ModelMessage(
                            role="user",
                            content=(
                                f"Your tool call was INVALID and was rejected: "
                                f"{'; '.join(vr.issues)}. "
                                "You MUST complete the work before submitting: "
                                "1) call discover_capabilities to find the right capability, "
                                "2) call invoke_capability to execute it, "
                                "3) THEN call submit_result with the actual outcome."
                            ),
                        )
                    )
                    _iter_dur = int((time.monotonic() - _iter_start) * 1000)
                    _iteration_durations.append(_iter_dur)
                    continue

        # ---- MALFORMED TOOL CALL: model tried a tool call but JSON was invalid ----
        if response.finish_reason == FinishReason.MALFORMED_TOOL_CALL:
            _record_loop_event("schema_repair", iteration, {"reason": "malformed_tool_call"})
            logger.warning(
                "Malformed tool call from %s on iteration %d -- nudging to simplify",
                actor,
                iteration,
            )
            if iteration < effective_max_iterations - 1:
                if actor == "back":
                    malformed_nudge = (
                        "Your previous function call had invalid JSON and was rejected before "
                        "execution. Retry the next appropriate tool call with valid JSON. If you "
                        "were invoking capabilities, use the exact discovered capability names and "
                        "simple JSON arguments. Do not call submit_result until the required "
                        "capability work has been invoked or a tool result says human input is needed."
                    )
                else:
                    malformed_nudge = (
                        "Your previous function call had invalid JSON and was rejected before "
                        "execution. Retry with a simpler valid JSON tool call, or respond directly "
                        "if no tool is needed."
                    )
                messages.append(
                    ModelMessage(
                        role="user",
                        content=malformed_nudge,
                    )
                )
                logger.info(
                    "react_loop: %s malformed_tool_call on iter=%d/%d, nudging to simplify",
                    actor,
                    iteration,
                    max_iterations,
                )
            _iter_dur = int((time.monotonic() - _iter_start) * 1000)
            _iteration_durations.append(_iter_dur)
            continue

        # ---- DEGENERATE: no text AND no tool calls ----
        if not response.has_text and not response.has_tool_calls:
            _empty_response_count += 1
            _record_loop_event("degenerate_response", iteration, {"count": _empty_response_count})
            if _empty_response_count >= 3:
                _record_loop_event(
                    "degenerate_loop",
                    iteration,
                    {"reason": "repeated_empty_response"},
                )
                _iter_dur = int((time.monotonic() - _iter_start) * 1000)
                _iteration_durations.append(_iter_dur)
                return _make_result(
                    "loop_degenerate",
                    data={"error_code": "REACT_LOOP_DEGENERATE"},
                )
            logger.warning("Degenerate response from %s on iteration %d", actor, iteration)
            if actor == "front":
                # Retry once with a nudge AND strip tools so the model
                # MUST produce text. Gemini 3 models sometimes exhaust
                # their thinking budget processing tool results and
                # return empty output. Forcing text-only on the retry
                # guarantees we get a real answer.
                if iteration < effective_max_iterations - 1:
                    # Context-aware nudge: HITL_RELAY / hitl_resolve / weave
                    # modes never call tools, so the "synthesize from tools
                    # above" wording confuses the model and we get a second
                    # empty turn. Use a mode-appropriate nudge instead.
                    scenario_lower = (scenario or "").lower()
                    if scenario_lower == "hitl_resolve":
                        nudge_text = (
                            "The user just answered your earlier clarifying "
                            "question. Acknowledge their answer warmly in ONE "
                            "short sentence and confirm you are proceeding "
                            "with that detail. Do NOT call tools. Do NOT "
                            "include reasoning. Output ONLY the message."
                        )
                    elif scenario_lower == "hitl_relay":
                        nudge_text = (
                            "A background task needs the user's input. Ask "
                            "the pending question naturally and briefly in "
                            "ONE sentence. Do NOT call tools. Do NOT include "
                            "reasoning. Output ONLY the question."
                        )
                    elif scenario_lower in ("weave", "present"):
                        nudge_text = (
                            "Respond now in one short, natural user-facing "
                            "message based on the prior context. Do NOT call "
                            "tools. Do NOT include reasoning. Output ONLY "
                            "the message."
                        )
                    else:
                        nudge_text = (
                            "Now respond directly to the user. Synthesize "
                            "everything you learned from the tools above "
                            "into a helpful, natural response. Do NOT call "
                            "any more tools. Do NOT include your reasoning "
                            "or analysis -- output ONLY the user-facing message."
                        )
                    messages.append(
                        ModelMessage(
                            role="user",
                            content=nudge_text,
                        )
                    )
                    logger.info(
                        "react_loop: front degenerate on iter=%d, "
                        "retrying with nudge + tools stripped",
                        iteration,
                    )
                    # Force text-only on the retry by temporarily
                    # clearing tools for the next iteration
                    tools = []
                    _degenerate_retry_active = True
                    _iter_dur = int((time.monotonic() - _iter_start) * 1000)
                    _iteration_durations.append(_iter_dur)
                    continue
                # If we have saved text from a mixed response, use it
                if last_text_with_tools:
                    logger.info(
                        "react_loop: degenerate on last iter but have saved text (%d chars)",
                        len(last_text_with_tools),
                    )
                    return _make_result("complete", text=last_text_with_tools)
                fallback = get_config().react.front_degenerate_fallback
                # Do NOT fire on_text_response here; front_handler
                # controls emission order (dispatches before final).
                return _make_result("complete", text=fallback)
            # Back degenerate: nudge to submit what it has
            if iteration < effective_max_iterations - 1:
                nudge = _back_progress_nudge(empty_response=True)
                messages.append(ModelMessage(role="user", content=nudge))
                logger.info(
                    "react_loop: back degenerate on iter=%d/%d, nudging (%s)",
                    iteration,
                    effective_max_iterations,
                    "state-aware",
                )
            _iter_dur = int((time.monotonic() - _iter_start) * 1000)
            _iteration_durations.append(_iter_dur)
            continue

        # ---- TEXT WITHOUT TOOL CALLS ----
        if response.has_text and not response.has_tool_calls:
            if actor == "front":
                # L1 termination: text is the final response.
                # Do NOT fire on_text_response here; front_handler
                # emits task dispatches first, THEN response.final,
                # so the FSM sees DISPATCHING -> COMPANIONING -> ...
                # before DISPATCHING -> LISTENING.
                _iter_dur = int((time.monotonic() - _iter_start) * 1000)
                _iteration_durations.append(_iter_dur)
                return _make_result("complete", text=response.text)
            # Back (ITEM #19): text without tool calls
            # Detect pseudo-code pattern: model writes code instead of
            # making a real tool call (e.g. "tool_code\nprint(...)").
            _txt = response.text or ""
            _is_pseudo = any(
                marker in _txt for marker in ("tool_code", "default_api.", "print(", "```python")
            )
            _has_prior_tools = (_parallel_count + _sequential_count) > 0
            if _is_pseudo:
                messages.append(
                    ModelMessage(
                        role="user",
                        content=(
                            "Do NOT write code or pseudo-code. Use the "
                            "submit_result function call directly. Call "
                            "submit_result now with result_type='complete'."
                        ),
                    )
                )
                logger.warning(
                    "react_loop: back pseudo-code detected on iter=%d, nudging",
                    iteration,
                )
            elif _has_prior_tools:
                # Back already used tools but wrote conversational text instead
                # of taking the correct terminal/action step. The nudge must
                # match the observed tool state: discovery-only work is not the
                # same as a successful authority invocation.
                messages.append(
                    ModelMessage(role="user", content=_back_progress_nudge(empty_response=False))
                )
                logger.info(
                    "react_loop: back text-only after tools on iter=%d, " "nudging submit_result",
                    iteration,
                )
            else:
                # Genuine thinking aloud before any tool calls
                messages.append(ModelMessage(role="assistant", content=response.text))
            _iter_dur = int((time.monotonic() - _iter_start) * 1000)
            _iteration_durations.append(_iter_dur)
            continue

        # ---- PROCESS TOOL CALLS ----
        # Track text from mixed (text + tools) responses so we never
        # lose useful content if the model keeps calling tools until
        # budget exhaustion.
        if response.has_text and response.has_tool_calls and actor == "front":
            last_text_with_tools = response.text
            logger.info(
                "react_loop: iter=%d text+tools -- saving text as fallback (%d chars)",
                iteration,
                len(response.text),
            )

        # Append ONE assistant message with ALL tool calls (Step 7f)
        messages.append(
            ModelMessage(
                role="assistant",
                content=response.text if response.text else "",
                tool_calls=response.tool_calls,
                _raw_provider_content=getattr(response, "_raw_provider_content", None),
            )
        )

        # E3.4.5: warn if submit_result appears alongside other tools.
        # submit_result is processed first (early-return below) and the
        # other tools are skipped, which is correct but indicates LLM
        # confusion when it happens.
        _has_submit = any(tc.name == "submit_result" for tc in response.tool_calls)
        _has_others = any(tc.name != "submit_result" for tc in response.tool_calls)
        if _has_submit and _has_others:
            logger.warning(
                "react_loop: submit_result returned alongside %d other tools "
                "(LLM confusion?) -- submit_result processed first, others "
                "skipped. trace=%s",
                sum(1 for tc in response.tool_calls if tc.name != "submit_result"),
                trace_id[:8] if trace_id else "",
            )

        for tc in response.tool_calls:

            # Back termination (L2): submit_result
            if tc.name == "submit_result":
                result = await tool_dispatcher.dispatch(tc)
                if result.status == "error":
                    # Schema validation or execution failed -- feed
                    # error back to LLM so it can retry with valid args.
                    logger.warning(
                        "react_loop: submit_result dispatch failed "
                        "(error=%s), feeding back to LLM. trace=%s",
                        result.error,
                        trace_id[:8] if trace_id else "",
                    )
                    messages.append(
                        ModelMessage(
                            role="tool",
                            content=json.dumps(
                                {"error": result.error, "hint": "Fix arguments and retry"}
                            ),
                            tool_call_id=getattr(tc, "id", None),
                        )
                    )
                    break  # Let LLM retry on next iteration
                status = (
                    "complete" if tc.arguments.get("result_type") == "complete" else "suspended"
                )
                _iter_dur = int((time.monotonic() - _iter_start) * 1000)
                _iteration_durations.append(_iter_dur)
                return _make_result(status, data=tc.arguments)

        # ---- CLASSIFIED TOOL EXECUTION (M3 E3.4.2/3.4.3/3.4.5) ----
        # Split non-terminal tool calls into parallel-safe and sequential
        # groups using the safety classifier.  A config toggle can force
        # all tools to run sequentially for debugging.
        non_terminal = [tc for tc in response.tool_calls if tc.name != "submit_result"]

        parallel_enabled = get_config().react.parallel_tools_enabled
        parallel_names, sequential_names = classify_tool_batch([tc.name for tc in non_terminal])

        logger.info(
            "react_loop: tool_batch_classified  parallel=%s sequential=%s "
            "parallel_enabled=%s trace=%s",
            parallel_names,
            sequential_names,
            parallel_enabled,
            trace_id[:8] if trace_id else "",
        )

        # Build lookup: name -> list of tool calls (preserves order for dupes)
        _tc_by_name: dict[str, list[Any]] = {}
        for tc in non_terminal:
            _tc_by_name.setdefault(tc.name, []).append(tc)

        paired_results: list[tuple[Any, ToolResult]] = []

        if parallel_enabled and parallel_names:
            # Gather parallel-safe tools from the original order
            parallel_tcs = [tc for tc in non_terminal if tc.name in set(parallel_names)]
            parallel_results = await asyncio.gather(*[_run_tool(tc) for tc in parallel_tcs])
            paired_results.extend(parallel_results)
            _parallel_count += len(parallel_tcs)

        # Sequential tools (always sequential, or ALL tools when toggle off)
        if parallel_enabled:
            sequential_tcs = [tc for tc in non_terminal if tc.name in set(sequential_names)]
        else:
            sequential_tcs = non_terminal

        for tc in sequential_tcs:
            # M6 E6.2 (C03): Use the timeout-wrapped helper so sequential
            # tool dispatch shares the same hang protection as parallel.
            _tc, result = await _run_tool(tc)
            paired_results.append((tc, result))
            _sequential_count += 1

        # Re-sort results to match the LLM's original tool call order.
        # parallel+sequential execution may interleave; the LLM expects
        # observations in the same order it issued calls.
        _tc_order = {id(tc): idx for idx, tc in enumerate(non_terminal)}
        paired_results.sort(key=lambda pair: _tc_order.get(id(pair[0]), 999))

        for idx, (tc, result) in enumerate(paired_results):
            tool_key = _tool_key(tc)
            _tool_name = getattr(tc, "name", "") or ""
            _tool_name_counts[_tool_name] = _tool_name_counts.get(_tool_name, 0) + 1
            if result.is_ok():
                call_id = str(getattr(tc, "id", "") or "")
                if call_id:
                    _completed_tool_call_ids.add(call_id)
                _completed_tool_arg_keys.add(tool_key)
            elif _is_retryable_error(result):
                _retryable_error_counts[tool_key] = _retryable_error_counts.get(tool_key, 0) + 1
                _record_loop_event(
                    "tool_retryable_error",
                    iteration,
                    {
                        "tool_name": getattr(tc, "name", ""),
                        "args_hash": hash_tool_arguments(getattr(tc, "arguments", {}) or {}),
                        "count": _retryable_error_counts[tool_key],
                    },
                )
                if _retryable_error_counts[tool_key] >= 2:
                    result = ToolResult(
                        tool_name=getattr(tc, "name", "unknown"),
                        status="error",
                        data={"retryable": False},
                        error=f"terminal repeated retryable error: {result.error}",
                    )
                    paired_results[idx] = (tc, result)

        for tc, result in paired_results:
            if actor == "back":
                tool_name = str(getattr(tc, "name", "") or "")
                if tool_name:
                    _back_tool_names_seen.add(tool_name)
                if tool_name == "discover_capabilities" and result.is_ok():
                    data = result.data if isinstance(result.data, dict) else {}
                    count = data.get("count")
                    capabilities = data.get("capabilities")
                    if (isinstance(count, int) and count > 0) or bool(capabilities):
                        _back_capability_candidates_seen = True
                        _back_discovery_payloads.append(data)
                elif tool_name in _BACK_AUTHORITY_TOOL_NAMES and result.is_ok():
                    _back_authority_tool_attempted = True

            # Collect dispatch_task calls (L3)
            if tc.name == "dispatch_task":
                task_entry = dict(tc.arguments)
                # Merge system-generated task_id from ToolResult so the
                # downstream dispatch envelope carries the canonical ID.
                if result.is_ok() and result.data:
                    task_id = result.data.get("task_id")
                    if task_id:
                        task_entry["task_id"] = task_id
                    # Also merge the full _dispatch payload if present
                    dispatch_payload = result.data.get("_dispatch")
                    if isinstance(dispatch_payload, dict):
                        task_entry.update(dispatch_payload)
                dispatched_tasks.append(task_entry)

            # Log artifact creation (invoke_capability with artifact_type)
            if (
                tc.name == "invoke_capability"
                and result.is_ok()
                and result.data.get("artifact_type")
            ):
                logger.info("Artifact created: type=%s", result.data.get("artifact_type"))

            # Append tool result as observation (ReAct pattern)
            messages.append(_tool_result_to_msg(tc, _result_to_dict(result)))
            if (
                actor == "back"
                and result.is_error()
                and str(result.error or "").startswith("capability_binding_")
            ):
                messages.append(
                    ModelMessage(role="user", content=_capability_binding_repair_message(result))
                )

        if actor == "front" and not dispatched_tasks:
            if context_read_gap_requires_dispatch(paired_results):
                policy_result = _front_policy_dispatch("context_read_no_evidence")
                if policy_result is not None:
                    _iter_dur = int((time.monotonic() - _iter_start) * 1000)
                    _iteration_durations.append(_iter_dur)
                    return policy_result

            # Front spin guard: inject a synthesis nudge when recall_memory
            # has been called 3+ times across iterations without the model
            # producing a response. Identical completed calls are already
            # de-duplicated by _is_completed_duplicate(); varied queries need
            # a name-level nudge rather than a terminal loop kill.
            _spin_recall = _tool_name_counts.get("recall_memory", 0)
            if _spin_recall >= 3 and iteration < effective_max_iterations - 2:
                messages.append(
                    ModelMessage(
                        role="user",
                        content=(
                            "You have queried memory multiple times and have enough context. "
                            "Now respond directly to the user using the information above. "
                            "If the task needs a background action, call dispatch_task once. "
                            "Do NOT call recall_memory again."
                        ),
                    )
                )
                logger.info(
                    "react_loop: front spin guard — recall_memory called %d times "
                    "without response, injecting synthesis nudge iter=%d trace=%s",
                    _spin_recall,
                    iteration,
                    trace_id[:8] if trace_id else "",
                )
                _record_loop_event(
                    "front_spin_nudge",
                    iteration,
                    {"recall_count": _spin_recall},
                )

        if (
            actor == "back"
            and _back_capability_candidates_seen
            and not _back_authority_tool_attempted
            and not _back_capability_spin_nudge_sent
        ):
            _back_spin_count = (
                _tool_name_counts.get("discover_capabilities", 0)
                + _tool_name_counts.get("recall_memory", 0)
                + _tool_name_counts.get("summarize_context", 0)
            )
            if _back_spin_count >= 2 and iteration < effective_max_iterations - 1:
                messages.append(
                    ModelMessage(
                        role="user",
                        content=(
                            "You have already discovered viable capability candidates and "
                            "checked enough context. Do NOT call discover_capabilities, "
                            "recall_memory, or summarize_context again for this same task. "
                            "Use invoke_capability or batch_invoke_capabilities with an exact "
                            "registry-owned capability name and schema-valid params. If a "
                            "required input is missing, call submit_result with "
                            "result_type='needs_human' and ask only for that missing detail."
                        ),
                    )
                )
                _back_capability_spin_nudge_sent = True
                logger.info(
                    "react_loop: back capability spin guard — observed %d discovery/context "
                    "tools without authority invocation, injecting nudge iter=%d trace=%s",
                    _back_spin_count,
                    iteration,
                    trace_id[:8] if trace_id else "",
                )
                _record_loop_event(
                    "back_capability_spin_nudge",
                    iteration,
                    {"tool_count": _back_spin_count},
                )

        if actor == "back":
            for _, result in paired_results:
                recovery = ask_human_recovery_from_tool_data(result.data)
                if recovery is None:
                    continue
                logger.info(
                    "react_loop: back tool recovery contract -> suspended "
                    "action=%s capability=%s trace=%s",
                    recovery.get("action"),
                    recovery.get("capability_name"),
                    trace_id[:8] if trace_id else "",
                )
                _iter_dur = int((time.monotonic() - _iter_start) * 1000)
                _iteration_durations.append(_iter_dur)
                return _make_result("suspended", data=_recovery_to_suspended_data(recovery))

        # ---- M13.E3 SAFETY SHORT-CIRCUIT ----
        # Detect a safety / policy denial in this iteration's tool
        # results and short-circuit the ReAct loop. Without this the
        # loop will faithfully feed the denial observation back to
        # the LLM, which often retries the same forbidden act and
        # burns the entire iteration budget. Front returns a graceful
        # apology; Back marks the task suspended for human review.
        _SAFETY_REASONS = frozenset(
            {
                "front_capability_not_whitelisted",
                "conscience_forbidden",
                "policy_deny",
                "policy_denied",
            }
        )
        _safety_hit: tuple[Any, ToolResult] | None = None
        for _tc, _r in paired_results:
            if not _r.is_error():
                continue
            _data = _r.data if isinstance(_r.data, dict) else {}
            _decision = str(_data.get("policy_decision", "")).upper()
            _reason = str(_data.get("reason", "")).lower()
            if _decision == "DENY" or _reason in _SAFETY_REASONS:
                _safety_hit = (_tc, _r)
                break
        if _safety_hit is not None:
            _tc, _r = _safety_hit
            logger.warning(
                "react_loop: SAFETY short-circuit on iter=%d actor=%s "
                "tool=%s reason=%s -- aborting loop. trace=%s",
                iteration,
                actor,
                _tc.name,
                (_r.data or {}).get("reason") if isinstance(_r.data, dict) else "",
                trace_id[:8] if trace_id else "",
            )
            _iter_dur = int((time.monotonic() - _iter_start) * 1000)
            _iteration_durations.append(_iter_dur)
            if actor == "front":
                _safety_text = "I can't help with that here. I've flagged it for review."
                return _make_result("complete", text=_safety_text)
            # Back: mark suspended so the orchestrator surfaces to HIL.
            return _make_result(
                "suspended",
                data={
                    "safety_denial": True,
                    "tool": _tc.name,
                    "reason": (
                        (_r.data or {}).get("reason")
                        if isinstance(_r.data, dict)
                        else "policy_deny"
                    ),
                },
            )

        if actor == "front" and any(
            tc.name == "dispatch_task" and result.is_ok() for tc, result in paired_results
        ):
            # If the model already produced text alongside the dispatch tool
            # call, surface it immediately. Otherwise, inject a synthesis
            # nudge and continue the loop so the LLM (not the kernel) crafts
            # the user-facing acknowledgement. No deterministic ACK text is
            # ever emitted by the kernel.
            if last_text_with_tools:
                logger.info(
                    "react_loop: front dispatched task(s) on iter=%d -- "
                    "using mixed-response text from LLM",
                    iteration,
                )
                _iter_dur = int((time.monotonic() - _iter_start) * 1000)
                _iteration_durations.append(_iter_dur)
                return _make_result("complete", text=last_text_with_tools)
            messages.append(
                ModelMessage(
                    role="user",
                    content=(
                        "You have dispatched the background task. Now write a brief, "
                        "natural acknowledgement to the user confirming you are working "
                        "on their request. Do NOT call any more tools. Respond with text only."
                    ),
                )
            )
            logger.info(
                "react_loop: front dispatched task(s) on iter=%d -- "
                "no text yet, looping for LLM ack",
                iteration,
            )

        # Per-iteration timing for the tool-execution branch
        _iter_dur = int((time.monotonic() - _iter_start) * 1000)
        _iteration_durations.append(_iter_dur)
        logger.debug(
            "react_loop: iter=%d completed in %dms (actor=%s)",
            iteration,
            _iter_dur,
            actor,
        )

    # ---- BUDGET EXHAUSTED ----
    if actor == "front":
        # If we captured text from a mixed (text+tools) response, use it
        # instead of the generic fallback -- it's real LLM output.
        if last_text_with_tools:
            logger.info(
                "react_loop: budget exhausted but recovered text from mixed response (%d chars)",
                len(last_text_with_tools),
            )
            return _make_result("complete", text=last_text_with_tools)
        # Do NOT fire on_text_response here; front_handler handles emission.
        return _make_result("budget_exhausted", text=get_config().react.front_budget_fallback)

    _record_loop_event(
        "last_iteration_submit",
        max(0, effective_max_iterations - 1),
        {"error_code": "REACT_MISSING_SUBMIT_RESULT"},
    )
    return _make_result(
        "missing_submit_result",
        data={"error_code": "REACT_MISSING_SUBMIT_RESULT"},
    )
