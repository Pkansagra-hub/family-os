"""
K1 Layer 3 Execution — dialogue/

PURPOSE:
========
Dialogue management with common ground tracking, state tracking, turn management, and repair.
Implements conversation management for multi-turn dialogue.

ARCHITECTURE:
=============
4 sub-modules implementing dialogue management:

1. scoreboard/     - Common ground tracking (QUD, referents, <5ms update)
2. state_tracker/  - Dialogue state (beliefs, slots, <5ms update)
3. turn_manager/   - Turn-taking logic, barge-in (<10ms turn transition)
4. repair/         - Conversation repair (<10ms repair decision)

PRIMARY ADRs:
=============
- ADR-0003b: Barge-In Protocol (3 states, 5 transitions)
- ADR-0003b: Clarification Protocol (4 states, 6 transitions, nested)
- ADR-0015d: Token Streaming (barge-in handling)
- ADR-0017: SessionState 6-Section Design (beliefs, scoreboard, persona)
- ADR-0017a: Beliefs Section (fact storage, confidence)
- ADR-0017b: Scoreboard Section (QUD stack, entity tracking)
- ADR-0019: SessionState Serialization (beliefs, scoreboard sections)
- ADR-0021c: Turn History Retention Compliance (GDPR Article 5(e), 365-day baseline)
- ADR-0024: Performance Budgets (barge-in <120ms P95)
- ADR-0054: Turn Boundary Management (research foundation)
- ADR-0054a: Implicit Pause (TRP 0.5-2.5s)
- ADR-0054b: Explicit Submit (send button, Enter key)

PERFORMANCE BUDGETS:
====================
- Scoreboard update: <5ms P95
- State update: <5ms P95
- Turn transition: <10ms P95
- Barge-in detection: <20ms (VAD)
- Barge-in cancellation: <120ms P95 (total pipeline)
- Repair decision: <10ms P95

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
