"""
SessionState Test Suite
=======================

This folder contains tests for the SessionState module.

Test Categories:
- Unit tests: Individual component isolation
- Integration tests: Component interaction
- Contract tests: Port/adapter compliance
- Performance tests: SLA validation

Test Coverage Requirements:
- 80% line coverage minimum
- All public methods tested
- All error paths tested
- All port adapters tested

Fixtures:
- conftest.py provides shared fixtures
- Use InMemoryStorageAdapter for isolation
- Use LocalEventAdapter with capture mode
- Use DirectWriterAdapter for testing

Running Tests:
    python -m pytest tests/k1/sessionstate/ -v
    python -m pytest tests/k1/sessionstate/ --cov=k1.sessionstate

Implementation Plan: docs/plans/sessionstate-implementation-plan.md
"""
