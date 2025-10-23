"""
Module: k1.l2_orchestration.protocol_monitor.fsm_executor
Purpose: Runtime FSM execution and message validation

ADR References:
- ADR-0003c: Protocol Monitor runtime implementation
- ADR-0002: Actor Model (mailbox integration)
- ADR-0011: FlatBuffers (FSM binary format)
- ADR-0024: Performance budgets (<2ms P95 validation)

This module loads compiled FSMs and validates all agent messages against protocol state machines.
It tracks per-session protocol state with RwLock concurrency for high-throughput validation.

Performance Budget:
  - FSM loading: <100ms per protocol (6 protocols = 600ms startup)
  - Runtime validation: <2ms P95 per message
  - Session state lookup: <0.1ms (hash table)
  - State transition: <0.5ms (deterministic)

Components:
  1. FSM Registry: Load 6 protocols from FlatBuffers, reachability check
  2. Session Tracker: Per-session FSM state, RwLock concurrency, hash table cleanup
  3. Validator: Receive-side validation, <5ms P95 mailbox budget, <2ms validation
  4. Transition Engine: Execute state transitions, emit K0 events

6 Protocol FSMs:
  1. hire.fsm (Agent Hire): 6 states, 8 transitions
  2. task.fsm (Task Execution): 5 states, 10 transitions
  3. clarification.fsm (Clarification): 4 states, 6 transitions
  4. barge_in.fsm (Barge-In): 3 states, 5 transitions
  5. tool_call.fsm (Tool Call): 4 states, 7 transitions
  6. saga.fsm (Saga Rollback): 5 states, 9 transitions

Validation Strategy:
  - Receive-side: Validate before delivering to actor mailbox
  - Reject invalid: Drop message, log to K0, increment violation counter
  - Progress guarantee: Timeout enforcer auto-transitions on stall

TODO: Import this module in parent __init__.py once implemented
"""

# TODO: Implement FSMRegistry, SessionTracker, Validator, TransitionEngine classes
