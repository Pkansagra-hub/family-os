"""IStateReadPort -- read-only SessionState access [F12].

MH-01: NEVER writes SessionState. Read-only access for model selection context.
NO write/update/set/delete methods exist on this port.

Import graph (Layer 1)
----------------------
k1.model_hub.ports.state_read_port
  -> stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol, runtime_checkable


@dataclass(frozen=True)
class StateSnapshot:
    """Read-only snapshot of requested SessionState sections."""

    sections: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class IStateReadPort(Protocol):
    """Read-only SessionState access (MH-01).

    Sections: persona (model preference), control (user_band).
    Multi-reader, lock-free.

    INVARIANT MH-01: This port has NO write methods.
    """

    async def read(self, sections: List[str]) -> StateSnapshot:
        """Read requested sections from SessionState."""
        ...


__all__ = ["IStateReadPort", "StateSnapshot"]
