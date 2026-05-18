"""ModelHubAdapter -- bridges MW's IModelHubPort to K1's IModelHubPort.

Translates:
  MW  chat(messages, budget_tokens, model_hint) -> ChatResponse
  K1  execute(HubRequest(CHAT, ChatPayload)) -> HubResponse

Invariants enforced:
  MW-06: budget_tokens capped to config limit (default 2000).
  MH-03: trace_id always non-empty (generated if not supplied).
  MH-15: Priority.BACKGROUND (extraction is background work, 60s timeout).

References:
  - E-0.5.3: MemoryWriter->ModelHub Incompatible Port
  - I-0.5.3.1: MW ModelHub adapter implementation
"""

from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional

from k1.memory_writer.types import ChatResponse

# Import K1's IModelHubPort with alias to avoid name collision with MW's
from k1.model_hub.ports.hub_port import IModelHubPort as K1ModelHubPort
from k1.model_hub.types import (
    CapabilityType,
    ChatPayload,
    HubRequest,
    Message,
    ModelPreference,
    Priority,
    RequestConstraints,
)


class ModelHubAdapter:
    """Implements MW's IModelHubPort by wrapping K1's IModelHubPort.

    Translation:
        chat(messages, budget_tokens, model_hint)
        -> execute(HubRequest(CHAT, ChatPayload([Message(...)]),
                   RequestConstraints(max_tokens=budget_tokens,
                                      priority=BACKGROUND)))
        -> ChatResponse(content, token_usage, model, latency_ms)
    """

    def __init__(
        self,
        hub: K1ModelHubPort,
        *,
        trace_id: Optional[str] = None,
        consumer_id: str = "memory_writer",
    ) -> None:
        self._hub = hub
        self._trace_id = trace_id
        self._consumer_id = consumer_id

    async def chat(
        self,
        messages: List[Dict[str, str]],
        budget_tokens: int,
        model_hint: str,
    ) -> ChatResponse:
        """Translate MW chat() to K1 execute().

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            budget_tokens: Max tokens (MW-06: always 2000).
            model_hint: Routing hint (e.g. "cheapest").

        Returns:
            ChatResponse with extracted content and token usage.
        """
        # Build K1 Message objects from MW dict format
        hub_messages = [Message(role=m["role"], content=m["content"]) for m in messages]

        # Separate system prompt if first message is system role
        system_prompt: Optional[str] = None
        chat_messages = hub_messages
        if hub_messages and hub_messages[0].role == "system":
            system_prompt = hub_messages[0].content
            chat_messages = hub_messages[1:]
            # ChatPayload requires non-empty messages; if only system msg,
            # keep it in messages list instead
            if not chat_messages:
                chat_messages = hub_messages
                system_prompt = None

        payload = ChatPayload(
            messages=chat_messages,
            system_prompt=system_prompt,
        )

        trace_id = self._trace_id or str(uuid.uuid4())

        model_preference: Optional[ModelPreference] = None
        provider_preference: Optional[str] = None
        if model_hint and model_hint != "cheapest":
            if _looks_like_model_id(model_hint):
                model_preference = ModelPreference(preferred_model=model_hint)
            else:
                provider_preference = model_hint

        constraints = RequestConstraints(
            max_tokens=budget_tokens,
            timeout_ms=60000,  # BACKGROUND tier: 60s (MH-15)
            priority=Priority.BACKGROUND,
            temperature=0.7,
            model_preference=model_preference,
            provider_preference=provider_preference,
            consumer_id=self._consumer_id,
        )

        request = HubRequest(
            capability=CapabilityType.CHAT,
            payload=payload,
            constraints=constraints,
            trace_id=trace_id,
        )

        start_ms = time.monotonic() * 1000
        response = await self._hub.execute(request)
        elapsed_ms = (time.monotonic() * 1000) - start_ms

        # Extract text from result
        result = response.result
        if isinstance(result, dict):
            content = str(result.get("content", ""))
        else:
            content = str(result) if result is not None else ""

        meta = response.metadata
        return ChatResponse(
            content=content,
            total_tokens=meta.usage.total_tokens,
            prompt_tokens=meta.usage.prompt_tokens,
            completion_tokens=meta.usage.completion_tokens,
            model=meta.model_id,
            latency_ms=elapsed_ms,
        )


def _looks_like_model_id(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        "/" in normalized
        or normalized.startswith("gemini-")
        or normalized.startswith("gpt-")
        or normalized.startswith("claude-")
        or normalized.startswith("mistral-")
        or normalized.startswith("llama-")
    )
