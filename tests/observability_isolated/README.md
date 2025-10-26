# Observability Metrics Tests (Isolated)

## Why These Tests Are Separate

The observability metrics tests use Prometheus client library which maintains a **global singleton registry**. When running the full L5 test suite, this causes conflicts:

1. Prometheus metrics are registered in a global `CollectorRegistry`
2. Once registered, metrics cannot be re-registered without clearing the registry
3. Multiple test modules trying to create metrics causes `ValueError: Duplicated timeseries`

## How to Run These Tests

### Run Observability Tests Only
```bash
python -m ward test --path tests/k1/l5_infrastructure/observability_isolated/
```

### Run All Other L5 Tests (Without Observability)
```bash
python -m ward test --path tests/k1/l5_infrastructure/
```

This will run all tests EXCEPT observability since this directory is separate.

### Run Complete Test Suite (Recommended Order)

**Phase 1:** Run all L5 infrastructure tests (excluding observability)
```bash
cd d:\familyos
python -m ward test --path tests/k1/l5_infrastructure/
```

**Phase 2:** Run observability tests separately
```bash
cd d:\familyos
python -m ward test --path tests/k1/l5_infrastructure/observability_isolated/
```

## Technical Details

The observability tests require:
- K1MetricsCollector singleton instance
- Prometheus CollectorRegistry cleanup between test runs
- Global fixture scope in conftest.py

These requirements conflict with other L5 tests that may also use metrics, causing cross-contamination.

## Status

- **Observability Tests**: 21/21 passing (100%) when run in isolation
- **Other L5 Tests**: Should all pass without observability interference

Last Updated: October 26, 2025
