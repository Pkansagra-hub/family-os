"""Kernel-level Bridge adapter — wraps bridge client for IBridgePort.

S4 adapter that satisfies ``k1.kernel.ports.bridge_port.IBridgePort``.

Provides two modes:
  - **OfflineBridgeAdapter**: Always offline (bridge_enabled=False or
    no K0 available).  ``is_connected()`` returns False, ``get_client()``
    returns None.
  - **SinkBridgeAdapter**: Wraps ``SinkBridgeClient`` + ``LocalOutbox``
    for offline command queueing.  ``is_connected()`` returns False
    (K0 not reachable), but ``get_client()`` returns a real
    ``SinkBridgeClient`` so callers can queue commands to the outbox.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class OfflineBridgeAdapter:
    """Null-object bridge satisfying kernel IBridgePort (offline mode).

    Used when ``KernelConfig.bridge_enabled`` is False.
    Everything is a no-op; no outbox, no client.
    """

    async def connect(self) -> None:
        """No-op — offline mode."""

    async def disconnect(self) -> None:
        """No-op — offline mode."""

    def is_connected(self) -> bool:
        """Always False — offline mode."""
        return False

    def get_client(self) -> Any | None:
        """Always None — offline mode."""
        return None


class SinkBridgeAdapter:
    """Offline-first bridge with command queueing via LocalOutbox.

    Satisfies kernel ``IBridgePort``.  K0 is not connected
    (``is_connected()`` returns False) but ``get_client()`` returns
    a ``SinkBridgeClient`` that queues commands to a SQLite outbox
    for deferred delivery when K0 becomes reachable.

    Parameters
    ----------
    outbox_path : str | Path
        Path to the SQLite outbox database file.
    """

    def __init__(self, outbox_path: str | Path) -> None:
        from bridge.client import create_sink_bridge_client

        self._client = create_sink_bridge_client(outbox_path)
        # Keep the outbox handle accessible for tests/observability.
        self._outbox = self._client._outbox  # noqa: SLF001 - public seam exposes outbox

    async def connect(self) -> None:
        """No-op — SinkBridgeClient is always offline."""

    async def disconnect(self) -> None:
        """No-op — SinkBridgeClient has no connection to close."""

    def is_connected(self) -> bool:
        """Always False — K0 not reachable, commands queued to outbox."""
        return False

    def get_client(self) -> Any:
        """Return the SinkBridgeClient (for command queueing)."""
        return self._client
