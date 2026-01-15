---
adr_number: 'K021'
affected_layers: [governance]
affected_modules: []
authors:
- K0 Architecture Team
concerns:
- governance
- accuracy
date_created: '2025-12-30'
date_updated: '2025-12-30'
implementation_date: '2025-12-30'
implementation_phase: immediate
implementation_status: IMPLEMENTED
propagation:
  affected_adrs: []
  affected_contracts: []
  affected_tests: []
  triggers:
  - Governance sync produces false positives from non-authoritative sources
related_adrs: []
related_contracts: []
related_diagrams: []
research_citations: []
status: ACCEPTED
superseded_by: []
supersedes: []
title: Governance Scanner Tightening
---

# ADR-K021: Governance Scanner Tightening

**Status**: Accepted

**Date**: 2025-12-30

**Authors**: K0 Architecture Team

## Context

The governance sync tool (`governance/k0/scripts/sync.py`) uses scanners to detect drift between code and architecture documentation. Two scanners are overly permissive:

1. **event_scanner.py**: Scans ALL `*.py` files under `k0/` using broad regex patterns that match topic strings in comments, docstrings, and example code - not just actual emit calls.

2. **module_scanner.py**: Scans ALL `*.py` files in `k0/modules/<folder>/` - treating helper files, utilities, and non-module code as modules.

This produces inflated counts and potential false positives that undermine governance accuracy.

## Decision

Tighten both scanners to use authoritative sources only:

### event_scanner.py
- **Remove** broad string literal pattern matching from `_scan_emit_calls()`
- **Keep** only actual `.emit()` and `outbox_emit*()` call patterns
- **Primary source**: Contract YAMLs (`k0/contracts/modules/*.yaml`, `k0/contracts/pipelines/*.yaml`)
- **Secondary source**: Whiteboard topic registry (`k0/pipelines/whiteboard.md`)

### module_scanner.py
- **Primary source**: Contract YAMLs (`k0/contracts/modules/*.yaml`)
- **Fallback**: Only scan `*.py` files if they have a matching contract OR are registered in master doc
- Cross-reference against `k0_architecture_master.md` Part 3.1 for ID mapping

## Consequences

### Positive
- Scanner counts reflect actual registered artifacts
- Drift detection becomes meaningful (no noise from incidental strings)
- Governance sync trustworthiness increases

### Negative
- Events/modules without contracts will not be scanned (by design - forces contract discipline)

### Risks
- None significant - this enforces existing K0 contract-first policy
