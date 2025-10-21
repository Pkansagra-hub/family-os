"""Ward tests for performance testing infrastructure.

This directory contains tests validating the performance testing framework:

## Test Coverage

### Scenario Validation (`test_scenario_validation.py`)
- YAML scenario parsing
- Schema compliance checking
- Phase duration validation
- Environment configuration requirements
- Dry-run execution

### Package Structure (`test_perf_init.py`)
- Package imports
- Export definitions
- Module organization

## Running Tests

Run all performance tests:
```bash
python -m ward test --path tests/performance/
```

Run specific test file:
```bash
python -m ward test --path tests/performance/test_scenario_validation.py
```

## Test Fixtures

Performance tests use the scenario YAML files in `k0/perf/scenarios/` as test data.
These scenarios double as:
1. Test fixtures for validation logic
2. Real scenarios for nightly performance runs

## CI Integration

These tests run as part of the standard CI pipeline before scenarios are executed
in the nightly performance workflow.
"""
