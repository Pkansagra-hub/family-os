"""
Module: k1.l2_orchestration.protocol_monitor
Purpose: Multiparty Session Type (MPST) protocol validation for agent communication

ADR References:
- ADR-0003: Protocol Validation (MPST overview)
- ADR-0003a: PDL Language (YAML-based protocol definition)
- ADR-0003b: 6 Protocol Definitions
- ADR-0003c: Protocol Monitor (runtime validation)
- ADR-0003d: Security (role verification, 2-phase validation)

The Protocol Monitor ensures all agent communication follows strict protocols to
prevent deadlocks, ensure progress guarantees, and validate security properties.

Components:
  1. pdl_parser/ - Parse PDL YAML → compile to FSM → detect deadlocks
  2. fsm_executor/ - Load FSM → track session state → validate messages
  3. violation_handler/ - Handle protocol violations (BLOCK/WARN/DLQ/REPAIR/FALLBACK/ABORT)
  4. timeout_enforcer/ - Monitor timeouts → auto-transition → progress guarantees

Performance Budget:
  - Protocol compilation: <100ms per protocol (one-time startup)
  - FSM loading: <100ms per protocol (6 protocols = 600ms startup)
  - Runtime validation: <2ms P95 per message
  - Role verification: <1ms P95 (HMAC check)
  - 2-Phase validation total: <3ms P95

6 Validated Protocols:
  1. Agent Hire: 6 states, 8 transitions, Contract Net, 500ms negotiation
  2. Task Execution: 5 states, 10 transitions, AI planning, 5000ms LLM timeout
  3. Clarification: 4 states, 6 transitions, nested protocol, 30000ms user timeout
  4. Barge-In: 3 states, 5 transitions, interrupt handling, 200ms decision
  5. Tool Call: 4 states, 7 transitions, MCP/WASM sandbox, 3000ms execution
  6. Saga Rollback: 5 states, 9 transitions, compensation, 5000ms compensate

Research: Multiparty Session Types (Honda et al. 2008), Scribble protocol language

Integration:
  - All Layer 2 → Layer 3 actor messages validated
  - MPSC queue integration (mailbox receive-side validation)
  - FlatBuffers serialization for FSM binary format
  - K0 WAL audit trail for violations
"""

__all__ = [
    "PDLParser",
    "FSMExecutor",
    "ViolationHandler",
    "TimeoutEnforcer",
]

# TODO: Import from submodules once implemented
# from .pdl_parser import PDLParser
# from .fsm_executor import FSMExecutor
# from .violation_handler import ViolationHandler
# from .timeout_enforcer import TimeoutEnforcer
