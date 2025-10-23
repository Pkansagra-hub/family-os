# Layer 2 - Orchestration Module

**Location:** `k1/l2_orchestration/`
**Purpose:** Multi-agent coordination, AI-powered planning, and protocol validation
**Performance Budget:** <100ms P95 (orchestration only, planning <2500ms)

## Overview

Layer 2 (Orchestration) is the coordination layer of the K1 Intelligence Module. It orchestrates multi-agent task execution using a 3-phase protocol, generates structured plans using a 4-stage AI-powered pipeline, and validates all agent communication using Multiparty Session Types (MPST).

### Core Components

1. **planner/** - 4-Stage AI-Powered Planning Pipeline (ADR-0007)
2. **orchestrator/** - 3-Phase Multi-Agent Coordination (ADR-0006)
3. **protocol_monitor/** - MPST Protocol Validation (ADR-0003)

---

## Architecture Overview

```
l2_orchestration/
├── planner/           # 4-Stage Planning Pipeline (<2500ms P95)
│   ├── sketch/        # Stage 1: LLM-powered plan generation (<500ms)
│   ├── expand/        # Stage 2: Tool registry enrichment (<1ms)
│   ├── validate/      # Stage 3: 2-tier validation (<1ms Tier 1, 50-100ms Tier 2)
│   └── commit/        # Stage 4: K0 WAL persistence (<10ms)
│
├── orchestrator/      # 3-Phase Orchestration (<250ms P95)
│   ├── negotiation.py # Phase 1: Contract Net Protocol (<50ms)
│   ├── selection.py   # Phase 2: MADM 6-factor scoring (<5ms)
│   ├── execution.py   # Phase 3: DAG parallel execution (variable)
│   └── saga.py        # Saga Coordinator: LIFO compensation
│
└── protocol_monitor/  # MPST Protocol Validation (<2ms P95)
    ├── pdl_parser/    # PDL → FSM compiler (<100ms startup)
    ├── fsm_executor/  # Runtime FSM validation (<2ms)
    ├── violation_handler/ # Block/warn/DLQ actions
    └── timeout_enforcer/  # Auto-transitions on timeout
```

---

## Module 1: planner/ - 4-Stage Planning Pipeline

**ADR Reference:** [ADR-0007](../../docs/architecture/decisions/0007-4-stage-planning-pipeline.md)

### Purpose
Generate structured task execution plans using a 4-stage pipeline combining LLM reasoning with deterministic validation.

### Performance Budget
- **Total:** <2500ms P95
- Stage 1 (Sketch): 500ms P95 (LLM inference)
- Stage 2 (Expand): 1ms P95 (tool lookup)
- Stage 3 (Validate): 1ms P95 (rule-based, 85% of plans)
- Stage 4 (Commit): 10ms P95 (K0 WAL write)

### Stages

#### Stage 1: sketch/ - LLM Plan Generation
**ADR:** [ADR-0007a](../../docs/architecture/decisions/0007a-sketch-stage-llm-prompt-engineering.md)

**Files:**
- `__init__.py` - Module documentation
- `prompt_assembler.py` - 5-component prompt builder
- `llm_client.py` - Model Hub integration (OpenAI, Gemini, Claude)
- `sketch_generator.py` - End-to-end sketch generation with retry logic

**Key Responsibilities:**
1. Assemble multi-component prompt (system + examples + tools + context)
2. Call Model Hub with temperature tuning (0.3 primary, 0.0 fallback)
3. Parse JSON response with >99% success rate
4. Return PlanSketch (intent, steps[], complexity)

**Quality Metrics:**
- JSON parse success: >99%
- Tool hallucination: <1%
- Intent accuracy: >95%

#### Stage 2: expand/ - Tool Registry Integration
**ADR:** [ADR-0007b](../../docs/architecture/decisions/0007b-expand-stage-tool-prompt-registry-integration.md)

**Files:**
- `__init__.py` - Module documentation
- `tool_lookup.py` - O(1) hash table lookup
- `prompt_matcher.py` - Keyword/category matching (>90% success)
- `plan_enricher.py` - Metadata enrichment (schema_in, schema_out, hints)

**Key Responsibilities:**
1. Lookup tools from registry (O(1) per tool)
2. Match prompts via keyword search
3. Enrich steps with schema references, latency hints, cost estimates
4. Return ExpandedPlan with complete metadata

#### Stage 3: validate/ - 2-Tier Validation
**ADR:** [ADR-0007c](../../docs/architecture/decisions/0007c-validation-stage-2-tier-implementation.md)

**Files:**
- `__init__.py` - Module documentation
- `structural_validator.py` - Basic structure checks (<0.1ms)
- `dependency_validator.py` - Kahn's algorithm DAG validation (<0.2ms)
- `capability_validator.py` - Agent capability checks (<0.05ms)
- `budget_validator.py` - Latency/cost budget checks (<0.05ms)
- `band_validator.py` - Privacy band hierarchy (<0.05ms)
- `schema_validator.py` - JSON Schema validation (<0.5ms)
- `arbiter_validator.py` - LLM arbiter for AMBER/RED (<15% invocation)

**Key Responsibilities:**
- **Tier 1 (Rule-Based):** 6 validation checks in <1ms P95
- **Tier 2 (LLM Arbiter):** Safety review for sensitive plans (50-100ms)

**Validation Checks:**
1. Structural: Step count, unique IDs, sequential numbering
2. Dependency: DAG acyclic, valid references
3. Capability: Agent has required tools/models
4. Budget: Within latency/cost limits
5. Band: Privacy hierarchy respected
6. Schema: Parameters match tool schemas

#### Stage 4: commit/ - K0 WAL Integration
**ADR:** [ADR-0007d](../../docs/architecture/decisions/0007d-commit-stage-k0-wal-integration.md)

**Files:**
- `__init__.py` - Module documentation
- `flatbuffers_serializer.py` - FlowDef serialization (<1ms)
- `k0_wal_writer.py` - HTTP POST to K0 WAL (<5ms)
- `session_state_locker.py` - Prevent concurrent plans
- `state_delta_emitter.py` - K0 sync events
- `idempotency_checker.py` - Hash-based deduplication (60s window)

**Key Responsibilities:**
1. Serialize plan to FlatBuffers (FlowDef format)
2. Write to K0 WAL (PLAN_COMMITTED topic)
3. Lock SessionState.control.current_flow
4. Emit STATE_DELTA for field updates
5. Check idempotency (prevent duplicates)

---

## Module 2: orchestrator/ - 3-Phase Coordination

**ADR Reference:** [ADR-0006](../../docs/architecture/decisions/0006-3-phase-orchestration.md)

### Purpose
Coordinate multi-agent task execution using Contract Net Protocol with 3-phase orchestration.

### Performance Budget
- **Total:** <250ms P95
- Phase 1 (Negotiation): 50ms P95
- Phase 2 (Selection): 5ms P95
- Phase 3 (Execution): Variable (plan-dependent)

### Phases

#### Phase 1: negotiation.py - Contract Net Protocol
**ADR:** [ADR-0006a](../../docs/architecture/decisions/0006a-contract-net-negotiation.md)

**Key Responsibilities:**
1. Broadcast TaskAnnouncement to all ACTIVE agents
2. Collect Proposals with 50ms deadline (MPSC queue)
3. 4-tier fallback: Hire → Simplify → Wait-retry → Degrade

**Agent Bidding (4-Factor Confidence):**
- Capability match (40%): Tool/model availability
- Success rate (30%): Historical track record
- Load factor (20%): Current mailbox depth (inverse)
- Context match (10%): SessionState availability

**Fallback Strategy:**
- Tier 1: Hire new agent (~150ms)
- Tier 2: Simplify task requirements (~80ms)
- Tier 3: Wait 100ms for agents to warm up (~150ms)
- Tier 4: Graceful degradation (<1ms)

#### Phase 2: selection.py - MADM Scoring
**ADR:** [ADR-0006b](../../docs/architecture/decisions/0006b-multi-criteria-scoring.md)

**Key Responsibilities:**
1. Score proposals using 6-factor weighted formula
2. Normalize latency/cost (0-1 scale)
3. Apply tie-breaking (4 strategies: resident/fast/cheap/random)
4. Return TaskAssignment for winner

**6-Factor Scoring:**
- Confidence (weight 10.0): Agent self-reported
- Latency (weight 8.0): Estimated execution time
- Cost (weight -5.0): Cheaper is better (negative weight)
- Parallelism (weight 3.0): Can run in parallel
- Track record (weight 2.0): Historical success
- Busy penalty (weight -4.0): Current load

**Formula:** `Score = Σ(factor × weight)`

#### Phase 3: execution.py - DAG Parallel Execution
**ADR:** [ADR-0006c](../../docs/architecture/decisions/0006c-parallel-dag-execution.md)

**Key Responsibilities:**
1. Build DAG from plan dependencies
2. Compute execution waves (topological sort)
3. Execute waves in parallel (asyncio.gather)
4. Resolve dependencies (variable substitution)
5. Detect stragglers (timeout enforcement)

**DAG Builder:**
- Nodes: Plan steps
- Edges: Dependencies between steps
- Validation: Acyclic check (Kahn's algorithm)

**Wave Computation:**
- Topological sort for ordering
- Group independent steps into waves
- Parallelism: Up to 3 concurrent steps

**Dependency Resolution:**
- Syntax: `{step_N.field}` references prior step results
- Lookup: Step result from completed steps map
- Substitution: Replace placeholders with actual values

#### Saga Coordination: saga.py - Error Recovery
**ADR:** [ADR-0008](../../docs/architecture/decisions/0008-saga-pattern-error-recovery.md)

**Key Responsibilities:**
1. Execute workflow with compensation tracking
2. LIFO compensation on failure (reverse order)
3. Best-effort rollback (compensations may fail)
4. Audit trail to K0 receipts

**Saga Pattern (Garcia-Molina & Salem, 1987):**
- Forward execution: Execute steps 1 → N
- Failure detection: Step N fails
- Backward compensation: Compensate N-1 → 1 (LIFO)
- Audit logging: All compensations logged to K0

**Compensation Actions:**
- Tool-based: Execute tool with reverse parameters
- API-based: HTTP DELETE or POST to undo operation
- Custom: Registered compensation handlers

**Performance:**
- Compensation trigger: <5ms (deterministic LIFO stack)
- Compensation execution: Variable (API calls <100ms, AI reasoning 50-500ms)
- Total recovery: <5s for 5-step workflow

---

## Module 3: protocol_monitor/ - MPST Validation

**ADR Reference:** [ADR-0003](../../docs/architecture/decisions/0003-mpst-protocol-validation.md)

### Purpose
Validate all agent communication using Multiparty Session Types (MPST) to prevent deadlocks and ensure protocol compliance.

### Performance Budget
- Protocol compilation: <100ms per protocol (startup only)
- Runtime validation: <2ms P95 per message
- Role verification: <1ms P95 (HMAC check)

### Components

#### PDL Parser: pdl_parser/
**ADR:** [ADR-0003a](../../docs/architecture/decisions/0003a-protocol-definition-language-pdl-specification.md)

**Files:**
- `yaml_parser.py` - Parse PDL YAML files
- `syntax_validator.py` - Validate syntax/semantics
- `fsm_generator.py` - Generate FSM from PDL
- `deadlock_detector.py` - Tarjan's algorithm for cycle detection

**Key Responsibilities:**
1. Parse YAML protocol definitions
2. Validate syntax (states, transitions, messages)
3. Generate FSM (states, transitions, timeouts)
4. Detect deadlocks (circular wait detection)
5. Serialize to FlatBuffers (FSM binary format)

#### FSM Executor: fsm_executor/
**ADR:** [ADR-0003c](../../docs/architecture/decisions/0003c-protocol-monitor-runtime-implementation.md)

**Files:**
- `fsm_registry.py` - Load 6 protocols from FlatBuffers
- `session_tracker.py` - Per-session FSM state (RwLock concurrency)
- `validator.py` - Receive-side validation (<2ms P95)
- `transition_engine.py` - Execute state transitions

**Key Responsibilities:**
1. Load 6 protocols: hire, task, clarification, barge_in, tool_call, saga
2. Track per-session protocol state
3. Validate messages against current state
4. Execute transitions on valid messages
5. Reject invalid messages (violation handler)

**6 Protocols:**
1. Agent Hire: 6 states, 8 transitions, 500ms negotiation
2. Task Execution: 5 states, 10 transitions, 5000ms LLM timeout
3. Clarification: 4 states, 6 transitions, 30000ms user timeout
4. Barge-In: 3 states, 5 transitions, 200ms decision
5. Tool Call: 4 states, 7 transitions, 3000ms execution
6. Saga Rollback: 5 states, 9 transitions, 5000ms compensate

#### Violation Handler: violation_handler/
**Files:**
- `violation_detector.py` - Detect invalid messages
- `action_executor.py` - Execute violation actions
- `dlq_writer.py` - Write to Dead Letter Queue

**Violation Actions:**
- BLOCK: Reject message, don't deliver
- WARN: Log warning, deliver anyway
- DLQ: Log to DLQ for manual review
- REPAIR: Auto-inject timeout transition
- FALLBACK: Trigger fallback protocol
- ABORT: Abort protocol, cleanup FSM

#### Timeout Enforcer: timeout_enforcer/
**Files:**
- `timeout_monitor.py` - Background task (100ms poll)
- `auto_transition.py` - Auto-transitions on timeout
- `progress_checker.py` - Liveness property validation

**Key Responsibilities:**
1. Poll FSM states every 100ms
2. Detect timeout violations (no progress within timeout)
3. Auto-transition to timeout state (progress guarantee)
4. Log timeout events to K0

---

## ADR Cross-Reference

### Primary ADRs (Core Layer 2)
- **ADR-0004:** 52-Module 5-Layer Architecture (Layer 2 definition)
- **ADR-0006:** 3-Phase Orchestration (orchestrator module)
- **ADR-0007:** 4-Stage Planning Pipeline (planner module)
- **ADR-0008:** Saga Error Recovery (saga coordinator)
- **ADR-0003:** MPST Protocol Validation (protocol monitor)

### Sub-ADRs (Detailed Implementation)
- **ADR-0006a-e:** Orchestration phases (negotiation, selection, execution, saga, coordination)
- **ADR-0007a-d:** Planning stages (sketch, expand, validate, commit)
- **ADR-0008a-d:** Saga patterns (compensation, recovery, state, timeout)
- **ADR-0003a-d:** Protocol validation (PDL, protocols, monitor, security)

### Cross-Cutting ADRs
- **ADR-0002:** Actor Model (mailbox communication)
- **ADR-0011-0013:** FlatBuffers (serialization, schemas, versioning)
- **ADR-0024:** Performance Budgets (layer-level targets)
- **ADR-0029:** Prometheus Metrics (observability)
- **ADR-0010:** Capability Security (role verification)

**Complete Reference:** See [layer2_adr_map.md](./layer2_adr_map.md) for all 127 relevant ADRs.

---

## Performance Budgets

| Component | P95 Target | Typical | Notes |
|-----------|------------|---------|-------|
| **Planner (Total)** | 2500ms | 1500ms | One-time per turn |
| → Sketch | 500ms | 300ms | LLM inference |
| → Expand | 1ms | 0.5ms | Tool lookup |
| → Validate | 1ms | 0.8ms | Rule-based (85%) |
| → Commit | 10ms | 5ms | K0 WAL write |
| **Orchestrator (Total)** | 250ms | 150ms | Per step |
| → Negotiation | 50ms | 30ms | Contract Net |
| → Selection | 5ms | 3ms | MADM scoring |
| → Execution | Variable | Variable | DAG-dependent |
| **Protocol Monitor** | 2ms | 1ms | Per message |
| **Saga Compensation** | 100ms | 50ms | Per step (best-effort) |

---

## Implementation Status

### Completed Components ✅
- Module structure and folder organization
- Comprehensive ADR documentation in all __init__.py files
- Python stub files with detailed docstrings
- Architecture diagrams and cross-references

### In Progress 🔄
- Python implementation of core classes
- WARD test suites (target: >90% coverage)
- Prometheus metrics integration
- OpenTelemetry tracing spans

### Not Started ⏳
- FlatBuffers schema definitions
- K0 Bridge integration (WAL writes, STATE_DELTA events)
- Protocol PDL files (6 protocols)
- Model Hub integration (LLM inference)
- Tool Registry integration

---

## Development Workflow

### 1. Adding New Files
Each file should include:
- **Module docstring** with ADR reference, purpose, responsibilities
- **Performance targets** (latency, throughput, resource usage)
- **Class/function docstrings** with ADR references
- **Input/output specifications**
- **Error handling strategy**
- **TODO comments** for incomplete implementations

### 2. ADR Alignment
Before implementing:
1. Read relevant ADR (see cross-reference above)
2. Verify alignment with architecture patterns
3. Check performance budgets
4. Review integration points (K0, Model Hub, Tool Registry)

### 3. Testing Strategy
- **Unit tests:** WARD framework, >85% coverage target
- **Integration tests:** End-to-end workflow validation
- **Performance tests:** Validate P95 latency budgets
- **Protocol tests:** Validate all 6 MPST protocols

### 4. Observability
Every component should emit:
- **Metrics:** Prometheus counters, histograms, gauges
- **Traces:** OpenTelemetry spans with cognitive_trace_id
- **Logs:** Structured logging (structlog) with context

---

## File Naming Conventions

- **Modules:** lowercase with underscores (`planner/`, `orchestrator/`)
- **Files:** lowercase with underscores (`prompt_assembler.py`, `dependency_validator.py`)
- **Classes:** PascalCase (`PromptAssembler`, `DependencyValidator`)
- **Functions:** snake_case (`assemble_prompt`, `validate_dependencies`)
- **Constants:** UPPER_SNAKE_CASE (`MAX_RETRIES`, `TIMEOUT_MS`)

---

## References

### Documentation
- **Layer 2 ADR Map:** [layer2_adr_map.md](./layer2_adr_map.md) (127 ADRs)
- **ADR Reference:** [ADR_REFERENCE.md](./ADR_REFERENCE.md) (Quick lookup)
- **Whiteboard Spec:** [docs/whiteboard.md](../../docs/whiteboard.md) (21K lines)
- **Module Analysis:** [docs/k1_module_analysis.md](../../docs/k1_module_analysis.md) (52 modules)

### Architecture Diagrams
- `architecture_diagrams/k1_orchestrator_3phase.mmd` - 3-phase orchestration flow
- `architecture_diagrams/k1_planner_4stage.mmd` - 4-stage planning pipeline
- `architecture_diagrams/k1_protocol_monitor_fsms.mmd` - 6 protocol FSMs

### Research Papers
- Contract Net Protocol (Smith 1980) - Multi-agent coordination
- Sagas (Garcia-Molina & Salem 1987) - Error recovery
- MPST (Honda et al. 2008) - Session type theory
- MADM (Hwang & Yoon 1981) - Multi-attribute decision making

---

**Last Updated:** January 2025
**Maintainer:** K1 Architecture Team
**Status:** ✅ Structure Complete, 🔄 Implementation In Progress
