# K0 Essential Coverage Plan: Kernel & Pipeline Robustness

**Document ID**: COVERAGE-PLAN-002
**Version**: 1.0
**Created**: 2025-12-26
**Status**: Active
**Target**: 92% coverage on essential modules only
**Current**: 70% overall (essential modules vary)
**Estimated Effort**: 15 days (vs 37 days original plan)

---

## Executive Summary

This is a **focused coverage plan** targeting only the modules essential to proving kernel and pipeline robustness. Non-essential modules (CLI tools, telemetry, ML/embedding infrastructure, automation scripts) are explicitly excluded.

### Philosophy

> "Test what proves the system works, not what makes dashboards pretty."

### Scope Reduction

| Category | Original Plan | This Plan | Removed |
|----------|--------------|-----------|---------|
| Total Modules | 128 | 30 | 98 |
| Estimated Days | 37 | 15 | 22 |
| Test Files | ~150 | ~45 | ~105 |

---

## What We're Testing (Essential)

| Category | Purpose | Module Count |
|----------|---------|--------------|
| **Kernel Core** | Syscalls, lifecycle, config, admission | 7 |
| **Pipeline Infrastructure** | Loading, execution, DAG, scheduling | 7 |
| **Event Bus** | Inter-module communication | 4 |
| **Data Integrity** | WAL, outbox, idempotency, UoW | 5 |
| **Fabric & Policy** | Actor management, authorization | 7 |
| **Total** | | **30 modules** |

---

## What We're NOT Testing (Removed from Scope)

### Explicitly Removed Categories

| Category | Reason | Modules Removed |
|----------|--------|-----------------|
| CLI Tools | Operational tooling, not runtime | `cli/*` |
| Telemetry/Dashboards | Observability, not correctness | `telemetry/*` |
| Performance Profiles | Tuning, not functionality | `perf/profiles/*` |
| Sync/CRDT | Multi-node future feature | `sync/*` |
| Embedding/ML | ML infrastructure, integration-tested | `modules/embedding/*`, `drivers/faiss.py`, etc. |
| External Drivers | Require live services | `drivers/postgres.py`, `drivers/neo4j_driver.py` |
| Automation Scripts | Dev tooling | `automation/*` |
| SSE/Streaming | External interface | `ports/sse.py`, `sse/*` |
| Full-text Search | Search feature, not core | `storage/fts.py`, `drivers/fts5.py` |

---

## Milestone 0: Fix Remaining Test Failures

**Target**: Green test suite
**Priority**: P0 Blocker
**Estimated Effort**: 1 day

### Epic 0.1: P08 Scheduler Failures (5 remaining)

| Issue ID | File | Error | Fix Strategy |
|----------|------|-------|--------------|
| 0.1.1 | `test_p08_triggers.py` | Status `PENDING` vs `READY` | Fix trigger state machine |
| 0.1.2 | `test_p08_scheduler_migration.py` | Trigger registration | Fix migration sequence |

**Acceptance**: All tests pass with `pytest tests/ -x --tb=short`

---

## Milestone 1: Kernel Core (7 modules)

**Target**: 92% coverage on kernel internals
**Priority**: P0 Critical
**Estimated Effort**: 4 days

### Epic 1.1: Syscall Layer

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `kernel/syscalls.py` | 438 | 6% | 92% | **THE kernel API** - all module interactions |

**Test Strategy**:

- Test each syscall method independently
- Test error paths and validation
- Test capability checks
- Test event emission from syscalls

### Epic 1.2: Kernel Lifecycle

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `kernel/main.py` | 56 | 30% | 92% | Entry point, startup/shutdown |
| `kernel/app.py` | 699 | 71% | 92% | App factory, DI container |
| `kernel/dependencies.py` | 93 | 70% | 92% | Dependency injection |

**Test Strategy**:

- Test startup sequence
- Test graceful shutdown
- Test dependency resolution
- Test configuration injection

### Epic 1.3: Kernel Control

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `kernel/admission.py` | 70 | 86% | 92% | Event admission control |
| `kernel/config.py` | 297 | 62% | 92% | Runtime configuration |
| `kernel/readiness.py` | 32 | 91% | 92% | Health/readiness probes |

**Test Strategy**:

- Test admission accept/reject paths
- Test config validation
- Test config hot-reload
- Test readiness probe states

---

## Milestone 2: Pipeline Infrastructure (7 modules)

**Target**: 92% coverage on pipeline execution
**Priority**: P0 Critical
**Estimated Effort**: 3 days

### Epic 2.1: Pipeline Loading & Protocol

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `pipelines/loader.py` | 116 | 86% | 92% | Pipeline discovery and loading |
| `pipelines/protocol.py` | 36 | 82% | 92% | Pipeline execution contract |

**Test Strategy**:

- Test YAML loading
- Test pipeline validation
- Test protocol enforcement

### Epic 2.2: Pipeline Execution

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `runtime/pipeline_runner.py` | 131 | 73% | 92% | Executes pipeline stages |
| `runtime/dag_builder.py` | 76 | 82% | 92% | Builds execution DAG |
| `runtime/module_registry.py` | 120 | 77% | 92% | Module discovery |

**Test Strategy**:

- Test DAG construction from pipeline def
- Test stage execution order
- Test error propagation
- Test module loading

### Epic 2.3: Scheduling

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `scheduler/scheduler.py` | 179 | 95% | 95% | Task scheduling (maintain) |
| `scheduler/triggers.py` | 288 | 82% | 92% | Trigger system |

**Test Strategy**:

- Test trigger registration
- Test trigger firing
- Test schedule evaluation

---

## Milestone 3: Event Bus (4 modules)

**Target**: 92% coverage on event communication
**Priority**: P0 Critical
**Estimated Effort**: 2 days

### Epic 3.1: Bus Core

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `bus/core.py` | 199 | 92% | 92% | Event bus implementation (maintain) |
| `bus/middleware.py` | 62 | 97% | 97% | Middleware chain (maintain) |
| `bus/universal.py` | 22 | 83% | 92% | Universal bus interface |

### Epic 3.2: Internal Bus Driver

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `drivers/internal_bus_driver.py` | 49 | 34% | 92% | In-process event routing |

**Test Strategy**:

- Test publish/subscribe
- Test topic routing
- Test middleware execution order
- Test error handling in handlers

---

## Milestone 4: Data Integrity (5 modules)

**Target**: 92% coverage on durability guarantees
**Priority**: P0 Critical
**Estimated Effort**: 3 days

### Epic 4.1: Write-Ahead Log & Outbox

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `storage/wal.py` | 86 | 85% | 92% | Durability guarantee |
| `storage/outbox.py` | 94 | 84% | 92% | Reliable event publishing |

**Test Strategy**:

- Test WAL write/read/replay
- Test outbox enqueue/dequeue
- Test failure recovery

### Epic 4.2: Idempotency

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `idem/ledger.py` | 82 | 65% | 92% | Idempotency tracking |
| `idem/derive.py` | 54 | 71% | 92% | Key derivation |

**Test Strategy**:

- Test duplicate detection
- Test key generation determinism
- Test ledger persistence

### Epic 4.3: Unit of Work

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `uow/unit_of_work.py` | 184 | 26% | 92% | Transaction boundaries |

**Test Strategy**:

- Test commit/rollback
- Test nested transactions
- Test resource cleanup

---

## Milestone 5: Fabric & Policy (7 modules)

**Target**: 92% coverage on actor management and authorization
**Priority**: P0 Critical
**Estimated Effort**: 2 days

### Epic 5.1: Actor Fabric

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `fabric/fabric.py` | 136 | 91% | 92% | Actor lifecycle |
| `fabric/registry.py` | 155 | 94% | 94% | Actor discovery (maintain) |
| `fabric/policy.py` | 73 | 87% | 92% | Execution policies |

### Epic 5.2: Policy Enforcement

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `policy/pep_syscall.py` | 328 | 90% | 92% | Policy enforcement point |
| `policy/acl_enforcer.py` | 92 | 86% | 92% | Access control |

### Epic 5.3: Gate & Schema

| Module | Stmts | Current | Target | Description |
|--------|-------|---------|--------|-------------|
| `gate/minimal_gate.py` | 423 | 82% | 92% | Pipeline admission gate |
| `gate/schema_registry.py` | 182 | 95% | 95% | Schema validation (maintain) |

**Test Strategy**:

- Test actor start/stop/restart
- Test policy evaluation
- Test ACL checks
- Test gate accept/reject
- Test schema validation errors

---

## Test Implementation Priority

### Week 1: Foundation

| Day | Focus | Modules |
|-----|-------|---------|
| 1 | Fix failures | P08 scheduler tests |
| 2-3 | Syscalls | `kernel/syscalls.py` |
| 4-5 | Kernel lifecycle | `kernel/main.py`, `kernel/app.py` |

### Week 2: Pipelines & Bus

| Day | Focus | Modules |
|-----|-------|---------|
| 6-7 | Pipeline execution | `runtime/pipeline_runner.py`, `runtime/dag_builder.py` |
| 8 | Event bus | `bus/universal.py`, `drivers/internal_bus_driver.py` |
| 9-10 | Scheduling | `scheduler/triggers.py` |

### Week 3: Data & Policy

| Day | Focus | Modules |
|-----|-------|---------|
| 11-12 | Data integrity | `uow/unit_of_work.py`, `idem/ledger.py` |
| 13-14 | Fabric & Policy | `fabric/policy.py`, `policy/acl_enforcer.py` |
| 15 | Polish & verify | All modules at 92% |

---

## Success Criteria

### Must Have (Release Blocker)

- [ ] All 30 essential modules at ≥92% coverage
- [ ] Zero test failures
- [ ] Zero test collection errors
- [ ] All kernel syscalls have explicit tests
- [ ] All pipeline stages have execution tests
- [ ] All event bus paths tested

### Nice to Have

- [ ] Integration tests for full pipeline flows
- [ ] Performance regression tests for critical paths
- [ ] Chaos tests for failure scenarios

---

## Modules Tracking Table

| # | Module | Stmts | Current | Target | Status |
|---|--------|-------|---------|--------|--------|
| 1 | `kernel/syscalls.py` | 438 | 6% | 92% | 🔴 |
| 2 | `kernel/main.py` | 56 | 30% | 92% | 🔴 |
| 3 | `kernel/app.py` | 699 | 71% | 92% | 🟡 |
| 4 | `kernel/dependencies.py` | 93 | 70% | 92% | 🟡 |
| 5 | `kernel/admission.py` | 70 | 86% | 92% | 🟡 |
| 6 | `kernel/config.py` | 297 | 62% | 92% | 🟡 |
| 7 | `kernel/readiness.py` | 32 | 91% | 92% | 🟢 |
| 8 | `pipelines/loader.py` | 116 | 86% | 92% | 🟡 |
| 9 | `pipelines/protocol.py` | 36 | 82% | 92% | 🟡 |
| 10 | `runtime/pipeline_runner.py` | 131 | 73% | 92% | 🟡 |
| 11 | `runtime/dag_builder.py` | 76 | 82% | 92% | 🟡 |
| 12 | `runtime/module_registry.py` | 120 | 77% | 92% | 🟡 |
| 13 | `scheduler/scheduler.py` | 179 | 95% | 95% | ✅ |
| 14 | `scheduler/triggers.py` | 288 | 82% | 92% | 🟡 |
| 15 | `bus/core.py` | 199 | 92% | 92% | ✅ |
| 16 | `bus/middleware.py` | 62 | 97% | 97% | ✅ |
| 17 | `bus/universal.py` | 22 | 83% | 92% | 🟡 |
| 18 | `drivers/internal_bus_driver.py` | 49 | 34% | 92% | 🔴 |
| 19 | `storage/wal.py` | 86 | 85% | 92% | 🟡 |
| 20 | `storage/outbox.py` | 94 | 84% | 92% | 🟡 |
| 21 | `idem/ledger.py` | 82 | 65% | 92% | 🟡 |
| 22 | `idem/derive.py` | 54 | 71% | 92% | 🟡 |
| 23 | `uow/unit_of_work.py` | 184 | 26% | 92% | 🔴 |
| 24 | `fabric/fabric.py` | 136 | 91% | 92% | 🟢 |
| 25 | `fabric/registry.py` | 155 | 94% | 94% | ✅ |
| 26 | `fabric/policy.py` | 73 | 87% | 92% | 🟡 |
| 27 | `policy/pep_syscall.py` | 328 | 90% | 92% | 🟢 |
| 28 | `policy/acl_enforcer.py` | 92 | 86% | 92% | 🟡 |
| 29 | `gate/minimal_gate.py` | 423 | 82% | 92% | 🟡 |
| 30 | `gate/schema_registry.py` | 182 | 95% | 95% | ✅ |

**Legend**: 🔴 <50% | 🟡 50-89% | 🟢 90-91% | ✅ ≥92%

---

## Commands Reference

```bash
# Run all tests
pytest tests/ -v --tb=short

# Run with coverage for essential modules only
pytest tests/ --cov=k0.kernel --cov=k0.pipelines --cov=k0.runtime --cov=k0.scheduler --cov=k0.bus --cov=k0.storage --cov=k0.idem --cov=k0.uow --cov=k0.fabric --cov=k0.policy --cov=k0.gate --cov-report=term-missing

# Run specific module tests
pytest tests/k0/kernel/ -v
pytest tests/k0/runtime/ -v

# Generate HTML coverage report
pytest tests/ --cov=k0 --cov-report=html
```
