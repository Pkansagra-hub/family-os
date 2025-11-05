# Architecture Decision Records (ADRs) - K1 Intelligence Module

**Last Updated:** October 10, 2025
**Total ADRs:** 47 (0 completed, 47 in progress)
**Status:** Planning Phase

---

## 📚 What are ADRs?

Architecture Decision Records (ADRs) document significant architectural decisions made during the development of the K1 Intelligence Module. Each ADR captures:

- **Context:** Why we needed to make a decision
- **Decision:** What we decided to do
- **Alternatives:** What other options we considered
- **Consequences:** The impact (positive and negative) of our decision

ADRs are **immutable** once accepted. If a decision needs to change, we create a new ADR that supersedes the old one.

---

## 🎯 ADR Categories

### Core Architecture (10 ADRs)
Foundational decisions about system structure and design patterns

### Serialization & Contracts (6 ADRs)
Decisions about data formats and API contracts

### State Management (7 ADRs)
Decisions about how state is stored, cached, and managed

### Performance & Optimization (8 ADRs)
Decisions about performance targets and optimization strategies

### Security & Privacy (8 ADRs)
Decisions about security controls and privacy protections

### Communication & Integration (8 ADRs)
Decisions about APIs and system integration

---

## 📋 All ADRs (By Number)

### Phase 1: Critical Foundation (Week 1) - 20 ADRs

#### Core Architecture
- [ADR-0001](0001-k0-k1-kernel-split.md) - K0/K1 Kernel Split Architecture ⏳ *Not Started*
- [ADR-0002](0002-actor-model-agent-isolation.md) - Actor Model for Agent Isolation ⏳ *Not Started*
- [ADR-0003](0003-mpst-protocol-validation.md) - MPST Protocol Validation ⏳ *Not Started*
- [ADR-0004](0004-52-module-5-layer-architecture.md) - 52-Module 5-Layer Architecture ⏳ *Not Started*
- [ADR-0005](0005-agent-lifecycle-fsm.md) - Agent Lifecycle FSM (6 States) ⏳ *Not Started*
- [ADR-0006](0006-3-phase-orchestration.md) - 3-Phase Orchestration Pattern ⏳ *Not Started*
- [ADR-0007](0007-4-stage-planning-pipeline.md) - 4-Stage Planning Pipeline ⏳ *Not Started*
- [ADR-0008](0008-saga-pattern-error-recovery.md) - Saga Pattern for Error Recovery ⏳ *Not Started*
- [ADR-0009](0009-circuit-breaker-pattern.md) - Circuit Breaker Pattern ⏳ *Not Started*
- [ADR-0010](0010-capability-based-security.md) - Capability-Based Security ⏳ *Not Started*

#### Serialization & Contracts
- [ADR-0011](0011-flatbuffers-serialization.md) - FlatBuffers for All Contracts ⏳ *Not Started*
- [ADR-0012](0012-76-flatbuffers-schemas.md) - 76 FlatBuffers Schemas ⏳ *Not Started*
- [ADR-0015](0015-websocket-binary-protocol.md) - WebSocket Binary Protocol ⏳ *Not Started*

#### State Management
- [ADR-0017](0017-sessionstate-6-section-design.md) - SessionState 6-Section Design ⏳ *Not Started*
- [ADR-0018](0018-3-tier-eviction-strategy.md) - 3-Tier Eviction Strategy ⏳ *Not Started*
- [ADR-0020](0020-multi-tier-storage.md) - Multi-Tier Storage (Hot/Warm/Cold) ⏳ *Not Started*

#### Security & Privacy
- [ADR-0032](0032-band-based-egress-rules.md) - Band-Based Egress Rules ⏳ *Not Started*
- [ADR-0033](0033-3-tier-sandbox-strategy.md) - 3-Tier Sandbox Strategy ⏳ *Not Started*
- [ADR-0036](0036-e2ee-red-band.md) - E2EE for RED Band ⏳ *Not Started*
- [ADR-0038](0038-audit-trail-k0-receipts.md) - Audit Trail to K0 Receipts ⏳ *Not Started*

---

### Phase 2: Implementation Support (Week 2) - 17 ADRs

#### Serialization & Contracts
- [ADR-0013](0013-pipeline-versioning-policy.md) - Pipeline Versioning Policy ⏳ *Not Started*
- [ADR-0014](0014-json-rest-api-option.md) - JSON for REST API (Option) ⏳ *Not Started*
- [ADR-0016](0016-sse-event-schemas.md) - SSE Event Schemas (17 Types) ⏳ *Not Started*

#### State Management
- [ADR-0019](0019-flatbuffers-sessionstate.md) - FlatBuffers SessionState Serialization ⏳ *Not Started*
- [ADR-0021](0021-turn-history-retention.md) - Turn History Retention Policies ⏳ *Not Started*
- [ADR-0022](0022-k0-bridge-bounded-batching.md) - K0 Bridge Bounded Batching ⏳ *Not Started*
- [ADR-0023](0023-cursor-based-pagination.md) - Cursor-Based Turn Pagination ⏳ *Not Started*

#### Performance & Optimization
- [ADR-0024](0024-performance-budgets.md) - Performance Budgets (P95 Targets) ⏳ *Not Started*
- [ADR-0025](0025-kv-cache-management.md) - KV Cache Management (512MB) ⏳ *Not Started*
- [ADR-0026](0026-thermal-hysteresis-matrix.md) - Thermal Hysteresis Matrix ⏳ *Not Started*
- [ADR-0027](0027-model-placement-cascade.md) - Model Placement Cascade ⏳ *Not Started*

#### Security & Privacy
- [ADR-0034](0034-mcp-protocol-tool-sandbox.md) - MCP Protocol for Tool Sandboxing ⏳ *Not Started*
- [ADR-0035](0035-pii-detection-redaction.md) - PII Detection & Redaction ⏳ *Not Started*
- [ADR-0037](0037-jwt-authentication.md) - JWT Authentication ⏳ *Not Started*
- [ADR-0039](0039-privacy-band-overrides.md) - Privacy Band Overrides ⏳ *Not Started*

#### Communication & Integration
- [ADR-0040](0040-websocket-realtime-chat.md) - WebSocket for Real-Time Chat ⏳ *Not Started*
- [ADR-0041](0041-rest-api-session-management.md) - REST API for Session Management ⏳ *Not Started*

---

### Phase 3: Optimization & Integration (Week 3) - 10 ADRs

#### Performance & Optimization
- [ADR-0028](0028-weighted-fair-queuing.md) - Weighted Fair Queuing Scheduler ⏳ *Not Started*
- [ADR-0029](0029-prometheus-metrics-red.md) - Prometheus Metrics (RED Method) ⏳ *Not Started*
- [ADR-0030](0030-intelligent-trace-sampling.md) - Intelligent Trace Sampling ⏳ *Not Started*
- [ADR-0031](0031-cost-tracking-per-session.md) - Cost Tracking Per Session ⏳ *Not Started*

#### Communication & Integration
- [ADR-0042](0042-k0-sse-event-streaming.md) - K0 SSE for Event Streaming ⏳ *Not Started*
- [ADR-0043](0043-60-sse-topic-taxonomy.md) - 60+ SSE Topic Taxonomy ⏳ *Not Started*
- [ADR-0044](0044-k0-bridge-http2-flatbuffers.md) - K0 Bridge HTTP/2 + FlatBuffers ⏳ *Not Started*
- [ADR-0045](0045-agent-agent-sse-coordination.md) - Agent-to-Agent SSE Coordination ⏳ *Not Started*
- [ADR-0046](0046-sse-websocket-bridge.md) - SSE → WebSocket Bridge ⏳ *Not Started*
- [ADR-0047](0047-openapi-3-1-rest-specs.md) - OpenAPI 3.1 for REST Specs ⏳ *Not Started*

---

### Phase 4: Operations & Multi-Device (M2-M5) - 4 ADRs **✅ NEW Q1 DECISION**

#### Multi-Device Family Sync (Device-First, Privacy-First)
- [ADR-0050](0050-multi-device-family-sync-strategy.md) - Multi-Device Family Sync Strategy ✅ **ACCEPTED** (Parent ADR)
  - **Purpose:** Q1 resolution for device-to-device family memory sync (no cloud intermediary)
  - **Scope:** All family devices (iOS, Android, macOS, Windows), three sync scenarios (LAN, Internet, Cross-border)
  - **Approach:** Hybrid Phase 1 (mDNS LAN) + Phase 2 (P2P E2EE internet)
  - **Status:** ✅ Complete (22.1 KB, 434 lines)

  - **Child ADRs:**
    - [ADR-0050a](0050a-sessionstate-coherence-guarantees.md) - SessionState Coherence Guarantees ✅ **ACCEPTED**
      - **Purpose:** Per-device consistency model (read-your-write, monotonic reads)
      - **Scope:** K0 local store per device
      - **Status:** ✅ Complete (child: coherence guarantees)

    - [ADR-0050b](0050b-crdt-device-to-device-merge.md) - CRDT Device-to-Device Merge ✅ **ACCEPTED**
      - **Purpose:** Conflict resolution for simultaneous writes across devices
      - **Algorithm:** Last-Write-Wins (LWW) + device ID ordering + vector clocks
      - **Status:** ✅ Complete (10.8 KB, 352 lines)

    - [ADR-0050c](0050c-lan-first-sync-implementation.md) - LAN-First Sync Implementation ✅ **ACCEPTED** (Phase 1)
      - **Purpose:** MVP sync over local WiFi using mDNS + TCP P07 channel
      - **Tech:** RFC 6762 multicast DNS discovery, FlatBuffers, 5s sync loop
      - **Timeline:** M2-M3 (4-5 weeks), manual "Sync Now" button for remote
      - **Status:** ✅ Complete (12.4 KB, 387 lines)

    - [ADR-0050d](0050d-p2p-e2ee-internet-sync.md) - P2P E2EE Internet Sync ✅ **ACCEPTED** (Phase 2)
      - **Purpose:** Remote device sync without cloud intermediary
      - **Tech:** Device certificates (Ed25519/X25519), STUN NAT traversal, QUIC, ChaCha20-Poly1305 AEAD
      - **Timeline:** M4-M5 (parallel, full rollout M5-W4)
      - **Status:** ✅ Complete (12.2 KB, 387 lines)

---

---

### Phase 5: HITL Extensions & Advanced Workflows (M3-M4) - 20 ADRs

#### HITL Extensions (4 ADRs + 4 sub-ADRs)
- [ADR-0052](0052-hitl-extensions-overview.md) - HITL Extensions Overview ⏳ *Not Started* (Parent)
  - [ADR-0052a](0052a-step-by-step-approval.md) - Step-by-Step Approval ⏳ *Not Started*
  - [ADR-0052b](0052b-red-band-approval-two-person-rule.md) - Red-Band Approval (Two-Person) ⏳ *Not Started*
  - [ADR-0052c](0052c-nested-clarification-chains-history.md) - Nested Clarifications ⏳ *Not Started*
  - [ADR-0052d](0052d-proactive-risk-confirmation.md) - Proactive Risk Confirmation ⏳ *Not Started*

#### Message Queue & Coalescing (1 ADR + 3 sub-ADRs)
- [ADR-0053](0053-message-queue-coalescing.md) - Message Queue & Coalescing ⏳ *Not Started* (Parent)
  - [ADR-0053a](0053a-coalesce-window-limits.md) - Coalesce Window & Limits ⏳ *Not Started*
  - [ADR-0053b](0053b-rate-limits-bursts.md) - Rate Limits & Bursts ⏳ *Not Started*
  - [ADR-0053c](0053c-cancel-path-p95.md) - Cancel Path P95 ⏳ *Not Started*

#### Turn Boundary Management (1 ADR + 3 sub-ADRs)
- [ADR-0054](0054-turn-boundary-management.md) - Turn Boundary Management ⏳ *Not Started* (Parent)
  - [ADR-0054a](0054a-implicit-pause-2s.md) - Implicit Pause ≥2s ⏳ *Not Started*
  - [ADR-0054b](0054b-explicit-submit-ux.md) - Explicit Submit & UX ⏳ *Not Started*
  - [ADR-0054c](0054c-mpst-turn-transitions.md) - MPST Turn Transitions ⏳ *Not Started*

#### Context-Switch Detection (1 ADR + 3 sub-ADRs)
- [ADR-0055](0055-context-switch-detection.md) - Context-Switch Detection ⏳ *Not Started* (Parent)
  - [ADR-0055a](0055a-intent-drift-rules.md) - Intent Category Drift Rules ⏳ *Not Started*
  - [ADR-0055b](0055b-switch-prompt.md) - Switch Prompt ("new/continue/go back") ⏳ *Not Started*
  - [ADR-0055c](0055c-history-keep-clear.md) - History Keep/Clear Semantics ⏳ *Not Started*

---

### Phase 6: Voice & Audio Pipeline (M4-M5) - 15 ADRs

#### Voice Pipeline Implementation (1 ADR + 5 sub-ADRs)
- [ADR-0056](0056-voice-pipeline-implementation.md) - Voice Pipeline IMPLEMENTATION Architecture ⏳ *Not Started* (Parent)
  - [ADR-0056a](0056a-asr-ingress.md) - ASR Ingress (Frame Size, VAD, Partials) ⏳ *Not Started*
  - [ADR-0056b](0056b-intent-bridge.md) - Intent Bridge (Voice→DM Contract) ⏳ *Not Started*
  - [ADR-0056c](0056c-tool-interleaving.md) - Tool Call Interleaving While Streaming ⏳ *Not Started*
  - [ADR-0056d](0056d-tts-synthesis.md) - TTS Synthesis Streaming (Prosody Controls) ⏳ *Not Started*
  - [ADR-0056e](0056e-audio-out.md) - Audio Out & Device Handshake ⏳ *Not Started*

#### Voice-Specific Backpressure (1 ADR + 3 sub-ADRs)
- [ADR-0057](0057-voice-specific-backpressure.md) - Voice-Specific Backpressure ⏳ *Not Started* (Parent)
  - [ADR-0057a](0057a-asr-frame-drop.md) - ASR Frame Drop/Downsample Policy ⏳ *Not Started*
  - [ADR-0057b](0057b-tts-degradation-ladder.md) - TTS Degradation Ladder (Bitrate, Prosody) ⏳ *Not Started*
  - [ADR-0057c](0057c-barge-in-preemption.md) - Barge-in Preemption & Recovery ⏳ *Not Started*

#### Intent Classification (Voice) (1 ADR + 2 sub-ADRs)
- [ADR-0058](0058-intent-classification-voice.md) - Intent Classification Integration (Voice Path) ⏳ *Not Started* (Parent)
  - [ADR-0058a](0058a-confidence-thresholds.md) - Confidence/Ambiguity Thresholds & Repairs ⏳ *Not Started*
  - [ADR-0058b](0058b-safety-hooks.md) - Safety Hooks (Band Gates, Refusal Carry-Over) ⏳ *Not Started*

---

### Phase 7: Learning Loop & Adaptive Systems (M5-M6) - 10 ADRs

#### Learning Loop (1 ADR + 5 sub-ADRs)
- [ADR-0059](0059-learning-loop.md) - Learning Loop (K1 Advisory-Only, K0 Persistence) ⏳ *Not Started* (Parent) **� K0 P06 persistence**
  - [ADR-0059a](0059a-feedback-signal-taxonomy.md) - Feedback Signal Taxonomy (Explicit/Implicit/Behavioral) ⏳ *Not Started*
  - [ADR-0059b](0059b-drift-detection.md) - Drift Detection & Safeguards ⏳ *Not Started*
  - [ADR-0059c](0059c-planner-parameter-contracts.md) - Planner/DM Parameter Update Contracts ⏳ *Not Started*
  - [ADR-0059d](0059d-audit-rollback.md) - Audit & Rollback of Learned Preferences ⏳ *Not Started*
  - [ADR-0059e](0059e-synthetic-data-pipeline.md) - Synthetic Data Pipeline ⏳ *Not Started*

#### Adaptive KV-Cache (1 ADR + 2 sub-ADRs)
- [ADR-0060](0060-adaptive-kv-cache-management.md) - Adaptive KV-Cache Management ⏳ *Not Started* (Parent)
  - [ADR-0060a](0060a-learning-driven-admission.md) - Learning-Driven Admission/Eviction ⏳ *Not Started*
  - [ADR-0060b](0060b-cache-hints.md) - Cache Hints (Domain/Persona/Session) ⏳ *Not Started*

#### 3-Tier Backpressure Cascade (1 ADR + 4 sub-ADRs)
- [ADR-0061](0061-3-tier-backpressure-cascade.md) - 3-Tier Backpressure Cascade (Unified) ⏳ *Not Started* (Parent)
  - [ADR-0061a](0061a-watermarks-actions.md) - Watermarks & Actions (80/90/95%) ⏳ *Not Started*
  - [ADR-0061b](0061b-metrics-red-alerts.md) - Metrics (RED) & Alerts ⏳ *Not Started*
  - [ADR-0061c](0061c-privacy-band-overrides.md) - Privacy-Band Overrides ⏳ *Not Started*
  - [ADR-0061d](0061d-cross-stream-fairness.md) - Cross-Stream Fairness & Starvation Guards ⏳ *Not Started*

---

### Phase 8: Governance & Production (M6-M7) - 10 ADRs

#### Boundary Enforcement & Traceability
- [ADR-0001f](0001c-k0-k1-pipeline-boundary-enforcement.md) - K0/K1 Boundary Enforcement — No Pipelines in K1 🚨 ⏳ *Not Started*
- [ADR-0062](0062-adr-diagram-code-traceability.md) - ADR ↔ Diagram ↔ Code Traceability Policy ⏳ *Not Started*
- [ADR-0063](0063-evidence-packs-in-adrs.md) - Evidence Packs in ADRs (Chat/Bench/Logs) ⏳ *Not Started*

#### Product Quality & Personalization
- [ADR-0064](0064-self-model-persona-controls.md) - Self-Model & Consent: Persona Mimicry Controls (K0 P14) ⏳ *Not Started* (Parent) **🚨 K0 P14 implementation**
  - [ADR-0064a](0064a-style-vector-schema.md) - Style Vector Schema (K0 P14 Storage) ⏳ *Not Started*
  - [ADR-0064b](0064b-exemplars-watermarking.md) - Exemplars & Watermarking (K0 P14 Storage) ⏳ *Not Started*
  - [ADR-0064c](0064c-consent-scopes.md) - Consent Scopes & Revocation (K0 P10 ABAC) ⏳ *Not Started*
  - [ADR-0064d](0064d-decode-knobs-mapping.md) - Decode-Knobs Mapping (Style Vector → LLM Parameters) ⏳ *Not Started*
- [ADR-0065](0065-product-craft-ux.md) - Product Craft & UX Micro-Interactions ⏳ *Not Started* (Parent)
  - [ADR-0065a](0065a-streaming-text-typing.md) - Streaming Text & Typing Indicators ⏳ *Not Started*
  - [ADR-0065b](0065b-session-continuity-handoff.md) - Session Continuity & Device Handoff ⏳ *Not Started*
  - [ADR-0065c](0065c-quick-actions-suggestions.md) - Quick Actions & Suggested Replies ⏳ *Not Started*
- [ADR-0066](0066-developer-testing-harness.md) - Developer Testing & Simulation Harness ⏳ *Not Started* (Parent)
  - [ADR-0066a](0066a-conversation-simulator.md) - Conversation Simulator (Synthetic Users) ⏳ *Not Started*
  - [ADR-0066b](0066b-regression-eval-suites.md) - Regression Eval Suites ⏳ *Not Started*
- [ADR-0067](0067-conversational-delight.md) - Conversational Delight Factors ⏳ *Not Started*
- [ADR-0068](0068-voice-quality-measurement.md) - Voice Quality Measurement (ASR WER + TTS MOS) ⏳ *Not Started*
- [ADR-0069](0069-p08-affect-modulation.md) - P08 AffectModulation (K0 Implementation Spec) ⏳ *Not Started* **🚨 K0 implementation**
- [ADR-0070](0070-observability-evaluation.md) - Observability Evaluation Infrastructure ⏳ *Not Started* (Parent)
  - [ADR-0070a](0070a-labeled-transcript-storage.md) - Labeled Transcript Storage & Analysis ⏳ *Not Started*
  - [ADR-0070b](0070b-ab-test-harness.md) - A/B Test Harness ⏳ *Not Started*
- [ADR-0071](0071-multilingual-code-switching.md) - Multilingual & Code-Switching ⏳ *Not Started*

---

### Overall Progress
- **Total ADRs:** 51 (47 + 4 Q1 Multi-Device)
- **Completed:** 4 (7.8%) - ✅ ADR-0050 family complete
- **In Progress:** 0 (0%)
- **Not Started:** 47 (92%)

### Phase Progress
- **Phase 1 (Critical):** 0/20 ADRs (0%)
- **Phase 2 (Implementation):** 0/17 ADRs (0%)
- **Phase 3 (Optimization):** 0/10 ADRs (0%)
- **Phase 4 (Q1 Operations):** 4/4 ADRs (100%) ✅ **COMPLETE** - Multi-Device Family Sync (Device-First)
- **Phase 5 (HITL Extensions):** 0/20 ADRs (0%)
- **Phase 6 (Voice & Audio):** 0/15 ADRs (0%)
- **Phase 7 (Learning Loop):** 0/10 ADRs (0%)
- **Phase 8 (Governance & Production):** 0/10 ADRs (0%)

### Status Legend
- ✅ **Accepted** - ADR is complete and approved
- 🔄 **In Review** - ADR is written, awaiting approval
- ✏️ **Draft** - ADR is being written
- ⏳ **Not Started** - ADR not yet started
- ⚠️ **Amended** - ADR has been updated after initial approval
- ❌ **Superseded** - ADR has been replaced by a newer decision
- 🗑️ **Deprecated** - Decision is no longer relevant

---

## 🔗 ADR Dependency Graph

### Core Dependencies
```
ADR-001 (K0/K1 Split)
├── ADR-017 (SessionState Design)
├── ADR-020 (Multi-Tier Storage)
├── ADR-022 (K0 Bridge Batching)
└── ADR-044 (K0 Bridge HTTP/2)

ADR-002 (Actor Model)
├── ADR-005 (Agent Lifecycle FSM)
└── ADR-006 (3-Phase Orchestration)

ADR-003 (MPST Protocol)
└── ADR-006 (3-Phase Orchestration)

ADR-011 (FlatBuffers)
├── ADR-012 (76 Schemas)
├── ADR-015 (WebSocket Binary)
├── ADR-016 (SSE Event Schemas)
└── ADR-019 (SessionState Serialization)
```

### Security Dependencies
```
ADR-010 (Capability-Based Security)
├── ADR-032 (Band-Based Egress)
└── ADR-033 (3-Tier Sandbox)

ADR-033 (3-Tier Sandbox)
└── ADR-034 (MCP Protocol)

ADR-032 (Band-Based Egress)
├── ADR-036 (E2EE RED Band)
└── ADR-039 (Privacy Band Overrides)
```

### Communication Dependencies
```
ADR-040 (WebSocket)
├── ADR-015 (Binary Protocol)
└── ADR-046 (SSE Bridge)

ADR-042 (K0 SSE)
├── ADR-043 (SSE Topic Taxonomy)
├── ADR-045 (Agent-Agent Coordination)
└── ADR-046 (SSE Bridge)
```

---

## 📖 How to Use This Index

### For New Team Members
1. Start with **Core Architecture** ADRs (001-010) to understand system design
2. Read **Serialization & Contracts** ADRs (011-016) to understand data formats
3. Review **Security & Privacy** ADRs (032-039) to understand security model
4. Explore other categories based on your area of work

### For Implementers
1. Check which ADRs apply to your feature area
2. Read the ADR before writing code
3. Reference the ADR number in your code comments and PRs
4. Update the ADR if you discover issues during implementation

### For Reviewers
1. Verify that code follows the decisions in relevant ADRs
2. Check that new architectural decisions have ADRs
3. Ensure ADR references are included in PRs

### For Architects
1. Review ADRs regularly for consistency
2. Create new ADRs for new decisions
3. Update ADR dependency graph when adding new ADRs
4. Maintain this index with current status

---

## 🔍 Search Guide

### By Technology
- **FlatBuffers:** ADR-011, 012, 015, 016, 019, 044
- **Actor Model:** ADR-002, 005, 006
- **WebSocket:** ADR-015, 040, 046
- **SSE:** ADR-016, 042, 043, 045, 046
- **K0/K1:** ADR-001, 020, 022, 044

### By Pattern
- **Saga Pattern:** ADR-008
- **Circuit Breaker:** ADR-009
- **Contract Net Protocol:** ADR-006
- **MPST:** ADR-003
- **Multi-Tier Storage:** ADR-020

### By Concern
- **Security:** ADR-010, 032, 033, 034, 035, 036, 037, 038, 039
- **Performance:** ADR-024, 025, 026, 027, 028, 029, 030, 031
- **State Management:** ADR-017, 018, 019, 020, 021, 022, 023
- **Communication:** ADR-040, 041, 042, 043, 044, 045, 046, 047

---

## 📝 Creating a New ADR

### Step 1: Copy Template
```bash
cp docs/architecture/decisions/ADR_TEMPLATE.md \
   docs/architecture/decisions/0048-your-decision-title.md
```

### Step 2: Fill in Sections
- Update status to "Proposed"
- Add date and deciders
- Write context, decision, alternatives, consequences
- Add references and diagrams

### Step 3: Review & Approval
- Share with team for review
- Address feedback
- Get approval from lead architect
- Update status to "Accepted"

### Step 4: Update Index
- Add to this README.md
- Update progress dashboard
- Add to dependency graph if applicable
- Update cross-references in related ADRs

---

## 📚 Additional Resources

### Templates & Guides
- [ADR Template](ADR_TEMPLATE.md) - Standard template for all ADRs
- [ADR Creation Plan](ADR_CREATION_PLAN.md) - 3-week plan to create all 47 ADRs

### Related Documentation
- [Architecture Overview](../../README.md) - High-level system architecture
- [Whiteboard](../../whiteboard/whiteboard.md) - Complete design specification (26,902 lines)
- [Architecture Diagrams](../../../architecture_diagrams/) - Visual architecture documentation

### External Resources
- [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) - Original ADR concept by Michael Nygard
- [ADR GitHub Organization](https://adr.github.io/) - ADR tools and best practices
- [Architecture Decision Records](https://www.thoughtworks.com/radar/techniques/lightweight-architecture-decision-records) - ThoughtWorks Radar

---

## 🤝 Contributing

### Review Process
1. ADR author creates draft in branch
2. Team reviews for technical accuracy
3. Lead architect approves or requests changes
4. ADR is merged and status updated to "Accepted"

### Amendment Process
1. Create new branch
2. Add "Amendment" section to existing ADR
3. Explain what changed and why
4. Update status to "Amended"
5. Get approval and merge

### Superseding Process
1. Create new ADR with updated decision
2. Reference old ADR in "Supersedes" section
3. Update old ADR status to "Superseded"
4. Link new ADR in old ADR notes

---

## 📞 Contact

**Questions about ADRs?**
- Create an issue with label `adr-question`
- Contact the architecture team
- Check the [ADR Creation Plan](ADR_CREATION_PLAN.md) for guidance

**Want to propose a new ADR?**
- Use the [ADR Template](ADR_TEMPLATE.md)
- Follow the creation process above
- Tag architecture team for review

---

**Last Updated:** October 10, 2025
**Maintained by:** K1 Architecture Team
**Next Review:** Weekly during Phase 1-3, Monthly after completion
