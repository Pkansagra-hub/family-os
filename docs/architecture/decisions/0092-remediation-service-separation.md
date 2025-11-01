# ADR-0121: Remediation Service Separation & Microkernel Purity

**Status**: ACCEPTED
**Date**: 2025-11-01
**Deciders**: Architecture Team
**Relates to**: K0 Microkernel Architecture, SSE Event Model, Port Abstraction
**References**: ADR-0001 (K0 Microkernel Ports), ADR-0086 (SSE Event Model)

---

## Context

K0 was designed as a microkernel providing exactly four ABIs:

1. **Command Port** (async command submission + transactional execution)
2. **Query Port** (point-in-time reads with consistency guarantees)
3. **SSE Port** (event streaming for async notifications)
4. **Observability Port** (metrics, traces, logs)

Historically, remediation logic (infrastructure state correction in response to failures) was implemented directly in the kernel:

- `k0/automation/remediation_actions.py` (~2,091 lines): Direct execution of `sudo iptables`, `docker-compose restart`, `kill -9` operations
- `k0/automation/remediation_service.py` (~1,847 lines): Flask webhook handler consuming Alertmanager webhooks

This approach violated two critical architectural principles:

1. **Microkernel Purity**: K0 should not execute privileged operations; these belong in user-space orchestration
2. **Separation of Concerns**: Remediation logic is operational policy, not kernel functionality

---

## Problem Statement

**Architectural Violation**: Kernel directly executes infrastructure operations.

**Security Concerns**:
- `sudo iptables` calls violate least-privilege principle
- Hard-coded Docker paths break portability
- `kill -9` operations are forceful vs graceful, violating POSIX-recommended signal hierarchy

**Operational Issues**:
- Remediation becomes tightly coupled to K0 release cycle
- Policy changes require kernel restarts (high impact)
- Testing remediation requires kernel infrastructure (slows development)
- No clear separation between kernel concerns (ACID transactions) and ops concerns (infrastructure management)

**Testing & Developer Experience**:
- Remediation cannot be tested independently of kernel
- Chaos/fault injection requires kernel modifications
- Hot-reload breaks because remediation state becomes kernel-managed

---

## Decision

**Remove remediation logic from K0 kernel. Implement SSE-based event publishing for operational concerns.**

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ K0 Microkernel (Pure)                                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  • Command Port (transactional execution)                   │
│  • Query Port (ACID reads)                                 │
│  • Observability Port (metrics, traces, logs)              │
│                                                             │
│  ✅ NEW: SSE Port emits high-level events                  │
│    - infra.remediation.required                            │
│    - infra.alert.fired                                     │
│    - infra.drift.detected                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                          ↓ SSE Events
┌─────────────────────────────────────────────────────────────┐
│ User-Space Orchestration Layer (P04 Tier)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Remediation Service (independent, scalable)               │
│    • Subscribes to SSE infra.* events                      │
│    • Executes remediation policy (pluggable)               │
│    • Lifecycle management (graceful shutdown, SIGTERM)     │
│    • Reports outcome back via SSE (audit trail)            │
│                                                             │
│  Alert Service (independent, pluggable)                    │
│    • Subscribes to SSE infra.alert.* events               │
│    • Routes to external systems (Alertmanager, Slack, etc) │
│    • Handles retries and backpressure                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### SSE Event Contracts

**Remediation Required Event**:

```json
{
  "event_type": "infra.remediation.required",
  "severity": "critical",  // critical | high | medium | low
  "component": "k0.kernel",
  "failure_mode": "fsync_failure",
  "description": "WAL fsync failed 5 times consecutively",
  "suggested_actions": [
    {
      "action": "restart_kernel",
      "grace_period_seconds": 30
    },
    {
      "action": "fail_over_to_replica",
      "replica_id": "k0-replica-2"
    }
  ],
  "timestamp": "2025-11-01T12:34:56.789Z",
  "trace_id": "c4a1d3f5-2e8b-4a9c-b1d5-7f9e3c6a2b1d"
}
```

**Alert Event**:

```json
{
  "event_type": "infra.alert.fired",
  "alert_rule": "k0_command_latency_p95_exceeded",
  "severity": "warning",
  "value": 205,  // P95 latency in ms
  "threshold": 150,
  "timestamp": "2025-11-01T12:34:56.789Z",
  "trace_id": "..."
}
```

---

## Consequences

### Benefits ✅

1. **Microkernel Purity**: K0 focuses solely on transaction coordination and consensus
2. **Operational Flexibility**: Remediation policy becomes pluggable; change without kernel restart
3. **Security**: No privileged operations in kernel; least-privilege enforcement at deployment
4. **Testing**: Remediation and chaos injection can be tested independently
5. **Developer Experience**: Hot-reload works correctly; no kernel state coupling
6. **Scalability**: Remediation service can scale independently (multi-instance for HA)

### Changes Required

1. **Removal**: Delete 4,571 lines of deprecated automation code:
   - `k0/automation/remediation_actions.py`
   - `k0/automation/remediation_service.py`
   - `k0/automation/generate_chaos_report.py`
   - `k0/automation/test_service.ps1`
   - `k0/automation/test_webhook_payload.json`

2. **Addition**: Implement SSE event emission in kernel:
   - New SSE event types: `infra.remediation.required`, `infra.alert.fired`
   - Events published from error handlers in K0 runtime
   - Structured event schema validation

3. **Migration**: Document pattern for consuming remediation events:
   - Example implementation: `examples/remediation-service/` (reference architecture)
   - Runbook: `docs/development/runbooks/remediation-service.md`

4. **Testing**: Move chaos injection to user-space:
   - Chaos service consumes K0 SSE events
   - Fault injection via environment variables (no kernel modifications)
   - Ward tests for chaos recovery scenarios

---

## Rationale

**Why SSE-based events?**

- K0 already has SSE infrastructure (proven, tested)
- Decouples kernel from consumer lifecycle
- Multiple services can consume same events (remediation + audit + analytics)
- Backpressure handled by SSE cursor position (no loss of events)

**Why now?**

- Hot-reload infrastructure requires operational code separation
- Performance regression detection benefits from independent remediation testing
- Security audit identified privilege escalation risks in direct remediation

**Why not alternatives?**

- ❌ Remain in kernel: Violates microkernel purity, blocks hot-reload, security risk
- ❌ RPC-based remediation: Still couples kernel to policy; harder to test
- ❌ File-based (Unix domain socket): Limited to local node; complicates distributed scenarios

---

## Implementation Plan

### Phase 1: Deprecation (Week 0)
- [ ] Archive deprecated files to `_archived/deprecated-2025-11-01/`
- [ ] Update `k0/README.md` to document SSE-based remediation pattern
- [ ] Add CHANGELOG entry with deprecation notice
- [ ] Create this ADR

### Phase 2: SSE Events (Weeks 1-2)
- [ ] Define SSE event schemas in `k0/contracts/asyncapi/events.yaml`
- [ ] Implement event emission in K0 error handlers
- [ ] Add telemetry for event publication (prometheus counters)
- [ ] Integration tests for event emission

### Phase 3: Reference Implementation (Weeks 3-4)
- [ ] Create example remediation service in `examples/remediation-service/`
- [ ] Document consumption pattern in `docs/development/runbooks/remediation-service.md`
- [ ] Reference architecture diagram: `docs/architecture/diagrams/k0-remediation-pattern.mmd`

### Phase 4: Cutover (Week 5)
- [ ] Remove archived files from git history (if needed)
- [ ] Update any external references to deprecated automation
- [ ] Mark ADR as IMPLEMENTED

---

## Open Questions

1. **How should remediation events be routed?**
   - Option A: All events to single remediation service (simple, centralized)
   - Option B: Event-type specific handlers (flexible, distributed)
   - **Decision**: Deferred to remediation service implementation ADR

2. **Should K0 wait for remediation response?**
   - Option A: Fire-and-forget (eventual consistency)
   - Option B: Remediation must succeed before resuming (strong consistency)
   - **Decision**: Fire-and-forget (SSE is inherently async); caller can react to subsequent events

3. **How is chaos injection triggered in user-space?**
   - Option A: Environment variables (`K0_CHAOS_PROFILE=moderate`)
   - Option B: Separate chaos controller service
   - Option C: File-based toggle (watch for changes)
   - **Decision**: Deferred to chaos automation ADR

---

## Related ADRs

- **ADR-0001**: K0 Microkernel Ports (foundational architecture)
- **ADR-0086**: SSE Event Model (async event publishing)
- **ADR-0XX** (pending): Chaos Automation via User-Space Injection
- **ADR-0XX** (pending): Remediation Service Design

---

## Sign-Off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Architecture | TBD | 2025-11-01 | Pending review |
| Security | TBD | 2025-11-01 | Pending review |
| Ops | TBD | 2025-11-01 | Pending review |

---

## Appendix: Deprecated Code Locations

Files archived to `k0/automation/_archived/deprecated-2025-11-01/`:

1. **remediation_actions.py** (2,091 lines): Direct execution of infrastructure operations
   - Contains: `sudo iptables`, `docker-compose restart`, `kill -9` logic
   - Reason for removal: Violates microkernel purity and least-privilege

2. **remediation_service.py** (1,847 lines): Flask webhook handler
   - Contains: Alertmanager webhook consumer
   - Reason for removal: Should be external service consuming SSE events

3. **generate_chaos_report.py** (412 lines): Ward output parser
   - Contains: Basic chaos test result aggregation
   - Reason for removal: Superseded by `chaos_scheduler.py` with integrated chaos framework

4. **test_service.ps1** (187 lines): PowerShell service management script
   - Contains: Docker/service control logic
   - Reason for removal: Covered by Ward integration tests; platform-specific

5. **test_webhook_payload.json** (34 lines): Test fixture
   - Contains: Sample Alertmanager webhook JSON
   - Reason for removal: Should live in `tests/fixtures/`; orphaned test data

---

**Next Action**: Implement Phase 1 (deprecation) and proceed to Phase 2 (SSE event emission).
