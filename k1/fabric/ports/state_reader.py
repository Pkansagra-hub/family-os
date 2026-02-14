"""
k1.fabric.ports.state_reader -- ISessionStateReader port (5.1.1).

Read-only access to SessionState for the Capability Fabric.

This is the CANONICAL definition.  Several modules previously declared
local structural subtypes (policy/ports.py, context_builder.py,
semantic_validator.py, agent_provider.py).  All are structurally
compatible with this definition.

Design:
  - Read-only (FAB-01): Fabric NEVER writes SessionState.
  - Multi-reader, lock-free: multiple concurrent readers are safe.
  - Optional port: when None is injected, consumers degrade gracefully
    (policy scores neutral, context sections empty, validation skipped).
  - SessionSnapshot: frozen point-in-time snapshot of all sections.

Consumers:
  - PolicyEngine (3.2.2, 3.2.3) -- AffectiveRouting, CognitiveLoadRouting
  - ContextBuilder (4.2.1) -- step 2 (fetch SessionState sections)
  - SemanticValidator (3.5.3) -- grounding check against beliefs
  - AgentFactory (4.3.1 step 4) -- declared read-only sections
  - HardFilter (4.1.2) -- input satisfiability from SessionState

Production adapter: SessionStateReaderAdapter (5.2.1)
Test adapter: TestSessionStateReaderAdapter (5.2.2)

References:
  - FAB-01 (Fabric never writes SessionState)
  - K1 SessionState schema sections

Exports:
  ISessionStateReader
  SessionSnapshot
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionSnapshot:
    """
    Immutable point-in-time snapshot of SessionState sections.

    IMPORTANT: This is the CANONICAL SessionSnapshot for cross-module use.
    Orchestrator (PlanRequest.context) and Planner (IStateReadPort) use THIS type.
    SessionState has its own internal SessionSnapshot (sessionstate/snapshot.py,
    sessionstate/manager.py) with 12+ diagnostic fields -- those are for
    internal monitoring only. The adapter layer maps internal -> this type.

    Returned by ``ISessionStateReader.get_snapshot()``.
    Contains all available sections at the moment of capture.

    Attributes:
        session_id: The session this snapshot belongs to.
        sections: Mapping of section name -> section data.
            Missing sections are simply absent from the dict.
        timestamp_ms: Epoch milliseconds when the snapshot was captured.
        section_names: Ordered list of section names present.
    """

    session_id: str = ""
    sections: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    timestamp_ms: int = 0
    section_names: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Auto-populate section_names from sections keys if not provided
        if not self.section_names and self.sections:
            object.__setattr__(self, "section_names", sorted(self.sections.keys()))

    def has_section(self, section: str) -> bool:
        """Check if a section is present in the snapshot."""
        return section in self.sections

    def get_section(self, section: str) -> Optional[Dict[str, Any]]:
        """Get a section, or None if not present."""
        return self.sections.get(section)


# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ISessionStateReader(Protocol):
    """
    Read-only access to SessionState sections.

    This is the canonical port interface (5.1.1).  Any object with
    matching method signatures satisfies this protocol (structural
    subtyping via ``typing.Protocol``).

    SessionState section names follow the K1 schema:
      - ``affective_now``   -- current detected emotion + intensity
      - ``cognitive``        -- cognitive load / complexity tier
      - ``control``          -- safety band, user preferences
      - ``beliefs_active``   -- active belief set
      - ``history_recent``   -- recent conversation turns
      - ``scoreboard``       -- current QUD (question under discussion)

    Thread safety:
      Implementations MUST support concurrent reads from multiple
      threads/tasks without external synchronization.

    FAB-01 enforcement:
      This port provides read-only access ONLY.  There is no write
      method.  Fabric components MUST NOT circumvent this port to
      write SessionState.
    """

    def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single named section from SessionState.

        Args:
            session_id: The session identifier.
            section: Section name (e.g. ``"affective_now"``, ``"cognitive"``).

        Returns:
            Section data as a dict, or ``None`` if the section is
            unavailable or the session does not exist.
        """
        ...  # pragma: no cover

    def read_sections(
        self,
        session_id: str,
        names: List[str],
    ) -> Dict[str, Any]:
        """
        Retrieve multiple sections in a single call.

        Batch read for efficiency when multiple sections are needed
        (e.g. ContextBuilder step 2 reads all required + optional).

        Args:
            session_id: The session identifier.
            names: List of section names to retrieve.

        Returns:
            Dict mapping section name -> section data.
            Missing sections are omitted from the result (not None-valued).
        """
        ...  # pragma: no cover

    def get_snapshot(
        self,
        session_id: str,
    ) -> SessionSnapshot:
        """
        Capture a point-in-time snapshot of all available sections.

        Used when consistency across multiple section reads is important
        (e.g. SemanticValidator needs beliefs + context atomically).

        Args:
            session_id: The session identifier.

        Returns:
            SessionSnapshot containing all available sections at capture time.
        """
        ...  # pragma: no cover
