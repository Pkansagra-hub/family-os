"""
Protocol interfaces for the ReactLoopScratchpad PoC.

Defines abstract contracts for runners, LLM clients, and tools
so both naive and smart implementations share a common interface.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.models import Finding, Message, RunResult, Scenario, ToolCall, ToolResult

# ---------------------------------------------------------------------------
# LLM Client protocol
# ---------------------------------------------------------------------------


class LLMResponse:
    """Structured response from an LLM call."""

    def __init__(
        self,
        text: Optional[str] = None,
        tool_calls: Optional[List[ToolCall]] = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        raw: Any = None,
    ):
        self.text = text
        self.tool_calls = tool_calls or []
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.raw = raw

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def has_text(self) -> bool:
        return self.text is not None and len(self.text.strip()) > 0


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM interactions."""

    async def generate(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        force_tool_call: bool = False,
    ) -> LLMResponse:
        """Generate a response from the LLM."""
        ...

    async def summarize_messages(
        self,
        messages: List[Message],
    ) -> str:
        """Summarize a list of messages into a concise digest."""
        ...

    async def extract_findings(
        self,
        tool_name: str,
        raw_result: Any,
    ) -> List[Finding]:
        """Extract structured findings from a raw tool result."""
        ...

    async def extract_findings_batch(
        self,
        tool_results: List[tuple],
    ) -> List[Finding]:
        """Extract findings from multiple tool results in one LLM call."""
        ...


# ---------------------------------------------------------------------------
# Tool Registry protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ToolRegistry(Protocol):
    """Protocol for tool registries."""

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        """Get tool declarations in Google AI function calling format."""
        ...

    async def execute(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Execute a tool and return the result."""
        ...

    def get_tool_names(self) -> List[str]:
        """Get all registered tool names."""
        ...


# ---------------------------------------------------------------------------
# React Runner protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ReactRunner(Protocol):
    """Protocol for ReAct loop runners (naive or smart)."""

    @property
    def name(self) -> str:
        """Runner name for identification."""
        ...

    async def run(
        self,
        scenario: Scenario,
        tools: ToolRegistry,
        llm: LLMClient,
    ) -> RunResult:
        """Execute a scenario and return the result."""
        ...
