# Orchestrator Operational Runbook

Status: Active (Epic 9.3.3)
Owner: Orchestrator Team
Last Updated: 2026-02-13
Source Plan: `docs/plans/orchestrator-implementation-plan.md` (Epic 9.3.3)

This runbook provides step-by-step procedures for operating, debugging, and maintaining the K1 Orchestrator in production. Each procedure references the specific admin API endpoint (WB section 5.2), metric (8.2.1 catalog), log query (8.3.1 structured fields), and admin action required.

Alert rules defined in `k1/orchestrator/docs/alerts.md` (Epic 8.4.1) link directly to procedures in this document.

---

## Table of Contents

1. [Procedure 1: Drain Mailbox for Maintenance](#procedure-1-drain-mailbox-for-maintenance)
2. [Procedure 2: Debug Stuck DAG](#procedure-2-debug-stuck-dag)
3. [Procedure 3: Force-Cancel In-Flight DAG](#procedure-3-force-cancel-in-flight-dag)
4. [Procedure 4: Restart MCP Discovery](#procedure-4-restart-mcp-discovery)
5. [Procedure 5: Inspect Scheduler Trigger State](#procedure-5-inspect-scheduler-trigger-state)
6. [Procedure 6: Handle Saga Dead-Letter](#procedure-6-handle-saga-dead-letter)
7. [Procedure 7: CB_PLANNER Management](#procedure-7-cb_planner-management)
8. [Procedure 8: Trigger Manual Workflow Run](#procedure-8-trigger-manual-workflow-run)
9. [Procedure 9: Read Audit Trail](#procedure-9-read-audit-trail)
10. [Procedure 10: Handle Token Budget Exhaustion](#procedure-10-handle-token-budget-exhaustion)

Appendices:
- [Appendix A: Admin API Quick Reference](#appendix-a-admin-api-quick-reference)
- [Appendix B: Alert-to-Runbook Mapping](#appendix-b-alert-to-runbook-mapping)
- [Appendix C: Metrics Catalog Quick Reference](#appendix-c-metrics-catalog-quick-reference)
- [Appendix D: Error Classification Matrix](#appendix-d-error-classification-matrix)

---

## Procedure 1: Drain Mailbox for Maintenance

**Purpose**: Gracefully drain the mailbox before planned maintenance, deployment, or shutdown. Ensures all in-flight messages are processed or logged before the Orchestrator stops accepting work.

**Triggered by alert**: `MailboxBackpressure` (mailbox depth > 80% capacity for 1 minute).

### Pre-Checks

1. Verify current mailbox depth:

   ```
   GET http://localhost:8081/admin/mailbox/depth
   ```

   Response:
   ```json
   {"depth": 42, "capacity": 200}
   ```

2. Verify current health status:

   ```
   GET http://localhost:8081/health/status
   ```

   Response includes `mailbox_depth`, `active_dags`, and `circuit_breakers` state.

### Steps

1. **Check mailbox stats** to understand pending work:

   ```
   GET http://localhost:8081/admin/mailbox/stats
   ```

   Response:
   ```json
   {
     "depth": 42,
     "capacity": 200,
     "pending_plans": 1,
     "pending_hil": 0
   }
   ```

   - `pending_plans > 0` means a HIGH-tier plan request is awaiting Planner response.
   - `pending_hil > 0` means a HIL approval request is awaiting user response.

2. **Initiate drain** with a timeout:

   ```
   POST http://localhost:8081/admin/drain
   Content-Type: application/json

   {"timeout_ms": 30000}
   ```

   Response:
   ```json
   {
     "drained": true,
     "active_dags_remaining": 0,
     "timeout_reached": false,
     "duration_ms": 12345
   }
   ```

   The drain operation:
   - Sets `_running = False` immediately (stops accepting new messages).
   - Waits for the active DAG (if any) to complete, polling every 100ms.
   - Returns `drained: true` when the concurrency guard reports no active DAG.
   - Returns `timeout_reached: true` if the DAG did not finish within `timeout_ms`.

3. **If drain timed out** (`timeout_reached: true, active_dags_remaining: 1`):
   - The active DAG is still running. Decide whether to:
     - Wait longer (re-issue drain with a higher timeout).
     - Force-cancel the DAG (see [Procedure 3](#procedure-3-force-cancel-in-flight-dag)).

4. **Verify the drain succeeded**:

   ```
   GET http://localhost:8081/admin/mailbox/depth
   ```

   Expect `depth: 0`. If depth > 0 after drain, messages were enqueued between check and drain -- re-drain.

### Shutdown Sequence (Reference)

After drain completes, `OrchestratorService.shutdown()` executes a 9-step sequence:

| Step | Action | Notes |
|------|--------|-------|
| 1 | `_running = False` | Stop mailbox loop |
| 2 | Stop ConnectorLifecycleManager | Cancel lifecycle monitoring |
| 3 | Wait for active DAG (30s) | Cooperative wait on concurrency guard |
| 4 | Force-compensate active DAG | Deferred in V1 |
| 5 | Stop WorkflowScheduler | Cancel pending triggers |
| 6 | Stop gap detector, unsubscribe events | Release event subscriptions |
| 7 | Persist trigger state | Deferred in V1 |
| 8 | Submit audit record | Logs orphan plan/HIL counts |
| 9 | Stop admin HTTP, cancel async tasks | Clean shutdown |

### Metrics to Monitor

| Metric | Type | What to Check |
|--------|------|---------------|
| `orchestrator.mailbox.depth` | Gauge | Should drop to 0 after drain |
| `orchestrator.mailbox.processed_total` | Counter | Check processing rate before drain |
| `orchestrator.dag.active` | Gauge | Should be 0 when drain completes |

### Log Query

```
component=orchestrator AND (message="shutdown*" OR message="drain*")
```

Structured fields: `trace_id`, `component`, `event`, `orphan_plans`, `orphan_hil`.

---

## Procedure 2: Debug Stuck DAG

**Purpose**: Identify and diagnose a DAG that appears stuck (not progressing through waves). Determine whether the issue is in Fabric step execution, Planner response delays, or Orchestrator internal state.

**Triggered by alerts**: `OrchestratorHighOverhead`, `DAGWaveConstructionSlow`, `StepRetryRateHigh`, `PendingPlanLeak`, `TokenBudgetExhausted`.

### Pre-Checks

1. Confirm a DAG is active:

   ```
   GET http://localhost:8081/admin/dags
   ```

   Response (when a DAG is active):
   ```json
   [
     {
       "dag_id": "dag-abc123",
       "plan_id": "plan-xyz789",
       "current_wave": 2,
       "total_waves": 4,
       "steps_completed": 5,
       "steps_failed": 0,
       "started_at": "2026-02-13T10:30:00Z",
       "trace_id": "trace-aaa111"
     }
   ]
   ```

   V1 returns at most 1 DAG (single-DAG-at-a-time per ADR-1.1.5).

### Steps

1. **Get DAG detail** for the active DAG:

   ```
   GET http://localhost:8081/admin/dags/{dag_id}
   ```

   Inspect:
   - `current_wave` vs `total_waves` -- is wave progress stalled?
   - `steps_completed` vs `steps_failed` -- are steps failing?
   - `started_at` -- how long has this DAG been running?

2. **Check circuit breaker state** (a common cause of stuck DAGs):

   ```
   GET http://localhost:8081/admin/circuit-breakers
   ```

   Response:
   ```json
   {
     "CB_PLANNER": {
       "state": "CLOSED",
       "failure_count": 0,
       "last_failure_at": null,
       "last_success_at": 1739440200.0,
       "opened_at": null
     }
   }
   ```

   - `CB_PLANNER = OPEN` -> Planner calls are blocked. See [Procedure 7](#procedure-7-cb_planner-management).
   - Fabric-owned circuit breakers (`CB_FABRIC`, `CB_MCP`) are managed by Fabric; check Fabric admin API.

3. **Check overall health**:

   ```
   GET http://localhost:8081/health/status
   ```

   `HealthStatus` logic:
   - `HEALTHY`: CB_PLANNER is CLOSED and mailbox depth < 80% capacity.
   - `DEGRADED`: CB_PLANNER is HALF_OPEN, or mailbox depth between 80-100%.
   - `UNHEALTHY`: CB_PLANNER is OPEN and mailbox is at capacity.

4. **Check mailbox depth** for backpressure:

   ```
   GET http://localhost:8081/admin/mailbox/stats
   ```

   If `pending_plans > 0`, the Orchestrator is waiting for a Planner response (event-driven dispatch_high flow). The DAG has not started because the plan has not been received yet.

5. **Inspect metrics** for anomalies:

   ```
   GET http://localhost:8081/admin/metrics
   ```

   Check:
   - `executed_plans_count` -- how many plans have been processed?
   - `pending_plans` -- are plan contexts accumulating? (indicates orphan plan leak)
   - `mailbox_depth` -- is backpressure building?

6. **Check DAG limits**: DAGExecutor enforces hard limits:
   - `MAX_WAVES = 20` (including micro-replans).
   - `MAX_STEPS = 50` per DAG.
   - `_MAX_CONCURRENT_PER_WAVE = 10` concurrent steps per wave.

   If the DAG is near these limits, it may be performing excessive micro-replans.

### Log Queries

```
# All events for a specific DAG
trace_id={trace_id} AND component=orchestrator

# Wave progress
component=orchestrator AND event=ORCH_DAG_STARTED AND dag_id={dag_id}

# Step failures
component=orchestrator AND event=ORCH_STEP_FAILED AND dag_id={dag_id}

# Error routing decisions
component=orchestrator AND event=ORCH_ERROR_ROUTED AND trace_id={trace_id}
```

### Metrics to Monitor

| Metric | Type | What to Check |
|--------|------|---------------|
| `orchestrator.dag.active` | Gauge | 1 if DAG running, 0 if idle |
| `orchestrator.dag.duration_ms` | Histogram | P99 should be < expected for tier |
| `orchestrator.dag.overhead_ms` | Histogram | P99 < 18ms (SLI #13) |
| `orchestrator.wave.construction_ms` | Histogram | P99 < 10ms |
| `orchestrator.step.duration_ms` | Histogram | Per-step latency |
| `orchestrator.step.retry_total` | Counter | Increasing = steps are failing and retrying |
| `orchestrator.pending_plans` | Gauge | > 0 for extended period = orphan plan context |

### Decision Tree

```
DAG appears stuck
|
+-- Check GET /admin/dags -> no DAGs listed?
|   |
|   +-- Check pending_plans gauge -> > 0?
|       +-- YES: Orchestrator waiting for Planner event. Check Planner health.
|       +-- NO: No active work. Check mailbox depth for queued messages.
|
+-- DAG listed but current_wave not advancing?
    |
    +-- Check CB state -> CB_PLANNER OPEN?
    |   +-- YES: Planner is unreachable. See Procedure 7.
    |
    +-- Check step retry counter -> increasing?
    |   +-- YES: Steps are failing. Check Fabric provider health.
    |
    +-- Check step duration -> abnormally high?
        +-- YES: Fabric adapter is slow. Check Fabric CB and provider health.
```

---

## Procedure 3: Force-Cancel In-Flight DAG

**Purpose**: Immediately cancel an active DAG via cooperative interrupt. The DAGExecutor checks the interrupt flag between steps and between waves; upon seeing it, it halts execution and triggers saga compensation for completed steps.

**Triggered by alerts**: `DAGFailureRateHigh`, `SagaCompensationSpike`.

### Pre-Checks

1. Identify the DAG to cancel:

   ```
   GET http://localhost:8081/admin/dags
   ```

   Note the `dag_id` from the response.

### Steps

1. **Send cancel request**:

   ```
   POST http://localhost:8081/admin/dags/{dag_id}/cancel
   ```

   Response on success:
   ```json
   {"cancelled": true, "dag_id": "dag-abc123"}
   ```

   Response if DAG not found:
   ```json
   {"error": "DAG not found", "dag_id": "dag-abc123"}
   ```

2. **Understand the cancellation mechanism**:

   The cancel endpoint sets `dag_executor.interrupt_flag = True` (cooperative cancellation per `_handle_interrupt()` in `OrchestratorService`). The DAG does not stop instantly; it halts at the next cooperative check point:
   - Between wave executions.
   - Between step dispatches within a wave.

   V1 limitation: Only `CANCEL_DAG` interrupt type is supported. `PAUSE` returns a failed response.

3. **Verify cancellation completed**:

   ```
   GET http://localhost:8081/admin/dags
   ```

   Should return an empty list `[]` once the DAG has terminated.

4. **Verify saga compensation was triggered**:

   Check logs for compensation events:
   ```
   component=orchestrator AND event=ORCH_SAGA_COMPENSATING AND dag_id={dag_id}
   ```

   CompensationRecord lifecycle:
   - `PENDING` -- compensation capability identified for completed step.
   - `EXECUTED` -- compensation ran successfully.
   - `FAILED` -> `DEAD_LETTERED` -- compensation failed, requires manual intervention (see [Procedure 6](#procedure-6-handle-saga-dead-letter)).

5. **Verify DAG completion event**:

   Check for the DAG completed event:
   ```
   component=orchestrator AND event=ORCH_DAG_COMPLETED AND dag_id={dag_id}
   ```

   The completion event is emitted even for cancelled DAGs (with a cancelled/failed status).

### InterruptRequest Schema

```python
@dataclass
class InterruptRequest:
    target_dag_id: str       # DAG to cancel
    interrupt_type: str      # "CANCEL_DAG" (V1 only)
    reason: str              # Human-readable reason
    trace_id: str            # Trace correlation
```

### Metrics to Monitor

| Metric | Type | What to Check |
|--------|------|---------------|
| `orchestrator.dag.active` | Gauge | Should drop to 0 after cancel |
| `orchestrator.dag.completed_total` | Counter | Increments with `status=cancelled` |
| `orchestrator.saga.compensation_total` | Counter | Increments for each compensated step |
| `orchestrator.error.total` | Counter | Check for new errors during cancellation |

### Log Query

```
trace_id={trace_id} AND component=orchestrator AND (
  event=ORCH_SAGA_COMPENSATING OR
  event=ORCH_DAG_COMPLETED OR
  event=ORCH_STEP_CANCELLED
)
```

---

## Procedure 4: Restart MCP Discovery

**Purpose**: Trigger a full MCP tool re-discovery cycle when tools are missing, a provider has been added or removed, or a `WorkflowGapDetected` or `MCPCapabilityCountDropped` alert fires. The ConnectorLifecycleManager discovers MCP servers, registers their tools into Fabric, and maintains a server-to-capability mapping.

**Triggered by alerts**: `WorkflowGapDetected`, `MCPCapabilityCountDropped`.

### Pre-Checks

1. Check current MCP server state:

   ```
   GET http://localhost:8081/admin/mcp/servers
   ```

   Response:
   ```json
   [
     {
       "registered": 12,
       "skipped": 0,
       "errors": [],
       "tools": ["tool1", "tool2", "..."]
     }
   ]
   ```

   Note the current `registered` count and any `errors`.

2. Check capability gauge:

   Metric `orchestrator.mcp.registered_capabilities` shows the current count of registered MCP capabilities.

### Steps

1. **Trigger full re-discovery**:

   ```
   POST http://localhost:8081/admin/mcp/rediscover
   ```

   Response on success:
   ```json
   {
     "triggered": true,
     "registered": 15,
     "skipped": 0,
     "errors": []
   }
   ```

   Response on failure:
   ```json
   {
     "triggered": false,
     "error": "Connection refused to MCP server: mcp-server-A"
   }
   ```

   The re-discovery cycle calls `ConnectorLifecycleManager.discover_and_register()`, which:
   - Calls `discovery.discover_all()` to enumerate tools from all configured MCP servers.
   - Calls `registrar.register_tools()` to register discovered tools with Fabric.
   - Updates the internal `server_capabilities` mapping.

2. **Verify post-discovery state**:

   ```
   GET http://localhost:8081/admin/mcp/servers
   ```

   Confirm `registered` count matches expected. Check `errors` array for any failed servers.

3. **For a specific server refresh** (programmatic, not via admin API in V1):

   `ConnectorLifecycleManager.refresh(server_id)` performs a targeted refresh:
   - Unregisters old capabilities for that server.
   - Re-discovers tools from that specific server.
   - Re-registers into Fabric.

   V1 note: Per-server refresh is not exposed via admin HTTP -- use the full re-discovery endpoint.

4. **If re-discovery fails**:
   - Check MCP server connectivity (is the server reachable?).
   - Check `mcp_servers.yaml` configuration for correct endpoints.
   - Check Fabric health: provider CB state may block registration.
   - Inspect lifecycle monitoring: `ConnectorLifecycleManager.start_lifecycle_monitoring()` subscribes to `k1.fabric.provider.health.changed.v1` events. If Fabric emits a health event indicating recovery, the lifecycle manager auto-triggers re-discovery.

### Metrics to Monitor

| Metric | Type | What to Check |
|--------|------|---------------|
| `orchestrator.mcp.registered_capabilities` | Gauge | Should return to expected count after re-discovery |
| `orchestrator.error.total` | Counter | Check for new errors tagged with MCP operations |

### Log Query

```
component=orchestrator AND (
  message="*discover*" OR
  message="*register*" OR
  message="*ConnectorLifecycle*" OR
  event=ORCH_MCP_TOOL_REGISTERED
)
```

---

## Procedure 5: Inspect Scheduler Trigger State

**Purpose**: Examine and troubleshoot workflow scheduler triggers. Verify that cron-based, event-based, and manual triggers are firing correctly and that `next_fire` / `last_fire` timestamps make sense.

### Pre-Checks

1. List all registered triggers:

   ```
   GET http://localhost:8081/admin/scheduler/triggers
   ```

   Response:
   ```json
   [
     {
       "workflow_id": "daily-health-check",
       "trigger": "CronTrigger(cron='0 8 * * *', next_fire='2026-02-14T08:00:00Z')"
     },
     {
       "workflow_id": "weekly-report",
       "trigger": "CronTrigger(cron='0 9 * * 1', next_fire='2026-02-17T09:00:00Z')"
     }
   ]
   ```

### Steps

1. **Get details for a specific workflow trigger**:

   ```
   GET http://localhost:8081/admin/scheduler/triggers/{workflow_id}
   ```

   Response:
   ```json
   {
     "workflow_id": "daily-health-check",
     "trigger": "CronTrigger(cron='0 8 * * *', next_fire='2026-02-14T08:00:00Z')"
   }
   ```

2. **Diagnose missed triggers**:

   - Compare `next_fire` with current time. If `next_fire` is in the past and no workflow run occurred, the scheduler may have been down during the expected fire time.
   - Check if the Orchestrator was running during the expected trigger time:
     ```
     GET http://localhost:8081/admin/metrics
     ```
     Check `uptime_ms` to determine when the Orchestrator last started.

3. **Diagnose trigger drift**:

   If `next_fire` does not match expected cron schedule:
   - The trigger state is managed via `IWorkflowStoragePort.get_due_triggers(now)` and `update_trigger_state(workflow_id, next_fire, last_fire)`.
   - In V1, trigger state persistence across restarts is deferred (shutdown step 7). After restart, triggers are re-calculated from the WorkflowSpec cron expression.

4. **Verify trigger execution**:

   Check events for workflow trigger:
   ```
   component=orchestrator AND event=ORCH_WORKFLOW_TRIGGERED AND workflow_id={workflow_id}
   ```

### Metrics to Monitor

| Metric | Type | What to Check |
|--------|------|---------------|
| `orchestrator.workflow.trigger_total` | Counter | Increments each time a trigger fires (tagged by `trigger_type`) |
| `orchestrator.workflow.active_count` | Gauge | Number of active workflow runs |

### Log Query

```
component=orchestrator AND (
  event=ORCH_WORKFLOW_TRIGGERED OR
  event=ORCH_WORKFLOW_COMPLETED
) AND workflow_id={workflow_id}
```

---

## Procedure 6: Handle Saga Dead-Letter

**Purpose**: Investigate and resolve saga compensation failures. When a DAG step is compensated (rolled back) and the compensation itself fails, the CompensationRecord transitions to `DEAD_LETTERED` status, requiring manual intervention.

### Background

CompensationRecord lifecycle:

```
PENDING  -->  EXECUTED       (compensation succeeded)
    |
    +---->  FAILED
              |
              +---->  DEAD_LETTERED  (manual intervention required)
```

Each `CompensationRecord` contains:
- `dag_id` -- which DAG this compensation belongs to.
- `step_id` -- which step needs compensation.
- `compensation_capability` -- the Fabric capability to call for rollback.
- `status` -- current state in the lifecycle above.

### Steps

1. **Identify dead-lettered compensations**:

   Check logs for dead-letter entries:
   ```
   component=orchestrator AND event=ORCH_SAGA_COMPENSATING AND status=DEAD_LETTERED
   ```

   Also check the compensation counter:
   Metric `orchestrator.saga.compensation_total` tracks all compensation attempts.

2. **Inspect the WAL for the affected DAG**:

   The Write-Ahead Log (WAL) managed by `IBridgeWritePort` records execution history:
   - `write_wal(dag_id, entry_type, payload, trace_id)` writes entries.
   - `read_wal(dag_id)` returns all WAL entries for a DAG.
   - `list_wal_ids()` returns all DAG IDs with WAL entries.

   WAL entry types:
   | Entry Type | Written When |
   |-----------|-------------|
   | `PLAN_START` | DAG execution begins |
   | `STEP_COMPLETE` | Individual step finishes |
   | `WAVE_COMPLETE` | Entire wave finishes |
   | `DAG_COMPLETE` | DAG fully completes |

3. **Reconstruct what happened**:

   Using the `trace_id` from the dead-lettered record:
   ```
   trace_id={trace_id} AND component=orchestrator AND (
     event=ORCH_STEP_COMPLETED OR
     event=ORCH_STEP_FAILED OR
     event=ORCH_SAGA_COMPENSATING
   )
   ```

   Determine:
   - Which step failed originally.
   - Which compensation capability was attempted.
   - Why the compensation itself failed.

4. **Manual compensation**:

   If the compensation capability is still available in Fabric:
   - Re-invoke the compensation capability manually via Fabric's tool execution API.
   - Write an audit record via `IBridgeWritePort.submit_audit()` documenting the manual action.

   If the compensation capability is unavailable:
   - Check MCP server health (see [Procedure 4](#procedure-4-restart-mcp-discovery)).
   - Perform manual rollback of the affected data/state.
   - Document all manual actions in the audit trail.

5. **Clear the dead-letter entry**:

   After successful manual compensation, the dead-letter record should be archived. Write a final audit record documenting the resolution.

### Metrics to Monitor

| Metric | Type | What to Check |
|--------|------|---------------|
| `orchestrator.saga.compensation_total` | Counter | Rate of compensation attempts |
| `orchestrator.error.total` | Counter | Tagged with `classification=TERMINAL` for fatal errors |
| `orchestrator.dag.completed_total` | Counter | Tagged with `status=failed` for DAGs requiring compensation |

### Log Query

```
component=orchestrator AND event=ORCH_SAGA_COMPENSATING AND dag_id={dag_id}
```

---

## Procedure 7: CB_PLANNER Management

**Purpose**: Manage the CB_PLANNER circuit breaker, which protects the Orchestrator from Planner failures. Force-open to isolate a failing Planner, force-close after a fix is deployed, or set to half-open to test partial recovery.

**Triggered by alert**: `CircuitBreakerOpen` (CB_PLANNER remained OPEN for > 2 minutes).

### Background

The Orchestrator owns one circuit breaker: `CB_PLANNER`. Fabric owns `CB_FABRIC` and `CB_MCP`.

CircuitBreakerState machine:

```
CLOSED  -- (failures > threshold) -->  OPEN
   ^                                     |
   |                              (reset_timeout expires)
   |                                     |
   |                                     v
   +---- (probe succeeds) ----  HALF_OPEN
```

Fields on `CircuitBreakerState`:
- `state`: CLOSED, OPEN, or HALF_OPEN.
- `failure_count`: consecutive failures since last success.
- `last_failure_at`: timestamp of most recent failure.
- `last_success_at`: timestamp of most recent success.
- `opened_at`: timestamp when CB transitioned to OPEN.

Impact on Orchestrator:
- `CB_PLANNER = OPEN`: HIGH-tier requests degrade to MEDIUM tier (Planner is bypassed; direct Fabric execution). ErrorRouter classifies Planner errors as DEGRADED -> `FALLBACK` action (tier HIGH -> MEDIUM).
- `CB_PLANNER = HALF_OPEN`: Probe requests are allowed through to test Planner recovery.
- `CB_PLANNER = CLOSED`: Normal operation -- all tiers available.

Health status derivation uses CB_PLANNER state:
- HEALTHY: CB_PLANNER CLOSED and mailbox < 80% capacity.
- DEGRADED: CB_PLANNER HALF_OPEN, or mailbox near capacity.
- UNHEALTHY: CB_PLANNER OPEN and mailbox at capacity.

### Steps

1. **View current CB state**:

   ```
   GET http://localhost:8081/admin/circuit-breakers
   ```

   Response:
   ```json
   {
     "CB_PLANNER": {
       "state": "OPEN",
       "failure_count": 5,
       "last_failure_at": 1739440200.0,
       "last_success_at": 1739439600.0,
       "opened_at": 1739440200.0
     }
   }
   ```

2. **Force CB to a specific state**:

   ```
   POST http://localhost:8081/admin/circuit-breakers/CB_PLANNER/state
   Content-Type: application/json

   {"state": "CLOSED"}
   ```

   Response:
   ```json
   {"name": "CB_PLANNER", "state": "CLOSED", "updated": true}
   ```

   State transitions and side effects:
   - `CLOSED`: Resets `failure_count` to 0, clears `opened_at`. All tiers resume normal operation.
   - `OPEN`: Sets `opened_at` to current time. HIGH-tier requests immediately degrade to MEDIUM.
   - `HALF_OPEN`: Allows probe requests through. Next success transitions to CLOSED; next failure transitions back to OPEN.

   V1 note: Only `CB_PLANNER` is managed via this endpoint. Attempts to set other CB names return 404.

3. **Typical recovery flow**:

   a. Alert fires: `CircuitBreakerOpen` (CB_PLANNER OPEN for > 2m).
   b. Investigate Planner health (external to Orchestrator).
   c. After Planner fix is deployed:
      - Force CB to `HALF_OPEN` to test with probe requests:
        ```
        POST /admin/circuit-breakers/CB_PLANNER/state
        {"state": "HALF_OPEN"}
        ```
      - Monitor for successful Planner responses.
      - If probes succeed, force to `CLOSED`:
        ```
        POST /admin/circuit-breakers/CB_PLANNER/state
        {"state": "CLOSED"}
        ```
   d. Verify health returns to HEALTHY:
      ```
      GET /health/status
      ```

### Metrics to Monitor

| Metric | Type | What to Check |
|--------|------|---------------|
| `orchestrator.error.total` | Counter | Tagged with `classification=DEGRADED` for Planner failures |
| `orchestrator.dag.completed_total` | Counter | Check `status=success` rate after CB reset |

### Log Query

```
component=orchestrator AND (
  message="*circuit*breaker*" OR
  message="*CB_PLANNER*" OR
  event=ORCH_ERROR_ROUTED
) AND classification=DEGRADED
```

---

## Procedure 8: Trigger Manual Workflow Run

**Purpose**: Submit a manual workflow run request for testing, debugging, or one-off execution of a registered workflow.

### Steps

1. **Verify the workflow exists** by checking scheduler triggers:

   ```
   GET http://localhost:8081/admin/scheduler/triggers
   ```

   Confirm the target `workflow_id` appears in the trigger list.

2. **Submit the manual run**:

   A `WorkflowRunRequest` is enqueued via the mailbox at `INTERACTIVE` priority (highest WFQ priority, dispatched before BACKGROUND).

   WorkflowRunRequest schema:
   ```python
   @dataclass
   class WorkflowRunRequest:
       workflow_id: str           # Target workflow
       version: Optional[str]     # Specific version (optional)
       trigger_type: TriggerType  # TriggerType.MANUAL
       trace_id: str              # Trace correlation
       priority: str              # "INTERACTIVE"
   ```

   V1 note: Manual workflow submission is programmatic via `IMailboxPort.enqueue()`. There is no dedicated admin HTTP endpoint for manual workflow triggering in V1. Use the Concierge layer or direct mailbox injection.

3. **Monitor execution**:

   ```
   component=orchestrator AND event=ORCH_WORKFLOW_TRIGGERED AND workflow_id={workflow_id}
   ```

   Then follow the resulting DAG:
   ```
   GET http://localhost:8081/admin/dags
   ```

4. **Verify workflow completion**:

   ```
   component=orchestrator AND event=ORCH_WORKFLOW_COMPLETED AND workflow_id={workflow_id}
   ```

### Metrics to Monitor

| Metric | Type | What to Check |
|--------|------|---------------|
| `orchestrator.workflow.trigger_total` | Counter | Should increment with `trigger_type=MANUAL` |
| `orchestrator.workflow.active_count` | Gauge | Should increment then decrement |
| `orchestrator.dag.completed_total` | Counter | Should increment with `status=success` |

### Log Query

```
component=orchestrator AND workflow_id={workflow_id} AND (
  event=ORCH_WORKFLOW_TRIGGERED OR
  event=ORCH_DAG_STARTED OR
  event=ORCH_DAG_COMPLETED OR
  event=ORCH_WORKFLOW_COMPLETED
)
```

---

## Procedure 9: Read Audit Trail

**Purpose**: Reconstruct the full execution path for a DAG or workflow run using the Write-Ahead Log (WAL) and event trail. Used for post-incident analysis, compliance review, or debugging.

### Background

The audit trail is built from two sources:

1. **WAL entries** (`IBridgeWritePort`):
   - `write_wal(dag_id, entry_type, payload, trace_id)` -- written at execution milestones.
   - `read_wal(dag_id)` -- retrieve all entries for a specific DAG.
   - `list_wal_ids()` -- enumerate all DAG IDs with WAL data.

2. **Audit records** (`IBridgeWritePort.submit_audit(run_manifest, trace_id)`):
   - Fire-and-forget submission of execution summaries to K0 Bridge.
   - Written at shutdown (with orphan counts) and at DAG completion.

### Steps

1. **List all DAGs with WAL entries**:

   This operation is programmatic via `IBridgeWritePort.list_wal_ids()`. V1 does not expose a dedicated admin HTTP endpoint for WAL browsing.

2. **Read WAL entries for a specific DAG**:

   Programmatic via `IBridgeWritePort.read_wal(dag_id)`. Returns a list of WAL entries ordered by write time.

   WAL entry types and their meanings:

   | Entry Type | Meaning | Key Payload Fields |
   |-----------|---------|-------------------|
   | `PLAN_START` | DAG execution began | plan_id, step_count, trace_id |
   | `STEP_COMPLETE` | Individual step finished | step_id, capability_name, status |
   | `WAVE_COMPLETE` | Wave finished | wave_index, steps_in_wave |
   | `DAG_COMPLETE` | DAG fully finished | final_status, duration_ms |

3. **Correlate with event trail**:

   Use the `trace_id` to find all related events:
   ```
   trace_id={trace_id} AND component=orchestrator
   ```

   Key events in execution order:
   1. `ORCH_TASK_ACCEPTED` -- message received in mailbox.
   2. `ORCH_PLAN_REQUESTED` -- plan request sent to Planner (HIGH tier only).
   3. `ORCH_DAG_STARTED` -- DAG execution begins.
   4. `ORCH_STEP_STARTED` / `ORCH_STEP_COMPLETED` / `ORCH_STEP_FAILED` -- per-step events.
   5. `ORCH_DAG_MICRO_REPLAN` -- micro-replan triggered (if applicable).
   6. `ORCH_DELTA_V1` -- delta emitted to session state.
   7. `ORCH_DAG_COMPLETED` -- DAG finished.
   8. `ORCH_WORKFLOW_COMPLETED` -- workflow finished (if workflow run).

4. **Crash recovery and WAL**:

   On startup, `OrchestratorService.crash_recovery()` scans WAL entries:
   - `DAG_COMPLETE` -> skip (already finished before crash).
   - `PLAN_START` or `WAVE_COMPLETE` -> re-enqueue the associated task for retry.
   - If K0 Bridge is offline -> skip recovery (WAL not accessible).

   V1 limitation: Recovery from `WAVE_COMPLETE` re-enqueues from wave 0 (full DAG re-execution).

### Metrics to Monitor

| Metric | Type | What to Check |
|--------|------|---------------|
| `orchestrator.dag.completed_total` | Counter | Total DAGs, tagged by status |
| `orchestrator.dag.duration_ms` | Histogram | End-to-end DAG duration |

### Log Query

```
trace_id={trace_id} AND component=orchestrator
```

For audit-specific entries:
```
component=orchestrator AND (message="*audit*" OR message="*WAL*")
```

---

## Procedure 10: Handle Token Budget Exhaustion

**Purpose**: Diagnose and resolve token budget exhaustion events. When a DAG step or the overall DAG exceeds its token/cost budget, the budget guard triggers a HARD_STOP, halting execution.

**Triggered by alert**: `TokenBudgetExhausted` (event-based alert on `orchestrator.token_budget.hard_stop`).

### Background

Token budgets are enforced at two levels:
- **Step level**: `TaskEnvelope.timeout_ms` field defines a per-step time budget.
- **DAG level**: Overall budget for the entire DAG execution.

The budget guard emits a `orchestrator.token_budget.hard_stop` event when the budget is exhausted, triggering the `TokenBudgetExhausted` alert.

### Steps

1. **Identify the affected DAG**:

   ```
   GET http://localhost:8081/admin/dags
   ```

   Check if a DAG is currently active and may be the one that exhausted its budget.

2. **Inspect the DAG detail**:

   ```
   GET http://localhost:8081/admin/dags/{dag_id}
   ```

   Check `steps_completed` and `steps_failed` to see how far the DAG progressed before budget exhaustion.

3. **Check step-level cost breakdown**:

   Query logs for individual step durations and costs:
   ```
   trace_id={trace_id} AND component=orchestrator AND (
     event=ORCH_STEP_COMPLETED OR
     event=ORCH_STEP_FAILED
   )
   ```

   Look for steps with unusually high `duration_ms` or token consumption.

4. **Identify the root cause**:

   Common causes of budget exhaustion:
   - **Excessive micro-replans**: Each replan adds waves and steps. Check `ORCH_DAG_MICRO_REPLAN` events.
   - **Slow Fabric providers**: Single steps consuming disproportionate time/tokens.
   - **Runaway step count**: DAG approaching `MAX_STEPS = 50` limit.
   - **Incorrect budget configuration**: Budget too low for the task complexity.

5. **Remediation options**:

   - **Adjust budget**: Increase `timeout_ms` in the TaskEnvelope for time-budget issues, or adjust token budget in the workflow spec.
   - **Optimize the plan**: Work with the Planner to generate more efficient plans (fewer steps, better parallelization).
   - **Check provider performance**: If a specific Fabric provider is slow, check its health and CB state.
   - **Cancel the DAG**: If the DAG is still running, force-cancel it (see [Procedure 3](#procedure-3-force-cancel-in-flight-dag)).

6. **Review DAG limits**:

   DAGExecutor enforces:
   - `MAX_WAVES = 20` (hard limit, including micro-replans).
   - `MAX_STEPS = 50` (hard limit).
   - `_MAX_CONCURRENT_PER_WAVE = 10` (concurrency cap).

   If these limits are being hit, the DAG may need restructuring.

### Metrics to Monitor

| Metric | Type | What to Check |
|--------|------|---------------|
| `orchestrator.dag.duration_ms` | Histogram | Compare against expected duration for tier |
| `orchestrator.step.duration_ms` | Histogram | Identify slow steps |
| `orchestrator.step.retry_total` | Counter | Retries consume additional budget |
| `orchestrator.dag.overhead_ms` | Histogram | Orchestrator's own overhead should be < 18ms P99 |

### Log Query

```
trace_id={trace_id} AND component=orchestrator AND (
  event=ORCH_STEP_COMPLETED OR
  event=ORCH_STEP_FAILED OR
  event=ORCH_DAG_MICRO_REPLAN OR
  message="*budget*" OR
  message="*token*"
)
```

---

## Appendix A: Admin API Quick Reference

All endpoints are served via `AdminHttpAdapter` on port 8081 (localhost only, aiohttp). Responses are JSON with `X-Trace-Id` header.

### Health Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/health/live` | Liveness probe | `{"alive": true}` |
| GET | `/health/ready` | Readiness probe (503 if not ready) | `{"ready": true/false, ...}` |
| GET | `/health/status` | Detailed health status | `HealthStatus` object |

### DAG Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/admin/dags` | List active DAGs (max 1 in V1) | `[ActiveDAGInfo, ...]` |
| GET | `/admin/dags/{dag_id}` | Get DAG detail | `ActiveDAGInfo` or 404 |
| POST | `/admin/dags/{dag_id}/cancel` | Cancel active DAG | `{"cancelled": true}` or 404 |

### Circuit Breaker Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/admin/circuit-breakers` | List CB states | `{"CB_PLANNER": {...}}` |
| POST | `/admin/circuit-breakers/{name}/state` | Force CB state | `{"updated": true}` or 404 |

### Scheduler Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/admin/scheduler/triggers` | List workflow triggers | `[{workflow_id, trigger}, ...]` |
| GET | `/admin/scheduler/triggers/{workflow_id}` | Get trigger detail | `{workflow_id, trigger}` or 404 |

### Operations Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| POST | `/admin/drain` | Graceful drain | `DrainResult` object |
| GET | `/admin/config` | Read-only config view | `OrchestratorConfig` dict |

### Mailbox Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/admin/mailbox/depth` | Current queue depth | `{depth, capacity}` |
| GET | `/admin/mailbox/stats` | Queue stats with pending counts | `{depth, capacity, pending_plans, pending_hil}` |

### MCP Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/admin/mcp/servers` | List MCP server state | `[{registered, skipped, errors, tools}]` |
| POST | `/admin/mcp/rediscover` | Trigger full MCP re-discovery | `{triggered, registered, ...}` |

### Diagnostic Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/admin/metrics` | Aggregated runtime metrics | `{uptime_ms, mailbox_depth, ...}` |
| GET | `/admin/version` | Build/version info | `{version, build, python, platform}` |

---

## Appendix B: Alert-to-Runbook Mapping

All 12 alerts from `k1/orchestrator/docs/alerts.md` (Epic 8.4.1) mapped to runbook procedures:

| Alert Name | Severity | Metric / Event | Runbook Procedure |
|-----------|----------|---------------|-------------------|
| `OrchestratorHighOverhead` | critical | `orchestrator.dag.overhead_ms` P99 > 18ms | [Procedure 2: Debug Stuck DAG](#procedure-2-debug-stuck-dag) |
| `DAGWaveConstructionSlow` | warning | `orchestrator.wave.construction_ms` P99 > 10ms | [Procedure 2: Debug Stuck DAG](#procedure-2-debug-stuck-dag) |
| `DAGFailureRateHigh` | critical | `orchestrator.dag.completed_total` fail ratio > 5% | [Procedure 3: Force-Cancel In-Flight DAG](#procedure-3-force-cancel-in-flight-dag) |
| `StepRetryRateHigh` | warning | `orchestrator.step.retry_total` retry ratio > 10% | [Procedure 2: Debug Stuck DAG](#procedure-2-debug-stuck-dag) |
| `SagaCompensationSpike` | warning | `orchestrator.saga.compensation_total` > 3 in 5m | [Procedure 3: Force-Cancel In-Flight DAG](#procedure-3-force-cancel-in-flight-dag) |
| `WorkflowGapDetected` | warning | `event:k1.orchestration.gap.detected` | [Procedure 4: Restart MCP Discovery](#procedure-4-restart-mcp-discovery) |
| `TokenBudgetExhausted` | critical | `event:orchestrator.token_budget.hard_stop` | [Procedure 10: Handle Token Budget Exhaustion](#procedure-10-handle-token-budget-exhaustion) |
| `HILTimeoutRate` | warning | `orchestrator.hil.request_total` timeout ratio > 20% | [Procedure 6: Handle Saga Dead-Letter](#procedure-6-handle-saga-dead-letter) |
| `CircuitBreakerOpen` | critical | `orchestrator.cb.planner.state` OPEN > 2m | [Procedure 7: CB_PLANNER Management](#procedure-7-cb_planner-management) |
| `MailboxBackpressure` | warning | `orchestrator.mailbox.depth` > 80% capacity | [Procedure 1: Drain Mailbox for Maintenance](#procedure-1-drain-mailbox-for-maintenance) |
| `PendingPlanLeak` | warning | `orchestrator.pending_plans` > 0 unchanged 60s | [Procedure 2: Debug Stuck DAG](#procedure-2-debug-stuck-dag) |
| `MCPCapabilityCountDropped` | warning | `orchestrator.mcp.registered_capabilities` drop | [Procedure 4: Restart MCP Discovery](#procedure-4-restart-mcp-discovery) |

---

## Appendix C: Metrics Catalog Quick Reference

All metrics emitted by `OrchestratorMetrics` (source: `k1/orchestrator/metrics.py`):

### Histograms (Timing)

| Metric Name | Tags | Description |
|------------|------|-------------|
| `orchestrator.dag.duration_ms` | `tier` | End-to-end DAG execution time |
| `orchestrator.dag.overhead_ms` | `message_type`, `tier` | Orchestrator overhead (Fabric/Planner wait subtracted) |
| `orchestrator.step.duration_ms` | `step_id`, `capability_name` | Per-step execution time |
| `orchestrator.wave.construction_ms` | `step_count` | Wave build time (dependency resolution) |
| `orchestrator.constraint.resolution_ms` | `step_count` | Constraint validation time |
| `orchestrator.sli.dequeue_ms` | -- | Mailbox dequeue latency |
| `orchestrator.sli.route_ms` | `message_type` | Message routing decision time |
| `orchestrator.sli.wave_dispatch_ms` | `wave_index`, `step_count` | Wave dispatch latency |
| `orchestrator.sli.guard_pipeline_ms` | `phase`, `scope_id` | Guard pipeline execution time |
| `orchestrator.sli.aggregation_ms` | `plan_id` | Result aggregation time |
| `orchestrator.sli.param_resolution_ms` | `step_id` | Parameter resolution time |
| `orchestrator.sli.adapter_wait_ms` | `adapter`, `operation` | Time waiting on external adapters |

### Counters

| Metric Name | Tags | Description |
|------------|------|-------------|
| `orchestrator.dag.completed_total` | `status` | DAGs completed (success/failed/cancelled) |
| `orchestrator.step.retry_total` | `reason` | Step retries |
| `orchestrator.saga.compensation_total` | -- | Saga compensation attempts |
| `orchestrator.workflow.trigger_total` | `trigger_type` | Workflow triggers fired |
| `orchestrator.error.total` | `classification` | Errors by ErrorRouter classification |
| `orchestrator.hil.request_total` | `outcome` | HIL requests (approved/rejected/timed_out) |
| `orchestrator.mailbox.processed_total` | `message_type` | Messages processed from mailbox |

### Gauges

| Metric Name | Description |
|------------|-------------|
| `orchestrator.dag.active` | 1 if a DAG is running, 0 otherwise |
| `orchestrator.mailbox.depth` | Current mailbox queue depth |
| `orchestrator.workflow.active_count` | Number of active workflow runs |
| `orchestrator.mcp.registered_capabilities` | Count of registered MCP capabilities |
| `orchestrator.pending_plans` | Pending plan contexts awaiting Planner response |
| `orchestrator.pending_hil` | Pending HIL contexts awaiting user response |

---

## Appendix D: Error Classification Matrix

ErrorRouter (`k1/orchestrator/orchestration/error_router.py`) classifies adapter errors and determines the recovery action:

### Classification Table

| Adapter Origin | Classification | Action | Details |
|---------------|---------------|--------|---------|
| `mailbox` | RECOVERABLE | RETRY (max 1) | Mailbox enqueue failure |
| `delta_emit` | RECOVERABLE | RETRY (max 1) | Delta emission to session state |
| `bridge_write` | RECOVERABLE | RETRY (max 1) | K0 Bridge write failure |
| `event_sub` | RECOVERABLE | RETRY (max 1) | Event subscription failure |
| `fabric_gateway` | DEGRADED | DEGRADE | Fabric execution failure -> degrade capability |
| `planner` | DEGRADED | FALLBACK | Planner failure -> degrade HIGH tier to MEDIUM |
| `state_read` | DEGRADED | DEGRADE (empty) | State read failure -> proceed with empty state |
| Any adapter | TERMINAL | ABORT | Unrecoverable error -> abort DAG |

### Error Actions

| Action | Behavior |
|--------|----------|
| `RETRY(n)` | Retry the operation up to `n` times |
| `DEGRADE` | Continue execution with degraded functionality |
| `FALLBACK` | Switch to a lower tier (e.g., HIGH -> MEDIUM) |
| `ABORT` | Terminate the DAG, trigger saga compensation |

The ErrorRouter emits an `ORCH_ERROR_ROUTED` diagnostic event for every classified error, enabling alerting and post-incident analysis.
