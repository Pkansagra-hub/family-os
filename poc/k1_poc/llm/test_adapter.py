"""
TestConciergeAdapter -- Deterministic Test Adapter
===================================================

V2 Design Ref: Section 10.10 (TestConciergeAdapter, scripted responses)

No real LLM calls. Keyed by (actor, scenario) so each test can
configure exact responses. Records all calls for test assertions.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from poc.k1_poc.llm.types import (
    ConciergeModelRequest,
    ConciergeModelResponse,
    FinishReason,
    StreamChunk,
)

logger = logging.getLogger(__name__)


class TestConciergeAdapter:
    """Deterministic test adapter. No real LLM calls.

    Keyed by (actor, scenario) so each test can configure
    exact responses for Front user_input, Back task_dispatch, etc.
    Records all calls for test assertions.

    Usage:
        adapter = TestConciergeAdapter()
        adapter.set_response("front", "user_input", ConciergeModelResponse(
            text="",
            tool_calls=[
                ToolCallResult(id="c1", name="update_beliefs", arguments={"beliefs": [{"subject": "user", "predicate": "said", "object": "greeting", "confidence": 0.9}]}),
            ],
            finish_reason=FinishReason.TOOL_CALLS,
        ))
        response = await adapter.generate(request)
        assert adapter.call_count == 1
    """

    def __init__(self):
        self.responses: dict[tuple[str, str], ConciergeModelResponse] = {}
        self.calls: list[ConciergeModelRequest] = []
        self._sequence_responses: dict[tuple[str, str], list[ConciergeModelResponse]] = {}
        self._sequence_counters: dict[tuple[str, str], int] = {}

        # Default fallback
        self._default_response = ConciergeModelResponse(
            text="OK",
            finish_reason=FinishReason.STOP,
            model_id="test-model",
        )
        logger.info("TestConciergeAdapter initialised")

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_response(
        self,
        actor: str,
        scenario: str,
        response: ConciergeModelResponse,
    ) -> None:
        """Set a fixed response for (actor, scenario) pair."""
        self.responses[(actor, scenario)] = response

    def set_response_sequence(
        self,
        actor: str,
        scenario: str,
        responses: list[ConciergeModelResponse],
    ) -> None:
        """Set a sequence of responses for (actor, scenario).

        Each call returns the next response in sequence.
        After exhausting the sequence, the last response repeats.
        """
        self._sequence_responses[(actor, scenario)] = responses
        self._sequence_counters[(actor, scenario)] = 0

    def set_default_response(self, response: ConciergeModelResponse) -> None:
        """Set fallback response when no (actor, scenario) match."""
        self._default_response = response

    # ------------------------------------------------------------------
    # IConciergeModelPort: generate
    # ------------------------------------------------------------------

    async def generate(self, request: ConciergeModelRequest) -> ConciergeModelResponse:
        """Return configured response. Records the call."""
        self.calls.append(request)
        key = (request.actor, request.scenario)
        logger.debug(
            "TestConciergeAdapter.generate  actor=%s scenario=%s key=%s",
            request.actor,
            request.scenario,
            key,
        )

        # Check sequence first
        if key in self._sequence_responses:
            seq = self._sequence_responses[key]
            idx = self._sequence_counters[key]
            response = seq[min(idx, len(seq) - 1)]
            self._sequence_counters[key] = idx + 1
            return response

        # Check fixed response
        if key in self.responses:
            return self.responses[key]

        return self._default_response

    # ------------------------------------------------------------------
    # IConciergeModelPort: generate_stream
    # ------------------------------------------------------------------

    async def generate_stream(self, request: ConciergeModelRequest) -> AsyncIterator[StreamChunk]:
        """Streaming stub. Yields text deltas from response, then done."""
        response = await self.generate(request)

        # Yield text as deltas (simulate streaming)
        if response.text:
            # Split into word-level chunks for realistic simulation
            words = response.text.split(" ")
            for i, word in enumerate(words):
                chunk_text = word if i == len(words) - 1 else word + " "
                yield StreamChunk(chunk_type="text_delta", text=chunk_text)

        # Yield tool calls
        for tc in response.tool_calls:
            yield StreamChunk(chunk_type="tool_call_delta", tool_call_partial=tc)

        # Final done
        yield StreamChunk(chunk_type="done", response=response)

    # ------------------------------------------------------------------
    # Assertion helpers
    # ------------------------------------------------------------------

    @property
    def call_count(self) -> int:
        """Total number of generate() calls made."""
        return len(self.calls)

    @property
    def last_call(self) -> ConciergeModelRequest | None:
        """The most recent request, or None."""
        return self.calls[-1] if self.calls else None

    def calls_for(self, actor: str, scenario: str) -> list[ConciergeModelRequest]:
        """All calls matching (actor, scenario)."""
        return [c for c in self.calls if c.actor == actor and c.scenario == scenario]

    def calls_for_actor(self, actor: str) -> list[ConciergeModelRequest]:
        """All calls for a given actor."""
        return [c for c in self.calls if c.actor == actor]

    def assert_called(self, actor: str, scenario: str) -> None:
        """Assert at least one call for (actor, scenario)."""
        matches = self.calls_for(actor, scenario)
        if not matches:
            available = [(c.actor, c.scenario) for c in self.calls]
            raise AssertionError(
                f"Expected call for ({actor!r}, {scenario!r}), " f"but only got: {available}"
            )

    def assert_not_called(self, actor: str, scenario: str) -> None:
        """Assert no calls for (actor, scenario)."""
        matches = self.calls_for(actor, scenario)
        if matches:
            raise AssertionError(
                f"Expected no calls for ({actor!r}, {scenario!r}), " f"but got {len(matches)}"
            )

    def assert_tool_called(self, tool_name: str) -> None:
        """Assert that at least one request included the named tool."""
        for call in self.calls:
            if call.tools:
                for t in call.tools:
                    if t.name == tool_name:
                        return
        raise AssertionError(f"Tool {tool_name!r} never included in any request")

    def reset(self) -> None:
        """Clear all recorded calls and configured responses."""
        self.calls.clear()
        self.responses.clear()
        self._sequence_responses.clear()
        self._sequence_counters.clear()
