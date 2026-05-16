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
from typing import Any, Iterable

from k1.concierge.llm.types import ModelMessage, ToolSchema
from k1.concierge.tools.result_protocol import ToolResult

CONTEXT_READ_TOOLS = frozenset({"recall_memory", "summarize_context"})
DISCOVERY_TOOLS = frozenset({"discover_capabilities"})
TERMINAL_AUTHORITY_TOOLS = frozenset(
    {"dispatch_task", "invoke_capability", "batch_invoke_capabilities"}
)


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
        "safety_band": "AMBER",
        "_policy_route": reason,
    }
