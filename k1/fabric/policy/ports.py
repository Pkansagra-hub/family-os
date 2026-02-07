"""
k1.fabric.policy.ports -- Port protocols for Policy Engine subsystem.

Defines the minimal interfaces (Protocols) that external systems must
satisfy to integrate with the Policy Engine.  These are structural
subtypes -- any object with matching methods will work.

Ports defined:
  ISessionStateReader -- Read sections from SessionState (5.1.1)

References:
  - Epic 3.2 wiring: AffectiveRouting + CognitiveLoadRouting depend on
    ISessionStateReader for SessionState reads.
  - Epic 5.1.1 provides the concrete implementation.

Exports:
  ISessionStateReader
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class ISessionStateReader(Protocol):
    """
    Read-only access to SessionState sections.

    Concrete implementation lives in Epic 5.1.1.  Policy Engine
    dimensions (3.2.2 AffectiveRouting, 3.2.3 CognitiveLoadRouting)
    accept this as an optional port.  When ``None`` is injected, each
    dimension gracefully degrades to a neutral score.

    Section names follow the K1 SessionState schema:
      - "affective_now"  -- current detected emotion + intensity
      - "cognitive"       -- cognitive load / complexity tier
      - "control"         -- safety band, user preferences
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
            section: Section name (e.g. "affective_now", "cognitive").

        Returns:
            Section data as a dict, or ``None`` if the section is
            unavailable or the session does not exist.
        """
        ...
