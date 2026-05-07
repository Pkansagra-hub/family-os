"""k1.memory_writer.adapters.test_adapters -- Fake port implementations for testing.

In-memory implementations of all 5 MW ports. Designed for:
  - Phase 4 integration tests (E-MW-4.4)
  - Phase 5 Fabric integration tests (E-MW-5.4)
  - Unit tests that need programmable port behavior

Design goals:
  1. In-memory everything — no real I/O, no real LLM, no real Bridge
  2. Capture + assert — test code can inspect submitted envelopes, published events
  3. Configurable failures — each fake can be told to raise errors
  4. Canned responses — FakeModelHubPort returns configured extraction responses
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, FrozenSet

from k1.memory_writer.types import ChatResponse, HealthStatus, Subscription

logger = logging.getLogger(__name__)


class FakeSessionReadPort:
    """In-memory session state for testing.

    Accepts a dict of section_name -> section_data at construction.
    snapshot() returns configured sections. read_section() returns by name.
    Optionally raises on configured section names (for error testing).
    """

    def __init__(
        self,
        sections: dict[str, dict] | None = None,
        *,
        fail_on: set[str] | None = None,
    ) -> None:
        self._sections = sections or {}
        self._fail_on = fail_on or set()

    async def snapshot(self, sections: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in sections:
            data = await self.read_section(name)
            if data is not None:
                result[name] = data
        return result

    async def read_section(self, name: str) -> dict | None:
        if name in self._fail_on:
            raise RuntimeError(f"FakeSessionReadPort: configured failure for {name}")
        return self._sections.get(name)

    async def list_sections(self) -> FrozenSet[str]:
        """P5.6: Return all known section names. ISessionReadPort contract."""
        return frozenset(self._sections.keys())

    async def snapshot_all(self, exclude: FrozenSet[str] = frozenset()) -> dict[str, Any]:
        """P5.6: Return every section except those in ``exclude``.

        Honours configured ``fail_on`` so error paths can still be exercised.
        """
        result: dict[str, Any] = {}
        for name, data in self._sections.items():
            if name in exclude:
                continue
            if name in self._fail_on:
                raise RuntimeError(f"FakeSessionReadPort: configured failure for {name}")
            result[name] = data
        return result


class FakeModelHubPort:
    """Canned LLM responses for testing.

    Returns pre-configured ChatResponse. Can be set to raise
    for error-path testing.
    """

    def __init__(
        self,
        response_content: str = "[]",
        *,
        fail: bool = False,
        fail_count: int = 0,
    ) -> None:
        self._response_content = response_content
        self._fail = fail
        self._fail_count = fail_count
        self._call_count = 0
        self.calls: list[dict] = []  # capture for assertions

    async def chat(
        self,
        messages: list[dict[str, str]],
        budget_tokens: int,
        model_hint: str,
    ) -> ChatResponse:
        self._call_count += 1
        self.calls.append(
            {
                "messages": messages,
                "budget_tokens": budget_tokens,
                "model_hint": model_hint,
            }
        )

        if self._fail or (self._fail_count > 0 and self._call_count <= self._fail_count):
            raise RuntimeError("FakeModelHubPort: configured LLM failure")

        return ChatResponse(
            content=self._response_content,
            total_tokens=len(self._response_content),
            model="fake-model",
            latency_ms=10.0,
        )


class FakeBridgeCommandPort:
    """Captures Bridge submissions for test assertions.

    All submitted envelopes stored in .submitted list.
    Can be set to raise for error-path testing.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.submitted: list[dict] = []
        self.batches: list[list[dict]] = []

    async def submit(self, topic: str, schema_uri: str, body: dict) -> None:
        if self._fail:
            raise RuntimeError("FakeBridgeCommandPort: configured failure")
        self.submitted.append({"topic": topic, "schema_uri": schema_uri, "body": body})

    async def submit_batch(self, envelopes: list[dict]) -> None:
        if self._fail:
            raise RuntimeError("FakeBridgeCommandPort: configured failure")
        self.batches.append(envelopes)
        self.submitted.extend(envelopes)


class FakeEventSubscriptionPort:
    """In-memory K1 Bus for testing.

    subscribe() stores handlers. publish() dispatches to matching handlers.
    Captured events stored in .published for assertions.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}
        self._next_id: int = 0
        self._subscriptions: dict[str, str] = {}  # sub_id -> topic
        self.published: list[tuple[str, dict]] = []  # (topic, payload) capture

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> Subscription:
        self._next_id += 1
        sub_id = f"fake-sub-{self._next_id}"
        self._handlers.setdefault(topic, []).append(handler)
        self._subscriptions[sub_id] = topic
        return Subscription(subscription_id=sub_id, topic=topic)

    async def unsubscribe(self, subscription_id: str) -> None:
        self._subscriptions.pop(subscription_id, None)

    async def publish(self, topic: str, payload: dict) -> None:
        self.published.append((topic, payload))
        for handler in self._handlers.get(topic, []):
            await handler(payload)


class FakeHealthPort:
    """Configurable health port for testing."""

    def __init__(
        self,
        *,
        ready: bool = True,
        healthy: bool = True,
        circuit_open: bool = False,
    ) -> None:
        self._ready = ready
        self._healthy = healthy
        self._circuit_open = circuit_open

    async def is_ready(self) -> bool:
        return self._ready

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            is_healthy=self._healthy,
            llm_circuit_open=self._circuit_open,
            pending_batch_count=0,
            last_extraction_ms=0.0,
            detail="fake",
        )
