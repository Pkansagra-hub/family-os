---
adr_number: 'K006'
affected_modules: ['M06']
title: Salience Scoring Architecture - Attention and Priority
status: PROPOSED
date_created: '2025-11-16'
---

# K006: Salience Scoring Architecture

**Status**: PROPOSED | **Module**: M06

## Context

SalienceScorer computes attention priority for memory events.

## Current Capabilities (Write-Path)

- Formula: 0.50×social_importance + 0.40×affect_intensity + 0.10×recency_score
- Social importance from participant roles (partner > parent > friend)
- Affect intensity from valence + arousal magnitude
- Recency boost for recent events

## Future Capabilities

- Read-path salience (query-time reranking based on user context)
- Learned attention networks (train on user interaction patterns)
- Multi-factor salience (novelty, relevance, emotional significance)
- Temporal decay models (older memories fade unless reinforced)

## Sub-ADRs

- [K006.1: Write-Path Salience](k006.1-write-path-salience.md)
- [K006.2: Read-Path Salience](k006.2-read-path-salience.md)
- [K006.3: Attention Networks](k006.3-attention-networks.md)

## Performance Budget

- Write-path P95: ≤5ms | Memory: <10MB

---
**Last Updated**: 2025-11-16
