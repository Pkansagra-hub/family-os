"""Prometheus metrics for the bridge runtime + first-contract dispatcher.

Per the MS-2.5 observability rule (≥1 health gauge, ≥1 error counter,
≥1 latency histogram, structured boundary log per epic), this module
defines the surface for Epic 2.5.5 (``memory.write.v1``).

Importing this module is idempotent: prometheus_client registers each
metric on a global registry, so re-import inside tests reuses the
existing collectors. We do *not* tear down or unregister metrics — that
would break per-process accounting and tooling expects them as
permanent labels of the process.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

bridge_runtime_up = Gauge(
    "bridge_runtime_up",
    "1 when the bridge runtime has booted and registered all expected "
    "handlers; 0 during shutdown or pre-boot.",
    labelnames=("role",),
)


# ---------------------------------------------------------------------------
# memory.write.v1 (Epic 2.5.5 first contract)
# ---------------------------------------------------------------------------

memory_write_v1_accepted_total = Counter(
    "bridge_memory_write_v1_accepted_total",
    "Number of memory.write.v1 envelopes successfully dispatched to the " "consumer-side handler.",
    labelnames=("tenant_id",),
)

memory_write_v1_rejected_total = Counter(
    "bridge_memory_write_v1_rejected_total",
    "Number of memory.write.v1 envelopes rejected before reaching the "
    "consumer-side handler. ``reason`` distinguishes schema validation "
    "failures from unknown-topic errors.",
    labelnames=("tenant_id", "reason"),
)

memory_write_v1_latency_ms = Histogram(
    "bridge_memory_write_v1_latency_ms",
    "End-to-end dispatch latency for memory.write.v1 (millis), measured "
    "from inbound dispatcher receipt to handler return.",
    labelnames=("tenant_id",),
    buckets=(0.5, 1, 2.5, 5, 10, 25, 50, 100, 250, 500, 1000, 2500),
)
