"""
Tool Result Protocol -- ToolResult envelope and tool_result_to_message()
========================================================================

V2 Design Ref: Section 6.3 (Result Protocol)

Every tool returns a ToolResult envelope that carries:
  - tool_name: which tool was called
  - status: "ok" | "error" | "partial"
  - data: the actual result payload (JSON-serializable)
  - error: optional error message

tool_result_to_message() converts a ToolResult into a ToolResultMessage
that the LLM adapter can append to conversation history for multi-turn
ReAct loops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from k1.concierge.llm.types import ToolResultMessage


@dataclass(frozen=True)
class ToolResult:
    """Envelope returned by every tool implementation."""

    tool_name: str
    status: str  # "ok" | "error" | "partial"
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def is_ok(self) -> bool:
        return self.status == "ok"

    def is_error(self) -> bool:
        return self.status == "error"


def tool_result_to_message(
    call_id: str,
    result: ToolResult,
) -> ToolResultMessage:
    """Convert a ToolResult into a ToolResultMessage for the LLM history.

    Args:
        call_id: The tool_call_id from the model's function-call request.
        result: The ToolResult envelope from tool execution.

    Returns:
        ToolResultMessage ready to append to the conversation.
    """
    import json

    if result.is_error():
        content = json.dumps(
            {"error": result.error, "tool": result.tool_name},
            ensure_ascii=False,
        )
    else:
        content = json.dumps(result.data, ensure_ascii=False)

    return ToolResultMessage(
        tool_call_id=call_id,
        name=result.tool_name,
        content=content,
    )
