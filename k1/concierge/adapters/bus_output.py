"""
k1.concierge.adapters.bus_output -- Production adapter for IOutputPort.

Wraps IBus.publish(): forwards response envelopes to the bus for
SSE/transport consumption.
"""

from __future__ import annotations

import logging

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus

logger = logging.getLogger(__name__)


class BusOutputAdapter:
    """Production adapter for IOutputPort — publishes responses to bus.

    Thin wrapper: takes an Envelope (already built via build_final_response
    or build_response_stream) and publishes it to the bus.
    """

    def __init__(self, bus: IBus) -> None:
        self._bus = bus

    async def send(self, envelope: Envelope) -> None:
        self._bus.publish(envelope)
