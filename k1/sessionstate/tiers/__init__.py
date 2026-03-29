"""
SessionState Tiers Package - HOT, WARM, LOCAL COLD
===================================================

This package contains tier managers that coordinate sections.
Each tier manages a group of sections with shared budget and behavior.

Tiers:
- hot.py       - HOT CORE tier (48KB, always in memory)
- warm.py      - WARM tier (48KB, evictable)
- local_cold.py - LOCAL COLD tier (K1 SQLite, offline-safe)

Tier Hierarchy:
    HOT CORE (48KB) - Always in memory, fast access
        ↓ demote
    WARM TIER (48KB) - In memory, evictable
        ↓ evict
    LOCAL COLD (SQLite) - Persistent archive

See: docs/plans/sessionstate-implementation-plan.md
Epic 2.4: Implement Tier Managers
"""

from .hot import HotTier
from .local_cold import LocalColdTier
from .warm import WarmTier

__all__ = [
    "HotTier",
    "WarmTier",
    "LocalColdTier",
]
