---
adr_id: ORCH-011
title: "Open Questions Resolution Batch -- Q3 through Q11 Decisions"
status: Accepted
date: 2026-02-11
module: orchestrator
layer: "L2"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-001"
  - "ORCH-005"
  - "ORCH-007"
  - "ORCH-009"
  - "ORCH-010"
related_events:
  - "k1.orchestration.dag.step.completed.v1"
  - "k1.orchestration.workflow.triggered.v1"
related_contracts:
  - "k1/contracts/schemas/modules/orchestrator/module.contract.yaml"
related_ports:
  - "IFabricGatewayPort"
  - "IStateReadPort"
  - "IWorkflowStoragePort"
  - "IEventSubscriptionPort"
implements_issue: "1.1.11"
superseded_by: ""
tags:
  - architecture
  - orchestrator
  - open-questions
  - batch-resolution
---

# ORCH-011: Open Questions Resolution Batch -- Q3 through Q11 Decisions

## Context

### Problem Statement

Orchestrator.md Section 26 listed 11 open questions (Q1-Q11) requiring architectural decisions. Q1 and Q2 are resolved by ORCH-008 (saga compensation ordering) and ORCH-009 (workflow persistence strategy) respectively. This ADR resolves Q3-Q11 as a batch, documenting each decision with rationale.

### Questions Addressed

| ID | Question | Resolution |
|----|----------|------------|
| Q3 | MCP health monitoring strategy | Resolved (passive CB + active for critical) |
| Q4 | When to re-read safety_band during DAG execution | Resolved (wave boundaries) |
| Q5 | Concurrent workflow run handling | Resolved (single active, abort previous) |
| Q6 | Sub-workflow parameter precedence | Resolved (parent overrides) |
| Q7 | Cost metering and budgets | DEFERRED to V2 |
| Q8 | Gap detection heuristic conservatism | Resolved (exact match V1) |
| Q9 | Quality threshold configuration | DEFERRED to V2 |
| Q10 | Conditional edge expression language | Resolved (simple comparisons V1) |
| Q11 | Sub-step event rate limiting | Resolved (1/step/500ms) |

---

## Decision

### Q3: MCP Health Monitoring -- Passive CB with Active Probing for Critical

**Decision:** Orchestrator does NOT monitor MCP health directly. Fabric owns health monitoring via HealthChecker and AvailabilityTracker. Orchestrator's ConnectorLifecycleManager subscribes to Fabric health events (k1.fabric.provider.health.changed.v1) via IEventSubscriptionPort.

For critical MCP servers (`critical: true` in config):
- Fabric performs active health probes (half-open CB at 30s intervals)
- Orchestrator receives health status changes via events
- On critical server down: emit telemetry alert via IDeltaEmitPort

For non-critical servers:
- Passive monitoring only (CB tracks failures during normal execution)
- No active probing overhead

**Rationale:** Orchestrator has no transport-level access to MCP servers (ORCH-04: every step through Fabric). Health probing is a Fabric concern. Orchestrator consumes health status as an event consumer.

**Affects:** Epic 5.1.5 (MCP health monitoring)

---

### Q4: Safety Band Re-Read Timing -- Wave Boundaries

**Decision:** IStateReadPort.read_safety_band() is called at two points:

1. **At task dequeue:** Snapshot safety_band when TaskEnvelope is dequeued from mailbox. Use for initial dispatch decision (MEDIUM vs HIGH routing).

2. **At wave boundaries (HIGH tier only):** Before dispatching each wave, re-read safety_band. If safety_band has changed (e.g., GREEN -> AMBER during execution), adjust available capabilities for remaining waves.

**NOT re-read:**
- During individual step execution within a wave (too frequent, adds latency)
- For MEDIUM tier (1-2 steps, too short to benefit from re-read)

**Rationale:** Wave boundaries are natural checkpoints where the DAG executor already pauses between parallel batches. Re-reading here catches safety band changes within seconds of occurrence without adding per-step overhead. Typical DAG has 2-4 waves.

**Affects:** Epic 2.2.2 (DAG wave dispatch)

---

### Q5: Concurrent Workflow Runs -- Single Active, Abort Previous

**Decision:** V1 enforces single active run per workflow. When a new trigger fires for a workflow that already has an active run:

1. Current run receives CANCEL_DAG interrupt (via InterruptRequest)
2. Current run compensates completed side-effect steps (per ORCH-008)
3. New run starts after current run completes cancellation

**Justification for abort-previous (not queue):**
- Queuing creates unbounded backlog for high-frequency cron triggers
- The new trigger typically has more current context, making the old run stale
- User can re-trigger manually if needed

**V2 consideration:** Add configurable concurrent run policy (`abort_previous`, `queue`, `skip_new`).

**Affects:** Epic 4.2.3 (WorkflowSupervisor concurrent run handling)

---

### Q6: Sub-Workflow Parameter Precedence -- Parent Overrides

**Decision:** When a parent workflow invokes a sub-workflow step, parameter resolution follows:

```text
Priority (highest to lowest):
  1. Parent's per-step param_overrides (explicit overrides in PlanStep.params)
  2. Sub-workflow's default params (from WorkflowSpec.default_params)
  3. System defaults (from OrchestratorConfig)
```

Parent overrides take precedence because the parent workflow has context-specific knowledge about why this sub-workflow is being invoked. Sub-workflow defaults are generic and may not match the parent's intent.

**Merge strategy:** Shallow merge (dict.update). Nested structures are replaced, not deep-merged, to maintain determinism.

**Affects:** Epic 4.2.5 (CrossWorkflowResolver parameter merge)

---

### Q7: Cost Metering -- DEFERRED to V2

**Decision:** Cost metering is deferred to V2. No cost tracking, no per-request cost visibility, no cost budgets.

**Reason:** Fabric CapabilityResult does not include `cost_usd`. No LLM provider in V1 reports cost per invocation. CostBudgetGuard and CostAccumulator are removed from V1 types and guard pipeline (see ORCH-007).

**Reintroduction criteria:** V2 when LLM providers report cost metadata in CapabilityResult or a separate cost reporting API exists.

**Affects:** Guard pipeline (ORCH-007), types (CostAccumulator removed)

---

### Q8: Gap Detection Heuristic -- Exact Field Match (V1)

**Decision:** GapDetector uses conservative exact field match for schema drift detection:

```text
Drift detected when:
  - A field in the capability's registered input_schema is ADDED or REMOVED
  - A field's type changes (string -> number, etc.)
  - A required field becomes optional or vice versa

NOT flagged as drift:
  - New optional fields added (backward compatible)
  - Description/metadata changes
  - Field ordering changes
```

**Rationale:** Conservative heuristic avoids false positives that would flood users with unnecessary gap notifications. Exact match catches breaking changes. New optional fields are backward-compatible and should not trigger workflow repair.

**V2:** Semantic similarity heuristic (detect field renames, type-compatible changes).

**Affects:** Epic 4.2.7 (GapDetector classification)

---

### Q9: Quality Thresholds -- DEFERRED to V2

**Decision:** Quality thresholds and quality-based retry are deferred to V2. No QualityGate guard, no quality_score tracking.

**Reason:** Fabric CapabilityResult does not include `quality_score`. No provider computes quality metrics per invocation. QualityGate is removed from V1 guard pipeline (see ORCH-007).

**Reintroduction criteria:** V2 when a quality scoring pipeline exists (inference-time or post-hoc evaluation via Learning Loop).

**Affects:** Guard pipeline (ORCH-007)

---

### Q10: Conditional Edge Expression Language -- Simple Comparisons (V1)

**Decision:** ConditionalEdgeEvaluator supports simple comparison expressions only:

```text
Supported operators:
  ==, !=, <, >, <=, >=

Supported operand types:
  - String literals: "value"
  - Numeric literals: 42, 3.14
  - Boolean literals: true, false
  - Step result references: $step_id.result.field
  - Step status references: $step_id.status

Supported boolean operators:
  and, or, not

Examples:
  $step_1.result.count > 0
  $step_1.status == "COMPLETED" and $step_2.result.type == "calendar"
  not $step_1.result.is_empty

NOT supported (V1):
  - Function calls: len($step_1.result.items) > 0
  - Nested expressions: ($a > $b) and ($c or $d)
  - Regex matching
  - Array indexing
  - Arithmetic
```

**Implementation:** Simple recursive descent parser. No eval(), no code generation, no sandbox needed.

**Rationale:** Simple comparisons cover 90%+ of practical conditional edge cases. Complex expressions add parser complexity and security concerns without proportional value in V1.

**V2:** Extended expression language with functions, array indexing, and regex.

**Affects:** Epic 3.2.2 (ConditionalEdgeEvaluator)

---

### Q11: Sub-Step Event Rate Limiting -- 1 per Step per 500ms

**Decision:** Sub-step observability events (agent tool calls, LLM calls forwarded from Fabric) are rate-limited to max 1 event per step per 500ms.

```text
Rate limit:
  - Key: (dag_id, step_id)
  - Window: 500ms
  - Max events per window: 1
  - Excess events: silently dropped (counted in telemetry)

Applied to:
  - fabric.agent.*.tool_call.* events
  - fabric.agent.*.llm_call.* events
  - Forwarded to IDeltaEmitPort for user-facing progress
```

**Rationale:** Sub-step events can be high-frequency (agent making multiple tool calls per second). Without rate limiting, IDeltaEmitPort would flood DeltaBus and Concierge's 500ms aggregation window would still batch them. Rate limiting at source reduces bus load and ensures progress updates are digestible.

**Affects:** Epic 3.2.7 (Sub-Step Observability pass-through)

---

## Alternatives Considered

### Alternative: Resolve All Questions Individually as Separate ADRs

**Rejected because:** Q3-Q11 are tactical design decisions, not major architectural shifts. Individual ADRs would create 9 documents for decisions that are each 2-3 paragraphs. Batch resolution keeps the ADR directory focused on structural decisions while providing the same traceability.

---

## Consequences

### Positive

- All 11 open questions from S26 are now resolved or explicitly deferred
- Each decision has clear rationale and V2 upgrade path
- Deferred items (Q7, Q9) have explicit reintroduction criteria

### Negative

- Batch ADR is longer and covers multiple concerns (trade-off vs. 9 separate documents)
- Q7/Q9 deferral means no cost or quality visibility in V1

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Q10 expression language too limited | Medium | Low | Covers 90%+ of cases; V2 extends |
| Q5 abort-previous loses work | Low | Medium | Compensation preserves side effects; user can re-trigger |
| Q11 rate limit drops important events | Low | Low | Telemetry counts dropped events; adjustable threshold |

---

## Implementation

### Cross-Reference to Implementation Epics

| Question | Epic | Component |
|----------|------|-----------|
| Q3 | 5.1.5 | ConnectorLifecycleManager health subscription |
| Q4 | 2.2.2 | DAGExecutor wave dispatch |
| Q5 | 4.2.3 | WorkflowSupervisor concurrent run |
| Q6 | 4.2.5 | CrossWorkflowResolver param merge |
| Q7 | -- | Deferred to V2 |
| Q8 | 4.2.7 | GapDetector classification |
| Q9 | -- | Deferred to V2 |
| Q10 | 3.2.2 | ConditionalEdgeEvaluator |
| Q11 | 3.2.7 | Sub-Step Observability rate limiter |

### Testing Strategy

- [ ] Q3: Integration test -- ConnectorLifecycleManager receives Fabric health events
- [ ] Q4: Unit test -- safety_band re-read at wave boundary, NOT mid-wave
- [ ] Q5: Integration test -- concurrent trigger aborts previous run
- [ ] Q6: Unit test -- parent overrides > sub-workflow defaults > system defaults
- [ ] Q8: Unit test -- exact field match: added field = drift, removed = drift, optional added = no drift
- [ ] Q10: Unit test -- parser accepts valid expressions, rejects functions/regex
- [ ] Q11: Unit test -- rate limiter drops excess events within 500ms window

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-11 | K1 Architecture Team | Initial batch resolution -- Q3 through Q11 |
