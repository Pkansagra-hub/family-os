"""
k1.concierge.adapters.bus_input -- Production adapter for IInputPort.

Wraps IBus subscription: subscribes to TOPIC_USER_INPUT and buffers
incoming envelopes in an async queue for the FSM to consume.
"""

from __future__ import annotations

import asyncio
import logging

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus
from k1.concierge.bus.topics import TOPIC_USER_INPUT

logger = logging.getLogger(__name__)


class BusInputAdapter:
    """Production adapter for IInputPort — receives user input from bus.

    Subscribes to TOPIC_USER_INPUT on the bus and buffers envelopes.
    FSM (or any consumer) calls receive() to pull the next input.
    """

    def __init__(self, bus: IBus) -> None:
        self._bus = bus
        self._queue: asyncio.Queue[Envelope] = asyncio.Queue()
        self._handle = bus.subscribe(TOPIC_USER_INPUT, self._on_input)

    def _on_input(self, envelope: Envelope) -> None:
        """Bus handler — buffer incoming envelope."""
        self._queue.put_nowait(envelope)

    async def receive(self) -> Envelope:
        return await self._queue.get()

    def has_buffered(self) -> bool:
        return not self._queue.empty()

    def close(self) -> None:
        """Unsubscribe from the bus. Call on shutdown."""
        if self._handle is not None:
            self._bus.unsubscribe(self._handle)
            self._handle = None
