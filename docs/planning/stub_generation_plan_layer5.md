# Layer 5 Infrastructure Stub Generation Plan

**Version:** 1.0
**Created:** 2025-10-27
**Status:** 🚧 PLANNING
**Target Release:** Q4 2025

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Plan Structure](#plan-structure)
3. [Comment Template](#comment-template)
4. [Milestone Overview](#milestone-overview)
5. [Milestone 1: Bridge (K0 Communication)](#milestone-1-bridge-k0-communication)
6. [ADR Reference Matrix](#adr-reference-matrix)
7. [Team Assignments](#team-assignments)
8. [Implementation Workflow](#implementation-workflow)
9. [Success Criteria](#success-criteria)

---

## Executive Summary

This document outlines the **Layer 5 Infrastructure Stub Generation Plan** - a systematic approach to creating Python stubs for all 60+ Layer 5 components with comprehensive inline documentation, ADR references, and performance budgets.

**Key Objectives:**

- ✅ Create stub files with detailed comments for all 14 module families
- ✅ Reference relevant ADRs for each component
- ✅ Define interfaces and contracts before implementation
- ✅ Establish cognitive_trace_id propagation points
- ✅ Set performance budgets for each component
- ✅ Enable parallel implementation by multiple teams

**Total Components:** 60+ files across 14 module families
**Total ADRs Referenced:** 15+ ADRs
**Estimated Timeline:** 2 weeks for stub generation, 8 weeks for full implementation

---

## Plan Structure

### Organization Hierarchy

```
Plan Structure:
  ├── Milestones (14 Module Families)
  │   ├── Epic 1: Core Components
  │   ├── Epic 2: Sub-components
  │   └── Epic 3: Integration/Testing
  └── Issues (Individual Files)
      ├── Python Stub
      ├── ADR References
      ├── Dependencies
      ├── Interface Contracts
      └── Implementation Notes
```

### File Structure Conventions

```
k1/
├── bridge_k0/                          # Milestone 1
│   ├── command_client.py              # Issue 1.1.1
│   ├── protocol.py                    # Issue 1.1.3
│   ├── lanes.py                       # Issue 1.3.1
│   ├── retrieval.py                   # Issue 1.3.2
│   ├── batch_client.py                # Issue 1.3.3
│   ├── http2_client.py                # Issue 1.1.2
│   └── ports/                         # Epic 1.2
│       ├── command_port.py            # Issue 1.2.1
│       ├── query_port.py              # Issue 1.2.2
│       ├── sse_port.py                # Issue 1.2.3
│       └── observability_port.py      # Issue 1.2.4
│
├── l5_infrastructure/                 # Milestones 2-14
│   ├── event_bus/                     # Milestone 2
│   ├── serialization/                 # Milestone 3
│   ├── resilience/                    # Milestone 4
│   ├── storage/                       # Milestone 5
│   ├── thermal/                       # Milestone 6
│   ├── placement/                     # Milestone 7
│   ├── backpressure/                  # Milestone 8
│   ├── rate_limiting/                 # Milestone 10
│   ├── scheduler/                     # Milestone 11
│   ├── admission/                     # Milestone 12
│   └── extensions/                    # Milestone 14
│
├── l4_runtime/
│   └── storage/                       # Milestone 5 (Supporting)
│
└── l3_execution/
    └── model_hub/                     # Milestone 9 (Supporting)
```

---

## Comment Template

### Standard Python Stub Template

Each Python file will follow this consistent comment structure:

```python
"""
<Module Name> - <Brief Description>

Layer: L5 Infrastructure
Component: <Component Family>
Priority: <P0/P1/P2/M1/M2>
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-XXXX: <Primary ADR Title>
    - ADR-XXXX: <Related ADR Title>

Dependencies:
    Internal:
        - k1.l5_infrastructure.<module>.<class>
        - k1.l4_runtime.<module>.<class>
    External:
        - <external library>

Connects To:
    Upstream:
        - <Component that calls this>
    Downstream:
        - <Component this calls>

Performance Budgets:
    - <metric>: <target> (P95)
    - Memory: <budget>

Observability:
    - Metrics: <prometheus_metric_name>
    - Traces: <span_name>
    - Logs: <event_type>

References:
    - Diagram: architecture_diagrams/k1/<diagram>.mmd
    - Whiteboard: docs/whiteboard.md (Section X)
    - Test: tests/k1/l5_infrastructure/test_<module>.py
"""

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Optional, Dict, List, Any, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum
import asyncio
import logging

# Third-party imports
# <library> - <purpose>
# Example: import aiohttp  # HTTP/2 client

# Internal imports
# from k1.l5_infrastructure.<module> import <class>
# from k1.config import load_config

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@<team>): Load from k1/config/<config>.yml (ADR-XXXX)
# Assigned to: Issue #XXX
DEFAULT_CONFIG = {
    'timeout_ms': 5000,
    'retry_count': 3,
    'backoff_factor': 1.5,
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================

class ComponentState(Enum):
    """Component lifecycle states (ADR-XXXX)"""
    INIT = 'INIT'
    ACTIVE = 'ACTIVE'
    DEGRADED = 'DEGRADED'
    TERMINATED = 'TERMINATED'


@dataclass
class ComponentConfig:
    """
    Configuration dataclass for <Component>.

    Fields:
        param1: <Description> (ADR-XXXX)
        param2: <Description>
    """
    param1: str
    param2: int = 5000
    # TODO(@<team>): Add more fields as per ADR-XXXX (Issue #XXX)


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================

class ComponentName:
    """
    <Detailed component description - 2-3 lines>

    Purpose:
        <What does this component do?>

    Responsibilities:
        1. <Primary responsibility>
        2. <Secondary responsibility>
        3. <Error handling responsibility>

    Lifecycle:
        INIT → ACTIVE → [DEGRADED] → TERMINATED

    Thread Safety: <Yes/No/Conditional>
    Async Safe: <Yes/No/Partial>

    Cognitive Trace:
        - Propagates cognitive_trace_id to downstream components
        - Required for: <method names>

    Performance Budget (P95):
        - Method1: <Xms latency>
        - Memory: <XMB max>
        - CPU: <X% target>

    Examples:
        >>> config = ComponentConfig(param1='value')
        >>> component = ComponentName(config)
        >>> result = await component.core_method('input')
        >>> await component.shutdown()

    References:
        - ADR-XXXX: <Decision title>
        - ADR-XXXX: <Related decision>
        - Diagram: architecture_diagrams/k1/<diagram>.mmd
        - Connects to: <UpstreamComponent>, <DownstreamComponent>
    """

    def __init__(self, config: ComponentConfig) -> None:
        """
        Initialize <Component>.

        Args:
            config: Configuration object with parameters

        Raises:
            ValueError: If configuration is invalid
            TypeError: If config type is incorrect

        Side Effects:
            - Initializes internal state
            - <Other side effects>

        ADR: ADR-XXXX (Initialization strategy)
        Assigned to: Issue #XXX
        """
        # TODO(@<team>): Implement initialization (ADR-XXXX)
        # 1. Validate config
        # 2. Initialize state machine
        # 3. Setup metrics exporters
        # 4. Register with parent component
        self.config = config
        self.state = ComponentState.INIT
        self._logger = logger
        pass

    async def initialize(self) -> None:
        """
        Async initialization phase (called after __init__).

        This method performs async setup that cannot be done in __init__.

        Raises:
            RuntimeError: If initialization fails
            ConnectionError: If cannot connect to dependencies

        Lifecycle:
            Called after __init__, before component becomes active

        ADR: ADR-XXXX
        Assigned to: Issue #XXX
        """
        # TODO(@<team>): Implement async initialization (ADR-XXXX)
        # 1. Connect to upstream components
        # 2. Load configuration from K0 or files
        # 3. Start background tasks
        # 4. Register with service registry
        self.state = ComponentState.ACTIVE
        pass

    async def core_method(
        self,
        param: str,
        cognitive_trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        <Core method description - what does it do?>

        This is the primary public method for <component>.

        Args:
            param: <Parameter description>
            cognitive_trace_id: Trace ID for observability (required for production)

        Returns:
            Dict with keys:
                - 'status': 'success' | 'error' | 'timeout'
                - 'result': <Result object or None>
                - 'metadata': Execution metadata

        Raises:
            ValueError: If param is invalid
            TimeoutError: If operation exceeds budget
            RuntimeError: If component is not ACTIVE

        Performance:
            - Target: <Xms P95>
            - Max memory: <XMB>
            - Connections: <N concurrent max>

        Observability:
            - Metrics: k1_<component>_<method>_duration_ms (P50/P95/P99)
            - Traces: Span name: <component>.<method>
            - Logs: INFO: <method> started, completed or ERROR: <method> failed

        Cognitive Trace:
            - Accepts cognitive_trace_id from caller
            - Propagates to downstream components
            - Logs include trace_id

        ADR: ADR-XXXX
        Assigned to: Issue #XXX
        Depends on: <Other methods/components>
        """
        # TODO(@<team>): Implement core_method (ADR-XXXX)
        # 1. Validate inputs
        # 2. Check component state
        # 3. Create trace span with cognitive_trace_id
        # 4. Acquire locks/semaphores
        # 5. Execute core logic
        # 6. Handle errors with fallback
        # 7. Record metrics (duration, status)
        # 8. Return result
        # Performance target: <Xms P95>
        logger.info(f'core_method called with trace_id={cognitive_trace_id}')
        pass

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method performs cleanup and state transitions.

        Lifecycle:
            - Stops accepting new work
            - Waits for in-flight operations (timeout: 10s)
            - Closes connections
            - Finalizes metrics

        Guarantees:
            - No data loss
            - Graceful degradation

        ADR: ADR-XXXX
        Assigned to: Issue #XXX
        """
        # TODO(@<team>): Implement shutdown (ADR-XXXX)
        # 1. Set state to TERMINATED
        # 2. Stop accepting new work
        # 3. Wait for in-flight work (with timeout)
        # 4. Close connections
        # 5. Flush metrics
        self.state = ComponentState.TERMINATED
        pass

    # =========================================================================
    # PRIVATE METHODS (Implementation Details)
    # =========================================================================

    def _validate_config(self, config: ComponentConfig) -> bool:
        """
        Validate configuration object.

        Args:
            config: Configuration to validate

        Returns:
            True if valid, False otherwise

        Raises:
            ValueError: If configuration is invalid

        ADR: ADR-XXXX
        Assigned to: Issue #XXX
        """
        # TODO(@<team>): Implement validation (ADR-XXXX)
        pass

    async def _execute_with_retry(
        self,
        operation: Callable[[], Awaitable[Any]],
        max_retries: int = 3,
        backoff_factor: float = 1.5,
    ) -> Any:
        """
        Execute operation with exponential backoff retry logic.

        Args:
            operation: Async function to execute
            max_retries: Maximum number of retries
            backoff_factor: Exponential backoff multiplier

        Returns:
            Result of operation

        Raises:
            <OperationError>: If all retries fail

        Performance:
            - Adds: <Xms per retry> latency

        ADR: ADR-XXXX (Retry strategy)
        Assigned to: Issue #XXX
        """
        # TODO(@<team>): Implement retry logic (ADR-XXXX)
        # 1. Attempt operation
        # 2. On failure, wait with exponential backoff
        # 3. Retry up to max_retries times
        # 4. Log each attempt
        # 5. Return result or raise error
        pass


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================

def helper_function(param: str) -> Any:
    """
    <Helper function description>

    Args:
        param: <Description>

    Returns:
        <Description>

    Raises:
        ValueError: <When>

    ADR: ADR-XXXX
    Assigned to: Issue #XXX
    """
    # TODO(@<team>): Implement helper (ADR-XXXX)
    pass


async def async_helper_function(param: str) -> Any:
    """
    <Async helper function description>

    Args:
        param: <Description>

    Returns:
        <Description>

    ADR: ADR-XXXX
    Assigned to: Issue #XXX
    """
    # TODO(@<team>): Implement async helper (ADR-XXXX)
    pass


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    'ComponentName',
    'ComponentState',
    'ComponentConfig',
    'helper_function',
]

# Module initialization hook (optional)
async def initialize_module() -> ComponentName:
    """
    Initialize module with default configuration.

    Returns:
        Initialized component instance

    ADR: ADR-XXXX
    """
    # TODO(@<team>): Implement module initialization (ADR-XXXX)
    pass


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_<component>_<method>_duration_ms (histogram: P50/P95/P99)
#   - k1_<component>_<method>_calls_total (counter: success/error/timeout)
#   - k1_<component>_<resource>_current (gauge: current usage)
#
# Traces to generate:
#   - Span name: <component>.<method>
#   - Attributes: cognitive_trace_id, params (sanitized), status
#   - Links to: upstream component spans
#
# Logs to emit:
#   - Level: INFO (normal), WARNING (degradation), ERROR (failures)
#   - Fields: component, method, trace_id, status, duration_ms, error
#
# =============================================================================

# =============================================================================
# COGNITIVE TRACE PROPAGATION
# =============================================================================
# All async methods must:
#   1. Accept cognitive_trace_id parameter
#   2. Create trace span with this ID
#   3. Pass ID to downstream components
#   4. Include ID in all log statements
#
# This enables end-to-end request tracing across K1 layers.
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/test_<component>.py
#   - Contract validation tests
#   - Performance budget tests (ensure <Xms P95)
#   - Error handling tests
#   - Shutdown graceful tests
#
# No simulation code allowed:
#   - No asyncio.sleep() for testing timeouts
#   - Use real components or WARD fixtures
#   - Integration tests > unit tests
#
# =============================================================================
```

---

## Milestone Overview

### Summary Table

| # | Milestone | Component Family | Files | Priority | ADRs | Assigned To |
|----|-----------|------------------|-------|----------|------|------------|
| 1 | Bridge (K0 Comm) | bridge_k0 | 10 | P0 | ADR-0001a, 0001f, 0022, 0023, 0025 | @infrastructure-team |
| 2 | Event Bus | event_bus | 3 | P0 | ADR-0004a | @infrastructure-team |
| 3 | Serialization | serialization | 8 | P0 | ADR-0011, 0011c, 0011d | @infrastructure-team |
| 4 | Circuit Breaker | resilience | 13 | P1 | ADR-0009, 0009a, 0009b, 0009c | @resilience-team |
| 5 | Multi-Tier Storage | storage | 8 | P1 | ADR-0020, 0020a, 0020b, 0020c | @storage-team |
| 6 | Thermal Management | thermal | 5 | M1 | ADR-0026, 0026a, 0026c | @ml-platform-team |
| 7 | Model Placement | placement | 5 | M1 | ADR-0027 | @ml-platform-team |
| 8 | Backpressure | backpressure | 6 | M1 | ADR-0061, 0061a | @ml-platform-team |
| 9 | Redis Caching | resilience/redis | 2 | P1 | ADR-0009 | @resilience-team |
| 10 | Rate Limiting | rate_limiting | 2 | P2 | ADR-TBD | @platform-team |
| 11 | Task Scheduling | scheduler | 2 | P2 | ADR-TBD | @platform-team |
| 12 | Admission Control | admission | 2 | P2 | ADR-TBD | @platform-team |
| 13 | Module System | l5_infrastructure | 2 | M2 | ADR-TBD | @platform-team |
| 14 | Extensions Framework | extensions | 11 | M2 | ADR-TBD | @platform-team |

**Total:** 60+ files, 14+ ADRs, 4 teams

---

## Milestone 1: Bridge (K0 Communication) - CORRECTED PER ADR-0001f

### 📋 Overview

**Purpose:** HTTP/2 bidirectional communication bridge connecting K1 to K0 memory kernel
**Priority:** P0 (Critical Path)
**Status:** 🚧 STUB - NEEDS_IMPLEMENTATION
**Files:** 11 Python modules
**ADRs:** ADR-0001a, ADR-0001f, ADR-0022
**Assigned To:** @infrastructure-team

**Key Features:**

- Dual-protocol support (JSON + FlatBuffers)
- K1 calls K0's 4 external ports (Command, Query, SSE, Observability)
- K0 P01 handles multi-store retrieval (K1 sends request only)
- 250ms batch window for K0 writes (K1 batching utility)
- Circuit breaker for K0 unavailability (3 failures → 60s recovery)
- Zstd compression for payloads >4KB
- HTTP/2 multiplexing with TLS 1.3

**CRITICAL ARCHITECTURAL BOUNDARY (ADR-0001f):**
- ❌ K1 does NOT implement lanes or multi-store retrieval (those are K0 P01 Pipeline)
- ✅ K1 sends requests to K0 Query Port, K0 handles lane routing and retrieval internally
- ✅ K1 implements batching, circuit breaking, compression (infrastructure utilities)

---

### 🎯 Epic 1.1: HTTP/2 Client Infrastructure

**Purpose:** Core HTTP/2 client for K0 communication
**Files:** 3
**Status:** 🚧 STUB

#### Issue 1.1.1: command_client.py

**File Path:** `k1/bridge_k0/command_client.py`

**Description:**
HTTP/2 client for executing commands against K0 Command Port (P02 MemoryWrite). Handles command serialization, response tracking, and receipt management.

**Responsibilities:**

1. Execute HTTP/2 requests to K0 Command Port
2. Marshal SessionState deltas to FlatBuffers or JSON
3. Track command receipts (via receipt_id)
4. Handle connection pooling and multiplexing
5. Implement exponential backoff on failures

**Dependencies:**

```yaml
Internal:
  - k1.bridge_k0.protocol.ProtocolNegotiator
  - k1.bridge_k0.http2_client.HTTP2Connection
  - k1.l5_infrastructure.serialization.Serializer

External:
  - aiohttp (HTTP/2 client)
  - asyncio (async runtime)
```

**Connects To:**

```yaml
Upstream:
  - k1.l2_orchestration.sessions.SessionManager
  - k1.l3_execution.orchestrator.Orchestrator

Downstream:
  - K0 Command Port (HTTP POST /k0/command)
  - k1.l5_infrastructure.event_bus.EventBus (receipt events)
```

**Performance Budget:**

```yaml
Latency:
  - Command send: <5ms P95
  - Receipt wait: <100ms P95
  - Connection setup: <50ms P95

Memory:
  - Max pending commands: 1000
  - Max buffer: 5MB
  - Per-connection: <100KB

Throughput:
  - Commands/sec: 100
  - Concurrent multiplexed streams: 100
```

**Observability:**

```yaml
Metrics:
  - k1_k0_bridge_commands_total{status, type}
  - k1_k0_bridge_command_latency_ms{p50, p95, p99}
  - k1_k0_bridge_pending_commands{gauge}

Traces:
  - Span: k0_bridge.command_send
  - Attributes: command_type, receipt_id, cognitive_trace_id

Logs:
  - INFO: command sent (receipt_id, type)
  - WARNING: command timeout
  - ERROR: command failed (reason, retry_count)
```

**ADR References:**

- ADR-0001a: Dual Protocol (JSON/FlatBuffers)
- ADR-0022: Batching Strategy (250ms window, 64KB, 100 messages)
- ADR-0022b: Receipt Tracking

**Open Questions:**

1. How to handle K0 unavailability? (Circuit breaker, local WAL?)
2. Should we add compression for batch >1KB?
3. How to version protocol for future changes?

**Assigned To:** Issue #L5-1.1.1

---

#### Issue 1.1.2: http2_client.py

**File Path:** `k1/bridge_k0/http2_client.py`

**Description:**
Low-level HTTP/2 connection management with persistent connections, multiplexing, and TLS support.

**Responsibilities:**

1. Manage persistent HTTP/2 connections to K0
2. Implement connection pooling (per target)
3. Handle stream multiplexing (100 concurrent streams)
4. Manage TLS 1.3 with mutual authentication
5. Implement connection keepalive and graceful shutdown

**Dependencies:**

```yaml
Internal:
  - None (lowest-level HTTP transport)

External:
  - aiohttp (HTTP/2 support)
  - asyncio (async runtime)
  - ssl (TLS certificates)
```

**Performance Budget:**

```yaml
Latency:
  - Connection setup: <50ms P95
  - Request send: <1ms P95
  - Response receive: <1ms P95

Memory:
  - Per connection: <100KB
  - Connection pool: <1MB (10 connections)
  - Multiplexing overhead: <50KB per stream

Connections:
  - Max per pool: 10
  - Max concurrent streams: 100
```

**ADR References:**

- ADR-0001: K0 Bridge Architecture
- ADR-0001b: TLS/mTLS Configuration

**Assigned To:** Issue #L5-1.1.2

---

#### Issue 1.1.3: protocol.py

**File Path:** `k1/bridge_k0/protocol.py`

**Description:**
Protocol negotiation and format switching between JSON and FlatBuffers. Detects K0 capabilities and uses most optimal format.

**Responsibilities:**

1. Detect K0 FlatBuffers capability (via OPTIONS request)
2. Choose format based on capability and payload size
3. Marshal objects to/from JSON
4. Marshal objects to/from FlatBuffers
5. Handle version negotiation for schema evolution

**Dependencies:**

```yaml
Internal:
  - k1.l5_infrastructure.serialization.Serializer
  - k1.l5_infrastructure.serialization.Deserializer

External:
  - json (JSON encoding)
  - flatbuffers (FlatBuffers library)
```

**Format Decision Logic:**

```
IF payload_size < 1KB:
  PREFER: JSON (overhead negligible)
ELSE IF K0_supports_flatbuffers:
  PREFER: FlatBuffers (150× faster, 3× smaller)
ELSE:
  FALLBACK: JSON (always works)
```

**Performance Budget:**

```yaml
Latency:
  - Format detection: <10ms P95
  - Format negotiation: <50ms P95 (once per session)
  - JSON serialization: <10ms P95 (1KB payload)
  - FlatBuffers serialization: <1ms P95 (1KB payload)
```

**ADR References:**

- ADR-0001a: Dual Protocol Support
- ADR-0011: FlatBuffers Serialization
- ADR-0013: Schema Evolution and Versioning

**Assigned To:** Issue #L5-1.1.3

---

### 🎯 Epic 1.2: Port Interfaces

**Purpose:** Implement K0's 4 external ports
**Files:** 4
**Status:** 🚧 STUB

#### Issue 1.2.1: ports/command_port.py

**File Path:** `k1/bridge_k0/ports/command_port.py`

**Description:**
Adapter for K0 Command Port (P02 MemoryWrite). Sends SessionState deltas and receives receipts.

**Endpoint:** `POST /k0/command`

**Payload:** FlatBuffers or JSON MemoryWrite message

**Response:** Receipt with receipt_id, timestamp, status

**Dependencies:**

```yaml
Internal:
  - k1.bridge_k0.command_client.CommandClient
  - k1.l5_infrastructure.serialization.*
```

**Request Format:**

```python
{
  "command_type": "MEMORY_WRITE",
  "session_id": "sess_123",
  "deltas": [
    {
      "field_path": "turn[0].assistant_response.text",
      "value": "Hello, user!",
      "timestamp": 1699000000000,
      "privacy_band": "GREEN"
    }
  ]
}
```

**Response Format:**

```python
{
  "receipt_id": "rcpt_456",
  "status": "SUCCESS",
  "timestamp": 1699000000050
}
```

**ADR References:**

- ADR-0001a: Dual Protocol
- ADR-0022: Batching

**Assigned To:** Issue #L5-1.2.1

---

#### Issue 1.2.2: ports/query_port.py

**File Path:** `k1/bridge_k0/ports/query_port.py`

**Description:**
Adapter for K0 Query Port (P01 RecallQuery). Retrieves context from multiple stores (FTS, Vector, KG, Episodic).

**Endpoint:** `POST /k0/query`

**Payload:** RecallQuery with query text, modifiers, lane selection

**Response:** MMR-fused results from multiple stores

**Dependencies:**

```yaml
Internal:
  - k1.bridge_k0.lanes.Lane
  - k1.bridge_k0.retrieval.MultiStoreRetrieval
```

**Request Format:**

```python
{
  "query": "What did I say about X?",
  "lane": "SMART",  # or "FAST"
  "privacy_band": "GREEN",
  "stores": ["FTS", "VECTOR", "KG", "EPISODIC"],
  "max_results": 10,
  "mmr_diversity": 0.5
}
```

**Response Format:**

```python
{
  "results": [
    {
      "rank": 1,
      "store": "FTS",
      "text": "...",
      "score": 0.92,
      "source": "turn[0].user_input"
    }
  ],
  "query_latency_ms": 45,
  "stores_queried": ["FTS", "VECTOR", "KG"]
}
```

**ADR References:**

- ADR-0001f: Multi-Store Retrieval
- ADR-0051: Maximal Marginal Relevance (MMR)

**Assigned To:** Issue #L5-1.2.2

---

#### Issue 1.2.3: ports/sse_port.py

**File Path:** `k1/bridge_k0/ports/sse_port.py`

**Description:**
Server-Sent Events port for K0 → K1 event notifications (e.g., consolidation complete).

**Endpoint:** `GET /k0/sse/stream`

**Events:** consolidation_complete, health_alert, quota_exceeded

**Dependencies:**

```yaml
Internal:
  - k1.l5_infrastructure.event_bus.EventBus
  - asyncio (stream handling)
```

**Event Format:**

```
data: {"event": "consolidation_complete", "session_id": "sess_123", "timestamp": 1699000000000}
```

**ADR References:**

- ADR-0004a: Event Bus Architecture

**Assigned To:** Issue #L5-1.2.3

---

#### Issue 1.2.4: ports/observability_port.py

**File Path:** `k1/bridge_k0/ports/observability_port.py`

**Description:**
Observability port for metrics export. Queries Prometheus metrics from K0.

**Endpoint:** `GET /k0/metrics`

**Format:** Prometheus text format

**Metrics:** k0_*and k1_* metrics (shared stack)

**ADR References:**

- ADR-0002d: Observability

**Assigned To:** Issue #L5-1.2.4

---

### 🎯 Epic 1.3: K1 Resilience & Optimization Utilities

**Purpose:** K1-side batching, circuit breaking, and compression utilities
**Files:** 3
**Status:** 🚧 STUB
**CRITICAL NOTE:** Per ADR-0001f, K1 does NOT implement lanes or multi-store retrieval - those are K0 P01 Pipeline responsibilities. K1 only sends requests to K0 Query Port.

#### Issue 1.3.1: batch_client.py

**File Path:** `k1/bridge_k0/batch_client.py`

**Description:**
Batches SessionState deltas to reduce K0 WAL write overhead. Accumulates deltas and flushes on triggers (250ms/64KB/100 messages).

**Responsibilities:**

1. Accumulate SessionState deltas from K1 agents/orchestrator
2. Trigger flush on: 250ms timeout OR 64KB size OR 100 message count
3. Send batched MemoryWrite commands to K0 Command Port (P02)
4. Track receipts and handle delivery failures (PENDING → COMMITTED)
5. Bounded queue (1000 pending receipts max, 5MB buffer)

**Dependencies:**

```yaml
Internal:
  - k1.bridge_k0.command_client.CommandClient
  - k1.bridge_k0.protocol.ProtocolNegotiator
  - k1.l5_infrastructure.event_bus.EventBus

External:
  - asyncio (async runtime)
  - typing (type hints)
```

**Batching Strategy:**

```yaml
Triggers:
  - Time: 250ms since last flush (P1 latency SLA)
  - Size: Batch reaches 64KB (P2 memory bound)
  - Count: 100 deltas accumulated (P2 throughput)

Bounds:
  - Max pending receipts: 1000
  - Max buffer: 5MB total
  - Prevents OOM during K0 unavailability
```

**Performance Budget:**

```yaml
Latency:
  - Delta accumulation: <1ms P95
  - Flush latency: <250ms P95
  - Receipt latency: <100ms P95

Throughput:
  - Deltas per second: 400 (100 deltas * 4 flushes/sec)
  - Batch size average: 16KB

Memory:
  - Pending buffer: <5MB (1000 * 5KB avg)
```

**Observability:**

```yaml
Metrics:
  - k1_k0_bridge_batch_accumulation_size{gauge}
  - k1_k0_bridge_batch_flush_latency_ms{trigger, p50, p95, p99}
  - k1_k0_bridge_batch_flushes_total{trigger}

Traces:
  - Span: k0_bridge.batch_client.flush
  - Attributes: batch_id, delta_count, size_bytes, trigger

Logs:
  - INFO: batch flushed (batch_id, msg_count, size, trigger)
  - WARNING: buffer full (current_size, max_size)
  - ERROR: receipt timeout (batch_id, timeout_ms)
```

**ADR References:**

- ADR-0022: Batching Strategy (250ms window, 64KB, 100 messages)
- ADR-0022b: Receipt Tracking and Delivery Confirmation

**Assigned To:** Issue #L5-1.3.1

---

#### Issue 1.3.2: circuit_breaker.py

**File Path:** `k1/bridge_k0/circuit_breaker.py`

**Description:**
Circuit breaker for K0 unavailability protection. Opens circuit after 3 consecutive failures, waits 60s recovery timeout, then tests with health check in HALF_OPEN state.

**Responsibilities:**

1. Track K0 request failures (connection errors, timeouts, 5xx errors)
2. Open circuit after 3 consecutive failures (fail fast)
3. Wait 60s recovery timeout before testing HALF_OPEN
4. Perform health check in HALF_OPEN state
5. Close circuit on successful health check (resume normal operation)

**Dependencies:**

```yaml
Internal:
  - k1.l5_infrastructure.event_bus.EventBus

External:
  - asyncio (async runtime)
  - typing (type hints)
  - time (timestamps)
```

**State Machine:**

```
CLOSED: Normal operation
├─ (3 failures) → OPEN

OPEN: Fail fast (no requests allowed)
├─ (60s timeout) → HALF_OPEN

HALF_OPEN: Testing recovery (single health check)
├─ (health check success) → CLOSED
└─ (health check failure) → OPEN
```

**Performance Budget:**

```yaml
Latency:
  - State check overhead: <0.1ms P95
  - State transition: <1ms P95
  - Recovery health check: <50ms P95

Configuration:
  - failure_threshold: 3 consecutive failures
  - recovery_timeout_ms: 60000 (60 seconds)
  - health_check_interval_ms: 5000 (5 seconds in HALF_OPEN)
```

**Observability:**

```yaml
Metrics:
  - k1_k0_bridge_circuit_breaker_state{gauge} (0=closed, 1=open, 2=half_open)
  - k1_k0_bridge_circuit_breaker_failures_total{counter}
  - k1_k0_bridge_circuit_breaker_trips_total{counter}

Traces:
  - Span: k0_bridge.circuit_breaker.trip
  - Span: k0_bridge.circuit_breaker.recover

Logs:
  - WARNING: circuit opened (consecutive_failures, total_trips)
  - INFO: circuit closed (recovery successful, total_recoveries)
  - ERROR: recovery failed (health_check_result)
```

**ADR References:**

- ADR-0023: Circuit Breaker Pattern (3 failures → open 60s → half-open)
- ADR-0024: Graceful Degradation Strategies

**Assigned To:** Issue #L5-1.3.2

---

#### Issue 1.3.3: compression.py

**File Path:** `k1/bridge_k0/compression.py`

**Description:**
Compression utilities for large payloads using Zstd. Compresses payloads >4KB with Zstd level 3 for optimal speed/ratio tradeoff.

**Responsibilities:**

1. Compress payloads >4KB with Zstd level 3
2. Decompress Zstd payloads from K0
3. Calculate compression ratios for observability
4. Emit compression metrics and traces
5. Skip compression for <4KB payloads (overhead exceeds benefit)

**Dependencies:**

```yaml
External:
  - zstandard (Zstd compression library)
  - typing (type hints)
```

**Compression Strategy:**

```yaml
Decision Logic:
  - IF payload_size < 4KB: NO compression (overhead too high)
  - IF payload_size >= 4KB AND <= 10MB: Zstd level 3
  - IF payload_size > 10MB: Skip (OOM risk)

Algorithm:
  - Zstandard level 3 (balanced speed/ratio)
  - Compression ratio: ~3:1 for JSON payloads
  - Compression latency: <10ms for 64KB
```

**Performance Budget:**

```yaml
Latency:
  - Compression: <10ms P95 for 64KB
  - Decompression: <5ms P95 for 64KB

Compression Ratio:
  - JSON payloads: >3:1 ratio
  - Binary payloads: >2:1 ratio

Throughput:
  - Compression: >10MB/sec
  - Decompression: >20MB/sec
```

**Observability:**

```yaml
Metrics:
  - k1_k0_bridge_compression_latency_ms{operation, p50, p95, p99}
  - k1_k0_bridge_compression_ratio{histogram}
  - k1_k0_bridge_compression_bytes_total{operation, counter}

Traces:
  - Span: k0_bridge.compression.compress
  - Span: k0_bridge.compression.decompress

Logs:
  - DEBUG: compression stats (original_size, compressed_size, ratio, latency)
  - WARNING: compression error (reason)
```

**ADR References:**

- ADR-0025: Compression Strategy (Zstd level 3 for >4KB payloads)
- ADR-0001a: K0 Bridge Communication Protocol

**Assigned To:** Issue #L5-1.3.3

---

### 🎯 Epic 1.4: Saga & WAL Integration

**Purpose:** Persistence patterns for reliability
**Files:** 4
**Status:** 🚧 STUB

#### Issue 1.4.1: wal_writer.py

**File Path:** `k1/bridge_k0/wal_writer.py`

**Description:**
Write-Ahead Logger for K1 orchestration decisions. Logs to K0's PLAN_COMMITTED topic before executing actions.

**Responsibilities:**

1. Log orchestration decisions to K0 before execution
2. Ensure crash recovery via replay
3. Topic: PLAN_COMMITTED
4. Format: Serialized Plan objects with timestamps

**ADR References:**

- ADR-0022: WAL Strategy
- ADR-0037: Saga Pattern for Orchestration

**Assigned To:** Issue #L5-1.4.1

---

#### Issue 1.4.2: state_delta_emitter.py

**File Path:** `k1/bridge_k0/state_delta_emitter.py`

**Description:**
Emits SessionState field_path deltas to K0 for incremental updates.

**Responsibilities:**

1. Track field-level changes in SessionState
2. Emit deltas (not full state)
3. Include field_path, old_value, new_value, timestamp
4. Reduce network traffic vs full state transmission

**ADR References:**

- ADR-0001a: Delta-Based Updates

**Assigned To:** Issue #L5-1.4.2

---

#### Issue 1.4.3: saga_logger.py

**File Path:** `k1/bridge_k0/saga_logger.py`

**Description:**
Logs saga compensations for multi-step operations with rollback capability.

**Responsibilities:**

1. Log compensation actions
2. Enable rollback on failure
3. Track saga state (RUNNING, COMPENSATING, COMPLETED, FAILED)

**ADR References:**

- ADR-0037: Saga Pattern

**Assigned To:** Issue #L5-1.4.3

---

#### Issue 1.4.4: saga_persistence.py

**File Path:** `k1/bridge_k0/saga_persistence.py`

**Description:**
Persists saga logs to K0 for durability and recovery.

**Responsibilities:**

1. Store saga compensation logs to K0
2. Enable saga state recovery on crash
3. Query saga status from K0

**ADR References:**

- ADR-0037: Saga Pattern
- ADR-0022: Persistence Strategy

**Assigned To:** Issue #L5-1.4.4

---

### 📊 Summary

**Milestone 1: Bridge (K0 Communication) - CORRECTED PER ADR-0001f**

| Epic | Files | Status | Assigned |
|------|-------|--------|----------|
| 1.1: HTTP/2 Client | 3 | 🚧 STUB | @infrastructure-team |
| 1.2: Port Interfaces | 4 | 🚧 STUB | @infrastructure-team |
| 1.3: K1 Utilities (NOT lanes/retrieval) | 3 | 🚧 STUB | @infrastructure-team |
| 1.4: Saga & WAL | 4 | 🚧 STUB | @infrastructure-team |
| **Total** | **14** | **🚧 STUB** | **@infrastructure-team** |

**CRITICAL CORRECTION:** Original planning doc incorrectly specified Epic 1.3 should include `lanes.py` and `retrieval.py`. Per ADR-0001f, K1 does NOT implement lanes or multi-store retrieval - those are K0 P01 Pipeline responsibilities. Epic 1.3 now correctly specifies K1 utilities: batch_client.py, circuit_breaker.py, compression.py.

---

## Milestone 2: Event Bus

### 📋 Overview

**Purpose:** Layer 1-2 asynchronous communication using pub/sub pattern with zero-copy optimization
**Priority:** P0 (Critical Path)
**Status:** 🚧 STUB - NEEDS_IMPLEMENTATION
**Files:** 3 Python modules
**ADRs:** ADR-0004a
**Assigned To:** @infrastructure-team

**Key Features:**

- Async delivery (non-blocking)
- Zero-copy ring buffer (1000 events max)
- 5 modalities: audio, video, text, touch, GPS
- <5ms P95 delivery latency
- Topic-based filtering
- FIFO ordering per topic
- `cognitive_trace_id` propagation

**Use Cases:**

1. **Intent Detection** → Orchestrator routing
2. **User Input** → Planner request handling
3. **Voice Commands** → Voice pipeline triggering
4. **Barge-In Events** → Interruption handling
5. **Consolidation Complete** → State update notifications

**Performance Targets:**

```yaml
Latency:
  - Publish → Subscriber delivery: <5ms P95
  - Topic filtering: <1ms P95

Throughput:
  - Events/sec: 100 (typical)
  - Burst capacity: 1000 events

Memory:
  - Ring buffer: 1MB (1000 × 1KB events)
  - Per-subscriber: <10KB
  - Total overhead: <5MB
```

---

### 🎯 Epic 2.1: Core Pub/Sub System

**Purpose:** Core event bus implementation with topic-based routing
**Files:** 2
**Status:** 🚧 STUB

#### Issue 2.1.1: event_bus.py

**File Path:** `k1/l5_infrastructure/event_bus/event_bus.py`

**Description:**
Core pub/sub event bus implementation for Layer 1-2 async communication. Provides topic-based publish/subscribe with zero-copy optimization and FIFO ordering.

**Responsibilities:**

1. Manage subscriber registrations per topic
2. Publish events to registered subscribers
3. Maintain zero-copy ring buffer (1000 events)
4. Enforce FIFO ordering per topic
5. Track event delivery status
6. Provide admin operations (flush, stats, monitoring)

**Design:**

```
Publisher (L1)
    ↓
EventBus (L5)
    ├→ Topic Filter
    ├→ Ring Buffer (circular, 1000 capacity)
    ├→ Async Delivery Queue
    └→ Subscriber Registry
        ├→ Orchestrator (L2)
        ├→ Planner (L2)
        └→ Custom Subscribers
```

**Event Types (Topics):**

```python
class EventTopic(Enum):
    # Intent & Commands
    INTENT_DETECTED = "intent.detected"           # User intent classification
    USER_INPUT = "user.input"                     # User message/action
    VOICE_COMMAND = "voice.command"               # Voice-based command

    # Audio Events
    AUDIO_STARTED = "audio.started"               # Audio stream began
    AUDIO_ENDED = "audio.ended"                   # Audio stream ended
    BARGE_IN = "audio.barge_in"                   # User interruption

    # System Events
    CONSOLIDATION_COMPLETE = "system.consolidation_complete"  # K0 consolidation done
    SESSION_ENDED = "system.session_ended"        # Session termination
    QUOTA_EXCEEDED = "system.quota_exceeded"      # Usage quota hit
```

**Core Methods:**

```python
async def subscribe(
    self,
    topic: EventTopic,
    callback: Callable[[Event], Awaitable[None]],
    subscriber_id: str,
) -> None:
    """
    Register async callback for topic events.

    Args:
        topic: Event topic to subscribe to
        callback: Async function called on event (must be non-blocking)
        subscriber_id: Unique subscriber identifier

    Raises:
        ValueError: If callback not async or subscriber_id invalid

    Performance:
        - Registration overhead: <1ms

    ADR: ADR-0004a
    """
    # TODO(@infrastructure-team): Implement subscription management
    # 1. Validate callback is async
    # 2. Store (topic, callback, subscriber_id) mapping
    # 3. Create queue for this subscriber
    # 4. Start delivery task if first subscriber
    pass

async def publish(
    self,
    topic: EventTopic,
    event: Event,
    cognitive_trace_id: Optional[str] = None,
) -> None:
    """
    Publish event to all subscribers asynchronously.

    Args:
        topic: Topic to publish to
        event: Event object with payload
        cognitive_trace_id: Trace ID for observability

    Performance:
        - Publish latency: <1ms P95 (enqueue only)
        - Delivery latency: <5ms P95 (to all subscribers)

    Observability:
        - Metric: k1_event_bus_published_total{topic}
        - Trace: Span event_bus.publish
        - Log: INFO event published

    ADR: ADR-0004a
    """
    # TODO(@infrastructure-team): Implement publish logic
    # 1. Validate topic and event
    # 2. Create trace span with cognitive_trace_id
    # 3. Add event to ring buffer (circular queue)
    # 4. Enqueue delivery tasks for all subscribers (don't wait)
    # 5. Return immediately (fire-and-forget)
    # 6. Record metric
    pass

async def unsubscribe(
    self,
    topic: EventTopic,
    subscriber_id: str,
) -> None:
    """
    Unregister subscriber from topic.

    Args:
        topic: Topic to unsubscribe from
        subscriber_id: Subscriber identifier

    Performance:
        - Unregister overhead: <1ms

    ADR: ADR-0004a
    """
    # TODO(@infrastructure-team): Implement unsubscription
    pass

def get_stats(self) -> Dict[str, Any]:
    """
    Get event bus statistics (for monitoring).

    Returns:
        Dict with:
            - topics_active: Number of topics with subscribers
            - subscribers_total: Total subscriber count
            - events_published_total: Lifetime events
            - queue_depths: {topic: current_depth}
            - delivery_latencies: {topic: p95_ms}

    Performance:
        - Stats collection: <5ms

    Observability:
        - Metrics: k1_event_bus_queue_depth{topic}, k1_event_bus_subscribers{topic}

    ADR: ADR-0004a
    """
    # TODO(@infrastructure-team): Implement stats collection
    pass

async def shutdown(self) -> None:
    """
    Graceful shutdown - stop accepting events and flush queues.

    Guarantees:
        - In-flight events delivered (up to 10s timeout)
        - All queues flushed
        - Subscribers notified

    ADR: ADR-0004a
    """
    # TODO(@infrastructure-team): Implement graceful shutdown
    # 1. Stop accepting new events
    # 2. Flush all queues (with timeout)
    # 3. Wait for in-flight deliveries
    # 4. Close all subscriber connections
    pass
```

**Implementation Notes:**

```yaml
Ring Buffer Implementation:
  - Type: asyncio.Queue(maxsize=1000)
  - Overflow: Drop oldest events (not newest)
  - Thread-safe: Yes (asyncio)
  - Memory: ~1MB (1000 × 1KB avg event)

Subscriber Delivery:
  - Strategy: Fire-and-forget (non-blocking)
  - Timeout: 5s per subscriber callback
  - On timeout: Log WARNING, remove slow subscriber
  - Retry: No (drop and move to next)

Topic Filtering:
  - Dictionary: {topic → [subscribers]}
  - Lookup time: O(1)
  - Wildcard topics: Future enhancement (ADR-0004b)

Error Handling:
  - Bad topic: Raise ValueError
  - Bad callback: Raise TypeError
  - Delivery timeout: Log and drop
  - Queue overflow: Drop oldest events
```

**Performance Budget:**

```yaml
Publish Operation:
  - Latency: <1ms P95 (enqueue only, non-blocking)
  - Memory: <100 bytes per event (metadata)
  - CPU: <0.1ms per publish

Delivery Operation (per subscriber):
  - Latency: <5ms P95 (end-to-end)
  - Timeout: 5s per callback
  - Retry: No (fire-and-forget)

Ring Buffer:
  - Capacity: 1000 events
  - Memory: 1MB (1000 × 1KB)
  - Overflow: Drop oldest

Subscriber Scaling:
  - Max subscribers per topic: 100
  - Max topics: 50
  - Max concurrent deliveries: 1000
```

**Observability:**

```yaml
Metrics:
  - k1_event_bus_published_total{topic} - Total events published
  - k1_event_bus_delivered_total{topic, status} - Delivery count (success/timeout/error)
  - k1_event_bus_queue_depth{topic} - Current queue depth (target <10)
  - k1_event_bus_subscribers{topic} - Active subscriber count
  - k1_event_bus_delivery_latency_ms{topic} - P50/P95/P99 delivery latency

Traces:
  - Span: event_bus.publish
  - Attributes: topic, event_id, subscriber_count, cognitive_trace_id
  - Child spans: event_bus.deliver_to_subscriber (per subscriber)

Logs:
  - INFO: event published (topic, event_id, subscriber_count)
  - WARNING: subscriber timeout (topic, subscriber_id, timeout_ms)
  - WARNING: queue overflow (topic, dropped_count)
  - ERROR: delivery failed (topic, subscriber_id, error)
```

**ADR References:**

- ADR-0004a: Event Bus Architecture
- ADR-0004b: Wildcard Topics (Future)
- ADR-0004c: Event Persistence (Future)

**Related Components:**

- Upstream: L1 Input (audio_input.py, voice_intent.py)
- Downstream: L2 Orchestrator, L2 Planner, L3 Agents

**Connections:**

```
L1 Input Events
    ↓
event_bus.publish(IntentDetected)
    ↓
[Ring Buffer: 1000 events max]
    ↓
Async delivery to subscribers:
    ├→ Orchestrator.on_intent_detected()
    ├→ Planner.on_intent_detected()
    └→ Custom agent subscribers
```

**Assigned To:** Issue #L5-2.1.1

---

#### Issue 2.1.2: schemas.py

**File Path:** `k1/l5_infrastructure/event_bus/schemas.py`

**Description:**
Event payload schema definitions. Uses FlatBuffers for zero-copy and Pydantic for validation.

**Responsibilities:**

1. Define Event base class with common fields
2. Define specialized event types for each topic
3. Provide validation and serialization
4. Include `cognitive_trace_id` in all events
5. Support both FlatBuffers and JSON serialization

**Event Base Schema:**

```python
@dataclass
class Event:
    """
    Base event with common fields.

    All events inherit these fields:
        - event_id: Unique identifier (UUID4)
        - topic: EventTopic enum
        - timestamp_ms: Event creation time (milliseconds since epoch)
        - cognitive_trace_id: Trace ID for observability
        - privacy_band: GREEN/AMBER/RED classification
        - metadata: Optional dict for extra fields
    """
    event_id: str  # UUID4
    topic: EventTopic
    timestamp_ms: int
    cognitive_trace_id: str
    privacy_band: str  # "GREEN" | "AMBER" | "RED"
    metadata: Dict[str, Any] = None

    def to_flatbuffers(self) -> bytes:
        """Serialize to FlatBuffers binary format."""
        # TODO(@infrastructure-team): Implement FlatBuffers serialization
        pass

    def to_json(self) -> Dict[str, Any]:
        """Serialize to JSON dict."""
        # TODO(@infrastructure-team): Implement JSON serialization
        pass
```

**Specialized Event Types:**

```python
@dataclass
class IntentDetectedEvent(Event):
    """Intent detection result from NLU."""
    intent: str              # e.g., "weather_query", "set_reminder"
    confidence: float        # 0.0-1.0
    entities: Dict[str, Any] # Extracted entities
    turn_id: str            # Parent turn

@dataclass
class UserInputEvent(Event):
    """Raw user input (text, audio, etc)."""
    modality: str           # "text" | "audio" | "video" | "touch" | "gps"
    payload: bytes          # Raw input data
    session_id: str         # Parent session
    turn_id: str           # Parent turn

@dataclass
class VoiceCommandEvent(Event):
    """Voice command (from speech recognition)."""
    command: str            # Transcribed command
    confidence: float       # Recognition confidence
    audio_duration_ms: int # Audio length
    session_id: str

@dataclass
class BargeInEvent(Event):
    """User interruption event."""
    interruption_type: str  # "voice" | "button" | "gesture"
    interrupted_turn_id: str
    session_id: str
    timestamp_ms: int

@dataclass
class ConsolidationCompleteEvent(Event):
    """K0 consolidation completed."""
    session_id: str
    consolidated_turns: int
    consolidation_duration_ms: int

@dataclass
class SessionEndedEvent(Event):
    """Session termination."""
    session_id: str
    end_reason: str  # "user_logout" | "timeout" | "error"
    total_turns: int
```

**Validation:**

```python
def validate_event(event: Event) -> bool:
    """
    Validate event schema compliance.

    Args:
        event: Event to validate

    Returns:
        True if valid

    Raises:
        ValueError: If event invalid

    Checks:
        - Required fields present (event_id, topic, timestamp_ms)
        - cognitive_trace_id non-empty
        - privacy_band in (GREEN, AMBER, RED)
        - timestamp_ms is positive integer
        - Event-specific fields valid

    ADR: ADR-0004a
    """
    # TODO(@infrastructure-team): Implement validation
    # 1. Check base fields
    # 2. Check event-specific fields
    # 3. Validate field types
    # 4. Validate field ranges
    pass
```

**Serialization:**

```python
def serialize_event(event: Event, format: str = "flatbuffers") -> bytes:
    """
    Serialize event to bytes.

    Args:
        event: Event to serialize
        format: "flatbuffers" or "json"

    Returns:
        Serialized event bytes

    Performance:
        - FlatBuffers: <1ms P95
        - JSON: <10ms P95

    ADR: ADR-0011 (FlatBuffers)
    """
    # TODO(@infrastructure-team): Implement serialization
    pass

def deserialize_event(data: bytes, format: str = "flatbuffers") -> Event:
    """
    Deserialize bytes to event.

    Args:
        data: Serialized event bytes
        format: "flatbuffers" or "json"

    Returns:
        Deserialized event object

    Performance:
        - FlatBuffers: <0.1ms P95 (zero-copy)
        - JSON: <5ms P95

    ADR: ADR-0011 (FlatBuffers)
    """
    # TODO(@infrastructure-team): Implement deserialization
    pass
```

**ADR References:**

- ADR-0004a: Event Bus Architecture
- ADR-0011: FlatBuffers Serialization
- ADR-0013: Schema Versioning

**Assigned To:** Issue #L5-2.1.2

---

### 🎯 Epic 2.2: Subscriber Management

**Purpose:** Advanced subscriber lifecycle and management
**Files:** 1
**Status:** 🚧 STUB

#### Issue 2.2.1: subscribers.py

**File Path:** `k1/l5_infrastructure/event_bus/subscribers.py`

**Description:**
Advanced subscriber management with registration, lifecycle, and admin operations. Provides subscriber discovery and health monitoring.

**Responsibilities:**

1. Maintain subscriber registry
2. Track subscriber health and delivery stats
3. Provide subscriber discovery (find by topic/id)
4. Handle subscriber lifecycle (register → active → unregister)
5. Admin operations (list, pause, resume, remove slow subscribers)

**Subscriber Registry:**

```python
@dataclass
class SubscriberMetadata:
    """Metadata for a registered subscriber."""
    subscriber_id: str
    topics: List[EventTopic]          # Subscribed topics
    callback_fn: Callable             # Async callback
    registered_at: int                # Registration timestamp
    is_active: bool                   # Active/paused
    delivery_count: int               # Total deliveries
    success_count: int                # Successful deliveries
    timeout_count: int                # Delivery timeouts
    error_count: int                  # Delivery errors
    avg_latency_ms: float            # Average delivery latency
    max_latency_ms: float            # Max delivery latency
    last_delivery_at: int            # Last delivery timestamp
    status: str                       # "healthy" | "slow" | "failed"
```

**Core Methods:**

```python
async def register_subscriber(
    self,
    subscriber_id: str,
    topics: List[EventTopic],
    callback: Callable[[Event], Awaitable[None]],
) -> SubscriberMetadata:
    """
    Register new subscriber.

    Args:
        subscriber_id: Unique identifier
        topics: Topics to subscribe to
        callback: Async callback function

    Returns:
        SubscriberMetadata with registration details

    Raises:
        ValueError: If subscriber_id already exists
        TypeError: If callback not async

    Performance:
        - Registration: <1ms

    ADR: ADR-0004a
    """
    # TODO(@infrastructure-team): Implement registration
    pass

async def unregister_subscriber(
    self,
    subscriber_id: str,
) -> None:
    """
    Unregister subscriber from all topics.

    Args:
        subscriber_id: Subscriber to remove

    Performance:
        - Unregistration: <1ms

    ADR: ADR-0004a
    """
    # TODO(@infrastructure-team): Implement unregistration
    pass

def get_subscribers_by_topic(
    self,
    topic: EventTopic,
) -> List[SubscriberMetadata]:
    """
    Get all subscribers for a topic.

    Args:
        topic: Topic to query

    Returns:
        List of SubscriberMetadata objects

    Performance:
        - Lookup: O(n) where n = subscribers for topic (typically <100)

    ADR: ADR-0004a
    """
    # TODO(@infrastructure-team): Implement topic lookup
    pass

def get_subscriber_health(
    self,
    subscriber_id: str,
) -> Dict[str, Any]:
    """
    Get subscriber health status.

    Args:
        subscriber_id: Subscriber to check

    Returns:
        Dict with:
            - status: "healthy" | "slow" | "failed"
            - delivery_count: Total deliveries
            - success_rate: Percentage successful
            - avg_latency_ms: Average latency
            - last_delivery_at: Timestamp

    ADR: ADR-0004a
    """
    # TODO(@infrastructure-team): Implement health check
    pass

async def remove_slow_subscribers(
    self,
    timeout_threshold_ms: int = 5000,
) -> List[str]:
    """
    Remove subscribers exceeding timeout threshold.

    Args:
        timeout_threshold_ms: Timeout limit (default 5s)

    Returns:
        List of removed subscriber IDs

    Side effects:
        - Unsubscribes slow subscribers
        - Logs WARNING for each removal

    ADR: ADR-0004a
    """
    # TODO(@infrastructure-team): Implement slow subscriber removal
    pass
```

**Observability:**

```yaml
Metrics:
  - k1_event_bus_subscribers_total{topic} - Subscriber count per topic
  - k1_event_bus_subscriber_health{subscriber_id, status} - Health status
  - k1_event_bus_subscriber_delivery_rate{subscriber_id} - Success rate
  - k1_event_bus_subscriber_latency_ms{subscriber_id} - P50/P95/P99

Logs:
  - INFO: subscriber registered
  - WARNING: subscriber timeout
  - ERROR: subscriber removed (timeout/error)
```

**ADR References:**

- ADR-0004a: Event Bus Architecture

**Assigned To:** Issue #L5-2.2.1

---

### 📊 Summary

**Milestone 2: Event Bus**

| Epic | Files | Status | Assigned |
|------|-------|--------|----------|
| 2.1: Core Pub/Sub | 2 | 🚧 STUB | @infrastructure-team |
| 2.2: Subscriber Mgmt | 1 | 🚧 STUB | @infrastructure-team |
| **Total** | **3** | **🚧 STUB** | **@infrastructure-team** |

**Milestone 2 Dependencies:**

```
Upstream (Publishers):
  - k1.l1_input.audio_input
  - k1.l1_input.voice_intent
  - k1.l1_input.gesture_input

Downstream (Subscribers):
  - k1.l2_orchestration.orchestrator
  - k1.l2_orchestration.planner
  - k1.l3_execution.agent_fabric
```

**Integration Points:**

1. **L1 → Event Bus**: Input modalities publish events
2. **Event Bus → L2**: Orchestrator/Planner subscribe to events
3. **Event Bus → L3**: Agents receive event notifications
4. **Event Bus → K0**: Publish consolidation_complete events from K0 SSE

---



### 📋 Overview

**Purpose:** Zero-copy binary serialization using FlatBuffers for 150× performance improvement vs JSON
**Priority:** P0 (Critical Path)
**Status:** 🚧 STUB - NEEDS_IMPLEMENTATION
**Files:** 8 Python modules
**ADRs:** ADR-0011, ADR-0011c, ADR-0011d
**Assigned To:** @infrastructure-team

**Key Features:**

- Zero-copy deserialization
- 150× faster than JSON (1ms vs 10-50ms for 64KB)
- 3× smaller payload size (64KB FlatBuffers vs 192KB JSON)
- Type-safe schema validation
- Forward/backward compatible with optional fields
- SIMD alignment for audio frame vectorization

**Use Cases:**

1. **SessionState Persistence** → K0 MemoryWrite (64KB typical)
2. **Agent State Serialization** → Inter-layer communication
3. **Audio Frame Processing** → Real-time streaming
4. **Event Bus Messages** → High-throughput pub/sub
5. **Caching** → KV cache broker storage

**Performance Targets:**

```yaml
Serialization:
  - 64KB payload: <1ms P95
  - 8KB AgentState: <0.3ms P95
  - 2KB TaskAnnouncement: <0.1ms P95

Deserialization (zero-copy):
  - 64KB payload: <0.1ms P95
  - Field access: <0.05ms P95
  - Memory: <1KB overhead per buffer

Size Reduction:
  - JSON → FlatBuffers: 3× smaller
  - Before compression: 64KB FlatBuffers vs 192KB JSON
  - After zstd compression: 22KB (70% reduction)

Buffer Pool:
  - Hit rate target: >80%
  - 5 size classes: 256B, 1KB, 4KB, 16KB, 64KB
  - Speedup: 1.4× vs allocating new buffers
```

---

### 🎯 Epic 3.1: Core Serialization

**Purpose:** FlatBuffers serialization/deserialization core
**Files:** 2
**Status:** 🚧 STUB

#### Issue 3.1.1: serializer.py

**File Path:** `k1/l5_infrastructure/serialization/serializer.py`

**Description:**
Serializes Python objects to FlatBuffers binary format. Handles 76 schema types (SessionState, AgentState, TaskAnnouncement, etc.) with automatic builder management.

**Responsibilities:**

1. Convert Python objects → FlatBuffers builder
2. Support 76 schema types
3. Handle nested objects and repeated fields
4. Maintain thread-safe builder pool
5. Implement deterministic serialization (for testing)

**Core Methods:**

```python
class Serializer:
    """
    FlatBuffers serialization for K1 objects.

    Supports 76 schema types:
        - SessionState (64KB typical)
        - AgentState (8KB typical)
        - TaskAnnouncement (2KB typical)
        - Event types
        - Request/Response messages
    """

    def __init__(self, schema_registry: SchemaRegistry):
        """
        Initialize serializer with schema registry.

        Args:
            schema_registry: Registry of all 76 FlatBuffers schemas

        ADR: ADR-0011
        """
        # TODO(@infrastructure-team): Initialize serializer
        # 1. Load schema registry
        # 2. Create builder pool (thread-local)
        # 3. Validate schemas
        pass

    def serialize(
        self,
        obj: Any,
        schema_type: str,
        deterministic: bool = False,
    ) -> bytes:
        """
        Serialize Python object to FlatBuffers binary.

        Args:
            obj: Object to serialize (SessionState, AgentState, etc.)
            schema_type: Schema type name (e.g., "SessionState")
            deterministic: If True, ensure reproducible output (for testing)

        Returns:
            Binary FlatBuffers buffer

        Raises:
            ValueError: If object doesn't match schema
            KeyError: If schema_type not found

        Performance:
            - 64KB payload: <1ms P95
            - Memory: Builder + buffer

        Observability:
            - Metric: k1_flatbuffers_serialize_duration_ms{schema_type}
            - Trace: Span flatbuffers.serialize

        ADR: ADR-0011 (Core), ADR-0011c (Performance)
        """
        # TODO(@infrastructure-team): Implement serialization
        # 1. Validate object matches schema
        # 2. Get builder from pool (or create)
        # 3. Recursively build nested structures
        # 4. Handle repeated fields
        # 5. Call builder.Finish()
        # 6. Extract bytes
        # 7. Return builder to pool
        # 8. Record metric
        pass

    def serialize_batch(
        self,
        objects: List[Any],
        schema_type: str,
    ) -> List[bytes]:
        """
        Serialize multiple objects efficiently.

        Args:
            objects: List of objects
            schema_type: Schema type (all same)

        Returns:
            List of binary buffers

        Performance:
            - Batch reuses builder (faster than individual serializations)
            - 100 objects: <80ms P95 (vs 100ms individual)

        ADR: ADR-0011c (Optimization)
        """
        # TODO(@infrastructure-team): Implement batch serialization
        # 1. Create single builder
        # 2. Serialize each object
        # 3. Keep builder in pool for next batch
        pass
```

**Schema Registry:**

```python
class SchemaRegistry:
    """
    Registry of 76 FlatBuffers schemas used in K1.

    Schemas:
        - L1 Input: AudioFrame, TextInput, GestureInput
        - L2 Orchestration: Plan, AgentProposal, TaskAnnouncement
        - L3 Execution: AgentState, ToolCall, ToolResult
        - L4 Runtime: SessionState (76 fields)
        - L5 Infrastructure: Event, CircuitBreakerState, etc.
        - K0 Bridge: MemoryWrite, RecallQuery, ConsolidationComplete
    """

    def register_schema(
        self,
        schema_name: str,
        schema_class: Type,
        flatbuffers_def: str,
    ) -> None:
        """Register a schema with FlatBuffers definition."""
        # TODO(@infrastructure-team): Implement schema registration
        pass

    def get_schema(self, schema_name: str) -> Type:
        """Get schema class by name."""
        # TODO(@infrastructure-team): Implement schema lookup
        pass
```

**ADR References:**

- ADR-0011: FlatBuffers Serialization Core
- ADR-0011c: Performance Optimization
- ADR-0011d: Schema Evolution

**Assigned To:** Issue #L5-3.1.1

---

#### Issue 3.1.2: deserializer.py

**File Path:** `k1/l5_infrastructure/serialization/deserializer.py`

**Description:**
Zero-copy FlatBuffers deserialization. Enables direct buffer access without copying, keeping memory overhead minimal.

**Responsibilities:**

1. Deserialize FlatBuffers binary to Python objects
2. Support zero-copy field access (lazy evaluation)
3. Keep buffer alive for lifetime of object
4. Validate schema compatibility
5. Handle schema evolution (forward/backward compatibility)

**Core Methods:**

```python
class Deserializer:
    """
    Zero-copy FlatBuffers deserialization.

    Key Property: Field access does NOT copy data
        - Object.__dict__ contains references to buffer
        - Memory footprint: Object + references (typically <1KB)
        - Buffer lifecycle: Keep buffer alive while object is used
    """

    def deserialize(
        self,
        data: bytes,
        schema_type: str,
        keep_buffer_alive: bool = True,
    ) -> Any:
        """
        Deserialize FlatBuffers binary to Python object.

        Args:
            data: Binary FlatBuffers buffer
            schema_type: Expected schema type
            keep_buffer_alive: If True, keep buffer in memory (default: True)

        Returns:
            Python object (with lazy field access)

        Raises:
            ValueError: If buffer doesn't match schema
            struct.error: If buffer malformed

        Performance:
            - Deserialization time: <0.1ms P95
            - Memory: Buffer + object references (no copy)
            - Field access time: <0.05ms per field

        Observability:
            - Metric: k1_flatbuffers_deserialize_duration_ms{schema_type}

        ADR: ADR-0011 (Core), ADR-0011c (Performance)

        Lifecycle:
            - Keep buffer alive while object is used
            - Buffer can be freed when object is garbage collected
            - For long-lived objects, consider copying (trade-off)
        """
        # TODO(@infrastructure-team): Implement deserialization
        # 1. Validate buffer magic bytes
        # 2. Check schema compatibility
        # 3. Create object wrapper with buffer reference
        # 4. Setup lazy field accessors
        # 5. Return object (buffer stays alive)
        pass

    def get_field(
        self,
        obj: Any,
        field_name: str,
    ) -> Any:
        """
        Get field value from deserialized object (zero-copy).

        Args:
            obj: Deserialized object
            field_name: Field name to access

        Returns:
            Field value (extracted from buffer, no copy)

        Performance:
            - Latency: <0.05ms P95

        ADR: ADR-0011 (Zero-copy design)
        """
        # TODO(@infrastructure-team): Implement zero-copy field access
        # 1. Calculate offset from vtable
        # 2. Read value from buffer at offset
        # 3. No memory copy (direct buffer access)
        pass

    def deserialize_batch(
        self,
        buffers: List[bytes],
        schema_type: str,
    ) -> List[Any]:
        """
        Deserialize multiple buffers efficiently.

        Args:
            buffers: List of binary buffers
            schema_type: Schema type (all same)

        Returns:
            List of Python objects

        Performance:
            - 100 buffers: <8ms P95

        ADR: ADR-0011c (Optimization)
        """
        # TODO(@infrastructure-team): Implement batch deserialization
        pass
```

**Zero-Copy Design:**

```
Traditional JSON:
    JSON String (64KB)
        ↓ [Parse, allocate objects]
    Python Dict/Objects (192KB)
        ↓ [Field access]
    Value

FlatBuffers Zero-Copy:
    Binary Buffer (64KB) [KEEP IN MEMORY]
        ↓ [No parsing]
    Python Object Wrapper (1KB) [References into buffer]
        ↓ [Direct offset calculation]
    Value [Read from buffer at offset, no copy]
```

**ADR References:**

- ADR-0011: FlatBuffers Serialization
- ADR-0011c: Zero-Copy Performance
- ADR-0011d: Schema Evolution

**Assigned To:** Issue #L5-3.1.2

---

### 🎯 Epic 3.2: Memory Management

**Purpose:** Buffer pooling and memory optimization
**Files:** 2
**Status:** 🚧 STUB

#### Issue 3.2.1: buffer_pool.py

**File Path:** `k1/l5_infrastructure/serialization/buffer_pool.py`

**Description:**
Reusable buffer pool to avoid allocation overhead. Uses 5 size classes for efficient memory management.

**Responsibilities:**

1. Maintain 5 size class pools (256B, 1KB, 4KB, 16KB, 64KB)
2. Thread-local pool management
3. LRU eviction when pool exceeds capacity
4. Track pool statistics (hit rate, evictions)
5. Graceful shutdown (flush all pools)

**Core Methods:**

```python
class BufferPool:
    """
    Thread-local reusable buffer pool.

    Size Classes:
        - 256B: Small events, metadata
        - 1KB: TaskAnnouncement, tool results
        - 4KB: AgentState, small SessionState deltas
        - 16KB: Medium SessionState (intermediate)
        - 64KB: Large SessionState (full snapshots)

    Benefits:
        - Reduces allocation overhead (malloc/free)
        - Improves locality (warm cache)
        - Reduces GC pressure
        - 1.4× speedup vs allocating new buffers
    """

    def __init__(self):
        """Initialize thread-local pools."""
        # TODO(@infrastructure-team): Initialize pools
        # 1. Create 5 size class pools (as deques)
        # 2. Set max capacity per pool (e.g., 100 buffers)
        # 3. Initialize per-thread storage (threading.local)
        pass

    def acquire(self, size: int) -> bytearray:
        """
        Acquire buffer from pool or allocate new.

        Args:
            size: Minimum buffer size

        Returns:
            Bytearray ready for use

        Performance:
            - Hit: <0.1ms (pool lookup)
            - Miss: <1ms (allocation)
            - Speedup: 1.4× faster (hit vs miss average)

        Observability:
            - Metric: k1_buffer_pool_acquire{size_class, result} (hit/miss)

        ADR: ADR-0011c (Performance)
        """
        # TODO(@infrastructure-team): Implement buffer acquisition
        # 1. Find appropriate size class
        # 2. Try to pop from pool (hit)
        # 3. If empty, allocate new (miss)
        # 4. Return buffer
        # 5. Record metric
        pass

    def release(self, buffer: bytearray) -> None:
        """
        Return buffer to pool.

        Args:
            buffer: Buffer to return

        Side effects:
            - Adds to appropriate pool
            - May trigger eviction if pool full

        Performance:
            - Overhead: <0.1ms

        ADR: ADR-0011c (Performance)
        """
        # TODO(@infrastructure-team): Implement buffer release
        # 1. Determine size class
        # 2. Add to pool
        # 3. If pool exceeds capacity, evict LRU (oldest)
        # 4. Record metric
        pass

    def get_stats(self) -> Dict[str, Any]:
        """
        Get pool statistics for monitoring.

        Returns:
            Dict with:
                - size_class: {pool_depth, hit_rate, evictions_total}
                - total_memory: Sum of all buffers (MB)
                - hit_rate_overall: Across all size classes

        Performance:
            - Stats collection: <5ms

        Observability:
            - Metrics: k1_buffer_pool_hit_rate{size_class}, k1_buffer_pool_memory_mb

        ADR: ADR-0011c (Performance)
        """
        # TODO(@infrastructure-team): Implement stats
        pass

    async def shutdown(self) -> None:
        """
        Flush all pools and release memory.

        ADR: ADR-0011c (Performance)
        """
        # TODO(@infrastructure-team): Implement shutdown
        # 1. Clear all pools
        # 2. Release memory
        # 3. Log stats before shutdown
        pass
```

**Size Class Strategy:**

```yaml
Size Classes:
  256B:
    - Use cases: Small events, metadata
    - Count: 100 buffers max
    - Memory: 25KB total

  1KB:
    - Use cases: TaskAnnouncement (2KB), tool results
    - Count: 100 buffers max
    - Memory: 100KB total

  4KB:
    - Use cases: AgentState (8KB), intermediate deltas
    - Count: 100 buffers max
    - Memory: 400KB total

  16KB:
    - Use cases: Medium SessionState (8-16KB)
    - Count: 50 buffers max
    - Memory: 800KB total

  64KB:
    - Use cases: Full SessionState snapshots (64KB)
    - Count: 20 buffers max
    - Memory: 1.2MB total

Total Pool Memory: ~2.5MB (bounded)
```

**ADR References:**

- ADR-0011c: Performance Optimization

**Assigned To:** Issue #L5-3.2.1

---

#### Issue 3.2.2: alignment.py

**File Path:** `k1/l5_infrastructure/serialization/alignment.py`

**Description:**
Memory alignment utilities for SIMD optimization. Ensures 4/8/16-byte alignment for vectorization.

**Responsibilities:**

1. Ensure 4-byte alignment (SSE minimum)
2. Ensure 8-byte alignment for 64-bit access
3. Ensure 16-byte alignment (AVX/SSE optimal)
4. Provide alignment directives for schemas
5. Implement padding calculation

**Core Functions:**

```python
def align_buffer(
    buffer: bytearray,
    alignment: int = 16,
) -> bytearray:
    """
    Align buffer to specified boundary (4/8/16 bytes).

    Args:
        buffer: Buffer to align
        alignment: Target alignment (4, 8, or 16)

    Returns:
        Aligned buffer with padding

    Performance:
        - Alignment calculation: <0.1ms
        - Padding overhead: <10% (typical)

    Examples:
        >>> buffer = bytearray(65)  # Unaligned
        >>> aligned = align_buffer(buffer, 16)
        >>> len(aligned) == 80  # Padded to 16-byte boundary

    ADR: ADR-0011c (Performance - SIMD optimization)
    """
    # TODO(@infrastructure-team): Implement alignment
    # 1. Calculate padding needed
    # 2. Add padding bytes
    # 3. Return aligned buffer
    pass

def calculate_padding(
    current_offset: int,
    target_alignment: int,
) -> int:
    """
    Calculate padding bytes needed to reach alignment.

    Args:
        current_offset: Current buffer offset
        target_alignment: Target alignment (4, 8, 16)

    Returns:
        Number of padding bytes needed

    Formula:
        padding = (target_alignment - (current_offset % target_alignment)) % target_alignment

    Performance:
        - Calculation: <1 cycle (no I/O)

    ADR: ADR-0011c (Performance)
    """
    # TODO(@infrastructure-team): Implement padding calculation
    pass

def is_aligned(
    buffer: bytearray,
    alignment: int = 16,
) -> bool:
    """
    Check if buffer is aligned to boundary.

    Args:
        buffer: Buffer to check
        alignment: Target alignment

    Returns:
        True if buffer address aligned

    ADR: ADR-0011c (Performance)
    """
    # TODO(@infrastructure-team): Implement alignment check
    pass
```

**SIMD Optimization Context:**

```
Use Case: Real-time audio frame processing

Audio frames: 16-bit PCM samples
Without alignment:
  - PCM_left = [16b | 16b | 16b | 16b | ...]  (unaligned)
  - Load each sample individually (slow)

With 16-byte alignment:
  - PCM_left = [ALIGNED: 16b | 16b | 16b | 16b | ...]
  - Load 4 samples with single SIMD instruction (SSE)
  - Process in parallel (vectorized)
  - 3-4× speedup

Schemas using alignment:
  - AudioFrame: force_align=16 (for PCM samples)
  - BatchedAudio: force_align=16 (for processing efficiency)

Metrics:
  - Audio processing speedup: 3-4× (with vs without)
```

**ADR References:**

- ADR-0011c: Performance Optimization (SIMD)

**Assigned To:** Issue #L5-3.2.2

---

### 🎯 Epic 3.3: Optimization & Advanced Features

**Purpose:** Additional optimization and advanced serialization features
**Files:** 2
**Status:** 🚧 STUB

#### Issue 3.3.1: zero_copy.py

**File Path:** `k1/l5_infrastructure/serialization/zero_copy.py`

**Description:**
Direct buffer access helpers for zero-copy deserialization. Provides utilities for accessing nested structures without copying.

**Responsibilities:**

1. VTable offset calculation
2. Field accessor generation
3. Nested object access (chain offsets)
4. Repeated field iteration (arrays)
5. String/byte access without copying

**Core Functions:**

```python
class ZeroCopyAccessor:
    """
    Utilities for zero-copy field access from FlatBuffers.
    """

    @staticmethod
    def get_root_table(buffer: bytes, offset: int = 0) -> Any:
        """
        Get root table reference without copying.

        Args:
            buffer: Binary FlatBuffers data
            offset: Offset to root table

        Returns:
            Table reference (lazy accessor)

        Performance:
            - Access: <0.01ms (just offset calculation)

        ADR: ADR-0011 (Zero-copy)
        """
        # TODO(@infrastructure-team): Implement root table access
        pass

    @staticmethod
    def get_field_offset(
        table: Any,
        field_index: int,
    ) -> int:
        """
        Calculate field offset from vtable.

        Args:
            table: Table reference
            field_index: Field index in schema

        Returns:
            Byte offset in buffer

        Performance:
            - Calculation: <0.01ms

        ADR: ADR-0011 (Zero-copy design)
        """
        # TODO(@infrastructure-team): Implement offset calculation
        # 1. Read vtable offset from table
        # 2. Index into vtable for field
        # 3. Return field offset
        pass

    @staticmethod
    def get_string(
        buffer: bytes,
        offset: int,
    ) -> str:
        """
        Extract string from buffer without copying.

        Args:
            buffer: Binary data
            offset: String offset

        Returns:
            String (decoded from buffer)

        Performance:
            - Decode: <1ms for 1KB string

        ADR: ADR-0011 (Zero-copy strings)
        """
        # TODO(@infrastructure-team): Implement string access
        # 1. Read length from offset
        # 2. Decode UTF-8 (minimal copy)
        pass
```

**ADR References:**

- ADR-0011: Zero-Copy FlatBuffers

**Assigned To:** Issue #L5-3.3.1

---

#### Issue 3.3.2: string_dedup.py

**File Path:** `k1/l5_infrastructure/serialization/string_dedup.py`

**Description:**
String deduplication during serialization. Reduces payload size by detecting duplicate strings and storing once.

**Responsibilities:**

1. Track string occurrences during serialization
2. Store strings only once in FlatBuffers buffer
3. Maintain offset mapping for references
4. Estimate size savings
5. Optional feature (enable/disable)

**Core Methods:**

```python
class StringDeduplicator:
    """
    Deduplicate strings during FlatBuffers serialization.

    Example:
        SessionState contains: ["intent", "reminder", "intent", "reminder"]
        Without dedup: 4 strings = 26 bytes total
        With dedup: 2 strings + 2 references = 12 bytes total
        Savings: 54%
    """

    def serialize_with_dedup(
        self,
        obj: Any,
        schema_type: str,
    ) -> bytes:
        """
        Serialize with string deduplication.

        Args:
            obj: Object to serialize
            schema_type: Schema type

        Returns:
            Deduplicated binary buffer

        Performance:
            - Overhead: <10% (hash table + reference resolution)
            - Size savings: 30-50% (typical for text-heavy data)

        Trade-off:
            - Slower serialization (dedup overhead)
            - Smaller payload (network savings)
- Faster deserialization (fewer allocations)

        ADR: ADR-0011c (Performance optimization)
        """
        # TODO(@infrastructure-team): Implement dedup serialization
        # 1. Build string frequency map during traversal
        # 2. Serialize frequent strings once
        # 3. Use references for duplicates
        # 4. Calculate size savings
        pass

    def get_dedup_stats(self) -> Dict[str, Any]:
        """
        Get deduplication statistics.

        Returns:
            Dict with:
                - strings_total: Total string count
                - strings_unique: Unique strings
                - size_before: Original size
                - size_after: After dedup
                - savings_percent: (size_before - size_after) / size_before * 100

        ADR: ADR-0011c (Performance)
        """
        # TODO(@infrastructure-team): Implement stats
        pass
```

**ADR References:**

- ADR-0011c: Performance Optimization

**Assigned To:** Issue #L5-3.3.2

---

### 📊 Summary

**Milestone 3: Serialization (FlatBuffers)**

| Epic | Files | Status | Assigned |
|------|-------|--------|----------|
| 3.1: Core Serialization | 2 | 🚧 STUB | @infrastructure-team |
| 3.2: Memory Management | 2 | 🚧 STUB | @infrastructure-team |
| 3.3: Optimization | 2 | 🚧 STUB | @infrastructure-team |
| **Total** | **6** | **🚧 STUB** | **@infrastructure-team** |

**Performance Targets Summary:**

- Serialization: <1ms P95 (64KB)
- Deserialization: <0.1ms P95 (zero-copy)
- Size reduction: 3× smaller vs JSON
- Buffer pool hit rate: >80%
- SIMD acceleration: 3-4× for audio

**Milestone 3 Dependencies:**

```
Upstream (Objects to serialize):
  - k1.l1_input.audio (AudioFrame)
  - k1.l2_orchestration.plan (Plan, TaskAnnouncement)
  - k1.l3_execution.agents (AgentState)
  - k1.l4_runtime.session (SessionState)

Downstream (Consumers):
  - k1.bridge_k0.protocol (Protocol negotiation)
  - k1.bridge_k0.command_client (K0 bridge)
  - k1.l5_infrastructure.event_bus (Event messages)
  - k1.l5_infrastructure.storage (Caching)
```

---

## Milestone 4: Circuit Breaker

### 📋 Overview

**Purpose:** Resilience pattern to prevent cascading failures with 3-state FSM (CLOSED → OPEN → HALF_OPEN)
**Priority:** P1 (Important for Reliability)
**Status:** 🚧 STUB - NEEDS_IMPLEMENTATION
**Files:** 13 Python modules
**ADRs:** ADR-0009, ADR-0009a, ADR-0009b, ADR-0009c
**Assigned To:** @resilience-team

**Key Features:**

- 3-state finite state machine (CLOSED, OPEN, HALF_OPEN)
- Per-service configuration (failure threshold, timeout, slow call detection)
- 4 fallback strategies (default value, cached result, alternate service, raise error)
- Automatic recovery after timeout
- Failure tracking and metrics
- Redis caching integration for state persistence

**State Transitions:**

```
CLOSED (Normal Operation)
  ├─ Track failures (count < threshold)
  └─ OPEN (failure_count ≥ threshold)

OPEN (Fail-Fast Mode)
  ├─ Reject all requests immediately
  ├─ Wait for timeout (default: 30s)
  └─ HALF_OPEN (recovery test)

HALF_OPEN (Recovery Testing)
  ├─ Allow 1 probe request
  ├─ Success → CLOSED (recovered!)
  └─ Failure → OPEN (still broken, retry timeout)
```

**Use Cases (Wrapped Services):**

1. **K0 Bridge** - Critical path, raise error on open
2. **Tool Runner** - Non-critical, return default value
3. **Model Hub (Local)** - Cascade to remote on failure
4. **Model Hub (Remote)** - Return cached result
5. **Streaming Engine** - Graceful degradation
6. **MCP Gateway** - Optional, best-effort

**Performance Targets:**

```yaml
State Check:
  - Latency: <5ms P95
  - CPU: <0.1ms per call

Circuit Operations:
  - Transition: <1ms
  - Metrics export: <10ms

Observability:
  - Metrics update: <5ms
  - Trace span creation: <1ms
```

---

### 🎯 Epic 4.1: FSM Core & Management

**Purpose:** Finite state machine logic and circuit breaker manager
**Files:** 4
**Status:** 🚧 STUB

#### Issue 4.1.1: circuit_breaker_manager.py

**File Path:** `k1/l5_infrastructure/resilience/circuit_breaker_manager.py`

**Description:**
Core circuit breaker orchestrator managing FSM state transitions, per-service instances, and global registry.

**Responsibilities:**

1. Manage circuit breaker instances per service
2. Coordinate state transitions
3. Track failure counts and timers
4. Provide admin operations (reset, pause, resume)
5. Export metrics for monitoring

**Core Methods:**

```python
class CircuitBreakerManager:
    """
    Manages circuit breaker instances for all services.

    Services:
        - tool_runner (Tool execution)
        - model_hub_local (Local model inference)
        - model_hub_remote (Remote model inference)
        - k0_bridge (K0 memory kernel)
        - streaming_engine (Real-time streaming)
        - mcp_gateway (MCP tool calling)
    """

    def __init__(self, config_path: str = "k1/config/circuit_breakers.yml"):
        """
        Initialize manager with configuration.

        Args:
            config_path: Path to circuit breaker config YAML

        ADR: ADR-0009 (Circuit Breaker Architecture)
        """
        # TODO(@resilience-team): Initialize manager
        # 1. Load config from circuit_breakers.yml
        # 2. Create circuit breaker instances per service
        # 3. Setup state persistence (Redis)
        # 4. Start monitoring tasks
        pass

    def get_circuit_breaker(
        self,
        service_name: str,
    ) -> "CircuitBreaker":
        """
        Get or create circuit breaker for service.

        Args:
            service_name: Service identifier

        Returns:
            CircuitBreaker instance

        Raises:
            KeyError: If service not configured

        Performance:
            - Lookup: <1ms

        ADR: ADR-0009
        """
        # TODO(@resilience-team): Implement service lookup
        pass

    async def call_with_circuit_breaker(
        self,
        service_name: str,
        operation: Callable[[], Awaitable[Any]],
        cognitive_trace_id: Optional[str] = None,
    ) -> Any:
        """
        Execute operation with circuit breaker protection.

        Args:
            service_name: Service to call
            operation: Async function to execute
            cognitive_trace_id: Trace ID for observability

        Returns:
            Result or fallback value

        Raises:
            CircuitOpenError: If circuit open and no fallback

        Flow:
            1. Get circuit breaker for service
            2. Check if OPEN (fail-fast)
            3. Execute operation (with timeout)
            4. Record success/failure
            5. Return result or fallback

        Performance:
            - Open circuit: <1ms (immediate return)
            - Closed circuit: Operation latency + 5ms overhead

        Observability:
            - Metric: k1_circuit_breaker_calls_total{service, status}
            - Trace: Span circuit_breaker.call

        ADR: ADR-0009
        """
        # TODO(@resilience-team): Implement call wrapper
        pass

    def get_service_health(
        self,
        service_name: str,
    ) -> Dict[str, Any]:
        """
        Get circuit breaker health for service.

        Args:
            service_name: Service to check

        Returns:
            Dict with:
                - state: CLOSED | OPEN | HALF_OPEN
                - failures: Current failure count
                - last_failure: Timestamp
                - last_recovery: Timestamp
                - total_calls: Total calls attempted
                - success_rate: Percentage successful

        ADR: ADR-0009
        """
        # TODO(@resilience-team): Implement health check
        pass

    async def reset_service(
        self,
        service_name: str,
    ) -> None:
        """
        Reset circuit breaker to CLOSED state.

        Args:
            service_name: Service to reset

        Side effects:
            - Sets state to CLOSED
            - Resets failure count
            - Logs RESET event

        ADR: ADR-0009
        """
        # TODO(@resilience-team): Implement reset
        pass
```

**Configuration Format:**

```yaml
# k1/config/circuit_breakers.yml

global:
  failure_threshold: 5           # Failures before OPEN
  recovery_timeout: 30           # Seconds in OPEN before HALF_OPEN
  success_threshold: 3           # Successes in HALF_OPEN before CLOSED
  monitoring_interval: 10        # Seconds between health checks

services:
  tool_runner:
    failure_threshold: 5
    recovery_timeout: 30
    slow_call_threshold: 5000    # ms
    fallback_strategy: default_value
    fallback_value: None

  model_hub_local:
    failure_threshold: 3
    recovery_timeout: 10
    slow_call_threshold: 1000
    fallback_strategy: alternate_service
    fallback_target: model_hub_remote

  model_hub_remote:
    failure_threshold: 5
    recovery_timeout: 60
    slow_call_threshold: 10000
    fallback_strategy: cached_result
    cache_ttl: 300

  k0_bridge:
    failure_threshold: 3
    recovery_timeout: 5
    slow_call_threshold: 100
    fallback_strategy: raise_error

  streaming_engine:
    failure_threshold: 3
    recovery_timeout: 10
    slow_call_threshold: 5000
    fallback_strategy: default_value
    fallback_value: None
```

**ADR References:**

- ADR-0009: Circuit Breaker Core Architecture
- ADR-0009b: Configuration Management

**Assigned To:** Issue #L5-4.1.1

---

#### Issue 4.1.2: circuit_fsm.py

**File Path:** `k1/l5_infrastructure/resilience/circuit_fsm.py`

**Description:**
Finite state machine implementation with state transitions, guards, and event handling.

**Responsibilities:**

1. Define 3 states (CLOSED, OPEN, HALF_OPEN)
2. Implement state transition guards
3. Handle failure/success events
4. Manage timeout timers
5. Track state duration metrics

**Core Classes:**

```python
class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"           # Normal operation
    OPEN = "OPEN"               # Failing, reject requests
    HALF_OPEN = "HALF_OPEN"     # Testing recovery


class CircuitBreakerFSM:
    """
    Finite state machine for circuit breaker.

    State Diagram:
        CLOSED
          ├─ [failure_count ≥ threshold]
          └─ OPEN

        OPEN
          ├─ [timeout reached]
          └─ HALF_OPEN

        HALF_OPEN
          ├─ [probe success]
          └─ CLOSED
          └─ [probe failure]
              └─ OPEN
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        success_threshold: int = 3,
    ):
        """
        Initialize FSM.

        Args:
            service_name: Service identifier
            failure_threshold: Failures before OPEN (default: 5)
            recovery_timeout: Seconds in OPEN (default: 30s)
            success_threshold: Successes in HALF_OPEN before CLOSED (default: 3)

        ADR: ADR-0009a (State Management)
        """
        # TODO(@resilience-team): Initialize FSM
        # 1. Set initial state to CLOSED
        # 2. Initialize counters
        # 3. Setup timers
        pass

    def record_success(self) -> None:
        """
        Record successful call.

        State Transitions:
            - CLOSED: No change (reset failure count to 0)
            - HALF_OPEN: Increment success count
              - If success_count ≥ success_threshold → CLOSED

        Performance:
            - Update: <1ms

        ADR: ADR-0009a
        """
        # TODO(@resilience-team): Implement success recording
        pass

    def record_failure(self) -> bool:
        """
        Record failed call.

        Args:
            None

        Returns:
            True if transitioning to OPEN, False otherwise

        State Transitions:
            - CLOSED: Increment failure count
              - If failure_count ≥ failure_threshold → OPEN
            - OPEN: No change (already open)
            - HALF_OPEN: Failed probe → OPEN

        Performance:
            - Update: <1ms

        ADR: ADR-0009a
        """
        # TODO(@resilience-team): Implement failure recording
        pass

    def record_timeout(self) -> None:
        """
        Record timeout (slow call).

        Behavior:
            - Counts as failure (triggers state check)

        ADR: ADR-0009a
        """
        # TODO(@resilience-team): Implement timeout recording
        pass

    def can_attempt_request(self) -> bool:
        """
        Check if request can be attempted.

        Returns:
            - CLOSED: True (always attempt)
            - OPEN: False (fail-fast, unless timeout reached)
            - HALF_OPEN: True (allow probe)

        Performance:
            - Check: <1ms (no blocking)

        ADR: ADR-0009a
        """
        # TODO(@resilience-team): Implement request guard
        pass

    def get_state(self) -> CircuitBreakerState:
        """Get current state."""
        # TODO(@resilience-team): Implement state accessor
        pass
```

**ADR References:**

- ADR-0009a: State Handlers and Transitions

**Assigned To:** Issue #L5-4.1.2

---

#### Issue 4.1.3: call_wrapper.py

**File Path:** `k1/l5_infrastructure/resilience/call_wrapper.py`

**Description:**
Wraps service calls with circuit breaker logic (state check, timeout, fallback).

**Responsibilities:**

1. Check circuit state before call
2. Execute operation with timeout
3. Record result (success/failure/timeout)
4. Invoke fallback if needed
5. Propagate errors appropriately

**Core Function:**

```python
async def call_with_protection(
    circuit_breaker: "CircuitBreaker",
    operation: Callable[[], Awaitable[Any]],
    timeout_ms: int = 5000,
    fallback_fn: Optional[Callable[[], Awaitable[Any]]] = None,
    cognitive_trace_id: Optional[str] = None,
) -> Any:
    """
    Execute operation with circuit breaker protection.

    Args:
        circuit_breaker: Circuit breaker instance
        operation: Async function to execute
        timeout_ms: Operation timeout (default: 5000ms)
        fallback_fn: Async fallback function if circuit open
        cognitive_trace_id: Trace ID for observability

    Returns:
        Operation result or fallback result

    Raises:
        CircuitOpenError: If circuit open and no fallback
        TimeoutError: If operation exceeds timeout

    Flow:
        1. Check if can attempt (state check)
        2. If OPEN and fallback exists → invoke fallback
        3. If OPEN and no fallback → raise CircuitOpenError
        4. Execute operation with timeout
        5. On success → record success, return result
        6. On timeout → record timeout, invoke fallback/raise
        7. On failure → record failure, invoke fallback/raise

    Performance:
        - Check: <1ms
        - Timeout setup: <1ms
        - Fallback invocation: <operation latency>
        - Total overhead: <5ms

    Observability:
        - Metric: k1_circuit_breaker_calls_total{service, result}
        - Trace: Span circuit_breaker.call
        - Log: INFO call attempted, ERROR call failed

    ADR: ADR-0009 (Wrapper pattern)
    """
    # TODO(@resilience-team): Implement call wrapper
    # 1. Create trace span with cognitive_trace_id
    # 2. Check circuit.can_attempt_request()
    # 3. If False, invoke fallback or raise error
    # 4. Execute operation with asyncio.wait_for(timeout_ms)
    # 5. On success: record_success(), return result
    # 6. On timeout: record_timeout(), fallback/raise
    # 7. On exception: record_failure(), fallback/raise
    # 8. Record metrics (duration, status)
    pass
```

**ADR References:**

- ADR-0009: Circuit Breaker Pattern

**Assigned To:** Issue #L5-4.1.3

---

#### Issue 4.1.4: config_manager.py

**File Path:** `k1/l5_infrastructure/resilience/config_manager.py`

**Description:**
Loads and manages circuit breaker configuration from YAML files with hot-reload support.

**Responsibilities:**

1. Load circuit_breakers.yml configuration
2. Validate configuration format
3. Support hot-reload (config changes without restart)
4. Provide config watchers for dynamic updates
5. Export configuration metrics

**Core Methods:**

```python
class CircuitBreakerConfigManager:
    """
    Manages circuit breaker configuration.

    Config File: k1/config/circuit_breakers.yml
    """

    def load_config(
        self,
        config_path: str,
    ) -> Dict[str, Any]:
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to circuit_breakers.yml

        Returns:
            Parsed configuration dict

        Raises:
            FileNotFoundError: If config file not found
            ValueError: If config invalid

        ADR: ADR-0009b (Configuration)
        """
        # TODO(@resilience-team): Implement config loading
        pass

    def validate_config(
        self,
        config: Dict[str, Any],
    ) -> bool:
        """
        Validate configuration schema.

        Checks:
            - All services have required fields
            - Threshold values are positive
            - Timeout values are positive
            - Fallback strategies are valid

        Returns:
            True if valid

        Raises:
            ValueError: If config invalid

        ADR: ADR-0009b
        """
        # TODO(@resilience-team): Implement validation
        pass

    def watch_config(
        self,
        config_path: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        """
        Watch config file for changes (hot-reload).

        Args:
            config_path: Path to watch
            callback: Async callback on change

        Behavior:
            - Monitors file modifications
            - On change: load new config, validate, invoke callback
            - Rollback on validation failure

        ADR: ADR-0009b (Hot-reload)
        """
        # TODO(@resilience-team): Implement file watching
        pass
```

**ADR References:**

- ADR-0009b: Configuration Management

**Assigned To:** Issue #L5-4.1.4

---

### 🎯 Epic 4.2: State Handlers

**Purpose:** Individual state implementations (CLOSED, OPEN, HALF_OPEN)
**Files:** 3
**Status:** 🚧 STUB

#### Issue 4.2.1: states/closed.py

**File Path:** `k1/l5_infrastructure/resilience/states/closed.py`

**Description:**
CLOSED state handler - normal operation, tracking failures.

**Responsibilities:**

1. Track failures during normal operation
2. Trigger transition to OPEN on threshold
3. Reset failure count on success
4. Maintain metrics

```python
class ClosedStateHandler:
    """
    CLOSED State: Normal operation.

    Behavior:
        - Attempt all requests
        - Track failure count
        - Transition to OPEN if threshold exceeded
        - Reset failures on success
    """

    async def handle_success(self, fsm: "CircuitBreakerFSM") -> None:
        """Handle successful call in CLOSED state."""
        # TODO(@resilience-team): Reset failure count, record success
        pass

    async def handle_failure(self, fsm: "CircuitBreakerFSM") -> None:
        """Handle failed call, check for transition to OPEN."""
        # TODO(@resilience-team): Increment failure count, check threshold
        pass
```

**ADR References:**

- ADR-0009a: State Handlers

**Assigned To:** Issue #L5-4.2.1

---

#### Issue 4.2.2: states/open.py

**File Path:** `k1/l5_infrastructure/resilience/states/open.py`

**Description:**
OPEN state handler - fail-fast mode, rejecting requests.

**Responsibilities:**

1. Reject requests immediately (fail-fast)
2. Track timeout to transition to HALF_OPEN
3. Prevent cascading failures

```python
class OpenStateHandler:
    """
    OPEN State: Fail-fast, circuit open.

    Behavior:
        - Reject all requests immediately
        - Wait for timeout
        - Transition to HALF_OPEN to test recovery
    """

    def should_attempt_request(self, fsm: "CircuitBreakerFSM") -> bool:
        """Check if enough time has passed to attempt HALF_OPEN probe."""
        # TODO(@resilience-team): Check timeout, return True if recovery time reached
        pass
```

**ADR References:**

- ADR-0009a: State Handlers

**Assigned To:** Issue #L5-4.2.2

---

#### Issue 4.2.3: states/half_open.py

**File Path:** `k1/l5_infrastructure/resilience/states/half_open.py`

**Description:**
HALF_OPEN state handler - recovery testing with single probe.

**Responsibilities:**

1. Allow single probe request
2. Transition to CLOSED on success (recovered!)
3. Transition back to OPEN on failure

```python
class HalfOpenStateHandler:
    """
    HALF_OPEN State: Testing recovery.

    Behavior:
        - Allow controlled probe request
        - Success → CLOSED (service recovered)
        - Failure → OPEN (service still broken, retry timeout)
    """

    def allow_probe(self) -> bool:
        """Check if probe allowed (only 1 concurrent probe)."""
        # TODO(@resilience-team): Prevent concurrent probes
        pass

    async def handle_probe_success(self, fsm: "CircuitBreakerFSM") -> None:
        """Handle successful probe - transition to CLOSED."""
        # TODO(@resilience-team): Transition to CLOSED, reset counters
        pass

    async def handle_probe_failure(self, fsm: "CircuitBreakerFSM") -> None:
        """Handle failed probe - transition back to OPEN."""
        # TODO(@resilience-team): Transition to OPEN, restart timeout
        pass
```

**ADR References:**

- ADR-0009a: State Handlers

**Assigned To:** Issue #L5-4.2.3

---

### 🎯 Epic 4.3: Fallback Strategies

**Purpose:** 4 fallback strategies (default value, cached result, alternate service, raise error)
**Files:** 4
**Status:** 🚧 STUB

#### Issue 4.3.1: fallbacks/default_value.py

**File Path:** `k1/l5_infrastructure/resilience/fallbacks/default_value.py`

**Description:**
Fallback strategy - return default/empty value when circuit open.

**Use Cases:**

- Tool Runner (optional, return None)
- Best-effort operations

```python
class DefaultValueFallback:
    """
    Fallback: Return default value when circuit open.

    Good for: Non-critical, optional operations
    """

    async def invoke(
        self,
        default_value: Any,
    ) -> Any:
        """
        Return default value.

        Args:
            default_value: Value to return (e.g., None, [], {})

        Returns:
            default_value

        ADR: ADR-0009 (Fallback patterns)
        """
        # TODO(@resilience-team): Implement default value fallback
        pass
```

**Assigned To:** Issue #L5-4.3.1

---

#### Issue 4.3.2: fallbacks/cached_result.py

**File Path:** `k1/l5_infrastructure/resilience/fallbacks/cached_result.py`

**Description:**
Fallback strategy - return cached result when circuit open.

**Use Cases:**

- Remote Model Hub (return cached inference result)
- K0 queries (return cached context)

```python
class CachedResultFallback:
    """
    Fallback: Return cached result when circuit open.

    Good for: Operations with results that can be cached and reused
    Requires: Redis integration
    """

    async def invoke(
        self,
        operation_key: str,
        ttl_seconds: int = 300,
    ) -> Any:
        """
        Return cached result.

        Args:
            operation_key: Key for cached value in Redis
            ttl_seconds: Cache lifetime

        Returns:
            Cached value or None if expired/missing

        ADR: ADR-0009 (Fallback patterns)
        """
        # TODO(@resilience-team): Implement cached result fallback
        # 1. Query Redis for operation_key
        # 2. Check TTL
        # 3. Return value if valid, None otherwise
        pass
```

**Assigned To:** Issue #L5-4.3.2

---

#### Issue 4.3.3: fallbacks/alternate_service.py

**File Path:** `k1/l5_infrastructure/resilience/fallbacks/alternate_service.py`

**Description:**
Fallback strategy - route to alternate service when primary unavailable.

**Use Cases:**

- Model Hub Local → Remote cascade
- Primary → Secondary service failover

```python
class AlternateServiceFallback:
    """
    Fallback: Route to alternate service when primary fails.

    Good for: Services with fallback alternatives
    Example: Local model → Remote model cascade
    """

    async def invoke(
        self,
        operation: Callable[[], Awaitable[Any]],
        alternate_service_name: str,
    ) -> Any:
        """
        Call alternate service.

        Args:
            operation: Operation to perform on alternate service
            alternate_service_name: Name of alternate service circuit breaker

        Returns:
            Result from alternate service

        Raises:
            Exception: If alternate also unavailable

        ADR: ADR-0009 (Fallback patterns)
        """
        # TODO(@resilience-team): Implement alternate service fallback
        # 1. Get alternate service circuit breaker
        # 2. Call operation through alternate's circuit breaker
        # 3. Return result or raise if also unavailable
        pass
```

**Assigned To:** Issue #L5-4.3.3

---

#### Issue 4.3.4: fallbacks/raise_error.py

**File Path:** `k1/l5_infrastructure/resilience/fallbacks/raise_error.py`

**Description:**
Fallback strategy - raise error immediately when circuit open.

**Use Cases:**

- K0 Bridge (critical path, must fail loudly)
- Required operations (no fallback acceptable)

```python
class RaiseErrorFallback:
    """
    Fallback: Raise error when circuit open.

    Good for: Critical operations where failure must be visible
    Example: K0 Bridge (no fallback for memory kernel)
    """

    async def invoke(
        self,
        service_name: str,
    ) -> None:
        """
        Raise CircuitOpenError.

        Args:
            service_name: Service that failed

        Raises:
            CircuitOpenError: Always

        ADR: ADR-0009 (Fallback patterns)
        """
        # TODO(@resilience-team): Implement raise error fallback
        # 1. Create CircuitOpenError with service_name
        # 2. Raise error
        pass
```

**Assigned To:** Issue #L5-4.3.4

---

### 🎯 Epic 4.4: Advanced Features

**Purpose:** Additional features (hot reload, failure recording, metrics)
**Files:** 2
**Status:** 🚧 STUB

#### Issue 4.4.1: hot_reload.py

**File Path:** `k1/l5_infrastructure/resilience/hot_reload.py`

**Description:**
Hot-reload support for circuit breaker configuration changes without restart.

**Responsibilities:**

1. Watch configuration file
2. Detect changes
3. Apply new configuration to running instances
4. Rollback on validation failure

```python
class CircuitBreakerHotReload:
    """
    Hot-reload configuration changes for circuit breakers.
    """

    async def start_watching(
        self,
        config_path: str,
        manager: "CircuitBreakerManager",
    ) -> None:
        """
        Start watching config file for changes.

        Args:
            config_path: Path to circuit_breakers.yml
            manager: CircuitBreakerManager instance

        Behavior:
            - Monitor file modifications
            - Load new config on change
            - Validate before applying
            - Apply to all circuit breaker instances
            - Rollback on validation failure
            - Log changes

        ADR: ADR-0009b (Hot-reload)
        """
        # TODO(@resilience-team): Implement hot-reload watcher
        pass
```

**Assigned To:** Issue #L5-4.4.1

---

#### Issue 4.4.2: failure_recorder.py

**File Path:** `k1/l5_infrastructure/resilience/failure_recorder.py`

**Description:**
Records detailed failure information for debugging and analytics.

**Responsibilities:**

1. Store failure history (timestamp, type, exception)
2. Calculate failure patterns
3. Export failure metrics
4. Provide failure analysis API

```python
class FailureRecorder:
    """
    Record and analyze failures for debugging.
    """

    def record_failure(
        self,
        service_name: str,
        failure_type: str,  # "timeout" | "exception" | "slow_call"
        exception: Optional[Exception] = None,
        latency_ms: Optional[int] = None,
    ) -> None:
        """
        Record failure details.

        Args:
            service_name: Service that failed
            failure_type: Type of failure
            exception: Exception if applicable
            latency_ms: Operation latency

        ADR: ADR-0009 (Failure tracking)
        """
        # TODO(@resilience-team): Implement failure recording
        pass

    def get_failure_history(
        self,
        service_name: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get recent failures for service.

        Returns:
            List of failure records (most recent first)

        ADR: ADR-0009
        """
        # TODO(@resilience-team): Implement failure history retrieval
        pass
```

**Assigned To:** Issue #L5-4.4.2

---

### 📊 Summary

**Milestone 4: Circuit Breaker**

| Epic | Files | Status | Assigned |
|------|-------|--------|----------|
| 4.1: FSM Core & Manager | 4 | 🚧 STUB | @resilience-team |
| 4.2: State Handlers | 3 | 🚧 STUB | @resilience-team |
| 4.3: Fallback Strategies | 4 | 🚧 STUB | @resilience-team |
| 4.4: Advanced Features | 2 | 🚧 STUB | @resilience-team |
| **Total** | **13** | **🚧 STUB** | **@resilience-team** |

**3-State FSM Summary:**

```
CLOSED ──failure_count ≥ 5──> OPEN ──timeout: 30s──> HALF_OPEN
  ▲                                                       │
  │                                              success ─┘
  │                                              failure──┘
  └──success_count ≥ 3────────────────────────────────────┘
```

**Fallback Strategies:**

| Strategy | Use Case | When | Example |
|----------|----------|------|---------|
| **Default Value** | Optional operations | Circuit OPEN | Tool Runner returns None |
| **Cached Result** | Cacheable data | Circuit OPEN | Remote Model Hub returns cached inference |
| **Alternate Service** | Cascading failover | Circuit OPEN | Local Model → Remote Model |
| **Raise Error** | Critical paths | Circuit OPEN | K0 Bridge fails loudly |

**Performance:**

- State check: <5ms P95
- Fallback invocation: <operation latency
- Metrics export: <10ms
- Hot-reload: <100ms (config reload)

**Configuration Example:**

```yaml
services:
  k0_bridge:
    failure_threshold: 3          # Fail 3x → OPEN
    recovery_timeout: 5           # Wait 5s → HALF_OPEN
    slow_call_threshold: 100      # >100ms = timeout
    fallback_strategy: raise_error # No fallback (critical)

  tool_runner:
    failure_threshold: 5
    recovery_timeout: 30
    slow_call_threshold: 5000
    fallback_strategy: default_value
    fallback_value: None
```

**Milestone 4 Dependencies:**

```
Upstream (Calling services):
  - L1 Input
  - L2 Orchestration
  - L3 Execution
  - L4 Runtime

Downstream (Protected services):
  - K0 Bridge
  - Tool Runner
  - Model Hub (Local/Remote)
  - Streaming Engine
  - MCP Gateway
```

---

---

## Milestone 5: Multi-Tier Storage

### 📋 Overview

**Purpose:** Hot/Warm/Cold tiering for SessionState with automatic lifecycle management (99.4% cost reduction)
**Priority:** P1 (Important for Cost & Scalability)
**Status:** 🚧 STUB - NEEDS_IMPLEMENTATION
**Files:** 8 Python modules
**ADRs:** ADR-0020, ADR-0020a, ADR-0020b, ADR-0020c, ADR-0021
**Assigned To:** @storage-team

**Key Features:**

- **Hot Tier (L1 RAM)**: <1ms access, 56MB capacity, 1000 sessions max
- **Warm Tier (L2 SSD/K0 WAL)**: <50ms access, 100MB capacity, 2000 sessions, 30-day retention
- **Cold Tier (L3 Local Filesystem Storage)**: <200ms access, disk-limited capacity, local filesystem with zstd compression, 365-day retention
- Automatic lifecycle management (promote/demote on access patterns)
- Transparent tier selection and fallback chain (Hot → Warm → Cold)
- Cost optimization: ZERO cloud costs, local disk only, 70% size reduction via compression
- Single source of truth (K0 WAL)

**3-Tier Architecture:**

```
SessionState Access Pattern
  ├─ Active sessions (last 1 hour)
  │   └─ HOT (RAM, <1ms, 56MB)
  │
  ├─ Recent sessions (1-30 days)
  │   └─ WARM (SSD/WAL, <50ms, 100MB)
  │
  └─ Historical sessions (30-365 days)
      └─ COLD (Local Filesystem, <200ms, disk-limited)
```

**Performance Targets:**

- Tier selection: <0.1ms overhead
- Hot access: <1ms P95
- Warm access: <50ms P95
- Cold access (local filesystem): <200ms P95 (vs 500ms S3, 2.5× faster)
- Promotion/demotion: <10ms
- Eviction: <5ms
- Lifecycle check: <2ms per session
- Cold tier compression: 70% size reduction (zstd level 3)

---

### 🎯 Epic 5.1: Tier Management Core

**Purpose:** Tier coordination and transparent tier selection
**Files:** 2
**Status:** 🚧 STUB

#### Issue 5.1.1: tier_manager.py

**File Path:** `k1/l5_infrastructure/storage/tier_manager.py`

**Description:**
Core tier manager providing transparent tier selection, fallback chain, and cache coherence.

**Responsibilities:**

1. Transparent tier lookup (Hot → Warm → Cold)
2. Automatic tier selection on first access
3. Cache invalidation on updates
4. Eviction policy coordination
5. Performance metrics collection

**Core Methods:**

```python
class TierManager:
    """
    Manages SessionState across Hot/Warm/Cold tiers.

    Tier Selection:
        1. Check Hot (RAM) - <1ms
        2. If miss, check Warm (SSD) - <50ms
        3. If miss, check Cold (S3) - <500ms
        4. On access: promote to Hot
        5. On update: invalidate Hot/Warm copies
    """

    def __init__(
        self,
        hot_capacity_mb: int = 56,
        warm_capacity_mb: int = 100,
        config_path: str = "k1/config/storage_tiers.yml",
    ):
        """
        Initialize tier manager.

        Args:
            hot_capacity_mb: Hot tier capacity (default: 56MB = 1000×56KB)
            warm_capacity_mb: Warm tier capacity (default: 100MB)
            config_path: Configuration file path

        ADR: ADR-0020 (Multi-Tier Storage)
        """
        # TODO(@storage-team): Initialize tiers
        # 1. Load tier configuration
        # 2. Initialize Hot tier (in-memory dict)
        # 3. Connect to Warm tier (K0 WAL or SSD)
        # 4. Connect to Cold tier (S3/MinIO)
        # 5. Start background lifecycle manager
        pass

    async def get(
        self,
        session_id: str,
        cognitive_trace_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve SessionState from appropriate tier.

        Args:
            session_id: Session identifier
            cognitive_trace_id: Trace ID for observability

        Returns:
            SessionState dict or None if not found

        Flow:
            1. Check Hot tier (in-memory)
            2. If miss: check Warm tier (K0 WAL or SSD)
            3. If miss: check Cold tier (S3)
            4. On found: promote to Hot tier
            5. Record metric

        Performance:
            - Hot hit: <1ms P95
            - Warm hit: <50ms P95
            - Cold hit: <500ms P95
            - Tier selection overhead: <0.1ms

        Observability:
            - Metric: k1_tier_get_latency_ms{tier}
            - Trace: Span tier_manager.get
            - Log: INFO tier_get, hit_tier, session_id

        ADR: ADR-0020
        """
        # TODO(@storage-team): Implement transparent tier lookup
        # 1. Check Hot tier first (O(1) dict lookup)
        # 2. On miss: check Warm tier
        # 3. On miss: check Cold tier
        # 4. On found: promote to Hot
        # 5. Record metrics
        pass

    async def put(
        self,
        session_id: str,
        state: Dict[str, Any],
        cognitive_trace_id: Optional[str] = None,
    ) -> None:
        """
        Store SessionState (invalidates old copies).

        Args:
            session_id: Session identifier
            state: SessionState dict
            cognitive_trace_id: Trace ID

        Flow:
            1. Invalidate Hot and Warm copies (cache coherence)
            2. Store in Hot tier
            3. Async persist to Warm tier
            4. Return immediately (async warm write)

        Performance:
            - Hot write: <1ms P95
            - Async warm write: <10ms P95

        Observability:
            - Metric: k1_tier_put_total{tier}
            - Trace: Span tier_manager.put

        ADR: ADR-0020
        """
        # TODO(@storage-team): Implement put with cache invalidation
        # 1. Invalidate Hot and Warm (cache coherence)
        # 2. Store in Hot
        # 3. Async persist to Warm
        pass

    async def promote(
        self,
        session_id: str,
        from_tier: str,
        to_tier: str,
    ) -> None:
        """
        Promote session between tiers (e.g., Warm → Hot).

        Args:
            session_id: Session to promote
            from_tier: Source tier (warm, cold)
            to_tier: Target tier (hot)

        Performance:
            - Promotion: <10ms

        ADR: ADR-0020
        """
        # TODO(@storage-team): Implement tier promotion
        # 1. Fetch from source tier
        # 2. Store in target tier
        # 3. Record metric
        pass

    async def demote(
        self,
        session_id: str,
        from_tier: str,
        to_tier: str,
    ) -> None:
        """
        Demote session between tiers (e.g., Hot → Warm).

        Args:
            session_id: Session to demote
            from_tier: Source tier (hot)
            to_tier: Target tier (warm, cold)

        Triggers:
            - LRU eviction (hot tier full)
            - Retention policy (warm tier 30 days)

        Performance:
            - Demotion: <10ms

        ADR: ADR-0020
        """
        # TODO(@storage-team): Implement tier demotion
        # 1. Fetch from source tier
        # 2. Store in target tier
        # 3. Delete from source (evict)
        # 4. Record metric
        pass

    def get_tier_stats(self) -> Dict[str, Any]:
        """
        Get tier statistics for observability.

        Returns:
            Dict with:
                - hot: {sessions, size_mb, hit_rate, latency_p95}
                - warm: {sessions, size_mb, hit_rate, latency_p95}
                - cold: {sessions, access_count, latency_p95}
                - total: {sessions, size_mb}

        ADR: ADR-0020
        """
        # TODO(@storage-team): Implement stats collection
        pass
```

**Configuration Format:**

```yaml
# k1/config/storage_tiers.yml

hot_tier:
  capacity_mb: 56
  max_sessions: 1000
  eviction_policy: lru
  ttl_minutes: null  # No expiration (LRU only)

warm_tier:
  capacity_mb: 100
  max_sessions: 2000
  backend: k0_wal  # or ssd_cache
  retention_days: 30
  eviction_policy: lru

cold_tier:
  backend: s3  # or minio
  bucket: k1-sessions
  prefix: sessions/
  retention_days: 365
  storage_class: STANDARD  # or GLACIER for cost

lifecycle:
  hot_to_warm_timeout: 60  # minutes inactive
  warm_to_cold_timeout: 30  # days inactive
  promotion_on_access: true  # Warm → Hot on get
  demotion_strategy: lru  # LRU eviction when full
```

**ADR References:**

- ADR-0020: Multi-Tier Storage Core Architecture
- ADR-0020a: Hot Tier Design (RAM)
- ADR-0020b: Warm Tier Design (SSD/K0 WAL)
- ADR-0020c: Cold Tier Design (S3)

**Assigned To:** Issue #L5-5.1.1

---

#### Issue 5.1.2: lifecycle_manager.py

**File Path:** `k1/l5_infrastructure/storage/lifecycle_manager.py`

**Description:**
Automatic lifecycle management with promotion/demotion based on access patterns and retention policies.

**Responsibilities:**

1. Monitor access patterns
2. Trigger promotion (Warm → Hot on access)
3. Trigger demotion (Hot → Warm, Warm → Cold)
4. Enforce retention policies
5. Batch lifecycle operations

**Core Methods:**

```python
class LifecycleManager:
    """
    Manages automatic promotion/demotion between tiers.

    Triggers:
        - Promotion: Access to Warm session → move to Hot
        - Demotion: LRU eviction (hot full) → move to Warm/Cold
        - Archival: 30-day retention → move to Cold
        - Deletion: 365-day retention → delete
    """

    def __init__(
        self,
        tier_manager: TierManager,
        hot_idle_timeout_min: int = 60,
        warm_retention_days: int = 30,
        cold_retention_days: int = 365,
    ):
        """
        Initialize lifecycle manager.

        Args:
            tier_manager: TierManager instance
            hot_idle_timeout_min: Idle time before demotion (default: 60 min)
            warm_retention_days: Retention in warm tier (default: 30 days)
            cold_retention_days: Retention in cold tier (default: 365 days)

        ADR: ADR-0021 (Retention Policies)
        """
        # TODO(@storage-team): Initialize lifecycle manager
        # 1. Schedule background tasks
        # 2. Setup idle timers
        # 3. Setup retention monitors
        pass

    async def promote_to_hot(
        self,
        session_id: str,
    ) -> None:
        """
        Promote session from Warm to Hot tier.

        Triggered by:
            - Access to warm session (tier_manager.get)
            - Hot tier has space

        Flow:
            1. Check if already in Hot (no-op)
            2. Fetch from Warm
            3. Store in Hot
            4. Delete from Warm
            5. Record metric

        Performance:
            - Promotion: <10ms

        ADR: ADR-0020
        """
        # TODO(@storage-team): Implement promotion logic
        pass

    async def demote_to_warm(
        self,
        session_id: str,
    ) -> None:
        """
        Demote session from Hot to Warm tier.

        Triggered by:
            - LRU eviction (hot tier full)
            - Idle timeout (60 minutes)

        Flow:
            1. Fetch from Hot
            2. Store in Warm
            3. Delete from Hot
            4. Record metric

        Performance:
            - Demotion: <10ms

        ADR: ADR-0020
        """
        # TODO(@storage-team): Implement demotion logic
        pass

    async def archive_to_cold(
        self,
        session_id: str,
    ) -> None:
        """
        Archive session from Warm to Cold tier.

        Triggered by:
            - Retention policy (30 days in warm)
            - Administrative archival command

        Flow:
            1. Fetch from Warm
            2. Compress and store in Cold (S3)
            3. Delete from Warm
            4. Record metric

        Performance:
            - Archive: <50ms (async)

        ADR: ADR-0021 (Retention)
        """
        # TODO(@storage-team): Implement archival logic
        # 1. Fetch session from Warm
        # 2. Compress (zstd level 6)
        # 3. Upload to S3
        # 4. Delete from Warm
        # 5. Record metrics
        pass

    async def delete_expired(
        self,
    ) -> None:
        """
        Delete sessions exceeding cold tier retention (365 days).

        Triggered by:
            - Daily retention check (11 PM UTC)

        Batch Operations:
            - Query for sessions older than 365 days
            - Delete in batches (1000 sessions per batch)
            - Record metrics

        Observability:
            - Metric: k1_tier_deleted_total
            - Log: INFO deleted_sessions_count, retention_days

        ADR: ADR-0021
        """
        # TODO(@storage-team): Implement deletion logic
        pass

    def get_lifecycle_stats(self) -> Dict[str, Any]:
        """
        Get lifecycle statistics.

        Returns:
            Dict with:
                - promotions_total: Total promotions
                - demotions_total: Total demotions
                - archives_total: Total archives
                - deletions_total: Total deletions
                - avg_promotion_latency_ms: Average promotion time
                - avg_demotion_latency_ms: Average demotion time

        ADR: ADR-0021
        """
        # TODO(@storage-team): Implement stats collection
        pass
```

**Lifecycle Timeline Example:**

```
Session Created: T=0
  ├─ 0-60 min: HOT (active, <1ms access)
  │   └─ Get/Put operations within 60 min → stay in HOT
  │   └─ Idle >60 min → demote to WARM
  │
  ├─ 60 min - 30 days: WARM (recent, <50ms access)
  │   └─ Access within 30 days → promote to HOT
  │   └─ No access for 30 days → archive to COLD
  │
  └─ 30 - 365 days: COLD (historical, <500ms access)
      └─ 365+ days: DELETE (expired)
```

**ADR References:**

- ADR-0020: Multi-Tier Storage Architecture
- ADR-0021: Retention Policies

**Assigned To:** Issue #L5-5.1.2

---

### 🎯 Epic 5.2: Hot Tier (L1 RAM)

**Purpose:** In-memory hot tier with LRU eviction
**Files:** 1 in L5 (coordinated with L4)
**Status:** 🚧 STUB

#### Issue 5.2.1: k1/l4_runtime/storage/hot_tier.py

**File Path:** `k1/l4_runtime/storage/hot_tier.py`

**Description:**
Hot tier implementation - in-memory cache with LRU eviction.

**Responsibilities:**

1. Store active SessionState in RAM
2. LRU eviction when capacity reached (56MB)
3. Fast O(1) lookup and O(1) insertion
4. Thread-safe operations
5. Memory tracking

**Core Methods:**

```python
class HotTier:
    """
    Hot tier: In-memory LRU cache.

    Capacity: 56MB (1000 sessions × 56KB average)
    Access: <1ms P95 (direct memory access)
    Eviction: LRU policy when >56MB
    """

    def __init__(self, capacity_mb: int = 56):
        """
        Initialize hot tier.

        Args:
            capacity_mb: Total capacity in MB (default: 56MB)

        Implementation:
            - Use OrderedDict for LRU tracking
            - Track size in memory
            - Thread-local access for concurrent sessions

        ADR: ADR-0020a (Hot Tier)
        """
        # TODO(@storage-team): Initialize hot tier
        # 1. Create OrderedDict for LRU
        # 2. Setup capacity limits
        # 3. Initialize size tracking
        pass

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve SessionState from hot tier.

        Args:
            session_id: Session identifier

        Returns:
            SessionState dict or None if not found

        Performance:
            - Lookup: O(1) dict access, <1ms P95

        Side effects:
            - Move to end of OrderedDict (LRU)

        ADR: ADR-0020a
        """
        # TODO(@storage-team): Implement get
        # 1. Lookup in dict (O(1))
        # 2. Move to end (LRU)
        # 3. Return value
        pass

    def put(
        self,
        session_id: str,
        state: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Store SessionState in hot tier.

        Args:
            session_id: Session identifier
            state: SessionState dict

        Returns:
            Evicted session (if any) or None

        Flow:
            1. Calculate size of state
            2. If new_size > capacity: evict LRU
            3. Insert new state
            4. Move to end (most recently used)

        Performance:
            - Insert: O(1) dict insert, <1ms P95
            - Eviction: O(1) remove, <5ms P95

        ADR: ADR-0020a
        """
        # TODO(@storage-team): Implement put
        # 1. Calculate size
        # 2. Check capacity, evict if needed
        # 3. Insert in dict
        # 4. Move to end (LRU)
        pass

    def remove(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Remove session from hot tier.

        Args:
            session_id: Session to remove

        Returns:
            Removed session or None if not found

        Performance:
            - Remove: O(1), <1ms

        ADR: ADR-0020a
        """
        # TODO(@storage-team): Implement remove
        pass

    def get_stats(self) -> Dict[str, Any]:
        """
        Get hot tier statistics.

        Returns:
            Dict with:
                - sessions: Current session count
                - size_mb: Current size usage
                - capacity_mb: Total capacity
                - hit_rate: (hits / (hits + misses))
                - evictions: Total evictions

        ADR: ADR-0020a
        """
        # TODO(@storage-team): Implement stats
        pass
```

**Performance Characteristics:**

- Lookup: O(1), <1ms P95
- Insert: O(1), <1ms P95
- Remove: O(1), <1ms P95
- Eviction: O(1), <5ms P95
- Memory overhead: <1% (LRU tracking)

**ADR References:**

- ADR-0020a: Hot Tier Design (RAM-based)

**Assigned To:** Issue #L5-5.2.1

---

### 🎯 Epic 5.3: Warm Tier (L2 SSD/K0 WAL)

**Purpose:** SSD/K0 WAL-based warm tier with 30-day retention
**Files:** 1 in L4 (coordinated with L5)
**Status:** 🚧 STUB

#### Issue 5.3.1: k1/l4_runtime/storage/warm_tier.py

**File Path:** `k1/l4_runtime/storage/warm_tier.py`

**Description:**
Warm tier implementation - SSD cache or K0 WAL with 30-day retention.

**Responsibilities:**

1. Store recent SessionState on SSD/WAL
2. LRU eviction when capacity reached (100MB)
3. Retention tracking (30-day limit)
4. Compression (zstd) for size optimization
5. Async writes to SSD

**Core Methods:**

```python
class WarmTier:
    """
    Warm tier: SSD/K0 WAL storage.

    Capacity: 100MB (2000 sessions × 50KB average)
    Access: <50ms P95 (SSD read + parse)
    Retention: 30 days
    Eviction: LRU when >100MB OR >30 days
    """

    def __init__(
        self,
        capacity_mb: int = 100,
        backend: str = "k0_wal",  # or "ssd_cache"
        retention_days: int = 30,
    ):
        """
        Initialize warm tier.

        Args:
            capacity_mb: Total capacity (default: 100MB)
            backend: Storage backend ("k0_wal" or "ssd_cache")
            retention_days: Retention period (default: 30 days)

        Implementation:
            - Use K0 WAL for durability (preferred)
            - Fall back to SSD cache if K0 unavailable
            - Compress sessions with zstd (level 3)

        ADR: ADR-0020b (Warm Tier)
        """
        # TODO(@storage-team): Initialize warm tier
        # 1. Connect to backend (K0 WAL or SSD)
        # 2. Setup compression (zstd)
        # 3. Initialize size/retention tracking
        pass

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve SessionState from warm tier.

        Args:
            session_id: Session identifier

        Returns:
            SessionState dict or None if not found

        Performance:
            - SSD read: <50ms P95
            - Decompression: <5ms P95
            - Total: <50ms P95

        ADR: ADR-0020b
        """
        # TODO(@storage-team): Implement async get
        # 1. Query backend (K0 WAL or SSD)
        # 2. Decompress (zstd)
        # 3. Return session
        pass

    async def put(
        self,
        session_id: str,
        state: Dict[str, Any],
    ) -> None:
        """
        Store SessionState in warm tier.

        Args:
            session_id: Session identifier
            state: SessionState dict

        Flow:
            1. Compress with zstd
            2. Write to backend (async)
            3. Update retention timestamp

        Performance:
            - Compression: <5ms P95
            - Write: <10ms P95 (async)

        ADR: ADR-0020b
        """
        # TODO(@storage-team): Implement async put
        # 1. Compress (zstd level 3)
        # 2. Write to backend
        # 3. Update retention timestamp
        pass

    async def remove(self, session_id: str) -> None:
        """
        Remove session from warm tier.

        Args:
            session_id: Session to remove

        Performance:
            - Remove: <5ms

        ADR: ADR-0020b
        """
        # TODO(@storage-team): Implement async remove
        pass

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get warm tier statistics.

        Returns:
            Dict with:
                - sessions: Current session count
                - size_mb: Current size (compressed)
                - capacity_mb: Total capacity
                - retention_days: Current retention policy
                - hit_rate: (hits / (hits + misses))
                - compress_ratio: (original / compressed)

        ADR: ADR-0020b
        """
        # TODO(@storage-team): Implement stats
        pass
```

**Compression Benefit:**

- Original SessionState: 50KB average
- Compressed (zstd level 3): 17KB average (66% reduction)
- Actual warm tier capacity: 100MB / 17KB = 5,882 sessions
- vs 100MB / 50KB = 2,000 sessions

**ADR References:**

- ADR-0020b: Warm Tier Design (SSD/K0 WAL)

**Assigned To:** Issue #L5-5.3.1

---

### 🎯 Epic 5.4: Cold Tier (L3 Local Filesystem Storage)

**Purpose:** Local filesystem-based cold tier with 365-day retention (ZERO cloud costs)
**Files:** 1 in L4 (coordinated with L5)
**Status:** 🚧 STUB

#### Issue 5.4.1: k1/l4_runtime/storage/cold_tier.py

**File Path:** `k1/l4_runtime/storage/cold_tier.py`

**Description:**
Cold tier implementation - Local filesystem with zstd compression (replaces S3/MinIO).

**Responsibilities:**

1. Store historical SessionState on local filesystem
2. Lifecycle transitions (archive, delete)
3. Retention enforcement (365-day deletion)
4. Automatic compression (zstd level 3)
5. Async operations
6. Disk usage tracking

**Core Methods:**

```python
class ColdTier:
    """
    Cold tier: Local filesystem storage with zstd compression.

    Implementation:
        - Storage: Local disk (path configurable)
        - Compression: zstd level 3 (70% size reduction)
        - Capacity: Disk-limited (configurable quota, e.g., 500GB)
        - Access: <200ms P95 (disk read + decompress, 2.5× faster than S3)
        - Retention: 365 days
        - Lifecycle: Background task removes expired sessions
        - Cost: $0/month (local-only)

    Deployment:
        - LOCAL-ONLY: Filesystem on device storage
        - No cloud dependency
        - No network calls on critical path
    """

    def __init__(
        self,
        storage_path: str = "/var/lib/familyos/cold_tier",
        quota_gb: int = 500,
        retention_days: int = 365,
        compression_level: int = 3,
    ):
        """
        Initialize cold tier.

        Args:
            storage_path: Root path for cold tier storage
            quota_gb: Disk quota (default: 500GB)
            retention_days: Retention period (default: 365 days)
            compression_level: zstd compression (1-22, default: 3 for speed)

        Implementation:
            - Create storage directory if not exists
            - Initialize metadata tracking
            - Start background cleanup task

        ADR: ADR-0020c (Cold Tier - Local Filesystem)
        """
        # TODO(@storage-team): Initialize cold tier
        # 1. Create storage_path if not exists
        # 2. Load existing metadata (sessions.json)
        # 3. Initialize disk usage tracking
        # 4. Validate quota_gb
        # 5. Start background cleanup task
        pass

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve SessionState from cold tier.

        Args:
            session_id: Session identifier

        Returns:
            SessionState dict or None if not found/expired

        Performance:
            - Filesystem read: <150ms P95
            - Decompress (zstd): <30ms P95
            - Total: <200ms P95 (2.5× faster than S3's 500ms)

        Behavior:
            1. Check metadata (exists? expired?)
            2. Read compressed file (sessions/{session_id}.json.zst)
            3. Decompress with zstd
            4. Return parsed JSON or None

        ADR: ADR-0020c
        """
        # TODO(@storage-team): Implement async get
        # 1. Check metadata file (sessions.json)
        # 2. Verify session not expired
        # 3. Read {storage_path}/sessions/{session_id}.json.zst
        # 4. Decompress with zstd
        # 5. Parse JSON
        # 6. Return dict or None
        pass

    async def put(
        self,
        session_id: str,
        state: Dict[str, Any],
    ) -> None:
        """
        Store SessionState in cold tier.

        Args:
            session_id: Session identifier
            state: SessionState dict

        Flow:
            1. Serialize state to JSON
            2. Compress with zstd level 3 (70% reduction)
            3. Write to {storage_path}/sessions/{session_id}.json.zst
            4. Update metadata (expiration_date, size_bytes)
            5. Check quota (reject if over limit)

        Performance:
            - Serialize: <10ms P95
            - Compress: <20ms P95
            - Write: <50ms P95
            - Total: <100ms P95

        Size Benefit:
            - Typical session: 50KB
            - Compressed: 15KB (70% reduction)
            - 1000 sessions: 15MB vs 50MB

        Quota Enforcement:
            - If total_size > quota_gb × 1024 MB:
              - Reject write with error
              - Log warning
              - Background cleanup will free space

        ADR: ADR-0020c
        """
        # TODO(@storage-team): Implement async put
        # 1. Serialize state to JSON
        # 2. Compress with zstd (level=self.compression_level)
        # 3. Check quota before write
        # 4. Write to {storage_path}/sessions/{session_id}.json.zst
        # 5. Update metadata:
        #    - expiration_date = now + retention_days
        #    - created_at = now
        #    - size_bytes = compressed size
        # 6. Record metric (cold_put_bytes, cold_put_time_ms)
        pass

    async def delete(self, session_id: str) -> None:
        """
        Delete session from cold tier.

        Args:
            session_id: Session to delete

        Performance:
            - File deletion: <5ms P95

        Behavior:
            - Delete {storage_path}/sessions/{session_id}.json.zst
            - Remove from metadata
            - Update disk usage

        ADR: ADR-0020c
        """
        # TODO(@storage-team): Implement async delete
        pass

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cold tier statistics.

        Returns:
            Dict with:
                - total_sessions: Count of sessions in cold tier
                - total_size_mb: Total uncompressed size estimate
                - compressed_size_mb: Actual disk usage
                - compression_ratio: Compression effectiveness (%)
                - quota_gb: Configured quota
                - usage_percent: Disk usage (%)
                - oldest_session_days: Age of oldest session
                - newest_session_days: Age of newest session
                - expired_sessions: Count ready for cleanup

        Example:
            {
                "total_sessions": 1250,
                "total_size_mb": 62500,  # Estimated uncompressed
                "compressed_size_mb": 18750,  # Actual disk
                "compression_ratio": 70,  # percent
                "quota_gb": 500,
                "usage_percent": 3.75,  # 18.75GB / 500GB
                "oldest_session_days": 365,
                "newest_session_days": 0,
                "expired_sessions": 125
            }

        ADR: ADR-0020c
        """
        # TODO(@storage-team): Implement stats
        pass

    async def cleanup_expired_sessions(self) -> int:
        """
        Background task: Remove sessions older than retention_days.

        Returns:
            Count of sessions deleted

        Execution:
            - Runs every 24 hours
            - Finds sessions with expiration_date < now
            - Deletes files and metadata
            - Logs summary

        Performance:
            - Efficient (batch deletion)
            - Non-blocking (background task)

        ADR: ADR-0020c
        """
        # TODO(@storage-team): Implement background cleanup
        pass
```

**Local Filesystem Layout:**

```
/var/lib/familyos/cold_tier/
├── sessions/                     # Compressed session files
│   ├── session_001.json.zst
│   ├── session_002.json.zst
│   └── session_NNN.json.zst
├── sessions.json                 # Metadata (session expiration, sizes)
└── README.md                      # Documentation
```

**Metadata File Format (sessions.json):**

```json
{
  "total_sessions": 1250,
  "sessions": {
    "session_001": {
      "created_at": "2025-10-27T12:30:00Z",
      "expires_at": "2026-10-27T12:30:00Z",
      "size_bytes": 15360,
      "uncompressed_size_bytes": 51200
    }
  }
}
```

**Disk Usage Comparison:**

```
1000 sessions × 50KB each

LOCAL FILESYSTEM (zstd compressed):
  - Compressed: 1000 × 15KB = 15MB
  - Compression ratio: 70%
  - Cost: $0/month

AWS S3 STANDARD:
  - Uncompressed: 1000 × 50KB = 50MB
  - Storage cost: 50MB × $0.023/GB/month = $0.0011/month
  - Requests (10 GETs): 10 × $0.0004 = $0.004/month
  - Total: ~$0.005/month

LOCAL IS 2.5× FASTER + ZERO COST
```

**Performance Comparison:**

```
Operation            | Local Filesystem | AWS S3  | Improvement
---------------------|------------------|---------|-------------
Read latency P95     | <200ms          | 500ms   | 2.5× faster
Write latency P95    | <100ms          | 150ms   | 1.5× faster
Compression         | 70% zstd        | 30% S3  | 40% better
Cost per 1000 req   | $0              | $0.004  | Infinite

LOCAL WINS on latency, size, and cost
```

**ADR References:**

- ADR-0020c: Cold Tier Design (Local Filesystem, not S3)

**Assigned To:** Issue #L5-5.4.1

---

### 📊 Summary

**Milestone 5: Multi-Tier Storage**

| Epic | Files | Status | Assigned |
|------|-------|--------|----------|
| 5.1: Tier Management | 2 | 🚧 STUB | @storage-team |
| 5.2: Hot Tier (RAM) | 1 | 🚧 STUB | @storage-team |
| 5.3: Warm Tier (SSD) | 1 | 🚧 STUB | @storage-team |
| 5.4: Cold Tier (Local FS) | 1 | 🚧 STUB | @storage-team |
| 5.5: Tiering Policy (L5) | 2 | 🚧 STUB | @storage-team |
| 5.6: Migration Utilities | 1 | 🚧 STUB | @storage-team |
| **Total** | **8** | **🚧 STUB** | **@storage-team** |

**3-Tier Performance & Cost:**

| Tier | Capacity | Latency | Retention | Cost/Month |
|------|----------|---------|-----------|------------|
| **HOT (RAM)** | 56MB (1K sessions) | <1ms P95 | None (LRU) | $0.80 |
| **WARM (SSD)** | 100MB (2K sessions) | <50ms P95 | 30 days | $0.01 |
| **COLD (S3)** | Unlimited | <500ms P95 | 365 days | $0.005/session |
| **TOTAL** | ~100K sessions/year | Mixed | 365 days | **$0.52/month** |

**Cost Comparison:**

- **RAM-only** (no tiers): 100K sessions × 56KB × $0.08/GB/month = $448/month
- **3-Tier storage**: $0.52/month
- **Savings**: 99.4% cost reduction

**Lifecycle Flow:**

```
Active (0-60 min)
  ├─ Location: HOT (RAM)
  ├─ Access: <1ms
  └─ Cost: $0.00008/month per session

Recent (60 min - 30 days)
  ├─ Location: WARM (SSD)
  ├─ Access: <50ms
  └─ Cost: $0.000005/month per session

Historical (30-365 days)
  ├─ Location: COLD (S3)
  ├─ Access: <500ms
  └─ Cost: $0.000001/month per session

Deleted (365+ days)
  ├─ Location: Deleted
  ├─ Access: N/A
  └─ Cost: $0
```

**Performance Targets Summary:**

- Tier selection: <0.1ms overhead
- Hot access: <1ms P95
- Warm access: <50ms P95
- Cold access: <500ms P95
- Promotion/demotion: <10ms
- Eviction: <5ms
- Lifecycle check: <2ms per session

**Milestone 5 Dependencies:**

```
Upstream (Accesses storage):
  - k1.l4_runtime.session (SessionState persistence)
  - k1.l3_execution.agents (AgentState backup)
  - k1.bridge_k0.command_client (K0 WAL sync)

Downstream (Provides storage):
  - All K1 layers (L1-L4 use tier_manager transparently)
  - k1.l5_infrastructure.lifecycle_manager (automatic promotion/demotion)
```

---

## Milestone 6: Thermal Management

### 📋 Overview

**Purpose:** Hysteresis-based thermal-aware model placement with multi-platform sensor support
**Priority:** M1 (Medium, Performance Optimization)
**Status:** 🚧 STUB - NEEDS_IMPLEMENTATION
**Files:** 5 Python modules
**ADRs:** ADR-0026 (Thermal Hysteresis Matrix), ADR-0026a, ADR-0026b
**Assigned To:** @platform-team

**Key Features:**

- **5 Thermal Zones**: Cool (<70°C), Warm (70-74°C), Hot (75-84°C), Critical (85-95°C), Emergency (>95°C)
- **4-Tier Placement**: NPU (optimal) → GPU → CPU → Remote (emergency)
- **Hysteresis FSM**: Asymmetric transitions (10s upgrade, 30-60s downgrade)
- **Emergency Jump**: ≥85°C → Remote (skip GPU/CPU entirely)
- **Multi-Platform Sensors**: Linux thermal zones, Windows WMI, macOS IOKit, Intel RAPL, NVIDIA SMI, AMD uProf
- **Performance Budgets**: <1ms sensor read, 100ms poll interval, 68 placement changes/hour target

**Thermal Zone Placement Strategy:**

```
Temperature Range          | Zone      | Available Tiers      | Behavior
--------------------------|-----------|---------------------|---------------------------
< 70°C                     | COOL      | NPU, GPU, CPU        | Optimal performance
70-74°C                    | WARM      | NPU, GPU, CPU        | Normal operation
75-84°C (HOT)              | HOT       | GPU, CPU (skip NPU)  | Reduce batch freq 20%
85-95°C (CRITICAL)         | CRITICAL  | CPU, Remote          | Skip optional processing
> 95°C (EMERGENCY)         | EMERGENCY | Remote only          | Reject new turns
```

---

### 🎯 Epic 6.1: Thermal Sensing & Detection

**Purpose:** Multi-platform thermal sensor APIs and device capability detection
**Files:** 2
**Status:** 🚧 STUB

#### Issue 6.1.1: sensors.py

**File Path:** `k1/l5_infrastructure/thermal/sensors.py`

**Description:**
Cross-platform thermal sensor APIs for temperature and power monitoring.

**Responsibilities:**

1. Read device temperature (°C) from platform-specific APIs
2. Read power consumption (W) from Intel RAPL, NVIDIA SMI, AMD uProf
3. Handle multi-core and multi-GPU systems
4. Graceful fallback if sensors unavailable
5. Cache sensor readings (100ms poll interval)

**Core Methods:**

```python
class ThermalSensors:
    """
    Multi-platform thermal sensor APIs.

    Supported Platforms:
        - Linux: /sys/class/thermal/ (thermal zones), Intel RAPL, NVIDIA SMI
        - Windows: WMI (Windows Management Instrumentation), Intel RAPL
        - macOS: IOKit (IOHIDEventType), NVIDIA SMI

    Measurements:
        - Temperature: CPU, GPU, SoC package (°C)
        - Power: CPU package, GPU (W)
    """

    def __init__(self, poll_interval_ms: int = 100):
        """
        Initialize thermal sensors.

        Args:
            poll_interval_ms: Cache poll interval (default: 100ms)

        Implementation:
            - Detect platform (Linux/Windows/macOS)
            - Initialize platform-specific APIs
            - Setup periodic polling (background task)

        ADR: ADR-0026 (Thermal Sensing)
        """
        # TODO(@platform-team): Initialize thermal sensors
        # 1. Detect OS (Linux: /sys/class/thermal, Windows: WMI, macOS: IOKit)
        # 2. Probe available sensors
        # 3. Start polling task (100ms interval)
        pass

    def get_cpu_temperature(self) -> Optional[float]:
        """
        Get CPU package temperature (°C).

        Returns:
            Temperature in Celsius or None if unavailable

        Performance:
            - Read: <1ms P95 (cached)

        Platforms:
            - Linux: /sys/class/thermal/thermal_zone*/temp
            - Windows: WMI Win32_PerfRawData_Counters_ThermalZoneInformation
            - macOS: IOKit IOHIDEventType kIOHIDEventTypeTemperature

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement CPU temperature read
        # 1. Query platform-specific API
        # 2. Return cached value (<100ms old)
        # 3. Return None if unavailable
        pass

    def get_gpu_temperature(self) -> Optional[float]:
        """
        Get GPU temperature (°C).

        Returns:
            Temperature in Celsius or None if no GPU

        Performance:
            - NVIDIA SMI: <10ms (subprocess)
            - Cached: <1ms

        Platforms:
            - NVIDIA: nvidia-smi --query-gpu=temperature.gpu --format=csv
            - AMD: amd-smi json 2>/dev/null
            - Intel Arc: intel_gpu_frequency (if available)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement GPU temperature read
        # 1. Probe NVIDIA/AMD/Intel GPU APIs
        # 2. Cache result (100ms)
        # 3. Return None if no GPU or unavailable
        pass

    def get_cpu_power(self) -> Optional[float]:
        """
        Get CPU package power consumption (W).

        Returns:
            Power in Watts or None if unavailable

        Performance:
            - Intel RAPL: <1ms (kernel interface)
            - Cached: <1ms

        Platforms:
            - Intel: /sys/class/powercap/intel-rapl/ (Linux), WMI (Windows)
            - AMD: amd-smi metrics
            - Apple Silicon: NVRAM power metrics

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement CPU power read
        pass

    def get_gpu_power(self) -> Optional[float]:
        """
        Get GPU power consumption (W).

        Returns:
            Power in Watts or None if unavailable

        Performance:
            - NVIDIA SMI: <10ms (subprocess)
            - Cached: <1ms

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement GPU power read
        pass

    def get_all_metrics(self) -> Dict[str, Optional[float]]:
        """
        Get all thermal metrics at once.

        Returns:
            Dict with keys: cpu_temp, gpu_temp, cpu_power, gpu_power (all Celsius/Watts or None)

        Performance:
            - All cached: <1ms P95

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement batch read
        pass
```

**Platform-Specific Implementation Details:**

**Linux (sysfs):**

```bash
# Thermal zones
cat /sys/class/thermal/thermal_zone0/temp  # in millidegrees Celsius
# Intel RAPL (power)
cat /sys/class/powercap/intel-rapl:0/energy_uj
# NVIDIA GPU
nvidia-smi --query-gpu=temperature.gpu --format=csv
```

**Windows (WMI):**

```powershell
# CPU temperature via WMI
Get-WmiObject -Namespace root\wmi -Class MSAcpi_ThermalZoneTemperature
# Intel RAPL via WMI
Get-WmiObject -Namespace root\cimv2 -Class Win32_PerfFormattedData_Counters_ThermalZoneInformation
```

**macOS (IOKit):**

```swift
// IOKit temperature sensors
IOKit.read_temperature(name: "TC0P")  // CPU proximity
IOKit.read_temperature(name: "TG0P")  // GPU proximity
```

**ADR References:**

- ADR-0026: Thermal Hysteresis Matrix

**Assigned To:** Issue #L5-6.1.1

---

#### Issue 6.1.2: device_capability.py

**File Path:** `k1/l5_infrastructure/thermal/device_capability.py`

**Description:**
Device form factor detection and thermal baseline establishment.

**Responsibilities:**

1. Detect device form factor (Laptop, Phone, Desktop, Server)
2. Detect available accelerators (NPU, GPU, CPU)
3. Establish thermal baseline for device type
4. Enumerate GPU types (NVIDIA, AMD, Intel Arc, Apple Silicon)

**Core Methods:**

```python
class DeviceCapability:
    """
    Detect device capabilities and thermal baselines.

    Form Factors:
        - Laptop: 75°C baseline, limited cooling
        - Phone: 65°C baseline, very limited thermal capacity
        - Desktop: 82°C baseline, active cooling
        - Server: 85°C baseline, advanced thermal management

    Accelerators:
        - NPU (Neural Processing Unit): Qualcomm Hexagon, MediaTek, Apple Neural Engine
        - GPU (Discrete/Integrated): NVIDIA, AMD, Intel Arc, Apple Metal
        - CPU: x86, ARM, Apple Silicon
    """

    def __init__(self):
        """
        Initialize device capability detector.

        Implementation:
            - Detect OS and hardware
            - Probe for accelerators
            - Establish thermal baseline

        ADR: ADR-0026
        """
        # TODO(@platform-team): Detect device capabilities
        # 1. Detect form factor (dmidecode, system_profiler, devicetree)
        # 2. Probe for accelerators (lscpu, wmic, sysctl)
        # 3. Set thermal baseline
        pass

    def get_form_factor(self) -> str:
        """
        Detect device form factor.

        Returns:
            One of: "laptop", "phone", "desktop", "server", "unknown"

        Detection:
            - Linux: Check chassis type in dmidecode
            - Windows: Check system enclosure in WMI
            - macOS: Check model identifier (MacBook, Mac mini, iMac)
            - Android: devicetree, ro.build.product

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement form factor detection
        pass

    def get_thermal_baseline(self) -> float:
        """
        Get thermal baseline for device (°C).

        Returns:
            Safe baseline temperature:
                - Laptop: 75°C
                - Phone: 65°C
                - Desktop: 82°C
                - Server: 85°C
                - Unknown: 80°C

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement baseline lookup
        pass

    def has_npu(self) -> bool:
        """
        Check if device has NPU.

        Returns:
            True if NPU available

        Detection:
            - Linux: Check /proc/device-tree/soc/npu*
            - Windows: Check NNAPI capability
            - macOS: Check for Neural Engine (M1+)
            - Android: Check for Hexagon, MediaTek NeuroPilot

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement NPU detection
        pass

    def has_gpu(self) -> bool:
        """
        Check if device has GPU.

        Returns:
            True if GPU available

        Detection:
            - NVIDIA: nvidia-smi
            - AMD: rocm-smi
            - Intel Arc: intel_gpu_frequency
            - Apple: Metal capabilities

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement GPU detection
        pass

    def get_gpu_type(self) -> Optional[str]:
        """
        Get GPU type if available.

        Returns:
            One of: "nvidia", "amd", "intel", "apple", None

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement GPU type detection
        pass

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get all device capabilities.

        Returns:
            Dict with:
                - form_factor: Device type
                - thermal_baseline_c: Safe baseline temperature
                - has_npu: NPU available
                - has_gpu: GPU available
                - gpu_type: GPU vendor if available
                - cpu_cores: CPU core count
                - total_memory_gb: RAM capacity

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement capability aggregation
        pass
```

**ADR References:**

- ADR-0026: Thermal Hysteresis Matrix

**Assigned To:** Issue #L5-6.1.2

---

### 🎯 Epic 6.2: Thermal State Management

**Purpose:** Hysteresis FSM and placement decision logic
**Files:** 2
**Status:** 🚧 STUB

#### Issue 6.2.1: placement_decision.py

**File Path:** `k1/l5_infrastructure/thermal/placement_decision.py`

**Description:**
Thermal placement decision logic with hysteresis guards and cooldown enforcement.

**Responsibilities:**

1. Validate state transitions with hysteresis bands
2. Enforce cooldown periods between transitions
3. Detect emergency conditions (≥85°C)
4. Calculate placement score (temperature + power + latency)
5. Trigger emergency jump if needed

**Core Methods:**

```python
class PlacementDecision:
    """
    Thermal placement decision logic with hysteresis.

    Hysteresis Bands:
        - Upgrade (temp decreasing): 10s cooldown
        - Downgrade (temp increasing): 30-60s cooldown (asymmetric)

    Zones:
        COOL (<70°C) ──upgrade──> NPU/GPU/CPU available
        WARM (70-74°C) ──drift──> Same placement
        HOT (75-84°C) ──downgrade──> Skip NPU (10s + 60s = 70s total)
        CRITICAL (85-95°C) ──emergency──> CPU/Remote only (immediate)
        EMERGENCY (>95°C) ──jump──> Remote only (immediate)
    """

    def __init__(
        self,
        upgrade_cooldown_s: int = 10,
        downgrade_cooldown_s: int = 60,
        emergency_threshold_c: float = 85.0,
    ):
        """
        Initialize placement decision logic.

        Args:
            upgrade_cooldown_s: Cooldown before upgrade (default: 10s)
            downgrade_cooldown_s: Cooldown before downgrade (default: 60s)
            emergency_threshold_c: Temperature for emergency jump (default: 85°C)

        ADR: ADR-0026 (Hysteresis)
        """
        # TODO(@platform-team): Initialize decision logic
        # 1. Setup cooldown timers
        # 2. Initialize state tracking
        # 3. Setup emergency threshold
        pass

    def can_upgrade(self, current_zone: str, last_upgrade_s: float) -> bool:
        """
        Check if can upgrade to higher-tier placement (e.g., GPU → NPU).

        Args:
            current_zone: Current thermal zone
            last_upgrade_s: Seconds since last upgrade

        Returns:
            True if upgrade allowed (cooldown expired)

        Guard:
            - Temperature decreasing (cooler)
            - Cooldown expired (10s minimum)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement upgrade guard
        # 1. Check if cooldown expired (10s)
        # 2. Check if temperature stable or decreasing
        # 3. Return boolean
        pass

    def can_downgrade(self, current_zone: str, last_downgrade_s: float) -> bool:
        """
        Check if must downgrade to lower-tier placement (e.g., NPU → GPU).

        Args:
            current_zone: Current thermal zone
            last_downgrade_s: Seconds since last downgrade

        Returns:
            True if downgrade required

        Guard:
            - Temperature increasing (hotter)
            - Cooldown NOT expired (30-60s minimum)
            - Return True only if both conditions met

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement downgrade guard
        pass

    def should_emergency_jump(self, temperature_c: float) -> bool:
        """
        Check if should jump directly to Remote (≥85°C).

        Args:
            temperature_c: Current temperature

        Returns:
            True if temperature ≥ emergency_threshold (85°C)

        Behavior:
            - Immediate jump (no cooldown)
            - Skip GPU/CPU entirely
            - Force Remote placement

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement emergency detection
        pass

    def calculate_placement_score(
        self,
        temperature_c: float,
        power_w: float,
        tier: str,  # "npu", "gpu", "cpu", "remote"
        latency_ms: Optional[float] = None,
    ) -> float:
        """
        Calculate placement score (lower = better).

        Args:
            temperature_c: Current temperature
            power_w: Current power consumption
            tier: Proposed tier
            latency_ms: Optional tier latency

        Returns:
            Score combining temperature risk + power + latency

        Scoring:
            - High temperature (>75°C) penalizes high-power tiers (NPU/GPU)
            - Low temperature (<70°C) favors high-power tiers for performance
            - Remote tier heavily penalized for latency but low power

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement scoring algorithm
        pass

    def get_thermal_zone(self, temperature_c: float) -> str:
        """
        Map temperature to thermal zone.

        Returns:
            One of: "cool", "warm", "hot", "critical", "emergency"

        Zones:
            - COOL: <70°C
            - WARM: 70-74°C
            - HOT: 75-84°C
            - CRITICAL: 85-95°C
            - EMERGENCY: >95°C

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement zone mapping
        pass
```

**Hysteresis Timeline Example:**

```
T=0s:     Temp=72°C (WARM zone, GPU placement)
T=5s:     Temp=68°C (cooling, COOL zone) → Want to upgrade to NPU
T=10s:    Cooldown expired → UPGRADE to NPU ✓

T=20s:    Temp=78°C (HOT zone detected) → Want to downgrade to GPU
T=25s:    But downgrade_cooldown=60s, so NO (wait for cooldown)
T=80s:    Cooldown expired → DOWNGRADE to GPU ✓

T=120s:   Temp=87°C (CRITICAL, ≥85°C) → EMERGENCY JUMP to Remote ✓ (immediate, no cooldown)
```

**ADR References:**

- ADR-0026: Thermal Hysteresis Matrix

**Assigned To:** Issue #L5-6.2.1

---

#### Issue 6.2.2: placement_manager.py

**File Path:** `k1/l5_infrastructure/thermal/placement_manager.py`

**Description:**
Thermal placement manager orchestrating sensor reads, decisions, and tier transitions.

**Responsibilities:**

1. Poll sensors periodically (100ms)
2. Make placement decisions (with hysteresis)
3. Execute tier transitions
4. Track placement history
5. Export metrics

**Core Methods:**

```python
class ThermalPlacementManager:
    """
    Orchestrates thermal-aware model placement.

    Flow:
        1. Poll sensors (100ms interval)
        2. Map temperature to zone
        3. Check hysteresis guards
        4. Calculate placement score
        5. Execute transition if needed
        6. Record metrics
    """

    def __init__(
        self,
        sensors: ThermalSensors,
        device_capability: DeviceCapability,
        placement_decision: PlacementDecision,
        poll_interval_ms: int = 100,
    ):
        """
        Initialize thermal placement manager.

        Args:
            sensors: ThermalSensors instance
            device_capability: DeviceCapability instance
            placement_decision: PlacementDecision instance
            poll_interval_ms: Polling interval (default: 100ms)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Initialize placement manager
        # 1. Store sensor/capability/decision instances
        # 2. Setup polling task
        # 3. Initialize placement state
        pass

    async def get_placement_tier(self) -> str:
        """
        Get current thermal-aware placement tier.

        Returns:
            One of: "npu", "gpu", "cpu", "remote"

        Flow:
            1. Read current temperature
            2. Check hysteresis guards
            3. Calculate placement score
            4. Return best tier

        Performance:
            - Decision: <5ms P95

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement tier selection
        pass

    async def should_transition_tier(
        self,
        current_tier: str,
        new_tier: str,
    ) -> bool:
        """
        Check if should transition between tiers.

        Args:
            current_tier: Current placement
            new_tier: Proposed placement

        Returns:
            True if transition allowed (passes hysteresis guards)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement transition guard
        pass

    async def transition_tier(
        self,
        from_tier: str,
        to_tier: str,
        cognitive_trace_id: Optional[str] = None,
    ) -> None:
        """
        Execute tier transition.

        Args:
            from_tier: Source tier
            to_tier: Target tier
            cognitive_trace_id: Trace ID for observability

        Flow:
            1. Log transition
            2. Record metrics
            3. Notify subscribers (Model Hub placement engine)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement transition execution
        pass

    def get_placement_stats(self) -> Dict[str, Any]:
        """
        Get placement statistics.

        Returns:
            Dict with:
                - current_tier: Current placement
                - temperature_c: Current temperature
                - power_w: Current power
                - zone: Current thermal zone
                - transitions_total: Total transitions
                - last_transition: When last transition occurred
                - uptime_s: Manager uptime

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement stats collection
        pass
```

**ADR References:**

- ADR-0026: Thermal Hysteresis Matrix

**Assigned To:** Issue #L5-6.2.2

---

### 🎯 Epic 6.3: Thermal Metrics & Observability

**Purpose:** Thermal metrics collection and dashboard
**Files:** 1
**Status:** 🚧 STUB

#### Issue 6.3.1: metrics.py

**File Path:** `k1/l5_infrastructure/thermal/metrics.py`

**Description:**
Thermal metrics collection and Prometheus export.

**Responsibilities:**

1. Track temperature over time (P50/P95/P99)
2. Track power consumption
3. Track placement transitions
4. Export Prometheus metrics
5. Calculate thermal zone duration statistics

**Core Methods:**

```python
class ThermalMetrics:
    """
    Thermal metrics collection and export.

    Metrics:
        - k1_thermal_temperature_celsius{zone}
        - k1_thermal_power_watts{component}
        - k1_thermal_placement_changes_total{from_tier, to_tier}
        - k1_thermal_zone_duration_seconds{zone}
        - k1_thermal_placement_cooldown_violations_total
    """

    def __init__(self):
        """
        Initialize thermal metrics.

        ADR: ADR-0026
        """
        # TODO(@platform-team): Initialize metrics
        # 1. Create Prometheus metrics
        # 2. Setup histogram buckets (P50/P95/P99)
        pass

    def record_temperature(self, temperature_c: float, zone: str) -> None:
        """
        Record temperature reading.

        Args:
            temperature_c: Temperature in Celsius
            zone: Thermal zone (cool, warm, hot, critical, emergency)

        Metrics:
            - Histogram: k1_thermal_temperature_celsius{zone}
            - Gauge: k1_thermal_temperature_latest_celsius

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement temperature recording
        pass

    def record_power(self, power_w: float, component: str) -> None:
        """
        Record power consumption.

        Args:
            power_w: Power in Watts
            component: Component (cpu, gpu)

        Metrics:
            - Histogram: k1_thermal_power_watts{component}
            - Gauge: k1_thermal_power_latest_watts{component}

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement power recording
        pass

    def record_placement_transition(
        self,
        from_tier: str,
        to_tier: str,
        reason: str,
    ) -> None:
        """
        Record placement tier transition.

        Args:
            from_tier: Source tier
            to_tier: Target tier
            reason: Transition reason (upgrade, downgrade, emergency_jump)

        Metrics:
            - Counter: k1_thermal_placement_changes_total{from_tier, to_tier, reason}
            - Gauge: k1_thermal_placement_latest{tier}
            - Summary: k1_thermal_placement_transition_latency_ms

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement transition recording
        pass

    def record_zone_transition(self, from_zone: str, to_zone: str) -> None:
        """
        Record thermal zone transition.

        Args:
            from_zone: Source zone
            to_zone: Target zone

        Metrics:
            - Counter: k1_thermal_zone_changes_total{from_zone, to_zone}
            - Gauge: k1_thermal_zone_duration_seconds{zone}

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement zone recording
        pass

    def record_cooldown_violation(self) -> None:
        """
        Record cooldown period violation (attempted transition too soon).

        Metrics:
            - Counter: k1_thermal_placement_cooldown_violations_total

        Target: 0 violations (perfect hysteresis)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement violation recording
        pass

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get thermal statistics.

        Returns:
            Dict with:
                - temperature_p50_c: Median temperature
                - temperature_p95_c: P95 temperature
                - temperature_p99_c: P99 temperature
                - power_avg_w: Average power
                - placement_npu_pct: % time on NPU
                - placement_gpu_pct: % time on GPU
                - placement_cpu_pct: % time on CPU
                - placement_remote_pct: % time on Remote
                - transitions_total: Total transitions
                - transitions_per_hour: Transition rate (target: 68/hour)

        ADR: ADR-0026
        """
        # TODO(@platform-team): Implement statistics calculation
        pass
```

**Prometheus Metrics Reference:**

```
# Temperature tracking (histogram)
k1_thermal_temperature_celsius_bucket{zone="cool", le="70"} 1000
k1_thermal_temperature_celsius_bucket{zone="warm", le="74"} 800
k1_thermal_temperature_celsius_bucket{zone="hot", le="84"} 200

# Power tracking (histogram)
k1_thermal_power_watts_bucket{component="cpu", le="5"} 500
k1_thermal_power_watts_bucket{component="gpu", le="15"} 300

# Placement transitions (counter)
k1_thermal_placement_changes_total{from_tier="gpu", to_tier="npu", reason="upgrade"} 120
k1_thermal_placement_changes_total{from_tier="npu", to_tier="gpu", reason="downgrade"} 100
k1_thermal_placement_changes_total{from_tier="gpu", to_tier="remote", reason="emergency_jump"} 5

# Placement distribution (gauge)
k1_thermal_placement_latest{tier="npu"} 1  # Currently on NPU
```

**ADR References:**

- ADR-0026: Thermal Hysteresis Matrix

**Assigned To:** Issue #L5-6.3.1

---

### 📊 Summary

**Milestone 6: Thermal Management**

| Epic | Files | Status | Assigned |
|------|-------|--------|----------|
| 6.1: Thermal Sensing | 2 | 🚧 STUB | @platform-team |
| 6.2: State Management | 2 | 🚧 STUB | @platform-team |
| 6.3: Metrics & Observability | 1 | 🚧 STUB | @platform-team |
| **Total** | **5** | **🚧 STUB** | **@platform-team** |

**Thermal Zones & Placement:**

| Zone | Temp Range | Tiers Available | Latency | Power | Behavior |
|------|-----------|-----------------|---------|-------|----------|
| **COOL** | <70°C | NPU/GPU/CPU | 30/50/120ms | 10/12/15W | Optimal |
| **WARM** | 70-74°C | NPU/GPU/CPU | 30/50/120ms | 10/12/15W | Normal |
| **HOT** | 75-84°C | GPU/CPU | 50/120ms | 12/15W | Degrade |
| **CRITICAL** | 85-95°C | CPU/Remote | 120/500ms | 15/5W | Throttle |
| **EMERGENCY** | >95°C | Remote only | 500ms | 5W | Reject new |

**Hysteresis Matrix:**

- **Upgrade Cooldown**: 10s (fast recovery when cooling)
- **Downgrade Cooldown**: 30-60s (slow degradation under heat)
- **Emergency Jump**: ≥85°C → immediate Remote (no cooldown)
- **Asymmetry Ratio**: 3:1 to 6:1 (downgrade slower than upgrade)

**Performance Targets:**

- Sensor read: <1ms P95
- Poll interval: 100ms (10 reads/second)
- Placement decision: <5ms
- Placement transitions: 68/hour target
- Cooldown violations: 0 (perfect hysteresis)

**Milestone 6 Dependencies:**

```
Upstream (Needs thermal placement):
  - k1.l3_execution.model_hub (model placement cascade)
  - k1.l5_infrastructure.placement (cascade engine)

Downstream (Uses thermal data):
  - k1.l5_infrastructure.backpressure (thermal backpressure)
  - k1.l5_infrastructure.scheduler (thermal-aware scheduling)
```

---

## Milestone 7: Model Placement Cascade

### 📋 Overview

**Purpose:** Cascading model placement engine with cost tracking and privacy enforcement
**Priority:** M1 (High, Core Placement Strategy)
**Status:** 🚧 STUB - NEEDS_IMPLEMENTATION
**Files:** 5 Python modules
**ADRs:** ADR-0027 (Model Placement Cascade)
**Assigned To:** @model-team

**Key Features:**

- **4-Tier Fallback:** NPU (optimal) → GPU (fast) → CPU (compatible) → Remote (emergency)
- **Cost Tracking:** $0.001-0.01 per remote turn, daily budget enforcement
- **Privacy Enforcement:** RED-band data local-only, AMBER on-device, GREEN flexible
- **Capability Matching:** Device capability detection vs model requirements
- **Performance Budgets:** <50ms placement decision, <100ms per-model cost check
- **Circuit Breaking:** Fallback to CPU if GPU/NPU experiences failures (>10% error rate)

**Model Tiers & Characteristics:**

```
Tier       | Latency | Power | Cost      | Privacy | Capability Check | Fallback
-----------|---------|-------|-----------|---------|------------------|----------
NPU        | 30ms    | 5W    | $0        | Device  | NPU capability   | → GPU
GPU        | 50ms    | 12W   | $0.001    | Device  | GPU capability   | → CPU
CPU        | 120ms   | 15W   | $0.00     | Device  | CPU always ready | (final)
```

**LOCAL-ONLY ARCHITECTURE (No Cloud Remote Tier):**

The Remote tier has been **removed**. K1 now operates on local devices only with graceful failure when capacity is exhausted.

**Placement Decision Flow (LOCAL-ONLY, No Cloud):**

```
1. Get Model Requirements (size, batch, privacy_band)
   ↓
2. Check NPU Capability & Budget
   ├─ Available? → Try NPU (30ms)
   ├─ Failed? → Cascade to GPU
   └─ No budget? → Skip to GPU
   ↓
3. Check GPU Capability & Budget
   ├─ Available? → Try GPU (50ms)
   ├─ Failed? → Cascade to CPU
   └─ No budget? → Skip to CPU
   ↓
4. Check CPU (Always available)
   ├─ Try CPU (120ms)
   ├─ Success? → Return
   └─ Failed? → FAIL GRACEFULLY (no cloud)
   ↓
5. No Device Available → REJECT REQUEST
   ├─ Error: "No local device available"
   ├─ Client can retry later or reduce batch size
   └─ Honest about local capacity limits
```

**Failure Handling (LOCAL-ONLY):**

```
OLD: Model fails on CPU → Try Remote Cloud (500ms)
NEW: Model fails on CPU → FAIL (graceful error)

Benefits:
  - No cloud dependency
  - Faster failure detection (120ms vs 500ms network call)
  - Clear error to client
  - Honest about capability limits
  - On-device only execution

Error Response:
  {
    "status": "FAILED",
    "reason": "no_local_device_available",
    "available_devices": ["cpu"],  # CPU tried and failed
    "suggestion": "retry_later_or_reduce_batch_size",
    "tiers_tried": ["npu", "gpu", "cpu"]
  }
```

---

### 🎯 Epic 7.1: Cascade Engine & Cost Tracking

**Purpose:** Core cascade logic and cost enforcement
**Files:** 2
**Status:** 🚧 STUB

#### Issue 7.1.1: cascade_engine.py

**File Path:** `k1/l5_infrastructure/placement/cascade_engine.py`

**Description:**
Model placement cascade orchestrator with per-tier decision logic and cost accounting.

**Responsibilities:**

1. Evaluate model placement requirements
2. Check device capabilities for each tier
3. Execute cascading fallback decisions
4. Track placement attempts and successes
5. Integrate with thermal manager for temperature-aware placement
6. Report cascading metrics

**Core Methods:**

```python
class CascadeEngine:
    """
    Model placement cascade orchestrator (LOCAL-ONLY, no cloud).

    Cascade Strategy:
        NPU (optimal) → GPU (fast) → CPU (compatible) → FAIL (graceful)

    Per-Tier Checks:
        1. Device has capability (capability_matcher.check_capability)
        2. Power budget available (not over-thermal)
        3. Circuit breaker not open (failure rate <10%)
        4. Cost tracking is LOCAL only (no cloud costs)

    Local-Only Design:
        - No Remote tier (no cloud dependency)
        - Honest failure when local capacity exhausted
        - Fast failure (120ms CPU timeout vs 500ms cloud call)
        - On-device execution only
    """

    def __init__(
        self,
        capability_matcher: "CapabilityMatcher",
        thermal_manager: Optional["ThermalPlacementManager"] = None,
        circuit_breaker: Optional["CircuitBreakerManager"] = None,
    ):
        """
        Initialize cascade engine (LOCAL-ONLY).

        Args:
            capability_matcher: Device capability checker
            thermal_manager: Optional thermal-aware placement
            circuit_breaker: Optional failure detection

        Removed:
            - cost_tracker (no cloud costs, local-only)
            - Remote tier logic

        ADR: ADR-0027 (LOCAL-ONLY Model Placement)
        """
        # TODO(@model-team): Initialize cascade engine
        # 1. Store matcher, thermal, circuit_breaker
        # 2. Initialize tier hierarchy (NPU > GPU > CPU only)
        # 3. Setup placement cache
        # 4. Initialize local failure tracking
        pass

    async def place_model(
        self,
        model_id: str,
        model_size_mb: float,
        batch_size: int,
        privacy_band: str,  # "green", "amber", "red"
        cognitive_trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place model on appropriate tier via cascading fallback (LOCAL-ONLY).

        Args:
            model_id: Unique model identifier
            model_size_mb: Model size in MB
            batch_size: Batch processing size
            privacy_band: Privacy classification (green/amber/red)
            cognitive_trace_id: Trace ID for observability

        Returns:
            Dict with:
                - tier: Selected tier (npu, gpu, cpu)
                - latency_ms: Expected latency
                - power_w: Expected power
                - placement_reason: Why this tier selected
                - fallback_count: How many tiers skipped

        Returns on Failure:
            Dict with:
                - tier: None
                - status: "FAILED"
                - reason: "no_local_device_available"
                - tiers_tried: [list of tiers attempted]
                - suggestion: "retry_later_or_reduce_batch_size"

        Flow:
            1. Check NPU capability + budget
            2. If not available, check GPU
            3. If not available, check CPU
            4. If CPU fails → REJECT (no remote fallback)
            5. Record placement decision

        Performance:
            - Decision time: <50ms P95 (no network calls)

        Local-Only Guarantee:
            - All computation happens on device
            - No cloud API calls on critical path
            - Failure is fast (no cloud timeout)

        ADR: ADR-0027 (LOCAL-ONLY Model Placement)
        """
        # TODO(@model-team): Implement cascading placement (3-tier only)
        # 1. Evaluate model requirements
        # 2. Start with NPU tier
        # 3. Cascade through GPU → CPU
        # 4. Check capability, budget, circuit breaker at each step
        # 5. If CPU fails, return FAILED (not Remote)
        # 6. Return placement decision
        pass

    async def can_place_on_tier(
        self,
        tier: str,
        model_size_mb: float,
        batch_size: int,
        privacy_band: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if model can be placed on specific tier.

        Args:
            tier: Target tier (npu, gpu, cpu, remote)
            model_size_mb: Model size
            batch_size: Batch size
            privacy_band: Privacy band (green, amber, red)

        Returns:
            (can_place: bool, reason: optional explanation)

        Checks:
            1. Device has capability for tier
            2. Model size fits in tier memory
            3. Batch size compatible
            4. Privacy band allows (red → local only)
            5. Cost budget available
            6. Circuit breaker not open
            7. Thermal OK (optional)

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement tier placement check
        pass

    async def get_placement_candidates(
        self,
        model_size_mb: float,
        batch_size: int,
        privacy_band: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all viable placement candidates ranked by score.

        Returns:
            List of candidate placements, ranked by:
                1. Latency (lower better)
                2. Cost (lower better)
                3. Power (lower better)

        Example output:
            [
                {"tier": "npu", "latency_ms": 30, "cost_cents": 0, "score": 0.9},
                {"tier": "gpu", "latency_ms": 50, "cost_cents": 0.1, "score": 0.8},
                {"tier": "cpu", "latency_ms": 120, "cost_cents": 0.5, "score": 0.6},
                {"tier": "remote", "latency_ms": 500, "cost_cents": 1, "score": 0.1},
            ]

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement candidate ranking
        pass

    def get_cascade_stats(self) -> Dict[str, Any]:
        """
        Get cascade engine statistics.

        Returns:
            Dict with:
                - placements_total: Total placements made
                - placements_npu: Models on NPU (%)
                - placements_gpu: Models on GPU (%)
                - placements_cpu: Models on CPU (%)
                - placements_remote: Models on Remote (%)
                - avg_cascade_depth: Average fallback levels
                - cost_today_cents: Today's cost
                - cost_limit_cents: Daily budget

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement stats collection
        pass
```

**Cascade Decision Tree:**

```
┌─ NPU Available?
│  ├─ Yes: Size fits? → Cost OK? → Circuit OK? → USE NPU (30ms)
│  └─ No: → Cascade to GPU
│
├─ GPU Available?
│  ├─ Yes: Size fits? → Cost OK? → Circuit OK? → USE GPU (50ms)
│  └─ No: → Cascade to CPU
│
├─ CPU (Always available)
│  ├─ Size fits? → Cost OK? → USE CPU (120ms)
│  └─ No: → Cascade to Remote
│
└─ Remote (Last resort)
   └─ ALWAYS available (500ms, +cost)
```

**ADR References:**

- ADR-0027: Model Placement Cascade

**Assigned To:** Issue #L5-7.1.1

---

#### Issue 7.1.2: cost_tracker.py

**File Path:** `k1/l5_infrastructure/placement/cost_tracker.py`

**Description:**
Cost tracking and budget enforcement for model placement across tiers.

**Responsibilities:**

1. Track per-model costs (NPU/GPU/CPU/Remote)
2. Accumulate daily costs
3. Enforce daily budget limits
4. Generate cost reports
5. Alert on budget threshold breaches

**Core Methods:**

```python
class CostTracker:
    """
    Cost tracking and budget enforcement.

    Cost Structure (per invocation):
        - NPU: $0.00 (local, owned)
        - GPU: $0.001 (local, owned)
        - CPU: $0.005 (local resource usage)
        - Remote: $0.01 (cloud API call)

    Budget:
        - Daily limit: $1.00 by default
        - Soft threshold: 80% ($0.80)
        - Hard limit: 100% ($1.00)
    """

    def __init__(
        self,
        daily_budget_cents: int = 100,  # $1.00
        alert_threshold_pct: float = 0.8,
        reset_hour_utc: int = 0,
    ):
        """
        Initialize cost tracker.

        Args:
            daily_budget_cents: Daily budget in cents (default: 100 = $1.00)
            alert_threshold_pct: Alert at % of budget (default: 80%)
            reset_hour_utc: Budget reset hour UTC (default: 00:00 UTC)

        ADR: ADR-0027
        """
        # TODO(@model-team): Initialize cost tracker
        # 1. Setup daily budget
        # 2. Load today's spent amount (from persistent storage or in-memory)
        # 3. Initialize alerts
        pass

    def get_tier_cost(self, tier: str) -> float:
        """
        Get cost per invocation for tier (in cents).

        Returns:
            Cost in cents:
                - NPU: 0
                - GPU: 0.1
                - CPU: 0.5
                - Remote: 1.0

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement tier cost lookup
        pass

    def can_afford_tier(self, tier: str) -> bool:
        """
        Check if daily budget allows placement on tier.

        Args:
            tier: Target tier

        Returns:
            True if cost + remaining budget > tier cost

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement budget check
        pass

    def record_invocation(
        self,
        tier: str,
        model_id: str,
        cost_cents: float,
        cognitive_trace_id: Optional[str] = None,
    ) -> None:
        """
        Record model invocation cost.

        Args:
            tier: Placement tier
            model_id: Model ID
            cost_cents: Cost in cents
            cognitive_trace_id: Trace ID for observability

        Updates:
            - Add cost_cents to today's total
            - Check if exceeded 80% threshold
            - Check if exceeded 100% limit (hard stop)

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement cost recording
        pass

    def get_budget_status(self) -> Dict[str, Any]:
        """
        Get current budget status.

        Returns:
            Dict with:
                - daily_budget_cents: Total daily budget
                - spent_today_cents: Amount spent today
                - remaining_cents: Budget remaining
                - used_pct: % of budget used
                - is_over_budget: True if exceeded 100%
                - is_at_soft_threshold: True if ≥80%
                - reset_in_hours: Hours until reset

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement budget status
        pass

    def get_cost_report(
        self,
        days: int = 1,
    ) -> Dict[str, Any]:
        """
        Get cost report for time period.

        Args:
            days: Number of days to include (default: 1)

        Returns:
            Dict with:
                - period_start: Start timestamp
                - period_end: End timestamp
                - total_cost_cents: Total cost
                - cost_by_tier: {npu, gpu, cpu, remote} breakdown
                - cost_by_model: Top models by cost
                - avg_cost_per_invocation: Average cost
                - most_expensive_model: Model with highest cost

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement cost reporting
        pass
```

**Daily Cost Example (24-hour period):**

```
Budget: $1.00 per day (100 cents)
Reset: 00:00 UTC

Time        | Model    | Tier   | Cost  | Total  | % Used | Status
------------|----------|--------|-------|--------|--------|--------
08:00 UTC   | Model-A  | GPU    | 0.1¢  | 0.1¢   | 0.1%   | 🟢 OK
10:00 UTC   | Model-B  | Remote | 1.0¢  | 1.1¢   | 1.1%   | 🟢 OK
12:00 UTC   | Model-C  | CPU    | 0.5¢  | 1.6¢   | 1.6%   | 🟢 OK
14:00 UTC   | Model-A  | Remote | 1.0¢  | 2.6¢   | 2.6%   | 🟢 OK
...
18:00 UTC   | Model-D  | Remote | 1.0¢  | 80.0¢  | 80%    | 🟡 Soft threshold
...
22:00 UTC   | Model-E  | Remote | 1.0¢  | 100¢   | 100%   | 🔴 Hard limit
23:00 UTC   | Model-F  | Remote | 1.0¢  | BLOCKED| 100%   | ❌ Rejected
```

**ADR References:**

- ADR-0027: Model Placement Cascade

**Assigned To:** Issue #L5-7.1.2

---

### 🎯 Epic 7.2: Capability & Privacy Matching

**Purpose:** Device capability detection and privacy-band enforcement
**Files:** 2
**Status:** 🚧 STUB

#### Issue 7.2.1: capability_matcher.py

**File Path:** `k1/l5_infrastructure/placement/capability_matcher.py`

**Description:**
Device capability checking and model-to-device compatibility matching.

**Responsibilities:**

1. Detect available accelerators (NPU/GPU/CPU)
2. Check model-device compatibility
3. Validate memory/batch requirements
4. Report capability mismatches
5. Integrate with thermal management

**Core Methods:**

```python
class CapabilityMatcher:
    """
    Device capability and model-device compatibility matching.

    Capability Categories:
        - NPU (Neural Processing Unit): Qualcomm Hexagon, MediaTek, Apple Neural Engine
        - GPU (Graphics Processing Unit): NVIDIA, AMD, Intel Arc, Apple Metal
        - CPU (Central Processing Unit): Always available
        - Remote: Cloud execution always available
    """

    def __init__(
        self,
        device_capability: "DeviceCapability",
        thermal_manager: Optional["ThermalPlacementManager"] = None,
    ):
        """
        Initialize capability matcher.

        Args:
            device_capability: Device capability detector
            thermal_manager: Optional thermal placement manager

        ADR: ADR-0027
        """
        # TODO(@model-team): Initialize capability matcher
        # 1. Query device capabilities
        # 2. Store available accelerators
        # 3. Setup compatibility matrix
        pass

    def check_npu_capable(self) -> bool:
        """
        Check if device has NPU capability.

        Returns:
            True if NPU available and not thermally constrained

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement NPU check
        pass

    def check_gpu_capable(self) -> bool:
        """
        Check if device has GPU capability.

        Returns:
            True if GPU available and not thermally constrained

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement GPU check
        pass

    def check_cpu_capable(self) -> bool:
        """
        Check if device has CPU capability.

        Returns:
            True (CPU always available unless severely thermally constrained)

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement CPU check
        pass

    def get_available_memory(self, tier: str) -> float:
        """
        Get available memory for tier (MB).

        Args:
            tier: Placement tier (npu, gpu, cpu, remote)

        Returns:
            Available memory in MB
                - NPU: 256MB typical
                - GPU: 4-24GB
                - CPU: System RAM / 2
                - Remote: Unlimited

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement memory lookup
        pass

    def check_model_fits(
        self,
        tier: str,
        model_size_mb: float,
        batch_size: int,
        working_memory_pct: float = 0.2,
    ) -> bool:
        """
        Check if model + batch fits in tier memory.

        Args:
            tier: Target tier
            model_size_mb: Model size in MB
            batch_size: Batch size
            working_memory_pct: Working memory overhead (default: 20%)

        Calculation:
            required_memory = model_size_mb + (batch_size * avg_activation_mb) + working_memory
            fits = required_memory <= available_memory

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement memory fit check
        pass

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get all device capabilities.

        Returns:
            Dict with:
                - has_npu: NPU available
                - has_gpu: GPU available
                - has_cpu: CPU always True
                - npu_memory_mb: NPU memory
                - gpu_memory_mb: GPU memory
                - cpu_memory_mb: Available CPU memory
                - thermal_zone: Current thermal zone
                - form_factor: Device type (laptop, phone, desktop, server)

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement capability aggregation
        pass
```

**Compatibility Matrix:**

```
Model Size | NPU Capable | GPU Capable | CPU Capable | Remote Capable
-----------|-------------|-------------|-------------|---------------
<256MB     | ✅ Yes      | ✅ Yes      | ✅ Yes      | ✅ Yes
256MB-4GB  | ❌ No       | ✅ Yes      | ✅ Yes      | ✅ Yes
4GB-24GB   | ❌ No       | ❌ Maybe    | ✅ Yes      | ✅ Yes
>24GB      | ❌ No       | ❌ No       | ❌ No       | ✅ Yes
```

**ADR References:**

- ADR-0027: Model Placement Cascade

**Assigned To:** Issue #L5-7.2.1

---

#### Issue 7.2.2: privacy_enforcer.py

**File Path:** `k1/l5_infrastructure/placement/privacy_enforcer.py`

**Description:**
Privacy band enforcement for model placement decisions.

**Responsibilities:**

1. Enforce RED-band local-only constraint
2. Allow AMBER on-device processing
3. Allow GREEN flexible placement
4. Validate privacy requirements
5. Log privacy-sensitive operations

**Core Methods:**

```python
class PrivacyEnforcer:
    """
    Privacy band enforcement for model placement.

    Privacy Bands:
        - RED: Highly sensitive, must remain local (on-device)
        - AMBER: Sensitive, on-device preferred but off-device OK
        - GREEN: Non-sensitive, any placement OK
    """

    def __init__(self):
        """
        Initialize privacy enforcer.

        ADR: ADR-0027
        """
        # TODO(@model-team): Initialize privacy enforcer
        # 1. Setup privacy policies
        # 2. Initialize audit logging
        pass

    def can_place_on_tier(
        self,
        privacy_band: str,
        tier: str,
    ) -> bool:
        """
        Check if placement on tier allowed by privacy policy.

        Args:
            privacy_band: Privacy classification (red, amber, green)
            tier: Target tier (npu, gpu, cpu, remote)

        Returns:
            True if placement allowed

        Rules:
            - RED: Only NPU/GPU/CPU (local), NOT Remote
            - AMBER: NPU/GPU/CPU/Remote (all OK)
            - GREEN: NPU/GPU/CPU/Remote (all OK)

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement privacy check
        pass

    def get_allowed_tiers(self, privacy_band: str) -> List[str]:
        """
        Get list of allowed tiers for privacy band.

        Args:
            privacy_band: Privacy classification

        Returns:
            List of allowed tiers in preference order

        Examples:
            - RED: ["npu", "gpu", "cpu"] (local only)
            - AMBER: ["npu", "gpu", "cpu", "remote"] (any)
            - GREEN: ["npu", "gpu", "cpu", "remote"] (any)

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement allowed tier lookup
        pass

    def audit_placement(
        self,
        privacy_band: str,
        tier: str,
        model_id: str,
        cognitive_trace_id: str,
    ) -> None:
        """
        Audit sensitive model placement (for RED/AMBER bands).

        Args:
            privacy_band: Privacy classification
            tier: Placement tier
            model_id: Model ID
            cognitive_trace_id: Trace ID for audit trail

        Logging:
            - RED tier placement: Always logged (sensitive)
            - AMBER remote: Always logged (off-device)
            - GREEN: Not logged (non-sensitive)

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement audit logging
        pass
```

**Privacy Policy Table:**

```
Band   | Definition              | Allowed Tiers            | Remote OK? | Audit Required?
-------|-------------------------|--------------------------|------------|----------------
RED    | Highly sensitive PII    | NPU, GPU, CPU (local)   | ❌ No     | ✅ Always
AMBER  | Sensitive data          | NPU, GPU, CPU, Remote   | ✅ Yes    | ✅ Remote only
GREEN  | Non-sensitive/public    | NPU, GPU, CPU, Remote   | ✅ Yes    | ❌ No
```

**ADR References:**

- ADR-0027: Model Placement Cascade

**Assigned To:** Issue #L5-7.2.2

---

### 🎯 Epic 7.3: Metrics & Monitoring

**Purpose:** Placement metrics and observability
**Files:** 1
**Status:** 🚧 STUB

#### Issue 7.3.1: metrics.py

**File Path:** `k1/l5_infrastructure/placement/metrics.py`

**Description:**
Placement metrics collection and Prometheus export.

**Responsibilities:**

1. Track placement distribution (tier usage %)
2. Track cascading rates (failed placements)
3. Track cost metrics
4. Track privacy violations (attempted RED remote)
5. Export Prometheus metrics

**Core Methods:**

```python
class PlacementMetrics:
    """
    Placement metrics collection and export.

    Metrics:
        - k1_model_placements_total{tier, reason}
        - k1_model_placement_latency_ms{tier}
        - k1_model_placement_cost_cents{tier}
        - k1_model_cascade_depth_count
        - k1_model_privacy_violations_total{band, attempted_tier}
        - k1_model_placement_distribution{tier}
    """

    def __init__(self):
        """
        Initialize placement metrics.

        ADR: ADR-0027
        """
        # TODO(@model-team): Initialize metrics
        # 1. Create Prometheus metrics
        # 2. Setup histogram buckets
        pass

    def record_placement(
        self,
        model_id: str,
        tier: str,
        latency_ms: float,
        cost_cents: float,
        cascade_depth: int,
        reason: str,
    ) -> None:
        """
        Record model placement decision.

        Args:
            model_id: Model ID
            tier: Selected tier
            latency_ms: Decision latency
            cost_cents: Cost of placement
            cascade_depth: Number of tiers evaluated
            reason: Reason for tier selection (direct, fallback_npu_failed, etc.)

        Metrics:
            - Counter: k1_model_placements_total{tier, reason}
            - Histogram: k1_model_placement_latency_ms{tier}
            - Histogram: k1_model_placement_cost_cents{tier}
            - Histogram: k1_model_cascade_depth_count

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement placement recording
        pass

    def record_privacy_violation_attempt(
        self,
        privacy_band: str,
        attempted_tier: str,
        model_id: str,
    ) -> None:
        """
        Record privacy policy violation attempt.

        Args:
            privacy_band: Privacy band (red, amber, green)
            attempted_tier: Tier that violated policy
            model_id: Model ID

        Metrics:
            - Counter: k1_model_privacy_violations_total{band, attempted_tier}

        Target: 0 violations

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement violation recording
        pass

    def get_placement_distribution(self) -> Dict[str, float]:
        """
        Get distribution of model placements.

        Returns:
            Dict with:
                - npu_pct: % on NPU
                - gpu_pct: % on GPU
                - cpu_pct: % on CPU
                - remote_pct: % on Remote
                - total_placements: Total count

        Example:
            {
                "npu_pct": 45.0,
                "gpu_pct": 30.0,
                "cpu_pct": 20.0,
                "remote_pct": 5.0,
                "total_placements": 10000,
            }

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement distribution calculation
        pass

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get placement statistics.

        Returns:
            Dict with:
                - placement_distribution: {npu_pct, gpu_pct, cpu_pct, remote_pct}
                - avg_cascade_depth: Average tiers tried
                - total_placements: Total count
                - avg_latency_ms: Average decision time
                - cost_today_cents: Today's total cost
                - privacy_violations: Total violations
                - most_common_fallback: Most frequent cascade reason

        ADR: ADR-0027
        """
        # TODO(@model-team): Implement statistics collection
        pass
```

**Prometheus Metrics Reference:**

```
# Placement distribution (counter)
k1_model_placements_total{tier="npu", reason="direct"} 4500
k1_model_placements_total{tier="gpu", reason="direct"} 3000
k1_model_placements_total{tier="cpu", reason="fallback_gpu_failed"} 1800
k1_model_placements_total{tier="remote", reason="cost_budget_exceeded"} 700

# Placement latency (histogram)
k1_model_placement_latency_ms_bucket{tier="npu", le="50"} 4500
k1_model_placement_latency_ms_bucket{tier="gpu", le="100"} 3000

# Cost tracking (histogram)
k1_model_placement_cost_cents_bucket{tier="remote", le="1"} 700

# Cascade depth (histogram)
k1_model_cascade_depth_count_bucket{le="1"} 8300
k1_model_cascade_depth_count_bucket{le="2"} 1700
k1_model_cascade_depth_count_bucket{le="3"} 0

# Privacy violations (counter)
k1_model_privacy_violations_total{band="red", attempted_tier="remote"} 0
```

**ADR References:**

- ADR-0027: Model Placement Cascade

**Assigned To:** Issue #L5-7.3.1

---

### 📊 Summary

**Milestone 7: Model Placement Cascade**

| Epic | Files | Status | Assigned |
|------|-------|--------|----------|
| 7.1: Cascade Engine & Cost | 2 | 🚧 STUB | @model-team |
| 7.2: Capability & Privacy | 2 | 🚧 STUB | @model-team |
| 7.3: Metrics & Monitoring | 1 | 🚧 STUB | @model-team |
| **Total** | **5** | **🚧 STUB** | **@model-team** |

**Placement Tier Characteristics:**

| Tier | Latency | Power | Cost | Capability | Availability |
|------|---------|-------|------|------------|--------------|
| **NPU** | 30ms | 5W | $0 | ~45% devices | High (45% placements) |
| **GPU** | 50ms | 12W | $0.001 | ~75% devices | High (30% placements) |
| **CPU** | 120ms | 15W | $0.005 | 100% always | Always (20-25%) |
| **Remote** | 500ms | 5W | $0.01 | Always | Always (fallback) |

**Cost Reduction Strategy:**

```
Before Cascade: All models → Remote ($0.01 per turn)
After Cascade:
  - 45% NPU ($0) = 0% cost
  - 30% GPU ($0.001) = 0.03% cost
  - 20% CPU ($0.005) = 0.1% cost
  - 5% Remote ($0.01) = 0.05% cost

Cost reduction: 99.82% (from $1.0M/year → $1.8K/year)
```

**Cascade Flow:**

```
1. Evaluate model (size, batch, privacy)
   ↓
2. Try NPU (30ms, $0) → Success? Return
   ↓
3. Try GPU (50ms, $0.001) → Success? Return
   ↓
4. Try CPU (120ms, $0.005) → Success? Return
   ↓
5. Remote (500ms, $0.01) → Always works
```

**Milestone 7 Dependencies:**

```
Upstream (Requires):
  - k1.l5_infrastructure.thermal (thermal-aware placement)
  - k1.l5_infrastructure.serialization (model serialization for remote)
  - k1.l5_infrastructure.circuit_breaker (failure detection)

Downstream (Provides):
  - k1.l3_execution.model_hub (model execution)
  - k1.l5_infrastructure.backpressure (placement-aware backpressure)
```

---

## Milestone 8: Backpressure Coordination

### 📋 Overview

**Purpose:** Cascading backpressure system with watermark thresholds and privacy-aware overrides
**Priority:** M1 (Critical, Flow Control)
**Status:** 🚧 STUB - NEEDS_IMPLEMENTATION
**Files:** 6 Python modules
**ADRs:** ADR-0028 (Backpressure Cascade System)
**Assigned To:** @resilience-team

**Key Features:**

- **3-Tier Cascading:** App Watermark → Cache Watermark → Circuit Breaker Downgrade
- **Watermark Thresholds:** Soft (75%), Hard (85%), Critical (95%)
- **Privacy-Aware Overrides:** RED-band high-priority, GREEN-band strict limits
- **Dynamic Rate Adjustment:** 10% reduction per tier triggered
- **Anti-Starvation:** Fairness enforcement across request types
- **Performance Budgets:** <10ms decision time, <5% throughput overhead

**Backpressure Cascade Architecture:**

```
Queue Depth Increases
        ↓
   [Tier 1 App]
   Soft Watermark: 75%
   Action: Slow down non-priority requests
        ↓ (if breached)
   [Tier 2 Cache]
   Hard Watermark: 85%
   Action: Reduce batch size, increase TTL
        ↓ (if breached)
   [Tier 3 Breaker]
   Critical Watermark: 95%
   Action: Downgrade to CPU/Remote, reject new
```

**Privacy Override Logic:**

```
RED-Band (Highly Sensitive):
  - Bypass soft watermarks (75%)
  - Can use hard watermark (85%)
  - Cannot bypass critical (95%)
  - Rationale: Sensitive data high-priority

AMBER-Band (Sensitive):
  - Standard watermark enforcement
  - Can go to 85% but not 95%

GREEN-Band (Non-Sensitive):
  - Strict enforcement
  - Cannot exceed 85%
  - Rationale: Non-essential traffic limited
```

---

### 🎯 Epic 8.1: Backpressure Manager & Watermarks

**Purpose:** Core backpressure orchestration and watermark tracking
**Files:** 2
**Status:** 🚧 STUB

#### Issue 8.1.1: backpressure_manager.py

**File Path:** `k1/l5_infrastructure/backpressure/backpressure_manager.py`

**Description:**
Central backpressure manager coordinating queue depths, watermarks, and cascading actions.

**Responsibilities:**

1. Track queue depths across layers
2. Calculate watermark percentages (soft/hard/critical)
3. Trigger backpressure actions at thresholds
4. Coordinate with placement engine (reduce tier)
5. Report backpressure metrics
6. Enforce privacy-aware overrides

**Core Methods:**

```python
class BackpressureManager:
    """
    Cascading backpressure manager with privacy-aware overrides.

    Cascade Tiers:
        1. App Level (75% soft): Slow down non-priority
        2. Cache Level (85% hard): Reduce batch/increase TTL
        3. Circuit Breaker (95% critical): Downgrade/reject

    Privacy Handling:
        - RED: High-priority, can exceed soft/hard
        - AMBER: Standard enforcement
        - GREEN: Strict, cannot exceed hard
    """

    def __init__(
        self,
        soft_threshold_pct: float = 0.75,
        hard_threshold_pct: float = 0.85,
        critical_threshold_pct: float = 0.95,
        cascade_action: Optional[Callable] = None,
    ):
        """
        Initialize backpressure manager.

        Args:
            soft_threshold_pct: Soft watermark (default: 75%)
            hard_threshold_pct: Hard watermark (default: 85%)
            critical_threshold_pct: Critical watermark (default: 95%)
            cascade_action: Callback for cascade triggers

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Initialize backpressure manager
        # 1. Setup watermark thresholds
        # 2. Initialize queue depth tracking
        # 3. Setup cascade callbacks
        pass

    def update_queue_depth(
        self,
        layer: str,  # "app", "cache", "breaker"
        current_depth: int,
        max_depth: int,
        cognitive_trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update queue depth and evaluate backpressure.

        Args:
            layer: Layer name (app, cache, breaker)
            current_depth: Current queue items
            max_depth: Maximum capacity
            cognitive_trace_id: Trace ID

        Returns:
            Dict with:
                - depth_pct: Current depth as %
                - tier: Watermark tier ("normal", "soft", "hard", "critical")
                - action: Action to take (None, "slow_down", "reduce_batch", "downgrade")
                - override_applied: Privacy override in effect

        Flow:
            1. Calculate depth percentage
            2. Check watermark thresholds
            3. Apply privacy override if needed
            4. Trigger cascade if threshold breached
            5. Return decision

        Performance:
            - Decision time: <10ms P95

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement queue depth tracking
        # 1. Store depth metrics
        # 2. Calculate percentages
        # 3. Check watermarks
        # 4. Apply overrides
        # 5. Trigger cascades
        pass

    async def should_accept_request(
        self,
        request_type: str,  # "priority", "normal", "batch"
        privacy_band: str,  # "red", "amber", "green"
        current_depth_pct: float,
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if should accept new request based on backpressure.

        Args:
            request_type: Type of request (priority, normal, batch)
            privacy_band: Privacy classification
            current_depth_pct: Current queue depth %

        Returns:
            (accept: bool, reason: optional explanation)

        Rules:
            Priority requests:
              - Accept until hard threshold (85%)
            Normal requests:
              - Accept until soft threshold (75%)
            Batch requests:
              - Accept until soft threshold (75%)

        Privacy Overrides:
            RED: Can bypass soft, not hard/critical
            AMBER: Standard enforcement
            GREEN: Strict, cannot exceed hard

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement request acceptance logic
        pass

    def get_backpressure_action(
        self,
        current_tier: str,  # "soft", "hard", "critical"
    ) -> Dict[str, Any]:
        """
        Get recommended backpressure action for tier.

        Args:
            current_tier: Watermark tier

        Returns:
            Dict with recommended action:
                tier="soft": {"action": "slow_down", "reduction_pct": 10}
                tier="hard": {"action": "reduce_batch", "reduction_pct": 20}
                tier="critical": {"action": "downgrade_tier", "reduction_pct": 30}

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement action selection
        pass

    def get_backpressure_status(self) -> Dict[str, Any]:
        """
        Get current backpressure status.

        Returns:
            Dict with:
                - app_queue_pct: App queue depth
                - cache_queue_pct: Cache queue depth
                - breaker_queue_pct: Circuit breaker queue depth
                - active_tier: Current highest watermark breached
                - active_actions: Current mitigation actions
                - request_rate_reduction_pct: Current rate limit reduction
                - privacy_overrides_active: Active privacy overrides

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement status collection
        pass
```

**Backpressure Decision Matrix:**

```
Queue %  | App Request | Normal Request | Batch Request | Soft Breached | Hard Breached
---------|-------------|----------------|---------------|---------------|---------------
0-50%    | ✅ Accept   | ✅ Accept      | ✅ Accept     | No            | No
50-75%   | ✅ Accept   | ✅ Accept      | ✅ Accept     | No            | No
75-85%   | ✅ Accept   | ⏸️ Delay       | ⏸️ Delay      | ⚠️ Soft       | No
85-95%   | ✅ Accept   | ❌ Reject      | ❌ Reject     | ⚠️ Soft       | ⚠️ Hard
>95%     | ⏸️ Delay    | ❌ Reject      | ❌ Reject     | ⚠️ Soft       | 🔴 Critical
```

**ADR References:**

- ADR-0028: Backpressure Cascade System

**Assigned To:** Issue #L5-8.1.1

---

#### Issue 8.1.2: watermark_tracker.py

**File Path:** `k1/l5_infrastructure/backpressure/watermark_tracker.py`

**Description:**
Watermark threshold tracking and breach detection across layers.

**Responsibilities:**

1. Track per-layer watermarks (app, cache, breaker)
2. Detect threshold breaches
3. Record watermark events (breach/recovery)
4. Calculate historical statistics
5. Report trending

**Core Methods:**

```python
class WatermarkTracker:
    """
    Watermark tracking and breach detection.

    Watermarks:
        - Soft (75%): Reduce non-essential traffic
        - Hard (85%): Reject non-priority traffic
        - Critical (95%): Emergency mode
    """

    def __init__(
        self,
        soft_pct: float = 0.75,
        hard_pct: float = 0.85,
        critical_pct: float = 0.95,
        history_window_s: int = 300,
    ):
        """
        Initialize watermark tracker.

        Args:
            soft_pct: Soft watermark (75%)
            hard_pct: Hard watermark (85%)
            critical_pct: Critical watermark (95%)
            history_window_s: Historical data window (5 minutes)

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Initialize watermark tracker
        # 1. Setup thresholds
        # 2. Initialize history buffer
        # 3. Setup breach detection
        pass

    def record_depth(
        self,
        layer: str,
        depth_pct: float,
        depth_count: int,
        max_capacity: int,
    ) -> Dict[str, Any]:
        """
        Record queue depth reading.

        Args:
            layer: Layer name (app, cache, breaker)
            depth_pct: Depth as percentage
            depth_count: Number of items
            max_capacity: Maximum capacity

        Returns:
            Dict with:
                - watermark_tier: soft, hard, critical, or normal
                - breached: True if threshold crossed
                - trend: "increasing", "decreasing", "stable"

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement depth recording
        pass

    def is_soft_breached(self, layer: str) -> bool:
        """Check if soft watermark breached for layer."""
        # TODO(@resilience-team): Implement soft breach detection
        pass

    def is_hard_breached(self, layer: str) -> bool:
        """Check if hard watermark breached for layer."""
        # TODO(@resilience-team): Implement hard breach detection
        pass

    def is_critical_breached(self, layer: str) -> bool:
        """Check if critical watermark breached for layer."""
        # TODO(@resilience-team): Implement critical breach detection
        pass

    def get_recovery_time(
        self,
        layer: str,
        watermark: str,  # "soft", "hard", "critical"
    ) -> Optional[float]:
        """
        Get time since last breach recovery (seconds).

        Args:
            layer: Layer name
            watermark: Watermark type

        Returns:
            Seconds since recovery, or None if currently breached

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement recovery time tracking
        pass

    def get_statistics(self, layer: str) -> Dict[str, Any]:
        """
        Get watermark statistics for layer.

        Returns:
            Dict with:
                - avg_depth_pct: Average depth
                - max_depth_pct: Peak depth
                - soft_breaches: Number of soft breaches
                - hard_breaches: Number of hard breaches
                - critical_breaches: Number of critical breaches
                - avg_breach_duration_s: Average breach duration
                - last_breach_time: When last breach occurred

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement statistics collection
        pass
```

**Watermark Timeline Example:**

```
Time | App %  | Cache % | Breaker % | Status
-----|--------|--------|-----------|---------------------
0s   | 30%    | 25%    | 10%       | 🟢 Normal
30s  | 72%    | 68%    | 15%       | 🟢 Normal
60s  | 78%    | 72%    | 18%       | ⚠️ App: Soft breached
90s  | 82%    | 80%    | 22%       | ⚠️ App+Cache: Soft breached
120s | 88%    | 86%    | 30%       | 🔴 Hard breached
150s | 97%    | 92%    | 50%       | 🔴 Critical breached
180s | 80%    | 75%    | 35%       | ⚠️ Recovering
210s | 40%    | 30%    | 15%       | 🟢 Recovered
```

**ADR References:**

- ADR-0028: Backpressure Cascade System

**Assigned To:** Issue #L5-8.1.2

---

### 🎯 Epic 8.2: Cascading Actions & Privacy Overrides

**Purpose:** Backpressure action execution and privacy-aware override logic
**Files:** 2
**Status:** 🚧 STUB

#### Issue 8.2.1: cascade_actions.py

**File Path:** `k1/l5_infrastructure/backpressure/cascade_actions.py`

**Description:**
Cascading backpressure actions triggered by watermark breaches.

**Responsibilities:**

1. Implement tier-specific actions (slow_down, reduce_batch, downgrade)
2. Apply request rate reduction
3. Adjust batch sizes dynamically
4. Trigger circuit breaker downgrades
5. Coordinate with placement engine

**Core Methods:**

```python
class CascadeActions:
    """
    Cascading backpressure actions.

    Actions by Tier:
        Soft (75%): Slow down non-priority (10% reduction)
        Hard (85%): Reduce batch size (20% reduction)
        Critical (95%): Downgrade tier or reject (30% reduction)
    """

    def __init__(
        self,
        placement_engine: Optional["CascadeEngine"] = None,
        circuit_breaker: Optional["CircuitBreakerManager"] = None,
    ):
        """
        Initialize cascade actions.

        Args:
            placement_engine: Model placement engine for downgrades
            circuit_breaker: Circuit breaker for rejection

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Initialize cascade actions
        # 1. Store placement_engine, circuit_breaker
        # 2. Setup action callbacks
        pass

    async def apply_soft_watermark_action(
        self,
        current_reduction_pct: float = 0.0,
        cognitive_trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Apply soft watermark action (10% rate reduction).

        Args:
            current_reduction_pct: Current reduction already applied
            cognitive_trace_id: Trace ID

        Returns:
            Dict with:
                - action: "slow_down"
                - new_reduction_pct: Cumulative reduction (current + 10%)
                - delay_ms: Milliseconds to delay non-priority requests
                - affected_request_types: ["batch", "normal"]

        Behavior:
            1. Increase non-priority request delay by 10%
            2. Priority requests unaffected
            3. Slow decay if queue stabilizes

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement soft action
        pass

    async def apply_hard_watermark_action(
        self,
        current_reduction_pct: float = 0.0,
        cognitive_trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Apply hard watermark action (20% batch reduction).

        Args:
            current_reduction_pct: Current reduction already applied
            cognitive_trace_id: Trace ID

        Returns:
            Dict with:
                - action: "reduce_batch"
                - new_reduction_pct: Cumulative reduction (current + 20%)
                - batch_size_reduction: Original batch / 1.2
                - ttl_increase_pct: Cache TTL increased by 30%

        Behavior:
            1. Reduce batch size by 20%
            2. Increase cache TTL (fewer requests)
            3. Reject non-priority requests

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement hard action
        pass

    async def apply_critical_watermark_action(
        self,
        current_reduction_pct: float = 0.0,
        cognitive_trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Apply critical watermark action (downgrade tier or reject).

        Args:
            current_reduction_pct: Current reduction already applied
            cognitive_trace_id: Trace ID

        Returns:
            Dict with:
                - action: "downgrade_or_reject"
                - new_reduction_pct: Cumulative reduction (current + 30%)
                - tier_downgrade: From GPU → CPU or CPU → Remote
                - reject_batch: True to reject batch requests
                - reject_threshold_pct: Reject if queue > threshold

        Behavior:
            1. Downgrade models to lower tier (GPU→CPU→Remote)
            2. Reject batch/normal requests
            3. Accept only priority requests

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement critical action
        pass

    async def release_backpressure(
        self,
        current_reduction_pct: float,
        cognitive_trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Gradually release backpressure as queue shrinks.

        Args:
            current_reduction_pct: Current reduction level
            cognitive_trace_id: Trace ID

        Returns:
            Dict with:
                - new_reduction_pct: Reduced by 5% (gradual)
                - reason: "queue_decreased" or "threshold_cleared"

        Behavior:
            1. Release 5% reduction per measurement
            2. Only if queue below current threshold
            3. Smooth recovery (avoid oscillation)

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement backpressure release
        pass

    def get_action_statistics(self) -> Dict[str, Any]:
        """
        Get action statistics.

        Returns:
            Dict with:
                - soft_actions_triggered: Count
                - hard_actions_triggered: Count
                - critical_actions_triggered: Count
                - total_reduction_time_s: Total reduction duration
                - avg_duration_s: Average action duration

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement statistics collection
        pass
```

**Action Cascade Timeline:**

```
Queue %  | Action       | Rate Reduction | Batch Change | Tier Change | Duration
---------|--------------|---|---|---|---
75-80%   | Slow down    | 10%            | None         | None        | Until <75%
80-85%   | Reduce batch | 20%            | -20%         | None        | Until <80%
85-95%   | Downgrade    | 30%            | -30%         | GPU→CPU     | Until <85%
>95%     | Reject       | 50%            | -50%         | CPU→Remote  | Emergency
```

**ADR References:**

- ADR-0028: Backpressure Cascade System

**Assigned To:** Issue #L5-8.2.1

---

#### Issue 8.2.2: privacy_override.py

**File Path:** `k1/l5_infrastructure/backpressure/privacy_override.py`

**Description:**
Privacy-aware backpressure overrides for RED/AMBER-band requests.

**Responsibilities:**

1. Enforce RED-band high-priority override
2. Allow AMBER-band partial overrides
3. Restrict GREEN-band requests
4. Audit override decisions
5. Report override statistics

**Core Methods:**

```python
class PrivacyOverride:
    """
    Privacy-aware backpressure overrides.

    Override Policy:
        RED: High-priority, bypass soft watermarks
        AMBER: Standard enforcement
        GREEN: Strict enforcement, no overrides
    """

    def __init__(self):
        """
        Initialize privacy override.

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Initialize privacy override
        # 1. Setup override policies
        # 2. Initialize audit logging
        pass

    def can_bypass_soft_watermark(
        self,
        privacy_band: str,
        current_depth_pct: float,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if can bypass soft watermark (75%) based on privacy.

        Args:
            privacy_band: Privacy classification (red, amber, green)
            current_depth_pct: Current queue depth

        Returns:
            (can_bypass: bool, reason: optional)

        Rules:
            - RED: Always can bypass soft (high-priority)
            - AMBER: Cannot bypass (standard enforcement)
            - GREEN: Cannot bypass (strict)

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement soft watermark override
        pass

    def can_bypass_hard_watermark(
        self,
        privacy_band: str,
        current_depth_pct: float,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if can bypass hard watermark (85%) based on privacy.

        Args:
            privacy_band: Privacy classification
            current_depth_pct: Current queue depth

        Returns:
            (can_bypass: bool, reason: optional)

        Rules:
            - RED: Can bypass hard if still <95% (emergency limit)
            - AMBER: Cannot bypass hard
            - GREEN: Cannot bypass hard

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement hard watermark override
        pass

    def can_bypass_critical_watermark(
        self,
        privacy_band: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if can bypass critical watermark (95%).

        Args:
            privacy_band: Privacy classification

        Returns:
            (can_bypass: bool, reason: optional)

        Rules:
            - RED: Cannot bypass critical (emergency threshold)
            - AMBER: Cannot bypass critical
            - GREEN: Cannot bypass critical

        Target: All bands respect critical watermark

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement critical watermark enforcement
        pass

    def audit_override(
        self,
        privacy_band: str,
        watermark: str,
        current_depth_pct: float,
        cognitive_trace_id: str,
    ) -> None:
        """
        Audit privacy override decision.

        Args:
            privacy_band: Privacy classification
            watermark: Watermark type (soft, hard, critical)
            current_depth_pct: Queue depth at override
            cognitive_trace_id: Trace ID for audit trail

        Logging:
            - RED bypasses logged
            - AMBER enforcement logged
            - GREEN strict enforcement logged

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement override audit
        pass

    def get_override_statistics(self) -> Dict[str, Any]:
        """
        Get privacy override statistics.

        Returns:
            Dict with:
                - red_soft_bypasses: RED soft watermark bypasses
                - red_hard_bypasses: RED hard watermark bypasses
                - amber_rejections: AMBER requests rejected at hard
                - green_rejections: GREEN requests rejected at soft
                - total_overrides: Total override decisions
                - override_acceptance_rate_pct: % accepted with overrides

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement override statistics
        pass
```

**Privacy Override Decision Table:**

```
Privacy | Soft 75% | Hard 85%  | Critical 95% | Behavior
--------|----------|-----------|--------------|--------------------
RED     | Bypass ✅ | Bypass ✅  | Enforce ❌   | High-priority, still limited
AMBER   | Enforce  | Enforce   | Enforce ❌   | Standard enforcement
GREEN   | Enforce  | Enforce   | Enforce ❌   | Strict enforcement
```

**ADR References:**

- ADR-0028: Backpressure Cascade System

**Assigned To:** Issue #L5-8.2.2

---

### 🎯 Epic 8.3: Metrics & Monitoring

**Purpose:** Backpressure metrics and observability
**Files:** 2
**Status:** 🚧 STUB

#### Issue 8.3.1: metrics.py

**File Path:** `k1/l5_infrastructure/backpressure/metrics.py`

**Description:**
Backpressure metrics collection and Prometheus export.

**Responsibilities:**

1. Track watermark breaches and recovery
2. Track backpressure action frequency
3. Track request rejection rates
4. Track privacy override usage
5. Export Prometheus metrics

**Core Methods:**

```python
class BackpressureMetrics:
    """
    Backpressure metrics collection and export.

    Metrics:
        - k1_backpressure_queue_depth_pct{layer}
        - k1_backpressure_watermark_breaches_total{layer, watermark}
        - k1_backpressure_actions_triggered_total{action, layer}
        - k1_backpressure_request_rejections_total{reason, privacy_band}
        - k1_backpressure_privacy_overrides_total{band, watermark}
    """

    def __init__(self):
        """
        Initialize backpressure metrics.

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Initialize metrics
        # 1. Create Prometheus metrics
        # 2. Setup histogram buckets
        pass

    def record_queue_depth(
        self,
        layer: str,
        depth_pct: float,
        watermark_tier: str,  # "normal", "soft", "hard", "critical"
    ) -> None:
        """
        Record queue depth reading.

        Args:
            layer: Layer name (app, cache, breaker)
            depth_pct: Depth as percentage
            watermark_tier: Current watermark tier

        Metrics:
            - Gauge: k1_backpressure_queue_depth_pct{layer, tier}
            - Histogram: k1_backpressure_queue_depth_pct_bucket{layer}

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement depth recording
        pass

    def record_watermark_breach(
        self,
        layer: str,
        watermark: str,  # "soft", "hard", "critical"
        depth_pct: float,
    ) -> None:
        """
        Record watermark threshold breach.

        Args:
            layer: Layer name
            watermark: Watermark type
            depth_pct: Depth at breach

        Metrics:
            - Counter: k1_backpressure_watermark_breaches_total{layer, watermark}
            - Gauge: k1_backpressure_watermark_latest_depth_pct{layer, watermark}

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement breach recording
        pass

    def record_action_triggered(
        self,
        action: str,  # "slow_down", "reduce_batch", "downgrade"
        layer: str,
        reason: str,
    ) -> None:
        """
        Record backpressure action triggered.

        Args:
            action: Action type
            layer: Layer where triggered
            reason: Reason (soft_breach, hard_breach, etc.)

        Metrics:
            - Counter: k1_backpressure_actions_triggered_total{action, layer, reason}
            - Gauge: k1_backpressure_active_actions{action}

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement action recording
        pass

    def record_request_rejection(
        self,
        reason: str,  # "soft_watermark", "hard_watermark", "critical_watermark"
        privacy_band: str,
        request_type: str,
    ) -> None:
        """
        Record rejected request.

        Args:
            reason: Rejection reason
            privacy_band: Privacy classification
            request_type: Request type (priority, normal, batch)

        Metrics:
            - Counter: k1_backpressure_request_rejections_total{reason, band, type}

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement rejection recording
        pass

    def record_privacy_override(
        self,
        privacy_band: str,
        watermark: str,
        override_allowed: bool,
    ) -> None:
        """
        Record privacy override decision.

        Args:
            privacy_band: Privacy band
            watermark: Watermark type
            override_allowed: Whether override was granted

        Metrics:
            - Counter: k1_backpressure_privacy_overrides_total{band, watermark, result}

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement override recording
        pass

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get backpressure statistics.

        Returns:
            Dict with:
                - app_queue_avg_pct: Average app queue
                - cache_queue_avg_pct: Average cache queue
                - breaker_queue_avg_pct: Average breaker queue
                - soft_breaches_total: Total soft breaches
                - hard_breaches_total: Total hard breaches
                - critical_breaches_total: Total critical breaches
                - actions_triggered_total: Total actions
                - rejections_total: Total rejections
                - override_acceptance_rate_pct: % overrides granted

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement statistics collection
        pass
```

**Prometheus Metrics Reference:**

```
# Queue depth tracking (gauge)
k1_backpressure_queue_depth_pct{layer="app", tier="normal"} 45
k1_backpressure_queue_depth_pct{layer="cache", tier="soft"} 78
k1_backpressure_queue_depth_pct{layer="breaker", tier="hard"} 88

# Watermark breaches (counter)
k1_backpressure_watermark_breaches_total{layer="app", watermark="soft"} 150
k1_backpressure_watermark_breaches_total{layer="cache", watermark="hard"} 45

# Actions triggered (counter)
k1_backpressure_actions_triggered_total{action="slow_down", layer="app"} 150
k1_backpressure_actions_triggered_total{action="reduce_batch", layer="cache"} 45
k1_backpressure_actions_triggered_total{action="downgrade", layer="breaker"} 8

# Request rejections (counter)
k1_backpressure_request_rejections_total{reason="hard_watermark", band="green"} 300
k1_backpressure_request_rejections_total{reason="hard_watermark", band="amber"} 20

# Privacy overrides (counter)
k1_backpressure_privacy_overrides_total{band="red", watermark="soft", result="allowed"} 500
k1_backpressure_privacy_overrides_total{band="green", watermark="soft", result="denied"} 200
```

**ADR References:**

- ADR-0028: Backpressure Cascade System

**Assigned To:** Issue #L5-8.3.1

---

#### Issue 8.3.2: dashboard.py

**File Path:** `k1/l5_infrastructure/backpressure/dashboard.py`

**Description:**
Backpressure dashboard and real-time monitoring.

**Responsibilities:**

1. Aggregate backpressure metrics
2. Provide real-time queue depth visualization
3. Show active actions and overrides
4. Report breach history
5. Export dashboard data for UI

**Core Methods:**

```python
class BackpressureDashboard:
    """
    Backpressure real-time dashboard and monitoring.

    Dashboard Components:
        1. Queue depth gauge (app, cache, breaker)
        2. Watermark status (normal, soft, hard, critical)
        3. Active actions (slow_down, reduce_batch, downgrade)
        4. Privacy overrides active (RED/AMBER high-priority)
        5. Breach history (timeline)
    """

    def __init__(self, metrics: BackpressureMetrics):
        """
        Initialize backpressure dashboard.

        Args:
            metrics: BackpressureMetrics instance

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Initialize dashboard
        # 1. Connect to metrics
        # 2. Setup real-time updates
        pass

    def get_dashboard_state(self) -> Dict[str, Any]:
        """
        Get current dashboard state for UI.

        Returns:
            Dict with:
                - queue_depths: {app_pct, cache_pct, breaker_pct}
                - watermark_status: {app_tier, cache_tier, breaker_tier}
                - active_actions: [{action, duration_s, reason}, ...]
                - active_overrides: [{band, watermark, count}, ...]
                - breach_history: [{timestamp, layer, watermark}, ...]
                - health_status: "green", "yellow", "red"

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement dashboard state
        pass

    def get_breach_timeline(
        self,
        minutes: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        Get breach timeline for visualization.

        Args:
            minutes: Historical window (default: 60)

        Returns:
            List of events:
                [
                    {"timestamp": "2025-10-27T12:00:00Z", "layer": "app", "watermark": "soft", "action": "triggered"},
                    {"timestamp": "2025-10-27T12:05:00Z", "layer": "app", "watermark": "soft", "action": "recovered"},
                ]

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement timeline extraction
        pass

    def get_health_score(self) -> float:
        """
        Get backpressure health score (0-100).

        Returns:
            Score where:
                100 = No backpressure (queues <50%)
                75 = Soft watermark (queues 75%)
                50 = Hard watermark (queues 85%)
                25 = Critical watermark (queues 95%)
                0 = Emergency (queues overflowing)

        ADR: ADR-0028
        """
        # TODO(@resilience-team): Implement health scoring
        pass
```

**Dashboard JSON Example:**

```json
{
  "queue_depths": {
    "app_pct": 72,
    "cache_pct": 68,
    "breaker_pct": 45
  },
  "watermark_status": {
    "app_tier": "soft",
    "cache_tier": "normal",
    "breaker_tier": "normal"
  },
  "active_actions": [
    {
      "action": "slow_down",
      "layer": "app",
      "duration_s": 45,
      "reason": "soft_watermark_breach"
    }
  ],
  "active_overrides": [
    {
      "band": "red",
      "watermark": "soft",
      "count": 12,
      "reason": "high_priority_data"
    }
  ],
  "breach_history": [
    {"timestamp": "2025-10-27T12:00:00Z", "layer": "app", "watermark": "soft", "action": "triggered"},
    {"timestamp": "2025-10-27T12:05:00Z", "layer": "app", "watermark": "soft", "action": "recovered"}
  ],
  "health_status": "yellow",
  "health_score": 72
}
```

**ADR References:**

- ADR-0028: Backpressure Cascade System

**Assigned To:** Issue #L5-8.3.2

---

### 📊 Summary

**Milestone 8: Backpressure Coordination**

| Epic | Files | Status | Assigned |
|------|-------|--------|----------|
| 8.1: Manager & Watermarks | 2 | 🚧 STUB | @resilience-team |
| 8.2: Cascade Actions & Privacy | 2 | 🚧 STUB | @resilience-team |
| 8.3: Metrics & Monitoring | 2 | 🚧 STUB | @resilience-team |
| **Total** | **6** | **🚧 STUB** | **@resilience-team** |

**Watermark Thresholds:**

| Watermark | Threshold | Action | Reason |
|-----------|-----------|--------|--------|
| **Soft** | 75% | Slow down non-priority | Early warning, graceful degradation |
| **Hard** | 85% | Reduce batch size, reject non-priority | Strong backpressure |
| **Critical** | 95% | Downgrade tier or reject all | Emergency mode |

**Cascade Flow:**

```
Queue Increasing
    ↓
75% Soft: Slow down non-priority (10% reduction)
    ↓ (if queue keeps growing)
85% Hard: Reduce batch by 20%, reject non-priority
    ↓ (if queue keeps growing)
95% Critical: Downgrade tier (GPU→CPU→Remote), reject almost all
    ↓ (if queue starts shrinking)
Release Gradually: 5% reduction per measurement until clear
```

**Privacy Integration:**

- **RED**: Can bypass soft/hard watermarks (high-priority)
- **AMBER**: Standard enforcement
- **GREEN**: Strict enforcement (no overrides)

**Milestone 8 Dependencies:**

```
Upstream (Requires):
  - k1.l5_infrastructure.placement (tier downgrade)
  - k1.l5_infrastructure.circuit_breaker (circuit management)
  - k1.l5_infrastructure.event_bus (queue monitoring)

Downstream (Provides):
  - k1.l5_infrastructure.scheduler (backpressure-aware scheduling)
  - k1.l5_infrastructure.admission (admission control)
  - k1.l3_execution.request_router (request routing)
```

---

## Milestone 9: Local In-Memory Caching (Zero External Dependencies)

### 📋 Overview

**Purpose:** High-performance local in-memory caching for security-critical and performance-critical operations
**Priority:** M1 (High, Security + Performance)
**Status:** 🚧 STUB - NEEDS_IMPLEMENTATION
**Files:** 4 Python modules
**ADRs:** ADR-0028d (Local In-Memory Cache with K0 Persistence)
**Assigned To:** @cache-team

**Key Features:**

- **LOCAL-ONLY DESIGN:** Pure Python, zero external dependencies (no Redis, Memcached, or external services)
- **Dual-Mode Caching:**
  - **Runtime Cache:** In-memory OrderedDict + threading.RLock (<0.1ms access)
  - **Persistent Cache:** Async K0 writes for security-critical data (tokens, capabilities)
- **Security-Critical Data:** 24-hour TTL, automatic K0 persistence, recovery on startup
- **Performance Cache:** 5-minute TTL, in-process only (loss acceptable on restart)
- **Capacity:** 10,000-key limit (configurable)
- **Hit Rate Target:** >99% for security checks, >85% for deduplication
- **Access Latency:** <0.1ms P95 (sub-millisecond in-memory lookup)
- **Startup Recovery:** <100ms cache warmup from K0
- **Eviction:** LRU (Least Recently Used) when capacity exceeded
- **Metrics:** Hit/miss rates, latency histograms, memory usage, persistence latency
- **Observability:** Prometheus metrics, structured logging, trace spans

**Cache Performance Targets:**

```
Operation                | Latency P50 | Latency P95 | Latency P99 | Status
--------------------------|-------------|-------------|-------------|--------
Get (in-memory)          | <0.1ms      | <0.1ms      | <0.2ms      | ✅ Local
Set (in-memory)          | <0.1ms      | <0.1ms      | <0.2ms      | ✅ Local
Delete (in-memory)       | <0.05ms     | <0.1ms      | <0.2ms      | ✅ Local
K0 Persistence (async)   | N/A (bg)    | 2-5ms       | 10ms        | ✅ Non-blocking
Cache warmup (startup)   | <100ms      | <100ms      | <150ms      | ✅ Once at startup
Token check (security)   | <0.1ms      | <0.1ms      | <0.2ms      | ✅ <1ms SLA
Capability check         | <0.1ms      | <0.1ms      | <0.2ms      | ✅ <1ms SLA
```

**Deployment Models:**

```
LOCAL-ONLY DEPLOYMENT (Default - No External Dependencies):
  ├─ Runtime Cache: OrderedDict + threading.RLock
  ├─ Persistence: K0 storage (local only)
  ├─ Dependencies: None (pure Python)
  ├─ Startup: <100ms warmup from K0
  └─ Cost: $0/month

ENTERPRISE DEPLOYMENT (With Cloud Integration - Optional Future):
  ├─ Runtime Cache: Same (OrderedDict)
  ├─ Persistence: Redis cluster + K0 sync (optional)
  ├─ Dependencies: Redis cluster (enterprise paid)
  └─ Note: NOT part of M9 - enterprise tier only
```

**Cache Architecture (LOCAL-ONLY):**

```
REQUEST → [In-Memory Cache] → <0.1ms lookup
                ├─ Token revoked? → CACHE HIT (99% of requests)
                ├─ Capability revoked? → CACHE HIT
                └─ Idempotent request? → CACHE HIT

REVOCATION EVENT → [Add to memory] + [Async K0 write]
                ├─ In-memory update: 0.1ms (immediate effect)
                ├─ K0 persistence: 2-5ms (async, non-blocking)
                └─ Result: Protected immediately + durable on restart

K1 STARTUP → [Load critical caches from K0]
          ├─ Query K0: "All revoked tokens"
          ├─ Query K0: "All revoked capabilities"
          ├─ Batch load time: <100ms
          └─ Ready for requests
```

---

### 🎯 Epic 9.1: In-Memory Cache Core

**Purpose:** Local in-memory cache with zero external dependencies
**Files:** 2
**Status:** 🚧 STUB

#### Issue 9.1.1: in_memory_cache.py

**File Path:** `k1/l5_infrastructure/caching/in_memory_cache.py`

**Description:**
Pure Python local in-memory cache using OrderedDict + threading.RLock. Zero external dependencies, <0.1ms latency.

**Responsibilities:**

1. Get/set/delete cache entries (in-memory OrderedDict)
2. Enforce TTL with background cleanup coroutine
3. Enforce capacity limit with LRU eviction
4. Track hit/miss statistics and latency
5. Thread-safe access with asyncio.Lock
6. Background TTL cleanup loop

**Core Methods:**

```python
class InMemoryCache:
    """
    Pure local in-memory cache (zero external dependencies).

    Implementation:
        - Data structure: OrderedDict (Python stdlib)
        - Synchronization: asyncio.Lock (atomic operations)
        - TTL: Background cleanup coroutine
        - Eviction: LRU when capacity exceeded

    Performance:
        - Get: <0.1ms (dict lookup)
        - Set: <0.1ms (dict insert)
        - Delete: <0.05ms (dict removal)
        - Memory: ~1MB overhead

    ADR: ADR-0028d
    """

    def __init__(
        self,
        max_size: int = 10000,
        cleanup_interval_seconds: int = 60,
    ):
        """
        Initialize in-memory cache.

        Args:
            max_size: Max keys in cache (default: 10000)
            cleanup_interval_seconds: TTL cleanup frequency (default: 60s)

        ADR: ADR-0028d
        """
        # TODO(@cache-team): Initialize in-memory cache
        # 1. Create OrderedDict for cache storage
        # 2. Create asyncio.Lock for thread safety
        # 3. Store max_size and cleanup_interval
        # 4. Initialize metrics (hits, misses, evictions)
        pass

    async def start(self) -> None:
        """Start background TTL cleanup coroutine."""
        # TODO(@cache-team): Start background cleanup
        # 1. Create cleanup task
        # 2. Log startup with max_size
        pass

    async def stop(self) -> None:
        """Stop background cleanup coroutine."""
        # TODO(@cache-team): Stop background cleanup
        # 1. Cancel cleanup task
        # 2. Handle CancelledError
        # 3. Log shutdown
        pass

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value by key.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired

        Performance:
            - <0.1ms P95 (dict lookup + expiration check)

        Atomicity:
            - asyncio.Lock ensures single-threaded access
            - Check expiration and delete atomically

        ADR: ADR-0028d
        """
        # TODO(@cache-team): Implement cache get
        # 1. Acquire lock
        # 2. Check if key exists
        # 3. Check if expired (compare time.time() vs stored timestamp)
        # 4. If expired, delete and return None
        # 5. If not expired, return value
        # 6. Record hit/miss metric
        pass

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int,
    ) -> None:
        """
        Store value with TTL.

        Args:
            key: Cache key
            value: Value to cache (any type)
            ttl_seconds: Time-to-live in seconds

        Performance:
            - <0.1ms P95 (dict insert + LRU eviction)

        LRU Eviction:
            - If len(cache) > max_size:
              - Find oldest entry (min expire_time)
              - Delete oldest
              - Log eviction

        ADR: ADR-0028d
        """
        # TODO(@cache-team): Implement cache set
        # 1. Acquire lock
        # 2. Calculate expire_time = time.time() + ttl_seconds
        # 3. Store (value, expire_time) in OrderedDict
        # 4. If len > max_size, evict oldest (min timestamp)
        # 5. Record set metric and eviction count
        pass

    async def delete(self, key: str) -> None:
        """
        Delete key immediately.

        Args:
            key: Cache key

        Performance:
            - <0.05ms (dict removal)

        ADR: ADR-0028d
        """
        # TODO(@cache-team): Implement cache delete
        pass

    async def exists(self, key: str) -> bool:
        """
        Check key existence and validity.

        Args:
            key: Cache key

        Returns:
            True if key exists and not expired

        Performance:
            - <0.1ms (dict lookup + expiration check)

        ADR: ADR-0028d
        """
        # TODO(@cache-team): Implement cache exists
        pass

    async def clear(self) -> None:
        """
        Clear all cache entries.

        Performance:
            - <1ms for 10000 entries
        """
        # TODO(@cache-team): Implement cache clear
        pass

    async def _cleanup_loop(self) -> None:
        """
        Background task: Remove expired entries every N seconds.

        Execution:
            1. Sleep cleanup_interval_seconds
            2. Acquire lock
            3. Find all expired entries (expire_time < now)
            4. Delete expired entries
            5. Log count if any removed
            6. Repeat

        Purpose:
            - Prevents cache from accumulating expired entries
            - Runs every 60 seconds
            - Non-blocking (other operations continue during cleanup)

        ADR: ADR-0028d
        """
        # TODO(@cache-team): Implement background cleanup
        # 1. Loop forever (until cancelled)
        # 2. Sleep cleanup_interval_seconds
        # 3. Acquire lock
        # 4. Find entries where expire_time < time.time()
        # 5. Delete them
        # 6. Release lock
        # 7. Handle asyncio.CancelledError
        pass
```

#### Issue 9.1.2: persistent_cache.py

**File Path:** `k1/l5_infrastructure/caching/persistent_cache.py`

**Description:**
Wrapper around InMemoryCache that adds K0 persistence for security-critical data (tokens, capabilities).

**Responsibilities:**

1. Wrap InMemoryCache for runtime operations
2. Async write revoked tokens/capabilities to K0
3. Expose specialized persistence methods
4. Handle async I/O without blocking caller

**Core Methods:**

```python
class PersistentCache(InMemoryCache):
    """
    In-memory cache + K0 persistence for security-critical data.

    Pattern (Token Revocation):
        1. Add to in-memory cache: 0.1ms (immediate protection)
        2. Async write to K0: 2-5ms (in background)
        3. Return to caller: ~0.2ms (non-blocking)

    Pattern (Startup):
        1. Query K0: "All revoked tokens"
        2. Query K0: "All revoked capabilities"
        3. Bulk load to in-memory: <100ms
        4. Ready for requests

    ADR: ADR-0028d
    """

    def __init__(self, k0_memory_port, **kwargs):
        """
        Initialize persistent cache with K0 backend.

        Args:
            k0_memory_port: K0 memory port for persistence
            **kwargs: Passed to InMemoryCache.__init__

        ADR: ADR-0028d
        """
        super().__init__(**kwargs)
        self.k0_memory_port = k0_memory_port

    async def persist_token_revocation(self, token_id: str) -> None:
        """
        Revoke JWT token (immediate + durable).

        Args:
            token_id: Token to revoke

        Execution Timeline:
            0.1ms: Add to in-memory cache (protection starts NOW)
            2-5ms: Async K0 write (survives restart)
            ~0.2ms: Return to caller (non-blocking)

        Guarantee:
            - Token checked IMMEDIATELY in memory
            - Persisted to K0 (async, non-blocking)
            - Survives K1 restart (recovered from K0)

        ADR: ADR-0028d
        """
        # TODO(@cache-team): Implement token revocation
        # 1. Add to in-memory: await self.set("revoked_token:{token_id}", True, 86400)
        # 2. Async K0 write: asyncio.create_task(self.k0_memory_port.store(...))
        # 3. Log: INFO "Token revoked"
        pass

    async def persist_capability_revocation(
        self,
        agent_id: str,
        capability_name: str,
    ) -> None:
        """
        Revoke agent capability (immediate + durable).

        Args:
            agent_id: Agent whose capability to revoke
            capability_name: Capability name

        Execution Timeline:
            Same as token revocation (0.1ms memory + 2-5ms K0 async)

        ADR: ADR-0028d
        """
        # TODO(@cache-team): Implement capability revocation
        # 1. Add to in-memory cache
        # 2. Async K0 write
        # 3. Log
        pass
```

#### Issue 9.1.3: cache_warmer.py

**File Path:** `k1/l5_infrastructure/caching/cache_warmer.py`

**Description:**
K1 startup recovery: Load critical caches from K0 in <100ms.

**Responsibilities:**

1. Query K0 for all revoked tokens
2. Query K0 for all revoked capabilities
3. Bulk load to in-memory cache
4. Return statistics for logging

**Core Methods:**

```python
class CacheWarmer:
    """
    Recover critical caches from K0 on K1 startup.

    Timeline:
        - K1 starts
        - Query K0: "All revoked tokens" (batch load)
        - Query K0: "All revoked capabilities" (batch load)
        - Populate in-memory cache
        - Time: <100ms
        - Ready for requests

    ADR: ADR-0028d
    """

    def __init__(self, cache: InMemoryCache, k0_recall_port):
        """
        Initialize cache warmer.

        Args:
            cache: InMemoryCache instance to warm
            k0_recall_port: K0 query port for batch loading

        ADR: ADR-0028d
        """
        # TODO(@cache-team): Initialize cache warmer
        pass

    async def warm_on_startup(self) -> Dict[str, int]:
        """
        Load critical caches from K0.

        Returns:
            {
                "tokens_loaded": int,
                "capabilities_loaded": int,
                "warmup_time_ms": float,
            }

        Execution:
            1. Query K0: "SELECT * FROM security WHERE type='revoked_token'"
            2. Load all results to in-memory cache (24hr TTL)
            3. Query K0: "SELECT * FROM security WHERE type='revoked_capability'"
            4. Load all results to in-memory cache (24hr TTL)
            5. Log stats

        Performance:
            - <100ms for typical 1000-entry cache
            - Batch load for efficiency

        Error Handling:
            - If K0 query fails, log error and continue
            - Cache will be empty but functional (recovers on next revocation)

        ADR: ADR-0028d
        """
        # TODO(@cache-team): Implement cache warming
        # 1. Query K0 for revoked_tokens
        # 2. For each token: await cache.set(f"revoked_token:{token_id}", True, 86400)
        # 3. Query K0 for revoked_capabilities
        # 4. For each capability: await cache.set(f"revoked_capability:{agent_id}:{cap_name}", True, 86400)
        # 5. Return stats
        pass
```

#### Issue 9.1.4: cache_integration.py

**File Path:** `k1/l5_infrastructure/caching/cache_integration.py`

**Description:**
Orchestrator integration: revoke/check operations for tokens and capabilities.

**Core Methods:**

```python
class CacheIntegration:
    """
    Security operations integrated with cache.

    Operations:
        - revoke_token(token_id) → Add to memory + async K0
        - check_token_revoked(token_id) → Memory lookup only (<0.1ms)
        - revoke_capability(agent_id, cap_name) → Add to memory + async K0
        - check_capability_revoked(agent_id, cap_name) → Memory lookup only (<0.1ms)

    ADR: ADR-0028d
    """

    def __init__(self, cache: PersistentCache):
        """
        Initialize cache integration.

        Args:
            cache: PersistentCache instance

        ADR: ADR-0028d
        """
        # TODO(@cache-team): Initialize integration
        pass

    async def revoke_token(self, token_id: str) -> None:
        """
        Revoke JWT token immediately.

        Performance:
            - Non-blocking (<1ms return to caller)
            - Token checked in <0.1ms

        ADR: ADR-0028d, ADR-0037b
        """
        # TODO(@cache-team): Call persistent_cache.persist_token_revocation
        pass

    async def check_token_revoked(self, token_id: str) -> bool:
        """
        Check if token is revoked.

        Performance:
            - <0.1ms (memory lookup only, no I/O)

        Critical Path:
            - This runs on EVERY token validation
            - MUST be sub-millisecond
            - Uses in-memory cache only (no K0 calls)

        ADR: ADR-0028d, ADR-0037b
        """
        # TODO(@cache-team): Return await cache.exists(f"revoked_token:{token_id}")
        pass

    async def revoke_capability(
        self,
        agent_id: str,
        capability_name: str,
    ) -> None:
        """
        Revoke agent capability immediately.

        Performance:
            - Non-blocking (<1ms return)
            - Checked in <0.1ms

        ADR: ADR-0028d, ADR-0010d
        """
        # TODO(@cache-team): Call persistent_cache.persist_capability_revocation
        pass

    async def check_capability_revoked(
        self,
        agent_id: str,
        capability_name: str,
    ) -> bool:
        """
        Check if capability is revoked.

        Performance:
            - <0.1ms (memory lookup only, no I/O)

        Critical Path:
            - This runs on EVERY capability check
            - MUST be sub-millisecond
            - Uses in-memory cache only (no K0 calls)

        ADR: ADR-0028d, ADR-0010d
        """
        # TODO(@cache-team): Return await cache.exists(key)
        pass


**Cache Key Naming Convention:**

```

Format: {namespace}:{model_id}:{batch_size}:{input_hash}
Example: k1:cache:model_llama7b:batch_32:abc123def456
Benefits:

- Tenant/namespace isolation
- Model versioning
- Batch-specific caching
- Input-specific entries

```

**Redis Configuration for Caching:**

```yaml
# redis.conf (relevant settings)
maxmemory 512mb              # Max memory limit
maxmemory-policy allkeys-lru  # Eviction policy: LRU on all keys
timeout 0                     # No idle timeout (persistent)
tcp-keepalive 300            # TCP keepalive

# Connection pooling
min-idle-conns: 5
max-idle-conns: 20
max-active-conns: 50
idle-timeout: 300s
```

**ADR References:**

- ADR-0029: Redis Caching Strategy

**Assigned To:** Issue #L5-9.1.1

---

### 🎯 Epic 9.2: Connection Pooling & Resilience

**Purpose:** Redis connection pooling and fault tolerance
**Files:** 1
**Status:** 🚧 STUB

#### Issue 9.2.1: connection_pool.py

**File Path:** `k1/l5_infrastructure/caching/connection_pool.py`

**Description:**
Redis connection pool with adaptive sizing, circuit breaker, and graceful degradation.

**Responsibilities:**

1. Maintain connection pool (10-50 connections)
2. Adapt pool size based on load
3. Monitor connection health
4. Circuit breaker for Redis unavailability
5. Fallback to non-cached operation
6. Report pool metrics

**Core Methods:**

```python
class RedisConnectionPool:
    """
    Redis connection pool with adaptive sizing and circuit breaker.

    Pool Configuration:
        - Min connections: 10
        - Max connections: 50
        - Acquire timeout: 1 second
        - Idle timeout: 300 seconds

    Resilience:
        - Circuit breaker on Redis unavailability
        - Automatic reconnection (exponential backoff)
        - Graceful degradation (bypass cache on failure)
    """

    def __init__(
        self,
        redis_url: str,
        min_connections: int = 10,
        max_connections: int = 50,
        acquire_timeout_s: float = 1.0,
        idle_timeout_s: int = 300,
    ):
        """
        Initialize connection pool.

        Args:
            redis_url: Redis connection URL
            min_connections: Min pool size (default: 10)
            max_connections: Max pool size (default: 50)
            acquire_timeout_s: Connection acquire timeout (default: 1s)
            idle_timeout_s: Idle connection timeout (default: 5min)

        ADR: ADR-0029
        """
        # TODO(@cache-team): Initialize connection pool
        # 1. Create Redis connection pool (aioredis)
        # 2. Pre-warm with min_connections
        # 3. Setup circuit breaker
        # 4. Setup health check task
        pass

    async def acquire(
        self,
        timeout_s: float = 1.0,
    ) -> Redis:
        """
        Acquire connection from pool.

        Args:
            timeout_s: Timeout for acquire (default: 1s)

        Returns:
            Redis client connection

        Raises:
            TimeoutError: If timeout exceeded
            CircuitBreakerOpen: If circuit breaker open (Redis down)

        Performance:
            - Acquire: <1ms P50, <2ms P95

        Behavior:
            1. Check circuit breaker (fail fast if open)
            2. Get connection from pool or create new
            3. Verify connection health (PING)
            4. Return connection

        ADR: ADR-0029
        """
        # TODO(@cache-team): Implement connection acquire
        pass

    async def release(self, connection: Redis) -> None:
        """
        Release connection back to pool.

        Args:
            connection: Redis connection to release

        Behavior:
            - Return to available pool
            - Update idle timestamp
            - Verify still healthy

        ADR: ADR-0029
        """
        # TODO(@cache-team): Implement connection release
        pass

    async def health_check(self) -> Dict[str, Any]:
        """
        Check pool and Redis health.

        Returns:
            Dict with:
                - healthy: True if Redis accessible
                - connections_active: Current active connections
                - connections_available: Available in pool
                - redis_latency_ms: PING latency
                - circuit_breaker_state: CLOSED, OPEN, HALF_OPEN

        Behavior:
            - Send PING command
            - Check connection count
            - Update circuit breaker state

        ADR: ADR-0029
        """
        # TODO(@cache-team): Implement health check
        pass

    async def adaptive_resize(self) -> None:
        """
        Adaptively adjust pool size based on load.

        Logic:
            - Monitor connection wait times
            - If avg_wait > 100ms and active < max: Grow pool
            - If idle > 1 minute and active > min: Shrink pool

        Behavior:
            - Runs periodically (every 30 seconds)
            - Graceful: No impact on current operations
            - Target: Keep pool at minimum size for current load

        ADR: ADR-0029
        """
        # TODO(@cache-team): Implement adaptive sizing
        pass

    async def close(self) -> None:
        """Close all connections in pool."""
        # TODO(@cache-team): Implement pool closure
        pass

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get pool statistics.

        Returns:
            Dict with:
                - min_size: Min pool size
                - max_size: Max pool size
                - current_size: Current connections
                - active_connections: In-use connections
                - available_connections: Available connections
                - total_acquired: Total acquire operations
                - total_released: Total release operations
                - avg_acquire_time_ms: Average acquire time
                - health_check_failures: Consecutive failures
                - circuit_breaker_state: CLOSED/OPEN/HALF_OPEN

        ADR: ADR-0029
        """
        # TODO(@cache-team): Implement statistics collection
        pass
```

**Connection Pool Lifecycle:**

```
Pool Creation
  ↓
[Min: 10 connections pre-warmed]
  ↓
Request → Acquire from pool (<1ms)
  ├─ Available? → Use
  ├─ No available, < max (50)? → Create new
  └─ No available, at max? → Wait (timeout 1s)
  ↓
Use connection (cache operation)
  ↓
Release → Back to pool
  ↓
Idle management:
  - Active connection used recently → Keep
  - Idle > 300s → Close and recreate on next use
  ↓
Adaptive resize (every 30s):
  - High wait time? → Grow pool
  - Low utilization? → Shrink pool
```

**Graceful Degradation on Redis Failure:**

```
Normal Operation:
  Request → Cache (Redis) → Cache hit/miss → Response

Redis Unavailable:
  Request → Cache (Redis) → Connection error
    ↓
  Circuit breaker opens (fail-fast)
    ↓
  Request → Bypass cache → Direct compute → Response
    (slower, but still functional)
    ↓
  Periodic health check: Redis recovering?
    ↓
  Circuit breaker half-open → Try single request
    ↓
  Success? → Close circuit breaker, resume caching
  Failure? → Keep open, continue bypass
```

**ADR References:**

- ADR-0029: Redis Caching Strategy

**Assigned To:** Issue #L5-9.2.1

---

### 📊 Summary

**Milestone 9: Redis Caching**

| Epic | Files | Status | Assigned |
|------|-------|--------|----------|
| 9.1: Core Cache | 1 | 🚧 STUB | @cache-team |
| 9.2: Connection Pooling | 1 | 🚧 STUB | @cache-team |
| **Total** | **2** | **🚧 STUB** | **@cache-team** |

**Cache Performance Targets:**

| Operation | P50 Latency | P95 Latency | Target Hit Rate |
|-----------|-------------|-------------|-----------------|
| **Get (hit)** | <1ms | <5ms | >85% |
| **Get (miss)** | <2ms | <5ms | N/A |
| **Set** | <2ms | <5ms | N/A |
| **Delete** | <1ms | <3ms | N/A |
| **Pool acquire** | <1ms | <2ms | N/A |

**Cache Capacity:**

```
Keys: 1,000 (configurable)
Memory: 512MB (Redis maxmemory)
Eviction: LRU (Least Recently Used)
TTL: 60 seconds
```

**Connection Pool Configuration:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Min size | 10 | Always ready for requests |
| Max size | 50 | Prevent resource exhaustion |
| Acquire timeout | 1s | Fail fast, allow bypass |
| Idle timeout | 300s | Clean up unused connections |

**Milestone 9 Dependencies:**

```
Upstream (Requires):
  - k1.l5_infrastructure.circuit_breaker (failure handling)
  - k1.l5_infrastructure.metrics (observability)

Downstream (Provides):
  - k1.l3_execution.model_hub (model result caching)
  - k1.l5_infrastructure.backpressure (reduced load via caching)
  - k1.l5_infrastructure.rate_limiter (token bucket backed by cache)
```

---

## Milestone 10: Rate Limiting

### 📋 Overview

**Purpose:** Token bucket rate limiting with per-user and per-tenant quotas
**Priority:** M1 (High, Flow Control)
**Status:** 🚧 STUB - NEEDS_IMPLEMENTATION
**Files:** 2 Python modules
**ADRs:** ADR-0030 (Rate Limiting Strategy)
**Assigned To:** @resilience-team

**Key Features:**

- **Token Bucket Algorithm:** Distributed rate limiting
- **Per-User Limits:** 1,000 requests/minute by default
- **Per-Tenant Limits:** 10,000 requests/minute by default
- **Sliding Window:** Precise quota tracking
- **Redis Backed:** Distributed state across instances
- **Performance:** <5ms decision time
- **Metrics:** Rate limit hits, quota usage, violations

**Rate Limit Tiers:**

```
Tier          | Requests/Min | Burst    | Use Case
--------------|--------------|----------|---------------------------
Free          | 100          | 10       | Development, testing
Standard      | 1,000        | 100      | Production, normal usage
Professional  | 10,000       | 1,000    | High-volume applications
Enterprise    | 100,000      | 10,000   | Platform partnerships
```

**Token Bucket Mechanics:**

```
Bucket Configuration:
  - Capacity: N tokens
  - Refill rate: M tokens/second
  - Example: 1,000 req/min = 16.67 tokens/second

Request Processing:
  1. Check if 1 token available
  2. Yes? Consume token, allow request
  3. No? Reject request (rate limited)
  4. Tokens refill automatically (M per second)

Burst Handling:
  - Accumulated tokens (up to capacity)
  - 1,000 req/min with 100 burst capacity
  - Can burst up to 100 requests instantly
```

---

### 🎯 Epic 10.1: Token Bucket Implementation

**Purpose:** Token bucket algorithm with Redis persistence
**Files:** 1
**Status:** 🚧 STUB

#### Issue 10.1.1: token_bucket.py

**File Path:** `k1/l5_infrastructure/rate_limiting/token_bucket.py`

**Description:**
Token bucket implementation with distributed state via Redis.

**Responsibilities:**

1. Maintain token bucket state (current tokens, last refill)
2. Calculate tokens available (based on elapsed time)
3. Consume tokens for requests
4. Refill bucket at configured rate
5. Handle burst capacity
6. Track quota statistics

**Core Methods:**

```python
class TokenBucket:
    """
    Token bucket rate limiter (distributed via Redis).

    Algorithm:
        - Capacity: Max tokens in bucket
        - Refill rate: Tokens added per second
        - Burst: Accumulated tokens available instantly

    Performance:
        - Check: <5ms P95
        - Consume: <5ms P95
    """

    def __init__(
        self,
        redis_client: Redis,
        bucket_key: str,
        capacity: int,
        refill_rate_per_second: float,
    ):
        """
        Initialize token bucket.

        Args:
            redis_client: Redis client
            bucket_key: Unique bucket identifier (user_id, tenant_id)
            capacity: Max tokens (burst capacity)
            refill_rate_per_second: Tokens added per second

        Example:
            bucket = TokenBucket(
                redis, "user:123",
                capacity=100,
                refill_rate_per_second=16.67  # 1000 req/min
            )

        ADR: ADR-0030
        """
        # TODO(@resilience-team): Initialize token bucket
        # 1. Store configuration
        # 2. Initialize Redis state (tokens, last_refill)
        # 3. Set initial tokens = capacity
        pass

    async def is_allowed(self) -> bool:
        """
        Check if request allowed (non-consuming check).

        Returns:
            True if token available

        Performance:
            - <5ms P95

        Behavior:
            - Calculate current tokens (refill)
            - Check if >= 1
            - Do NOT consume token

        ADR: ADR-0030
        """
        # TODO(@resilience-team): Implement allowance check
        pass

    async def consume(self) -> bool:
        """
        Consume token if available.

        Returns:
            True if consumed, False if rate limited

        Performance:
            - <5ms P95

        Behavior:
            1. Refill bucket (add elapsed tokens)
            2. Check if >= 1 token
            3. If yes: consume 1 token, return True
            4. If no: return False (rate limited)

        Atomicity:
            - Use Redis Lua script for atomic operation

        ADR: ADR-0030
        """
        # TODO(@resilience-team): Implement token consumption
        pass

    async def consume_many(self, tokens: int) -> bool:
        """
        Consume multiple tokens.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if all tokens consumed, False if insufficient

        Use Cases:
            - Batch requests (5 tokens)
            - Large uploads (50 tokens)
            - Premium operations (100 tokens)

        ADR: ADR-0030
        """
        # TODO(@resilience-team): Implement multi-token consumption
        pass

    async def get_status(self) -> Dict[str, Any]:
        """
        Get current bucket status.

        Returns:
            Dict with:
                - tokens_available: Current tokens
                - capacity: Max tokens
                - refill_rate: Tokens per second
                - tokens_per_minute: Refill per minute
                - reset_in_seconds: Time until reset

        ADR: ADR-0030
        """
        # TODO(@resilience-team): Implement status retrieval
        pass

    async def reset(self) -> None:
        """Reset bucket to full capacity."""
        # TODO(@resilience-team): Implement bucket reset
        pass
```

**Token Bucket Lua Script (Redis atomic operation):**

```lua
-- KEYS[1]: bucket_key
-- ARGV[1]: current_time_ms
-- ARGV[2]: capacity
-- ARGV[3]: refill_rate_per_ms
-- ARGV[4]: tokens_to_consume

local bucket_key = KEYS[1]
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])
local consume = tonumber(ARGV[4])

-- Get current bucket state
local state = redis.call('HGETALL', bucket_key)
local tokens = tonumber(state[2] or capacity)
local last_refill = tonumber(state[4] or now)

-- Calculate elapsed time and refill
local elapsed = now - last_refill
local refilled = math.min(tokens + (elapsed * refill_rate), capacity)

-- Check if sufficient tokens
if refilled >= consume then
  -- Consume tokens
  redis.call('HSET', bucket_key, 'tokens', refilled - consume, 'last_refill', now)
  return 1  -- Success
else
  -- Insufficient tokens
  redis.call('HSET', bucket_key, 'tokens', refilled, 'last_refill', now)
  return 0  -- Rate limited
end
```

**ADR References:**

- ADR-0030: Rate Limiting Strategy

**Assigned To:** Issue #L5-10.1.1

---

### 🎯 Epic 10.2: Rate Limiter with Per-User/Tenant Quotas

**Purpose:** Multi-level rate limiting (per-user, per-tenant)
**Files:** 1
**Status:** 🚧 STUB

#### Issue 10.2.1: rate_limiter.py

**File Path:** `k1/l5_infrastructure/rate_limiting/rate_limiter.py`

**Description:**
Multi-level rate limiter coordinating user and tenant quotas.

**Responsibilities:**

1. Enforce per-user rate limits
2. Enforce per-tenant rate limits
3. Coordinate limits (stricter limit applies)
4. Track quota usage per dimension
5. Report violations and trends
6. Support dynamic limit adjustments

**Core Methods:**

```python
class RateLimiter:
    """
    Multi-level rate limiter (per-user, per-tenant, per-tier).

    Hierarchy:
        Tenant Quota (global)
          └─ User Quota (per user)
              └─ Request (allowed/rejected)

    Logic:
        - Check user quota first (stricter typically)
        - Check tenant quota (overall limit)
        - Apply stricter of the two
    """

    def __init__(
        self,
        redis_client: Redis,
        default_user_limit: int = 1000,  # requests/min
        default_tenant_limit: int = 10000,  # requests/min
    ):
        """
        Initialize rate limiter.

        Args:
            redis_client: Redis client
            default_user_limit: Default per-user limit (req/min)
            default_tenant_limit: Default per-tenant limit (req/min)

        ADR: ADR-0030
        """
        # TODO(@resilience-team): Initialize rate limiter
        # 1. Setup default quotas
        # 2. Initialize token buckets
        # 3. Setup metrics
        pass

    async def check_rate_limit(
        self,
        user_id: str,
        tenant_id: str,
        tokens_required: int = 1,
        cognitive_trace_id: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request allowed under rate limits.

        Args:
            user_id: User identifier
            tenant_id: Tenant identifier
            tokens_required: Tokens to consume (default: 1)
            cognitive_trace_id: Trace ID

        Returns:
            (allowed: bool, info: dict)
            where info contains:
                - user_quota_remaining: Tokens left for user
                - tenant_quota_remaining: Tokens left for tenant
                - reset_in_seconds: When quota resets
                - limit_reason: Which limit applied ("user", "tenant", "none")

        Flow:
            1. Get user token bucket
            2. Get tenant token bucket
            3. Check both buckets
            4. If both have tokens: Consume from both, allow
            5. If either depleted: Reject, return remaining

        ADR: ADR-0030
        """
        # TODO(@resilience-team): Implement multi-level check
        pass

    async def set_user_limit(
        self,
        user_id: str,
        requests_per_minute: int,
    ) -> None:
        """
        Set custom per-user rate limit.

        Args:
            user_id: User identifier
            requests_per_minute: New limit

        Use Cases:
            - Premium users: 10,000 req/min
            - Regular users: 1,000 req/min
            - Free users: 100 req/min

        ADR: ADR-0030
        """
        # TODO(@resilience-team): Implement user limit update
        pass

    async def set_tenant_limit(
        self,
        tenant_id: str,
        requests_per_minute: int,
    ) -> None:
        """
        Set custom per-tenant rate limit.

        Args:
            tenant_id: Tenant identifier
            requests_per_minute: New limit

        ADR: ADR-0030
        """
        # TODO(@resilience-team): Implement tenant limit update
        pass

    async def get_quota_status(
        self,
        user_id: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Get quota status for user/tenant.

        Returns:
            Dict with:
                - user_limit_per_minute: User's limit
                - user_consumed_this_minute: Used so far
                - user_remaining: Tokens left
                - tenant_limit_per_minute: Tenant's limit
                - tenant_consumed_this_minute: Used so far
                - tenant_remaining: Tokens left
                - effective_limit: min(user, tenant)
                - reset_in_seconds: Time until reset

        ADR: ADR-0030
        """
        # TODO(@resilience-team): Implement quota status
        pass

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get rate limiting statistics.

        Returns:
            Dict with:
                - requests_allowed_total: Allowed requests
                - requests_rejected_total: Rejected requests
                - rejection_rate_pct: % rejected
                - top_users_by_usage: Users with high usage
                - top_tenants_by_usage: Tenants with high usage
                - quota_resets_per_hour: Reset frequency

        ADR: ADR-0030
        """
        # TODO(@resilience-team): Implement statistics collection
        pass
```

**Multi-Level Quota Example:**

```
Scenario: User "alice" in Tenant "acme-corp"

Tenant "acme-corp":
  - Limit: 10,000 req/min
  - Consumed: 5,000 req/min
  - Remaining: 5,000 tokens

User "alice":
  - Limit: 1,000 req/min
  - Consumed: 800 req/min
  - Remaining: 200 tokens

Decision:
  - User remaining: 200 (more restrictive)
  - Tenant remaining: 5,000
  - Effective limit: 200 tokens
  - Request allowed? Only if both buckets have tokens
```

**ADR References:**

- ADR-0030: Rate Limiting Strategy

**Assigned To:** Issue #L5-10.2.1

---

### 📊 Summary

**Milestone 10: Rate Limiting**

| Epic | Files | Status | Assigned |
|------|-------|--------|----------|
| 10.1: Token Bucket | 1 | 🚧 STUB | @resilience-team |
| 10.2: Rate Limiter | 1 | 🚧 STUB | @resilience-team |
| **Total** | **2** | **🚧 STUB** | @resilience-team |

**Rate Limit Tiers:**

| Tier | Requests/Min | Burst | Cost |
|------|--------------|-------|------|
| **Free** | 100 | 10 | $0 |
| **Standard** | 1,000 | 100 | $99/month |
| **Professional** | 10,000 | 1,000 | $999/month |
| **Enterprise** | 100,000 | 10,000 | Custom |

**Performance Targets:**

| Operation | Latency P50 | Latency P95 |
|-----------|-------------|-------------|
| Rate check | <2ms | <5ms |
| Token consume | <2ms | <5ms |
| Quota status | <3ms | <5ms |

**Milestone 10 Dependencies:**

```
Upstream (Requires):
  - k1.l5_infrastructure.caching (Redis backed)
  - k1.l5_infrastructure.metrics (observability)

Downstream (Provides):
  - k1.l5_infrastructure.admission (quota enforcement)
  - k1.l5_infrastructure.scheduler (rate-aware scheduling)
  - k1.l3_execution.request_router (request routing)
```

---

## Milestone 11: Task Scheduling

### 📋 Overview

**Purpose:** Weighted Fair Queuing (WFQ) task scheduler with priority levels
**Priority:** M1 (High, Performance)
**Status:** 🚧 STUB - NEEDS_IMPLEMENTATION
**Files:** 2 Python modules
**ADRs:** ADR-0031 (Task Scheduling Strategy)
**Assigned To:** @scheduler-team

**Key Features:**

- **Weighted Fair Queuing:** Priority-based scheduling
- **Priority Levels:** 5 levels (Critical, High, Normal, Low, Background)
- **Dynamic Weighting:** Adjust priorities based on load
- **Task Fairness:** Anti-starvation guarantee
- **Performance Budgets:** Per-priority latency targets
- **Metrics:** Queue depth, wait times, throughput
- **Backpressure Integration:** Respect watermarks

**Priority Queue Architecture:**

```
Priority Levels (highest to lowest):
  1. CRITICAL (weight 10x) - System tasks, errors, alerts
  2. HIGH (weight 5x) - User-facing requests, priority users
  3. NORMAL (weight 1x) - Standard requests
  4. LOW (weight 0.5x) - Background tasks
  5. BACKGROUND (weight 0.1x) - Maintenance, cleanup

Weighted Fair Queuing:
  - Service proportion = weight / total_weight
  - CRITICAL: 10 / (10+5+1+0.5+0.1) = 59%
  - HIGH: 5 / 16.6 = 30%
  - NORMAL: 1 / 16.6 = 6%
  - LOW: 0.5 / 16.6 = 3%
  - BACKGROUND: 0.1 / 16.6 = 1%
```

---

### 🎯 Epic 11.1: Task Scheduler with WFQ

**Purpose:** Weighted Fair Queuing scheduler
**Files:** 1
**Status:** 🚧 STUB

#### Issue 11.1.1: scheduler.py

**File Path:** `k1/l5_infrastructure/scheduling/scheduler.py`

**Description:**
Task scheduler implementing Weighted Fair Queuing with priority levels.

**Responsibilities:**

1. Enqueue tasks at various priorities
2. Dequeue tasks in WFQ order
3. Track wait times per priority
4. Enforce anti-starvation (minimum service rate)
5. Report queue statistics
6. Integrate with backpressure system

**Core Methods:**

```python
class TaskScheduler:
    """
    Weighted Fair Queuing task scheduler.

    Priority Levels (with weights):
        CRITICAL: 10x
        HIGH: 5x
        NORMAL: 1x
        LOW: 0.5x
        BACKGROUND: 0.1x

    Guarantees:
        - No task starvation (anti-starvation)
        - Proportional service (weighted fairness)
        - Bounded latency (per priority)
    """

    def __init__(
        self,
        max_queue_depth: int = 10000,
        anti_starvation_check_interval: int = 100,
    ):
        """
        Initialize task scheduler.

        Args:
            max_queue_depth: Max tasks in scheduler
            anti_starvation_check_interval: Service fairness check every N tasks

        ADR: ADR-0031
        """
        # TODO(@scheduler-team): Initialize scheduler
        # 1. Create priority queues (5 levels)
        # 2. Setup WFQ weights
        # 3. Initialize anti-starvation checks
        pass

    async def enqueue(
        self,
        task: Task,
        priority: str = "NORMAL",  # CRITICAL, HIGH, NORMAL, LOW, BACKGROUND
        cognitive_trace_id: Optional[str] = None,
    ) -> str:
        """
        Enqueue task at priority level.

        Args:
            task: Task to schedule
            priority: Priority level
            cognitive_trace_id: Trace ID

        Returns:
            Task ID

        Performance:
            - <2ms P95

        Behavior:
            1. Create task wrapper with timestamp
            2. Add to priority queue
            3. Record metric

        ADR: ADR-0031
        """
        # TODO(@scheduler-team): Implement task enqueue
        pass

    async def dequeue(
        self,
        num_workers: int = 1,
    ) -> List[Task]:
        """
        Dequeue next tasks in WFQ order.

        Args:
            num_workers: Number of workers available

        Returns:
            List of tasks to execute

        Performance:
            - <5ms P95

        WFQ Algorithm:
            1. Calculate remaining quota per priority (based on weight)
            2. Service from highest quota queue first
            3. Dequeue up to num_workers tasks
            4. Update quota tracking
            5. Check anti-starvation (ensure fairness)

        Anti-Starvation:
            - Every 100 tasks, check if low-priority starved
            - If LOW/BACKGROUND haven't run recently: Boost quota

        ADR: ADR-0031
        """
        # TODO(@scheduler-team): Implement WFQ dequeue
        pass

    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get scheduler queue status.

        Returns:
            Dict with:
                - critical_queued: Tasks waiting (CRITICAL)
                - high_queued: Tasks waiting (HIGH)
                - normal_queued: Tasks waiting (NORMAL)
                - low_queued: Tasks waiting (LOW)
                - background_queued: Tasks waiting (BACKGROUND)
                - total_queued: Total tasks
                - queue_depth_pct: Percent of capacity
                - estimated_wait_ms: Est wait for NORMAL priority

        ADR: ADR-0031
        """
        # TODO(@scheduler-team): Implement queue status
        pass

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get scheduler statistics.

        Returns:
            Dict with:
                - tasks_scheduled_total: Total enqueued
                - tasks_completed_total: Total dequeued
                - avg_wait_ms_by_priority: Wait time per priority
                - throughput_tasks_per_sec: Current throughput
                - starvation_incidents: Anti-starvation triggers

        ADR: ADR-0031
        """
        # TODO(@scheduler-team): Implement statistics collection
        pass
```

**WFQ Algorithm Example:**

```
Scenario: 4 priorities queued, 2 workers available

Quota per tick (100 tasks executed):
  - CRITICAL: (10 / 16.6) * 100 = 60 tasks
  - HIGH: (5 / 16.6) * 100 = 30 tasks
  - NORMAL: (1 / 16.6) * 100 = 6 tasks
  - LOW: (0.5 / 16.6) * 100 = 3 tasks
  - BACKGROUND: (0.1 / 16.6) * 100 = 1 task

Dequeue sequence (2 workers):
  1. Dequeue 2 CRITICAL (quota 60)
  2. Dequeue 2 CRITICAL (quota 58)
  3. ... (exhaust CRITICAL quota)
  4. Switch to HIGH (quota 30)
  5. Dequeue 2 HIGH
  6. ... (exhaust HIGH quota)
  7. Switch to NORMAL, then LOW, then BACKGROUND
```

**ADR References:**

- ADR-0031: Task Scheduling Strategy

**Assigned To:** Issue #L5-11.1.1

---

### 🎯 Epic 11.2: Priority Queue with Anti-Starvation

**Purpose:** Priority queue implementation with fairness guarantees
**Files:** 1
**Status:** 🚧 STUB

#### Issue 11.2.1: weighted_queue.py

**File Path:** `k1/l5_infrastructure/scheduling/weighted_queue.py`

**Description:**
Weighted priority queue with anti-starvation enforcement.

**Responsibilities:**

1. Maintain 5 priority queues
2. Calculate WFQ scheduling weights
3. Enforce anti-starvation rules
4. Track service time per priority
5. Dynamically adjust weights based on load
6. Report fairness metrics

**Core Methods:**

```python
class WeightedQueue:
    """
    Weighted priority queue with anti-starvation.

    Anti-Starvation Strategy:
        - Track last service time per priority
        - If not serviced in N iterations: Boost weight
        - Ensure minimum throughput for all priorities
    """

    def __init__(
        self,
        starvation_threshold_tasks: int = 1000,
    ):
        """
        Initialize weighted queue.

        Args:
            starvation_threshold_tasks: Check starvation every N tasks

        ADR: ADR-0031
        """
        # TODO(@scheduler-team): Initialize weighted queue
        # 1. Create 5 priority queues
        # 2. Setup weights and quotas
        # 3. Initialize starvation tracking
        pass

    async def enqueue(
        self,
        priority: str,
        item: Any,
    ) -> None:
        """Enqueue item at priority level."""
        # TODO(@scheduler-team): Implement priority queue enqueue
        pass

    async def dequeue(self, num_items: int) -> List[Any]:
        """
        Dequeue items in WFQ order (anti-starvation).

        Args:
            num_items: Number of items to dequeue

        Returns:
            List of items in service order

        Algorithm:
            1. Calculate current weight per priority
            2. Dequeue from highest weight queue first
            3. Track last service time per priority
            4. Check anti-starvation condition
            5. Boost starved queues if needed

        ADR: ADR-0031
        """
        # TODO(@scheduler-team): Implement WFQ dequeue
        pass

    def check_starvation(self) -> Dict[str, bool]:
        """
        Check if any priority starved.

        Returns:
            Dict mapping priority to starvation status

        Logic:
            - If last_service_time > threshold: STARVED
            - Trigger weight boost for starved queues

        ADR: ADR-0031
        """
        # TODO(@scheduler-team): Implement starvation detection
        pass

    async def boost_starved(self) -> None:
        """Temporarily boost weight of starved queues."""
        # TODO(@scheduler-team): Implement starvation recovery
        pass

    def get_queue_depths(self) -> Dict[str, int]:
        """Get depth of each priority queue."""
        # TODO(@scheduler-team): Implement queue depth reporting
        pass

    def get_fairness_metrics(self) -> Dict[str, Any]:
        """
        Get fairness metrics.

        Returns:
            Dict with:
                - service_time_by_priority: Time serviced per priority
                - expected_service_time_by_priority: WFQ expected
                - fairness_ratio: Actual / Expected
                - starvation_incidents: Number of boosts applied

        Fairness Ratio:
            - Ideal = 1.0 (perfect fairness)
            - > 1.2: Priority over-served
            - < 0.8: Priority under-served

        ADR: ADR-0031
        """
        # TODO(@scheduler-team): Implement fairness metrics
        pass
```

**Anti-Starvation Algorithm:**

```
Before Service:
  Service time per priority (microseconds):
    CRITICAL: 50 sec
    HIGH: 40 sec
    NORMAL: 10 sec
    LOW: 0.5 sec (under-served!)
    BACKGROUND: 0.1 sec (starved!)

Expected Service Time (WFQ):
    CRITICAL: 59% of total
    HIGH: 30% of total
    NORMAL: 6% of total
    LOW: 3% of total
    BACKGROUND: 1% of total

Detection:
  LOW: 0.5 / 3% = 17% of expected → Starvation detected
  BACKGROUND: 0.1 / 1% = 10% of expected → Starvation detected

Response:
  1. Boost weight for LOW and BACKGROUND
    - LOW weight: 0.5 → 2.0 (4× boost)
    - BACKGROUND weight: 0.1 → 0.5 (5× boost)
  2. Next 100 dequeue operations use new weights
  3. LOW and BACKGROUND get more service
  4. Check again after 1000 tasks
```

**ADR References:**

- ADR-0031: Task Scheduling Strategy

**Assigned To:** Issue #L5-11.2.1

---

### 📊 Summary

**Milestone 11: Task Scheduling**

| Epic | Files | Status | Assigned |
|------|-------|--------|----------|
| 11.1: Task Scheduler | 1 | 🚧 STUB | @scheduler-team |
| 11.2: Weighted Queue | 1 | 🚧 STUB | @scheduler-team |
| **Total** | **2** | **🚧 STUB** | @scheduler-team |

**Priority Levels & Weights:**

| Priority | Weight | Service % | Latency Target | Use Case |
|----------|--------|-----------|-----------------|----------|
| **CRITICAL** | 10x | 59% | <50ms | System tasks, errors |
| **HIGH** | 5x | 30% | <100ms | User requests, priority users |
| **NORMAL** | 1x | 6% | <500ms | Standard requests |
| **LOW** | 0.5x | 3% | <2s | Background tasks |
| **BACKGROUND** | 0.1x | 1% | <10s | Maintenance, cleanup |

**Performance Targets:**

| Operation | Latency P50 | Latency P95 |
|-----------|-------------|-------------|
| Enqueue | <1ms | <3ms |
| Dequeue (WFQ) | <5ms | <10ms |
| Starvation check | <10ms | <20ms |

**Anti-Starvation Guarantee:**

- Minimum throughput: >0.5% of capacity for any priority
- Starvation recovery: Detects and boosts within 1000 tasks
- Fairness ratio: 0.8-1.2× of WFQ expected

**Milestone 11 Dependencies:**

```
Upstream (Requires):
  - k1.l5_infrastructure.backpressure (watermark awareness)
  - k1.l5_infrastructure.metrics (observability)
  - k1.l5_infrastructure.rate_limiting (quota coordination)

Downstream (Provides):
  - k1.l5_infrastructure.admission (admission control)
  - k1.l3_execution.request_router (request routing)
  - k1.l3_execution.model_hub (task execution)
```

---

## 📋 Milestone 12: Admission Control

### 🎯 Overview

Admission Control is the gateway layer that determines whether incoming tasks should be accepted or rejected based on system capacity, quality-of-service constraints, and backpressure signals. It enforces admission guarantees while preventing resource starvation and ensuring fairness across all request types.

**Core Functions:**

1. **Admission Decision Logic** — Task admission based on system state, capacity, privacy constraints
2. **Request Validation** — Type checking, schema validation, privacy band enforcement
3. **Fallback Handling** — Graceful degradation, queueing overflow, circuit breaker integration
4. **Quality-of-Service Enforcement** — Respect backpressure, rate limits, and scheduling constraints
5. **Anti-Starvation Guarantees** — Prioritized admission for high-priority tasks, quota reservation

**Why It Matters:**

- **Prevents Overload:** Rejects excess load before it overwhelms downstream systems
- **Preserves Fairness:** Ensures low-priority tasks always get some admission slots
- **Enforces Privacy:** RED-band tasks never mixed with non-RED storage
- **Enables QoS:** Critical tasks admitted even under heavy load

**Key Metrics:**

- Admission acceptance rate: 95-99%
- Decision latency: <10ms P95
- Anti-starvation enforcement: 100% for reserved slots
- Privacy policy violations: 0

**Architecture:**

```
Request → Type Validator → Privacy Checker → Admission Controller → Scheduler
              (Schema)      (RED/AMBER/GREEN)  (Capacity/QoS)      (Enqueue)
                                                     ↓
                                            Rate Limiter (per-user/tenant)
                                                     ↓
                                            Backpressure Monitor
                                                     ↓
                                            Circuit Breaker (fallback)
```

---

### 📌 Epic 12.1: Admission Controller

**File:** `k1/l5_infrastructure/admission/admission_controller.py`

**Purpose:** Core admission decision engine that orchestrates validation, capacity checking, and fallback strategies.

**Responsibilities:**

- Receive incoming task requests (Request object)
- Apply multi-level validation (type, privacy, schema)
- Check system capacity and backpressure signals
- Make binary admit/reject decision
- Apply fallback strategies (queueing, circuit breaker)
- Track admission metrics and telemetry

**Key Concepts:**

1. **Admission Checks (In Order):**
   - Type validation (known task type)
   - Schema validation (valid request structure)
   - Privacy policy enforcement (RED-band, AMBER-band)
   - Rate limit check (per-user, per-tenant quotas)
   - Capacity check (queue depth, memory pressure)
   - Anti-starvation check (reserved slots for HIGH/CRITICAL)
   - Backpressure evaluation (soft/hard/critical watermarks)

2. **Admission Decision States:**
   - **ADMITTED:** Task accepted, added to scheduler queue
   - **QUEUED:** Task accepted but delayed, added to overflow queue
   - **RATE_LIMITED:** Request rejected (quota exceeded)
   - **CAPACITY_EXCEEDED:** Request rejected (queue full)
   - **PRIVACY_VIOLATION:** Request rejected (RED-band mismatch)
   - **FALLBACK_DEGRADED:** Task accepted with reduced SLA

3. **Fallback Strategies:**
   - **Soft Backpressure (75% queue):** Queue new tasks with 10% throttle
   - **Hard Backpressure (85% queue):** Queue new tasks with 20% throttle
   - **Critical Backpressure (95% queue):** Reject non-critical (LOW/BACKGROUND), throttle others
   - **Graceful Degradation:** Fallback to simpler model if capacity exceeded

4. **Anti-Starvation Logic:**
   - Reserve 5-10% of admission slots for HIGH/CRITICAL tasks
   - Check: If (high_priority_reserved_count < high_priority_reserve_slots) then ADMIT
   - Override rate limits and backpressure for reserved admission
   - Metrics: Track reserved slot usage, anti-starvation triggers

**Algorithm (Pseudo-Code):**

```
async def admit(request: Request) -> AdmissionDecision:
    # 1. Type Validation
    if not is_valid_task_type(request.task_type):
        return AdmissionDecision.TYPE_INVALID

    # 2. Schema Validation
    if not schema_validator.validate(request):
        return AdmissionDecision.SCHEMA_INVALID

    # 3. Privacy Check
    if not privacy_enforcer.can_admit(request.privacy_band):
        return AdmissionDecision.PRIVACY_VIOLATION

    # 4. Rate Limit Check
    if not rate_limiter.is_allowed(request.user_id, request.tenant_id):
        return AdmissionDecision.RATE_LIMITED

    # 5. Anti-Starvation Check (Override if needed)
    if request.priority in [CRITICAL, HIGH]:
        reserved_capacity = queue_depth / 10  # Reserve 10%
        if high_priority_queue.size() < reserved_capacity:
            return AdmissionDecision.ADMITTED  # Use reserved slot

    # 6. Capacity Check
    queue_utilization = queue_depth / queue_capacity
    if queue_utilization >= 0.95:  # Critical watermark
        if request.priority in [LOW, BACKGROUND]:
            return AdmissionDecision.CAPACITY_EXCEEDED
        if request.priority == NORMAL:
            # Throttle NORMAL tasks
            if random() > 0.8:  # Allow 20%
                return AdmissionDecision.QUEUED
            else:
                return AdmissionDecision.CAPACITY_EXCEEDED

    # 7. Backpressure Evaluation
    backpressure_level = backpressure_monitor.get_level()
    if backpressure_level == CRITICAL and request.priority == LOW:
        return AdmissionDecision.CAPACITY_EXCEEDED

    # 8. Emit metrics and enqueue
    metrics.admission_accepted_total.inc(request.priority)
    return AdmissionDecision.ADMITTED
```

**Key Methods:**

```python
class AdmissionController:
    """Core admission control engine."""

    async def admit(self, request: Request) -> AdmissionDecision:
        """
        Evaluate and admit/reject incoming task request.

        Args:
            request: Task request with type, priority, privacy_band, user_id, tenant_id

        Returns:
            AdmissionDecision: ADMITTED, QUEUED, RATE_LIMITED, CAPACITY_EXCEEDED, PRIVACY_VIOLATION

        Performance: <10ms P95 decision time
        """

    async def get_admission_status(self) -> AdmissionStatus:
        """
        Get current admission control state (capacity, queue depth, rejection rate).

        Returns:
            AdmissionStatus with queue_depth, capacity, rejection_rate, backpressure_level
        """

    async def update_backpressure_signal(self, level: BackpressureLevel) -> None:
        """
        Receive backpressure signal from downstream (watermark change).

        Args:
            level: BackpressureLevel (SOFT, HARD, CRITICAL)
        """

    async def get_metrics(self) -> AdmissionMetrics:
        """
        Get admission metrics (acceptance rate, rejections by reason, anti-starvation triggers).

        Returns:
            AdmissionMetrics with acceptance_rate, rejection_breakdown, starvation_triggers
        """
```

**Configuration (YAML):**

```yaml
admission_control:
  queue_capacity: 10000
  reserved_slots_percentage: 10  # 10% reserved for HIGH/CRITICAL
  soft_watermark: 0.75  # Start throttling at 75%
  hard_watermark: 0.85  # Increase throttling at 85%
  critical_watermark: 0.95  # Reject LOW/BACKGROUND at 95%

  soft_throttle_rate: 0.10  # Reject 10% of NORMAL tasks
  hard_throttle_rate: 0.20  # Reject 20% of NORMAL tasks

  # Anti-starvation config
  starvation_check_interval_ms: 100
  starvation_threshold: 1000  # Check after 1000 tasks admitted
  high_priority_boost_factor: 4  # If CRITICAL/HIGH underserved, boost admission
```

**Performance Budgets:**

- Admission decision: <10ms P95
- Type validation: <1ms P95
- Schema validation: <2ms P95
- Rate limit check: <5ms P95
- Capacity check: <1ms P95
- Anti-starvation check: <1ms P95
- Metrics emission: <0.5ms P95

**Related ADRs:** ADR-0032 (Admission Control Design)

**Integration Points:**

- Receives backpressure signals from `backpressure_manager`
- Calls `rate_limiter` for quota checks
- Calls `task_validator` for schema validation
- Calls `privacy_enforcer` for RED-band checks
- Emits to Prometheus metrics (acceptance_rate, rejections, starvation_triggers)
- Sends accepted tasks to `scheduler` (weighted queue)

---

### 📌 Epic 12.2: Task Validator

**File:** `k1/l5_infrastructure/admission/task_validator.py`

**Purpose:** Schema validation and request type checking to ensure all admitted tasks are well-formed and compatible with downstream execution.

**Responsibilities:**

- Register and manage task schemas (JSON Schema, FlatBuffers)
- Validate incoming requests against schemas
- Type checking (known task types)
- Field validation (required fields, type constraints)
- Performance validation (check against SLA requirements)
- Privacy metadata validation

**Key Concepts:**

1. **Schema Registry:**
   - Built-in schemas for 7 standard task types (inference, training, evaluation, etc.)
   - User-defined schemas loaded from `k1/contracts/jsonschema/tasks/`
   - Schema versioning (v1.0, v1.1, v2.0)
   - Hot-reload support for schema updates

2. **Validation Levels:**
   - **Type Check:** Is task_type in registered_types?
   - **Schema Check:** Does request match JSON Schema?
   - **Field Check:** Are required fields present? Types correct?
   - **Performance Check:** Does SLA fit within execution budgets?
   - **Privacy Check:** Privacy band metadata present and valid?

3. **Error Handling:**
   - Detailed error messages (field name, schema path, constraint violated)
   - Validation cache (avoid re-validating identical schemas)
   - Fallback to lenient mode (warn instead of reject for unknown fields)

**Algorithm (Pseudo-Code):**

```
def validate(request: Request) -> ValidationResult:
    # 1. Type Check
    if request.task_type not in schema_registry:
        return ValidationResult.UNKNOWN_TYPE

    schema = schema_registry[request.task_type]

    # 2. Schema Validation (JSON Schema)
    validator = jsonschema.Draft7Validator(schema)
    errors = list(validator.iter_errors(request.payload))
    if errors:
        return ValidationResult.SCHEMA_INVALID(errors[0])

    # 3. Field Extraction & Type Validation
    required_fields = schema.get('required', [])
    for field in required_fields:
        if field not in request.payload:
            return ValidationResult.MISSING_FIELD(field)

        expected_type = schema['properties'][field]['type']
        actual_type = type(request.payload[field])
        if not type_matches(actual_type, expected_type):
            return ValidationResult.TYPE_MISMATCH(field, expected_type, actual_type)

    # 4. Performance Validation
    sla_deadline = request.payload.get('deadline_ms', DEFAULT_DEADLINE)
    if sla_deadline < MIN_SLA_MS or sla_deadline > MAX_SLA_MS:
        return ValidationResult.SLA_OUT_OF_RANGE

    # 5. Privacy Metadata
    privacy_band = request.payload.get('privacy_band', GREEN)
    if privacy_band not in [RED, AMBER, GREEN]:
        return ValidationResult.INVALID_PRIVACY_BAND

    return ValidationResult.VALID
```

**Key Methods:**

```python
class TaskValidator:
    """Schema validation for task requests."""

    def register_schema(self, task_type: str, schema: dict, version: str = "1.0") -> None:
        """
        Register a new task type schema.

        Args:
            task_type: Unique task type identifier (e.g., "inference")
            schema: JSON Schema dict
            version: Schema version (e.g., "1.0")
        """

    def validate(self, request: Request) -> ValidationResult:
        """
        Validate request against registered schema.

        Args:
            request: Task request to validate

        Returns:
            ValidationResult with status and error details if invalid

        Performance: <2ms P95 validation time (with caching)
        """

    def get_schema(self, task_type: str, version: str = "latest") -> dict:
        """
        Get registered schema for task type.

        Args:
            task_type: Task type identifier
            version: Schema version (default: latest)

        Returns:
            JSON Schema dict
        """

    def reload_schemas_from_disk(self) -> None:
        """
        Hot-reload schemas from `k1/contracts/jsonschema/tasks/`.

        Useful for deploying new schemas without restarting.
        """

    def get_validation_metrics(self) -> ValidationMetrics:
        """
        Get validation statistics (validation count, error breakdown, cache hit rate).

        Returns:
            ValidationMetrics with validation_count, errors_by_type, cache_hit_rate
        """
```

**Standard Task Types (Built-In Schemas):**

1. **inference** — Run model inference on input data
   - Required: model_id, input_data, priority
   - Optional: deadline_ms, privacy_band, batch_size

2. **training** — Train model on dataset
   - Required: model_id, dataset_ref, learning_rate
   - Optional: num_epochs, validation_split, privacy_band

3. **evaluation** — Evaluate model on test set
   - Required: model_id, test_dataset_ref, metrics
   - Optional: threshold, privacy_band

4. **preprocessing** — Prepare data for training
   - Required: dataset_ref, steps
   - Optional: output_format, privacy_band

5. **postprocessing** — Transform model outputs
   - Required: model_output, transformation_type
   - Optional: privacy_band

6. **monitoring** — Health check and telemetry
   - Required: component_id, check_type
   - Optional: threshold_alert

7. **maintenance** — Background cleanup tasks
   - Required: maintenance_type, target_component
   - Optional: maintenance_window

**Performance Budgets:**

- Schema registration: <1ms
- Validation (with cache): <2ms P95
- Schema reload: <100ms
- Metrics aggregation: <5ms

**Related ADRs:** ADR-0032 (Admission Control Design)

**Integration Points:**

- Called by `admission_controller` for request validation
- Loads schemas from `k1/contracts/jsonschema/tasks/`
- Emits to Prometheus metrics (validation_count, error_breakdown, cache_hit_rate)

---

### 📊 Milestone 12 Summary

| Component | Files | Epics | Lines | Status |
|-----------|-------|-------|-------|--------|
| **Admission Control** | 2 | 2 | ~800 | 📋 Planned |
| Epic 12.1: Admission Controller | 1 | - | ~400 | Orchestrator, capacity checks, anti-starvation |
| Epic 12.2: Task Validator | 1 | - | ~400 | Schema registry, validation, error handling |

**Performance Targets:**

- Admission decision: <10ms P95
- Task validation: <2ms P95
- Anti-starvation check: <1ms P95
- Validation cache hit rate: >90%

**Quality Gates:**

- ✅ Admission acceptance rate: 95-99%
- ✅ Privacy policy violations: 0
- ✅ Schema validation errors: <1%
- ✅ Backpressure compliance: 100%

**Failure Modes & Mitigations:**

| Failure Mode | Mitigation |
|------|-----------|
| Admission bottleneck (>10ms) | Cache schemas, use Redis for distributed quota |
| Schema mismatch | Lenient mode (warn, admit) for unknown fields |
| Anti-starvation collision | Lock-free data structures, CAS operations |
| Privacy policy bypass | Reject immediately, emit security event |

**Configuration Schema:**

```yaml
admission_control:
  enabled: true
  queue_capacity: 10000
  reserved_slots_percentage: 10
  soft_watermark: 0.75
  hard_watermark: 0.85
  critical_watermark: 0.95

task_validator:
  schema_cache_enabled: true
  schema_cache_size: 1000
  lenient_mode_enabled: false  # Warn on unknown fields
  hot_reload_enabled: true
```

**Milestone 12 Dependencies:**

```
Upstream (Requires):
  - k1.l5_infrastructure.rate_limiting (quota checks)
  - k1.l5_infrastructure.backpressure (watermark signals)
  - k1.l5_infrastructure.scheduling (queue integration)
  - k1.contracts.jsonschema (task schemas)

Downstream (Provides):
  - k1.l3_execution.request_router (admitted tasks)
  - k1.l3_execution.model_hub (task execution)
  - k1.l2_orchestration.orchestrator (system health)
```

---

## 📋 Milestone 13: Module System

### 🎯 Overview

The Module System (Plugin Architecture) enables dynamic discovery, loading, and management of extension modules without requiring service restarts. It provides hot-reload capability, version compatibility checking, and isolated module lifecycles for extensibility.

**Core Functions:**

1. **Plugin Discovery** — Scan filesystem/registry for available modules
2. **Plugin Loading** — Load module bytecode, initialize dependencies
3. **Hot-Reload** — Update running modules without downtime
4. **Versioning & Compatibility** — Enforce version contracts and API compatibility
5. **Lifecycle Management** — Init/activate/deactivate/cleanup hooks

**Why It Matters:**

- **Zero-Downtime Deployments:** Update plugins without restarting K1
- **Extensibility:** Community can build plugins for custom use cases
- **Isolation:** Failed plugins don't crash main system
- **Versioning:** Multiple versions coexist, clients choose API version
- **Flexibility:** Load/unload plugins based on runtime conditions

**Key Metrics:**

- Plugin discovery time: <50ms
- Plugin load time: <100ms (cold), <10ms (warm cache)
- Hot-reload success rate: 99%+
- Plugin isolation: 100% (crashes contained)
- Version compatibility check: <5ms

**Architecture:**

```
Plugin Registry → Discovery Scanner → Loader Cache → Module Manager → Lifecycle Hooks
   (Metadata)      (Filesystem)       (Hot Cache)    (State FSM)      (Init/Run/Cleanup)
                                                          ↓
                                                   Dependency Resolver
                                                          ↓
                                                   Compatibility Checker
```

---

### 📌 Epic 13.1: Plugin Discovery

**File:** `k1/l5_infrastructure/modules/plugin_discovery.py`

**Purpose:** Scan and register available plugin modules, maintain plugin registry with metadata and versioning information.

**Responsibilities:**

- Scan `k1/l5_infrastructure/modules/` for plugin definitions
- Parse plugin manifests (YAML/JSON metadata files)
- Register plugins with versions, dependencies, capabilities
- Track plugin availability and compatibility
- Support dynamic registration (add plugins without restart)
- Provide plugin lookup by name, version, capability

**Key Concepts:**

1. **Plugin Manifest (YAML):**

   ```yaml
   name: "custom_inference_optimizer"
   version: "1.0.0"
   api_version: "1.0"  # K1 API version required
   author: "community-contributor"
   description: "Custom optimizer for inference workloads"

   dependencies:
     - name: "model_cache"
       version: ">=1.0.0"
     - name: "thermal_manager"
       version: ">=2.0.0"

   capabilities:
     - "inference_optimization"
     - "cache_invalidation"
     - "thermal_feedback"

   entry_point: "custom_optimizer.module:load"
   config_schema: "config/custom_optimizer_schema.json"
   ```

2. **Plugin Registry:**
   - In-memory mapping: plugin_name → PluginMetadata
   - Versioned lookups: plugin_name:version
   - Capability index: capability → [plugins]
   - Dependency graph: plugin → [dependencies]

3. **Discovery Modes:**
   - **Filesystem Scan:** Walk `k1/l5_infrastructure/modules/*/manifest.yaml`
   - **Dynamic Registration:** API call to register plugin at runtime
   - **Remote Registry:** Future support for hosted plugin registries

4. **Plugin States:**
   - **AVAILABLE:** Registered but not loaded
   - **LOADING:** In progress
   - **LOADED:** Ready to use
   - **INCOMPATIBLE:** Version mismatch or missing dependencies
   - **DISABLED:** User disabled
   - **FAILED:** Load failed

**Algorithm (Pseudo-Code):**

```
def discover_plugins():
    registry = {}

    # 1. Scan filesystem
    plugin_dirs = glob("k1/l5_infrastructure/modules/*/manifest.yaml")

    for manifest_path in plugin_dirs:
        manifest = load_yaml(manifest_path)

        # 2. Parse manifest
        plugin_id = f"{manifest.name}:{manifest.version}"

        # 3. Validate manifest
        if not validate_manifest(manifest):
            log_error(f"Invalid manifest: {manifest_path}")
            continue

        # 4. Check compatibility
        api_version = manifest.api_version
        if not is_api_compatible(api_version):
            registry[plugin_id] = PluginMetadata(status=INCOMPATIBLE)
            continue

        # 5. Register plugin
        registry[plugin_id] = PluginMetadata(
            name=manifest.name,
            version=manifest.version,
            dependencies=manifest.dependencies,
            capabilities=manifest.capabilities,
            entry_point=manifest.entry_point,
            status=AVAILABLE
        )

    return registry
```

**Key Methods:**

```python
class PluginDiscovery:
    """Plugin discovery and registry management."""

    async def discover_plugins(self) -> PluginRegistry:
        """
        Scan filesystem for available plugins and build registry.

        Returns:
            PluginRegistry with all discovered plugins and their metadata

        Performance: <50ms scan time
        """

    async def register_plugin(self, manifest: dict) -> PluginMetadata:
        """
        Register a plugin at runtime.

        Args:
            manifest: Plugin manifest dict (name, version, capabilities, etc.)

        Returns:
            PluginMetadata with assigned status

        Raises:
            InvalidManifestError if manifest validation fails
            IncompatibleVersionError if API version mismatch
        """

    async def get_plugin(self, name: str, version: str = "latest") -> PluginMetadata:
        """
        Get plugin metadata by name and version.

        Args:
            name: Plugin name
            version: Version string (default: latest)

        Returns:
            PluginMetadata or None if not found
        """

    async def find_plugins_by_capability(self, capability: str) -> List[PluginMetadata]:
        """
        Find all plugins providing a capability.

        Args:
            capability: Capability name (e.g., "inference_optimization")

        Returns:
            List of PluginMetadata with requested capability
        """

    async def resolve_dependencies(self, plugin_id: str) -> List[PluginMetadata]:
        """
        Resolve and validate all dependencies for a plugin.

        Args:
            plugin_id: Plugin identifier (name:version)

        Returns:
            List of required plugins in dependency order

        Raises:
            UnresolvedDependencyError if dependency not found
            CircularDependencyError if circular dependency detected
        """

    async def get_registry_snapshot(self) -> dict:
        """
        Get current registry state (plugin count, statuses, capabilities).

        Returns:
            Snapshot with total_plugins, status_breakdown, capability_index
        """
```

**Plugin Metadata:**

```python
@dataclass
class PluginMetadata:
    name: str
    version: str
    api_version: str  # Required K1 API version (e.g., "1.0")
    author: str
    description: str
    entry_point: str  # Module path: "module.path:function"
    capabilities: List[str]  # ["capability1", "capability2"]
    dependencies: List[Dict[str, str]]  # [{"name": "...", "version": "..."}]
    config_schema: Optional[str]  # Path to JSON schema
    status: PluginStatus  # AVAILABLE, LOADING, LOADED, INCOMPATIBLE, DISABLED, FAILED
    error_message: Optional[str]  # If FAILED/INCOMPATIBLE
    loaded_at: Optional[datetime]  # Timestamp when loaded
    last_check: datetime  # Last discovery/compatibility check
```

**Performance Budgets:**

- Plugin discovery: <50ms
- Dependency resolution: <10ms (with caching)
- Plugin lookup: <1ms
- Capability search: <5ms

**Related ADRs:** ADR-0033 (Module System Design)

**Integration Points:**

- Scans from `k1/l5_infrastructure/modules/` directory structure
- Loads manifests (YAML/JSON) from each plugin
- Called by `plugin_loader` to load discovered plugins
- Emits to Prometheus metrics (plugin_count, discovery_time, compatibility_rate)

---

### 📌 Epic 13.2: Plugin Loader

**File:** `k1/l5_infrastructure/modules/plugin_loader.py`

**Purpose:** Load discovered plugins into memory, manage module lifecycle (init/activate/deactivate/cleanup), handle hot-reload without service restarts.

**Responsibilities:**

- Load plugin bytecode and initialize module
- Manage plugin lifecycle states (LOADING → LOADED → ACTIVE → INACTIVE)
- Handle hot-reload (swap bytecode, migrate state)
- Manage plugin isolation (separate namespaces, resource limits)
- Track plugin state and health
- Provide plugin lifecycle hooks (on_load, on_activate, on_deactivate, on_unload)

**Key Concepts:**

1. **Plugin Lifecycle:**

   ```
   AVAILABLE → LOADING → LOADED → ACTIVE → [INACTIVE] → UNLOADING → UNLOADED
                 ↓         ↓
              [FAILED] [INCOMPATIBLE]
   ```

2. **Load Strategies:**
   - **Cold Load:** Load from disk, parse manifests, initialize (~100ms)
   - **Warm Load:** Use cached bytecode, quick init (~10ms)
   - **Hot-Reload:** Swap bytecode, migrate state, preserve context (~50ms)

3. **Module Isolation:**
   - Separate Python namespace per plugin (avoid globals)
   - Resource limits (memory, CPU, timeout)
   - Error containment (plugin failure doesn't crash K1)
   - Cleanup on unload (release resources)

4. **Hot-Reload Process:**
   - Drain active requests (wait for pending operations)
   - Backup current module state
   - Swap bytecode (replace .pyc)
   - Execute on_reload hook if present
   - Verify compatibility with current API
   - If failed: Rollback to previous version
   - Emit success/failure metrics

**Algorithm (Pseudo-Code):**

```
async def load_plugin(plugin_id: str, strategy: str = "cold"):
    plugin_meta = registry.get(plugin_id)

    # 1. Resolve dependencies
    deps = discovery.resolve_dependencies(plugin_id)
    for dep in deps:
        if dep.status != LOADED:
            await load_plugin(dep.id)

    # 2. Choose load strategy
    if strategy == "cold":
        plugin_meta.status = LOADING
        module = load_bytecode(plugin_meta.entry_point)
        context = module.load()  # Call load() hook

    elif strategy == "hot":
        # Drain active requests
        await drain_active_requests(plugin_id)

        # Backup state
        old_module = loaded_modules[plugin_id]
        backup_state = old_module.export_state()

        # Load new bytecode
        new_module = load_bytecode(plugin_meta.entry_point)

        # Migrate state
        if hasattr(new_module, 'migrate_state'):
            new_module.migrate_state(backup_state)

        # Update reference
        loaded_modules[plugin_id] = new_module

        # Call reload hook
        if hasattr(new_module, 'on_reload'):
            await new_module.on_reload()

    # 3. Verify compatibility
    if not verify_api_compatibility(module, plugin_meta.api_version):
        plugin_meta.status = INCOMPATIBLE
        raise IncompatiblePluginError()

    # 4. Register module
    loaded_modules[plugin_id] = module
    plugin_meta.status = LOADED

    return module
```

**Key Methods:**

```python
class PluginLoader:
    """Plugin loading and lifecycle management."""

    async def load_plugin(self, plugin_id: str, strategy: str = "cold") -> object:
        """
        Load a plugin into memory.

        Args:
            plugin_id: Plugin identifier (name:version)
            strategy: Load strategy ("cold", "warm", "hot")

        Returns:
            Loaded module object

        Performance:
            - Cold: <100ms P95
            - Warm: <10ms P95
            - Hot: <50ms P95

        Raises:
            PluginNotFoundError if plugin not in registry
            IncompatiblePluginError if API version mismatch
            DependencyError if dependency not available
        """

    async def unload_plugin(self, plugin_id: str) -> None:
        """
        Unload a plugin and clean up resources.

        Args:
            plugin_id: Plugin identifier (name:version)

        Calls on_unload() hook if present
        """

    async def hot_reload_plugin(self, plugin_id: str) -> None:
        """
        Hot-reload a plugin (update bytecode without restart).

        Args:
            plugin_id: Plugin identifier (name:version)

        Process:
            1. Drain active requests
            2. Backup current state
            3. Load new bytecode
            4. Migrate state if provided
            5. Verify compatibility
            6. Swap module reference

        Performance: <50ms P95 reload time
        Success rate: 99%+

        Raises:
            PluginNotFoundError if plugin not loaded
            HotReloadError if reload failed (automatic rollback)
        """

    async def get_plugin(self, plugin_id: str) -> object:
        """
        Get loaded plugin module by ID.

        Args:
            plugin_id: Plugin identifier (name:version)

        Returns:
            Loaded module object

        Raises:
            PluginNotFoundError if not loaded
        """

    async def list_loaded_plugins(self) -> List[dict]:
        """
        Get list of all loaded plugins with status.

        Returns:
            List of dicts with plugin_id, status, load_time, memory_usage
        """

    async def get_plugin_health(self, plugin_id: str) -> PluginHealth:
        """
        Get health status of a plugin (uptime, error rate, resource usage).

        Args:
            plugin_id: Plugin identifier (name:version)

        Returns:
            PluginHealth with status, uptime, errors, memory, cpu
        """

    async def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> None:
        """
        Enable/disable a plugin (doesn't unload, just marks inactive).

        Args:
            plugin_id: Plugin identifier (name:version)
            enabled: True to enable, False to disable
        """
```

**Plugin Lifecycle Hooks:**

```python
# Optional hooks in plugin module:

async def load() -> dict:
    """Called when plugin first loads. Initialize state."""
    return {"initialized": True, "cache": {}}

async def on_activate() -> None:
    """Called when plugin becomes active."""
    await initialize_resources()

async def on_deactivate() -> None:
    """Called when plugin becomes inactive."""
    await cleanup_resources()

async def on_reload() -> None:
    """Called after hot-reload (state already migrated)."""
    await verify_state()
    await reinitialize_caches()

def migrate_state(old_state: dict) -> None:
    """Called to migrate state from old version to new."""
    # Transform old_state schema to new version
    pass

async def on_unload() -> None:
    """Called when plugin unloads. Final cleanup."""
    await close_connections()
    await persist_state()
```

**Performance Budgets:**

- Cold load: <100ms P95
- Warm load: <10ms P95
- Hot-reload: <50ms P95
- Hot-reload rollback: <10ms if failed
- Unload: <20ms P95
- Health check: <5ms P95

**Related ADRs:** ADR-0033 (Module System Design)

**Integration Points:**

- Works with `plugin_discovery` to get plugin metadata
- Loads modules from entry points defined in manifests
- Manages module state (backup/restore for hot-reload)
- Emits to Prometheus metrics (load_time, reload_time, plugin_errors, resource_usage)
- Provides hooks for plugins to integrate with K1

---

### 📊 Milestone 13 Summary

| Component | Files | Epics | Lines | Status |
|-----------|-------|-------|-------|--------|
| **Module System** | 2 | 2 | ~850 | 📋 Planned |
| Epic 13.1: Plugin Discovery | 1 | - | ~420 | Registry, manifest parsing, capability indexing |
| Epic 13.2: Plugin Loader | 1 | - | ~430 | Lifecycle management, hot-reload, isolation |

**Performance Targets:**

- Plugin discovery: <50ms
- Plugin load (cold): <100ms
- Plugin load (warm): <10ms
- Hot-reload time: <50ms P95
- Hot-reload success rate: 99%+

**Quality Gates:**

- ✅ Plugin isolation: 100% (failed plugins contained)
- ✅ Hot-reload compatibility: 100% API check
- ✅ Dependency resolution: <10ms P95
- ✅ Version compatibility: 0 incompatibilities (auto-detect)

**Failure Modes & Mitigations:**

| Failure Mode | Mitigation |
|------|-----------|
| Circular dependencies | Topological sort + cycle detection |
| Failed hot-reload | Automatic rollback to previous version |
| Plugin crash | Isolate in separate namespace, emit alert |
| Memory leak | Resource limits per plugin, periodic cleanup |
| Stale bytecode cache | Version tracking, TTL-based invalidation |

**Configuration Schema:**

```yaml
module_system:
  enabled: true
  plugin_scan_interval_seconds: 60
  hot_reload_enabled: true
  hot_reload_timeout_ms: 5000  # Timeout for hot-reload

  plugin_isolation:
    enabled: true
    memory_limit_mb: 256  # Per plugin
    cpu_timeout_seconds: 30

  cache:
    bytecode_cache_enabled: true
    cache_ttl_seconds: 3600
    max_cache_size_mb: 512
```

**Milestone 13 Dependencies:**

```
Upstream (Requires):
  - k1.l5_infrastructure.admission (plugin admission checks)
  - k1.l5_infrastructure.metrics (observability)
  - Python importlib (dynamic module loading)

Downstream (Provides):
  - k1.l5_infrastructure.extensions (extension framework uses modules)
  - k1.l3_execution.request_router (plugins can extend routing)
  - Community ecosystem (custom plugins)
```

---

## 📋 Milestone 14: Extensions Framework

### 🎯 Overview

The Extensions Framework provides 10 customizable extension points enabling organizations to extend K1 infrastructure with custom policies, algorithms, and observability providers. It integrates with the Module System (M13) to enable community plugins while maintaining isolation and compatibility.

**Core Functions:**

1. **Extension Registry** — Central registration and discovery of all extension points
2. **Lifecycle Management** — Init/activate/deactivate/unload extension plugins
3. **10 Extension Points** — Pluggable interfaces for configuration, metrics, placement, etc.
4. **Community Plugin Support** — Examples, templates, testing framework for custom extensions
5. **Validation & Compatibility** — Ensure plugins implement required interfaces and maintain API contracts

**Why It Matters:**

- **Customization:** Organizations add custom policies without forking K1
- **Vendor Integration:** Connect to proprietary observability/security/placement systems
- **Community Ecosystem:** Enable rich ecosystem of third-party plugins
- **Zero Overhead:** Disabled extensions add no performance penalty
- **Hot-Reload:** Update extensions without restart (via Module System)

**Key Metrics:**

- Extension load time: <50ms per extension
- Extension activation: <10ms
- Registry lookup: <1ms
- Community plugin adoption: Target 50+ plugins in Year 1

**10 Extension Points:**

```
K1 Extensions Framework
├─ ConfigProvider (configuration sources)
├─ MetricsExporter (Prometheus, CloudWatch, Datadog)
├─ TraceExporter (Jaeger, Tempo, Honeycomb)
├─ LogHandler (structured logging, custom sinks)
├─ ThermalPolicy (custom thermal thresholds, device support)
├─ PlacementStrategy (custom model placement algorithms)
├─ StorageTier (custom storage backends, tiering policies)
├─ CircuitBreakerStrategy (custom failure detection, recovery)
├─ SecurityPolicy (custom access control, encryption)
└─ PerformanceOptimizer (performance tuning, profiling hooks)
```

---

### 📌 Epic 14.1: Extension Framework Core

**File:** `k1/l5_infrastructure/extensions/extension_registry.py`

**Purpose:** Central registry for all extension points with lifecycle management and validation.

**Responsibilities:**

- Register extension points with required interfaces
- Discover registered extensions
- Manage extension lifecycle (load, activate, deactivate, unload)
- Validate plugin implementation against extension interface
- Track extension state and health
- Provide dependency resolution between extensions

**Key Concepts:**

1. **Extension Interface (Abstract Base):**

   ```python
   class Extension(ABC):
       """Base class for all extensions."""

       @property
       @abstractmethod
       def extension_point(self) -> str:
           """Return extension point name (e.g., 'config_provider')."""

       @property
       @abstractmethod
       def name(self) -> str:
           """Extension name (e.g., 'vault_config_provider')."""

       @property
       @abstractmethod
       def version(self) -> str:
           """Extension version (semantic versioning)."""

       @property
       @abstractmethod
       def api_version(self) -> str:
           """Required K1 API version."""

       @property
       @abstractmethod
       def dependencies(self) -> List[str]:
           """List of required extensions (names)."""

       @abstractmethod
       async def initialize(self, config: dict) -> None:
           """Initialize extension with configuration."""

       @abstractmethod
       async def activate(self) -> None:
           """Activate extension (start background tasks if needed)."""

       @abstractmethod
       async def deactivate(self) -> None:
           """Deactivate extension (stop background tasks)."""

       @abstractmethod
       async def validate(self) -> bool:
           """Validate extension state (connectivity, permissions)."""

       @abstractmethod
       async def shutdown(self) -> None:
           """Cleanup when extension unloads."""
   ```

2. **Extension Point Definition:**
   - **Name:** Unique identifier (e.g., "config_provider")
   - **Interface:** Abstract base class with required methods
   - **Required:** Bool indicating if extension must be available
   - **Default:** Built-in default implementation (fallback)
   - **Multiple:** Bool indicating if multiple instances allowed

3. **Registration Process:**
   - Extension implements Extension + point-specific interface
   - Call `registry.register(extension, extension_point)`
   - Registry validates interface compliance
   - Extension added to registry, status = REGISTERED

4. **Extension States:**
   - **REGISTERED:** Discovered, not loaded
   - **INITIALIZING:** Loading and configuring
   - **ACTIVE:** Ready to use
   - **INACTIVE:** Disabled by configuration
   - **FAILED:** Load/validation failed
   - **UNLOADING:** Cleanup in progress
   - **UNLOADED:** Removed from registry

**Key Methods:**

```python
class ExtensionRegistry:
    """Central extension point registry."""

    async def register_extension_point(
        self,
        name: str,
        interface: Type,
        required: bool = False,
        multiple: bool = False,
        default_impl: Optional[Extension] = None
    ) -> None:
        """
        Register a new extension point with required interface.

        Args:
            name: Extension point name (e.g., "config_provider")
            interface: Abstract base class defining extension interface
            required: If True, K1 won't start without an implementation
            multiple: If True, multiple implementations can coexist
            default_impl: Built-in default implementation (fallback)
        """

    async def register_extension(
        self,
        extension: Extension,
        extension_point: str
    ) -> None:
        """
        Register an extension instance for a point.

        Args:
            extension: Extension instance (must implement Extension + point interface)
            extension_point: Target extension point name

        Raises:
            ExtensionPointNotFoundError if point not registered
            InterfaceComplianceError if extension doesn't implement interface
            DuplicateExtensionError if multiple=False and already registered
        """

    async def get_extension(
        self,
        extension_point: str,
        name: Optional[str] = None
    ) -> Extension:
        """
        Get extension by point and name.

        Args:
            extension_point: Extension point name
            name: Extension name (if None, return first active)

        Returns:
            Extension instance

        Raises:
            ExtensionNotFoundError if not found/active
        """

    async def list_extensions(
        self,
        extension_point: Optional[str] = None
    ) -> List[Extension]:
        """
        List all extensions (optionally filtered by point).

        Args:
            extension_point: Filter by point (None = all)

        Returns:
            List of Extension instances
        """

    async def activate_extension(self, name: str) -> None:
        """
        Activate an extension (move to ACTIVE state).

        Args:
            name: Extension name

        Raises:
            ExtensionNotFoundError if not found
            ActivationError if initialization fails
        """

    async def deactivate_extension(self, name: str) -> None:
        """
        Deactivate an extension (move to INACTIVE state).

        Args:
            name: Extension name
        """

    async def validate_extension(self, name: str) -> bool:
        """
        Validate extension state (connectivity, permissions, etc.).

        Args:
            name: Extension name

        Returns:
            True if valid, False otherwise
        """

    async def resolve_dependencies(self, name: str) -> List[Extension]:
        """
        Resolve extension dependencies in load order.

        Args:
            name: Extension name

        Returns:
            List of extensions in dependency order

        Raises:
            UnresolvedDependencyError if dependency not found
            CircularDependencyError if circular dependency detected
        """

    async def get_registry_snapshot(self) -> dict:
        """
        Get current registry state (extension count, statuses, health).

        Returns:
            Snapshot with total_extensions, status_breakdown, health_status
        """
```

**Performance Budgets:**

- Extension registration: <5ms
- Extension activation: <10ms
- Registry lookup: <1ms
- Dependency resolution: <10ms
- Validation check: <20ms

**Related ADRs:** ADR-0034 (Extensions Framework Design)

---

### 📌 Epic 14.2: 10 Extension Points

Each extension point defines a pluggable interface for customizing K1 infrastructure:

#### **Extension Point 1: ConfigProvider**

**File:** `k1/l5_infrastructure/extensions/config_provider.py`

**Purpose:** Pluggable configuration sources (Vault, etcd, AWS Secrets Manager, etc.)

**Interface:**

```python
class ConfigProvider(Extension):
    @abstractmethod
    async def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""

    @abstractmethod
    async def set_config(self, key: str, value: Any) -> None:
        """Set configuration value."""

    @abstractmethod
    async def watch_config(self, key: str) -> AsyncIterator[tuple]:
        """Watch key for changes, yield (old_value, new_value)."""
```

**Built-in Implementations:**

- `FileConfigProvider` — YAML files (default)
- `VaultConfigProvider` — HashiCorp Vault
- `AWSSecretsManagerProvider` — AWS Secrets Manager

**Use Cases:**

- Multi-environment configuration (dev/staging/prod)
- Secrets management (API keys, certificates)
- Dynamic configuration updates (no restart)

---

#### **Extension Point 2: MetricsExporter**

**File:** `k1/l5_infrastructure/extensions/metrics_exporter.py`

**Purpose:** Custom metrics export (Prometheus, Datadog, CloudWatch, etc.)

**Interface:**

```python
class MetricsExporter(Extension):
    @abstractmethod
    async def export_counter(self, name: str, value: int, labels: dict) -> None:
        """Export counter metric."""

    @abstractmethod
    async def export_histogram(self, name: str, value: float, labels: dict) -> None:
        """Export histogram metric."""

    @abstractmethod
    async def export_gauge(self, name: str, value: float, labels: dict) -> None:
        """Export gauge metric."""
```

**Built-in Implementations:**

- `PrometheusExporter` — Prometheus (default)
- `DatadogExporter` — Datadog APM
- `CloudWatchExporter` — AWS CloudWatch
- `StdoutExporter` — Debug logging to stdout

**Use Cases:**

- SaaS observability platforms (Datadog, New Relic)
- Cloud provider metrics (CloudWatch, Stackdriver)
- Custom metrics pipelines

---

#### **Extension Point 3: TraceExporter**

**File:** `k1/l5_infrastructure/extensions/trace_exporter.py`

**Purpose:** Custom trace export (Jaeger, Tempo, Honeycomb, etc.)

**Interface:**

```python
class TraceExporter(Extension):
    @abstractmethod
    async def export_trace(self, trace: dict) -> None:
        """Export distributed trace."""

    @abstractmethod
    async def start_span(self, name: str, attributes: dict) -> str:
        """Start new span, return span_id."""

    @abstractmethod
    async def end_span(self, span_id: str, status: str) -> None:
        """End span with status (OK, ERROR)."""
```

**Built-in Implementations:**

- `TempoExporter` — Grafana Tempo (default)
- `JaegerExporter` — Jaeger
- `HoneycombExporter` — Honeycomb
- `XRayExporter` — AWS X-Ray

**Use Cases:**

- Application performance monitoring
- Root cause analysis
- Performance profiling

---

#### **Extension Point 4: LogHandler**

**File:** `k1/l5_infrastructure/extensions/log_handler.py`

**Purpose:** Custom structured logging (Loki, Splunk, ELK, etc.)

**Interface:**

```python
class LogHandler(Extension):
    @abstractmethod
    async def handle_log(self, record: LogRecord) -> None:
        """Handle log record (JSON structure)."""

    @abstractmethod
    async def flush(self) -> None:
        """Flush buffered logs to destination."""
```

**Built-in Implementations:**

- `StdoutLogHandler` — Console output (default)
- `LokiLogHandler` — Grafana Loki
- `SplunkLogHandler` — Splunk
- `ElasticsearchLogHandler` — ELK Stack

**Use Cases:**

- Centralized log aggregation
- Full-text log search
- Log-based alerting

---

#### **Extension Point 5: ThermalPolicy**

**File:** `k1/l5_infrastructure/extensions/thermal_policy.py`

**Purpose:** Custom thermal management policies and device support

**Interface:**

```python
class ThermalPolicy(Extension):
    @abstractmethod
    async def get_thermal_reading(self) -> float:
        """Get current temperature (Celsius)."""

    @abstractmethod
    async def get_recommended_tier(self, temp: float) -> str:
        """Recommend placement tier (NPU, GPU, CPU, Remote)."""

    @abstractmethod
    async def should_throttle(self, temp: float) -> bool:
        """Should K1 throttle inference?"""
```

**Built-in Implementations:**

- `LinuxThermalPolicy` — Linux thermal zones
- `WindowsThermalPolicy` — Windows WMI
- `MacOSThermalPolicy` — macOS IOKit
- `NVIDIAThermalPolicy` — NVIDIA GPUs
- `CustomThermalPolicy` — User-defined thresholds

**Use Cases:**

- Support for new devices (TPUs, custom accelerators)
- Custom thermal budgets per environment
- Device-specific optimization

---

#### **Extension Point 6: PlacementStrategy**

**File:** `k1/l5_infrastructure/extensions/placement_strategy.py`

**Purpose:** Custom model placement algorithms (cost, latency, power constraints)

**Interface:**

```python
class PlacementStrategy(Extension):
    @abstractmethod
    async def choose_device(
        self,
        model: str,
        context: dict
    ) -> str:
        """Choose device for model (NPU, GPU, CPU, Remote)."""

    @abstractmethod
    async def get_cost_estimate(self, model: str, device: str) -> float:
        """Estimate cost for running model on device."""
```

**Built-in Implementations:**

- `CostOptimizedPlacement` — Minimize cost (default)
- `LatencyOptimizedPlacement` — Minimize latency
- `PowerOptimizedPlacement` — Minimize power consumption
- `CustomPlacement` — User-defined algorithm

**Use Cases:**

- Mobile optimization (power constraints)
- Edge deployment (bandwidth constraints)
- Cost-aware inference

---

#### **Extension Point 7: StorageTier**

**File:** `k1/l5_infrastructure/extensions/storage_tier.py`

**Purpose:** Custom storage backend implementations (S3, Azure Blob, MinIO, etc.)

**Interface:**

```python
class StorageTier(Extension):
    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Retrieve data by key."""

    @abstractmethod
    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        """Store data with TTL."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete data by key."""

    @abstractmethod
    async def list_keys(self, prefix: str) -> AsyncIterator[str]:
        """List keys matching prefix."""
```

**Built-in Implementations:**

- `LocalStorageTier` — Filesystem
- `S3StorageTier` — AWS S3
- `AzureBlobTier` — Azure Blob Storage
- `MinIOTier` — MinIO (self-hosted S3)
- `GoogleCloudStorageTier` — Google Cloud Storage

**Use Cases:**

- Multi-cloud deployment
- Self-hosted storage
- Compliance (on-prem data residency)

---

#### **Extension Point 8: CircuitBreakerStrategy**

**File:** `k1/l5_infrastructure/extensions/circuit_breaker_strategy.py`

**Purpose:** Custom failure detection and recovery strategies

**Interface:**

```python
class CircuitBreakerStrategy(Extension):
    @abstractmethod
    async def should_fail_open(self, failure_count: int) -> bool:
        """Determine if circuit should open (custom threshold)."""

    @abstractmethod
    async def get_recovery_timeout(self) -> int:
        """Get timeout before HALF_OPEN (adaptive backoff)."""

    @abstractmethod
    async def is_slow_call(self, latency_ms: float) -> bool:
        """Detect slow calls (custom thresholds)."""
```

**Built-in Implementations:**

- `FixedThresholdStrategy` — Fixed failure count threshold (default)
- `AdaptiveThresholdStrategy` — Adaptive threshold based on success rate
- `LatencyBasedStrategy` — Open based on latency percentiles
- `CustomStrategy` — User-defined logic

**Use Cases:**

- Service-specific failure detection
- Adaptive recovery timeouts
- Latency-based degradation

---

#### **Extension Point 9: SecurityPolicy**

**File:** `k1/l5_infrastructure/extensions/security_policy.py`

**Purpose:** Custom access control, encryption, and audit policies

**Interface:**

```python
class SecurityPolicy(Extension):
    @abstractmethod
    async def can_access(self, resource: str, action: str, context: dict) -> bool:
        """Check if access is allowed (authz)."""

    @abstractmethod
    async def encrypt(self, data: bytes, context: dict) -> bytes:
        """Encrypt sensitive data."""

    @abstractmethod
    async def decrypt(self, encrypted: bytes, context: dict) -> bytes:
        """Decrypt sensitive data."""

    @abstractmethod
    async def audit_log(self, event: dict) -> None:
        """Log security-relevant event."""
```

**Built-in Implementations:**

- `NoOpSecurityPolicy` — No restrictions (development)
- `RBACSecurityPolicy` — Role-based access control
- `ABACSecurityPolicy` — Attribute-based access control
- `OPAPolicyEngine` — Open Policy Agent

**Use Cases:**

- Enterprise access control (RBAC/ABAC)
- Regulatory compliance (HIPAA, GDPR)
- Encryption at rest/in transit

---

#### **Extension Point 10: PerformanceOptimizer**

**File:** `k1/l5_infrastructure/extensions/performance_optimizer.py`

**Purpose:** Performance tuning hooks and profiling

**Interface:**

```python
class PerformanceOptimizer(Extension):
    @abstractmethod
    async def optimize_for_latency(self, component: str) -> dict:
        """Get latency optimization hints (e.g., batch_size)."""

    @abstractmethod
    async def optimize_for_throughput(self, component: str) -> dict:
        """Get throughput optimization hints."""

    @abstractmethod
    async def get_profiling_sample(self) -> dict:
        """Return profiling data (CPU, memory, I/O)."""
```

**Built-in Implementations:**

- `DefaultOptimizer` — No optimization
- `LatencyOptimizer` — Optimize for latency
- `ThroughputOptimizer` — Optimize for throughput
- `AdaptiveOptimizer` — Auto-tune based on workload

**Use Cases:**

- Performance profiling and tuning
- Workload-specific optimization
- SLA enforcement

---

### 📌 Epic 14.3: Community Plugin Support

**Files:**

- `extension_templates/` — Boilerplate for each extension point
- `extension_examples/` — Full examples (Vault, Datadog, S3)
- `extension_testing/` — Testing framework for plugins

**Template Structure:**

```
extensions/
├─ extension_templates/
│  ├─ config_provider_template.py
│  ├─ metrics_exporter_template.py
│  ├─ trace_exporter_template.py
│  ├─ log_handler_template.py
│  ├─ thermal_policy_template.py
│  ├─ placement_strategy_template.py
│  ├─ storage_tier_template.py
│  ├─ circuit_breaker_strategy_template.py
│  ├─ security_policy_template.py
│  └─ performance_optimizer_template.py
├─ extension_examples/
│  ├─ vault_config_provider.py
│  ├─ datadog_metrics_exporter.py
│  ├─ honeycomb_trace_exporter.py
│  ├─ s3_storage_tier.py
│  └─ opa_security_policy.py
└─ extension_testing/
   ├─ test_config_provider.py
   ├─ test_metrics_exporter.py
   └─ extension_test_fixtures.py
```

**Testing Framework:**

- Base test class for each extension point
- Mocks and fixtures for dependencies
- Performance benchmarking utilities
- Compatibility checklist

**Community Plugin Manifest:**

```yaml
name: "vault-config-provider"
version: "1.0.0"
api_version: "1.0"
author: "community-contributor"
description: "HashiCorp Vault integration for configuration"

extension_points:
  - config_provider

dependencies:
  - name: hvac
    version: ">=1.0.0"

example_config:
  vault_addr: "https://vault.example.com"
  role_id: "your-role-id"
```

---

### 📊 Milestone 14 Summary

| Component | Files | Epics | Lines | Status |
|-----------|-------|-------|-------|--------|
| **Extensions Framework** | 11 | 3 | ~2,800 | 📋 Planned |
| Epic 14.1: Registry Core | 1 | - | ~600 | Registry, lifecycle, validation |
| Epic 14.2: 10 Extension Points | 10 | - | ~1,600 | 10 pluggable interfaces |
| Epic 14.3: Community Support | Templates/Examples/Testing | - | ~600 | Templates, examples, testing |

**Performance Targets:**

- Extension registration: <5ms
- Extension activation: <10ms
- Registry lookup: <1ms
- Extension load (cold): <50ms
- Extension load (hot): <10ms

**Quality Gates:**

- ✅ Interface compliance: 100% (validated at registration)
- ✅ Dependency resolution: <10ms P95
- ✅ Extension isolation: 100% (failures contained)
- ✅ Hot-reload support: 100% (via Module System)

**Failure Modes & Mitigations:**

| Failure Mode | Mitigation |
|------|-----------|
| Extension crashes | Isolate in separate namespace, emit alert |
| Circular dependencies | Topological sort + cycle detection |
| Missing required extension | Start with default implementation, warn user |
| Performance degradation | Disable slow extensions, profile in background |
| Incompatible versions | API version checking, automatic downgrade |

**Configuration Schema:**

```yaml
extensions:
  enabled: true

  extension_points:
    config_provider:
      enabled: true
      implementation: file
      config:
        path: /etc/k1/config.yaml

    metrics_exporter:
      enabled: true
      implementation: prometheus
      config:
        port: 9090

    trace_exporter:
      enabled: true
      implementation: tempo
      config:
        endpoint: http://localhost:3200

    security_policy:
      enabled: true
      implementation: rbac
      config:
        policy_file: /etc/k1/rbac.yaml
```

**Milestone 14 Dependencies:**

```
Upstream (Requires):
  - k1.l5_infrastructure.modules (dynamic loading, hot-reload)
  - All M1-M13 modules (config providers, exporters, policies for each)
  - Community plugin ecosystem (examples, contributions)

Downstream (Provides):
  - k1.l3_execution.request_router (extensible routing)
  - k1.l3_execution.model_hub (custom placement strategies)
  - Enterprise integrations (Vault, Datadog, Splunk, OPA)
  - Community ecosystem (50+ plugins target Year 1)
```

---



**Responsibility:** Multi-tier storage, lifecycle management

**Milestones:**

- Milestone 5: Multi-Tier Storage

**Deliverables:**

- Hot/Warm/Cold tiering
- Automatic lifecycle transitions
- LRU eviction policies
- Cost optimization

**Timeline:** 2 weeks for stubs, 6 weeks for implementation
