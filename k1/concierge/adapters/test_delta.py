"""
k1.concierge.adapters.test_delta -- Test adapter for IDeltaPort.

Creates a local in-process bus via BusFactory for test use.
All test adapters live under k1.concierge.adapters.
"""

from __future__ import annotations

from k1.bus.factory import BusFactory


def create_test_bus():
    """Create a local in-process bus for testing (satisfies IDeltaPort / IBus)."""
    return BusFactory.create_local()


__all__ = ["create_test_bus"]
