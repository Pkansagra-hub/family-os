# BATCH 1 Quick Start Guide

**Status:** 🚀 READY TO START
**Batch Owner:** Infrastructure Team
**Timeline:** Weeks 1-4
**Total Effort:** 80 hours (22 issues)
**Deliverables:** 4 documents + updated DEPENDENCY_MAP.md

---

## What We're Building

**Goal:** Populate DEPENDENCY_MAP.md with complete ADR logic for **all 19 Layer 5 (Infrastructure) modules** by replacing every "TBD" reference with concrete decision logic from the ADRs.

**Output:** 
1. `docs/plan/ADR_MASTER_INDEX.csv` - Master index of all 63+ ADRs
2. `docs/plan/DEPENDENCY_MAP.md` - Updated Layer 5 sections (no TBD)
3. `docs/plan/EVENT_BUS_SPECIFICATION.md` - Topic topology + SLAs
4. `docs/plan/K0_BRIDGE_PORT_MAPPING.md` - Port P01-P20 definitions
5. `docs/plan/DEPENDENCY_MAP_VALIDATION_REPORT.md` - Validation report

---

## Batch 1 Structure

```
BATCH 1: Foundation & Layer 5 (Weeks 1-4)
│
├─ WEEK 1: EPIC 1.1 - ADR Indexing (5 issues, 24h)
│  └─ Issue 1.1.1: Extract ADR metadata from docs/architecture/decisions/
│  └─ Issue 1.1.2: Build ADR dependency graph (topological sort)
│  └─ Issue 1.1.3: Map ADRs to 52 modules (bidirectional)
│  └─ Issue 1.1.4: Add performance SLOs (trace to ADR-0024)
│  └─ Issue 1.1.5: Finalize ADR_MASTER_INDEX.csv
│
├─ WEEK 2: EPIC 1.2 - Infrastructure Core 7 Modules (5 issues, 16h)
│  ├─ Issue 1.2.1: scheduler (ADR-0028 → WFQ 4-tier priority)
│  ├─ Issue 1.2.2: backpressure (ADR-0061 → 3-tier cascade)
│  ├─ Issue 1.2.3: thermal, budgets, cache (ADR-0026/0024/0025)
│  ├─ Issue 1.2.4: rate_limiting, storage_connector (ADR-0028c/0020/0022)
│  └─ Issue 1.2.5: event_bus (ADR-0004a/0045/0048 → pub/sub backbone)
│
├─ WEEK 2-3: EPIC 1.3 - Safety & Policy 5 Modules (3 issues, 6h)
│  ├─ Issue 1.3.1: policy (ADR-0032 → GREEN/AMBER/RED bands)
│  ├─ Issue 1.3.2: pii_detector (ADR-0035 → 3-tier detection)
│  └─ Issue 1.3.3: arbiter (ADR-0052 → HITL approval workflow)
│
├─ WEEK 3-4: EPIC 1.4 - Observability & Config 7 Modules (2 issues, 10h)
│  ├─ Issue 1.4.1: tracing, metrics, receipts, perf_harness (ADR-0029/0030/0038/0066)
│  └─ Issue 1.4.2: global, schemas, config_manager (ADR-0011/0012/0013/0042/0043/0044)
│
├─ WEEK 4: EPIC 1.5 - Event Bus & K0 Bridge Spec (3 issues, 12h)
│  ├─ Issue 1.5.1: Define 6+ event bus topics with schemas
│  ├─ Issue 1.5.2: Map K0 bridge ports P01-P20
│  └─ Issue 1.5.3: Document Layer 1→L5→L2 async pattern
│
└─ WEEK 4: EPIC 1.6 - Validation & Gate Criteria (4 issues, 12h)
   ├─ Issue 1.6.1: Cross-reference validation (grep for TBD → 0 results)
   ├─ Issue 1.6.2: Performance budget validation (trace all budgets to ADR-0024)
   ├─ Issue 1.6.3: Dependency graph validation (topological sort, no cycles)
   └─ Issue 1.6.4: Create validation report

GATE CRITERIA (Must all pass):
✅ Zero TBD references in DEPENDENCY_MAP.md
✅ All 19 Layer 5 modules fully documented
✅ All ADRs traced and valid
✅ Performance budgets complete and consistent
✅ Dependency graph acyclic
✅ Validation report signed off
```

---

## Quick Checklist

### WEEK 1 (ADR Indexing)
- [ ] Read all ADRs from `docs/architecture/decisions/`
- [ ] Create ADR_MASTER_INDEX.csv with 63+ rows
- [ ] Verify: no broken ADR references
- [ ] Verify: all sub-ADRs linked to primaries
- [ ] Verify: dependencies form valid DAG (no cycles)

### WEEK 2 (Infrastructure Core)
- [ ] Update DEPENDENCY_MAP.md Layer 5 → "5a: Infrastructure"
- [ ] Replace scheduler TBD → ADR-0028 logic
- [ ] Replace backpressure TBD → ADR-0061 logic
- [ ] Replace thermal/budgets/cache TBDs → ADR-0026/0024/0025 logic
- [ ] Replace rate_limiting/storage TBDs → ADR-0028c/0020/0022 logic
- [ ] Document event_bus (ADR-0004a) as L5 foundation
- [ ] Verify: no TBD in these 7 modules

### WEEK 2-3 (Safety & Policy)
- [ ] Update DEPENDENCY_MAP.md Layer 5 → "5b: Safety & Policy"
- [ ] Replace policy TBD → ADR-0032 (GREEN/AMBER/RED bands)
- [ ] Replace pii_detector TBD → ADR-0035 (3-tier detection)
- [ ] Replace arbiter TBD → ADR-0052 (HITL approvals)
- [ ] Verify: all band-specific behaviors documented
- [ ] Verify: no TBD in these 5 modules

### WEEK 3-4 (Observability & Config)
- [ ] Update DEPENDENCY_MAP.md Layer 5 → "5c: Observability"
- [ ] Replace tracing TBD → ADR-0029 (OpenTelemetry + cognitive_trace_id)
- [ ] Replace metrics TBD → ADR-0030 (Prometheus RED method)
- [ ] Replace receipts TBD → ADR-0038 (immutable audit ledger)
- [ ] Replace perf_harness TBD → ADR-0066/0070 (synthetic load + regression detection)
- [ ] Update DEPENDENCY_MAP.md Layer 5 → "5d: Configuration"
- [ ] Replace global/schemas/config_manager TBDs → ADR-0011/0012/0013/0042/0043/0044
- [ ] Verify: K0 bridge SSE integration documented
- [ ] Verify: no TBD in these 7 modules

### WEEK 4 (Event Bus & K0 Bridge)
- [ ] Define 6+ event bus topics (IntentDetected, UserInput, VoiceCommand, BargeIn, StateChanged, MetricEmitted, ConfigUpdated)
- [ ] For each topic: document publisher, subscribers, payload schema, SLA
- [ ] Map K0 bridge ports P01-P20 (20 points of integration)
- [ ] Document Layer 1→L5→L2 async communication pattern
- [ ] Create example trace (user input → intent event → orchestration)
- [ ] Verify: all ports have latency budgets

### WEEK 4 (Validation)
- [ ] Grep DEPENDENCY_MAP.md for "TBD" → should return 0 results
- [ ] Trace all performance budgets to ADR-0024
- [ ] Verify all module→ADR mappings are bidirectional
- [ ] Run topological sort on dependency graph (should succeed)
- [ ] Verify no ADR references missing ADRs
- [ ] Create DEPENDENCY_MAP_VALIDATION_REPORT.md
- [ ] Get sign-off from Architecture Team
- [ ] GATE: Ready for Batch 2

---

## Key ADR References for Batch 1

**Infrastructure Core (WEEK 2):**
- ADR-0028: WFQ scheduler (4-tier priority, anti-starvation)
- ADR-0061: 3-tier backpressure cascade (warn/backpressure/drop)
- ADR-0026: Thermal hysteresis matrix (COOL/WARM/HOT/CRITICAL)
- ADR-0024: Performance budgets (TTFT, E2E, per-component SLOs)
- ADR-0025: KV cache management (LRU-LFU hybrid, Zstd compression)
- ADR-0028c: Token bucket rate limiting
- ADR-0020: Multi-tier storage (L1 RAM / L2 SSD K0 WAL / L3 S3)
- ADR-0022: K0 bridge bounded batching (10-50 msgs / 100ms)
- ADR-0004a: Event bus pub/sub backbone
- ADR-0045: Agent SSE coordination
- ADR-0048: K1 internal event bus

**Safety & Policy (WEEK 2-3):**
- ADR-0032: Band-based egress rules (GREEN/AMBER/RED)
- ADR-0035: PII detection & redaction (regex/ONNX/LLM)
- ADR-0036: E2EE for RED band (AES-256-GCM)
- ADR-0010: Capability-based security (CBAC tokens)
- ADR-0052: HITL approval workflows (standard/escalated/executive)

**Observability & Config (WEEK 3-4):**
- ADR-0029: OpenTelemetry tracing (cognitive_trace_id propagation)
- ADR-0030: Prometheus metrics (RED method: Rate/Errors/Duration)
- ADR-0038: Audit trail receipts (Merkle tree chaining, immutable)
- ADR-0066: Developer testing harness (LLM eval + synthetic users)
- ADR-0070: Observability evaluation infrastructure
- ADR-0011: FlatBuffers serialization strategy
- ADR-0012: 76 FlatBuffers schemas across 5 layers
- ADR-0013: Schema versioning (90-day deprecation workflow)
- ADR-0042: K0 SSE event streaming
- ADR-0043: SSE topic taxonomy
- ADR-0044: K0 bridge HTTP/2 + FlatBuffers

**Event Bus & K0 Bridge (WEEK 4):**
- ADR-0004a: Event bus architecture (L1→L5→L2 async pattern)
- ADR-0001a: K0-K1 bridge communication protocol
- ADR-0022: K0 bridge bounded batching
- ADR-0042/0043/0044: K0 bridge protocols (SSE, topic taxonomy, HTTP/2)

---

## Documentation Templates

### Module Section Template (for DEPENDENCY_MAP.md)

```markdown
**module_name** (`k1/path/to/module/`)

ADR References: ADR-XXXX, ADR-XXXXa, ADR-XXXXb (sub-ADRs)

Decision Logic:
  - [Main decision from primary ADR]
  - [Sub-decision from sub-ADR a]
  - [Sub-decision from sub-ADR b]
  - [Performance implications]

Performance Budget:
  - Operation latency: XXms P95 (source: ADR-XXXX)
  - Memory usage: XXkB (source: ADR-XXXX)
  - [Other SLOs]

Dependencies:
  - Imports: [other modules, tracing this to ADR]
  - Exports to: [other modules, tracing this to ADR]

External Connections:
  - [Service/System integration]
  - [K0 bridge if applicable]

Implementation Notes:
  - Reference: ADR-XXXXd (implementation strategy)
  - Reference: ADR-YYYY (related decision)
```

### Event Bus Topic Template

```markdown
| Topic | Publisher | Subscribers | Payload Schema | SLA |
|-------|-----------|-------------|----------------|-----|
| topic.name | module_a (L1) | module_b (L2), module_c (L5) | FieldType1, FieldType2 | <Xms P95 |
```

### K0 Bridge Port Template

```markdown
| Port | Purpose | Protocol | From | To | Latency Budget | Batching |
|------|---------|----------|------|-----|-----------------|----------|
| P01 | State sync | FlatBuffers | K1 | K0 | <500ms | 10-50 msgs / 100ms |
```

---

## Success Metrics

**WEEK 1:**
- ✅ ADR_MASTER_INDEX.csv created with 63+ rows
- ✅ All ADRs indexed with dependencies
- ✅ Bidirectional ADR↔Module mapping complete

**WEEK 2:**
- ✅ 12 modules fully documented (infra + safety + 1 config)
- ✅ Zero TBD references in those sections
- ✅ All performance budgets traced to ADRs

**WEEK 3-4:**
- ✅ All 19 Layer 5 modules documented
- ✅ Event bus topics finalized (6+)
- ✅ K0 bridge ports mapped (P01-P20)
- ✅ Validation report complete
- ✅ GATE PASSED: ready for Batch 2

---

## Who Does What

**Infrastructure Team (Owner):**
- EPIC 1.1: ADR indexing
- EPIC 1.2: Infrastructure core modules (scheduler, backpressure, thermal, budgets, cache, rate_limiting, storage)
- EPIC 1.4: Configuration modules (global, schemas, config_manager)
- EPIC 1.5: K0 bridge port mapping
- EPIC 1.6: Validation

**Safety/Security Team (Contributor):**
- EPIC 1.3: Safety & policy modules (policy, pii_detector, arbiter)
- EPIC 1.5: K0 bridge security ports

**Observability Team (Contributor):**
- EPIC 1.4: Observability modules (tracing, metrics, receipts, perf_harness)
- EPIC 1.5: Event bus topics

---

## Next Steps After Batch 1

Once GATE CRITERIA pass:

1. **Batch 2 Planning:** Core Layers 2-4 (Weeks 5-8)
   - Layer 4: Runtime Core (SessionState, learning loop)
   - Layer 3: Execution (agents, model hub, tools, dialogue)
   - Layer 2: Orchestration (planner, orchestrator, protocol monitor)

2. **Batch 3 Planning:** Input & Integration (Weeks 9-12)
   - Layer 1: Input Processing (stream_switch, operators, intent_router, meta_policy)
   - Voice pipeline integration
   - External systems (LLM providers, tools, observability backends)
   - Performance critical paths refinement
   - Final validation & roadmap consolidation

3. **Phase 2 Start:** Code Implementation
   - Begin coding Layer 5 modules (highest priority)
   - Use DEPENDENCY_MAP.md as architecture specification
   - All ADR decisions embedded in module code via comments
   - Performance budgets enforced via integration tests

---

## Questions?

- **ADR uncertainty?** → Check `docs/architecture/decisions/[ADR_ID].md`
- **Performance budget questions?** → Check ADR-0024 master table
- **Module structure questions?** → Check `docs/k1_module_analysis.md`
- **Whiteboard design?** → Check `docs/whiteboard.md` (21,123 lines of specs)

---

**START DATE:** Week 1 (Date TBD)
**BATCH 1 OWNER:** Infrastructure Team
**EXPECTED COMPLETION:** End of Week 4
**GATE SIGN-OFF:** Architecture Team
