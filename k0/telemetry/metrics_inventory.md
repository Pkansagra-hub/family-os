# K0 Kernel Prometheus Metrics Inventory

> **Generated:** 2025-10-01
> **Owner:** Observability Team
> **Purpose:** Canonical list of metrics exposed by k0_kernel for SLO dashboard design

---

## Metric Classification

### Latency (Histograms)
- `k0_kernel_http_request_latency_seconds` - HTTP request latency (FastAPI middleware)
  - Labels: `method`, `route`, `status`
  - Buckets: 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10
  - SLI: Command/Query API p50/p95/p99

- `k0_uow_commit_seconds` - Unit of Work commit latency
  - Labels: `outcome` (success/failure)
  - SLI: Storage durability latency

- `k0_uow_wal_fsync_seconds` - WAL fsync latency
  - Labels: none
  - SLI: Write durability guarantee

- `k0_bus_dispatch_latency` - Bus dispatch latency (event processing)
  - Labels: `driver`, `outcome`
  - SLI: Event delivery latency

- Query/SSE observe metrics (from ports):
  - Labels vary by port
  - SLI: Read path performance

### Availability (Counters)
- `k0_kernel_http_requests_total` - Total HTTP requests
  - Labels: `method`, `route`, `status`
  - SLI: Availability = (non-5xx / total)

- `k0_uow_commit_total` - Total UoW commits
  - Labels: `outcome` (success/failure)
  - SLI: Transaction success rate

- `k0_uow_rollback_total` - Total UoW rollbacks
  - Labels: none
  - SLI: Transaction failure rate

- `k0_uow_wal_fsync_total` - Total WAL fsyncs
  - Labels: none
  - SLI: Durability operations

- `k0_outbox_apply_total` - Outbox delivery attempts
  - Labels: `outcome` (success/retry/quarantine), `driver`
  - SLI: Event delivery success rate

- `k0_driver_handshakes_total` - Driver handshake attempts
  - Labels: `driver`, `outcome`
  - SLI: Driver connectivity

### Saturation (Gauges)
- `k0_kernel_active_connections` - Active HTTP connections
  - Labels: none
  - SLI: Connection pool saturation

- `k0_kernel_snapshot_watermark` - Latest snapshot watermark
  - Labels: none
  - SLI: Snapshot freshness

- `k0_kernel_replay_watermark` - Replay progress watermark
  - Labels: none
  - SLI: Replay lag

- `k0_outbox_pending_total` - Pending outbox entries
  - Labels: `state` (pending/requeued/quarantined)
  - SLI: Outbox backlog

- `k0_sse_active_subscriptions` - Active SSE subscriptions
  - Labels: none
  - SLI: SSE load

### Error Rates (Counters)
- Derived from `k0_kernel_http_requests_total` with `status=~"5.."` filter
- Derived from `k0_uow_commit_total` with `outcome="failure"` filter
- Derived from `k0_outbox_apply_total` with `outcome="quarantine"` filter

---

## SLO Mapping

| SLO | Metric(s) | Target |
|-----|-----------|--------|
| Command latency p95 | `k0_kernel_http_request_latency_seconds{route="/k0/command.submit"}` | < 100ms |
| Query latency p95 | `k0_kernel_http_request_latency_seconds{route="/k0/query.execute"}` | < 50ms |
| API availability | `rate(k0_kernel_http_requests_total{status!~"5.."}[5m]) / rate(k0_kernel_http_requests_total[5m])` | > 99.9% |
| Replay throughput | `rate(k0_kernel_replay_watermark[1m])` | > 1000 events/sec |
| WAL lag | `time() - k0_kernel_snapshot_watermark` | < 60s |
| Outbox backlog | `k0_outbox_pending_total{state="pending"}` | < 10000 |
| SSE disconnect rate | `rate(k0_sse_active_subscriptions[5m])` | < 5% of active |

---

## Notes
- All metrics use namespace prefix `k0_kernel`
- Default histogram buckets cover 5ms → 10s range
- Labels are consistent across related metrics for JOIN queries
- Metrics align with `.github/copilot-instructions.md` zero-simulation policy
