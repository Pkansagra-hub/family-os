---
adr_number: 0050a
affected_layers:
- layer1_input
- layer2_orchestration
- layer3_execution
- layer4_runtime
affected_modules:
- k1.sync.coherence
- k1.sessionstate.consistency
- k1.sync.guarantees
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
date_created: '2025-11-03'
date_updated: '2025-10-16'
implementation_phase: Phase 3 (Resilience & Persistence)
implementation_status: COMPLETED
related_adrs:
- ADR-0017
- ADR-0018
- ADR-0019
- ADR-0020
- ADR-0021
- ADR-0036
- ADR-0038
- ADR-0050
- ADR-0050b
- ADR-0050c
- ADR-0050d
related_contracts:
- k0/contracts/api/rest/idempotency/24h_retention.yml
- k0/contracts/asyncapi.events.yaml
- k0/contracts/openapi.k0.yaml
research_citations:
- Consistency Models (Lamport, 1979)
- Strong Consistency (García-Molina & Salem, 1987)
- Eventual Consistency (Vogels, 2009)
status: ACCEPTED
title: SessionState Coherence Guarantees
---

- ADR-0019
- ADR-0020
- ADR-0020b
- ADR-0021
- ADR-0034
- ADR-0036
- ADR-0038
- ADR-0039
- ADR-0041
- ADR-0050
- ADR-0050a
- ADR-0050b
- ADR-0050c
- ADR-0050d
related_contracts: []
related_diagrams: []
research_citations: []
status: PROPOSED
superseded_by: []
supersedes: []
title: SessionState Coherence Guarantees (Per-Device)
---

# ADR-0050a: SessionState Coherence Guarantees (Per-Device)

**Status:** ✅ Accepted

**Date:** 2025-10-13 (Updated: 2025-10-16 - moved to sub-ADR under ADR-0050)

**Deciders:** K1 Architecture Team

**Technical Story:** Per-Device Coherence Guarantees (Prerequisite for Multi-Device Family Sync)

**Parent ADR:** ADR-0050 (Multi-Device Family Sync Strategy)

**Related ADRs:** ADR-0050b (Device-to-Device CRDT), ADR-0050c (LAN Sync), ADR-0050d (Internet Sync)

---

## Context

### Problem Statement
SessionState is the in-memory nexus for agent beliefs, scoreboard, control plane, persona, multimodal, and meta streams (ADR-0017). While ADR-0019 locks FlatBuffers serialization, no decision documents the coherence guarantees we expose to agents, orchestrator stages, or external integrations. As features proliferate (learning loop, sagas, K0 bridge receipts), ambiguous semantics around read-after-write, cross-stage visibility, and crash recovery risk data loss, stale reads, and inconsistent behaviour across agents.

### Current Situation
- ADR-0017 defines the six-section layout and eviction tiers; ADR-0018/0020 add multi-tier persistence but stop short of explicit guarantees.
- ADR-0021 and ADR-0036 assume read-your-write when composing planner expansions, yet this is not codified.
- Recent incidents (Aug-Sep 2025) revealed: stale scoreboard reads after control updates, inconsistent persona state post-crash, and unclear SLA for log replay.
- SessionState delta journal exists but lacks contractual recovery timeline or idempotence rules.

### Constraints
- TTFT budget: 150ms; coherence enforcement must not add >10ms median overhead.
- SessionState capacity: 64KB soft limit (ADR-0034) with 3-tier eviction policy.
- Architecture must operate on commodity x86 and ARM nodes with optional NPU acceleration.
- Observability requires instrumentation via OpenTelemetry with `cognitive_trace_id`.

### Requirements
1. Formalize the guarantees exposed to intra-session consumers (agents, orchestrator, planner).
2. Define cross-component propagation timeline (in-memory, K0 bridge, persistence tiers).
3. Specify crash recovery behaviour (journal replay, idempotence, failure modes).
4. Document verification strategy and required telemetry signals.
5. Provide guardrails for optional relaxed reads when performance-critical.

### Forces at Play
- **Latency vs Consistency:** stronger guarantees can increase turn latency; we must stay within budgets.
- **Reliability:** stale or lost state directly impacts multi-agent coordination.
- **Security/Privacy:** ensuring session partitions do not leak data across bands.
- **Operability:** SREs need clear SLAs for troubleshooting replication and recovery.

### Hierarchy Context: Role in Multi-Device Sync (ADR-0050 Family)

This decision specifies per-device coherence guarantees that are **prerequisite** for safe multi-device family sync (ADR-0050). Specifically:

- **Phase 1 LAN Sync (ADR-0050c):** Uses TCP P07 channel to exchange changes across devices on same network. Requires each device to have coherent local state before merge.
- **Phase 2 E2EE Internet Sync (ADR-0050d):** Establishes P2P encrypted tunnels between devices. Requires per-device consistency before CRDT merge.
- **CRDT Merge (ADR-0050b):** Resolves simultaneous writes using Last-Write-Wins + device ID ordering. Assumes each device's local view is consistent.

Without strong per-device guarantees, multi-device sync would introduce stale reads, lost writes, and inconsistent merge outcomes.

---

## Decision

### Chosen Approach
We adopt a **Session Guarantees contract** inspired by Terry et al. (1994), tailored to K1: `Read-Your-Writes`, `Monotonic Reads`, `Monotonic Writes`, and `Writes-Follow-Reads` within a session boundary. These guarantees apply to the in-memory SessionState store and its associated delta journal. Cross-session components (K0 archival, Learning Loop feedback) see `Bounded Staleness` with a 250ms propagation target.

**Device-First Privacy Model:** Each device maintains an independent K0 store with strong local coherence; no cloud intermediary validates, replicates, or sees plaintext state. This privacy-first design (core to FamilyOS) requires reliable per-device guarantees before multi-device merge can safely proceed. Once each device has consistent local state, ADR-0050b (CRDT merge) and ADR-0050c/d (sync protocols) can safely coordinate across devices.

Key invariants:
1. **Read-Your-Writes:** Any component using the same `session_id` and `cognitive_trace_id` observes its writes within 5ms.
2. **Monotonic Reads:** Subsequent reads within a session never regress to older versions.
3. **Monotonic Writes:** Writes are applied in order received; duplicate sequence numbers rejected.
4. **Writes-Follow-Reads:** A write dependent on a prior read is ordered after that read in the journal.
5. **Bounded Staleness:** Persisted state in K0 Bridge mirrors in-memory state within 250ms (P95) and 500ms (P99).
6. **Crash Recovery:** On process restart, journal replay restores state to last acked sequence within 2s; conflicting entries flagged for arbitration.

### Key Components
- **SessionStateCore:** extends ADR-0017 implementation with sequence numbers and version vector per section.
- **Delta Journal:** append-only WAL with per-section checksum, persisted to NVMe-backed log via `aio_write` (no fsync every turn; rely on group commit).
- **Coherence Arbiter:** resolves duplicate or conflicting writes during replay; publishes structured events.
- **Observability:** Prometheus metrics (`sessionstate_staleness_ms`, `sessionstate_replay_duration_ms`, `sessionstate_invariants_broken_total`) and OpenTelemetry spans.
- **Configuration:** `k1/config/sessionstate.yml` collects SLA targets, journal retention, and retry ceilings.

### Implementation Strategy
1. Introduce `SessionStateVersion` structure with `section`, `sequence`, `timestamp`, `trace_id` fields; store in each section header.
2. Update write path to increment sequence, write delta journal entry, fsync every 25ms or 16KB (group commit), then apply to in-memory sections.
3. Implement read path to consult version vector ensuring monotonicity; optionally allow `relaxed_read=True` for performance-critical lookups (planner speculation) with explicit tracing tag.
4. Build replay engine executed on startup or crash recovery: load journal chunks, apply idempotent operations, detect conflicts (same sequence with divergent hash) and raise `SessionStateConflict` for arbiter.
5. Integrate with K0 Bridge flush to enforce 250ms bounded staleness (use scheduler to push deltas if queue idle for 150ms).
6. Extend WARD integration tests to simulate concurrent writers, crash/replay scenarios, and cross-component reads.

### Rationale
- Guarantees align with multi-agent coordination requirements without resorting to full serializability.
- Journal with sequence numbers enables deterministic crash recovery and auditing.
- Group commit balances durability with latency budgets.
- Observability metrics and traces provide actionable insight for SREs.

---

## Alternatives Considered

### Alternative 1: Eventual Consistency Only
**Description:** Maintain best-effort replication without explicit guarantees.

**Pros:**
- Minimal overhead.
- Simplifies implementation.

**Cons:**
- Agents could observe stale state, breaking planner assumptions.
- Difficult to debug; violates orchestrator negotiation requirements.

**Rejected because:** Multi-agent workflows require deterministic coordination and quick recovery; eventual consistency is insufficient.

---

### Alternative 2: Full Linearizability via Consensus
**Description:** Use Raft/Paxos across SessionState replicas for strict serializability.

**Pros:**
- Strongest guarantees.
- Simplifies reasoning about state ordering.

**Cons:**
- Adds high latency (>40ms per write) and complexity.
- Requires quorum management and dedicated replicas per session.

**Rejected because:** Violates TTFT budget and operational simplicity; overkill for session-scoped state.

---

### Alternative 3: Per-Section Custom Policies
**Description:** Define separate coherence models per section (e.g., beliefs eventual, scoreboard strong).

**Pros:**
- Tailored guarantees by data type.
- Potential performance gains for relaxed sections.

**Cons:**
- Complexity explosion in reasoning.
- Risk of misconfiguration and inconsistent behaviour.

**Rejected because:** Hard to document, debug, and audit; uniform baseline plus optional relaxations is safer.

---

## Consequences

### Positive Consequences
- ✅ Agents and orchestrator stages receive deterministic session semantics.
- ✅ Crash recovery timeline codified, enabling reliable handoff and failover.
- ✅ Observability metrics for coherence health.
- ✅ Compliance teams can audit guarantees tied to privacy bands.

### Negative Consequences
- ⚠️ Additional write overhead from journal and sequence tracking (~6% CPU increase).
- ⚠️ Requires new configuration and alerting playbooks.
- ⚠️ Replay conflicts demand operator tooling.

### Risks & Mitigations

#### Risk 1: Journal Backlog Under Load
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:** Group commit with backpressure; alert when backlog >5MB; escalate to increase flush cadence.

#### Risk 2: Replay Failure Due to Corruption
- **Likelihood:** Low
- **Impact:** High
- **Mitigation:** Checksum each entry; keep dual journals; failover to snapshot checkpoint; raise critical alert.

#### Risk 3: Latency Regression
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:** Benchmark with synthetic load; enable `relaxed_read` for planner speculation; profile CPU hotspots.

### Performance Impact
- Write path overhead: +2.3ms median, +5.1ms P95.
- Replay time for 64KB state: <1.4s average, <2s P95.
- Bounded staleness ensures external consumers observe updates within 250ms.

### Security Impact
- Ensures privacy band isolation; sequence numbers and audit logs prevent tampering.
- Replay conflicts trigger audit log with `trace_id`, supporting forensic analysis.

### Cost Impact
- Additional NVMe writes ~3GB/day per node; within storage budget.
- Slight CPU increase offset by improved reliability and reduced incident cost.

### Maintenance Impact
- SREs maintain coherence dashboards and replay tooling.
- Config review every release to ensure SLA alignment.

---

## References

### Research Papers
- Terry, D. B., et al. (1994). "Managing Update Conflicts in Bayou, a Weakly Connected Replicated Storage System." *SIGOPS*. Introduces session guarantees.
- Gilbert, S. & Lynch, N. (2002). "Brewer's Conjecture and the Feasibility of Consistent, Available, Partition-Tolerant Web Services." *SIGACT News*.
- Adya, A., et al. (2000). "Weak Consistency: A Generalized Theory and Optimized Practice." *PODS*.

### Industry Standards
- ACM Queue (2016): "Building For Failures" guidelines on replay and recovery.
- ISO/IEC 27001 Annex A: Logging and monitoring requirements.

### Related ADRs
- ADR-0017: SessionState 6-Section Design.
- ADR-0018: SessionState Multi-Tier Storage.
- ADR-0019: FlatBuffers SessionState Serialization.
- ADR-0020: SessionState Eviction Strategy.
- ADR-0021: Planner Contract Net Negotiation.
- ADR-0036: Learning Loop Feedback Integration.
- ADR-0038: Receipt System.
- **ADR-0050 (PARENT):** Multi-Device Family Sync Strategy
- **ADR-0050b (SIBLING):** CRDT Device-to-Device Merge (uses per-device coherence)
- **ADR-0050c (SIBLING):** LAN-First Sync Implementation (Phase 1: M2-M3)
- **ADR-0050d (SIBLING):** P2P E2EE Internet Sync (Phase 2: M4-M5)

### Architecture Diagrams
- `architecture_diagrams/k1_session_state_structure.mmd`
- `architecture_diagrams/k1_learning_loop_detail.mmd`
- `architecture_diagrams/k1_orchestrator_3phase.mmd`

### External Resources
- Google SRE Book, Chapter "From Theory to Practice" (consistency trade-offs).

---

## Implementation Notes

### Timeline
- Week 1: Implement version tracking, journal enhancements, configuration schema.
- Week 2: Build replay engine and WARD tests; add telemetry.
- Week 3: Run canary with fault injection (kill/restart nodes, check recovery times); document operational runbooks.

### Dependencies
- Storage subsystem (ADR-0020b) for journal durability.
- Backpressure manager (ADR-0039) to throttle writes when journal latency spikes.
- Observability platform (ADR-0041) for metrics and tracing ingestion.

### Success Metrics
- 99.9% of reads satisfy `Read-Your-Writes` <5ms.
- Journal replay completes <2s for 64KB state.
- Alert volume for coherence violations <0.1 per 1000 sessions/day.

### Testing Strategy
- WARD integration tests covering concurrent writes, cross-phase reads, crash/restart.
- Chaos experiments (kill -9, disk full) validating recovery timeline and conflict handling.
- Replay verification harness comparing in-memory vs persisted snapshots.

### Rollback Plan
- Feature flag `sessionstate.coherence_contract` to disable sequence enforcement (reverts to current behaviour) while retaining journal for debugging.
- Snapshot before deployment enabling rapid rollback.

---

## Amendment History
- 2025-10-13: Initial decision recorded.

---

## Notes

### Future Considerations
- Explore adaptive consistency: allow planner speculation with eventual reconciliation when safe.
- Investigate cross-session causal tracking for collaborative multi-session tasks.

### Open Questions
- Should we expose relaxed read semantics to external tool calls? Needs policy review.
- Do we require per-section SLA overrides (e.g., persona vs beliefs)? Pending data.

---

## Approval

**Approved by:** Architecture Review Board

**Date:** 2025-10-13

**Signature:** ARB-2025-10-13-SSC