---
description: Testing standards and coverage requirements for MemoryOS components.
applyTo: "tests/**/*.py,**/*test*.py"
---
# 🧪 Testing Requirements

## 0) Testing Philosophy
- **No mock theater** - test real components under controlled conditions
- **Contract validation** - prove interface compliance with actual schemas
- **Performance benchmarks** - validate SLA requirements with measurable metrics
- **WARD framework** - use `python -m ward test --path tests/` for async testing

## 1) Coverage Standards (Measurable)
- **Unit tests**: ≥95% code coverage measured with `coverage.py`
- **Integration tests**: 100% of I/O paths (API endpoints, event handlers, storage operations)
- **Contract tests**: 100% API/event/storage schema compliance validation
- **Performance tests**: All SLA requirements validated (<200ms p95, >1000 req/s)

## 2) Test Categories (Exact Structure)
```
tests/
├── component/           # Individual component tests (≥95% coverage each)
│   ├── test_memory_service.py
│   ├── test_hippocampus_store.py
│   └── test_event_handlers.py
├── integration/         # Multi-component interaction tests
│   ├── test_api_to_storage.py
│   ├── test_event_flows.py
│   └── test_policy_enforcement.py
├── e2e/                # End-to-end scenario tests
│   ├── test_memory_lifecycle.py
│   └── test_user_workflows.py
├── performance/        # Load and benchmark tests
│   ├── test_api_performance.py
│   ├── test_memory_throughput.py
│   └── test_concurrent_users.py
├── security/           # Security and penetration tests
│   ├── test_rbac_enforcement.py
│   ├── test_data_encryption.py
│   └── test_input_validation.py
└── contracts/          # Contract compliance tests
    ├── test_api_schemas.py
    ├── test_event_schemas.py
    └── test_storage_schemas.py
```

## 3) Test Implementation (Concrete Patterns)
- **WARD Framework**:
  ```python
  from ward import test, fixture

  @test("memory service creates memory correctly")
  async def test_memory_creation():
      # Test with real components, not mocks
  ```
- **Real Components**: Use actual `BaseStore`, `EventBus`, `PolicyService` instances
- **Isolated Environments**: Each test gets fresh database, event bus, policy context
- **Deterministic Outcomes**: Use fixed test data, seeded randomness, frozen time

## 4) Contract Validation Tests
```python
# Example contract validation test
@test("API response matches OpenAPI schema")
async def test_api_contract_compliance():
    response = await api_client.get("/api/v1/memories/123")
    validate_against_schema(response.json(), "contracts/api/openapi/modules/memory-openapi.yaml")

@test("Event payload matches event schema")
async def test_event_contract_compliance():
    event = MemoryCreatedEvent(memory_id="123", user_id="456")
    validate_against_schema(event.dict(), "contracts/events/schemas/memory-created.schema.json")
```

## 5) Performance Testing Requirements
- **Load Testing**: Simulate realistic user loads (1000+ concurrent users)
- **Benchmark Testing**: Measure p95 response times under load
- **Throughput Testing**: Validate requests per second requirements
- **Resource Testing**: Monitor CPU, memory, storage usage under load

## 6) Quality Gates (Automated Validation)
```bash
# Coverage measurement
coverage run -m ward test --path tests/
coverage report --fail-under=95

# Performance validation
python -m pytest tests/performance/ --benchmark-only --benchmark-min-rounds=10

# Contract compliance
python contracts/automation/validation_helper.py --test-contracts

# Security testing
python scripts/security/test_security_controls.py
```

## 7) CI Integration (Automated Pipeline)
- **Pre-commit**: Run fast unit tests and linting
- **PR Validation**: Full test suite with coverage reporting
- **Performance Regression**: Compare benchmarks against baselines
- **Contract Validation**: Ensure all schemas pass validation
- **Security Scanning**: Run security tests and vulnerability checks

## 8) Test Data Management
- **Fixtures**: Use deterministic test data in `tests/fixtures/`
- **Factories**: Create test objects with `factory_boy` or similar
- **Cleanup**: Ensure proper cleanup with pytest fixtures or WARD teardown
- **Isolation**: Each test gets clean state, no shared data

## 9) Error Prevention in Tests
- **No Simulation Code**: Use real components, never `asyncio.sleep()` or `time.sleep()`
- **No Mock Theater**: Mock only external dependencies (network, filesystem)
- **Deterministic**: Use fixed timestamps, seeded random, known test data
- **Resource Cleanup**: Proper async cleanup, context managers, exception handling

## 10) Test Execution Commands
```bash
# Run all tests with coverage
python -m ward test --path tests/ --capture=no
coverage run -m ward test --path tests/
coverage report --show-missing

# Run specific test categories
python -m ward test --path tests/component/
python -m ward test --path tests/integration/
python -m pytest tests/performance/ --benchmark-only

# Continuous testing during development
python -m ward test --path tests/component/test_memory_service.py --watch
```
