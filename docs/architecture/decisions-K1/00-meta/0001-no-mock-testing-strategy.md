---
adr_number: 0001
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: null
implementation_phase: 'Phase 1 (Foundation)'
implementation_status: PLANNING
authors:
- K1 Architecture Team
title: No-Mock Testing Strategy (Real Adapters with Stubs)
affected_layers:
- layer1_input
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- tests.*
concerns:
- architecture
- reliability
- testing
propagation:
  affected_adrs:
  - ADR-0017
  - ADR-0018
  - ADR-0019
  - ADR-0020d
  affected_tests:
  - tests/**/*.py
  triggers:
  - Testing philosophy changes
  - New adapter interface additions
  - Test infrastructure changes
related_adrs:
- ADR-0017
- ADR-0017g
- ADR-0018
- ADR-0019e
- ADR-0020d
related_contracts:
- k1/contracts/schemas/wiring/sessionstate.wiring.yaml
related_diagrams: []
research_citations:
- 'Mocks Aren''t Stubs (Martin Fowler, 2007)'
- 'Test-Driven Development by Example (Kent Beck, 2002)'
- 'Working Effectively with Legacy Code (Michael Feathers, 2004)'
- 'Growing Object-Oriented Software, Guided by Tests (Freeman & Pryce, 2009)'
superseded_by: []
supersedes: []
---

# ADR-0001 (Meta): No-Mock Testing Strategy (Real Adapters with Stubs)

**Status:** ACCEPTED
**Date:** 2025-11-03
**Authors:** K1 Architecture Team
**Category:** Meta - Testing Philosophy
**Related ADRs:**

- [ADR-0017 (SessionState Design)](../03-layer2-orchestration/0017-sessionstate-6-section-design/0017.md)
- [ADR-0017g (Single-Writer Concurrency)](../03-layer2-orchestration/0017-sessionstate-6-section-design/0017g-single-writer-concurrency-pattern.md)
- [ADR-0020d (LOCAL COLD Tier)](../06-layer5-infrastructure/0020-multi-tier-storage/0020d-local-cold-tier-l1a-k1-sqlite-edge-first.md)

---

## Context

### Problem Statement

K1 testing faces a critical choice: **use mocks** (fake objects that verify behavior) or **use real components** (actual implementations or lightweight stubs).

**Problems with Mock-Heavy Testing:**

1. **Mocks Lie:** Mocks return what you tell them, not what real code does
2. **Brittle Tests:** Mocks couple tests to implementation details
3. **False Confidence:** Tests pass but production fails
4. **Maintenance Burden:** Mocks must be updated when interfaces change
5. **Integration Gaps:** Mocks hide real integration issues

**Real-World Failures from Mock-Heavy Testing:**

| Failure | Root Cause | Mock Problem |
|---------|------------|--------------|
| SQLite query syntax error | Mock returned hardcoded data | Never tested real SQL |
| Event serialization crash | Mock skipped serialization | Never tested real encoding |
| Race condition in eviction | Mock had no timing | Never tested concurrent access |
| K0 Bridge timeout | Mock returned instantly | Never tested network latency |

### Requirements

1. **Tests Must Run Standalone:** No external services (K0, databases, APIs)
2. **Tests Must Use Real Code:** Actual adapters, real serialization, true concurrency
3. **Tests Must Be Fast:** <10s for unit tests, <60s for integration tests
4. **Tests Must Be Deterministic:** Same result every run
5. **Tests Must Catch Real Bugs:** Failures should predict production issues

---

## Decision

We will implement a **No-Mock Testing Strategy** using **real adapters with lightweight stubs**:

### Core Principle: No Mocks, Real Adapters

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NO-MOCK TESTING STRATEGY                                  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    PRODUCTION                                        │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │SessionState │──│ SQLite      │──│ K0 Bridge   │                  │    │
│  │  │  Manager    │  │ Adapter     │  │ Adapter     │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    TESTING (SAME CODE, STUB ADAPTERS)               │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │SessionState │──│ InMemory    │──│ Local       │                  │    │
│  │  │  Manager    │  │ Storage     │  │ Event       │                  │    │
│  │  │  (REAL)     │  │ Adapter     │  │ Adapter     │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  │                   (REAL IMPL)      (REAL IMPL)                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  KEY DIFFERENCE:                                                            │
│  • MOCKS: Fake objects that verify calls (e.g., mock.assert_called)        │
│  • STUBS: Real implementations with in-memory backing (e.g., InMemory*)    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Adapter Interfaces (Ports)

All external dependencies are accessed through port interfaces:

```python
# k1/sessionstate/ports.py
"""Port interfaces for SessionState external dependencies"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


class IStoragePort(ABC):
    """Port for LOCAL COLD and K0 storage operations"""

    @abstractmethod
    async def archive(self, section: str, session_id: str, data: bytes) -> None:
        """Archive section data to storage"""
        pass

    @abstractmethod
    async def restore(self, section: str, session_id: str) -> Optional[bytes]:
        """Restore section data from storage"""
        pass

    @abstractmethod
    async def delete(self, section: str, session_id: str) -> None:
        """Delete section data from storage"""
        pass

    @abstractmethod
    async def list_sessions(self) -> List[str]:
        """List all stored sessions"""
        pass


class IEventPort(ABC):
    """Port for event bus operations"""

    @abstractmethod
    async def publish(self, topic: str, event: Any) -> None:
        """Publish event to topic"""
        pass

    @abstractmethod
    async def subscribe(self, topic: str, handler: Any) -> None:
        """Subscribe to topic with handler"""
        pass

    @abstractmethod
    async def unsubscribe(self, topic: str, handler: Any) -> None:
        """Unsubscribe handler from topic"""
        pass


class IWriterPort(ABC):
    """Port for verifying writer identity"""

    @abstractmethod
    def get_writer_id(self) -> str:
        """Get authorized writer ID"""
        pass

    @abstractmethod
    def is_writer(self, agent_id: str) -> bool:
        """Check if agent is authorized writer"""
        pass


class ILifecyclePort(ABC):
    """Port for session lifecycle operations"""

    @abstractmethod
    async def start(self) -> None:
        """Start the component"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the component gracefully"""
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """Check component health"""
        pass
```

### Stub Adapters for Testing

#### InMemoryStorageAdapter

```python
# k1/sessionstate/adapters/inmemory_storage.py
"""In-memory storage adapter for testing LOCAL COLD tier"""

from typing import Dict, List, Optional
from k1.sessionstate.ports import IStoragePort


class InMemoryStorageAdapter(IStoragePort):
    """
    In-memory implementation of IStoragePort.

    Used for testing SessionState without real SQLite or K0.
    REAL IMPLEMENTATION - not a mock. Stores actual data in memory.

    Features:
    - Full IStoragePort contract compliance
    - Inspectable state for assertions
    - Supports failure injection for error testing
    - Thread-safe for concurrent tests
    """

    def __init__(self):
        self._storage: Dict[str, Dict[str, bytes]] = {}
        self._failure_mode: Optional[str] = None
        self._call_count: Dict[str, int] = {"archive": 0, "restore": 0, "delete": 0}

    async def archive(self, section: str, session_id: str, data: bytes) -> None:
        """Archive section data to in-memory storage"""
        self._call_count["archive"] += 1

        if self._failure_mode == "archive_fails":
            raise IOError("Simulated archive failure")

        key = f"{session_id}:{section}"
        if session_id not in self._storage:
            self._storage[session_id] = {}
        self._storage[session_id][section] = data

    async def restore(self, section: str, session_id: str) -> Optional[bytes]:
        """Restore section data from in-memory storage"""
        self._call_count["restore"] += 1

        if self._failure_mode == "restore_fails":
            raise IOError("Simulated restore failure")

        if session_id in self._storage and section in self._storage[session_id]:
            return self._storage[session_id][section]
        return None

    async def delete(self, section: str, session_id: str) -> None:
        """Delete section data from in-memory storage"""
        self._call_count["delete"] += 1

        if self._failure_mode == "delete_fails":
            raise IOError("Simulated delete failure")

        if session_id in self._storage and section in self._storage[session_id]:
            del self._storage[session_id][section]

    async def list_sessions(self) -> List[str]:
        """List all stored sessions"""
        return list(self._storage.keys())

    # Test helpers (not part of IStoragePort)

    def set_failure_mode(self, mode: Optional[str]) -> None:
        """Enable failure injection for error testing"""
        self._failure_mode = mode

    def get_call_count(self, method: str) -> int:
        """Get call count for method (for assertions)"""
        return self._call_count.get(method, 0)

    def get_stored_data(self, session_id: str, section: str) -> Optional[bytes]:
        """Directly inspect stored data (for assertions)"""
        if session_id in self._storage:
            return self._storage[session_id].get(section)
        return None

    def clear(self) -> None:
        """Clear all stored data"""
        self._storage.clear()
        self._call_count = {"archive": 0, "restore": 0, "delete": 0}
```

#### LocalEventAdapter

```python
# k1/sessionstate/adapters/local_event.py
"""Local event adapter for testing event emission"""

from typing import Dict, List, Any, Callable, Awaitable
from collections import defaultdict
import asyncio
from k1.sessionstate.ports import IEventPort


class LocalEventAdapter(IEventPort):
    """
    Local in-process event adapter for testing.

    REAL IMPLEMENTATION - not a mock. Actually dispatches events
    to registered handlers synchronously (for deterministic tests).

    Features:
    - Full IEventPort contract compliance
    - Synchronous dispatch for predictable tests
    - Event capture for assertions
    - Handler inspection for debugging
    """

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._captured_events: List[tuple] = []  # (topic, event) pairs
        self._synchronous: bool = True  # Sync dispatch for tests

    async def publish(self, topic: str, event: Any) -> None:
        """Publish event to topic, dispatching to all handlers"""
        self._captured_events.append((topic, event))

        handlers = self._handlers.get(topic, [])
        for handler in handlers:
            if self._synchronous:
                # Sync dispatch for deterministic tests
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            else:
                # Async dispatch (production-like)
                asyncio.create_task(handler(event))

    async def subscribe(self, topic: str, handler: Callable) -> None:
        """Subscribe handler to topic"""
        self._handlers[topic].append(handler)

    async def unsubscribe(self, topic: str, handler: Callable) -> None:
        """Unsubscribe handler from topic"""
        if topic in self._handlers and handler in self._handlers[topic]:
            self._handlers[topic].remove(handler)

    # Test helpers (not part of IEventPort)

    def get_captured_events(self, topic: Optional[str] = None) -> List[tuple]:
        """Get captured events, optionally filtered by topic"""
        if topic:
            return [(t, e) for t, e in self._captured_events if t == topic]
        return self._captured_events.copy()

    def get_last_event(self, topic: str) -> Optional[Any]:
        """Get last event for topic"""
        for t, e in reversed(self._captured_events):
            if t == topic:
                return e
        return None

    def get_handler_count(self, topic: str) -> int:
        """Get number of handlers for topic"""
        return len(self._handlers.get(topic, []))

    def clear(self) -> None:
        """Clear captured events and handlers"""
        self._captured_events.clear()
        self._handlers.clear()

    def set_synchronous(self, sync: bool) -> None:
        """Set synchronous/async dispatch mode"""
        self._synchronous = sync
```

### Test Fixture Patterns

```python
# tests/k1/sessionstate/conftest.py
"""Shared test fixtures for SessionState testing"""

import pytest
from k1.sessionstate.manager import SessionStateManager
from k1.sessionstate.adapters.inmemory_storage import InMemoryStorageAdapter
from k1.sessionstate.adapters.local_event import LocalEventAdapter


@pytest.fixture
def storage_adapter():
    """Provide InMemoryStorageAdapter for tests"""
    adapter = InMemoryStorageAdapter()
    yield adapter
    adapter.clear()


@pytest.fixture
def event_adapter():
    """Provide LocalEventAdapter for tests"""
    adapter = LocalEventAdapter()
    yield adapter
    adapter.clear()


@pytest.fixture
def session_manager(storage_adapter, event_adapter):
    """
    Provide fully wired SessionStateManager for tests.

    Uses REAL SessionStateManager with STUB adapters.
    NO MOCKS - all code paths exercised.
    """
    manager = SessionStateManager(
        session_id="test-session-001",
        writer_id="concierge-test",
        storage_port=storage_adapter,
        event_port=event_adapter
    )
    return manager


@pytest.fixture
def populated_session_manager(session_manager):
    """
    Provide SessionStateManager with pre-populated test data.

    Useful for testing eviction, migration, reconstruction.
    """
    # Add test data to sections
    session_manager.beliefs_active.add_fact(
        fact_id="fact-001",
        subject="user",
        predicate="name",
        value="Alice",
        confidence=0.95
    )
    session_manager.scoreboard.add_referent(
        referent_id="ref-001",
        text="the meeting",
        entity_id="meeting-123",
        salience=0.8
    )
    return session_manager
```

### Why Mocks Are Forbidden

| Mock Pattern | Problem | Stub Alternative |
|--------------|---------|------------------|
| `mock.return_value = data` | Hardcodes behavior | InMemoryStorageAdapter stores real data |
| `mock.assert_called_with(args)` | Couples to implementation | Assert on captured events |
| `@patch('module.function')` | Hides import issues | Use dependency injection |
| `MagicMock()` | Returns anything | Real interfaces fail on wrong calls |
| `side_effect = Exception` | Fake errors | `adapter.set_failure_mode()` |

### Test Categories

| Category | Scope | Adapters | Example |
|----------|-------|----------|---------|
| **Unit** | Single component | Stub adapters | MutationGuard.preflight() |
| **Integration** | Multiple components | Stub adapters | SessionStateManager → EvictionEngine |
| **Contract** | Port compliance | Real + Stub | SQLiteStorageAdapter vs InMemoryStorageAdapter |
| **E2E** | Full system | Real adapters | SessionState → K0 Bridge |

---

## Implementation Guidelines

### DO: Use Port Interfaces

```python
# Good: Depend on interface
class SessionStateManager:
    def __init__(self, storage_port: IStoragePort):
        self._storage = storage_port

# Test: Inject stub adapter
def test_eviction():
    storage = InMemoryStorageAdapter()
    manager = SessionStateManager(storage_port=storage)
    # Test with REAL code, STUB storage
```

### DON'T: Use Mock Libraries

```python
# Bad: Mock hides real behavior
from unittest.mock import Mock, patch

@patch('k1.sessionstate.storage.SQLiteStorage')
def test_eviction(mock_storage):
    mock_storage.archive.return_value = None  # Lie!
    manager = SessionStateManager()
    # Test passes but production fails
```

### DO: Assert on Real State

```python
# Good: Assert on actual stored data
async def test_archive_persists_data():
    storage = InMemoryStorageAdapter()
    await storage.archive("beliefs", "session-1", b"data")

    # Assert on REAL stored data
    assert storage.get_stored_data("session-1", "beliefs") == b"data"
```

### DON'T: Assert on Mock Calls

```python
# Bad: Asserts on implementation detail
def test_archive_persists_data(mock_storage):
    manager.archive_beliefs(data)

    # Asserts on HOW, not WHAT
    mock_storage.archive.assert_called_once_with("beliefs", "session-1", data)
```

### DO: Inject Failure Modes

```python
# Good: Test error handling with real adapter
async def test_restore_handles_failure():
    storage = InMemoryStorageAdapter()
    storage.set_failure_mode("restore_fails")

    manager = SessionStateManager(storage_port=storage)
    result = await manager.restore_session("session-1")

    assert result.success is False
    assert "restore failure" in result.error
```

---

## Consequences

### Positive

1. **Catches Real Bugs:** Tests exercise actual code paths
2. **Refactor Safe:** Interface changes caught at compile time
3. **Less Maintenance:** No mock updates when implementation changes
4. **Deterministic:** Stub adapters have predictable behavior
5. **Fast Feedback:** In-memory adapters are fast

### Negative

1. **More Code:** Must implement stub adapters
2. **Less Isolation:** Unit tests touch more code
3. **Setup Complexity:** Wiring real components takes more setup

### Mitigations

| Concern | Mitigation |
|---------|------------|
| More code | Shared stub adapters in `adapters/` |
| Less isolation | Accept larger test scope, catch more bugs |
| Setup complexity | pytest fixtures encapsulate wiring |

---

## Contract Compliance Testing

Stub adapters must pass the same contract tests as production adapters:

```python
# tests/k1/sessionstate/contracts/test_storage_contract.py
"""Contract tests for IStoragePort implementations"""

import pytest
from k1.sessionstate.ports import IStoragePort
from k1.sessionstate.adapters.inmemory_storage import InMemoryStorageAdapter
from k1.sessionstate.adapters.sqlite_storage import SQLiteStorageAdapter


class StorageContractTests:
    """
    Contract tests that ALL IStoragePort implementations must pass.

    Run with both InMemoryStorageAdapter (unit tests) and
    SQLiteStorageAdapter (integration tests).
    """

    @pytest.fixture
    def adapter(self) -> IStoragePort:
        raise NotImplementedError("Subclass must provide adapter")

    async def test_archive_and_restore_round_trip(self, adapter):
        """Archived data can be restored exactly"""
        data = b"test data"
        await adapter.archive("beliefs", "session-1", data)
        restored = await adapter.restore("beliefs", "session-1")
        assert restored == data

    async def test_restore_nonexistent_returns_none(self, adapter):
        """Restoring missing data returns None"""
        result = await adapter.restore("beliefs", "nonexistent")
        assert result is None

    async def test_delete_removes_data(self, adapter):
        """Deleted data cannot be restored"""
        await adapter.archive("beliefs", "session-1", b"data")
        await adapter.delete("beliefs", "session-1")
        result = await adapter.restore("beliefs", "session-1")
        assert result is None

    async def test_list_sessions_includes_archived(self, adapter):
        """Listed sessions include all archived sessions"""
        await adapter.archive("beliefs", "session-1", b"data1")
        await adapter.archive("beliefs", "session-2", b"data2")
        sessions = await adapter.list_sessions()
        assert "session-1" in sessions
        assert "session-2" in sessions


class TestInMemoryStorageContract(StorageContractTests):
    """InMemoryStorageAdapter contract compliance"""

    @pytest.fixture
    def adapter(self):
        return InMemoryStorageAdapter()


class TestSQLiteStorageContract(StorageContractTests):
    """SQLiteStorageAdapter contract compliance (integration)"""

    @pytest.fixture
    def adapter(self, tmp_path):
        db_path = tmp_path / "test.db"
        return SQLiteStorageAdapter(db_path)
```

---

## Final Decision

**No-Mock Testing Strategy** is ACCEPTED for all K1 SessionState tests.

### Key Principles

| Principle | Implementation |
|-----------|----------------|
| **No mocks** | Forbidden: `unittest.mock`, `MagicMock`, `@patch` |
| **Real adapters** | Use actual implementations of port interfaces |
| **Stub adapters** | InMemoryStorageAdapter, LocalEventAdapter for tests |
| **Contract tests** | All adapters (stub and real) pass same contract tests |
| **Failure injection** | `adapter.set_failure_mode()` not `side_effect` |

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| IStoragePort interface | PLANNING | Port definition |
| IEventPort interface | PLANNING | Port definition |
| InMemoryStorageAdapter | PLANNING | Test stub |
| LocalEventAdapter | PLANNING | Test stub |
| Contract tests | PLANNING | Shared test suite |
| Test fixtures | PLANNING | pytest conftest.py |
