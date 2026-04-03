"""
k1.concierge.adapters.ssm_state -- Production adapter for IStatePort.

Wraps the real SessionStateManager (created via SessionStateFactory).
Delegates get_section/get_snapshot to the SSM instance.
"""

from __future__ import annotations

from typing import Any


class SSMStateAdapter:
    """Production adapter for IStatePort — wraps SessionStateManager.

    The SSM is duck-typed as `Any` throughout Concierge. This adapter
    formalises the read surface into the IStatePort Protocol.

    Write path is NOT included — writes go through ctx.writer_port
    (MutationRequest-based), which is a separate concern.
    """

    def __init__(self, session_state: Any) -> None:
        self._ss = session_state

    def get_section(self, name: str) -> Any:
        return self._ss.get_section(name)

    def get_snapshot(self) -> dict[str, Any]:
        """Build a snapshot dict of all sections.

        Attempts to_dict() on each section (standard SSM pattern),
        falls back to raw section object.
        """
        snapshot: dict[str, Any] = {}
        # SSM sections are accessed by name — iterate known sections
        if hasattr(self._ss, "sections"):
            for name, section in self._ss.sections.items():
                snapshot[name] = section.to_dict() if hasattr(section, "to_dict") else section
        elif hasattr(self._ss, "_sections"):
            for name, section in self._ss._sections.items():
                snapshot[name] = section.to_dict() if hasattr(section, "to_dict") else section
        return snapshot
