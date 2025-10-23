"""
Module: k1.l2_orchestration.protocol_monitor.pdl_parser
Purpose: Parse Protocol Definition Language (PDL) YAML files and compile to FSM

ADR References:
- ADR-0003a: PDL Language specification (YAML-based protocol definition)
- ADR-0003b: 6 Protocol Definitions (hire, task, clarification, barge-in, tool, saga)
- ADR-0011: FlatBuffers serialization (FSM binary format)

This module parses YAML protocol definitions and compiles them into Finite State Machines (FSMs)
for runtime validation. It also performs deadlock detection using Tarjan's algorithm.

Performance Budget: <100ms per protocol (one-time startup cost)

Compiler Pipeline:
  1. YAML Parser: Parse PDL YAML → validate syntax
  2. Semantic Validator: Check state/transition/message consistency
  3. FSM Generator: Build FSM data structure
  4. Deadlock Detector: Tarjan's algorithm for cycle detection
  5. FlatBuffers Serializer: Binary FSM format for fast loading

PDL YAML Structure:
  protocol:
    name: "agent_hire"
    version: "1.0.0"
    states:
      - name: "IDLE"
        initial: true
      - name: "NEGOTIATING"
        timeout_ms: 500
    transitions:
      - from: "IDLE"
        to: "NEGOTIATING"
        message: "TaskAnnouncement"
        sender: "orchestrator"
        receiver: "agent"

TODO: Import this module in parent __init__.py once implemented
"""

__all__ = [
    "PDLParser",
    "FSMGenerator",
    "DeadlockDetector",
]

# TODO: Implement PDLParser, FSMGenerator, DeadlockDetector classes
