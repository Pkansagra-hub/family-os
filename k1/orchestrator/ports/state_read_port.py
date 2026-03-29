"""
k1.orchestrator.ports.state_read_port -- IStateReadPort port (1.4.4).

Read-only async access to SessionState for the Orchestrator.

Design:
  - All methods ASYNC (SessionState may involve I/O).
  - Aligns with Fabric's ISessionStateReader (k1/fabric/ports/state_reader.py)
    which is the established read-only interface to SessionState. Uses same
    method signatures for consistency across K1 modules.
  - Reuses SessionSnapshot from k1.fabric.ports.state_reader.

CRITICAL INVARIANT (ORCH-01):
  NO write methods. This port is intentionally read-only. If any
  implementor adds a write method, it violates the Orchestrator's
  core identity. The Orchestrator NEVER writes SessionState.

Consumers:
  - OrchestratorService.dispatch_high() (2.1.4) -- initial snapshot
  - OrchestratorService.receive_plan() (2.1.4) -- re-snapshot (RACE-1)
  - OrchestratorService.dispatch_medium() (2.1.3) -- safety band read
  - DAGExecutor.execute_wave() (2.2.2) -- safety band re-read

Production adapter: StateReadAdapter (6.1.4) in adapters/state_read_adapter.py
Test adapter: MockStateReadAdapter (6.1.11) in adapters/mock_state_read_adapter.py

References:
  - ORCH-001 (Orchestrator never writes SessionState)
  - k1/fabric/ports/state_reader.py (ISessionStateReader pattern)

Exports:
  IStateReadPort
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k1.fabric.ports.state_reader import SessionSnapshot

# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IStateReadPort(Protocol):
    """
    Read-only async access to SessionState sections.

    This port mirrors Fabric's ISessionStateReader but with async
    methods (SessionState access may involve I/O in production).

    ORCH-01: This port provides read-only access ONLY. There are
    NO write methods. The Orchestrator MUST NOT circumvent this
    port to write SessionState.

    SessionState section names follow the K1 schema:
      - ``beliefs``        -- active belief set
      - ``persona``        -- user persona / preferences
      - ``control``        -- safety band, system control state
      - ``scoreboard``     -- current QUD (question under discussion)

    Thread safety:
      Implementations MUST support concurrent reads from multiple
      asyncio tasks without external synchronization.

    Performance:
      get_snapshot() should be cheap (in-memory read from
      SessionState's latest committed state). Do not trigger
      reconstruction or hydration.
    """

    async def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single named section from SessionState.

        Args:
            session_id: The session identifier.
            section: Section name (e.g. ``"control"``, ``"beliefs"``).

        Returns:
            Section data as a dict, or ``None`` if the section is
            unavailable or the session does not exist.

        Raises:
            AdapterError: With severity DEGRADED if SessionState
                is unreachable.
        """
        ...  # pragma: no cover

    async def read_sections(
        self,
        session_id: str,
        names: List[str],
    ) -> Dict[str, Any]:
        """
        Retrieve multiple sections in a single call.

        Args:
            session_id: The session identifier.
            names: List of section names to retrieve.

        Returns:
            Dict mapping section name -> section data.
            Missing sections are omitted from the result.

        Raises:
            AdapterError: With severity DEGRADED if SessionState
                is unreachable.
        """
        ...  # pragma: no cover

    async def get_snapshot(
        self,
        session_id: str,
    ) -> SessionSnapshot:
        """
        Capture a point-in-time snapshot of all available sections.

        Used when consistency across multiple section reads is needed
        (e.g. receive_plan re-snapshot for RACE-1 freshness).

        Args:
            session_id: The session identifier.

        Returns:
            SessionSnapshot containing all available sections.
            If session_id is not found, returns an empty snapshot.

        Raises:
            AdapterError: With severity DEGRADED if SessionState
                is unreachable.
        """
        ...  # pragma: no cover
