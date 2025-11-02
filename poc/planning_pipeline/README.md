# PoC 2.4: 4-Stage Planning Pipeline

**Status:** Ready for Implementation
**Objective:** Validate LLM-powered planning with 4-stage pipeline (Sketch → Expand → Validate → Commit)
**Target Latency:** <2.5s P95

## Quick Start

```bash
cd d:\familyos\poc\planning_pipeline

# Run the planning pipeline
python poc_planning_pipeline.py

# This will:
# 1. Use shared llm_provider from d:\familyos\poc\llm_provider.py
# 2. Run 3 test planning scenarios
# 3. Measure latency for each stage
# 4. Validate against <2.5s SLO
```

## Architecture

**4-Stage Pipeline:**

1. **Sketch (LLM)** — 150-500ms
   - Generate high-level plan using LLM
   - Structured JSON output (intent + steps)
   - Few-shot examples for consistency

2. **Expand (Deterministic)** — <1ms
   - Fill tool schemas from registry
   - Add latency hints, cost hints, capabilities

3. **Validate (Two-Tier)** — <1ms + 50-100ms (risky plans only)
   - Tier 1 (Rules): Check structure, cycles, capabilities, budget
   - Tier 2 (Arbiter): LLM safety check for AMBER/RED plans

4. **Commit (Persistence)** — <10ms
   - Serialize to FlatBuffers (JSON in PoC)
   - Write to K0 WAL (simulated as in-memory store)

## Files

- `poc_planning_pipeline.py` — Main implementation (4 stages + tests)
- `POC_PLANNING_PIPELINE_SPEC.md` — Full specification with ADR references
- `README.md` — This file

## Key Features

✅ **Uses shared LLM provider** from `d:\familyos\poc\llm_provider.py`
✅ **Fallback chain:** Local → Groq → OpenRouter → Mock
✅ **Mock tool registry** with 6 tools (weather, calendar, restaurants, etc)
✅ **Two-tier validation** (fast rules + selective LLM arbiter)
✅ **Comprehensive metrics** (latency per stage, SLO compliance)
✅ **Full ADR integration** (ADR-0007 + dependencies)

## Related ADRs

- **ADR-0001** — K0/K1 Kernel Split (Planner is K1 AI Agent)
- **ADR-0002** — Actor Model (Planner uses Actor+mailbox)
- **ADR-0006** — 3-Phase Orchestration (Orchestrator executes plans)
- **ADR-0007** ⭐ — 4-Stage Planning Pipeline (THIS POC)
- **ADR-0010** — Capability-Based Security (validation checks)
- **ADR-0011** — FlatBuffers Serialization (Stage 4 uses FlatBuffers)

## Test Scenarios

1. **Multi-intent:** "Book dinner with my wife at 7pm and check if it'll rain"
   - Tests: Multi-step plan, schema lookup, dependency tracking

2. **Simple query:** "What time is my next meeting?"
   - Tests: Simple plan, calendar tool, basic validation

3. **Location-based:** "Check the weather and show me restaurant options nearby"
   - Tests: Parallel steps, restaurant search, filtering

## Expected Output

```
======================================================================
PLANNING: Book dinner with my wife at 7pm and check if it'll rain
======================================================================

STAGE 1: SKETCH (LLM)
--------------------------------------------------
[Sketch] Complete: 4 steps, 450.2ms

STAGE 2: EXPAND (Schema Lookup)
--------------------------------------------------
[Expand] Complete: 4 steps, 0.8ms

STAGE 3: VALIDATE (Tier 1 - Rules)
--------------------------------------------------
[Validate Tier1] PASS: 0 errors, 0.05ms

STAGE 4: COMMIT (Persistence)
--------------------------------------------------
[Commit] Complete: a1b2c3d4-e5f6-..., 7.3ms

======================================================================
✅ PLANNING COMPLETE
======================================================================
Flow ID: a1b2c3d4-e5f6-...

Latencies:
  Sketch:          450.2ms
  Expand:            0.8ms
  Validate Tier1:    0.05ms
  Validate Tier2:    0.0ms
  Commit:            7.3ms
  TOTAL:           458.4ms
  SLO:             <2500ms (✅ PASS)

Plan Summary:
  Intent: plan_dinner
  Steps: 4
  Complexity: medium
```

## Success Criteria

- ✅ All 4 stages complete end-to-end
- ✅ Sketch produces valid JSON >99% success rate
- ✅ Total latency <2.5s P95
- ✅ Validation catches invalid plans (cycles, missing tools, budget violations)
- ✅ Arbiter handles safety checks for AMBER/RED plans
- ✅ Committed plans persisted to simulated K0 WAL

## Configuration

Edit `poc_planning_pipeline.py` to customize:

```python
# LLM settings
sketch_model = "gpt-4o-mini"  # or local SLM
sketch_temperature = 0.3      # Low for consistency
sketch_max_tokens = 800

# Validation settings
max_steps = 12                 # Max plan complexity
max_latency_budget = 10000     # ms
max_cost_budget = 1.0          # dollars

# Arbiter (Tier 2)
trigger_bands = ["AMBER", "RED", "BLACK"]  # When to invoke arbiter
```

## Metrics

Pipeline tracks:
- Total plans processed
- Successful plans committed
- Failed validations (Tier 1 vs Tier 2)
- Arbiter invocations
- Latency per stage
- SLO compliance

## Next Steps

1. Run this PoC with Groq API (fast LLM for sketching)
2. Integrate with K1 Orchestrator
3. Add replay + refinement logic
4. Performance optimization (caching, batching)
5. Production deployment

---

**Created:** 2025-11-01
**Based on:** ADR-0007: 4-Stage Planning Pipeline
**Implementation Status:** ✅ Ready for execution
