"""
Module: k1.l2_orchestration.protocol_monitor.violation_handler
Purpose: Handle protocol violations with configurable actions

ADR References:
- ADR-0003c: Protocol Monitor runtime (violation actions)
- ADR-0038: Audit trail (DLQ logging to K0)
- ADR-0029: Prometheus metrics (violation counters)

This module handles protocol violations detected by the FSM executor.
It supports 6 violation actions: BLOCK, WARN, DLQ, REPAIR, FALLBACK, ABORT.

Performance Budget: <1ms P95 (violation detection + action execution)

Violation Actions:
  1. BLOCK: Reject message, don't deliver to mailbox
  2. WARN: Log warning to K0, deliver message anyway
  3. DLQ: Write to Dead Letter Queue for manual review
  4. REPAIR: Auto-inject timeout transition to advance protocol
  5. FALLBACK: Trigger fallback protocol (e.g., clarification)
  6. ABORT: Abort protocol, cleanup FSM state, notify orchestrator

Configuration:
  - Per-protocol violation policy (YAML config)
  - Per-message-type overrides
  - Safety-critical: BLOCK (default)
  - Best-effort: WARN or REPAIR

Example YAML:
  violation_policy:
    agent_hire:
      default: BLOCK
      timeout: REPAIR
    task_execution:
      default: WARN
      invalid_state: FALLBACK

TODO: Import this module in parent __init__.py once implemented
"""

__all__ = [
    "ViolationDetector",
    "ActionExecutor",
    "DLQWriter",
]

# TODO: Implement ViolationDetector, ActionExecutor, DLQWriter classes
