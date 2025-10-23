# ADR-0052e: HITL Schema Integration Strategy

**Status:** 🔄 **PROPOSED** (2025-10-22)
**Date:** 2025-10-22
**Decision Date:** TBD
**Parent ADR:** [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md)
**Authors:** K1 Architecture Team
**Category:** Architecture & Integration
**Technical Story:** [Integration Strategy for 6 HITL FlatBuffers Schemas]

**Related ADRs:**

- [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md) - Parent umbrella ADR
- [ADR-0052a: Step-by-Step Approval Protocol](0052a-step-by-step-approval-protocol.md)
- [ADR-0052b: RED Band Approval](0052b-red-band-approval-two-person-rule.md)
- [ADR-0052c: Nested Clarification Chains](0052c-nested-clarification-chains-history.md)
- [ADR-0052d: Proactive Risk Confirmation](0052d-proactive-risk-confirmation.md)
- [ADR-0003b: 6 Core Protocol Implementations](0003b-6-core-protocol-implementations.md) - Protocol 3 (Clarification) foundation
- [ADR-0012b: Layer 2 State & Persistence](0012b-layer2-state-persistence-schemas.md)
- [ADR-0012d: Layer 4 Ingress & Voice](0012d-layer4-ingress-voice-schemas.md)

---

## Executive Summary

**Purpose:** Define integration strategy for 6 new HITL (Human-in-the-Loop) FlatBuffers schemas required by ADR-0052 and sub-ADRs.

**Key Decision Points:**

1. **Where to place HITL schemas?** (Layer 4 vs. separate module vs. distributed)
2. **How to integrate with existing WebSocket protocol?** (message types, flow)
3. **State persistence strategy** (SessionState, K0 WAL, K0 receipts)
4. **Namespace organization** (consistent naming across schemas)
5. **Message flow design** (embedding vs. separate message types)

**Recommended Approach: Option B - Hybrid Integration**

- **Communication schemas** (requests/responses) → Layer 4 (WebSocket protocol)
- **State schemas** (workflow/history) → Layer 2 (SessionState integration)
- **Audit schemas** (approval records) → Layer 2 (K0 receipts extension)
- **Shared enums** → Common schema for reuse

**Schema Count Impact:**

- **Original Plan:** 76 schemas (Layer 1-5)
- **With HITL:** 82 schemas (+6 HITL schemas)
  - Layer 4: 20 schemas (14 existing + 6 HITL)
  - OR distributed: Layer 2 +3, Layer 4 +3

---

## Context

### Current State

**Existing FlatBuffers Schema Structure:**

```
k1/contracts/flatbuffers/
├── layer1_core/              # 15 schemas ✅ (agent, task, plan, protocol, feedback)
├── layer2_state/             # 18 schemas ✅ (session_state, memory, receipts, events)
├── layer3_execution/         # 16 schemas ✅ (tools, models, MCP, streams)
├── layer4_ingress/           # 14 schemas ✅ (HTTP, WebSocket, SSE, voice)
└── layer5_infrastructure/    # 13 schemas (pending) (metrics, logging, errors)
```

**Existing WebSocket Protocol (Layer 4):**

- `websocket_message.fbs` - Low-level WebSocket frames (TEXT/BINARY/PING/PONG/CLOSE)
- `ws_connection_init.fbs` - Handshake/authentication
- `ws_turn_message.fbs` - Turn-based conversation (USER_INPUT/AGENT_OUTPUT/SYSTEM_EVENT)
- `ws_heartbeat.fbs` - Keep-alive

**Current Turn Message Structure:**

```flatbuffers
namespace k1.websocket;

enum WSTurnMessageType : uint8 {
  USER_INPUT = 0,
  AGENT_OUTPUT = 1,
  SYSTEM_EVENT = 2
}

table WSTurnMessage {
  turn_id: string (required);
  message_type: WSTurnMessageType (required);
  payload: string (required);        // ← Generic string payload
  timestamp_ms: uint64 = 0;
}
```

**Problem:** Generic `payload: string` cannot carry structured HITL messages (clarifications, approvals, confirmations).

### Required HITL Schemas (From ADR-0052 Sub-ADRs)

**ADR-0052a: Step-by-Step Approval (5 schemas)**

1. `StepByStepRequest` - Agent → User (per-step approval)
2. `StepByStepResponse` - User → Agent (approve/reject/rollback)
3. `WorkflowState` - Persistent workflow state (K0 WAL)
4. `StepHistoryItem` - Step execution history
5. Enums: `RiskLevel`, `StepAction`, `RollbackOption`, `WorkflowStatus`, `StepStatus`

**ADR-0052b: RED Band Approval (3 schemas)**

1. `RedBandApprovalRequest` - Agent → User (explicit phrase confirmation)
2. `RedBandApprovalResponse` - User → Agent (phrase + action)
3. `RedBandAuditRecord` - Audit trail (K0 receipts, 7-year retention)
4. Enums: `PrivacyBand`, `ApprovalLevel`, `ApprovalAction`

**ADR-0052c: Nested Clarifications (3 schemas)**

1. `NestedClarificationRequest` - Agent → User (multi-level clarification)
2. `NestedClarificationResponse` - User → Agent (answer/go-back/cancel)
3. `ClarificationHistory` - History stack (SessionState Scoreboard)
4. `ClarificationItem` - Single clarification record
5. Enum: `ClarificationAction`

**ADR-0052d: Proactive Confirmation (2 schemas)**

1. `ProactiveConfirmationRecord` - Audit trail (K0 receipts)
2. `ConfidenceFactor` - Confidence score breakdown

**Shared/Common:**

1. `ClarificationType` enum - Extends ADR-0003b Protocol 3
   - Existing: MULTIPLE_CHOICE, FREE_TEXT, YES_NO, APPROVAL
   - New: STEP_BY_STEP, RED_BAND_APPROVAL, CONDITIONAL_CHAIN, PROACTIVE_CONFIRM

**Total: 13+ tables + 10+ enums = ~6-8 schema files**

---

## Integration Challenges

### Challenge 1: Message Type Explosion

**Problem:** Adding 4 new HITL message types to `WSTurnMessageType` creates message type explosion:

- Existing: USER_INPUT, AGENT_OUTPUT, SYSTEM_EVENT
- New: STEP_BY_STEP_REQUEST, STEP_BY_STEP_RESPONSE, RED_BAND_REQUEST, RED_BAND_RESPONSE, NESTED_CLARIFICATION_REQUEST, NESTED_CLARIFICATION_RESPONSE, PROACTIVE_CONFIRMATION_REQUEST, PROACTIVE_CONFIRMATION_RESPONSE
- Total: 3 existing + 8 new = 11 message types

**Trade-off:**

- ✅ Explicit typing (type-safe message routing)
- ❌ Enum bloat (hard to maintain, violates Open/Closed Principle)

### Challenge 2: State Persistence Fragmentation

**Problem:** HITL schemas have different persistence requirements:

- `WorkflowState` → K0 WAL (ephemeral, 24-hour retention, checkpoint after each step)
- `ClarificationHistory` → SessionState Scoreboard (in-memory, session-scoped)
- `RedBandAuditRecord` → K0 receipts (durable, 7-year retention, compliance)
- `ProactiveConfirmationRecord` → K0 receipts (durable, 7-year retention)

**Trade-off:**

- ✅ Right persistence tier per schema (performance + durability)
- ❌ Complex integration (3 different storage backends)

### Challenge 3: Namespace Collision

**Problem:** ADRs use different namespaces:

- ADR-0052a: `k1.websocket` (WebSocket-focused)
- ADR-0052b: `FamilyOS.HITL` (HITL-focused)
- ADR-0052c: `k1.websocket` (WebSocket-focused)
- ADR-0052d: `FamilyOS.HITL` (HITL-focused)
- Existing Layer 4: `k1.websocket`, `k1.api_gateway`, `k1.voice_pipeline`, `k1.barge_in`

**Need:** Consistent namespace strategy.

### Challenge 4: Protocol 3 (Clarification) Extension

**Problem:** ADR-0003b defines Protocol 3 (Clarification) in PDL YAML format:

- States: 4 (start → clarifying → clarified/timeout)
- Transitions: 6
- Message types: ClarificationRequest, ClarificationResponse

**Current:** No FlatBuffers schema for Protocol 3 messages (only PDL YAML).

**HITL Requirement:** Protocol 3 needs FlatBuffers schemas for 7 ClarificationType variants.

**Trade-off:**

- ✅ Unify HITL clarifications under Protocol 3 umbrella
- ❌ Complex migration (existing clarifications vs. new HITL types)

---

## Decision: 3 Integration Options

### Option A: All HITL Schemas in Layer 4 (Monolithic WebSocket)

**Structure:**

```
k1/contracts/flatbuffers/layer4_ingress/
├── websocket_message.fbs              # Existing
├── ws_connection_init.fbs             # Existing
├── ws_turn_message.fbs                # Existing (modify: add HITL message types)
├── ws_heartbeat.fbs                   # Existing
├── http_request.fbs                   # Existing
├── ... (10 more existing Layer 4)
├── clarification.fbs                  # NEW (base Protocol 3 + ClarificationType enum)
├── step_by_step_approval.fbs         # NEW (ADR-0052a)
├── red_band_approval.fbs             # NEW (ADR-0052b)
├── nested_clarification.fbs          # NEW (ADR-0052c)
├── proactive_confirmation.fbs        # NEW (ADR-0052d)
└── hitl_common.fbs                   # NEW (shared enums)
```

**Namespace:** `k1.websocket` for all HITL schemas

**WSTurnMessage Changes:**

```flatbuffers
enum WSTurnMessageType : uint8 {
  USER_INPUT = 0,
  AGENT_OUTPUT = 1,
  SYSTEM_EVENT = 2,

  // NEW: HITL message types
  CLARIFICATION_REQUEST = 3,
  CLARIFICATION_RESPONSE = 4,
  STEP_BY_STEP_REQUEST = 5,
  STEP_BY_STEP_RESPONSE = 6,
  RED_BAND_REQUEST = 7,
  RED_BAND_RESPONSE = 8,
  NESTED_CLARIFICATION_REQUEST = 9,
  NESTED_CLARIFICATION_RESPONSE = 10,
  PROACTIVE_CONFIRMATION_REQUEST = 11,
  PROACTIVE_CONFIRMATION_RESPONSE = 12,
}

table WSTurnMessage {
  turn_id: string (required);
  message_type: WSTurnMessageType (required);

  // Polymorphic payload (union)
  payload: WSTurnPayload (required);

  timestamp_ms: uint64 = 0;
}

union WSTurnPayload {
  user_input: string,
  agent_output: string,
  system_event: string,
  clarification_request: ClarificationRequest,
  clarification_response: ClarificationResponse,
  step_by_step_request: StepByStepRequest,
  step_by_step_response: StepByStepResponse,
  red_band_request: RedBandApprovalRequest,
  red_band_response: RedBandApprovalResponse,
  nested_clarification_request: NestedClarificationRequest,
  nested_clarification_response: NestedClarificationResponse,
  proactive_confirmation_request: ProactiveConfirmationRecord,
  // ... more as needed
}
```

**Pros:**

- ✅ All WebSocket messages in one layer (clear ownership)
- ✅ Type-safe routing (explicit message types)
- ✅ Easy to find (developers look in Layer 4 for WebSocket)

**Cons:**

- ❌ Message type explosion (12 types, growing)
- ❌ Layer 4 bloat (20 schemas in one directory)
- ❌ Violates Single Responsibility (Layer 4 = ingress, not state/audit)
- ❌ State schemas (`WorkflowState`, `ClarificationHistory`) don't belong in Layer 4

**Verdict:** ❌ **Rejected** - Layer 4 should not contain state/audit schemas.

---

### Option B: Hybrid Integration (Distributed by Function) ✅ **RECOMMENDED**

**Structure:**

```
k1/contracts/flatbuffers/
├── layer2_state/
│   ├── ... (18 existing)
│   ├── workflow_state.fbs                # NEW (ADR-0052a - K0 WAL persistence)
│   ├── clarification_history.fbs         # NEW (ADR-0052c - SessionState)
│   └── hitl_audit.fbs                    # NEW (ADR-0052b/d - K0 receipts)
│
└── layer4_ingress/
    ├── ... (14 existing)
    ├── clarification.fbs                 # NEW (Protocol 3 base + ClarificationType enum)
    ├── step_by_step_request.fbs          # NEW (ADR-0052a - request/response only)
    ├── red_band_request.fbs              # NEW (ADR-0052b - request/response only)
    └── nested_clarification_request.fbs  # NEW (ADR-0052c - request/response only)
```

**Distribution Logic:**

- **Layer 4 (Ingress/Communication):** Request/Response messages (WebSocket protocol)
  - `clarification.fbs` - Base Protocol 3 + ClarificationType enum
  - `step_by_step_request.fbs` - StepByStepRequest/Response
  - `red_band_request.fbs` - RedBandApprovalRequest/Response
  - `nested_clarification_request.fbs` - NestedClarificationRequest/Response

- **Layer 2 (State/Persistence):** State + audit schemas
  - `workflow_state.fbs` - WorkflowState, StepHistoryItem (K0 WAL)
  - `clarification_history.fbs` - ClarificationHistory, ClarificationItem (SessionState)
  - `hitl_audit.fbs` - RedBandAuditRecord, ProactiveConfirmationRecord (K0 receipts)

**Namespace Strategy:**

- Layer 4 communication: `k1.websocket.hitl`
- Layer 2 state: `k1.session_state.hitl`
- Layer 2 audit: `k1.receipts.hitl`

**WSTurnMessage Changes (Simplified):**

```flatbuffers
enum WSTurnMessageType : uint8 {
  USER_INPUT = 0,
  AGENT_OUTPUT = 1,
  SYSTEM_EVENT = 2,

  // NEW: Generic HITL message type
  HITL_REQUEST = 3,
  HITL_RESPONSE = 4,
}

table WSTurnMessage {
  turn_id: string (required);
  message_type: WSTurnMessageType (required);

  // Polymorphic payload
  payload: WSTurnPayload (required);

  timestamp_ms: uint64 = 0;
}

union WSTurnPayload {
  user_input: string,
  agent_output: string,
  system_event: string,

  // HITL messages (polymorphic)
  hitl_request: HITLRequest,
  hitl_response: HITLResponse,
}

// Polymorphic HITL request
union HITLRequest {
  step_by_step: StepByStepRequest,
  red_band: RedBandApprovalRequest,
  nested_clarification: NestedClarificationRequest,
  proactive_confirmation: ProactiveConfirmationRequest,
}

// Polymorphic HITL response
union HITLResponse {
  step_by_step: StepByStepResponse,
  red_band: RedBandApprovalResponse,
  nested_clarification: NestedClarificationResponse,
  proactive_confirmation: ProactiveConfirmationResponse,
}
```

**Pros:**

- ✅ Clear separation of concerns (communication vs. state vs. audit)
- ✅ Layer 4 stays focused on ingress/protocol
- ✅ Layer 2 naturally holds state/audit schemas
- ✅ Scalable (adding new HITL type = 1 new schema in Layer 4, optional state in Layer 2)
- ✅ Minimal WSTurnMessage changes (2 new types, not 8)
- ✅ Namespaces reflect function (`websocket.hitl`, `session_state.hitl`, `receipts.hitl`)

**Cons:**

- ⚠️ Schema split across layers (need to read both Layer 2 and Layer 4)
- ⚠️ Import dependencies (Layer 4 schemas reference Layer 2 state schemas)

**Verdict:** ✅ **RECOMMENDED** - Best balance of clarity and scalability.

---

### Option C: Separate HITL Module (Domain-Focused)

**Structure:**

```
k1/contracts/flatbuffers/
├── layer1_core/              # 15 schemas
├── layer2_state/             # 18 schemas
├── layer3_execution/         # 16 schemas
├── layer4_ingress/           # 14 schemas
├── layer5_infrastructure/    # 13 schemas
└── hitl/                     # NEW: 6 HITL schemas (cross-layer)
    ├── clarification.fbs
    ├── step_by_step.fbs
    ├── red_band.fbs
    ├── nested_clarification.fbs
    ├── proactive_confirmation.fbs
    └── hitl_common.fbs
```

**Namespace:** `k1.hitl` for all schemas

**Pros:**

- ✅ HITL as first-class module (clear domain)
- ✅ Easy to find (all HITL in one place)
- ✅ Decoupled from layer architecture (cross-cutting concern)

**Cons:**

- ❌ Breaks layer architecture (6th "layer" not in original 5-layer design)
- ❌ Namespace confusion (`k1.hitl` vs. `k1.websocket` vs. `k1.session_state`)
- ❌ State persistence unclear (which layer owns HITL state?)
- ❌ Import dependencies (HITL schemas reference Layer 2 SessionState, Layer 4 WebSocket)

**Verdict:** ❌ **Rejected** - Violates 5-layer architecture, adds complexity.

---

## Recommended Approach: Option B - Hybrid Integration

### Schema Placement

**Layer 4 (Ingress/Communication) - 17 schemas:**

```
k1/contracts/flatbuffers/layer4_ingress/
├── ... (14 existing)
├── clarification.fbs                 # Protocol 3 base + ClarificationType enum
├── step_by_step_request.fbs          # StepByStepRequest/Response
└── red_band_request.fbs              # RedBandApprovalRequest/Response + NestedClarificationRequest/Response
```

**Layer 2 (State/Persistence) - 21 schemas:**

```
k1/contracts/flatbuffers/layer2_state/
├── ... (18 existing)
├── workflow_state.fbs                # WorkflowState, StepHistoryItem
├── clarification_history.fbs         # ClarificationHistory, ClarificationItem
└── hitl_audit.fbs                    # RedBandAuditRecord, ProactiveConfirmationRecord
```

**Total Schema Count:**

- **Original Plan:** 76 schemas
- **With HITL:** 82 schemas (+6 HITL)
  - Layer 1: 15 ✅
  - Layer 2: 21 (18 + 3 HITL) ✅
  - Layer 3: 16 ✅
  - Layer 4: 17 (14 + 3 HITL) ✅
  - Layer 5: 13 (pending)

### Namespace Strategy

**Consistent Namespace Hierarchy:**

```
k1.websocket.hitl          # Layer 4 HITL communication schemas
k1.session_state.hitl      # Layer 2 HITL state schemas
k1.receipts.hitl           # Layer 2 HITL audit schemas
```

**Example:**

```flatbuffers
// layer4_ingress/clarification.fbs
namespace k1.websocket.hitl;

enum ClarificationType : uint8 {
  MULTIPLE_CHOICE = 0,
  FREE_TEXT = 1,
  YES_NO = 2,
  APPROVAL = 3,
  STEP_BY_STEP = 4,
  RED_BAND_APPROVAL = 5,
  CONDITIONAL_CHAIN = 6,
  PROACTIVE_CONFIRM = 7,
}

// layer2_state/workflow_state.fbs
namespace k1.session_state.hitl;

table WorkflowState {
  workflow_id: string;
  session_id: string;
  total_steps: uint16;
  // ... rest of fields
}

// layer2_state/hitl_audit.fbs
namespace k1.receipts.hitl;

table RedBandAuditRecord {
  approval_id: string;
  session_id: string;
  operation: string;
  // ... rest of fields
}
```

### Message Flow Design

**Simplified WSTurnMessage with HITL Support:**

```flatbuffers
// layer4_ingress/ws_turn_message.fbs (MODIFIED)
namespace k1.websocket;

enum WSTurnMessageType : uint8 {
  USER_INPUT = 0,
  AGENT_OUTPUT = 1,
  SYSTEM_EVENT = 2,
  HITL_REQUEST = 3,       // NEW: Agent → User HITL clarification
  HITL_RESPONSE = 4,      // NEW: User → Agent HITL response
}

table WSTurnMessage {
  turn_id: string (required);
  message_type: WSTurnMessageType (required);
  payload: WSTurnPayload (required);
  timestamp_ms: uint64 = 0;
}

union WSTurnPayload {
  text: string,                              // USER_INPUT/AGENT_OUTPUT/SYSTEM_EVENT
  hitl_request: HITLRequestPayload,          // HITL_REQUEST
  hitl_response: HITLResponsePayload,        // HITL_RESPONSE
}
```

**HITL Request/Response Payloads:**

```flatbuffers
// layer4_ingress/clarification.fbs
namespace k1.websocket.hitl;

// Import Layer 4 request schemas
include "step_by_step_request.fbs";
include "red_band_request.fbs";

// Polymorphic HITL request
union HITLRequestPayload {
  step_by_step: StepByStepRequest,
  red_band: RedBandApprovalRequest,
  nested_clarification: NestedClarificationRequest,
  proactive_confirmation: ProactiveConfirmationRequest,
}

// Polymorphic HITL response
union HITLResponsePayload {
  step_by_step: StepByStepResponse,
  red_band: RedBandApprovalResponse,
  nested_clarification: NestedClarificationResponse,
  proactive_confirmation: ProactiveConfirmationResponse,
}
```

### State Persistence Integration

**1. WorkflowState → K0 WAL (ADR-0052a)**

```python
# k1/l2_orchestration/hitl/step_by_step.py
async def checkpoint_workflow_state(workflow: WorkflowState):
    """Persist workflow state to K0 WAL after each step"""
    fb_bytes = serialize_workflow_state(workflow)  # → FlatBuffers

    await k0_client.append_wal(
        session_id=workflow.session_id,
        event_type="workflow_checkpoint",
        payload=fb_bytes,
        retention_sec=86400,  # 24 hours (ephemeral)
    )
```

**2. ClarificationHistory → SessionState Scoreboard (ADR-0052c)**

```python
# k1/l2_orchestration/state/session_state.py
from k1.contracts.flatbuffers.layer2_state.clarification_history import ClarificationHistory

# SessionState Scoreboard integration
@dataclass
class Scoreboard:
    qud_stack: Deque[str]
    clarification_history: ClarificationHistory  # NEW field
    last_user_intent: str
    grounding_status: GroundingStatus
```

**3. RedBandAuditRecord → K0 Receipts (ADR-0052b)**

```python
# k1/l2_orchestration/hitl/red_band.py
async def log_red_band_audit(approval: RedBandApprovalResponse, result: OperationResult):
    """Write audit record to K0 receipts (7-year retention)"""
    audit_record = RedBandAuditRecord(...)
    fb_bytes = serialize_audit_record(audit_record)  # → FlatBuffers

    await k0_client.write_receipt(
        event_type="red_band_approval",
        payload=fb_bytes,
        retention_years=7,  # Compliance requirement
    )
```

---

## Implementation Plan

### Phase 1: Foundation (Week 1)

**Goal:** Create base HITL schemas + WSTurnMessage integration

**Tasks:**

1. Create `layer4_ingress/clarification.fbs` (ClarificationType enum)
2. Modify `layer4_ingress/ws_turn_message.fbs` (add HITL_REQUEST/HITL_RESPONSE)
3. Create `layer4_ingress/step_by_step_request.fbs` (ADR-0052a communication)
4. Create `layer4_ingress/red_band_request.fbs` (ADR-0052b communication)
5. Validate file_identifier uniqueness across all Layer 4 schemas

**Deliverables:**

- 3 new Layer 4 schemas
- 1 modified Layer 4 schema (ws_turn_message.fbs)
- Unit tests: FlatBuffers serialization/deserialization

### Phase 2: State Integration (Week 2)

**Goal:** Create state/audit schemas + persistence integration

**Tasks:**

1. Create `layer2_state/workflow_state.fbs` (ADR-0052a state)
2. Create `layer2_state/clarification_history.fbs` (ADR-0052c state)
3. Create `layer2_state/hitl_audit.fbs` (ADR-0052b/d audit)
4. Update `layer2_state/scoreboard_section.fbs` (add ClarificationHistory field)
5. Validate file_identifier uniqueness across all Layer 2 schemas

**Deliverables:**

- 3 new Layer 2 schemas
- 1 modified Layer 2 schema (scoreboard_section.fbs)
- Integration tests: K0 WAL checkpoint, SessionState persistence

### Phase 3: Protocol 3 Extension (Week 3)

**Goal:** Unify HITL under Protocol 3 (Clarification) umbrella

**Tasks:**

1. Update `k1/protocols/clarification.pdl.yml` (add 4 new ClarificationType states)
2. Create Protocol 3 FlatBuffers validator (compile PDL → FSM)
3. Wire HITL message handlers to Protocol 3 FSM
4. Add timeout enforcement per clarification type
5. Integration tests: Protocol 3 validation for all 7 ClarificationType variants

**Deliverables:**

- Updated Protocol 3 PDL YAML
- Protocol 3 FSM validator
- Integration tests: HITL message flow end-to-end

### Phase 4: Testing & Documentation (Week 4)

**Goal:** Comprehensive testing + documentation

**Tasks:**

1. WARD unit tests: All 6 HITL schemas (serialize/deserialize)
2. WARD integration tests: Message flow (request → response → state persistence)
3. Performance tests: Serialization <10ms, validation <2ms
4. Update architecture diagrams (add HITL layer)
5. Document namespace strategy + integration patterns

**Deliverables:**

- 100% WARD test coverage
- Performance validation (meet budgets)
- Updated architecture documentation

---

## Acceptance Criteria

- ✅ All 6 HITL schemas created in correct layers (3 Layer 4, 3 Layer 2)
- ✅ WSTurnMessage extended with HITL_REQUEST/HITL_RESPONSE (2 new types, not 8)
- ✅ Consistent namespaces: `k1.websocket.hitl`, `k1.session_state.hitl`, `k1.receipts.hitl`
- ✅ File identifiers unique across ALL layers (no duplicates)
- ✅ State persistence integrated: WorkflowState → K0 WAL, ClarificationHistory → SessionState, Audit → K0 receipts
- ✅ Protocol 3 (Clarification) extended with 4 new ClarificationType enums
- ✅ All schemas pass FlatBuffers compilation (no syntax errors)
- ✅ WARD tests pass: Serialization, deserialization, message flow
- ✅ Performance targets met: Serialize <10ms, validate <2ms
- ✅ Documentation updated: Architecture diagrams, integration patterns

---

## Alternatives Considered

### Alternative 1: Keep Generic String Payload in WSTurnMessage

**Approach:** Don't modify `WSTurnMessage`, serialize HITL messages as JSON strings in `payload` field.

**Pros:**

- ✅ No WSTurnMessage changes (backward compatible)
- ✅ Simple to implement (no FlatBuffers unions)

**Cons:**

- ❌ Loses type safety (can't validate HITL messages at compile time)
- ❌ JSON serialization slower than FlatBuffers (10-50x)
- ❌ No schema evolution (breaking changes if HITL schema changes)
- ❌ Violates FlatBuffers contract design (mixing JSON + FlatBuffers)

**Verdict:** ❌ **Rejected** - Loses FlatBuffers benefits.

### Alternative 2: Create Separate WebSocket Endpoints per HITL Type

**Approach:** Instead of `wss://k1/chat`, create `wss://k1/step-by-step`, `wss://k1/red-band`, etc.

**Pros:**

- ✅ Explicit routing (URL determines HITL type)
- ✅ Can version independently (`wss://k1/step-by-step/v1`, `/v2`)

**Cons:**

- ❌ WebSocket connection explosion (4 connections per session)
- ❌ Complex client-side logic (which endpoint to use?)
- ❌ Violates single WebSocket principle (all messages in one connection)
- ❌ Harder to compose (e.g., nested clarification inside step-by-step)

**Verdict:** ❌ **Rejected** - WebSocket per message type is anti-pattern.

---

## Questions for Review

1. **Namespace Strategy:** Is `k1.websocket.hitl` too verbose? Should we use `k1.hitl` instead?
2. **WSTurnMessage Union:** Should we use FlatBuffers union (polymorphic) or separate message types?
3. **State Schema Location:** Should `WorkflowState` be in Layer 2 or Layer 4? (Recommendation: Layer 2)
4. **Audit Retention:** 7-year retention (ADR-0052b) requires K0 receipts. Should we create separate audit schema or extend existing `receipt.fbs`?
5. **Protocol 3 Migration:** Should we create FlatBuffers schemas for existing Protocol 3 (MULTIPLE_CHOICE, FREE_TEXT, YES_NO) or only new types (STEP_BY_STEP, RED_BAND, etc.)?

---

## References

**ADRs:**

- [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md)
- [ADR-0052a: Step-by-Step Approval](0052a-step-by-step-approval-protocol.md)
- [ADR-0052b: RED Band Approval](0052b-red-band-approval-two-person-rule.md)
- [ADR-0052c: Nested Clarifications](0052c-nested-clarification-chains-history.md)
- [ADR-0052d: Proactive Confirmation](0052d-proactive-risk-confirmation.md)
- [ADR-0003b: 6 Core Protocol Implementations](0003b-6-core-protocol-implementations.md)
- [ADR-0012b: Layer 2 State & Persistence](0012b-layer2-state-persistence-schemas.md)
- [ADR-0012d: Layer 4 Ingress & Voice](0012d-layer4-ingress-voice-schemas.md)

**Source Documents:**

- `k1/contracts/flatbuffers/` - Existing FlatBuffers schema structure
- `k1/protocols/clarification.pdl.yml` - Protocol 3 PDL definition

---

**Document Status:** 🔄 **PROPOSED** (2025-10-22)

**Next Steps:**

1. Review with architecture team (approval required for Option B)
2. Finalize namespace strategy (`k1.websocket.hitl` vs. `k1.hitl`)
3. Create Phase 1 schemas (3 Layer 4 communication schemas)
4. Create Phase 2 schemas (3 Layer 2 state/audit schemas)
5. Update WSTurnMessage with HITL_REQUEST/HITL_RESPONSE
6. WARD integration tests

---

**END OF ADR-0052e**
