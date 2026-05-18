"""Domain-agnostic Front routing policy based on tool authority.

The kernel does not know whether a deployment is family, banking, finance,
government, or something else. It only knows actor/tool contracts:

* context-read tools may provide memory or session context;
* discovery tools may expose capability contracts;
* terminal authority tools dispatch work or invoke capabilities.

This module keeps that separation explicit so Front cannot turn an empty
context lookup into a final answer when a worker/capability path is available.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from inspect import isawaitable
from typing import Any, Literal

from k1.concierge.llm.types import ModelMessage, ToolSchema
from k1.concierge.tools.result_protocol import ToolResult

CONTEXT_READ_TOOLS = frozenset({"recall_memory", "summarize_context"})
DISCOVERY_TOOLS = frozenset({"discover_capabilities"})
TERMINAL_AUTHORITY_TOOLS = frozenset(
    {"dispatch_task", "invoke_capability", "batch_invoke_capabilities"}
)

CapabilityBindingStatus = Literal[
    "bound",
    "needs_discovery",
    "ambiguous",
    "not_found",
    "invalid_candidate",
    "needs_human",
]


@dataclass(frozen=True)
class CapabilityBindingRequest:
    action: str
    domain: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    candidate_capability_name: str | None = None
    session_id: str = ""
    trace_id: str = ""
    safety_band: str = "GREEN"
    actor: str = "back"


@dataclass(frozen=True)
class CapabilityBindingResult:
    status: CapabilityBindingStatus
    capability_name: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    prompt_template: str | None = None
    activity_profile: str | None = None
    context_override: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    recovery: dict[str, Any] | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DiscoveryCallable = Callable[..., Awaitable[Any]]
ExactLookupCallable = Callable[[str], Awaitable[Any] | Any]


async def bind_capability(
    request: CapabilityBindingRequest,
    discover_capabilities: DiscoveryCallable,
    exact_lookup: ExactLookupCallable | None = None,
) -> CapabilityBindingResult:
    """Bind a conversational capability request to exact registry evidence."""
    candidate_name = _clean_optional_str(request.candidate_capability_name)
    action = _clean_optional_str(request.action)

    if candidate_name is not None:
        if exact_lookup is not None:
            exact_contract = await _lookup_exact_capability(exact_lookup, candidate_name)
            if exact_contract is not None:
                return _bound_result(
                    request,
                    _candidate_from_contract(exact_contract),
                    reason="exact_registry_lookup",
                )

        exact_candidates = await _discover_binding_candidates(
            discover_capabilities,
            intent=candidate_name,
            domain=None,
            top_k=25,
            safety_band=request.safety_band,
        )
        for candidate in exact_candidates:
            if candidate.get("name") == candidate_name:
                return _bound_result(
                    request,
                    candidate,
                    reason="exact_candidate_match",
                )

        if exact_candidates:
            return CapabilityBindingResult(
                status="invalid_candidate",
                params=dict(request.params),
                candidates=exact_candidates,
                recovery=_selection_recovery(exact_candidates, rejected_name=candidate_name),
                reason="candidate_not_exact_registry_name",
            )

        if action and action != candidate_name:
            discovered_candidates = await _discover_binding_candidates(
                discover_capabilities,
                intent=action,
                domain=request.domain,
                top_k=5,
                safety_band=request.safety_band,
            )
            if discovered_candidates:
                return CapabilityBindingResult(
                    status="invalid_candidate",
                    params=dict(request.params),
                    candidates=discovered_candidates,
                    recovery=_selection_recovery(
                        discovered_candidates,
                        rejected_name=candidate_name,
                    ),
                    reason="candidate_not_exact_registry_name",
                )

        return CapabilityBindingResult(
            status="needs_discovery",
            params=dict(request.params),
            reason="candidate_not_verified_by_discovery",
        )

    if action is None:
        return CapabilityBindingResult(
            status="needs_discovery",
            params=dict(request.params),
            reason="action_required_for_binding",
        )

    discovered_candidates = await _discover_binding_candidates(
        discover_capabilities,
        intent=action,
        domain=request.domain,
        top_k=5,
        safety_band=request.safety_band,
    )
    if not discovered_candidates:
        return CapabilityBindingResult(
            status="not_found",
            params=dict(request.params),
            reason="no_registry_candidates",
        )
    if len(discovered_candidates) == 1:
        return _bound_result(
            request,
            discovered_candidates[0],
            reason="single_discovered_candidate",
        )
    return CapabilityBindingResult(
        status="ambiguous",
        params=dict(request.params),
        candidates=discovered_candidates,
        recovery=_selection_recovery(discovered_candidates),
        reason="multiple_discovered_candidates",
    )


async def _lookup_exact_capability(
    exact_lookup: ExactLookupCallable,
    capability_name: str,
) -> Any | None:
    try:
        contract = exact_lookup(capability_name)
        if isawaitable(contract):
            contract = await contract
    except Exception:
        return None
    if _mapping_or_attr(contract, "name") == capability_name:
        return contract
    return None


async def _discover_binding_candidates(
    discover_capabilities: DiscoveryCallable,
    *,
    intent: str,
    domain: str | None,
    top_k: int,
    safety_band: str,
) -> list[dict[str, Any]]:
    try:
        retrieval = await discover_capabilities(
            intent=intent,
            domain=[domain] if domain else None,
            top_k=top_k,
            safety_band=safety_band,
        )
    except Exception:
        return []
    capabilities = getattr(retrieval, "capabilities", [])
    if not isinstance(capabilities, (list, tuple)):
        return []

    candidates: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for scored in capabilities:
        candidate = _candidate_from_scored_capability(scored)
        name = str(candidate.get("name", "") or "")
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        candidates.append(candidate)
    return candidates


def _candidate_from_scored_capability(scored: Any) -> dict[str, Any]:
    contract = _mapping_or_attr(scored, "contract")
    source = contract if contract is not None else scored
    candidate = _candidate_from_contract(source)
    candidate["score"] = _safe_float(_mapping_or_attr(scored, "score"), default=0.0)
    return candidate


def _candidate_from_contract(source: Any) -> dict[str, Any]:
    domains = _string_list(_mapping_or_attr(source, "domain"))
    candidate = {
        "name": str(_mapping_or_attr(source, "name") or ""),
        "description": str(_mapping_or_attr(source, "description") or ""),
        "domain": domains[0] if domains else "",
        "domains": domains,
        "score": 1.0,
    }
    prompt_template = _clean_optional_str(_mapping_or_attr(source, "prompt_template"))
    activity_profile = _clean_optional_str(_mapping_or_attr(source, "activity_profile"))
    if prompt_template is not None:
        candidate["prompt_template"] = prompt_template
    if activity_profile is not None:
        candidate["activity_profile"] = activity_profile
    return candidate


def _bound_result(
    request: CapabilityBindingRequest,
    candidate: Mapping[str, Any],
    *,
    reason: str,
) -> CapabilityBindingResult:
    activity_profile = _clean_optional_str(candidate.get("activity_profile"))
    context_override: dict[str, Any] = {}
    if activity_profile is not None:
        context_override["activity_profile"] = activity_profile
    return CapabilityBindingResult(
        status="bound",
        capability_name=str(candidate.get("name") or ""),
        params=dict(request.params),
        prompt_template=_clean_optional_str(candidate.get("prompt_template")),
        activity_profile=activity_profile,
        context_override=context_override,
        candidates=[dict(candidate)],
        reason=reason,
    )


def _selection_recovery(
    candidates: list[dict[str, Any]],
    *,
    rejected_name: str | None = None,
) -> dict[str, Any]:
    recovery = {
        "action": "select_capability",
        "instruction": (
            "The rejected capability name is not bound to this task. Use one "
            "of the exact registry names in candidates, and do not retry the "
            "same rejected name with the same parameters."
        ),
        "candidates": [dict(candidate) for candidate in candidates],
    }
    if rejected_name:
        recovery["rejected_name"] = rejected_name
    return recovery


def _mapping_or_attr(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value if item]
    return []


def _clean_optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def latest_user_text(messages: list[ModelMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and isinstance(message.content, str):
            return message.content.strip()
    return ""


def has_dispatch_tool(tools: Iterable[ToolSchema]) -> bool:
    return any(tool.name == "dispatch_task" for tool in tools)


def has_terminal_authority_tool(tool_names: Iterable[str]) -> bool:
    return any(name in TERMINAL_AUTHORITY_TOOLS for name in tool_names)


def used_only_context_read_tools(tool_names: Iterable[str]) -> bool:
    names = list(tool_names)
    return bool(names) and all(name in CONTEXT_READ_TOOLS for name in names)


def context_read_has_evidence(result: ToolResult) -> bool:
    if result.is_error() or not isinstance(result.data, dict):
        return False
    data = result.data
    count = data.get("count")
    if isinstance(count, int):
        return count > 0
    for key in ("memories", "items", "results", "documents", "records"):
        value = data.get(key)
        if isinstance(value, (list, tuple, dict, set)):
            return bool(value)
    return any(value not in (None, "", [], {}, ()) for value in data.values())


def context_read_gap_requires_dispatch(paired_results: Iterable[tuple[Any, ToolResult]]) -> bool:
    pairs = list(paired_results)
    if not pairs:
        return False
    tool_names = [str(getattr(tool_call, "name", "") or "") for tool_call, _ in pairs]
    if has_terminal_authority_tool(tool_names) or not used_only_context_read_tools(tool_names):
        return False
    return not any(context_read_has_evidence(result) for _, result in pairs)


def synthesize_dispatch_task(user_text: str, reason: str) -> dict[str, Any]:
    return {
        "task_id": f"task-{uuid.uuid4().hex[:8]}",
        "intents": [
            {
                "action": user_text,
                "params": {},
            }
        ],
        "urgency": "normal",
        "reference_context": {},
        "tier": "LOW",
        "safety_band": "GREEN",
        "_policy_route": reason,
    }
