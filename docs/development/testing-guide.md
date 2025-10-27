# Testing Guide - WARD Framework

## Overview

K1 uses the **WARD test framework** for all testing. WARD emphasizes:
- **Integration tests over unit tests**: Test real component interactions
- **No mocking theater**: Use real implementations
- **Comprehensive coverage**: ≥85% overall, ≥90% core modules
- **Performance validation**: Measure latency and memory in tests

## Testing Philosophy

### Integration > Unit

K1 prioritizes integration tests that validate real component interactions:

✅ **Good**: Integration test with real components
```python
@test("orchestrator completes 3-phase coordination")
async def _(orchestrator=real_orchestrator, agents=real_agents):
    """Test real 3-phase orchestration"""
    task = TaskAnnouncement(...)
    result = await orchestrator.coordinate(task, agents)
    assert result.status == "COMPLETED"
    assert result.latency_ms < 250  # Performance validation
```

❌ **Bad**: Unit test with mocks
```python
@test("orchestrator coordinates (mocked)")
async def _():
    """Mocked test - avoid this!"""
    mock_orchestrator = Mock()
    mock_orchestrator.coordinate.return_value = {"status": "COMPLETED"}
    # This doesn't test real behavior!
```

### Zero Tolerance Policy

**NO SIMULATIONS IN TESTS:**
- ❌ NO `asyncio.sleep()` to simulate delays
- ❌ NO `time.sleep()` for timing
- ❌ NO mock delays or artificial waits
- ✅ Use real components with real timing
- ✅ Use `pass` with TODO for unimplemented features

## WARD Test Structure

### Basic Test

```python
from ward import test

@test("agent transitions from PENDING to WARMING")
async def _():
    """Test agent state transition"""
    agent = Agent(state=AgentState.PENDING)
    await agent.transition_to(AgentState.WARMING)
    assert agent.state == AgentState.WARMING
```

### Test with Fixtures

```python
from ward import test, fixture
import asyncio

@fixture
async def orchestrator():
    """Fixture provides real orchestrator with cleanup"""
    config = load_test_config()
    orch = Orchestrator(config=config)
    await orch.initialize()

    yield orch  # Provide to test

    # Cleanup after test
    await orch.shutdown()

@test("orchestrator handles task announcement")
async def _(orch=orchestrator):
    """Test with orchestrator fixture"""
    task = TaskAnnouncement(
        task_id="task-1",
        intent="answer_question",
        trace_id="trace-123"
    )

    result = await orch.coordinate(task)

    assert result.status == "COMPLETED"
    assert result.latency_ms < 2000  # P95 budget
```

### Parameterized Tests

```python
from ward import test, each

@test("agent transitions are valid for {transition}")
async def _(transition=each(
    ("PENDING", "WARMING"),
    ("WARMING", "ACTIVE"),
    ("ACTIVE", "IDLE"),
    ("IDLE", "DRAINING"),
    ("DRAINING", "TERMINATED")
)):
    """Test all valid agent transitions"""
    from_state, to_state = transition
    agent = Agent(state=AgentState[from_state])

    result = await agent.transition_to(AgentState[to_state])

    assert result is True
    assert agent.state == AgentState[to_state]
```

### Error Path Testing

```python
@test("agent rejects invalid transition")
async def _():
    """Test error handling for invalid transition"""
    agent = Agent(state=AgentState.PENDING)

    # PENDING → TERMINATED is invalid (skips states)
    with raises(InvalidTransitionError):
        await agent.transition_to(AgentState.TERMINATED)

    # Agent should remain in PENDING
    assert agent.state == AgentState.PENDING
```

## Test Organization

K1 tests are organized by module, mirroring the source structure:

```
tests/
├── agent_fabric/              # Layer 1 - Core Kernel
│   ├── test_lifecycle_fsm.py
│   ├── test_supervisor.py
│   ├── test_hiring_score.py
│   └── test_blacklist.py
├── orchestrator/              # Layer 1 - Core Kernel
│   ├── test_3phase.py
│   ├── test_negotiation.py
│   ├── test_selection.py
│   └── test_execution.py
├── planner/                   # Layer 1 - Core Kernel
│   ├── test_4stage_pipeline.py
│   ├── test_sketch_llm.py
│   ├── test_expand_deterministic.py
│   ├── test_validate_arbiter.py
│   └── test_fallbacks.py
├── protocol_monitor/          # Layer 1 - Core Kernel
│   ├── test_mpst_validation.py
│   ├── test_agent_hire_protocol.py
│   ├── test_task_execution_protocol.py
│   ├── test_clarification_protocol.py
│   ├── test_barge_in_protocol.py
│   ├── test_tool_call_protocol.py
│   ├── test_saga_rollback_protocol.py
│   └── test_timeout_enforcement.py
├── learning_loop/             # Layer 1 - Core Kernel
│   ├── test_feedback_signals.py
│   ├── test_drift_detection.py
│   └── test_config_reload.py
├── session_state/             # Layer 2 - State & Persistence
│   ├── test_6sections.py
│   ├── test_3tier_eviction.py
│   ├── test_flatbuffers_serialization.py
│   └── test_state_manager.py
├── k0_bridge/                 # Layer 2 - State & Persistence
│   ├── test_batching.py
│   ├── test_durability.py
│   └── test_saga_persistence.py
├── tool_runner/               # Layer 3 - Execution & Tools
│   ├── test_capability_checks.py
│   ├── test_tool_execution.py
│   └── test_tool_protocol.py
├── api_gateway/               # Layer 4 - Ingress & Voice
│   ├── test_rest_endpoints.py
│   ├── test_websocket_protocol.py
│   └── test_sse_streaming.py
├── backpressure/              # Layer 5 - Infrastructure
│   ├── test_cascade.py
│   └── test_watermarks.py
└── integration/               # End-to-end tests
    ├── test_end_to_end_turn.py
    ├── test_barge_in_flow.py
    ├── test_multi_agent_coordination.py
    └── test_saga_rollback_flow.py
```

## Writing Tests

### 1. Test File Naming

- **Naming**: `test_<module_or_feature>.py`
- **Location**: Mirror source structure in `tests/`
- **Examples**: `test_lifecycle_fsm.py`, `test_3phase.py`, `test_mpst_validation.py`

### 2. Test Function Naming

```python
# Good: Descriptive test names
@test("agent transitions from PENDING to WARMING state")
@test("orchestrator completes 3-phase coordination under 250ms")
@test("protocol monitor rejects invalid state transition")

# Bad: Vague test names
@test("test1")
@test("it works")
```

### 3. Arrange-Act-Assert Pattern

```python
@test("planner validates FlowDef with arbiter")
async def _(planner=planner_fixture):
    # Arrange: Set up test data
    flow_def = FlowDef(
        nodes=[Node(id="n1"), Node(id="n2")],
        edges=[Edge(src="n1", dst="n2")]
    )

    # Act: Execute the operation
    validation_result = await planner.validate(flow_def)

    # Assert: Verify the outcome
    assert validation_result.status == "VALID"
    assert validation_result.violations == []
    assert validation_result.latency_ms < 50
```

### 4. Performance Validation

Always validate performance against P95 budgets:

```python
@test("TTFT is under 150ms budget")
async def _(model_hub=model_hub_fixture):
    """Test Time To First Token performance"""
    start_ms = current_time_ms()

    first_token = await model_hub.generate_first_token(
        prompt="What is K1?",
        trace_id="trace-123"
    )

    ttft_ms = current_time_ms() - start_ms

    assert first_token is not None
    assert ttft_ms < 150  # P95 budget
```

### 5. Error Path Coverage

Test all error paths explicitly:

```python
@test("agent hire fails when no agents available")
async def _(orchestrator=orchestrator_fixture):
    """Test error path: no available agents"""
    task = TaskAnnouncement(...)

    # No agents registered
    with raises(NoAgentsAvailableError):
        await orchestrator.coordinate(task)

@test("protocol monitor handles timeout")
async def _(monitor=protocol_monitor_fixture):
    """Test error path: protocol timeout"""
    session_id = "session-1"

    # Simulate timeout by setting old start time
    monitor.active_sessions[session_id] = ProtocolSession(
        state="NEGOTIATION",
        state_start_ms=current_time_ms() - 300  # 300ms ago
    )

    # Timeout budget is 250ms
    valid = await monitor.validate_transition(
        session_id=session_id,
        from_state="NEGOTIATION",
        to_state="SELECTION"
    )

    assert valid is False  # Should reject due to timeout
```

## Running Tests

### Run All Tests

```bash
python -m ward test --path tests/
```

### Run Specific Module

```bash
python -m ward test --path tests/agent_fabric/
python -m ward test --path tests/orchestrator/
python -m ward test --path tests/integration/
```

### Run with Verbose Output

```bash
python -m ward test --path tests/ --verbose
```

### Run Specific Test

```bash
python -m ward test --search "agent transitions from PENDING"
```

### Run with Coverage

```bash
python -m ward test --path tests/ --coverage
```

## Coverage Requirements

K1 enforces strict coverage requirements:

| Module Category | Coverage Requirement |
|----------------|---------------------|
| Core Kernel (Layer 1) | ≥90% |
| State & Persistence (Layer 2) | ≥90% |
| Execution & Tools (Layer 3) | ≥85% |
| Ingress & Voice (Layer 4) | ≥85% |
| Infrastructure (Layer 5) | ≥85% |
| Integration Tests | ≥85% |
| **Overall** | **≥85%** |

### Check Coverage

```bash
# Generate coverage report
python -m ward test --path tests/ --coverage

# View HTML report
open htmlcov/index.html
```

## Testing Best Practices

### ✅ Do

- **Use real components**: Test with actual K1 components, not mocks
- **Validate performance**: Always check latency against P95 budgets
- **Test error paths**: Cover all error conditions explicitly
- **Use fixtures**: Reuse setup code with fixtures
- **Clean up resources**: Always clean up in fixture teardown
- **Descriptive names**: Use clear, descriptive test names
- **One assertion focus**: Each test should focus on one behavior
- **Integration focus**: Prioritize integration tests over unit tests

### ❌ Don't

- **No mocking**: Don't use Mock objects for K1 components
- **No sleep**: Don't use `asyncio.sleep()` or `time.sleep()` for delays
- **No simulations**: Don't simulate behavior, test real behavior
- **No skipped tests**: Don't commit tests with `@skip` decorator
- **No flaky tests**: Fix flaky tests, don't ignore them
- **No vague names**: Avoid `test1`, `test_foo`, `it_works`
- **No bloated tests**: Keep tests focused on single behavior

## Example: Complete Test Module

```python
"""
Tests for agent lifecycle FSM.

Module: k1/agent_fabric/lifecycle.py
Coverage target: ≥90%
"""

from ward import test, fixture, each, raises
import asyncio

from k1.agent_fabric.lifecycle import Agent, AgentState, InvalidTransitionError


@fixture
async def agent():
    """Fixture: Agent in PENDING state"""
    a = Agent(
        agent_id="test-agent-1",
        state=AgentState.PENDING,
        capabilities=["TOOL_CALL"],
        memory_mb=10
    )
    yield a
    # Cleanup
    a.state = AgentState.TERMINATED


@test("agent initializes in PENDING state")
async def _():
    """Test agent initialization"""
    agent = Agent(agent_id="test-1")
    assert agent.state == AgentState.PENDING


@test("agent transitions through valid states")
async def _(agent=agent):
    """Test valid state transitions"""
    # PENDING → WARMING
    await agent.transition_to(AgentState.WARMING)
    assert agent.state == AgentState.WARMING

    # WARMING → ACTIVE
    await agent.transition_to(AgentState.ACTIVE)
    assert agent.state == AgentState.ACTIVE

    # ACTIVE → IDLE
    await agent.transition_to(AgentState.IDLE)
    assert agent.state == AgentState.IDLE


@test("agent rejects invalid transition {transition}")
async def _(agent=agent, transition=each(
    ("PENDING", "ACTIVE"),     # Skips WARMING
    ("PENDING", "TERMINATED"), # Skips intermediate states
    ("WARMING", "IDLE"),       # Skips ACTIVE
)):
    """Test invalid transition rejection"""
    from_state, to_state = transition
    agent.state = AgentState[from_state]

    with raises(InvalidTransitionError):
        await agent.transition_to(AgentState[to_state])


@test("warming transition completes under 200ms")
async def _(agent=agent):
    """Test warming performance budget"""
    start_ms = current_time_ms()

    await agent.transition_to(AgentState.WARMING)
    await agent.wait_until_ready()

    latency_ms = current_time_ms() - start_ms

    assert agent.state == AgentState.ACTIVE
    assert latency_ms < 200  # P95 budget
```

## End-to-End Data Flow Testing

### Comprehensive K1 → K0 → K1 Round-Trip Test

K1's most critical integration test validates the complete data persistence cycle with real cryptographic signatures and K0 database operations.

**Test Location**: `tests/k1/l5_infrastructure/bridge_k0/test_real_data_flow.py`

**What This Test Proves**:

1. ✅ K1 can create properly signed envelopes using K0's NaCl Ed25519 signing infrastructure
2. ✅ K0 validates and accepts valid signatures (rejects invalid test signatures)
3. ✅ K0 commits data to WAL database (receipt contains WAL offset)
4. ✅ Data persists correctly (query retrieves exact data at WAL position)
5. ✅ K1 can query and retrieve persisted data from K0
6. ✅ Data integrity maintained (content matches exactly)
7. ✅ `cognitive_trace_id` propagates through full cycle
8. ✅ **Full K1 → K0 → K1 data flow: WORKING**

### Test Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    E2E Data Flow Test                       │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         [1] Sign        [2] Submit      [3] Query
              │               │               │
              ▼               ▼               ▼
    ┌─────────────────┐ ┌──────────┐ ┌──────────────┐
    │ K0 Signing      │ │ K0       │ │ K0 Query     │
    │ Infrastructure  │ │ Command  │ │ Client       │
    │                 │ │ Client   │ │              │
    │ • dev_profile   │ │          │ │              │
    │ • signing_key   │ │ POST     │ │ POST         │
    │ • NaCl Ed25519  │ │ /command │ │ /query       │
    └─────────────────┘ │ .submit  │ │ .recall      │
                        └──────────┘ └──────────────┘
                              │               │
                              ▼               ▼
                        ┌──────────────────────────┐
                        │   K0 Docker Kernel       │
                        │                          │
                        │ • Policy validation      │
                        │ • Signature verification │
                        │ • WAL persistence        │
                        │ • SQLite database        │
                        └──────────────────────────┘
```

### Key Components

#### 1. Real Signature Creation

```python
from k0.local.dev_profile import default_profile, signing_key_for
from k0.security import canonical_envelope, canonical_json
from k0.security.crypto import encode_base64url

def create_signed_envelope(sequence: int) -> dict:
    """Create properly signed command envelope."""
    # Get development profile (tenant, space, device, topic)
    profile = default_profile()
    signing_key = signing_key_for(profile)

    # Create memory payload
    body = {
        "operation": "memory.store",
        "memory_id": f"test_e2e_{sequence}_{uuid.uuid4().hex[:8]}",
        "content": {
            "type": "episodic",
            "title": f"E2E Test Memory #{sequence}",
            "body": f"Real data flow test at {timestamp}",
            "tags": ["e2e-test", "k1-k0-integration"],
        }
    }

    # Build envelope with checksums
    body_json = canonical_json(body)
    envelope = {
        "cognitive_trace_id": str(uuid.uuid4()),
        "tenant_id": profile.tenant_id,
        "space_id": profile.space_id,
        "device_id": profile.device_id,
        "topic": profile.topic,
        "schema_uri": profile.schema_uri,
        "band": "GREEN",
        "payload_sha256": hashlib.sha256(body_json).hexdigest(),
        # ... other envelope fields
    }

    # Sign with REAL NaCl signature
    message = canonical_envelope(envelope)
    signature = encode_base64url(signing_key.sign(message).signature)
    envelope["sig"] = signature
    envelope["body"] = body

    return envelope
```

#### 2. Command Submission

```python
async def submit_command(envelope: dict) -> dict:
    """Submit to K0 and get receipt with WAL offset."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "http://localhost:8080/k0/command.submit",
            json=envelope,
            headers={
                "Content-Type": "application/json",
                "X-Cognitive-Trace-Id": envelope["cognitive_trace_id"]
            }
        )
        response.raise_for_status()
        return response.json()  # Returns receipt with WAL offset
```

#### 3. WAL Persistence Verification

```python
def verify_wal_persistence(trace_id: str) -> dict | None:
    """Check if command persisted to WAL database."""
    result = subprocess.run([
        "docker", "exec", "k0-kernel",
        "sqlite3", "/data/k0_kernel.db",
        f"SELECT pos, tenant_id, space_id, topic FROM st_wal "
        f"WHERE cognitive_trace_id='{trace_id}' LIMIT 1"
    ], capture_output=True, text=True)

    if result.returncode == 0 and result.stdout.strip():
        parts = result.stdout.strip().split("|")
        return {
            "pos": int(parts[0]),
            "tenant_id": parts[1],
            "space_id": parts[2],
            "topic": parts[3],
        }
    return None
```

#### 4. Query Verification

```python
async def query_memories(space_id: str, tenant_id: str) -> dict:
    """Query stored memories from K0."""
    payload = {
        "selectors": [{
            "type": "episodic",
            "tags": ["e2e-test"],
            "limit": 10,
        }],
        "space_id": space_id,
        "tenant_id": tenant_id,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "http://localhost:8080/k0/query.recall",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()
```

### Expected Test Output

```text
================================================================================
🚀 REAL K1 → K0 → K1 DATA FLOW TEST
================================================================================

📝 Step 1: Creating properly signed command envelope...
   Trace ID: 92278fbe-1b01-49c9-b7f5-68f2d13217f7
   Tenant: tenant-001
   Space: space-home
   Device: device-local-001
   Signature: hIRxMKkvE7SuXJ7hXLtjS8ZX1FLmR_aZ... (NaCl Ed25519)

📤 Step 2: Submitting command to K0...
   ✅ Command accepted! (HTTP 200 SUCCESS)
   Receipt: {
     "receipt_id": "1b8428cb-28bb-41c6-af68-c07a2432859b",
     "commit_ts": "2025-10-26T08:25:04.353378Z",
     "offsets": {
       "memory.delta": 87  // ← PROOF: Data persisted at WAL position 87
     },
     "idem_key": "726a57d314a34586f29e8224264ca8c52fe73139babad370287e28ee46dc56c4",
     "obligations": ["kernel.audit.trace"]
   }

🔍 Step 3: Verifying WAL persistence...
   ✅ Found in WAL at position 87
   Tenant: tenant-001
   Space: space-home
   Topic: memory.delta

🔎 Step 4: Querying memories from K0...
   ✅ Query successful!
   Retrieved memory at wal_pos 87:
   {
     "cognitive_trace_id": "92278fbe-1b01-49c9-b7f5-68f2d13217f7",
     "body": {
       "memory_id": "test_e2e_1_026258d6",
       "content": {
         "title": "E2E Test Memory #1",
         "body": "Real data flow test at 2025-10-26T08:25:04.320Z",
         "tags": ["e2e-test", "k1-k0-integration"]
       }
     }
   }

================================================================================
✅ DATA FLOW TEST COMPLETE
================================================================================

Summary:
  1. ✅ Command submitted with REAL signature
  2. ✅ K0 accepted and validated signature (HTTP 200, not 400!)
  3. ✅ Data persisted to WAL (position 87 confirmed in receipt AND query)
  4. ✅ Query endpoint working (retrieved exact data)

🎉 FULL K1 → K0 → K1 ROUND-TRIP PROVEN!
```

### K0 Kernel Logs Validation

The test also validates K0's internal logs showing:

```json
// Policy validation passed
{"logger": "k0.policy.pep_syscall", "message": "PEP allow",
 "context": {"band": "GREEN", "topic": "memory.delta", "tenant": "tenant-001"}}

// Unit of Work commit
{"logger": "k0.uow.unit_of_work", "message": "🔍 DEBUG: _commit() method called"}

// Snapshot watermark updated
{"logger": "k0.uow.unit_of_work",
 "message": "🔍 DEBUG: Updating snapshot_watermark to [REDACTED].392947"}

// HTTP success
{"logger": "uvicorn.access",
 "message": "172.18.0.1:59592 - \"POST /k0/command.submit HTTP/1.1\" 200"}

// Query success
{"logger": "uvicorn.access",
 "message": "172.18.0.1:59598 - \"POST /k0/query.recall HTTP/1.1\" 200"}
```

### Running the E2E Test

```bash
# Run from project root
python test_real_data_flow.py

# Or run as part of test suite
python -m ward test --path tests/k1/l5_infrastructure/bridge_k0/test_real_data_flow.py
```

### Prerequisites

1. **K0 Docker kernel running**: `docker ps | grep k0-kernel`
2. **K0 database accessible**: SQLite at `/data/k0_kernel.db` in container
3. **Development profile configured**: `k0.local.dev_profile` available
4. **Signing keys present**: NaCl Ed25519 keys for device-local-001

### What Makes This Test Different

| Aspect | Previous Connectivity Tests | Real Data Flow Test |
|--------|----------------------------|---------------------|
| **Signatures** | Test placeholders (rejected by K0) | REAL NaCl Ed25519 signatures |
| **K0 Response** | 400 INVALID_SIGNATURE | 200 OK with receipt |
| **Persistence** | Not tested | Verified in WAL database |
| **Query** | Not attempted | Full query and data retrieval |
| **Data Integrity** | N/A | Exact content match confirmed |
| **Proof** | Connection works | **Full data cycle works** |

### Critical Success Criteria

✅ **Signature Acceptance**: K0 returns HTTP 200, not 400 (proves valid signature)
✅ **Receipt with Offset**: Receipt contains `offsets.memory.delta` (proves WAL write)
✅ **WAL Persistence**: SQLite query finds data at exact WAL position
✅ **Query Success**: K0 returns memory at correct `wal_pos`
✅ **Data Integrity**: Retrieved content matches submitted content exactly
✅ **Trace Propagation**: `cognitive_trace_id` present in all operations

### Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| **400 INVALID_SIGNATURE** | Using test signature, not real | Use `k0.local.dev_profile` signing |
| **404 Not Found** | Wrong K0 endpoint | Use unified port 8080, not 5200 |
| **Connection refused** | K0 not running | Start K0: `docker-compose up -d` |
| **Empty query results** | Wrong space/tenant | Use same IDs from dev_profile |
| **SQLite permission denied** | Docker exec failed | Check container name: `k0-kernel` |

### Integration with 5-Step Workflow

This test validates **GATE 4 (Testing)** for Layer 5 Infrastructure:

- **GATE 1 (ADRs)**: References ADR-0024 (K0 Bridge), ADR-0065 (Signing)
- **GATE 2 (Contracts)**: Validates `k0/contracts/openapi.k0.yaml`
- **GATE 3 (Implementation)**: Tests real `K0CommandClient`, `K0QueryClient`
- **GATE 4 (Testing)**: ✅ **THIS TEST** - Proves full data persistence cycle
- **GATE 5 (Memory)**: Documents test results, WAL positions, trace IDs

## Next Steps

- **[Debugging Guide](./debugging-guide.md)**: Learn how to debug K1 with traces and metrics
- **[Performance Profiling](./performance-profiling.md)**: Profile K1 components
- **[Contribution Guide](./contribution-guide.md)**: Submit your tests with code

## References

- **WARD Documentation**: <https://ward.readthedocs.io/>
- **Testing Standards**: [.github/instructions/testing-standards.instructions.md](../../.github/instructions/testing-standards.instructions.md)
- **K1 Module Analysis**: [../k1_module_analysis.md](../k1_module_analysis.md)
