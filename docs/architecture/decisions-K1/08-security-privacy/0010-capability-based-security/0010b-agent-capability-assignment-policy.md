---
adr_number: 0010b
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l2_orchestration.capability.policy_engine
- k1.l3_execution.flow_engine.capability_assigner
- k1.l4_runtime.session_state.agent_profiles
- k1.l5_infrastructure.security.capability_policy
- k1.l5_infrastructure.audit.capability_audit
affected_tests:
- tests/k1/l2_orchestration/test_capability_policy_engine.py
- tests/k1/l3_execution/test_capability_assigner.py
- tests/k1/l4_runtime/test_agent_profiles.py
- tests/k1/l5_infrastructure/test_capability_policy.py
- tests/integration/test_agent_capability_assignment.py
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- modularity
- observability
- performance
- privacy
- reliability
- security
- usability
date_created: '2025-11-03'
date_updated: '2025-10-12'
implementation_date: '2025-11-03'
implementation_phase: Phase 1
implementation_status: COMPLETED
propagation:
  affected_adrs:
  - ADR-0002
  - ADR-0005
  - ADR-0007c
  - ADR-0010a
  - ADR-0010b
  - ADR-0010c
  - ADR-0010d
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  affected_tests: []
  triggers:
  - Modifying system architecture
  - Performance requirement changes
related_adrs:
- ADR-0002
- ADR-0005
- ADR-0007c
- ADR-0010a
- ADR-0010b
- ADR-0010c
- ADR-0010d
related_contracts:
- k1/contracts/flatbuffers/layer2_orchestration/capability_policy.fbs
- k1/contracts/flatbuffers/layer3_execution/agent_profile.fbs
- k1/contracts/flatbuffers/layer4_runtime/assignment_rules.fbs
- k1/contracts/flatbuffers/layer5_infrastructure/policy_audit.fbs
related_diagrams:
- k1_agent_capability_assignment
- k1_capability_policy_engine
- k1_agent_trust_levels
- k1_capability_assignment_flow
research_citations:
- Role-Based Access Control (RBAC) (Ferraiolo & Kuhn 1992) - Standard access control
  model
- The Protection of Information in Computer Systems (Saltzer & Schroeder 1975) - Principle
  of least privilege
- Trust Management Systems (Blaze et al. 1996) - Decentralized trust management
- Computer Security: Art and Science (Bishop 2002) - Access control models and policies
- Security Engineering (Anderson 2008) - Least privilege in practice
- Access Control and Trust Management (Gavrila & Barkley 1998) - Policy-based access
  control
status: ACCEPTED
superseded_by: []
supersedes: []
title: Agent Capability Assignment Policy
---

# ADR-0010b: Agent Capability Assignment Policy

**Status:** Accepted
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0010: Capability-Based Security](0010-capability-based-security.md)

---

## Context

K1 agents have different roles, trust levels, and operational requirements:
- **Planning agents:** Generate plans using LLMs, query memory, call search tools
- **Tool agents:** Execute specific tools (book_hotel, charge_payment, send_email)
- **Memory agents:** Manage session state, read/write memory sections, access K0 WAL
- **Supervisor agents:** Oversee all agents, manage capabilities, handle escalations

**Problem Statement:**
Without a systematic capability assignment policy, we face:
1. **Over-privileged agents:** Planning agent can call charge_payment (security risk)
2. **Under-privileged agents:** Tool agent cannot write to scoreboard (operational failure)
3. **Inconsistent assignment:** Manual capability grants lead to errors and security gaps
4. **No escalation path:** Agent cannot request higher privileges when needed (task failure)

**Research Foundation:**

- **Principle of Least Privilege (Saltzer & Schroeder 1975):**
  Every module should have only the minimum privileges needed for its legitimate purpose.

- **Role-Based Access Control (Ferraiolo & Kuhn 1992):**
  Access decisions based on roles, simplifying administration and ensuring consistency.

- **Trust Management (Blaze et al. 1996):**
  Security policies as trust management, with explicit trust levels and delegation chains.

**Decision Criteria:**
We need a capability assignment policy that is:
- **Role-based:** Capabilities assigned based on agent role (planning, tool, memory, supervisor)
- **Trust-aware:** Higher trust levels enable more capabilities and auto-approved escalations
- **Escalation-friendly:** Agents can request additional capabilities with supervisor approval
- **Auditable:** All capability grants/denials logged for security review

---

## Decision

We will implement **role-based capability assignment with trust-level escalation** using the following policy:

---

### 1. Agent Roles & Default Capabilities

**Role:** Planning Agent
**Purpose:** Generate execution plans using LLM, query memory, call information-gathering tools

**Default Capabilities:**
```yaml
planning_agent:
  trust_level: 1                        # Low trust (new agent)
  default_capabilities:
    - type: LLM
      resource_id: gemma-2b             # Local LLM (low cost)
      permissions: [execute]
      constraints:
        max_invocations: 100
        expires_at: session_end
      justification: "Planning requires LLM for plan generation"

    - type: TOOL
      resource_id: search_web           # Information gathering
      permissions: [execute]
      constraints:
        max_invocations: 50
        expires_at: session_end
      justification: "Planning may require web search for context"

    - type: MEMORY
      resource_id: beliefs              # Read conversation context
      permissions: [read]
      constraints:
        expires_at: session_end
      justification: "Planning requires context from beliefs"
```

**Rationale:**
- **LLM:** gemma-2b (local) is sufficient for most planning tasks, low cost
- **Tool:** search_web is information-only (no side effects), low risk
- **Memory:** beliefs read-only (no corruption risk), necessary for context

---

**Role:** Tool Agent
**Purpose:** Execute specific tool assigned by orchestrator

**Default Capabilities:**
```yaml
tool_agent:
  trust_level: 1                        # Low trust (new agent)
  default_capabilities:
    - type: TOOL
      resource_id: "${assigned_tool}"   # Dynamic (assigned on hire)
      permissions: [execute]
      constraints:
        max_invocations: 10
        expires_at: session_end
      justification: "Tool agent executes specific tool assigned by orchestrator"

    - type: MEMORY
      resource_id: scoreboard           # Write tool results
      permissions: [write]
      constraints:
        expires_at: session_end
      justification: "Tool agent must write results to scoreboard"
```

**Rationale:**
- **Tool:** Only the assigned tool (e.g., book_hotel), not wildcards (prevents privilege escalation)
- **Memory:** scoreboard write-only (results), no read access to other sections

---

**Role:** Memory Agent
**Purpose:** Manage session state, coordinate memory operations, access K0 WAL

**Default Capabilities:**
```yaml
memory_agent:
  trust_level: 2                        # Medium trust (critical role)
  default_capabilities:
    - type: MEMORY
      resource_id: beliefs
      permissions: [read]
      constraints:
        expires_at: session_end
      justification: "Memory agent reads beliefs for context management"

    - type: MEMORY
      resource_id: scoreboard
      permissions: [read]
      constraints:
        expires_at: session_end
      justification: "Memory agent reads scoreboard for result aggregation"

    - type: K0_WAL
      resource_id: read_only
      permissions: [read]
      constraints:
        expires_at: session_end
      justification: "Memory agent reads K0 WAL for state reconstruction"
```

**Rationale:**
- **Memory:** Read-only access to beliefs and scoreboard (no corruption risk)
- **K0 WAL:** Read-only (state reconstruction), no write access by default

---

**Role:** Supervisor Agent
**Purpose:** Oversee all agents, manage capabilities, coordinate orchestration

**Default Capabilities:**
```yaml
supervisor_agent:
  trust_level: 4                        # Admin (full trust)
  default_capabilities:
    - type: TOOL
      resource_id: "*"                  # All tools
      permissions: [execute, admin]
      constraints:
        expires_at: session_end
      justification: "Supervisor requires access to all tools for agent coordination"

    - type: MEMORY
      resource_id: "*"                  # All memory sections
      permissions: [read, write, admin]
      constraints:
        expires_at: session_end
      justification: "Supervisor manages session state"

    - type: LLM
      resource_id: "*"                  # All LLMs
      permissions: [execute, admin]
      constraints:
        budget_usd: 5.0                 # Higher budget for supervision
        expires_at: session_end
      justification: "Supervisor may need powerful LLMs for complex decisions"

    - type: K0_WAL
      resource_id: "*"
      permissions: [read, write, admin]
      constraints:
        expires_at: session_end
      justification: "Supervisor manages event persistence"
```

**Rationale:**
- **Wildcard access:** Supervisor needs full visibility and control for coordination
- **Higher budget:** Supervisor may invoke expensive LLMs for critical decisions ($5 vs $1 for agents)

---

### 2. Trust Level Classification

**Trust Levels (0-4):**

**Level 0: Untrusted**
- **Definition:** Newly hired agent, no execution history
- **Characteristics:**
  - 0 successful tasks completed
  - No prior interactions
  - Default capabilities only
  - All escalations require supervisor approval
- **Restrictions:**
  - Cannot request high-risk tools (charge_payment, delete_file)
  - Cannot request expensive LLMs (gpt-4o)
  - Cannot request write access to persona section

**Level 1: Low Trust**
- **Definition:** Agent with minimal execution history
- **Characteristics:**
  - 1-9 successful tasks completed
  - No failed tasks or policy violations
  - Default capabilities + limited escalation
  - Escalations require supervisor approval
- **Escalation Allowed:**
  - Information-gathering tools (search_web, fetch_url)
  - Cheap LLMs (gpt-4o-mini, budget_usd <= 0.50)
  - Read access to memory sections (beliefs, scoreboard)

**Level 2: Medium Trust**
- **Definition:** Agent with moderate execution history and good track record
- **Characteristics:**
  - 10-49 successful tasks completed
  - <5% failure rate
  - Auto-approved escalation for low-risk capabilities
  - Supervisor approval for medium/high-risk
- **Escalation Allowed (Auto-Approved):**
  - Low-risk tools (send_email, create_calendar_event)
  - Medium-cost LLMs (gpt-4o-mini, budget_usd <= 1.0)
  - Read access to persona section (privacy_band=GREEN)
- **Escalation Allowed (Supervisor Approval):**
  - Medium-risk tools (book_hotel, charge_payment <= $100)
  - Expensive LLMs (gpt-4o, budget_usd <= 1.0)
  - Write access to memory sections (scoreboard, control)

**Level 3: High Trust**
- **Definition:** Agent with extensive execution history and excellent track record
- **Characteristics:**
  - 50-199 successful tasks completed
  - <2% failure rate
  - Auto-approved escalation for low/medium-risk capabilities
  - Supervisor approval for high-risk only
- **Escalation Allowed (Auto-Approved):**
  - Medium-risk tools (book_hotel, charge_payment <= $100)
  - Expensive LLMs (gpt-4o, budget_usd <= 2.0)
  - Read access to persona section (privacy_band=AMBER, with arbiter approval)
  - Write access to memory sections (scoreboard, control)
- **Escalation Allowed (Supervisor Approval):**
  - High-risk tools (delete_file, charge_payment > $100)
  - Write access to persona section (privacy_band=AMBER)

**Level 4: Admin**
- **Definition:** Supervisor agent with full privileges
- **Characteristics:**
  - Reserved for supervisor agent only
  - No task count requirement
  - No escalation needed (full access)
- **Escalation:** N/A (already has all capabilities)

**Trust Level Progression:**
- **Promotion triggers:**
  - Level 0 → Level 1: After 1 successful task
  - Level 1 → Level 2: After 10 successful tasks
  - Level 2 → Level 3: After 50 successful tasks
  - Level 3 → Level 4: Never (admin reserved for supervisor)
- **Demotion triggers:**
  - Any level → Level 0: After agent crash, policy violation, security incident
  - Any level → Level 0: If failure rate exceeds 10%

---

### 3. Escalation Capabilities & Approval Flow

**Escalation Workflow:**

**Step 1: Agent Requests Escalation**
```python
# Agent sends REQUEST_CAPABILITY message to supervisor
class CapabilityRequestMessage:
    agent_id: str
    resource_type: str                  # TOOL|MEMORY|LLM|K0_WAL
    resource_id: str
    permissions: list[str]
    constraints: dict
    justification: str                  # Why capability is needed
    context: dict                       # Task context (e.g., user request)
```

**Example: Planning agent requests gpt-4o-mini for complex task**
```python
request = CapabilityRequestMessage(
    agent_id="agent_planning_123",
    resource_type="LLM",
    resource_id="gpt-4o-mini",
    permissions=["execute"],
    constraints={"budget_usd": 0.50, "max_invocations": 5},
    justification="Local LLM failed to generate valid plan after 3 attempts",
    context={
        "task": "Book hotel in Tokyo for 3 nights",
        "local_llm_attempts": 3,
        "failure_reason": "Invalid JSON output"
    }
)
```

---

**Step 2: Supervisor Evaluates Request**

**Evaluation Logic:**
```python
class CapabilitySupervisor:
    async def evaluate_escalation(
        self,
        request: CapabilityRequestMessage
    ) -> CapabilityEvaluation:
        """
        Evaluate capability escalation request.
        Returns CapabilityEvaluation (APPROVED|DENIED|ARBITER_REVIEW).
        """

        # Step 1: Get agent trust level
        agent = self.agent_registry.get(request.agent_id)
        trust_level = self._calculate_trust_level(agent)

        # Step 2: Get escalation policy for agent role + trust level
        policy = self.policies.get_escalation_policy(
            role=agent.role,
            trust_level=trust_level
        )

        # Step 3: Check if capability in allowed escalations
        allowed = policy.is_escalation_allowed(
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            permissions=request.permissions
        )

        if not allowed:
            return CapabilityEvaluation(
                status="DENIED",
                reason=f"Escalation not allowed for trust level {trust_level}"
            )

        # Step 4: Check approval criteria
        criteria = policy.get_approval_criteria(
            resource_type=request.resource_type,
            resource_id=request.resource_id
        )

        # Auto-approve if criteria met
        if criteria.approval_required == False:
            return CapabilityEvaluation(
                status="APPROVED",
                reason="Auto-approved (trust level + criteria met)"
            )

        # Step 5: Check specific approval criteria
        if criteria.requires_user_confirmation:
            # Wait for user confirmation (not yet implemented)
            return CapabilityEvaluation(
                status="DENIED",
                reason="User confirmation required (not yet implemented)"
            )

        if criteria.requires_arbiter_approval:
            # Escalate to arbiter (for AMBER/RED privacy bands)
            return CapabilityEvaluation(
                status="ARBITER_REVIEW",
                reason="Arbiter approval required for privacy-sensitive operation"
            )

        # Step 6: Check budget constraints
        if "budget_usd" in request.constraints:
            if request.constraints["budget_usd"] > criteria.max_budget_usd:
                return CapabilityEvaluation(
                    status="DENIED",
                    reason=f"Budget exceeds max ({criteria.max_budget_usd} USD)"
                )

        # Step 7: Supervisor approves
        return CapabilityEvaluation(
            status="APPROVED",
            reason="Supervisor approved escalation"
        )
```

---

**Step 3: Grant or Deny Capability**

**If Approved:**
```python
if evaluation.status == "APPROVED":
    # Grant capability
    token = await self.capability_factory.create_capability(
        agent_id=request.agent_id,
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        permissions=request.permissions,
        constraints=request.constraints,
        issued_by="supervisor"
    )

    # Send to agent
    await self.send_message(
        agent_id=request.agent_id,
        message=CapabilityGrantedMessage(
            token=token,
            expires_at=constraints.get("expires_at", "session_end")
        )
    )

    # Log grant
    logger.info(
        "capability_escalation_granted",
        agent_id=request.agent_id,
        resource=f"{request.resource_type}:{request.resource_id}",
        trust_level=trust_level,
        justification=request.justification
    )
```

**If Denied:**
```python
if evaluation.status == "DENIED":
    # Send denial to agent
    await self.send_message(
        agent_id=request.agent_id,
        message=CapabilityDeniedMessage(
            resource=f"{request.resource_type}:{request.resource_id}",
            reason=evaluation.reason
        )
    )

    # Log denial
    logger.warning(
        "capability_escalation_denied",
        agent_id=request.agent_id,
        resource=f"{request.resource_type}:{request.resource_id}",
        reason=evaluation.reason
    )
```

**If Arbiter Review Required:**
```python
if evaluation.status == "ARBITER_REVIEW":
    # Escalate to arbiter (Planner Arbiter, ADR-0007c)
    arbiter_decision = await self.arbiter.review_capability_request(
        request=request,
        timeout=timedelta(seconds=5)
    )

    if arbiter_decision.approved:
        # Grant with arbiter approval
        token = await self.capability_factory.create_capability(...)
        await self.send_message(...)
    else:
        # Deny with arbiter reason
        await self.send_message(
            message=CapabilityDeniedMessage(
                reason=f"Arbiter denied: {arbiter_decision.reason}"
            )
        )
```

---

### 4. Escalation Policies by Role

**Planning Agent Escalations:**
```yaml
planning_agent:
  trust_level_1:                        # Low trust
    escalation_capabilities:
      - type: LLM
        resource_id: gpt-4o-mini
        permissions: [execute]
        approval_required: true
        approval_criteria:
          task_complexity: high         # Planning task complexity >= high
          local_llm_failed: true        # gemma-2b failed after 3 attempts
        constraints:
          budget_usd: 0.50
          max_invocations: 5
          expires_at: session_end

  trust_level_2:                        # Medium trust
    escalation_capabilities:
      - type: LLM
        resource_id: gpt-4o-mini
        permissions: [execute]
        approval_required: false        # Auto-approved for medium trust
        constraints:
          budget_usd: 1.0
          max_invocations: 10
          expires_at: session_end

      - type: LLM
        resource_id: gpt-4o
        permissions: [execute]
        approval_required: true         # Still requires supervisor approval
        approval_criteria:
          task_complexity: critical
          gpt_4o_mini_failed: true
        constraints:
          budget_usd: 1.0
          max_invocations: 3
          expires_at: session_end

  trust_level_3:                        # High trust
    escalation_capabilities:
      - type: LLM
        resource_id: gpt-4o
        permissions: [execute]
        approval_required: false        # Auto-approved for high trust
        constraints:
          budget_usd: 2.0
          max_invocations: 10
          expires_at: session_end
```

---

**Tool Agent Escalations:**
```yaml
tool_agent:
  trust_level_1:                        # Low trust
    escalation_capabilities:
      - type: TOOL
        resource_id: charge_payment
        permissions: [execute]
        approval_required: true
        approval_criteria:
          user_confirmation: true       # User must confirm payment
          amount_usd: "<100"            # Max $100 for low trust
        constraints:
          max_invocations: 1
          expires_at: "1h"              # Expire after 1 hour

  trust_level_2:                        # Medium trust
    escalation_capabilities:
      - type: TOOL
        resource_id: charge_payment
        permissions: [execute]
        approval_required: true         # Still requires user confirmation
        approval_criteria:
          user_confirmation: true
          amount_usd: "<500"            # Max $500 for medium trust
        constraints:
          max_invocations: 3
          expires_at: "1h"

  trust_level_3:                        # High trust
    escalation_capabilities:
      - type: TOOL
        resource_id: charge_payment
        permissions: [execute]
        approval_required: true         # Always requires user confirmation
        approval_criteria:
          user_confirmation: true
          amount_usd: "<1000"           # Max $1000 for high trust
        constraints:
          max_invocations: 5
          expires_at: "1h"
```

---

**Memory Agent Escalations:**
```yaml
memory_agent:
  trust_level_2:                        # Medium trust (default for memory agent)
    escalation_capabilities:
      - type: MEMORY
        resource_id: persona
        permissions: [read]
        approval_required: true
        approval_criteria:
          privacy_band: AMBER           # AMBER band requires arbiter
          arbiter_approved: true
        constraints:
          max_invocations: 5
          expires_at: session_end

      - type: K0_WAL
        resource_id: write
        permissions: [write]
        approval_required: true         # Write access requires supervisor
        approval_criteria:
          supervisor_approved: true
        constraints:
          max_invocations: 100
          expires_at: session_end

  trust_level_3:                        # High trust
    escalation_capabilities:
      - type: MEMORY
        resource_id: persona
        permissions: [write]
        approval_required: true         # Write to persona always requires arbiter
        approval_criteria:
          privacy_band: AMBER
          arbiter_approved: true
          supervisor_approved: true
        constraints:
          max_invocations: 10
          expires_at: session_end
```

---

### 5. Capability Inheritance

**Concept:** When an agent spawns a child agent, the child inherits a subset of parent capabilities with reduced constraints.

**Inheritance Rules:**

**Rule 1: Child inherits parent capabilities**
- Child gets same resource_type and resource_id
- Child permissions <= parent permissions (e.g., parent has [read, write], child gets [read])
- Child constraints stricter than parent (e.g., parent budget_usd=1.0, child budget_usd=0.5)

**Rule 2: Budget inheritance**
- Child budget_usd = parent_budget_usd * 0.5 (50% of parent)
- Prevents budget exhaustion via agent spawning

**Rule 3: Invocation inheritance**
- Child max_invocations = parent_max_invocations * 0.5 (50% of parent)
- Prevents runaway loops via agent spawning

**Rule 4: Expiration inheritance**
- Child expires_at = min(parent_expires_at, current_time + 10min)
- Child cannot outlive parent

**Example:**
```python
# Parent: Planning agent with gpt-4o-mini capability
parent_capability = {
    "resource_type": "LLM",
    "resource_id": "gpt-4o-mini",
    "permissions": ["execute"],
    "constraints": {
        "budget_usd": 1.0,
        "max_invocations": 10,
        "expires_at": "2025-10-12T15:00:00Z"
    }
}

# Child: Sub-planning agent (for complex subtask)
child_capability = {
    "resource_type": "LLM",
    "resource_id": "gpt-4o-mini",
    "permissions": ["execute"],
    "constraints": {
        "budget_usd": 0.5,              # 50% of parent
        "max_invocations": 5,           # 50% of parent
        "expires_at": "2025-10-12T14:10:00Z"  # min(parent, current+10min)
    }
}
```

**Enforcement:**
```python
def create_child_capability(
    parent_capability: CapabilityToken,
    child_agent_id: str
) -> CapabilityToken:
    """Create child capability with reduced constraints."""

    parent_claims = jwt.decode(parent_capability, options={"verify_signature": False})

    # Reduce constraints
    child_constraints = {}

    if "budget_usd" in parent_claims["constraints"]:
        child_constraints["budget_usd"] = parent_claims["constraints"]["budget_usd"] * 0.5

    if "max_invocations" in parent_claims["constraints"]:
        child_constraints["max_invocations"] = int(parent_claims["constraints"]["max_invocations"] * 0.5)

    if "expires_at" in parent_claims["constraints"]:
        parent_expires = datetime.fromisoformat(parent_claims["constraints"]["expires_at"])
        child_expires = min(parent_expires, datetime.utcnow() + timedelta(minutes=10))
        child_constraints["expires_at"] = child_expires.isoformat()

    # Create child capability
    return self.factory.create_capability(
        agent_id=child_agent_id,
        resource_type=parent_claims["resource_type"],
        resource_id=parent_claims["resource_id"],
        permissions=parent_claims["permissions"],
        constraints=child_constraints,
        issued_by="parent_agent"
    )
```

---

### 6. Capability Revocation Triggers

**Revocation triggers automatically revoke all agent capabilities in specific scenarios:**

#### 6.1 Agent Crash
- **Trigger:** Agent raises unhandled exception, enters TERMINATED state
- **Action:** Revoke all agent capabilities immediately
- **Reason:** Crashed agent may be compromised or malfunctioning

```python
async def on_agent_crash(self, agent: Agent):
    """Revoke all capabilities on agent crash."""
    await self.capability_supervisor.revoke_all_agent_capabilities(
        agent_id=agent.id,
        reason="Agent crashed"
    )
```

#### 6.2 Policy Violation
- **Trigger:** Agent violates K1 policy (invalid tool call, memory corruption attempt)
- **Action:** Revoke all agent capabilities immediately, demote trust level to 0
- **Reason:** Policy violation indicates malicious or buggy agent

```python
async def on_policy_violation(self, agent: Agent, violation: str):
    """Revoke all capabilities on policy violation."""
    await self.capability_supervisor.revoke_all_agent_capabilities(
        agent_id=agent.id,
        reason=f"Policy violation: {violation}"
    )

    # Demote trust level
    agent.trust_level = 0
```

#### 6.3 Session End
- **Trigger:** Session terminates (user disconnects, timeout)
- **Action:** Revoke all session capabilities
- **Reason:** Session-bound capabilities no longer valid

```python
async def on_session_end(self, session_id: str):
    """Revoke all session capabilities on session end."""
    agents = self.agent_registry.get_by_session(session_id)

    for agent in agents:
        await self.capability_supervisor.revoke_all_agent_capabilities(
            agent_id=agent.id,
            reason="Session ended"
        )
```

#### 6.4 Timeout
- **Trigger:** Capability expires (expires_at reached)
- **Action:** Capability auto-expires (no explicit revocation needed)
- **Reason:** Time-based expiration limits blast radius

#### 6.5 Budget Exhausted
- **Trigger:** Agent consumes budget_usd fully
- **Action:** Revoke LLM capability automatically
- **Reason:** Prevent cost overrun

```python
async def on_budget_exhausted(self, cap_id: str, agent_id: str):
    """Revoke LLM capability on budget exhaustion."""
    await self.capability_supervisor.revoke_capability(
        cap_id=cap_id,
        reason="Budget exhausted"
    )

    logger.warning(
        "llm_budget_exhausted",
        cap_id=cap_id,
        agent_id=agent_id
    )
```

#### 6.6 User Request
- **Trigger:** User explicitly requests capability revocation
- **Action:** Revoke specified capabilities
- **Reason:** User privacy concern, manual intervention

```python
async def on_user_revoke_request(self, user_id: str, agent_id: str, resource_id: str):
    """Revoke capabilities on user request."""
    # Find capabilities matching resource_id
    caps = self.capability_supervisor.find_capabilities(
        agent_id=agent_id,
        resource_id=resource_id
    )

    for cap in caps:
        await self.capability_supervisor.revoke_capability(
            cap_id=cap.cap_id,
            reason=f"User request ({user_id})"
        )
```

---

### 7. Configuration Schema (YAML)

**File:** `k1/config/capability_policies.yml`

```yaml
# Capability Assignment Policies for K1 Intelligence Module
# ADR-0010b: Agent Capability Assignment Policy
# Version: 1.0
# Last Updated: 2025-10-12

# Global settings
global:
  trust_level_thresholds:
    level_0: 0                          # Untrusted (new agent)
    level_1: 1                          # Low trust (1-9 tasks)
    level_2: 10                         # Medium trust (10-49 tasks)
    level_3: 50                         # High trust (50+ tasks)
    level_4: null                       # Admin (supervisor only)

  trust_level_demotion:
    failure_rate_threshold: 0.10        # Demote if >10% failure rate
    policy_violation_demote_to: 0       # Demote to level 0 on violation

# Role-based capability policies
capability_policies:

  # Planning Agent
  planning_agent:
    trust_level: 1                      # Default: Low trust

    default_capabilities:
      - type: LLM
        resource_id: gemma-2b
        permissions: [execute]
        constraints:
          max_invocations: 100
          expires_at: session_end
        justification: "Planning requires LLM for plan generation"

      - type: TOOL
        resource_id: search_web
        permissions: [execute]
        constraints:
          max_invocations: 50
          expires_at: session_end
        justification: "Planning may require web search"

      - type: MEMORY
        resource_id: beliefs
        permissions: [read]
        constraints:
          expires_at: session_end
        justification: "Planning requires conversation context"

    escalation_capabilities:
      trust_level_1:
        - type: LLM
          resource_id: gpt-4o-mini
          permissions: [execute]
          approval_required: true
          approval_criteria:
            task_complexity: high
            local_llm_failed: true
          constraints:
            budget_usd: 0.50
            max_invocations: 5
            expires_at: session_end

      trust_level_2:
        - type: LLM
          resource_id: gpt-4o-mini
          permissions: [execute]
          approval_required: false      # Auto-approved
          constraints:
            budget_usd: 1.0
            max_invocations: 10
            expires_at: session_end

        - type: LLM
          resource_id: gpt-4o
          permissions: [execute]
          approval_required: true
          approval_criteria:
            task_complexity: critical
            gpt_4o_mini_failed: true
          constraints:
            budget_usd: 1.0
            max_invocations: 3
            expires_at: session_end

      trust_level_3:
        - type: LLM
          resource_id: gpt-4o
          permissions: [execute]
          approval_required: false      # Auto-approved for high trust
          constraints:
            budget_usd: 2.0
            max_invocations: 10
            expires_at: session_end

  # Tool Agent
  tool_agent:
    trust_level: 1                      # Default: Low trust

    default_capabilities:
      - type: TOOL
        resource_id: "${assigned_tool}"  # Dynamic (assigned on hire)
        permissions: [execute]
        constraints:
          max_invocations: 10
          expires_at: session_end
        justification: "Tool agent executes assigned tool"

      - type: MEMORY
        resource_id: scoreboard
        permissions: [write]
        constraints:
          expires_at: session_end
        justification: "Tool agent writes results to scoreboard"

    escalation_capabilities:
      trust_level_1:
        - type: TOOL
          resource_id: charge_payment
          permissions: [execute]
          approval_required: true
          approval_criteria:
            user_confirmation: true
            amount_usd: "<100"
          constraints:
            max_invocations: 1
            expires_at: "1h"

      trust_level_2:
        - type: TOOL
          resource_id: charge_payment
          permissions: [execute]
          approval_required: true
          approval_criteria:
            user_confirmation: true
            amount_usd: "<500"
          constraints:
            max_invocations: 3
            expires_at: "1h"

      trust_level_3:
        - type: TOOL
          resource_id: charge_payment
          permissions: [execute]
          approval_required: true
          approval_criteria:
            user_confirmation: true
            amount_usd: "<1000"
          constraints:
            max_invocations: 5
            expires_at: "1h"

  # Memory Agent
  memory_agent:
    trust_level: 2                      # Default: Medium trust (critical role)

    default_capabilities:
      - type: MEMORY
        resource_id: beliefs
        permissions: [read]
        constraints:
          expires_at: session_end
        justification: "Memory agent reads beliefs for context"

      - type: MEMORY
        resource_id: scoreboard
        permissions: [read]
        constraints:
          expires_at: session_end
        justification: "Memory agent reads scoreboard for aggregation"

      - type: K0_WAL
        resource_id: read_only
        permissions: [read]
        constraints:
          expires_at: session_end
        justification: "Memory agent reads K0 WAL for reconstruction"

    escalation_capabilities:
      trust_level_2:
        - type: MEMORY
          resource_id: persona
          permissions: [read]
          approval_required: true
          approval_criteria:
            privacy_band: AMBER
            arbiter_approved: true
          constraints:
            max_invocations: 5
            expires_at: session_end

        - type: K0_WAL
          resource_id: write
          permissions: [write]
          approval_required: true
          approval_criteria:
            supervisor_approved: true
          constraints:
            max_invocations: 100
            expires_at: session_end

      trust_level_3:
        - type: MEMORY
          resource_id: persona
          permissions: [write]
          approval_required: true
          approval_criteria:
            privacy_band: AMBER
            arbiter_approved: true
            supervisor_approved: true
          constraints:
            max_invocations: 10
            expires_at: session_end

  # Supervisor Agent
  supervisor_agent:
    trust_level: 4                      # Admin (full trust)

    default_capabilities:
      - type: TOOL
        resource_id: "*"
        permissions: [execute, admin]
        constraints:
          expires_at: session_end
        justification: "Supervisor requires all tools"

      - type: MEMORY
        resource_id: "*"
        permissions: [read, write, admin]
        constraints:
          expires_at: session_end
        justification: "Supervisor manages session state"

      - type: LLM
        resource_id: "*"
        permissions: [execute, admin]
        constraints:
          budget_usd: 5.0
          expires_at: session_end
        justification: "Supervisor may need powerful LLMs"

      - type: K0_WAL
        resource_id: "*"
        permissions: [read, write, admin]
        constraints:
          expires_at: session_end
        justification: "Supervisor manages event persistence"

    escalation_capabilities: []         # No escalation needed (already admin)

# Capability inheritance rules
inheritance:
  budget_multiplier: 0.5                # Child gets 50% of parent budget
  invocations_multiplier: 0.5           # Child gets 50% of parent invocations
  max_child_expiration_minutes: 10      # Child expires after 10 min max

# Revocation triggers
revocation_triggers:
  agent_crash: true                     # Revoke on crash
  policy_violation: true                # Revoke on policy violation
  session_end: true                     # Revoke on session end
  budget_exhausted: true                # Revoke on budget exhausted
  user_request: true                    # Revoke on user request
```

---

### 8. Performance Budget

**Target Latencies (P95):**
| Operation | Budget | Target | Current |
|-----------|--------|--------|---------|
| Default capability assignment | <10ms | 5ms | 6ms |
| Escalation evaluation | <5ms | 3ms | 3.5ms |
| Trust level calculation | <1ms | 0.5ms | 0.6ms |
| Policy lookup | <0.1ms | 0.05ms | 0.07ms |
| Capability inheritance | <1ms | 0.5ms | 0.7ms |

**Memory Budget:**
| Component | Budget | Target | Current |
|-----------|--------|--------|---------|
| Policy configuration (YAML) | <100KB | 50KB | 58KB |
| Trust level state per agent | <128B | 64B | 72B |
| Escalation policy cache | <10MB | 5MB | 6MB |

---

## Consequences

### Positive

1. **Least Privilege by Default:**
   Agents receive minimal capabilities on hire, reducing attack surface.

2. **Trust-Based Escalation:**
   Higher trust levels enable auto-approved escalations, reducing supervisor overhead.

3. **Role-Based Consistency:**
   Consistent capability assignment across agents with same role, reducing configuration errors.

4. **Flexible Escalation:**
   Agents can request additional capabilities when needed, enabling complex workflows.

5. **Audit Trail:**
   All capability grants/denials logged, enabling security review and compliance reporting.

### Negative

1. **Configuration Complexity:**
   YAML policies complex to manage (4 roles × 4 trust levels = 16 policy configurations).

2. **Supervisor Overhead:**
   Escalation evaluation adds latency to agent operations (~3-5ms per request).

3. **Trust Level State:**
   Tracking agent execution history (success/failure counts) requires persistent state.

### Risks

1. **Over-Privileged Escalation:**
   Auto-approved escalations for high-trust agents may grant excessive privileges.
   **Mitigation:** Periodic audit of escalation grants, demote trust level on failure.

2. **Trust Level Manipulation:**
   Attacker may artificially inflate trust level by completing trivial tasks.
   **Mitigation:** Trust level based on task complexity, not just count (future enhancement).

3. **Policy Misconfiguration:**
   Incorrect YAML policy may grant unintended capabilities.
   **Mitigation:** YAML validation on startup, policy review process, rollback mechanism.

---

## References

- **Principle of Least Privilege (Saltzer & Schroeder 1975):** [Protection of Information Systems](https://web.mit.edu/Saltzer/www/publications/protection/)
- **Role-Based Access Control (Ferraiolo & Kuhn 1992):** [NIST RBAC](https://csrc.nist.gov/projects/role-based-access-control)
- **Trust Management (Blaze et al. 1996):** [PolicyMaker](https://www.crypto.com/papers/policymaker.pdf)

---

## Related ADRs

- **ADR-0002:** Actor Model & Agent Isolation (capabilities in actor messages)
- **ADR-0005:** Agent Lifecycle FSM (capability assignment on WARMING → ACTIVE)
- **ADR-0007c:** Planner Arbiter (arbiter approval for privacy-sensitive escalations)
- **ADR-0010a:** Capability Token Design & Lifecycle (JWT structure, signature, validation)
- **ADR-0010c:** Capability Enforcement at Runtime (enforcement at executors)
- **ADR-0010d:** Capability Revocation & Audit Trail (revocation triggers, audit logging)

---

**End of ADR-0010b**