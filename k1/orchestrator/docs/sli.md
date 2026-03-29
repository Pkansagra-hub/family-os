# Orchestrator SLI Definition

Status: Active (V1)
Owner: Orchestrator Team
Last Updated: 2026-02-13
Source Plan: `docs/plans/orchestrator-implementation-plan.md` (Epic 8.1.1)

This document defines the service level indicators (SLIs) for Orchestrator critical paths.

- Latency SLIs are measured at P99 unless stated otherwise.
- Orchestrator overhead excludes Planner/Fabric adapter wait time where specified.
- V1 removed SLIs (token budget, quality gate) are documented but not active.

## SLI Catalog (YAML)

```yaml
sli_version: 1.0.0
module: orchestrator
measurement_policy:
  latency_statistic: p99
  clock_source: time.perf_counter_ns
  units:
    latency: ms
    ratio: percent

latency_slis:
  - name: mailbox_dequeue_route_latency
    description: Time from mailbox dequeue to routing dispatch completion in OrchestratorService.
    target: "< 1 ms"
    measurement_point: "OrchestratorService._mailbox_loop + _process_one route dispatch"
    unit: ms

  - name: dag_wave_construction_latency
    description: Kahn topological sort plus wave grouping latency for DAG construction.
    target: "< 5 ms"
    measurement_point: "DAGExecutor.build_waves"
    unit: ms

  - name: capreq_construction_latency
    description: Per-step latency to build CapabilityRequest from PlanStep.
    target: "< 1 ms per step"
    measurement_point: "StepRunner request construction path"
    unit: ms

  - name: param_resolution_latency
    description: Per-step latency to resolve $step_N.result references and nested params.
    target: "< 1 ms per step"
    measurement_point: "ParamResolver.resolve"
    unit: ms

  - name: output_schema_validation_latency
    description: Per-step JSON schema validation latency for output guard enforcement (ORCH-15).
    target: "< 1 ms per step"
    measurement_point: "StepRunner.validate_output_schema / OutputSchemaGuard"
    unit: ms

  - name: conditional_edge_eval_latency
    description: Per-wave conditional edge evaluation latency (ORCH-16).
    target: "< 1 ms per wave"
    measurement_point: "ConditionalEdgeEvaluator.before_wave"
    unit: ms

  - name: discovery_heuristic_latency
    description: Per-wave micro-replan overlap heuristic latency (ORCH-13 trigger decision).
    target: "< 1 ms per wave"
    measurement_point: "MicroReplan heuristic overlap check"
    unit: ms

  - name: result_aggregation_latency
    description: Latency to aggregate N StepResults into AggregatedResult.
    target: "< 2 ms"
    measurement_point: "OrchestratorService.aggregate"
    unit: ms

  - name: progress_delta_emission_latency
    description: Latency to construct and emit progress delta payload.
    target: "< 1 ms"
    measurement_point: "ExecutionMonitor.after_wave + DeltaEmit path"
    unit: ms

  - name: constraint_validation_latency
    description: Full ConstraintResolver pass latency before DAG execution.
    target: "< 5 ms"
    measurement_point: "ConstraintResolver.validate"
    unit: ms

  - name: total_orchestrator_overhead_latency
    description: End-to-end Orchestrator overhead (excluding Planner/Fabric adapter wait) across process path.
    target: "< 18 ms"
    measurement_point: "OrchestratorService.process total overhead timer"
    unit: ms

  - name: wave_dispatch_overhead_latency
    description: Async wave dispatch setup overhead for parallel step execution.
    target: "< 1 ms"
    measurement_point: "DAGExecutor asyncio.gather setup path"
    unit: ms

  - name: wave_construction_scaling_latency
    description: Wave construction scaling targets by plan size.
    target: "10-step < 5 ms; 25-step < 10 ms; 50-step < 20 ms"
    measurement_point: "DAGExecutor.build_waves size-scaled benchmark"
    unit: ms

budget_envelope_slis:
  - name: medium_tier_e2e_budget
    description: Total MEDIUM tier end-to-end execution budget, including Fabric latency.
    target: "< 10 s"
    measurement_point: "TaskEnvelope(MEDIUM) ingest to AggregatedResult"
    unit: s

  - name: high_tier_e2e_budget
    description: Total HIGH tier end-to-end execution budget, including Planner and Fabric latency.
    target: "< 45 s"
    measurement_point: "TaskEnvelope(HIGH) ingest to AggregatedResult"
    unit: s

operational_slis:
  - name: step_success_rate
    description: Fraction of steps completed successfully.
    target: "> 95%"
    measurement_point: "orchestrator.step.completed_total vs orchestrator.step.failed_total"
    unit: percent

  - name: dag_completion_rate
    description: Fraction of DAG runs reaching completed state.
    target: "> 90%"
    measurement_point: "orchestrator.dag.completed_total(status=success) / total"
    unit: percent

  - name: retry_rate
    description: Fraction of steps that required retries.
    target: "< 10% of steps"
    measurement_point: "orchestrator.step.retry_total / orchestrator.step.attempt_total"
    unit: percent

  - name: saga_compensation_rate
    description: Fraction of DAGs requiring saga compensation.
    target: "< 5% of DAGs"
    measurement_point: "orchestrator.saga.compensation_total / orchestrator.dag.completed_total"
    unit: percent

  - name: workflow_trigger_precision
    description: Trigger execution skew from scheduled cron fire time.
    target: "within 1 second"
    measurement_point: "WorkflowScheduler scheduled_time vs actual_fire_time"
    unit: s

  - name: hil_response_rate
    description: Fraction of HIL requests answered within timeout.
    target: "> 80% within 30 seconds"
    measurement_point: "orchestrator.hil.request_total(outcome=responded_within_timeout)"
    unit: percent

removed_v1_slis:
  - name: token_budget_check_latency
    status: removed
    reason: "ORCH-14 deferred in V1; no provider token metadata source"

  - name: quality_gate_check_latency
    status: removed
    reason: "No provider quality_score signal in V1"
```

## Notes

- This file is the source of truth for SLI targets consumed by performance tests (Epic 7.7.x), metrics hooks (8.1.2), and alerting thresholds (8.4.1).
- Any SLI target change here must be reflected in benchmark thresholds and alert rules.
