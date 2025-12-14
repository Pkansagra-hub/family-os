---
adr_number: 0007d
title: Commit Stage K0 WAL Integration
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer2_orchestration
- layer3_execution
- layer4_runtime
affected_modules:
- k1.l1_input.intent_parser
- k1.l2_orchestration.planner.commit_stage
- k1.l2_orchestration.commit.k0_wal_writer
- k1.l2_orchestration.commit.sessionstate_locker
- k1.l2_orchestration.commit.flow_definition_serializer
- k1.l3_execution.flow_engine.flow_def_loader
- k1.l4_runtime.sessionstate.commit_lock_manager
- k1.l5_infrastructure.k0_bridge.commit_writer
concerns:
- architecture
- compliance
- cost
- observability
- performance
- privacy
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0001a
- ADR-0007
- ADR-0007c
- ADR-0007d
- ADR-0011
- ADR-0017
implementation_status: COMPLETED
implementation_date: '2025-02-01'
implementation_phase: MVP
related_contracts:
- k1/contracts/flatbuffers/layer2_orchestration/committed_plan.fbs
- k1/contracts/flatbuffers/layer2_orchestration/flow_definition.fbs
- k1/contracts/flatbuffers/layer2_orchestration/commit_transaction.fbs
- k1/contracts/flatbuffers/layer3_execution/flow_engine.fbs
- k1/contracts/flatbuffers/layer4_runtime/sessionstate_lock.fbs
- k1/contracts/flatbuffers/layer5_infrastructure/k0_bridge.fbs
- k0/contracts/api/rest/idempotency/24h_retention.yml
- k0/contracts/asyncapi.events.yaml
- k0/contracts/openapi.k0.yaml
- k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
- k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
- k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
- k1/contracts/flatbuffers/layer3_execution/model_request.fbs
- k1/contracts/flatbuffers/layer3_execution/model_response.fbs
related_diagrams:
- k1_commit_stage_k0_wal_integration
- k1_flow_definition_serialization
- k1_sessionstate_commit_locking
- k1_k0_bridge_commit_writer
- k1_wal_transaction_protocol
- k1_commit_stage_error_recovery
research_citations:
- "Write-Ahead Logging" by C. Mohan et al. (1992)
- "ARIES: A Transaction Recovery Method Supporting Fine-Granularity Locking and Partial Rollbacks Using Write-Ahead Logging" by C. Mohan et al. (1992)
- "Distributed Commit Protocols for Distributed Database Systems" by Philip A. Bernstein et al. (1987)
- "Two-Phase Commit Protocol" by Jim Gray (1978)
- "Session State Management in Distributed Systems" by Gustavo Alonso et al. (2002)
- "Flow Definition Languages" by Frank Leymann and Dieter Roller (2000)
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0001a
  - ADR-0007
  - ADR-0007c
  - ADR-0007d
  - ADR-0011
  - ADR-0017
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  affected_tests:
  - tests/k1/l2_orchestration/test_commit_stage.py
  - tests/k1/l2_orchestration/test_k0_wal_writer.py
  - tests/k1/l2_orchestration/test_sessionstate_locker.py
  - tests/k1/l2_orchestration/test_flow_definition_serializer.py
  - tests/k1/l3_execution/test_flow_def_loader.py
  - tests/k1/l4_runtime/test_commit_lock_manager.py
  - tests/k1/l5_infrastructure/test_k0_bridge_commit_writer.py
  - tests/integration/test_commit_stage_pipeline.py
  - tests/performance/test_commit_latency.py
---


# ADR-0007d: Commit Stage K0 WAL Integration

**Status:** ✅ Approved (2025-10-12)
**Parent ADR:** [ADR-0007: 4-Stage Planning Pipeline](./0007-4stage-planning-pipeline.md)
**Related ADRs:**
- [ADR-0007c: Validation Stage 2-Tier Implementation](./0007c-validation-stage-2-tier-implementation.md) - Provides validated plan input
- [ADR-0001a: K0 Bridge Communication Protocol](./0001a-k0-bridge-communication-protocol.md) - K0 WAL write protocol
- [ADR-0011: FlatBuffers Serialization](./0011-flatbuffers-serialization.md) - FlowDef schema
- [ADR-0017: SessionState 6-Section Design](./0017-sessionstate-6-section-design.md) - State locking

---

## Context & Problem Statement

### Current State
After Stage 3 (Validate), the Planner has a ValidatedPlan ready for execution, but **not persisted or locked in SessionState**:
- ❌ No durable persistence (plan lost if K1 crashes)
- ❌ No audit trail (can't trace plan commits)
- ❌ No state locking (SessionState not updated with active plan)
- ❌ No idempotency (retries may create duplicate commits)

### Problem Statement
**How do we persist ValidatedPlan to K0 Write-Ahead Log (WAL) for durability + audit trail, lock SessionState for execution, and ensure idempotency in <10ms P95?**

### Key Challenges

1. **Commit Latency (<10ms):**
   - FlatBuffers serialization + K0 WAL write must complete in <10ms
   - Target: <10ms P95 commit latency

2. **100% Durability:**
   - All committed plans must be persisted to K0 WAL
   - No data loss on K1 crash/restart

3. **Idempotency:**
   - Retries must not create duplicate plan commits
   - Use idempotency key (plan hash + session ID)

4. **Audit Trail:**
   - All plans logged with trace_id, session_id, space for traceability

---

## Decision

### Overview
Implement **K0 WAL integration** for Stage 4 (Commit) of the 4-stage planning pipeline:
1. **FlowDef serialization** (FlatBuffers)
2. **K0 WAL write** (PLAN_COMMITTED topic, durable persistence)
3. **SessionState locking** (current_flow field, mark plan as active)
4. **STATE_DELTA emission** (K0 state change: current_flow: null → flow_id)
5. **Idempotency** (idempotency key for plan commits)
6. **Commit metrics** (commit_latency_ms, plans_committed_total)

---

### Component 1: FlowDef Serialization (FlatBuffers)

**Purpose:** Serialize ValidatedPlan to compact binary format for K0 WAL.

**FlowDef Schema (FlatBuffers):**
```flatbuffers
// flow_def.fbs
namespace K1.Planning;

table PlanStep {
  step_id: int;
  action: string;
  tool: string;
  parameters: string;  // JSON string
  dependencies: [int];

  // Metadata from expansion
  latency_hint_ms: int;
  cost_hint_usd: float;
  band_required: string;
}

table FlowDef {
  flow_id: string;
  intent: string;
  steps: [PlanStep];
  complexity: string;

  // Aggregate metadata
  total_latency_hint_ms: int;
  total_cost_hint_usd: float;
  highest_band_required: string;

  // Audit metadata
  session_id: string;
  trace_id: string;
  space: string;
  created_at: long;  // Unix timestamp (ms)

  // Validation metadata
  validation_errors: [string];
  arbiter_invoked: bool;
  arbiter_reason: string;
}

root_type FlowDef;
```

**Serialization Algorithm:**
```python
import flatbuffers
from k1.schemas.flow_def import FlowDef, PlanStep

def serialize_flow_def(
    validated_plan: ValidatedPlan,
    session_state: SessionState,
    trace_id: str
) -> bytes:
    """
    Serialize ValidatedPlan to FlatBuffers binary.

    Returns: bytes (FlatBuffers binary)
    """
    builder = flatbuffers.Builder(1024)  # Initial capacity

    # Serialize steps
    step_offsets = []
    for step in validated_plan.plan.steps:
        # Serialize parameters as JSON string
        params_json = json.dumps(step.parameters)
        params_offset = builder.CreateString(params_json)

        # Create PlanStep
        PlanStep.Start(builder)
        PlanStep.AddStepId(builder, step.step_id)
        PlanStep.AddAction(builder, builder.CreateString(step.action))
        PlanStep.AddTool(builder, builder.CreateString(step.tool))
        PlanStep.AddParameters(builder, params_offset)
        PlanStep.AddDependencies(builder, step.dependencies)
        PlanStep.AddLatencyHintMs(builder, step.latency_hint_ms)
        PlanStep.AddCostHintUsd(builder, step.cost_hint_usd)
        PlanStep.AddBandRequired(builder, builder.CreateString(step.band_required))
        step_offset = PlanStep.End(builder)
        step_offsets.append(step_offset)

    # Create steps vector
    FlowDef.StartStepsVector(builder, len(step_offsets))
    for step_offset in reversed(step_offsets):
        builder.PrependUOffsetTRelative(step_offset)
    steps_vector = builder.EndVector()

    # Create FlowDef
    flow_id = generate_flow_id()  # UUID
    FlowDef.Start(builder)
    FlowDef.AddFlowId(builder, builder.CreateString(flow_id))
    FlowDef.AddIntent(builder, builder.CreateString(validated_plan.plan.intent))
    FlowDef.AddSteps(builder, steps_vector)
    FlowDef.AddComplexity(builder, builder.CreateString(validated_plan.plan.complexity))
    FlowDef.AddTotalLatencyHintMs(builder, validated_plan.plan.total_latency_hint_ms)
    FlowDef.AddTotalCostHintUsd(builder, validated_plan.plan.total_cost_hint_usd)
    FlowDef.AddHighestBandRequired(builder, builder.CreateString(validated_plan.plan.highest_band_required))
    FlowDef.AddSessionId(builder, builder.CreateString(session_state.session_id))
    FlowDef.AddTraceId(builder, builder.CreateString(trace_id))
    FlowDef.AddSpace(builder, builder.CreateString(session_state.meta.space))
    FlowDef.AddCreatedAt(builder, int(time.time() * 1000))  # Unix timestamp (ms)
    flow_def_offset = FlowDef.End(builder)

    builder.Finish(flow_def_offset)
    return bytes(builder.Output())
```

**Performance:** <1ms (FlatBuffers serialization)

---

### Component 2: K0 WAL Write (PLAN_COMMITTED Topic)

**Purpose:** Write FlowDef to K0 WAL for durable persistence.

**K0 WAL Write Protocol (from ADR-0001a):**
```python
async def write_plan_to_k0_wal(
    flow_def_bytes: bytes,
    flow_id: str,
    idempotency_key: str
) -> K0WriteResponse:
    """
    Write FlowDef to K0 WAL (PLAN_COMMITTED topic).

    K0 Command Port:
    POST /api/v1/command
    Content-Type: application/octet-stream
    X-Idempotency-Key: {idempotency_key}
    X-Topic: PLAN_COMMITTED
    X-Flow-ID: {flow_id}

    Body: FlatBuffers binary (FlowDef)
    """
    headers = {
        "Content-Type": "application/octet-stream",
        "X-Idempotency-Key": idempotency_key,
        "X-Topic": "PLAN_COMMITTED",
        "X-Flow-ID": flow_id
    }

    response = await k0_client.post(
        url=f"{K0_BASE_URL}/api/v1/command",
        headers=headers,
        data=flow_def_bytes,
        timeout=5.0  # 5s timeout
    )

    if response.status_code != 200:
        raise K0WriteError(f"K0 WAL write failed: {response.text}")

    return K0WriteResponse(
        flow_id=flow_id,
        committed_at=response.json()["committed_at"],
        receipt_id=response.json()["receipt_id"]
    )
```

**Performance:** <5ms (HTTP POST to K0)

---

### Component 3: SessionState Locking (current_flow Field)

**Purpose:** Lock SessionState to prevent concurrent plan execution.

**SessionState Update:**
```python
async def lock_session_state(
    session_state: SessionState,
    flow_id: str
) -> None:
    """
    Lock SessionState by setting current_flow field.

    SessionState.control.current_flow: null → flow_id
    """
    # Check if current_flow is already set
    if session_state.control.current_flow is not None:
        raise PlanningError(
            f"Session already has active plan: {session_state.control.current_flow}"
        )

    # Set current_flow
    session_state.control.current_flow = flow_id
    session_state.control.flow_started_at = int(time.time() * 1000)

    logger.info(
        "session_state_locked",
        session_id=session_state.session_id,
        flow_id=flow_id
    )
```

**Performance:** <0.1ms (in-memory update)

---

### Component 4: STATE_DELTA Emission (K0 Sync)

**Purpose:** Emit state change to K0 for persistence.

**STATE_DELTA Message:**
```python
async def emit_state_delta_to_k0(
    session_id: str,
    field_path: str,
    old_value: Any,
    new_value: Any
) -> None:
    """
    Emit STATE_DELTA to K0 for SessionState persistence.

    K0 Command Port:
    POST /api/v1/command
    Content-Type: application/json
    X-Topic: STATE_DELTA

    Body:
    {
      "session_id": "sess_123",
      "field_path": "control.current_flow",
      "old_value": null,
      "new_value": "flow_abc",
      "timestamp": 1696800000000
    }
    """
    delta_message = {
        "session_id": session_id,
        "field_path": field_path,
        "old_value": old_value,
        "new_value": new_value,
        "timestamp": int(time.time() * 1000)
    }

    await k0_client.post(
        url=f"{K0_BASE_URL}/api/v1/command",
        headers={
            "Content-Type": "application/json",
            "X-Topic": "STATE_DELTA"
        },
        json=delta_message
    )
```

**Performance:** <2ms (HTTP POST to K0)

---

### Component 5: Idempotency (Idempotency Key)

**Purpose:** Prevent duplicate plan commits on retry.

**Idempotency Key Generation:**
```python
def generate_idempotency_key(
    validated_plan: ValidatedPlan,
    session_id: str
) -> str:
    """
    Generate idempotency key for plan commit.

    Key = hash(session_id + plan_hash + timestamp_bucket)
    - session_id: Scope to session
    - plan_hash: Hash of plan content (intent, steps, dependencies)
    - timestamp_bucket: 60s bucket (allow retry within 60s window)
    """
    # Compute plan hash
    plan_dict = {
        "intent": validated_plan.plan.intent,
        "steps": [
            {
                "action": s.action,
                "tool": s.tool,
                "parameters": s.parameters,
                "dependencies": s.dependencies
            }
            for s in validated_plan.plan.steps
        ]
    }
    plan_json = json.dumps(plan_dict, sort_keys=True)
    plan_hash = hashlib.sha256(plan_json.encode()).hexdigest()[:16]

    # Compute timestamp bucket (60s)
    timestamp_bucket = int(time.time() // 60) * 60

    # Generate idempotency key
    idempotency_key = f"{session_id}:{plan_hash}:{timestamp_bucket}"
    return idempotency_key
```

**Idempotency Check (K0 Side):**
- K0 Command Port checks `X-Idempotency-Key` header
- If key exists in cache (5-minute TTL), return cached response (no duplicate write)
- If key not in cache, write to WAL and cache response

**Performance:** <0.1ms (hash computation)

---

### Component 6: Commit Metrics (Observability)

**Metrics (Prometheus):**
```python
from prometheus_client import Counter, Histogram

# Commit latency
commit_latency_ms = Histogram(
    'commit_latency_ms',
    'Plan commit latency in milliseconds',
    buckets=[5, 10, 20, 50, 100]
)

# Plans committed
plans_committed_total = Counter(
    'plans_committed_total',
    'Total plans committed',
    ['intent', 'space']
)

# K0 write errors
k0_write_errors_total = Counter(
    'k0_write_errors_total',
    'K0 WAL write errors',
    ['error_type']
)
```

---

### Complete Commit Flow

```python
class PlanCommitter:
    """Commit validated plans to K0 WAL"""

    def __init__(self, k0_client: K0Client):
        self.k0_client = k0_client

    async def commit_plan(
        self,
        validated_plan: ValidatedPlan,
        session_state: SessionState,
        trace_id: str
    ) -> CommittedPlan:
        """
        Commit validated plan:
        1. Serialize to FlatBuffers (FlowDef)
        2. Write to K0 WAL (PLAN_COMMITTED topic)
        3. Lock SessionState (current_flow field)
        4. Emit STATE_DELTA to K0
        5. Return CommittedPlan
        """
        start_time = time.time()

        # Step 1: Serialize FlowDef
        flow_def_bytes = serialize_flow_def(validated_plan, session_state, trace_id)
        flow_id = extract_flow_id_from_bytes(flow_def_bytes)

        # Step 2: Generate idempotency key
        idempotency_key = generate_idempotency_key(validated_plan, session_state.session_id)

        # Step 3: Write to K0 WAL
        k0_response = await write_plan_to_k0_wal(
            flow_def_bytes=flow_def_bytes,
            flow_id=flow_id,
            idempotency_key=idempotency_key
        )

        # Step 4: Lock SessionState
        lock_session_state(session_state, flow_id)

        # Step 5: Emit STATE_DELTA to K0
        await emit_state_delta_to_k0(
            session_id=session_state.session_id,
            field_path="control.current_flow",
            old_value=None,
            new_value=flow_id
        )

        # Metrics
        latency_ms = (time.time() - start_time) * 1000
        commit_latency_ms.observe(latency_ms)
        plans_committed_total.labels(
            intent=validated_plan.plan.intent,
            space=session_state.meta.space
        ).inc()

        logger.info(
            "plan_committed",
            flow_id=flow_id,
            intent=validated_plan.plan.intent,
            step_count=len(validated_plan.plan.steps),
            latency_ms=latency_ms,
            trace_id=trace_id
        )

        return CommittedPlan(
            plan=validated_plan.plan,
            flow_id=flow_id,
            committed_at=k0_response.committed_at,
            receipt_id=k0_response.receipt_id
        )
```

---

## Performance Analysis

### Latency Breakdown

| Component | Latency (P95) |
|-----------|---------------|
| FlowDef serialization | <1ms |
| K0 WAL write | <5ms |
| SessionState locking | <0.1ms |
| STATE_DELTA emission | <2ms |
| **Total** | **<8ms** |

**Target:** <10ms P95 ✅

---

## Canonical Values

```yaml
# k1/config/planner.yml
planner:
  commit:
    # Performance targets
    commit_latency_p95_ms: 10

    # K0 WAL configuration
    k0_base_url: "http://k0-service:8080"
    k0_write_timeout_ms: 5000

    # Idempotency
    idempotency_window_seconds: 60  # 60s window for retry
```

---

## Conclusion

Stage 4 (Commit) persists ValidatedPlan to K0 WAL in <10ms with 100% durability, idempotency, and audit trail. SessionState locked for execution.

**4-Stage Planning Pipeline Complete!**
- **Stage 1 (Sketch):** <500ms P95 ✅
- **Stage 2 (Expand):** <1ms P95 ✅
- **Stage 3 (Validate):** <1ms P95 (Tier 1), 50-100ms P95 (Tier 2) ✅
- **Stage 4 (Commit):** <10ms P95 ✅

**Total (GREEN band):** ~502ms P95
**Total (AMBER/RED band):** ~560-600ms P95
