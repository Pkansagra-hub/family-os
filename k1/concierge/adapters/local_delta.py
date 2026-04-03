"""
k1.concierge.adapters.local_delta -- Production adapter for IDeltaPort.

Re-exports BusFactory from its canonical location so all production
adapters live under k1.concierge.adapters.

Usage:
    bus = BusFactory.create_local()          # Python backend
    bus = BusFactory.create_local_ordered()  # With TimingChain
"""

from __future__ import annotations

from k1.bus.factory import BusFactory

__all__ = ["BusFactory"]
