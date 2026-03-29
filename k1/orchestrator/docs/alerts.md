# Orchestrator Alert Definitions

Status: Active (Epic 8.4.1)
Owner: Orchestrator Team
Last Updated: 2026-02-13
Source Plan: `docs/plans/orchestrator-implementation-plan.md` (Epic 8.4.1)

This document defines alert thresholds for SLO violations and operational anomalies.

- Format is YAML alert definitions.
- Each alert maps to one metric/event source and one condition.
- Event-based alerts are represented with `metric: event:<topic>` and `condition: event_received`.

## Alert Catalog (YAML)

```yaml
alerts_version: 1.0.0
module: orchestrator

alerts:
  - name: OrchestratorHighOverhead
    metric: orchestrator.dag.overhead_ms
    condition: p99_gt
    threshold: 18
    window: 5m
    severity: critical
    description: "Orchestrator overhead P99 exceeded 18ms for 5 minutes (SLI #13)."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-2-debug-stuck-dag

  - name: DAGWaveConstructionSlow
    metric: orchestrator.wave.construction_ms
    condition: p99_gt
    threshold: 10
    window: 5m
    severity: warning
    description: "DAG wave construction P99 exceeded 10ms for 5 minutes (SLI #2)."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-2-debug-stuck-dag

  - name: DAGFailureRateHigh
    metric: orchestrator.dag.completed_total
    condition: ratio_failed_over_total_gt
    threshold: 0.05
    window: 15m
    severity: critical
    description: "DAG failure ratio exceeded 5% over 15 minutes."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-3-force-cancel-in-flight-dag

  - name: StepRetryRateHigh
    metric: orchestrator.step.retry_total
    condition: ratio_retry_over_step_completed_gt
    threshold: 0.10
    window: 15m
    severity: warning
    description: "Step retry ratio exceeded 10% over 15 minutes."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-2-debug-stuck-dag

  - name: SagaCompensationSpike
    metric: orchestrator.saga.compensation_total
    condition: increase_gt
    threshold: 3
    window: 5m
    severity: warning
    description: "More than 3 saga compensations were triggered within 5 minutes."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-3-force-cancel-in-flight-dag

  - name: WorkflowGapDetected
    metric: event:k1.orchestration.gap.detected
    condition: event_received
    threshold: 1
    window: 5m
    severity: warning
    description: "A proactive workflow gap was detected (capability removed affecting active workflow)."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-4-restart-mcp-discovery

  - name: TokenBudgetExhausted
    metric: event:orchestrator.token_budget.hard_stop
    condition: event_received
    threshold: 1
    window: 5m
    severity: critical
    description: "Token budget HARD_STOP was triggered."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-10-handle-token-budget-exhaustion

  - name: HILTimeoutRate
    metric: orchestrator.hil.request_total
    condition: ratio_timed_out_over_total_gt
    threshold: 0.20
    window: 30m
    severity: warning
    description: "HIL timeout ratio exceeded 20% over 30 minutes."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-6-hil-override-and-timeout-handling

  - name: CircuitBreakerOpen
    metric: orchestrator.cb.planner.state
    condition: equals_open_sustained
    threshold: 2m
    window: 2m
    severity: critical
    description: "CB_PLANNER remained OPEN for more than 2 minutes (Orchestrator-owned circuit breaker)."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-7-cb-planner-management

  - name: MailboxBackpressure
    metric: orchestrator.mailbox.depth
    condition: gt_percent_of_config
    threshold: 0.80
    window: 1m
    severity: warning
    description: "Mailbox depth exceeded 80% of configured capacity for 1 minute."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-1-drain-mailbox-for-maintenance

  - name: PendingPlanLeak
    metric: orchestrator.pending_plans
    condition: gt_and_unchanged
    threshold: 0
    window: 60s
    severity: warning
    description: "Pending plan contexts remained > 0 without change for 60 seconds (possible orphan context leak)."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-2-debug-stuck-dag

  - name: MCPCapabilityCountDropped
    metric: orchestrator.mcp.registered_capabilities
    condition: drops_below_expected_after_health_event
    threshold: expected_count
    window: 5m
    severity: warning
    description: "Registered MCP capability count dropped below expected after Fabric health event processing."
    runbook_link: k1/orchestrator/docs/orchestrator_runbook.md#procedure-4-restart-mcp-discovery
```

## Notes

- `WorkflowGapDetected` and `TokenBudgetExhausted` are represented as event-based alerts.
- `CircuitBreakerOpen` is scoped only to `CB_PLANNER` (Orchestrator-owned). Alerts for `CB_FABRIC` and `CB_MCP` belong to their owning modules.
- Runbook links point to the planned `orchestrator_runbook.md` procedures from Epic 9.3.3.
