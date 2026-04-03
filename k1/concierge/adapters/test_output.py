"""
k1.concierge.adapters.test_output -- Test adapter for IOutputPort.

Captures all emitted Envelopes in a list for assertion.
No bus, no SSE -- pure in-memory for unit tests.
"""

from __future__ import annotations

from k1.bus.envelope import Envelope


class TestOutputAdapter:
    """Test adapter for IOutputPort — captures emitted Envelopes."""

    def __init__(self) -> None:
        self.sent: list[Envelope] = []

    async def send(self, envelope: Envelope) -> None:
        self.sent.append(envelope)

    # -- Test helpers ----------------------------------------------------------

    def get_sent(self, topic: str | None = None) -> list[Envelope]:
        """Return sent envelopes, optionally filtered by topic."""
        if topic is None:
            return list(self.sent)
        return [e for e in self.sent if e.topic == topic]

    def last(self) -> Envelope | None:
        """Return most recently sent envelope, or None."""
        return self.sent[-1] if self.sent else None

    def clear(self) -> None:
        """Reset captured envelopes."""
        self.sent.clear()
