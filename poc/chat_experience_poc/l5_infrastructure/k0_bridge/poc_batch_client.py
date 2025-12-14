"""
PoC BatchClient - Mock for writer testing

In production, this would be the real BatchClient with:
- Bounded batching (250ms/64KB/100 deltas)
- HTTP communication with K0
- Circuit breaker, retry logic, health checks

For PoC, this directly forwards to MockCommandPort.
"""

from typing import Any, Dict


class PoCBatchClient:
    """
    PoC BatchClient - Mock that forwards to MockCommandPort.

    Real BatchClient: Batches deltas, communicates with K0 over HTTP
    PoC BatchClient: Direct passthrough to MockCommandPort
    """

    def __init__(self, mock_command_port):
        """Initialize with mock command port."""
        self.mock_command_port = mock_command_port
        self.deltas_added = 0

    async def add_delta(self, delta: Dict[str, Any]) -> bool:
        """
        Add delta to batch (PoC: immediately send to MockCommandPort).

        Args:
            delta: Delta from writer

        Returns:
            True if successful
        """
        self.deltas_added += 1

        # In PoC, send directly to mock command port
        # In production, batch and flush periodically
        try:
            result = await self.mock_command_port.receive_batch(
                batch_id=f"poc_batch_{self.deltas_added}",
                delta_type=delta.delta_type,
                deltas=[
                    {
                        "delta_id": delta.delta_id,
                        "delta_type": delta.delta_type,
                        "content": delta.content,
                        "timestamp": delta.timestamp,
                    }
                ],
                trace_id=delta.trace_id,
            )
            return result
        except Exception:
            return False

    async def flush(self) -> bool:
        """Flush all batches (PoC: no-op)."""
        return True

    async def start(self):
        """Start client (PoC: no-op)."""
        pass

    async def stop(self):
        """Stop client (PoC: no-op)."""
        pass
