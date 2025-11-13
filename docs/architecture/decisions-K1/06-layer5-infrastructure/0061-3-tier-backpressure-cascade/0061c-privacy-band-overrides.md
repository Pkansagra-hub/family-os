---
adr_number: 0061c
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l4_runtime.privacy_gate
- k1.l3_execution.override_controller
- k1.l5_infrastructure.priority_scheduler
authors:
- K1 Architecture Team
concerns:
- architecture
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_phase: Phase 4 (Performance Optimization)
implementation_status: COMPLETED
related_adrs:
- ADR-0002
- ADR-0061
related_contracts:
- k0/contracts/api/rest/idempotency/24h_retention.yml
- k0/contracts/asyncapi.events.yaml
- k0/contracts/openapi.k0.yaml
- k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
research_citations:
- Priority Inversion and Solutions (Sha et al., 1990)
- Real-Time Scheduling (Liu & Layland, 1973)
- Safety-Critical Systems Design (Leveson, 1995)
status: PROPOSED
title: Privacy-Band Overrides for Critical Operations
---

# ADR-0061c: Privacy-Band Overrides for Critical Operations

**Status:** Proposed
**Date:** 2025-10-15
**Parent:** [ADR-0061: 3-Tier Backpressure Cascade](0061-3-tier-backpressure-cascade.md)
**Tier:** 1

## Context

K1 Intelligence Module operates under strict safety and privacy requirements where certain operations **must never be blocked** by backpressure, regardless of system load. The challenge: **how do we ensure RED band (safety-critical) operations always succeed while maintaining backpressure protection for routine traffic?**

**Problem Statement:**

Backpressure systems typically apply uniform policies across all traffic:
- ❌ **No differentiation**: All requests treated equally (safety checks blocked same as background tasks)
- ❌ **Priority inversion**: Low-priority work consumes resources needed for critical operations
- ❌ **Compliance risk**: Safety/privacy checks delayed or rejected violates regulatory requirements

**K1 Safety Requirements:**

1. **Arbiter approval**: RED band operations requiring human arbiter approval must never be delayed (compliance: HIPAA, GDPR, financial regulations)
2. **Safety checks**: Real-time safety validation (content moderation, PII detection, harm prevention) cannot be postponed
3. **Emergency shutdown**: Circuit breaker triggers (user distress signals, system compromise) require immediate action
4. **Audit logging**: Compliance-mandated audit events must be persisted even under overload

**Industry Precedent:**

- **TCP**: Guaranteed delivery for control packets (ACK, RST, FIN) even under congestion
- **Kubernetes**: Critical pods (kube-dns, kube-proxy) exempt from eviction under memory pressure
- **Databases**: WAL (Write-Ahead Log) writes prioritized over query processing
- **WebRTC**: RTCP control packets bypass bandwidth limits

---

## Decision

We adopt **privacy-band-aware bypass** where RED band operations and CRITICAL priority traffic skip all backpressure checks, with mandatory capability verification and comprehensive audit logging.

### **Core Principles**

**1. RED Band Always Bypasses**
- Any operation tagged `privacy_band=RED` skips watermark checks
- Applies to all 3 tiers (per-stream, voice pipeline, global limits)
- No exceptions: Safety over load shedding

**2. CRITICAL Priority Always Bypasses**
- Priority 0 (CRITICAL) operations skip backpressure
- Examples: Arbiter approval, safety checks, emergency shutdown, audit logging
- Combined with RED band: Maximum protection

**3. Capability-Based Verification**
- Bypass requires `Capability.BYPASS_BACKPRESSURE` token
- Token issued only to safety-critical components (arbiter, safety checker, audit logger)
- Prevents abuse: Regular agents cannot self-grant bypass

**4. Comprehensive Audit Logging**
- Every bypass event logged with full context
- Audit log includes: operation ID, requester, reason, timestamp, backpressure state
- 7-year retention (compliance requirement)

**5. Rate Limiting on Bypass (Safety Valve)**
- Even bypass traffic rate-limited (1000 req/s max)
- Prevents runaway bypass abuse (e.g., bug in arbiter flooding system)
- Rate limit enforced at K1 ingress (API Gateway)

**6. Graceful Degradation for Non-Critical**
- REALTIME (priority 1), INTERACTIVE (priority 2), BACKGROUND (priority 3) still subject to backpressure
- Ensures system resources available for bypass traffic

---

### **Privacy Band Classification**

K1 uses 3 privacy bands (defined in SessionState):

| Band | Sensitivity | Examples | Bypass Backpressure? |
|------|-------------|----------|---------------------|
| **GREEN** | Low | Weather, news, public data | ❌ No |
| **AMBER** | Medium | Calendar, email, personal files | ❌ No |
| **RED** | High | Health records, financial data, legal docs | ✅ **YES** |

**RED Band Criteria:**
- PHI (Protected Health Information) — HIPAA compliance
- PII (Personally Identifiable Information) — GDPR compliance
- Financial data — PCI-DSS compliance
- Legal/attorney-client privileged — Legal requirement

**Arbiter Approval Flow (RED Band):**

```
User Request (RED band)
  ↓
K1 Ingress (check privacy_band)
  ↓
if privacy_band == RED:
    ↓
  Arbiter Approval Required
    ↓
  Set BYPASS_BACKPRESSURE capability
    ↓
  Route to arbiter queue (priority 0)
    ↓
  Arbiter reviews request
    ↓
  if approved:
      Execute request (with bypass)
  else:
      Reject with explanation
```

---

### **Priority Classification**

K1 uses 4 priority levels:

| Priority | Level | Use Cases | Bypass Backpressure? |
|----------|-------|-----------|---------------------|
| **CRITICAL** | 0 | Arbiter approval, safety checks, emergency shutdown, audit logging | ✅ **YES** |
| **REALTIME** | 1 | User-facing voice, streaming responses, barge-in | ❌ No (throttled at 90%) |
| **INTERACTIVE** | 2 | Tool calls, model inference, state updates | ❌ No (shed at 85%) |
| **BACKGROUND** | 3 | Analytics, metrics, non-critical logging | ❌ No (shed at 75%) |

**Priority Assignment Rules:**

```python
def assign_priority(operation: Operation) -> Priority:
    """Assign priority based on operation characteristics"""

    # CRITICAL: Safety and compliance
    if operation.type in ["arbiter_approval", "safety_check", "emergency_shutdown", "audit_log"]:
        return Priority.CRITICAL

    # CRITICAL: RED band operations
    if operation.privacy_band == PrivacyBand.RED:
        return Priority.CRITICAL

    # REALTIME: User-facing, latency-sensitive
    if operation.type in ["voice_processing", "streaming_response", "barge_in"]:
        return Priority.REALTIME

    # INTERACTIVE: User-initiated, moderate latency tolerance
    if operation.type in ["tool_call", "model_inference", "state_update"]:
        return Priority.INTERACTIVE

    # BACKGROUND: Everything else
    return Priority.BACKGROUND
```

---

### **Capability-Based Bypass Verification**

**Capability Token Structure:**

```python
@dataclass
class BypassCapability:
    """Capability token for backpressure bypass"""

    capability_id: str              # Unique token ID
    operation_type: str             # "arbiter_approval", "safety_check", etc.
    requester: str                  # Component requesting bypass (e.g., "arbiter_agent")
    issued_at_ms: int               # Timestamp (milliseconds since epoch)
    expires_at_ms: int              # Expiration (5min TTL)
    reason: str                     # Human-readable justification
    privacy_band: PrivacyBand       # GREEN, AMBER, RED
    priority: Priority              # CRITICAL, REALTIME, INTERACTIVE, BACKGROUND
    signature: bytes                # HMAC-SHA256 signature (prevents forgery)
```

**Token Issuance (Capability Manager):**

```python
# k1/security/capability_manager.py
class CapabilityManager:
    """Issue and verify capability tokens"""

    def __init__(self, secret_key: bytes):
        self.secret_key = secret_key  # HMAC secret key (256-bit, rotated monthly)

    def issue_bypass_capability(
        self,
        operation_type: str,
        requester: str,
        reason: str,
        privacy_band: PrivacyBand,
        priority: Priority
    ) -> BypassCapability:
        """Issue bypass capability token"""

        # 1. Validate requester is authorized (whitelist check)
        if requester not in ["arbiter_agent", "safety_checker", "audit_logger", "emergency_handler"]:
            raise PermissionError(f"Requester {requester} not authorized for bypass")

        # 2. Create token
        now_ms = time.time_ns() // 1_000_000
        capability = BypassCapability(
            capability_id=uuid.uuid4().hex,
            operation_type=operation_type,
            requester=requester,
            issued_at_ms=now_ms,
            expires_at_ms=now_ms + 300_000,  # 5min TTL
            reason=reason,
            privacy_band=privacy_band,
            priority=priority,
            signature=b""  # Placeholder
        )

        # 3. Sign token (HMAC-SHA256)
        payload = f"{capability.capability_id}:{capability.requester}:{capability.issued_at_ms}"
        signature = hmac.new(self.secret_key, payload.encode(), hashlib.sha256).digest()
        capability.signature = signature

        # 4. Log issuance (audit trail)
        self.audit_log.write(
            event="capability_issued",
            capability_id=capability.capability_id,
            requester=requester,
            operation_type=operation_type,
            privacy_band=privacy_band.value,
            priority=priority.value,
            reason=reason
        )

        return capability

    def verify_bypass_capability(self, capability: BypassCapability) -> bool:
        """Verify capability token is valid"""

        # 1. Check expiration
        now_ms = time.time_ns() // 1_000_000
        if now_ms > capability.expires_at_ms:
            logger.warning("capability_expired", capability_id=capability.capability_id)
            return False

        # 2. Verify signature
        payload = f"{capability.capability_id}:{capability.requester}:{capability.issued_at_ms}"
        expected_sig = hmac.new(self.secret_key, payload.encode(), hashlib.sha256).digest()

        if not hmac.compare_digest(capability.signature, expected_sig):
            logger.error("capability_signature_invalid", capability_id=capability.capability_id)
            return False

        # 3. Verify requester still authorized (revocation check)
        if capability.requester in self.revoked_requesters:
            logger.error("capability_revoked", requester=capability.requester)
            return False

        return True
```

---

### **Bypass Logic Integration (3 Tiers)**

**Tier 1: Per-Stream Watermark Bypass**

```python
# k1/infrastructure/backpressure/watermark_checker.py
async def check_admission(
    self,
    operation: Operation,
    capability: BypassCapability | None
) -> tuple[bool, str]:
    """
    Check if operation should be admitted to queue

    Returns:
        (admitted: bool, reason: str)
    """

    # 1. Check bypass capability first
    if capability is not None and self.capability_mgr.verify_bypass_capability(capability):
        # Log bypass event
        self.audit_log.write(
            event="backpressure_bypassed",
            stream=self.stream_name,
            operation_id=operation.id,
            capability_id=capability.capability_id,
            watermark_level=self.state.current_level.value
        )

        # Emit metrics
        self.metrics.backpressure_bypass_total.labels(
            stream=self.stream_name,
            reason="capability"
        ).inc()

        return (True, "bypassed_via_capability")

    # 2. Check privacy band bypass (RED band always bypasses)
    if operation.privacy_band == PrivacyBand.RED:
        # Log bypass event
        self.audit_log.write(
            event="backpressure_bypassed",
            stream=self.stream_name,
            operation_id=operation.id,
            privacy_band="RED",
            watermark_level=self.state.current_level.value
        )

        # Emit metrics
        self.metrics.backpressure_bypass_total.labels(
            stream=self.stream_name,
            reason="red_band"
        ).inc()

        return (True, "bypassed_red_band")

    # 3. Check priority bypass (CRITICAL always bypasses)
    if operation.priority == Priority.CRITICAL:
        # Log bypass event
        self.audit_log.write(
            event="backpressure_bypassed",
            stream=self.stream_name,
            operation_id=operation.id,
            priority="CRITICAL",
            watermark_level=self.state.current_level.value
        )

        # Emit metrics
        self.metrics.backpressure_bypass_total.labels(
            stream=self.stream_name,
            reason="critical_priority"
        ).inc()

        return (True, "bypassed_critical_priority")

    # 4. No bypass, apply normal watermark checks
    current_depth = await self.get_queue_depth()
    level, action = self.evaluate(current_depth)

    if level == WatermarkLevel.REJECT:
        return (False, "rejected_watermark_95pct")
    elif level == WatermarkLevel.DEGRADE:
        # Apply degradation action but admit
        await self.apply_action(action)
        return (True, "admitted_with_degradation")
    else:
        return (True, "admitted_normal")
```

**Tier 2: Voice Pipeline Bypass**

```python
# k1/infrastructure/backpressure/voice_pipeline_monitor.py
async def check_voice_admission(
    self,
    stage: str,
    operation: Operation,
    capability: BypassCapability | None
) -> bool:
    """Check admission for voice pipeline stage"""

    # 1. RED band bypass
    if operation.privacy_band == PrivacyBand.RED:
        self.metrics.voice_bypass_total.labels(stage=stage, reason="red_band").inc()
        return True

    # 2. CRITICAL priority bypass
    if operation.priority == Priority.CRITICAL:
        self.metrics.voice_bypass_total.labels(stage=stage, reason="critical_priority").inc()
        return True

    # 3. Capability bypass
    if capability and self.capability_mgr.verify_bypass_capability(capability):
        self.metrics.voice_bypass_total.labels(stage=stage, reason="capability").inc()
        return True

    # 4. Normal backpressure logic
    buffer_pct = await self.get_buffer_utilization(stage)

    if buffer_pct >= 95:
        return False  # Reject
    else:
        return True   # Admit
```

**Tier 3: Global Limits Bypass**

```python
# k1/infrastructure/backpressure/global_limits_enforcer.py
async def check_global_admission(
    self,
    operation: Operation,
    capability: BypassCapability | None
) -> bool:
    """Check admission against global limits"""

    # 1. Bypass checks (RED band, CRITICAL, capability)
    if (operation.privacy_band == PrivacyBand.RED or
        operation.priority == Priority.CRITICAL or
        (capability and self.capability_mgr.verify_bypass_capability(capability))):

        self.metrics.global_bypass_total.inc()
        return True

    # 2. Check global memory limit
    total_memory_mb = await self.get_total_memory_mb()
    if total_memory_mb >= 512:  # 512MB max
        return False

    # 3. Check global queue items limit
    total_items = await self.get_total_queue_items()
    if total_items >= 5000:  # 5000 items max
        return False

    return True
```

---

### **Rate Limiting on Bypass (Safety Valve)**

**Purpose:** Prevent bypass abuse (e.g., bug in arbiter flooding system with CRITICAL priority requests)

**Implementation:**

```python
# k1/infrastructure/backpressure/bypass_rate_limiter.py
class BypassRateLimiter:
    """Rate limit bypass traffic to prevent abuse"""

    def __init__(self, max_bypass_rps: int = 1000):
        self.max_bypass_rps = max_bypass_rps
        self.token_bucket = TokenBucket(rate=max_bypass_rps, burst=max_bypass_rps * 1.5)

    async def check_bypass_rate_limit(self, operation: Operation) -> bool:
        """
        Check if bypass traffic is within rate limit

        Returns:
            True if within limit, False if rate limit exceeded
        """

        if self.token_bucket.consume(1):
            return True  # Within limit
        else:
            # Rate limit exceeded, log and reject
            logger.critical(
                "bypass_rate_limit_exceeded",
                operation_id=operation.id,
                priority=operation.priority.value,
                privacy_band=operation.privacy_band.value
            )

            self.metrics.bypass_rate_limit_exceeded_total.inc()

            return False  # Rate limit exceeded
```

**Rate Limit Values:**

| Traffic Type | Rate Limit | Burst | Rationale |
|--------------|------------|-------|-----------|
| **Bypass (all)** | 1000 req/s | 1500 req/s | Prevents bypass abuse |
| **RED band** | 500 req/s | 750 req/s | Subset of bypass |
| **CRITICAL priority** | 500 req/s | 750 req/s | Subset of bypass |
| **Audit logging** | 2000 req/s | 3000 req/s | Higher limit (compliance) |

**Rate Limit Enforcement Point:**

- **K1 Ingress (API Gateway)**: Rate limit enforced before admission to queues
- **Benefit**: Prevents malicious/buggy clients from exhausting bypass capacity
- **Trade-off**: Even legitimate bypass traffic rejected if rate limit exceeded (rare)

---

### **Audit Logging (Compliance)**

**Audit Log Schema:**

```python
@dataclass
class BackpressureBypassAuditEvent:
    """Audit log entry for bypass event"""

    event_id: str                   # Unique event ID
    timestamp_ms: int               # Event timestamp (milliseconds)
    operation_id: str               # Operation that bypassed
    operation_type: str             # "arbiter_approval", "safety_check", etc.
    requester: str                  # Component that requested bypass
    bypass_reason: str              # "red_band", "critical_priority", "capability"
    capability_id: str | None       # Capability token ID (if applicable)
    privacy_band: str               # "GREEN", "AMBER", "RED"
    priority: str                   # "CRITICAL", "REALTIME", "INTERACTIVE", "BACKGROUND"
    watermark_level: str            # Watermark state at bypass time ("NORMAL", "WARN", "DEGRADE", "REJECT")
    stream: str | None              # Stream name (if Tier 1 bypass)
    voice_stage: str | None         # Voice stage (if Tier 2 bypass)
    global_memory_mb: float         # Global memory at bypass time
    global_queue_items: int         # Global queue items at bypass time
    cognitive_trace_id: str         # Trace ID for correlation
```

**Audit Log Destination:**

- **Primary**: Append-only audit log file (`/var/log/k1/backpressure_bypass_audit.log`)
- **Secondary**: S3 bucket with versioning and object lock (tamper-proof)
- **Retention**: 7 years (compliance requirement: HIPAA, GDPR)

**Audit Log Query Examples:**

```bash
# Query 1: Count bypass events by reason (last 24h)
jq -r '[.bypass_reason] | group_by(.) | map({reason: .[0], count: length})' \
  /var/log/k1/backpressure_bypass_audit.log

# Output:
# [
#   {"reason": "red_band", "count": 1247},
#   {"reason": "critical_priority", "count": 523},
#   {"reason": "capability", "count": 89}
# ]

# Query 2: Find all bypasses during REJECT watermark
jq -r 'select(.watermark_level == "REJECT")' \
  /var/log/k1/backpressure_bypass_audit.log

# Query 3: Identify requesters with >1000 bypasses (potential abuse)
jq -r '[.requester] | group_by(.) | map({requester: .[0], count: length}) | sort_by(.count) | reverse | .[0:10]' \
  /var/log/k1/backpressure_bypass_audit.log
```

---

### **Emergency Shutdown Handling**

**Scenario:** User triggers emergency shutdown (e.g., detects system compromise, user distress signal)

**Requirements:**
- **Immediate action**: Shutdown must complete within 500ms
- **No backpressure**: Shutdown signal bypasses all queues
- **Graceful termination**: All agents notified before termination
- **Audit logging**: Shutdown event logged with full context

**Implementation:**

```python
# k1/security/emergency_handler.py
class EmergencyHandler:
    """Handle emergency shutdown signals"""

    async def trigger_shutdown(
        self,
        reason: str,
        user_id: str | None,
        cognitive_trace_id: str
    ):
        """
        Trigger emergency shutdown (CRITICAL priority, bypasses backpressure)

        Args:
            reason: Human-readable shutdown reason
            user_id: User who triggered shutdown (if applicable)
            cognitive_trace_id: Trace ID for correlation
        """

        # 1. Issue bypass capability
        capability = self.capability_mgr.issue_bypass_capability(
            operation_type="emergency_shutdown",
            requester="emergency_handler",
            reason=reason,
            privacy_band=PrivacyBand.RED,  # Treat as RED band
            priority=Priority.CRITICAL
        )

        # 2. Create shutdown operation
        shutdown_op = Operation(
            operation_id=uuid.uuid4().hex,
            operation_type="emergency_shutdown",
            priority=Priority.CRITICAL,
            privacy_band=PrivacyBand.RED,
            cognitive_trace_id=cognitive_trace_id
        )

        # 3. Send shutdown signal to all agents (bypasses backpressure)
        await self.router.broadcast(
            message=ShutdownSignal(reason=reason),
            capability=capability,
            timeout_ms=500  # 500ms max
        )

        # 4. Audit log shutdown event
        self.audit_log.write(
            event="emergency_shutdown",
            operation_id=shutdown_op.operation_id,
            reason=reason,
            user_id=user_id,
            capability_id=capability.capability_id,
            cognitive_trace_id=cognitive_trace_id
        )

        # 5. Emit metrics
        self.metrics.emergency_shutdown_total.labels(reason=reason).inc()

        logger.critical("emergency_shutdown_triggered", reason=reason, user_id=user_id)
```

---

## Consequences

### **Positive**

✅ **Safety guaranteed**: RED band operations never blocked, compliance maintained
✅ **Capability-based security**: Bypass requires token, prevents abuse
✅ **Comprehensive audit**: 7-year retention, tamper-proof logging
✅ **Rate limiting**: Bypass traffic limited (1000 req/s), prevents runaway abuse

### **Negative**

⚠️ **Bypass capacity risk**: If bypass traffic exceeds 1000 req/s, even legitimate RED band rejected
⚠️ **Complexity**: 3-tier bypass logic (per-stream, voice, global) requires careful testing
⚠️ **Audit storage**: 7-year retention requires significant storage (estimate: 10GB/year)

---

## References

- [ADR-0061: 3-Tier Backpressure Cascade](0061-3-tier-backpressure-cascade.md) — Parent ADR
- [ADR-0002: Actor Model Agent Isolation](0002-actor-model-agent-isolation.md) — Capability-based access control
- HIPAA Security Rule: 45 CFR § 164.312 (Technical Safeguards)
- GDPR Article 32: Security of Processing
- PCI-DSS Requirement 10: Track and monitor all access to network resources

---

**Status:** Proposed
**Implementation:** Phase 2 (Week 2) - Tier 2 voice pipeline (includes bypass logic)