"""
k1.kernel.ports.session_manager_port -- ISessionManagerPort (2.0.8).

Kernel-level port for per-session resource lifecycle (CRUD).

Each user session gets its own set of Tier 2 components: SSM, per-session
Fabric, Concierge, mailboxes, tool dispatchers, etc. This port abstracts
the creation, lookup, and destruction of per-session component bags
(``SessionInstance``).

Design:
  - ``create_session()`` is async (SSM, Fabric, Concierge are async init).
  - ``destroy_session()`` is async (reverse teardown order P7→P1).
  - ``get_session()`` is sync (dict lookup).
  - ``list_sessions()`` is sync (dict keys).

References:
  - P1..P7 (Tier 2 Per-Session Components) in
    08_end_to_end_wiring_requirements
  - Issue 2.0.9 (converge KernelRuntime + ConciergeRuntime)
  - Issue 2.0.10 (ADR: shared vs per-session resource map)

Exports:
  ISessionManagerPort
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ISessionManagerPort(Protocol):
    """Kernel port for per-session component lifecycle.

    Manages the full lifecycle of per-session component bags:
    creation (P1-P7), lookup, and destruction (reverse order).
    """

    async def create_session(
        self,
        session_id: str,
        device_id: str | None = None,
    ) -> Any:
        """Create a new session with all Tier 2 components.

        Executes phases P1 (bus) through P7 (register) in order.

        Args:
            session_id: Unique session identifier.
            device_id: Optional device/member identifier for
                household projection.

        Returns:
            A ``SessionInstance`` containing all per-session components.
        """
        ...  # pragma: no cover

    async def destroy_session(self, session_id: str) -> None:
        """Destroy a session, releasing all Tier 2 resources.

        Executes teardown in reverse order: P7 → P1.

        Args:
            session_id: The session to destroy.

        Raises:
            KeyError: If ``session_id`` is not found.
        """
        ...  # pragma: no cover

    def get_session(self, session_id: str) -> Any | None:
        """Look up a session by ID.

        Args:
            session_id: The session to find.

        Returns:
            The ``SessionInstance``, or ``None`` if not found.
        """
        ...  # pragma: no cover

    def list_sessions(self) -> list[str]:
        """Return all active session IDs."""
        ...  # pragma: no cover
