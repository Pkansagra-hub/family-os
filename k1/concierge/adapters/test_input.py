"""
k1.concierge.adapters.test_input -- Test adapter for IInputPort.

Injects Envelopes into the system via an async queue.
No bus, no transport -- pure in-memory for unit tests.
"""

from __future__ import annotations

import asyncio

from k1.bus.envelope import Envelope
from k1.concierge.bus.builders import build_user_input


class TestInputAdapter:
    """Test adapter for IInputPort — injects Envelopes via async queue."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Envelope] = asyncio.Queue()

    async def receive(self) -> Envelope:
        return await self._queue.get()

    def has_buffered(self) -> bool:
        return not self._queue.empty()

    # -- Test helpers ----------------------------------------------------------

    def inject(self, envelope: Envelope) -> None:
        """Push a pre-built envelope into the queue."""
        self._queue.put_nowait(envelope)

    def inject_text(self, text: str, session_id: str = "test") -> None:
        """Build and push a user-input envelope from plain text."""
        env = build_user_input({"text": text, "device_id": "test", "session_id": session_id})
        self._queue.put_nowait(env)
