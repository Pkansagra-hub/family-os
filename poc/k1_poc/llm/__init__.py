"""
LLM Universal Adapter Package
==============================

V2 Design Ref: Section 10 (LLM Adapter & Operability)

Provider-agnostic LLM interface. Every actor calls IConciergeModelPort.
No actor imports google.genai, openai, or anthropic.

Exports:
  - IConciergeModelPort       : universal protocol
  - ConciergeModelRequest     : request envelope
  - ConciergeModelResponse    : response envelope
  - ToolCallResult            : single tool call from LLM
  - ToolResultMessage         : tool execution result for LLM
  - StreamChunk               : streaming response chunk
  - ModelMessage              : conversation message
  - ToolSchema                : tool definition
  - Capability                : call type tag
  - FinishReason              : why LLM stopped
  - ThinkingLevel             : thinking budget control
  - GeminiConciergeAdapter    : Gemini provider
  - TestConciergeAdapter      : deterministic test adapter
  - select_model              : capability-based model selection
  - tool_result_to_message    : tool result -> ModelMessage
  - response_to_assistant_message : response -> assistant ModelMessage
"""

from poc.k1_poc.llm.model_selection import (
    DEFAULT_MODEL,
    MODEL_HINT_OVERRIDES,
    MODEL_SELECTION_TABLE,
    select_model,
)
from poc.k1_poc.llm.ports import IConciergeModelPort
from poc.k1_poc.llm.test_adapter import TestConciergeAdapter
from poc.k1_poc.llm.types import (
    Capability,
    ConciergeModelRequest,
    ConciergeModelResponse,
    FinishReason,
    ModelMessage,
    StreamChunk,
    ThinkingLevel,
    ToolCallResult,
    ToolResultMessage,
    ToolSchema,
    response_to_assistant_message,
    tool_result_to_message,
)
from poc.k1_poc.llm.validator import LLMOutputValidator, ValidationResult

# GeminiConciergeAdapter is imported lazily to avoid requiring
# google-genai SDK just to import the package.
# Use: from poc.k1_poc.llm.gemini_adapter import GeminiConciergeAdapter

__all__ = [
    # Protocol
    "IConciergeModelPort",
    # Types
    "Capability",
    "ConciergeModelRequest",
    "ConciergeModelResponse",
    "FinishReason",
    "ModelMessage",
    "StreamChunk",
    "ThinkingLevel",
    "ToolCallResult",
    "ToolResultMessage",
    "ToolSchema",
    # Adapters
    "TestConciergeAdapter",
    # Model selection
    "DEFAULT_MODEL",
    "MODEL_HINT_OVERRIDES",
    "MODEL_SELECTION_TABLE",
    "select_model",
    # Validation (Epic 4.1)
    "LLMOutputValidator",
    "ValidationResult",
    # Helpers
    "tool_result_to_message",
    "response_to_assistant_message",
]
