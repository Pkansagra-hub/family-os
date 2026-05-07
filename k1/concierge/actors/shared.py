"""
k1.concierge.actors.shared -- Shared Actor Utility Functions
============================================================

Extracted from front.py and back.py (M3 E3.5) to eliminate duplication.

Source: Duplication Inventory D1, D2, D3.

Exports:
  - parse_envelope_payload: Safely parse JSON bytes from Envelope (D1)
  - safe_get_section: Safely read a SessionState section (D2)
  - never_cancel: Async no-op cancellation check (D3)

Design constraint: This module must remain dependency-minimal.
Only imports: json, typing, k1.bus.envelope.
No imports from actors.front, actors.back, config, or bus.builders.
"""

from __future__ import annotations

import json
from typing import Any

from k1.bus.envelope import Envelope

# =========================================================================
# D1: parse_envelope_payload (was _parse_payload in front.py / back.py)
# =========================================================================


def parse_envelope_payload(envelope: Envelope) -> dict[str, Any]:
    """Safely parse JSON bytes payload from Envelope.

    Returns empty dict if payload is empty or invalid JSON.
    """
    if not envelope.payload:
        return {}
    try:
        return json.loads(envelope.payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


# =========================================================================
# D2: safe_get_section (was _safe_get_section in front.py / back.py)
# =========================================================================


def safe_get_section(ss: Any, name: str) -> Any:
    """Get a section from SessionStateManager, returning None on error."""
    try:
        return ss.get_section(name)
    except Exception:
        return None


# =========================================================================
# D3: never_cancel (was _never_cancel in front.py / back.py)
# =========================================================================


async def never_cancel() -> bool:
    """Always returns False -- no cancellation requested."""
    return False
