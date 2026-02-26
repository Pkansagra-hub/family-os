"""
LLM Adapter Types -- Provider-Agnostic Request/Response Envelope
================================================================

V2 Design Ref: Section 10.2 (ConciergeModelRequest, ConciergeModelResponse,
ToolCallResult, ToolResultMessage, StreamChunk, ModelMessage, ToolSchema)

Every actor (Front, Back, Planner, dynamic agents) uses these types.
No provider SDK types leak outside the adapter boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Capability tags -- what kind of LLM call?
# ---------------------------------------------------------------------------


class Capability(str, Enum):
    """LLM call capability tag.

    The adapter uses this to select model, configure tool_config,
    set response_mime_type, and enforce budgets.
    """

    CHAT = "CHAT"  # text in, text out (acks, error explanations)
    TOOL_CALL = "TOOL_CALL"  # text in, tool calls + text out (ReAct loops)
    STRUCTURED = "STRUCTURED"  # text in, schema-valid JSON out (dispatch parsing)
    STREAM = "STREAM"  # streaming variant of CHAT
    REASON = "REASON"  # chain-of-thought + answer (complex planning)


class FinishReason(str, Enum):
    """Why the LLM stopped generating."""

    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    ERROR = "error"
    SAFETY = "safety"
    VALIDATION_FALLBACK = "validation_fallback"


class ThinkingLevel(str, Enum):
    """Controls the thinking budget for models that support it."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ---------------------------------------------------------------------------
# Tool Schema -- provider-agnostic tool definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSchema:
    """Provider-agnostic tool definition using JSON Schema parameters.

    The adapter converts this to provider-native format internally:
      - Gemini: types.FunctionDeclaration(name, description, parameters)
      - OpenAI: {"type": "function", "function": {...}}
      - Anthropic: {"name": ..., "input_schema": ...}

    Callers define tools once; the adapter handles the rest.

    V2 Design Ref: Section 6.0 (tool taxonomy: signal, cognitive, read, action, control)
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object
    returns: dict[str, Any] | None = None  # documentation/validation only
    actor: str | None = None  # "front" | "back" | "both"
    category: str | None = None  # "signal" | "cognitive" | "read" | "action" | "control"
    side_effects: bool = False  # Does this tool mutate state?


# ---------------------------------------------------------------------------
# ModelMessage -- provider-agnostic conversation message
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelMessage:
    """Provider-agnostic message in conversation history.

    role mapping per provider:
      "user"      -> Gemini: role="user"     | OpenAI: role="user"
      "assistant" -> Gemini: role="model"    | OpenAI: role="assistant"
      "tool"      -> Gemini: FunctionResponse| OpenAI: role="tool"
      "system"    -> NOT used in contents; passed via system_instruction
    """

    role: str  # "user" | "assistant" | "tool"
    content: str  # text content
    tool_call_id: str | None = None  # for role="tool": which call this answers
    name: str | None = None  # for role="tool": tool name
    tool_calls: list[ToolCallResult] | None = None  # for role="assistant": tool calls made
    # Raw provider Content object (Gemini). Preserves thought signatures
    # across function-calling round-trips so the model can maintain its
    # reasoning chain.  Set by the adapter; opaque to all other layers.
    _raw_provider_content: Any = None


# ---------------------------------------------------------------------------
# ConciergeModelRequest -- the universal LLM request envelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConciergeModelRequest:
    """Provider-agnostic LLM request envelope.

    Constructed by Front handler, Back handler, or any actor.
    The adapter translates this to the target provider's format.
    """

    # --- What kind of call? ---
    capability: str = Capability.TOOL_CALL

    # --- Messages (provider-agnostic) ---
    system_prompt: str = ""
    messages: list[ModelMessage] = field(default_factory=list)

    # --- Tools (only for TOOL_CALL capability) ---
    tools: list[ToolSchema] | None = None
    tool_choice: str = "auto"  # "auto" | "required" | "none" | specific tool name

    # --- Structured output (JSON mode) ---
    response_schema: dict[str, Any] | None = None  # JSON Schema for STRUCTURED capability

    # --- Budget constraints ---
    # Defaults read from config (llm.default_max_tokens, etc.).
    # Kept as module-level defaults for backward compatibility.
    max_tokens: int = 65536
    timeout_ms: int = 120_000
    temperature: float = 1.0  # Gemini 3 recommends 1.0 default

    # --- Thinking configuration ---
    thinking: ThinkingLevel | None = None  # None = model default

    # --- Observability ---
    trace_id: str = ""
    actor: str = ""  # "front" | "back" | "planner" | agent name
    scenario: str = ""  # "user_input" | "task_dispatch" | "weave" etc.

    # --- Model preference (optional) ---
    model_hint: str | None = None  # "fast" | "smart" | "cheap" | specific model name

    # --- Batch control ---
    stop_sequences: list[str] | None = None


# ---------------------------------------------------------------------------
# ToolCallResult -- single tool call extracted from LLM response
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolCallResult:
    """Single tool call extracted from LLM response."""

    id: str  # unique call ID (for tool result pairing)
    name: str  # tool function name
    arguments: dict[str, Any] = field(default_factory=dict)  # parsed arguments


# ---------------------------------------------------------------------------
# ToolResultMessage -- tool execution result for LLM consumption
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolResultMessage:
    """Tool execution result formatted for LLM consumption.

    Used to build the next iteration's messages in ReAct loops.
    Section 10.4 defines the conversion function.
    """

    tool_call_id: str  # matches ToolCallResult.id
    name: str  # tool name (for display)
    content: str  # JSON-serialized result


# ---------------------------------------------------------------------------
# ConciergeModelResponse -- the universal LLM response envelope
# ---------------------------------------------------------------------------


@dataclass
class ConciergeModelResponse:
    """Provider-agnostic LLM response envelope.

    The adapter normalizes ALL provider responses to this format.
    Callers never see Gemini candidates, OpenAI choices,
    or Anthropic content blocks.
    """

    # --- Text output ---
    text: str = ""

    # --- Tool calls ---
    tool_calls: list[ToolCallResult] = field(default_factory=list)

    # --- Structured JSON output ---
    json_output: dict[str, Any] | None = None  # parsed JSON when STRUCTURED capability

    # --- Token usage ---
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_thoughts: int = 0  # thinking tokens (Gemini 3 / 2.5 with thinking)
    latency_ms: int = 0
    model_id: str = ""
    finish_reason: str = FinishReason.STOP

    # --- Thinking content ---
    thought_text: str = ""  # exposed thinking/reasoning content if available

    # Raw provider Content object from the response (Gemini).
    # Preserves thought signatures for function-calling round-trips.
    _raw_provider_content: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def has_text(self) -> bool:
        return bool(self.text and self.text.strip())

    @property
    def has_json(self) -> bool:
        return self.json_output is not None

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out + self.tokens_thoughts


# ---------------------------------------------------------------------------
# StreamChunk -- single chunk from streaming response
# ---------------------------------------------------------------------------


@dataclass
class StreamChunk:
    """Single chunk from streaming response.

    Used by generate_stream(). Front consumes these for real-time
    ack delivery and final response streaming.

    chunk_type values:
      - "text_delta":      incremental text for real-time display
      - "tool_call_delta": tool call accumulating across chunks
      - "thought_delta":   thinking/reasoning text (Gemini 3)
      - "done":            final signal with complete ConciergeModelResponse
    """

    chunk_type: str  # "text_delta" | "tool_call_delta" | "thought_delta" | "done"
    text: str = ""  # for text_delta
    tool_call_partial: ToolCallResult | None = None  # for tool_call_delta
    thought_text: str = ""  # for thought_delta
    response: ConciergeModelResponse | None = None  # for done: complete response


# ---------------------------------------------------------------------------
# Convenience: tool_result_to_message
# ---------------------------------------------------------------------------


def tool_result_to_message(tool_call: ToolCallResult, result: dict[str, Any]) -> ModelMessage:
    """Convert tool execution result to a ModelMessage for the LLM.

    This is how the LLM "observes" tool results in the ReAct loop.
    The adapter converts this ModelMessage to provider format:
      - Gemini: Content(role="user", parts=[FunctionResponse(...)])
      - OpenAI: {"role": "tool", "content": json, "tool_call_id": id}
    """
    return ModelMessage(
        role="tool",
        content=json.dumps(result, default=str),
        tool_call_id=tool_call.id,
        name=tool_call.name,
    )


# ---------------------------------------------------------------------------
# Convenience: build assistant message from response
# ---------------------------------------------------------------------------


def response_to_assistant_message(response: ConciergeModelResponse) -> ModelMessage:
    """Convert a ConciergeModelResponse to an assistant ModelMessage.

    Used in ReAct loops to append the model's turn to conversation history
    before adding tool results.
    """
    return ModelMessage(
        role="assistant",
        content=response.text,
        tool_calls=response.tool_calls if response.has_tool_calls else None,
    )
