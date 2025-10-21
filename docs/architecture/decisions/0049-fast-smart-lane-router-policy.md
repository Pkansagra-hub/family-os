# ADR-0049: Fast/Smart Lane Router Policy

**Status:** ✅ Accepted

**Date:** 2025-10-13

**Deciders:** K1 Architecture Team

**Technical Story:** K0/K1 Bridge Admission Control Harmonization

---

## Context

### Problem Statement
K1 lacks a formal policy for selecting K0s Fast Lane (<50ms, GREEN band) versus Smart Lane (Hippocampus, 150-200ms, AMBER/RED) when issuing memory writes and updates. Without a codified router, teams implement ad-hoc heuristics that create inconsistent latency, privacy, and compliance behavior across agents and infrastructure modules. We must lock a deterministic policy that keeps latency budgets intact while honouring privacy bands, obligations, and consolidation rules.

### Current Situation
- **ADR-0001a** defines dual lanes but leaves lane selection up to callers.
- **ADR-0001f** governs state boundaries but assumes reliable fast vs smart routing.
- **ADR-0028/0028b** introduce admission weights and preemption for runtime queues, yet memory routing still bypasses those guarantees.
- Agents today push GREEN writes directly to the bridge while some infrastructure modules always choose Smart Lane, producing divergent behaviour, inconsistent receipts, and unpredictable load on Hippocampus pipelines.

### Constraints
- SessionState flush window: 250ms (ADR-0019).
- Fast Lane target latency: <50ms P95; Smart Lane target latency: <200ms P95.
- Privacy bands: GREEN/AMBER/RED (ADR-0032, ADR-0035).
- Obligations must not be skipped (PII vault, GDPR receipts, dedup triggers).
- Router must execute in <5ms CPU and operate with zero allocations >512 bytes per request to fit hot path.

### Requirements
1. Deterministic routing decision per envelope with audit trail.
2. Read-your-write semantics: Smart Lane required when obligations include consolidation, dedup, or cross-family updates.
3. Backpressure integration: lane choice must honour watermarks defined in ADR-0039.
4. Configurable but centrally governed thresholds in `k1/config/k0_bridge.yml`.
5. Observability: per-lane counters, latency histograms, and mis-route alerts.

### Forces at Play
- **Performance:** Maintain <10ms bridge overhead while protecting Hippocampus capacity (Tail at Scale, Dean & Barroso 2013).
- **Privacy & Compliance:** Smart Lane required for AMBER/RED content, GDPR obligations, and PII vault updates.
- **Operational Simplicity:** Router must be explainable to SREs with minimal tuning knobs.
- **Reliability:** Avoid oscillations and feedback loops that trigger backpressure cascades.

---

## Decision

### Chosen Approach
Introduce a centralized **Fast/Smart Lane Router** in the K0 Bridge client that evaluates every envelope against a scoring policy. The router emits a binary lane decision plus rationale metadata, ensuring identical behaviour for agents, infrastructure modules, and automation.

Routing is driven by a four-factor score:

```
score = privacy_weight + obligation_weight + payload_weight + time_budget_weight
```

- **privacy_weight:** GREEN = 0, AMBER = 40, RED = 80.
- **obligation_weight:** +50 if obligations array includes consolidation, dedup, compliance export, saga receipt, or cross-family replication.
- **payload_weight:** +20 if payload size >16KB, +30 if write type = `episodic_event` or `procedural_script`, +10 if multi-turn delta.
- **time_budget_weight:** -20 if caller requests latency_budget_ms <80, +10 otherwise.

Routing rule:
- `score < 40` **and** Fast Lane queue depth <70% watermark  route Fast Lane.
- Otherwise route Smart Lane.

Dedicated override flags allow the orchestrator to force Smart Lane when a saga demands durable ordering.

### Key Components
- `k1/infrastructure/k0_bridge/router.py` coordinating decision logic.
- Configurable weights in `k1/config/k0_bridge.yml` backed by hot-reload via Config Manager.
- Prometheus metrics:
  - `k1_k0_router_fast_total`, `k1_k0_router_smart_total`.
  - `k1_k0_router_score_bucket` histogram.
  - `k1_k0_router_misroute_total` (policy violations detected by K0 receipts).
- Structured logging with `cognitive_trace_id` plus `lane_decision`, `score_breakdown`, and `watermark_snapshot`.
- Audit sink persisted in K0 receipts (extends ADR-0038a schema with `lane_decision` field).

### Implementation Strategy
1. **Router module**: implement deterministic scoring function with unit benchmarks (<200ns per call) and expose `decide_lane(envelope)` API.
2. **Bridge integration**: call router before enqueueing to Fast or Smart dispatch queues; attach lane metadata to envelope headers.
3. **Observability**: emit metrics and structured logs; connect to backpressure monitors (ADR-0039b/c).
4. **Policy enforcement**: augment K0 acknowledgements to validate lane correctness; raise `MisroutedEnvelope` if Smart-only obligations reached Fast Lane.
5. **Configuration rollout**: define default weights in config; guard with feature flag `lane_router.enabled` to support staged deploy.
6. **Documentation**: update `docs/k1_module_analysis.md` (Bridge section) and `docs/architecture/K0_K1_INTEGRATION_SUMMARY.md` with policy summary.

### Rationale
- Centralizing routing eliminates divergent heuristics across agents and infrastructure.
- Weighted scoring keeps decision explicit, explainable, and easy to tune.
- Coupling with backpressure prevents Fast Lane saturation during spikes.
- Observability and receipt validation ensure compliance teams can audit lane usage.
- Implementation leverages existing bridge and backpressure infrastructure, minimizing new code paths.

---

## Alternatives Considered

### Alternative 1: Client-Provided Lane Flag
**Description:** Allow callers to specify `lane="fast"|"smart"` on each envelope with minimal validation.

**Pros:**
- Simple implementation.
- Caller retains explicit control.

**Cons:**
- Inconsistent behaviour across teams.
- High risk of misrouting sensitive data.
- No audit trail tying back to policy.

**Rejected because:** Violates architecture governance; increases compliance risk and creates debugging overhead.

---

### Alternative 2: Always Smart Lane
**Description:** Route every write through Smart Lane regardless of contents.

**Pros:**
- Simplifies reasoning; maximal consistency.
- Ensures all obligations executed.

**Cons:**
- Breaks latency budgets (<50ms) for GREEN traffic.
- Overloads Hippocampus pipelines, triggering backpressure cascades.
- Increases cost and energy consumption.

**Rejected because:** P95 latency and throughput targets fail; unnecessary load on Smart Lane contradicts ADR-0001a design.

---

### Alternative 3: ML-Based Lane Classification
**Description:** Train an ML model on historical envelopes to predict optimal lane.

**Pros:**
- Could capture nuanced patterns.
- Learns from real workload shifts.

**Cons:**
- Opaque decisions unfit for compliance review.
- Requires feature store, inference latency, and ongoing training.
- Difficult to guarantee deterministic behaviour and quick rollback.

**Rejected because:** Complexity outweighs benefit; explainability and deterministic guarantees are mandatory for governance.

---

## Consequences

### Positive Consequences
- ✅ Consistent lane selection across all modules.
- ✅ Protects Fast Lane latency while reserving Smart Lane for high-obligation writes.
- ✅ Provides observable metrics and audit logs for compliance reviews.
- ✅ Integrates with backpressure to reduce cascading overloads.

### Negative Consequences
- ⚠️ Additional configuration knobs that require SRE ownership.
- ⚠️ Slight CPU overhead (<5ms worst-case) in bridge hot path.
- ⚠️ Requires coordination with ADR-0038 receipt schema update.

### Risks & Mitigations

#### Risk 1: Mis-tuned thresholds cause Smart Lane overload
- **Likelihood:** Medium
- **Impact:** High
- **Mitigation:** Default thresholds validated against historical traces; add canary alert when Smart Lane occupancy >85% for 2 minutes.

#### Risk 2: Fast Lane selected for sensitive payload due to bypass bug
- **Likelihood:** Low
- **Impact:** High
- **Mitigation:** Receipt validation triggers `MisroutedEnvelope`; audit log escalates to Security; automated circuit breaker flips router to Smart-only mode until manual review.

#### Risk 3: Route oscillation under fluctuating load
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:** Add 5% hysteresis to watermark checks; integrate with ADR-0039 recovery manager to smooth transitions.

### Performance Impact
- Router adds ~0.4ms median decision cost, keeping total bridge latency within <10ms P95.
- Smart Lane usage expected to drop 23% for GREEN traffic, freeing Hippocampus cycles for consolidation.

### Security Impact
- Enforces privacy band policy: AMBER/RED always Smart Lane.
- Ensures obligations (GDPR, PII vault) never bypass required processing.

### Cost Impact
- Reduced Smart Lane load translates to ~12% NPU utilization savings in Hippocampus cluster.
- Minimal additional CPU cost on K1 nodes.

### Maintenance Impact
- Router weights maintained via Config Manager with change logging.
- Requires quarterly review alongside backpressure thresholds.

---

## References

### Research Papers
- Dean, J. & Barroso, L. A. (2013). "The Tail at Scale." *Communications of the ACM*, 56(2).
- Gray, J. & Reuter, A. (1992). *Transaction Processing: Concepts and Techniques*  guidance on durability obligations.

### Industry Standards
- IETF RFC 7540: HTTP/2 (transport for K0 bridge).
- NIST SP 800-53 Rev. 5: Audit logging and traceability requirements (AU family).

### Related ADRs
- ADR-0001a: K0 Bridge Communication Protocol.
- ADR-0001f: State Boundary Management (K1 vs K0).
- ADR-0028: Weighted Fair Queuing Scheduler.
- ADR-0028b: Priority Classes & Preemption.
- ADR-0032: Band-Based Egress Rules.
- ADR-0038a: Receipt Generation Schema.
- ADR-0039b/c: Backpressure Propagation & Recovery.

### Architecture Diagrams
- `architecture_diagrams/k0_k1_integration_architecture.mmd`
- `architecture_diagrams/k1_backpressure_cascade.mmd`
- `architecture_diagrams/k1_kv_cache_thermal.mmd`

### External Resources
- AWS Builders Library: "Avoiding insurmountable queue backlogs" (2020)  operational guidance on admission control.

---

## Implementation Notes

### Timeline
- Week 1: Implement router, integrate metrics, add receipt field.
- Week 2: Roll out canary in staging with synthetic workloads; adjust thresholds.
- Week 3: Enable in production with gradual ramp (10% -> 100%).

### Dependencies
- Receipt schema update (ADR-0038a) to store `lane_decision`.
- Config Manager hot-reload pipeline (ADR-0026d) for router weights.

### Success Metrics
- Fast Lane P95 latency remains <45ms.
- Smart Lane occupancy stays <75% average with <5% of GREEN traffic routed Smart.
- Misroute alerts <0.01% of total envelopes.

### Testing Strategy
- WARD integration tests simulating GREEN/AMBER/RED payloads.
- Load tests with synthetic spikes to validate hysteresis and backpressure integration.
- Compliance replay suite verifying obligations map to Smart Lane.

### Rollback Plan
- Feature flag `lane_router.enabled` toggles router off (reverts to current heuristics).
- Config rollbacks stored in Config Manager history; can revert weights instantly.

---

## Amendment History
- 2025-10-13: Initial decision captured.

---

## Notes

### Future Considerations
- Explore adaptive thresholds based on Hippocampus health metrics once telemetry maturity increases.
- Evaluate per-family customizations with guardrails after baseline stability proven.

### Open Questions
- Should Smart Lane quota be enforced per privacy band or per family? Pending analysis.
- Do we need a dedicated saga lane for long-running transactional writes? Requires further study.

---

## Approval

**Approved by:** Architecture Review Board

**Date:** 2025-10-13

**Signature:** ARB-2025-10-13-FSL
