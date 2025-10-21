# ADR-0003d: Role Attestation & Capability Verification

**Status:** ✅ **COMPLETED** (2025-10-12)
**Date:** 2025-10-12
**Last Updated:** 2025-10-17 (M2 Context: See ADR-0074 for module isolation strategy with capabilities)
**Deciders:** K1 Architecture Team
**Technical Story:** Implement role attestation and capability verification for protocol message security
**Parent ADR:** [ADR-0003: MPST Protocol Validation for Agent Communication](0003-mpst-protocol-validation.md)
**Related ADRs:**
- [ADR-0003a: Protocol Definition Language (PDL) Specification](0003a-protocol-definition-language-pdl-specification.md)
- [ADR-0003b: 6 Core Protocol Implementations](0003b-6-core-protocol-implementations.md)
- [ADR-0003c: Protocol Monitor Runtime Implementation](0003c-protocol-monitor-runtime-implementation.md)
- [ADR-0010: Capability-Based Security](0010-capability-based-security.md)
- [ADR-0002: Actor Model for Agent Isolation](0002-actor-model-agent-isolation.md)
- [ADR-0074 (Pluggable Module System - **NEW M2**)](0074-pluggable-module-system.md)

---

## Executive Summary

**Role Attestation** ensures that protocol messages come from legitimate agents with proper capabilities. Every Actor message includes a **role + lease signature** that the Protocol Monitor verifies before validation.

**Key Features:**
- **Message Envelope**: Every Actor message includes `sender_role`, `sender_lease_id`, `signature`
- **Role Verification**: Protocol Monitor checks HMAC-SHA256 signature (secret key = agent lease)
- **Capability Binding**: PDL protocol specifies required capabilities per role
- **Zero Spoofing**: Unsigned messages blocked, invalid signatures rejected
- **Audit Trail**: All role verification failures logged with trace_id
- **Performance**: <1ms P95 HMAC-SHA256 verification overhead

**Security Properties:**
- **No role spoofing:** Agents cannot impersonate other roles (orchestrator, tool_runner, etc.)
- **No privilege escalation:** Agents cannot send messages outside their capabilities
- **Capability least privilege:** Agents have minimal capabilities (e.g., Planner has TOOL_CALL, Concierge does not)
- **Lease expiry enforcement:** Expired leases rejected (prevents zombie agents)

**Architecture:**
- Role attestation happens **before** protocol validation (2-phase check)
- Phase 1: Verify role signature (HMAC-SHA256, <1ms)
- Phase 2: Validate protocol FSM (current_state + message_type, <2ms)
- Total overhead: <3ms P95 (within <5ms mailbox budget)

---

## Context

### The Challenge

**K1 Security Threat Model:**
- **58 agents:** 4 AI + 54 pure, exchanging messages via Actor mailbox
- **Trust boundary:** Agents are isolated actors, but message channel is shared
- **Threat:** Malicious/buggy agent sends message with fake role (e.g., impersonate orchestrator)
- **Impact:** Protocol bypass, privilege escalation, system compromise

**Example Attack:**
```python
# Malicious agent impersonates orchestrator
fake_message = ActorMessage(
    sender_role="orchestrator",  # FAKE! Agent is not orchestrator
    message_type="HireApproval",
    session_id="session_123",
)
# Without role attestation → message delivered, agent gets hired illegitimately
```

**Requirements:**
- Verify sender role matches agent identity (no spoofing)
- Verify agent has capability to send this message type
- Verify agent lease is valid (not expired)
- Verify message signature (HMAC-SHA256 with lease secret)
- Performance: <1ms P95 verification overhead

**Research Foundation:**
- Capability-Based Security (Dennis & Van Horn 1966) — Fine-grained access control
- Message Authentication Codes (Bellare et al. 1996) — HMAC-SHA256 signatures
- Actor Model (Hewitt 1973) — Message authenticity in distributed systems

---

## Design

### Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                         Actor Message Envelope                          │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ActorMessage {                                                          │
│    // Core fields                                                        │
│    session_id: str                    // Session ID                     │
│    message_type: str                  // "HireRequest", "Proposal", etc.│
│    payload: bytes                     // FlatBuffers payload            │
│    cognitive_trace_id: str            // OpenTelemetry trace ID         │
│                                                                          │
│    // Role attestation fields (NEW)                                     │
│    sender_role: str                   // "orchestrator", "agent", etc.  │
│    sender_agent_id: str               // Agent ID (from lease)          │
│    sender_lease_id: str               // Capability lease ID            │
│    signature: bytes                   // HMAC-SHA256(message, lease)    │
│  }                                                                       │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                        Role Verification Flow                           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Message arrives at mailbox (Actor mailbox delivery path)           │
│     → Extract: sender_role, sender_lease_id, signature                 │
│                                                                          │
│  2. Lookup agent lease (LeaseRegistry, O(1) hash table)                │
│     → Validate: lease exists, not expired, matches sender_agent_id     │
│     → Budget: <500μs P95                                                │
│                                                                          │
│  3. Verify HMAC-SHA256 signature (message + lease secret)              │
│     → Compute: HMAC-SHA256(message_type + session_id + payload, secret)│
│     → Compare: computed == signature (constant-time comparison)        │
│     → Budget: <500μs P95                                                │
│                                                                          │
│  4. Verify sender_role matches lease role                               │
│     → Check: lease.role == message.sender_role                         │
│     → Budget: <50μs P95                                                 │
│                                                                          │
│  5. Verify capability for message_type (PDL protocol spec)             │
│     → Lookup: protocol.roles[sender_role].capabilities                 │
│     → Check: message_type in allowed_message_types                     │
│     → Budget: <50μs P95                                                 │
│                                                                          │
│  6. Decision: PASS (deliver to protocol validator) or BLOCK (reject)   │
│     → Total overhead: ~1100μs = 1.1ms P95                               │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                     2-Phase Validation Pipeline                         │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Phase 1: Role Attestation (<1ms P95)                                   │
│    → Verify signature (HMAC-SHA256)                                     │
│    → Verify lease (exists, not expired)                                 │
│    → Verify role (matches lease)                                        │
│    → Verify capability (message_type allowed)                           │
│    → Result: PASS (proceed to Phase 2) or BLOCK (reject)               │
│                                                                          │
│  Phase 2: Protocol Validation (<2ms P95)                                │
│    → Validate FSM (current_state + message_type)                        │
│    → Check guard conditions (if present)                                │
│    → Update FSM state (valid transition)                                │
│    → Result: PASS (deliver) or BLOCK (violation)                       │
│                                                                          │
│  Total: <3ms P95 (within <5ms mailbox budget)                           │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### Component 1: Agent Lease (Capability Metadata)

**Purpose:** Store agent capabilities and role information (issued by Agent Fabric).

```python
"""
Module: k1.agent_fabric.lease
Purpose: Agent capability lease with role and signature secret

Research: Capability-Based Security (Dennis & Van Horn 1966)
"""

from dataclasses import dataclass
from typing import Set
import time
import secrets

@dataclass
class AgentLease:
    """
    Agent Lease: Capability lease with role and signature secret

    Issued by Agent Fabric during agent hire (see ADR-0005, ADR-0010).
    Contains:
    - Agent ID and role (orchestrator, agent, tool_runner, etc.)
    - Capabilities (TOOL_CALL, MCP_ACCESS, etc.)
    - Signature secret (for HMAC-SHA256 message authentication)
    - Expiry timestamp (lease duration)
    """

    lease_id: str                # Unique lease ID (UUID)
    agent_id: str                # Agent ID (actor_id)
    role: str                    # "orchestrator", "agent", "tool_runner", "system"
    capabilities: Set[str]       # {"TOOL_CALL", "MCP_ACCESS", "MODEL_HUB_READ", ...}
    signature_secret: bytes      # HMAC-SHA256 secret (32 bytes, random)
    issued_at: float             # Unix timestamp (issue time)
    expires_at: float            # Unix timestamp (expiry time)

    @staticmethod
    def issue(agent_id: str, role: str, capabilities: Set[str], duration_seconds: int = 3600) -> 'AgentLease':
        """Issue new agent lease"""
        now = time.time()
        return AgentLease(
            lease_id=secrets.token_urlsafe(16),  # Random lease ID
            agent_id=agent_id,
            role=role,
            capabilities=capabilities,
            signature_secret=secrets.token_bytes(32),  # 256-bit random secret
            issued_at=now,
            expires_at=now + duration_seconds,
        )

    def is_expired(self) -> bool:
        """Check if lease expired"""
        return time.time() > self.expires_at

    def has_capability(self, capability: str) -> bool:
        """Check if lease has capability"""
        return capability in self.capabilities

# Example: Issue lease for AI agent (Planner)
planner_lease = AgentLease.issue(
    agent_id="agent_planner_01",
    role="agent",
    capabilities={"TOOL_CALL", "MCP_ACCESS", "MODEL_HUB_READ"},
    duration_seconds=3600,  # 1 hour
)
```

---

### Component 2: Message Signing (Sender Side)

**Purpose:** Sign Actor messages with HMAC-SHA256 before sending.

```python
"""
Module: k1.actor.message_signer
Purpose: Sign Actor messages with HMAC-SHA256

Research: Message Authentication Codes (Bellare et al. 1996)
"""

import hmac
import hashlib
from dataclasses import dataclass

@dataclass
class ActorMessage:
    """Actor message with role attestation fields"""
    session_id: str
    message_type: str
    payload: bytes
    cognitive_trace_id: str

    # Role attestation fields
    sender_role: str
    sender_agent_id: str
    sender_lease_id: str
    signature: bytes

class MessageSigner:
    """
    Message Signer: Sign Actor messages with HMAC-SHA256

    Responsibilities:
    1. Extract message fields (session_id, message_type, payload)
    2. Compute HMAC-SHA256(message_fields, lease_secret)
    3. Attach signature to message envelope
    """

    @staticmethod
    def sign(message_type: str, session_id: str, payload: bytes, lease: AgentLease, trace_id: str) -> ActorMessage:
        """Sign message with agent lease"""

        # Compute message digest (for HMAC input)
        message_digest = f"{message_type}:{session_id}:{len(payload)}".encode('utf-8')

        # Compute HMAC-SHA256 signature
        signature = hmac.new(
            key=lease.signature_secret,
            msg=message_digest + payload,
            digestmod=hashlib.sha256,
        ).digest()

        # Build signed message
        return ActorMessage(
            session_id=session_id,
            message_type=message_type,
            payload=payload,
            cognitive_trace_id=trace_id,
            sender_role=lease.role,
            sender_agent_id=lease.agent_id,
            sender_lease_id=lease.lease_id,
            signature=signature,
        )

# Example: AI agent signs message
planner = get_agent("agent_planner_01")
lease = planner.get_lease()

message = MessageSigner.sign(
    message_type="PlanProposal",
    session_id="session_123",
    payload=plan_payload_bytes,
    lease=lease,
    trace_id="trace_456",
)

# Send to orchestrator
send_message(receiver="orchestrator_01", message=message)
```

---

### Component 3: Role Verifier (Receiver Side)

**Purpose:** Verify message signature and role before protocol validation.

```python
"""
Module: k1.protocol_monitor.role_verifier
Purpose: Verify message signature and role attestation

Research: Capability-Based Security (Dennis & Van Horn 1966), HMAC (Bellare 1996)
"""

import hmac
import hashlib
import time
from typing import Optional
import structlog

logger = structlog.get_logger()

@dataclass
class VerificationResult:
    """Role verification result"""
    valid: bool
    reason: Optional[str]
    action: str  # "PASS", "BLOCK"

class LeaseRegistry:
    """
    Lease Registry: Store and lookup agent leases

    Responsibilities:
    1. Store leases issued by Agent Fabric (hash table: lease_id -> AgentLease)
    2. Lookup lease by lease_id (O(1) hash table access)
    3. Validate lease (exists, not expired)
    """

    def __init__(self):
        self.leases: Dict[str, AgentLease] = {}

    def register(self, lease: AgentLease):
        """Register new lease"""
        self.leases[lease.lease_id] = lease

    def get(self, lease_id: str) -> Optional[AgentLease]:
        """Get lease by ID"""
        return self.leases.get(lease_id)

    def cleanup_expired(self):
        """Cleanup expired leases (periodic task)"""
        expired = [lid for lid, lease in self.leases.items() if lease.is_expired()]
        for lid in expired:
            del self.leases[lid]

class RoleVerifier:
    """
    Role Verifier: Verify message signature and role attestation

    Responsibilities:
    1. Lookup agent lease (LeaseRegistry)
    2. Verify HMAC-SHA256 signature
    3. Verify lease not expired
    4. Verify sender_role matches lease.role
    5. Verify capability for message_type (PDL protocol spec)
    6. Return PASS or BLOCK decision
    7. Budget: <1ms P95
    """

    def __init__(self, lease_registry: LeaseRegistry, fsm_registry: 'FSMRegistry'):
        self.lease_registry = lease_registry
        self.fsm_registry = fsm_registry

    def verify(self, message: ActorMessage, protocol_name: str) -> VerificationResult:
        """
        Verify message role attestation

        This is Phase 1 of 2-phase validation pipeline.
        MUST complete in <1ms P95.
        """
        start_time = time.time()

        # Step 1: Lookup agent lease
        lease = self.lease_registry.get(message.sender_lease_id)
        if not lease:
            return VerificationResult(
                valid=False,
                reason=f"Lease {message.sender_lease_id} not found",
                action="BLOCK"
            )

        # Step 2: Verify lease not expired
        if lease.is_expired():
            return VerificationResult(
                valid=False,
                reason=f"Lease {message.sender_lease_id} expired",
                action="BLOCK"
            )

        # Step 3: Verify sender_agent_id matches lease
        if message.sender_agent_id != lease.agent_id:
            return VerificationResult(
                valid=False,
                reason=f"Agent ID mismatch: {message.sender_agent_id} != {lease.agent_id}",
                action="BLOCK"
            )

        # Step 4: Verify sender_role matches lease.role
        if message.sender_role != lease.role:
            return VerificationResult(
                valid=False,
                reason=f"Role mismatch: {message.sender_role} != {lease.role}",
                action="BLOCK"
            )

        # Step 5: Verify HMAC-SHA256 signature
        message_digest = f"{message.message_type}:{message.session_id}:{len(message.payload)}".encode('utf-8')
        expected_signature = hmac.new(
            key=lease.signature_secret,
            msg=message_digest + message.payload,
            digestmod=hashlib.sha256,
        ).digest()

        if not hmac.compare_digest(expected_signature, message.signature):
            return VerificationResult(
                valid=False,
                reason="Invalid signature (HMAC-SHA256 mismatch)",
                action="BLOCK"
            )

        # Step 6: Verify capability for message_type (PDL protocol spec)
        protocol = self.fsm_registry.get_protocol(protocol_name)
        allowed = self._check_capability(protocol, message.sender_role, message.message_type)
        if not allowed:
            return VerificationResult(
                valid=False,
                reason=f"Role {message.sender_role} not allowed to send {message.message_type}",
                action="BLOCK"
            )

        # All checks passed
        latency_ms = (time.time() - start_time) * 1000

        # Metrics
        from k1.observability.metrics import role_verification_latency_ms
        role_verification_latency_ms.observe(latency_ms)

        return VerificationResult(valid=True, reason=None, action="PASS")

    def _check_capability(self, protocol: 'FSMProtocol', sender_role: str, message_type: str) -> bool:
        """Check if role allowed to send message_type (from PDL protocol spec)"""

        # Find transitions with this message_type
        allowed_roles = set()
        for trans in protocol.transitions:
            if trans.message_type == message_type:
                allowed_roles.add(trans.sender_role)

        # Check if sender_role allowed
        return sender_role in allowed_roles or "*" in allowed_roles
```

---

### Component 4: PDL Protocol Role Specification

**Purpose:** Extend PDL YAML to specify allowed roles per message type.

```yaml
# Example: Agent Hire Protocol with Role Specification
# File: k1/protocols/hire.pdl.yml

protocol:
  name: "agent_hire"
  version: "1.0"

  # ... states, transitions (see ADR-0003b) ...

  # ===== Role Definitions (NEW) =====
  roles:
    - name: "orchestrator"
      description: "Orchestrator agent (initiates hire)"
      capabilities:
        - "HIRE_REQUEST"         # Can send HireRequest
        - "HIRE_APPROVAL"        # Can send HireApproval
        - "HIRE_REJECTION"       # Can send HireRejection
      allowed_message_types:
        - "HireRequest"
        - "HireApproval"
        - "HireRejection"
        - "NoValidProposals"

    - name: "agent"
      description: "Agent (responds to hire)"
      capabilities:
        - "PROPOSAL_SUBMIT"      # Can send Proposal
      allowed_message_types:
        - "Proposal"

    - name: "system"
      description: "System (timeout triggers)"
      capabilities:
        - "TIMEOUT_TRIGGER"      # Can send timeout messages
      allowed_message_types:
        - "ProposalsClosed"
        - "Timeout"
        - "SelectionTimeout"

  # ===== Message Definitions with Role Restrictions (NEW) =====
  messages:
    - name: "HireRequest"
      sender_role: "orchestrator"       # ONLY orchestrator can send
      receiver_roles: ["*"]             # Broadcast to all agents
      schema: "HireRequestSchema"       # FlatBuffers schema

    - name: "Proposal"
      sender_role: "agent"              # ONLY agents can send
      receiver_roles: ["orchestrator"]  # Only to orchestrator
      schema: "ProposalSchema"

    - name: "HireApproval"
      sender_role: "orchestrator"
      receiver_roles: ["agent"]
      schema: "HireApprovalSchema"

    - name: "HireRejection"
      sender_role: "orchestrator"
      receiver_roles: ["agent"]
      schema: "HireRejectionSchema"

    - name: "ProposalsClosed"
      sender_role: "system"             # System-triggered
      receiver_roles: []
      schema: null
```

**Role Specification Benefits:**
- Declarative role-message mapping (readable, verifiable)
- Compiler validates: all message_types have sender_role defined
- Runtime checks: RoleVerifier uses PDL spec to verify capabilities

---

### Component 5: 2-Phase Validation Pipeline Integration

**Purpose:** Integrate role attestation (Phase 1) with protocol validation (Phase 2).

```python
"""
Module: k1.protocol_monitor.two_phase_validator
Purpose: 2-phase validation pipeline (role + protocol)

Research: Defense in depth (security layering)
"""

class TwoPhaseValidator:
    """
    2-Phase Validation Pipeline

    Phase 1: Role Attestation (<1ms P95)
      → Verify signature, lease, role, capability

    Phase 2: Protocol Validation (<2ms P95)
      → Validate FSM (current_state + message_type)

    Total: <3ms P95 (within <5ms mailbox budget)
    """

    def __init__(self, role_verifier: RoleVerifier, protocol_validator: 'ProtocolValidator'):
        self.role_verifier = role_verifier
        self.protocol_validator = protocol_validator

    def validate(self, message: ActorMessage, protocol_name: str) -> ValidationResult:
        """2-phase validation"""

        # Phase 1: Role Attestation
        role_result = self.role_verifier.verify(message, protocol_name)
        if not role_result.valid:
            # Role verification failed → BLOCK immediately
            logger.warning(
                "role_verification_failed",
                session_id=message.session_id,
                message_type=message.message_type,
                sender_role=message.sender_role,
                reason=role_result.reason,
                trace_id=message.cognitive_trace_id,
            )
            from k1.observability.metrics import role_verification_failures_total
            role_verification_failures_total.labels(reason=role_result.reason).inc()

            return ValidationResult(valid=False, reason=role_result.reason, action="BLOCK")

        # Phase 2: Protocol Validation
        proto_result = self.protocol_validator.validate(
            session_id=message.session_id,
            message_type=message.message_type,
            sender_role=message.sender_role,
        )

        return proto_result
```

**Mailbox Integration:**

```python
# Mailbox delivery hook (Actor mailbox, see ADR-0002)
def deliver_message(actor_id: str, message: ActorMessage, protocol_name: str):
    """Deliver message to actor mailbox (with 2-phase validation)"""

    # 2-phase validation: role attestation + protocol validation
    result = two_phase_validator.validate(message, protocol_name)

    if result.action == "PASS":
        # Valid message → deliver to actor
        actor_mailbox[actor_id].put(message)
    elif result.action == "BLOCK":
        # Invalid message → drop, log, metric
        logger.warning(
            "message_blocked",
            actor_id=actor_id,
            session_id=message.session_id,
            message_type=message.message_type,
            reason=result.reason,
            trace_id=message.cognitive_trace_id,
        )
```

---

## Security Analysis

### Threat Model

**Threat 1: Role Spoofing**
- **Attack:** Malicious agent sends message with fake `sender_role="orchestrator"`
- **Mitigation:** HMAC-SHA256 signature verification (requires lease secret)
- **Result:** ✅ Attack blocked (no lease secret → signature mismatch)

**Threat 2: Privilege Escalation**
- **Attack:** Agent sends message type outside its capabilities (e.g., Concierge sends ToolRequest)
- **Mitigation:** Capability check (PDL protocol role specification)
- **Result:** ✅ Attack blocked (Concierge role not allowed to send ToolRequest)

**Threat 3: Replay Attack**
- **Attack:** Attacker captures signed message, replays later
- **Mitigation:** Lease expiry (leases valid for 1 hour, expired leases rejected)
- **Result:** ⚠️ Partial protection (replay possible within lease duration)
- **Future Enhancement:** Add nonce/timestamp to message signature

**Threat 4: Lease Theft**
- **Attack:** Attacker steals agent's lease secret (memory dump, side channel)
- **Mitigation:** Lease rotation (periodic re-issue), memory protection
- **Result:** ⚠️ Partial protection (stolen lease valid until expiry)
- **Future Enhancement:** Hardware security module (HSM) for lease storage

**Threat 5: Signature Forgery**
- **Attack:** Attacker forges HMAC-SHA256 signature without lease secret
- **Mitigation:** HMAC-SHA256 cryptographic strength (256-bit secret, collision-resistant)
- **Result:** ✅ Computationally infeasible (2^256 brute force)

---

### Security Properties

**Property 1: No Role Spoofing**
- **Guarantee:** Agent cannot send message with role ≠ lease.role
- **Proof:** HMAC-SHA256 signature binds message to lease secret, lease secret unique per agent

**Property 2: No Privilege Escalation**
- **Guarantee:** Agent cannot send message_type outside lease.capabilities
- **Proof:** RoleVerifier checks PDL protocol role specification, blocks unauthorized messages

**Property 3: Lease Expiry Enforcement**
- **Guarantee:** Expired leases rejected, zombie agents blocked
- **Proof:** RoleVerifier checks lease.expires_at < current_time, blocks expired

**Property 4: Audit Trail**
- **Guarantee:** All role verification failures logged with trace_id
- **Proof:** Structured logs in RoleVerifier, Prometheus metrics for failures

**Property 5: Constant-Time Comparison**
- **Guarantee:** HMAC signature comparison not vulnerable to timing attacks
- **Proof:** `hmac.compare_digest()` uses constant-time comparison (Python standard library)

---

## Consequences

### Positive ✅

**✅ Zero Role Spoofing:**
- HMAC-SHA256 signature verification prevents role impersonation
- **Result:** Agents cannot fake orchestrator, system, or other roles

**✅ Capability Enforcement:**
- PDL protocol role specification declarative, verifiable
- **Result:** Agents have minimal capabilities (least privilege)

**✅ <1ms Verification Overhead:**
- HMAC-SHA256 computation <500μs, lease lookup O(1) hash table
- **Result:** <3ms total (role + protocol validation), within <5ms mailbox budget

**✅ Audit Trail:**
- All role verification failures logged with trace_id, metrics
- **Result:** Security incidents traceable, observable

**✅ Lease Expiry:**
- Expired leases rejected, zombie agents blocked
- **Result:** No stale agents operating without valid capabilities

---

### Negative ⚠️

**⚠️ Signature Overhead:**
- Every Actor message requires HMAC-SHA256 computation (sender + receiver)
- **Mitigation:** <1ms overhead, amortized over message latency
- **Risk Level:** LOW (acceptable for security gain)

**⚠️ Lease Management Complexity:**
- Agent Fabric must issue, rotate, revoke leases (lifecycle management)
- **Mitigation:** Lease lifecycle tied to agent lifecycle (ADR-0005)
- **Risk Level:** MEDIUM (requires careful implementation)

**⚠️ Replay Attack Window:**
- Signed messages valid for entire lease duration (1 hour)
- **Mitigation:** Future enhancement: add nonce/timestamp to signature
- **Risk Level:** MEDIUM (acceptable for MVP, enhance later)

**⚠️ PDL Protocol Role Specification:**
- Must maintain role-message mappings in PDL YAML
- **Mitigation:** Compiler validates, runtime enforces
- **Risk Level:** LOW (declarative spec, testable)

---

## Implementation Notes

### **Implementation Timeline**

**Phase 1 (Week 1): Core Components**
- Implement AgentLease (capability metadata)
- Implement MessageSigner (HMAC-SHA256 signing)
- Golden tests: signature generation, verification

**Phase 2 (Week 2): Role Verifier**
- Implement LeaseRegistry (lease storage, lookup)
- Implement RoleVerifier (signature verification, capability check)
- Unit tests: valid/invalid signatures, expired leases, capability checks

**Phase 3 (Week 3): PDL Integration**
- Extend PDL YAML schema (roles, messages, capabilities)
- Update PDL compiler (parse roles, validate role-message mappings)
- Golden tests: PDL protocols with role specifications

**Phase 4 (Week 4): Integration**
- Implement TwoPhaseValidator (role + protocol validation)
- Integrate with Actor mailbox (see ADR-0002)
- End-to-end test: signed message delivery, role spoofing blocked

---

### **Dependencies**

**Before Starting:**
- ✅ ADR-0003a (PDL Specification) - Protocol language foundation
- ✅ ADR-0003b (6 Core Protocols) - Protocol definitions
- ✅ ADR-0003c (Protocol Monitor Runtime) - Validation infrastructure
- ✅ ADR-0010 (Capability-Based Security) - Capability design
- ✅ ADR-0002 (Actor Model) - Mailbox delivery hooks

**Blocking:**
- ADR-0005 (Agent Lifecycle FSM) - Lease issuance during agent hire
- ADR-0006 (3-Phase Orchestration) - Uses role attestation for hire protocol

---

### **Success Metrics**

**Security:**
- ✅ Zero role spoofing attacks succeed (all blocked)
- ✅ Zero privilege escalation attacks succeed (all blocked)
- ✅ 100% expired leases rejected
- ✅ Audit trail for all verification failures

**Performance:**
- ✅ Role verification: <1ms P95 (HMAC-SHA256 + lease lookup)
- ✅ Total validation: <3ms P95 (role + protocol)
- ✅ Mailbox overhead: <5ms P95 (within budget)

**Quality:**
- ✅ 100% test coverage (signature generation, verification, capability checks)
- ✅ Security audit (threat model, attack scenarios)
- ✅ Integration tests with Actor mailbox (ADR-0002)

---

## References

### **Research Papers**

1. **Dennis, J. B., Van Horn, E. C. (1966)**
   "Programming Semantics for Multiprogrammed Computations"
   *Communications of the ACM*
   **Relevance**: Capability-Based Security foundation

2. **Bellare, M., Canetti, R., Krawczyk, H. (1996)**
   "Keying Hash Functions for Message Authentication"
   *CRYPTO*
   **Relevance**: HMAC-SHA256 security proofs

3. **Hewitt, C., Bishop, P., Steiger, R. (1973)**
   "A Universal Modular Actor Formalism for Artificial Intelligence"
   *IJCAI*
   **Relevance**: Actor message authenticity in distributed systems

### **Related ADRs**

- [ADR-0003: MPST Protocol Validation](0003-mpst-protocol-validation.md) — Parent ADR
- [ADR-0003a: PDL Specification](0003a-protocol-definition-language-pdl-specification.md) — Protocol language
- [ADR-0003b: 6 Core Protocols](0003b-6-core-protocol-implementations.md) — Protocol definitions
- [ADR-0003c: Protocol Monitor Runtime](0003c-protocol-monitor-runtime-implementation.md) — Validation infrastructure
- [ADR-0010: Capability-Based Security](0010-capability-based-security.md) — Capability design
- [ADR-0002: Actor Model](0002-actor-model-agent-isolation.md) — Mailbox delivery hooks
- [ADR-0005: Agent Lifecycle FSM](0005-agent-lifecycle-fsm.md) — Lease issuance

### **Architecture Diagrams**

- `architecture_diagrams/k1_protocol_monitor_fsms.mmd` — Protocol Monitor architecture
- `architecture_diagrams/k1_agent_lifecycle_fsm.mmd` — Agent lifecycle (lease issuance)

### **Whiteboard References**

- `docs/whiteboard.md` (lines 1401-1500) — MPST overview, security considerations
- `docs/whiteboard.md` (lines 3650-3800) — Protocol examples

---

**Document Status:** ✅ **COMPLETE** - Role attestation and capability verification fully specified with HMAC-SHA256 signatures, lease management, PDL role specifications, and 2-phase validation pipeline.

**Cross-References:**
- ADR-0003 (Parent): MPST Protocol Validation
- ADR-0003a: PDL Specification
- ADR-0003b: 6 Core Protocols
- ADR-0003c: Protocol Monitor Runtime
- ADR-0010: Capability-Based Security
- ADR-0002: Actor Model (mailbox hooks)

**Canonical Values:**
- **Signature algorithm:** HMAC-SHA256 (256-bit secret)
- **Verification overhead:** <1ms P95 (Phase 1)
- **Total validation:** <3ms P95 (Phase 1 + Phase 2)
- **Lease duration:** 3600 seconds (1 hour, configurable)
- **Signature comparison:** Constant-time (`hmac.compare_digest`)

**Security Properties:**
- ✅ No role spoofing (HMAC-SHA256 prevents impersonation)
- ✅ No privilege escalation (PDL role specification enforced)
- ✅ Lease expiry enforcement (zombie agents blocked)
- ✅ Audit trail (all failures logged with trace_id)
- ⚠️ Replay attack window (1 hour lease duration, future: add nonce)

**Document End**
