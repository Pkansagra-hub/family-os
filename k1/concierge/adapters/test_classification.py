"""
k1.concierge.adapters.test_classification -- Test adapter for IClassificationPort.

Re-exports StubPhase1Pipeline from its canonical location so all test
adapters live under k1.concierge.adapters.
"""

from __future__ import annotations

from k1.concierge.fsm.phase1 import StubPhase1Pipeline

__all__ = ["StubPhase1Pipeline"]
