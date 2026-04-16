"""
k1.kernel.ports.bridge_port -- IBridgePort (2.0.8).

Kernel-level port for the K0 Cross-Kernel Bridge connection.

The Bridge connects K1 (edge device) to K0 (cloud). It is optional —
offline mode uses null adapters everywhere. Created in Tier 1 (S4).

Design:
  - ``connect()`` is async (network I/O to K0).
  - ``disconnect()`` is async (graceful shutdown).
  - ``is_connected()`` is sync (cached health state).
  - ``get_client()`` returns the bridge client or ``None`` for offline.

Production adapter: will wrap ``BridgeClient.connect()``
  (see ``bridge.client``).

References:
  - S4 (Bridge K0 Connection) in 08_end_to_end_wiring_requirements
  - BR-P1..P5 (Bridge port inventory) in 05_port_adapter_mapping
  - 18_bridge_audit (HttpTransport, HMAC+Ed25519 signing, health FSM)

Exports:
  IBridgePort
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IBridgePort(Protocol):
    """Kernel port for K0 Bridge connection lifecycle.

    Manages the optional K0 connection. Offline mode is normal
    operation — the kernel must function without K0.
    """

    async def connect(self) -> None:
        """Attempt to connect to K0. Silent failure = offline mode."""
        ...  # pragma: no cover

    async def disconnect(self) -> None:
        """Gracefully disconnect from K0."""
        ...  # pragma: no cover

    def is_connected(self) -> bool:
        """Check whether K0 is currently reachable."""
        ...  # pragma: no cover

    def get_client(self) -> Any | None:
        """Return the bridge client, or ``None`` if offline.

        Returns:
            A ``BridgeClient`` instance, or ``None`` if no K0
            connection was established or the connection was lost.
        """
        ...  # pragma: no cover
