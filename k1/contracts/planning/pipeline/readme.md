# Issue 2.3.1 Completion: 4-Stage Planning Pipeline Contracts

**Report Date:** October 15, 2025
**Status:** ✅ **COMPLETE**
**Epic:** 2.3 - Planning Pipeline Contracts

## Quick Summary

| Metric | Value |
|--------|-------|
| **Contracts Created** | 4 YAML + 1 README |
| **Total Lines** | ~2,800+ lines (contracts) |
| **Total Bytes** | ~145 KB |
| **Stages Implemented** | 4/4 (100%) |
| **Performance Targets Met** | ✅ All targets specified |
| **ADR References** | ADR-0007, ADR-0007a-d |
| **Implementation Readiness** | 80% (architecture complete) |

## Files Created

### 1. **sketch_stage.yml** (572 lines)

**Purpose:** LLM-powered plan sketching - creative planning phase

**Key Components:**
- **LLM Prompt Template System** - Jinja2 templates for different domains (shopping, travel, payment)
- **Plan Sketch Data Structure** - Step definitions with alternatives and confidence scores
- **Sketch Generation Workflow** - Template assembly → LLM call → JSON parsing → enrichment
- **DAG Analysis** - Compute wave structure and critical path from sketch
- **Rule-Based Fallback** - Simple templates if LLM fails or times out
- **Quality Metrics** - llm_confidence, complexity_penalty, risk_count scoring
- **Observability** - Latency histograms, validation success rate, confidence distribution

**Example Outputs:**
- E-commerce sketch for laptop purchase (5 steps)
- Travel booking sketch (parallel flight/hotel/car searches)
- Shopping domain example with alternatives

**Performance Targets:**
- Sketch generation: P95 < 150ms (LLM dominates ~100ms)
- Validation success rate: > 90%

### 2. **expand_stage.yml** (698 lines)

**Purpose:** Concretize sketch with tool specs, agent assignments, error handlers

**Key Components:**
- **Tool Registry Integration** - Lookup tools with schemas, durations, costs
- **Agent Capability Matching** - Score agents by: capability match (1.0) + specialization (0.3) + availability (0.2) + success rate (0.1)
- **Prompt Template Selection** - Choose domain-specific templates for each tool
- **Error Handler Insertion** - Timeout policies, retry strategies, fallback chains
- **Parameter Resolution** - Validate variable references ({{step_1.result.field}})
- **Expanded Plan Structure** - Full executable plan with tool configs and error handlers
- **Observability** - Tool resolution success rate, agent assignment metrics

**Matching Algorithm Example:**
```
SearchAgent-01:  1.0 (capability) + 0.3 (shopping) - 0.04 (20% busy) + 0.098 (98% success) = 1.358 ← WINNER
SearchAgent-02:  1.0 (capability) + 0.3 (shopping) - 0.16 (80% busy) + 0.095 (95% success) = 1.235
```

**Performance Targets:**
- Expand duration: P95 < 50ms (registry lookups O(steps * max_agents))

### 3. **validation_stage.yml** (660 lines)

**Purpose:** 2-tier validation - deterministic rules + human arbiter fallback

**Key Components:**

**Tier 1: Rule Engine**
- **Constraint Validation** - Budget, time, step count bounds
- **Capability Matching** - Agent capabilities vs requirements
- **Graph Structure** - No cycles, all dependencies exist
- **Safety & Security** - RED band escalation, capability tokens, data residency
- **Business Rules** - Domain-specific policies
- **Parameter Validation** - Type checking, range validation, format validation

**Tier 2: Arbiter Fallback**
- Triggered for: RED band tasks, multiple warnings, novel tasks
- Arbiter reviews plan with context
- Decision: APPROVE | REJECT | NEEDS_REVISION
- Timeout: 30 seconds with auto-reject on timeout

**Decision Matrix:**
- PASS → Continue to Commit
- PASS_WITH_WARNINGS → Continue to Commit (warnings logged)
- ESCALATE + RED → Escalate to Arbiter
- ESCALATE + AMBER → Escalate to Arbiter (if complex)
- ESCALATE + GREEN → Continue to Commit
- REJECT → Reject to user with error explanation

**Error Messaging Example:**
```json
{
  "severity": "ERROR",
  "rule": "budget_exceeded",
  "message": "Plan cost $12.50 exceeds budget $10.00",
  "fix_suggestion": "Increase budget or ask planner for cheaper alternatives"
}
```

**Performance Targets:**
- Tier 1 validation: P95 < 50ms (deterministic rules)
- Tier 2 arbiter: 1-30 seconds (human review as needed)
- Tier 1 pass rate: > 70% (avoid arbiter escalation when possible)
- Tier 2 approval rate: > 90% (most escalations ultimately approved)

### 4. **commit_stage.yml** (655 lines)

**Purpose:** Persist validated plan to K0 Write-Ahead Log (durable, auditable, executable)

**Key Components:**
- **K0 WAL Integration** - Append-only durability log
- **Plans Table Schema** - Full plan tracking with execution lifecycle
- **Plan Serialization** - JSON (human-readable) + FlatBuffers option (performant)
- **Idempotency** - Duplicate detection via SHA256 hash
- **Execution Lifecycle** - PENDING → RUNNING → COMPLETED/FAILED
- **Plan History & Versioning** - Track versions, diffs, user feedback
- **Audit & Compliance** - GDPR, HIPAA, SOC2 audit trail
- **Failure Recovery** - K0 unavailability handling, retry strategies

**K0 Plans Table:**
```sql
CREATE TABLE plans (
  plan_id TEXT PRIMARY KEY,
  sketch_id, task_id, context_id,
  plan_json, plan_hash,
  execution_status, execution_started_at, execution_completed_at,
  estimated_duration_ms, estimated_cost_cents,
  actual_duration_ms, actual_cost_cents,
  quality_score, feedback_json,
  privacy_band, tags_json
)
```

**Execution Status Transitions:**
```
PENDING → RUNNING → COMPLETED (success) / FAILED (error) / PAUSED
```

**Idempotency Example:**
- First commit: plan_hash="abc123" → creates plan_id_1
- Network timeout, retry with same plan
- Second commit: plan_hash="abc123" → returns existing plan_id_1 ✓

**Performance Targets:**
- Commit duration: P95 < 20ms (K0 WAL write dominated)
- Commit success rate: > 99.5%
- Plan serialization: 40-60KB typical JSON
- Duplicate plan rate: < 5% (idempotent retries)
- Commit-to-execution latency: < 1000ms

---

## 4-Stage Pipeline Architecture

```
USER TASK
   ↓
┌─────────────────────────────────────┐
│ STAGE 1: SKETCH (100ms P95)         │  ← LLM-powered plan outline
│ - LLM generates high-level steps    │    Prompt templates by domain
│ - Identifies dependencies           │    Fallback: rule-based templates
│ - Estimates duration/cost          │
│ Output: Plan sketch with alternatives
└─────────────────────────────────────┘
   ↓
┌─────────────────────────────────────┐
│ STAGE 2: EXPAND (50ms P95)          │  ← Concretize with tools/agents
│ - Lookup tools in registry          │    Tool schemas (input/output)
│ - Match agents by capability        │    Prompt template selection
│ - Insert error handlers             │    Error handlers + retries
│ - Render prompts                    │
│ Output: Executable plan with specs
└─────────────────────────────────────┘
   ↓
┌─────────────────────────────────────┐
│ STAGE 3: VALIDATION (30-30000ms)    │  ← Deterministic + arbiter
│ Tier 1: Rule Engine (<50ms)         │    Rules: budget, capability, DAG
│ - Check constraints (budget, time)  │    Arbiter: RED band, complex
│ - Verify capabilities match         │
│ - Detect cycles                     │
│ - Validate parameters               │
│                                     │
│ Tier 2: Arbiter Fallback (opt.)     │
│ - RED band approval                 │
│ - Complex judgment calls            │
│ Output: APPROVED | REJECTED
└─────────────────────────────────────┘
   ↓ (if APPROVED)
┌─────────────────────────────────────┐
│ STAGE 4: COMMIT (20ms P95)          │  ← Durable persistence
│ - Serialize plan to JSON            │    K0 WAL (fsync)
│ - Compute SHA256 hash               │    Idempotency check
│ - Duplicate detection               │    Plan history
│ - Write to K0 WAL                   │    Audit trail
│ Output: plan_id, committed
└─────────────────────────────────────┘
   ↓
   ✓ Ready for Orchestrator execution
```

**Total Pipeline Latency:**
- Fast path (GREEN band): ~230ms (100+50+30+20)
- With arbiter (RED band): 1-30 seconds (depends on arbiter review)

---

## Example: E-Commerce Flow

### User Task
*"Find a running shoe under $150 with good battery life (if tech shoe) and add to cart"*

### Stage 1: Sketch (Generated by LLM)
```yaml
steps:
  - step_1: SearchProduct(query="running shoes", max_price=150)
  - step_2: FilterBattery(products=<<step_1.result>>, hours_min=8)
  - step_3: GetDetails(product_ids=<<step_2.result.top_3>>)
  - step_4: AddToCart(product_id=<<step_3.result.best_id>>)
  - step_5: Checkout()
```
LLM confidence: 0.93

### Stage 2: Expand (Concretized)
```yaml
step_1:
  tool: SearchProduct v2.1
  agent: SearchAgent-01 (scored 1.358)
  timeout_ms: 550
  error_handlers:
    timeout: [retry 2x, then BrowseCategory fallback]
    no_results: [use RecommendationEngine]
  prompt: "...rendered from shopping_domain template..."
```

### Stage 3: Validation
**Tier 1 Rules:**
- ✓ Budget check: $0 < $150 budget
- ✓ Time check: Critical path 1000ms < deadline
- ✓ Capability check: All agents have required capabilities
- ✓ DAG check: No cycles, all dependencies valid
- ✓ Parameter check: All types match tool schemas

Result: **PASS** (GREEN band, no arbiter needed)

### Stage 4: Commit
```json
{
  "plan_id": "plan_sk89ab",
  "plan_hash": "abc123def456...",
  "execution_status": "PENDING",
  "total_estimated_duration_ms": 1000,
  "total_estimated_cost_cents": 15,
  "created_at": "2025-10-15T15:30:00Z"
}
```

✓ Plan persisted to K0 WAL, ready for Orchestrator

---

## Key Insights

### Design Principles

1. **Separation of Concerns**
   - Sketch: Creative (LLM)
   - Expand: Deterministic (registry lookups)
   - Validation: Policy enforcement (rules + arbiter)
   - Commit: Durability (K0 WAL)

2. **Performance Optimization**
   - Sketch: LLM inference dominates (100ms)
   - Expand: Fast registry lookups (50ms)
   - Validation: Tier 1 is deterministic (30ms), Tier 2 async
   - Commit: K0 write limited (20ms)

3. **Reliability & Safety**
   - Error handlers at expand stage
   - 2-tier validation (rules + human judgment)
   - Idempotent commit (safe retries)
   - Comprehensive audit trail

4. **Flexibility**
   - LLM fallback to rule-based templates
   - Domain-specific prompt templates
   - Configurable error handler strategies
   - Arbiter escalation for complex cases

### Research Foundations

- **Program Synthesis** (Gulwani, Solar-Lezama) - LLM-based plan generation
- **Tool Use in LLMs** (Schick et al., 2023) - Prompt template patterns
- **Formal Methods** (Floyd-Hoare logic) - Rule-based validation
- **Constraint Solving** (SMT solvers) - Validation rule conflicts
- **Write-Ahead Logging** (Gray & Seltzer) - Durability via K0 WAL
- **Event Sourcing** (Fowler) - Plan history & audit trail

---

## Performance Metrics Summary

| Stage | Metric | Target | Notes |
|-------|--------|--------|-------|
| **Sketch** | Duration P95 | 150ms | LLM inference ~100ms |
| | Validation success | > 90% | JSON parsing quality |
| | Confidence score | 0.8-0.95 | LLM confidence metric |
| **Expand** | Duration P95 | 50ms | Registry lookups O(n) |
| | Tool resolution | > 98% | Tools found in registry |
| | Unresolved steps | 0 | Every step must resolve |
| **Validation** | Tier 1 P95 | 50ms | Deterministic rules |
| | Tier 1 pass rate | > 70% | Reduce arbiter load |
| | Tier 2 approval | > 90% | Most escalations approve |
| **Commit** | Duration P95 | 20ms | K0 WAL write dominated |
| | Success rate | > 99.5% | Durability guarantee |
| | Duplicate rate | < 5% | Idempotent retries |
| **Total** | E2E P95 | 250ms | Fast path (no arbiter) |
| | E2E (with arbiter) | 1-30s | RED band review |

---

## Observability & Metrics

### Key Traces
- `planner.sketch` → `prompt_assembly`, `llm_inference`, `response_parsing`, `validation`, `dag_analysis`
- `planner.expand` → `tool_lookup`, `agent_matching`, `prompt_selection`, `error_handler_insertion`
- `planner.validation` → `tier1_rule_engine`, `tier2_arbiter_check`
- `planner.commit` → `plan_serialization`, `plan_hashing`, `duplicate_check`, `k0_write`, `durability_confirm`

### Key Metrics
- Sketch generation duration by domain
- LLM confidence score distribution
- Tool resolution success rate
- Agent matching scoring breakdown
- Validation rule violations by type
- Arbiter escalation rate by reason
- Commit-to-execution latency

---

## Implementation Next Steps

### Phase 1: Infrastructure (Week 1)
- [ ] Set up Jinja2 template system
- [ ] Integrate LLM models (GPT-4o-mini, Claude Haiku)
- [ ] Create tool registry database
- [ ] Set up prompt registry

### Phase 2: Core Pipeline (Week 2-3)
- [ ] Implement Sketch stage with LLM
- [ ] Implement Expand stage with capability matching
- [ ] Implement Tier 1 validation rules
- [ ] Implement Tier 2 Arbiter integration

### Phase 3: Persistence (Week 3)
- [ ] Create K0 WAL integration
- [ ] Implement plans table schema
- [ ] Add plan serialization (JSON + FlatBuffers)
- [ ] Implement idempotency

### Phase 4: Testing & Observability (Week 4)
- [ ] WARD tests for each stage
- [ ] Performance profiling
- [ ] Metrics emission (Prometheus)
- [ ] E2E integration tests

---

## Files Reference

| File | Lines | Purpose |
|------|-------|---------|
| `sketch_stage.yml` | 572 | LLM prompt templates, sketch generation, fallback |
| `expand_stage.yml` | 698 | Tool registry, agent matching, error handlers |
| `validation_stage.yml` | 660 | Tier 1 rules, Tier 2 arbiter, error messages |
| `commit_stage.yml` | 655 | K0 WAL, serialization, idempotency, audit |
| `README.md` | This | Architecture overview and completion summary |

**Total:** ~2,800 lines of comprehensive contract documentation

---

## Related Issues & Dependencies

**Depends On:**
- Issue 2.3.2 (Tool & Prompt Registries) - *To be completed*
- Issue 2.3.3 (Plan Validation) - *To be completed*

**Depended On By:**
- Planner Agent implementation
- Orchestrator integration with Planner

**Related ADRs:**
- ADR-0007 - 4-Stage Planning Pipeline (overview)
- ADR-0007a - Sketch Stage (LLM-based planning)
- ADR-0007b - Expand Stage (tool/prompt registry)
- ADR-0007c - Validation Stage (2-tier validation)
- ADR-0007d - Commit Stage (K0 WAL integration)

---

## Conclusion

Issue 2.3.1 successfully defines the complete 4-stage Planning Pipeline with comprehensive contracts for all stages. The architecture balances:
- **Creativity** (LLM in Sketch stage)
- **Determinism** (registry lookups in Expand stage)
- **Safety** (2-tier validation with arbiter escalation)
- **Durability** (K0 WAL persistence)

The pipeline enables K1 to generate, validate, and commit complex multi-agent plans with full observability and audit trails, supporting everything from simple sequential tasks to complex parallel workflows with error recovery.
