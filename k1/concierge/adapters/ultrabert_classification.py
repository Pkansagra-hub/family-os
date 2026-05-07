"""
k1.concierge.adapters.ultrabert_classification -- Production adapter for IClassificationPort.

Re-exports UltraBERTPhase1Pipeline from its canonical location so all
production adapters live under k1.concierge.adapters.
"""

from __future__ import annotations

from k1.concierge.fsm.ultrabert_phase1 import UltraBERTPhase1Pipeline

__all__ = ["UltraBERTPhase1Pipeline"]
