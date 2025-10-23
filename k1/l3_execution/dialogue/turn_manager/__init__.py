"""
K1 Layer 3 Execution — dialogue/turn_manager/

PURPOSE:
========
Turn-taking logic with barge-in (<10ms turn transition).
Manages turn boundaries and interruption handling.

RESPONSIBILITIES:
=================
1. Turn Management: Track current speaker, turn boundaries
2. Barge-In Detection: VAD-based interrupt detection (<20ms)
3. Cancellation: SIGTERM to inference, stop TTS, stop audio (<120ms P95)

PRIMARY ADRs:
=============
- ADR-0003b: Barge-In Protocol (3 states, 5 transitions)
- ADR-0015d: Token Streaming, Barge-In Handling

RELATED ADRs:
=============
- ADR-0024: Performance Budgets (barge-in <120ms)
- ADR-0054: Turn Boundary Management (research foundation)
- ADR-0054a: Implicit Pause (TRP 0.5-2.5s)
- ADR-0054b: Explicit Submit (send button, Enter key)

PERFORMANCE METRICS:
====================
- Turn transition: <10ms P95
- Barge-in detection: <20ms (VAD)
- Cancellation latency: <120ms P95 (total pipeline)

RESEARCH FOUNDATIONS:
=====================
- Turn-taking (Sacks et al. 1974) — TRP transition relevance places
- Barge-in (Raux & Eskenazi 2009) — Incremental speech processing

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
