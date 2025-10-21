# ADR-0017f: Meta Section - Telemetry & Performance Metrics

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0017 (SessionState 6-Section Design)](0017-sessionstate-6-section-design.md)
**Category:** State Management (Layer 2) - Observability
**Related ADRs:**
- [ADR-0011 (FlatBuffers Serialization)](0011-flatbuffers-serialization.md)
- [ADR-0017a (Beliefs Section)](0017a-beliefs-section-user-facts-preferences.md)

---

## Context

### Problem Statement

The **Meta Section** stores session telemetry, timestamps, and performance metrics for observability:

- **Turn Counters:** Total turns, successful turns, failed turns
- **Performance Metrics:** Average TTFT, E2E latency, token count
- **Session Metadata:** Created at, last active, session duration
- **Eviction Policy:** Evict FIRST under pressure (low priority, observability only)
- **Size Budget:** 2-4KB (100-200 metrics)

**Key Challenges:**

1. **Metric Aggregation:** Average TTFT, P95 latency (incremental calculation)
2. **Low Priority:** First to evict under memory pressure (observability, not critical)
3. **Prometheus Integration:** Export metrics to Prometheus for monitoring
4. **Size Budget:** 2-4KB (100-200 counters/gauges)
5. **Minimal Overhead:** Fast updates (<100μs per metric)

### Current Landscape

**Industry Telemetry Patterns:**

1. **Prometheus Metrics (Counters, Gauges, Histograms)**:
   - **Pattern:** In-memory metrics with /metrics endpoint
   - **Advantage:** Industry standard, rich ecosystem
   - **Disadvantage:** No persistence (metrics reset on restart)

2. **OpenTelemetry Spans**:
   - **Pattern:** Distributed tracing with span attributes
   - **Advantage:** Rich context, trace propagation
   - **Disadvantage:** High overhead (10-50ms per span)

3. **StatsD Counters**:
   - **Pattern:** Fire-and-forget UDP metrics
   - **Advantage:** Low overhead (<1ms), simple
   - **Disadvantage:** No persistence, no aggregation

4. **Session Metadata (OpenAI Assistants API)**:
   - **Pattern:** Flat metadata dict (created_at, last_active_at)
   - **Advantage:** Simple, built-in
   - **Disadvantage:** No performance metrics, no aggregation

### K1 Requirements

**Meta Section Properties:**

1. **Turn Counters:** Increment on each turn (total, successful, failed)
2. **Performance Metrics:** Track averages (TTFT, E2E latency, tokens)
3. **Session Metadata:** Track timestamps (created_at, last_active, duration)
4. **Low Priority:** Evict first under memory pressure (non-critical)
5. **Prometheus Export:** Export metrics to Prometheus /metrics endpoint

**Performance Targets (P95):**

| Operation | Target | Rationale |
|-----------|--------|-----------|
| `increment_counter(name)` | <50μs | Fast counter increment |
| `record_latency(value)` | <100μs | Fast latency recording |
| `get_metrics()` | <1ms | Fast metrics retrieval |
| `serialize()` | <5ms | FlatBuffers serialization |

---

## Decision

We will implement **Meta Section** as:

1. **Counter Store:** HashMap with counter_name → int (turn_count, success_count, failure_count)
2. **Gauge Store:** HashMap with gauge_name → float (avg_ttft_ms, avg_e2e_latency_ms)
3. **Session Metadata:** Simple fields (session_id, created_at_ms, last_active_ms, session_duration_ms)
4. **Incremental Aggregation:** Running averages (no full history, just mean)
5. **Low Priority:** First section to evict under memory pressure

**Data Model:**

```
PerformanceMetrics:
  - avg_ttft_ms: float (average time to first token)
  - avg_e2e_latency_ms: float (average end-to-end latency)
  - total_tokens_generated: long (cumulative token count)
  - total_turns: int (total turn count)
  - successful_turns: int (successful turn count)
  - failed_turns: int (failed turn count)

MetaSection:
  - session_id: string (session identifier)
  - created_at_ms: long (session creation timestamp)
  - last_active_ms: long (last activity timestamp)
  - session_duration_ms: long (total session duration)
  - performance: PerformanceMetrics (performance metrics)
```

---

## Implementation

### FlatBuffers Schema

```flatbuffers
// k1/session_state/schemas/meta_section.fbs
namespace K1.SessionState;

/// Performance metrics (TTFT, latency, tokens, etc.)
table PerformanceMetrics {
  /// Average time to first token (milliseconds)
  avg_ttft_ms: float;

  /// Average end-to-end turn latency (milliseconds)
  avg_e2e_latency_ms: float;

  /// Total tokens generated (cumulative)
  total_tokens_generated: long;

  /// Total turns (all states)
  total_turns: int;

  /// Successful turns
  successful_turns: int;

  /// Failed turns
  failed_turns: int;
}

/// Meta section (session telemetry & performance)
table MetaSection {
  /// Session identifier
  session_id: string (required);

  /// Session creation timestamp (milliseconds)
  created_at_ms: long (required);

  /// Last activity timestamp (milliseconds)
  last_active_ms: long (required);

  /// Total session duration (milliseconds)
  session_duration_ms: long;

  /// Performance metrics
  performance: PerformanceMetrics;

  /// Total size in bytes
  total_size_bytes: int;
}

root_type MetaSection;
```

---

### Python Implementation

```python
# k1/session_state/meta_manager.py
"""Meta Section Manager - Telemetry & Performance Metrics

Research:
- Metrics Aggregation: "Prometheus Exposition Format" (Prometheus, 2024)
- Running Averages: "Incremental Calculation of Weighted Mean and Variance" (West, 1979)
"""

from typing import Dict, Optional
from dataclasses import dataclass
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetricsData:
    """In-memory performance metrics representation"""
    avg_ttft_ms: float = 0.0
    avg_e2e_latency_ms: float = 0.0
    total_tokens_generated: int = 0
    total_turns: int = 0
    successful_turns: int = 0
    failed_turns: int = 0


class MetaManager:
    """Manage meta section (session telemetry & performance)

    Responsibilities:
    - Track turn counters (total, successful, failed)
    - Calculate performance metrics (avg TTFT, avg E2E latency)
    - Track session metadata (created_at, last_active, duration)
    - Export metrics to Prometheus

    Performance:
    - increment_counter: O(1) update, <50μs P95
    - record_latency: O(1) update, <100μs P95
    - get_metrics: O(1) retrieval, <1ms P95

    EVICTION: This section is FIRST to evict (low priority, observability only)
    """

    def __init__(self, session_id: str):
        """Initialize meta manager

        Args:
            session_id: Session identifier
        """
        self.session_id = session_id
        self.created_at_ms = self._get_timestamp_ms()
        self.last_active_ms = self.created_at_ms
        self.performance = PerformanceMetricsData()

    def increment_turn_counter(self, success: bool):
        """Increment turn counter

        Args:
            success: True if turn succeeded, False if failed

        Performance: <50μs P95
        """
        self.performance.total_turns += 1
        if success:
            self.performance.successful_turns += 1
        else:
            self.performance.failed_turns += 1

        self._update_last_active()

    def record_ttft(self, ttft_ms: float):
        """Record time to first token (incremental average)

        Args:
            ttft_ms: Time to first token in milliseconds

        Performance: <100μs P95
        """
        # Incremental average: avg_new = (avg_old * n + value) / (n + 1)
        n = self.performance.successful_turns
        if n > 0:
            self.performance.avg_ttft_ms = (
                (self.performance.avg_ttft_ms * (n - 1) + ttft_ms) / n
            )
        else:
            self.performance.avg_ttft_ms = ttft_ms

        self._update_last_active()

    def record_e2e_latency(self, latency_ms: float):
        """Record end-to-end turn latency (incremental average)

        Args:
            latency_ms: Turn latency in milliseconds

        Performance: <100μs P95
        """
        # Incremental average
        n = self.performance.successful_turns
        if n > 0:
            self.performance.avg_e2e_latency_ms = (
                (self.performance.avg_e2e_latency_ms * (n - 1) + latency_ms) / n
            )
        else:
            self.performance.avg_e2e_latency_ms = latency_ms

        self._update_last_active()

    def record_tokens(self, token_count: int):
        """Record tokens generated

        Args:
            token_count: Number of tokens generated

        Performance: <50μs P95
        """
        self.performance.total_tokens_generated += token_count
        self._update_last_active()

    def get_session_duration_ms(self) -> int:
        """Get total session duration

        Returns:
            Session duration in milliseconds
        """
        return self._get_timestamp_ms() - self.created_at_ms

    def get_metrics(self) -> Dict[str, float]:
        """Get all metrics as dict (for Prometheus export)

        Returns:
            Dict of metric_name → value

        Performance: <1ms P95
        """
        return {
            # Turn counters
            "total_turns": self.performance.total_turns,
            "successful_turns": self.performance.successful_turns,
            "failed_turns": self.performance.failed_turns,

            # Performance metrics
            "avg_ttft_ms": self.performance.avg_ttft_ms,
            "avg_e2e_latency_ms": self.performance.avg_e2e_latency_ms,
            "total_tokens_generated": self.performance.total_tokens_generated,

            # Session metadata
            "session_duration_ms": self.get_session_duration_ms(),
            "created_at_ms": self.created_at_ms,
            "last_active_ms": self.last_active_ms,
        }

    def export_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus exposition format

        Returns:
            Prometheus-formatted metrics string

        Example Output:
            k1_session_total_turns{session_id="sess_123"} 42
            k1_session_avg_ttft_ms{session_id="sess_123"} 145.3
        """
        metrics = self.get_metrics()
        lines = []

        for metric_name, value in metrics.items():
            prometheus_name = f"k1_session_{metric_name}"
            lines.append(f'{prometheus_name}{{session_id="{self.session_id}"}} {value}')

        return "\n".join(lines)

    def _update_last_active(self):
        """Update last active timestamp"""
        self.last_active_ms = self._get_timestamp_ms()

    def _get_timestamp_ms(self) -> int:
        """Get current timestamp in milliseconds

        Returns:
            Milliseconds since epoch
        """
        return int(time.time() * 1000)

    def get_size_kb(self) -> int:
        """Estimate section size in KB

        Returns:
            Estimated size in KB
        """
        # Fixed size: 8 metrics * 8 bytes + metadata (100 bytes)
        total_bytes = 8 * 8 + 100
        return total_bytes // 1024  # ~1KB

    def serialize(self) -> bytes:
        """Serialize to FlatBuffers for K0 persistence

        Returns:
            FlatBuffers serialized bytes

        Performance: <5ms P95
        """
        import flatbuffers
        # FlatBuffers serialization code
        # ... (implementation details)
        pass

    @staticmethod
    def deserialize(data: bytes) -> "MetaManager":
        """Deserialize from FlatBuffers

        Args:
            data: FlatBuffers serialized bytes

        Returns:
            MetaManager instance
        """
        # FlatBuffers deserialization code
        # ... (implementation details)
        pass
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/session_state/test_meta_manager.py
from ward import test, fixture
from k1.session_state.meta_manager import MetaManager

@fixture
def meta():
    """Fixture for MetaManager"""
    return MetaManager(session_id="test_session")

@test("increment_turn_counter tracks turns")
def _(meta=meta):
    meta.increment_turn_counter(success=True)
    meta.increment_turn_counter(success=True)
    meta.increment_turn_counter(success=False)

    assert meta.performance.total_turns == 3
    assert meta.performance.successful_turns == 2
    assert meta.performance.failed_turns == 1

@test("record_ttft calculates incremental average")
def _(meta=meta):
    meta.increment_turn_counter(success=True)
    meta.record_ttft(100.0)

    meta.increment_turn_counter(success=True)
    meta.record_ttft(200.0)

    # Average: (100 + 200) / 2 = 150
    assert abs(meta.performance.avg_ttft_ms - 150.0) < 0.1

@test("export_prometheus_metrics formats correctly")
def _(meta=meta):
    meta.increment_turn_counter(success=True)
    meta.record_ttft(145.3)

    prometheus_output = meta.export_prometheus_metrics()
    assert 'k1_session_total_turns{session_id="test_session"} 1' in prometheus_output
    assert 'k1_session_avg_ttft_ms{session_id="test_session"} 145.3' in prometheus_output
```

---

## Prometheus Integration

### Metrics Export Endpoint

```python
# k1/api/metrics_endpoint.py
from flask import Flask, Response
from k1.session_state import SessionState

app = Flask(__name__)

@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint"""
    # Collect metrics from all active sessions
    all_metrics = []

    for session in get_active_sessions():
        session_metrics = session.meta.export_prometheus_metrics()
        all_metrics.append(session_metrics)

    # Combine all metrics
    combined = "\n\n".join(all_metrics)

    return Response(combined, mimetype='text/plain')
```

---

## Research Citations

1. **Prometheus Documentation (2024).** *"Exposition Format."* https://prometheus.io/docs/instrumenting/exposition_formats/ — Prometheus metrics format.

2. **West, D. H. D. (1979).** *"Updating Mean and Variance Estimates: An Improved Method."* Communications of the ACM. — Incremental average calculation.

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-12
**Target Completion:** 2025-11-09 (4 weeks)
**Blocked By:** 0017 (SessionState 6-Section Design)
**Blocks:** None

---

**END OF ADR-0017f**
