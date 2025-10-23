---
description: Testing standards and coverage requirements for MemoryOS components.
applyTo: "tests/**/*.py,**/*test*.py"
---

# 🧪 Testing Requirements & WARD Framework

## Overview

Testing is **GATE 4** in the 5-step workflow. All production code changes require comprehensive test coverage before proceeding to memory documentation.

**Philosophy:**
- **No mock theater** — test real components under controlled conditions
- **Contract validation** — prove interface compliance with actual schemas
- **Performance budgets** — validate SLA requirements with measurable metrics
- **WARD framework** — use `python -m ward test --path tests/` for async testing
- **Integration > Unit** — prioritize integration tests with real components

---

## 1) Testing Philosophy (Non-Negotiable)

| Principle | What to Do | What NOT to Do |
|-----------|-----------|----------------|
| Real components | Use actual `Orchestrator`, `Agent`, `PlannerAgent` instances | ❌ No mocks for core logic |
| Contract-first | Validate all schemas, APIs, events against contracts | ❌ Don't skip contract validation |
| Performance budgets | Test P95 latency, throughput, memory under load | ❌ No assumptions—measure everything |
| Determinism | Use fixed test data, seeded randomness, frozen time | ❌ No `asyncio.sleep()`, `time.sleep()` |
| Isolation | Each test gets clean fixtures and fresh state | ❌ No shared test state between tests |
| Async-native | Use WARD for async tests; proper `await` semantics | ❌ No blocking I/O in tests |

## 2) Coverage Standards (Measurable)

| Category | Requirement | Tool | Threshold |
|----------|-------------|------|-----------|
| **Code coverage** | Unit + integration combined | `coverage.py` | ≥95% |
| **Integration tests** | 100% of I/O paths tested | `ward` | 100% |
| **Contract compliance** | API/event/storage schemas | JSONSchema + AsyncAPI | 100% |
| **Performance** | P95 latency, throughput, memory | `py-spy`, custom benchmarks | Meet SLA |
| **Security** | RBAC, encryption, input validation | security tests | 100% |

---

## 3) Test Organization (K0 & K1 Structure)

### K0 (Memory Subsystem) Tests
```
tests/k0/
├── component/                    # ≥95% coverage each
│   ├── test_bus_core.py         # Event bus core logic
│   ├── test_storage_layer.py    # Hippocampus storage
│   ├── test_policy_service.py   # Policy enforcement
│   └── test_security.py         # Encryption & auth
├── integration/                  # Multi-component flows
│   ├── test_api_to_storage.py   # API → Storage path
│   ├── test_event_flows.py      # Event bus flows
│   └── test_policy_enforcement.py # Full policy validation
├── performance/                  # SLA validation
│   ├── test_storage_throughput.py
│   ├── test_bus_latency.py
│   └── test_concurrent_load.py
└── contracts/                    # Schema compliance
    ├── test_api_schemas.py
    ├── test_event_schemas.py
    └── test_storage_schemas.py
```

### K1 (Agent Fabric) Tests
```
tests/k1/
├── component/                    # ≥95% coverage each
│   ├── test_agent_lifecycle.py  # Agent FSM
│   ├── test_orchestrator_3phase.py # 3-phase coordination
│   ├── test_planner_pipeline.py # 4-stage planning
│   └── test_protocol_monitor.py # MPST validation
├── integration/                  # Multi-agent flows
│   ├── test_e2e_turn.py         # Complete user turn
│   ├── test_barge_in.py         # Interruption handling
│   ├── test_backpressure.py     # Load management
│   └── test_learning_loop.py    # Feedback integration
├── performance/                  # Budget validation
│   ├── test_ttft_latency.py     # TTFT < 150ms p95
│   ├── test_e2e_latency.py      # E2E < 2000ms p95
│   └── test_memory_footprint.py # Memory < 500MB
└── contracts/                    # Schema compliance
    ├── test_agent_contracts.py
    ├── test_event_contracts.py
    └── test_protocol_contracts.py
```

---

## 4) WARD Framework Usage

### Basic Test Structure
```python
from ward import test, fixture
import asyncio

# Fixtures for real component instances
@fixture
async def orchestrator():
    """Real orchestrator instance with test config"""
    orch = Orchestrator(config=test_config)
    await orch.initialize()
    yield orch
    await orch.shutdown()

@fixture
async def agent_fabric():
    """Real agent fabric with 3 test agents"""
    fabric = AgentFabric(max_agents=3)
    await fabric.initialize()
    yield fabric
    await fabric.shutdown()

# Tests with real components
@test("orchestrator completes 3-phase coordination")
async def _(orch=orchestrator):
    task = TaskAnnouncement(
        task_id="test-123",
        description="Test task",
        deadline_ms=2000
    )
    result = await orch.coordinate(task)
    assert result.status == "COMPLETED"
    assert result.latency_ms < 250  # Performance validation

@test("agent transitions through lifecycle states correctly")
async def _(fabric=agent_fabric):
    agent = fabric.create_agent(agent_id="test-agent")
    assert agent.state == AgentState.PENDING

    await agent.warm()
    assert agent.state == AgentState.WARMING

    await agent.activate()
    assert agent.state == AgentState.ACTIVE
```

### Contract Validation in Tests
```python
@test("API response matches OpenAPI schema")
async def test_api_contract_compliance():
    response = await api_client.get("/api/v1/agents/123")
    validate_against_schema(
        response.json(),
        "k1/contracts/api/agent-fabric-openapi.yaml"
    )

@test("Event payload matches AsyncAPI schema")
async def test_event_contract_compliance():
    event = AgentTransitionEvent(
        agent_id="123",
        from_state="ACTIVE",
        to_state="IDLE",
        trace_id="trace-abc"
    )
    validate_against_schema(
        event.dict(),
        "k1/contracts/events/agent-transition-asyncapi.yaml"
    )
```

### Performance & Benchmark Tests
```python
@test("TTFT latency is under 150ms p95")
async def test_ttft_budget(orchestrator=orchestrator):
    latencies = []
    for i in range(100):
        start = time.perf_counter()
        result = await orchestrator.generate_first_token(prompt="test")
        latencies.append((time.perf_counter() - start) * 1000)

    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    assert p95 < 150, f"TTFT p95={p95}ms exceeds 150ms budget"

@test("E2E latency is under 2000ms p95")
async def test_e2e_budget(orchestrator=orchestrator):
    latencies = []
    for i in range(50):
        start = time.perf_counter()
        result = await orchestrator.complete_turn(task)
        latencies.append((time.perf_counter() - start) * 1000)

    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    assert p95 < 2000, f"E2E p95={p95}ms exceeds 2000ms budget"
```

---

## 5) Contract Validation Tests

All contracts must be validated during test execution:

```python
# API Contract Validation
@test("All API responses match OpenAPI schema")
async def test_agent_fabric_api_contracts():
    """Validate k1/contracts/api/agent-fabric-openapi.yaml"""
    validator = OpenAPIValidator("k1/contracts/api/agent-fabric-openapi.yaml")

    # Test each endpoint
    response = await api_client.get("/api/v1/agents/123")
    validator.validate_response("/agents/{id}", "GET", 200, response.json())

    response = await api_client.post("/api/v1/tasks", json={"description": "test"})
    validator.validate_response("/tasks", "POST", 201, response.json())

# Event Contract Validation
@test("All events match AsyncAPI schema")
async def test_event_contracts():
    """Validate k1/contracts/events/*.yaml"""
    validator = AsyncAPIValidator("k1/contracts/events/")

    event = AgentTransitionEvent(agent_id="123", from_state="ACTIVE", to_state="IDLE")
    validator.validate_event("agent.transition", event.dict())

    event = TaskCompletedEvent(task_id="456", status="SUCCESS")
    validator.validate_event("task.completed", event.dict())

# Storage Contract Validation
@test("All storage operations comply with schema")
async def test_storage_contracts(fabric=agent_fabric):
    """Validate k1/contracts/storage/*.schema.json"""
    validator = JSONSchemaValidator("k1/contracts/storage/")

    agent = fabric.create_agent(agent_id="test-agent")
    stored = await storage.save_agent(agent)
    validator.validate(stored, "agent-schema.json")
```

---

## 6) Performance Testing Requirements

### Performance Budget Validation
- **TTFT (Time-to-First-Token)**: <150ms p95
- **E2E Latency**: <2000ms p95
- **Memory**: <500MB steady state
- **Throughput**: >100 concurrent orchestrations
- **Agent Density**: 3+ agents per session

### Load Testing Pattern
```python
@test("Orchestrator handles 100 concurrent tasks")
async def test_concurrent_load(orchestrator=orchestrator):
    tasks = [
        TaskAnnouncement(task_id=f"task-{i}", ...)
        for i in range(100)
    ]

    start = time.perf_counter()
    results = await asyncio.gather(*[orchestrator.coordinate(t) for t in tasks])
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len([r for r in results if r.status == "COMPLETED"]) == 100
    assert elapsed_ms < 10000  # All complete within 10 seconds
```

---

## 7) Quality Gates (Automated Validation)
## 7) Quality Gates (Automated Validation)

```bash
# GATE 4 Quality Checks - Run before proceeding to memory documentation

# 1. Coverage measurement (≥95%)
python -m ward test --path tests/ --output=json > test_results.json
coverage run -m ward test --path tests/
coverage report --fail-under=95 --show-missing

# 2. Contract compliance (100%)
python k1/automation/lint_schemas.py --test-all
python k0/automation/lint_schemas.py --test-all

# 3. Performance validation (meet SLA)
python -m ward test --path tests/k1/performance/ --verbose
python -m ward test --path tests/k0/performance/ --verbose

# 4. Security testing (100% coverage)
python -m ward test --path tests/security/ --verbose

# 5. All tests must pass
python -m ward test --path tests/ --fail-fast
```

### Required Outputs
- ✅ Coverage report (≥95%)
- ✅ Contract validation passed
- ✅ Performance budgets met (p95 latencies documented)
- ✅ All tests passing
- ✅ No simulation code detected

---

## 8) GATE 4 Integration (5-Step Workflow)

**GATE 4: Test Implementation** blocks progression to GATE 5 (Memory Documentation).

Before marking tests complete:
- [ ] All tests pass: `python -m ward test --path tests/`
- [ ] Coverage ≥95%: `coverage report --fail-under=95`
- [ ] Contracts validated: `python k1/automation/lint_schemas.py --test-all`
- [ ] Performance budgets met: `python -m ward test --path tests/*/performance/`
- [ ] No simulation code: Grep for `asyncio.sleep`, `time.sleep`, mocks
- [ ] ADR references in comments: All key decisions documented
- [ ] Memory entry ready: Include test results, coverage %, budget status

**After GATE 4 passes:**
→ Move to **GATE 5: Memory Documentation**
→ Record coverage, test count, performance results in memory
→ Link to related ADRs and implementation files

---

## 9) Test Execution Commands

### Development Workflow
```bash
# Quick test during development
python -m ward test --path tests/component/ --verbose

# Full suite with coverage
python -m ward test --path tests/
coverage run -m ward test --path tests/
coverage report --show-missing --fail-under=95

# Specific test module
python -m ward test --path tests/k1/component/test_orchestrator_3phase.py --verbose

# Watch mode (re-run on file changes)
python -m ward test --path tests/ --watch
```

### Pre-Commit Validation
```bash
# Fast smoke test (component tests only)
python -m ward test --path tests/component/ --fail-fast

# Contract validation
python k1/automation/lint_schemas.py --test-all
python k0/automation/lint_schemas.py --test-all
```

### CI/CD Pipeline
```bash
# Full validation for PR
python -m ward test --path tests/ --output=json > test_results.json
coverage run -m ward test --path tests/
coverage report --fail-under=95 --format=json > coverage.json

# Performance regression check
python -m ward test --path tests/k1/performance/ --verbose > perf_results.json
python -m ward test --path tests/k0/performance/ --verbose >> perf_results.json

# Security scanning
python -m ward test --path tests/security/ --verbose
```

---

## 10) Test Data Management

### Fixtures (WARD)
```python
@fixture
def test_config():
    """Deterministic test configuration"""
    return Config(
        log_level="DEBUG",
        debug_mode=True,
        # No random delays, fixed ports
        port=9090 + randint(1000, 9999),
        seed=42  # Fixed seed for reproducibility
    )

@fixture(scope="module")
async def storage():
    """Shared storage instance for module tests"""
    store = InMemoryStore()
    await store.initialize()
    yield store
    await store.cleanup()
```

### Test Data Patterns
```python
# Fixed deterministic data
TEST_AGENT_ID = "test-agent-123"
TEST_USER_ID = "test-user-456"
TEST_TASK_ID = "test-task-789"

# Seeded randomness for reproducibility
import random
random.seed(42)
random_port = random.randint(10000, 20000)

# Frozen timestamps
from freezegun import freeze_time
@freeze_time("2025-10-23 12:00:00")
async def test_timestamp_handling():
    # Time is now fixed at 2025-10-23 12:00:00
    pass
```

---

## 11) Error Prevention Checklist

### ❌ Anti-Patterns (ZERO TOLERANCE)
- ❌ `asyncio.sleep()` or `time.sleep()` — causes test flakiness
- ❌ Mocking core logic — defeats purpose of integration tests
- ❌ Shared test state — breaks test isolation
- ❌ Non-deterministic data — random timestamps, IDs, etc.
- ❌ Blocking I/O in tests — violates async model
- ❌ Untrapped exceptions — hides test failures
- ❌ Incomplete cleanup — leaves resources allocated

### ✅ Best Practices
- ✅ Use real component instances
- ✅ Fresh fixtures for each test
- ✅ Deterministic test data (fixed IDs, timestamps)
- ✅ Proper `async`/`await` semantics
- ✅ Context managers for resource cleanup
- ✅ Exception handling with assertions
- ✅ Performance assertions (latency, throughput)

---

## 12) Integration Tests Example (Real Components)

```python
"""
Integration test for K1 agent fabric.
Real components: Orchestrator, AgentFabric, PlannerAgent, ProtocolMonitor.
Tests: Task negotiation → selection → execution.
"""

from ward import test, fixture

@fixture
async def orchestrator():
    orch = Orchestrator(config=test_config)
    await orch.initialize()
    yield orch
    await orch.shutdown()

@fixture
async def agent_fabric():
    fabric = AgentFabric(max_agents=3)
    await fabric.initialize()
    yield fabric
    await fabric.shutdown()

@test("End-to-end task coordination with 3 agents")
async def _(orch=orchestrator, fabric=agent_fabric):
    # Create 3 real agents
    agents = [
        fabric.create_agent(agent_id=f"agent-{i}")
        for i in range(3)
    ]

    # Task announcement
    task = TaskAnnouncement(
        task_id="e2e-test-task",
        description="Complex multi-step task",
        deadline_ms=2000
    )

    # Phase 1: Negotiation (all 3 agents propose)
    proposals = await orch.negotiate(task, timeout_ms=500)
    assert len(proposals) == 3

    # Phase 2: Selection (best agent chosen)
    selected = await orch.select(proposals, timeout_ms=300)
    assert selected is not None
    assert selected.score > 0

    # Phase 3: Execution (task executes)
    result = await orch.execute(task, selected.agent_id, timeout_ms=1000)
    assert result.status == "COMPLETED"
    assert result.latency_ms < 250  # Performance budget
```

---

## 13) References

- **WARD Documentation**: Framework for async testing in Python
- **Coverage.py**: Code coverage measurement tool
- **Freezegun**: Time freezing for deterministic tests
- **5-Step Workflow**: `.github/instructions/service-design.instructions.md` (GATE 4)
- **ADR Master Reference**: `docs/ADR_MASTER_REFERENCE.md`
- **K1 Module Analysis**: `docs/k1_module_analysis.md`
