"""
K1 Layer 3 Execution — dialogue/state_tracker/

PURPOSE:
========
Dialogue state (beliefs, slots) with <5ms update.
Tracks user beliefs, intent history, and slot filling.

RESPONSIBILITIES:
=================
1. Dialogue State: Track user beliefs, intent history, slot filling
2. Slot Tracking: Extract values for structured tasks (flight booking, calendar event)
3. Belief Updates: Confidence scores, temporal decay, source tracking

PRIMARY ADRs:
=============
- ADR-0017: SessionState 6-Section Design (beliefs section)
- ADR-0017a: Beliefs Section (fact storage, confidence)

RELATED ADRs:
=============
- ADR-0019: SessionState Serialization (beliefs section)

PERFORMANCE METRICS:
====================
- State update: <5ms P95
- Slot filling accuracy: >90%

RESEARCH FOUNDATIONS:
=====================
- Dialogue State Tracking (Williams et al. 2013) — DST benchmarks
- Belief tracking (Henderson et al. 2014) — Multi-domain tracking

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
