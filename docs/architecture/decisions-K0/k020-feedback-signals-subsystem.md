---
adr_number: 'K020'
affected_layers:
- layer1_ports
- layer2_bus
- layer5_infrastructure
affected_modules:
- k0.ports.observe
- k0.feedback.envelope
- k0.feedback.signals
- k0.modules.feedback.ingest
authors:
- K0 Architecture Team
concerns:
- architecture
- maintainability
- performance
- security
- data-integrity
date_created: '2025-12-25'
date_updated: '2025-12-25'
implementation_date: null
implementation_phase: null
implementation_status: DRAFT
propagation:
  affected_adrs: []
  affected_contracts:
  - k0/contracts/modules/feedback.ingest.v1.yaml
  - k0/contracts/schemas/feedback_signal_envelope.json
  affected_tests: []
  triggers:
  - Introduce pipeline-agnostic feedback ingestion (Observe → Store → Bus)
related_adrs: []
related_contracts:
- docs/plans/PLAN-feedback-pipeline-system.md
- docs/plans/FEEDBACK-issues-tracker.md
- k0/ports/FEEDBACK.md
related_diagrams: []
research_citations: []
status: DRAFT
superseded_by: []
supersedes: []
title: Feedback Signals Subsystem (Observe → Store → Bus)
---

## ADR-K020: Feedback Signals Subsystem (Observe → Store → Bus)

**Status**: Draft

**Date**: 2025-12-25

**Authors**: @K0-Architecture-Team

## Context

K0 currently has no first-class mechanism for pipelines to receive structured outcome/correction signals. Pipelines (notably P02 Write and P08 Embeddings) operate with static parameters and cannot learn from user corrections, retrieval failures, or session behavioral signals.

Constraints:

- Only P02 and P08 are currently implemented; avoid predefining schemas for non-existent pipelines.
- Feedback must be pipeline-agnostic at the envelope layer, and pipeline-specific at the payload layer.
- Ingress must follow K0 port patterns and be safe against malformed or noisy signals.

## Decision

We will add a pipeline-agnostic Feedback Signals subsystem with:

1. **Ingress** via the existing Observe port (`/k0/obs.emit`) using `kind: "feedback"`.
2. A versioned **FeedbackEnvelope** model used for routing, correlation, and provenance.
3. A **Signal Class taxonomy** to categorize feedback signals consistently across pipelines.
4. **Schema validation** of the pipeline-specific `payload` using a FeedbackSchemaRegistry (per-pipeline schemas; permissive mode for unregistered pipelines during early rollout).
5. **Persistence** in `st_feedback_signals` (generic columns + JSONB payload).
6. **Dispatch** onto bus topics `feedback.signal.<pipeline>.v1` for pipeline-specific consumers.

Initial implementation scope is Milestone 0 (Envelope + taxonomy) and Milestone 1 foundations for P02/P08 only.

## Consequences

### Positive

- Enables learning loops without hardcoding schema changes for every new pipeline.
- Allows robust correlation back to originating K0 operations (event_ids, wal positions, receipts).
- Establishes a stable contract boundary for K1 → K0 feedback emission.

### Negative

- Introduces a new ingestion surface area that must be guarded (rate limiting, anomaly detection) to avoid noisy/malicious feedback.
- Requires careful schema/versioning discipline to avoid breaking K1 emitters.

### Risks

- Feedback loops contaminating themselves if provenance is missing or mutable.
- Storage growth if retention is not enforced.

## Alternatives Considered

### Alternative 1: Hardcode feedback fields per pipeline in Observe

Rejected: becomes a bottleneck and breaks the "unlimited future pipelines" constraint.

### Alternative 2: Emit raw strings and let pipelines parse

Rejected: no reliable validation, poor auditability, and high coupling to NLP parsing.

## Implementation Notes

- Start with FEEDBACK-001 (FeedbackEnvelope model) and FEEDBACK-002 (signal taxonomy).
- Add FEEDBACK-000 (FeedbackProvenance) before any adaptive learning behavior consumes feedback.
- Ensure all feedback models use `extra="forbid"` and normalize/validate IDs.

## References

- Plan: `docs/plans/PLAN-feedback-pipeline-system.md`
- Issue Tracker: `docs/plans/FEEDBACK-issues-tracker.md`
- Wiring Guide: `k0/ports/FEEDBACK.md`
