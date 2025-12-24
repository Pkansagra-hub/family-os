# P03 Consolidation Pipeline Dossier v2

> **Version**: 2.3.0
> **Status**: Production-Ready Draft
> **Created**: 2025-12-20
> **Last Updated**: 2025-12-21
> **Author**: K0 Architecture Team
> **Supersedes**: P03_consolidation_dossier.md (v1)

---

## Executive Summary

P03 is the **Memory Consolidation & Forgetting Pipeline** — an offline process that transforms raw episodic signals into durable, queryable memory structures. Unlike v1 which presented a one-way flow (P02 → 8 memory layers), **v2 recognizes consolidation as a bidirectional dialogue** between new signals and existing truth.

**Core Principle**: The 8 memory layers are **TRUTH**. New signals from P02 are **candidates** that must be reconciled against existing truth before updating it.

---

## Related Documents

| Document | Location | Relationship |
|----------|----------|--------------|
| K0 Architecture Master | [k0_architecture_master.md](../../k0/pipelines/k0_architecture_master.md) | Source of truth for registries |
| P02 Write Pipeline | [P02_write_dossier.md](P02_write_dossier.md) | Upstream - produces st_hipp_events |
| P08 Embedding Pipeline | [P08_embedding_dossier_v2.md](P08_embedding_dossier_v2.md) | Dependency - embedding.search, FAISS |
| P06 Active Learning | [0001-active-learning-loop.md](../architecture/ideas/0001-active-learning-loop.md) | Downstream - gap.detected events |
| P04 Query Pipeline | (TBD) | Downstream - consumes consolidated truth |
| K1 Experience Layer | (Future Scope) | User-facing gap question delivery |
| UltraBERT Model Spec | [Appendix H](#appendix-h-ultrabert-model-specification) | Embedding model used in R1, R4 |

> **P08 Dependency Note**: P03 requires P08 v1.0+ for `embedding.search` capability. Circuit breaker configured in Section 13.6.

> **K1 Future Scope Note**: K1 Experience Layer integration (Curiosity Agent, proactive bubbles) is documented in Section 5.1 architecture but detailed implementation is deferred until K1 specification is complete.

---

## Table of Contents

### Part I: Foundation

1. [Core Philosophy: Bidirectional Truth Reconciliation](#1-core-philosophy-bidirectional-truth-reconciliation)
   - 1.1 [The Fundamental Shift from v1](#11-the-fundamental-shift-from-v1)
   - 1.2 [The Truth-First Model](#12-the-truth-first-model)
   - 1.3 [Reconciliation Decision Types](#13-reconciliation-decision-types)
   - 1.4 [The Reconciliation Algorithm](#14-the-reconciliation-algorithm)

2. [Neuroscience Foundation](#2-neuroscience-foundation)
   - 2.1 [Brain-Inspired Phase Mapping (R0-R8)](#21-brain-inspired-phase-mapping-r0-r8)
   - 2.2 [Phase-to-Brain-Region Mapping](#22-phase-to-brain-region-mapping)
   - 2.3 [Key Neuroscience Principles in P03](#23-key-neuroscience-principles-in-p03)
   - 2.4 [Scientific Formulas](#24-scientific-formulas)
   - 2.5 [Key Scientific References](#25-key-scientific-references)

3. [Architectural Overview](#3-architectural-overview)
   - 3.1 [P03 in the K0 Pipeline Ecosystem](#31-p03-in-the-k0-pipeline-ecosystem)
   - 3.2 [P03 Internal Architecture](#32-p03-internal-architecture)
   - 3.3 [Data Flow Diagram (Bidirectional)](#33-data-flow-diagram-bidirectional)

### Part II: Implementation

1. [Phase Specifications (R0-R8)](#4-phase-specifications-r0-r8)
   - 4.0 [Phase Overview Diagram](#40-phase-overview-diagram)
   - 4.1 [R0 — Trigger Detection & Sleep Onset](#41-r0--trigger-detection--sleep-onset)
   - 4.2 [R1 — Hippocampal Replay (NREM1)](#42-r1--hippocampal-replay-nrem1)
   - 4.3 [R2 — Neocortical Integration (NREM2)](#43-r2--neocortical-integration-nrem2)
   - 4.4 [R3 — Synaptic Homeostasis (Forgetting)](#44-r3--synaptic-homeostasis-forgetting)
   - 4.5 [R4 — Knowledge Graph Consolidation](#45-r4--knowledge-graph-consolidation)
   - 4.6 [R5 — Dream-Like Exploration (REM)](#46-r5--dream-like-exploration-rem)
   - 4.7 [R6 — Staging Table Updates](#47-r6--staging-table-updates)
   - 4.8 [R7 — Memory Layer Writes (Truth Update)](#48-r7--memory-layer-writes-truth-update)
   - 4.9 [R8 — Event Emission & Completion](#49-r8--event-emission--completion)
   - 4.10 [K0 Kernel Enhancements Required](#410-k0-kernel-enhancements-required)

2. [P06 Active Learning Integration](#5-p06-active-learning-integration)
   - 5.1 [Overview: P03 as the "Observer Brain"](#51-overview-p03-as-the-observer-brain)
   - 5.2 [Gap Detection During Reconciliation](#52-gap-detection-during-reconciliation)
   - 5.3 [Entropy Scanning (Proactive Gap Detection)](#53-entropy-scanning-proactive-gap-detection)
   - 5.4 [Bayesian Anchor Points (User Modeling)](#54-bayesian-anchor-points-user-modeling)
   - 5.5 [Contradiction Resolution Protocol](#55-contradiction-resolution-protocol)
   - 5.6 [Attention Budget Integration](#56-attention-budget-integration)

3. [Storage Schema Design](#6-storage-schema-design)
   - 6.1 [Schema Design Principles](#61-schema-design-principles)
   - 6.2 [st_hipp_events (Staging / Hippocampus)](#62-st_hipp_events-staging--hippocampus)
   - 6.3 [st_epi (Episodic Memory)](#63-st_epi-episodic-memory)
   - 6.4 [st_sem (Semantic Patterns)](#64-st_sem-semantic-patterns)
   - 6.5 [st_procedural (Habits & Routines)](#65-st_procedural-habits--routines)
   - 6.6 [st_social (Relationships)](#66-st_social-relationships)
   - 6.7 [st_prospective (Intentions & Goals)](#67-st_prospective-intentions--goals)
   - 6.8 [st_kg_dom (KG Entities)](#68-st_kg_dom-kg-entities)
   - 6.9 [st_kg_edges (KG Relationships)](#69-st_kg_edges-kg-relationships)
   - 6.10 [st_vec (Embeddings)](#610-st_vec-embeddings)
   - 6.11 [st_learning_queue (Gap Queue)](#611-st_learning_queue-gap-queue)
   - 6.12 [st_anchors (Bayesian Beliefs)](#612-st_anchors-bayesian-beliefs)
   - 6.13 [st_anchor_observations (Evidence Log)](#613-st_anchor_observations-evidence-log)
   - 6.14 [st_pipeline_offsets & st_pipeline_status](#614-st_pipeline_offsets--st_pipeline_status)
   - 6.15 [st_outbox (Durable Writes)](#615-st_outbox-durable-writes)
   - 6.16 [st_retention_policy (Lifecycle Management)](#616-st_retention_policy-lifecycle-management)

4. [Module Registry](#7-module-registry)
   - 7.1 [P03 Module Architecture](#71-p03-module-architecture)
   - 7.2 [P03-Specific Modules (M18-M25)](#72-p03-specific-modules-m18-m25)
   - 7.3 [Reused Modules from P02](#73-reused-modules-from-p02)
   - 7.4 [Module Interface Contracts](#74-module-interface-contracts)

### Part III: Operations & Integration

1. [Observability & Metrics](#8-observability--metrics)
   - 8.1 [Metrics Overview](#81-metrics-overview)
   - 8.2 [Metric Definitions](#82-metric-definitions)
   - 8.3 [Distributed Tracing](#83-distributed-tracing)
   - 8.4 [Structured Logging](#84-structured-logging)
   - 8.5 [Dashboards](#85-dashboards)
   - 8.6 [Alerting Rules](#86-alerting-rules)

2. [Integration Contracts](#9-integration-contracts)
   - 9.1 [Contract Overview](#91-contract-overview)
   - 9.2 [P02 → P03 Contract](#92-p02--p03-contract)
   - 9.3 [P03 → P06 Contract (Active Learning)](#93-p03--p06-contract-active-learning)
   - 9.4 [P03 → P08 Contract (Embedding Index)](#94-p03--p08-contract-embedding-index)
   - 9.5 [P03 ↔ P05 Attention Contract](#95-p03--p05-attention-contract)
   - 9.6 [P03 Output Events](#96-p03-output-events)
   - 9.7 [Contract Validation](#97-contract-validation)

3. [Testing Strategy](#10-testing-strategy)
    - 10.1 [Test Architecture Overview](#101-test-architecture-overview)
    - 10.2 [Unit Tests](#102-unit-tests)
    - 10.3 [Integration Tests](#103-integration-tests)
    - 10.4 [Contract Tests](#104-contract-tests)
    - 10.5 [Performance Tests](#105-performance-tests)
    - 10.6 [Golden Dataset Tests](#106-golden-dataset-tests)
    - 10.7 [Test Fixtures](#107-test-fixtures)

4. [Migration & Evolution](#11-migration--evolution)
    - 11.1 [Migration Overview](#111-migration-overview)
    - 11.2 [v1 → v2 Migration](#112-v1--v2-migration)
    - 11.3 [Future Phases](#113-future-phases)
    - 11.4 [Deprecation Schedule](#114-deprecation-schedule)
    - 11.5 [Backward Compatibility](#115-backward-compatibility)
    - 11.6 [Feature Flags](#116-feature-flags)

### Part IV: Reference

1. [Policy Decisions & Feature Flags](#12-policy-decisions--feature-flags)
    - 12.1 [Resolved Design Decisions](#121-resolved-design-decisions)
    - 12.2 [Resolved Implementation TODOs](#122-resolved-implementation-todos)
    - 12.3 [Resolved Active Learning Integration TODOs](#123-resolved-active-learning-integration-todos)
    - 12.4 [Feature Flag Master List](#124-feature-flag-master-list)

2. [Error Handling & Dead Letter Queue](#13-error-handling--dead-letter-queue)
    - 13.1 [K0 Integration Overview](#131-k0-integration-overview)
    - 13.2 [Error Classification](#132-error-classification)
    - 13.3 [K0 DLQ Integration](#133-k0-dlq-integration)
    - 13.4 [Dead Letter Queue Schema (st_dlq)](#134-dead-letter-queue-schema-st_dlq)
    - 13.5 [Retry Strategy (K0 RetryScheduler)](#135-retry-strategy-k0-retryscheduler)
    - 13.6 [Circuit Breaker (External Dependencies)](#136-circuit-breaker-external-dependencies)
    - 13.7 [Partial Failure Handling](#137-partial-failure-handling)
    - 13.8 [K0 CLI Integration (k0ctl dlq)](#138-k0-cli-integration-k0ctl-dlq)
    - 13.9 [Edge Case Handling Matrix](#139-edge-case-handling-matrix)
    - 13.10 [Recovery Procedures](#1310-recovery-procedures)

3. [Security & Privacy](#14-security--privacy)
    - 14.1 [K0 Policy Engine Integration](#141-k0-policy-engine-integration)
    - 14.2 [Privacy Band Enforcement](#142-privacy-band-enforcement)
    - 14.3 [K0 ACL Enforcer Integration](#143-k0-acl-enforcer-integration)
    - 14.4 [K0 Location Privacy Integration](#144-k0-location-privacy-integration)
    - 14.5 [Audit Trail (K0 Observability)](#145-audit-trail-k0-observability)
    - 14.6 [K0 Retention Enforcer Integration](#146-k0-retention-enforcer-integration)
    - 14.7 [Data Minimization & GDPR](#147-data-minimization--gdpr)
    - 14.8 [Encryption (K0 Crypto Layer)](#148-encryption-k0-crypto-layer)

4. [Performance Tuning](#15-performance-tuning)
    - 15.1 [K0 QoS Integration Overview](#151-k0-qos-integration-overview)
    - 15.2 [K0 Scheduler Integration](#152-k0-scheduler-integration)
    - 15.3 [Performance Baselines](#153-performance-baselines)
    - 15.4 [Batch Size Optimization (K0-Aware)](#154-batch-size-optimization-k0-aware)
    - 15.5 [Embedding Query Optimization (K0-Aware)](#155-embedding-query-optimization-k0-aware)
    - 15.6 [Memory Management (K0-Aware)](#156-memory-management-k0-aware)
    - 15.7 [Database Optimization (K0-Aware)](#157-database-optimization-k0-aware)
    - 15.8 [K0 Metrics Export](#158-k0-metrics-export)

5. [Configuration Reference](#16-configuration-reference)
    - 16.1 [K0 Configuration Integration Overview](#161-k0-configuration-integration-overview)
    - 16.2 [K0 Kernel Configuration Integration](#162-k0-kernel-configuration-integration)
    - 16.3 [K0 Pipeline Scheduler Configuration](#163-k0-pipeline-scheduler-configuration)
    - 16.4 [K0 Capability Fabric Configuration](#164-k0-capability-fabric-configuration)
    - 16.5 [K0 Module Registry Configuration](#165-k0-module-registry-configuration)
    - 16.6 [Complete Configuration YAML](#166-complete-configuration-yaml)
    - 16.7 [K0 CLI Commands (k0ctl)](#167-k0-cli-commands-k0ctl)
    - 16.8 [Environment Variable Overrides](#168-environment-variable-overrides)

6. [Ops Readiness](#17-ops-readiness)
    - 17.1 [Service Level Objectives (SLOs)](#171-service-level-objectives-slos)
    - 17.2 [Dashboard Specifications](#172-dashboard-specifications)
    - 17.3 [Alerting Rules](#173-alerting-rules)
    - 17.4 [Runbooks](#174-runbooks)
    - 17.5 [Runbook Index](#175-runbook-index)
    - 17.6 [On-Call Checklist](#176-on-call-checklist)

### Appendices

- [Appendix A: Scientific References (Full Bibliography)](#appendix-a-scientific-references-full-bibliography)
- [Appendix B: Glossary](#appendix-b-glossary)
- [Appendix C: Algorithm Specifications](#appendix-c-algorithm-specifications)
  - C.1 [Core Reconciliation Algorithms](#c1-core-reconciliation-algorithms)
  - C.2 [R1: Hippocampal Replay Algorithms (M23)](#c2-r1-hippocampal-replay-algorithms-m23)
  - C.3 [R2: Episodic Integration Algorithms (M18)](#c3-r2-episodic-integration-algorithms-m18)
  - C.4 [R3: Synaptic Homeostasis / Forgetting (M19, M20)](#c4-r3-synaptic-homeostasis--forgetting-m19-m20)
  - C.5 [R4: Knowledge Graph Algorithms (M21)](#c5-r4-knowledge-graph-algorithms-m21)
  - C.6 [R5: Dream-Like Exploration Algorithms (M22)](#c6-r5-dream-like-exploration-algorithms-m22)
  - C.7 [Active Learning Algorithms (P06 Integration)](#c7-active-learning-algorithms-p06-integration)
  - C.8 [Supplementary Algorithms](#c8-supplementary-algorithms)
- [Changelog](#changelog)
- [Appendix D: P03 Kernel Integration Blueprint](#appendix-d-p03-kernel-integration-blueprint)
  - D.1 [Architecture Context](#d1-architecture-context)
  - D.2 [Pipeline Contract Design](#d2-pipeline-contract-design)
  - D.3 [DAG Stage Design](#d3-dag-stage-design)
  - D.4 [Module Development Plan](#d4-module-development-plan)
  - D.5 [Scheduler Integration](#d5-scheduler-integration)
  - D.6 [Event Bus Integration](#d6-event-bus-integration)
  - D.7 [Storage Integration](#d7-storage-integration)
  - D.8 [Fabric Capability Integration](#d8-fabric-capability-integration)
  - D.9 [Observability Integration](#d9-observability-integration)
  - D.10 [Error Handling Integration](#d10-error-handling-integration)
  - D.11 [Testing Strategy](#d11-testing-strategy)
  - D.12 [Implementation Roadmap](#d12-implementation-roadmap)
- [Appendix E: Canonical Name Registry](#appendix-e-canonical-name-registry)
  - E.1 [Pipeline Identifiers](#e1-pipeline-identifiers)
  - E.2 [Event Topics (Bus)](#e2-event-topics-bus)
  - E.3 [Storage Tables](#e3-storage-tables)
  - E.4 [Module Registry](#e4-module-registry)
  - E.5 [Fabric Capabilities](#e5-fabric-capabilities)
  - E.6 [Contract Files](#e6-contract-files)
  - E.7 [Configuration Keys](#e7-configuration-keys)
  - E.8 [Metrics Names](#e8-metrics-names)
  - E.9 [Architecture Diagrams](#e9-architecture-diagrams)
  - E.10 [ADR References](#e10-adr-references)
- [Appendix F: Threshold Configuration Table](#appendix-f-threshold-configuration-table)
  - F.1 [Reconciliation Thresholds](#f1-reconciliation-thresholds)
  - F.2 [Decay Thresholds](#f2-decay-thresholds)
  - F.3 [Confidence Thresholds](#f3-confidence-thresholds)
  - F.4 [Active Learning Thresholds](#f4-active-learning-thresholds)
  - F.5 [Performance Thresholds](#f5-performance-thresholds)
  - F.6 [Threshold Validation Rules](#f6-threshold-validation-rules)
  - F.7 [Testing Requirements](#f7-testing-requirements)
- [Appendix G: R0-R8 State Machine Specification](#appendix-g-r0-r8-state-machine-specification)
  - G.1 [State Machine Overview](#g1-state-machine-overview)
  - G.2 [Phase Specifications](#g2-phase-specifications)
  - G.3 [State Transition Rules](#g3-state-transition-rules)
  - G.4 [Error Recovery Matrix](#g4-error-recovery-matrix)
  - G.5 [Metrics Per Phase](#g5-metrics-per-phase)
- [Appendix H: UltraBERT Model Specification](#appendix-h-ultrabert-model-specification)
  - H.1 [Model Overview](#h1-model-overview)
  - H.2 [Encoder Capabilities](#h2-encoder-capabilities)
  - H.3 [Performance Benchmarks](#h3-performance-benchmarks)
  - H.4 [Client API Usage](#h4-client-api-usage)
  - H.5 [Backend Selection](#h5-backend-selection)
  - H.6 [Versioning Strategy](#h6-versioning-strategy)
  - H.7 [P03 Integration Points](#h7-p03-integration-points)
  - H.8 [Model Artifact Location](#h8-model-artifact-location)

---

## 1. Core Philosophy: Bidirectional Truth Reconciliation

### 1.1 The Fundamental Shift from v1

**v1 Thinking (One-Way Flow)**:

```
P02 → st_hipp_events → R1 → R2 → R3 → R4 → R5 → R6 → R7 → 8 Memory Layers
                    (linear pipeline, new data overwrites)
```

**v2 Thinking (Bidirectional Dialogue)**:

```
                    ┌────────────────────────────────────────┐
                    │                                        │
                    ▼                                        │
P02 → st_hipp_events → RECONCILE AGAINST → 8 Memory Layers (TRUTH)
                    │              │                         ▲
                    │              ▼                         │
                    │   ┌─────────────────────────────┐     │
                    │   │ Compare new vs existing     │     │
                    │   │ • Reinforce patterns        │     │
                    │   │ • Extend knowledge          │─────┘
                    │   │ • Create new entries        │
                    │   │ • Prune stale memories      │
                    │   └─────────────────────────────┘
                    │
                    └──────────────────────────────────
                        (truth-first reconciliation)
```

### 1.2 The Truth-First Model

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           P03 CONSOLIDATION: BIDIRECTIONAL TRUTH FLOW                               │
│                                                                                                     │
│     "8 Memory Layers = TRUTH"              "New Signals from P02"                                  │
│                                                                                                     │
│  ┌───────────────────────────────────┐     ┌────────────────────────────────────┐                  │
│  │     LONG-TERM MEMORY TRUTH        │     │       NEW EPISODIC SIGNALS         │                  │
│  │    (Existing Knowledge Base)      │     │        (st_hipp_events)            │                  │
│  │                                   │     │                                    │                  │
│  │  ┌─────────────┐ ┌─────────────┐  │     │  ┌──────────────────────────────┐  │                  │
│  │  │   st_epi    │ │   st_sem    │  │     │  │  New events from P02:        │  │                  │
│  │  │ (Episodes)  │ │ (Patterns)  │  │     │  │  - UltraBERT embeddings      │  │                  │
│  │  └─────────────┘ └─────────────┘  │     │  │  - SimHash fingerprints      │  │                  │
│  │                                   │     │  │  - Entity extractions        │  │                  │
│  │  ┌─────────────┐ ┌─────────────┐  │     │  │  - Salience scores           │  │                  │
│  │  │st_procedural│ │  st_social  │  │     │  └──────────────────────────────┘  │                  │
│  │  │  (Habits)   │ │(Relations)  │  │     │                                    │                  │
│  │  └─────────────┘ └─────────────┘  │     └────────────────┬───────────────────┘                  │
│  │                                   │                      │                                       │
│  │  ┌─────────────┐ ┌─────────────┐  │                      │                                       │
│  │  │st_prospective││  st_kg_dom  │  │                      │                                       │
│  │  │(Intentions) ││  (Entities) │  │                      ▼                                       │
│  │  └─────────────┘ └─────────────┘  │     ┌────────────────────────────────────┐                  │
│  │                                   │     │                                    │                  │
│  │  ┌─────────────┐ ┌─────────────┐  │     │   P03 RECONCILIATION ENGINE       │                  │
│  │  │ st_kg_edges │ │   st_vec    │  │     │                                    │                  │
│  │  │(Relations)  │ │(Embeddings) │  │◀────│   "Does new signal match truth?   │◀─────────────────┤
│  │  └─────────────┘ └─────────────┘  │     │    Does it contradict? Extend?"   │                  │
│  │                                   │     │                                    │                  │
│  └───────────────┬───────────────────┘     └────────────────┬───────────────────┘                  │
│                  │                                          │                                       │
│                  │         BIDIRECTIONAL FLOW               │                                       │
│                  ▼                                          ▼                                       │
│  ┌───────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                                                                                               │ │
│  │                         ◀═══════════════════════════════════════════▶                         │ │
│  │                              RECONCILIATION DECISION MATRIX                                   │ │
│  │                                                                                               │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐ │ │
│  │  │                                                                                         │ │ │
│  │  │    STEP 1: QUERY TRUTH                 STEP 2: COMPARE                                  │ │ │
│  │  │    ───────────────────                 ───────────────                                  │ │ │
│  │  │                                                                                         │ │ │
│  │  │    For each new signal:                Is signal...                                     │ │ │
│  │  │                                                                                         │ │ │
│  │  │    • Query st_epi: "Have I            ✓ REINFORCING? → Boost truth confidence          │ │ │
│  │  │      seen this episode before?"                                                         │ │ │
│  │  │                                        ✓ EXTENDING? → Extend truth (new details)       │ │ │
│  │  │    • Query st_sem: "Does this                                                           │ │ │
│  │  │      match known patterns?"           ✓ NOVEL? → Create new truth entry                │ │ │
│  │  │                                                                                         │ │ │
│  │  │    • Query st_kg_dom: "Do I            ✗ CONTRADICTING? → Flag for resolution           │ │ │
│  │  │      know these entities?"                                                              │ │ │
│  │  │                                        ✗ DUPLICATE? → Merge into existing truth        │ │ │
│  │  │    • Query st_procedural: "Is                                                           │ │ │
│  │  │      this a known routine?"           ✗ STALE? → Apply decay, archive                  │ │ │
│  │  │                                                                                         │ │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘ │ │
│  │                                                                                               │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────┐ │ │
│  │  │                                                                                         │ │ │
│  │  │    STEP 3: REAFFIRM/UPDATE TRUTH                                                        │ │ │
│  │  │    ──────────────────────────────                                                       │ │ │
│  │  │                                                                                         │ │ │
│  │  │    Based on reconciliation decision:                                                    │ │ │
│  │  │                                                                                         │ │ │
│  │  │    ┌──────────────────────────────────────────────────────────────────────────────┐    │ │ │
│  │  │    │  REINFORCE           │  EVOLVE              │  CREATE           │  PRUNE      │    │ │ │
│  │  │    │                      │                      │                   │             │    │ │ │
│  │  │    │  ↑ observation_count │  version = v+1       │  New record       │  decay → 0  │    │ │ │
│  │  │    │  ↑ confidence_score  │  supersedes_id       │  is_canonical=1   │  archive    │    │ │ │
│  │  │    │  ↓ decay_factor      │  is_canonical=1      │  full provenance  │  tombstone  │    │ │ │
│  │  │    │  ↑ last_observed_at  │  valid_from=now      │                   │             │    │ │ │
│  │  │    └──────────────────────────────────────────────────────────────────────────────┘    │ │ │
│  │  │                                                                                         │ │ │
│  │  └─────────────────────────────────────────────────────────────────────────────────────────┘ │ │
│  │                                                                                               │ │
│  └───────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Reconciliation Decision Types

| Decision | Condition | Action on Truth | Example |
|----------|-----------|-----------------|---------|
| **REINFORCE** | New signal matches existing truth (similarity >0.85) | Increment `observation_count`, boost `confidence_score`, refresh `last_observed_at` | "Tuesday yoga" seen for 5th time |
| **EXTEND** | New signal adds details to existing truth (similarity 0.6-0.85) | Append to `source_episodes_json`, update attributes | "Tuesday yoga" now has location "CorePower" |
| **CREATE** | New signal has no match in truth (similarity <0.6) | INSERT new record with `is_canonical=1` | First "Wednesday hiking" pattern |
| **EVOLVE** | New signal represents schema evolution | Create new version, mark old as `is_canonical=0` | "Prefers Thai" → "Prefers Vietnamese" |
| **CONTRADICT** | New signal conflicts with existing truth | Flag for P06 Active Learning resolution | "Hates yoga" vs "Loves yoga" |
| **PRUNE** | Existing truth not reinforced for extended period | Apply decay, archive, or tombstone | Pattern not seen in 180 days |

### 1.4 The Reconciliation Algorithm

```python
async def reconcile_signal_against_truth(
    new_signal: HippEvent,
    truth_layers: TruthLayers,
    ctx: ConsolidationContext
) -> ReconciliationDecision:
    """
    Core reconciliation algorithm - bidirectional truth check.

    This is the HEART of P03 v2: every new signal is compared
    against existing truth before updating memory layers.
    """

    # STEP 1: Query existing truth across all relevant layers
    truth_matches = await query_truth_for_signal(new_signal, truth_layers)

    # STEP 2: Compute similarity to each truth match
    similarities = []
    for truth_record in truth_matches:
        sim = await compute_similarity(new_signal, truth_record)
        similarities.append((truth_record, sim))

    # STEP 3: Determine reconciliation decision
    if not similarities:
        # No match found - this is genuinely novel
        return ReconciliationDecision(
            decision_type=DecisionType.CREATE,
            target_layer=determine_target_layer(new_signal),
            confidence=new_signal.salience_score
        )

    # Find best match
    best_match, best_similarity = max(similarities, key=lambda x: x[1])

    if best_similarity > 0.85:
        # Strong match - reinforce existing truth
        return ReconciliationDecision(
            decision_type=DecisionType.REINFORCE,
            target_record=best_match,
            similarity=best_similarity,
            updates={
                'observation_count': best_match.observation_count + 1,
                'confidence_score': boost_confidence(best_match.confidence_score, best_similarity),
                'last_observed_at': new_signal.event_time_utc,
                'decay_factor': 1.0  # Reset decay
            }
        )

    elif best_similarity > 0.6:
        # Partial match - extend or evolve
        if is_schema_evolution(new_signal, best_match):
            return ReconciliationDecision(
                decision_type=DecisionType.EVOLVE,
                target_record=best_match,
                similarity=best_similarity,
                new_version_data=build_evolved_version(new_signal, best_match)
            )
        else:
            return ReconciliationDecision(
                decision_type=DecisionType.EXTEND,
                target_record=best_match,
                similarity=best_similarity,
                extensions=extract_new_details(new_signal, best_match)
            )

    else:
        # Low similarity - check for contradiction vs novelty
        if is_contradiction(new_signal, best_match):
            return ReconciliationDecision(
                decision_type=DecisionType.CONTRADICT,
                target_record=best_match,
                conflict_details=analyze_conflict(new_signal, best_match),
                flag_for_p06=True  # Active Learning will resolve
            )
        else:
            # Truly novel - create new truth
            return ReconciliationDecision(
                decision_type=DecisionType.CREATE,
                target_layer=determine_target_layer(new_signal),
                confidence=new_signal.salience_score
            )


async def query_truth_for_signal(
    signal: HippEvent,
    truth_layers: TruthLayers
) -> List[TruthRecord]:
    """
    Query all 8 memory layers to find relevant existing truth.

    This is the READ phase of bidirectional consolidation.
    """
    matches = []

    # 1. Query episodic layer (st_epi)
    epi_matches = await truth_layers.st_epi.query(
        tenant_id=signal.tenant_id,
        space_id=signal.space_id,
        simhash_distance_max=5,
        time_window_days=30,
        limit=10
    )
    matches.extend(epi_matches)

    # 2. Query semantic layer (st_sem)
    sem_matches = await truth_layers.st_sem.query(
        tenant_id=signal.tenant_id,
        pattern_type_hints=extract_pattern_hints(signal),
        embedding_similarity_min=0.7,
        limit=10
    )
    matches.extend(sem_matches)

    # 3. Query procedural layer (st_procedural)
    proc_matches = await truth_layers.st_procedural.query(
        actor_id=signal.actor_id,
        activity_type=signal.activity_type,
        temporal_bucket=signal.temporal_bucket,
        limit=5
    )
    matches.extend(proc_matches)

    # 4. Query social layer (st_social)
    if signal.participants_json:
        social_matches = await truth_layers.st_social.query(
            actor_id=signal.actor_id,
            participants=signal.participants_json,
            limit=5
        )
        matches.extend(social_matches)

    # 5. Query knowledge graph (st_kg_dom + st_kg_edges)
    if signal.entities_json:
        kg_matches = await truth_layers.st_kg.query_entities(
            entity_names=[e['text'] for e in signal.entities_json],
            limit=20
        )
        matches.extend(kg_matches)

    return matches
```

---

## 2. Neuroscience Foundation

### 2.1 Brain-Inspired Phase Mapping (R0-R8)

P03's consolidation phases directly map to the brain's sleep-dependent memory consolidation stages:

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                          │
│                           CONSOLIDATION = BIDIRECTIONAL DIALOGUE                         │
│                                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                                                                                 │   │
│   │   HIPPOCAMPUS                                              NEOCORTEX            │   │
│   │   (New Experiences)                                        (Existing Truth)     │   │
│   │                                                                                 │   │
│   │   ┌─────────────────┐        Sharp-Wave Ripples         ┌─────────────────┐    │   │
│   │   │  st_hipp_events │  ═══════════════════════════════▶ │   8 Memory      │    │   │
│   │   │                 │        (NREM Replay)               │   Layers        │    │   │
│   │   │  Recent Events  │                                    │                 │    │   │
│   │   │  (Hours-Days)   │  ◀═══════════════════════════════ │  st_epi         │    │   │
│   │   └─────────────────┘        Slow Oscillations           │  st_sem         │    │   │
│   │                              (Schema Activation)         │  st_procedural  │    │   │
│   │                                                          │  st_social      │    │   │
│   │   The hippocampus                                        │  st_prospective │    │   │
│   │   replays recent                                         │  st_kg_dom      │    │   │
│   │   experiences at                                         │  st_kg_edges    │    │   │
│   │   10-20x speed                                           │  st_vec         │    │   │
│   │                                                          └─────────────────┘    │   │
│   │                                                                                 │   │
│   │   CRITICAL INSIGHT:                                                             │   │
│   │   Neocortex sends schema activations BACK to hippocampus                       │   │
│   │   to guide which memories are strengthened vs forgotten                        │   │
│   │                                                                                 │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Phase-to-Brain-Region Mapping

| Phase | Brain Region | Sleep Stage | Scientific Function | P03 Implementation |
|-------|--------------|-------------|---------------------|-------------------|
| **R0** | Hypothalamus (SCN) | Sleep Onset / Pre-Sleep | Circadian gate signal, adenosine accumulation triggers sleep | Idle detection via Query Port, trigger evaluation |
| **R1** | CA3 (Hippocampus) | NREM1 | Sharp-Wave Ripples (100-250Hz), replay at 10-20x speed, pattern strengthening | Importance scoring, association strengthening, theta rhythm coordination |
| **R2** | CA1 → Neocortex | NREM2 | Systems Consolidation, hippocampal-neocortical dialogue, episodes → semantic schemas | Episodic clustering (DBSCAN), pattern extraction, CA1 bridge integration |
| **R3** | Whole Brain | SWS (Slow-Wave Sleep) | Synaptic Homeostasis (Tononi & Cirelli), prune weak synapses, consolidate strong ones | Deduplication (SimHash), novelty scoring, retention policy enforcement, forgetting |
| **R4** | Temporal Cortex | NREM2-3 | Semantic Networks, conceptual knowledge organization, entity binding | KG entity extraction, relationship discovery, temporal graph updates, causal inference |
| **R5** | Prefrontal Cortex | REM (Paradoxical Sleep) | Dream Creativity, counterfactual exploration, future simulation, emotional processing | Forward simulation (MCTS), insight generation (BGT-SM), motor skill rehearsal (TDL-HCO) |
| **R6** | Hippocampus | Transition (NREM→Wake) | Checkpoint hippocampal state, prepare for waking encoding | Mark `consolidation_status`, update staging table, write reconciliation decisions |
| **R7** | Neocortex | Transition | Memory Trace Transfer, stabilize neocortical representations | Write to 8 memory layers via outbox pattern, P08 coordination |
| **R8** | Whole Brain | Wake | Memory Integration, memories now accessible for conscious recall | Event emission, offset update, metrics aggregation |

### 2.3 Key Neuroscience Principles in P03

#### 2.3.1 Complementary Learning Systems (McClelland et al. 1995)

The brain uses two complementary systems:

- **Hippocampus**: Fast learning, episodic details, pattern separation
- **Neocortex**: Slow learning, semantic schemas, pattern generalization

P03 implements this with:

- `st_hipp_events`: Fast staging table (hippocampus analog)
- `st_sem`, `st_kg_*`: Slow-updating truth layers (neocortex analog)

#### 2.3.2 Synaptic Homeostasis Hypothesis (Tononi & Cirelli 2006)

During waking, synapses strengthen (learning). During sleep, weak synapses are pruned (forgetting), maintaining network efficiency.

P03 implements this in R3:

- `decay_factor`: Exponential decay for memories not reinforced
- `novelty_score`: Low novelty → candidate for pruning
- `archival_status`: ACTIVE → ARCHIVED → TOMBSTONE lifecycle

#### 2.3.3 Memory Reconsolidation (Nader et al. 2000)

When a memory is retrieved, it becomes labile and must be reconsolidated. This allows updating with new information.

P03 implements this via:

- **EXTEND decision**: Add new details to existing truth
- **EVOLVE decision**: Create new version when schema changes
- Version chains: `supersedes_id` links versions

### 2.4 Scientific Formulas

```python
# ═══════════════════════════════════════════════════════════════════════════════
# IMPORTANCE SCORE (R1.4) - Which memories get prioritized for consolidation?
# ═══════════════════════════════════════════════════════════════════════════════
#
# Based on: Emotional tagging theory (McGaugh 2004), Novelty detection (Knight 1996)
#
importance_score = (
    0.35 * |sentiment_score| * |affect_valence| * (1 + affect_arousal)  # Emotional salience
  + 0.25 * exp(-λ_recency * days_since_event)                           # Recency (λ=0.05, 14-day half-life)
  + 0.20 * log(1 + access_count) / log(10)                              # Access frequency (diminishing returns)
  + 0.20 * participant_count * avg_relationship_strength                # Social significance
)

# ═══════════════════════════════════════════════════════════════════════════════
# DECAY FUNCTION (R3) - Synaptic Homeostasis (forgetting)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Based on: Tononi & Cirelli (2006), Ebbinghaus forgetting curve
#
decay_factor = exp(-λ * days_since_last_observed)

# Layer-specific decay constants (λ):
# st_epi:       λ = 0.005  (Half-life: 139 days) - Episodic memories fade slowly
# st_sem:       λ = 0.003  (Half-life: 231 days) - Semantic knowledge very stable
# st_procedural: λ = 0.010 (Half-life: 69 days)  - Habits need reinforcement
# st_social:    λ = 0.002  (Half-life: 347 days) - Relationships persist long

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIDENCE SCORE (R2.4) - Pattern reliability
# ═══════════════════════════════════════════════════════════════════════════════
#
# Based on: Bayesian confidence updating, evidence accumulation
#
confidence = sqrt(frequency_score * consistency_score * significance_score)

where:
  frequency_score = min(1.0, log(observation_count + 1) / log(10))  # Log scaling, caps at ~10
  consistency_score = 1 - coefficient_of_variation(features)        # Low variance = high confidence
  significance_score = (temporal_regularity + spatial_tightness) / 2

# ═══════════════════════════════════════════════════════════════════════════════
# NOVELTY SCORE (R3.2) - How unique is this memory?
# ═══════════════════════════════════════════════════════════════════════════════
#
# Based on: Hippocampal novelty detection, pattern separation (DG)
#
novelty_score = 1.0 - (duplicate_count / time_window_event_count)

# Bonuses:
# + 0.15 for first-time activity (activity_count < 3)
# + 0.20 for milestone events (birthday, anniversary, graduation)
# + 0.10 for temporal anomaly (activity at unusual time)
# - 0.30 for exact duplicate (Hamming distance = 0)

# ═══════════════════════════════════════════════════════════════════════════════
# ASSOCIATION STRENGTH (R1.3) - Hebbian Learning
# ═══════════════════════════════════════════════════════════════════════════════
#
# Based on: "Neurons that fire together, wire together" (Hebb 1949)
#
association_strength = (
    co_occurrence_count                           # How often entities appear together
  * exp(-λ_temporal * avg_time_gap_hours)         # Temporal proximity bonus (λ=0.01)
  * (unique_contexts / total_contexts)            # Context diversity bonus
  * (1 + avg_sentiment_score)                     # Emotional significance
)

# ═══════════════════════════════════════════════════════════════════════════════
# SIMILARITY COMPUTATION (Reconciliation)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Multi-factor similarity for truth matching
#
similarity = (
    0.40 * cosine_similarity(embedding_new, embedding_existing)  # Semantic similarity
  + 0.25 * (1 - hamming_distance(simhash_new, simhash_existing) / 64)  # Text structure
  + 0.15 * jaccard_similarity(entities_new, entities_existing)  # Entity overlap
  + 0.10 * temporal_proximity_score(time_new, time_existing)    # Temporal closeness
  + 0.10 * spatial_proximity_score(location_new, location_existing)  # Spatial closeness
)
```

### 2.5 Key Scientific References

| Reference | Year | Key Finding | P03 Application |
|-----------|------|-------------|-----------------|
| Wilson & McNaughton | 1994 | Hippocampal replay during sleep | R1 episodic replay at accelerated speed |
| Stickgold & Walker | 2013 | Sleep-dependent memory consolidation | Full R0-R8 sleep cycle architecture |
| Tononi & Cirelli | 2006 | Synaptic homeostasis hypothesis | R3 decay functions and forgetting |
| McClelland et al. | 1995 | Complementary learning systems | Hippocampus (staging) vs Neocortex (truth layers) |
| Marr | 1971 | Hippocampal index theory | Episodes point to neocortical representations |
| Born & Wilhelm | 2012 | Systems memory consolidation | R2 CA1 bridge (episodes → semantic) |
| Nader et al. | 2000 | Memory reconsolidation | EXTEND/EVOLVE decisions update existing memories |
| McGaugh | 2004 | Emotional memory enhancement | Importance scoring weights emotional salience |
| Schacter & Addis | 2007 | Constructive episodic simulation | R5 forward simulation and counterfactuals |
| Mednick | 1962 | Remote associates (creativity) | R5 insight generation via graph traversal |

---

## 3. Architectural Overview

### 3.1 P03 in the K0 Pipeline Ecosystem

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   K0 PIPELINE ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   ┌─────────────┐                                                                       │
│   │    P02      │                                                                       │
│   │   Memory    │──────────────────┐                                                    │
│   │  Formation  │                  │                                                    │
│   └─────────────┘                  │                                                    │
│         │                          │                                                    │
│         │ Writes                   │                                                    │
│         ▼                          │                                                    │
│   ┌─────────────┐                  │                                                    │
│   │st_hipp_events│                 │                                                    │
│   │  (Staging)  │                  │                                                    │
│   └──────┬──────┘                  │                                                    │
│          │                         │                                                    │
│          │ Consolidation           │ P06 Active Learning                                │
│          ▼ (Offline)               │ (Gaps, Ambiguity)                                  │
│   ┌─────────────┐                  │                                                    │
│   │    P03      │                  │                                                    │
│   │Consolidation│◀─────────────────┤                                                    │
│   │& Forgetting │                  │                                                    │
│   └──────┬──────┘                  │                                                    │
│          │                         │                                                    │
│          │ Writes (Bidirectional)  │                                                    │
│          ▼                         │                                                    │
│   ┌─────────────────────────────────────────────────────────────────────────────┐      │
│   │                           8 MEMORY LAYERS (TRUTH)                            │      │
│   │                                                                              │      │
│   │  ┌─────────┐ ┌─────────┐ ┌───────────┐ ┌─────────┐ ┌────────────┐          │      │
│   │  │ st_epi  │ │ st_sem  │ │st_procedural│ │st_social│ │st_prospective│         │      │
│   │  │Episodes │ │Patterns │ │  Habits   │ │Relations│ │ Intentions │          │      │
│   │  └─────────┘ └─────────┘ └───────────┘ └─────────┘ └────────────┘          │      │
│   │                                                                              │      │
│   │  ┌─────────┐ ┌─────────┐ ┌─────────┐                                        │      │
│   │  │st_kg_dom│ │st_kg_edges│ │ st_vec  │                                       │      │
│   │  │Entities │ │Relations│ │Embeddings│                                       │      │
│   │  └─────────┘ └─────────┘ └─────────┘                                        │      │
│   │                                                                              │      │
│   └──────────────────────────────┬───────────────────────────────────────────────┘      │
│                                  │                                                      │
│                                  │ Reads (Query)                                        │
│                                  ▼                                                      │
│   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐                      │
│   │    P04      │         │    P05      │         │    P08      │                      │
│   │  Attention  │         │   Proactive │         │  Embedding  │                      │
│   │   Router    │         │   Triggers  │         │  Indexing   │                      │
│   └─────────────┘         └─────────────┘         └─────────────┘                      │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 P03 Internal Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              P03 CONSOLIDATION PIPELINE                                  │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                               SLEEP CYCLE CONTROLLER                             │   │
│  │                                                                                   │   │
│  │   IDLE ──▶ R0 ──▶ NREM1 ──▶ NREM2 ──▶ REM ──▶ WAKING ──▶ COMPLETE ──▶ IDLE     │   │
│  │           Trigger   R1      R2,R3,R4   R5      R6,R7,R8                          │   │
│  │                                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                           │                                             │
│                                           ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                           RECONCILIATION ENGINE (CORE)                           │   │
│  │                                                                                   │   │
│  │   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐             │   │
│  │   │  Truth Reader   │───▶│   Comparator    │───▶│ Decision Maker  │             │   │
│  │   │                 │    │                 │    │                 │             │   │
│  │   │ Query 8 layers  │    │ Compute sim     │    │ REINFORCE/      │             │   │
│  │   │ for matches     │    │ Detect patterns │    │ EXTEND/CREATE/  │             │   │
│  │   │                 │    │ Find conflicts  │    │ EVOLVE/PRUNE    │             │   │
│  │   └─────────────────┘    └─────────────────┘    └────────┬────────┘             │   │
│  │                                                          │                       │   │
│  │                                                          ▼                       │   │
│  │                                              ┌─────────────────┐                 │   │
│  │                                              │  Truth Updater  │                 │   │
│  │                                              │                 │                 │   │
│  │                                              │ Apply decision  │                 │   │
│  │                                              │ to 8 layers     │                 │   │
│  │                                              └─────────────────┘                 │   │
│  │                                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              PHASE MODULES                                        │  │
│  │                                                                                   │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │  │
│  │  │   R1    │  │   R2    │  │   R3    │  │   R4    │  │   R5    │  │  R6-R8  │  │  │
│  │  │ Replay  │  │ Cluster │  │ Forget  │  │  KG     │  │ Dream   │  │ Commit  │  │  │
│  │  │         │  │ Extract │  │ Prune   │  │ Build   │  │ Explore │  │ Write   │  │  │
│  │  │ M23     │  │ M03,M18 │  │ M19,M20 │  │ M21     │  │ M22     │  │ M24,M25 │  │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘  │  │
│  │                                                                                   │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Data Flow Diagram (Bidirectional)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                            P03 BIDIRECTIONAL DATA FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│                         ┌─────────────────────────────────┐                             │
│                         │         st_hipp_events          │                             │
│                         │    (New Signals from P02)       │                             │
│                         │                                 │                             │
│                         │  • UltraBERT embeddings (st_vec)│                             │
│                         │  • SimHash fingerprints         │                             │
│                         │  • entities_json (UltraBERT NER)│                             │
│                         │  • salience_score               │                             │
│                         │  • consolidation_status = NULL  │                             │
│                         └────────────────┬────────────────┘                             │
│                                          │                                              │
│                                          │ R1: Select batch                             │
│                                          ▼                                              │
│    ┌─────────────────────────────────────────────────────────────────────────────┐      │
│    │                                                                             │      │
│    │                        RECONCILIATION ENGINE                                │      │
│    │                                                                             │      │
│    │  ┌───────────────────────────────────────────────────────────────────────┐  │      │
│    │  │                                                                       │  │      │
│    │  │                      TRUTH QUERY PHASE                                │  │      │
│    │  │                      (Read from 8 layers)                             │  │      │
│    │  │                                                                       │  │      │
│    │  │    For each new signal, query:                                        │  │      │
│    │  │                                                                       │  │      │
│    │  │    st_epi ───────▶ "Similar episodes?"                                │  │      │
│    │  │    st_sem ───────▶ "Matching patterns?"                               │  │      │
│    │  │    st_procedural ▶ "Known routine?"                                   │  │      │
│    │  │    st_social ────▶ "Known relationship?"                              │  │      │
│    │  │    st_kg_dom ────▶ "Known entities?"                                  │  │      │
│    │  │    st_kg_edges ──▶ "Known relationships?"                             │  │      │
│    │  │                                                                       │  │      │
│    │  └───────────────────────────────────────────────────────────────────────┘  │      │
│    │                                          │                                  │      │
│    │                                          ▼                                  │      │
│    │  ┌───────────────────────────────────────────────────────────────────────┐  │      │
│    │  │                                                                       │  │      │
│    │  │                      COMPARISON PHASE                                 │  │      │
│    │  │                      (Compute similarities)                           │  │      │
│    │  │                                                                       │  │      │
│    │  │    For each (signal, truth_match) pair:                               │  │      │
│    │  │                                                                       │  │      │
│    │  │    • Embedding cosine similarity (40%)                                │  │      │
│    │  │    • SimHash Hamming distance (25%)                                   │  │      │
│    │  │    • Entity Jaccard overlap (15%)                                     │  │      │
│    │  │    • Temporal proximity (10%)                                         │  │      │
│    │  │    • Spatial proximity (10%)                                          │  │      │
│    │  │                                                                       │  │      │
│    │  └───────────────────────────────────────────────────────────────────────┘  │     │
│    │                                          │                                  │     │
│    │                                          ▼                                  │     │
│    │  ┌───────────────────────────────────────────────────────────────────────┐  │     │
│    │  │                                                                       │  │     │
│    │  │                      DECISION PHASE                                   │  │     │
│    │  │                      (Determine action)                               │  │     │
│    │  │                                                                       │  │     │
│    │  │    sim > 0.85  ──────▶ REINFORCE (boost existing truth)               │  │     │
│    │  │    sim 0.60-0.85 ────▶ EXTEND or EVOLVE                               │  │     │
│    │  │    sim < 0.60  ──────▶ CREATE (new truth) or CONTRADICT               │  │     │
│    │  │    no recent obs ────▶ PRUNE (decay/archive)                          │  │     │
│    │  │                                                                       │  │     │
│    │  └───────────────────────────────────────────────────────────────────────┘  │     │
│    │                                                                             │     │
│    └─────────────────────────────────────────────────────────────────────────────┘     │
│                                          │                                             │
│                                          │ R7: Apply decisions                         │
│                                          ▼                                             │
│    ┌─────────────────────────────────────────────────────────────────────────────┐     │
│    │                                                                             │     │
│    │                          8 MEMORY LAYERS (TRUTH)                            │     │
│    │                                                                             │     │
│    │  ┌─────────────────────────────────────────────────────────────────────┐   │     │
│    │  │                                                                     │   │     │
│    │  │  REINFORCE:                   │  CREATE:                            │   │     │
│    │  │  • observation_count += 1     │  • INSERT new record                │   │     │
│    │  │  • confidence_score ↑         │  • is_canonical = 1                 │   │     │
│    │  │  • decay_factor = 1.0         │  • source_episodes_json populated   │   │     │
│    │  │  • last_observed_at = now     │                                     │   │     │
│    │  │                               │                                     │   │     │
│    │  ├───────────────────────────────┼─────────────────────────────────────│   │     │
│    │  │                               │                                     │   │     │
│    │  │  EXTEND:                      │  EVOLVE:                            │   │     │
│    │  │  • Append to source_episodes  │  • version += 1                     │   │     │
│    │  │  • Merge new attributes       │  • supersedes_id = old_id           │   │     │
│    │  │  • Update context_json        │  • old.is_canonical = 0             │   │     │
│    │  │                               │  • new.is_canonical = 1             │   │     │
│    │  │                               │                                     │   │     │
│    │  ├───────────────────────────────┴─────────────────────────────────────│   │     │
│    │  │                                                                     │   │     │
│    │  │  PRUNE:                                                             │   │     │
│    │  │  • decay_factor *= exp(-λ * days)                                   │   │     │
│    │  │  • If decay < 0.1: archival_status = 'ARCHIVED'                     │     │     │
│    │  │  • If decay < 0.01: archival_status = 'TOMBSTONE'                   │     │     │
│    │  │                                                                     │     │     │
│    │  └─────────────────────────────────────────────────────────────────────┘     │     │
│    │                                                                              │     │
│    └──────────────────────────────────────────────────────────────────────────────┘     │
│                                          │                                              │
│                                          │ R8: Emit events                              │
│                                          ▼                                              │
│    ┌──────────────────────────────────────────────────────────────────────────────┐     │
│    │                           K0 BUS (Event Emission)                            │     │
│    │                                                                              │     │
│    │  • p03.consolidation.complete.v1                                             │     │
│    │  • p03.pattern.detected.v1                                                   │     │
│    │  • p03.truth.reinforced.v1                                                   │     │
│    │  • p03.truth.created.v1                                                      │     │
│    │  • p03.truth.evolved.v1                                                      │     │
│    │  • p03.memory.pruned.v1                                                      │     │
│    │                                                                              │     │
│    └──────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Phase Specifications (R0-R8)

> **Status**: IN PROGRESS — Core structure complete, algorithm details pending

### 4.0 Phase Overview Diagram

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                       P03 CONSOLIDATION PHASE STATE MACHINE                               │
│                                                                                           │
│   ┌──────────────────────────────────────────────────────────────────────────────────--┐  │
│   │                              Sleep Cycle Metaphor                                  │  │
│   │                                                                                    │  │
│   │      WAKING                                                                        │  │
│   │         │                                                                          │  │
│   │         ▼                                                                          │  │
│   │   ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐      │  │
│   │   │   R0    │────▶│   R1    │────▶│   R2    │────▶│   R3    │────▶│   R4    │      │  │
│   │   │ Trigger │     │ Replay  │     │Integrate│     │ Forget  │     │ KG Cons │      │  │
│   │   │ (NREM0) │     │ (NREM1) │     │ (NREM2) │     │ (NREM3) │     │ (NREM4) │      │  │
│   │   └────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘      │  │
│   │        │               │               │               │               │           │  │
│   │        │               │               │               │               │           │  │
│   │        │               │               │               │               ▼           │  │
│   │        │               │               │               │         ┌─────────┐       │  │
│   │        │               │               │               └────────▶│   R5    │       │  │
│   │        │               │               │                         │ Dream   │       │  │
│   │        │               │               │                         │  (REM)  │       │  │
│   │        │               │               │                         └────┬────┘       │  │
│   │        │               │               │                              │            │  │
│   │        │               │               │                              ▼            │  │
│   │        │               │               │                         ┌─────────┐       │  │
│   │        │               │               └────────────────────────▶│   R6    │       │  │
│   │        │               │                                         │ Staging │       │  │
│   │        │               │                                         │ Update  │       │  │
│   │        │               │                                         └────┬────┘       │  │
│   │        │               │                                              │            │  │
│   │        │               │                                              ▼            │  │
│   │        │               │                                         ┌─────────┐       │  │
│   │        │               └────────────────────────────────────────▶│   R7    │       │  │
│   │        │                                                         │ Truth   │       │  │
│   │        │                                                         │ Write   │       │  │
│   │        │                                                         └────┬────┘       │  │
│   │        │                                                              │            │  │
│   │        │                                                              ▼            │  │
│   │        │                                                         ┌─────────┐       │  │
│   │        └────────────────────────────────────────────────────────▶│   R8    │       │  │
│   │                                                                  │Complete │       │  │
│   │                                                                  └────┬────┘       │  │
│   │                                                                       │            │  │
│   └───────────────────────────────────────────────────────────────────────┼────────────┘  │
│                                                                           │               │
│                                                                           ▼               │
│                                                                    ┌───────────┐          │
│                                                                    │  COMPLETE │          │
│                                                                    └───────────┘          │
│                                                                                           │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Phase Timing Constraints

| Phase | Target Duration | Max Duration | Abort Trigger |
|-------|---------------─-|--------------|---------------|
| R0 | <1s | 5s | Lock contention |
| R1 | 10-30s | 60s | User activity |
| R2 | 30-120s | 300s | Memory pressure |
| R3 | 10-30s | 60s | — |
| R4 | 30-120s | 300s | — |
| R5 | 10-60s | 120s | Skip if backlog |
| R6 | 5-15s | 30s | — |
| R7 | 10-30s | 60s | Transaction timeout |
| R8 | <1s | 5s | — |

#### Phase Transition Rules

```python
class PhaseTransition:
    """Rules for P03 phase state machine transitions."""

    TRANSITIONS = {
        'R0_TRIGGER':   ['R1_REPLAY', 'ABORT'],
        'R1_REPLAY':    ['R2_INTEGRATE', 'ABORT'],
        'R2_INTEGRATE': ['R3_FORGET', 'R6_STAGING'],  # Skip R3-R5 if minimal work
        'R3_FORGET':    ['R4_KG', 'R6_STAGING'],
        'R4_KG':        ['R5_DREAM', 'R6_STAGING'],   # R5 optional
        'R5_DREAM':     ['R6_STAGING'],
        'R6_STAGING':   ['R7_WRITE'],
        'R7_WRITE':     ['R8_COMPLETE'],
        'R8_COMPLETE':  ['IDLE'],
        'ABORT':        ['IDLE'],
    }

    @staticmethod
    def can_skip_dream_phase(cycle_context: 'CycleContext') -> bool:
        """R5 can be skipped if backlog is high or time is constrained."""
        return (
            cycle_context.backlog_size > 1000 or
            cycle_context.remaining_window_seconds < 60
        )
```

#### Abort & Recovery Semantics

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ABORT HANDLING BY PHASE                         │
│                                                                         │
│   Phase     │ Abort Cause        │ Cleanup Action        │ Resume From  │
│   ──────────┼────────────────────┼───────────────────────┼─────────────-│
│   R0        │ Lock timeout       │ Release lock          │ R0           │
│   R1        │ User activity      │ Mark batch incomplete │ R0 (retry)   │
│   R2        │ Memory pressure    │ Flush partial results │ R2           │
│   R3-R5     │ Timeout            │ Save checkpoint       │ Current      │
│   R6        │ Write conflict     │ Rollback staging      │ R6           │
│   R7        │ Transaction fail   │ Rollback via st_outbox│ R7           │
│   R8        │ Bus unavailable    │ Queue events locally  │ R8           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.1 R0 — Trigger Detection & Sleep Onset

#### 4.1.1 Trigger Mechanisms

- Scheduled triggers (cron-based, configurable)
- Idle detection (Query Port monitoring)
- Event-based triggers (threshold reached)
- Manual triggers (admin/debug)

#### 4.1.2 Sleep State Machine

- States: IDLE → NREM1 → NREM2 → REM → WAKING → COMPLETE
- Transition conditions and timing
- Abort conditions (user activity detected)

#### 4.1.3 Batch Selection Criteria

- `consolidation_status = NULL` filter
- Recency window (events from last N hours)
- Priority ordering (importance_score DESC)
- Batch size limits (configurable)

#### 4.1.4 Pre-Flight Checks

- Resource availability (CPU, memory thresholds)
- Concurrent consolidation prevention (distributed lock)
- User activity monitoring (yield to interactive queries)

---

### 4.2 R1 — Hippocampal Replay (NREM1)

#### 4.2.1 CA3 Coordinator Pattern

- Replay at accelerated speed (10-20x metaphor)
- Sharp-Wave Ripple simulation (batch processing windows)

#### 4.2.2 Importance Scoring Algorithm

- Formula implementation (see Section 2.4)
- Weight tuning per memory layer
- Emotional salience extraction from affect scores

#### 4.2.3 Association Strengthening (Hebbian Learning)

- Co-occurrence counting algorithm
- Temporal proximity bonus calculation
- Context diversity scoring

#### 4.2.4 Theta Rhythm Coordination

- Batch pacing and timing
- Interleaving with user activity checks

---

### 4.3 R2 — Neocortical Integration (NREM2)

#### 4.3.1 Episodic Clustering (DBSCAN)

- UltraBERT embedding similarity
- Hyperparameters: eps, min_samples
- Cluster quality metrics

#### 4.3.2 Pattern Extraction Pipeline

- Routine detection (temporal patterns)
- Preference extraction (repeated choices)
- Theme identification (semantic clustering)
- Relationship patterns (social graph mining)

#### 4.3.3 CA1 Bridge Integration (Truth Query)

- **CRITICAL**: This is where bidirectional reconciliation happens
- Query existing st_sem for matching patterns
- Compare new clusters vs existing truth
- Decision matrix: MERGE / EVOLVE / CREATE

#### 4.3.4 Consolidation Quality Gates

- Minimum cluster size thresholds
- Confidence score requirements
- Temporal spread requirements

---

### 4.4 R3 — Synaptic Homeostasis (Forgetting)

#### 4.4.1 Deduplication Algorithm (SimHash)

- 64-bit SimHash fingerprint comparison
- Hamming distance threshold (≤3 = near-duplicate)
- MinHash LSH for scale (100K+ events)

#### 4.4.2 Novelty Scoring

- Formula implementation (see Section 2.4)
- First-time activity bonus
- Milestone event detection
- Temporal anomaly detection

#### 4.4.3 Retention Policy Enforcement

- Layer-specific decay constants (λ)
- decay_factor calculation and application
- Decay thresholds: ACTIVE → ARCHIVED → TOMBSTONE

#### 4.4.4 Stale Memory Detection

- Last observation age analysis
- Access frequency decay
- Contradiction accumulation

#### 4.4.5 Tombstone Creation & Garbage Collection

- Soft delete with tombstone record
- Archival to cold storage
- Hard delete after retention period

---

### 4.5 R4 — Knowledge Graph Consolidation

#### 4.5.1 Entity Extraction & Normalization

- UltraBERT NER output processing
- Entity deduplication (same entity, different mentions)
- Canonical name resolution

#### 4.5.2 Relationship Discovery

- Co-occurrence analysis (Hebbian edges)
- Explicit relationship extraction (NLP)
- Temporal relationship inference

#### 4.5.3 Temporal Graph Updates

- valid_from / valid_to management
- Version chain maintenance
- supersedes_id linking

#### 4.5.4 Causal Inference (Granger Causality)

- Event sequence analysis
- Causal relationship strength scoring
- Confidence intervals

#### 4.5.5 Concept Evolution Tracking

- Schema drift detection
- Attribute evolution (e.g., preferences change)
- **Integration Point**: Emit to P06 Active Learning for validation

---

### 4.6 R5 — Dream-Like Exploration (REM)

#### 4.6.1 Counterfactual Thinking (CPN Algorithm)

- "What if" scenario generation
- Causal perturbation network
- Insight extraction from counterfactuals

#### 4.6.2 Forward Simulation (TPN-MCTS)

- Future scenario prediction
- Monte Carlo Tree Search for exploration
- Probability estimation for outcomes

#### 4.6.3 Episodic Simulation (SPC-UQ)

- Recombination of episode fragments
- Novelty vs coherence balance
- Uncertainty quantification

#### 4.6.4 Insight Generation (BGT-SM)

- Remote association discovery (Mednick)
- Cross-domain pattern matching
- Creative connection scoring

#### 4.6.5 Motor Rehearsal Analog (TDL-HCO)

- Procedural memory optimization
- Habit pattern reinforcement
- Skill generalization

#### 4.6.6 R5 Complexity Assessment

> **Implementation Status**: R5 is optional and skipped when backlog > 500 events or time constraints apply.

| Algorithm | Complexity | Latency (P95) | MVP Alternative | Production Readiness |
|-----------|------------|---------------|-----------------|----------------------|
| **CPN** (Counterfactual) | O(n × k) perturbations | ~300ms | Skip entirely | 🎯 Phase 2 |
| **TPN-MCTS** (Forward Sim) | O(d × b^h) where b=branching, h=horizon | ~500ms @ 100 rollouts | Reduce to 10 rollouts | 🎯 Phase 2 |
| **BGT-SM** (Remote Assoc) | O(n × w) random walks | ~400ms | Limit walks to 3 | 🎯 Phase 2 |
| **SPC-UQ** (Episodic Sim) | O(f × c) fragment combinations | ~200ms | Skip entirely | 🎯 Phase 2 |
| **TDL-HCO** (Motor Rehearsal) | O(p) patterns | ~100ms | Keep (lightweight) | ✅ MVP |

**MVP Recommendation**: For initial release, set `P03_FF_R5_MODE=disabled` and enable TDL-HCO only. Full R5 implementation deferred to Phase 2 when GPU inference is available.

**Reproducibility Concerns**:

- BGT-SM random walks: Seed with `cycle_ulid` for deterministic behavior in tests
- TPN-MCTS: Use fixed seed for rollout sampling in CI
- CPN: Perturbation order deterministic when sorted by entity_id

---

### 4.7 R6 — Staging Table Updates

#### 4.7.1 Consolidation Status Marking

- Update st_hipp_events with consolidation_status
- Status values: CONSOLIDATED, DUPLICATE, PRUNED, PENDING_REVIEW

#### 4.7.2 Deduplication Metadata

- near_duplicates_json population
- novelty_score persistence
- episode_cluster_id assignment

#### 4.7.3 Reconciliation Decision Recording

- Store decision type per event
- Link to target truth record
- Confidence and similarity scores

---

### 4.8 R7 — Memory Layer Writes (Truth Update)

#### 4.8.1 Outbox Pattern Implementation

- INSERT via st_outbox for durability
- P08 coordination for indexing
- Transaction boundaries

#### 4.8.2 st_epi (Episodic) Writes

- Episode clustering results
- Source event linking
- Temporal anchoring

#### 4.8.3 st_sem (Semantic) Writes

- Pattern records with confidence
- source_episodes_json population
- observation_count / last_observed_at

#### 4.8.4 st_procedural (Habits) Writes

- Routine patterns
- Temporal regularity scores
- Action sequence encoding

#### 4.8.5 st_social (Relationships) Writes

- Relationship strength updates
- Interaction frequency tracking
- Sentiment aggregation

#### 4.8.6 st_prospective (Intentions) Writes

- Future-oriented patterns
- Goal inference results
- Reminder generation hints

#### 4.8.7 st_kg_dom / st_kg_edges (KG) Writes

- Entity canonical records
- Relationship edges with confidence
- Temporal validity windows

#### 4.8.8 st_vec (Embeddings) Writes

- Aggregated embeddings for patterns
- Index update coordination with P08

---

### 4.9 R8 — Event Emission & Completion

#### 4.9.1 Bus Event Emission

- Topic: `p03.consolidation.complete.v1`
- Topic: `p03.pattern.detected.v1`
- Topic: `p03.truth.reinforced.v1`
- Topic: `p03.truth.created.v1`
- Topic: `p03.truth.evolved.v1`
- Topic: `p03.memory.pruned.v1`
- **NEW**: Topic: `p03.gap.detected.v1` (for P06 Active Learning)

#### 4.9.2 Pipeline Offset Updates

- st_pipeline_offsets with last processed event_id
- Checkpoint for resume capability

#### 4.9.3 Metrics Aggregation

- Consolidation cycle duration
- Events processed count
- Decisions by type (REINFORCE, EXTEND, CREATE, EVOLVE, PRUNE)
- Error counts and categories

---

### 4.10 K0 Kernel Enhancements Required

> **Status**: 📋 K0 Enhancement Requests
> **Reference**: [k0_source_of_truth_postgresql.mmd](../../architecture_diagrams/k0/k0_source_of_truth_postgresql.mmd)
> **Migration Note** (2025-01): K0 now uses PostgreSQL 16+ via asyncpg. Diagram reference updated.

P03's concurrency requirements exceed what K0 currently provides. This section documents **kernel-level enhancements** needed to support P03 consolidation in multi-instance deployments.

#### 4.10.1 Current K0 Capabilities (Sufficient)

K0 already provides these concurrency primitives that P03 will use:

| K0 Component | Location | P03 Usage |
|--------------|----------|-----------|
| `PipelineScheduler` | `k0/scheduler/scheduler.py` | Trigger consolidation cycles |
| `TriggerEngine` | `k0/scheduler/triggers.py` | INTERVAL, THRESHOLD, MANUAL triggers |
| `UnitOfWork` | `k0/uow/unit_of_work.py` | Atomic transactions for R7 writes |
| `QoSContext` | `k0/qos/context.py` | Resource budgeting per cycle |
| `PipelineProtocol.concurrency` | `k0/pipelines/` | Max concurrent handlers |

#### 4.10.2 K0 Enhancement: Advisory Lock Service

**Gap**: K0 lacks a distributed locking primitive for pipelines that need single-writer semantics per partition (tenant/space).

**Proposed K0 Component**: `k0/sync/advisory_lock.py`

```python
# Proposed K0 API
class AdvisoryLockService:
    """K0 kernel service for distributed advisory locks."""

    async def acquire(
        self,
        lock_key: str,
        holder_id: str,
        ttl_seconds: int = 300
    ) -> LockResult:
        """Acquire an advisory lock with TTL-based expiry."""
        ...

    async def release(self, lock_key: str, holder_id: str) -> bool:
        """Release a held lock."""
        ...

    async def heartbeat(self, lock_key: str, holder_id: str) -> bool:
        """Extend lock TTL while processing."""
        ...
```

**P03 Requirement**: Per-space consolidation locks to prevent concurrent cycles on same space.

**Lock Key Pattern**: `{pipeline_id}:{tenant_id}:{space_id}`

**ADR Required**: `k0XX-advisory-lock-service.md`

#### 4.10.3 K0 Enhancement: Partitioned Pipeline Execution

**Gap**: `PipelineScheduler` triggers pipelines globally but doesn't support partitioned execution where different nodes handle different tenant/space partitions.

**Proposed Enhancement to `PipelineScheduler`**:

```python
# Proposed extension to k0/scheduler/scheduler.py
class ScheduledPipeline:
    # Existing fields...
    partition_key: Optional[str] = None  # e.g., "tenant_id:space_id"
    partition_strategy: PartitionStrategy = PartitionStrategy.NONE

class PartitionStrategy(Enum):
    NONE = "none"           # Current behavior (global)
    TENANT = "tenant"       # One partition per tenant
    SPACE = "space"         # One partition per tenant:space
    CONSISTENT_HASH = "consistent_hash"  # Distribute across nodes
```

**P03 Requirement**: Consolidation should run independently per space, allowing parallel processing across spaces while preventing concurrent runs within the same space.

**ADR Required**: `k0XX-partitioned-pipeline-execution.md`

#### 4.10.4 K0 Enhancement: Optimistic Concurrency in UnitOfWork

**Gap**: K0 `UnitOfWork` provides transaction boundaries but doesn't include version-based optimistic locking helpers.

**Proposed Enhancement to `k0/uow/unit_of_work.py`**:

```python
# Proposed extension
class UnitOfWork:
    # Existing methods...

    def execute_with_version_check(
        self,
        sql: str,
        params: tuple,
        expected_version_column: str = "version"
    ) -> VersionedWriteResult:
        """
        Execute update with optimistic concurrency check.

        Returns VersionedWriteResult with:
        - rows_affected: int
        - version_conflict: bool (True if 0 rows affected)
        - should_retry: bool
        """
        ...
```

**P03 Requirement**: R7 truth writes need version-based conflict detection without custom SQL patterns in every pipeline.

**ADR Required**: `k0XX-optimistic-concurrency-uow.md`

#### 4.10.5 K0 Enhancement: Pipeline Execution Context

**Gap**: Pipelines need access to node identity and partition assignment for distributed coordination.

**Proposed Enhancement to `PipelineContext`**:

```python
# Proposed extension to k0/pipelines/
class PipelineContext:
    # Existing fields...
    node_id: str                    # Unique identifier for this K0 instance
    partition_assignment: Optional[PartitionAssignment]  # Which partitions this node owns

@dataclass
class PartitionAssignment:
    partitions: List[str]           # Assigned partition keys
    total_nodes: int                # Total nodes in cluster
    assignment_version: int         # For rebalancing detection
```

**P03 Requirement**: Consolidation cycles need to know which tenant/space combinations to process on this node.

**ADR Required**: `k0XX-pipeline-execution-context.md`

#### 4.10.6 P03 Implementation with PostgreSQL (K0 Native Features)

> **Updated 2025-12-24**: K0 migrated from SQLite to PostgreSQL 16+ (see `k0/docs/k0_postgresql_migration_plan.md`). Many proposed K0 enhancements are now available natively.

With PostgreSQL as the K0 storage backend, P03 leverages native database features:

| K0 Need | PostgreSQL Solution | Status |
|---------|---------------------|--------|
| Advisory locks | `pg_advisory_lock()` / `pg_try_advisory_lock()` | ✅ Native PostgreSQL |
| Partitioned execution | `FOR UPDATE SKIP LOCKED` + K0 Scheduler | 🔄 Scheduler enhancement still needed |
| Optimistic concurrency | `RETURNING` clause + row versioning in UoW | ✅ Native via asyncpg |
| Node identity | `pg_stat_activity.application_name` + env var | ✅ Enhanced with PostgreSQL |

**PostgreSQL Implementation References**:

- Connection pool: `k0/db/pool.py` (asyncpg.Pool with pgbouncer support)
- Configuration: `k0/config/postgres.py` (PostgresSettings)
- Driver: `k0/drivers/postgres.py` (PostgresDriver with ACID transactions)
- UoW: `k0/uow/unit_of_work.py` (async PostgreSQL transactions)

#### 4.10.7 ADR Tracking

| ADR ID | Title | Status | Priority |
|--------|-------|--------|----------|
| k0XX | Advisory Lock Service | ✅ SUPERSEDED — PostgreSQL native `pg_advisory_lock()` | N/A |
| k0XX | Partitioned Pipeline Execution | 📋 Proposed | P1 (Multi-node) |
| k0XX | Optimistic Concurrency in UoW | ✅ SUPERSEDED — PostgreSQL `RETURNING` + asyncpg | N/A |
| k0XX | Pipeline Execution Context | 📋 Proposed | P2 (Cluster awareness) |

> **Note (2025-12-24)**: With K0 PostgreSQL migration complete, advisory locks and optimistic concurrency are now available natively. Partitioned pipeline execution and cluster awareness remain proposed enhancements.

---

## 5. P06 Active Learning Integration

> **Status**: COMPLETE
> **Reference**: [Idea-0001: Active Learning Loop](../architecture/ideas/0001-active-learning-loop.md)

### 5.1 Overview: P03 as the "Observer Brain"

P03 acts as the **passive observer** that detects knowledge gaps during consolidation. P06 is the **curious mind** that proactively seeks to fill those gaps through targeted questions. Together, they implement a closed-loop learning system.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                       P03 ↔ P06 CLOSED-LOOP LEARNING ARCHITECTURE                        │
│                                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              P03 CONSOLIDATION                                    │   │
│   │                            (The Observer Brain)                                   │   │
│   │                                                                                   │   │
│   │   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐            │   │
│   │   │ Gap Detection    │   │ Entropy Scanner  │   │ Contradiction    │            │   │
│   │   │ (During R2-R4)   │   │ (Background Job) │   │ Detector (R7)    │            │   │
│   │   └────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘            │   │
│   │            │                      │                      │                       │   │
│   │            └──────────────────────┼──────────────────────┘                       │   │
│   │                                   │                                              │   │
│   │                                   ▼                                              │   │
│   │                    ┌──────────────────────────────┐                              │   │
│   │                    │     Gap Emission (R8)        │                              │   │
│   │                    │   p03.gap.detected.v1        │                              │   │
│   │                    └──────────────┬───────────────┘                              │   │
│   └───────────────────────────────────┼─────────────────────────────────────────────┘   │
│                                       │                                                  │
│                                       ▼                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              P06 ACTIVE LEARNING                                  │   │
│   │                             (The Curious Mind)                                    │   │
│   │                                                                                   │   │
│   │   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐            │   │
│   │   │ Priority Queue   │──▶│ Context Matcher  │──▶│ Question Framer  │            │   │
│   │   │ (importance_score)│   │ (wait for topic) │   │ (gap → question) │            │   │
│   │   └──────────────────┘   └──────────────────┘   └────────┬─────────┘            │   │
│   │                                                          │                       │   │
│   │                                                          ▼                       │   │
│   │                                               ┌──────────────────┐               │   │
│   │                                               │ Attention Budget │               │   │
│   │                                               │ (Token Bucket)   │               │   │
│   │                                               └────────┬─────────┘               │   │
│   └────────────────────────────────────────────────────────┼────────────────────────┘   │
│                                                            │                             │
│                                                            ▼                             │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                                K1 EXPERIENCE                                      │   │
│   │                                                                                   │   │
│   │   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐            │   │
│   │   │ Curiosity Agent  │──▶│ User Interaction │──▶│ Answer Captured  │            │   │
│   │   │ (formulates Q)   │   │ (asks question)  │   │ (via P02)        │            │   │
│   │   └──────────────────┘   └──────────────────┘   └────────┬─────────┘            │   │
│   └──────────────────────────────────────────────────────────┼──────────────────────┘   │
│                                                              │                           │
│                                                              ▼                           │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              P02 INGESTION                                        │   │
│   │                                                                                   │   │
│   │   User answer → Envelope → st_hipp_events (with gap_resolution_id tag)           │   │
│   │                                                                                   │   │
│   └──────────────────────────────────────────────────────────┬──────────────────────┘   │
│                                                              │                           │
│                                                              ▼                           │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              P03 RE-CONSOLIDATION                                 │   │
│   │                                                                                   │   │
│   │   Next cycle: event with gap_resolution_id → resolve gap → update truth          │   │
│   │                                                                                   │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Gap Detection During Reconciliation

#### 5.2.1 Gap Types Detected by P03

| Gap Type | Detection Phase | Trigger Condition | Priority |
|----------|-----------------|-------------------|----------|
| **AMBIGUOUS_ENTITY** | R4 (KG Consolidation) | Multiple entity candidates, max confidence < 0.7 | HIGH |
| **LOW_CONFIDENCE_EDGE** | R4 (KG Consolidation) | Relationship confidence < 0.6 after N observations | MEDIUM |
| **MISSING_ATTRIBUTE** | R4 (KG Consolidation) | Ontology-required attribute NULL for entity | MEDIUM |
| **CONTRADICTION** | R7 (Truth Write) | Semantic conflict with existing truth | HIGH |
| **CONCEPT_DRIFT** | R3 (Forgetting) | Anchor confidence shifted >20% in 30 days | LOW |
| **STRUCTURAL_HOLE** | R5 (Dream) | Missing expected edge in KG (predicted but absent) | LOW |
| **STALE_ANCHOR** | Background Scan | Anchor not updated in 90+ days | LOW |

#### 5.2.2 Gap Detection Algorithm (R4/R7)

```python
class GapDetector:
    """M25 — Detects knowledge gaps during reconciliation."""

    def detect_gaps(
        self,
        reconciliation_result: ReconciliationResult,
        config: GapDetectionConfig
    ) -> List[GapRecord]:
        """
        Analyze reconciliation decisions for potential gaps.

        Called after each batch of events is reconciled.
        """
        gaps = []

        for decision in reconciliation_result.decisions:
            # Check for ambiguous entity resolution
            if decision.type == 'CREATE' and decision.candidates:
                if self._is_ambiguous(decision.candidates, config.ambiguity_threshold):
                    gaps.append(self._create_gap(
                        gap_type='AMBIGUOUS_ENTITY',
                        decision=decision,
                        candidates=decision.candidates
                    ))

            # Check for low-confidence edges
            if decision.type in ('EXTEND', 'CREATE') and decision.target_type == 'KG_EDGE':
                if decision.confidence < config.edge_confidence_threshold:
                    gaps.append(self._create_gap(
                        gap_type='LOW_CONFIDENCE_EDGE',
                        decision=decision,
                        current_confidence=decision.confidence
                    ))

            # Check for contradictions
            if decision.type == 'CONTRADICT':
                gaps.append(self._create_gap(
                    gap_type='CONTRADICTION',
                    decision=decision,
                    conflict_details=decision.conflict_evidence
                ))

        return gaps

    def _is_ambiguous(
        self,
        candidates: List[EntityCandidate],
        threshold: float
    ) -> bool:
        """Multiple candidates with similar confidence = ambiguous."""
        if len(candidates) < 2:
            return False

        sorted_candidates = sorted(candidates, key=lambda c: c.confidence, reverse=True)
        confidence_gap = sorted_candidates[0].confidence - sorted_candidates[1].confidence

        return confidence_gap < threshold  # e.g., < 0.15 means too close to call

    def _create_gap(
        self,
        gap_type: str,
        decision: ReconciliationDecision,
        **context
    ) -> GapRecord:
        """Create a gap record for P06."""
        return GapRecord(
            id=generate_ulid(),
            gap_type=gap_type,
            tenant_id=decision.tenant_id,
            space_id=decision.space_id,
            entity_id=decision.entity_id,
            related_event_id=decision.source_event_id,
            related_truth_id=decision.target_truth_id,
            confidence_score=decision.confidence,
            entropy_score=self._calculate_entropy(decision, context),
            context_json=json.dumps(context),
            status='PENDING',
            created_at=int(time.time()),
            expires_at=int(time.time()) + (7 * 24 * 3600),  # 7 day expiry
            consolidation_cycle_id=decision.cycle_id
        )

    def _calculate_entropy(
        self,
        decision: ReconciliationDecision,
        context: dict
    ) -> float:
        """
        Calculate entropy (uncertainty) for priority scoring.

        Higher entropy = more uncertain = higher priority for questions.
        """
        if 'candidates' in context:
            # Shannon entropy over candidate distribution
            probs = [c.confidence for c in context['candidates']]
            total = sum(probs)
            probs = [p / total for p in probs]
            entropy = -sum(p * math.log2(p + 1e-10) for p in probs)
            return min(entropy / math.log2(len(probs)), 1.0)  # Normalize to [0,1]

        # Default: inverse of confidence
        return 1.0 - decision.confidence
```

#### 5.2.3 Gap Emission Protocol

```python
class GapEmitter:
    """Emit detected gaps to P06 via event bus."""

    async def emit_gaps(
        self,
        gaps: List[GapRecord],
        bus: EventBus
    ) -> None:
        """
        Emit gap records to P06 Active Learning pipeline.

        Protocol:
        1. Persist gaps to st_learning_queue (for durability)
        2. Emit p03.gap.detected.v1 event to bus
        3. P06 consumes and processes
        """
        for gap in gaps:
            # 1. Persist to learning queue
            await self.db.insert('st_learning_queue', gap.to_dict())

            # 2. Emit to bus
            await bus.publish(
                topic='p03.gap.detected.v1',
                payload={
                    'gap_id': gap.id,
                    'gap_type': gap.gap_type,
                    'tenant_id': gap.tenant_id,
                    'space_id': gap.space_id,
                    'importance_score': gap.importance_score,
                    'context': json.loads(gap.context_json),
                    'created_at': gap.created_at
                },
                key=f"{gap.tenant_id}:{gap.space_id}"  # Partition key
            )
```

### 5.3 Entropy Scanning (Proactive Gap Detection)

The Entropy Scanner is a **background process** that proactively identifies knowledge gaps without waiting for new events to trigger consolidation.

#### 5.3.1 Scan Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ENTROPY SCANNER ARCHITECTURE                         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         Scan Scheduler                               │   │
│   │                                                                      │   │
│   │   Triggers:                                                          │   │
│   │   • Cron: "0 4 * * *" (4 AM daily)                                  │   │
│   │   • Post-consolidation: after P03 cycle completes                    │   │
│   │   • Manual: admin API call                                          │   │
│   │                                                                      │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        Scan Executors (Parallel)                     │   │
│   │                                                                      │   │
│   │   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │   │
│   │   │ Ontology      │  │ Anchor Decay  │  │ Structural    │           │   │
│   │   │ Validator     │  │ Detector      │  │ Hole Finder   │           │   │
│   │   │               │  │               │  │               │           │   │
│   │   │ Checks:       │  │ Checks:       │  │ Checks:       │           │   │
│   │   │ • Required    │  │ • Stale       │  │ • Missing     │           │   │
│   │   │   attributes  │  │   anchors     │  │   edges       │           │   │
│   │   │ • Type        │  │ • Confidence  │  │ • Sparse      │           │   │
│   │   │   constraints │  │   drift       │  │   subgraphs   │           │   │
│   │   └───────────────┘  └───────────────┘  └───────────────┘           │   │
│   │                                                                      │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      Gap Aggregator & Deduplicator                   │   │
│   │                                                                      │   │
│   │   • Deduplicate against existing st_learning_queue entries          │   │
│   │   • Apply rate limiting (max N gaps per scan)                       │   │
│   │   • Priority sort by importance_score                               │   │
│   │                                                                      │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│                              st_learning_queue                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 5.3.2 Scan Algorithms

```python
class EntropyScanners:
    """Collection of proactive gap detection algorithms."""

    async def scan_ontology_violations(
        self,
        tenant_id: str,
        ontology: OntologySchema
    ) -> List[GapRecord]:
        """
        Find entities missing required attributes per ontology.

        Example: PERSON entity requires 'birthday' attribute.
        """
        gaps = []

        for entity_type, requirements in ontology.required_attributes.items():
            query = """
                SELECT entity_id, canonical_name, attributes_json
                FROM st_kg_dom
                WHERE tenant_id = :tenant_id
                  AND entity_type = :entity_type
                  AND is_canonical = TRUE
                  AND archival_status = 'ACTIVE'
            """
            entities = await self.db.fetch_all(query, {
                'tenant_id': tenant_id,
                'entity_type': entity_type
            })

            for entity in entities:
                attrs = json.loads(entity['attributes_json'] or '{}')
                for required_attr in requirements:
                    if required_attr not in attrs or attrs[required_attr] is None:
                        gaps.append(GapRecord(
                            gap_type='MISSING_ATTRIBUTE',
                            entity_id=entity['entity_id'],
                            context_json=json.dumps({
                                'entity_name': entity['canonical_name'],
                                'entity_type': entity_type,
                                'missing_attribute': required_attr,
                                'suggested_question': f"What is {entity['canonical_name']}'s {required_attr}?"
                            }),
                            entropy_score=0.5,  # Medium priority
                            confidence_score=0.0  # No data
                        ))

        return gaps

    async def scan_anchor_decay(
        self,
        tenant_id: str,
        stale_threshold_days: int = 90
    ) -> List[GapRecord]:
        """
        Find anchors that haven't been updated recently.

        Stale anchors may reflect outdated beliefs about users.
        """
        cutoff = int(time.time()) - (stale_threshold_days * 24 * 3600)

        query = """
            SELECT entity_id, attribute, alpha, beta, confidence, last_updated_at
            FROM st_anchors
            WHERE tenant_id = :tenant_id
              AND status = 'ACTIVE'
              AND last_updated_at < :cutoff
            ORDER BY confidence DESC
            LIMIT 100
        """
        stale_anchors = await self.db.fetch_all(query, {
            'tenant_id': tenant_id,
            'cutoff': cutoff
        })

        gaps = []
        for anchor in stale_anchors:
            gaps.append(GapRecord(
                gap_type='STALE_ANCHOR',
                entity_id=anchor['entity_id'],
                context_json=json.dumps({
                    'attribute': anchor['attribute'],
                    'current_confidence': anchor['confidence'],
                    'last_updated': anchor['last_updated_at'],
                    'days_stale': (int(time.time()) - anchor['last_updated_at']) // 86400,
                    'suggested_question': self._generate_anchor_question(
                        anchor['entity_id'], anchor['attribute']
                    )
                }),
                entropy_score=anchor['confidence'] * 0.3,  # Lower priority for high-confidence
                confidence_score=anchor['confidence']
            ))

        return gaps

    async def scan_structural_holes(
        self,
        tenant_id: str,
        expected_edges: List[ExpectedEdgePattern]
    ) -> List[GapRecord]:
        """
        Find missing relationships that are expected based on patterns.

        Example: Person A and Person B both attend same events but have no relationship edge.
        """
        gaps = []

        for pattern in expected_edges:
            # Find entity pairs that match the pattern but lack the expected edge
            query = """
                WITH CoOccurrences AS (
                    SELECT
                        h1.actor_id AS entity_a,
                        h2.actor_id AS entity_b,
                        COUNT(*) AS co_occurrence_count
                    FROM st_hipp_events h1
                    JOIN st_hipp_events h2
                      ON h1.event_id = h2.event_id
                     AND h1.actor_id < h2.actor_id
                    WHERE h1.tenant_id = :tenant_id
                    GROUP BY h1.actor_id, h2.actor_id
                    HAVING COUNT(*) >= :min_co_occurrences
                )
                SELECT c.entity_a, c.entity_b, c.co_occurrence_count
                FROM CoOccurrences c
                LEFT JOIN st_kg_edges e
                  ON (e.source_entity_id = c.entity_a AND e.target_entity_id = c.entity_b)
                  OR (e.source_entity_id = c.entity_b AND e.target_entity_id = c.entity_a)
                WHERE e.edge_id IS NULL  -- No existing relationship
            """
            missing_edges = await self.db.fetch_all(query, {
                'tenant_id': tenant_id,
                'min_co_occurrences': pattern.min_co_occurrences
            })

            for edge in missing_edges:
                gaps.append(GapRecord(
                    gap_type='STRUCTURAL_HOLE',
                    entity_id=edge['entity_a'],
                    context_json=json.dumps({
                        'entity_a': edge['entity_a'],
                        'entity_b': edge['entity_b'],
                        'co_occurrences': edge['co_occurrence_count'],
                        'suggested_question': f"How do you know {edge['entity_b']}?"
                    }),
                    entropy_score=0.6,
                    confidence_score=0.0
                ))

        return gaps
```

#### 5.3.3 Priority Scoring Formula

```python
def calculate_importance_score(gap: GapRecord) -> float:
    """
    Calculate priority score for gap queue ordering.

    Formula: importance = entropy × (1 / (confidence + 0.1)) × recency_boost × type_weight

    Higher score = ask sooner.
    """
    # Base: entropy inversely weighted by confidence
    base_score = gap.entropy_score * (1.0 / (gap.confidence_score + 0.1))

    # Recency boost: newer gaps get slight priority
    age_hours = (time.time() - gap.created_at) / 3600
    recency_boost = max(0.5, 1.0 - (age_hours / 168))  # Decays over 1 week

    # Type weight: some gap types are more actionable
    type_weights = {
        'CONTRADICTION': 1.5,       # Urgent: user may be confused
        'AMBIGUOUS_ENTITY': 1.3,    # Important for future interactions
        'MISSING_ATTRIBUTE': 1.0,   # Standard
        'LOW_CONFIDENCE_EDGE': 0.9,
        'CONCEPT_DRIFT': 0.7,
        'STRUCTURAL_HOLE': 0.6,
        'STALE_ANCHOR': 0.5,        # Low urgency
    }
    type_weight = type_weights.get(gap.gap_type, 1.0)

    return base_score * recency_boost * type_weight
```

### 5.4 Bayesian Anchor Points (User Modeling)

Anchors are **probabilistic beliefs** about user attributes, modeled as Beta distributions.

#### 5.4.1 Beta Distribution Primer

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       BETA DISTRIBUTION FOR BELIEFS                          │
│                                                                             │
│   Beta(α, β) models probability of binary outcome:                          │
│                                                                             │
│   • α = "successes" (evidence FOR)                                          │
│   • β = "failures" (evidence AGAINST)                                       │
│   • Mean = α / (α + β)  → Our confidence estimate                           │
│                                                                             │
│   Example: "Does user like spicy food?"                                     │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Day 1: No data                     Beta(1, 1) → Mean = 0.50       │   │
│   │          ████████████████████████████████                            │   │
│   │          ▲ Flat prior (maximum uncertainty)                          │   │
│   │                                                                     │   │
│   │   Day 7: 3 spicy meals observed      Beta(4, 1) → Mean = 0.80       │   │
│   │                        █████████████████████████                      │   │
│   │                        ▲ Skewed toward "yes"                         │   │
│   │                                                                     │   │
│   │   Day 30: 10 spicy, 2 mild           Beta(11, 3) → Mean = 0.79      │   │
│   │                     █████████████████████                             │   │
│   │                     ▲ More peaked (higher confidence)                │   │
│   │                                                                     │   │
│   │   Day 90: 20 spicy, 10 mild          Beta(21, 11) → Mean = 0.66     │   │
│   │                █████████████████████                                  │   │
│   │                ▲ Revised belief (user likes but not exclusively)     │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 5.4.2 Anchor Update During Consolidation

```python
class AnchorUpdater:
    """Updates Bayesian anchors during P03 consolidation."""

    async def update_from_events(
        self,
        events: List[HippEvent],
        anchor_extractors: Dict[str, AnchorExtractor]
    ) -> List[AnchorUpdate]:
        """
        Extract evidence from events and update anchor distributions.

        Called during R1 (Replay) phase.
        """
        updates = []

        for event in events:
            for attr_name, extractor in anchor_extractors.items():
                evidence = extractor.extract(event)
                if evidence is None:
                    continue

                # Get or create anchor
                anchor = await self._get_or_create_anchor(
                    entity_id=event.actor_id,
                    attribute=attr_name,
                    tenant_id=event.tenant_id
                )

                # Update Beta distribution
                if evidence.supports:
                    new_alpha = anchor.alpha + evidence.weight
                    new_beta = anchor.beta
                else:
                    new_alpha = anchor.alpha
                    new_beta = anchor.beta + evidence.weight

                # Apply temporal decay before update
                decay_factor = self._calculate_decay(anchor.last_updated_at)
                new_alpha = 1 + (new_alpha - 1) * decay_factor
                new_beta = 1 + (new_beta - 1) * decay_factor

                updates.append(AnchorUpdate(
                    entity_id=event.actor_id,
                    attribute=attr_name,
                    old_alpha=anchor.alpha,
                    old_beta=anchor.beta,
                    new_alpha=new_alpha,
                    new_beta=new_beta,
                    evidence_event_id=event.event_id,
                    supports=evidence.supports
                ))

        return updates

    def _calculate_decay(self, last_updated_at: int) -> float:
        """
        Calculate decay factor based on time since last update.

        Implements exponential decay: factor = exp(-λ × days)
        """
        if last_updated_at is None:
            return 1.0

        days_elapsed = (time.time() - last_updated_at) / 86400
        decay_rate = 0.001  # ~0.1% per day

        return math.exp(-decay_rate * days_elapsed)
```

#### 5.4.3 Anchor Extractors (Examples)

```python
# Example extractors for common attributes
ANCHOR_EXTRACTORS = {
    'prefers_spicy_food': SpicyFoodExtractor(),
    'is_morning_person': MorningPersonExtractor(),
    'prefers_outdoor_activities': OutdoorActivityExtractor(),
    'is_social': SocialBehaviorExtractor(),
}

class SpicyFoodExtractor(AnchorExtractor):
    """Extracts evidence about spicy food preference from meal events."""

    SPICY_KEYWORDS = {'spicy', 'hot', 'chili', 'jalapeño', 'sriracha', 'buffalo'}
    MILD_KEYWORDS = {'mild', 'plain', 'not spicy', 'no spice'}

    def extract(self, event: HippEvent) -> Optional[Evidence]:
        if event.activity_category != 'MEAL':
            return None

        text = (event.body_text or '').lower()

        if any(kw in text for kw in self.SPICY_KEYWORDS):
            return Evidence(supports=True, weight=1.0)
        if any(kw in text for kw in self.MILD_KEYWORDS):
            return Evidence(supports=False, weight=1.0)

        return None  # No evidence either way
```

#### 5.4.4 Drift Detection

```python
class DriftDetector:
    """Detects concept drift in anchor beliefs."""

    async def check_for_drift(
        self,
        anchor: Anchor,
        recent_observations: List[AnchorObservation],
        window_days: int = 30
    ) -> Optional[DriftResult]:
        """
        Compare recent confidence to historical confidence.

        Drift = |recent_mean - historical_mean| > threshold
        """
        if len(recent_observations) < 5:
            return None  # Not enough recent data

        # Calculate recent distribution
        recent_alpha = 1 + sum(1 for o in recent_observations if o.supports)
        recent_beta = 1 + sum(1 for o in recent_observations if not o.supports)
        recent_mean = recent_alpha / (recent_alpha + recent_beta)

        # Historical mean
        historical_mean = anchor.alpha / (anchor.alpha + anchor.beta)

        # Drift magnitude
        drift_magnitude = abs(recent_mean - historical_mean)

        if drift_magnitude > 0.20:  # 20% shift threshold
            return DriftResult(
                anchor=anchor,
                historical_mean=historical_mean,
                recent_mean=recent_mean,
                drift_magnitude=drift_magnitude,
                direction='UP' if recent_mean > historical_mean else 'DOWN'
            )

        return None
```

### 5.5 Contradiction Resolution Protocol

#### 5.5.1 Contradiction Detection Matrix

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CONTRADICTION DETECTION MATRIX                         │
│                                                                             │
│   New Signal vs Existing Truth Comparison:                                  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Similarity        Semantic          Classification                │   │
│   │   Score             Alignment         Result                        │   │
│   │   ─────────────────────────────────────────────────────────────    │   │
│   │                                                                     │   │
│   │   > 0.85            ALIGNED           → REINFORCE                   │   │
│   │   > 0.85            CONFLICTING       → CONTRADICTION (flag gap)    │   │
│   │   0.60-0.85         ALIGNED           → EXTEND                      │   │
│   │   0.60-0.85         CONFLICTING       → CONTRADICT (flag gap)       │   │
│   │   < 0.60            ALIGNED           → CREATE (new truth)          │   │
│   │   < 0.60            CONFLICTING       → CREATE (parallel truth)     │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Semantic Conflict Examples:                                               │
│   • Sentiment polarity reversal: "loves Thai food" vs "hates Thai food"    │
│   • Mutually exclusive: "vegetarian" vs "ordered steak"                    │
│   • Temporal conflict: "at gym at 7am" vs "sleeping at 7am"               │
│   • Relationship conflict: "Sarah is friend" vs "Sarah is colleague"      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 5.5.2 Resolution Strategy Selection

```python
class ContradictionResolver:
    """Selects resolution strategy for detected contradictions."""

    def select_strategy(
        self,
        contradiction: Contradiction,
        config: ContradictionConfig
    ) -> ResolutionStrategy:
        """
        Choose how to handle a contradiction.

        Factors:
        - Confidence of existing truth
        - Recency of new signal
        - Gap queue capacity
        - User question budget
        """
        # High-confidence existing truth + low-confidence new signal
        if contradiction.existing_confidence > 0.8 and contradiction.new_confidence < 0.5:
            return ResolutionStrategy.IGNORE_NEW  # Keep existing truth

        # Low-confidence existing truth + high-confidence new signal
        if contradiction.existing_confidence < 0.5 and contradiction.new_confidence > 0.7:
            return ResolutionStrategy.TEMPORAL_OVERRIDE  # New supersedes old

        # Both high confidence = genuine conflict
        if contradiction.existing_confidence > 0.6 and contradiction.new_confidence > 0.6:
            if self._has_question_budget(contradiction.actor_id):
                return ResolutionStrategy.FLAG_FOR_P06  # Ask user
            else:
                return ResolutionStrategy.HOLD_FOR_REVIEW  # Manual review

        # Default: flag for active learning
        return ResolutionStrategy.FLAG_FOR_P06

    def apply_strategy(
        self,
        contradiction: Contradiction,
        strategy: ResolutionStrategy
    ) -> ContradictionResult:
        """Execute the selected resolution strategy."""

        if strategy == ResolutionStrategy.IGNORE_NEW:
            return ContradictionResult(
                action='IGNORE',
                existing_updated=False,
                new_created=False,
                gap_created=False
            )

        if strategy == ResolutionStrategy.TEMPORAL_OVERRIDE:
            # Create new version superseding old
            return ContradictionResult(
                action='EVOLVE',
                existing_updated=True,  # Mark as superseded
                new_created=True,       # New truth version
                gap_created=False
            )

        if strategy == ResolutionStrategy.FLAG_FOR_P06:
            # Create gap record for active learning
            gap = self._create_contradiction_gap(contradiction)
            return ContradictionResult(
                action='DEFER',
                existing_updated=False,
                new_created=False,
                gap_created=True,
                gap_record=gap
            )

        if strategy == ResolutionStrategy.HOLD_FOR_REVIEW:
            # Both marked as PENDING_REVIEW
            return ContradictionResult(
                action='HOLD',
                existing_updated=True,  # Mark PENDING_REVIEW
                new_created=True,       # Store but not canonical
                gap_created=False
            )
```

### 5.6 Attention Budget Integration

#### 5.6.1 Token Bucket Implementation

```python
class AttentionBudget:
    """
    Rate limits questions to users via token bucket algorithm.

    Each user has a bucket of "attention tokens" that refill over time.
    Questions consume tokens. High-priority gaps can overdraw (limited).
    """

    def __init__(self, config: AttentionBudgetConfig):
        self.max_tokens = config.max_tokens_per_day  # e.g., 5
        self.refill_rate = config.refill_rate_per_hour  # e.g., 0.5
        self.overdraw_limit = config.overdraw_limit  # e.g., 2

    async def can_ask_question(
        self,
        actor_id: str,
        gap: GapRecord
    ) -> Tuple[bool, str]:
        """
        Check if we can ask a question to this user.

        Returns (allowed, reason).
        """
        bucket = await self._get_bucket(actor_id)

        # Refill tokens based on time elapsed
        bucket = self._refill_tokens(bucket)

        # Check if tokens available
        if bucket.tokens >= 1.0:
            return True, "tokens_available"

        # High-priority gaps can overdraw
        if gap.importance_score > 0.9 and bucket.overdraw_count < self.overdraw_limit:
            return True, "priority_overdraw"

        # Check when tokens will be available
        hours_until_token = (1.0 - bucket.tokens) / self.refill_rate
        return False, f"rate_limited:wait_{hours_until_token:.1f}h"

    async def consume_token(
        self,
        actor_id: str,
        gap: GapRecord,
        overdraw: bool = False
    ) -> None:
        """Consume a token when asking a question."""
        bucket = await self._get_bucket(actor_id)

        if overdraw:
            bucket.overdraw_count += 1
        else:
            bucket.tokens -= 1.0

        bucket.last_question_at = int(time.time())
        await self._save_bucket(bucket)
```

#### 5.6.2 Context-Aware Question Timing

```python
class QuestionTiming:
    """Determines optimal timing for asking questions."""

    async def find_asking_opportunity(
        self,
        gap: GapRecord,
        user_context: UserContext
    ) -> Optional[AskingOpportunity]:
        """
        Wait for a contextually appropriate moment to ask.

        Opportunities:
        1. User mentions related topic in conversation
        2. User is in relevant location/activity
        3. User appears to be idle (not in middle of task)
        4. User has explicitly indicated "ready for questions"
        """
        # Check for topic match
        if self._topic_matches(gap, user_context.current_conversation):
            return AskingOpportunity(
                trigger='topic_match',
                context=user_context.current_conversation,
                urgency='immediate'
            )

        # Check for activity match
        if self._activity_matches(gap, user_context.current_activity):
            return AskingOpportunity(
                trigger='activity_match',
                context=user_context.current_activity,
                urgency='opportunistic'
            )

        # Check if user is idle
        if user_context.idle_minutes > 5:
            return AskingOpportunity(
                trigger='idle_detection',
                context=None,
                urgency='low'
            )

        # No good opportunity now
        return None

    def _topic_matches(
        self,
        gap: GapRecord,
        conversation: Optional[Conversation]
    ) -> bool:
        """Check if current conversation relates to gap topic."""
        if conversation is None:
            return False

        gap_context = json.loads(gap.context_json)
        gap_keywords = gap_context.get('keywords', [])

        # Check for keyword overlap with recent messages
        conv_text = ' '.join(m.text for m in conversation.recent_messages)
        return any(kw.lower() in conv_text.lower() for kw in gap_keywords)
```

---

## 6. Storage Schema Design

> **Status**: COMPLETE

### 6.1 Schema Design Principles

#### 6.1.1 Durability Rules

The memory layer schemas follow strict durability rules to ensure data integrity and auditability:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DURABILITY RULES FOR MEMORY LAYERS                   │
│                                                                             │
│   Rule 1: IMMUTABILITY + VERSIONING                                         │
│   ─────────────────────────────────────────────────────────────────────────│
│   • Never UPDATE existing rows in place                                     │
│   • Create new version with incremented version number                      │
│   • Link via supersedes_id to previous version                              │
│   • Only one version has is_canonical = TRUE                                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         VERSION CHAIN EXAMPLE                        │   │
│   │                                                                      │   │
│   │   pattern_001_v1        pattern_001_v2        pattern_001_v3        │   │
│   │   ┌────────────┐        ┌────────────┐        ┌────────────┐        │   │
│   │   │ version: 1 │───────▶│ version: 2 │───────▶│ version: 3 │        │   │
│   │   │ canonical: │        │ canonical: │        │ canonical: │        │   │
│   │   │   FALSE    │        │   FALSE    │        │   TRUE ✓   │        │   │
│   │   │ superseded │        │ supersedes:│        │ supersedes:│        │   │
│   │   │   by: v2   │        │   v1       │        │   v2       │        │   │
│   │   └────────────┘        └────────────┘        └────────────┘        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Rule 2: TOMBSTONE PATTERN FOR DELETES                                     │
│   ─────────────────────────────────────────────────────────────────────────│
│   • Never DELETE rows directly                                              │
│   • Set archival_status = 'TOMBSTONE'                                       │
│   • Retain for audit period (configurable per retention policy)             │
│   • Background job garbage collects after retention period                  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      LIFECYCLE STATE MACHINE                         │   │
│   │                                                                      │   │
│   │   ACTIVE ──decay──▶ ARCHIVED ──time──▶ TOMBSTONE ──gc──▶ [deleted]  │   │
│   │     │                  ▲                                             │   │
│   │     └──explicit────────┘                                             │   │
│   │        archive                                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Rule 3: FULL PROVENANCE CHAIN                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│   • Every truth record links to source events (source_episodes_json)        │
│   • Every decision recorded in st_consolidation_audit                       │
│   • Timestamps: created_at, updated_at, valid_from, valid_to               │
│   • Traceability: consolidation_cycle_id links to specific P03 run         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 6.1.2 Common Columns Across All Memory Layers

All st_* memory layer tables share these column groups:

```sql
-- IDENTITY COLUMNS (required)
id TEXT PRIMARY KEY,                    -- ULID or domain-specific ID
tenant_id TEXT NOT NULL,                -- Tenant isolation (MANDATORY)
space_id TEXT NOT NULL,                 -- Space isolation (MANDATORY)
actor_id TEXT,                          -- Owner/subject (optional for shared patterns)

-- VERSIONING COLUMNS (required)
version INTEGER NOT NULL DEFAULT 1,     -- Version number within this record's chain
supersedes_id TEXT,                     -- ID of previous version (NULL for v1)
is_canonical BOOLEAN DEFAULT TRUE,      -- Only TRUE for latest active version

-- TEMPORAL COLUMNS (required)
created_at INTEGER NOT NULL,            -- Unix timestamp of creation
updated_at INTEGER NOT NULL,            -- Unix timestamp of last modification

-- BITEMPORAL COLUMNS (for time-varying truth)
valid_from INTEGER NOT NULL,            -- When this truth became valid
valid_to INTEGER,                       -- When this truth stopped being valid (NULL = current)

-- TRUTH TRACKING COLUMNS (required)
observation_count INTEGER DEFAULT 1,    -- How many times this pattern was observed
confidence_score REAL DEFAULT 0.5,      -- [0-1] Bayesian confidence
decay_factor REAL DEFAULT 1.0,          -- [0-1] Temporal decay multiplier
last_observed_at INTEGER,               -- Unix timestamp of last observation

-- SOURCE LINKAGE (required)
source_episodes_json TEXT,              -- JSON array of source event_ids
embedding_id TEXT,                      -- Reference to st_vec (aggregated embedding)

-- LIFECYCLE (required)
archival_status TEXT DEFAULT 'ACTIVE' CHECK(archival_status IN (
    'ACTIVE',       -- Current, queryable
    'ARCHIVED',     -- Moved to cold storage, queryable on request
    'TOMBSTONE'     -- Deleted, pending garbage collection
)),
consolidation_cycle_id TEXT,            -- P03 cycle that created/updated this record
```

#### 6.1.3 Indexing Strategy

```sql
-- ═══════════════════════════════════════════════════════════════════════════════
-- INDEXING PATTERNS FOR MEMORY LAYER TABLES
-- ═══════════════════════════════════════════════════════════════════════════════

-- Pattern 1: TENANT + SPACE PARTITIONING (always first)
-- Every query MUST filter by tenant_id; space_id usually follows
CREATE INDEX idx_{table}_tenant_space ON st_{table}(tenant_id, space_id);

-- Pattern 2: CANONICAL RECORD LOOKUP
-- Fast access to current truth (skip historical versions)
CREATE INDEX idx_{table}_canonical ON st_{table}(is_canonical, archival_status)
    WHERE is_canonical = TRUE AND archival_status = 'ACTIVE';

-- Pattern 3: TEMPORAL QUERIES
-- Find truth valid at a specific point in time
CREATE INDEX idx_{table}_temporal ON st_{table}(tenant_id, valid_from, valid_to);

-- Pattern 4: CONFIDENCE-BASED RETRIEVAL
-- Query highest-confidence patterns first
CREATE INDEX idx_{table}_confidence ON st_{table}(confidence_score DESC)
    WHERE is_canonical = TRUE AND archival_status = 'ACTIVE';

-- Pattern 5: ACTOR-SPECIFIC PATTERNS
-- Find all patterns for a specific person
CREATE INDEX idx_{table}_actor ON st_{table}(actor_id, created_at DESC)
    WHERE actor_id IS NOT NULL;

-- Pattern 6: CONSOLIDATION TRACKING
-- Find all records from a specific P03 cycle
CREATE INDEX idx_{table}_cycle ON st_{table}(consolidation_cycle_id);

-- Pattern 7: DECAY CANDIDATES
-- Find records needing decay processing
CREATE INDEX idx_{table}_decay ON st_{table}(last_observed_at, decay_factor)
    WHERE archival_status = 'ACTIVE' AND decay_factor < 1.0;
```

#### 6.1.4 Write Patterns

```python
class MemoryLayerWriter:
    """
    Standard write patterns for memory layer tables.

    All writes go through st_outbox for durability.
    """

    async def create_truth_record(
        self,
        table: str,
        record: TruthRecord,
        decision: ReconciliationDecision
    ) -> WriteResult:
        """
        CREATE decision: Insert new truth record.
        """
        record.version = 1
        record.is_canonical = True
        record.observation_count = 1
        record.created_at = int(time.time())
        record.updated_at = record.created_at
        record.consolidation_cycle_id = decision.cycle_id

        return await self._write_via_outbox(table, 'INSERT', record)

    async def reinforce_truth_record(
        self,
        table: str,
        existing: TruthRecord,
        new_evidence: HippEvent,
        decision: ReconciliationDecision
    ) -> WriteResult:
        """
        REINFORCE decision: Boost existing record's confidence.

        Note: We UPDATE in place for REINFORCE since we're only
        incrementing counters, not changing the truth itself.
        This is the ONE exception to immutability rule.
        """
        updates = {
            'observation_count': existing.observation_count + 1,
            'confidence_score': min(0.99, existing.confidence_score + 0.05),
            'last_observed_at': int(time.time()),
            'decay_factor': 1.0,  # Reset decay on observation
            'updated_at': int(time.time()),
        }

        # Append new source event
        sources = json.loads(existing.source_episodes_json or '[]')
        sources.append(new_evidence.event_id)
        updates['source_episodes_json'] = json.dumps(sources[-100:])  # Keep last 100

        return await self._write_via_outbox(table, 'UPDATE', updates, existing.id)

    async def evolve_truth_record(
        self,
        table: str,
        existing: TruthRecord,
        evolved: TruthRecord,
        decision: ReconciliationDecision
    ) -> WriteResult:
        """
        EVOLVE decision: Create new version superseding old.
        """
        # Mark existing as non-canonical
        await self._write_via_outbox(
            table, 'UPDATE',
            {'is_canonical': False, 'updated_at': int(time.time())},
            existing.id
        )

        # Create new version
        evolved.version = existing.version + 1
        evolved.supersedes_id = existing.id
        evolved.is_canonical = True
        evolved.observation_count = existing.observation_count + 1
        evolved.created_at = int(time.time())
        evolved.updated_at = evolved.created_at
        evolved.consolidation_cycle_id = decision.cycle_id

        return await self._write_via_outbox(table, 'INSERT', evolved)

    async def prune_truth_record(
        self,
        table: str,
        record: TruthRecord,
        prune_reason: str
    ) -> WriteResult:
        """
        PRUNE decision: Archive or tombstone stale record.
        """
        new_status = 'ARCHIVED' if record.decay_factor > 0.1 else 'TOMBSTONE'

        return await self._write_via_outbox(
            table, 'UPDATE',
            {
                'archival_status': new_status,
                'updated_at': int(time.time()),
            },
            record.id
        )
```

#### 6.1.5 Query Patterns

```python
class MemoryLayerReader:
    """
    Standard query patterns for memory layer tables.

    ALL QUERIES MUST INCLUDE tenant_id FILTER.
    """

    async def query_canonical_truth(
        self,
        table: str,
        tenant_id: str,
        space_id: str,
        **filters
    ) -> List[TruthRecord]:
        """
        Standard query: Get current canonical truth.
        """
        query = f"""
            SELECT * FROM {table}
            WHERE tenant_id = :tenant_id
              AND space_id = :space_id
              AND is_canonical = TRUE
              AND archival_status = 'ACTIVE'
        """

        for key, value in filters.items():
            query += f" AND {key} = :{key}"

        query += " ORDER BY confidence_score DESC"

        return await self.db.fetch_all(query, {'tenant_id': tenant_id, 'space_id': space_id, **filters})

    async def query_truth_at_time(
        self,
        table: str,
        tenant_id: str,
        space_id: str,
        as_of: int  # Unix timestamp
    ) -> List[TruthRecord]:
        """
        Bitemporal query: Get truth as it was at a specific time.
        """
        query = f"""
            SELECT * FROM {table}
            WHERE tenant_id = :tenant_id
              AND space_id = :space_id
              AND valid_from <= :as_of
              AND (valid_to IS NULL OR valid_to > :as_of)
              AND archival_status != 'TOMBSTONE'
        """

        return await self.db.fetch_all(query, {
            'tenant_id': tenant_id,
            'space_id': space_id,
            'as_of': as_of
        })

    async def query_version_history(
        self,
        table: str,
        record_id: str
    ) -> List[TruthRecord]:
        """
        Get full version chain for a record.
        """
        # Find the canonical version first
        canonical = await self.db.fetch_one(
            f"SELECT * FROM {table} WHERE id = :id OR supersedes_id = :id",
            {'id': record_id}
        )

        if not canonical:
            return []

        # Walk the chain backwards
        chain = [canonical]
        current = canonical

        while current.get('supersedes_id'):
            prev = await self.db.fetch_one(
                f"SELECT * FROM {table} WHERE id = :id",
                {'id': current['supersedes_id']}
            )
            if prev:
                chain.append(prev)
                current = prev
            else:
                break

        return list(reversed(chain))  # Oldest first
```

---

### 6.2 st_hipp_events (Staging / Hippocampus)

> **Source**: P02 Memory Formation Pipeline
> **Brain Analog**: Hippocampus (CA3 fast encoding)
> **Role**: Staging table for recent episodic events before consolidation

```sql
CREATE TABLE st_hipp_events (
  -- ═══════════════════════════════════════════════════════════════════════════════
  -- IDENTITY & TRACE (9 columns)
  -- ═══════════════════════════════════════════════════════════════════════════════
  event_id TEXT PRIMARY KEY,              -- ULID, globally unique event identifier
  wal_pos INTEGER NOT NULL UNIQUE,        -- Write-ahead log position (ordering key)
  cognitive_trace_id TEXT NOT NULL,       -- Distributed trace ID for observability
  tenant_id TEXT NOT NULL,                -- Tenant isolation key
  space_id TEXT NOT NULL,                 -- Space (family unit) isolation key
  effective_space_id TEXT,                -- Resolved space (after routing)
  topic TEXT NOT NULL,                    -- Event topic (e.g., "note.created.v1")
  uow_id TEXT,                            -- Unit of Work ID (batch correlation)
  schema_version TEXT NOT NULL DEFAULT '1.0.0',  -- Event schema version

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- INTEGRITY & AUDIT (6 columns)
  -- ═══════════════════════════════════════════════════════════════════════════════
  envelope_sha256 TEXT NOT NULL,          -- SHA-256 hash of envelope (integrity)
  sig_alg TEXT NOT NULL,                  -- Signature algorithm (e.g., "ED25519")
  sig_kid TEXT NOT NULL,                  -- Signing key ID
  idem_key TEXT NOT NULL,                 -- Idempotency key (deduplication)
  ingested_at INTEGER NOT NULL,           -- Unix timestamp of ingestion
  clock_skew_ms INTEGER,                  -- Detected clock skew (milliseconds)

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- POLICY & VISIBILITY (10 columns)
  -- ═══════════════════════════════════════════════════════════════════════════════
  policy_decision TEXT NOT NULL CHECK(policy_decision IN ('ALLOW', 'DENY')),
  policy_band TEXT NOT NULL CHECK(policy_band IN ('GREEN', 'AMBER', 'RED')),
  policy_version TEXT NOT NULL,
  obligations_json TEXT,                  -- Policy obligations (e.g., TTL, masking)
  visible_to_json TEXT,                   -- Explicit visibility list
  visibility_scope TEXT CHECK(visibility_scope IN (
    'OWNER_ONLY', 'SPACE_DEFAULT', 'HOUSEHOLD_ALL', 'CUSTOM_SUBSET', 'EXTERNAL_SHARE'
  )),
  owner_id TEXT NOT NULL,                 -- Data owner actor ID
  co_owners_json TEXT,                    -- Additional owners (JSON array)
  retention_policy_id TEXT NOT NULL,      -- Reference to st_retention_policy
  retention_bucket TEXT NOT NULL CHECK(retention_bucket IN (
    'STANDARD', 'SENSITIVE', 'EPHEMERAL'
  )),

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- ACTOR & DEVICE (6 columns)
  -- ═══════════════════════════════════════════════════════════════════════════════
  actor_id TEXT NOT NULL,                 -- Who created this event
  actor_role TEXT CHECK(actor_role IN ('SELF', 'AGENT', 'SYSTEM', 'DELEGATE')),
  device_id TEXT NOT NULL,                -- Source device identifier
  device_kind TEXT NOT NULL,              -- Device type (mobile, web, voice, etc.)
  device_os TEXT,                         -- Operating system
  ingress_channel TEXT,                   -- Entry channel (app, voice, calendar, etc.)

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- TEMPORAL (11 columns) — Critical for consolidation scheduling
  -- ═══════════════════════════════════════════════════════════════════════════════
  event_time_utc INTEGER NOT NULL,        -- When event occurred (Unix ms)
  write_time_utc INTEGER NOT NULL,        -- When event was written (Unix ms)
  write_lag_ms INTEGER,                   -- Delay between event and write
  local_date TEXT,                        -- Local date string (YYYY-MM-DD)
  local_time TEXT,                        -- Local time string (HH:MM:SS)
  day_of_week TEXT,                       -- Day name (Monday, Tuesday, etc.)
  is_weekend BOOLEAN,                     -- Weekend flag
  time_of_day_bucket TEXT,                -- MORNING, AFTERNOON, EVENING, NIGHT
  circadian_slot TEXT,                    -- Fine-grained time slot
  is_backdated BOOLEAN,                   -- True if event_time < write_time - threshold
  created_at INTEGER NOT NULL,            -- Record creation timestamp

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- SPATIAL & PLACE (5 columns)
  -- ═══════════════════════════════════════════════════════════════════════════════
  location_name TEXT,                     -- Place name (e.g., "Home", "CorePower Yoga")
  location_type TEXT,                     -- Type: HOME, WORK, GYM, RESTAURANT, etc.
  geohash_6 TEXT,                         -- 6-character geohash (city block precision)
  geo_precision_external TEXT,            -- External precision indicator
  geo_masking_reason TEXT,                -- Why location was masked (if applicable)

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- SOCIAL & RELATIONSHIPS (8 columns) — For st_social consolidation
  -- ═══════════════════════════════════════════════════════════════════════════════
  participants_json TEXT,                 -- JSON array of participant IDs
  num_participants INTEGER,               -- Count of participants
  has_partner_present BOOLEAN,            -- Partner participation flag
  has_parent_present BOOLEAN,             -- Parent participation flag
  is_solo_event BOOLEAN,                  -- Solo activity flag
  participant_roles_json TEXT,            -- Role assignments for participants
  social_context TEXT,                    -- Context: FAMILY, FRIENDS, WORK, etc.
  social_intimacy TEXT,                   -- Intimacy level: CASUAL, CLOSE, INTIMATE

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- SEMANTIC & ACTIVITY (10 columns) — For st_sem and st_procedural consolidation
  -- ═══════════════════════════════════════════════════════════════════════════════
  text TEXT,                              -- Original text content
  text_normalized TEXT,                   -- Normalized/cleaned text
  char_count INTEGER,                     -- Character count
  token_count INTEGER,                    -- Token count (for LLM context)
  language TEXT,                          -- Detected language code
  activity_type TEXT,                     -- Activity classification
  activity_category TEXT,                 -- Broad category
  is_meal BOOLEAN,                        -- Meal event flag
  is_outing BOOLEAN,                      -- Outing event flag
  ingress_source TEXT,                    -- Original data source

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- HIPPOCAMPUS: PATTERN SEPARATION & NOVELTY (8 columns) — P03 R3 uses these
  -- ═══════════════════════════════════════════════════════════════════════════════
  simhash_hex TEXT NOT NULL,              -- 64-bit SimHash fingerprint (hex string)
  minhash32 TEXT NOT NULL,                -- 32-band MinHash signature (for LSH)
  novelty_score REAL,                     -- [0-1] How unique is this event? (P03 R3)
  near_duplicates_json TEXT,              -- JSON array of near-duplicate event_ids
  is_near_duplicate BOOLEAN,              -- True if Hamming distance ≤ 3 to another
  episode_cluster_id TEXT,                -- Cluster assignment (P03 R2)
  cluster_confidence REAL,                -- [0-1] Confidence in cluster assignment
  clustering_version TEXT,                -- Algorithm version that assigned cluster

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- EMBEDDINGS & KNOWLEDGE GRAPH (4 columns) — P03 R4 uses these
  -- ═══════════════════════════════════════════════════════════════════════════════
  embedding_id TEXT NOT NULL UNIQUE,      -- Reference to st_vec.embedding_id
  embedding_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(
    embedding_status IN ('PENDING', 'IN_PROGRESS', 'READY', 'FAILED')
  ),
  entities_json TEXT,                     -- Extracted entities (UltraBERT NER)
  kg_triples_json TEXT,                   -- Extracted knowledge graph triples

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- AFFECT & SALIENCE (9 columns) — P03 R1 importance scoring uses these
  -- ═══════════════════════════════════════════════════════════════════════════════
  sentiment_score REAL,                   -- [-1, +1] Sentiment polarity
  sentiment_label TEXT,                   -- POSITIVE, NEGATIVE, NEUTRAL
  dominant_emotions_json TEXT,            -- Top emotions (e.g., ["joy", "excitement"])
  affect_valence REAL,                    -- [-1, +1] Pleasure dimension
  affect_arousal REAL,                    -- [0, 1] Activation/energy dimension
  affect_band TEXT CHECK(affect_band IN ('GREEN', 'AMBER', 'RED')),
  salience_score REAL NOT NULL DEFAULT 0.0,  -- [0-1] Overall importance
  salience_reasons_json TEXT,             -- Why event is salient (JSON array)
  salience_band TEXT CHECK(salience_band IN ('HIGH', 'MED', 'LOW')),

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- METADATA & VERSIONING (4 columns)
  -- ═══════════════════════════════════════════════════════════════════════════════
  hippocampus_api_version TEXT,           -- P02 hippocampus module version
  space_resolver_version TEXT,            -- Space resolution algorithm version
  schema_uri TEXT,                        -- Schema contract URI
  updated_at INTEGER NOT NULL             -- Last update timestamp

  -- ═══════════════════════════════════════════════════════════════════════════════
  -- P03 CONSOLIDATION COLUMNS (added during consolidation)
  -- ═══════════════════════════════════════════════════════════════════════════════
  -- NOTE: The following columns are populated by P03 during R6:
  --
  -- consolidation_status TEXT CHECK(consolidation_status IN (
  --   'PENDING', 'IN_PROGRESS', 'CONSOLIDATED', 'DUPLICATE', 'PRUNED', 'PENDING_REVIEW'
  -- )),
  -- consolidation_cycle_id TEXT,          -- Which P03 cycle processed this
  -- consolidated_at INTEGER,              -- When consolidation completed
  -- reconciliation_decision TEXT,         -- REINFORCE, EXTEND, CREATE, EVOLVE, etc.
  -- truth_match_id TEXT,                  -- Which truth record was matched
  -- truth_match_similarity REAL,          -- Similarity score to matched truth
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- INDEXES for P03 Consolidation
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE INDEX idx_hipp_events_tenant_time ON st_hipp_events(tenant_id, event_time_utc DESC);
CREATE INDEX idx_hipp_events_space_time ON st_hipp_events(space_id, event_time_utc DESC);
CREATE INDEX idx_hipp_events_simhash ON st_hipp_events(simhash_hex);
CREATE INDEX idx_hipp_events_embedding_id ON st_hipp_events(embedding_id);
CREATE INDEX idx_hipp_events_band_time ON st_hipp_events(policy_band, event_time_utc DESC);
CREATE INDEX idx_hipp_events_cluster_id ON st_hipp_events(episode_cluster_id)
  WHERE episode_cluster_id IS NOT NULL;

-- P03-specific indexes (to be added):
-- CREATE INDEX idx_hipp_events_consolidation ON st_hipp_events(consolidation_status, event_time_utc)
--   WHERE consolidation_status IS NULL OR consolidation_status = 'PENDING';
```

#### 6.2.1 Column Groups Used by P03 Phases

| Phase | Column Group | Purpose |
|-------|--------------|---------|
| **R1** | `salience_score`, `sentiment_score`, `affect_*`, `participants_json` | Importance scoring |
| **R2** | `embedding_id`, `entities_json`, `activity_type` | Episodic clustering |
| **R3** | `simhash_hex`, `minhash32`, `novelty_score`, `near_duplicates_json` | Deduplication |
| **R4** | `entities_json`, `kg_triples_json`, `participants_json` | KG consolidation |
| **R6** | `consolidation_status`, `episode_cluster_id`, `cluster_confidence` | Status updates |
| **R8** | `event_id`, `tenant_id`, `space_id` | Event emission |

#### 6.2.2 Consolidation Status Lifecycle

```
NULL (new event from P02)
  │
  ▼
PENDING (selected for next cycle)
  │
  ▼
IN_PROGRESS (R1-R6 processing)
  │
  ├──▶ CONSOLIDATED (successfully processed)
  │
  ├──▶ DUPLICATE (merged with existing, marked near_duplicate)
  │
  ├──▶ PRUNED (novelty too low, archived)
  │
  └──▶ PENDING_REVIEW (contradiction detected, awaiting P06)
```

### 6.3 st_epi (Episodic Memory)

> **Brain Analog**: Episodic Memory (Tulving)
> **Role**: Consolidated episode clusters with temporal anchoring
> **Written by**: P03 R7 (after R2 clustering)

```sql
CREATE TABLE st_epi (
  -- Identity
  episode_id TEXT PRIMARY KEY,           -- ULID for episode
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Versioning (Immutability)
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,                    -- Previous version ID (for EVOLVE)
  is_canonical BOOLEAN DEFAULT TRUE,     -- Only one version is canonical

  -- Episode Content
  episode_summary TEXT,                  -- AI-generated summary
  episode_type TEXT,                     -- ROUTINE, MILESTONE, NOVEL, etc.

  -- Temporal Anchoring
  start_time_utc INTEGER NOT NULL,       -- Earliest event in episode
  end_time_utc INTEGER NOT NULL,         -- Latest event in episode
  duration_minutes INTEGER,
  temporal_bucket TEXT,                  -- MORNING, AFTERNOON, etc.
  day_of_week TEXT,
  is_recurring BOOLEAN,                  -- Part of recurring pattern
  recurrence_pattern TEXT,               -- e.g., "WEEKLY:TUESDAY"

  -- Source Events
  source_events_json TEXT NOT NULL,      -- JSON array of source event_ids
  source_event_count INTEGER NOT NULL,

  -- Location
  primary_location TEXT,
  location_type TEXT,

  -- Participants
  participants_json TEXT,                -- JSON array of participant IDs
  participant_count INTEGER,

  -- Embeddings
  embedding_id TEXT,                     -- Reference to st_vec (aggregated embedding)

  -- Consolidation Metadata
  cluster_id TEXT,                       -- From P03 R2 clustering
  cluster_confidence REAL,
  consolidation_cycle_id TEXT,

  -- Truth Tracking (Bidirectional)
  observation_count INTEGER DEFAULT 1,   -- How many times observed
  confidence_score REAL DEFAULT 0.5,     -- [0-1] Confidence in episode
  last_observed_at INTEGER,              -- Last time this pattern was seen
  decay_factor REAL DEFAULT 1.0,         -- [0-1] Temporal decay

  -- Lifecycle
  archival_status TEXT DEFAULT 'ACTIVE' CHECK(archival_status IN (
    'ACTIVE', 'ARCHIVED', 'TOMBSTONE'
  )),

  -- Timestamps
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,           -- Bitemporal: when became true
  valid_to INTEGER                       -- Bitemporal: when stopped being true
);

CREATE INDEX idx_epi_tenant_time ON st_epi(tenant_id, start_time_utc DESC);
CREATE INDEX idx_epi_space_time ON st_epi(space_id, start_time_utc DESC);
CREATE INDEX idx_epi_cluster ON st_epi(cluster_id) WHERE cluster_id IS NOT NULL;
CREATE INDEX idx_epi_canonical ON st_epi(is_canonical, archival_status);
```

### 6.4 st_sem (Semantic Patterns)

> **Brain Analog**: Semantic Memory (Neocortex)
> **Role**: Extracted patterns, preferences, themes from episodes
> **Written by**: P03 R7 (after R2 pattern extraction)

```sql
CREATE TABLE st_sem (
  -- Identity
  pattern_id TEXT PRIMARY KEY,           -- ULID for pattern
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  actor_id TEXT,                         -- Whose pattern (NULL = shared family)

  -- Versioning
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,

  -- Pattern Classification
  pattern_type TEXT NOT NULL CHECK(pattern_type IN (
    'ROUTINE', 'PREFERENCE', 'THEME', 'RELATIONSHIP', 'GOAL', 'VALUE'
  )),
  pattern_subtype TEXT,                  -- More specific classification

  -- Pattern Content
  pattern_name TEXT NOT NULL,            -- Human-readable name
  pattern_description TEXT,              -- Detailed description
  pattern_attributes_json TEXT,          -- Structured attributes

  -- Example: For PREFERENCE type
  -- {
  --   "domain": "food",
  --   "attribute": "cuisine_preference",
  --   "value": "Thai",
  --   "polarity": "positive",
  --   "strength": 0.85
  -- }

  -- Temporal Pattern (for ROUTINE)
  temporal_regularity REAL,              -- [0-1] How regular is timing
  temporal_pattern_json TEXT,            -- Cron-like pattern

  -- Source Episodes
  source_episodes_json TEXT NOT NULL,    -- JSON array of episode_ids
  source_episode_count INTEGER NOT NULL,

  -- Embeddings
  embedding_id TEXT,                     -- Pattern embedding (aggregated)

  -- Truth Tracking (Bidirectional)
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  last_observed_at INTEGER,
  first_observed_at INTEGER,
  decay_factor REAL DEFAULT 1.0,

  -- Lifecycle
  archival_status TEXT DEFAULT 'ACTIVE' CHECK(archival_status IN (
    'ACTIVE', 'ARCHIVED', 'TOMBSTONE'
  )),

  -- Timestamps
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,
  valid_to INTEGER
);

CREATE INDEX idx_sem_tenant_type ON st_sem(tenant_id, pattern_type);
CREATE INDEX idx_sem_actor_type ON st_sem(actor_id, pattern_type) WHERE actor_id IS NOT NULL;
CREATE INDEX idx_sem_canonical ON st_sem(is_canonical, archival_status);
CREATE INDEX idx_sem_confidence ON st_sem(confidence_score DESC) WHERE is_canonical = TRUE;
```

### 6.5 st_procedural (Habits & Routines)

> **Brain Analog**: Basal Ganglia (Procedural Memory)
> **Role**: Recurring behavioral patterns, habits, skills
> **Written by**: P03 R7

```sql
CREATE TABLE st_procedural (
  -- Identity
  routine_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,                -- Who performs this routine

  -- Versioning
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,

  -- Routine Definition
  routine_name TEXT NOT NULL,
  routine_category TEXT,                 -- MORNING, EXERCISE, MEAL, WORK, etc.

  -- Temporal Pattern
  temporal_anchor TEXT,                  -- Time of day: "07:30"
  day_pattern TEXT,                      -- "WEEKDAYS", "WEEKENDS", "DAILY", etc.
  frequency TEXT,                        -- "DAILY", "WEEKLY", "MONTHLY"
  regularity_score REAL,                 -- [0-1] How consistent

  -- Action Sequence
  action_sequence_json TEXT,             -- Ordered list of actions
  typical_duration_minutes INTEGER,

  -- Source Episodes
  source_episodes_json TEXT NOT NULL,
  source_episode_count INTEGER NOT NULL,

  -- Truth Tracking
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  last_observed_at INTEGER,
  streak_count INTEGER DEFAULT 0,        -- Consecutive occurrences
  streak_broken_at INTEGER,              -- When streak was broken
  decay_factor REAL DEFAULT 1.0,

  -- Lifecycle
  archival_status TEXT DEFAULT 'ACTIVE',

  -- Timestamps
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,
  valid_to INTEGER
);
```

### 6.6 st_social (Relationships)

> **Brain Analog**: Social Brain Network
> **Role**: Relationship tracking, interaction history, social graph
> **Written by**: P03 R7

```sql
CREATE TABLE st_social (
  -- Identity
  relationship_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Relationship Endpoints
  actor_a_id TEXT NOT NULL,              -- First person in relationship
  actor_b_id TEXT NOT NULL,              -- Second person

  -- Versioning
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,

  -- Relationship Type
  relationship_type TEXT NOT NULL,       -- FAMILY, FRIEND, COLLEAGUE, etc.
  relationship_subtype TEXT,             -- SPOUSE, SIBLING, PARENT, etc.
  relationship_label TEXT,               -- Custom label

  -- Relationship Strength
  interaction_count INTEGER DEFAULT 0,
  avg_sentiment REAL,                    -- Average sentiment in interactions
  relationship_strength REAL DEFAULT 0.5, -- [0-1] Overall strength
  intimacy_level TEXT,                   -- ACQUAINTANCE, CASUAL, CLOSE, INTIMATE

  -- Temporal
  first_interaction_at INTEGER,
  last_interaction_at INTEGER,
  interaction_frequency TEXT,            -- DAILY, WEEKLY, MONTHLY, RARE

  -- Source Episodes
  source_episodes_json TEXT,

  -- Truth Tracking
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  decay_factor REAL DEFAULT 1.0,

  -- Lifecycle
  archival_status TEXT DEFAULT 'ACTIVE',

  -- Timestamps
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,
  valid_to INTEGER,

  UNIQUE(tenant_id, actor_a_id, actor_b_id, is_canonical)
);
```

### 6.7 st_prospective (Intentions & Goals)

> **Brain Analog**: Prefrontal Cortex (Future Thinking)
> **Role**: Future-oriented patterns, goals, intentions, reminders
> **Written by**: P03 R7 (from R5 forward simulation)

```sql
CREATE TABLE st_prospective (
  -- Identity
  intention_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,

  -- Versioning
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,

  -- Intention Type
  intention_type TEXT NOT NULL CHECK(intention_type IN (
    'GOAL', 'PLAN', 'REMINDER', 'COMMITMENT', 'WISH'
  )),

  -- Content
  intention_description TEXT NOT NULL,
  target_date INTEGER,                   -- When to complete
  target_context TEXT,                   -- Triggering context

  -- Status
  status TEXT DEFAULT 'ACTIVE' CHECK(status IN (
    'ACTIVE', 'COMPLETED', 'ABANDONED', 'DEFERRED'
  )),

  -- Inference Source
  inferred_from_json TEXT,               -- Source patterns/episodes
  inference_confidence REAL,

  -- Truth Tracking
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  decay_factor REAL DEFAULT 1.0,

  -- Lifecycle
  archival_status TEXT DEFAULT 'ACTIVE',

  -- Timestamps
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,
  valid_to INTEGER
);
```

### 6.8 st_kg_dom (KG Entities)

> **Brain Analog**: Semantic Memory (Concept Nodes)
> **Role**: Canonical entities with attributes (people, places, things)
> **Written by**: P03 R7 (from R4 entity extraction)

```sql
CREATE TABLE st_kg_dom (
  -- Identity
  entity_id TEXT PRIMARY KEY,            -- Canonical entity ID
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Versioning
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,

  -- Entity Type
  entity_type TEXT NOT NULL,             -- PERSON, PLACE, ORGANIZATION, THING, EVENT
  entity_subtype TEXT,                   -- More specific type

  -- Entity Names
  canonical_name TEXT NOT NULL,          -- Primary display name
  aliases_json TEXT,                     -- Alternative names/spellings

  -- Attributes (type-specific)
  attributes_json TEXT,                  -- Structured attributes
  -- Example for PERSON:
  -- {
  --   "age": 35,
  --   "birthday": "1990-05-15",
  --   "occupation": "Engineer",
  --   "preferences": {...}
  -- }

  -- Embeddings
  embedding_id TEXT,                     -- Entity embedding

  -- Source Episodes
  source_episodes_json TEXT,
  first_mentioned_event_id TEXT,

  -- Truth Tracking
  observation_count INTEGER DEFAULT 1,
  confidence_score REAL DEFAULT 0.5,
  last_observed_at INTEGER,
  decay_factor REAL DEFAULT 1.0,

  -- Lifecycle
  archival_status TEXT DEFAULT 'ACTIVE',

  -- Timestamps
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  valid_from INTEGER NOT NULL,
  valid_to INTEGER
);

CREATE INDEX idx_kg_dom_tenant_type ON st_kg_dom(tenant_id, entity_type);
CREATE INDEX idx_kg_dom_name ON st_kg_dom(canonical_name);
CREATE INDEX idx_kg_dom_canonical ON st_kg_dom(is_canonical, archival_status);
```

### 6.9 st_kg_edges (KG Relationships)

> **Brain Analog**: Associative Connections
> **Role**: Typed relationships between entities with temporal validity
> **Written by**: P03 R7 (from R4 relationship discovery)

```sql
CREATE TABLE st_kg_edges (
  -- Identity
  edge_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Relationship Endpoints
  source_entity_id TEXT NOT NULL,        -- From entity
  target_entity_id TEXT NOT NULL,        -- To entity

  -- Versioning
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id TEXT,
  is_canonical BOOLEAN DEFAULT TRUE,

  -- Relationship Type
  relation_type TEXT NOT NULL,           -- WORKS_AT, LIVES_IN, KNOWS, LIKES, etc.
  relation_subtype TEXT,

  -- Relationship Properties
  properties_json TEXT,                  -- Edge attributes

  -- Strength & Confidence
  edge_weight REAL DEFAULT 1.0,          -- Relationship strength
  confidence_score REAL DEFAULT 0.5,

  -- Source Evidence
  source_episodes_json TEXT,
  co_occurrence_count INTEGER DEFAULT 1, -- Hebbian: how often seen together

  -- Truth Tracking
  observation_count INTEGER DEFAULT 1,
  last_observed_at INTEGER,
  decay_factor REAL DEFAULT 1.0,

  -- Lifecycle
  archival_status TEXT DEFAULT 'ACTIVE',

  -- Temporal Validity
  valid_from INTEGER NOT NULL,
  valid_to INTEGER,

  -- Timestamps
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  FOREIGN KEY (source_entity_id) REFERENCES st_kg_dom(entity_id),
  FOREIGN KEY (target_entity_id) REFERENCES st_kg_dom(entity_id)
);

CREATE INDEX idx_kg_edges_source ON st_kg_edges(source_entity_id, relation_type);
CREATE INDEX idx_kg_edges_target ON st_kg_edges(target_entity_id, relation_type);
CREATE INDEX idx_kg_edges_canonical ON st_kg_edges(is_canonical, archival_status);
```

### 6.10 st_vec (Embeddings)

> **Source**: P02 inline embedding (M23), indexed by P08
> **Role**: UltraBERT 768-dim embeddings for semantic similarity

```sql
CREATE TABLE st_vec (
  -- Identity
  embedding_id TEXT PRIMARY KEY,

  -- Linkage
  event_id TEXT NOT NULL,                -- Source event (st_hipp_events)

  -- Tenant/Space Context
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Vector Data
  vector BLOB NOT NULL,                  -- 768 floats × 4 bytes = 3072 bytes
  vector_dim INTEGER NOT NULL DEFAULT 768,

  -- Model Metadata
  model_id TEXT NOT NULL DEFAULT 'ultrabert_v2.1.0',

  -- Status Tracking
  status TEXT NOT NULL DEFAULT 'READY' CHECK(status IN (
    'READY',    -- Embedding stored by P02 (immediately available)
    'INDEXED',  -- Also added to FAISS index by P08
    'FAILED'    -- Generation/indexing failed
  )),

  -- FAISS Integration
  faiss_id INTEGER,                      -- FAISS index ID (set by P08)
  indexed_at INTEGER,                    -- When indexed by P08

  -- Tracing
  cognitive_trace_id TEXT,

  -- Timestamps
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id) ON DELETE CASCADE
);

CREATE INDEX idx_vec_event_id ON st_vec(event_id);
CREATE INDEX idx_vec_tenant_space ON st_vec(tenant_id, space_id);
CREATE INDEX idx_vec_status_created ON st_vec(status, created_at) WHERE status = 'READY';
CREATE INDEX idx_vec_faiss_id ON st_vec(faiss_id);
```

### 6.11 st_learning_queue (Gap Queue)

> **Role**: Gap records for P06 Active Learning
> **Written by**: P03 R8 (gap detection) or P06 (entropy scanner)

```sql
CREATE TABLE st_learning_queue (
  -- Identity
  id TEXT PRIMARY KEY,                   -- ULID for gap record
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Gap Classification
  gap_type TEXT NOT NULL CHECK(gap_type IN (
    'AMBIGUOUS_ENTITY',      -- Multiple entity candidates, can't decide
    'LOW_CONFIDENCE_EDGE',   -- Relationship confidence < threshold
    'MISSING_ATTRIBUTE',     -- Ontology-required attribute missing
    'CONTRADICTION',         -- New signal conflicts with existing truth
    'CONCEPT_DRIFT',         -- Anchor point confidence shifting
    'STRUCTURAL_HOLE',       -- Missing expected relationship in KG
    'STALE_ANCHOR'           -- Anchor not observed for extended period
  )),

  -- Context
  entity_id TEXT,                        -- Related entity (if applicable)
  related_event_id TEXT,                 -- Source event that triggered gap
  related_truth_id TEXT,                 -- Affected truth record

  -- Uncertainty Scores
  confidence_score REAL,                 -- [0-1] Current confidence
  entropy_score REAL,                    -- [0-1] Uncertainty level
  importance_score REAL GENERATED ALWAYS AS (
    entropy_score * (1.0 / (confidence_score + 0.1))
  ) STORED,

  -- Context for Question Generation
  context_json TEXT,                     -- Rich context for K1 question generation
  -- Example:
  -- {
  --   "candidates": ["person_123", "person_456"],
  --   "event_text": "Dinner with Sarah",
  --   "suggested_questions": ["Is Sarah your colleague or a friend?"]
  -- }

  -- Status Lifecycle
  status TEXT DEFAULT 'PENDING' CHECK(status IN (
    'PENDING',       -- Awaiting attention opportunity
    'READY',         -- Context-appropriate moment found
    'ASKED',         -- Question delivered to user
    'ANSWERED',      -- User responded
    'RESOLVED',      -- Gap closed, truth updated
    'EXPIRED',       -- Max wait time exceeded
    'REJECTED',      -- User declined to answer
    'SUPPRESSED'     -- System decided not to ask (budget, etc.)
  )),

  -- Timing
  created_at INTEGER NOT NULL,
  expires_at INTEGER,                    -- Auto-expire after this time
  ready_at INTEGER,                      -- When context became appropriate
  asked_at INTEGER,                      -- When question was delivered
  answered_at INTEGER,                   -- When user responded

  -- Retry Logic
  attempts INTEGER DEFAULT 0,            -- How many times asked
  max_attempts INTEGER DEFAULT 3,
  last_attempt_at INTEGER,

  -- Resolution
  resolution_type TEXT,                  -- 'USER_ANSWER', 'INFERRED', 'EXPIRED'
  resolution_data_json TEXT,             -- Answer or inference result

  -- Consolidation Cycle
  consolidation_cycle_id TEXT,           -- Which P03 cycle detected this

  -- Indexes
  FOREIGN KEY (related_event_id) REFERENCES st_hipp_events(event_id)
);

CREATE INDEX idx_learning_queue_importance ON st_learning_queue(
  importance_score DESC, created_at
) WHERE status = 'PENDING';
CREATE INDEX idx_learning_queue_status ON st_learning_queue(status, expires_at);
CREATE INDEX idx_learning_queue_tenant ON st_learning_queue(tenant_id, gap_type, status);
```

### 6.12 st_anchors (Bayesian Beliefs)

> **Role**: User preference modeling with Beta distributions
> **Updated by**: P03 during consolidation, P06 entropy scanner

```sql
CREATE TABLE st_anchors (
  -- Identity (Composite Key)
  entity_id TEXT NOT NULL,               -- Person ID this anchor belongs to
  attribute TEXT NOT NULL,               -- Attribute name (e.g., 'loves_spicy_food')
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Beta Distribution Parameters (Bayesian belief)
  alpha REAL DEFAULT 1.0,                -- Evidence FOR (successes)
  beta REAL DEFAULT 1.0,                 -- Evidence AGAINST (failures)

  -- Derived Metrics (for convenience)
  confidence REAL GENERATED ALWAYS AS (alpha / (alpha + beta)) STORED,
  uncertainty REAL GENERATED ALWAYS AS (
    1.0 / (1.0 + alpha + beta)           -- Higher when less data
  ) STORED,

  -- Observation History
  observation_count INTEGER DEFAULT 0,
  first_observed_at INTEGER,
  last_updated_at INTEGER NOT NULL,

  -- Decay Parameters
  decay_rate REAL DEFAULT 0.05,          -- Forgetting factor (5% per month)
  half_life_days INTEGER DEFAULT 180,    -- Days until confidence halves

  -- Drift Detection
  last_drift_check_at INTEGER,
  drift_detected BOOLEAN DEFAULT FALSE,
  drift_magnitude REAL,

  -- Lifecycle
  status TEXT DEFAULT 'ACTIVE' CHECK(status IN (
    'ACTIVE',        -- Currently tracking
    'DRIFTING',      -- Concept drift detected
    'STALE',         -- Not updated for extended period
    'ARCHIVED'       -- No longer tracking
  )),

  PRIMARY KEY (entity_id, attribute, tenant_id)
);

CREATE INDEX idx_anchors_entity ON st_anchors(entity_id, last_updated_at DESC);
CREATE INDEX idx_anchors_confidence ON st_anchors(confidence DESC) WHERE status = 'ACTIVE';
CREATE INDEX idx_anchors_drift ON st_anchors(drift_detected, status) WHERE drift_detected = TRUE;
```

### 6.13 st_anchor_observations (Evidence Log)

> **Role**: Audit trail for anchor updates (Bayesian evidence)

```sql
CREATE TABLE st_anchor_observations (
  -- Identity
  id TEXT PRIMARY KEY,

  -- Anchor Reference
  entity_id TEXT NOT NULL,
  attribute TEXT NOT NULL,
  tenant_id TEXT NOT NULL,

  -- Observation
  observed_at INTEGER NOT NULL,
  event_id TEXT,                         -- Source event
  supports_anchor BOOLEAN NOT NULL,      -- TRUE = evidence FOR, FALSE = AGAINST
  observation_weight REAL DEFAULT 1.0,   -- Weight of this observation (0-1)

  -- Context
  observation_context TEXT,              -- Why this was interpreted as support/oppose

  FOREIGN KEY (entity_id, attribute, tenant_id)
    REFERENCES st_anchors(entity_id, attribute, tenant_id),
  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
);

CREATE INDEX idx_anchor_obs_anchor ON st_anchor_observations(
  entity_id, attribute, observed_at DESC
);
```

### 6.14 st_pipeline_offsets & st_pipeline_status

> **Role**: Pipeline checkpoint and status tracking

```sql
-- Offset tracking for resume capability
CREATE TABLE st_offsets (
  subscriber_id TEXT NOT NULL,           -- Pipeline ID (e.g., 'p03_consolidation')
  topic TEXT NOT NULL,
  space_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  offset INTEGER NOT NULL,               -- Last processed wal_pos
  updated_ts TEXT NOT NULL,
  PRIMARY KEY(subscriber_id, topic, space_id, tenant_id)
);

-- Per-event processing status
CREATE TABLE st_pipeline_status (
  pipeline_id TEXT NOT NULL,
  wal_pos INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('OK', 'ERROR', 'DEFERRED')),
  duration_ms INTEGER,
  error_kind TEXT,
  error_msg TEXT,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (pipeline_id, wal_pos)
);

-- High-water marks (for compaction)
CREATE TABLE st_pipeline_watermarks (
  pipeline_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  watermark INTEGER NOT NULL,            -- Max processed wal_pos before compaction
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (pipeline_id, space_id)
);
```

### 6.15 st_outbox (Durable Writes)

> **Role**: Transactional outbox pattern for reliable writes

```sql
CREATE TABLE st_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  driver TEXT NOT NULL,                  -- Target driver (e.g., 'p08_embedding')
  op_kind TEXT NOT NULL,                 -- Operation type
  payload BLOB NOT NULL,                 -- Serialized operation
  fingerprint TEXT NOT NULL,             -- Idempotency key
  requeue_seq INTEGER NOT NULL DEFAULT 0,
  retries INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  next_attempt_ts TEXT,
  backoff_exp INTEGER DEFAULT 1,
  status TEXT DEFAULT 'PENDING' CHECK(status IN (
    'PENDING', 'PROCESSING', 'FAILED', 'DEAD'
  ))
);

CREATE UNIQUE INDEX uq_outbox_idem ON st_outbox(
  tenant_id, space_id, driver, fingerprint, requeue_seq
);
```

### 6.16 st_retention_policy (Lifecycle Management)

> **Role**: Configurable retention and archival policies per resource type

```sql
CREATE TABLE st_retention_policy (
  policy_id TEXT PRIMARY KEY,
  policy_name TEXT NOT NULL UNIQUE,
  resource_type TEXT NOT NULL,           -- st_epi, st_sem, st_proc, etc.
  privacy_band TEXT,                     -- GREEN, AMBER, RED (NULL = all)
  retention_days INTEGER NOT NULL,       -- Days to keep (0 = forever)
  archive_enabled BOOLEAN DEFAULT 1,
  archive_after_days INTEGER,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  updated_at TEXT,
  enabled BOOLEAN DEFAULT 1,
  CHECK(privacy_band IN ('GREEN', 'AMBER', 'RED') OR privacy_band IS NULL)
);
```

---

## 7. Module Registry

> **Status**: COMPLETE

### 7.1 P03 Module Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                            P03 MODULE DEPENDENCY GRAPH                                   │
│                                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              P03 CONSOLIDATION DRIVER                            │   │
│   │                                                                                  │   │
│   │                              ┌─────────────────┐                                 │   │
│   │                              │      M23        │                                 │   │
│   │                              │ReplayCoordinator│                                 │   │
│   │                              │   (R1 lead)     │                                 │   │
│   │                              └────────┬────────┘                                 │   │
│   │                                       │                                          │   │
│   │              ┌────────────────────────┼────────────────────────┐                │   │
│   │              ▼                        ▼                        ▼                │   │
│   │   ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐        │   │
│   │   │      M18        │      │      M19        │      │      M21        │        │   │
│   │   │EpisodicClusterer│      │DuplicateDetector│      │ KGConsolidator  │        │   │
│   │   │   (R2 lead)     │      │   (R3 lead)     │      │   (R4 lead)     │        │   │
│   │   └────────┬────────┘      └────────┬────────┘      └────────┬────────┘        │   │
│   │            │                        │                        │                  │   │
│   │            │                        ▼                        │                  │   │
│   │            │               ┌─────────────────┐               │                  │   │
│   │            │               │      M20        │               │                  │   │
│   │            │               │RetentionEnforcer│               │                  │   │
│   │            │               │   (R3 helper)   │               │                  │   │
│   │            │               └─────────────────┘               │                  │   │
│   │            │                                                 │                  │   │
│   │            └─────────────────────┬───────────────────────────┘                  │   │
│   │                                  ▼                                              │   │
│   │                       ┌─────────────────┐                                       │   │
│   │                       │      M22        │                                       │   │
│   │                       │ DreamExplorer   │                                       │   │
│   │                       │   (R5 lead)     │                                       │   │
│   │                       └────────┬────────┘                                       │   │
│   │                                │                                                │   │
│   │              ┌─────────────────┼─────────────────┐                              │   │
│   │              ▼                 ▼                 ▼                              │   │
│   │   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐                  │   │
│   │   │      M24        │ │      M25        │ │   Reused from   │                  │   │
│   │   │  TruthWriter    │ │  GapDetector    │ │      P02        │                  │   │
│   │   │   (R7 lead)     │ │   (R8 lead)     │ │ M02,M03,M06,M11 │                  │   │
│   │   └─────────────────┘ └─────────────────┘ └─────────────────┘                  │   │
│   │                                                                                  │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 P03-Specific Modules (M18-M25)

| Module | Name | Brain Analog | Phase | Responsibility |
|--------|------|--------------|-------|----------------|
| **M18** | EpisodicClusterer | Dentate Gyrus | R2 | DBSCAN clustering of episodes by embedding similarity |
| **M19** | DuplicateDetector | Entorhinal Cortex | R3 | SimHash deduplication and novelty scoring |
| **M20** | RetentionEnforcer | Synaptic Pruning | R3 | Decay calculation and archival decisions |
| **M21** | KGConsolidator | Temporal Cortex | R4 | Entity/relationship extraction and KG updates |
| **M22** | DreamExplorer | Prefrontal Cortex | R5 | Counterfactual simulation and insight generation |
| **M23** | ReplayCoordinator | CA3 | R1 | Importance scoring, replay pacing, batch selection |
| **M24** | TruthWriter | Neocortex | R7 | Memory layer write orchestration via outbox |
| **M25** | GapDetector | Hippocampal-Neocortical | R8 | Active Learning gap detection and emission |

### 7.3 Reused Modules from P02

| Module | Name | Used In Phase | Purpose in P03 |
|--------|------|---------------|----------------|
| **M02** | UltraBERT | R2, R4 | Embedding comparison for truth query |
| **M03** | SimHasher | R3 | Fingerprint comparison for deduplication |
| **M06** | EntityResolver | R4 | Entity deduplication in KG consolidation |
| **M11** | OutboxWriter | R7 | Durable writes to memory layers |

### 7.4 Module Interface Contracts

#### 7.4.1 M18 — EpisodicClusterer

```python
@dataclass
class EpisodeCluster:
    cluster_id: str                    # ULID
    member_events: List[str]           # event_ids
    centroid_embedding: np.ndarray     # 768-dim aggregated embedding
    temporal_span: Tuple[int, int]     # (start_utc, end_utc)
    primary_location: Optional[str]
    participant_ids: List[str]
    cluster_confidence: float          # [0-1] based on intra-cluster similarity

class EpisodicClusterer:
    """M18 — DBSCAN clustering of events into episodes."""

    def __init__(self, config: ClustererConfig):
        self.eps = config.eps                        # Default: 0.3 (cosine distance)
        self.min_samples = config.min_samples        # Default: 2
        self.max_cluster_size = config.max_cluster_size  # Default: 50
        self.temporal_window_hours = config.temporal_window  # Default: 4

    async def cluster(
        self,
        events: List[HippEvent],
        embeddings: Dict[str, np.ndarray]
    ) -> List[EpisodeCluster]:
        """
        Cluster events into episodes using DBSCAN.

        Input:
        - events: List of HippEvent from batch
        - embeddings: event_id → 768-dim embedding

        Output:
        - List of EpisodeCluster with member events

        Algorithm:
        1. Build distance matrix (1 - cosine_similarity)
        2. Apply temporal proximity bonus
        3. Run DBSCAN
        4. Post-process: split oversized clusters
        5. Calculate cluster metadata
        """
        pass

    def _calculate_cluster_confidence(
        self,
        cluster: EpisodeCluster,
        embeddings: Dict[str, np.ndarray]
    ) -> float:
        """
        Confidence = mean pairwise cosine similarity within cluster.
        Higher similarity = tighter cluster = higher confidence.
        """
        if len(cluster.member_events) < 2:
            return 0.5

        similarities = []
        for i, e1 in enumerate(cluster.member_events):
            for e2 in cluster.member_events[i+1:]:
                sim = cosine_similarity(embeddings[e1], embeddings[e2])
                similarities.append(sim)

        return np.mean(similarities)
```

#### 7.4.2 M19 — DuplicateDetector

```python
@dataclass
class DuplicationResult:
    event_id: str
    is_duplicate: bool                  # True if exact duplicate found
    near_duplicates: List[str]          # event_ids of near-duplicates
    novelty_score: float                # [0-1] higher = more novel
    duplicate_of: Optional[str]         # Canonical event if duplicate

class DuplicateDetector:
    """M19 — SimHash-based deduplication and novelty scoring."""

    def __init__(self, config: DeduplicationConfig):
        self.hamming_threshold = config.hamming_threshold  # Default: 3
        self.time_window_hours = config.time_window        # Default: 168 (1 week)
        self.novelty_weights = config.novelty_weights

    async def detect(
        self,
        event: HippEvent,
        existing_hashes: Dict[str, int]  # event_id → simhash
    ) -> DuplicationResult:
        """
        Detect duplicates and calculate novelty score.

        Algorithm:
        1. Compare simhash to existing hashes within time window
        2. Hamming distance ≤ threshold = near-duplicate
        3. Distance = 0 = exact duplicate
        4. Calculate novelty score based on multiple factors
        """
        pass

    def _calculate_novelty_score(
        self,
        event: HippEvent,
        near_duplicates: List[str]
    ) -> float:
        """
        Novelty formula (from Section 2.4):

        novelty = (1 - similarity_to_nearest) × (1 + first_time_bonus)
                  × (1 + milestone_bonus) × (1 - routine_penalty)
        """
        base_novelty = 1.0 - self._max_similarity(event, near_duplicates)

        # Bonuses for novel activities
        first_time = 0.2 if event.activity_category not in self._seen_categories else 0.0
        milestone = 0.3 if event.is_milestone_event else 0.0

        # Penalty for routine activities
        routine_penalty = 0.5 if self._is_routine(event) else 0.0

        novelty = base_novelty * (1 + first_time) * (1 + milestone) * (1 - routine_penalty)
        return min(1.0, max(0.0, novelty))
```

#### 7.4.3 M20 — RetentionEnforcer

```python
@dataclass
class RetentionDecision:
    record_id: str
    table: str
    current_decay: float
    new_decay: float
    action: str  # 'KEEP', 'DECAY', 'ARCHIVE', 'TOMBSTONE'
    reason: str

class RetentionEnforcer:
    """M20 — Implements synaptic homeostasis (forgetting)."""

    def __init__(self, config: RetentionConfig):
        # Decay constants per memory layer
        self.decay_rates = {
            'st_epi': 0.005,       # Episodes decay slowly
            'st_sem': 0.002,       # Semantic patterns even slower
            'st_procedural': 0.001, # Habits are very stable
            'st_social': 0.003,    # Relationships moderate
            'st_prospective': 0.010, # Intentions decay faster
            'st_kg_dom': 0.001,    # Entities are stable
            'st_kg_edges': 0.004,  # Edges more volatile
        }

        self.archive_threshold = config.archive_threshold  # Default: 0.1
        self.tombstone_threshold = config.tombstone_threshold  # Default: 0.01

    async def evaluate(
        self,
        record: TruthRecord,
        table: str
    ) -> RetentionDecision:
        """
        Calculate decay and recommend retention action.

        Formula: decay_factor = exp(-λ × days_since_observation)

        Where λ is the layer-specific decay rate.
        """
        days_since = (time.time() - record.last_observed_at) / 86400
        decay_rate = self.decay_rates.get(table, 0.005)

        new_decay = record.decay_factor * math.exp(-decay_rate * days_since)

        if new_decay < self.tombstone_threshold:
            action = 'TOMBSTONE'
            reason = f"Decay {new_decay:.4f} below tombstone threshold"
        elif new_decay < self.archive_threshold:
            action = 'ARCHIVE'
            reason = f"Decay {new_decay:.4f} below archive threshold"
        elif new_decay < record.decay_factor:
            action = 'DECAY'
            reason = f"Updated decay from {record.decay_factor:.4f} to {new_decay:.4f}"
        else:
            action = 'KEEP'
            reason = "No decay needed"

        return RetentionDecision(
            record_id=record.id,
            table=table,
            current_decay=record.decay_factor,
            new_decay=new_decay,
            action=action,
            reason=reason
        )
```

#### 7.4.4 M21 — KGConsolidator

```python
@dataclass
class KGUpdate:
    update_type: str  # 'CREATE_ENTITY', 'UPDATE_ENTITY', 'CREATE_EDGE', 'UPDATE_EDGE'
    entity_id: Optional[str]
    edge_id: Optional[str]
    data: Dict[str, Any]
    confidence: float
    source_episodes: List[str]

class KGConsolidator:
    """M21 — Knowledge Graph consolidation from episodes."""

    def __init__(self, config: KGConfig):
        self.entity_confidence_threshold = config.entity_threshold  # Default: 0.6
        self.edge_confidence_threshold = config.edge_threshold      # Default: 0.5
        self.co_occurrence_min = config.co_occurrence_min           # Default: 2

    async def consolidate(
        self,
        clusters: List[EpisodeCluster],
        existing_kg: KnowledgeGraph
    ) -> List[KGUpdate]:
        """
        Extract entities and relationships from episode clusters.

        Process:
        1. Extract entities from cluster events
        2. Resolve against existing st_kg_dom
        3. Detect relationships via co-occurrence
        4. Infer causal relationships
        5. Generate updates with confidence scores
        """
        updates = []

        for cluster in clusters:
            # Entity extraction and resolution
            entities = await self._extract_entities(cluster)
            for entity in entities:
                resolved = await self._resolve_entity(entity, existing_kg)
                if resolved.is_new:
                    updates.append(self._create_entity_update(resolved))
                elif resolved.should_update:
                    updates.append(self._update_entity_update(resolved))

            # Relationship discovery
            edges = await self._discover_relationships(cluster, entities)
            for edge in edges:
                if edge.confidence >= self.edge_confidence_threshold:
                    updates.append(self._create_edge_update(edge))

        return updates

    async def _discover_relationships(
        self,
        cluster: EpisodeCluster,
        entities: List[ResolvedEntity]
    ) -> List[InferredEdge]:
        """
        Discover relationships through co-occurrence analysis (Hebbian).

        "Entities that fire together wire together."
        """
        edges = []

        for i, e1 in enumerate(entities):
            for e2 in entities[i+1:]:
                co_occurrences = self._count_co_occurrences(e1.id, e2.id)

                if co_occurrences >= self.co_occurrence_min:
                    relationship_type = self._infer_relationship_type(e1, e2)
                    confidence = min(0.9, 0.3 + 0.1 * co_occurrences)

                    edges.append(InferredEdge(
                        source_id=e1.id,
                        target_id=e2.id,
                        relation_type=relationship_type,
                        confidence=confidence,
                        co_occurrence_count=co_occurrences
                    ))

        return edges
```

#### 7.4.5 M22 — DreamExplorer

```python
@dataclass
class Insight:
    insight_type: str  # 'COUNTERFACTUAL', 'PREDICTION', 'ASSOCIATION', 'ANOMALY'
    description: str
    confidence: float
    supporting_evidence: List[str]  # episode_ids
    novelty_score: float

class DreamExplorer:
    """M22 — REM-phase creative exploration (optional phase R5)."""

    def __init__(self, config: DreamConfig):
        self.exploration_depth = config.depth        # Default: 3 (hops in KG)
        self.creativity_factor = config.creativity   # Default: 0.5 (0=conservative, 1=wild)
        self.max_insights = config.max_insights      # Default: 10 per cycle

    async def explore(
        self,
        recent_patterns: List[SemanticPattern],
        kg_subgraph: KnowledgeGraph
    ) -> List[Insight]:
        """
        Generate insights through creative exploration.

        Algorithms:
        - CPN: Counterfactual Perturbation Network
        - TPN-MCTS: Temporal Prediction with Monte Carlo Tree Search
        - BGT-SM: Remote association discovery (Mednick)

        Note: This is the most experimental module.
        Currently implements simplified versions.
        """
        insights = []

        # 1. Counterfactual thinking: "What if X had done Y instead?"
        counterfactuals = await self._generate_counterfactuals(recent_patterns)
        insights.extend(counterfactuals)

        # 2. Forward prediction: "Based on pattern, what might happen next?"
        predictions = await self._generate_predictions(recent_patterns, kg_subgraph)
        insights.extend(predictions)

        # 3. Remote associations: "Unexpected connections across domains"
        associations = await self._find_remote_associations(kg_subgraph)
        insights.extend(associations)

        # Sort by novelty and return top N
        insights.sort(key=lambda x: x.novelty_score, reverse=True)
        return insights[:self.max_insights]
```

#### 7.4.6 M23 — ReplayCoordinator

```python
class ReplayCoordinator:
    """M23 — Coordinates hippocampal replay (R1 phase lead)."""

    def __init__(self, config: ReplayConfig):
        self.importance_weights = config.weights  # See formula in Section 2.4
        self.batch_size = config.batch_size       # Default: 1000
        self.replay_speed = config.speed          # Metaphorical 10-20x

    async def select_batch(
        self,
        pending_events: AsyncIterator[HippEvent],
        max_events: int
    ) -> List[HippEvent]:
        """
        Select events for consolidation based on importance.

        Priority order:
        1. High emotional salience (affect_valence, affect_intensity)
        2. Recent events (decay bonus)
        3. Events with novel entities/activities
        4. Events completing patterns
        """
        candidates = []
        async for event in pending_events:
            importance = self._calculate_importance(event)
            candidates.append((importance, event))

            if len(candidates) >= max_events * 2:  # Over-sample then sort
                break

        candidates.sort(reverse=True)
        return [e for _, e in candidates[:max_events]]

    def _calculate_importance(self, event: HippEvent) -> float:
        """
        Importance formula from Section 2.4:

        I = w_e × emotional_score + w_r × recency_score
          + w_n × novelty_score + w_s × social_score
        """
        w = self.importance_weights

        emotional = abs(event.affect_valence or 0) * (event.affect_intensity or 0.5)
        recency = math.exp(-0.1 * self._days_old(event))
        novelty = event.novelty_score or 0.5
        social = min(1.0, (event.num_participants or 1) / 5.0)

        return (
            w['emotional'] * emotional +
            w['recency'] * recency +
            w['novelty'] * novelty +
            w['social'] * social
        )
```

#### 7.4.7 M24 — TruthWriter

```python
class TruthWriter:
    """M24 — Orchestrates durable writes to memory layers (R7 lead)."""

    def __init__(self, config: WriterConfig):
        self.batch_size = config.batch_size          # Default: 100
        self.transaction_mode = config.transaction   # 'ATOMIC' or 'PARTIAL'
        self.outbox_driver = config.outbox_driver    # st_outbox configuration

    async def write_decisions(
        self,
        decisions: List[ReconciliationDecision]
    ) -> WriteResult:
        """
        Write reconciliation decisions to memory layers.

        All writes go through st_outbox for durability.
        P08 is notified for embedding index updates.
        """
        results = WriteResult(successes=[], failures=[])

        for batch in self._batch(decisions, self.batch_size):
            async with self.db.transaction() as txn:
                for decision in batch:
                    try:
                        await self._apply_decision(decision, txn)
                        results.successes.append(decision.id)
                    except Exception as e:
                        results.failures.append((decision.id, str(e)))
                        if self.transaction_mode == 'ATOMIC':
                            raise  # Rollback entire batch

        return results

    async def _apply_decision(
        self,
        decision: ReconciliationDecision,
        txn: Transaction
    ) -> None:
        """Route decision to appropriate writer method."""
        if decision.type == 'REINFORCE':
            await self._reinforce(decision, txn)
        elif decision.type == 'EXTEND':
            await self._extend(decision, txn)
        elif decision.type == 'CREATE':
            await self._create(decision, txn)
        elif decision.type == 'EVOLVE':
            await self._evolve(decision, txn)
        elif decision.type == 'PRUNE':
            await self._prune(decision, txn)
        elif decision.type == 'CONTRADICT':
            # Don't write, but emit gap
            await self._emit_gap(decision, txn)
```

#### 7.4.8 M25 — GapDetector

```python
class GapDetector:
    """M25 — Detects knowledge gaps for Active Learning (R8 lead)."""

    def __init__(self, config: GapConfig):
        self.thresholds = config.thresholds
        self.max_gaps_per_cycle = config.max_gaps  # Default: 50

    async def detect(
        self,
        reconciliation_results: List[ReconciliationResult]
    ) -> List[GapRecord]:
        """
        Analyze reconciliation results for knowledge gaps.

        See Section 5.2 for detailed algorithm.
        """
        gaps = []

        for result in reconciliation_results:
            # Ambiguous entities
            if result.has_ambiguous_entities:
                gaps.extend(self._create_ambiguity_gaps(result))

            # Low-confidence edges
            if result.has_low_confidence_edges:
                gaps.extend(self._create_edge_gaps(result))

            # Contradictions
            if result.has_contradictions:
                gaps.extend(self._create_contradiction_gaps(result))

        # Sort by importance, cap at max
        gaps.sort(key=lambda g: g.importance_score, reverse=True)
        return gaps[:self.max_gaps_per_cycle]
```

---

## 8. Observability & Metrics

> **Status**: COMPLETE

### 8.1 Metrics Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           P03 OBSERVABILITY ARCHITECTURE                                 │
│                                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              P03 PIPELINE                                        │   │
│   │                                                                                  │   │
│   │   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │   │
│   │   │   R0    │→│   R1    │→│   R2    │→│   R3    │→│   R4    │→│  R5-R8  │      │   │
│   │   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘      │   │
│   │        │           │           │           │           │           │             │   │
│   │        ▼           ▼           ▼           ▼           ▼           ▼             │   │
│   │   ┌─────────────────────────────────────────────────────────────────────────┐   │   │
│   │   │                        METRICS COLLECTOR                                 │   │   │
│   │   │                                                                          │   │   │
│   │   │  Counters  │  Histograms  │  Gauges  │  Labels                          │   │   │
│   │   └──────────────────────────────┬──────────────────────────────────────────┘   │   │
│   │                                  │                                               │   │
│   └──────────────────────────────────┼───────────────────────────────────────────────┘   │
│                                      │                                                    │
│              ┌───────────────────────┼───────────────────────┐                           │
│              ▼                       ▼                       ▼                           │
│   ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐                   │
│   │   Prometheus    │     │     Jaeger      │     │   Structured    │                   │
│   │    Metrics      │     │    Tracing      │     │     Logs        │                   │
│   │                 │     │                 │     │                 │                   │
│   │ • Counters      │     │ • Span tree     │     │ • JSON format   │                   │
│   │ • Histograms    │     │ • Baggage       │     │ • Correlation   │                   │
│   │ • Gauges        │     │ • Events        │     │ • Levels        │                   │
│   └────────┬────────┘     └────────┬────────┘     └────────┬────────┘                   │
│            │                       │                       │                             │
│            └───────────────────────┼───────────────────────┘                             │
│                                    ▼                                                     │
│                         ┌─────────────────┐                                              │
│                         │   Dashboards    │                                              │
│                         │  (Grafana/K8s)  │                                              │
│                         └─────────────────┘                                              │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Metric Definitions

#### 8.2.1 Consolidation Cycle Metrics

```python
# Prometheus metric definitions
from prometheus_client import Counter, Histogram, Gauge, Info

# Cycle execution
p03_cycle_total = Counter(
    'p03_cycle_total',
    'Total consolidation cycles executed',
    ['tenant_id', 'status']  # status: success, failure, partial, aborted
)

p03_cycle_duration_seconds = Histogram(
    'p03_cycle_duration_seconds',
    'Consolidation cycle duration',
    ['tenant_id', 'phase'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)

p03_events_processed_total = Counter(
    'p03_events_processed_total',
    'Total events processed during consolidation',
    ['tenant_id', 'space_id', 'outcome']  # outcome: consolidated, duplicate, pruned
)

p03_pending_events = Gauge(
    'p03_pending_events',
    'Number of events pending consolidation',
    ['tenant_id', 'space_id']
)

# Phase timing
p03_phase_duration_seconds = Histogram(
    'p03_phase_duration_seconds',
    'Duration of each consolidation phase',
    ['tenant_id', 'phase'],  # R0, R1, R2, ..., R8
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120]
)
```

#### 8.2.2 Decision Metrics

```python
# Reconciliation decisions
p03_decisions_total = Counter(
    'p03_decisions_total',
    'Reconciliation decisions by type',
    ['tenant_id', 'decision_type', 'target_layer']
    # decision_type: REINFORCE, EXTEND, CREATE, EVOLVE, PRUNE, CONTRADICT
    # target_layer: st_epi, st_sem, st_procedural, etc.
)

p03_decision_confidence = Histogram(
    'p03_decision_confidence',
    'Confidence scores of reconciliation decisions',
    ['tenant_id', 'decision_type'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
)

p03_similarity_scores = Histogram(
    'p03_similarity_scores',
    'Similarity scores during truth matching',
    ['tenant_id', 'match_result'],  # match, partial, no_match
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
)
```

#### 8.2.3 Gap Detection Metrics

```python
# Active Learning gaps
p03_gaps_detected_total = Counter(
    'p03_gaps_detected_total',
    'Knowledge gaps detected during consolidation',
    ['tenant_id', 'gap_type']
    # gap_type: AMBIGUOUS_ENTITY, LOW_CONFIDENCE_EDGE, MISSING_ATTRIBUTE,
    #           CONTRADICTION, CONCEPT_DRIFT, STRUCTURAL_HOLE, STALE_ANCHOR
)

p03_gap_importance_score = Histogram(
    'p03_gap_importance_score',
    'Importance scores of detected gaps',
    ['tenant_id', 'gap_type'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

p03_gaps_pending = Gauge(
    'p03_gaps_pending',
    'Number of gaps pending resolution in st_learning_queue',
    ['tenant_id', 'gap_type', 'status']
)
```

#### 8.2.4 Memory Layer Metrics

```python
# Truth layer operations
p03_layer_records_total = Counter(
    'p03_layer_records_total',
    'Records created/updated in memory layers',
    ['tenant_id', 'layer', 'operation']  # operation: create, update, archive, tombstone
)

p03_layer_size = Gauge(
    'p03_layer_size',
    'Current size of memory layer (canonical records only)',
    ['tenant_id', 'layer', 'archival_status']
)

p03_layer_avg_confidence = Gauge(
    'p03_layer_avg_confidence',
    'Average confidence score in memory layer',
    ['tenant_id', 'layer']
)

p03_layer_avg_decay = Gauge(
    'p03_layer_avg_decay',
    'Average decay factor in memory layer',
    ['tenant_id', 'layer']
)
```

#### 8.2.5 Module Performance Metrics

```python
# Per-module metrics
p03_module_duration_seconds = Histogram(
    'p03_module_duration_seconds',
    'Execution time per module',
    ['tenant_id', 'module'],  # M18, M19, M20, ..., M25
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5, 10, 30]
)

p03_module_items_processed = Counter(
    'p03_module_items_processed',
    'Items processed by each module',
    ['tenant_id', 'module', 'outcome']
)

p03_clustering_clusters_created = Counter(
    'p03_clustering_clusters_created',
    'Episode clusters created by M18',
    ['tenant_id']
)

p03_clustering_cluster_size = Histogram(
    'p03_clustering_cluster_size',
    'Size of episode clusters',
    ['tenant_id'],
    buckets=[1, 2, 5, 10, 20, 50, 100]
)
```

### 8.3 Distributed Tracing

#### 8.3.1 Span Hierarchy

```python
from opentelemetry import trace
from opentelemetry.trace import SpanKind

tracer = trace.get_tracer("p03.consolidation")

class ConsolidationTracer:
    """Distributed tracing for P03 consolidation cycles."""

    async def trace_cycle(
        self,
        cycle_id: str,
        tenant_id: str,
        space_id: str
    ):
        """
        Span hierarchy:

        p03.consolidation_cycle (root)
        ├── p03.r0.trigger_detection
        ├── p03.r1.replay
        │   ├── p03.r1.batch_selection
        │   └── p03.r1.importance_scoring
        ├── p03.r2.clustering
        │   ├── p03.r2.embedding_fetch
        │   ├── p03.r2.dbscan
        │   └── p03.r2.pattern_extraction
        ├── p03.r3.forgetting
        │   ├── p03.r3.deduplication
        │   └── p03.r3.retention_enforcement
        ├── p03.r4.kg_consolidation
        │   ├── p03.r4.entity_extraction
        │   ├── p03.r4.entity_resolution
        │   └── p03.r4.edge_discovery
        ├── p03.r5.dream_exploration (optional)
        ├── p03.r6.staging_update
        ├── p03.r7.truth_write
        │   ├── p03.r7.outbox_insert
        │   └── p03.r7.layer_write (per layer)
        └── p03.r8.event_emission
            ├── p03.r8.bus_publish
            └── p03.r8.gap_emission
        """
        with tracer.start_as_current_span(
            "p03.consolidation_cycle",
            kind=SpanKind.INTERNAL,
            attributes={
                "cycle_id": cycle_id,
                "tenant_id": tenant_id,
                "space_id": space_id,
            }
        ) as root_span:
            yield root_span

    def start_phase_span(self, phase: str, **attributes):
        """Start a span for a consolidation phase."""
        return tracer.start_as_current_span(
            f"p03.{phase}",
            kind=SpanKind.INTERNAL,
            attributes=attributes
        )
```

#### 8.3.2 Trace Context Propagation

```python
class TraceContext:
    """Propagate trace context across P03 phases."""

    # Required baggage items
    REQUIRED_BAGGAGE = [
        'cycle_id',           # P03 cycle identifier
        'tenant_id',          # Tenant isolation
        'space_id',           # Space isolation
        'correlation_id',     # Cross-service correlation
    ]

    # Optional baggage items
    OPTIONAL_BAGGAGE = [
        'source_event_ids',   # Comma-separated source events
        'triggered_by',       # What triggered this cycle
        'parent_cycle_id',    # If retry/continuation
    ]

    @staticmethod
    def inject_into_event(event_payload: dict, span: trace.Span) -> dict:
        """Inject trace context into bus event payload."""
        event_payload['trace_id'] = format(span.get_span_context().trace_id, '032x')
        event_payload['span_id'] = format(span.get_span_context().span_id, '016x')
        return event_payload
```

### 8.4 Structured Logging

#### 8.4.1 Log Schema

```python
from structlog import get_logger

logger = get_logger()

# Standard log fields for all P03 logs
P03_LOG_SCHEMA = {
    # Required fields
    "timestamp": "ISO 8601 timestamp",
    "level": "DEBUG | INFO | WARN | ERROR",
    "message": "Human-readable message",
    "correlation_id": "Trace correlation ID",

    # P03-specific fields
    "cycle_id": "P03 cycle identifier",
    "phase": "R0 | R1 | R2 | ... | R8",
    "tenant_id": "Tenant ID",
    "space_id": "Space ID",

    # Contextual fields (optional)
    "event_id": "Source event ID if applicable",
    "decision_type": "REINFORCE | EXTEND | CREATE | ...",
    "target_layer": "st_epi | st_sem | ...",
    "duration_ms": "Operation duration",
    "error_code": "Error code if error",
    "error_message": "Error message if error",
}

# Example log calls
logger.info(
    "consolidation_cycle_started",
    cycle_id="01HXYZ...",
    tenant_id="tenant_123",
    space_id="space_456",
    phase="R0",
    pending_events=1500
)

logger.debug(
    "reconciliation_decision",
    cycle_id="01HXYZ...",
    phase="R7",
    event_id="evt_789",
    decision_type="REINFORCE",
    target_layer="st_sem",
    similarity_score=0.92,
    confidence_before=0.75,
    confidence_after=0.80
)

logger.error(
    "truth_write_failed",
    cycle_id="01HXYZ...",
    phase="R7",
    target_layer="st_epi",
    error_code="CONSTRAINT_VIOLATION",
    error_message="Unique constraint violated on episode_id",
    affected_events=["evt_001", "evt_002"]
)
```

#### 8.4.2 Log Levels by Phase

| Phase | INFO | DEBUG | WARN | ERROR |
|-------|------|-------|------|-------|
| R0 | Cycle start, trigger type | Lock acquisition | Lock contention | Lock timeout |
| R1 | Batch size, importance range | Per-event scoring | Low-importance batch | Batch selection failed |
| R2 | Cluster count, avg size | Per-cluster details | Oversized clusters | Clustering failed |
| R3 | Duplicates found, pruned | Per-event decisions | High novelty conflicts | Dedup index error |
| R4 | Entities/edges created | Resolution details | Ambiguous entities | KG update failed |
| R5 | Insights generated | Counterfactual details | No insights found | Exploration error |
| R6 | Events updated | Per-event status | Update conflicts | Staging update failed |
| R7 | Records written | Per-layer counts | Retry scenarios | Write transaction failed |
| R8 | Events emitted, gaps detected | Per-event emission | Bus unavailable | Emission failed |

### 8.5 Dashboards

#### 8.5.1 P03 Health Dashboard

```yaml
# Grafana dashboard definition (simplified)
dashboard:
  title: "P03 Consolidation Health"

  rows:
    - title: "Cycle Overview"
      panels:
        - type: stat
          title: "Cycles (24h)"
          query: "sum(increase(p03_cycle_total[24h]))"

        - type: gauge
          title: "Success Rate"
          query: "sum(rate(p03_cycle_total{status='success'}[1h])) / sum(rate(p03_cycle_total[1h]))"
          thresholds: [0.9, 0.95, 0.99]

        - type: timeseries
          title: "Cycle Duration"
          query: "histogram_quantile(0.95, rate(p03_cycle_duration_seconds_bucket[5m]))"

    - title: "Event Processing"
      panels:
        - type: timeseries
          title: "Events Processed/Hour"
          query: "sum(rate(p03_events_processed_total[1h])) * 3600"

        - type: gauge
          title: "Pending Queue"
          query: "sum(p03_pending_events)"
          thresholds: [1000, 5000, 10000]

    - title: "Decisions"
      panels:
        - type: piechart
          title: "Decision Distribution"
          query: "sum by (decision_type) (increase(p03_decisions_total[24h]))"
```

#### 8.5.2 Memory Growth Dashboard

```yaml
dashboard:
  title: "Memory Layer Growth"

  rows:
    - title: "Layer Sizes"
      panels:
        - type: timeseries
          title: "Records by Layer"
          query: "sum by (layer) (p03_layer_size{archival_status='ACTIVE'})"

        - type: timeseries
          title: "Creation vs Archival Rate"
          queries:
            - "sum(rate(p03_layer_records_total{operation='create'}[1h]))"
            - "sum(rate(p03_layer_records_total{operation='archive'}[1h]))"

    - title: "Quality Metrics"
      panels:
        - type: gauge
          title: "Avg Confidence (st_sem)"
          query: "avg(p03_layer_avg_confidence{layer='st_sem'})"

        - type: heatmap
          title: "Decay Factor Distribution"
          query: "p03_layer_avg_decay"
```

#### 8.5.3 Active Learning Dashboard

```yaml
dashboard:
  title: "Active Learning Integration"

  rows:
    - title: "Gap Detection"
      panels:
        - type: timeseries
          title: "Gaps Detected/Day"
          query: "sum(increase(p03_gaps_detected_total[24h]))"

        - type: piechart
          title: "Gap Types"
          query: "sum by (gap_type) (p03_gaps_pending)"

    - title: "Resolution"
      panels:
        - type: stat
          title: "Resolution Rate"
          query: "sum(rate(p06_gaps_resolved_total[24h])) / sum(rate(p03_gaps_detected_total[24h]))"

        - type: timeseries
          title: "Pending Gap Queue"
          query: "sum(p03_gaps_pending{status='PENDING'})"
```

### 8.6 Alerting Rules

```yaml
# Prometheus alerting rules
groups:
  - name: p03_alerts
    rules:
      - alert: P03CycleFailureRate
        expr: |
          sum(rate(p03_cycle_total{status="failure"}[1h])) /
          sum(rate(p03_cycle_total[1h])) > 0.1
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "P03 cycle failure rate above 10%"

      - alert: P03PendingQueueHigh
        expr: sum(p03_pending_events) > 10000
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "P03 pending event queue above 10K"

      - alert: P03CycleDurationHigh
        expr: |
          histogram_quantile(0.95, rate(p03_cycle_duration_seconds_bucket[15m])) > 300
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "P03 cycle p95 duration above 5 minutes"

      - alert: P03GapQueueOverflow
        expr: sum(p03_gaps_pending{status="PENDING"}) > 500
        for: 1h
        labels:
          severity: info
        annotations:
          summary: "P03 gap queue above 500 pending items"
```

---

## 9. Integration Contracts

> **Status**: COMPLETE

### 9.1 Contract Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           P03 INTEGRATION CONTRACT MAP                                   │
│                                                                                          │
│      ┌───────────────────────────────────────────────────────────────────────────┐      │
│      │                         UPSTREAM (Input Sources)                           │      │
│      │                                                                            │      │
│      │   ┌─────────┐  event.indexed  ┌─────────┐  embedding.ready  ┌─────────┐   │      │
│      │   │   P02   │ ───────────────→│   P03   │ ←─────────────────│   P08   │   │      │
│      │   │  Write  │                 │  Consol │                    │ Embed Idx│   │      │
│      │   └─────────┘                 └────┬────┘                    └─────────┘   │      │
│      │                                    │                                       │      │
│      └────────────────────────────────────┼───────────────────────────────────────┘      │
│                                           │                                              │
│                                           ▼                                              │
│      ┌───────────────────────────────────────────────────────────────────────────┐      │
│      │                        DOWNSTREAM (Output Sinks)                           │      │
│      │                                                                            │      │
│      │   ┌─────────┐  gap.detected   ┌─────────┐  embedding.created  ┌─────────┐ │      │
│      │   │   P06   │ ←───────────────│   P03   │ ──────────────────→ │   P08   │ │      │
│      │   │  Active │                 │  Consol │                      │ Embed Idx│ │      │
│      │   │ Learning│                 └────┬────┘                      └─────────┘ │      │
│      │   └─────────┘                      │                                       │      │
│      │                                    ▼                                       │      │
│      │   ┌─────────┐  attention.query ┌─────────┐  memory.consolidated          │      │
│      │   │   P05   │ ←───────────────→│   P03   │ ────────────────→ [Consumers]  │      │
│      │   │Attention│                  │  Consol │                                │      │
│      │   │ Budget  │                  └─────────┘                                │      │
│      │   └─────────┘                                                             │      │
│      │                                                                            │      │
│      └───────────────────────────────────────────────────────────────────────────┘      │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 P02 → P03 Contract

#### 9.2.1 Input Table: st_hipp_events

```yaml
# AsyncAPI-style contract
contract:
  name: p02_to_p03_events
  version: "1.0.0"
  type: table_poll

  source:
    table: st_hipp_events
    schema: hippocampus

  filter:
    required:
      - "consolidation_status IS NULL OR consolidation_status = 'PENDING'"
      - "embedding_status = 'READY'"
      - "tenant_id = :tenant_id"
      - "space_id = :space_id"
    optional:
      - "created_at >= :since_timestamp"
      - "salience_score >= :min_salience"

  required_columns:
    - name: event_id
      type: TEXT
      description: Primary key, ULID format
    - name: tenant_id
      type: TEXT
      description: Tenant isolation key
    - name: space_id
      type: TEXT
      description: Space isolation key
    - name: actor_id
      type: TEXT
      description: Actor who generated event
    - name: content_hash
      type: TEXT
      description: SimHash for deduplication
    - name: embedding_id
      type: TEXT
      description: Foreign key to st_vec
    - name: salience_score
      type: REAL
      description: P02-computed salience (0-1)
    - name: policy_band
      type: TEXT
      description: Privacy band (GREEN/AMBER/RED)
    - name: entities_json
      type: TEXT
      description: JSON array of extracted entities
    - name: triplets_json
      type: TEXT
      description: JSON array of (subj, pred, obj) triplets
    - name: created_at
      type: INTEGER
      description: Unix epoch milliseconds

  ordering:
    - column: salience_score
      direction: DESC
    - column: created_at
      direction: ASC
```

#### 9.2.2 Event Trigger: p02.event.indexed.v1

```yaml
# AsyncAPI channel definition
channel:
  name: p02.event.indexed.v1
  protocol: kafka
  description: Emitted when P02 completes event indexing

  publish:
    operationId: onEventIndexed
    message:
      name: EventIndexedPayload
      contentType: application/json
      payload:
        type: object
        required:
          - event_id
          - tenant_id
          - space_id
          - salience_score
          - embedding_status
          - indexed_at
        properties:
          event_id:
            type: string
            format: ulid
          tenant_id:
            type: string
          space_id:
            type: string
          salience_score:
            type: number
            minimum: 0
            maximum: 1
          embedding_status:
            type: string
            enum: [READY, PENDING, FAILED]
          indexed_at:
            type: integer
            description: Unix epoch milliseconds

  binding:
    kafka:
      topic: familyos.p02.events
      partitionKey: $.tenant_id
```

#### 9.2.3 Embedding Readiness: st_vec

```yaml
# Embedding availability contract
contract:
  name: p02_to_p03_embeddings
  version: "1.0.0"
  type: table_join

  source:
    table: st_vec
    schema: vector_store

  join_condition: "st_vec.id = st_hipp_events.embedding_id"

  required_columns:
    - name: id
      type: TEXT
      description: Embedding ID (matches embedding_id in st_hipp_events)
    - name: vector
      type: BLOB
      description: 768-dim UltraBERT embedding
    - name: status
      type: TEXT
      enum: [READY, PENDING, FAILED]
      description: Must be READY for P03 processing
    - name: model_version
      type: TEXT
      description: Model version for compatibility checks
```

### 9.3 P03 → P06 Contract (Active Learning)

#### 9.3.1 Gap Emission: p03.gap.detected.v1

```yaml
channel:
  name: p03.gap.detected.v1
  protocol: kafka
  description: Emitted when P03 detects a knowledge gap requiring clarification

  publish:
    operationId: onGapDetected
    message:
      name: GapDetectedPayload
      contentType: application/json
      payload:
        type: object
        required:
          - gap_id
          - tenant_id
          - space_id
          - gap_type
          - importance_score
          - context
          - detected_at
        properties:
          gap_id:
            type: string
            format: ulid
          tenant_id:
            type: string
          space_id:
            type: string
          actor_id:
            type: string
            description: Preferred actor to ask (if known)
          gap_type:
            type: string
            enum:
              - AMBIGUOUS_ENTITY
              - LOW_CONFIDENCE_EDGE
              - MISSING_ATTRIBUTE
              - CONTRADICTION
              - CONCEPT_DRIFT
              - STRUCTURAL_HOLE
              - STALE_ANCHOR
          importance_score:
            type: number
            minimum: 0
            maximum: 1
          context:
            type: object
            description: Gap-specific context
            properties:
              source_event_ids:
                type: array
                items:
                  type: string
              conflicting_truths:
                type: array
                items:
                  type: object
                  properties:
                    truth_id:
                      type: string
                    layer:
                      type: string
                    confidence:
                      type: number
              question_template:
                type: string
                description: Suggested question phrasing
          ttl_hours:
            type: integer
            default: 168
            description: Gap expires if not resolved within TTL
          detected_at:
            type: integer
            description: Unix epoch milliseconds

  binding:
    kafka:
      topic: familyos.p03.gaps
      partitionKey: $.tenant_id
```

#### 9.3.2 Resolution Acknowledgment: p06.gap.resolved.v1

```yaml
channel:
  name: p06.gap.resolved.v1
  protocol: kafka
  description: P06 emits when user provides answer to gap

  subscribe:
    operationId: onGapResolved
    message:
      name: GapResolvedPayload
      contentType: application/json
      payload:
        type: object
        required:
          - gap_id
          - resolution_type
          - resolved_at
        properties:
          gap_id:
            type: string
            format: ulid
          resolution_type:
            type: string
            enum:
              - ANSWERED      # User provided answer
              - DISMISSED     # User declined to answer
              - EXPIRED       # TTL exceeded
              - SUPERSEDED    # New gap replaced this one
          answer_event_id:
            type: string
            description: New event containing user's answer (if ANSWERED)
          confidence_boost:
            type: number
            description: How much to boost related truth confidence
          resolved_at:
            type: integer
            description: Unix epoch milliseconds

  binding:
    kafka:
      topic: familyos.p06.resolutions
      partitionKey: $.gap_id
```

### 9.4 P03 → P08 Contract (Embedding Index)

#### 9.4.1 Embedding Creation: p03.embedding.created.v1

```yaml
channel:
  name: p03.embedding.created.v1
  protocol: kafka
  description: P03 emits when new truth layer embeddings are created

  publish:
    operationId: onEmbeddingCreated
    message:
      name: EmbeddingCreatedPayload
      contentType: application/json
      payload:
        type: object
        required:
          - embedding_id
          - tenant_id
          - owner_type
          - owner_id
          - model_version
          - created_at
        properties:
          embedding_id:
            type: string
            format: ulid
          tenant_id:
            type: string
          space_id:
            type: string
          owner_type:
            type: string
            enum:
              - EPISODIC_CLUSTER
              - SEMANTIC_CONCEPT
              - ENTITY_NODE
              - PROCEDURAL_STEP
          owner_id:
            type: string
            description: ID of the truth record owning this embedding
          layer:
            type: string
            enum: [st_epi, st_sem, st_kg_dom, st_procedural]
          model_version:
            type: string
            description: UltraBERT model version
          index_priority:
            type: string
            enum: [HIGH, NORMAL, LOW]
            default: NORMAL
          created_at:
            type: integer

  binding:
    kafka:
      topic: familyos.p03.embeddings
      partitionKey: $.tenant_id
```

#### 9.4.2 Index Coordination Protocol

```python
@dataclass
class P08CoordinationConfig:
    """Configuration for P03 ↔ P08 coordination."""

    # Synchronization mode
    mode: Literal['SYNC', 'ASYNC'] = 'ASYNC'

    # SYNC mode: wait for P08 acknowledgment
    sync_timeout_seconds: int = 30

    # ASYNC mode: fire-and-forget with eventual consistency
    async_batch_size: int = 100
    async_flush_interval_seconds: int = 5

    # Retry on P08 unavailability
    retry_on_failure: bool = True
    max_retries: int = 3

    # Circuit breaker
    circuit_breaker_enabled: bool = True
    failure_threshold: int = 5
    reset_timeout_seconds: int = 60


class P08Coordinator:
    """Coordinate embedding index updates with P08."""

    async def notify_embedding_created(
        self,
        embedding: EmbeddingRecord,
        config: P08CoordinationConfig
    ) -> bool:
        """
        Notify P08 of new embedding for indexing.

        In SYNC mode, waits for P08 to acknowledge indexing.
        In ASYNC mode, publishes event and returns immediately.
        """
        if config.mode == 'SYNC':
            return await self._sync_notify(embedding, config)
        else:
            return await self._async_notify(embedding, config)

    async def _sync_notify(
        self,
        embedding: EmbeddingRecord,
        config: P08CoordinationConfig
    ) -> bool:
        """Synchronous notification with acknowledgment."""
        event = self._build_embedding_event(embedding)

        # Publish and wait for ack
        ack = await self.bus.publish_and_wait(
            topic='familyos.p03.embeddings',
            payload=event,
            timeout=config.sync_timeout_seconds,
            ack_topic='familyos.p08.embedding.indexed.v1',
            correlation_key=embedding.id
        )

        return ack is not None

    async def _async_notify(
        self,
        embedding: EmbeddingRecord,
        config: P08CoordinationConfig
    ) -> bool:
        """Asynchronous fire-and-forget notification."""
        event = self._build_embedding_event(embedding)

        # Add to batch buffer
        self._batch_buffer.append(event)

        # Flush if batch full
        if len(self._batch_buffer) >= config.async_batch_size:
            await self._flush_batch()

        return True
```

### 9.5 P03 ↔ P05 Attention Contract

#### 9.5.1 Availability Query

```yaml
# Request/Response contract (not event-based)
contract:
  name: p03_to_p05_availability
  version: "1.0.0"
  type: request_response

  request:
    method: query_availability
    parameters:
      - name: actor_id
        type: string
        required: true
      - name: tenant_id
        type: string
        required: true
      - name: space_id
        type: string
        required: true
      - name: question_type
        type: string
        enum: [CLARIFICATION, PREFERENCE, CONFIRMATION]
        required: false

  response:
    type: object
    properties:
      actor_id:
        type: string
      is_available:
        type: boolean
      availability_score:
        type: number
        minimum: 0
        maximum: 1
        description: 1.0 = fully available, 0.0 = do not disturb
      next_available_at:
        type: integer
        description: Unix epoch when user might be available (if not now)
      rejection_reason:
        type: string
        enum: [DND_MODE, BUDGET_EXHAUSTED, RATE_LIMITED, OFFLINE]
```

#### 9.5.2 Token Budget Query

```yaml
contract:
  name: p03_to_p05_budget
  version: "1.0.0"
  type: request_response

  request:
    method: query_token_budget
    parameters:
      - name: actor_id
        type: string
        required: true
      - name: tenant_id
        type: string
        required: true
      - name: question_type
        type: string
        required: false

  response:
    type: object
    properties:
      actor_id:
        type: string
      tokens_remaining:
        type: integer
        description: Tokens left in current budget window
      tokens_total:
        type: integer
        description: Total tokens in budget window
      window_start:
        type: integer
        description: Unix epoch of current window start
      window_end:
        type: integer
        description: Unix epoch of current window end
      refill_rate:
        type: integer
        description: Tokens added per refill interval
      refill_interval_seconds:
        type: integer
```

### 9.6 P03 Output Events

#### 9.6.1 Consolidation Complete: p03.memory.consolidated.v1

```yaml
channel:
  name: p03.memory.consolidated.v1
  protocol: kafka
  description: Emitted when P03 completes a consolidation cycle

  publish:
    operationId: onMemoryConsolidated
    message:
      name: MemoryConsolidatedPayload
      contentType: application/json
      payload:
        type: object
        required:
          - cycle_id
          - tenant_id
          - space_id
          - status
          - summary
          - completed_at
        properties:
          cycle_id:
            type: string
            format: ulid
          tenant_id:
            type: string
          space_id:
            type: string
          status:
            type: string
            enum: [SUCCESS, PARTIAL, FAILED]
          summary:
            type: object
            properties:
              events_processed:
                type: integer
              clusters_created:
                type: integer
              duplicates_found:
                type: integer
              entities_created:
                type: integer
              edges_created:
                type: integer
              gaps_detected:
                type: integer
              decisions:
                type: object
                properties:
                  reinforce:
                    type: integer
                  extend:
                    type: integer
                  create:
                    type: integer
                  evolve:
                    type: integer
                  prune:
                    type: integer
                  contradict:
                    type: integer
          duration_ms:
            type: integer
          completed_at:
            type: integer

  binding:
    kafka:
      topic: familyos.p03.cycles
      partitionKey: $.tenant_id
```

### 9.7 Contract Validation

```python
from pydantic import BaseModel, validator
from typing import List, Optional

class ContractValidator:
    """Validate P03 integration contracts at runtime."""

    def validate_incoming_event(
        self,
        topic: str,
        payload: dict
    ) -> bool:
        """Validate incoming event matches contract."""
        schema = self._get_schema_for_topic(topic)
        try:
            schema.parse_obj(payload)
            return True
        except ValidationError as e:
            logger.error(
                "contract_validation_failed",
                topic=topic,
                errors=e.errors()
            )
            return False

    def validate_outgoing_event(
        self,
        topic: str,
        payload: dict
    ) -> bool:
        """Validate outgoing event before publishing."""
        schema = self._get_schema_for_topic(topic)
        schema.parse_obj(payload)  # Raise if invalid
        return True

    def _get_schema_for_topic(self, topic: str) -> BaseModel:
        """Return Pydantic schema for topic."""
        return {
            'p03.gap.detected.v1': GapDetectedPayload,
            'p03.embedding.created.v1': EmbeddingCreatedPayload,
            'p03.memory.consolidated.v1': MemoryConsolidatedPayload,
        }[topic]
```

---

## 10. Testing Strategy

> **Status**: COMPLETE

### 10.1 Test Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           P03 TESTING PYRAMID                                            │
│                                                                                          │
│                              ┌─────────────────┐                                         │
│                              │   E2E Tests     │  ← Full cycle, real DB                  │
│                              │  (5-10 tests)   │                                         │
│                              └────────┬────────┘                                         │
│                                       │                                                  │
│                         ┌─────────────┴─────────────┐                                    │
│                         │    Integration Tests      │  ← Phase combinations             │
│                         │      (50-100 tests)       │    Multi-module flows             │
│                         └─────────────┬─────────────┘                                    │
│                                       │                                                  │
│              ┌────────────────────────┴────────────────────────┐                         │
│              │              Contract Tests                     │  ← Schema validation   │
│              │               (20-30 tests)                     │    Event payloads      │
│              └────────────────────────┬────────────────────────┘                         │
│                                       │                                                  │
│    ┌──────────────────────────────────┴──────────────────────────────────┐               │
│    │                          Unit Tests                                  │  ← Algos     │
│    │                        (200-500 tests)                               │    Decisions │
│    └─────────────────────────────────────────────────────────────────────┘               │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 Unit Tests

#### 10.2.1 Algorithm Tests

```python
# tests/k0/pipelines/p03/test_algorithms.py

import pytest
from k0.pipelines.p03.modules import (
    EpisodicClusterer,
    DuplicateDetector,
    RetentionEnforcer,
    ReplayCoordinator
)


class TestImportanceScoring:
    """Test M23 ReplayCoordinator importance scoring."""

    @pytest.mark.parametrize("recency,salience,novelty,expected_range", [
        (1.0, 1.0, 1.0, (0.9, 1.0)),      # All high → high importance
        (0.0, 0.5, 0.5, (0.2, 0.4)),      # Old, medium salience
        (1.0, 0.0, 1.0, (0.4, 0.6)),      # Recent, low salience, novel
        (0.5, 0.5, 0.5, (0.4, 0.6)),      # All medium → medium importance
    ])
    def test_importance_score_formula(
        self,
        recency: float,
        salience: float,
        novelty: float,
        expected_range: tuple[float, float]
    ):
        """Importance = w1*recency + w2*salience + w3*novelty."""
        coordinator = ReplayCoordinator(
            recency_weight=0.3,
            salience_weight=0.5,
            novelty_weight=0.2
        )

        score = coordinator.calculate_importance(
            recency=recency,
            salience=salience,
            novelty=novelty
        )

        assert expected_range[0] <= score <= expected_range[1]

    def test_importance_weights_sum_to_one(self):
        """Weights must be normalized."""
        coordinator = ReplayCoordinator()
        total = (
            coordinator.recency_weight +
            coordinator.salience_weight +
            coordinator.novelty_weight
        )
        assert abs(total - 1.0) < 0.001


class TestDecayComputation:
    """Test M20 RetentionEnforcer decay calculations."""

    @pytest.mark.parametrize("layer,days_old,expected_decay_range", [
        ("st_epi", 1, (0.95, 1.0)),       # Fresh episodic
        ("st_epi", 30, (0.3, 0.5)),       # Month-old episodic
        ("st_sem", 30, (0.85, 0.95)),     # Month-old semantic (slower decay)
        ("st_kg_dom", 365, (0.7, 0.9)),   # Year-old KG (very slow decay)
    ])
    def test_decay_by_layer_and_age(
        self,
        layer: str,
        days_old: int,
        expected_decay_range: tuple[float, float]
    ):
        """Each layer has different decay rates."""
        enforcer = RetentionEnforcer()

        decay = enforcer.compute_decay_factor(
            layer=layer,
            age_days=days_old,
            access_count=0
        )

        assert expected_decay_range[0] <= decay <= expected_decay_range[1]

    def test_access_slows_decay(self):
        """Frequent access should slow decay."""
        enforcer = RetentionEnforcer()

        decay_no_access = enforcer.compute_decay_factor(
            layer="st_epi",
            age_days=30,
            access_count=0
        )

        decay_with_access = enforcer.compute_decay_factor(
            layer="st_epi",
            age_days=30,
            access_count=10
        )

        assert decay_with_access > decay_no_access


class TestDBSCANClustering:
    """Test M18 EpisodicClusterer DBSCAN."""

    def test_similar_events_cluster_together(self):
        """Events with similar embeddings form clusters."""
        clusterer = EpisodicClusterer(eps=0.3, min_samples=2)

        # 4 events: 2 similar pairs
        embeddings = [
            [0.1, 0.1, 0.1],  # Cluster A
            [0.11, 0.12, 0.09],  # Cluster A
            [0.9, 0.9, 0.9],  # Cluster B
            [0.88, 0.91, 0.89],  # Cluster B
        ]

        clusters = clusterer.cluster(embeddings)

        assert len(set(clusters)) == 2  # Two clusters
        assert clusters[0] == clusters[1]  # First pair together
        assert clusters[2] == clusters[3]  # Second pair together
        assert clusters[0] != clusters[2]  # Pairs separate

    def test_outliers_marked_as_noise(self):
        """Isolated events are noise (cluster = -1)."""
        clusterer = EpisodicClusterer(eps=0.1, min_samples=3)

        embeddings = [
            [0.1, 0.1],
            [0.5, 0.5],  # Outlier
            [0.11, 0.09],
            [0.12, 0.11],
        ]

        clusters = clusterer.cluster(embeddings)

        assert clusters[1] == -1  # Outlier marked as noise


class TestSimHashDeduplication:
    """Test M19 DuplicateDetector SimHash."""

    def test_identical_content_has_zero_hamming(self):
        """Identical content produces identical hash."""
        detector = DuplicateDetector()

        hash1 = detector.compute_simhash("The quick brown fox")
        hash2 = detector.compute_simhash("The quick brown fox")

        distance = detector.hamming_distance(hash1, hash2)
        assert distance == 0

    def test_similar_content_has_low_hamming(self):
        """Similar content has low Hamming distance."""
        detector = DuplicateDetector(threshold=5)

        hash1 = detector.compute_simhash("The quick brown fox jumps")
        hash2 = detector.compute_simhash("The quick brown fox leaps")

        distance = detector.hamming_distance(hash1, hash2)
        assert distance < 10  # Similar

    def test_different_content_has_high_hamming(self):
        """Different content has high Hamming distance."""
        detector = DuplicateDetector()

        hash1 = detector.compute_simhash("The quick brown fox")
        hash2 = detector.compute_simhash("Machine learning algorithms")

        distance = detector.hamming_distance(hash1, hash2)
        assert distance > 20  # Different
```

#### 10.2.2 Decision Logic Tests

```python
# tests/k0/pipelines/p03/test_decisions.py

import pytest
from k0.pipelines.p03.reconciliation import ReconciliationEngine
from k0.pipelines.p03.models import (
    ReconciliationDecision,
    TruthRecord,
    HippEvent
)


class TestReconciliationDecisions:
    """Test reconciliation decision logic."""

    @pytest.fixture
    def engine(self):
        return ReconciliationEngine(
            reinforce_threshold=0.85,
            extend_threshold=0.6,
            evolve_threshold=0.4,
            contradict_threshold=0.3
        )

    def test_high_similarity_reinforces(self, engine):
        """Similarity >= 0.85 → REINFORCE."""
        decision = engine.decide(
            event=HippEvent(content="User prefers coffee"),
            truth=TruthRecord(
                content="User likes coffee",
                confidence=0.7
            ),
            similarity=0.92
        )

        assert decision.type == ReconciliationDecision.REINFORCE
        assert decision.new_confidence > 0.7

    def test_medium_similarity_extends(self, engine):
        """0.6 <= similarity < 0.85 → EXTEND."""
        decision = engine.decide(
            event=HippEvent(content="User prefers dark roast coffee"),
            truth=TruthRecord(
                content="User likes coffee",
                confidence=0.7
            ),
            similarity=0.72
        )

        assert decision.type == ReconciliationDecision.EXTEND

    def test_low_similarity_evolves(self, engine):
        """0.4 <= similarity < 0.6 → EVOLVE."""
        decision = engine.decide(
            event=HippEvent(content="User now prefers tea"),
            truth=TruthRecord(
                content="User likes coffee",
                confidence=0.7
            ),
            similarity=0.45
        )

        assert decision.type == ReconciliationDecision.EVOLVE

    def test_very_low_similarity_contradicts(self, engine):
        """similarity < 0.4 + high confidence → CONTRADICT."""
        decision = engine.decide(
            event=HippEvent(content="User hates coffee"),
            truth=TruthRecord(
                content="User loves coffee",
                confidence=0.9
            ),
            similarity=0.15
        )

        assert decision.type == ReconciliationDecision.CONTRADICT
        assert decision.gap_emitted is True

    def test_no_match_creates_new(self, engine):
        """No matching truth → CREATE."""
        decision = engine.decide(
            event=HippEvent(content="User has a dog named Max"),
            truth=None,
            similarity=0.0
        )

        assert decision.type == ReconciliationDecision.CREATE

    def test_low_decay_prunes(self, engine):
        """decay_factor < 0.1 → PRUNE."""
        decision = engine.decide_retention(
            truth=TruthRecord(
                content="Old preference",
                decay_factor=0.05,
                observation_count=1
            )
        )

        assert decision.type == ReconciliationDecision.PRUNE
```

### 10.3 Integration Tests

#### 10.3.1 End-to-End Consolidation Cycle

```python
# tests/k0/pipelines/p03/integration/test_full_cycle.py

import pytest
from tests.fixtures.p03 import P03TestFixtures
from k0.pipelines.p03 import ConsolidationPipeline
from k0.storage import StorageManager


@pytest.mark.integration
class TestFullConsolidationCycle:
    """End-to-end consolidation cycle tests."""

    @pytest.fixture
    async def pipeline(self, db_session):
        """Create pipeline with test database."""
        storage = StorageManager(session=db_session)
        return ConsolidationPipeline(storage=storage)

    async def test_basic_consolidation_cycle(
        self,
        pipeline,
        p03_fixtures: P03TestFixtures
    ):
        """Test complete R0-R8 cycle with known input."""
        # Setup: 100 events with known patterns
        events = p03_fixtures.create_events_with_patterns(
            n_events=100,
            n_patterns=5,  # 5 distinct patterns
            events_per_pattern=20
        )
        await pipeline.storage.insert_hipp_events(events)

        # Execute
        result = await pipeline.run_cycle(
            tenant_id="test_tenant",
            space_id="test_space"
        )

        # Assert cycle completed
        assert result.status == "SUCCESS"
        assert result.events_processed == 100

        # Assert patterns extracted to st_sem
        semantic_records = await pipeline.storage.query_semantic(
            tenant_id="test_tenant"
        )
        assert len(semantic_records) == 5  # 5 patterns

        # Assert observation counts
        for record in semantic_records:
            assert record.observation_count >= 15  # ~20 per pattern, some noise

    async def test_entity_extraction_to_kg(
        self,
        pipeline,
        p03_fixtures: P03TestFixtures
    ):
        """Test entity extraction creates KG nodes and edges."""
        # Setup: Events mentioning known entities
        events = p03_fixtures.create_events_with_entities(
            entities=["Alice", "Bob", "Project Alpha"],
            relationships=[
                ("Alice", "works_with", "Bob"),
                ("Alice", "leads", "Project Alpha"),
                ("Bob", "contributes_to", "Project Alpha")
            ]
        )
        await pipeline.storage.insert_hipp_events(events)

        # Execute
        await pipeline.run_cycle(
            tenant_id="test_tenant",
            space_id="test_space"
        )

        # Assert entities created
        entities = await pipeline.storage.query_kg_entities(
            tenant_id="test_tenant"
        )
        entity_names = {e.name for e in entities}
        assert "Alice" in entity_names
        assert "Bob" in entity_names
        assert "Project Alpha" in entity_names

        # Assert relationships created
        edges = await pipeline.storage.query_kg_edges(
            tenant_id="test_tenant"
        )
        assert len(edges) == 3


@pytest.mark.integration
class TestBidirectionalReconciliation:
    """Test bidirectional truth reconciliation."""

    async def test_reinforcing_signal_boosts_confidence(
        self,
        pipeline,
        p03_fixtures: P03TestFixtures
    ):
        """New signal matching existing truth boosts confidence."""
        # Setup: Existing truth
        existing = p03_fixtures.create_semantic_truth(
            content="User prefers morning meetings",
            confidence=0.6,
            observation_count=3
        )
        await pipeline.storage.insert_semantic(existing)

        # Setup: Reinforcing events
        events = p03_fixtures.create_events_matching_truth(
            truth=existing,
            n_events=5,
            similarity=0.9
        )
        await pipeline.storage.insert_hipp_events(events)

        # Execute
        await pipeline.run_cycle(
            tenant_id=existing.tenant_id,
            space_id=existing.space_id
        )

        # Assert confidence increased
        updated = await pipeline.storage.get_semantic_by_id(existing.id)
        assert updated.confidence > 0.6
        assert updated.observation_count == 8  # 3 + 5

    async def test_contradiction_emits_gap(
        self,
        pipeline,
        p03_fixtures: P03TestFixtures,
        mock_bus
    ):
        """Contradicting signal emits gap to P06."""
        # Setup: Existing high-confidence truth
        existing = p03_fixtures.create_semantic_truth(
            content="User strongly prefers email over calls",
            confidence=0.9,
            observation_count=10
        )
        await pipeline.storage.insert_semantic(existing)

        # Setup: Contradicting events
        events = p03_fixtures.create_events_contradicting_truth(
            truth=existing,
            n_events=3,
            content="User now prefers phone calls"
        )
        await pipeline.storage.insert_hipp_events(events)

        # Execute
        await pipeline.run_cycle(
            tenant_id=existing.tenant_id,
            space_id=existing.space_id
        )

        # Assert gap emitted
        gaps = mock_bus.get_published('p03.gap.detected.v1')
        assert len(gaps) == 1
        assert gaps[0]['gap_type'] == 'CONTRADICTION'
        assert existing.id in gaps[0]['context']['conflicting_truths']
```

#### 10.3.2 Phase Combination Tests

```python
# tests/k0/pipelines/p03/integration/test_phases.py

import pytest


@pytest.mark.integration
class TestPhaseTransitions:
    """Test transitions between consolidation phases."""

    async def test_r1_to_r2_event_selection(self, pipeline):
        """R1 selects high-importance events for R2."""
        # Setup: Mix of high and low importance events
        events = [
            {"salience_score": 0.9, "recency": 0.9},  # High
            {"salience_score": 0.1, "recency": 0.1},  # Low
            {"salience_score": 0.8, "recency": 0.7},  # High
        ]

        # Execute R1
        selected = await pipeline.phase_r1_replay(events)

        # Assert only high-importance selected
        assert len(selected) == 2
        assert all(e['salience_score'] > 0.5 for e in selected)

    async def test_r3_deduplication_before_r4(self, pipeline):
        """R3 removes duplicates before R4 KG consolidation."""
        # Setup: Events with duplicates
        events = [
            {"content_hash": "abc123", "event_id": "e1"},
            {"content_hash": "abc123", "event_id": "e2"},  # Duplicate
            {"content_hash": "def456", "event_id": "e3"},
        ]

        # Execute R3
        deduplicated = await pipeline.phase_r3_forgetting(events)

        # Assert duplicates removed
        assert len(deduplicated) == 2
        hashes = {e['content_hash'] for e in deduplicated}
        assert hashes == {"abc123", "def456"}
```

### 10.4 Contract Tests

```python
# tests/k0/pipelines/p03/contract/test_schemas.py

import pytest
from pydantic import ValidationError
from k0.pipelines.p03.contracts import (
    GapDetectedPayload,
    EmbeddingCreatedPayload,
    MemoryConsolidatedPayload
)


class TestGapDetectedContract:
    """Test p03.gap.detected.v1 contract."""

    def test_valid_gap_payload(self):
        """Valid payload passes validation."""
        payload = {
            "gap_id": "01HXYZ123ABC",
            "tenant_id": "tenant_123",
            "space_id": "space_456",
            "gap_type": "CONTRADICTION",
            "importance_score": 0.85,
            "context": {
                "source_event_ids": ["evt_1", "evt_2"],
                "conflicting_truths": [
                    {"truth_id": "truth_1", "layer": "st_sem", "confidence": 0.9}
                ]
            },
            "detected_at": 1699999999000
        }

        parsed = GapDetectedPayload(**payload)
        assert parsed.gap_type == "CONTRADICTION"

    def test_invalid_gap_type_rejected(self):
        """Invalid gap_type fails validation."""
        payload = {
            "gap_id": "01HXYZ123ABC",
            "tenant_id": "tenant_123",
            "space_id": "space_456",
            "gap_type": "INVALID_TYPE",  # Invalid
            "importance_score": 0.85,
            "context": {},
            "detected_at": 1699999999000
        }

        with pytest.raises(ValidationError):
            GapDetectedPayload(**payload)

    def test_missing_required_field_rejected(self):
        """Missing required field fails validation."""
        payload = {
            "gap_id": "01HXYZ123ABC",
            # Missing tenant_id
            "space_id": "space_456",
            "gap_type": "CONTRADICTION",
            "importance_score": 0.85,
            "context": {},
            "detected_at": 1699999999000
        }

        with pytest.raises(ValidationError):
            GapDetectedPayload(**payload)


class TestDatabaseSchemaContract:
    """Test database schema contracts."""

    async def test_st_hipp_events_schema(self, db_session):
        """st_hipp_events has required columns."""
        required_columns = [
            'event_id', 'tenant_id', 'space_id', 'actor_id',
            'content_hash', 'embedding_id', 'salience_score',
            'policy_band', 'entities_json', 'triplets_json',
            'consolidation_status', 'created_at'
        ]

        actual_columns = await db_session.get_table_columns('st_hipp_events')

        for col in required_columns:
            assert col in actual_columns

    async def test_st_sem_schema(self, db_session):
        """st_sem has required columns for bidirectional reconciliation."""
        required_columns = [
            'id', 'tenant_id', 'space_id', 'version',
            'content', 'embedding_id', 'confidence',
            'observation_count', 'decay_factor',
            'provenance_chain_json', 'archival_status',
            'valid_from', 'valid_until', 'created_at'
        ]

        actual_columns = await db_session.get_table_columns('st_sem')

        for col in required_columns:
            assert col in actual_columns
```

### 10.5 Performance Tests

```python
# tests/k0/pipelines/p03/performance/test_throughput.py

import pytest
import time
import asyncio
import tracemalloc


@pytest.mark.performance
class TestThroughputBenchmarks:
    """Performance benchmarks for P03."""

    async def test_consolidation_throughput(
        self,
        pipeline,
        p03_fixtures
    ):
        """Target: 1000 events/minute."""
        # Setup: 1000 events
        events = p03_fixtures.create_random_events(n=1000)
        await pipeline.storage.insert_hipp_events(events)

        # Execute with timing
        start = time.perf_counter()

        await pipeline.run_cycle(
            tenant_id="perf_tenant",
            space_id="perf_space"
        )

        elapsed = time.perf_counter() - start

        # Assert throughput
        events_per_second = 1000 / elapsed
        events_per_minute = events_per_second * 60

        assert events_per_minute >= 1000, (
            f"Throughput {events_per_minute:.0f} events/min "
            f"below target 1000 events/min"
        )

    async def test_large_batch_cycle_time(
        self,
        pipeline,
        p03_fixtures
    ):
        """Target: <5 minutes for 10K events."""
        # Setup: 10000 events
        events = p03_fixtures.create_random_events(n=10000)
        await pipeline.storage.insert_hipp_events(events)

        # Execute with timing
        start = time.perf_counter()

        await pipeline.run_cycle(
            tenant_id="perf_tenant",
            space_id="perf_space"
        )

        elapsed = time.perf_counter() - start

        # Assert cycle time
        assert elapsed < 300, (
            f"Cycle time {elapsed:.1f}s exceeds target 300s (5 min)"
        )


@pytest.mark.performance
class TestMemoryFootprint:
    """Memory usage benchmarks."""

    async def test_peak_memory_under_limit(
        self,
        pipeline,
        p03_fixtures
    ):
        """Target: <500MB peak memory."""
        # Setup: 10000 events
        events = p03_fixtures.create_random_events(n=10000)
        await pipeline.storage.insert_hipp_events(events)

        # Track memory
        tracemalloc.start()

        await pipeline.run_cycle(
            tenant_id="perf_tenant",
            space_id="perf_space"
        )

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)

        # Assert memory limit
        assert peak_mb < 500, (
            f"Peak memory {peak_mb:.1f}MB exceeds target 500MB"
        )

    async def test_streaming_prevents_oom(
        self,
        pipeline,
        p03_fixtures
    ):
        """Streaming batches prevent OOM on large datasets."""
        # Setup: Very large batch (100K events)
        events = p03_fixtures.create_random_events(n=100000)
        await pipeline.storage.insert_hipp_events(events)

        # Should not raise MemoryError
        try:
            await pipeline.run_cycle(
                tenant_id="perf_tenant",
                space_id="perf_space",
                batch_size=1000  # Stream in batches
            )
        except MemoryError:
            pytest.fail("MemoryError raised - streaming not working")
```

### 10.6 Golden Dataset Tests

```python
# tests/k0/pipelines/p03/golden/test_golden_dataset.py

import pytest
import yaml
from pathlib import Path


@pytest.mark.golden
class TestGoldenDataset:
    """Test against golden dataset with known expected outputs."""

    @pytest.fixture
    def golden_data(self):
        """Load golden dataset."""
        path = Path("golden_dataset/p03/consolidation_golden.yaml")
        with open(path) as f:
            return yaml.safe_load(f)

    async def test_golden_pattern_extraction(
        self,
        pipeline,
        golden_data
    ):
        """Verify pattern extraction matches golden outputs."""
        for case in golden_data['pattern_extraction_cases']:
            # Setup
            events = case['input_events']
            expected_patterns = case['expected_patterns']

            await pipeline.storage.clear_all()
            await pipeline.storage.insert_hipp_events(events)

            # Execute
            await pipeline.run_cycle(
                tenant_id=case['tenant_id'],
                space_id=case['space_id']
            )

            # Assert
            actual = await pipeline.storage.query_semantic(
                tenant_id=case['tenant_id']
            )
            actual_contents = {r.content for r in actual}

            for pattern in expected_patterns:
                assert pattern['content'] in actual_contents, (
                    f"Expected pattern '{pattern['content']}' not found"
                )

    async def test_golden_gap_detection(
        self,
        pipeline,
        golden_data,
        mock_bus
    ):
        """Verify gap detection matches golden outputs."""
        for case in golden_data['gap_detection_cases']:
            # Setup
            existing_truths = case['existing_truths']
            conflicting_events = case['conflicting_events']
            expected_gaps = case['expected_gaps']

            await pipeline.storage.clear_all()
            await pipeline.storage.insert_semantic(existing_truths)
            await pipeline.storage.insert_hipp_events(conflicting_events)
            mock_bus.clear()

            # Execute
            await pipeline.run_cycle(
                tenant_id=case['tenant_id'],
                space_id=case['space_id']
            )

            # Assert
            gaps = mock_bus.get_published('p03.gap.detected.v1')

            assert len(gaps) == len(expected_gaps), (
                f"Expected {len(expected_gaps)} gaps, got {len(gaps)}"
            )

            for expected in expected_gaps:
                matching = [
                    g for g in gaps
                    if g['gap_type'] == expected['gap_type']
                ]
                assert len(matching) > 0, (
                    f"Expected gap type {expected['gap_type']} not found"
                )
```

### 10.7 Test Fixtures

```python
# tests/fixtures/p03.py

from dataclasses import dataclass
from typing import List, Optional
import random
import hashlib
from ulid import ULID


@dataclass
class P03TestFixtures:
    """Factory for P03 test data."""

    def create_random_events(
        self,
        n: int,
        tenant_id: str = "test_tenant",
        space_id: str = "test_space"
    ) -> List[dict]:
        """Create n random st_hipp_events."""
        return [
            {
                "event_id": str(ULID()),
                "tenant_id": tenant_id,
                "space_id": space_id,
                "actor_id": f"actor_{random.randint(1, 10)}",
                "content": f"Random content {i}: {random.random()}",
                "content_hash": hashlib.md5(f"content_{i}".encode()).hexdigest(),
                "embedding_id": str(ULID()),
                "embedding_vector": [random.random() for _ in range(768)],
                "salience_score": random.uniform(0.1, 1.0),
                "policy_band": "GREEN",
                "entities_json": "[]",
                "triplets_json": "[]",
                "created_at": 1699999999000 + i
            }
            for i in range(n)
        ]

    def create_events_with_patterns(
        self,
        n_events: int,
        n_patterns: int,
        events_per_pattern: int
    ) -> List[dict]:
        """Create events following distinct patterns."""
        events = []
        patterns = [f"Pattern topic {i}: content about subject {i}" for i in range(n_patterns)]

        for pattern_idx, pattern in enumerate(patterns):
            for j in range(events_per_pattern):
                variation = f"{pattern} (variation {j})"
                events.append({
                    "event_id": str(ULID()),
                    "tenant_id": "test_tenant",
                    "space_id": "test_space",
                    "content": variation,
                    "pattern_id": pattern_idx,  # For verification
                    "salience_score": 0.8,
                    # ... other fields
                })

        return events

    def create_semantic_truth(
        self,
        content: str,
        confidence: float = 0.7,
        observation_count: int = 5,
        tenant_id: str = "test_tenant",
        space_id: str = "test_space"
    ) -> dict:
        """Create a semantic truth record."""
        return {
            "id": str(ULID()),
            "tenant_id": tenant_id,
            "space_id": space_id,
            "version": 1,
            "content": content,
            "confidence": confidence,
            "observation_count": observation_count,
            "decay_factor": 1.0,
            "archival_status": "ACTIVE",
            "created_at": 1699999999000
        }

    def create_events_matching_truth(
        self,
        truth: dict,
        n_events: int,
        similarity: float
    ) -> List[dict]:
        """Create events that match/reinforce existing truth."""
        # Generate content with controlled similarity
        base_content = truth['content']
        events = []

        for i in range(n_events):
            if similarity > 0.9:
                content = base_content  # Near-identical
            elif similarity > 0.7:
                content = f"{base_content} (additional detail {i})"
            else:
                content = f"Related: {base_content[:20]}... (different context {i})"

            events.append({
                "event_id": str(ULID()),
                "tenant_id": truth['tenant_id'],
                "space_id": truth['space_id'],
                "content": content,
                "salience_score": 0.8,
                # ... other fields
            })

        return events
```

---

## 11. Migration & Evolution

> **Status**: COMPLETE

### 11.1 Migration Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           P03 EVOLUTION ROADMAP                                          │
│                                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │  CURRENT (v2.0)              │  PHASE 2               │  PHASE 3               │   │
│   │                               │  (v2.5)                │  (v3.0)                │   │
│   │  • 8-phase pipeline           │  • Enhanced Dream      │  • Multi-tenant        │   │
│   │  • Bidirectional truth        │  • CPN/TPN-MCTS        │  • Distributed         │   │
│   │  • Gap detection              │  • Creative insights   │  • Partitioned         │   │
│   │  • Basic anchors              │  • Full UQ pipeline    │  • Auto-scaling        │   │
│   │                               │                        │                         │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
│   Timeline:                                                                              │
│   ─────────────────────────────────────────────────────────────────────────────────     │
│   Q1 2025                   Q2 2025                    Q3 2025                           │
│   v2.0 Production           v2.5 Dream Phase           v3.0 Distributed                  │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 11.2 v1 → v2 Migration

#### 11.2.1 Schema Migrations

```sql
-- Migration: P03_001_add_reconciliation_columns.sql

-- Add reconciliation tracking to st_hipp_events
ALTER TABLE st_hipp_events
ADD COLUMN reconciliation_decision_type TEXT CHECK(reconciliation_decision_type IN (
  'REINFORCE', 'EXTEND', 'CREATE', 'EVOLVE', 'PRUNE', 'CONTRADICT', 'SKIP'
));

ALTER TABLE st_hipp_events
ADD COLUMN truth_match_id TEXT;

ALTER TABLE st_hipp_events
ADD COLUMN truth_match_layer TEXT;

ALTER TABLE st_hipp_events
ADD COLUMN similarity_score REAL;

CREATE INDEX idx_hipp_reconciliation
ON st_hipp_events(reconciliation_decision_type, consolidation_status);


-- Migration: P03_002_create_learning_queue.sql

CREATE TABLE st_learning_queue (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  gap_type TEXT NOT NULL,
  importance_score REAL NOT NULL,
  context_json TEXT NOT NULL,
  source_event_ids_json TEXT NOT NULL,
  conflicting_truth_ids_json TEXT,
  question_template TEXT,
  status TEXT DEFAULT 'PENDING',
  ttl_expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  resolved_at INTEGER,
  resolution_type TEXT,
  answer_event_id TEXT
);

CREATE INDEX idx_learning_queue_status
ON st_learning_queue(tenant_id, status, importance_score DESC)
WHERE status = 'PENDING';


-- Migration: P03_003_create_anchors.sql

CREATE TABLE st_anchors (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  anchor_type TEXT NOT NULL,
  anchor_key TEXT NOT NULL,
  alpha REAL NOT NULL DEFAULT 1.0,
  beta REAL NOT NULL DEFAULT 1.0,
  mean_estimate REAL GENERATED ALWAYS AS (alpha / (alpha + beta)) STORED,
  last_updated_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX idx_anchors_unique_key
ON st_anchors(tenant_id, space_id, actor_id, anchor_type, anchor_key);


-- Migration: P03_004_add_observation_count.sql

-- Add observation_count to semantic layer
ALTER TABLE st_sem
ADD COLUMN observation_count INTEGER DEFAULT 1;

-- Add observation_count to KG entities
ALTER TABLE st_kg_entities
ADD COLUMN observation_count INTEGER DEFAULT 1;

-- Add observation_count to KG edges
ALTER TABLE st_kg_edges
ADD COLUMN observation_count INTEGER DEFAULT 1;
```

#### 11.2.2 Migration Execution Plan

```python
# k0/pipelines/p03/migrations/executor.py

from dataclasses import dataclass
from typing import List
import asyncio


@dataclass
class MigrationStep:
    """Single migration step."""
    id: str
    description: str
    sql_file: str
    rollback_sql: str
    depends_on: List[str]
    estimated_duration_minutes: int


class P03MigrationExecutor:
    """Execute P03 v1→v2 migration with safety checks."""

    MIGRATION_STEPS = [
        MigrationStep(
            id="P03_001",
            description="Add reconciliation columns to st_hipp_events",
            sql_file="P03_001_add_reconciliation_columns.sql",
            rollback_sql="ALTER TABLE st_hipp_events DROP COLUMN ...",
            depends_on=[],
            estimated_duration_minutes=5
        ),
        MigrationStep(
            id="P03_002",
            description="Create st_learning_queue table",
            sql_file="P03_002_create_learning_queue.sql",
            rollback_sql="DROP TABLE st_learning_queue",
            depends_on=["P03_001"],
            estimated_duration_minutes=1
        ),
        MigrationStep(
            id="P03_003",
            description="Create st_anchors table",
            sql_file="P03_003_create_anchors.sql",
            rollback_sql="DROP TABLE st_anchors",
            depends_on=["P03_001"],
            estimated_duration_minutes=1
        ),
        MigrationStep(
            id="P03_004",
            description="Add observation_count columns",
            sql_file="P03_004_add_observation_count.sql",
            rollback_sql="ALTER TABLE ... DROP COLUMN observation_count",
            depends_on=["P03_001"],
            estimated_duration_minutes=10
        ),
        MigrationStep(
            id="P03_005",
            description="Backfill observation_count from patterns",
            sql_file="P03_005_backfill_observation_count.sql",
            rollback_sql="UPDATE ... SET observation_count = 1",
            depends_on=["P03_004"],
            estimated_duration_minutes=60
        ),
    ]

    async def execute_migration(
        self,
        dry_run: bool = True,
        target_step: str = None
    ):
        """Execute migration with safety checks."""

        # 1. Pre-flight checks
        await self._verify_prerequisites()
        await self._create_backup()
        await self._acquire_migration_lock()

        try:
            # 2. Execute steps
            for step in self._ordered_steps(target_step):
                if dry_run:
                    logger.info(f"DRY RUN: Would execute {step.id}")
                    continue

                await self._execute_step(step)
                await self._record_step_complete(step)

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            if not dry_run:
                await self._rollback_to_checkpoint()
            raise

        finally:
            await self._release_migration_lock()

    async def _verify_prerequisites(self):
        """Verify migration can proceed."""
        # Check P03 is not running
        if await self._is_p03_running():
            raise MigrationError("P03 pipeline must be stopped before migration")

        # Check disk space
        if await self._get_free_space_gb() < 10:
            raise MigrationError("Insufficient disk space for migration")

        # Check database version
        current = await self._get_schema_version()
        if current >= "2.0.0":
            raise MigrationError("Already at v2.0 or later")
```

#### 11.2.3 Backfill Strategy

```python
# k0/pipelines/p03/migrations/backfill.py

class ObservationCountBackfill:
    """Backfill observation_count from historical patterns."""

    async def backfill_semantic_layer(self, batch_size: int = 1000):
        """
        Populate observation_count in st_sem by analyzing
        historical st_hipp_events.

        Algorithm:
        1. For each semantic record, find matching events
        2. Count events with similarity > 0.85
        3. Set observation_count = count
        """
        offset = 0
        total_updated = 0

        while True:
            # Batch query semantic records
            records = await self.storage.query(
                """
                SELECT id, embedding_id
                FROM st_sem
                WHERE observation_count = 1
                ORDER BY created_at
                LIMIT ? OFFSET ?
                """,
                (batch_size, offset)
            )

            if not records:
                break

            for record in records:
                # Find similar events
                count = await self._count_matching_events(
                    embedding_id=record['embedding_id'],
                    similarity_threshold=0.85
                )

                # Update observation_count
                await self.storage.execute(
                    """
                    UPDATE st_sem
                    SET observation_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (count, now_ms(), record['id'])
                )

                total_updated += 1

            offset += batch_size
            logger.info(f"Backfilled {total_updated} records")

        return total_updated

    async def _count_matching_events(
        self,
        embedding_id: str,
        similarity_threshold: float
    ) -> int:
        """Count events matching this semantic record."""
        # Use vector similarity search
        result = await self.storage.query(
            """
            SELECT COUNT(*) as cnt
            FROM st_hipp_events e
            JOIN st_vec v ON e.embedding_id = v.id
            WHERE cosine_similarity(v.vector,
                  (SELECT vector FROM st_vec WHERE id = ?)) > ?
            AND e.consolidation_status = 'CONSOLIDATED'
            """,
            (embedding_id, similarity_threshold)
        )
        return result[0]['cnt']
```

### 11.3 Future Phases

#### 11.3.1 Phase 2: Enhanced Dream Exploration (v2.5)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 2: DREAM EXPLORATION ENHANCEMENT                   │
│                                                                             │
│   Current R5 (Basic):                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │ • Remote association via embedding similarity                        │  │
│   │ • Simple counterfactual generation                                   │  │
│   │ • Basic prediction from patterns                                     │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Enhanced R5 (v2.5):                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                                                                      │  │
│   │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │  │
│   │   │     CPN      │    │   TPN-MCTS   │    │    SPC-UQ    │          │  │
│   │   │  Contrastive │    │   Temporal   │    │  Structured  │          │  │
│   │   │  Predictive  │    │   Planning   │    │  Predictive  │          │  │
│   │   │   Network    │    │   Network    │    │   Coding     │          │  │
│   │   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘          │  │
│   │          │                   │                   │                   │  │
│   │          └───────────────────┼───────────────────┘                   │  │
│   │                              ▼                                       │  │
│   │                    ┌─────────────────┐                               │  │
│   │                    │ Dream Synthesis │                               │  │
│   │                    │    & Ranking    │                               │  │
│   │                    └─────────────────┘                               │  │
│   │                                                                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   New Capabilities:                                                         │
│   • CPN: "What if X had happened instead of Y?"                            │
│   • TPN-MCTS: "What sequence of events might follow?"                      │
│   • SPC-UQ: "How confident are we in this prediction?"                     │
│                                                                             │
│   Timeline: Q2 2025                                                         │
│   Dependencies: M22 refactor, GPU inference support                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Phase 2 ADR Reference**: ADR-K0-042 (Enhanced Dream Exploration)

**Implementation Tasks**:

1. Refactor M22 (DreamExplorer) to support pluggable exploration engines
2. Implement CPN module for contrastive prediction
3. Implement TPN-MCTS for temporal planning
4. Implement SPC-UQ for uncertainty quantification
5. Add GPU inference support for dream phase
6. Create dream insight ranking algorithm

#### 11.3.2 Phase 3: Multi-Tenant Optimization (v2.8)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 3: MULTI-TENANT OPTIMIZATION                       │
│                                                                             │
│   Current Architecture:                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                                                                      │  │
│   │   [Tenant A] ─────┐                                                  │  │
│   │   [Tenant B] ─────┼───→ [ Single P03 Worker ] ───→ [ Single DB ]    │  │
│   │   [Tenant C] ─────┘                                                  │  │
│   │                                                                      │  │
│   │   Problems: Head-of-line blocking, no isolation, no priority        │  │
│   │                                                                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Optimized Architecture (v2.8):                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                                                                      │  │
│   │   [Tenant A] ───→ [ Worker Pool A ] ───→ [ Shard A ]                │  │
│   │     (Premium)       (3 workers)           (dedicated)                │  │
│   │                                                                      │  │
│   │   [Tenant B] ───→ [ Worker Pool B ] ───→ [ Shard B ]                │  │
│   │     (Standard)      (1 worker)            (shared)                   │  │
│   │                                                                      │  │
│   │   [Tenant C] ───→ [ Worker Pool B ] ───→ [ Shard B ]                │  │
│   │     (Standard)      (1 worker)            (shared)                   │  │
│   │                                                                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   New Features:                                                              │
│   • Tenant-tier-based worker allocation                                     │
│   • Priority queuing by tenant SLA                                          │
│   • Tenant-isolated resource limits                                         │
│   • Dedicated shards for premium tenants                                    │
│                                                                             │
│   Timeline: Q3 2025                                                         │
│   Dependencies: Kubernetes horizontal pod autoscaling                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Implementation Tasks**:

1. Implement tenant-aware job scheduler
2. Add priority queue with tenant tier weights
3. Implement tenant resource quotas
4. Add horizontal scaling based on queue depth
5. Implement shard routing for tenant isolation

#### 11.3.3 Phase 4: Distributed Consolidation (v3.0)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 4: DISTRIBUTED CONSOLIDATION                        │
│                                                                             │
│   Goal: Scale to 1M+ events/hour across multiple workers                    │
│                                                                             │
│   Architecture:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                                                                      │  │
│   │   ┌─────────────────────────────────────────────────────────────┐   │  │
│   │   │                    COORDINATION LAYER                        │   │  │
│   │   │                                                              │   │  │
│   │   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │   │  │
│   │   │  │ Partition│  │  Lock    │  │ Progress │  │ Barrier  │    │   │  │
│   │   │  │ Manager  │  │ Service  │  │ Tracker  │  │ Sync     │    │   │  │
│   │   │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │   │  │
│   │   │                                                              │   │  │
│   │   └─────────────────────────────────────────────────────────────┘   │  │
│   │                              │                                       │  │
│   │              ┌───────────────┼───────────────┐                      │  │
│   │              ▼               ▼               ▼                      │  │
│   │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │  │
│   │   │   Worker 1   │  │   Worker 2   │  │   Worker N   │             │  │
│   │   │              │  │              │  │              │             │  │
│   │   │  Partition:  │  │  Partition:  │  │  Partition:  │             │  │
│   │   │  A-F         │  │  G-M         │  │  N-Z         │             │  │
│   │   │              │  │              │  │              │             │  │
│   │   └──────────────┘  └──────────────┘  └──────────────┘             │  │
│   │                                                                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Partitioning Strategy:                                                     │
│   • Partition by: hash(tenant_id, space_id) % N                             │
│   • Each worker owns exclusive partitions                                   │
│   • Cross-partition KG edges require coordination                           │
│                                                                             │
│   Coordination Protocol:                                                     │
│   • Two-phase commit for cross-partition entities                           │
│   • Barrier sync before R7 truth write                                      │
│   • Distributed lock for anchor updates                                     │
│                                                                             │
│   Timeline: Q4 2025                                                         │
│   Dependencies: Redis cluster, Kafka partitioning                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 11.4 Deprecation Schedule

| Feature | Deprecated | Removed | Replacement |
|---------|-----------|---------|-------------|
| v1 consolidation_status values | v2.0 | v2.5 | reconciliation_decision_type |
| Single-worker mode | v2.8 | v3.0 | Multi-worker with partitioning |
| Basic dream exploration | v2.5 | v3.0 | Enhanced CPN/TPN-MCTS |
| Synchronous P08 coordination | v2.5 | v3.0 | Async with circuit breaker |

### 11.5 Backward Compatibility

```python
# k0/pipelines/p03/compat.py

class P03CompatibilityLayer:
    """Backward compatibility for v1 clients."""

    def translate_v1_status_to_v2(self, v1_status: str) -> str:
        """Translate v1 consolidation_status to v2 decision type."""
        mapping = {
            'CONSOLIDATED': 'CREATE',  # Best guess
            'PENDING': None,
            'ERROR': 'SKIP',
        }
        return mapping.get(v1_status)

    def emit_v1_event_format(self, v2_event: dict) -> dict:
        """Emit v1-format event for legacy consumers."""
        return {
            'event_type': 'consolidation.complete',  # v1 format
            'event_id': v2_event['cycle_id'],
            'status': 'success' if v2_event['status'] == 'SUCCESS' else 'failure',
            'timestamp': v2_event['completed_at'],
            # Omit v2-specific fields
        }

    async def should_emit_v1_events(self, tenant_id: str) -> bool:
        """Check if tenant requires v1 event format."""
        tenant = await self.tenant_service.get(tenant_id)
        return tenant.api_version == "1.x"
```

### 11.6 Feature Flags

```yaml
# k0/pipelines/p03/config/feature_flags.yaml

feature_flags:
  # v2.0 features
  bidirectional_reconciliation:
    description: "Enable bidirectional truth matching"
    default: true
    rollout: 100%

  gap_detection:
    description: "Enable active learning gap detection"
    default: true
    rollout: 100%

  bayesian_anchors:
    description: "Enable Bayesian anchor updates"
    default: true
    rollout: 100%

  # v2.5 features (coming soon)
  enhanced_dream_exploration:
    description: "Enable CPN/TPN-MCTS dream exploration"
    default: false
    rollout: 0%
    requires: [bidirectional_reconciliation]

  gpu_inference:
    description: "Use GPU for embedding similarity"
    default: false
    rollout: 0%
    requires: [cuda_available]

  # v3.0 features (future)
  distributed_workers:
    description: "Enable multi-worker partitioned consolidation"
    default: false
    rollout: 0%
    requires: [redis_cluster, kafka_partitioning]
```

---

## 12. Policy Decisions & Feature Flags

> **Status**: CLOSED — All decisions finalized with explicit defaults and feature flags.

### 12.1 Resolved Design Decisions

#### 12.1.1 Q1: CONTRADICT Decision Handling

**Decision**: CONTRADICT decisions proceed with reduced confidence but do NOT block P03 completion.

| Policy | Default | Feature Flag | Description |
|--------|---------|--------------|-------------|
| `contradict_blocking_mode` | `false` | `P03_FF_CONTRADICT_BLOCKING` | If true, P03 halts at R6 until P06 resolves contradiction |
| `contradict_confidence_penalty` | `0.3` | N/A (config) | Confidence reduction for unresolved contradictions |
| `contradict_max_pending` | `50` | `P03_CONTRADICT_MAX_PENDING` | Max unresolved contradictions before forcing P06 escalation |

**Rationale**: Blocking would create pipeline stalls in production. Lower confidence allows downstream systems to filter uncertain truths while P06 resolves asynchronously.

```yaml
# k0/config/p03/policy.yaml
contradict_handling:
  blocking_mode: false
  confidence_penalty: 0.3
  max_pending: 50
  escalation_topic: p06.contradiction.escalate.v1
```

---

#### 12.1.2 Q2: Gap Queue Maximum Depth

**Decision**: Gap detection stops when st_learning_queue exceeds threshold.

| Policy | Default | Feature Flag | Description |
|--------|---------|--------------|-------------|
| `gap_queue_max_depth` | `500` | `P03_GAP_QUEUE_MAX_DEPTH` | Stop gap detection above this depth |
| `gap_queue_high_watermark` | `400` | N/A | Emit warning at this level |
| `gap_priority_floor` | `0.3` | N/A | Only queue gaps with priority >= floor |

**Rationale**: Unbounded gap queues create P06 backlog. Dropping low-priority gaps is acceptable; high-priority gaps (entropy > 0.7) always queue.

```yaml
# k0/config/p03/policy.yaml
gap_detection:
  queue_max_depth: 500
  high_watermark: 400
  priority_floor: 0.3
  high_priority_threshold: 0.7
  always_queue_high_priority: true
```

---

#### 12.1.3 Q3: Anchor Drift with Conflicting Behaviors

**Decision**: Multi-modal anchor tracking with explicit conflict markers.

| Policy | Default | Feature Flag | Description |
|--------|---------|--------------|-------------|
| `anchor_drift_mode` | `multimodal` | `P03_FF_ANCHOR_DRIFT_MODE` | `single`, `multimodal`, `contextualized` |
| `anchor_conflict_threshold` | `0.4` | N/A | Divergence threshold to split anchor |
| `anchor_max_modes` | `3` | N/A | Maximum anchor modes per entity |

**Rationale**: Users have context-dependent behaviors (work vs home). Multimodal anchors capture this without averaging conflicting data.

```yaml
# k0/config/p03/policy.yaml
anchor_management:
  drift_mode: multimodal
  conflict_threshold: 0.4
  max_modes: 3
  recalibration_interval_days: 30
  emit_drift_event: true
```

---

#### 12.1.4 Q4: R5 Dream Phase Execution Conditions

**Decision**: R5 runs conditionally based on backlog and time constraints.

| Policy | Default | Feature Flag | Description |
|--------|---------|--------------|-------------|
| `r5_execution_mode` | `conditional` | `P03_FF_R5_MODE` | `always`, `conditional`, `disabled` |
| `r5_backlog_threshold` | `500` | N/A | Skip R5 if pending events > threshold |
| `r5_min_idle_seconds` | `60` | N/A | Minimum idle time before R5 |
| `r5_max_duration_seconds` | `120` | N/A | R5 timeout (hard limit) |

**Rationale**: Dream exploration is valuable but not critical. Skip during high-load periods to prioritize core consolidation.

```yaml
# k0/config/p03/policy.yaml
dream_phase:
  execution_mode: conditional
  backlog_threshold: 500
  min_idle_seconds: 60
  max_duration_seconds: 120
  insight_min_novelty: 0.5
```

---

### 12.2 Resolved Implementation TODOs

#### 12.2.1 Similarity Threshold Configuration

**Status**: ✅ COMPLETE — See [Appendix F: Threshold Configuration Table](#appendix-f-threshold-configuration-table)

All similarity thresholds are now defined in a single configuration table with:

- Canonical threshold names
- Default values
- Feature flag overrides
- Test coverage requirements

---

#### 12.2.2 P08 Coordination Circuit Breaker

**Status**: ✅ COMPLETE

| Parameter | Default | Config Key |
|-----------|---------|------------|
| Failure threshold | 5 | `p03.circuit_breaker.failure_threshold` |
| Success threshold | 3 | `p03.circuit_breaker.success_threshold` |
| Timeout seconds | 30 | `p03.circuit_breaker.timeout_seconds` |
| Half-open attempts | 1 | `p03.circuit_breaker.half_open_attempts` |

```python
# k0/pipelines/p03/circuit_breaker.py
P08_CIRCUIT_BREAKER = CircuitBreakerConfig(
    name="p03_p08_coordination",
    failure_threshold=5,
    success_threshold=3,
    timeout_seconds=30,
    half_open_attempts=1,
    fallback=P08FallbackStrategy.QUEUE_LOCAL
)
```

---

#### 12.2.3 Idempotency Key Design

**Status**: ✅ COMPLETE — See [Appendix G: R0-R8 State Machine Specification](#appendix-g-r0-r8-state-machine-specification)

Each phase now has explicit idempotency keys:

| Phase | Idempotency Key Format |
|-------|----------------------|
| R0 | `p03:cycle:{cycle_ulid}` |
| R1-R5 | `p03:{phase}:{cycle_ulid}:{batch_hash}` |
| R6 | `p03:staging:{cycle_ulid}:{event_id}` |
| R7 | `p03:write:{cycle_ulid}:{table}:{record_id}` |
| R8 | `p03:emit:{cycle_ulid}:{topic}:{offset}` |

---

#### 12.2.4 Golden Dataset for Integration Testing

**Status**: ✅ COMPLETE

Location: `golden_dataset/p03/`

| Dataset | Records | Purpose |
|---------|---------|---------|
| `hipp_events_baseline.yaml` | 1000 | Standard consolidation input |
| `hipp_events_duplicates.yaml` | 200 | Near-duplicate detection |
| `hipp_events_contradictions.yaml` | 50 | CONTRADICT decision testing |
| `expected_episodes.yaml` | 85 | R2 clustering verification |
| `expected_patterns.yaml` | 120 | R3 pattern extraction verification |

---

### 12.3 Resolved Active Learning Integration TODOs

#### 12.3.1 Gap Priority Formula

**Status**: ✅ COMPLETE

```python
# Gap priority formula with tunable weights
def compute_gap_priority(
    entropy: float,           # Shannon entropy [0, 1]
    recency_days: float,      # Days since gap created
    impact_factor: float,     # Affected record count / 100
    weights: GapPriorityWeights = DEFAULT_WEIGHTS
) -> float:
    """
    Priority = w_entropy * entropy
             + w_recency * (1 / (1 + recency_days))
             + w_impact * min(impact_factor, 1.0)
    """
    priority = (
        weights.entropy * entropy +
        weights.recency * (1.0 / (1.0 + recency_days)) +
        weights.impact * min(impact_factor, 1.0)
    )
    return min(1.0, max(0.0, priority))

DEFAULT_WEIGHTS = GapPriorityWeights(
    entropy=0.5,
    recency=0.3,
    impact=0.2
)
```

**Feature Flags**:

- `P03_GAP_WEIGHT_ENTROPY`: Override entropy weight (default: 0.5)
- `P03_GAP_WEIGHT_RECENCY`: Override recency weight (default: 0.3)
- `P03_GAP_WEIGHT_IMPACT`: Override impact weight (default: 0.2)

---

#### 12.3.2 Bayesian Anchor Update in P02/P03 Handoff

**Status**: ✅ COMPLETE

```yaml
# Anchor update protocol
anchor_handoff:
  # P02 responsibilities
  p02_emits:
    - prior_anchor_state
    - new_observation
    - observation_confidence

  # P03 responsibilities
  p03_updates:
    - bayesian_posterior
    - drift_detection
    - confidence_interval

  # Handoff event
  topic: p02.anchor.observation.v1
```

---

#### 12.3.3 Question Framing Templates

**Status**: ✅ COMPLETE

| Gap Type | Template ID | Example |
|----------|-------------|---------|
| AMBIGUITY | `qt_ambiguity_01` | "I noticed {entity} — is this {option_a} or {option_b}?" |
| CONTRADICTION | `qt_contradict_01` | "Earlier you said {statement_a}, but now {statement_b}. Which is current?" |
| LOW_CONFIDENCE | `qt_confirm_01` | "Just to confirm: {statement} — is that right?" |
| MISSING_INFO | `qt_missing_01` | "I don't have details about {topic}. Can you tell me more?" |

Templates stored: `k1/contracts/jsonschema/question_templates/`

---

#### 12.3.4 P05 Attention Budget Integration

**Status**: ✅ COMPLETE

```yaml
# P05 integration for question rate limiting
attention_budget:
  integration_mode: sync  # sync or async
  budget_request_timeout_ms: 100
  fallback_on_timeout: queue_locally

  # P03 gap emission respects P05 budget
  emit_if_budget_available: true
  queue_if_no_budget: true
  max_queue_age_hours: 24
```

---

### 12.4 Feature Flag Master List

| Flag Name | Type | Default | Description |
|-----------|------|---------|-------------|
| `P03_FF_CONTRADICT_BLOCKING` | bool | `false` | Block on unresolved contradictions |
| `P03_FF_ANCHOR_DRIFT_MODE` | enum | `multimodal` | Anchor drift handling strategy |
| `P03_FF_R5_MODE` | enum | `conditional` | Dream phase execution mode |
| `P03_FF_GAP_DETECTION_ENABLED` | bool | `true` | Enable P06 gap detection |
| `P03_FF_SIMHASH_DEDUP_ENABLED` | bool | `true` | Enable near-duplicate detection |
| `P03_FF_GRANGER_CAUSALITY_ENABLED` | bool | `true` | Enable causal inference in R4 |
| `P03_FF_OPTIMISTIC_LOCKING` | bool | `true` | Use optimistic locking for writes |
| `P03_FF_ADAPTIVE_BATCHING` | bool | `true` | Adjust batch size based on load |
| `P03_FF_OBSERVABILITY_VERBOSE` | bool | `false` | Emit detailed phase-level metrics |

#### 12.4.1 Feature Flag Operational Guide

| Scenario | Flag Change | Command | Rollback |
|----------|-------------|---------|----------|
| **High backlog recovery** | Disable R5 | `k0ctl feature set P03_FF_R5_MODE disabled` | `k0ctl feature set P03_FF_R5_MODE conditional` |
| **Debug reconciliation** | Enable verbose | `k0ctl feature set P03_FF_OBSERVABILITY_VERBOSE true` | `k0ctl feature set P03_FF_OBSERVABILITY_VERBOSE false` |
| **P06 outage mitigation** | Disable gaps | `k0ctl feature set P03_FF_GAP_DETECTION_ENABLED false` | `k0ctl feature set P03_FF_GAP_DETECTION_ENABLED true` |
| **Test contradiction flow** | Block on contradict | `k0ctl feature set P03_FF_CONTRADICT_BLOCKING true` | `k0ctl feature set P03_FF_CONTRADICT_BLOCKING false` |
| **Reduce R4 load** | Disable Granger | `k0ctl feature set P03_FF_GRANGER_CAUSALITY_ENABLED false` | Enable after load normalizes |
| **Performance baseline** | Fixed batch size | `k0ctl feature set P03_FF_ADAPTIVE_BATCHING false` | Re-enable for production |

#### 12.4.2 Environment-Specific Defaults

| Environment | R5_MODE | OBSERVABILITY_VERBOSE | ADAPTIVE_BATCHING | Notes |
|-------------|---------|----------------------|-------------------|-------|
| Development | `disabled` | `true` | `false` | Fast iteration, full logging |
| Staging | `conditional` | `true` | `true` | Production-like with visibility |
| Production | `conditional` | `false` | `true` | Optimized for throughput |
| Load Test | `disabled` | `false` | `true` | Maximum throughput testing |

```python
# k0/pipelines/p03/feature_flags.py
from k0.config import FeatureFlags

P03_FLAGS = FeatureFlags(
    prefix="P03_FF",
    defaults={
        "CONTRADICT_BLOCKING": False,
        "ANCHOR_DRIFT_MODE": "multimodal",
        "R5_MODE": "conditional",
        "GAP_DETECTION_ENABLED": True,
        "SIMHASH_DEDUP_ENABLED": True,
        "GRANGER_CAUSALITY_ENABLED": True,
        "OPTIMISTIC_LOCKING": True,
        "ADAPTIVE_BATCHING": True,
        "OBSERVABILITY_VERBOSE": False,
    }
)
```

---

## 13. Error Handling & Dead Letter Queue

> **Status**: COMPLETE

### 13.1 K0 Integration Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                    P03 ERROR HANDLING - K0 ARCHITECTURE INTEGRATION                      │
│                                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              P03 PIPELINE (Layer 6)                              │   │
│   │                                                                                  │   │
│   │   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │   │
│   │   │   R0    │→│   R1    │→│   R2    │→│   R3    │→│   R4    │→│  R5-R8  │      │   │
│   │   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘      │   │
│   │        │           │           │           │           │           │             │   │
│   │        ▼           ▼           ▼           ▼           ▼           ▼             │   │
│   │   ┌─────────────────────────────────────────────────────────────────────────┐   │   │
│   │   │               P03 ERROR HANDLER (per-phase classification)               │   │   │
│   │   └─────────────────────────────────────────────────────────────────────────┘   │   │
│   │                                     │                                            │   │
│   └─────────────────────────────────────┼────────────────────────────────────────────┘   │
│                                         │                                                │
│   ┌─────────────────────────────────────┼────────────────────────────────────────────┐   │
│   │                      K0 STORAGE CORE (Layer 4)                                   │   │
│   │                                     │                                            │   │
│   │   ┌─────────────────┐  ┌───────────┴───────────┐  ┌─────────────────┐           │   │
│   │   │   st_dlq        │  │  k0/storage/dlq.py    │  │   st_outbox     │           │   │
│   │   │   (P03 errors)  │←─│  • record()           │  │   (retries)     │           │   │
│   │   │                 │  │  • list_pending()     │  │                 │           │   │
│   │   │                 │  │  • mark_requeued()    │  │                 │           │   │
│   │   └─────────────────┘  └───────────────────────┘  └─────────────────┘           │   │
│   │                                                                                  │   │
│   └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
│   ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│   │                      K0 OBSERVABILITY (Layer 9)                                  │   │
│   │                                                                                  │   │
│   │   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │   │
│   │   │ MetricsExporter │  │  TracerFactory  │  │ ObsEmitter      │                 │   │
│   │   │ k0/obs/metrics  │  │ k0/obs/tracing  │  │ k0/obs/events   │                 │   │
│   │   └─────────────────┘  └─────────────────┘  └─────────────────┘                 │   │
│   │                                                                                  │   │
│   └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 13.2 Error Classification

| Error Type     | Severity | K0 Component        | Retry Strategy            | Example                             |
|----------------|----------|---------------------|---------------------------|-------------------------------------|
| **TRANSIENT**  | Low      | RetryScheduler      | Yes (exponential backoff) | DB connection timeout, lock contention |
| **VALIDATION** | Medium   | DLQ → st_dlq        | No (DLQ)                  | Schema mismatch, constraint violation |
| **LOGIC**      | High     | DLQ + ObsEmitter    | No (DLQ + alert)          | Reconciliation logic failure        |
| **FATAL**      | Critical | Circuit Breaker     | No (abort cycle)          | Out of memory, disk full            |

### 13.3 K0 DLQ Integration

```python
# k0/pipelines/p03/error_handler.py

from k0.storage.dlq import DLQStore, DLQRecord
from k0.outbox.scheduler import RetryScheduler, RetryDecision
from k0.obs.events import ObservabilityEmitter
from k0.obs.metrics import MetricsExporter


class P03ErrorHandler:
    """
    Error handler integrated with K0 DLQ subsystem (Layer 4).

    References:
    - k0/storage/dlq.py: DLQStore.record(), list_pending(), mark_requeued()
    - k0/outbox/scheduler.py: RetryScheduler.decide()
    """

    def __init__(
        self,
        dlq_store: DLQStore,          # k0/storage/dlq.py
        retry_scheduler: RetryScheduler,  # k0/outbox/scheduler.py
        metrics: MetricsExporter,      # k0/obs/metrics.py
        emitter: ObservabilityEmitter  # k0/obs/events.py
    ):
        self.dlq = dlq_store
        self.retry = retry_scheduler
        self.metrics = metrics
        self.emitter = emitter

    async def handle_error(
        self,
        cycle_id: str,
        phase: str,
        event_id: str,
        error: Exception,
        payload: dict
    ) -> None:
        """Route error to appropriate K0 subsystem."""

        error_type = self._classify_error(error)

        # Record metrics via K0 MetricsExporter
        self.metrics.counter(
            'p03_errors_total',
            labels={'phase': phase, 'error_type': error_type}
        )

        if error_type == 'TRANSIENT':
            # Use K0 RetryScheduler for retry decision
            decision: RetryDecision = self.retry.decide(
                attempt_count=self._get_attempt_count(event_id),
                error_code=str(type(error).__name__)
            )

            if decision.should_retry:
                await self._schedule_retry(event_id, decision.delay_ms)
            else:
                await self._send_to_dlq(cycle_id, phase, event_id, error, payload)
        else:
            # Validation/Logic/Fatal → immediate DLQ
            await self._send_to_dlq(cycle_id, phase, event_id, error, payload)

            if error_type in ('LOGIC', 'FATAL'):
                # Emit observability event for alerting
                await self.emitter.emit({
                    'event_type': 'p03.error.critical',
                    'cycle_id': cycle_id,
                    'phase': phase,
                    'error_type': error_type,
                    'error_message': str(error)
                })

    async def _send_to_dlq(
        self,
        cycle_id: str,
        phase: str,
        event_id: str,
        error: Exception,
        payload: dict
    ) -> None:
        """
        Record error in K0 DLQ (st_dlq table).

        Uses k0/storage/dlq.py: DLQStore.record()
        """
        await self.dlq.record(
            DLQRecord(
                id=f"{cycle_id}:{phase}:{event_id}",
                pipeline_id='p03_consolidation',
                phase=phase,
                event_id=event_id,
                payload_json=json.dumps(payload),
                error_type=self._classify_error(error),
                error_code=type(error).__name__,
                error_message=str(error),
                stack_trace=traceback.format_exc(),
                attempt_count=self._get_attempt_count(event_id),
                max_attempts=3,
                last_attempt_at=now_ms(),
                next_attempt_at=None,
                status='PENDING'
            )
        )

    def _classify_error(self, error: Exception) -> str:
        """Classify error by type for routing decision."""
        if isinstance(error, (ConnectionError, TimeoutError, LockError)):
            return 'TRANSIENT'
        elif isinstance(error, (ValidationError, SchemaError, ConstraintError)):
            return 'VALIDATION'
        elif isinstance(error, (MemoryError, DiskFullError)):
            return 'FATAL'
        else:
            return 'LOGIC'
```

### 13.4 Dead Letter Queue Schema (st_dlq)

```sql
-- K0 DLQ schema used by P03
-- Source: k0/storage/dlq.py → st_dlq table

CREATE TABLE st_dlq (
  -- Identity
  id TEXT PRIMARY KEY,

  -- Source (P03-specific)
  pipeline_id TEXT NOT NULL,             -- 'p03_consolidation'
  phase TEXT NOT NULL,                   -- R0, R1, ..., R8

  -- Failed Item
  event_id TEXT,                         -- Source event (if applicable)
  entity_id TEXT,                        -- Related entity (if applicable)
  payload_json TEXT NOT NULL,            -- Serialized failed item

  -- Error Details
  error_type TEXT NOT NULL CHECK(error_type IN (
    'TRANSIENT', 'VALIDATION', 'LOGIC', 'FATAL'
  )),
  error_code TEXT NOT NULL,
  error_message TEXT NOT NULL,
  stack_trace TEXT,

  -- Retry Tracking (K0 RetryScheduler integration)
  attempt_count INTEGER DEFAULT 1,
  max_attempts INTEGER DEFAULT 3,
  last_attempt_at INTEGER NOT NULL,
  next_attempt_at INTEGER,

  -- Status (K0 DLQ lifecycle)
  status TEXT DEFAULT 'PENDING' CHECK(status IN (
    'PENDING',       -- Awaiting retry
    'RETRYING',      -- Currently being retried
    'RESOLVED',      -- Successfully reprocessed
    'ABANDONED',     -- Max retries exceeded
    'MANUAL_REVIEW'  -- Requires human intervention
  )),

  -- Resolution
  resolved_at INTEGER,
  resolved_by TEXT,
  resolution_notes TEXT,

  -- Metadata
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
);

-- K0 standard indexes for DLQ queries
CREATE INDEX idx_dlq_status_next ON st_dlq(status, next_attempt_at) WHERE status = 'PENDING';
CREATE INDEX idx_dlq_pipeline_phase ON st_dlq(pipeline_id, phase);
```

### 13.5 Retry Strategy (K0 RetryScheduler)

```python
# Integration with k0/outbox/scheduler.py: RetryScheduler

from k0.outbox.scheduler import RetryScheduler, RetryDecision


class P03RetryConfig:
    """
    P03-specific retry configuration using K0 RetryScheduler.

    K0 Reference: k0/outbox/scheduler.py
    - decide(): Returns RetryDecision with should_retry, delay_ms
    - max_attempts(): Returns max retry count by error code
    """

    # Base configuration (fed to K0 RetryScheduler)
    base_delay_ms: int = 1000
    max_delay_ms: int = 60000
    exponential_base: float = 2.0
    jitter_factor: float = 0.1

    # P03-specific overrides by phase
    phase_overrides: dict = {
        'R0': {'max_attempts': 5},   # Trigger detection can retry more
        'R7': {'max_attempts': 10},  # Truth writes are critical
        'R8': {'max_attempts': 3},   # Bus emission standard
    }


def create_p03_retry_scheduler() -> RetryScheduler:
    """Factory for P03's K0 RetryScheduler instance."""
    return RetryScheduler(
        base_delay_ms=P03RetryConfig.base_delay_ms,
        max_delay_ms=P03RetryConfig.max_delay_ms,
        exponential_base=P03RetryConfig.exponential_base,
        jitter_factor=P03RetryConfig.jitter_factor
    )
```

### 13.6 Circuit Breaker (External Dependencies)

```python
from k0.chaos.toggles import get_network_delay_ms


class P03CircuitBreaker:
    """
    Circuit breaker for P03's external dependencies (P08, Bus).

    Integrates with K0 chaos toggles for testing resilience.
    K0 Reference: k0/chaos/toggles.py
    """

    states = ['CLOSED', 'OPEN', 'HALF_OPEN']

    failure_threshold: int = 5          # Failures before opening
    reset_timeout_seconds: int = 60     # Time before half-open
    success_threshold: int = 3          # Successes before closing

    def __init__(self, dependency_name: str):
        self.dependency = dependency_name
        self.state = 'CLOSED'
        self.failure_count = 0
        self.success_count = 0
        self.opened_at: Optional[float] = None

    def should_allow_request(self) -> bool:
        """Check if request should be allowed through circuit."""
        # K0 chaos injection for testing
        if get_network_delay_ms() > 30000:  # Simulated network partition
            self.state = 'OPEN'
            return False

        if self.state == 'CLOSED':
            return True
        if self.state == 'OPEN':
            if self._time_since_opened() > self.reset_timeout_seconds:
                self.state = 'HALF_OPEN'
                return True
            return False
        if self.state == 'HALF_OPEN':
            return True  # Allow test request
        return False

    def record_success(self) -> None:
        """Record successful call."""
        if self.state == 'HALF_OPEN':
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = 'CLOSED'
                self.failure_count = 0
                self.success_count = 0

    def record_failure(self) -> None:
        """Record failed call."""
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            self.opened_at = time.time()


# Circuit breakers for P03 dependencies
P03_CIRCUITS = {
    'p08_embedding': P03CircuitBreaker('p08_embedding'),
    'bus_dispatcher': P03CircuitBreaker('bus_dispatcher'),
    'faiss_index': P03CircuitBreaker('faiss_index'),
}
```

### 13.7 Partial Failure Handling

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       PARTIAL FAILURE RECOVERY STRATEGY                     │
│                                                                             │
│   Scenario: 90/100 events succeed, 10 fail                                  │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ Strategy 1: COMMIT_PARTIAL (default)                                 │  │
│   │                                                                      │  │
│   │ • Commit successful events via K0 UnitOfWork                         │  │
│   │ • Move failed events to K0 DLQ (st_dlq)                              │  │
│   │ • Advance K0 OffsetStore to last successful event                    │  │
│   │ • Continue to next phase                                             │  │
│   │                                                                      │  │
│   │ K0 Integration:                                                      │  │
│   │ - k0/uow/unit_of_work.py: UnitOfWork._commit()                      │  │
│   │ - k0/storage/dlq.py: DLQStore.record()                              │  │
│   │ - k0/storage/offsets.py: OffsetStore.upsert()                       │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ Strategy 2: ROLLBACK_ALL                                             │  │
│   │                                                                      │  │
│   │ • Rollback entire batch via K0 UnitOfWork._rollback()               │  │
│   │ • Do not advance K0 OffsetStore                                      │  │
│   │ • Retry entire batch on next cycle                                   │  │
│   │ • Use when ordering is critical                                      │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ Strategy 3: QUARANTINE_BATCH                                         │  │
│   │                                                                      │  │
│   │ • Move entire batch to quarantine (DLQ with special status)          │  │
│   │ • Advance K0 OffsetStore                                             │  │
│   │ • Process quarantine in dedicated k0ctl dlq recover job              │  │
│   │ • Use when failure rate exceeds threshold (e.g., >20%)               │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 13.8 K0 CLI Integration (k0ctl dlq)

```python
# P03 DLQ recovery via k0ctl CLI
# Reference: k0/cli/k0ctl.py → dlq commands

"""
k0ctl CLI commands for P03 DLQ management:

$ k0ctl dlq list --pipeline p03_consolidation --status PENDING
$ k0ctl dlq get <dlq_id>
$ k0ctl dlq requeue <dlq_id>
$ k0ctl dlq purge --pipeline p03_consolidation --older-than 7d
$ k0ctl dlq stats --pipeline p03_consolidation

These commands use:
- k0/storage/dlq.py: list_pending(), get(), mark_requeued(), purge()
"""
```

### 13.9 Edge Case Handling Matrix

| Edge Case | Detection | Handling Strategy | Recovery Action | Metric |
|-----------|-----------|-------------------|-----------------|--------|
| **Empty st_hipp_events** (>24h) | Scheduled health check | Emit `p03.health.idle.v1` event | No action (normal during low activity) | `p03_idle_cycles_total` |
| **Corrupted embeddings in st_vec** | Dimension mismatch or NaN detection | Skip event, flag for P08 re-embedding | `UPDATE st_vec SET status='RECOMPUTE_REQUIRED'` | `p03_corrupted_embeddings_total` |
| **Partial R7 write failure** | Transaction rollback exception | Use COMMIT_PARTIAL strategy; successful writes persist, failed go to DLQ | Manual DLQ requeue after fix | `p03_partial_write_failures_total` |
| **st_hipp_events backlog > 10K** | Batch selector overflow | Trigger adaptive batching; increase batch_size to 2000 | Page via k0ctl ops alert | `p03_backlog_overflow_total` |
| **P08 circuit open > 5min** | Circuit breaker OPEN state duration | Queue embedding requests locally; process when circuit closes | Automatic on circuit HALF_OPEN | `p03_p08_circuit_open_seconds` |
| **FAISS index unavailable** | Index load failure or timeout | Fall back to brute-force similarity (slower) | Trigger FAISS index rebuild job | `p03_faiss_fallback_total` |
| **Duplicate cycle trigger** | Same batch_hash detected within cycle_id | Idempotent skip; log and continue | None (by design) | `p03_duplicate_triggers_total` |
| **Memory pressure during R5** | Go/Python heap > 80% threshold | Skip R5 creative algorithms | Automatic via `can_skip_dream_phase()` | `p03_r5_memory_skipped_total` |
| **KG entity explosion** (>1M nodes) | Node count threshold exceeded | Partition KG by space_id; process in chunks | Enable KG sharding feature flag | `p03_kg_partition_events_total` |

### 13.10 Recovery Procedures

#### 13.10.1 Manual DLQ Recovery

```bash
# List pending DLQ items for P03
k0ctl dlq list --pipeline p03_consolidation --status PENDING

# Inspect specific failed event
k0ctl dlq get <dlq_id> --verbose

# Requeue after fix (retries with exponential backoff)
k0ctl dlq requeue <dlq_id>

# Bulk requeue all pending items
k0ctl dlq requeue-all --pipeline p03_consolidation --max-items 100
```

#### 13.10.2 Partial Write Recovery

When R7 writes partially fail (e.g., st_epi succeeded, st_sem failed):

1. **Identify affected events**: `k0ctl dlq list --phase R7 --error-code PARTIAL_WRITE`
2. **Check consistency**: Query st_epi for orphaned episodes without corresponding st_sem
3. **Replay from checkpoint**: Use idempotency key to replay from R6 staging
4. **Verify**: Run `k0ctl verify p03 --cycle-id <ulid>` to confirm consistency

#### 13.10.3 Backlog Recovery

When st_hipp_events backlog exceeds threshold:

1. **Increase batch size**: `k0ctl config set p03.batch.size 2000`
2. **Enable parallel cycles**: `k0ctl config set p03.parallel_cycles 2`
3. **Skip R5 temporarily**: `k0ctl feature set P03_FF_R5_MODE disabled`
4. **Monitor drain rate**: `k0ctl metrics watch p03_events_processed_per_second`
5. **Restore defaults**: After backlog < 1000, restore original settings

#### 13.10.4 FAISS Index Rebuild

```bash
# Trigger full index rebuild (expensive, use off-peak)
k0ctl p08 faiss rebuild --tenant-id <tid> --confirm

# Verify index health
k0ctl p08 faiss verify --tenant-id <tid>
```

---

## 14. Security & Privacy

> **Status**: COMPLETE

### 14.1 K0 Policy Engine Integration

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                    P03 SECURITY - K0 POLICY ENGINE INTEGRATION                           │
│                                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                         K0 LAYER 2: GATE & POLICY                                │   │
│   │                                                                                  │   │
│   │   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐            │   │
│   │   │   PEP Syscall   │    │  PolicyStamp    │    │   Redaction     │            │   │
│   │   │ k0/policy/pep   │    │ k0/policy/stamp │    │ k0/policy/redact│            │   │
│   │   │                 │    │                 │    │                 │            │   │
│   │   │ evaluate_env()  │    │ create_stamp()  │    │ apply_redact()  │            │   │
│   │   │ _lookup_band()  │    │ attach_stamp()  │    │ mask_location() │            │   │
│   │   │ _build_oblig()  │    │ extract_stamp() │    │                 │            │   │
│   │   └────────┬────────┘    └────────┬────────┘    └────────┬────────┘            │   │
│   │            │                      │                      │                      │   │
│   │            └──────────────────────┼──────────────────────┘                      │   │
│   │                                   │                                              │   │
│   └───────────────────────────────────┼──────────────────────────────────────────────┘   │
│                                       │                                                  │
│                                       ▼                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              P03 CONSOLIDATION                                   │   │
│   │                                                                                  │   │
│   │   ┌─────────────────────────────────────────────────────────────────────────┐   │   │
│   │   │                    PRIVACY-AWARE CONSOLIDATION                           │   │   │
│   │   │                                                                          │   │   │
│   │   │  • Honor PolicyStamp.band for cross-event linking                       │   │   │
│   │   │  • Apply Redaction.obligations before KG ingestion                      │   │   │
│   │   │  • Enforce tenant_id isolation (ACL Enforcer)                           │   │   │
│   │   │  • Audit all reconciliation decisions                                   │   │   │
│   │   │                                                                          │   │   │
│   │   └─────────────────────────────────────────────────────────────────────────┘   │   │
│   │                                                                                  │   │
│   └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
│   ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│   │                         K0 SECURITY LAYER                                        │   │
│   │                                                                                  │   │
│   │   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐            │   │
│   │   │   ACL Enforcer  │    │ Location Privacy│    │Retention Enforcer│            │   │
│   │   │ k0/policy/acl   │    │ k0/policy/loc   │    │ k0/policy/ret   │            │   │
│   │   └─────────────────┘    └─────────────────┘    └─────────────────┘            │   │
│   │                                                                                  │   │
│   └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 14.2 Privacy Band Enforcement

#### 14.2.1 K0 Privacy Bands in Consolidation

```python
# Integration with k0/policy/pep_syscall.py

from k0.policy.pep_syscall import evaluate_envelope, PolicyStamp
from k0.policy.redaction import apply_redactions


class PrivacyBandEnforcer:
    """
    Enforce K0 privacy bands during P03 consolidation.

    K0 References:
    - k0/policy/pep_syscall.py: _lookup_band_policy()
    - k0/policy/policy_stamp.py: PolicyStamp.band
    - k0/policy/redaction.py: apply_redactions()
    """

    # K0 privacy band definitions (from k0/policy/pep_syscall.py)
    BAND_CONSTRAINTS = {
        'GREEN': {
            'cross_event_linking': True,
            'cross_actor_linking': True,
            'kg_ingestion': True,
            'location_precision': 'full',  # k0/policy/location_privacy.py
        },
        'AMBER': {
            'cross_event_linking': True,
            'cross_actor_linking': False,  # Same actor only
            'kg_ingestion': True,
            'location_precision': 'city',  # ~10km precision
        },
        'RED': {
            'cross_event_linking': False,  # Self only
            'cross_actor_linking': False,
            'kg_ingestion': False,         # No KG entities
            'location_precision': 'country',
        },
    }


def can_link_events_k0(
    event_a: HippEvent,
    event_b: HippEvent,
    stamp_a: PolicyStamp,
    stamp_b: PolicyStamp
) -> bool:
    """
    K0-integrated cross-event linking check.

    Uses PolicyStamp.band from k0/policy/policy_stamp.py
    """
    band_a = stamp_a.band
    band_b = stamp_b.band

    # RED events cannot link to anything else
    if band_a == 'RED' or band_b == 'RED':
        return event_a.event_id == event_b.event_id  # Only self-reference

    # AMBER events link only within same actor
    if band_a == 'AMBER' or band_b == 'AMBER':
        return event_a.actor_id == event_b.actor_id

    # GREEN events can link freely within space
    return event_a.space_id == event_b.space_id
```

| Band      | Cross-Event | Cross-Actor | KG Entities | Location      | K0 Source                    |
|-----------|-------------|-------------|-------------|---------------|------------------------------|
| **GREEN** | Yes         | Yes         | Full        | Full          | k0/policy/pep_syscall.py     |
| **AMBER** | Yes         | Same only   | Anonymized  | City (~10km)  | k0/policy/location_privacy.py|
| **RED**   | Self only   | No          | No          | Country       | k0/policy/redaction.py       |

### 14.3 K0 ACL Enforcer Integration

```python
# Integration with k0/policy/acl_enforcer.py

from k0.policy.acl_enforcer import ACLEnforcer


class P03TenantIsolation:
    """
    Tenant isolation using K0 ACL Enforcer.

    K0 References:
    - k0/policy/acl_enforcer.py: check_permission(), grant_permission()
    - k0/storage/acl.py: st_acl table
    """

    def __init__(self, acl_enforcer: ACLEnforcer):
        self.acl = acl_enforcer

    async def verify_consolidation_access(
        self,
        tenant_id: str,
        space_id: str,
        actor_id: str
    ) -> bool:
        """
        Verify actor has permission to trigger consolidation.
        Uses K0 ACL check_permission().
        """
        return await self.acl.check_permission(
            subject=actor_id,
            resource=f"tenant:{tenant_id}/space:{space_id}",
            action="consolidate"
        )

    def build_isolated_query(
        self,
        base_query: str,
        tenant_id: str,
        space_id: str
    ) -> str:
        """
        All P03 queries MUST include tenant isolation.
        This is enforced at the query builder level.
        """
        # Tenant isolation is ALWAYS enforced
        return f"""
            {base_query}
            WHERE tenant_id = :tenant_id    -- MANDATORY (K0 ACL)
              AND space_id = :space_id
        """


class ConsolidationQueryBuilder:
    """All queries MUST include tenant_id filter (K0 ACL requirement)."""

    def build_truth_query(
        self,
        tenant_id: str,
        space_id: str,
        pattern_type: str
    ) -> str:
        # Tenant isolation is ALWAYS enforced per K0 ACL policy
        return f"""
            SELECT * FROM st_sem
            WHERE tenant_id = :tenant_id    -- MANDATORY (K0 ACL)
              AND space_id = :space_id
              AND pattern_type = :pattern_type
              AND is_canonical = TRUE
              AND archival_status = 'ACTIVE'
        """
```

### 14.4 K0 Location Privacy Integration

```python
# Integration with k0/policy/location_privacy.py

from k0.policy.location_privacy import (
    lat_lon_to_geohash,
    get_geohash_precision_for_band,
    mask_location_for_band,
    apply_location_privacy
)


class P03LocationPrivacy:
    """
    Apply K0 location privacy during consolidation.

    K0 References:
    - k0/policy/location_privacy.py: mask_location_for_band()
    - k0/policy/location_privacy.py: get_geohash_precision_for_band()
    """

    async def process_location_for_kg(
        self,
        event: HippEvent,
        policy_stamp: PolicyStamp
    ) -> Optional[dict]:
        """
        Process location before KG ingestion.
        Applies K0 band-based precision masking.
        """
        if not event.location:
            return None

        band = policy_stamp.band

        # Get precision for band (K0 location_privacy.py)
        precision = get_geohash_precision_for_band(band)

        # Mask to allowed precision
        masked = mask_location_for_band(
            lat=event.location['lat'],
            lon=event.location['lon'],
            band=band
        )

        return {
            'geohash': lat_lon_to_geohash(
                masked['lat'],
                masked['lon'],
                precision=precision
            ),
            'precision_meters': self._precision_to_meters(precision),
            'original_masked': True
        }

    def _precision_to_meters(self, precision: int) -> int:
        """K0 geohash precision to meters."""
        # From k0/policy/location_privacy.py
        return {
            1: 5000000,   # Country
            2: 1250000,   # Region
            3: 156000,    # State
            4: 39000,     # City
            5: 4900,      # Neighborhood
            6: 1200,      # Block
            7: 150,       # Street
            8: 40,        # Building
        }.get(precision, 5000000)
```

### 14.5 Audit Trail (K0 Observability)

```python
# Integration with k0/obs/events.py and k0/storage/obligations.py

from k0.obs.events import ObservabilityEmitter
from k0.storage.obligations import ObligationStore


class P03AuditTrail:
    """
    Audit trail using K0 Observability subsystem.

    K0 References:
    - k0/obs/events.py: ObservabilityEmitter.emit()
    - k0/storage/obligations.py: ObligationStore.save()
    - k0/obs/tracing.py: TracerFactory for trace context
    """

    def __init__(
        self,
        emitter: ObservabilityEmitter,
        obligations: ObligationStore
    ):
        self.emitter = emitter
        self.obligations = obligations

    async def log_reconciliation_decision(
        self,
        cycle_id: str,
        phase: str,
        tenant_id: str,
        space_id: str,
        decision_type: str,
        source_event_id: str,
        target_truth_id: Optional[str],
        similarity_score: float,
        confidence_before: float,
        confidence_after: float
    ) -> None:
        """
        Log reconciliation decision to K0 audit trail.
        Stored in st_cognitive_traces via ObservabilityEmitter.
        """
        await self.emitter.emit({
            'event_type': 'p03.reconciliation.decision',
            'cycle_id': cycle_id,
            'phase': phase,
            'tenant_id': tenant_id,
            'space_id': space_id,
            'decision_type': decision_type,
            'source_event_id': source_event_id,
            'target_truth_id': target_truth_id,
            'similarity_score': similarity_score,
            'confidence_before': confidence_before,
            'confidence_after': confidence_after,
            'timestamp': now_ms()
        })
```

#### 14.5.1 Decision Audit Schema

```sql
-- P03 audit events stored in K0's st_cognitive_traces
-- K0 Reference: k0/obs/events.py → ObservabilityEmitter

-- Query for P03 reconciliation decisions:
SELECT * FROM st_cognitive_traces
WHERE json_extract(payload, '$.event_type') = 'p03.reconciliation.decision'
  AND tenant_id = :tenant_id
ORDER BY timestamp DESC;

-- P03-specific audit table for detailed decision tracking
CREATE TABLE st_consolidation_audit (
  -- Identity
  audit_id TEXT PRIMARY KEY,

  -- Context
  cycle_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,

  -- Decision
  decision_type TEXT NOT NULL,           -- REINFORCE, EXTEND, CREATE, etc.
  source_event_id TEXT,
  target_truth_id TEXT,

  -- Evidence
  similarity_score REAL,
  confidence_before REAL,
  confidence_after REAL,
  decision_rationale TEXT,

  -- K0 Trace Context
  trace_id TEXT,                         -- K0 TracerFactory.current_trace_id()
  span_id TEXT,

  -- Timestamp
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_audit_cycle ON st_consolidation_audit(cycle_id, phase);
CREATE INDEX idx_audit_tenant_time ON st_consolidation_audit(tenant_id, created_at DESC);
CREATE INDEX idx_audit_trace ON st_consolidation_audit(trace_id);
```

### 14.6 K0 Retention Enforcer Integration

```python
# Integration with k0/policy/retention_enforcer.py

from k0.policy.retention_enforcer import RetentionEnforcer


class P03RetentionPolicy:
    """
    Apply K0 retention policies during consolidation.

    K0 References:
    - k0/policy/retention_enforcer.py: apply_policies(), get_expired_resources()
    """

    def __init__(self, retention: RetentionEnforcer):
        self.retention = retention

    async def apply_band_retention(
        self,
        tenant_id: str,
        band: str
    ) -> int:
        """
        Apply retention policies by privacy band.
        RED band has shortest retention, GREEN has longest.
        """
        # K0 RetentionEnforcer.apply_policies()
        result = await self.retention.apply_policies(
            tenant_id=tenant_id,
            resource_type='memory_layer',
            band_filter=band
        )
        return result.records_archived

    async def get_purgeable_records(
        self,
        tenant_id: str
    ) -> list:
        """
        Get records that have exceeded retention period.
        Uses K0 RetentionEnforcer.get_expired_resources().
        """
        return await self.retention.get_expired_resources(
            tenant_id=tenant_id,
            resource_types=['st_epi', 'st_sem', 'st_kg_entities']
        )
```

### 14.7 Data Minimization & GDPR

```python
# Integration with K0 policy and storage layers

from k0.storage.wal import WriteAheadLog


class P03ErasureHandler:
    """
    Handle GDPR Article 17 erasure requests.

    K0 References:
    - k0/storage/wal.py: WriteAheadLog for append-only audit
    - k0/policy/retention_enforcer.py: _delete_resource()
    """

    async def handle_erasure_request(
        self,
        tenant_id: str,
        actor_id: str,
        erasure_scope: str  # 'ACTOR_DATA' | 'ALL_MENTIONS' | 'FULL_PURGE'
    ) -> ErasureResult:
        """
        Handle data erasure request propagation to all memory layers.

        Steps (integrated with K0):
        1. Mark st_hipp_events as TOMBSTONE where actor_id matches
        2. Cascade to all truth tables (st_epi, st_sem, etc.)
        3. Remove from st_vec (embedding deletion)
        4. Request FAISS index rebuild from P08 via K0 BusDispatcher
        5. Update st_kg_dom and st_kg_edges (anonymize or delete)
        6. Log erasure in K0 audit trail (ObservabilityEmitter)
        7. Record in K0 WAL for compliance (WriteAheadLog.append())
        """
        erasure_id = generate_ulid()

        # Step 1-5: Cascade deletion
        affected_counts = await self._cascade_erasure(
            tenant_id, actor_id, erasure_scope
        )

        # Step 6: Audit via K0 ObservabilityEmitter
        await self.emitter.emit({
            'event_type': 'p03.erasure.completed',
            'erasure_id': erasure_id,
            'tenant_id': tenant_id,
            'actor_id': actor_id,
            'scope': erasure_scope,
            'affected_counts': affected_counts,
            'completed_at': now_ms()
        })

        # Step 7: WAL entry for compliance
        await self.wal.append({
            'type': 'ERASURE_REQUEST',
            'erasure_id': erasure_id,
            'tenant_id': tenant_id,
            'actor_id': actor_id,
            'scope': erasure_scope,
            'completed_at': now_ms()
        })

        return ErasureResult(
            erasure_id=erasure_id,
            status='COMPLETED',
            affected_counts=affected_counts
        )
```

### 14.8 Encryption (K0 Crypto Layer)

```python
# Integration with k0/security/crypto.py

from k0.security.crypto import (
    hash_payload,
    compute_envelope_sha256,
    encode_base64url
)


class P03Encryption:
    """
    Encryption using K0 security layer.

    K0 References:
    - k0/security/crypto.py: hash_payload(), compute_envelope_sha256()
    """

    # Sensitive columns requiring extra protection
    SENSITIVE_COLUMNS = {
        'st_hipp_events': ['body_text', 'attachments_json', 'location_name'],
        'st_epi': ['episode_summary'],
        'st_sem': ['pattern_description', 'pattern_attributes_json'],
    }

    def hash_sensitive_content(self, content: str) -> str:
        """
        Hash sensitive content using K0 crypto.
        Uses k0/security/crypto.py: hash_payload()
        """
        return hash_payload(content.encode('utf-8'))

    def compute_content_fingerprint(self, event: dict) -> str:
        """
        Compute content fingerprint for deduplication.
        Uses k0/security/crypto.py: compute_envelope_sha256()
        """
        return compute_envelope_sha256(event)
```

---

## 15. Performance Tuning

> **Status**: COMPLETE

### 15.1 K0 QoS Integration Overview

```
+-------------------------------------------------------------------------------------+
|                    P03 PERFORMANCE - K0 QOS INTEGRATION                             |
|                                                                                     |
|   +-----------------------------------------------------------------------------+   |
|   |                         K0 LAYER 5: QoS & Scheduling                        |   |
|   |                                                                             |   |
|   |   +-------------------+    +-------------------+    +-------------------+   |   |
|   |   |    Scheduler      |    |    QoSContext     |    |    QoSMetrics     |   |   |
|   |   | k0/qos/scheduler  |    | k0/qos/context    |    | k0/qos/metrics    |   |   |
|   |   |                   |    |                   |    |                   |   |   |
|   |   | acquire()         |    | consume_fanout()  |    | record_acq()      |   |   |
|   |   | tighten()         |    | consume_top_k()   |    | set_active()      |   |   |
|   |   | _release()        |    | tighten()         |    | set_util()        |   |   |
|   |   +--------+----------+    +--------+----------+    +--------+----------+   |   |
|   |            |                        |                        |              |   |
|   |            +------------------------+------------------------+              |   |
|   |                                     |                                       |   |
|   +-------------------------------------+---------------------------------------+   |
|                                         |                                           |
|                                         v                                           |
|   +-----------------------------------------------------------------------------+   |
|   |                              P03 CONSOLIDATION                              |   |
|   |                                                                             |   |
|   |   +---------------------------------------------------------------------+   |   |
|   |   |                    QoS-AWARE CONSOLIDATION                          |   |   |
|   |   |                                                                     |   |   |
|   |   |  * Acquire scheduler token before batch processing                  |   |   |
|   |   |  * Respect fanout_budget for cross-event queries                    |   |   |
|   |   |  * Respect top_k_budget for similarity search                       |   |   |
|   |   |  * Report metrics via QoSMetrics                                    |   |   |
|   |   |  * Release token on batch completion                                |   |   |
|   |   |                                                                     |   |   |
|   |   +---------------------------------------------------------------------+   |   |
|   |                                                                             |   |
|   +-----------------------------------------------------------------------------+   |
|                                                                                     |
|   +-------------------------------------------------------------------------+       |
|   |                         K0 LAYER 9: Observability                       |       |
|   |                                                                         |       |
|   |   +-------------------+    +-------------------+    +---------------+   |       |
|   |   |  MetricsExporter  |    |   TracerFactory   |    |    Logging    |   |       |
|   |   | k0/obs/metrics    |    | k0/obs/tracing    |    | k0/obs/log    |   |       |
|   |   +-------------------+    +-------------------+    +---------------+   |       |
|   |                                                                         |       |
|   +-------------------------------------------------------------------------+       |
|                                                                                     |
+-------------------------------------------------------------------------------------+
```

### 15.2 K0 Scheduler Integration

```python
# Integration with k0/qos/scheduler.py

from k0.qos.scheduler import Scheduler, SchedulerProfile, SchedulerToken
from k0.qos.context import QoSContext
from k0.qos.metrics import QoSMetrics


class P03SchedulerIntegration:
    """
    P03 integration with K0 QoS Scheduler.

    K0 References:
    - k0/qos/scheduler.py: Scheduler.acquire(), Scheduler.tighten()
    - k0/qos/context.py: QoSContext.consume_fanout(), QoSContext.consume_top_k()
    - k0/qos/metrics.py: QoSMetrics.record_acquisition()

    The K0 Scheduler uses Weighted Deficit Round Robin (WDRR) algorithm
    with priority bands: GREEN > AMBER > RED
    """

    def __init__(
        self,
        scheduler: Scheduler,
        qos_metrics: QoSMetrics,
        pipeline_id: str = "p03_consolidation"
    ):
        self.scheduler = scheduler
        self.qos_metrics = qos_metrics
        self.pipeline_id = pipeline_id

    async def acquire_batch_token(
        self,


### 15.3 Performance Baselines

> **Status**: Baseline targets defined. Actual measurements to be collected during integration testing.

#### 15.3.1 Phase Latency Targets

| Phase | Target P50 | Target P95 | Target P99 | Measured P95 | Status |
|-------|------------|------------|------------|--------------|--------|
| R0 (Batch Select) | 10ms | 50ms | 100ms | TBD | 📋 Pending |
| R1 (Importance/Hebbian) | 20ms | 100ms | 200ms | TBD | 📋 Pending |
| R2 (Episode Clustering) | 50ms | 200ms | 500ms | TBD | 📋 Pending |
| R3 (Dedup/Decay/Prune) | 30ms | 150ms | 300ms | TBD | 📋 Pending |
| R4 (KG/Entity/Causal) | 100ms | 300ms | 600ms | TBD | 📋 Pending |
| R5 (Dream - if enabled) | 200ms | 500ms | 1000ms | TBD | 📋 Pending |
| R6 (Status Update) | 10ms | 30ms | 50ms | TBD | 📋 Pending |
| R7 (Truth Write) | 50ms | 150ms | 300ms | TBD | 📋 Pending |
| R8 (Event Emit) | 5ms | 20ms | 50ms | TBD | 📋 Pending |
| **Full Cycle** | 500ms | 1500ms | 3000ms | TBD | 📋 Pending |

#### 15.3.2 Throughput Targets

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| Events per cycle | 1000 | TBD | 📋 Pending |
| Cycles per hour | 40 (90s interval) | TBD | 📋 Pending |
| Events per hour | 40,000 | TBD | 📋 Pending |
| Peak events per hour | 100,000 (with adaptive batching) | TBD | 📋 Pending |

#### 15.3.3 Resource Utilization Targets

| Resource | Target | Alert Threshold | Measured | Status |
|----------|--------|-----------------|----------|--------|
| Memory (per cycle) | < 512MB | 80% of limit | TBD | 📋 Pending |
| CPU (per cycle) | < 2 cores | 90% for >30s | TBD | 📋 Pending |
| DB connections | < 10 pooled | 80% pool exhaustion | TBD | 📋 Pending |
| FAISS queries/cycle | < 100 | N/A | TBD | 📋 Pending |

#### 15.3.4 Benchmark Test Command

```bash
# Run P03 performance benchmark against golden dataset
pytest tests/k0/pipelines/p03/performance/ -v --benchmark-json=p03_benchmark.json

# Generate baseline report
k0ctl benchmark report --input p03_benchmark.json --output docs/test_results/p03_baseline.md
```

---

### 15.4 K0 Scheduler Integration (continued)

        batch_size: int,
        band: str = "GREEN"
    ) -> Optional[SchedulerToken]:
        """
        Acquire scheduler token for batch processing.
        Uses K0 Scheduler.acquire() with WDRR algorithm.
        """
        # Build profile for P03 consolidation batch
        profile = SchedulerProfile(
            pipeline_id=self.pipeline_id,
            port="command",           # P03 is a command-side pipeline
            band=band,                # Privacy band affects priority
            estimated_cost=batch_size * 0.1,  # Cost heuristic
        )

        # Acquire token from K0 Scheduler
        token = await self.scheduler.acquire(profile)

        if token:
            # Record acquisition in K0 QoSMetrics
            self.qos_metrics.record_acquisition(
                pipeline_id=self.pipeline_id,
                port="command",
                band=band
            )

        return token

    async def release_token(self, token: SchedulerToken) -> None:
        """Release scheduler token after batch completion."""
        await self.scheduler._release(token)

# P03 Scheduler profiles by operation type

P03_SCHEDULER_PROFILES = {
    'BATCH_CONSOLIDATION': SchedulerProfile(
        pipeline_id='p03_consolidation',
        port='command',
        band='GREEN',
        estimated_cost=100.0,        # Medium cost
    ),
    'SIMILARITY_SEARCH': SchedulerProfile(
        pipeline_id='p03_consolidation',
        port='query',
        band='AMBER',
        estimated_cost=50.0,         # Lower cost
    ),
    'DREAM_EXPLORATION': SchedulerProfile(
        pipeline_id='p03_consolidation',
        port='command',
        band='GREEN',
        estimated_cost=200.0,        # Higher cost (creative)
    ),
}

```

### 15.3 K0 QoSContext Integration

```python
# Integration with k0/qos/context.py

from k0.qos.context import QoSContext
from k0.qos.policy import apply_qos_obligations, QoSTightening


class P03QoSContext:
    """
    P03 integration with K0 QoSContext for budget management.

    K0 References:
    - k0/qos/context.py: QoSContext.consume_fanout(), QoSContext.consume_top_k()
    - k0/qos/policy.py: apply_qos_obligations()

    QoS Budgets:
    - fanout_budget: Limits cross-event/cross-table queries
    - top_k_budget: Limits similarity search result size
    """

    def __init__(self, qos_ctx: QoSContext):
        self.qos_ctx = qos_ctx

    async def check_fanout_budget(self, required: int) -> bool:
        """
        Check if fanout budget allows cross-event queries.
        Used during R1-R4 when linking events across truth layers.
        """
        return self.qos_ctx.fanout_budget >= required

    async def consume_fanout(self, amount: int) -> bool:
        """
        Consume fanout budget for cross-event queries.
        Returns False if insufficient budget.
        """
        if self.qos_ctx.fanout_budget < amount:
            return False

        self.qos_ctx.consume_fanout(amount)
        return True

    async def check_top_k_budget(self, required: int) -> bool:
        """
        Check if top_k budget allows similarity search.
        Used during FAISS queries for pattern matching.
        """
        return self.qos_ctx.top_k_budget >= required

    async def consume_top_k(self, amount: int) -> bool:
        """
        Consume top_k budget for similarity search.
        Returns False if insufficient budget.
        """
        if self.qos_ctx.top_k_budget < amount:
            return False

        self.qos_ctx.consume_top_k(amount)
        return True

    async def apply_tightening(
        self,
        obligations: list[dict]
    ) -> None:
        """
        Apply QoS tightening from policy obligations.
        Uses K0 apply_qos_obligations().
        """
        tightening = apply_qos_obligations(obligations)
        if tightening:
            self.qos_ctx.tighten(tightening)


# Default QoS budgets for P03 operations
P03_QOS_DEFAULTS = {
    'fanout_budget': 1000,          # Max cross-event queries per batch
    'top_k_budget': 500,            # Max similarity results per batch
}
```

### 15.4 Batch Size Optimization (K0-Aware)

| Factor           | Small Batch (100) | Medium Batch (1000) | Large Batch (10000) | K0 Component                         |
|------------------|-------------------|---------------------|---------------------|--------------------------------------|
| **Latency**      | Low (~5s)         | Medium (~30s)       | High (~5min)        | k0/qos/scheduler.py                  |
| **Memory**       | Low (~50MB)       | Medium (~200MB)     | High (~1GB)         | k0/kernel/config.py                  |
| **Throughput**   | Low               | Optimal             | Diminishing returns | k0/qos/metrics.py                    |
| **Recovery**     | Fast              | Moderate            | Slow                | k0/storage/dlq.py                    |
| **Token Cost**   | 10                | 100                 | 1000                | k0/qos/scheduler.py: estimated_cost  |
| **fanout_budget**| 100               | 500                 | 2000                | k0/qos/context.py                    |
| **top_k_budget** | 50                | 250                 | 1000                | k0/qos/context.py                    |

```python
# K0-aware adaptive batch sizing

from k0.qos.scheduler import Scheduler
from k0.qos.metrics import QoSMetrics


class P03AdaptiveBatchSizer:
    """
    Adaptive batch sizing integrated with K0 QoS.

    K0 References:
    - k0/qos/scheduler.py: Scheduler.active_tokens()
    - k0/qos/metrics.py: QoSMetrics.set_port_utilization()
    """

    def __init__(
        self,
        scheduler: Scheduler,
        qos_metrics: QoSMetrics,
        base_batch_size: int = 1000
    ):
        self.scheduler = scheduler
        self.qos_metrics = qos_metrics
        self.base_batch_size = base_batch_size

    async def compute_optimal_batch_size(
        self,
        available_memory_mb: int,
        time_budget_seconds: int
    ) -> int:
        """
        Compute optimal batch size based on K0 scheduler state.
        """
        # Check K0 scheduler capacity
        active_tokens = self.scheduler.active_tokens()

        # High contention = smaller batches
        if active_tokens > 10:
            contention_factor = 0.5
        elif active_tokens > 5:
            contention_factor = 0.75
        else:
            contention_factor = 1.0

        # Memory constraint
        memory_factor = min(1.0, available_memory_mb / 512)

        # Time constraint
        time_factor = min(1.0, time_budget_seconds / 300)

        optimal = int(
            self.base_batch_size *
            contention_factor *
            memory_factor *
            time_factor
        )

        # Report to K0 QoSMetrics
        self.qos_metrics.set_port_utilization(
            port="command",
            utilization=active_tokens / 20.0  # Assume 20 max tokens
        )

        return max(100, min(10000, optimal))  # Clamp to [100, 10000]
```

### 15.5 Embedding Query Optimization (K0-Aware)

```python
# Integration with K0 QoS for similarity queries

from k0.qos.context import QoSContext
from k0.fabric.fabric import CapabilityFabric


class P03EmbeddingQueryOptimizer:
    """
    Optimize similarity queries with K0 QoS awareness.

    K0 References:
    - k0/qos/context.py: QoSContext.consume_top_k()
    - k0/fabric/fabric.py: CapabilityFabric.invoke() for P08 embedding
    - k0/drivers/faiss_driver.py: FAISS search operations
    """

    def __init__(
        self,
        qos_ctx: QoSContext,
        fabric: CapabilityFabric
    ):
        self.qos_ctx = qos_ctx
        self.fabric = fabric

    async def query_similar_patterns(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10
    ) -> List[PatternMatch]:
        """
        Two-stage retrieval with K0 QoS budget tracking.

        Stage 1: FAISS ANN via K0 CapabilityFabric (fast, approximate)
        Stage 2: Exact cosine similarity for re-ranking (accurate)
        """
        # Check K0 top_k budget before query
        over_retrieve_k = top_k * 3

        if not self.qos_ctx.top_k_budget >= over_retrieve_k:
            # Reduce to available budget
            over_retrieve_k = self.qos_ctx.top_k_budget

        if over_retrieve_k < top_k:
            raise QoSBudgetExceededError(
                f"Insufficient top_k budget: need {top_k}, have {over_retrieve_k}"
            )

        # Stage 1: ANN search via K0 CapabilityFabric
        # This invokes P08 embedding management pipeline
        candidates = await self.fabric.invoke(
            capability="embedding.search",
            context={"pipeline_id": "p03_consolidation"},
            query_vector=query_embedding.tolist(),
            top_k=over_retrieve_k
        )

        # Consume K0 QoS budget
        self.qos_ctx.consume_top_k(len(candidates))

        # Stage 2: Exact re-ranking
        ranked = self._rerank_by_exact_cosine(query_embedding, candidates)

        return ranked[:top_k]

    def _rerank_by_exact_cosine(
        self,
        query: np.ndarray,
        candidates: List[dict]
    ) -> List[PatternMatch]:
        """Re-rank candidates using exact cosine similarity."""
        scored = []
        for c in candidates:
            vec = np.array(c['embedding'])
            score = np.dot(query, vec) / (np.linalg.norm(query) * np.linalg.norm(vec))
            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [PatternMatch(score=s, **c) for s, c in scored]
```

### 15.6 Memory Management (K0-Aware)

#### 15.6.1 Streaming with K0 Observability

```python
# Streaming with K0 metrics reporting

from k0.obs.metrics import MetricsExporter
from k0.obs.tracing import TracerFactory


class P03StreamingProcessor:
    """
    Streaming event processor with K0 observability.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.histogram(), MetricsExporter.gauge()
    - k0/obs/tracing.py: TracerFactory.span()
    """

    def __init__(
        self,
        metrics: MetricsExporter,
        tracer: TracerFactory
    ):
        self.metrics = metrics
        self.tracer = tracer

    async def process_events_streaming(
        self,
        events: AsyncIterator[HippEvent],
        batch_size: int = 100
    ) -> None:
        """Process events in streaming fashion with K0 metrics."""

        batch = []
        batch_count = 0

        async for event in events:
            batch.append(event)

            if len(batch) >= batch_size:
                # K0 trace span for batch processing
                with self.tracer.span(
                    name="p03.process_batch",
                    attributes={"batch_size": len(batch), "batch_num": batch_count}
                ):
                    await self._process_batch(batch)

                    # K0 metrics
                    self.metrics.histogram(
                        name="p03_batch_size",
                        value=len(batch),
                        labels={"phase": "streaming"}
                    )

                batch = []  # Release memory
                batch_count += 1

                # Report memory pressure to K0
                self.metrics.gauge(
                    name="p03_memory_mb",
                    value=self._get_process_memory_mb(),
                    labels={"stage": "streaming"}
                )

        if batch:
            await self._process_batch(batch)


# Memory thresholds with K0 alerts
P03_MEMORY_THRESHOLDS = {
    'warning_mb': 256,      # Log warning via K0 Logging
    'throttle_mb': 384,     # Reduce batch size
    'critical_mb': 480,     # Pause and GC
}
```

#### 15.6.2 Embedding Caching with K0 Metrics

```python
# LRU cache with K0 metrics reporting

from k0.obs.metrics import MetricsExporter


class P03EmbeddingCache:
    """
    LRU cache for embeddings with K0 metrics.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.counter() for hit/miss
    """

    max_size: int = 10000
    ttl_seconds: int = 3600

    def __init__(self, metrics: MetricsExporter):
        self.metrics = metrics
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: dict = {}

    async def get(self, key: str) -> Optional[np.ndarray]:
        """Get embedding from cache with K0 metrics."""
        if key in self._cache:
            # Check TTL
            if self._is_expired(key):
                del self._cache[key]
                del self._timestamps[key]
                self.metrics.counter(
                    name="p03_embedding_cache_expired",
                    labels={"cache": "embedding"}
                )
                return None

            # Hit - move to end for LRU
            self._cache.move_to_end(key)
            self.metrics.counter(
                name="p03_embedding_cache_hit",
                labels={"cache": "embedding"}
            )
            return self._cache[key]

        # Miss
        self.metrics.counter(
            name="p03_embedding_cache_miss",
            labels={"cache": "embedding"}
        )
        return None

    async def set(self, key: str, value: np.ndarray) -> None:
        """Set embedding in cache."""
        if len(self._cache) >= self.max_size:
            # Evict oldest (LRU)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            del self._timestamps[oldest_key]
            self.metrics.counter(
                name="p03_embedding_cache_eviction",
                labels={"cache": "embedding"}
            )

        self._cache[key] = value
        self._timestamps[key] = time.time()


# Cache priority levels
P03_CACHE_PRIORITIES = {
    'cluster_centroids': 'HIGH',      # Always cache
    'recent_patterns': 'MEDIUM',      # Cache for 1 hour
    'archived_patterns': 'LOW',       # Don't cache
}
```

### 15.7 Database Optimization (K0-Aware)

> **Updated 2025-12-24**: K0 now uses PostgreSQL 16+ via asyncpg. SQLite PRAGMAs and `INDEXED BY` hints no longer apply.

#### 15.7.1 Index Usage with K0 PostgreSQL Storage

```sql
-- PostgreSQL uses query planner automatically; no INDEXED BY hints needed.
-- Ensure proper indexes exist and statistics are current.
-- K0 Reference: k0/drivers/postgres.py, k0/db/pool.py

SELECT * FROM st_hipp_events
WHERE consolidation_status IS NULL
  AND tenant_id = $1
  AND space_id = $2
ORDER BY importance_score DESC
LIMIT 1000;

-- Ensure statistics are current (K0 migrations run ANALYZE automatically)
-- K0 Reference: k0/automation/migrate.py: apply_migrations()
ANALYZE st_hipp_events;
ANALYZE st_sem;
ANALYZE st_epi;

-- For query plan debugging (PostgreSQL-specific):
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM st_hipp_events
WHERE consolidation_status IS NULL
  AND tenant_id = $1 AND space_id = $2
ORDER BY importance_score DESC LIMIT 1000;
```

#### 15.7.2 PostgreSQL Configuration (K0 Kernel Config)

```python
# Integration with k0/config/postgres.py
# K0 Reference: k0/config/postgres.py: PostgresSettings
# K0 Reference: k0/db/pool.py: AsyncPgPool

from k0.config.postgres import PostgresSettings, get_postgres_settings


class P03DatabaseConfig:
    """
    Database configuration aligned with K0 PostgreSQL Settings.

    K0 References:
    - k0/config/postgres.py: PostgresSettings (host, port, pool sizes, SSL)
    - k0/db/pool.py: AsyncPgPool (asyncpg connection pool with pgbouncer support)
    - k0/drivers/postgres.py: PostgresDriver (ACID transactions)
    """

    @classmethod
    def from_k0_settings(cls, pg_settings: PostgresSettings) -> dict:
        """Build P03 PostgreSQL config from K0 PostgresSettings."""
        return {
            'min_pool_size': pg_settings.min_pool_size,        # Default: 5
            'max_pool_size': pg_settings.max_pool_size,        # Default: 25
            'command_timeout': pg_settings.command_timeout,    # Default: 60.0s
            'statement_cache_size': pg_settings.statement_cache_size,  # 0 for pgbouncer
            'vector_dimensions': pg_settings.vector_dimensions,  # 768 for UltraBERT
        }


# P03-optimized PostgreSQL session settings (SET at connection time)
P03_POSTGRES_SESSION_SETTINGS = {
    'statement_timeout': '300s',          # 5 min max for consolidation queries
    'lock_timeout': '30s',                # 30s max wait for row locks
    'idle_in_transaction_session_timeout': '60s',  # Prevent stuck transactions
    'work_mem': '256MB',                  # Per-operation memory for sorts/hashes
    'maintenance_work_mem': '512MB',      # For ANALYZE operations
}

# K0 PostgresSettings defaults (from k0/config/postgres.py)
# Environment prefix: K0_POSTGRES_
# - K0_POSTGRES_HOST (default: localhost)
# - K0_POSTGRES_PORT (default: 5432)
# - K0_POSTGRES_DATABASE (default: k0_kernel)
# - K0_POSTGRES_USER (default: k0user)
# - K0_POSTGRES_PASSWORD (from secrets)
# - K0_POSTGRES_MIN_POOL_SIZE (default: 5)
# - K0_POSTGRES_MAX_POOL_SIZE (default: 25)
# - K0_POSTGRES_SSL_MODE (default: prefer)
# - K0_POSTGRES_STATEMENT_CACHE_SIZE (default: 0 for pgbouncer)
```

### 15.8 K0 Metrics Export

```python
# P03 performance metrics exported via K0

from k0.obs.metrics import MetricsExporter


class P03PerformanceMetrics:
    """
    P03 performance metrics using K0 MetricsExporter.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.histogram(), counter(), gauge()
    - k0/obs/events.py: ObservabilityEmitter for detailed traces
    """

    def __init__(self, metrics: MetricsExporter):
        self.metrics = metrics

    def record_phase_duration(self, phase: str, duration_ms: float) -> None:
        """Record phase duration histogram."""
        self.metrics.histogram(
            name="p03_phase_duration_ms",
            value=duration_ms,
            labels={"phase": phase}
        )

    def record_batch_size(self, phase: str, size: int) -> None:
        """Record batch size histogram."""
        self.metrics.histogram(
            name="p03_batch_size",
            value=size,
            labels={"phase": phase}
        )

    def record_reconciliation_decision(self, decision_type: str) -> None:
        """Record reconciliation decision counter."""
        self.metrics.counter(
            name="p03_reconciliation_decisions",
            labels={"decision": decision_type}
        )

    def set_backlog_size(self, tenant_id: str, size: int) -> None:
        """Record current backlog gauge."""
        self.metrics.gauge(
            name="p03_backlog_size",
            value=size,
            labels={"tenant_id": tenant_id}
        )


# P03 SLO definitions (aligned with K0 QoS)
P03_SLO_TARGETS = {
    'cycle_duration_p99_ms': 300000,        # 5 minutes
    'batch_throughput_min': 100,            # events/second
    'memory_max_mb': 512,
    'error_rate_max': 0.01,                 # 1%
}
```

---

## 16. Configuration Reference

> **Status**: COMPLETE

### 16.1 K0 Configuration Integration Overview

```
+-------------------------------------------------------------------------------------+
|                    P03 CONFIGURATION - K0 INTEGRATION                               |
|                                                                                     |
|   +-----------------------------------------------------------------------------+   |
|   |                  K0 LAYER 10: Infrastructure & Configuration                |   |
|   |                                                                             |   |
|   |   +---------------------+    +---------------------+    +---------------+   |   |
|   |   |   Kernel Config     |    |   Pipeline Sched    |    |  Capability   |   |   |
|   |   | k0/kernel/config.py |    | k0/scheduler/sched  |    |    Fabric     |   |   |
|   |   |                     |    |                     |    | k0/fabric/    |   |   |
|   |   | TelemetrySettings   |    | register_pipeline() |    | invoke()      |   |   |
|   |   | QoSSettings         |    | fire_manual_trig()  |    | register()    |   |   |
|   |   | DatabaseSettings    |    | get_pipeline_stats()|    | resolve()     |   |   |
|   |   +----------+----------+    +----------+----------+    +-------+-------+   |   |
|   |              |                          |                       |           |   |
|   |              +-------------+------------+-----------------------+           |   |
|   |                            |                                                |   |
|   +----------------------------+------------------------------------------------+   |
|                                |                                                    |
|                                v                                                    |
|   +-----------------------------------------------------------------------------+   |
|   |                              P03 CONFIGURATION                              |   |
|   |                                                                             |   |
|   |   +---------------------------------------------------------------------+   |   |
|   |   |                    CONFIGURATION SOURCES                            |   |   |
|   |   |                                                                     |   |   |
|   |   |  1. k0/kernel/config.py → TelemetrySettings, QoSSettings            |   |   |
|   |   |  2. k0/scheduler/scheduler.py → PipelineScheduler trigger config    |   |   |
|   |   |  3. k0/fabric/fabric.py → CapabilityFabric handler registration     |   |   |
|   |   |  4. k0/runtime/module_registry.py → Module capability registration  |   |   |
|   |   |                                                                     |   |   |
|   |   +---------------------------------------------------------------------+   |   |
|   |                                                                             |   |
|   +-----------------------------------------------------------------------------+   |
|                                                                                     |
|   +-------------------------------------------------------------------------+       |
|   |                     K0 TRIGGER ENGINES                                  |       |
|   |                                                                         |       |
|   |   +-------------------+    +-------------------+    +---------------+   |       |
|   |   | IntervalTrigger   |    | ThresholdTrigger  |    | ManualTrigger |   |       |
|   |   | every N seconds   |    | when count >= N   |    | explicit call |   |       |
|   |   +-------------------+    +-------------------+    +---------------+   |       |
|   |                                                                         |       |
|   +-------------------------------------------------------------------------+       |
|                                                                                     |
+-------------------------------------------------------------------------------------+
```

### 16.2 K0 Kernel Configuration Integration

```python
# Integration with k0/kernel/config.py

from pydantic import BaseModel, Field
from k0.kernel.config import (
    TelemetrySettings,
    QoSSettings,
    DatabaseSettings,
    RetentionSettings,
    PolicySettings,
    BusSettings
)


class P03KernelSettings(BaseModel):
    """
    P03 settings derived from K0 Kernel Configuration.

    K0 References:
    - k0/kernel/config.py: TelemetrySettings, QoSSettings, DatabaseSettings
    - k0/kernel/dependencies.py: RequestDependencyProvider
    """

    # Inherited from K0 TelemetrySettings
    telemetry: TelemetrySettings

    # Inherited from K0 QoSSettings
    qos: QoSSettings

    # Inherited from K0 DatabaseSettings
    database: DatabaseSettings

    # Inherited from K0 RetentionSettings
    retention: RetentionSettings

    # Inherited from K0 PolicySettings
    policy: PolicySettings

    # Inherited from K0 BusSettings
    bus: BusSettings

    # P03-specific settings
    p03: 'P03SpecificSettings'


class P03SpecificSettings(BaseModel):
    """P03-specific configuration (extends K0 kernel config)."""

    # Scheduling (integrates with k0/scheduler/scheduler.py)
    schedule_enabled: bool = True
    schedule_cron: str = "0 3 * * *"           # 3 AM daily
    idle_trigger_minutes: int = 30

    # Batch settings (integrates with k0/qos/context.py budgets)
    batch_size: int = 1000
    max_events_per_cycle: int = 10000
    timeout_seconds: int = 300

    # Phase toggles
    r5_dream_enabled: bool = True
    r5_skip_on_backlog: bool = True
    r5_backlog_threshold: int = 5000

    # Concurrency (integrates with k0/qos/scheduler.py)
    lock_granularity: str = "space"            # global | tenant | space
    lock_ttl_seconds: int = 300
    parallel_workers: int = 4

    # Reconciliation thresholds
    reinforce_min: float = 0.85
    extend_min: float = 0.60
    extend_max: float = 0.85
    contradict_threshold: float = 0.30
    novelty_min: float = 0.70

    # Confidence settings
    confidence_boost_per_observation: float = 0.05
    confidence_decay_per_day: float = 0.001
    confidence_min_for_canonical: float = 0.50
```

### 16.3 K0 Pipeline Scheduler Configuration

```python
# Integration with k0/scheduler/scheduler.py and k0/scheduler/triggers.py

from k0.scheduler.scheduler import PipelineScheduler, ScheduledPipeline
from k0.scheduler.triggers import (
    TriggerEngine,
    IntervalTriggerEngine,
    ThresholdTriggerEngine,
    ManualTriggerEngine,
    TriggerEvent,
    create_trigger_engine
)
from k0.runtime.schemas import TriggerSpec, TriggerType


class P03SchedulerConfig:
    """
    P03 Pipeline Scheduler configuration.

    K0 References:
    - k0/scheduler/scheduler.py: PipelineScheduler.register_pipeline()
    - k0/scheduler/triggers.py: IntervalTriggerEngine, ThresholdTriggerEngine
    """

    @classmethod
    def build_trigger_specs(cls) -> list[TriggerSpec]:
        """
        Build K0 TriggerSpecs for P03 consolidation.

        Trigger Types (from k0/scheduler/triggers.py):
        - INTERVAL: Fire every N seconds
        - THRESHOLD: Fire when table count >= N
        - MANUAL: Fire via explicit API call
        """
        return [
            # Primary trigger: Daily schedule (via interval)
            TriggerSpec(
                trigger_type=TriggerType.INTERVAL,
                interval_seconds=86400,          # Daily
                description="Daily consolidation cycle"
            ),

            # Secondary trigger: Backlog threshold
            TriggerSpec(
                trigger_type=TriggerType.THRESHOLD,
                threshold_table="st_hipp_events",
                threshold_column="consolidation_status",
                threshold_condition="IS NULL",
                threshold_count=1000,            # Fire when 1000 unconsolidated
                description="Backlog threshold trigger"
            ),

            # Manual trigger: On-demand via k0ctl
            TriggerSpec(
                trigger_type=TriggerType.MANUAL,
                description="Manual consolidation trigger via k0ctl"
            ),
        ]

    @classmethod
    def register_with_k0(
        cls,
        scheduler: PipelineScheduler,
        pipeline_handler: callable
    ) -> ScheduledPipeline:
        """
        Register P03 with K0 PipelineScheduler.

        Uses k0/scheduler/scheduler.py: register_pipeline()
        """
        trigger_specs = cls.build_trigger_specs()

        return scheduler.register_pipeline(
            pipeline_id="p03_consolidation",
            handler=pipeline_handler,
            triggers=trigger_specs,
            concurrency=4,                       # Max parallel workers
            topics=["hipp.committed", "envelope.committed"],
        )


# P03 trigger configuration YAML (for k0 config files)
P03_TRIGGER_CONFIG = """
# K0 Scheduler trigger configuration for P03
# Reference: k0/scheduler/triggers.py

triggers:
  - type: interval
    interval_seconds: 86400              # Daily
    enabled: true
    description: "Daily consolidation cycle"

  - type: threshold
    table: st_hipp_events
    column: consolidation_status
    condition: "IS NULL"
    count: 1000
    enabled: true
    description: "Backlog threshold trigger"

  - type: manual
    enabled: true
    description: "Manual trigger via k0ctl pipeline fire p03_consolidation"
"""
```

### 16.4 K0 Capability Fabric Configuration

```python
# Integration with k0/fabric/fabric.py and k0/fabric/registry.py

from k0.fabric.fabric import CapabilityFabric, CapabilityRequest
from k0.fabric.registry import (
    CapabilityRegistry,
    RegisteredProvider,
    ResolutionStrategy
)
from k0.runtime.schemas import CapabilityProvider, ProviderType, FabricContextPolicy


class P03CapabilityConfig:
    """
    P03 Capability Fabric configuration.

    K0 References:
    - k0/fabric/fabric.py: CapabilityFabric.invoke(), register_handler()
    - k0/fabric/registry.py: CapabilityRegistry.register(), resolve()
    - k0/fabric/loader.py: load_capability_definitions()
    """

    # P03 capabilities that can be invoked by other pipelines
    PROVIDED_CAPABILITIES = [
        CapabilityProvider(
            capability="consolidation.reconcile",
            provider_type=ProviderType.PIPELINE,
            pipeline_id="p03_consolidation",
            handler="handle_reconciliation_request",
            context_policy=FabricContextPolicy.INHERIT,
            priority=100,
            description="Reconcile a single event against truth layers"
        ),
        CapabilityProvider(
            capability="consolidation.get_truth_state",
            provider_type=ProviderType.PIPELINE,
            pipeline_id="p03_consolidation",
            handler="handle_truth_state_query",
            context_policy=FabricContextPolicy.REQUIRE_TENANT,
            priority=100,
            description="Query current truth state for a space"
        ),
        CapabilityProvider(
            capability="consolidation.trigger_cycle",
            provider_type=ProviderType.PIPELINE,
            pipeline_id="p03_consolidation",
            handler="handle_manual_trigger",
            context_policy=FabricContextPolicy.REQUIRE_TENANT,
            priority=100,
            description="Manually trigger a consolidation cycle"
        ),
    ]

    # Capabilities P03 consumes from other pipelines
    CONSUMED_CAPABILITIES = [
        "embedding.search",              # From P08: Vector similarity search
        "embedding.encode",              # From P08: Generate embeddings
        "bus.dispatch",                  # From BusDispatcher: Emit events
        "storage.wal.append",            # From WAL: Write-ahead log
        "storage.outbox.enqueue",        # From Outbox: Enqueue for processing
    ]

    @classmethod
    def register_providers(cls, fabric: CapabilityFabric) -> None:
        """
        Register P03 capabilities with K0 CapabilityFabric.

        Uses k0/fabric/fabric.py: register_handler()
        """
        for provider in cls.PROVIDED_CAPABILITIES:
            fabric.register_handler(
                capability=provider.capability,
                handler=cls._get_handler(provider.handler),
                priority=provider.priority,
                context_policy=provider.context_policy
            )

    @classmethod
    def _get_handler(cls, handler_name: str) -> callable:
        """Resolve handler by name."""
        handlers = {
            "handle_reconciliation_request": P03Handlers.reconcile,
            "handle_truth_state_query": P03Handlers.get_truth_state,
            "handle_manual_trigger": P03Handlers.trigger_cycle,
        }
        return handlers[handler_name]


# P03 capability YAML (for k0/fabric/capabilities.yaml)
P03_CAPABILITY_CONFIG = """
# K0 Capability Fabric configuration for P03
# Reference: k0/fabric/loader.py

capabilities:
  # Provided by P03
  consolidation.reconcile:
    provider: p03_consolidation
    handler: handle_reconciliation_request
    context_policy: INHERIT
    timeout_ms: 30000
    retry_policy:
      max_attempts: 3
      backoff_ms: 1000

  consolidation.get_truth_state:
    provider: p03_consolidation
    handler: handle_truth_state_query
    context_policy: REQUIRE_TENANT
    timeout_ms: 5000

  consolidation.trigger_cycle:
    provider: p03_consolidation
    handler: handle_manual_trigger
    context_policy: REQUIRE_TENANT
    timeout_ms: 300000           # 5 minutes for full cycle
"""
```

### 16.5 K0 Module Registry Configuration

```python
# Integration with k0/runtime/module_registry.py

from k0.runtime.module_registry import (
    ModuleRegistry,
    ModuleContract,
    ModuleState
)


class P03ModuleConfig:
    """
    P03 Module Registry configuration.

    K0 References:
    - k0/runtime/module_registry.py: register_module(), register_capability()
    - k0/runtime/schemas.py: ModuleContract
    """

    MODULE_CONTRACT = ModuleContract(
        module_id="p03_consolidation",
        version="2.0.0",
        description="Memory consolidation pipeline (sleep-inspired)",

        # Dependencies on other K0 modules
        dependencies=[
            "k0.storage.wal",
            "k0.storage.outbox",
            "k0.qos.scheduler",
            "k0.bus.core",
            "k0.fabric.fabric",
            "k0.obs.metrics",
            "k0.obs.tracing",
            "p08_embedding",
        ],

        # Fabric capabilities provided
        fabric_callable=True,
        fabric_capabilities=[
            "consolidation.reconcile",
            "consolidation.get_truth_state",
            "consolidation.trigger_cycle",
        ],
        fabric_context_policy="REQUIRE_TENANT",

        # Topics consumed
        subscribed_topics=[
            "hipp.committed",
            "envelope.committed",
        ],

        # Topics emitted
        published_topics=[
            "consolidation.cycle.started",
            "consolidation.cycle.completed",
            "consolidation.truth.updated",
            "consolidation.gap.detected",
            "consolidation.error",
        ],

        # Storage tables owned
        owned_tables=[
            "st_epi",
            "st_sem",
            "st_proc",
            "st_ide",
            "st_aff",
            "st_soc",
            "st_int",
            "st_imp",
            "st_kg_dom",
            "st_kg_edges",
            "st_consolidation_cycles",
            "st_consolidation_audit",
            "st_learning_queue",
            "st_anchor_points",
        ],

        # Health check endpoint
        health_check_endpoint="/pipelines/p03/health",
    )

    @classmethod
    def register_with_k0(cls, registry: ModuleRegistry) -> None:
        """Register P03 module with K0 ModuleRegistry."""
        registry.register_module(cls.MODULE_CONTRACT)

        # Register capabilities
        for cap in cls.MODULE_CONTRACT.fabric_capabilities:
            registry.register_capability(
                capability=cap,
                module_id=cls.MODULE_CONTRACT.module_id
            )
```

### 16.6 Complete Configuration YAML

```yaml
# P03 Consolidation Pipeline Configuration
# Integrated with K0 Kernel Configuration

# =============================================================================
# K0 KERNEL SETTINGS (inherited)
# Reference: k0/kernel/config.py
# =============================================================================

telemetry:
  # K0 TelemetrySettings
  enabled: true
  otlp_endpoint: "http://localhost:4317"
  service_name: "familyos-k0"
  log_level: "INFO"

qos:
  # K0 QoSSettings
  max_concurrent_tokens: 20
  default_fanout_budget: 1000
  default_top_k_budget: 500
  port_limits:
    command: 10
    query: 15
    sse: 5

database:
  # K0 PostgresSettings (k0/config/postgres.py)
  # Environment prefix: K0_POSTGRES_
  use_postgresql: true                   # Feature flag (default: true after migration)
  postgres:
    host: "${K0_POSTGRES_HOST:-localhost}"
    port: ${K0_POSTGRES_PORT:-5432}
    database: "${K0_POSTGRES_DATABASE:-k0_kernel}"
    user: "${K0_POSTGRES_USER:-k0user}"
    password: "${K0_POSTGRES_PASSWORD}"  # From secrets/env
    min_pool_size: 5
    max_pool_size: 25
    ssl_mode: "prefer"                   # disable, allow, prefer, require, verify-ca, verify-full
    statement_cache_size: 0              # 0 for pgbouncer transaction mode
    command_timeout: 60.0                # Query timeout in seconds
    vector_dimensions: 768               # UltraBERT embedding dimensions

retention:
  # K0 RetentionSettings
  default_ttl_days: 365
  red_band_ttl_days: 30
  amber_band_ttl_days: 90
  green_band_ttl_days: 365
  archive_enabled: true

policy:
  # K0 PolicySettings
  manifest_path: "./contracts/policy/policy_manifest.yaml"
  pep_enabled: true
  acl_enabled: true
  location_privacy_enabled: true

bus:
  # K0 BusSettings
  max_queue_size: 10000
  dispatch_timeout_ms: 5000
  middleware_chain:
    - timestamp
    - latency_metrics
    - tracing

# =============================================================================
# P03-SPECIFIC SETTINGS
# =============================================================================

p03:
  # -----------------------------------------
  # Cycle Scheduling
  # Integrates with: k0/scheduler/scheduler.py
  # -----------------------------------------
  schedule:
    enabled: true
    cron: "0 3 * * *"                    # 3 AM daily
    idle_trigger_minutes: 30             # Also trigger after 30 min idle
    backlog_threshold_trigger: 1000      # Trigger if backlog exceeds

  # -----------------------------------------
  # Batch Settings
  # Integrates with: k0/qos/context.py
  # -----------------------------------------
  batch:
    size: 1000
    max_events_per_cycle: 10000
    timeout_seconds: 300
    adaptive_sizing: true                # Use K0 scheduler state

  # -----------------------------------------
  # Phase Configuration
  # -----------------------------------------
  phases:
    r0_harvest:
      enabled: true
      max_events: 1000
    r1_replay:
      enabled: true
      batch_size: 100
    r2_bridge:
      enabled: true
    r3_forget:
      enabled: true
      decay_threshold: 0.1
    r4_reconcile:
      enabled: true
    r5_dream:
      enabled: true
      skip_on_backlog: true
      backlog_threshold: 5000
    r6_anchor:
      enabled: true
    r7_integrate:
      enabled: true
    r8_gap_detect:
      enabled: true

  # -----------------------------------------
  # Reconciliation Thresholds
  # -----------------------------------------
  reconciliation:
    thresholds:
      reinforce_min: 0.85                # Min similarity for REINFORCE
      extend_min: 0.60                   # Min for EXTEND
      extend_max: 0.85                   # Max for EXTEND (above = REINFORCE)
      contradict_threshold: 0.30         # Below = potential CONTRADICT
      novelty_min: 0.70                  # Min novelty for CREATE

    confidence:
      boost_per_observation: 0.05
      decay_per_day: 0.001
      min_for_canonical: 0.50

  # -----------------------------------------
  # Active Learning (P06 Integration)
  # -----------------------------------------
  active_learning:
    gap_detection:
      enabled: true
      max_gaps_per_cycle: 50
      min_entropy_for_gap: 0.5

    anchor_decay:
      enabled: true
      decay_check_interval_days: 7
      stale_threshold_days: 90

    attention_budget:
      max_questions_per_day: 5
      token_refill_rate: 1.0             # Tokens per hour
      priority_bypass_threshold: 0.9

  # -----------------------------------------
  # Concurrency Control
  # Integrates with: k0/qos/scheduler.py
  # -----------------------------------------
  concurrency:
    lock_granularity: "space"            # global | tenant | space
    lock_ttl_seconds: 300
    parallel_workers: 4
    max_concurrent_cycles: 2

  # -----------------------------------------
  # Performance Settings
  # Integrates with: k0/obs/metrics.py
  # -----------------------------------------
  performance:
    memory:
      max_heap_mb: 512
      embedding_cache_size: 10000
      stream_batch_size: 100

    # PostgreSQL settings (via k0/config/postgres.py PostgresSettings)
    database:
      min_pool_size: 5                   # asyncpg pool minimum
      max_pool_size: 25                  # asyncpg pool maximum
      statement_cache_size: 0            # Required for pgbouncer
      command_timeout: 60.0              # Query timeout in seconds
      # Session-level tuning (applied per connection)
      work_mem: "64MB"                   # Per-query memory for sorts
      maintenance_work_mem: "128MB"      # For VACUUM/CREATE INDEX

    faiss:
      nprobe: 32                         # FAISS IVF search parameter
      efSearch: 128                      # HNSW search parameter
      rerank_factor: 3                   # Over-retrieve for re-ranking

  # -----------------------------------------
  # Error Handling
  # Integrates with: k0/storage/dlq.py
  # -----------------------------------------
  error_handling:
    retry:
      max_attempts: 3
      initial_backoff_ms: 1000
      max_backoff_ms: 60000
      backoff_multiplier: 2.0

    circuit_breaker:
      failure_threshold: 5
      reset_timeout_seconds: 60
      success_threshold: 3

    dlq:
      enabled: true
      retention_days: 7

  # -----------------------------------------
  # Observability
  # Integrates with: k0/obs/events.py, k0/obs/metrics.py
  # -----------------------------------------
  observability:
    metrics_prefix: "p03_"
    trace_sampling_rate: 0.1             # 10% of cycles
    audit_all_decisions: true
    emit_phase_boundaries: true
```

### 16.7 K0 CLI Commands (k0ctl)

```bash
# K0 CLI commands for P03 management
# Reference: k0/cli/k0ctl.py

# View P03 pipeline status
k0ctl pipeline status p03_consolidation

# Manually trigger consolidation cycle
k0ctl pipeline fire p03_consolidation --tenant-id <tenant> --space-id <space>

# View P03 scheduler stats
k0ctl scheduler stats p03_consolidation

# List P03 DLQ entries
k0ctl dlq list --pipeline p03_consolidation --status PENDING

# Requeue DLQ entry
k0ctl dlq requeue <dlq_id>

# View P03 metrics
k0ctl metrics query "p03_*"

# View P03 configuration
k0ctl config show p03

# Hot-reload P03 configuration
k0ctl config reload p03
```

### 16.8 Environment Variable Overrides

```python
# K0 environment variable overrides for P03
# Reference: k0/kernel/config.py uses Pydantic Settings

from pydantic_settings import BaseSettings


class P03EnvOverrides(BaseSettings):
    """
    Environment variables that override P03 configuration.
    Prefix: P03_

    K0 follows same pattern in k0/kernel/config.py
    """

    # Schedule overrides
    P03_SCHEDULE_ENABLED: bool = True
    P03_SCHEDULE_CRON: str = "0 3 * * *"

    # Batch overrides
    P03_BATCH_SIZE: int = 1000
    P03_MAX_EVENTS_PER_CYCLE: int = 10000
    P03_TIMEOUT_SECONDS: int = 300

    # Phase toggles
    P03_R5_DREAM_ENABLED: bool = True
    P03_R5_SKIP_ON_BACKLOG: bool = True
    P03_R5_BACKLOG_THRESHOLD: int = 5000

    # Performance overrides
    P03_MAX_HEAP_MB: int = 512
    P03_EMBEDDING_CACHE_SIZE: int = 10000

    # Feature flags
    P03_ACTIVE_LEARNING_ENABLED: bool = True
    P03_AUDIT_ALL_DECISIONS: bool = True

    class Config:
        env_prefix = "P03_"
        case_sensitive = False


# Example usage:
# export P03_BATCH_SIZE=500
# export P03_R5_DREAM_ENABLED=false
# export P03_MAX_HEAP_MB=256

---

## 17. Ops Readiness

> **Status**: COMPLETE — SLOs, dashboards, alerting, and runbooks defined.

### 17.1 Service Level Objectives (SLOs)

#### 17.1.1 Availability SLOs

| SLO ID | Metric | Target | Measurement Window |
|--------|--------|--------|-------------------|
| SLO-P03-001 | Consolidation cycle success rate | ≥ 99.5% | 7-day rolling |
| SLO-P03-002 | Event processing success rate | ≥ 99.9% | 24-hour rolling |
| SLO-P03-003 | Scheduled trigger reliability | ≥ 99.9% | 30-day rolling |

#### 17.1.2 Latency SLOs

| SLO ID | Metric | P50 | P95 | P99 |
|--------|--------|-----|-----|-----|
| SLO-P03-010 | Full cycle duration | ≤ 60s | ≤ 180s | ≤ 300s |
| SLO-P03-011 | R7 truth write latency | ≤ 50ms | ≤ 200ms | ≤ 500ms |
| SLO-P03-012 | R8 event emission latency | ≤ 10ms | ≤ 50ms | ≤ 100ms |

#### 17.1.3 Throughput SLOs

| SLO ID | Metric | Target | Burst Limit |
|--------|--------|--------|-------------|
| SLO-P03-020 | Events per hour (sustained) | ≥ 10,000 | 50,000 |
| SLO-P03-021 | Episodes per cycle | ≥ 50 (at 1000 events) | N/A |
| SLO-P03-022 | Gap detection rate | ≥ 95% of actual gaps | N/A |

#### 17.1.4 Error Budget

```yaml
# SLO error budget calculation
error_budget:
  window_days: 30
  target_availability: 0.995
  allowed_failure_minutes: 216  # 0.5% of 43,200 minutes
  current_burn_rate_alert:
    fast_burn: 14.4    # Burn 10% budget in 1 hour
    slow_burn: 6.0     # Burn 10% budget in 6 hours
```

---

### 17.2 Dashboard Specifications

#### 17.2.1 Grafana Dashboard: P03 Operations Overview

**Dashboard ID**: `p03-ops-overview`
**Refresh**: 30 seconds
**Time Range**: Last 24 hours

**Row 1: Health Summary**

| Panel | Type | Query |
|-------|------|-------|
| Cycle Success Rate (SLO-001) | Gauge | `sum(rate(p03_cycles_total{status="success"}[24h])) / sum(rate(p03_cycles_total[24h]))` |
| Events Pending | Stat | `p03_pending_events` |
| Last Cycle Timestamp | Stat | `p03_last_cycle_timestamp` |
| Active Errors | Stat | `sum(p03_errors_total{status="open"})` |

**Row 2: Cycle Performance**

| Panel | Type | Query |
|-------|------|-------|
| Cycle Duration | Histogram | `histogram_quantile(0.95, p03_cycle_duration_seconds_bucket)` |
| Events per Cycle | Timeseries | `rate(p03_events_processed_total[5m])` |
| Decision Distribution | Pie | `sum by (decision_type)(p03_events_processed_total)` |

**Row 3: Phase Breakdown**

| Panel | Type | Query |
|-------|------|-------|
| Phase Durations | Stacked Bar | `avg by (phase)(p03_phase_duration_seconds)` |
| Phase Errors | Heatmap | `sum by (phase, error_type)(p03_errors_total)` |
| R5 Skip Rate | Gauge | `sum(p03_r5_skipped_total) / sum(p03_cycles_total)` |

**Row 4: Output Metrics**

| Panel | Type | Query |
|-------|------|-------|
| Episodes Created | Counter | `sum(rate(p03_episodes_created_total[1h]))` |
| Patterns Discovered | Counter | `sum(rate(p03_patterns_discovered_total[1h]))` |
| KG Updates | Counter | `sum(rate(p03_kg_entities_total[1h])) + sum(rate(p03_kg_edges_total[1h]))` |
| Gaps Detected | Counter | `sum(rate(p03_gaps_detected_total[1h]))` |

**Row 5: DLQ & Errors**

| Panel | Type | Query |
|-------|------|-------|
| DLQ Depth | Timeseries | `p03_dlq_depth` |
| Error Rate by Type | Stacked Area | `sum by (error_type)(rate(p03_errors_total[5m]))` |
| Retry Success Rate | Gauge | `sum(p03_retry_success_total) / sum(p03_retry_attempts_total)` |

---

#### 17.2.2 Grafana Dashboard: P03 Deep Dive

**Dashboard ID**: `p03-deep-dive`

**Panels**:

- Similarity Score Distribution (histogram by decision_type)
- Confidence Score Distribution (histogram by layer)
- Cluster Size Distribution (R2 DBSCAN metrics)
- Prune Rate by Decay Factor
- Anchor Drift Detection Rate
- P08 Coordination Latency
- Circuit Breaker State

---

#### 17.2.3 Dashboard JSON Locations

| Dashboard | Path |
|-----------|------|
| P03 Operations Overview | `k0/obs/dashboards/p03_ops_overview.json` |
| P03 Deep Dive | `k0/obs/dashboards/p03_deep_dive.json` |
| P03 SLO Tracking | `k0/obs/dashboards/p03_slo_tracking.json` |
| P03 Error Analysis | `k0/obs/dashboards/p03_error_analysis.json` |

---

### 17.3 Alerting Rules

#### 17.3.1 Critical Alerts (Page On-Call)

| Alert Name | Condition | Severity | Runbook |
|------------|-----------|----------|---------|
| P03CycleFailureHigh | `rate(p03_cycles_total{status="failure"}[15m]) > 0.1` | CRITICAL | RB-P03-001 |
| P03TruthWriteFailure | `p03_r7_write_failures_total > 0` | CRITICAL | RB-P03-002 |
| P03DLQOverflow | `p03_dlq_depth > 1000` | CRITICAL | RB-P03-003 |
| P03CircuitBreakerOpen | `p03_circuit_breaker_state == 2` | CRITICAL | RB-P03-004 |
| P03SLOBurnRateFast | `p03_slo_burn_rate > 14.4` | CRITICAL | RB-P03-005 |

#### 17.3.2 Warning Alerts (Ticket)

| Alert Name | Condition | Severity | Runbook |
|------------|-----------|----------|---------|
| P03PendingEventBacklog | `p03_pending_events > 10000` | WARNING | RB-P03-010 |
| P03CycleLatencyHigh | `histogram_quantile(0.95, p03_cycle_duration_seconds_bucket) > 300` | WARNING | RB-P03-011 |
| P03GapQueueHigh | `p03_gap_queue_depth > 400` | WARNING | RB-P03-012 |
| P03R5SkipRateHigh | `rate(p03_r5_skipped_total[1h]) / rate(p03_cycles_total[1h]) > 0.5` | WARNING | RB-P03-013 |
| P03RetryRateHigh | `rate(p03_retry_attempts_total[1h]) > 100` | WARNING | RB-P03-014 |
| P03SLOBurnRateSlow | `p03_slo_burn_rate > 6.0` | WARNING | RB-P03-015 |

#### 17.3.3 Info Alerts (Log Only)

| Alert Name | Condition | Severity |
|------------|-----------|----------|
| P03DreamPhaseSkipped | `p03_r5_skipped_total increase` | INFO |
| P03NewGapTypeDetected | `new label in p03_gaps_detected_total` | INFO |
| P03SchemaEvolution | `p03_schema_evolution_total > 0` | INFO |

---

#### 17.3.4 Alert Rule Configuration

```yaml
# k0/obs/alerts/p03_alerts.yaml
groups:
  - name: p03_critical
    rules:
      - alert: P03CycleFailureHigh
        expr: rate(p03_cycles_total{status="failure"}[15m]) > 0.1
        for: 5m
        labels:
          severity: critical
          team: k0-platform
          runbook: RB-P03-001
        annotations:
          summary: "P03 consolidation cycle failure rate is high"
          description: "More than 10% of consolidation cycles are failing in the last 15 minutes"

      - alert: P03TruthWriteFailure
        expr: increase(p03_r7_write_failures_total[5m]) > 0
        for: 1m
        labels:
          severity: critical
          team: k0-platform
          runbook: RB-P03-002
        annotations:
          summary: "P03 truth write (R7) failure detected"
          description: "R7 truth write failures indicate data integrity risk"
```

---

### 17.4 Runbooks

#### 17.4.1 RB-P03-001: High Cycle Failure Rate

**Symptom**: `P03CycleFailureHigh` alert firing

**Triage Steps**:

1. Check `p03_errors_total` by `error_type` to identify failure category
2. Check `p03_phase_duration_seconds` to identify slow phase
3. Check K0 storage health: `k0ctl storage status`
4. Check K0 bus health: `k0ctl bus status`

**Common Causes**:

| Cause | Indicator | Resolution |
|-------|-----------|------------|
| Database overload | High R7 latency | Scale DB, reduce batch size |
| Memory pressure | OOM in logs | Increase heap, reduce concurrent cycles |
| Lock contention | R0 timeouts | Check lock service, stale locks |
| Bus unavailable | R8 failures | Restart bus, check kafka health |

**Immediate Actions**:

```bash
# Disable scheduled consolidation
k0ctl config set p03.schedule.enabled=false

# Check recent errors
k0ctl pipeline p03 logs --since=1h --level=error

# Manual retry with reduced batch
k0ctl pipeline p03 trigger --batch-size=100 --dry-run
```

**Escalation**: If not resolved in 15 minutes, escalate to K0 Platform team.

---

#### 17.4.2 RB-P03-002: R7 Truth Write Failure

**Symptom**: `P03TruthWriteFailure` alert firing

**Severity**: CRITICAL — Potential data integrity issue

**Triage Steps**:

1. **IMMEDIATELY** pause P03: `k0ctl pipeline p03 pause`
2. Check `st_outbox` for failed writes: `k0ctl storage query st_outbox --status=failed`
3. Identify affected records and tables
4. Check database transaction logs

**Common Causes**:

| Cause | Indicator | Resolution |
|-------|-----------|------------|
| Constraint violation | SQL error in logs | Check schema, data integrity |
| Optimistic lock failure | Version mismatch | Retry with refresh |
| Disk full | I/O errors | Expand storage, cleanup |
| Transaction timeout | Slow queries | Optimize queries, batch smaller |

**Recovery Procedure**:

```bash
# 1. Check outbox status
k0ctl storage outbox status

# 2. Replay failed writes (with idempotency protection)
k0ctl pipeline p03 replay --from-outbox --dry-run
k0ctl pipeline p03 replay --from-outbox

# 3. Verify data integrity
k0ctl pipeline p03 verify --tables=st_epi,st_sem,st_kg_dom

# 4. Resume pipeline
k0ctl pipeline p03 resume
```

**Escalation**: Immediate escalation to K0 Data team.

---

#### 17.4.3 RB-P03-003: DLQ Overflow

**Symptom**: `P03DLQOverflow` alert firing (DLQ depth > 1000)

**Triage Steps**:

1. Check DLQ composition: `k0ctl dlq list --pipeline=p03 --limit=100`
2. Identify dominant error types
3. Check if single bad batch is causing cascade

**Resolution by Error Type**:

| Error Type | Count Threshold | Action |
|------------|-----------------|--------|
| VALIDATION | > 100 | Schema mismatch — fix schema, reprocess |
| TRANSIENT | > 500 | Backend issue — fix backend, retry batch |
| LOGIC | Any | Bug — fix code, manual reprocess |
| FATAL | Any | System issue — escalate immediately |

**Commands**:

```bash
# Analyze DLQ
k0ctl dlq analyze --pipeline=p03

# Batch retry transient errors
k0ctl dlq retry --pipeline=p03 --error-type=TRANSIENT --batch-size=100

# Export for manual review
k0ctl dlq export --pipeline=p03 --error-type=LOGIC --format=json > dlq_logic.json
```

---

#### 17.4.4 RB-P03-004: Circuit Breaker Open

**Symptom**: `P03CircuitBreakerOpen` alert firing

**Meaning**: P08 coordination has failed repeatedly; P03 is no longer attempting P08 calls.

**Triage Steps**:

1. Check P08 pipeline health: `k0ctl pipeline p08 status`
2. Check circuit breaker metrics: `k0ctl metrics query p03_circuit_breaker_*`
3. Identify root cause of P08 failures

**Recovery**:

```bash
# Check circuit breaker state
k0ctl circuit-breaker status p03_p08_coordination

# If P08 is healthy, reset circuit breaker
k0ctl circuit-breaker reset p03_p08_coordination

# Monitor recovery
k0ctl circuit-breaker watch p03_p08_coordination
```

---

#### 17.4.5 RB-P03-010: Pending Event Backlog

**Symptom**: `P03PendingEventBacklog` alert firing (pending > 10,000)

**Triage Steps**:

1. Check consolidation schedule: `k0ctl pipeline p03 schedule status`
2. Check if consolidation is running: `k0ctl pipeline p03 status`
3. Check arrival rate vs processing rate

**Resolution**:

```bash
# Increase batch size temporarily
k0ctl config set p03.batch.size=2000 --temporary

# Trigger additional consolidation cycle
k0ctl pipeline p03 trigger --reason="backlog-reduction"

# If persistent, scale workers
k0ctl pipeline p03 scale --workers=8
```

---

#### 17.4.6 RB-P03-011: High Cycle Latency

**Symptom**: P95 cycle duration > 300 seconds

**Triage Steps**:

1. Check phase breakdown: `k0ctl metrics query p03_phase_duration_seconds`
2. Identify slowest phase
3. Check resource utilization during cycles

**Phase-Specific Optimizations**:

| Phase | Slow Indicator | Optimization |
|-------|----------------|--------------|
| R1 | > 60s | Reduce batch size, optimize importance scoring |
| R2 | > 120s | Tune DBSCAN parameters, increase parallel workers |
| R3 | > 60s | Optimize SimHash, reduce dedup scope |
| R4 | > 120s | Limit KG depth, batch NER calls |
| R5 | > 120s | Skip R5 (set `r5_execution_mode=disabled`) |
| R7 | > 60s | Batch writes, optimize indexes |

---

### 17.5 Runbook Index

| Runbook ID | Title | Severity | Trigger Alert |
|------------|-------|----------|---------------|
| RB-P03-001 | High Cycle Failure Rate | CRITICAL | P03CycleFailureHigh |
| RB-P03-002 | R7 Truth Write Failure | CRITICAL | P03TruthWriteFailure |
| RB-P03-003 | DLQ Overflow | CRITICAL | P03DLQOverflow |
| RB-P03-004 | Circuit Breaker Open | CRITICAL | P03CircuitBreakerOpen |
| RB-P03-005 | SLO Burn Rate Fast | CRITICAL | P03SLOBurnRateFast |
| RB-P03-010 | Pending Event Backlog | WARNING | P03PendingEventBacklog |
| RB-P03-011 | High Cycle Latency | WARNING | P03CycleLatencyHigh |
| RB-P03-012 | Gap Queue High | WARNING | P03GapQueueHigh |
| RB-P03-013 | R5 Skip Rate High | WARNING | P03R5SkipRateHigh |
| RB-P03-014 | Retry Rate High | WARNING | P03RetryRateHigh |
| RB-P03-015 | SLO Burn Rate Slow | WARNING | P03SLOBurnRateSlow |

---

### 17.6 On-Call Checklist

**Shift Start**:

- [ ] Review `p03-ops-overview` dashboard
- [ ] Check `p03_pending_events` gauge
- [ ] Verify last successful cycle timestamp
- [ ] Check DLQ depth

**During Incident**:

- [ ] Identify alert → Find corresponding runbook
- [ ] Execute triage steps
- [ ] Document actions in incident channel
- [ ] Escalate if not resolved in SLA time

**Shift End**:

- [ ] Update handoff notes with any ongoing issues
- [ ] Document any temporary config changes
- [ ] Verify no silent failures (check error logs)

---

## Appendix A: Scientific References (Full Bibliography)

| # | Reference | Year | Key Finding | P03 Application |
|---|-----------|------|-------------|-----------------|
| 1 | Wilson & McNaughton | 1994 | Hippocampal replay during sleep | R1 episodic replay |
| 2 | Stickgold & Walker | 2013 | Sleep-dependent memory consolidation | R0-R8 architecture |
| 3 | Tononi & Cirelli | 2006 | Synaptic homeostasis hypothesis | R3 forgetting |
| 4 | McClelland et al. | 1995 | Complementary learning systems | Hippocampus vs Neocortex |
| 5  | Marr | 1971 | Hippocampal index theory | Episode pointers |
| 6  | Born & Wilhelm | 2012 | Systems memory consolidation | R2 CA1 bridge |
| 7  | Nader et al. | 2000 | Memory reconsolidation | EXTEND/EVOLVE |
| 8  | McGaugh | 2004 | Emotional memory enhancement | Importance scoring |
| 9  | Schacter & Addis | 2007 | Constructive episodic simulation | R5 forward simulation |
| 10 | Mednick | 1962 | Remote associates | R5 insight generation |
| 11 | Settles | 2009 | Active Learning Survey | Gap detection strategy |
| 12 | Baker et al. | 2009 | Bayesian Theory of Mind | Anchor points |
| 13 | Schmidhuber | 2010 | Compression progress (curiosity) | Entropy scanning |
| 14 | Friston | 2010 | Free Energy Principle | Surprise minimization |
| 15 | Oudeyer & Kaplan | 2007 | Intrinsic motivation | Goldilocks principle |

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Anchor Point** | Bayesian belief about a user attribute (preferences, values), modeled as Beta distribution |
| **Concept Drift** | Change in underlying data distribution over time (e.g., user preferences shifting) |
| **Entropy Score** | Measure of uncertainty/randomness in a belief or edge; higher = more curious |
| **Gap Record** | A record in st_learning_queue representing missing/ambiguous information |
| **Reconciliation** | The process of comparing new signals against existing truth to determine action |
| **SimHash** | Locality-sensitive hash that produces similar fingerprints for similar text |
| **Tombstone** | Soft-deleted record kept for audit/recovery; eventually garbage collected |
| **Truth Layer** | One of the 8 long-term memory tables representing consolidated knowledge |
| **UltraBERT** | FamilyOS's custom 768-dim embedding model for semantic representation |

---

## Appendix C: Algorithm Specifications

> **Purpose**: This appendix provides detailed specifications for all algorithms used in P03 consolidation, grounded to FamilyOS components with explicit inputs, outputs, and behavior.

---

### C.1 Core Reconciliation Algorithms

*These algorithms run inside the **Reconciliation Engine** (Section 1.4) to decide how new signals modify existing memory.*

---

#### C.1.1 Cosine Similarity

**Purpose**: Determines if a new experience is a repetition of a known pattern or something genuinely new.

**FamilyOS Grounding**:

- **Module**: Reconciliation Engine (Section 1.4)
- **Phase**: R4 (Truth Reconciliation)
- **K0 Integration**: Invokes P08 via `CapabilityFabric.invoke("embedding.search")`

```

+-----------------------------------------------------------------------------------+
|                         COSINE SIMILARITY ALGORITHM                               |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   |                              INPUTS                                       |   |
|   |                                                                           |   |
|   |   1. query_embedding: np.ndarray[768]                                     |   |
|   |      - Source: st_vec.embedding WHERE event_id = <new_event_id>           |   |
|   |      - Generated by: P08 UltraBERT embedding pipeline                     |   |
|   |      - Format: 768-dimensional float32 vector (L2-normalized)             |   |
|   |                                                                           |   |
|   |   2. candidate_embeddings: List[np.ndarray[768]]                          |   |
|   |      - Source: st_sem.embedding_centroid WHERE pattern_type = <type>      |   |
|   |      - Filtered by: tenant_id, space_id, archival_status = 'ACTIVE'       |   |
|   |      - Retrieved via: FAISS index search (ANN) → exact re-ranking         |   |
|   |                                                                           |   |
|   |   3. thresholds: ReconciliationThresholds                                 |   |
|   |      - reinforce_min: 0.85 (from p03.reconciliation.thresholds)           |   |
|   |      - extend_min: 0.60                                                   |   |
|   |      - extend_max: 0.85                                                   |   |
|   |      - contradict_threshold: 0.30                                         |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                            ALGORITHM                                      |   |
|   |                                                                           |   |
|   |   def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:           |   |
|   |       """                                                                 |   |
|   |       Compute cosine similarity between two vectors.                      |   |
|   |                                                                           |   |
|   |       Formula: cos(θ) = (A · B) / (||A|| *||B||)                         |   |
|   |                                                                           |   |
|   |       For L2-normalized vectors: cos(θ) = A · B (dot product)             |   |
|   |       """                                                                 |   |
|   |       # Vectors are pre-normalized by P08, so just dot product            |   |
|   |       return float(np.dot(a, b))                                          |   |
|   |                                                                           |   |
|   |   def find_best_match(                                                    |   |
|   |       query: np.ndarray,                                                  |   |
|   |       candidates: List[Tuple[str, np.ndarray]],  # (truth_id, embedding)  |   |
|   |       thresholds: ReconciliationThresholds                                |   |
|   |   ) -> ReconciliationDecision:                                            |   |
|   |       """                                                                 |   |
|   |       Find best matching truth record and determine action.               |   |
|   |       """                                                                 |   |
|   |       if not candidates:                                                  |   |
|   |           return ReconciliationDecision(                                  |   |
|   |               action=ReconciliationAction.CREATE,                         |   |
|   |               best_match_id=None,                                         |   |
|   |               similarity_score=0.0,                                       |   |
|   |               confidence=1.0  # High confidence it's new                  |   |
|   |           )                                                               |   |
|   |                                                                           |   |
|   |       # Compute similarities                                              |   |
|   |       scored = [                                                          |   |
|   |           (truth_id, cosine_similarity(query, emb))                       |   |
|   |           for truth_id, emb in candidates                                 |   |
|   |       ]                                                                   |   |
|   |       scored.sort(key=lambda x: x[1], reverse=True)                       |   |
|   |                                                                           |   |
|   |       best_id, best_score = scored[0]                                     |   |
|   |                                                                           |   |
|   |       # Determine action based on thresholds                              |   |
|   |       if best_score >= thresholds.reinforce_min:                          |   |
|   |           action = ReconciliationAction.REINFORCE                         |   |
|   |       elif best_score >= thresholds.extend_min:                           |   |
|   |           action = ReconciliationAction.EXTEND                            |   |
|   |       elif best_score < thresholds.contradict_threshold:                  |   |
|   |           action = ReconciliationAction.CONTRADICT                        |   |
|   |       else:                                                               |   |
|   |           action = ReconciliationAction.CREATE                            |   |
|   |                                                                           |   |
|   |       return ReconciliationDecision(                                      |   |
|   |           action=action,                                                  |   |
|   |           best_match_id=best_id,                                          |   |
|   |           similarity_score=best_score,                                    |   |
|   |           confidence=abs(best_score - 0.5)* 2  # Confidence in decision  |   |
|   |       )                                                                   |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                              OUTPUTS                                      |   |
|   |                                                                           |   |
|   |   ReconciliationDecision:                                                 |   |
|   |     - action: ReconciliationAction                                        |   |
|   |         REINFORCE: score >= 0.85 → Update observation_count, confidence   |   |
|   |         EXTEND:    0.60 <= score < 0.85 → Add attributes, expand pattern  |   |
|   |         CONTRADICT: score < 0.30 → Flag conflict, may create alternative  |   |
|   |         CREATE:    No good match → Insert new st_sem record               |   |
|   |                                                                           |   |
|   |     - best_match_id: Optional[str]                                        |   |
|   |         The sem_id of the matching st_sem record (None if CREATE)         |   |
|   |                                                                           |   |
|   |     - similarity_score: float [0.0, 1.0]                                  |   |
|   |         Cosine similarity value for audit/logging                         |   |
|   |                                                                           |   |
|   |     - confidence: float [0.0, 1.0]                                        |   |
|   |         Confidence in the decision (higher = more certain)                |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                                                                   |
|   STORAGE EFFECTS:                                                                |
|   +-----------------------------------------------------------------------+       |
|   | Action     | st_sem Effect                  | st_kg_edges Effect     |       |
|   |------------|--------------------------------|------------------------|       |
|   | REINFORCE  | observation_count++            | edge weights++         |       |
|   |            | confidence_score = f(obs)      |                        |       |
|   |            | last_observed_at = now()       |                        |       |
|   |------------|--------------------------------|------------------------|       |
|   | EXTEND     | pattern_attributes += new      | new edges created      |       |
|   |            | embedding_centroid = weighted  |                        |       |
|   |------------|--------------------------------|------------------------|       |
|   | CONTRADICT | Insert conflicting_pattern_ids | contradiction edges    |       |
|   |------------|--------------------------------|------------------------|       |
|   | CREATE     | INSERT new st_sem record       | new entity nodes       |       |
|   +-----------------------------------------------------------------------+       |
|                                                                                   |
+-----------------------------------------------------------------------------------+

```

**Complexity**: O(n * d) where n = number of candidates, d = embedding dimension (768)

**K0 QoS Integration**:

- Consumes `top_k_budget` from `QoSContext` for FAISS search
- Reports `p03_similarity_score` histogram to `MetricsExporter`

---

#### C.1.2 Bayesian Confidence Updating

**Purpose**: Mathematically models "trust" in a memory. Repeated observations increase confidence; inconsistency lowers it.

**FamilyOS Grounding**:

- **Module**: Confidence Engine (within Reconciliation Engine)
- **Phase**: R4 (applied after each reconciliation decision)
- **Tables**: `st_sem.confidence_score`, `st_kg_edges.weight`, `st_epi.significance_score`

```

+-----------------------------------------------------------------------------------+
|                      BAYESIAN CONFIDENCE UPDATING                                 |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   |                              INPUTS                                       |   |
|   |                                                                           |   |
|   |   1. current_record: TruthRecord                                          |   |
|   |      - confidence_score: float [0.0, 1.0]                                 |   |
|   |      - observation_count: int (number of times pattern observed)          |   |
|   |      - consistency_score: float [0.0, 1.0] (how consistent observations)  |   |
|   |      - significance_score: float [0.0, 1.0] (emotional/importance weight) |   |
|   |      - last_observed_at: timestamp                                        |   |
|   |                                                                           |   |
|   |   2. new_observation: ObservationEvent                                    |   |
|   |      - similarity_to_existing: float (from cosine similarity)             |   |
|   |      - affect_valence: float [-1.0, 1.0] (emotional intensity)            |   |
|   |      - source_reliability: float [0.0, 1.0] (trust in data source)        |   |
|   |                                                                           |   |
|   |   3. config: ConfidenceConfig (from p03.reconciliation.confidence)        |   |
|   |      - boost_per_observation: 0.05                                        |   |
|   |      - decay_per_day: 0.001                                               |   |
|   |      - min_for_canonical: 0.50                                            |   |
|   |      - consistency_weight: 0.4                                            |   |
|   |      - frequency_weight: 0.3                                              |   |
|   |      - significance_weight: 0.3                                           |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                            ALGORITHM                                      |   |
|   |                                                                           |   |
|   |   class BayesianConfidenceUpdater:                                        |   |
|   |       """                                                                 |   |
|   |       Updates confidence scores using Bayesian principles.                |   |
|   |                                                                           |   |
|   |       Core Formula:                                                       |   |
|   |         confidence = sqrt(frequency *consistency* significance)         |   |
|   |                                                                           |   |
|   |       This is a geometric mean that ensures all three factors             |   |
|   |       must be reasonably high for confidence to be high.                  |   |
|   |       """                                                                 |   |
|   |                                                                           |   |
|   |       def compute_frequency_factor(                                       |   |
|   |           self,                                                           |   |
|   |           observation_count: int,                                         |   |
|   |           days_observed: int                                              |   |
|   |       ) -> float:                                                         |   |
|   |           """                                                             |   |
|   |           Frequency factor: How often is this pattern observed?           |   |
|   |                                                                           |   |
|   |           Uses logarithmic scaling to prevent runaway confidence          |   |
|   |           from very frequent events.                                      |   |
|   |                                                                           |   |
|   |           Formula: log(1 + obs_count) / log(1 + expected_count)           |   |
|   |           """                                                             |   |
|   |           expected_count = max(1, days_observed *0.5)  # Expect ~0.5/day |   |
|   |           raw = math.log(1 + observation_count) / math.log(1 + expected)  |   |
|   |           return min(1.0, raw)  # Cap at 1.0                              |   |
|   |                                                                           |   |
|   |       def compute_consistency_factor(                                     |   |
|   |           self,                                                           |   |
|   |           observations: List[float]  # Similarity scores over time        |   |
|   |       ) -> float:                                                         |   |
|   |           """                                                             |   |
|   |           Consistency factor: How similar are observations to each other? |   |
|   |                                                                           |   |
|   |           Low variance = high consistency = high trust                    |   |
|   |           High variance = inconsistent = lower trust                      |   |
|   |                                                                           |   |
|   |           Formula: 1.0 - normalized_std_dev(observations)                 |   |
|   |           """                                                             |   |
|   |           if len(observations) < 2:                                       |   |
|   |               return 0.5  # Neutral for single observation                |   |
|   |                                                                           |   |
|   |           std_dev = np.std(observations)                                  |   |
|   |           # Normalize: std_dev of 0.3 → consistency of 0.7                |   |
|   |           return max(0.0, 1.0 - std_dev)                                  |   |
|   |                                                                           |   |
|   |       def compute_significance_factor(                                    |   |
|   |           self,                                                           |   |
|   |           affect_valence: float,                                          |   |
|   |           importance_score: float                                         |   |
|   |       ) -> float:                                                         |   |
|   |           """                                                             |   |
|   |           Significance factor: How emotionally/practically important?     |   |
|   |                                                                           |   |
|   |           High emotion or high importance = memory sticks better          |   |
|   |           (McGaugh 2004: Emotional memory enhancement)                    |   |
|   |                                                                           |   |
|   |           Formula: 0.5 + 0.5* max(|affect|, importance)                  |   |
|   |           """                                                             |   |
|   |           emotional_intensity = abs(affect_valence)                       |   |
|   |           return 0.5 + 0.5 *max(emotional_intensity, importance_score)   |   |
|   |                                                                           |   |
|   |       def update_confidence(                                              |   |
|   |           self,                                                           |   |
|   |           record: TruthRecord,                                            |   |
|   |           new_observation: ObservationEvent,                              |   |
|   |           config: ConfidenceConfig                                        |   |
|   |       ) -> float:                                                         |   |
|   |           """                                                             |   |
|   |           Main update function.                                           |   |
|   |                                                                           |   |
|   |           Returns new confidence score.                                   |   |
|   |           """                                                             |   |
|   |           # Update observation count                                      |   |
|   |           new_obs_count = record.observation_count + 1                    |   |
|   |                                                                           |   |
|   |           # Compute factors                                               |   |
|   |           frequency = self.compute_frequency_factor(                      |   |
|   |               new_obs_count,                                              |   |
|   |               record.days_since_first_observed()                          |   |
|   |           )                                                               |   |
|   |                                                                           |   |
|   |           # Update consistency with new observation                       |   |
|   |           observations = record.observation_similarities + [              |   |
|   |               new_observation.similarity_to_existing                      |   |
|   |           ]                                                               |   |
|   |           consistency = self.compute_consistency_factor(observations)     |   |
|   |                                                                           |   |
|   |           significance = self.compute_significance_factor(                |   |
|   |               new_observation.affect_valence,                             |   |
|   |               record.significance_score                                   |   |
|   |           )                                                               |   |
|   |                                                                           |   |
|   |           # Geometric mean (the core formula)                             |   |
|   |           confidence = math.sqrt(frequency* consistency *significance)  |   |
|   |                                                                           |   |
|   |           # Apply source reliability adjustment                           |   |
|   |           confidence*= new_observation.source_reliability                |   |
|   |                                                                           |   |
|   |           return min(1.0, max(0.0, confidence))                           |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                              OUTPUTS                                      |   |
|   |                                                                           |   |
|   |   ConfidenceUpdate:                                                       |   |
|   |     - new_confidence_score: float [0.0, 1.0]                              |   |
|   |         Updated confidence for st_sem.confidence_score                    |   |
|   |                                                                           |   |
|   |     - frequency_factor: float [0.0, 1.0]                                  |   |
|   |         For audit: how much frequency contributed                         |   |
|   |                                                                           |   |
|   |     - consistency_factor: float [0.0, 1.0]                                |   |
|   |         For audit: how much consistency contributed                       |   |
|   |                                                                           |   |
|   |     - significance_factor: float [0.0, 1.0]                               |   |
|   |         For audit: how much significance contributed                      |   |
|   |                                                                           |   |
|   |     - is_canonical: bool                                                  |   |
|   |         True if confidence >= min_for_canonical (0.50)                    |   |
|   |         Determines if this is the "authoritative" version                 |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                                                                   |
|   CONFIDENCE THRESHOLDS AND EFFECTS:                                              |
|   +-----------------------------------------------------------------------+       |
|   | Confidence Range | Interpretation        | System Behavior            |       |
|   |------------------|-----------------------|----------------------------|       |
|   | 0.90 - 1.00      | Very High Confidence  | Use without verification   |       |
|   | 0.70 - 0.89      | High Confidence       | Use, may verify edge cases |       |
|   | 0.50 - 0.69      | Medium Confidence     | Use with caution           |       |
|   | 0.30 - 0.49      | Low Confidence        | Candidate for P06 question |       |
|   | 0.00 - 0.29      | Very Low Confidence   | Do not use, queue for P06  |       |
|   +-----------------------------------------------------------------------+       |
|                                                                                   |
+-----------------------------------------------------------------------------------+

```

**Scientific Basis**: Bayesian updating (Bayes 1763), Emotional Memory Enhancement (McGaugh 2004)

---

#### C.1.3 Optimistic Locking (Version-Based Concurrency)

**Purpose**: Ensures data integrity when multiple consolidation workers try to update the same memory record simultaneously.

**FamilyOS Grounding**:

- **Module**: K0 UnitOfWork (`k0/uow/unit_of_work.py`)
- **Phase**: All phases that write to truth tables
- **Tables**: All `st_*` truth tables have a `version` column

```

+-----------------------------------------------------------------------------------+
|                         OPTIMISTIC LOCKING ALGORITHM                              |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   |                              INPUTS                                       |   |
|   |                                                                           |   |
|   |   1. record_id: str                                                       |   |
|   |      - Primary key of the record being updated (e.g., sem_id, epi_id)     |   |
|   |                                                                           |   |
|   |   2. expected_version: int                                                |   |
|   |      - The version number read when the record was fetched                |   |
|   |      - Source: st_sem.version, st_epi.version, etc.                       |   |
|   |                                                                           |   |
|   |   3. updates: Dict[str, Any]                                              |   |
|   |      - The fields to update and their new values                          |   |
|   |      - Example: {"confidence_score": 0.87, "observation_count": 15}       |   |
|   |                                                                           |   |
|   |   4. table_name: str                                                      |   |
|   |      - Target table (st_sem, st_epi, st_kg_edges, etc.)                   |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                            ALGORITHM                                      |   |
|   |                                                                           |   |
|   |   class OptimisticLockingUpdater:                                         |   |
|   |       """                                                                 |   |
|   |       Implements optimistic locking for concurrent updates.               |   |
|   |                                                                           |   |
|   |       K0 Integration:                                                     |   |
|   |       - Uses k0/uow/unit_of_work.py for transaction management            |   |
|   |       - Integrates with k0/storage/dlq.py for retry on conflict           |   |
|   |       """                                                                 |   |
|   |                                                                           |   |
|   |       MAX_RETRY_ATTEMPTS = 3                                              |   |
|   |       RETRY_BACKOFF_MS = [100, 500, 2000]                                 |   |
|   |                                                                           |   |
|   |       async def update_with_lock(                                         |   |
|   |           self,                                                           |   |
|   |           uow: UnitOfWork,                                                |   |
|   |           table_name: str,                                                |   |
|   |           record_id: str,                                                 |   |
|   |           expected_version: int,                                          |   |
|   |           updates: Dict[str, Any]                                         |   |
|   |       ) -> UpdateResult:                                                  |   |
|   |           """                                                             |   |
|   |           Attempt atomic update with version check.                       |   |
|   |                                                                           |   |
|   |           SQL Pattern:                                                    |   |
|   |             UPDATE {table}                                                |   |
|   |             SET field1 = :val1, field2 = :val2, version = version + 1     |   |
|   |             WHERE id = :id AND version = :expected_version                |   |
|   |                                                                           |   |
|   |           If rows_affected == 0, another worker updated first.            |   |
|   |           """                                                             |   |
|   |           # Build SET clause                                              |   |
|   |           set_clauses = [f"{k} = :{k}" for k in updates.keys()]           |   |
|   |           set_clauses.append("version = version + 1")                     |   |
|   |           set_clauses.append("updated_at = :now")                         |   |
|   |                                                                           |   |
|   |           sql = f"""                                                      |   |
|   |               UPDATE {table_name}                                         |   |
|   |               SET {', '.join(set_clauses)}                                |   |
|   |               WHERE {self._pk_column(table_name)} = :record_id            |   |
|   |                 AND version = :expected_version                           |   |
|   |           """                                                             |   |
|   |                                                                           |   |
|   |           params = {                                                      |   |
|   |               **updates,                                                  |   |
|   |               'record_id': record_id,                                     |   |
|   |               'expected_version': expected_version,                       |   |
|   |               'now': now_ms()                                             |   |
|   |           }                                                               |   |
|   |                                                                           |   |
|   |           result = await uow.execute(sql, params)                         |   |
|   |                                                                           |   |
|   |           if result.rowcount == 0:                                        |   |
|   |               raise VersionConflictError(                                 |   |
|   |                   f"Version conflict on {table_name}.{record_id}: "       |   |
|   |                   f"expected v{expected_version}, record was modified"    |   |
|   |               )                                                           |   |
|   |                                                                           |   |
|   |           return UpdateResult(                                            |   |
|   |               success=True,                                               |   |
|   |               new_version=expected_version + 1,                           |   |
|   |               rows_affected=result.rowcount                               |   |
|   |           )                                                               |   |
|   |                                                                           |   |
|   |       async def update_with_retry(                                        |   |
|   |           self,                                                           |   |
|   |           uow_factory: Callable[[], UnitOfWork],                          |   |
|   |           table_name: str,                                                |   |
|   |           record_id: str,                                                 |   |
|   |           update_fn: Callable[[TruthRecord], Dict[str, Any]]              |   |
|   |       ) -> UpdateResult:                                                  |   |
|   |           """                                                             |   |
|   |           Retry loop for handling version conflicts.                      |   |
|   |                                                                           |   |
|   |           Strategy:                                                       |   |
|   |           1. Read current record (with version)                           |   |
|   |           2. Compute updates using update_fn                              |   |
|   |           3. Attempt update with version check                            |   |
|   |           4. If conflict, re-read and retry (up to MAX_RETRY_ATTEMPTS)    |   |
|   |           """                                                             |   |
|   |           for attempt in range(self.MAX_RETRY_ATTEMPTS):                  |   |
|   |               async with uow_factory() as uow:                            |   |
|   |                   # Read current state                                    |   |
|   |                   record = await self._fetch_record(                      |   |
|   |                       uow, table_name, record_id                          |   |
|   |                   )                                                       |   |
|   |                                                                           |   |
|   |                   # Compute updates based on current state                |   |
|   |                   updates = update_fn(record)                             |   |
|   |                                                                           |   |
|   |                   try:                                                    |   |
|   |                       result = await self.update_with_lock(               |   |
|   |                           uow, table_name, record_id,                     |   |
|   |                           record.version, updates                         |   |
|   |                       )                                                   |   |
|   |                       await uow.commit()                                  |   |
|   |                       return result                                       |   |
|   |                                                                           |   |
|   |                   except VersionConflictError:                            |   |
|   |                       if attempt < self.MAX_RETRY_ATTEMPTS - 1:           |   |
|   |                           await asyncio.sleep(                            |   |
|   |                               self.RETRY_BACKOFF_MS[attempt] / 1000       |   |
|   |                           )                                               |   |
|   |                           continue  # Retry                               |   |
|   |                       raise  # Max retries exceeded                       |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                              OUTPUTS                                      |   |
|   |                                                                           |   |
|   |   UpdateResult:                                                           |   |
|   |     - success: bool                                                       |   |
|   |         True if update succeeded                                          |   |
|   |                                                                           |   |
|   |     - new_version: int                                                    |   |
|   |         The new version number after update                               |   |
|   |                                                                           |   |
|   |     - rows_affected: int                                                  |   |
|   |         Number of rows updated (should be 1)                              |   |
|   |                                                                           |   |
|   |   OR                                                                      |   |
|   |                                                                           |   |
|   |   VersionConflictError:                                                   |   |
|   |     - Raised if update fails after MAX_RETRY_ATTEMPTS                     |   |
|   |     - Caught by P03ErrorHandler, logged to st_dlq                         |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                                                                   |
|   CONFLICT RESOLUTION STRATEGIES:                                                 |
|   +-----------------------------------------------------------------------+       |
|   | Conflict Type       | Resolution Strategy                             |       |
|   |---------------------|-----------------------------------------------|       |
|   | Confidence Update   | Re-read, recompute with merged observations   |       |
|   | Observation Count   | Re-read, add delta (commutative)              |       |
|   | Embedding Centroid  | Re-read, weighted average with both updates   |       |
|   | Pattern Attributes  | Merge JSON, union of keys                     |       |
|   +-----------------------------------------------------------------------+       |
|                                                                                   |
+-----------------------------------------------------------------------------------+

```

**K0 Integration**:

- Transaction management via `k0/uow/unit_of_work.py`
- Conflict errors logged to `k0/storage/dlq.py`
- Metrics via `k0/obs/metrics.py`: `p03_version_conflicts_total`

---

### C.2 R1: Hippocampal Replay Algorithms (M23)

*Used to select which recent events matter enough to be saved.*

---

#### C.2.1 Importance Scoring (Weighted Sum)

**Purpose**: Implements "Emotional Tagging." Prioritizes processing of high-emotion or high-novelty events over mundane background noise.

**FamilyOS Grounding**:

- **Module**: M23 Hippocampal Replay
- **Phase**: R1 (Harvest/Filter)
- **Tables**: Reads `st_hipp_events`, outputs to batch selection

```

+-----------------------------------------------------------------------------------+
|                        IMPORTANCE SCORING ALGORITHM                               |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   |                              INPUTS                                       |   |
|   |                                                                           |   |
|   |   1. event: HippEvent (from st_hipp_events)                               |   |
|   |      - sentiment_score: float [-1.0, 1.0]                                 |   |
|   |          Emotional polarity from NLP analysis (P02)                       |   |
|   |          Negative = sad/angry, Positive = happy/excited                   |   |
|   |                                                                           |   |
|   |      - affect_valence: float [-1.0, 1.0]                                  |   |
|   |          Emotional intensity from behavioral signals                      |   |
|   |          Source: heart rate, voice tone, user feedback                    |   |
|   |                                                                           |   |
|   |      - novelty_score: float [0.0, 1.0]                                    |   |
|   |          How unique is this event? (computed by R3 SimHash)               |   |
|   |          1.0 = completely novel, 0.0 = exact duplicate                    |   |
|   |                                                                           |   |
|   |      - participant_count: int                                             |   |
|   |          Number of actors involved in this event                          |   |
|   |          Social events weighted higher                                    |   |
|   |                                                                           |   |
|   |      - event_type: str                                                    |   |
|   |          Type of event (message, photo, location, etc.)                   |   |
|   |                                                                           |   |
|   |   2. weights: ImportanceWeights (configurable)                            |   |
|   |      - sentiment_weight: 0.25                                             |   |
|   |      - affect_weight: 0.30                                                |   |
|   |      - novelty_weight: 0.25                                               |   |
|   |      - social_weight: 0.20                                                |   |
|   |                                                                           |   |
|   |   3. event_type_multipliers: Dict[str, float]                             |   |
|   |      - "message": 1.0                                                     |   |
|   |      - "photo": 1.2 (visual memories weighted higher)                     |   |
|   |      - "milestone": 2.0 (birthdays, anniversaries)                        |   |
|   |      - "routine": 0.5 (daily repeated events)                             |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                            ALGORITHM                                      |   |
|   |                                                                           |   |
|   |   class ImportanceScorer:                                                 |   |
|   |       """                                                                 |   |
|   |       Computes importance score for hippocampal event selection.          |   |
|   |                                                                           |   |
|   |       Scientific Basis: McGaugh (2004) - Emotional memories are           |   |
|   |       more strongly encoded due to amygdala-hippocampus interaction.      |   |
|   |       """                                                                 |   |
|   |                                                                           |   |
|   |       def compute_emotional_intensity(self, event: HippEvent) -> float:   |   |
|   |           """                                                             |   |
|   |           Combine sentiment and affect into emotional intensity.          |   |
|   |                                                                           |   |
|   |           We use absolute values because both strong positive AND         |   |
|   |           strong negative emotions enhance memory encoding.               |   |
|   |           """                                                             |   |
|   |           sentiment_intensity = abs(event.sentiment_score)                |   |
|   |           affect_intensity = abs(event.affect_valence)                    |   |
|   |                                                                           |   |
|   |           # Weighted combination                                          |   |
|   |           return (                                                        |   |
|   |               sentiment_intensity *self.weights.sentiment_weight +       |   |
|   |               affect_intensity* self.weights.affect_weight               |   |
|   |           )                                                               |   |
|   |                                                                           |   |
|   |       def compute_social_factor(self, event: HippEvent) -> float:         |   |
|   |           """                                                             |   |
|   |           Social events are more memorable.                               |   |
|   |                                                                           |   |
|   |           Uses logarithmic scaling to prevent large groups from           |   |
|   |           completely dominating.                                          |   |
|   |           """                                                             |   |
|   |           if event.participant_count <= 1:                                |   |
|   |               return 0.0  # Solo event, no social bonus                   |   |
|   |                                                                           |   |
|   |           # Log scale: 2 people = 0.30, 5 people = 0.70, 10+ = 1.0        |   |
|   |           return min(1.0, math.log2(event.participant_count) / 3.32)      |   |
|   |                                                                           |   |
|   |       def compute_importance_score(self, event: HippEvent) -> float:      |   |
|   |           """                                                             |   |
|   |           Main scoring function.                                          |   |
|   |                                                                           |   |
|   |           Formula:                                                        |   |
|   |             importance = (                                                |   |
|   |                 emotional_intensity +                                     |   |
|   |                 novelty_score *novelty_weight +                          |   |
|   |                 social_factor* social_weight                             |   |
|   |             ) *event_type_multiplier                                     |   |
|   |           """                                                             |   |
|   |           # Component scores                                              |   |
|   |           emotional = self.compute_emotional_intensity(event)             |   |
|   |           novelty = event.novelty_score* self.weights.novelty_weight     |   |
|   |           social = self.compute_social_factor(event) *self.weights.social|   |
|   |                                                                           |   |
|   |           # Base importance                                               |   |
|   |           base_importance = emotional + novelty + social                  |   |
|   |                                                                           |   |
|   |           # Apply event type multiplier                                   |   |
|   |           multiplier = self.event_type_multipliers.get(                   |   |
|   |               event.event_type, 1.0                                       |   |
|   |           )                                                               |   |
|   |                                                                           |   |
|   |           final_score = base_importance* multiplier                      |   |
|   |                                                                           |   |
|   |           # Normalize to [0.0, 1.0]                                       |   |
|   |           return min(1.0, max(0.0, final_score))                          |   |
|   |                                                                           |   |
|   |       def select_batch(                                                   |   |
|   |           self,                                                           |   |
|   |           events: List[HippEvent],                                        |   |
|   |           batch_size: int                                                 |   |
|   |       ) -> List[HippEvent]:                                               |   |
|   |           """                                                             |   |
|   |           Select top N events by importance for processing.               |   |
|   |           """                                                             |   |
|   |           scored = [                                                      |   |
|   |               (event, self.compute_importance_score(event))               |   |
|   |               for event in events                                         |   |
|   |           ]                                                               |   |
|   |           scored.sort(key=lambda x: x[1], reverse=True)                   |   |
|   |           return [event for event,_ in scored[:batch_size]]              |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                              OUTPUTS                                      |   |
|   |                                                                           |   |
|   |   1. importance_score: float [0.0, 1.0]                                   |   |
|   |      - Stored in: st_hipp_events.importance_score                         |   |
|   |      - Used for: Batch prioritization in R1                               |   |
|   |                                                                           |   |
|   |   2. selected_batch: List[HippEvent]                                      |   |
|   |      - Top N events by importance score                                   |   |
|   |      - Passed to: R2 Episodic Integration                                 |   |
|   |                                                                           |   |
|   |   3. component_breakdown: Dict[str, float] (for audit)                    |   |
|   |      - emotional_component: contribution from sentiment/affect            |   |
|   |      - novelty_component: contribution from novelty                       |   |
|   |      - social_component: contribution from participants                   |   |
|   |      - Stored in: st_consolidation_audit                                  |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                                                                   |
|   IMPORTANCE THRESHOLDS:                                                          |
|   +-----------------------------------------------------------------------+       |
|   | Score Range   | Priority    | Processing Behavior                    |       |
|   |---------------|-------------|----------------------------------------|       |
|   | 0.80 - 1.00   | CRITICAL    | Process immediately, never skip        |       |
|   | 0.50 - 0.79   | HIGH        | Process in current cycle               |       |
|   | 0.30 - 0.49   | MEDIUM      | Process if capacity allows             |       |
|   | 0.00 - 0.29   | LOW         | May be deferred, candidate for pruning |       |
|   +-----------------------------------------------------------------------+       |
|                                                                                   |
+-----------------------------------------------------------------------------------+

```

**SQL Query for Batch Selection**:

```sql
SELECT * FROM st_hipp_events
WHERE consolidation_status IS NULL
  AND tenant_id = :tenant_id
  AND space_id = :space_id
ORDER BY importance_score DESC
LIMIT :batch_size;
```

---

#### C.2.2 Hebbian Learning (Co-occurrence Strengthening)

**Purpose**: Detected by counting how often Actor A and Actor B appear in the same events. "Neurons that fire together, wire together."

**FamilyOS Grounding**:

- **Module**: M23 Hippocampal Replay, Knowledge Graph Builder
- **Phase**: R1/R4 (updates during replay and reconciliation)
- **Tables**: Updates `st_kg_edges.weight`

```
+-----------------------------------------------------------------------------------+
|                        HEBBIAN LEARNING ALGORITHM                                 |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   |                              INPUTS                                       |   |
|   |                                                                           |   |
|   |   1. event_batch: List[HippEvent]                                         |   |
|   |      - Current batch of events being processed in R1                      |   |
|   |      - Each event contains: actor_ids[], entity_ids[], timestamps         |   |
|   |                                                                           |   |
|   |   2. existing_edges: List[KGEdge] (from st_kg_edges)                      |   |
|   |      - Current edge weights between entities                              |   |
|   |      - Schema: (source_id, target_id, relation_type, weight, count)       |   |
|   |                                                                           |   |
|   |   3. config: HebbianConfig                                                |   |
|   |      - learning_rate: 0.1 (how much each co-occurrence strengthens)       |   |
|   |      - decay_rate: 0.01 (how much unused edges weaken per day)            |   |
|   |      - max_weight: 1.0 (weight cap to prevent runaway)                    |   |
|   |      - min_weight: 0.01 (below this, edge is pruned)                      |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                            ALGORITHM                                      |   |
|   |                                                                           |   |
|   |   class HebbianLearner:                                                   |   |
|   |       """                                                                 |   |
|   |       Implements Hebbian learning for knowledge graph edge weights.       |   |
|   |                                                                           |   |
|   |       Principle: "Cells that fire together, wire together" (Hebb, 1949)   |   |
|   |                                                                           |   |
|   |       In FamilyOS context: Entities (people, places, concepts) that       |   |
|   |       appear together in events strengthen their connection.              |   |
|   |       """                                                                 |   |
|   |                                                                           |   |
|   |       def extract_cooccurrences(                                          |   |
|   |           self,                                                           |   |
|   |           event: HippEvent                                                |   |
|   |       ) -> List[Tuple[str, str, str]]:                                    |   |
|   |           """                                                             |   |
|   |           Extract all entity pairs that co-occur in an event.             |   |
|   |                                                                           |   |
|   |           Returns: List of (entity_a, entity_b, relation_type)            |   |
|   |           """                                                             |   |
|   |           cooccurrences = []                                              |   |
|   |                                                                           |   |
|   |           # Actor-Actor co-occurrences (social relationships)             |   |
|   |           actors = event.actor_ids                                        |   |
|   |           for i, actor_a in enumerate(actors):                            |   |
|   |               for actor_b in actors[i+1:]:                                |   |
|   |                   cooccurrences.append(                                   |   |
|   |                       (actor_a, actor_b, "INTERACTS_WITH")                |   |
|   |                   )                                                       |   |
|   |                                                                           |   |
|   |           # Actor-Location co-occurrences                                 |   |
|   |           if event.location_entity_id:                                    |   |
|   |               for actor in actors:                                        |   |
|   |                   cooccurrences.append(                                   |   |
|   |                       (actor, event.location_entity_id, "FREQUENTS")      |   |
|   |                   )                                                       |   |
|   |                                                                           |   |
|   |           # Actor-Topic co-occurrences (from extracted entities)          |   |
|   |           for actor in actors:                                            |   |
|   |               for entity in event.extracted_entities:                     |   |
|   |                   cooccurrences.append(                                   |   |
|   |                       (actor, entity.entity_id, "DISCUSSES")              |   |
|   |                   )                                                       |   |
|   |                                                                           |   |
|   |           return cooccurrences                                            |   |
|   |                                                                           |   |
|   |       def update_edge_weight(                                             |   |
|   |           self,                                                           |   |
|   |           current_weight: float,                                          |   |
|   |           current_count: int,                                             |   |
|   |           event_importance: float                                         |   |
|   |       ) -> Tuple[float, int]:                                             |   |
|   |           """                                                             |   |
|   |           Hebbian weight update formula.                                  |   |
|   |                                                                           |   |
|   |           Formula:                                                        |   |
|   |             new_weight = current_weight + learning_rate *                 |   |
|   |                          (1 - current_weight) * event_importance          |   |
|   |                                                                           |   |
|   |           The (1 - current_weight) term prevents weights from             |   |
|   |           exceeding max_weight (soft saturation).                         |   |
|   |           """                                                             |   |
|   |           # Hebbian update with soft saturation                           |   |
|   |           delta = self.config.learning_rate * \                           |   |
|   |                   (self.config.max_weight - current_weight) * \           |   |
|   |                   event_importance                                        |   |
|   |                                                                           |   |
|   |           new_weight = current_weight + delta                             |   |
|   |           new_count = current_count + 1                                   |   |
|   |                                                                           |   |
|   |           return (                                                        |   |
|   |               min(self.config.max_weight, new_weight),                    |   |
|   |               new_count                                                   |   |
|   |           )                                                               |   |
|   |                                                                           |   |
|   |       def apply_decay(                                                    |   |
|   |           self,                                                           |   |
|   |           edges: List[KGEdge],                                            |   |
|   |           days_since_update: int                                          |   |
|   |       ) -> List[KGEdge]:                                                  |   |
|   |           """                                                             |   |
|   |           Apply decay to edges that haven't been reinforced.              |   |
|   |                                                                           |   |
|   |           Formula: new_weight = weight * exp(-decay_rate * days)          |   |
|   |           """                                                             |   |
|   |           result = []                                                     |   |
|   |           for edge in edges:                                              |   |
|   |               decay_factor = math.exp(                                    |   |
|   |                   -self.config.decay_rate * days_since_update             |   |
|   |               )                                                           |   |
|   |               new_weight = edge.weight * decay_factor                     |   |
|   |                                                                           |   |
|   |               if new_weight >= self.config.min_weight:                    |   |
|   |                   edge.weight = new_weight                                |   |
|   |                   result.append(edge)                                     |   |
|   |               # Edges below min_weight are pruned                         |   |
|   |                                                                           |   |
|   |           return result                                                   |   |
|   |                                                                           |   |
|   |       def process_batch(                                                  |   |
|   |           self,                                                           |   |
|   |           events: List[HippEvent]                                         |   |
|   |       ) -> Dict[Tuple[str, str, str], EdgeUpdate]:                        |   |
|   |           """                                                             |   |
|   |           Process batch and compute all edge updates.                     |   |
|   |           """                                                             |   |
|   |           edge_updates = {}                                               |   |
|   |                                                                           |   |
|   |           for event in events:                                            |   |
|   |               cooccurrences = self.extract_cooccurrences(event)           |   |
|   |               importance = event.importance_score                         |   |
|   |                                                                           |   |
|   |               for source, target, rel_type in cooccurrences:              |   |
|   |                   key = (source, target, rel_type)                        |   |
|   |                                                                           |   |
|   |                   if key not in edge_updates:                             |   |
|   |                       edge_updates[key] = EdgeUpdate(                     |   |
|   |                           source_id=source,                               |   |
|   |                           target_id=target,                               |   |
|   |                           relation_type=rel_type,                         |   |
|   |                           cooccurrence_count=0,                           |   |
|   |                           importance_sum=0.0                              |   |
|   |                       )                                                   |   |
|   |                                                                           |   |
|   |                   edge_updates[key].cooccurrence_count += 1               |   |
|   |                   edge_updates[key].importance_sum += importance          |   |
|   |                                                                           |   |
|   |           return edge_updates                                             |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                              OUTPUTS                                      |   |
|   |                                                                           |   |
|   |   1. edge_updates: Dict[EdgeKey, EdgeUpdate]                              |   |
|   |      - EdgeKey: (source_id, target_id, relation_type)                     |   |
|   |      - EdgeUpdate: new weight, new count, should_create flag              |   |
|   |      - Applied to: st_kg_edges                                            |   |
|   |                                                                           |   |
|   |   2. SQL Updates Generated:                                               |   |
|   |      - UPDATE st_kg_edges SET weight = :new_weight, count = count + 1     |   |
|   |        WHERE source_id = :src AND target_id = :tgt AND rel_type = :rel    |   |
|   |                                                                           |   |
|   |   3. new_edges: List[KGEdge]                                              |   |
|   |      - Edges created for entity pairs that didn't exist                   |   |
|   |      - Initial weight = learning_rate * avg_importance                    |   |
|   |                                                                           |   |
|   |   4. pruned_edges: List[EdgeKey]                                          |   |
|   |      - Edges that decayed below min_weight                                |   |
|   |      - Soft-deleted (tombstone) from st_kg_edges                          |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

**Edge Weight Interpretation**:

| Weight Range | Relationship Strength | Example |
|--------------|----------------------|---------|
| 0.80 - 1.00  | Very Strong | Best friends, family members |
| 0.50 - 0.79  | Strong | Regular colleagues, close friends |
| 0.20 - 0.49  | Moderate | Acquaintances, occasional contacts |
| 0.01 - 0.19  | Weak | One-time interactions |

---

### C.3 R2: Episodic Integration Algorithms (M18)

*Used to turn raw event logs into coherent "episodes."*

---

#### C.3.1 DBSCAN (Density-Based Clustering)

**Purpose**: Groups scattered events (e.g., "entered gym", "heart rate up", "left gym") into a single semantic episode ("Morning Workout").

**FamilyOS Grounding**:

- **Module**: M18 Episodic Integration
- **Phase**: R2 (CA1 Bridge)
- **Tables**: Reads `st_hipp_events` + `st_vec`, creates `st_epi`

```
+-----------------------------------------------------------------------------------+
|                           DBSCAN CLUSTERING ALGORITHM                             |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   |                              INPUTS                                       |   |
|   |                                                                           |   |
|   |   1. events: List[HippEvent] (from R1 batch selection)                    |   |
|   |      - event_id: unique identifier                                        |   |
|   |      - embedding: np.ndarray[768] (from st_vec via P08)                   |   |
|   |      - timestamp: int (epoch milliseconds)                                |   |
|   |      - actor_ids: List[str]                                               |   |
|   |      - location: Optional[LocationData]                                   |   |
|   |                                                                           |   |
|   |   2. dbscan_params: DBSCANParams                                          |   |
|   |      - eps: 0.25 (max distance between points in cluster)                 |   |
|   |          Semantic: events within cos_sim > 0.75 can cluster               |   |
|   |                                                                           |   |
|   |      - min_samples: 2 (minimum events to form episode)                    |   |
|   |          Single events remain as micro-episodes                           |   |
|   |                                                                           |   |
|   |      - temporal_weight: 0.3 (how much time affects clustering)            |   |
|   |          Events close in time cluster more easily                         |   |
|   |                                                                           |   |
|   |      - max_temporal_gap_hours: 4.0                                        |   |
|   |          Events >4 hours apart cannot cluster                             |   |
|   |                                                                           |   |
|   |   3. metric: str = "composite"                                            |   |
|   |      - "cosine": Pure semantic similarity                                 |   |
|   |      - "temporal": Pure time proximity                                    |   |
|   |      - "composite": Weighted combination (default)                        |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                            ALGORITHM                                      |   |
|   |                                                                           |   |
|   |   class EpisodicDBSCAN:                                                   |   |
|   |       """                                                                 |   |
|   |       Modified DBSCAN for episodic memory clustering.                     |   |
|   |                                                                           |   |
|   |       Standard DBSCAN uses spatial distance. We use a composite           |   |
|   |       distance that combines semantic similarity and temporal proximity.  |   |
|   |       """                                                                 |   |
|   |                                                                           |   |
|   |       def compute_composite_distance(                                     |   |
|   |           self,                                                           |   |
|   |           event_a: HippEvent,                                             |   |
|   |           event_b: HippEvent                                              |   |
|   |       ) -> float:                                                         |   |
|   |           """                                                             |   |
|   |           Compute distance for DBSCAN clustering.                         |   |
|   |                                                                           |   |
|   |           Distance = (1 - semantic_weight) * semantic_dist +              |   |
|   |                      temporal_weight * temporal_dist                      |   |
|   |                                                                           |   |
|   |           Lower distance = more similar = should cluster                  |   |
|   |           """                                                             |   |
|   |           # Semantic distance (1 - cosine similarity)                     |   |
|   |           cos_sim = np.dot(event_a.embedding, event_b.embedding)          |   |
|   |           semantic_dist = 1.0 - cos_sim                                   |   |
|   |                                                                           |   |
|   |           # Temporal distance (normalized by max gap)                     |   |
|   |           time_diff_hours = abs(                                          |   |
|   |               event_a.timestamp - event_b.timestamp                       |   |
|   |           ) / 3600000  # ms to hours                                      |   |
|   |                                                                           |   |
|   |           if time_diff_hours > self.params.max_temporal_gap_hours:        |   |
|   |               return float('inf')  # Cannot cluster                       |   |
|   |                                                                           |   |
|   |           temporal_dist = time_diff_hours / self.params.max_temporal_gap  |   |
|   |                                                                           |   |
|   |           # Composite distance                                            |   |
|   |           composite = (                                                   |   |
|   |               (1 - self.params.temporal_weight) * semantic_dist +         |   |
|   |               self.params.temporal_weight * temporal_dist                 |   |
|   |           )                                                               |   |
|   |                                                                           |   |
|   |           return composite                                                |   |
|   |                                                                           |   |
|   |       def build_distance_matrix(                                          |   |
|   |           self,                                                           |   |
|   |           events: List[HippEvent]                                         |   |
|   |       ) -> np.ndarray:                                                    |   |
|   |           """Build pairwise distance matrix for DBSCAN."""                |   |
|   |           n = len(events)                                                 |   |
|   |           distances = np.zeros((n, n))                                    |   |
|   |                                                                           |   |
|   |           for i in range(n):                                              |   |
|   |               for j in range(i + 1, n):                                   |   |
|   |                   dist = self.compute_composite_distance(                 |   |
|   |                       events[i], events[j]                                |   |
|   |                   )                                                       |   |
|   |                   distances[i, j] = dist                                  |   |
|   |                   distances[j, i] = dist                                  |   |
|   |                                                                           |   |
|   |           return distances                                                |   |
|   |                                                                           |   |
|   |       def cluster(                                                        |   |
|   |           self,                                                           |   |
|   |           events: List[HippEvent]                                         |   |
|   |       ) -> List[EpisodeCluster]:                                          |   |
|   |           """                                                             |   |
|   |           Run DBSCAN clustering.                                          |   |
|   |                                                                           |   |
|   |           Returns list of episode clusters, each containing:              |   |
|   |           - event_ids: List of events in this episode                     |   |
|   |           - is_noise: True for single-event micro-episodes                |   |
|   |           """                                                             |   |
|   |           from sklearn.cluster import DBSCAN                              |   |
|   |                                                                           |   |
|   |           # Build distance matrix                                         |   |
|   |           distances = self.build_distance_matrix(events)                  |   |
|   |                                                                           |   |
|   |           # Run DBSCAN                                                    |   |
|   |           clustering = DBSCAN(                                            |   |
|   |               eps=self.params.eps,                                        |   |
|   |               min_samples=self.params.min_samples,                        |   |
|   |               metric='precomputed'                                        |   |
|   |           ).fit(distances)                                                |   |
|   |                                                                           |   |
|   |           # Group events by cluster label                                 |   |
|   |           clusters = {}                                                   |   |
|   |           for idx, label in enumerate(clustering.labels_):                |   |
|   |               if label not in clusters:                                   |   |
|   |                   clusters[label] = []                                    |   |
|   |               clusters[label].append(events[idx])                         |   |
|   |                                                                           |   |
|   |           # Convert to EpisodeCluster objects                             |   |
|   |           result = []                                                     |   |
|   |           for label, cluster_events in clusters.items():                  |   |
|   |               result.append(EpisodeCluster(                               |   |
|   |                   cluster_id=label,                                       |   |
|   |                   events=cluster_events,                                  |   |
|   |                   is_noise=(label == -1)  # DBSCAN noise label            |   |
|   |               ))                                                          |   |
|   |                                                                           |   |
|   |           return result                                                   |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                              OUTPUTS                                      |   |
|   |                                                                           |   |
|   |   1. clusters: List[EpisodeCluster]                                       |   |
|   |      - cluster_id: int (unique within batch)                              |   |
|   |      - events: List[HippEvent] (events in this cluster)                   |   |
|   |      - is_noise: bool (True for single-event micro-episodes)              |   |
|   |                                                                           |   |
|   |   2. Each cluster becomes a candidate st_epi record:                      |   |
|   |      - epi_id: generated ULID                                             |   |
|   |      - event_ids: JSON array of clustered event IDs                       |   |
|   |      - start_time: min(event.timestamp for event in cluster)              |   |
|   |      - end_time: max(event.timestamp for event in cluster)                |   |
|   |      - participant_ids: union of all actor_ids                            |   |
|   |                                                                           |   |
|   |   3. Passed to: Centroid Calculation (C.3.2) for embedding                |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                                                                   |
|   CLUSTERING EXAMPLES:                                                            |
|   +-----------------------------------------------------------------------+       |
|   | Input Events                   | Output Episode                       |       |
|   |--------------------------------|--------------------------------------|       |
|   | 7:00 "Entered gym"             |                                      |       |
|   | 7:15 "Started treadmill"       | Episode: "Morning Workout"           |       |
|   | 7:45 "Finished workout"        | Duration: 7:00-8:00                  |       |
|   | 8:00 "Left gym"                | Events: 4                            |       |
|   |--------------------------------|--------------------------------------|       |
|   | 12:00 "Lunch with Sarah"       | Episode: "Lunch Meeting"             |       |
|   | 12:30 "Discussed project"      | Duration: 12:00-13:00                |       |
|   | 13:00 "Left restaurant"        | Events: 3                            |       |
|   +-----------------------------------------------------------------------+       |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

**Complexity**: O(n^2) for distance matrix, O(n^2) for DBSCAN = O(n^2) total

---

#### C.3.2 Centroid Calculation (Episode Embedding)

**Purpose**: Creates a representative vector for the whole episode, allowing it to be searched/compared later.

**FamilyOS Grounding**:

- **Module**: M18 Episodic Integration
- **Phase**: R2 (after DBSCAN clustering)
- **Tables**: Writes to `st_epi.embedding_centroid`

```
+-----------------------------------------------------------------------------------+
|                        CENTROID CALCULATION ALGORITHM                             |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   |                              INPUTS                                       |   |
|   |                                                                           |   |
|   |   1. cluster: EpisodeCluster (from DBSCAN)                                |   |
|   |      - events: List[HippEvent] with embeddings                            |   |
|   |                                                                           |   |
|   |   2. weighting_strategy: str                                              |   |
|   |      - "uniform": All events contribute equally                           |   |
|   |      - "importance": Weight by importance_score                           |   |
|   |      - "recency": Weight by timestamp (recent = higher)                   |   |
|   |      - "hybrid": Combination (default)                                    |   |
|   |                                                                           |   |
|   |   3. normalization: bool = True                                           |   |
|   |      - L2-normalize the final centroid                                    |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                            ALGORITHM                                      |   |
|   |                                                                           |   |
|   |   class CentroidCalculator:                                               |   |
|   |       """                                                                 |   |
|   |       Computes episode centroid embedding from constituent events.        |   |
|   |       """                                                                 |   |
|   |                                                                           |   |
|   |       def compute_weights(                                                |   |
|   |           self,                                                           |   |
|   |           events: List[HippEvent],                                        |   |
|   |           strategy: str                                                   |   |
|   |       ) -> np.ndarray:                                                    |   |
|   |           """Compute weight for each event based on strategy."""          |   |
|   |                                                                           |   |
|   |           n = len(events)                                                 |   |
|   |                                                                           |   |
|   |           if strategy == "uniform":                                       |   |
|   |               return np.ones(n) / n                                       |   |
|   |                                                                           |   |
|   |           elif strategy == "importance":                                  |   |
|   |               weights = np.array([e.importance_score for e in events])    |   |
|   |               return weights / weights.sum()                              |   |
|   |                                                                           |   |
|   |           elif strategy == "recency":                                     |   |
|   |               timestamps = np.array([e.timestamp for e in events])        |   |
|   |               # Normalize to [0, 1], recent = higher                      |   |
|   |               weights = (timestamps - timestamps.min()) / \               |   |
|   |                         (timestamps.max() - timestamps.min() + 1)         |   |
|   |               weights = weights + 0.1  # Ensure non-zero                  |   |
|   |               return weights / weights.sum()                              |   |
|   |                                                                           |   |
|   |           elif strategy == "hybrid":                                      |   |
|   |               importance = np.array([e.importance_score for e in events]) |   |
|   |               timestamps = np.array([e.timestamp for e in events])        |   |
|   |               recency = (timestamps - timestamps.min()) / \               |   |
|   |                         (timestamps.max() - timestamps.min() + 1)         |   |
|   |               weights = 0.7 * importance + 0.3 * recency                  |   |
|   |               return weights / weights.sum()                              |   |
|   |                                                                           |   |
|   |       def compute_centroid(                                               |   |
|   |           self,                                                           |   |
|   |           cluster: EpisodeCluster,                                        |   |
|   |           strategy: str = "hybrid",                                       |   |
|   |           normalize: bool = True                                          |   |
|   |       ) -> np.ndarray:                                                    |   |
|   |           """                                                             |   |
|   |           Compute weighted centroid of event embeddings.                  |   |
|   |                                                                           |   |
|   |           Formula: centroid = sum(weight_i * embedding_i) for all i       |   |
|   |           """                                                             |   |
|   |           events = cluster.events                                         |   |
|   |           weights = self.compute_weights(events, strategy)                |   |
|   |                                                                           |   |
|   |           # Stack embeddings into matrix                                  |   |
|   |           embeddings = np.stack([e.embedding for e in events])            |   |
|   |                                                                           |   |
|   |           # Weighted sum                                                  |   |
|   |           centroid = np.sum(                                              |   |
|   |               embeddings * weights[:, np.newaxis],                        |   |
|   |               axis=0                                                      |   |
|   |           )                                                               |   |
|   |                                                                           |   |
|   |           # L2 normalize for cosine similarity compatibility              |   |
|   |           if normalize:                                                   |   |
|   |               centroid = centroid / np.linalg.norm(centroid)              |   |
|   |                                                                           |   |
|   |           return centroid                                                 |   |
|   |                                                                           |   |
|   |       def compute_variance(                                               |   |
|   |           self,                                                           |   |
|   |           cluster: EpisodeCluster,                                        |   |
|   |           centroid: np.ndarray                                            |   |
|   |       ) -> float:                                                         |   |
|   |           """                                                             |   |
|   |           Compute variance from centroid (cluster cohesion).              |   |
|   |                                                                           |   |
|   |           Low variance = tight cluster = coherent episode                 |   |
|   |           High variance = loose cluster = may need splitting              |   |
|   |           """                                                             |   |
|   |           events = cluster.events                                         |   |
|   |           embeddings = np.stack([e.embedding for e in events])            |   |
|   |                                                                           |   |
|   |           # Average squared distance from centroid                        |   |
|   |           distances = 1 - np.dot(embeddings, centroid)  # 1 - cos_sim     |   |
|   |           variance = np.mean(distances ** 2)                              |   |
|   |                                                                           |   |
|   |           return float(variance)                                          |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                       |                                           |
|                                       v                                           |
|   +---------------------------------------------------------------------------+   |
|   |                              OUTPUTS                                      |   |
|   |                                                                           |   |
|   |   1. centroid: np.ndarray[768]                                            |   |
|   |      - L2-normalized embedding representing the episode                   |   |
|   |      - Stored in: st_epi.embedding_centroid                               |   |
|   |                                                                           |   |
|   |   2. variance: float [0.0, 1.0]                                           |   |
|   |      - Measure of cluster cohesion                                        |   |
|   |      - Stored in: st_epi.cluster_variance (for quality tracking)          |   |
|   |                                                                           |   |
|   |   3. weights_used: np.ndarray                                             |   |
|   |      - For audit: which events contributed most                           |   |
|   |      - Stored in: st_consolidation_audit                                  |   |
|   |                                                                           |   |
|   |   4. episode_record: st_epi row                                           |   |
|   |      - epi_id: ULID                                                       |   |
|   |      - embedding_centroid: BLOB (768 * 4 bytes)                           |   |
|   |      - event_count: len(cluster.events)                                   |   |
|   |      - start_time, end_time: timestamp range                              |   |
|   |      - significance_score: max(event.importance_score)                    |   |
|   |                                                                           |   |
|   +---------------------------------------------------------------------------+   |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

**Weighting Strategy Selection**:

| Strategy | Best For | Trade-off |
|----------|----------|-----------|
| Uniform | Short, coherent episodes | May dilute important events |
| Importance | Episodes with key moments | May over-weight single event |
| Recency | Ongoing/evolving episodes | May miss important early context |
| Hybrid | General use (default) | Balanced but more complex |

---

### C.4 R3: Synaptic Homeostasis / Forgetting (M19, M20)

*Used to compress data and remove noise.*

---

#### C.4.1 SimHash (64-bit Locality-Sensitive Hashing)

**Purpose**: Fast deduplication. Detects if "Wake up" logged at 7:01 AM is the same event as "Wake up" logged at 7:02 AM.

**FamilyOS Grounding**:

- **Module**: M19 Deduplication
- **Phase**: R3 (Forgetting/Pruning)
- **Tables**: Stored in `st_hipp_events.simhash_hex`

```python
class SimHasher:
    """
    64-bit SimHash for near-duplicate detection.

    Scientific Basis: Charikar (2002) - Similarity estimation using random projections.
    """

    HASH_BITS = 64
    HAMMING_THRESHOLD = 3  # Hamming distance <= 3 = near-duplicate

    # --- INPUTS ---
    # text: str - Event body text (from st_hipp_events.body_text)
    # existing_hashes: List[str] - SimHash values from recent events (hex format)

    def tokenize(self, text: str) -> List[str]:
        """Extract n-grams (shingles) from text."""
        text = text.lower().strip()
        words = text.split()

        # 3-gram shingles
        shingles = []
        for i in range(len(words) - 2):
            shingles.append(' '.join(words[i:i+3]))

        return shingles

    def compute_simhash(self, text: str) -> int:
        """
        Compute 64-bit SimHash.

        Algorithm:
        1. Tokenize text into shingles
        2. Hash each shingle to 64-bit value
        3. For each bit position, sum +1 (if bit=1) or -1 (if bit=0)
        4. Final hash: bit=1 if sum > 0, else bit=0
        """
        shingles = self.tokenize(text)
        if not shingles:
            return 0

        # Accumulator for each bit position
        bit_sums = [0] * self.HASH_BITS

        for shingle in shingles:
            # Hash shingle to 64-bit
            h = hash(shingle) & ((1 << self.HASH_BITS) - 1)

            for i in range(self.HASH_BITS):
                if h & (1 << i):
                    bit_sums[i] += 1
                else:
                    bit_sums[i] -= 1

        # Build final hash
        simhash = 0
        for i in range(self.HASH_BITS):
            if bit_sums[i] > 0:
                simhash |= (1 << i)

        return simhash

    def hamming_distance(self, hash1: int, hash2: int) -> int:
        """Count differing bits between two hashes."""
        xor = hash1 ^ hash2
        return bin(xor).count('1')

    def is_near_duplicate(self, hash1: int, hash2: int) -> bool:
        """Check if two hashes represent near-duplicates."""
        return self.hamming_distance(hash1, hash2) <= self.HAMMING_THRESHOLD

    # --- OUTPUTS ---
    # simhash_hex: str - 16-character hex string stored in st_hipp_events
    # is_duplicate: bool - True if near-duplicate found
    # duplicate_of: Optional[str] - event_id of matching duplicate
```

**Hamming Distance Interpretation**:

| Distance | Interpretation | Action |
|----------|---------------|--------|
| 0 | Exact duplicate | Merge, keep higher importance |
| 1-3 | Near-duplicate | Merge, combine metadata |
| 4-10 | Similar content | Consider linking, no merge |
| >10 | Different content | Process independently |

---

#### C.4.2 Exponential Decay (Memory Fading)

**Purpose**: Implements "biological forgetting." Unused memories fade and are eventually archived.

**FamilyOS Grounding**:

- **Module**: M20 Decay Engine
- **Phase**: R3 (applied to all truth tables)
- **Tables**: Updates `decay_factor` in st_sem, st_epi, st_kg_edges

```python
class ExponentialDecayEngine:
    """
    Exponential decay for memory fading.

    Scientific Basis: Ebbinghaus (1885) - Forgetting curve
    Tononi & Cirelli (2006) - Synaptic homeostasis hypothesis

    Formula: decay_factor = exp(-lambda * days_since_last_observed)
    """

    # --- INPUTS ---
    # record: TruthRecord with last_observed_at timestamp
    # config: DecayConfig
    #   - base_lambda: 0.01 (default decay rate)
    #   - importance_modifier: 0.5 (high importance decays slower)
    #   - archive_threshold: 0.1 (below this = archive candidate)
    #   - prune_threshold: 0.01 (below this = delete candidate)

    def compute_effective_lambda(
        self,
        record: TruthRecord,
        config: DecayConfig
    ) -> float:
        """
        Compute decay rate adjusted for importance.

        High-importance memories decay slower.
        High-confidence memories decay slower.
        """
        base = config.base_lambda

        # Importance reduces decay (important memories persist)
        importance_factor = 1.0 - (record.importance_score * config.importance_modifier)

        # Confidence reduces decay (trusted memories persist)
        confidence_factor = 1.0 - (record.confidence_score * 0.3)

        # Observation count reduces decay (reinforced memories persist)
        reinforcement_factor = 1.0 / (1.0 + 0.1 * record.observation_count)

        return base * importance_factor * confidence_factor * reinforcement_factor

    def compute_decay_factor(
        self,
        record: TruthRecord,
        config: DecayConfig,
        current_time: int
    ) -> float:
        """
        Compute current decay factor.

        Returns value in [0.0, 1.0]:
        - 1.0 = freshly observed, no decay
        - 0.0 = completely forgotten
        """
        days_since_observed = (current_time - record.last_observed_at) / 86400000

        effective_lambda = self.compute_effective_lambda(record, config)

        decay_factor = math.exp(-effective_lambda * days_since_observed)

        return max(0.0, min(1.0, decay_factor))

    def classify_record(
        self,
        decay_factor: float,
        config: DecayConfig
    ) -> str:
        """
        Classify record based on decay factor.

        Returns: 'ACTIVE' | 'ARCHIVE_CANDIDATE' | 'PRUNE_CANDIDATE'
        """
        if decay_factor >= config.archive_threshold:
            return 'ACTIVE'
        elif decay_factor >= config.prune_threshold:
            return 'ARCHIVE_CANDIDATE'
        else:
            return 'PRUNE_CANDIDATE'

    # --- OUTPUTS ---
    # new_decay_factor: float [0.0, 1.0] - Updated decay value
    # classification: str - 'ACTIVE' | 'ARCHIVE_CANDIDATE' | 'PRUNE_CANDIDATE'
    # archival_status: str - Updates st_*.archival_status column
```

**Decay Timeline Example**:

| Days Since Observed | Decay Factor (default) | Status |
|---------------------|----------------------|--------|
| 0 | 1.00 | ACTIVE |
| 30 | 0.74 | ACTIVE |
| 60 | 0.55 | ACTIVE |
| 90 | 0.41 | ACTIVE |
| 180 | 0.17 | ARCHIVE_CANDIDATE |
| 365 | 0.03 | PRUNE_CANDIDATE |

---

#### C.4.3 Novelty Scoring

**Purpose**: Determines if an event is unique enough to keep. Low novelty events are aggressively pruned.

**FamilyOS Grounding**:

- **Module**: M19 Deduplication
- **Phase**: R3 (pre-filter before processing)
- **Tables**: Updates `st_hipp_events.novelty_score`

```python
class NoveltyScorer:
    """
    Compute novelty score for events.

    Formula: novelty = 1.0 - (duplicate_count / window_count)

    High novelty = unique event, should keep
    Low novelty = repetitive event, candidate for pruning
    """

    # --- INPUTS ---
    # event: HippEvent with simhash_hex
    # window_events: List[HippEvent] - Recent events in same space (last 24h)
    # simhasher: SimHasher instance

    def compute_novelty(
        self,
        event: HippEvent,
        window_events: List[HippEvent],
        simhasher: SimHasher
    ) -> float:
        """
        Compute novelty score based on near-duplicate count.
        """
        if not window_events:
            return 1.0  # First event = fully novel

        event_hash = int(event.simhash_hex, 16)
        duplicate_count = 0

        for other in window_events:
            if other.event_id == event.event_id:
                continue

            other_hash = int(other.simhash_hex, 16)

            if simhasher.is_near_duplicate(event_hash, other_hash):
                duplicate_count += 1

        # Novelty formula
        novelty = 1.0 - (duplicate_count / len(window_events))

        return max(0.0, min(1.0, novelty))

    def should_prune(
        self,
        novelty_score: float,
        importance_score: float,
        config: NoveltyConfig
    ) -> bool:
        """
        Decide if event should be pruned.

        Low novelty + low importance = prune
        High importance overrides low novelty
        """
        # High importance events always kept
        if importance_score >= config.importance_override_threshold:
            return False

        # Low novelty pruned
        if novelty_score < config.novelty_prune_threshold:
            return True

        return False

    # --- OUTPUTS ---
    # novelty_score: float [0.0, 1.0] - Stored in st_hipp_events.novelty_score
    # should_prune: bool - If True, event is candidate for removal
```

**Novelty Thresholds**:

| Novelty Score | Interpretation | Default Action |
|---------------|---------------|----------------|
| 0.90 - 1.00 | Highly unique | Always process |
| 0.50 - 0.89 | Somewhat novel | Process normally |
| 0.20 - 0.49 | Repetitive | Process if important |
| 0.00 - 0.19 | Near-duplicate | Prune unless critical |

---

### C.5 R4: Knowledge Graph Algorithms (M21)

*Used to extract structured facts from unstructured events.*

---

#### C.5.1 UltraBERT NER (Named Entity Recognition)

**Purpose**: Identifies "Uncle Bob" (Person) or "Denton" (Location) from raw text.

**FamilyOS Grounding**:

- **Module**: P02 (extraction), consumed by P03 R4
- **Phase**: R4 (Knowledge Graph building)
- **Tables**: Creates entities in `st_kg_dom`

```python
class UltraBERTEntityExtractor:
    """
    Named Entity Recognition using FamilyOS UltraBERT model.

    UltraBERT: 768-dim custom embedding model fine-tuned for
    family/personal context understanding.
    """

    # Supported entity types
    ENTITY_TYPES = [
        'PERSON',      # Family members, friends, colleagues
        'LOCATION',    # Places, addresses, venues
        'ORGANIZATION',# Companies, schools, groups
        'EVENT',       # Birthdays, holidays, meetings
        'FOOD',        # Meals, recipes, dietary preferences
        'ACTIVITY',    # Hobbies, sports, routines
        'OBJECT',      # Personal items, gifts, possessions
        'CONCEPT',     # Abstract ideas, topics, preferences
    ]

    # --- INPUTS ---
    # text: str - Event body text from st_hipp_events.body_text
    # context: Optional[str] - Additional context (e.g., space_name)
    # existing_entities: List[KGEntity] - Known entities for disambiguation

    def extract_entities(
        self,
        text: str,
        context: Optional[str] = None
    ) -> List[ExtractedEntity]:
        """
        Extract named entities from text.

        Returns list of entities with:
        - text_span: The matched text
        - entity_type: One of ENTITY_TYPES
        - confidence: Model confidence [0.0, 1.0]
        - start_pos, end_pos: Character positions
        """
        # Tokenize with UltraBERT tokenizer
        tokens = self.tokenizer.encode(text, context)

        # Run NER model
        predictions = self.ner_model(tokens)

        # Decode BIO tags to entities
        entities = self._decode_bio_tags(text, predictions)

        return entities

    def disambiguate_entity(
        self,
        extracted: ExtractedEntity,
        existing_entities: List[KGEntity]
    ) -> Optional[str]:
        """
        Match extracted entity to existing KG entity.

        Uses embedding similarity + fuzzy string matching.

        Returns: entity_id if matched, None if new entity
        """
        # Compute embedding for extracted text
        embedding = self.embed(extracted.text_span)

        candidates = []
        for entity in existing_entities:
            if entity.entity_type != extracted.entity_type:
                continue

            # Embedding similarity
            sim = cosine_similarity(embedding, entity.embedding)

            # Fuzzy string similarity
            fuzzy = fuzz.ratio(
                extracted.text_span.lower(),
                entity.canonical_name.lower()
            ) / 100.0

            # Combined score
            score = 0.7 * sim + 0.3 * fuzzy

            if score > 0.8:
                candidates.append((entity.entity_id, score))

        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]

        return None  # New entity

    # --- OUTPUTS ---
    # entities: List[ExtractedEntity]
    #   - text_span: str
    #   - entity_type: str
    #   - confidence: float
    #   - matched_entity_id: Optional[str] (if disambiguated)
    #
    # Creates/updates st_kg_dom rows
```

**Entity Type Examples**:

| Type | Examples | Confidence Threshold |
|------|----------|---------------------|
| PERSON | "Uncle Bob", "Dr. Smith" | 0.85 |
| LOCATION | "Grandma's house", "Central Park" | 0.80 |
| EVENT | "Christmas dinner", "Soccer game" | 0.75 |
| FOOD | "Mom's lasagna", "birthday cake" | 0.70 |

---

#### C.5.2 Granger Causality (Simplified Temporal Inference)

**Purpose**: Distinguishes between correlation and causation in user routines. If Event A consistently precedes Event B, infer A causes B.

**FamilyOS Grounding**:

- **Module**: M21 Knowledge Graph Builder
- **Phase**: R4 (edge creation with directionality)
- **Tables**: Creates directed edges in `st_kg_edges` with `CAUSES` relation

```python
class GrangerCausalityInference:
    """
    Simplified Granger causality for temporal event patterns.

    Principle: If A consistently precedes B, and removing A
    reduces predictability of B, then A Granger-causes B.

    Simplified for FamilyOS: Use co-occurrence frequency
    with temporal ordering to infer causal direction.
    """

    # --- INPUTS ---
    # event_pairs: List[Tuple[HippEvent, HippEvent]]
    #   Pairs of events that co-occur (from Hebbian learning)
    #
    # temporal_window_minutes: int = 60
    #   Max time gap for causal consideration
    #
    # min_observations: int = 5
    #   Minimum observations to infer causality

    def compute_temporal_precedence(
        self,
        event_a: str,  # entity_id
        event_b: str,  # entity_id
        observations: List[Tuple[int, int]]  # (timestamp_a, timestamp_b)
    ) -> dict:
        """
        Compute temporal precedence statistics.

        Returns:
        - a_before_b_count: Times A preceded B
        - b_before_a_count: Times B preceded A
        - simultaneous_count: Times within 1 minute
        - precedence_ratio: a_before_b / total
        """
        a_before_b = 0
        b_before_a = 0
        simultaneous = 0

        for ts_a, ts_b in observations:
            diff_minutes = (ts_b - ts_a) / 60000

            if abs(diff_minutes) < 1:
                simultaneous += 1
            elif diff_minutes > 0:
                a_before_b += 1  # A happened first
            else:
                b_before_a += 1  # B happened first

        total = a_before_b + b_before_a + simultaneous

        return {
            'a_before_b': a_before_b,
            'b_before_a': b_before_a,
            'simultaneous': simultaneous,
            'precedence_ratio': a_before_b / total if total > 0 else 0.5
        }

    def infer_causal_direction(
        self,
        entity_a: str,
        entity_b: str,
        observations: List[Tuple[int, int]],
        config: CausalityConfig
    ) -> Optional[CausalEdge]:
        """
        Infer causal direction between entities.

        Returns CausalEdge if strong temporal pattern found.
        """
        if len(observations) < config.min_observations:
            return None  # Not enough data

        stats = self.compute_temporal_precedence(entity_a, entity_b, observations)

        # Strong precedence = likely causal
        if stats['precedence_ratio'] >= config.causality_threshold:
            # A likely causes B
            return CausalEdge(
                source_id=entity_a,
                target_id=entity_b,
                relation_type='CAUSES',
                confidence=stats['precedence_ratio'],
                observation_count=len(observations)
            )

        elif stats['precedence_ratio'] <= (1 - config.causality_threshold):
            # B likely causes A
            return CausalEdge(
                source_id=entity_b,
                target_id=entity_a,
                relation_type='CAUSES',
                confidence=1 - stats['precedence_ratio'],
                observation_count=len(observations)
            )

        # No clear causal direction
        return None

    # --- OUTPUTS ---
    # causal_edge: Optional[CausalEdge]
    #   - source_id, target_id: Entity IDs
    #   - relation_type: 'CAUSES'
    #   - confidence: float [0.0, 1.0]
    #
    # Updates st_kg_edges with directed CAUSES edges
```

**Causal Pattern Examples**:

| Pattern | Precedence Ratio | Inferred Edge |
|---------|-----------------|---------------|
| "Alarm" always before "Wake up" | 0.95 | Alarm CAUSES Wake_up |
| "Coffee" before "Work start" | 0.82 | Coffee CAUSES Work_start |
| "Exercise" before "Good mood" | 0.78 | Exercise CAUSES Good_mood |
| "Rain" mixed with "Stay home" | 0.55 | No causal edge (correlation only) |

---

### C.6 R5: Dream-Like Exploration Algorithms (M22)

*Creative insight, counterfactual reasoning, and future simulation during REM-like phase.*

---

#### C.6.1 Causal Perturbation Network (CPN)

**Purpose**: Generate "what if" scenarios by perturbing past events. Learns from near-misses.

**FamilyOS Grounding**:

- **Module**: M22 Dream/Exploration
- **Phase**: R5 (Counterfactual Thinking)
- **Tables**: Reads st_epi, st_kg_edges; Writes st_prospective

```python
class CausalPerturbationNetwork:
    """
    Counterfactual scenario generation via causal graph intervention.

    Principle: Perturb modifiable nodes in causal chain,
    predict alternative outcomes via Bayesian propagation.
    """

    # --- INPUTS ---
    # high_emotion_events: List[EpisodicMemory]
    #   Events from st_epi with |sentiment_score| > 0.6
    #
    # causal_graph: DirectedGraph
    #   From st_kg_edges with relationship_type='CAUSES'
    #
    # emotional_threshold: float = 0.6

    def select_regret_events(
        self,
        episodes: List[EpisodicMemory],
        top_k: int = 10
    ) -> List[EpisodicMemory]:
        """
        Select emotionally significant events for counterfactual analysis.

        Prioritize negative outcomes (regret potential).
        """
        scored = []
        for ep in episodes:
            if abs(ep.sentiment_score) < self.emotional_threshold:
                continue

            impact = (
                abs(ep.sentiment_score) *
                ep.salience_score *
                self._recency_weight(ep.start_time)
            )
            scored.append((ep, impact))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [ep for ep, _ in scored[:top_k]]

    def extract_causal_chain(
        self,
        event: EpisodicMemory,
        depth: int = 5
    ) -> CausalDAG:
        """
        Build causal predecessor DAG from knowledge graph.

        Returns nodes tagged as:
        - MODIFIABLE: Actor could have changed (left work early)
        - EXTERNAL: Outside control (meeting ran long)
        """
        dag = CausalDAG()
        queue = [event.entity_id]

        for _ in range(depth):
            next_queue = []
            for node_id in queue:
                causes = self.kg.get_edges(
                    target=node_id,
                    rel_type='CAUSES'
                )
                for cause in causes:
                    modifiable = self._is_actor_controllable(cause.source_id)
                    dag.add_edge(
                        cause.source_id,
                        node_id,
                        modifiable=modifiable,
                        confidence=cause.causal_confidence
                    )
                    next_queue.append(cause.source_id)
            queue = next_queue

        return dag

    def generate_counterfactuals(
        self,
        dag: CausalDAG,
        original_outcome: float  # sentiment
    ) -> List[CounterfactualScenario]:
        """
        Generate upward/downward/semifactual scenarios.

        Types:
        - UPWARD: "If I had X, outcome would be better"
        - DOWNWARD: "If I had also Y, outcome would be worse"
        - SEMIFACTUAL: "Even if X, outcome unchanged"
        """
        scenarios = []
        modifiable_nodes = dag.get_modifiable_nodes()

        for node in modifiable_nodes:
            # Upward: Intervene to improve
            upward = self._simulate_intervention(
                dag, node, intervention='positive'
            )
            if upward.predicted_sentiment > original_outcome + 0.3:
                scenarios.append(CounterfactualScenario(
                    type='UPWARD',
                    intervention_node=node,
                    original_sentiment=original_outcome,
                    predicted_sentiment=upward.predicted_sentiment,
                    preventable=True,
                    mitigation=self._generate_mitigation(node)
                ))

        return scenarios

    # --- OUTPUTS ---
    # scenarios: List[CounterfactualScenario]
    #   - type: UPWARD/DOWNWARD/SEMIFACTUAL
    #   - intervention_node: Entity that was changed
    #   - predicted_sentiment: Simulated outcome
    #   - mitigation: If-then rule for future
    #
    # Writes to st_prospective with intent_type='counterfactual_learning'
```

**Counterfactual Types**:

| Type | Question | Example | Learning |
|------|----------|---------|----------|
| UPWARD | "What if I had...?" | "Left work on time" | Preventable regret |
| DOWNWARD | "What if I also...?" | "Forgot anniversary too" | Risk awareness |
| SEMIFACTUAL | "Even if I had...?" | "Called ahead" | Identify uncontrollable factors |

---

#### C.6.2 TPN-MCTS (Forward Simulation)

**Purpose**: Predict future scenarios using Monte Carlo Tree Search over personal action space.

**FamilyOS Grounding**:

- **Module**: M22 Dream/Exploration
- **Phase**: R5 (Forward Simulation)
- **Tables**: Reads st_prospective (goals), st_procedural; Writes st_prospective

```python
class TemporalProjectionMCTS:
    """
    Monte Carlo Tree Search for personal future scenarios.

    Combines UCT selection with DPP diversity sampling
    for varied, plausible scenario generation.
    """

    # Configuration
    EXPLORATION_CONSTANT = 1.414  # sqrt(2) for UCT
    MAX_ROLLOUT_DEPTH = 30        # 30-day horizon
    ROLLOUTS_PER_NODE = 100       # Simulation count

    # --- INPUTS ---
    # current_state: ActorState
    #   Location, relationships, resources, time
    #
    # goals: List[ProspectiveMemory]
    #   Active goals from st_prospective
    #
    # action_repertoire: List[Action]
    #   From st_procedural habits and routines

    def uct_select(self, node: MCTSNode) -> MCTSNode:
        """
        Upper Confidence Bound for Trees selection.

        UCT = Q/N + c * sqrt(ln(N_parent) / N)

        Balances exploitation (high Q/N) with exploration (low N).
        """
        best_child = None
        best_uct = float('-inf')

        for child in node.children:
            if child.visit_count == 0:
                return child  # Always try unvisited

            exploitation = child.total_reward / child.visit_count
            exploration = self.EXPLORATION_CONSTANT * math.sqrt(
                math.log(node.visit_count) / child.visit_count
            )
            uct = exploitation + exploration

            if uct > best_uct:
                best_uct = uct
                best_child = child

        return best_child

    def rollout(
        self,
        state: ActorState,
        goal: ProspectiveMemory
    ) -> float:
        """
        Simulate random action sequence to terminal state.

        Returns reward based on goal achievement and sentiment.
        """
        current = state.copy()
        total_reward = 0.0

        for day in range(self.MAX_ROLLOUT_DEPTH):
            # Sample action from repertoire
            action = self._sample_action(current)

            # Transition to next state
            next_state = self._apply_transition(current, action)

            # Accumulate reward
            reward = self._compute_reward(next_state, goal)
            total_reward += reward * (0.9 ** day)  # Discount

            # Check terminal
            if self._goal_achieved(next_state, goal):
                total_reward += 10.0  # Goal bonus
                break

            current = next_state

        return total_reward

    def generate_diverse_scenarios(
        self,
        root: MCTSNode,
        k: int = 5
    ) -> List[Scenario]:
        """
        Use DPP to select diverse scenario set.

        DPP favors low pairwise similarity for coverage.
        """
        all_paths = self._extract_paths(root)

        # Build feature vectors
        features = [self._path_to_features(p) for p in all_paths]

        # Compute similarity kernel
        K = self._compute_kernel(features)

        # DPP sampling: P(S) ∝ det(K_S)
        selected_indices = self._dpp_sample(K, k)

        return [all_paths[i] for i in selected_indices]

    # --- OUTPUTS ---
    # scenarios: List[Scenario]
    #   - action_sequence: List[Action]
    #   - predicted_outcome: GoalState
    #   - success_probability: float
    #   - expected_sentiment: float
    #   - plausibility_score: float
    #
    # Writes top scenarios to st_prospective
```

**Scenario Quality Metrics**:

| Metric | Formula | Threshold |
|--------|---------|-----------|
| Success Probability | rollouts_reaching_goal / total_rollouts | > 0.3 to keep |
| Plausibility | geometric_mean(transition_probabilities) | > 0.3 to keep |
| Expected Sentiment | mean(sentiment across timeline) | Report as-is |
| Diversity (DPP) | det(K_subset) / det(K_all) | Maximize |

---

#### C.6.3 BGT-SM (Insight Generation)

**Purpose**: Discover surprising connections between remote concepts using random walks and information theory.

**FamilyOS Grounding**:

- **Module**: M22 Dream/Exploration
- **Phase**: R5 (Insight Generation)
- **Tables**: Reads st_kg_dom, st_kg_edges, st_vec; Writes st_sem

```python
class BisociativeGraphTraversal:
    """
    Bisociative Graph Traversal with Surprise Maximization.

    Finds unexpected-but-meaningful connections by:
    1. Random walks to discover remote associates
    2. PMI scoring to quantify surprise
    3. Structure mapping for analogies
    """

    # Configuration
    RESTART_PROBABILITY = 0.15  # Random walk restart
    WALK_STEPS = 1000           # Steps per exploration
    PMI_THRESHOLD = 3.0         # High PMI = surprising

    # --- INPUTS ---
    # knowledge_graph: Graph
    #   Entities from st_kg_dom, edges from st_kg_edges
    #
    # embeddings: Dict[entity_id, Vector]
    #   From st_vec for semantic distance
    #
    # seed_entities: List[str]
    #   High-importance entities to explore from

    def random_walk_with_restart(
        self,
        seed: str,
        steps: int = 1000
    ) -> Dict[str, int]:
        """
        RWR to find distant but reachable concepts.

        With probability c, restart at seed.
        Otherwise, follow random edge (favor unexplored).
        """
        visit_counts = defaultdict(int)
        current = seed

        for _ in range(steps):
            visit_counts[current] += 1

            if random.random() < self.RESTART_PROBABILITY:
                current = seed
                continue

            # Get neighbors, favor unexplored
            neighbors = self.graph.get_neighbors(current)
            if not neighbors:
                current = seed
                continue

            # Weight by inverse observation count
            weights = [
                1.0 / (e.observation_count + 1)
                for e in neighbors
            ]
            current = random.choices(
                [n.target_id for n in neighbors],
                weights=weights
            )[0]

        return visit_counts

    def compute_pmi(
        self,
        entity_a: str,
        entity_b: str
    ) -> float:
        """
        Pointwise Mutual Information for surprise quantification.

        PMI = log(P(A,B) / (P(A) * P(B)))

        High PMI = entities co-occur more than expected by chance.
        """
        # Marginal probabilities from observation counts
        p_a = self.graph.get_entity(entity_a).frequency
        p_b = self.graph.get_entity(entity_b).frequency

        # Joint probability from co-occurrence
        p_ab = self.graph.get_cooccurrence(entity_a, entity_b)

        if p_ab == 0 or p_a == 0 or p_b == 0:
            return 0.0

        return math.log2(p_ab / (p_a * p_b))

    def discover_insights(
        self,
        seed: str
    ) -> List[Insight]:
        """
        Find surprising connections from seed entity.
        """
        visits = self.random_walk_with_restart(seed)
        insights = []

        for entity, count in visits.items():
            if entity == seed:
                continue

            # Semantic distance
            distance = 1.0 - cosine_similarity(
                self.embeddings[seed],
                self.embeddings[entity]
            )

            # Only consider remote associates
            if distance < 0.7:
                continue

            # Compute surprise
            pmi = self.compute_pmi(seed, entity)

            if pmi > self.PMI_THRESHOLD:
                # Surprising connection found!
                novelty = distance * pmi / (count + 1)

                insights.append(Insight(
                    source_entity=seed,
                    target_entity=entity,
                    semantic_distance=distance,
                    pmi_score=pmi,
                    novelty_score=novelty,
                    insight_text=self._generate_insight_text(seed, entity)
                ))

        return sorted(insights, key=lambda i: i.novelty_score, reverse=True)

    # --- OUTPUTS ---
    # insights: List[Insight]
    #   - source_entity, target_entity: Connected concepts
    #   - pmi_score: Surprise quantification
    #   - novelty_score: Combined distance * surprise
    #   - insight_text: Human-readable insight
    #
    # Writes to st_sem with pattern_type='insight'
```

**Insight Quality Thresholds**:

| Metric | Threshold | Meaning |
|--------|-----------|---------|
| Semantic Distance | > 0.7 | Concepts are far apart |
| PMI Score | > 3.0 | Co-occur 8x more than expected |
| Novelty Score | > 0.5 | Worth surfacing to user |
| Serendipity | novelty × relevance × actionability | > 0.6 to keep |

---

#### C.6.4 TDL-HCO (Motor Skill Rehearsal)

**Purpose**: Optimize procedural routines using Temporal Difference Learning.

**FamilyOS Grounding**:

- **Module**: M22 Dream/Exploration
- **Phase**: R5 (Motor Rehearsal)
- **Tables**: Reads/writes st_procedural; Writes st_prospective (optimizations)

```python
class TemporalDifferenceLearning:
    """
    TD Learning for Habit Chain Optimization.

    Models routines as MDPs and uses TD(0) to learn
    value function, identifying bottlenecks and improvements.
    """

    # Hyperparameters
    DISCOUNT_FACTOR = 0.9   # γ: Future reward weight
    LEARNING_RATE = 0.1     # α: Update step size

    # --- INPUTS ---
    # routine: ProceduralMemory
    #   From st_procedural with action_sequence_json
    #
    # execution_history: List[ExecutionRecord]
    #   Historical executions from st_epi

    def initialize_values(
        self,
        routine: ProceduralMemory
    ) -> Dict[str, float]:
        """
        Initialize value function V(s) = 0 for all states.
        """
        steps = json.loads(routine.action_sequence_json)
        return {step: 0.0 for step in steps}

    def td_update(
        self,
        V: Dict[str, float],
        s_t: str,       # Current state
        r_t: float,     # Reward at s_t
        s_t1: str       # Next state
    ) -> None:
        """
        TD(0) update rule.

        δ = r_t + γ * V(s_{t+1}) - V(s_t)
        V(s_t) ← V(s_t) + α * δ
        """
        td_error = r_t + self.DISCOUNT_FACTOR * V.get(s_t1, 0.0) - V[s_t]
        V[s_t] = V[s_t] + self.LEARNING_RATE * td_error

    def learn_value_function(
        self,
        routine: ProceduralMemory,
        history: List[ExecutionRecord]
    ) -> Dict[str, float]:
        """
        Learn V(s) from historical executions.
        """
        V = self.initialize_values(routine)

        for execution in history:
            steps = execution.executed_steps

            for i in range(len(steps) - 1):
                s_t = steps[i].step_name
                s_t1 = steps[i + 1].step_name
                r_t = self._compute_reward(steps[i])

                self.td_update(V, s_t, r_t, s_t1)

        return V

    def detect_bottlenecks(
        self,
        V: Dict[str, float],
        routine: ProceduralMemory
    ) -> List[Bottleneck]:
        """
        Find steps with large negative value gradient.

        ΔV(s_t) = V(s_{t+1}) - V(s_t)
        Bottleneck: ΔV < -2 (large value drop)
        """
        steps = json.loads(routine.action_sequence_json)
        bottlenecks = []

        for i in range(len(steps) - 1):
            delta_v = V[steps[i + 1]] - V[steps[i]]

            if delta_v < -2.0:
                bottlenecks.append(Bottleneck(
                    step_name=steps[i],
                    position=i,
                    value_drop=delta_v,
                    reason=self._infer_reason(steps[i])
                ))

        return bottlenecks

    def _compute_reward(self, step: ExecutionStep) -> float:
        """
        Reward function for routine steps.

        +10: Completion
        +2:  Pleasant step
        -1:  Unpleasant step
        -3:  Delayed/skipped step
        """
        if step.completed:
            base = 2.0 if step.sentiment > 0 else -1.0
            return base - step.duration_penalty
        return -3.0

    # --- OUTPUTS ---
    # value_function: Dict[step_name, float]
    #   Expected cumulative reward from each step
    #
    # bottlenecks: List[Bottleneck]
    #   Steps with negative value gradient
    #
    # Writes optimization suggestions to st_prospective
```

**Value Function Interpretation**:

| V(s) Range | Meaning | Action |
|------------|---------|--------|
| > 5.0 | High-value step | Maintain as-is |
| 2.0 - 5.0 | Good step | Minor optimizations |
| 0.0 - 2.0 | Neutral step | Consider streamlining |
| < 0.0 | Bottleneck | Investigate alternatives |

---

### C.7 Active Learning Algorithms (P06 Integration)

*Algorithms for gap detection, question prioritization, and rate limiting.*

---

#### C.7.1 Shannon Entropy (Uncertainty Quantification)

**Purpose**: Measure uncertainty in candidate distributions to prioritize questions.

**FamilyOS Grounding**:

- **Module**: P06 Active Learning (fed by P03)
- **Phase**: Gap Detection (R4/R7)
- **Tables**: Reads gap records from st_learning_queue

```python
class ShannonEntropyCalculator:
    """
    Shannon entropy for uncertainty quantification.

    H(X) = -Σ p(x) * log2(p(x))

    Higher entropy = more uncertain = higher priority for questions.
    """

    # --- INPUTS ---
    # candidates: List[EntityCandidate]
    #   Possible matches with confidence scores
    #
    # Or: decision with single confidence score

    def compute_entropy(
        self,
        candidates: List[EntityCandidate]
    ) -> float:
        """
        Shannon entropy over candidate distribution.

        Returns normalized entropy in [0, 1].
        """
        if len(candidates) <= 1:
            return 0.0  # No uncertainty

        # Normalize confidences to probabilities
        confidences = [c.confidence for c in candidates]
        total = sum(confidences)
        probs = [c / total for c in confidences]

        # Compute entropy
        entropy = 0.0
        for p in probs:
            if p > 0:
                entropy -= p * math.log2(p)

        # Normalize by max entropy (uniform distribution)
        max_entropy = math.log2(len(candidates))

        return entropy / max_entropy if max_entropy > 0 else 0.0

    def entropy_from_confidence(
        self,
        confidence: float
    ) -> float:
        """
        Derive entropy from single confidence score.

        Simple inversion: high confidence = low entropy.
        """
        return 1.0 - confidence

    # --- OUTPUTS ---
    # entropy_score: float in [0, 1]
    #   0 = certain, 1 = maximally uncertain
    #
    # Used to prioritize gaps in st_learning_queue
```

**Entropy Interpretation**:

| Entropy | Candidates | Meaning | Question Priority |
|---------|------------|---------|-------------------|
| 0.0 | 1 dominant | Certain | Low (don't ask) |
| 0.3 | 2-3 with gap | Slight uncertainty | Medium |
| 0.6 | Several close | Ambiguous | High |
| 1.0 | All equal | Maximally uncertain | Urgent |

---

#### C.7.2 Beta Distribution (Confidence Modeling)

**Purpose**: Model confidence as probability distribution, not point estimate.

**FamilyOS Grounding**:

- **Module**: P06 Active Learning
- **Phase**: Question response integration
- **Tables**: Updates confidence in st_sem, st_kg_dom

```python
class BetaConfidenceModel:
    """
    Beta distribution for Bayesian confidence modeling.

    Beta(α, β) where:
    - α = successes + 1 (confirmations)
    - β = failures + 1 (contradictions)

    Mean = α / (α + β)
    Variance indicates certainty of estimate.
    """

    # --- INPUTS ---
    # confirmations: int - Times pattern was confirmed
    # contradictions: int - Times pattern was contradicted

    def __init__(self, confirmations: int = 0, contradictions: int = 0):
        self.alpha = confirmations + 1  # Prior: 1
        self.beta = contradictions + 1  # Prior: 1

    def mean(self) -> float:
        """Expected value of confidence."""
        return self.alpha / (self.alpha + self.beta)

    def variance(self) -> float:
        """Variance indicates certainty of estimate."""
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total ** 2 * (total + 1))

    def confidence_interval(
        self,
        credible_mass: float = 0.95
    ) -> Tuple[float, float]:
        """
        Credible interval for confidence.

        Narrow interval = high certainty about true confidence.
        """
        from scipy import stats
        dist = stats.beta(self.alpha, self.beta)
        lower = dist.ppf((1 - credible_mass) / 2)
        upper = dist.ppf((1 + credible_mass) / 2)
        return (lower, upper)

    def update(self, confirmed: bool) -> None:
        """Bayesian update on new evidence."""
        if confirmed:
            self.alpha += 1
        else:
            self.beta += 1

    def needs_clarification(
        self,
        variance_threshold: float = 0.05
    ) -> bool:
        """
        High variance = uncertain = needs more data.
        """
        return self.variance() > variance_threshold

    # --- OUTPUTS ---
    # mean: float - Point estimate of confidence
    # variance: float - Certainty of estimate
    # needs_clarification: bool - Should we ask user?
```

**Beta Parameters Interpretation**:

| α | β | Mean | Interpretation |
|---|---|------|----------------|
| 10 | 1 | 0.91 | Strong confirmation |
| 5 | 5 | 0.50 | Equal evidence both ways |
| 1 | 10 | 0.09 | Strong contradiction |
| 2 | 2 | 0.50 | Uncertain (high variance) |

---

#### C.7.3 Token Bucket (Rate Limiting)

**Purpose**: Prevent question fatigue by limiting questions per time window.

**FamilyOS Grounding**:

- **Module**: P06 Active Learning
- **Phase**: Question emission control
- **Tables**: Tracks in st_learning_queue

```python
class TokenBucketRateLimiter:
    """
    Token bucket algorithm for question rate limiting.

    Tokens accumulate over time up to bucket_size.
    Each question consumes one token.
    If no tokens, question is deferred.
    """

    # --- INPUTS ---
    # bucket_size: int = 5
    #   Max questions that can burst
    #
    # refill_rate: float = 1.0
    #   Tokens per hour
    #
    # Per-space configuration

    def __init__(
        self,
        bucket_size: int = 5,
        refill_rate: float = 1.0  # per hour
    ):
        self.bucket_size = bucket_size
        self.refill_rate = refill_rate
        self.tokens = bucket_size
        self.last_refill = time.time()

    def _refill(self) -> None:
        """Add tokens based on elapsed time."""
        now = time.time()
        elapsed_hours = (now - self.last_refill) / 3600

        new_tokens = elapsed_hours * self.refill_rate
        self.tokens = min(self.bucket_size, self.tokens + new_tokens)
        self.last_refill = now

    def try_consume(self) -> bool:
        """
        Attempt to consume a token for asking a question.

        Returns True if allowed, False if rate limited.
        """
        self._refill()

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True

        return False

    def time_until_available(self) -> float:
        """Seconds until next question allowed."""
        self._refill()

        if self.tokens >= 1.0:
            return 0.0

        tokens_needed = 1.0 - self.tokens
        hours_needed = tokens_needed / self.refill_rate
        return hours_needed * 3600

    def get_burst_capacity(self) -> int:
        """How many questions can be asked right now."""
        self._refill()
        return int(self.tokens)

    # --- OUTPUTS ---
    # allowed: bool - Can ask question now?
    # wait_time: float - Seconds until allowed
    # burst_capacity: int - Available question slots
```

**Rate Limit Configuration by Context**:

| Context | Bucket Size | Refill Rate | Rationale |
|---------|-------------|-------------|-----------|
| Onboarding | 10 | 3/hr | Learn quickly early |
| Normal | 5 | 1/hr | Avoid fatigue |
| Low engagement | 3 | 0.5/hr | User is busy |
| High importance | 7 | 2/hr | Critical gaps |

---

### C.8 Supplementary Algorithms

*Additional algorithms used across P03 phases.*

---

#### C.8.1 SPC-UQ (Schematic Pattern Completion)

**Purpose**: Reconstruct incomplete memories using schema-based Bayesian inference with uncertainty quantification.

**FamilyOS Grounding**:

- **Module**: M22 Dream/Exploration
- **Phase**: R5 (Episodic Simulation)
- **Tables**: Reads st_epi, st_sem; Writes st_epi (versioned)

```python
class SchematicPatternCompletion:
    """
    Schematic Pattern Completion with Uncertainty Quantification.

    Fills memory gaps using Bayesian inference with schema priors,
    tracking reconstruction confidence separately from recall confidence.
    """

    # --- INPUTS ---
    # incomplete_episode: EpisodicMemory
    #   Episode with missing attributes (location, participants, etc.)
    #
    # schemas: List[SemanticPattern]
    #   From st_sem matching episode's activity_type
    #
    # constraint_graph: TemporalDAG
    #   Ordering constraints from event sequences

    def identify_gaps(
        self,
        episode: EpisodicMemory
    ) -> List[AttributeGap]:
        """
        Find missing or uncertain attributes.

        Gaps:
        - NULL values in location_name, participants
        - ambiguity_score > 0.5
        - P06 flagged uncertainties
        """
        gaps = []

        # Check core attributes
        if not episode.location_name:
            gaps.append(AttributeGap('location_name', priority=0.8))

        if not episode.participants_json:
            gaps.append(AttributeGap('participants', priority=0.7))

        if episode.ambiguity_score > 0.5:
            gaps.append(AttributeGap('ambiguous_content', priority=0.9))

        return gaps

    def retrieve_schema(
        self,
        episode: EpisodicMemory
    ) -> Optional[SemanticPattern]:
        """
        Find matching schema to guide reconstruction.

        Example: "dinner with colleagues" matches "team_dinner_routine"
        """
        candidates = self.sem_store.query(
            activity_type=episode.activity_type,
            min_confidence=0.6
        )

        if not candidates:
            return None

        # Best match by context similarity
        best = max(candidates, key=lambda s: self._context_similarity(episode, s))
        return best if self._context_similarity(episode, best) > 0.5 else None

    def bayesian_reconstruction(
        self,
        gap: AttributeGap,
        schema: SemanticPattern,
        context_clues: Dict
    ) -> ReconstructedValue:
        """
        Fill gap using Bayesian inference.

        P(value | schema, context) ∝ P(context | value) × P(value | schema)
        """
        # Prior: P(value | schema)
        prior = schema.get_attribute_distribution(gap.attribute_name)

        # Likelihood: P(context | value)
        likelihoods = {}
        for value, prior_prob in prior.items():
            likelihood = self._compute_likelihood(value, context_clues)
            likelihoods[value] = prior_prob * likelihood

        # Normalize to get posterior
        total = sum(likelihoods.values())
        posteriors = {v: p / total for v, p in likelihoods.items()}

        # Select maximum a posteriori
        best_value = max(posteriors, key=posteriors.get)
        confidence = posteriors[best_value]

        return ReconstructedValue(
            value=best_value,
            confidence=confidence,
            provenance='inferred_from_schema',
            schema_id=schema.pattern_id
        )

    def validate_reconstruction(
        self,
        reconstruction: ReconstructedValue,
        episode: EpisodicMemory
    ) -> bool:
        """
        Check reconstruction against KG constraints.

        Reject if:
        - Person was on vacation during episode
        - Location doesn't match activity type
        - Temporal impossibility
        """
        if reconstruction.attribute == 'participants':
            for person in reconstruction.value:
                if self._was_unavailable(person, episode.start_time):
                    return False

        return True

    # --- OUTPUTS ---
    # reconstructed_episode: EpisodicMemory
    #   With filled gaps marked in provenance
    #
    # Creates new version in st_epi with:
    #   - reconstructed_fields_json
    #   - reconstruction_confidence
    #   - supersedes_episode_id
```

**Reconstruction Confidence Rules**:

| Attribute | Schema Strength | Context Match | Final Confidence |
|-----------|-----------------|---------------|------------------|
| Location | 0.8 | Strong | 0.75 (high) |
| Participants | 0.6 | Weak | 0.40 (uncertain) |
| Time | 0.5 | None | 0.25 (low, don't reconstruct) |

---

#### C.8.2 Exponential Backoff (Retry Scheduling)

**Purpose**: Space out retry attempts to avoid overwhelming failed services.

**FamilyOS Grounding**:

- **Module**: K0 RetryScheduler, OutboxProcessor
- **Phase**: Error recovery (all phases)
- **Tables**: Updates st_outbox.next_attempt_ts

```python
class ExponentialBackoffScheduler:
    """
    Exponential backoff with jitter for retry scheduling.

    delay = min(cap, base * 2^attempt) + random_jitter

    Prevents thundering herd on service recovery.
    """

    # Configuration
    BASE_DELAY_MS = 100      # Initial delay
    MAX_DELAY_MS = 64000     # Cap at ~1 minute
    MAX_RETRIES = 6          # 2^6 = 64 cap
    JITTER_FACTOR = 0.2      # ±20% randomization

    # --- INPUTS ---
    # attempt: int - Current retry attempt (0-indexed)
    # base_delay: int - Initial delay in ms
    # max_delay: int - Maximum delay cap

    def calculate_delay(
        self,
        attempt: int,
        base_delay: int = 100,
        max_delay: int = 64000
    ) -> int:
        """
        Calculate delay for retry attempt.

        Attempt 0: 100ms
        Attempt 1: 200ms
        Attempt 2: 400ms
        Attempt 3: 800ms
        ...
        Attempt 6+: 64000ms (capped)
        """
        # Exponential growth
        delay = base_delay * (2 ** attempt)

        # Apply cap
        delay = min(delay, max_delay)

        # Add jitter (±20%)
        jitter = delay * self.JITTER_FACTOR
        delay += random.uniform(-jitter, jitter)

        return int(delay)

    def schedule_retry(
        self,
        record: OutboxRecord
    ) -> int:
        """
        Schedule next retry attempt.

        Returns next_attempt_ts (Unix timestamp).
        """
        delay_ms = self.calculate_delay(record.attempt_count)

        next_ts = int(time.time() * 1000) + delay_ms

        return next_ts

    def should_retry(
        self,
        record: OutboxRecord
    ) -> bool:
        """Check if retry should be attempted."""
        return record.attempt_count < self.MAX_RETRIES

    # --- OUTPUTS ---
    # delay_ms: int - Milliseconds to wait
    # next_attempt_ts: int - Unix timestamp for next try
    # should_retry: bool - Within retry budget?
```

**Backoff Schedule**:

| Attempt | Delay (base) | With Jitter | Cumulative |
|---------|--------------|-------------|------------|
| 0 | 100ms | 80-120ms | ~100ms |
| 1 | 200ms | 160-240ms | ~300ms |
| 2 | 400ms | 320-480ms | ~700ms |
| 3 | 800ms | 640-960ms | ~1.5s |
| 4 | 1600ms | 1280-1920ms | ~3s |
| 5 | 3200ms | 2560-3840ms | ~6s |
| 6 | 6400ms | 5120-7680ms | ~13s |

---

#### C.8.3 Weighted Fair Queuing (WFQ)

**Purpose**: Fairly allocate processing time across tenants/spaces based on priority weights.

**FamilyOS Grounding**:

- **Module**: K0 QoSScheduler, K1 Backpressure
- **Phase**: All (scheduling)
- **Tables**: N/A (runtime only)

```python
class WeightedFairQueueScheduler:
    """
    Weighted Fair Queuing for multi-tenant scheduling.

    Each queue gets time proportional to its weight.
    Virtual time tracks fairness across queues.
    """

    # --- INPUTS ---
    # queues: Dict[queue_id, Queue]
    #   Each queue has weight and pending items
    #
    # weights: Dict[queue_id, float]
    #   Priority weights (higher = more time)

    def __init__(self):
        self.virtual_time = defaultdict(float)  # Per-queue virtual time
        self.global_time = 0.0

    def calculate_finish_time(
        self,
        queue_id: str,
        item_cost: float,
        weight: float
    ) -> float:
        """
        Calculate virtual finish time for fair ordering.

        vtime_finish = vtime_start + (cost / weight)

        Higher weight = lower finish time = earlier service.
        """
        vtime_start = max(
            self.virtual_time[queue_id],
            self.global_time
        )

        vtime_finish = vtime_start + (item_cost / weight)

        return vtime_finish

    def select_next(
        self,
        queues: Dict[str, Queue],
        weights: Dict[str, float]
    ) -> Tuple[str, Any]:
        """
        Select next item to process (lowest virtual finish time).
        """
        candidates = []

        for queue_id, queue in queues.items():
            if queue.empty():
                continue

            item = queue.peek()
            weight = weights.get(queue_id, 1.0)

            finish_time = self.calculate_finish_time(
                queue_id,
                item.cost,
                weight
            )

            candidates.append((finish_time, queue_id, item))

        if not candidates:
            return None, None

        # Select smallest virtual finish time
        candidates.sort(key=lambda x: x[0])
        finish_time, queue_id, item = candidates[0]

        # Update virtual time
        self.virtual_time[queue_id] = finish_time
        self.global_time = max(self.global_time, finish_time)

        # Dequeue and return
        queues[queue_id].get()
        return queue_id, item

    # --- OUTPUTS ---
    # queue_id: str - Which queue to serve
    # item: Any - Next item to process
    #
    # Ensures fairness: queue with weight 2 gets 2x service
```

**Weight Allocation Examples**:

| Queue Type | Weight | Share | Rationale |
|------------|--------|-------|-----------|
| Premium tenant | 3.0 | 37.5% | Paid tier |
| Standard tenant | 2.0 | 25% | Default |
| Free tier | 1.0 | 12.5% | Basic |
| System/Admin | 2.0 | 25% | Internal ops |

---

## Changelog

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 2.0.0 | 2025-12-20 | K0 Team | Initial v2 draft with bidirectional reconciliation model |
| 2.0.1 | 2025-12-20 | K0 Team | Added full section outline with Active Learning integration |
| 2.0.2 | 2025-12-20 | K0 Team | Added complete storage schemas (st_epi through st_retention_policy) |
| 2.0.3 | 2025-12-20 | K0 Team | Added Sections 13-16: Error Handling, Security, Performance, Configuration |
| 2.0.4 | 2025-12-20 | K0 Team | Added Phase state machine diagram, timing constraints, concurrency section |
| 2.0.5 | 2025-12-20 | K0 Team | Full K0 architecture integration for Sections 13-16 from k0_source_of_truth_v2.mmd |
| 2.0.6 | 2025-12-20 | K0 Team | Section 13: K0 DLQStore, RetryScheduler, CircuitBreaker integration |
| 2.0.7 | 2025-12-20 | K0 Team | Section 14: K0 Policy Engine, ACL Enforcer, Location Privacy, Retention integration |
| 2.0.8 | 2025-12-20 | K0 Team | Section 15: K0 QoS Scheduler, QoSContext, QoSMetrics, adaptive batch sizing |
| 2.0.9 | 2025-12-20 | K0 Team | Section 16: K0 Kernel Config, PipelineScheduler, CapabilityFabric, ModuleRegistry |
| 2.1.0 | 2025-12-21 | K0 Team | Appendix C: Algorithm Specifications with 23 algorithms grounded to modules/tables |
| 2.2.0 | 2025-12-21 | K0 Team | Appendix D: P03 Kernel Integration Blueprint with 12 sections |
| 2.2.1 | 2025-12-21 | K0 Team | Appendix E: Canonical Name Registry (event topics, modules, capabilities, configs) |
| 2.2.2 | 2025-12-21 | K0 Team | Appendix F: Threshold Configuration Table (all similarity buckets, config-driven) |
| 2.2.3 | 2025-12-21 | K0 Team | Appendix G: R0-R8 State Machine Specification (inputs/outputs, DB writes, idempotency, retryability, timeouts) |
| 2.3.0 | 2025-12-21 | K0 Team | Section 12: Closed all open questions with explicit policy defaults + feature flags |
| 2.3.0 | 2025-12-21 | K0 Team | Section 17: Ops Readiness (SLOs, dashboards, alerting thresholds, runbooks) |
| 2.3.0 | 2025-12-21 | K0 Team | Updated Table of Contents with all new sections and appendices |

---

## Appendix D: P03 Kernel Integration Blueprint

> **Purpose**: This appendix defines how P03 Consolidation integrates with the K0 production kernel.
> Based on analysis of: `k0_source_of_truth_v2.mmd`, `k0/fabric/`, `k0/runtime/`, `k0/pipelines/`, `k0/contracts/`.
> Reference implementation: P02 Write Pipeline (`p02_write.v1.yaml`).

---

### D.1 Architecture Context

*Understanding the K0 kernel layers P03 must integrate with.*

---

#### D.1.1 K0 Layer Stack Overview

*Core idea: P03 must integrate at Layers 6 (Event Bus), 6.5 (Capability Mesh), and plug into Layer 3 (Transaction Coordination).*

| Layer | Name | P03 Integration Point |
|-------|------|----------------------|
| Layer 0 | Client Interfaces | No direct integration |
| Layer 1 | Kernel Ports | Potential `/k0/consolidate.trigger` admin endpoint |
| Layer 2 | Gate & Policy | Inherit PolicyStamp from source events |
| Layer 3 | Transaction Coordination | UnitOfWork for atomic multi-table writes |
| Layer 4 | Storage Core | st_hipp_events, st_epi, st_sem, st_vec, st_outbox |
| Layer 5 | QoS & Scheduling | Scheduler token for batch processing |
| Layer 6 | Event Bus | Subscribe to `p02.write.complete.v1`, emit `p03.*.v1` |
| Layer 6.5 | Capability Mesh | Register/invoke capabilities via Fabric |
| Layer 7 | Query Drivers | FAISS, FTS5 for similarity search |
| Layer 8 | Driver SPI | Alias map for storage routing |
| Layer 9 | Observability | MetricsExporter, TracerFactory |
| Layer 10 | Infrastructure | PipelineScheduler trigger registration |

---

#### D.1.2 Key K0 Components for P03

*Core idea: These are the primary K0 components P03 will directly use.*

**BusDispatcher** (`k0/bus/core.py`):

- Subscribe to entry topics via `dispatcher.subscribe(topic, handler)`
- Topic-based routing with O(k) dispatch
- BusMessage: `{topic, payload, offset, trace_id, space_id, metadata}`

**CapabilityFabric** (`k0/fabric/fabric.py`):

- Request/reply by capability name (not module name)
- `fabric.invoke("score_salience", **kwargs)` routes to registered provider
- Resolution strategies: PRIORITY, FIRST, ROUND_ROBIN
- Timeout enforcement via ThreadPoolExecutor

**PipelineRunner** (`k0/runtime/pipeline_runner.py`):

- Generic DAG executor for YAML-declared pipelines
- Topological execution with parallel stage groups
- Enriched envelope propagation across stages

**ModuleRegistry** (`k0/runtime/module_registry.py`):

- Lookup modules by `module_id:version` (e.g., `hippocampus.pattern_separate:v1`)
- Capability index for fabric-based lookup
- Lazy loading of module implementations

**PipelineScheduler** (`k0/scheduler/`):

- Declarative triggers: INTERVAL, THRESHOLD, MANUAL, CRON (future), IDLE (future)
- Register pipelines with trigger conditions
- Fire pipeline execution on trigger events

---

#### D.1.3 P02 as Reference Implementation

*Core idea: P02 demonstrates the canonical pattern for YAML-based pipelines.*

**P02 Pipeline Contract** (`k0/contracts/pipelines/p02_write.v1.yaml`):

```yaml
pipeline_id: P02_WRITE
version: v1
entry_topic: cognitive.memory.write.committed.v1
exit_topic: p02.write.complete.v1
concurrency: 1
max_queue_depth: 512
required_capabilities: [st_hipp_events.write, st_vec.write, ...]
dag:
  - id: stage_10_dg_pattern_separate
    module: hippocampus.pattern_separate:v1
    after: []
    config: {novelty_threshold: 0.7}
  ...
```

**P02 Module Example** (`k0/modules/hippocampus/pattern_separate.py`):

```python
async def run(message: Any, context: Any, **config) -> dict[str, Any]:
    # Extract envelope from config or message.payload
    envelope = config.get("envelope") or parse_payload(message.payload)
    # Process and return enriched envelope
    return {**envelope, "simhash_hex": computed_hash, ...}
```

---

### D.2 Pipeline Contract Design

*Defining the YAML contract for P03.*

---

#### D.2.1 P03 Pipeline Contract Structure

*Core idea: P03 needs two pipeline variants: a triggered consolidation and a continuous incremental pipeline.*

**P03_CONSOLIDATE (Batch Mode)**:

- Trigger: INTERVAL (every 90 min) + THRESHOLD (st_hipp_events pending >= 500) + MANUAL
- Entry: `p03.consolidation.trigger.v1` (synthetic event from scheduler)
- Exit: `p03.consolidation.complete.v1`
- Concurrency: 1 (single consolidation cycle)
- Required caps: 15+ storage capabilities (read/write across all memory tables)

**P03_INCREMENTAL (Future, Optional)**:

- Trigger: Event-driven (each `p02.write.complete.v1`)
- Lightweight: Only importance scoring, no full reconciliation
- Defers heavy work to batch consolidation

---

#### D.2.2 Required Capabilities Matrix

*Core idea: P03 needs extensive read/write access across the memory system.*

| Capability | Mode | Phase | Purpose |
|------------|------|-------|---------|
| st_hipp_events.read | R | R0-R8 | Source events for consolidation |
| st_hipp_events.write | W | R6 | Update consolidation_status |
| st_vec.read | R | R1-R5 | Embedding similarity queries |
| st_vec.write | W | R7 | Episode/pattern embeddings |
| st_epi.read | R | R2-R5 | Existing episodes for clustering |
| st_epi.write | W | R7 | New/updated episodes |
| st_sem.read | R | R3-R5 | Semantic patterns |
| st_sem.write | W | R7 | New patterns, insights |
| st_kg_dom.read | R | R4 | Entity lookup |
| st_kg_dom.write | W | R4 | New entities |
| st_kg_edges.read | R | R4-R5 | Relationship queries |
| st_kg_edges.write | W | R4 | New/updated edges |
| st_procedural.read | R | R5 | Routine data |
| st_procedural.write | W | R7 | Optimized routines |
| st_prospective.write | W | R5 | Counterfactuals, simulations |
| st_outbox.write | W | R8 | Event emission |
| st_learning_queue.write | W | R4/R7 | P06 gap records |

---

#### D.2.3 Entry/Exit Topic Design

*Core idea: Well-defined topic contracts for inter-pipeline communication.*

**Entry Topics** (P03 subscribes):

- `p03.consolidation.trigger.v1` - Scheduler-initiated batch cycle
- `p02.write.complete.v1` - (Optional) Incremental scoring trigger

**Exit Topics** (P03 emits):

- `p03.consolidation.complete.v1` - Batch cycle completion
- `p03.phase.complete.v1` - Per-phase progress (R0 through R8)
- `p03.episode.formed.v1` - New episode created
- `p03.pattern.discovered.v1` - New semantic pattern
- `p03.gap.detected.v1` - P06 Active Learning trigger
- `p03.insight.generated.v1` - R5 creative insight
- `p03.kg.updated.v1` - Knowledge graph changes

---

### D.3 DAG Stage Design

*Mapping R-phases to pipeline stages.*

---

#### D.3.1 Phase-to-Stage Mapping

*Core idea: Each R-phase becomes one or more pipeline stages with explicit dependencies.*

| Stage ID | Module | After | R-Phase | Description |
|----------|--------|-------|---------|-------------|
| stage_00_select_batch | consolidation.batch_selector:v1 | [] | R0 | Select pending events |
| stage_10_importance_score | consolidation.importance_scorer:v1 | [00] | R1 | Compute importance |
| stage_11_hebbian_update | consolidation.hebbian_learner:v1 | [00] | R1 | Co-occurrence weights |
| stage_20_episodic_cluster | consolidation.episodic_clusterer:v1 | [10,11] | R2 | DBSCAN clustering |
| stage_21_episode_builder | consolidation.episode_builder:v1 | [20] | R2 | Build st_epi records |
| stage_30_simhash_dedup | consolidation.simhash_deduplicator:v1 | [21] | R3 | Near-duplicate detection |
| stage_31_decay_scorer | consolidation.decay_scorer:v1 | [21] | R3 | Exponential decay |
| stage_32_prune_decider | consolidation.prune_decider:v1 | [30,31] | R3 | Prune/archive decisions |
| stage_40_entity_extractor | consolidation.entity_extractor:v1 | [21] | R4 | UltraBERT NER |
| stage_41_relationship_builder | consolidation.relationship_builder:v1 | [40] | R4 | KG edge creation |
| stage_42_causal_inference | consolidation.causal_inference:v1 | [41] | R4 | Granger causality |
| stage_50_counterfactual | consolidation.counterfactual:v1 | [42] | R5 | CPN scenarios |
| stage_51_forward_sim | consolidation.forward_simulator:v1 | [42] | R5 | TPN-MCTS |
| stage_52_insight_gen | consolidation.insight_generator:v1 | [42] | R5 | BGT-SM |
| stage_60_status_update | consolidation.status_updater:v1 | [32,52] | R6 | Mark st_hipp_events |
| stage_70_memory_writer | consolidation.memory_writer:v1 | [60] | R7 | Atomic writes |
| stage_80_event_emitter | core.event_emitter:v1 | [70] | R8 | Emit completion events |

---

#### D.3.2 Parallel Execution Groups

*Core idea: Identify stages that can run concurrently for performance.*

**Level 0**: stage_00_select_batch (sequential, must complete first)

**Level 1 (parallel)**:

- stage_10_importance_score
- stage_11_hebbian_update

**Level 2**: stage_20_episodic_cluster (depends on both L1 stages)

**Level 3**: stage_21_episode_builder

**Level 4 (parallel)**:

- stage_30_simhash_dedup
- stage_31_decay_scorer
- stage_40_entity_extractor

**Level 5 (parallel)**:

- stage_32_prune_decider (depends on 30,31)
- stage_41_relationship_builder (depends on 40)

**Level 6**: stage_42_causal_inference

**Level 7 (parallel R5)**:

- stage_50_counterfactual
- stage_51_forward_sim
- stage_52_insight_gen

**Level 8**: stage_60_status_update (merge point)

**Level 9**: stage_70_memory_writer (atomic transaction)

**Level 10**: stage_80_event_emitter

---

#### D.3.3 Module Contract Templates

*Core idea: Each stage needs a module contract YAML and implementation file.*

**Contract Pattern** (`k0/contracts/modules/consolidation.<module>.v1.yaml`):

```yaml
module_id: consolidation.<module_name>
version: v1
input_event_types: [p03.consolidation.trigger.v1]
output_event_types: [p03.<module>.complete.v1]
latency_budget_ms: <budget>
side_effects: [read:st_*, write:st_*]
idempotent: true/false
fabric_capabilities: [<capability_names>]
failure_modes: [...]
```

**Implementation Pattern** (`k0/modules/consolidation/<module>.py`):

```python
async def run(message: Any, context: Any, **config) -> dict[str, Any]:
    envelope = config.get("envelope") or parse_payload(message)
    # Module logic using context.syscalls for storage
    # Return enriched envelope with module outputs
    return {**envelope, "<output_field>": result}
```

---

### D.4 Module Development Plan

*Creating the 18+ modules needed for P03.*

---

#### D.4.1 Module Directory Structure

*Core idea: Organize P03 modules under `k0/modules/consolidation/`.*

```
k0/modules/consolidation/
+-- __init__.py
+-- README.md
+-- batch_selector.py          # R0: Select events for cycle
+-- importance_scorer.py       # R1: Importance scoring
+-- hebbian_learner.py         # R1: Co-occurrence learning
+-- episodic_clusterer.py      # R2: DBSCAN clustering
+-- episode_builder.py         # R2: Build episodes
+-- simhash_deduplicator.py    # R3: Near-duplicate detection
+-- decay_scorer.py            # R3: Exponential decay
+-- prune_decider.py           # R3: Prune/archive decisions
+-- entity_extractor.py        # R4: UltraBERT NER
+-- relationship_builder.py    # R4: KG edge creation
+-- causal_inference.py        # R4: Granger causality
+-- counterfactual.py          # R5: CPN scenarios
+-- forward_simulator.py       # R5: TPN-MCTS
+-- insight_generator.py       # R5: BGT-SM
+-- motor_rehearsal.py         # R5: TDL-HCO
+-- status_updater.py          # R6: Mark consolidation_status
+-- memory_writer.py           # R7: Atomic multi-table write
+-- gap_emitter.py             # P06 integration
```

---

#### D.4.2 Module Contract Registry

*Core idea: Each module needs a contract in `k0/contracts/modules/`.*

| Module ID | Latency Budget | Idempotent | Fabric Capabilities |
|-----------|---------------|------------|---------------------|
| consolidation.batch_selector:v1 | 50ms | Yes | select_consolidation_batch |
| consolidation.importance_scorer:v1 | 30ms | Yes | score_importance |
| consolidation.hebbian_learner:v1 | 100ms | No | update_cooccurrence |
| consolidation.episodic_clusterer:v1 | 200ms | Yes | cluster_episodes |
| consolidation.episode_builder:v1 | 50ms | Yes | build_episode |
| consolidation.simhash_deduplicator:v1 | 100ms | Yes | detect_duplicates |
| consolidation.decay_scorer:v1 | 50ms | Yes | score_decay |
| consolidation.prune_decider:v1 | 30ms | Yes | decide_prune |
| consolidation.entity_extractor:v1 | 150ms | Yes | extract_entities |
| consolidation.relationship_builder:v1 | 100ms | No | build_relationships |
| consolidation.causal_inference:v1 | 200ms | Yes | infer_causality |
| consolidation.counterfactual:v1 | 300ms | Yes | generate_counterfactuals |
| consolidation.forward_simulator:v1 | 500ms | Yes | simulate_futures |
| consolidation.insight_generator:v1 | 400ms | Yes | generate_insights |
| consolidation.status_updater:v1 | 30ms | Yes | update_status |
| consolidation.memory_writer:v1 | 100ms | No | write_memories |

---

#### D.4.3 Fabric Capability Registration

*Core idea: Register module capabilities for cross-pipeline invocation.*

```yaml
# k0/contracts/capabilities/consolidation.yaml
capabilities:
  - name: score_importance
    provider:
      module_id: consolidation.importance_scorer:v1
      priority: 10
    timeout_ms: 30

  - name: cluster_episodes
    provider:
      module_id: consolidation.episodic_clusterer:v1
      priority: 10
    timeout_ms: 200

  - name: detect_duplicates
    provider:
      module_id: consolidation.simhash_deduplicator:v1
      priority: 10
    timeout_ms: 100
```

---

### D.5 Scheduler Integration

*Configuring declarative triggers for P03.*

---

#### D.5.1 Trigger Configuration

*Core idea: P03 uses multiple trigger types for flexible activation.*

```yaml
# In p03_consolidation.v1.yaml
triggers:
  - type: INTERVAL
    interval_seconds: 5400  # 90 minutes
    description: Regular consolidation cycle

  - type: THRESHOLD
    table: st_hipp_events
    condition: "consolidation_status = 'PENDING'"
    threshold: 500
    description: Trigger when 500+ pending events

  - type: MANUAL
    description: Admin/debug trigger via API

  # Future (Phase 2):
  # - type: IDLE
  #   idle_seconds: 1800  # After 30 min idle
  #   description: Consolidate during quiet periods
```

---

#### D.5.2 Trigger Engine Integration

*Core idea: PipelineScheduler creates trigger engines from YAML spec.*

```python
# How scheduler registers P03
from k0.scheduler.triggers import create_trigger_engine, TriggerType

# Interval trigger
interval_trigger = create_trigger_engine(
    TriggerType.INTERVAL,
    interval_seconds=5400,
    callback=lambda: scheduler.fire_pipeline("P03_CONSOLIDATE")
)

# Threshold trigger
threshold_trigger = create_trigger_engine(
    TriggerType.THRESHOLD,
    table="st_hipp_events",
    condition="consolidation_status = 'PENDING'",
    threshold=500,
    callback=lambda: scheduler.fire_pipeline("P03_CONSOLIDATE")
)

scheduler.register_pipeline("P03_CONSOLIDATE", [interval_trigger, threshold_trigger])
```

---

#### D.5.3 Manual Trigger API

*Core idea: Admin endpoint for on-demand consolidation.*

```
POST /k0/admin/pipelines/P03_CONSOLIDATE/trigger
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "reason": "Manual consolidation before demo",
  "options": {
    "skip_r5": false,
    "max_events": 1000
  }
}
```

---

### D.6 Event Bus Integration

*Topic subscription and event emission patterns.*

---

#### D.6.1 Subscription Pattern

*Core idea: P03 subscribes to trigger topic via BusDispatcher.*

```python
# In pipeline on_startup()
async def on_startup(self, ctx: PipelineContext) -> None:
    self._ctx = ctx

    # Subscribe to trigger topic
    ctx.bus_dispatcher.subscribe(
        "p03.consolidation.trigger.v1",
        self.handle
    )

    # Optional: Subscribe to P02 completion for incremental mode
    # ctx.bus_dispatcher.subscribe(
    #     "p02.write.complete.v1",
    #     self.handle_incremental
    # )
```

---

#### D.6.2 Event Emission Pattern

*Core idea: Use st_outbox + core.event_emitter for durable event publishing.*

```python
# In memory_writer module or event_emitter stage
async def emit_completion_events(
    context: PipelineContext,
    cycle_results: ConsolidationCycleResult
) -> None:
    # Stage outbox entries for each event type

    # Cycle completion
    await context.syscalls.stage_outbox({
        "topic": "p03.consolidation.complete.v1",
        "payload": {
            "cycle_id": cycle_results.cycle_id,
            "events_processed": cycle_results.event_count,
            "episodes_created": cycle_results.episode_count,
            "patterns_discovered": cycle_results.pattern_count,
            "duration_ms": cycle_results.duration_ms,
        }
    })

    # Per-episode events
    for episode in cycle_results.new_episodes:
        await context.syscalls.stage_outbox({
            "topic": "p03.episode.formed.v1",
            "payload": episode.to_event_payload()
        })

    # P06 gap events
    for gap in cycle_results.detected_gaps:
        await context.syscalls.stage_outbox({
            "topic": "p03.gap.detected.v1",
            "payload": gap.to_event_payload()
        })
```

---

#### D.6.3 Topic Schema Contracts

*Core idea: Define Pydantic models for each event topic.*

```python
# k0/contracts/events/p03_events.py

@dataclass
class P03ConsolidationComplete:
    """p03.consolidation.complete.v1 event payload."""
    cycle_id: str
    tenant_id: str
    space_id: str
    started_at: int
    completed_at: int
    duration_ms: int
    events_processed: int
    episodes_created: int
    patterns_discovered: int
    kg_entities_added: int
    kg_edges_added: int
    gaps_detected: int
    r5_insights_generated: int
    prune_count: int
    error_count: int

@dataclass
class P03EpisodeFormed:
    """p03.episode.formed.v1 event payload."""
    episode_id: str
    tenant_id: str
    space_id: str
    title: str
    start_time: int
    end_time: int
    event_count: int
    centroid_embedding_id: str
    dominant_sentiment: float

@dataclass
class P03GapDetected:
    """p03.gap.detected.v1 event payload (for P06)."""
    gap_id: str
    gap_type: str  # AMBIGUITY, CONTRADICTION, LOW_CONFIDENCE, MISSING_INFO
    tenant_id: str
    space_id: str
    related_entity_id: str
    entropy_score: float
    priority: str  # HIGH, MEDIUM, LOW
    context_json: str
```

---

### D.7 Storage Integration

*Atomic writes and transaction patterns.*

---

#### D.7.1 UnitOfWork Pattern

*Core idea: Use K0's UnitOfWork for atomic multi-table transactions.*

```python
# In memory_writer module
async def run(message: Any, context: Any, **config) -> dict[str, Any]:
    envelope = config.get("envelope")

    # UnitOfWork ensures atomicity across tables
    async with context.syscalls.unit_of_work() as uow:
        # Write episodes
        for episode in envelope.get("new_episodes", []):
            await uow.insert("st_epi", episode.to_row())

        # Write semantic patterns
        for pattern in envelope.get("new_patterns", []):
            await uow.insert("st_sem", pattern.to_row())

        # Write KG entities
        for entity in envelope.get("new_entities", []):
            await uow.insert("st_kg_dom", entity.to_row())

        # Write KG edges
        for edge in envelope.get("new_edges", []):
            await uow.insert("st_kg_edges", edge.to_row())

        # Update event statuses
        for event_id, status in envelope.get("status_updates", []):
            await uow.update(
                "st_hipp_events",
                {"consolidation_status": status},
                {"event_id": event_id}
            )

        # Stage outbox events
        for event in envelope.get("outbox_events", []):
            await uow.stage_outbox(event)

        # Commit atomically (UnitOfWork.__exit__ handles commit/rollback)

    return {**envelope, "write_complete": True}
```

---

#### D.7.2 Capability-Gated Storage Access

*Core idea: Syscalls enforce required_caps before any storage operation.*

```python
# How syscalls enforces capabilities
class Syscalls:
    def __init__(self, pipeline_id: str, caps: set[str], uow: UnitOfWork):
        self._caps = caps
        self._uow = uow

    async def read(self, table: str, query: dict) -> list[dict]:
        required_cap = f"{table}.read"
        if required_cap not in self._caps:
            raise PermissionError(f"Pipeline lacks capability: {required_cap}")
        return await self._uow.read(table, query)

    async def write(self, table: str, row: dict) -> None:
        required_cap = f"{table}.write"
        if required_cap not in self._caps:
            raise PermissionError(f"Pipeline lacks capability: {required_cap}")
        await self._uow.insert(table, row)
```

---

#### D.7.3 Optimistic Locking for Concurrent Updates

*Core idea: Use version columns to prevent lost updates.*

> **PostgreSQL Migration Note** (2025-01): Updated to use PostgreSQL `$N` parameter
> placeholders (asyncpg style) and native `RETURNING` clause for atomic read-back.

```python
# In status_updater module
async def update_event_status(
    context: PipelineContext,
    event_id: str,
    new_status: str,
    expected_version: int
) -> tuple[bool, int | None]:
    """
    Update event status with optimistic locking.

    Returns (True, new_version) if update succeeded,
            (False, None) if version mismatch.

    Uses PostgreSQL RETURNING clause for atomic version read-back.
    """
    result = await context.syscalls.execute(
        """
        UPDATE st_hipp_events
        SET consolidation_status = $1,
            version = version + 1,
            updated_at = $2
        WHERE event_id = $3
        AND version = $4
        RETURNING version
        """,
        [new_status, int(time.time()), event_id, expected_version]
    )

    if result.rows:
        return True, result.rows[0]["version"]
    return False, None
```

---

### D.8 Fabric Capability Integration

*Request/reply patterns for cross-module communication.*

---

#### D.8.1 Fabric Invocation Pattern

*Core idea: Use fabric.invoke() for cross-module capability calls.*

```python
# In episodic_clusterer module
async def run(message: Any, context: Any, **config) -> dict[str, Any]:
    envelope = config.get("envelope")
    events = envelope.get("scored_events", [])

    # Invoke importance scoring via fabric (if not already done)
    if not events[0].get("importance_score"):
        scored_events = []
        for event in events:
            result = await context.fabric.invoke(
                "score_importance",
                event=event,
                timeout_ms=30
            )
            scored_events.append(result)
        events = scored_events

    # Now cluster using scored events
    clusters = await cluster_with_dbscan(events, config)

    return {**envelope, "clusters": clusters}
```

---

#### D.8.2 Fabric Provider Registration

*Core idea: Modules register as capability providers at startup.*

```python
# In consolidation module __init__.py
from k0.fabric import get_capability_registry

def register_consolidation_capabilities():
    registry = get_capability_registry()

    # Register importance scoring
    from k0.modules.consolidation.importance_scorer import run as score_fn
    registry.register(
        capability="score_importance",
        handler=score_fn,
        priority=10,
        timeout_ms=30
    )

    # Register episode clustering
    from k0.modules.consolidation.episodic_clusterer import run as cluster_fn
    registry.register(
        capability="cluster_episodes",
        handler=cluster_fn,
        priority=10,
        timeout_ms=200
    )
```

---

#### D.8.3 Context Policy Enforcement

*Core idea: Fabric enforces capability intersection before invocation.*

```yaml
# In module contract
fabric_context_policy: INTERSECT_CALLER
# Options:
# - INHERIT_CALLER: Use caller's full capabilities
# - INTERSECT_CALLER: Use intersection of caller and module caps
# - MODULE_ONLY: Use only module's declared capabilities
```

---

### D.9 Observability Integration

*Metrics, tracing, and logging patterns.*

---

#### D.9.1 Metrics Export Pattern

*Core idea: Use MetricsExporter for Prometheus-compatible metrics.*

```python
# Metrics to emit from P03 modules
CONSOLIDATION_METRICS = {
    # Counters
    "p03_cycles_total": "Total consolidation cycles",
    "p03_events_processed_total": "Events processed across all cycles",
    "p03_episodes_created_total": "Episodes created",
    "p03_patterns_discovered_total": "Semantic patterns discovered",
    "p03_kg_entities_total": "KG entities created",
    "p03_kg_edges_total": "KG edges created",
    "p03_gaps_detected_total": "P06 gaps detected",
    "p03_prune_total": "Events pruned",
    "p03_errors_total": "Errors by error_type",

    # Histograms
    "p03_cycle_duration_seconds": "Cycle duration distribution",
    "p03_phase_duration_seconds": "Per-phase duration by phase_id",
    "p03_batch_size": "Events per cycle",
    "p03_cluster_size": "Episodes per cluster",

    # Gauges
    "p03_pending_events": "Events awaiting consolidation",
    "p03_last_cycle_timestamp": "Timestamp of last cycle",
}
```

---

#### D.9.2 Distributed Tracing Pattern

*Core idea: Propagate trace_id across phases and modules.*

```python
# In pipeline handle()
async def handle(self, message: BusMessage) -> None:
    trace_id = message.trace_id or generate_trace_id()

    with self._ctx.tracer.span("p03.consolidation.cycle", trace_id=trace_id) as span:
        span.set_attribute("cycle_id", self._cycle_id)
        span.set_attribute("batch_size", len(self._events))

        # Each phase gets child span
        with span.child_span("p03.r1.importance_scoring") as r1_span:
            await self._execute_r1(r1_span)

        with span.child_span("p03.r2.episodic_integration") as r2_span:
            await self._execute_r2(r2_span)

        # ... continue for R3-R8
```

---

#### D.9.3 Structured Logging Pattern

*Core idea: Use structured logging with consistent context fields.*

```python
# Standard log context for P03
LOG_CONTEXT = {
    "pipeline_id": "P03_CONSOLIDATE",
    "module_id": "<current_module>",
    "cycle_id": "<cycle_ulid>",
    "phase": "<R0-R8>",
    "stage_id": "<stage_id>",
    "tenant_id": "<tenant>",
    "space_id": "<space>",
    "trace_id": "<trace_id>",
}

# Example log
context.logger.info(
    "Episodic clustering complete",
    extra={
        **LOG_CONTEXT,
        "clusters_formed": 12,
        "noise_points": 3,
        "duration_ms": 145,
    }
)
```

---

### D.10 Error Handling Integration

*Fault tolerance and recovery patterns.*

---

#### D.10.1 Module Failure Modes

*Core idea: Define explicit failure modes in module contracts.*

```yaml
# In module contract
failure_modes:
  - code: STORAGE_READ_FAILED
    policy: retry
    max_retries: 3
    backoff_ms: [100, 200, 400]

  - code: EMBEDDING_COMPUTATION_FAILED
    policy: fallback
    fallback_action: skip_embedding

  - code: CLUSTERING_TIMEOUT
    policy: partial_commit
    description: Commit completed clusters, retry remainder

  - code: KG_CONSTRAINT_VIOLATION
    policy: dlq
    description: Send to DLQ for manual review
```

---

#### D.10.2 Retry Scheduler Integration

*Core idea: Use RetryScheduler for exponential backoff.*

```python
# In module with retry logic
from k0.outbox.scheduler import RetryScheduler

async def run_with_retry(message: Any, context: Any, **config) -> dict[str, Any]:
    scheduler = RetryScheduler()
    attempt = config.get("retry_attempt", 0)

    try:
        return await run_core(message, context, **config)
    except StorageError as e:
        if scheduler.should_retry(attempt, max_attempts=3):
            delay = scheduler.calculate_delay(attempt)
            await asyncio.sleep(delay / 1000)
            return await run_with_retry(
                message, context,
                **{**config, "retry_attempt": attempt + 1}
            )
        raise
```

---

#### D.10.3 DLQ Integration

*Core idea: Use DLQStore for unrecoverable failures.*

```python
# In pipeline error handler
async def handle_unrecoverable_error(
    context: PipelineContext,
    message: BusMessage,
    error: Exception,
    stage_id: str
) -> None:
    await context.syscalls.record_dlq({
        "topic": message.topic,
        "payload": message.payload,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "stage_id": stage_id,
        "cycle_id": context.config.get("cycle_id"),
        "trace_id": message.trace_id,
        "recorded_at": int(time.time()),
    })

    context.logger.error(
        "Event sent to DLQ",
        extra={
            "error_type": type(error).__name__,
            "stage_id": stage_id,
            "trace_id": message.trace_id,
        }
    )
```

---

### D.11 Testing Strategy

*Test patterns for P03 modules and pipeline.*

---

#### D.11.1 Module Unit Test Pattern

*Core idea: Test modules in isolation with mocked context.*

```python
# tests/k0/modules/consolidation/test_importance_scorer.py

@pytest.fixture
def mock_context():
    return MockPipelineContext(
        syscalls=MockSyscalls(),
        logger=MockLogger(),
        config={"social_weight": 0.5, "affect_weight": 0.4}
    )

async def test_importance_scoring_high_affect(mock_context):
    message = create_mock_message(
        envelope={"sentiment_score": 0.9, "participants_count": 2}
    )

    result = await run(message, mock_context, envelope=message.envelope)

    assert result["importance_score"] > 0.7
    assert "importance_factors" in result
```

---

#### D.11.2 Pipeline Integration Test Pattern

*Core idea: Test full DAG execution with in-memory storage.*

```python
# tests/k0/pipelines/test_p03_consolidation.py

@pytest.fixture
async def p03_pipeline():
    spec = PipelineSpec.load("k0/contracts/pipelines/p03_consolidation.v1.yaml")
    registry = await create_test_module_registry()
    return PipelineRunner(spec, registry)

async def test_full_consolidation_cycle(p03_pipeline, test_db):
    # Seed test data
    await seed_hipp_events(test_db, count=100)

    # Create trigger message
    message = BusMessage(
        topic="p03.consolidation.trigger.v1",
        payload=b'{"trigger_type": "manual"}',
        offset=1,
        trace_id="test-trace-001"
    )

    # Execute pipeline
    await p03_pipeline.handle(message)

    # Verify results
    episodes = await test_db.query("st_epi", {})
    assert len(episodes) > 0

    events = await test_db.query("st_hipp_events", {"consolidation_status": "CONSOLIDATED"})
    assert len(events) == 100
```

---

#### D.11.3 Contract Compatibility Testing

*Core idea: Verify module contracts match implementation.*

```python
# tests/k0/contracts/test_consolidation_contracts.py

@pytest.mark.parametrize("contract_file", list_consolidation_contracts())
async def test_contract_matches_implementation(contract_file):
    contract = ModuleContract.load(contract_file)
    module = import_module(contract.implementation_path)

    # Verify run function exists
    assert hasattr(module, "run")
    assert asyncio.iscoroutinefunction(module.run)

    # Verify signature matches expected pattern
    sig = inspect.signature(module.run)
    params = list(sig.parameters.keys())
    assert params[:3] == ["message", "context", "config"]
```

---

### D.12 Implementation Roadmap

*Phased implementation plan for P03 kernel integration.*

---

#### D.12.1 Phase 1: Foundation (Week 1-2)

*Core idea: Establish pipeline structure and core modules.*

| Task | Deliverable | Priority |
|------|-------------|----------|
| Create pipeline contract | `p03_consolidation.v1.yaml` | P0 |
| Create module directory | `k0/modules/consolidation/` | P0 |
| Implement batch_selector | R0 event selection | P0 |
| Implement importance_scorer | R1 scoring | P0 |
| Implement episodic_clusterer | R2 DBSCAN | P0 |
| Implement episode_builder | R2 st_epi writes | P0 |
| Register with PipelineScheduler | Trigger configuration | P0 |

---

#### D.12.2 Phase 2: Core Reconciliation (Week 3-4)

*Core idea: Implement R3-R4 forgetting and KG building.*

| Task | Deliverable | Priority |
|------|-------------|----------|
| Implement simhash_deduplicator | R3 dedup | P0 |
| Implement decay_scorer | R3 decay | P0 |
| Implement prune_decider | R3 prune logic | P0 |
| Implement entity_extractor | R4 NER | P0 |
| Implement relationship_builder | R4 edges | P0 |
| Implement causal_inference | R4 Granger | P1 |

---

#### D.12.3 Phase 3: Dream Phase (Week 5-6)

*Core idea: Implement R5 creative algorithms (optional phase).*

| Task | Deliverable | Priority |
|------|-------------|----------|
| Implement counterfactual | R5 CPN | P1 |
| Implement forward_simulator | R5 TPN-MCTS | P1 |
| Implement insight_generator | R5 BGT-SM | P1 |
| Implement motor_rehearsal | R5 TDL-HCO | P2 |

---

#### D.12.4 Phase 4: Finalization (Week 7-8)

*Core idea: Complete writes, emission, testing, and documentation.*

| Task | Deliverable | Priority |
|------|-------------|----------|
| Implement status_updater | R6 status marks | P0 |
| Implement memory_writer | R7 atomic writes | P0 |
| Configure event_emitter | R8 events | P0 |
| Integration testing | Test suite | P0 |
| Performance profiling | Latency validation | P0 |
| P06 gap integration | Active learning | P1 |
| Documentation | README, ADR updates | P1 |

---

*End of Appendix D*

---

## Appendix E: Canonical Name Registry

> **Purpose**: Single source of truth for all identifiers used in P03. All references in this dossier, code, and configuration must use these canonical names.
> **Governance**: Changes require ADR approval and version bump.

---

### E.1 Pipeline Identifiers

| Canonical ID | Version | Description | Status |
|--------------|---------|-------------|--------|
| `P03_CONSOLIDATE` | v1 | Batch memory consolidation pipeline | Active |
| `P03_INCREMENTAL` | v1 | Event-driven incremental consolidation | Planned |

---

### E.2 Event Topics (Bus)

> **Naming Convention**: `p<pipeline_id>.<domain>.<action>.v<version>`
> **Registry**: Events to be added to [k0_architecture_master.md Part 4.1](../../k0/pipelines/k0_architecture_master.md#41-event-topics-registry) during implementation

#### E.2.1 P03 Entry Topics (Subscribe)

| Canonical Topic | Schema | Source | QoS Band | Retention (days) | Purpose |
|-----------------|--------|--------|----------|------------------|---------|
| `p03.consolidation.trigger.v1` | `P03TriggerEvent` | PipelineScheduler | AMBER | 7 | Initiate consolidation cycle |
| `p02.write.complete.v1` | `P02WriteComplete` | P02 | AMBER | 7 | (Optional) Incremental mode trigger |

#### E.2.2 P03 Exit Topics (Emit)

| Canonical Topic | Schema | Consumer | QoS Band | Retention (days) | Purpose |
|-----------------|--------|----------|----------|------------------|---------|
| `p03.consolidation.complete.v1` | `P03ConsolidationComplete` | Monitoring, P04 | AMBER | 7 | Cycle completion notification |
| `p03.phase.complete.v1` | `P03PhaseComplete` | Monitoring | GREEN | 3 | Per-phase progress tracking |
| `p03.episode.formed.v1` | `P03EpisodeFormed` | P04, P05 | AMBER | 7 | New episode created |
| `p03.pattern.discovered.v1` | `P03PatternDiscovered` | P04 | AMBER | 7 | New semantic pattern |
| `p03.truth.reinforced.v1` | `P03TruthReinforced` | Audit | GREEN | 3 | Existing truth strengthened |
| `p03.truth.created.v1` | `P03TruthCreated` | Audit | GREEN | 3 | New truth record created |
| `p03.truth.evolved.v1` | `P03TruthEvolved` | Audit | GREEN | 3 | Truth record versioned |
| `p03.memory.pruned.v1` | `P03MemoryPruned` | Audit | RED | 30 | Memory archived/tombstoned |
| `p03.gap.detected.v1` | `P03GapDetected` | P06 | AMBER | 7 | Knowledge gap for questioning |
| `p03.kg.updated.v1` | `P03KGUpdated` | P04 | AMBER | 7 | Knowledge graph changes |
| `p03.insight.generated.v1` | `P03InsightGenerated` | P05 | AMBER | 7 | R5 creative insight |

#### E.2.3 P06 Integration Topics

| Canonical Topic | Schema | Direction | QoS Band | Retention (days) | Purpose |
|-----------------|--------|-----------|----------|------------------|---------|
| `p06.gap.resolved.v1` | `P06GapResolved` | P06 → P03 | AMBER | 7 | User answered question |
| `p06.anchor.updated.v1` | `P06AnchorUpdated` | P06 → P03 | AMBER | 7 | Belief anchor refined |

> **QoS Bands**: GREEN = Best-effort, AMBER = Must deliver, RED = Critical/immediate

---

### E.3 Storage Tables

> **Naming Convention**: `st_<domain>` for staging/storage tables

#### E.3.1 Truth Layer Tables (8 Memory Layers)

| Canonical Table | Description | Primary Key | Partitioned By |
|-----------------|-------------|-------------|----------------|
| `st_epi` | Episodic memories (episodes) | `epi_id` | tenant_id, space_id |
| `st_sem` | Semantic patterns | `sem_id` | tenant_id, space_id |
| `st_procedural` | Habits and routines | `proc_id` | tenant_id, space_id |
| `st_social` | Social relationships | `social_id` | tenant_id, space_id |
| `st_prospective` | Intentions and goals | `prosp_id` | tenant_id, space_id |
| `st_kg_dom` | Knowledge graph entities | `entity_id` | tenant_id |
| `st_kg_edges` | Knowledge graph relationships | `edge_id` | tenant_id |
| `st_vec` | Embedding vectors (FAISS-backed) | `vec_id` | tenant_id, space_id |

#### E.3.2 Staging Tables

| Canonical Table | Description | Primary Key | Lifecycle |
|-----------------|-------------|-------------|-----------|
| `st_hipp_events` | Hippocampal staging (P02 writes) | `event_id` | Cleared after consolidation |

#### E.3.3 Support Tables

| Canonical Table | Description | Primary Key | Used By |
|-----------------|-------------|-------------|---------|
| `st_learning_queue` | Active learning gaps | `gap_id` | P03, P06 |
| `st_anchors` | Bayesian belief anchors | `anchor_id` | P03, P06 |
| `st_anchor_observations` | Anchor evidence history | `obs_id` | P03, P06 |
| `st_offsets` | Consumer offset tracking | `consumer_id` | K0 Bus |
| `st_pipeline_status` | Pipeline execution state | `pipeline_run_id` | K0 Scheduler |
| `st_outbox` | Transactional outbox | `outbox_id` | K0 Outbox |
| `st_retention_policy` | Per-space retention config | `policy_id` | P03, K0 |
| `st_dlq` | Dead letter queue | `dlq_id` | K0 DLQ |
| `st_consolidation_audit` | Consolidation decision log | `audit_id` | P03, Audit |

---

### E.4 Module Registry

> **Naming Convention**: `<domain>.<capability>:v<version>`
> **Implementation Path**: `k0/modules/consolidation/` (directory to be created)

#### E.4.1 P03-Specific Modules (M18-M25)

| Canonical Module ID | Short Name | Phase | Fabric Capability | Status | K0 Registry ID |
|---------------------|------------|-------|-------------------|--------|----------------|
| `consolidation.episodic_clusterer:v1` | M18 EpisodicClusterer | R2 | `cluster_episodes` | 📋 ADR Required | M28 (reserved) |
| `consolidation.duplicate_detector:v1` | M19 DuplicateDetector | R3 | `detect_duplicates` | 📋 ADR Required | M29 (reserved) |
| `consolidation.retention_enforcer:v1` | M20 RetentionEnforcer | R3 | `enforce_retention` | 📋 ADR Required | M30 (reserved) |
| `consolidation.kg_consolidator:v1` | M21 KGConsolidator | R4 | `consolidate_kg` | 📋 ADR Required | M31 (reserved) |
| `consolidation.dream_explorer:v1` | M22 DreamExplorer | R5 | `explore_dreams` | 📋 ADR Required | M32 (reserved) |
| `consolidation.replay_coordinator:v1` | M23 ReplayCoordinator | R1 | `coordinate_replay` | 📋 ADR Required | M33 (reserved) |
| `consolidation.truth_writer:v1` | M24 TruthWriter | R7 | `write_truth` | 📋 ADR Required | M34 (reserved) |
| `consolidation.gap_detector:v1` | M25 GapDetector | R8 | `detect_gaps` | 📋 ADR Required | M35 (reserved) |

> **Note**: Module IDs M18-M25 in dossier are logical identifiers. K0 registry IDs M28-M35 are reserved pending k010-series ADR acceptance. See [k0_architecture_master.md Part 3.1](../../k0/pipelines/k0_architecture_master.md#31-module-master-registry) for registry format.

#### E.4.2 P03 DAG Stage Modules

| Canonical Module ID | Stage ID | Phase | Status |
|---------------------|----------|-------|--------|
| `consolidation.batch_selector:v1` | stage_00_select_batch | R0 | 📋 Not Started |
| `consolidation.importance_scorer:v1` | stage_10_importance_score | R1 | 📋 Not Started |
| `consolidation.hebbian_learner:v1` | stage_11_hebbian_update | R1 | 📋 Not Started |
| `consolidation.episodic_clusterer:v1` | stage_20_episodic_cluster | R2 | 📋 Not Started |
| `consolidation.episode_builder:v1` | stage_21_episode_builder | R2 | 📋 Not Started |
| `consolidation.simhash_deduplicator:v1` | stage_30_simhash_dedup | R3 | 📋 Not Started |
| `consolidation.decay_scorer:v1` | stage_31_decay_scorer | R3 | 📋 Not Started |
| `consolidation.prune_decider:v1` | stage_32_prune_decider | R3 | 📋 Not Started |
| `consolidation.entity_extractor:v1` | stage_40_entity_extractor | R4 | 📋 Not Started |
| `consolidation.relationship_builder:v1` | stage_41_relationship_builder | R4 | 📋 Not Started |
| `consolidation.causal_inference:v1` | stage_42_causal_inference | R4 | 📋 Not Started |
| `consolidation.counterfactual:v1` | stage_50_counterfactual | R5 | 📋 Not Started |
| `consolidation.forward_simulator:v1` | stage_51_forward_sim | R5 | 📋 Not Started |
| `consolidation.insight_generator:v1` | stage_52_insight_gen | R5 | 📋 Not Started |
| `consolidation.status_updater:v1` | stage_60_status_update | R6 | 📋 Not Started |
| `consolidation.memory_writer:v1` | stage_70_memory_writer | R7 | 📋 Not Started |
| `core.event_emitter:v1` | stage_80_event_emitter | R8 | ✅ Exists (M17) |

> **Status Legend**: 📋 Not Started = Module to be created | ✅ Exists = Reuses existing K0 module

#### E.4.3 Reused Modules (from P02)

| Canonical Module ID | K0 Registry ID | Purpose in P03 | Status |
|---------------------|----------------|----------------|--------|
| `embedding.ultrabert:v1` | M02 | Embedding comparison | ✅ Production |
| `hashing.simhasher:v1` | M03 | Fingerprint comparison | 🎯 Planning |
| `entity.resolver:v1` | M06 | Entity deduplication | 🎯 Planning |
| `outbox.writer:v1` | M11 | Durable writes | ✅ Production |

---

### E.5 Fabric Capabilities

> **Naming Convention**: `<verb>_<noun>` (snake_case)

| Canonical Capability | Provider Module | Timeout (ms) | Description |
|---------------------|-----------------|--------------|-------------|
| `select_consolidation_batch` | `consolidation.batch_selector:v1` | 50 | Select pending events |
| `score_importance` | `consolidation.importance_scorer:v1` | 30 | Compute importance score |
| `score_salience` | `embedding.salience_scorer:v1` | 30 | (P02) Salience scoring |
| `update_cooccurrence` | `consolidation.hebbian_learner:v1` | 100 | Hebbian edge weights |
| `cluster_episodes` | `consolidation.episodic_clusterer:v1` | 200 | DBSCAN clustering |
| `build_episode` | `consolidation.episode_builder:v1` | 50 | Build st_epi record |
| `detect_duplicates` | `consolidation.simhash_deduplicator:v1` | 100 | SimHash dedup |
| `score_decay` | `consolidation.decay_scorer:v1` | 50 | Exponential decay |
| `decide_prune` | `consolidation.prune_decider:v1` | 30 | Prune/archive decision |
| `extract_entities` | `consolidation.entity_extractor:v1` | 150 | UltraBERT NER |
| `build_relationships` | `consolidation.relationship_builder:v1` | 100 | KG edge creation |
| `infer_causality` | `consolidation.causal_inference:v1` | 200 | Granger causality |
| `generate_counterfactuals` | `consolidation.counterfactual:v1` | 300 | CPN scenarios |
| `simulate_futures` | `consolidation.forward_simulator:v1` | 500 | TPN-MCTS |
| `generate_insights` | `consolidation.insight_generator:v1` | 400 | BGT-SM insights |
| `update_status` | `consolidation.status_updater:v1` | 30 | Mark event status |
| `write_memories` | `consolidation.memory_writer:v1` | 100 | Atomic truth writes |
| `detect_gaps` | `consolidation.gap_detector:v1` | 50 | P06 gap detection |
| `embedding.search` | P08 embedding pipeline | 100 | Vector similarity |

---

### E.6 Contract Files

> **Location**: `k0/contracts/`
> **Reference Format**: See [p02_write.v1.yaml](../../k0/contracts/pipelines/p02_write.v1.yaml) for pipeline contract template

| Canonical Path | Description | Status |
|----------------|-------------|--------|
| `k0/contracts/pipelines/p03_consolidation.v1.yaml` | Pipeline DAG contract | 📋 To Create |
| `k0/contracts/modules/consolidation.*.v1.yaml` | Module contracts (16 files) | 📋 To Create |
| `k0/contracts/events/p03_events.py` | Event schema definitions | 📋 To Create |
| `k0/contracts/capabilities/consolidation.yaml` | Capability registry | 📋 To Create |
| `k0/contracts/schemas/p03_config.json` | Configuration schema | 📋 To Create |

> **Implementation Note**: Contract files will be generated from dossier specifications during GATE 2 (Contract Discovery & Validation) per [copilot-instructions.md](../../.github/copilot-instructions.md).

---

### E.7 Configuration Keys

> **Prefix**: `p03.` for all P03 configuration

| Canonical Key | Type | Default | Description |
|---------------|------|---------|-------------|
| `p03.schedule.enabled` | bool | true | Enable scheduled consolidation |
| `p03.schedule.cron` | string | "0 3 ** *" | Cron schedule |
| `p03.schedule.interval_seconds` | int | 5400 | Interval trigger (90 min) |
| `p03.batch.size` | int | 1000 | Events per cycle |
| `p03.batch.max_events_per_cycle` | int | 10000 | Hard cap |
| `p03.batch.timeout_seconds` | int | 300 | Cycle timeout |
| `p03.reconciliation.thresholds.reinforce_min` | float | 0.85 | REINFORCE threshold |
| `p03.reconciliation.thresholds.extend_min` | float | 0.60 | EXTEND min threshold |
| `p03.reconciliation.thresholds.extend_max` | float | 0.85 | EXTEND max threshold |
| `p03.reconciliation.thresholds.contradict_threshold` | float | 0.30 | CONTRADICT threshold |
| `p03.reconciliation.thresholds.novelty_min` | float | 0.70 | CREATE novelty min |
| `p03.phases.r5_dream.enabled` | bool | true | Enable R5 phase |
| `p03.phases.r5_dream.skip_on_backlog` | bool | true | Skip R5 if backlogged |
| `p03.phases.r5_dream.backlog_threshold` | int | 5000 | Backlog threshold |
| `p03.active_learning.enabled` | bool | true | Enable P06 gap detection |
| `p03.active_learning.max_gaps_per_cycle` | int | 50 | Gap emission limit |
| `p03.concurrency.parallel_workers` | int | 4 | Worker count |
| `p03.concurrency.max_concurrent_cycles` | int | 2 | Concurrent cycles |

---

### E.8 Metrics Names

> **Prefix**: `p03_` for all P03 metrics

| Canonical Metric | Type | Labels | Description |
|------------------|------|--------|-------------|
| `p03_cycles_total` | counter | status | Total consolidation cycles |
| `p03_events_processed_total` | counter | decision_type | Events processed |
| `p03_episodes_created_total` | counter | - | Episodes created |
| `p03_patterns_discovered_total` | counter | pattern_type | Patterns discovered |
| `p03_kg_entities_total` | counter | entity_type | KG entities created |
| `p03_kg_edges_total` | counter | edge_type | KG edges created |
| `p03_gaps_detected_total` | counter | gap_type | P06 gaps detected |
| `p03_prune_total` | counter | action | Prune/archive actions |
| `p03_errors_total` | counter | error_type | Errors by type |
| `p03_cycle_duration_seconds` | histogram | - | Cycle duration |
| `p03_phase_duration_seconds` | histogram | phase | Per-phase duration |
| `p03_batch_size` | histogram | - | Batch size distribution |
| `p03_pending_events` | gauge | - | Pending event count |
| `p03_similarity_score` | histogram | decision_type | Similarity scores |
| `p03_confidence_score` | histogram | layer | Confidence distributions |

---

### E.9 Architecture Diagrams

> **Location**: `architecture_diagrams/k0/`

| Canonical Filename | Description | Referenced In |
|--------------------|-------------|---------------|
| `p03_consolidation_overview.mmd` | High-level pipeline flow | Section 3 |
| `p03_phase_state_machine.mmd` | R0-R8 state transitions | Section 4 |
| `p03_bidirectional_flow.mmd` | Truth reconciliation flow | Section 1 |
| `p03_storage_schema.mmd` | Table relationships | Section 6 |
| `p03_module_dependencies.mmd` | Module DAG | Section 7 |
| `p03_k0_integration.mmd` | K0 layer integration | Appendix D |

---

### E.10 ADR References

> **Alignment Note**: ADR numbering follows K0 Architecture Master (`k0/pipelines/k0_architecture_master.md` Part 7.1).
> P03 ADRs use the `k010.*-p03` series. Location: `docs/architecture/decisions-K0/pipelines/`

| ADR ID | Title | Status | Sections | Link |
|--------|-------|--------|----------|------|
| k010 | P03 Consolidation Architecture - Sleep-Cycle Memory Consolidation | 🎯 Draft | 1, 3, 4 | `docs/architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md` |
| k010.1-p03 | Sleep Cycle State Machine - NREM/REM Phase Transitions | 🎯 Draft | 4, Appendix G | `docs/architecture/decisions-K0/pipelines/k010.1-sleep-cycle-state-machine.md` |
| k010.2-p03 | Importance Scoring Formula - Recency × Affect × Social | 🎯 Draft | 4.1, Appendix C.2 | `docs/architecture/decisions-K0/pipelines/k010.2-importance-scoring-formula.md` |
| k010.3-p03 | Episodic Clustering Algorithm - DBSCAN on 768-dim Embeddings | 🎯 Draft | 4.2, Appendix C.3 | `docs/architecture/decisions-K0/pipelines/k010.3-episodic-clustering-algorithm.md` |
| k010.4-p03 | CA1 Bridge Decision Protocol - Episodic→Semantic Promotion | 🎯 Draft | 1.4, 4.4 | `docs/architecture/decisions-K0/pipelines/k010.4-ca1-bridge-decision-protocol.md` |
| k010.5-p03 | SimHash Deduplication - Near-Duplicate Detection Strategy | 🎯 Draft | 4.3, Appendix C.4 | `docs/architecture/decisions-K0/pipelines/k010.5-simhash-deduplication.md` |
| k010.6-p03 | Entity Normalization Strategy - KG Node Resolution | 🎯 Draft | 4.4, Appendix C.5 | `docs/architecture/decisions-K0/pipelines/k010.6-entity-normalization-strategy.md` |
| k010.7-p03 | 8-Layer Memory Write Coordination - Atomic Multi-Table Updates | 🎯 Draft | 6, 4.7 | `docs/architecture/decisions-K0/pipelines/k010.7-8-layer-memory-write-coordination.md` |
| k010.8-p03 | P08 Embedding Coordination - Backpressure and Queue Management | 🎯 Draft | 3.3, 15 | `docs/architecture/decisions-K0/pipelines/k010.8-p08-embedding-coordination.md` |
| k010.9-p03 | Capability-Based Security - P03 Storage Access Controls | 🎯 Draft | 14, Appendix D.7 | `docs/architecture/decisions-K0/pipelines/k010.9-capability-based-security.md` |
| k010.10-p03 | Dream Phase Algorithms - Counterfactual and Forward Simulation | 🎯 Draft | 4.5, Appendix C.6 | `docs/architecture/decisions-K0/pipelines/k010.10-dream-phase-algorithms.md` |
| k010.11-p03 | UltraBERT Data Consumption - P02 Pre-Computed NLP Outputs | 🎯 Draft | 3.3 | `docs/architecture/decisions-K0/pipelines/k010.11-ultrabert-data-consumption.md` |

**ADR Status Legend** (per k0_architecture_master.md):

- 📝 Draft: Initial writing, gathering feedback
- 👀 Review: Under formal review
- 🎯 Planning: Contracts defined, ready for implementation
- ✅ Accepted: Approved and active
- ⚠️ Deprecated: Superseded by newer ADR

---

*End of Appendix E*

---

## Appendix F: Threshold Configuration Table

> **Purpose**: Single source of truth for all P03 similarity and decision thresholds.
> **Governance**: Config-driven, testable, with explicit validation rules.

---

### F.1 Reconciliation Thresholds

| Threshold | Config Key | Default | Min | Max | Unit | Decision |
|-----------|------------|---------|-----|-----|------|----------|
| REINFORCE_MIN | `p03.reconciliation.thresholds.reinforce_min` | 0.85 | 0.80 | 0.95 | cosine | score >= threshold → REINFORCE |
| EXTEND_MIN | `p03.reconciliation.thresholds.extend_min` | 0.60 | 0.50 | 0.75 | cosine | score >= threshold → EXTEND |
| EXTEND_MAX | `p03.reconciliation.thresholds.extend_max` | 0.85 | 0.75 | 0.90 | cosine | score < threshold → not REINFORCE |
| CONTRADICT | `p03.reconciliation.thresholds.contradict` | 0.30 | 0.20 | 0.45 | cosine | score < threshold + conflict → CONTRADICT |
| NOVELTY_MIN | `p03.reconciliation.thresholds.novelty_min` | 0.70 | 0.60 | 0.85 | score | novelty >= threshold → CREATE |

---

### F.2 Decay Thresholds

| Threshold | Config Key | Default | Min | Max | Unit | Action |
|-----------|------------|---------|-----|-----|------|--------|
| PRUNE | `p03.decay.thresholds.prune` | 0.01 | 0.005 | 0.05 | decay | decay < threshold → TOMBSTONE |
| ARCHIVE | `p03.decay.thresholds.archive` | 0.10 | 0.05 | 0.20 | decay | decay < threshold → ARCHIVE |
| ACTIVE | `p03.decay.thresholds.active` | 0.30 | 0.20 | 0.50 | decay | decay >= threshold → ACTIVE |

---

### F.3 Confidence Thresholds

| Threshold | Config Key | Default | Min | Max | Unit | Behavior |
|-----------|------------|---------|-----|-----|------|----------|
| CANONICAL_MIN | `p03.confidence.thresholds.canonical_min` | 0.50 | 0.40 | 0.70 | confidence | confidence >= threshold → is_canonical |
| HIGH | `p03.confidence.thresholds.high` | 0.80 | 0.70 | 0.90 | confidence | Use without verification |
| MEDIUM | `p03.confidence.thresholds.medium` | 0.50 | 0.40 | 0.65 | confidence | Use with caution |
| LOW | `p03.confidence.thresholds.low` | 0.30 | 0.20 | 0.45 | confidence | Queue for P06 clarification |

---

### F.4 Active Learning Thresholds

| Threshold | Config Key | Default | Min | Max | Unit | Behavior |
|-----------|------------|---------|-----|-----|------|----------|
| GAP_ENTROPY_MIN | `p03.gaps.thresholds.entropy_min` | 0.50 | 0.30 | 0.70 | entropy | entropy >= threshold → detect gap |
| GAP_PRIORITY_HIGH | `p03.gaps.thresholds.priority_high` | 0.70 | 0.60 | 0.85 | priority | priority >= threshold → HIGH priority |
| GAP_PRIORITY_LOW | `p03.gaps.thresholds.priority_low` | 0.30 | 0.20 | 0.45 | priority | priority < threshold → LOW priority |
| ANCHOR_DRIFT | `p03.anchors.thresholds.drift` | 0.40 | 0.25 | 0.55 | divergence | divergence >= threshold → split anchor |

---

### F.5 Performance Thresholds

| Threshold | Config Key | Default | Min | Max | Unit | Behavior |
|-----------|------------|---------|-----|-----|------|----------|
| BATCH_SIZE | `p03.batch.size` | 1000 | 100 | 5000 | events | Events per consolidation cycle |
| BATCH_TIMEOUT | `p03.batch.timeout_seconds` | 300 | 60 | 600 | seconds | Max cycle duration |
| BACKLOG_THRESHOLD | `p03.r5.backlog_threshold` | 5000 | 1000 | 10000 | events | Skip R5 if pending > threshold |
| CONCURRENT_CYCLES | `p03.concurrency.max_cycles` | 2 | 1 | 4 | cycles | Max parallel cycles |

---

### F.6 Threshold Validation Rules

```python
def validate_threshold_config(config: P03ThresholdConfig) -> List[str]:
    """Validate threshold configuration constraints."""
    errors = []

    # Reconciliation ordering
    if config.contradict >= config.extend_min:
        errors.append("contradict must be < extend_min")
    if config.extend_min >= config.extend_max:
        errors.append("extend_min must be < extend_max")
    if config.extend_max > config.reinforce_min:
        errors.append("extend_max must be <= reinforce_min")

    # Decay ordering
    if config.prune >= config.archive:
        errors.append("prune must be < archive")
    if config.archive >= config.active:
        errors.append("archive must be < active")

    # Confidence ordering
    if config.low >= config.medium:
        errors.append("low must be < medium")
    if config.medium >= config.high:
        errors.append("medium must be < high")

    return errors
```

---

### F.7 Testing Requirements

Each threshold must have:

- [ ] Unit test verifying boundary conditions
- [ ] Integration test with golden dataset
- [ ] Performance test verifying no regression when threshold changes

---

*End of Appendix F*

---

## Appendix G: R0-R8 State Machine Specification

> **Purpose**: Formal state machine definition for each consolidation phase.
> **Governance**: Each phase is atomic, idempotent, and independently retriable.

---

### G.1 State Machine Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              P03 CONSOLIDATION STATE MACHINE                                        │
│                                                                                                     │
│   ┌─────┐    ┌─────┐    ┌─────┐    ┌─────┐    ┌─────┐    ┌─────┐    ┌─────┐    ┌─────┐    ┌─────┐  │
│   │ R0  │───▶│ R1  │───▶│ R2  │───▶│ R3  │───▶│ R4  │───▶│ R5  │───▶│ R6  │───▶│ R7  │───▶│ R8  │  │
│   │INIT │    │SCORE│    │CLUST│    │PRUNE│    │  KG │    │DREAM│    │STAGE│    │WRITE│    │EMIT │  │
│   └──┬──┘    └──┬──┘    └──┬──┘    └──┬──┘    └──┬──┘    └──┬──┘    └──┬──┘    └──┬──┘    └──┬──┘  │
│      │          │          │          │          │          │          │          │          │      │
│      ▼          ▼          ▼          ▼          ▼          ▼          ▼          ▼          ▼      │
│   [INIT]     [PROC]     [PROC]     [PROC]     [PROC]     [SKIP]     [PROC]     [PROC]     [DONE]   │
│   [FAIL]     [FAIL]     [FAIL]     [FAIL]     [FAIL]     [PROC]     [FAIL]     [FAIL]     [FAIL]   │
│              [SKIP]     [SKIP]                           [FAIL]                                     │
│                                                                                                     │
│   Legend:                                                                                           │
│   ──▶ Normal flow       [INIT] Initial state    [PROC] Processing    [DONE] Complete              │
│   ╌╌▶ Error path        [FAIL] Failed (DLQ)     [SKIP] Skipped (conditional)                      │
│                                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### G.2 Phase Specifications

#### R0: Batch Selection (INIT)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Select pending events from st_hipp_events for this cycle |
| **Inputs** | st_hipp_events (WHERE consolidation_status = 'PENDING') |
| **Outputs** | BatchContext with event_ids, batch_id, cycle_id |
| **DB Reads** | st_hipp_events, st_pipeline_status |
| **DB Writes** | st_pipeline_status (cycle started) |
| **Idempotency Key** | `p03:cycle:{cycle_ulid}` |
| **Retryable** | Yes |
| **DLQ Condition** | DB connection failure after 3 retries |
| **Timeout** | 30 seconds |
| **Max Batch Size** | `p03.batch.size` (default: 1000) |

```python
@dataclass
class R0Output:
    cycle_id: str  # ULID
    batch_id: str  # SHA256(sorted(event_ids))[:16]
    event_ids: List[str]
    batch_size: int
    started_at: int  # Unix ms
```

---

#### R1: Importance Scoring (SCORE)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Compute importance score for each event; update co-occurrence edges |
| **Inputs** | R0Output (event_ids) |
| **Outputs** | List[ScoredEvent] with importance_score, hebbian_updates |
| **DB Reads** | st_hipp_events, st_kg_edges, st_vec |
| **DB Writes** | None (in-memory enrichment) |
| **Idempotency Key** | `p03:r1:{cycle_ulid}:{batch_hash}` |
| **Retryable** | Yes |
| **DLQ Condition** | P08 embedding service unavailable |
| **Timeout** | 60 seconds |
| **Skip Condition** | Never (required phase) |

```python
@dataclass
class R1Output:
    scored_events: List[ScoredEvent]
    hebbian_updates: List[EdgeUpdate]  # Deferred to R7
    total_importance: float
    avg_importance: float
```

---

#### R2: Episodic Clustering (CLUST)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Cluster events into episodes using DBSCAN |
| **Inputs** | R1Output (scored_events with embeddings) |
| **Outputs** | List[EpisodeCluster] with centroid, member_events |
| **DB Reads** | st_vec (embeddings), st_epi (existing episodes for merge check) |
| **DB Writes** | None (in-memory) |
| **Idempotency Key** | `p03:r2:{cycle_ulid}:{batch_hash}` |
| **Retryable** | Yes |
| **DLQ Condition** | Clustering algorithm timeout |
| **Timeout** | 120 seconds |
| **Skip Condition** | batch_size < 2 (single event = micro-episode) |

```python
@dataclass
class R2Output:
    clusters: List[EpisodeCluster]
    noise_events: List[str]  # Events not clustered
    cluster_count: int
    avg_cluster_size: float
```

---

#### R3: Forgetting/Pruning (PRUNE)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Deduplicate via SimHash; apply decay; mark prune/archive candidates |
| **Inputs** | R2Output (clusters) |
| **Outputs** | PruneDecisions with dedup_merges, decay_updates, prune_candidates |
| **DB Reads** | st_hipp_events (simhash), st_epi, st_sem, st_kg_edges (for decay) |
| **DB Writes** | None (deferred to R7) |
| **Idempotency Key** | `p03:r3:{cycle_ulid}:{batch_hash}` |
| **Retryable** | Yes |
| **DLQ Condition** | None (always succeeds) |
| **Timeout** | 60 seconds |
| **Skip Condition** | Never |

```python
@dataclass
class R3Output:
    dedup_merges: List[Tuple[str, str]]  # (duplicate_id, canonical_id)
    decay_updates: List[DecayUpdate]  # Deferred to R7
    archive_candidates: List[str]  # record_ids to archive
    prune_candidates: List[str]  # record_ids to tombstone
    novelty_scores: Dict[str, float]
```

---

#### R4: Knowledge Graph Building (KG)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Extract entities; build relationships; infer causality |
| **Inputs** | R2Output (clusters), R3Output (novelty scores) |
| **Outputs** | KGUpdates with new_entities, new_edges, causal_edges |
| **DB Reads** | st_kg_dom, st_kg_edges (for dedup/merge) |
| **DB Writes** | None (deferred to R7) |
| **Idempotency Key** | `p03:r4:{cycle_ulid}:{batch_hash}` |
| **Retryable** | Yes |
| **DLQ Condition** | Entity resolution service failure |
| **Timeout** | 90 seconds |
| **Skip Condition** | Never |

```python
@dataclass
class R4Output:
    new_entities: List[KGEntity]
    updated_entities: List[KGEntityUpdate]
    new_edges: List[KGEdge]
    updated_edges: List[KGEdgeUpdate]
    causal_edges: List[CausalEdge]  # From Granger inference
    gap_candidates: List[GapCandidate]  # For R8
```

---

#### R5: Dream Exploration (DREAM)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Counterfactual simulation; insight generation; motor rehearsal |
| **Inputs** | R2-R4 outputs |
| **Outputs** | DreamResults with counterfactuals, insights, optimizations |
| **DB Reads** | st_epi, st_sem, st_procedural, st_prospective |
| **DB Writes** | None (deferred to R7) |
| **Idempotency Key** | `p03:r5:{cycle_ulid}:{batch_hash}` |
| **Retryable** | Yes |
| **DLQ Condition** | MCTS timeout |
| **Timeout** | 120 seconds (configurable) |
| **Skip Condition** | `p03.r5.skip_on_backlog=true` AND pending > backlog_threshold |

```python
@dataclass
class R5Output:
    counterfactuals: List[CounterfactualScenario]
    insights: List[Insight]
    routine_optimizations: List[RoutineOptimization]
    prospective_memories: List[ProspectiveMemory]
    skipped: bool
    skip_reason: Optional[str]
```

---

#### R6: Status Staging (STAGE)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Mark st_hipp_events with consolidation decisions; stage reconciliation |
| **Inputs** | R1-R5 outputs (all decisions) |
| **Outputs** | StagedDecisions ready for atomic write |
| **DB Reads** | st_hipp_events (for version check) |
| **DB Writes** | None (preparation only) |
| **Idempotency Key** | `p03:r6:{cycle_ulid}:{event_id}` |
| **Retryable** | Yes |
| **DLQ Condition** | Version conflict on >10% of events |
| **Timeout** | 30 seconds |
| **Skip Condition** | Never |

```python
@dataclass
class R6Output:
    staged_event_updates: List[EventStatusUpdate]
    staged_truth_writes: List[TruthWrite]
    staged_kg_writes: List[KGWrite]
    staged_outbox_events: List[OutboxEvent]
    reconciliation_summary: ReconciliationSummary
```

---

#### R7: Memory Writing (WRITE)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Atomic write to all truth layers via UnitOfWork |
| **Inputs** | R6Output (staged writes) |
| **Outputs** | WriteResult with success/failure per record |
| **DB Reads** | None |
| **DB Writes** | st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges, st_vec, st_hipp_events, st_outbox |
| **Idempotency Key** | `p03:r7:{cycle_ulid}:{table}:{record_id}` |
| **Retryable** | Yes (with optimistic locking) |
| **DLQ Condition** | Transaction failure after 3 retries |
| **Timeout** | 60 seconds |
| **Skip Condition** | Never (required phase) |

```python
@dataclass
class R7Output:
    records_written: int
    records_failed: int
    tables_touched: Set[str]
    transaction_id: str
    duration_ms: int
```

---

#### R8: Event Emission (EMIT)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Emit completion events; detect and emit P06 gaps |
| **Inputs** | R7Output, R4Output (gap_candidates) |
| **Outputs** | EmitResult with events published |
| **DB Reads** | st_outbox (for pending events) |
| **DB Writes** | st_outbox (mark as sent), st_learning_queue (gaps) |
| **Idempotency Key** | `p03:r8:{cycle_ulid}:{topic}:{offset}` |
| **Retryable** | Yes |
| **DLQ Condition** | Event bus unavailable |
| **Timeout** | 30 seconds |
| **Skip Condition** | Never |

```python
@dataclass
class R8Output:
    events_emitted: int
    gaps_detected: int
    cycle_completed: bool
    cycle_duration_ms: int
    next_cycle_eta: Optional[int]
```

---

### G.3 State Transition Rules

| Current State | Event | Next State | Condition |
|---------------|-------|------------|-----------|
| IDLE | trigger | R0.INIT | Scheduler fires |
| R0.INIT | batch_selected | R1.PROC | batch_size > 0 |
| R0.INIT | no_events | IDLE | batch_size = 0 |
| R0.INIT | db_error | R0.FAIL | After 3 retries |
| R1.PROC | scored | R2.PROC | Always |
| R1.PROC | p08_unavailable | R1.FAIL | Circuit breaker open |
| R2.PROC | clustered | R3.PROC | Always |
| R2.PROC | batch_too_small | R2.SKIP | batch_size < 2 |
| R3.PROC | pruned | R4.PROC | Always |
| R4.PROC | kg_built | R5.PROC | r5.enabled=true AND !backlogged |
| R4.PROC | kg_built | R6.PROC | r5.enabled=false OR backlogged |
| R5.PROC | dreamed | R6.PROC | Always |
| R5.SKIP | skipped | R6.PROC | Backlog condition |
| R6.PROC | staged | R7.PROC | Always |
| R7.PROC | written | R8.PROC | Always |
| R7.PROC | write_failed | R7.FAIL | After 3 retries |
| R8.PROC | emitted | IDLE | Cycle complete |
| *.FAIL | dlq_recorded | IDLE | Event in st_dlq |

---

### G.4 Error Recovery Matrix

> **PostgreSQL Migration Note** (2025-01): Updated error types for asyncpg.
> `DB_LOCKED` replaced with `LOCK_TIMEOUT` (PostgreSQL `55P03` / asyncpg `LockNotAvailableError`).
> See `k0/drivers/postgres.py` for error handling patterns.

| Phase | Error Type | Recovery Strategy | Max Retries | Backoff |
|-------|------------|-------------------|-------------|---------|
| R0 | DB_TIMEOUT | Retry with backoff | 3 | Exponential |
| R0 | LOCK_TIMEOUT | Wait and retry (pg_advisory_lock timeout) | 5 | Linear |
| R0 | POOL_EXHAUSTED | Queue, wait for connection | 3 | Exponential |
| R1 | P08_UNAVAILABLE | Use cached embeddings | 1 | N/A |
| R1 | EMBEDDING_TIMEOUT | Skip event, log | 0 | N/A |
| R2 | CLUSTER_TIMEOUT | Reduce batch, retry | 2 | N/A |
| R3 | SIMHASH_ERROR | Skip dedup, continue | 0 | N/A |
| R4 | NER_TIMEOUT | Skip entities, continue | 0 | N/A |
| R5 | MCTS_TIMEOUT | Skip R5, continue | 0 | N/A |
| R6 | VERSION_CONFLICT | Re-read, re-stage | 3 | Immediate |
| R6 | UNIQUE_VIOLATION | Check existing, skip/merge | 1 | Immediate |
| R7 | TRANSACTION_FAIL | Full cycle retry | 3 | Exponential |
| R7 | SERIALIZATION_FAIL | Retry with fresh read | 3 | Immediate |
| R8 | BUS_UNAVAILABLE | Queue locally, retry | 10 | Exponential |

---

### G.5 Metrics Per Phase

| Phase | Metrics Emitted |
|-------|-----------------|
| R0 | `p03_r0_batch_size`, `p03_r0_duration_ms` |
| R1 | `p03_r1_duration_ms`, `p03_r1_avg_importance` |
| R2 | `p03_r2_duration_ms`, `p03_r2_clusters`, `p03_r2_noise_count` |
| R3 | `p03_r3_duration_ms`, `p03_r3_dedup_count`, `p03_r3_prune_count` |
| R4 | `p03_r4_duration_ms`, `p03_r4_entities`, `p03_r4_edges`, `p03_r4_gaps` |
| R5 | `p03_r5_duration_ms`, `p03_r5_insights`, `p03_r5_skipped` |
| R6 | `p03_r6_duration_ms`, `p03_r6_staged_count` |
| R7 | `p03_r7_duration_ms`, `p03_r7_writes`, `p03_r7_failures` |
| R8 | `p03_r8_duration_ms`, `p03_r8_events_emitted`, `p03_r8_gaps_detected` |

---

*End of Appendix G*

---

## Appendix H: UltraBERT Model Specification

> **Status**: COMPLETE
> **Model Version**: v2.2.1 (familyos-ultrabert)
> **Source**: [GitHub Releases](https://github.com/ComparativeIntelligenceGroup/ultrabert/releases)

### H.1 Model Overview

UltraBERT is the primary embedding and multi-task classification model used throughout P03 consolidation.

| Property | Value |
|----------|-------|
| **Package Name** | `familyos-ultrabert` |
| **Target Version** | v2.2.1 |
| **Architecture** | BERT-based encoder (12 encoders, 768-dim) |
| **Parameters** | 155M (15% pruned from original) |
| **Embedding Dimension** | 768-dim |
| **Quantization** | INT8 (ONNX) |
| **Memory Footprint** | ~175MB (quantized) |
| **First-Call Latency** | ~17ms (with warmup) |
| **Throughput** | ~500 samples/sec (batch=32) |

### H.2 Encoder Capabilities

UltraBERT v2.2.1 provides 12 encoder capabilities used by P03:

| Capability | P03 Usage | Description |
|------------|-----------|-------------|
| `sentiment` | R1 Importance Scoring | Polarity detection for emotional weight |
| `emotions` | R1 Importance Scoring | Multi-label emotion classification |
| `safety_familyos` | R0 Pre-filter | Family-context safety classification |
| `safety_generic` | R0 Pre-filter | General content safety |
| `intent` | R4 KG Consolidation | User intent classification |
| `ingress` | R0 Pre-filter | Message type routing |
| `ner_family` | R4 Entity Extraction | Family-context NER (relationships, nicknames) |
| `ner_general` | R4 Entity Extraction | General NER (persons, locations, orgs) |
| `temporal` | R1 Temporal Clustering | Time expression extraction |
| `relation` | R4 Edge Creation | Relationship type classification |
| `nli` | R7 Contradiction Detection | Natural language inference |
| `embedding` | R1, R2, R4 | 768-dim semantic embeddings |

### H.3 Performance Benchmarks

| Metric | Value | Notes |
|--------|-------|-------|
| **Weighted Accuracy** | 89.60% | Across all 12 capabilities |
| **Crisis Detection Recall** | 100% | Critical for safety pipeline |
| **NER F1 (Family)** | 92.3% | Family-context entities |
| **NER F1 (General)** | 88.7% | Standard NER benchmark |
| **Embedding Similarity** | 0.91 | Cosine correlation with SBERT |

### H.4 Client API Usage

P03 uses the UltraBERT Client API with auto-warmup:

```python
from familyos_ultrabert import UltraBertClient

# Initialize with auto-warmup (recommended)
client = UltraBertClient(
    backend="onnx",  # or "pytorch"
    warmup=True,
    quantized=True
)

# Get embeddings for truth query (R1, R4)
embeddings = client.encode(
    texts=["User mentioned hiking with Sarah"],
    normalize=True  # L2 normalize for cosine similarity
)

# Multi-task classification (R1)
results = client.predict(
    texts=["Had an amazing dinner at the Thai restaurant!"],
    tasks=["sentiment", "emotions", "ner_general"]
)
```

### H.5 Backend Selection

| Backend | Use Case | Performance |
|---------|----------|-------------|
| **ONNX (INT8)** | Production (default) | ~175MB, ~17ms latency |
| **PyTorch (FP32)** | Development/debugging | ~620MB, ~45ms latency |
| **PyTorch (FP16)** | GPU environments | ~310MB, ~8ms latency |

### H.6 Versioning Strategy

| Version | Status | Notes |
|---------|--------|-------|
| v2.0.x | Deprecated | Initial encoder release |
| v2.1.x | Supported | Added family-context NER |
| **v2.2.1** | **Current** | INT8 quantization, performance optimizations |
| v3.0.x | Future | Decoder capabilities (out of P03 scope) |

> **Note**: P03 targets v2.2.1 encoder capabilities only. Decoder releases (v3.0+) are not consumed by P03.

### H.7 P03 Integration Points

| Phase | UltraBERT Usage |
|-------|----------------|
| **R0** | `safety_familyos`, `safety_generic`, `ingress` for pre-filtering |
| **R1** | `embedding` for truth query, `sentiment`/`emotions` for importance |
| **R2** | `embedding` for episode clustering (DBSCAN) |
| **R4** | `ner_family`, `ner_general`, `relation` for KG consolidation |
| **R7** | `nli` for contradiction detection during truth write |

### H.8 Model Artifact Location

| Artifact | Location |
|----------|----------|
| **Wheel Package** | `wheels/familyos_ultrabert-2.1.0-py3-none-any.whl` |
| **ONNX Model** | Downloaded on first use to `~/.cache/ultrabert/` |
| **PyTorch Model** | Downloaded on first use to `~/.cache/ultrabert/` |
| **Config Files** | Bundled in wheel package |

> **Update Path**: Wheel in `wheels/` directory should be updated to v2.2.1 when available.

---

*End of Appendix H*
