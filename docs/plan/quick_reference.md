# DEPENDENCY_MAP Population - Quick Reference Guide

**Status:** Ready to Start
**First Batch:** Batch 1 (Layer 1 - 4 modules, 2-3 hours)
**Total Timeline:** 4 phases × 12 batches = 8-10 weeks

---

## 📋 PHASE 1: Core Layer Logic (Weeks 1-4, 12 Batches)

### Batch-by-Batch Summary

```
Week 1:
  Batch 1 (2-3h): Layer 1 Input (4 modules) ← START HERE
  Batch 2 (2-3h): Layer 2 Orchestration (3 modules)
  
Week 2:
  Batch 3 (2-3h): Layer 3 Agent Lifecycle (6 modules)
  Batch 4 (2-3h): Layer 3 Model Hub (7 modules)
  
Week 3:
  Batch 5 (3-4h): Layer 3 Tools & Dialogue (9 modules)
  Batch 6 (2-3h): Layer 4 Runtime (4 modules)
  Batch 7 (2-3h): Layer 4 Learning (4 modules)
  
Week 4:
  Batch 8 (3-4h): Layer 5 Infrastructure (7 modules)
  Batch 9 (2-3h): Layer 5 Safety & Policy (3 modules)
  Batch 10 (2-3h): Layer 5 Observability (4 modules)
  Batch 11 (2-3h): Layer 5 Configuration (3 modules)
  Batch 12 (2h):  Layer 5 Connectors (2 modules)
```

**Total: 52 modules populated across 5 layers**

---

## 🎯 What Gets Done Each Batch

### Batch 1: Layer 1 Input Processing (2-3 hours)

**4 Modules:**
1. `stream_switch` → ADR-0056, 0057
2. `operators` → ADR-0056a, 0056b
3. `intent_router` → ADR-0058, 0058a
4. `meta_policy` → ADR-0057c, 0058b

**Tasks:**
- [ ] Update Module Inventory table with ADR references
- [ ] Add Dependency Details for each module (imports/exports/perf)
- [ ] Create "Layer 1 Inter-Module Communication" diagram
- [ ] Link all performance budgets to ADR-0024

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 1 section (Lines 370-420)

**Success:** All 4 modules have ADR numbers (no "TBD")

---

### Batch 2: Layer 2 Orchestration (2-3 hours)

**3 Modules:**
1. `planner` → ADR-0007, 0007a-0007d
2. `orchestrator` → ADR-0006, 0006a-0006d
3. `protocol_monitor` → ADR-0003, 0003a-0003d

**Tasks:**
- [ ] Update Module Inventory with ADR-0006/0007 references
- [ ] Add 3-phase orchestration diagram
- [ ] Add 4-stage planning pipeline diagram
- [ ] Document 6 protocols validated by protocol_monitor

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 2 section (Lines 440-500)

**Success:** ADR-0006 and ADR-0007 fully documented

---

### Batch 3: Layer 3 Agent Lifecycle (2-3 hours)

**6 Modules:**
1. `registry` → ADR-0005
2. `hire_fire` → ADR-0005, 0005a
3. `supervisor` → ADR-0002b
4. `personality` → ADR-0005e
5. `mailbox` → ADR-0002a
6. `active_roster` → ADR-0005b

**Tasks:**
- [ ] Add 6-state FSM diagram (PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED)
- [ ] Document supervisor escalation policy
- [ ] Add mailbox MPSC queue design
- [ ] Add registry + personality integration

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 3, Section "3a: Agent Lifecycle" (Lines 540-580)

**Success:** All 6 modules have Actor Model pattern references

---

### Batch 4: Layer 3 Model Hub (2-3 hours)

**7 Modules:**
1. `router` → ADR-0001b, 0018
2. `placement_planner` → ADR-0027, 0027a-0027c
3. `adapters` → ADR-0018, 0019
4. `kv_cache_broker` → ADR-0025, 0060
5. `prompt_library` → ADR-0020
6. `fallback_cascade` → ADR-0019
7. `safety_filter` → ADR-0035, 0032

**Tasks:**
- [ ] Document router logic (which provider for which call)
- [ ] Add placement cascade diagram (NPU→GPU→CPU→Remote)
- [ ] List 4 AI agents served (Concierge, Planner, Researcher, Safety Watch)
- [ ] Add KV cache management strategy (128MB budget)
- [ ] Document fallback cascade with cost awareness

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 3, Section "3b: Model Hub" (Lines 600-650)

**Success:** 4 AI agents explicitly listed with Model Hub dependencies

---

### Batch 5: Layer 3 Tools & Dialogue (3-4 hours)

**9 Modules:**
- Tool Execution (5): runner, sandbox, registry, adapters, control
- Dialogue Management (4): scoreboard, state_tracker, turn_manager, repair

**Tasks:**
- [ ] Add three-tier sandbox diagram (Protocol × Sandbox × Band)
- [ ] Document MCP protocol adapter architecture
- [ ] Add turn boundary diagram (explicit vs implicit)
- [ ] Document message coalescing strategy
- [ ] Add repair/error recovery protocol

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 3, Sections "3c" & "3d" (Lines 680-750)

**Success:** Three-tier sandbox architecture fully documented

---

### Batch 6: Layer 4 Runtime (2-3 hours)

**4 Modules:**
1. `leases` → ADR-0010
2. `mailbox` → ADR-0002a
3. `session_state` → ADR-0017, 0017a-0017f
4. `flow_engine` → ADR-TBD

**Tasks:**
- [ ] Add 6-section SessionState architecture (Beliefs, Scoreboard, Control, Persona, Multimodal, Meta)
- [ ] Document memory budget (<64KB per session)
- [ ] Add FlatBuffers serialization (<1ms)
- [ ] Document capability-based security (ADR-0010)

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 4, Section "4a: Runtime" (Lines 810-860)

**Success:** 6-section SessionState fully documented

---

### Batch 7: Layer 4 Learning (2-3 hours)

**4 Modules:**
1. `learning_loop` → ADR-0059
2. `feedback_collector` → ADR-0059a
3. `drift_detector` → ADR-0059b
4. `model_updater` → ADR-0059c

**Tasks:**
- [ ] Document feedback signal weighting (explicit 1.0, implicit 0.5, behavioral 0.2)
- [ ] Add drift detection threshold (>20% = retrain)
- [ ] Document weight update + config hot-reload flow

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 4, Section "4b: Learning" (Lines 880-920)

**Success:** Learning loop feedback signals fully documented

---

### Batch 8: Layer 5 Infrastructure Core (3-4 hours)

**7 Modules:**
1. `scheduler` → ADR-0028
2. `backpressure` → ADR-0061
3. `thermal` → ADR-0026
4. `budgets` → ADR-0024, 0031
5. `cache` → ADR-0025
6. `rate_limiting` → ADR-TBD
7. `storage_connector` → ADR-0020

**Tasks:**
- [ ] Add WFQ scheduler 4-tier priority diagram
- [ ] Add backpressure 3-tier cascade (soft→hard→OOM)
- [ ] Document thermal state machine (5°C hysteresis)
- [ ] Add KV cache + prompt cache architecture
- [ ] Document multi-tier storage (L1 RAM / L2 SSD / L3 S3)

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 5, Section "5a: Infrastructure" (Lines 950-1020)

**Success:** Scheduler + backpressure + thermal fully documented

---

### Batch 9: Layer 5 Safety & Policy (2-3 hours)

**3 Modules:**
1. `policy` → ADR-0032, 0033
2. `pii_detector` → ADR-0035
3. `arbiter` → ADR-0052

**Tasks:**
- [ ] Add 3-band privacy model diagram (GREEN/AMBER/RED)
- [ ] Document PII detection 3-tier cascade (regex→ONNX→LLM)
- [ ] Add arbiter approval workflow
- [ ] Document egress enforcement per band

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 5, Section "5b: Safety & Policy" (Lines 1050-1100)

**Success:** 3-band privacy model fully documented

---

### Batch 10: Layer 5 Observability (2-3 hours)

**4 Modules:**
1. `tracing` → ADR-0029
2. `metrics` → ADR-0030
3. `receipts` → ADR-0038
4. `perf_harness` → ADR-0066

**Tasks:**
- [ ] Document OpenTelemetry tracing architecture
- [ ] Add Prometheus RED method metrics schema
- [ ] Document receipt types (4 types)
- [ ] Add performance harness synthetic load profiles

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 5, Section "5c: Observability" (Lines 1130-1180)

**Success:** Observability framework fully documented

---

### Batch 11: Layer 5 Configuration (2-3 hours)

**3 Modules:**
1. `global` → ADR-TBD
2. `schemas` → ADR-0011, 0012, 0013
3. `config_manager` → ADR-TBD, 0042

**Tasks:**
- [ ] Document 5 global config files (agents.yml, models.yml, tools.yml, scheduler.yml, policy.yml)
- [ ] Reference 76 FlatBuffers schemas
- [ ] Document hot-reload mechanics
- [ ] Add SSE listener for K0 config sync

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 5, Section "5d: Configuration" (Lines 1210-1260)

**Success:** Configuration hot-reload architecture documented

---

### Batch 12: Layer 5 Connectors (2 hours)

**2 Modules:**
1. `k0_bridge` → ADR-0001a, 0022
2. `model_hub_client` → ADR-0001b, 0018

**Tasks:**
- [ ] Document K0 bridge batching (10-50 msgs / 100ms)
- [ ] Add compression + port specifications
- [ ] Document Model Hub client unified interface

**Where:** `docs/plan/DEPENDENCY_MAP.md` → Layer 5, Section "5e: Connectors" (Lines 1290-1320)

**Success:** K0 bridge protocol fully documented

---

## 📊 Completion Tracking

### After Phase 1 (Week 4):
- ✅ 52 modules have ADR references
- ✅ 0 remaining "TBD" entries
- ✅ All inter-layer dependencies mapped
- ✅ All performance budgets linked
- ✅ Layer boundary enforcement validated

### Phase 1 Gate Criteria:
- ✅ ADR-0006 (3-phase orchestration) implemented
- ✅ ADR-0007 (4-stage planning) implemented
- ✅ ADR-0003 validates all 6 protocols
- ✅ ADR-0028 (WFQ scheduler) operational

---

## 🚀 Next Steps After Phase 1

1. **Phase 2 (Weeks 5-8):** External systems integration
   - Voice I/O adapters (ADR-0056)
   - LLM providers (OpenAI, Anthropic, etc.)
   - MCP tool integration (5+ tools)
   - Observability backends

2. **Phase 3 (Weeks 9-10):** K0 Bridge & Multi-Device Sync
   - K0 bridge protocols (ADR-0042/0043/0044)
   - Multi-device family sync (ADR-0050)
   - LAN sync (<1ms) + P2P E2EE (<500ms)

3. **Phase 4 (Weeks 11-12):** Testing & UX
   - Integration testing (WARD framework)
   - E2E test scenarios
   - UX polish + conversational delight

---

## 📚 Key Documents

- **This Guide:** `docs/plan/QUICK_REFERENCE.md` (you're reading it)
- **Full Roadmap:** `docs/plan/POPULATION_ROADMAP.md` (detailed batch specs)
- **Target Document:** `docs/plan/DEPENDENCY_MAP.md` (what we're populating)
- **Memory Notes:** Use `mcp_memory_mem_find()` with tag `batch-1-ready` for detailed Batch 1 instructions

---

## 💡 Pro Tips

1. **Small Pieces:** Each batch is 2-4 hours. Stop when done, no merging batches.
2. **Sequential Order:** Don't skip ahead. Each batch builds on previous layer foundations.
3. **Verify Acceptance Criteria:** Check all criteria before marking batch done.
4. **Link ADRs:** Always cite ADR numbers, never "TBD".
5. **Performance Budgets:** Every latency-critical module links to ADR-0024.
6. **Diagrams:** Use Mermaid format for all architecture diagrams.

---

## Questions?

Refer to:
- **Batch Details:** `docs/plan/POPULATION_ROADMAP.md`
- **Memory Notes:** Search with tag `batch-1-ready`, `batch-2-ready`, etc.
- **Architecture:** `docs/whiteboard.md` (21,123 lines of K1 specs)

---

**Ready to start? → Begin with BATCH 1: Layer 1 Input Processing**

