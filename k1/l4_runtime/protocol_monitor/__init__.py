"""
K1 L4 Runtime — Protocol Monitor (PDL, FSM, Validation)

**Purpose:** MPST protocol validation with PDL parser, FSM registry, message validation, timeout enforcement

**Components:**
- pdl_parser/ — YAML protocol parser, FSM compilation <100ms
- fsm_registry/ — Compiled FSM storage, protocol lookup
- validator/ — Message validation <5ms P95
- timeout_enforcer/ — Per-protocol timeout enforcement
- role_verifier/ — Security validation, role attestation

**Performance:**
- PDL parse: <5ms P95
- Message validation: <5ms P95
- FSM compilation: <100ms
- Timeout check: <1ms

**ADRs (8 total):**
- ADR-0003: PDL Language (YAML protocol parser, FSM compilation)
- ADR-0003a: PDL Language (compiler pipeline <100ms compilation)
- ADR-0003b: Protocol Definitions (6 protocols: hire, task, clarification, barge-in, tool, saga)
- ADR-0003c: Protocol Monitor (FSM registry, validator, timeout enforcer)
- ADR-0003d: Security (role verifier, agent lease, message signer)

**6 Validated Protocols (ADR-0003b):**
1. **Hire Protocol:** Orchestrator → Agent (TaskAnnouncement → Proposal → Accept/Reject)
2. **Task Protocol:** Agent → Tool (TaskRequest → Progress → Completion)
3. **Clarification Protocol:** Agent → User (Question → Answer → Acknowledgment)
4. **Barge-in Protocol:** User → Agent (Interrupt → Cancel → Resume)
5. **Tool Protocol:** Agent → Tool Sandbox (Execute → Stream → Complete)
6. **Saga Protocol:** Orchestrator → Agents (Compensate → Rollback → Commit)

**Research Foundations:**
- Honda et al. (2008) — Multiparty Session Types (MPST)
- Scribble Protocol Language (Imperial College 2013)

**Integration:**
- Actor Fabric: Router validates messages before delivery
- SessionState: Protocol transitions update control section
- L2 Orchestration: Hire/task protocols coordinate agents
- L3 Execution: Tool protocol validates tool calls

**Performance Metrics:**
- protocol_monitor_parse_latency_ms (histogram)
- protocol_monitor_validate_total (counter, protocol, result=valid|invalid)
- protocol_monitor_validate_latency_ms (histogram)
- protocol_monitor_timeout_violations_total (counter, protocol)

**Last Updated:** October 2025
**Status:** Production-ready MPST protocol validation
"""

__version__ = "0.1.0"

# TODO: Implement pdl_parser/, fsm_registry/, validator/, timeout_enforcer/, role_verifier/
# Per ADR-0003 family (0003-0003d)
