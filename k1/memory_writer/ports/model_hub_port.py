"""
k1.memory_writer.ports.model_hub_port -- IModelHubPort protocol.

LLM extraction call interface for Memory Writer v2.

CRITICAL INVARIANT (MW-06):
  LLM budget is 2000 tokens (input + output combined). The WriterAgent
  must pass budget_tokens=2000 on every call.

CRITICAL INVARIANT (MW-07):
  The RelevanceFilter MUST NOT depend on this port. Filter is rule-based
  only. This port is used exclusively by the extraction stage.

Circuit breaker protected:
  - failure_threshold: 3 failures per minute
  - recovery_probe: 30 seconds
  - model_hint: "cheapest" (Model Hub routes to cheapest capable model)

Production adapter: ModelHubAdapter in adapters/model_hub_adapter.py
Test adapter: In adapters/test_adapters.py

References:
  - MW-06 (LLM budget 2000 tokens)
  - MW-07 (Filter has no LLM dependency)
  - Epic 1.14 (WriterAgent + ExtractionValidator)
"""

from __future__ import annotations

from typing import Dict, List, Protocol, runtime_checkable

from k1.memory_writer.types import ChatResponse


@runtime_checkable
class IModelHubPort(Protocol):
    """
    LLM extraction call interface.

    MW-06: Budget is always 2000 tokens.
    MW-07: NEVER used by RelevanceFilter.

    Circuit breaker protected: adapter opens circuit after 3 failures/min,
    probes recovery after 30s.
    """

    async def chat(
        self,
        messages: List[Dict[str, str]],
        budget_tokens: int,
        model_hint: str,
    ) -> ChatResponse:
        """
        Send a chat completion request to Model Hub for memory extraction.

        Args:
            messages: List of message dicts with "role" and "content" keys.
                Typically: [{"role": "system", "content": persona},
                            {"role": "user", "content": serialized_context}]
            budget_tokens: Maximum tokens for input + output combined.
                MW-06: Always 2000 for MW extraction.
            model_hint: Routing hint for Model Hub.
                Default "cheapest" -- routes to cheapest capable model.

        Returns:
            ChatResponse with content (extracted JSON), token usage, latency.

        Raises:
            AdapterError: If LLM call fails or circuit breaker is open.
        """
        ...  # pragma: no cover
