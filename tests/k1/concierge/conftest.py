"""Shared test utilities for k1.concierge tests.

Provides helpers to construct K1 HubResponse mocks that work with
the updated react_loop (which calls model.execute() -> HubResponse
instead of the legacy model.generate() -> ConciergeModelResponse).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

from k1.model_hub.types import (
    CapabilityType,
    ChatResult,
    FinishReason,
    HubResponse,
    ResponseMetadata,
    TokenUsage,
    ToolCallResult,
    ToolCallResultSet,
)


def _default_metadata(
    finish_reason: FinishReason = FinishReason.STOP,
) -> ResponseMetadata:
    return ResponseMetadata(
        request_id="test-req-1",
        model_id="test-model",
        provider_id="test",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        cost_usd=0.0,
        latency_ms=50,
        cache_hit=False,
        capability=CapabilityType.CHAT,
        trace_id="test-trace",
        finish_reason=finish_reason,
    )


def make_hub_text_response(
    text: str = "Hello",
    finish_reason: FinishReason = FinishReason.STOP,
) -> HubResponse:
    """Build a HubResponse that _unwrap_response converts to text-only ConciergeModelResponse."""
    return HubResponse(
        result=ChatResult(text=text),
        metadata=_default_metadata(finish_reason),
    )


def make_hub_tool_response(
    tool_calls: list[dict[str, Any]] | None = None,
    text: str = "",
) -> HubResponse:
    """Build a HubResponse with tool calls.

    tool_calls: list of {"id": ..., "name": ..., "arguments": ...}
    arguments can be str (raw JSON) or dict (will be serialized).
    """
    tcs = [
        ToolCallResult(
            id=tc.get("id", f"call-{i}"),
            name=tc["name"],
            arguments=(
                json.dumps(tc["arguments"])
                if isinstance(tc.get("arguments"), dict)
                else tc.get("arguments", "{}")
            ),
        )
        for i, tc in enumerate(tool_calls or [])
    ]
    return HubResponse(
        result=ToolCallResultSet(text=text, tool_calls=tcs),
        metadata=_default_metadata(),
    )


def make_hub_empty_response() -> HubResponse:
    """Build a HubResponse representing a degenerate (empty) LLM reply."""
    return HubResponse(
        result=ChatResult(text=""),
        metadata=_default_metadata(),
    )


def make_execute_model(
    responses: list[HubResponse] | HubResponse | None = None,
) -> AsyncMock:
    """Create an AsyncMock model with execute() returning HubResponse(s).

    If responses is a list, execute() uses side_effect (one per call).
    If responses is a single HubResponse, execute() always returns it.
    If None, returns a default text response.
    """
    model = AsyncMock()
    if responses is None:
        model.execute.return_value = make_hub_text_response()
    elif isinstance(responses, list):
        model.execute.side_effect = responses
    else:
        model.execute.return_value = responses
    return model
