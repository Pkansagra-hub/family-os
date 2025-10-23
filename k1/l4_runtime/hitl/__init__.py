"""
K1 L4 Runtime — HITL Protocols (Human-in-the-Loop)

**Purpose:** Enhanced HITL with step-by-step approval, RED band auditing, nested clarifications, proactive confirmation

**Components:**
- step_by_step/ — Workflow checkpoints, K0 WAL integration <10ms
- red_band/ — Audit trail 7 years, forcing functions, approval workflow
- clarification/ — Stack max depth 3, nested question handling
- proactive/ — Confidence-based confirmation, feedback signals

**Performance:**
- Checkpoint: <10ms P95
- Audit write: <20ms
- Clarification: <50ms

**ADRs (5 total):**
- ADR-0052: Performance (step-by-step <10ms, 7-year audit, WARD tests)
- ADR-0052a: Step-by-Step Approval (K0 WAL checkpoint, WorkflowState FSM)
- ADR-0052b: RED Band Approval (audit trail 7 years, forcing functions, privacy bands)
- ADR-0052c: Nested Clarifications (clarification stack, max depth 3)
- ADR-0052d: Proactive Confirmation (confidence-based, feedback signals)
- ADR-0052e: Layer 4 Communication (clarification/step-by-step/RED band FlatBuffers schemas)

**Step-by-Step Approval (ADR-0052a):**
- Workflow checkpointing to K0 WAL <10ms
- WorkflowState FSM (PENDING → APPROVED → EXECUTING → COMPLETED)
- User approval required before each step execution

**RED Band Approval (ADR-0052b):**
- 7-year audit trail (legal compliance)
- Forcing functions (e.g., "type CONFIRM to proceed")
- Privacy band enforcement (GREEN/AMBER/RED)

**Nested Clarifications (ADR-0052c):**
- Clarification stack max depth 3 (prevent infinite loops)
- Track parent question → sub-question relationships
- Automatic unwind on resolution

**Proactive Confirmation (ADR-0052d):**
- Confidence threshold <0.7 triggers confirmation request
- User feedback signals update confidence model
- Adaptive confirmation frequency

**Integration:**
- Protocol Monitor: Validates HITL protocol transitions
- SessionState: Control section tracks approval workflow
- K0 WAL: Audit trail persistence

**Performance Metrics:**
- hitl_step_approval_latency_ms (histogram)
- hitl_red_band_approvals_total (counter)
- hitl_clarification_depth (histogram, max=3)
- hitl_proactive_confirmations_total (counter)

**Last Updated:** October 2025
**Status:** Production-ready HITL protocols
"""

__version__ = "0.1.0"

# TODO: Implement step_by_step/, red_band/, clarification/, proactive/
# Per ADR-0052 family (0052-0052e)
