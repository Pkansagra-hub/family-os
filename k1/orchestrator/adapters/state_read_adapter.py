"""
k1.orchestrator.adapters.state_read_adapter -- StateReadAdapter (6.1.4).

Production adapter for IStateReadPort.

Design:
  - Thin pass-through wrapping Fabric's ``ISessionStateReader``.
  - Exists as a named boundary for error translation (AdapterException).
  - MUST NOT expose any write method (ORCH-01 invariant).
  - All methods are async (IStateReadPort contract), wrapping the
    sync ``ISessionStateReader`` methods.

Error Mapping:
  - SessionState read failure -> AdapterException(DEGRADED, "stale context")
  - ErrorRouter returns empty_snapshot fallback.

References:
  - Issue 6.1.4 in orchestrator-implementation-plan.md
  - ORCH-001 (Orchestrator never writes SessionState)
  - k1/fabric/ports/state_reader.py (ISessionStateReader)

Exports:
  StateReadAdapter
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from k1.fabric.ports.state_reader import ISessionStateReader, SessionSnapshot
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import AdapterError, ErrorSeverity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 6.1.4 -- StateReadAdapter
# ---------------------------------------------------------------------------


class StateReadAdapter:
    """
    Production IStateReadPort adapter wrapping Fabric's ISessionStateReader.

    Pure pass-through with error translation.  All read methods delegate
    to the underlying ``ISessionStateReader`` and wrap failures as
    ``AdapterException(DEGRADED)``.

    ORCH-01 enforced: this class exposes NO write methods.

    Constructor Args:
        state_reader: Fabric's ``ISessionStateReader`` implementation
            (injected by OrchestratorFactory).

    Thread Safety:
        Safe for concurrent reads.  ``ISessionStateReader`` is
        multi-reader lock-free (copy-on-write snapshots).
    """

    __slots__ = ("_reader",)

    def __init__(self, state_reader: ISessionStateReader) -> None:
        self._reader = state_reader

    # ==================================================================
    # IStateReadPort implementation
    # ==================================================================

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
            Section data as a dict, or ``None`` if unavailable.

        Raises:
            AdapterException: DEGRADED if SessionState is unreachable.
        """
        try:
            return self._reader.read_section(session_id, section)
        except Exception as exc:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="state_read",
                    operation="read_section",
                    error_code="STATE_READ_ERROR",
                    error_message=f"read_section failed: {exc}",
                    original_exception=exc,
                )
            ) from exc

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
            Missing sections are omitted.

        Raises:
            AdapterException: DEGRADED if SessionState is unreachable.
        """
        try:
            return self._reader.read_sections(session_id, names)
        except Exception as exc:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="state_read",
                    operation="read_sections",
                    error_code="STATE_READ_ERROR",
                    error_message=f"read_sections failed: {exc}",
                    original_exception=exc,
                )
            ) from exc

    async def get_snapshot(
        self,
        session_id: str,
    ) -> SessionSnapshot:
        """
        Capture a point-in-time snapshot of all available sections.

        Args:
            session_id: The session identifier.

        Returns:
            SessionSnapshot containing all available sections.

        Raises:
            AdapterException: DEGRADED if SessionState is unreachable.
        """
        try:
            return self._reader.get_snapshot(session_id)
        except Exception as exc:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="state_read",
                    operation="get_snapshot",
                    error_code="STATE_READ_ERROR",
                    error_message=f"get_snapshot failed: {exc}",
                    original_exception=exc,
                )
            ) from exc
