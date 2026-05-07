"""SessionStateReadAdapter -- read-only SessionState access [F32].

MH-01: NEVER writes SessionState.
Lock-free multi-reader access to persona (model preference) and control (user_band).
Error: return empty snapshot on failure (DEGRADED, use default model pref).

Import graph (Layer 3 -- adapter)
---------------------------------
k1.model_hub.adapters.session_state_read_adapter
  -> k1.model_hub.ports      (Layer 1)
  -> stdlib only
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from k1.model_hub.ports.state_read_port import StateSnapshot

logger = logging.getLogger(__name__)


class SessionStateReadAdapter:
    """IStateReadPort adapter binding to K1 SessionState.

    Production: reads from K1 SessionState store.
    Current: in-memory dict for single-process operation.

    MH-01: This adapter has NO write methods.
    Error handling: return empty snapshot on failure, never crash hub.
    """

    def __init__(self, state_source: Dict[str, Any] | None = None) -> None:
        self._state: Dict[str, Any] = state_source or {}

    async def read(self, sections: List[str]) -> StateSnapshot:
        """Read requested sections from SessionState.

        Returns empty snapshot on error (degraded operation).
        """
        try:
            data = {s: self._state[s] for s in sections if s in self._state}
            return StateSnapshot(sections=data)
        except Exception:
            logger.exception("SessionStateReadAdapter.read failed")
            return StateSnapshot(sections={})


__all__ = ["SessionStateReadAdapter"]
