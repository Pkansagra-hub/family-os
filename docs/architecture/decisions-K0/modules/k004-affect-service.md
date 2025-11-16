---
adr_number: 'K004'
affected_modules: ['M04']
title: Affect Service Architecture - Emotional Classification System
status: PROPOSED
date_created: '2025-11-16'
---

# K004: Affect Service Architecture

**Status**: PROPOSED | **Module**: M04

## Context

AffectService classifies emotional valence, arousal, and affect bands for episodic memory enrichment.

## Current Capabilities

- Text-based affect classification (<70ms P95)
- Valence scoring (-1.0 to +1.0)
- Arousal scoring (0.0 to 1.0)
- Affect band classification (NEUTRAL/POSITIVE/NEGATIVE/MIXED)
- Tier-0 fast-path model (lightweight)

## Future Capabilities

- Multi-modal affect (images, audio, video, biometrics)
- Personalized affect models (learn per-user baselines)
- Affect learning loop (feedback from user corrections)
- Cultural affect adaptation
- Temporal affect patterns (mood tracking over time)

## Sub-ADRs

- [K004.1: Tier-0 Fast Affect](k004.1-tier0-fast-affect.md)
- [K004.2: Multi-Modal Affect](k004.2-multimodal-affect.md)
- [K004.3: Affect Learning Loop](k004.3-affect-learning-loop.md)

## Performance Budget

- P95: ≤70ms | P99: ≤100ms | Memory: <20MB

---
**Last Updated**: 2025-11-16
