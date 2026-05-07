"""
k1.memory_writer.batch.batch_emitter -- Flush batched envelopes to Bridge.

One submit_batch() call per flush — not one call per envelope.
Fire-and-forget: Bridge handles signing, idem_key, offline queuing.

MW-03: This is the ONLY output path to K0.
MW-09: Adapter queues locally when Bridge is offline.
"""

from __future__ import annotations

import logging

from k1.memory_writer.ports.bridge_command_port import IBridgeCommandPort

log = logging.getLogger(__name__)


class BatchEmitter:
    """Flush batched envelopes to Bridge via IBridgeCommandPort.

    One submit_batch() call per flush — not one call per envelope.
    Fire-and-forget: Bridge handles signing, idem_key, offline queuing.

    MW-03: This is the ONLY output path to K0.
    MW-09: Adapter queues locally when Bridge is offline.
    """

    def __init__(self, bridge_port: IBridgeCommandPort) -> None:
        self._bridge_port = bridge_port

    async def emit(self, batch: list[dict]) -> int:
        """Submit all envelopes in the batch to Bridge.

        Args:
            batch: List of envelope dicts from DeltaAggregator.flush().

        Returns:
            Number of envelopes submitted. 0 if batch is empty.

        Raises:
            Nothing — errors are caught and logged. Best-effort.
            If Bridge is offline, adapter queues via LocalOutbox (MW-09).
        """
        if not batch:
            return 0

        try:
            await self._bridge_port.submit_batch(batch)
            return len(batch)
        except Exception as exc:
            log.warning(
                "MW: Bridge submit_batch failed",
                extra={
                    "batch_size": len(batch),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            return 0
