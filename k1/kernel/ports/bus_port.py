"""
k1.kernel.ports.bus_port -- IBusPort (2.0.8).

Kernel-level port for bus infrastructure creation and access.

The bus is the in-process pub/sub backbone shared across all components.
KernelService uses this port to create, configure, and expose the bus
and mailbox router to other components during Tier 1 bootstrap (S1).

Design:
  - ``get_bus()`` and ``get_router()`` are sync (in-process, no I/O).
  - ``create_mailbox()`` is sync (LocalMailboxRouter is in-process).
  - Middleware is applied via the bus directly, not through this port.

Production adapter: will wrap ``BusFactory.create_local()`` +
  ``LocalMailboxRouter`` (see ``k1.bus.factory``).

References:
  - S1 (Bus Infrastructure Foundation) in 08_end_to_end_wiring_requirements
  - B-1..B-3 (Bus port inventory) in 05_port_adapter_mapping
  - B-BUS-1 (sync/async schism) resolved by AsyncBusBridge (2.0.1)

Exports:
  IBusPort
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.bus.ports.bus import IBus
from k1.bus.ports.mailbox import IMailbox, IMailboxRouter, MailboxConfig


@runtime_checkable
class IBusPort(Protocol):
    """Kernel port for bus infrastructure access.

    Provides access to the shared bus, mailbox router, and mailbox
    creation for both Tier 1 (shared) and Tier 2 (per-session)
    component wiring.
    """

    def get_bus(self) -> IBus:
        """Return the shared bus instance."""
        ...  # pragma: no cover

    def get_router(self) -> IMailboxRouter:
        """Return the shared mailbox router."""
        ...  # pragma: no cover

    def create_mailbox(
        self,
        actor_id: str,
        config: MailboxConfig | None = None,
    ) -> IMailbox:
        """Register an actor mailbox and return its handle.

        Args:
            actor_id: Unique actor identifier (e.g. ``"orchestrator"``,
                ``"front_session123"``).
            config: Optional mailbox configuration (capacity, priority
                weights). Uses defaults if ``None``.

        Returns:
            A mailbox handle for the registered actor.
        """
        ...  # pragma: no cover
