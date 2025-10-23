"""
K1 Layer 3 Execution — dialogue/scoreboard/

PURPOSE:
========
Common ground tracking (QUD, referents) with <5ms update.
Implements Questions Under Discussion stack and entity salience tracking.

RESPONSIBILITIES:
=================
1. Questions Under Discussion (QUD): Stack discipline, priority ordering (Roberts 1996)
2. Entity Tracking: Salience (0.0-1.0), last_mentioned_turn, pronoun mapping
3. Common Ground: Shared beliefs, grounding acts (Clark & Brennan 1991)

PRIMARY ADRs:
=============
- ADR-0017b: SessionState Scoreboard Section (QUD stack, entity tracking)

RELATED ADRs:
=============
- ADR-0019: SessionState Serialization (scoreboard section)

PERFORMANCE METRICS:
====================
- Scoreboard update: <5ms P95
- Salience decay: Exponential (0.9 per turn)
- Referent resolution: <200μs

RESEARCH FOUNDATIONS:
=====================
- QUD Theory (Roberts 1996) — Questions Under Discussion
- Common Ground (Clark & Brennan 1991) — Grounding acts
- Entity salience (Grosz & Sidner 1986) — Focus tracking

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
