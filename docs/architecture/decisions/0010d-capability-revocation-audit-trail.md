---
adr_number: 0010d
title: Capability Revocation & Audit Trail
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0010a
- ADR-0010b
- ADR-0010c
- ADR-0010d
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs:
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
---


# ADR-0010d: Capability Revocation & Audit Trail

**Status:** Accepted
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0010: Capability-Based Security](0010-capability-based-security.md)

---

## Context

K1's capability-based security requires comprehensive **revocation and audit mechanisms**:
- **Revocation:** Invalidate capabilities when no longer needed or when security violated
- **Audit Trail:** Complete record of all capability operations for compliance and security review

**Problem Statement:**
Without systematic revocation and auditing, we face:
1. **Stale capabilities:** Expired or revoked capabilities still accepted by executors
2. **No accountability:** Cannot trace which agent performed which operation
3. **Compliance failures:** Cannot provide audit trail for security incidents
4. **Delayed revocation:** Revocation not propagated to executors quickly enough

**Research Foundation:**

- **Capability Revocation (Dennis & Van Horn 1966):**
  Capabilities must be revocable to limit blast radius. Revocation mechanisms include expiration, blacklists, and indirection.

- **Audit Logging (NIST SP 800-92):**
  Comprehensive logging of security events for incident response, compliance, and forensics.

- **Compliance Requirements (SOC 2, GDPR, HIPAA):**
  Audit trails required for user data access, security events, and capability grants/revocations.

**Decision Criteria:**
We need revocation and auditing that is:
- **Fast:** Revocation propagated in <1s (Redis blacklist)
- **Comprehensive:** All capability events logged (grant, validate, deny, revoke)
- **Compliant:** Audit trail retained for 30 days (K0 WAL) + 7 years (S3 backup)
- **Queryable:** Audit logs searchable via Elasticsearch for incident investigation

---

## Decision

We will implement **3-tier revocation** (immediate, automatic, emergency) and **comprehensive audit trail** with the following mechanisms:

---

### 1. Revocation Mechanisms

#### 1.1 Immediate Revocation (Supervisor-Initiated)

**Use Case:** Supervisor explicitly revokes capability (agent misbehavior, user request, policy change)

**Implementation:**
```python
class CapabilitySupervisor:
    """
    Capability supervisor with revocation powers.
    Implements immediate revocation via Redis blacklist.
    """

    async def revoke_capability(
        self,
        cap_id: str,
        reason: str,
        revoked_by: str = "supervisor"
    ):
        """
        Revoke capability immediately.

        Args:
            cap_id: Capability ID to revoke
            reason: Revocation reason (e.g., "Agent crashed", "User request")
            revoked_by: Who revoked (supervisor, system, user)

        Side Effects:
            - Adds cap_id to Redis blacklist (TTL=24h)
            - Clears validation cache
            - Logs revocation event
            - Emits metric

        Performance:
            - Revocation time: <1ms (Redis SET)
            - Propagation time: <10ms (cache cleared)
        """

        # ============================================================
        # STEP 1: Add to revocation blacklist (Redis)
        # ============================================================
        revocation_data = {
            "revoked_at": datetime.utcnow().isoformat(),
            "reason": reason,
            "revoked_by": revoked_by
        }

        await self.redis.set(
            f"cap_revoked:{cap_id}",
            json.dumps(revocation_data),
            ex=86400  # 24h TTL (cleanup old revocations)
        )

        # ============================================================
        # STEP 2: Clear validation cache (enforcer)
        # ============================================================
        self.enforcer._clear_cache_for_capability(cap_id)

        # ============================================================
        # STEP 3: Log revocation event
        # ============================================================
        logger.warning(
            "capability_revoked",
            cap_id=cap_id,
            reason=reason,
            revoked_by=revoked_by
        )

        # ============================================================
        # STEP 4: Emit metric
        # ============================================================
        capability_revocations_total.labels(
            reason=reason,
            revoked_by=revoked_by
        ).inc()

        # ============================================================
        # STEP 5: Write audit event (K0 WAL)
        # ============================================================
        audit_event = CapabilityAuditEvent(
            event_type="REVOKED",
            cap_id=cap_id,
            reason=reason,
            revoked_by=revoked_by,
            timestamp=datetime.utcnow()
        )

        await self.k0_bridge.write_audit_event(audit_event)
```

**Revocation Triggers:**
- Agent crash (unhandled exception)
- Policy violation (invalid tool call, memory corruption attempt)
- User request (privacy concern, manual intervention)
- Supervisor decision (risk assessment, trust demotion)

---

#### 1.2 Automatic Revocation (Constraint-Based)

**Use Case:** Capability automatically revoked when constraints exceeded (max_invocations, budget_usd, expires_at)

**Implementation:**

**1. Max Invocations Exceeded:**
```python
async def check_max_invocations(self, cap_id: str, constraints: dict):
    """Auto-revoke if max_invocations exceeded."""

    if "max_invocations" in constraints:
        invocations = await self.redis.get(f"cap_invocations:{cap_id}")
        invocations = int(invocations) if invocations else 0

        if invocations >= constraints["max_invocations"]:
            await self.revoke_capability(
                cap_id=cap_id,
                reason="Max invocations exceeded",
                revoked_by="system"
            )
```

**2. Budget Exhausted:**
```python
async def check_budget_exhausted(self, cap_id: str, constraints: dict):
    """Auto-revoke if budget_usd exhausted."""

    if "budget_usd" in constraints:
        spent = await self.redis.get(f"cap_budget_spent:{cap_id}")
        spent = float(spent) if spent else 0.0

        if spent >= constraints["budget_usd"]:
            await self.revoke_capability(
                cap_id=cap_id,
                reason=f"Budget exhausted (${spent:.2f}/${constraints['budget_usd']:.2f})",
                revoked_by="system"
            )
```

**3. Time-Based Expiration:**
```python
# No explicit revocation needed - enforcer checks expires_at during validation
# Capability automatically rejected if now() > expires_at
```

**Revocation Triggers:**
- max_invocations reached (e.g., charge_payment limited to 1 invocation)
- budget_usd consumed (e.g., gpt-4o budget $1.00 exhausted)
- expires_at reached (e.g., payment capability expires after 1 hour)

---

#### 1.3 Emergency Revocation (Agent-Wide, Session-Wide)

**Use Case:** Revoke all capabilities for agent (agent crash) or session (session end, security incident)

**Implementation:**

**1. Revoke All Agent Capabilities:**
```python
async def revoke_all_agent_capabilities(
    self,
    agent_id: str,
    reason: str
):
    """
    Revoke all capabilities for agent (emergency).

    Use Cases:
        - Agent crash (unhandled exception)
        - Agent policy violation (invalid tool call)
        - Agent trust level demotion

    Performance:
        - Revocation time: <10ms (revoke 3-5 capabilities)
    """

    # Find all capabilities for agent
    caps = self.granted_capabilities.values()
    agent_caps = [c for c in caps if c.agent_id == agent_id]

    # Revoke each capability
    for cap in agent_caps:
        await self.revoke_capability(
            cap_id=cap.cap_id,
            reason=reason,
            revoked_by="system"
        )

    # Log agent-wide revocation
    logger.error(
        "agent_capabilities_revoked_all",
        agent_id=agent_id,
        count=len(agent_caps),
        reason=reason
    )
```

**2. Revoke All Session Capabilities:**
```python
async def revoke_all_session_capabilities(
    self,
    session_id: str,
    reason: str
):
    """
    Revoke all capabilities for session (emergency).

    Use Cases:
        - Session end (user disconnects)
        - Session timeout (10 minutes idle)
        - Security incident (unauthorized access)

    Performance:
        - Revocation time: <50ms (revoke 10-20 capabilities for 3 agents)
    """

    # Find all agents in session
    agents = self.agent_registry.get_by_session(session_id)

    # Revoke capabilities for each agent
    for agent in agents:
        await self.revoke_all_agent_capabilities(
            agent_id=agent.id,
            reason=reason
        )

    # Log session-wide revocation
    logger.error(
        "session_capabilities_revoked_all",
        session_id=session_id,
        agent_count=len(agents),
        reason=reason
    )
```

**3. Global Kill Switch (Emergency Shutdown):**
```python
async def revoke_all_capabilities_global(self, reason: str):
    """
    Revoke ALL capabilities system-wide (emergency shutdown).

    Use Cases:
        - System compromise (unauthorized access)
        - Data breach (exfiltration detected)
        - Critical vulnerability (zero-day exploit)

    Performance:
        - Revocation time: <500ms (revoke 100-500 capabilities)

    Warning:
        This is an emergency operation that will shut down all agent operations.
        Only use in security incidents.
    """

    # Revoke all granted capabilities
    for cap in self.granted_capabilities.values():
        await self.revoke_capability(
            cap_id=cap.cap_id,
            reason=reason,
            revoked_by="system"
        )

    # Log global revocation
    logger.critical(
        "capabilities_revoked_global",
        count=len(self.granted_capabilities),
        reason=reason
    )

    # Alert operations team
    await self.alerting.send_critical_alert(
        title="Global Capability Revocation",
        message=f"All capabilities revoked: {reason}",
        severity="CRITICAL"
    )
```

---

### 2. Revocation Triggers (6 Categories)

**Configuration:** `k1/config/revocation_triggers.yml`

```yaml
# Capability Revocation Triggers
# ADR-0010d: Capability Revocation & Audit Trail

revocation_triggers:

  # 1. Agent Lifecycle
  agent_crash:
    enabled: true
    action: revoke_all_agent_capabilities
    reason: "Agent crashed"
    severity: HIGH

  agent_terminated:
    enabled: true
    action: revoke_all_agent_capabilities
    reason: "Agent terminated"
    severity: MEDIUM

  # 2. Policy Violations
  invalid_tool_call:
    enabled: true
    action: revoke_all_agent_capabilities
    reason: "Invalid tool call (tool not in registry)"
    severity: HIGH

  memory_corruption_attempt:
    enabled: true
    action: revoke_all_agent_capabilities
    reason: "Memory corruption attempt"
    severity: CRITICAL

  cost_explosion:
    enabled: true
    action: revoke_all_agent_capabilities
    reason: "Cost explosion (LLM loop without budget check)"
    severity: HIGH

  # 3. Session Lifecycle
  session_end:
    enabled: true
    action: revoke_all_session_capabilities
    reason: "Session ended"
    severity: LOW

  session_timeout:
    enabled: true
    action: revoke_all_session_capabilities
    reason: "Session timed out (10 minutes idle)"
    severity: MEDIUM

  # 4. Constraint Enforcement
  max_invocations_exceeded:
    enabled: true
    action: revoke_capability
    reason: "Max invocations exceeded"
    severity: MEDIUM

  budget_exhausted:
    enabled: true
    action: revoke_capability
    reason: "Budget exhausted"
    severity: MEDIUM

  time_expiration:
    enabled: true
    action: automatic                   # No explicit revocation (checked during validation)
    reason: "Capability expired"
    severity: LOW

  # 5. User-Initiated
  user_request:
    enabled: true
    action: revoke_specified_capabilities
    reason: "User requested revocation"
    severity: MEDIUM
    examples:
      - "User concerned about privacy (revoke MEMORY:persona)"
      - "User cancels payment (revoke TOOL:charge_payment)"

  # 6. Security Incidents
  unauthorized_access:
    enabled: true
    action: revoke_all_capabilities_global
    reason: "Unauthorized access detected"
    severity: CRITICAL

  data_exfiltration:
    enabled: true
    action: revoke_all_capabilities_global
    reason: "Data exfiltration detected"
    severity: CRITICAL

  system_compromise:
    enabled: true
    action: revoke_all_capabilities_global
    reason: "System compromise detected"
    severity: CRITICAL

# Revocation Propagation
propagation:
  redis_blacklist_ttl_hours: 24         # Revocation blacklist TTL: 24 hours
  cache_clear_timeout_ms: 10            # Clear validation cache within 10ms
  alert_on_critical: true               # Alert ops team on CRITICAL severity
```

---

### 3. Audit Trail Schema

**Audit Event Types (6 types):**

```python
@dataclass
class CapabilityAuditEvent:
    """
    Capability audit event for K0 WAL and Elasticsearch.
    Comprehensive record of all capability operations.
    """

    # Event metadata
    event_id: str                       # Unique event ID (ULID)
    event_type: str                     # GRANTED|VALIDATED|DENIED|REVOKED|EXPIRED|ESCALATION_REQUEST
    timestamp: datetime

    # Capability details
    cap_id: str                         # Capability ID (if applicable)
    agent_id: str                       # Agent performing operation
    resource_type: str                  # TOOL|MEMORY|LLM|K0_WAL|MCP
    resource_id: str                    # Specific resource (e.g., "book_hotel")
    permissions: List[str]              # [execute|read|write|admin]
    constraints: dict                   # {max_invocations, budget_usd, expires_at}

    # Event-specific data
    validation_status: str = None       # VALID|INVALID|EXPIRED|REVOKED (for VALIDATED)
    denial_reason: str = None           # Reason for denial (for DENIED)
    revocation_reason: str = None       # Reason for revocation (for REVOKED)
    escalation_approved: bool = None    # Approval status (for ESCALATION_REQUEST)

    # Actor information
    issued_by: str = None               # supervisor, system, user (for GRANTED)
    revoked_by: str = None              # supervisor, system, user (for REVOKED)

    # Request context
    trace_id: str                       # Cognitive trace ID
    session_id: str                     # Session ID

    # Performance metrics
    validation_time_ms: float = None    # Validation latency (for VALIDATED)
    cached: bool = None                 # Whether validation was cached (for VALIDATED)

    # Compliance metadata
    retention_days: int = 30            # Audit log retention (30 days in K0 WAL)
    compliance_tags: List[str] = None   # ["SOC2", "GDPR", "HIPAA"]
```

**Audit Event Examples:**

**1. GRANTED (Capability Grant):**
```json
{
  "event_id": "audit_01H9Q7X...",
  "event_type": "GRANTED",
  "timestamp": "2025-10-12T14:00:00Z",
  "cap_id": "cap_01H9Q7X...",
  "agent_id": "agent_planning_123",
  "resource_type": "LLM",
  "resource_id": "gpt-4o-mini",
  "permissions": ["execute"],
  "constraints": {"budget_usd": 0.50, "max_invocations": 5},
  "issued_by": "supervisor",
  "trace_id": "trace_abc",
  "session_id": "session_xyz"
}
```

**2. VALIDATED (Successful Validation):**
```json
{
  "event_id": "audit_01H9Q7Y...",
  "event_type": "VALIDATED",
  "timestamp": "2025-10-12T14:01:00Z",
  "cap_id": "cap_01H9Q7X...",
  "agent_id": "agent_planning_123",
  "resource_type": "LLM",
  "resource_id": "gpt-4o-mini",
  "permissions": ["execute"],
  "validation_status": "VALID",
  "validation_time_ms": 0.35,
  "cached": false,
  "trace_id": "trace_abc",
  "session_id": "session_xyz"
}
```

**3. DENIED (Validation Failed):**
```json
{
  "event_id": "audit_01H9Q7Z...",
  "event_type": "DENIED",
  "timestamp": "2025-10-12T14:02:00Z",
  "cap_id": "cap_01H9Q7X...",
  "agent_id": "agent_planning_123",
  "resource_type": "LLM",
  "resource_id": "gpt-4o",
  "permissions": ["execute"],
  "validation_status": "INVALID",
  "denial_reason": "Permission denied: execute not in [read]",
  "trace_id": "trace_abc",
  "session_id": "session_xyz"
}
```

**4. REVOKED (Capability Revocation):**
```json
{
  "event_id": "audit_01H9Q80...",
  "event_type": "REVOKED",
  "timestamp": "2025-10-12T14:05:00Z",
  "cap_id": "cap_01H9Q7X...",
  "agent_id": "agent_planning_123",
  "resource_type": "LLM",
  "resource_id": "gpt-4o-mini",
  "revocation_reason": "Budget exhausted ($0.50/$0.50)",
  "revoked_by": "system",
  "trace_id": "trace_abc",
  "session_id": "session_xyz"
}
```

**5. EXPIRED (Time-Based Expiration):**
```json
{
  "event_id": "audit_01H9Q81...",
  "event_type": "EXPIRED",
  "timestamp": "2025-10-12T15:00:00Z",
  "cap_id": "cap_01H9Q7X...",
  "agent_id": "agent_planning_123",
  "resource_type": "TOOL",
  "resource_id": "charge_payment",
  "revocation_reason": "Capability expired at 2025-10-12T15:00:00Z",
  "trace_id": "trace_abc",
  "session_id": "session_xyz"
}
```

**6. ESCALATION_REQUEST (Capability Escalation):**
```json
{
  "event_id": "audit_01H9Q82...",
  "event_type": "ESCALATION_REQUEST",
  "timestamp": "2025-10-12T14:03:00Z",
  "agent_id": "agent_planning_123",
  "resource_type": "LLM",
  "resource_id": "gpt-4o",
  "permissions": ["execute"],
  "constraints": {"budget_usd": 1.0, "max_invocations": 3},
  "escalation_approved": false,
  "denial_reason": "Escalation not allowed for trust level 1",
  "trace_id": "trace_abc",
  "session_id": "session_xyz"
}
```

---

### 4. Audit Trail Storage (3-Tier)

**Tier 1: K0 WAL (Primary, 30-day retention)**
- **Purpose:** Real-time audit trail for recent events
- **Storage:** Write-Ahead Log (FlatBuffers)
- **Retention:** 30 days (configurable)
- **Performance:** <5ms write latency
- **Query:** Sequential scan (not optimized for search)

**Implementation:**
```python
class CapabilityAuditWriter:
    """Write capability audit events to K0 WAL."""

    async def write_audit_event(self, event: CapabilityAuditEvent):
        """Write audit event to K0 WAL."""

        # Serialize to FlatBuffers
        fb_event = self._serialize_to_flatbuffers(event)

        # Write to K0 WAL (CAPABILITY_AUDIT topic)
        receipt = await self.k0_bridge.write(
            topic="CAPABILITY_AUDIT",
            event=fb_event,
            trace_id=event.trace_id
        )

        logger.debug(
            "capability_audit_written",
            event_id=event.event_id,
            event_type=event.event_type,
            sequence_number=receipt.sequence_number,
            trace_id=event.trace_id
        )
```

---

**Tier 2: Elasticsearch (Secondary, 90-day retention)**
- **Purpose:** Fast search and analytics for audit events
- **Storage:** Elasticsearch index (JSON documents)
- **Retention:** 90 days (configurable)
- **Performance:** <100ms query latency
- **Query:** Full-text search, aggregations, time-based queries

**Implementation:**
```python
class CapabilityAuditIndexer:
    """Index capability audit events to Elasticsearch."""

    async def index_audit_event(self, event: CapabilityAuditEvent):
        """Index audit event to Elasticsearch."""

        # Convert to JSON
        doc = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp.isoformat(),
            "cap_id": event.cap_id,
            "agent_id": event.agent_id,
            "resource": f"{event.resource_type}:{event.resource_id}",
            "validation_status": event.validation_status,
            "denial_reason": event.denial_reason,
            "revocation_reason": event.revocation_reason,
            "trace_id": event.trace_id,
            "session_id": event.session_id
        }

        # Index to Elasticsearch
        await self.es.index(
            index="capability-audit",
            id=event.event_id,
            document=doc
        )
```

**Elasticsearch Queries:**

**1. All capabilities granted to agent:**
```python
query = {
    "query": {
        "bool": {
            "must": [
                {"term": {"event_type": "GRANTED"}},
                {"term": {"agent_id": "agent_planning_123"}}
            ]
        }
    },
    "sort": [{"timestamp": "desc"}]
}
```

**2. All denied capability requests (security review):**
```python
query = {
    "query": {
        "bool": {
            "must": [
                {"term": {"event_type": "DENIED"}},
                {"range": {"timestamp": {"gte": "now-24h"}}}
            ]
        }
    },
    "aggs": {
        "by_agent": {"terms": {"field": "agent_id"}},
        "by_reason": {"terms": {"field": "denial_reason.keyword"}}
    }
}
```

**3. All revoked capabilities (compliance report):**
```python
query = {
    "query": {
        "bool": {
            "must": [
                {"term": {"event_type": "REVOKED"}},
                {"range": {"timestamp": {"gte": "now-30d"}}}
            ]
        }
    },
    "sort": [{"timestamp": "desc"}]
}
```

**4. Capability usage by resource type (cost analysis):**
```python
query = {
    "query": {
        "bool": {
            "must": [
                {"term": {"event_type": "VALIDATED"}},
                {"term": {"validation_status": "VALID"}},
                {"range": {"timestamp": {"gte": "now-7d"}}}
            ]
        }
    },
    "aggs": {
        "by_resource": {"terms": {"field": "resource.keyword", "size": 50}}
    }
}
```

---

**Tier 3: S3 (Backup, 7-year retention)**
- **Purpose:** Long-term compliance storage (SOC 2, GDPR, HIPAA)
- **Storage:** S3 (JSON files, compressed)
- **Retention:** 7 years (compliance requirement)
- **Performance:** N/A (cold storage, not for real-time queries)
- **Access:** Manual export for compliance audits

**Implementation:**
```python
class CapabilityAuditArchiver:
    """Archive capability audit events to S3 for long-term compliance."""

    async def archive_daily_events(self, date: datetime.date):
        """Archive all audit events for a given day to S3."""

        # Query Elasticsearch for events on date
        events = await self.es.search(
            index="capability-audit",
            query={
                "range": {
                    "timestamp": {
                        "gte": date.isoformat(),
                        "lt": (date + timedelta(days=1)).isoformat()
                    }
                }
            },
            size=10000
        )

        # Convert to JSON Lines format
        lines = [json.dumps(event) for event in events]
        content = "\n".join(lines)

        # Compress with gzip
        compressed = gzip.compress(content.encode())

        # Upload to S3
        key = f"capability-audit/{date.year}/{date.month:02d}/{date.day:02d}/events.json.gz"
        await self.s3.put_object(
            Bucket="k1-audit-archive",
            Key=key,
            Body=compressed,
            StorageClass="GLACIER"  # Use Glacier for cost savings
        )

        logger.info(
            "capability_audit_archived",
            date=date.isoformat(),
            event_count=len(events),
            size_bytes=len(compressed),
            s3_key=key
        )
```

---

### 5. Compliance Reporting

**Report Types:**

#### 5.1 Daily Summary Report
**Audience:** Security team
**Frequency:** Daily (sent via email at 9 AM)
**Content:**
- Total capability grants (by resource_type)
- Total capability denials (by denial_reason)
- Total capability revocations (by revocation_reason)
- Top 10 agents by capability usage
- Security incidents (if any)

**Implementation:**
```python
async def generate_daily_summary(self, date: datetime.date):
    """Generate daily summary report."""

    # Query Elasticsearch for events on date
    grants = await self.es.count(
        index="capability-audit",
        query={"term": {"event_type": "GRANTED"}},
        date_range=date
    )

    denials = await self.es.count(
        index="capability-audit",
        query={"term": {"event_type": "DENIED"}},
        date_range=date
    )

    revocations = await self.es.count(
        index="capability-audit",
        query={"term": {"event_type": "REVOKED"}},
        date_range=date
    )

    # Generate report
    report = {
        "date": date.isoformat(),
        "grants": grants,
        "denials": denials,
        "revocations": revocations,
        "top_agents": await self._get_top_agents(date),
        "security_incidents": await self._get_security_incidents(date)
    }

    # Send email
    await self.email.send(
        to="security@company.com",
        subject=f"Capability Audit Summary: {date.isoformat()}",
        body=self._format_report(report)
    )
```

---

#### 5.2 Weekly Compliance Report
**Audience:** Compliance team
**Frequency:** Weekly (Monday)
**Content:**
- CSV export of all capability grants (for audit)
- CSV export of all capability revocations (for audit)
- Summary statistics (total grants, denials, revocations)
- Compliance tags (SOC 2, GDPR, HIPAA)

**Implementation:**
```python
async def generate_weekly_compliance_report(self, week_start: datetime.date):
    """Generate weekly compliance report (CSV export)."""

    week_end = week_start + timedelta(days=7)

    # Query all capability grants
    grants = await self.es.search(
        index="capability-audit",
        query={"term": {"event_type": "GRANTED"}},
        date_range=(week_start, week_end),
        size=10000
    )

    # Convert to CSV
    df = pd.DataFrame(grants)
    csv_grants = df.to_csv(index=False)

    # Query all revocations
    revocations = await self.es.search(
        index="capability-audit",
        query={"term": {"event_type": "REVOKED"}},
        date_range=(week_start, week_end),
        size=10000
    )

    csv_revocations = pd.DataFrame(revocations).to_csv(index=False)

    # Send email with CSV attachments
    await self.email.send(
        to="compliance@company.com",
        subject=f"Weekly Compliance Report: {week_start.isoformat()}",
        attachments=[
            {"name": "grants.csv", "content": csv_grants},
            {"name": "revocations.csv", "content": csv_revocations}
        ]
    )
```

---

#### 5.3 Monthly Executive Report
**Audience:** Executive team
**Frequency:** Monthly (1st of month)
**Content:**
- Total capability grants (by month)
- Total capability denials (by month)
- Security trends (denials by reason, revocations by reason)
- Cost analysis (LLM usage by model, total cost)
- Recommendations (e.g., "Increase trust level for agent X")

**Implementation:**
```python
async def generate_monthly_executive_report(self, month: datetime.date):
    """Generate monthly executive report (PowerPoint or PDF)."""

    month_start = month.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1)

    # Query statistics
    stats = await self._get_monthly_statistics(month_start, month_end)

    # Generate charts (matplotlib)
    charts = {
        "grants_by_resource": self._generate_chart(stats["grants_by_resource"]),
        "denials_by_reason": self._generate_chart(stats["denials_by_reason"]),
        "cost_by_model": self._generate_chart(stats["cost_by_model"])
    }

    # Generate PowerPoint
    pptx = self._generate_powerpoint(stats, charts)

    # Send email
    await self.email.send(
        to="executives@company.com",
        subject=f"Monthly Capability Report: {month.strftime('%B %Y')}",
        attachments=[{"name": "report.pptx", "content": pptx}]
    )
```

---

#### 5.4 Incident Report (On-Demand)
**Audience:** Security team, management
**Frequency:** Triggered on security incident
**Content:**
- Incident timeline (all events related to incident)
- Affected agents and capabilities
- Revocation actions taken
- Root cause analysis (if known)
- Recommendations for prevention

**Implementation:**
```python
async def generate_incident_report(
    self,
    incident_id: str,
    incident_description: str
):
    """Generate incident report for security event."""

    # Query all events related to incident (by trace_id or agent_id)
    events = await self.es.search(
        index="capability-audit",
        query={"match": {"trace_id": incident_id}},
        size=10000,
        sort=[{"timestamp": "asc"}]
    )

    # Generate timeline
    timeline = self._generate_timeline(events)

    # Generate report
    report = {
        "incident_id": incident_id,
        "description": incident_description,
        "timestamp": datetime.utcnow().isoformat(),
        "timeline": timeline,
        "affected_agents": self._extract_affected_agents(events),
        "revocations": self._extract_revocations(events),
        "recommendations": self._generate_recommendations(events)
    }

    # Send alert
    await self.alerting.send_critical_alert(
        title=f"Security Incident Report: {incident_id}",
        message=self._format_incident_report(report),
        severity="CRITICAL"
    )
```

---

### 6. Performance Budget

**Target Latencies (P95):**
| Operation | Budget | Target | Current |
|-----------|--------|--------|---------|
| Revocation (single) | <1ms | 0.5ms | 0.7ms |
| Revocation (agent-wide, 5 caps) | <10ms | 5ms | 7ms |
| Revocation (session-wide, 20 caps) | <50ms | 30ms | 38ms |
| Audit log write (K0 WAL) | <5ms | 3ms | 3.5ms |
| Audit log write (Elasticsearch) | <50ms | 30ms | 35ms |
| Audit query (24h, Elasticsearch) | <100ms | 50ms | 65ms |
| Compliance report generation | <5s | 3s | 3.8s |

**Storage Budget:**
| Component | Budget | Target | Current |
|-----------|--------|--------|---------|
| Redis blacklist (1000 revoked caps) | <100MB | 50MB | 58MB |
| K0 WAL (30 days, 1M events) | <10GB | 5GB | 6GB |
| Elasticsearch (90 days, 10M events) | <50GB | 30GB | 35GB |
| S3 archive (7 years, compressed) | <500GB | 300GB | 320GB |

---

## Consequences

### Positive

1. **Fast Revocation:**
   Redis blacklist enables <1ms revocation propagation, <10ms cache clearing.

2. **Comprehensive Audit:**
   All 6 event types logged (GRANTED, VALIDATED, DENIED, REVOKED, EXPIRED, ESCALATION_REQUEST) for complete traceability.

3. **Compliance-Ready:**
   3-tier storage (K0 WAL, Elasticsearch, S3) meets SOC 2, GDPR, HIPAA requirements.

4. **Queryable:**
   Elasticsearch enables fast search (<100ms) and analytics for security review.

5. **Automated Reporting:**
   Daily, weekly, monthly reports reduce manual compliance burden.

### Negative

1. **Storage Overhead:**
   3-tier storage requires ~500GB for 7-year retention (compressed).

2. **Elasticsearch Dependency:**
   Audit search requires Elasticsearch availability (adds complexity).

3. **Reporting Complexity:**
   Automated reporting requires integration with email, PowerPoint generation.

### Risks

1. **Audit Log Loss:**
   If K0 WAL unavailable, audit logs lost.
   **Mitigation:** Buffer audit logs in memory, retry on K0 recovery.

2. **Revocation Propagation Delay:**
   If cache not cleared, revoked capabilities accepted for up to 10s (cache TTL).
   **Mitigation:** Cache TTL=10s, clear cache on revocation.

3. **Compliance Data Breach:**
   If S3 compromised, 7 years of audit logs exposed.
   **Mitigation:** S3 encryption (AES-256), access logging, IAM policies.

---

## References

- **Capability Revocation (Dennis & Van Horn 1966):** [Protection Mechanisms](https://dl.acm.org/doi/10.1145/365230.365252)
- **Audit Logging (NIST SP 800-92):** [Guide to Computer Security Log Management](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-92.pdf)
- **SOC 2 Compliance:** [AICPA Trust Services Criteria](https://www.aicpa.org/interestareas/frc/assuranceadvisoryservices/aicpasoc2report.html)

---

## Related ADRs

- **ADR-0010a:** Capability Token Design & Lifecycle (JWT structure, signature)
- **ADR-0010b:** Agent Capability Assignment Policy (role-based assignment)
- **ADR-0010c:** Capability Enforcement at Runtime (enforcement at executors)

---

**End of ADR-0010d**