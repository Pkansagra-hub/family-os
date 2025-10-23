---
description: Test layout, coverage, and contract/integration expectations.
applyTo: "tests/**/*.py"
---

# ✅ Test Standards — WARD Framework

## Overview

This document specifies test structure, organization, and execution within the 5-step workflow. **Testing is GATE 4**, a blocker before proceeding to memory documentation (GATE 5).

**Core Principle**: Integration tests with real components, not mock theater. Every test validates actual functionality against contracts.

---

## 1) Test Structure & Organization

### Directory Layout
```
tests/
├── k0/                           # K0 (Memory subsystem) tests
│   ├── component/                # Unit tests for individual components
│   │   ├── test_bus_core.py     # Event bus core
│   │   ├── test_storage_layer.py
│   │   ├── test_policy_service.py
│   │   └── __init__.py
│   ├── integration/              # Multi-component integration
│   │   ├── test_api_to_storage.py
│   │   ├── test_event_flows.py
│   │   └── test_policy_enforcement.py
│   ├── performance/              # SLA validation
│   │   ├── test_storage_throughput.py
│   │   └── test_bus_latency.py
│   └── contracts/                # Contract compliance
│       ├── test_api_schemas.py
│       ├── test_event_schemas.py
│       └── test_storage_schemas.py
│
├── k1/                           # K1 (Agent Fabric) tests
│   ├── component/                # Unit tests for components
│   │   ├── test_agent_lifecycle.py
│   │   ├── test_orchestrator_3phase.py
│   │   ├── test_planner_pipeline.py
│   │   └── test_protocol_monitor.py
│   ├── integration/              # Multi-agent integration
│   │   ├── test_e2e_turn.py     # Complete user turn
│   │   ├── test_barge_in.py     # Interruption handling
│   │   ├── test_backpressure.py # Load management
│   │   └── test_learning_loop.py
│   ├── performance/              # Performance budgets
│   │   ├── test_ttft_latency.py  # TTFT < 150ms p95
│   │   ├── test_e2e_latency.py   # E2E < 2000ms p95
│   │   └── test_memory_footprint.py
│   └── contracts/                # Contract compliance
│       ├── test_agent_contracts.py
│       ├── test_event_contracts.py
│       └── test_protocol_contracts.py
│
├── fixtures/                     # Shared fixtures and factories
│   ├── k0_fixtures.py
│   ├── k1_fixtures.py
│   └── test_data.py
│
└── conftest.py                   # Global WARD configuration
```

### Naming Conventions
- **Test files**: `test_<component>_<aspect>.py` (e.g., `test_orchestrator_3phase.py`)
- **Test functions**: `@test("human-readable description")`
- **Fixtures**: `@fixture` with descriptive names
- **One behavior per test**: Keep tests focused and independent

---

## 2) Types of Tests (All Apply)

| Type | Purpose | Coverage Target | Tools |
|------|---------|-----------------|-------|
| **Unit** | Pure logic validation | ≥95% of component code | WARD, coverage.py |
| **Integration** | Real I/O paths (API ↔ events ↔ storage) | 100% of critical paths | WARD with real fixtures |
| **Contract** | Schema/API/event compliance | 100% of contracts | JSONSchema, OpenAPI validators |
| **Performance** | SLA validation (latency, throughput, memory) | All budgets met | Custom benchmarks, py-spy |
| **Security** | RBAC, encryption, input validation | 100% of protected paths | Security-specific tests |

---

## 3) WARD Framework & Conventions

### Test File Template
```python
"""
Module: k1.orchestrator.tests
Purpose: Test 3-phase coordination orchestration
Related ADRs: ADR-0005, ADR-0086
"""

from ward import test, fixture
import asyncio

@fixture
async def orchestrator():
    """Real orchestrator instance for testing"""
    orch = Orchestrator(config=test_config)
    await orch.initialize()
    yield orch
    await orch.shutdown()

@test("orchestrator coordinates 3 phases correctly")
async def _(orch=orchestrator):
    # Test with REAL component
    task = TaskAnnouncement(task_id="test-123", ...)
    result = await orch.coordinate(task)

    # Assert behavioral outcomes
    assert result.status == "COMPLETED"
    assert result.latency_ms < 250  # Performance budget
```

### WARD Conventions
- **Framework**: `python -m ward test --path tests/`
- **Test Decorator**: `@test("human-readable description")`
- **Fixture Scope**: Function-scoped by default (isolation); module-scoped for expensive resources
- **Real Components**: Use actual implementations, never mock core logic
- **Async Support**: Native `async`/`await`; no blocking I/O
- **Determinism**: Freeze time, seed RNG, use fixed test data

### Fixtures Best Practices
```python
# Function-scoped fixture (fresh for each test)
@fixture
async def fresh_orchestrator():
    orch = Orchestrator(config=test_config)
    await orch.initialize()
    yield orch
    await orch.shutdown()

# Module-scoped fixture (shared across tests)
@fixture(scope="module")
async def shared_storage():
    store = StorageLayer()
    await store.initialize()
    yield store
    await store.cleanup()

# Factory fixture (creates multiple instances)
@fixture
def agent_factory():
    def _create_agent(agent_id: str):
        return Agent(agent_id=agent_id, config=test_config)
    return _create_agent
```

### Determinism & Isolation
- **Time**: Use `freezegun` to freeze time at known timestamps
- **Randomness**: Seed RNG with fixed values for reproducibility
- **Filesystem**: Use `tempfile` for isolated test directories
- **No network**: Mock only external APIs (HTTP calls); use real internal components
- **Clean state**: Fresh fixtures for each test, proper cleanup

---

## 4) What to Assert

### Assertion Hierarchy (in order)
1. **Behavioral outcomes**: Task completed, state changed, decision made
2. **Field values**: Response fields match schema, correct agent selected
3. **Side effects**: Events emitted, storage written, metrics recorded
4. **Performance**: Latency < budget, throughput > target, memory < limit

### Example: Multi-Level Assertions
```python
@test("task completes with correct outcomes and side effects")
async def test_task_completion(orch=orchestrator):
    # Setup
    task = TaskAnnouncement(task_id="test-task", ...)

    # Act
    result = await orch.coordinate(task)

    # Assert: Behavioral outcomes
    assert result.status == "COMPLETED"

    # Assert: Field values
    assert result.agent_id == "agent-1"
    assert result.phase_count == 3

    # Assert: Side effects (events emitted)
    events = await event_bus.get_events_for_trace(result.trace_id)
    assert len(events) == 7  # All phases emit events

    # Assert: Performance
    assert result.latency_ms < 250  # P95 budget
```

### Contract Outcomes
- Validate **privacy bands** (GREEN/AMBER/RED) applied correctly
- Verify **redaction rules** enforced (no PII in logs)
- Check **policy version** in responses matches request
- Ensure **trace_id** propagates through all components

---

## 5) Contract Compliance Tests

## 5) Contract Compliance Tests

### API Schema Validation
```python
@test("all API responses match OpenAPI schema")
async def test_api_contract_compliance():
    """Validate k1/contracts/api/agent-fabric-openapi.yaml"""
    from jsonschema import validate

    response = await api_client.get("/api/v1/agents/123")
    schema = load_schema("k1/contracts/api/agent-fabric-openapi.yaml")

    # Validate response structure
    validate(instance=response.json(), schema=schema)

    # Validate required envelope fields
    assert "trace_id" in response.json()
    assert "agent_id" in response.json()
    assert response.status_code == 200
```

### Event Schema Validation
```python
@test("all events match AsyncAPI schemas")
async def test_event_contract_compliance():
    """Validate k1/contracts/events/*.yaml"""
    validator = AsyncAPIValidator("k1/contracts/events/")

    event = AgentTransitionEvent(
        agent_id="123",
        from_state="ACTIVE",
        to_state="IDLE",
        trace_id="trace-abc"
    )

    # Validate event schema
    validator.validate_event("agent.transition", event.dict())

    # Validate envelope invariants
    assert event.agent_id  # Required
    assert event.trace_id  # For tracing
```

### Storage Schema Validation
```python
@test("all storage operations comply with schema")
async def test_storage_contract_compliance(storage=storage_fixture):
    """Validate k1/contracts/storage/*.schema.json"""
    validator = JSONSchemaValidator("k1/contracts/storage/")

    agent = Agent(agent_id="test-123")
    stored = await storage.save_agent(agent)

    # Validate against contract
    validator.validate(stored, "agent-schema.json")
```

### Contract Checklist
- ✅ Updated **OpenAPI** and/or **JSON Schemas** under `k1/contracts/` and `k0/contracts/`
- ✅ Examples validated; `additionalProperties: false` where applicable
- ✅ Envelope invariants present: `trace_id`, `band`, `policy_version`, `timestamp`
- ✅ All event topics match contract declarations
- ✅ API routes match OpenAPI spec
- ✅ Error responses include proper status codes and error messages

---

## 6) Performance & Load Testing

### Performance Budget Assertions
```python
@test("TTFT latency stays under 150ms p95")
async def test_ttft_budget(orch=orchestrator):
    latencies = []
    for i in range(100):
        start = time.perf_counter()
        result = await orch.generate_first_token(prompt="test")
        latencies.append((time.perf_counter() - start) * 1000)

    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    assert p95 < 150, f"TTFT p95={p95}ms exceeds 150ms budget"

@test("E2E latency stays under 2000ms p95")
async def test_e2e_budget(orch=orchestrator):
    latencies = []
    for i in range(50):
        start = time.perf_counter()
        result = await orch.complete_turn(task)
        latencies.append((time.perf_counter() - start) * 1000)

    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    assert p95 < 2000, f"E2E p95={p95}ms exceeds 2000ms budget"

@test("concurrent load: 100 tasks complete successfully")
async def test_concurrent_load(orch=orchestrator):
    tasks = [
        TaskAnnouncement(task_id=f"task-{i}", ...)
        for i in range(100)
    ]

    results = await asyncio.gather(
        *[orch.coordinate(t) for t in tasks],
        return_exceptions=True
    )

    successful = len([r for r in results if r.status == "COMPLETED"])
    assert successful == 100
```

---

## 7) Running Tests & Quality Gates

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

### GATE 4 Quality Validation (Pre-Commit)
```bash
# All tests must pass
python -m ward test --path tests/ --fail-fast

# Coverage must be ≥95%
coverage run -m ward test --path tests/
coverage report --fail-under=95

# Contracts must be valid
python k1/automation/lint_schemas.py --test-all
python k0/automation/lint_schemas.py --test-all

# Performance budgets must be met
python -m ward test --path tests/k1/performance/ --verbose
python -m ward test --path tests/k0/performance/ --verbose

# No simulation code
grep -r "asyncio.sleep\|time.sleep" tests/ && echo "FAIL: Simulation code found" || echo "PASS: No simulation code"
```

### CI/CD Pipeline
```bash
# Full validation for PR
python -m ward test --path tests/ --output=json > test_results.json
coverage run -m ward test --path tests/
coverage report --fail-under=95 --format=json > coverage.json

# Performance regression
python -m ward test --path tests/k1/performance/ --verbose > perf_k1.json
python -m ward test --path tests/k0/performance/ --verbose > perf_k0.json

# Security testing
python -m ward test --path tests/security/ --verbose
```

---

## 8) Anti-Patterns (ZERO TOLERANCE)

### ❌ Prohibited Patterns
- ❌ `asyncio.sleep()` or `time.sleep()` — causes flakiness, use `freezegun`
- ❌ Mocking core logic — mock only external APIs (HTTP, filesystem)
- ❌ Shared test state — each test gets fresh fixtures
- ❌ Non-deterministic data — use fixed IDs, frozen timestamps, seeded RNG
- ❌ Blocking I/O — all I/O must be async
- ❌ Untrapped exceptions — all async operations need proper handling
- ❌ Resource leaks — proper cleanup in fixtures

### ✅ Correct Patterns
```python
# ❌ WRONG: Sleeps cause flakiness
async def test_timeout():
    asyncio.sleep(1)  # FLAKY!

# ✅ CORRECT: Use freezegun for time
from freezegun import freeze_time

@freeze_time("2025-10-23 12:00:00")
async def test_timeout():
    # Time is frozen; test is deterministic
    pass

# ❌ WRONG: Mocking core logic
@patch("orchestrator.coordinate")
async def test_coordination(mock_coord):
    mock_coord.return_value = Mock()  # WRONG!

# ✅ CORRECT: Use real components
async def test_coordination(orch=orchestrator):
    result = await orch.coordinate(task)  # Real implementation
    assert result.status == "COMPLETED"
```

---

## 9) Test Data & Fixtures

### Test Data Best Practices
```python
# Fixed deterministic data
TEST_AGENT_ID = "test-agent-123"
TEST_USER_ID = "test-user-456"
TEST_TASK_ID = "test-task-789"
TEST_TIMESTAMP = "2025-10-23T12:00:00Z"

# Seeded randomness for reproducibility
import random
random.seed(42)
test_port = random.randint(10000, 20000)

# Factories for creating test objects
def create_test_task(task_id=None, **kwargs):
    return TaskAnnouncement(
        task_id=task_id or TEST_TASK_ID,
        description=kwargs.get("description", "Test task"),
        deadline_ms=kwargs.get("deadline_ms", 2000),
        **kwargs
    )
```

### Shared Fixtures
```python
# Store common fixtures in tests/fixtures/
# tests/fixtures/k1_fixtures.py

@fixture(scope="module")
async def orchestrator_fixture():
    orch = Orchestrator(config=test_config)
    await orch.initialize()
    yield orch
    await orch.shutdown()

@fixture(scope="module")
async def agent_fabric_fixture():
    fabric = AgentFabric(max_agents=3)
    await fabric.initialize()
    yield fabric
    await fabric.shutdown()
```

---

## 10) Integration with 5-Step Workflow

### GATE 4 Checklist
- [ ] All tests pass: `python -m ward test --path tests/`
- [ ] Coverage ≥95%: `coverage report --fail-under=95`
- [ ] Contracts validated: `python k1/automation/lint_schemas.py --test-all`
- [ ] Performance budgets met: All p95 latencies documented
- [ ] No simulation code: Grep for sleep statements
- [ ] ADR references in code comments
- [ ] Memory entry ready for GATE 5

### Before Proceeding to GATE 5 (Memory Documentation)
- All GATE 4 checks passing
- Test results and coverage numbers documented
- Performance budget validation complete
- Ready to record in memory and link to ADRs

---

## 11) References

- **WARD Framework**: Python async testing library
- **Coverage.py**: Code coverage measurement
- **Testing Requirements**: `.github/instructions/testing-requirements.instructions.md`
- **5-Step Workflow**: `.github/instructions/service-design.instructions.md` (GATE 4)
- **ADR Master Reference**: `docs/ADR_MASTER_REFERENCE.md`
