"""
IConciergeModelPort -- Universal LLM Protocol
==============================================

V2 Design Ref: Section 10.1 (IConciergeModelPort protocol)

This is a typing.Protocol with @runtime_checkable so adapters can
be validated at boot time. Two methods: generate() (single call)
and generate_stream() (streaming). Both are async.

Contract rule: Callers NEVER import google.genai, openai, or anthropic.
Callers NEVER construct provider-specific message formats.
Every actor calls this same interface.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from k1.concierge.llm.types import (
    ConciergeModelRequest,
    ConciergeModelResponse,
    StreamChunk,
)


@runtime_checkable
class IConciergeModelPort(Protocol):
    """Universal LLM port for all actors.

    This is the POC's Model Hub interface. Production replaces this
    with the real Model Hub's ILLMPort + LLMGatewayAdapter pipeline.

    Every actor (Front, Back, dynamic agents) calls this same interface.
    The adapter handles:
      - Provider routing (Gemini, OpenAI, Anthropic, local)
      - Model selection per capability tag
      - Tool schema conversion to provider format
      - Token budget enforcement
      - Timeout enforcement
      - Streaming delegation
      - Response normalization to ConciergeModelResponse

    Callers NEVER import provider SDKs.
    Callers NEVER construct provider-specific message formats.
    """

    async def generate(self, request: ConciergeModelRequest) -> ConciergeModelResponse:
        """Single LLM inference call. Returns complete response.

        The adapter handles: provider routing, model selection,
        tool schema conversion, token budget enforcement,
        timeout enforcement, response normalization.
        """
        ...

    async def generate_stream(self, request: ConciergeModelRequest) -> AsyncIterator[StreamChunk]:
        """Streaming LLM inference. Yields text deltas + final tool calls.

        StreamChunk types:
          - text_delta:      incremental text for real-time display
          - tool_call_delta: tool call accumulating across chunks
          - thought_delta:   thinking/reasoning text
          - done:            final signal with complete ConciergeModelResponse

        Used by Front for acks and final responses.
        Back never calls generate_stream.
        """
        ...
