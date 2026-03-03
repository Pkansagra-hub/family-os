"""
k1.memory_writer.ports.bridge_command_port -- IBridgeCommandPort protocol.

Fire-and-forget command submission to K0 via Bridge.

CRITICAL INVARIANT (MW-03):
  This is the ONLY output path from Memory Writer to K0. All K0 writes
  go through Bridge. No direct database access, no HTTP calls to K0.

CRITICAL INVARIANT (MW-09):
  Offline-safe. The adapter MUST queue envelopes locally (LocalOutbox)
  when the Bridge is unreachable, and drain on reconnection.

CRITICAL INVARIANT (MW-10):
  Every envelope submitted MUST carry a cognitive_trace_id. The adapter
  should validate this before submission.

Production adapter: BridgeCommandAdapter in adapters/bridge_command_adapter.py
Test adapter: In adapters/test_adapters.py

References:
  - MW-03 (All K0 writes via Bridge)
  - MW-09 (Offline-safe LocalOutbox)
  - MW-10 (cognitive_trace_id on all envelopes)
"""

from __future__ import annotations

from typing import Dict, List, Protocol, runtime_checkable


@runtime_checkable
class IBridgeCommandPort(Protocol):
    """
    Fire-and-forget command submission to K0 via Bridge.

    MW-03: This is the ONLY output path from MW to K0.
    MW-09: Adapter MUST queue when Bridge is offline.
    MW-10: Every envelope MUST carry cognitive_trace_id.
    """

    async def submit(
        self,
        topic: str,
        schema_uri: str,
        body: Dict,
    ) -> None:
        """
        Submit a single command envelope to K0 via Bridge.

        Args:
            topic: Routing topic (e.g. "memory.write").
            schema_uri: Schema URI for K0 validation
                (e.g. "schema://k0/topics/memory_write.body.json").
            body: The envelope body (serialized MemoryAtom).

        Raises:
            AdapterError: If submission fails after outbox queueing.
        """
        ...  # pragma: no cover

    async def submit_batch(
        self,
        envelopes: List[Dict],
    ) -> None:
        """
        Submit a batch of command envelopes to K0 via Bridge.

        Used by BatchEmitter after DeltaAggregator flushes the
        250ms aggregation window (MW-08).

        Each envelope in the list must contain:
          - topic: str
          - schema_uri: str
          - body: dict
          - trace_id: str (MW-10)

        Args:
            envelopes: List of envelope dicts ready for Bridge submission.

        Raises:
            AdapterError: If batch submission fails after outbox queueing.
        """
        ...  # pragma: no cover
