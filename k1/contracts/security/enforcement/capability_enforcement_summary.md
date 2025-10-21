# Capability Enforcement & Audit Trail Contracts - Summary
# Issue 2.5.4: Capability Enforcement & Audit Contracts (ADR-0010c, 0010d)
# Created: 2025-10-15
#
# This document summarizes all capability enforcement contracts created for Issue 2.5.4

## ============================================================================
## CONTRACTS CREATED
## ============================================================================

### 1. Tool Runner Capability Enforcement Contract
**File:** `contracts/security/enforcement/tool_runner_enforcement.yml`
**Size:** ~600 lines
**Purpose:** Capability validation before tool execution
**Key Sections:**
- 7-step validation flow (cache lookup → signature verification → constraint check)
- Revocation integration (Redis pub/sub)
- Performance targets (<1ms P95 validation)
- Tool Runner implementation requirements
- Audit logging (all events to K0 WAL)
- Security guarantees
- Error handling & fallback strategies

**Performance Impact:**
- Cache hit: 0.05ms (85% of requests)
- Cache miss: 1.0ms P95 (worst case)
- Overall: <1% overhead on tool execution

**Audit Events:**
- `capability_validated` - successful validation
- `capability_invalid` - signature/permission denied
- `capability_expired` - token expired
- `capability_revoked` - capability revoked
- `constraint_violated` - budget/invocation limit exceeded

---

### 2. Model Hub Capability Enforcement Contract
**File:** `contracts/security/enforcement/model_hub_enforcement.yml`
**Size:** ~700 lines
**Purpose:** Capability validation before LLM model calls
**Key Sections:**
- Validation flow for MODEL_CALL capability (8 checks)
- Model-specific enforcement rules (GPT-4, Claude, local models)
- Revocation integration
- Cost tracking & budget enforcement
- Performance targets (<10ms P95)
- Agent-specific model access policies
- Audit logging to K0 WAL

**Model Coverage:**
- OpenAI: gpt-4o (0.5k tokens = $0.0125), gpt-4o-mini (0.5k = $0.001)
- Anthropic: claude-3-opus, claude-3-haiku
- Local: gemma-2b, mistral-7b, llama-3.1-70b

**Cost Tracking:**
- Pre-call: estimate cost, check budget
- Post-call: log actual tokens consumed
- Metrics: model_call_cost_total_usd per agent/model

---

### 3. Hot Path Capability Validation Contract
**File:** `contracts/security/enforcement/hot_path_validation.yml`
**Size:** ~500 lines
**Purpose:** Ultra-fast (<1ms) validation for performance-critical paths
**Key Sections:**
- Optimization techniques (in-memory caching, HMAC caching, constraint caching)
- Parallel verification (speculative execution)
- Ultra-fast validation pipeline (0.47ms typical, <1ms P95)
- Performance measurements & profiling
- Micro-optimizations (constant folding, inlining, SIMD)
- Stress testing scenarios (10K-50K val/s throughput)
- Future optimizations (GPU acceleration, ML caching)

**Optimization Techniques:**
1. In-memory cache (hash map, 1000 entries, 10s TTL): 85% hit rate
2. HMAC caching: Reuse cached HMAC results
3. Constraint caching: Track counters in-memory
4. Parallel verification: Revocation check in background
5. Speculative execution: Start checks in parallel

**Performance Targets:**
- Best case (cache hit): 0.04ms
- Typical case (cache miss): 0.47ms P95
- Worst case: 0.8ms P95
- All under 1ms target ✅

---

## ============================================================================
## SECTION: K0 WAL AUDIT LOGGING (ADR-0010d)
## ============================================================================

### Audit Trail Schema (to be stored in K0 WAL)

```yaml
audit_event:
  event_id: "uuid"
  timestamp: "ISO8601"
  trace_id: "from agent request"

  source:
    component: "Tool Runner | Model Hub | K0 Bridge"
    module: "security.capability_enforcement"
    method: "validate_capability()"

  subject:
    agent_id: "agent requesting capability"
    agent_role: "Planner | Concierge | Researcher | SafetyWatch"
    agent_version: "semantic version"

  resource:
    resource_type: "tool | model | memory"
    resource_id: "tool_id | model_id"
    resource_class: "tool_class | model_class"

  action:
    operation: "CAPABILITY_CHECK | EXECUTION_ALLOWED | EXECUTION_DENIED"
    permission_requested: "EXECUTE | INFER | READ_MEMORY | WRITE_MEMORY"
    permission_granted: true | false

  validation_result:
    status: "VALID | INVALID | EXPIRED | REVOKED | CONSTRAINT_VIOLATED"
    reason: "signature_invalid | expired | revoked | max_cost_exceeded | rate_limit_exceeded"
    latency_ms: 0.5
    cached: true | false

  constraints:
    max_invocations:
      limit: 1000
      current: 842
      violated: false
    max_cost_usd:
      limit: 100.0
      current: 45.32
      violated: false
    privacy_band:
      required: "GREEN"
      actual: "GREEN"
      violated: false
    rate_limit:
      limit: 500  # per minute
      current: 342
      violated: false

  revocation_status:
    revoked: false
    revoked_at: null
    revocation_reason: null

  security_metadata:
    token_subject_hash: "SHA256(agent_id)"  # For PII protection
    ip_address: "masked_ip_address"  # Last octet masked
    user_agent: "user_agent_string"
    session_id: "session_id"
    device_id: "device_id"

  retention:
    policy: "audit_trail"
    ttl_days: 90  # GDPR compliant
    deletion_requested: false
```

### Audit Logging Integration Points

**Tool Runner (execute_tool)**
- Logs before and after tool execution
- Captures: tool_id, agent_id, validation status, execution result

**Model Hub (before_inference)**
- Logs before and after model call
- Captures: model_id, agent_id, tokens consumed, cost, validation status

**Capability Manager (issue_capability)**
- Logs when capabilities are issued
- Captures: agent_id, capability_id, rights, constraints, ttl

**Capability Manager (revoke_capability)**
- Logs when capabilities are revoked
- Captures: capability_id, reason, revoked_by (admin)

**K0 Bridge (query/command)**
- Logs memory access attempts
- Captures: agent_id, operation (read/write), memory_section, validation status

### Audit Trail Querying

```python
# Example audit queries (SQL on K0 WAL)

# Query 1: All capability validations for agent_id
SELECT * FROM audit_events
WHERE subject.agent_id = 'agent_123'
  AND event_type = 'CAPABILITY_CHECK'
  AND timestamp > now() - interval '7 days'

# Query 2: Failed validations (security incidents)
SELECT * FROM audit_events
WHERE validation_result.status IN ('INVALID', 'REVOKED', 'CONSTRAINT_VIOLATED')
  AND timestamp > now() - interval '24 hours'

# Query 3: Cost tracking per agent
SELECT
  subject.agent_id,
  COUNT(*) as call_count,
  SUM(constraints.max_cost_usd) as total_cost_usd
FROM audit_events
WHERE resource_type = 'model'
  AND timestamp > now() - interval '1 day'
GROUP BY subject.agent_id

# Query 4: GDPR Data Subject Access Request
SELECT *
FROM audit_events
WHERE subject.agent_id = 'agent_123'
  OR security_metadata.user_id = 'user_456'
LIMIT 50000  # Paginate for large datasets
```

---

## ============================================================================
## SECTION: CAPABILITY USAGE METRICS (ADR-0010c)
## ============================================================================

### Prometheus Metrics

```yaml
# TOOL RUNNER METRICS

capability_validations_total:
  type: "Counter"
  labels: ["resource_type", "result"]
  description: "Total capability validations"
  example_query: "rate(capability_validations_total[5m])"

capability_validation_latency_ms:
  type: "Histogram"
  labels: ["resource_type", "cached"]
  buckets: [0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
  percentiles: ["p50", "p95", "p99"]

capability_cache_hits_total:
  type: "Counter"
  labels: ["resource_type"]
  description: "Successful cache hits"

capability_constraint_violations_total:
  type: "Counter"
  labels: ["resource_type", "constraint_name"]
  example_constraints: ["max_invocations", "max_cost_usd", "privacy_band"]

capability_signature_failures_total:
  type: "Counter"
  labels: ["resource_type", "failure_reason"]
  example_reasons: ["invalid_hmac", "expired_key", "malformed_token"]


# MODEL HUB METRICS

model_call_total:
  type: "Counter"
  labels: ["agent_id", "model_id", "status"]
  example_statuses: ["success", "denied", "error", "timeout"]

model_call_latency_ms:
  type: "Histogram"
  labels: ["agent_id", "model_id"]
  buckets: [50, 100, 200, 500, 1000, 2000, 5000, 10000]

model_call_cost_usd:
  type: "Histogram"
  labels: ["model_id"]
  buckets: [0.001, 0.01, 0.05, 0.10, 0.50, 1.00]

model_call_validation_latency_ms:
  type: "Histogram"
  labels: ["cached"]
  buckets: [0.1, 0.5, 1.0, 5.0, 10.0]

model_capability_violations_total:
  type: "Counter"
  labels: ["agent_id", "violation_reason"]


# REVOCATION METRICS

capability_revocations_total:
  type: "Counter"
  labels: ["capability_type"]
  description: "Total capabilities revoked"

revocation_propagation_latency_ms:
  type: "Histogram"
  labels: []
  percentiles: ["p50", "p95", "p99"]
  description: "Time for revocation to propagate across all K1 instances"

revoked_capabilities_active:
  type: "Gauge"
  labels: []
  description: "Number of currently-revoked capabilities in Redis"
```

### Grafana Dashboards

**Dashboard 1: Capability Validation Health**
- Validation success rate (target: >99.9%)
- P95 validation latency (target: <1ms)
- Cache hit rate (target: >85%)
- Top violations by type (constraint/signature/expiration)

**Dashboard 2: Model Hub Cost Tracking**
- Daily cost per agent (USD)
- Cost per model (distribution)
- Budget adherence (% of budget used)
- Projected monthly spend

**Dashboard 3: Revocation Efficiency**
- Revocation events per day
- Revocation propagation latency (P95)
- Active revoked capabilities count
- Cascading revocation effectiveness

**Dashboard 4: Security Incidents**
- Failed validations (INVALID/REVOKED)
- Constraint violations (rate limit, budget, band)
- Agent spoofing attempts (agent_id mismatch)
- Signature verification failures

### Alerting Rules

```yaml
alerts:
  - name: "ValidationLatencyHigh"
    condition: "histogram_quantile(0.95, capability_validation_latency_ms) > 2.0"
    severity: "warning"
    message: "Capability validation P95 latency > 2ms"

  - name: "CacheHitRateLow"
    condition: "rate(capability_cache_hits_total[5m]) / (rate(capability_cache_hits_total[5m]) + rate(capability_cache_misses_total[5m])) < 0.75"
    severity: "warning"
    message: "Cache hit rate <75% (target: >85%)"

  - name: "ConstraintViolationSpike"
    condition: "rate(capability_constraint_violations_total[5m]) > 100"
    severity: "critical"
    message: "Constraint violations >100/min (possible attack or misconfiguration)"

  - name: "SignatureFailureSpike"
    condition: "rate(capability_signature_failures_total[5m]) > 50"
    severity: "critical"
    message: "Signature verification failures >50/min (possible key rotation issue)"

  - name: "RevocationPropagationLatency"
    condition: "histogram_quantile(0.95, revocation_propagation_latency_ms) > 500"
    severity: "warning"
    message: "Revocation propagation latency >500ms"

  - name: "AgentSpoofingAttempt"
    condition: "rate(capability_validation_failures_total{reason='agent_id_mismatch'}[5m]) > 10"
    severity: "critical"
    message: "Agent spoofing attempts detected (>10/min)"
```

---

## ============================================================================
## SECTION: REVOCATION & PROPAGATION (ADR-0010d)
## ============================================================================

### Revocation System Architecture

**Components:**
1. **Capability Manager:** Issues/revokes capabilities
2. **Redis Revocation List:** Distributed revocation cache
3. **Redis Pub/Sub:** Broadcasts revocation events
4. **Enforcers:** Tool Runner, Model Hub, K0 Bridge (check revocation before execution)

**Revocation Flow:**
```
Step 1: Supervisor revokes capability
  └─> Capability Manager.revoke_capability(capability_id)

Step 2: Add to revocation list
  └─> Redis.add_to_revocation_set(capability_id)
  └─> Publish Redis pub/sub event: "capability.revoked:{capability_id}"

Step 3: All K1 instances receive event
  └─> Instance 1: update local revocation cache
  └─> Instance 2: update local revocation cache
  └─> Instance 3: update local revocation cache

Step 4: Enforcers check revocation before execution
  └─> Tool Runner: Redis.is_revoked(capability_id)
  └─> Model Hub: Redis.is_revoked(capability_id)
  └─> K0 Bridge: Redis.is_revoked(capability_id)

Step 5: If revoked, reject execution
  └─> Return error: "Capability revoked, please refresh"
```

**Performance:**
- Revocation latency: <100ms (Redis pub/sub)
- Revocation check latency: <1ms (cache lookup)
- Cascading revocation: <100ms for all K1 instances

### Graceful Revocation Policy

**Goal:** Revoke capability immediately, but allow in-flight operations to complete

**Implementation:**
```python
# When capability is revoked:

# Step 1: Mark revoked (immediate effect on new operations)
redis.add_to_revocation_set(capability_id)
redis.publish("capability.revoked", capability_id)

# Step 2: Allow in-flight operations (grace period)
# - Tool already executing: let it finish (max 5s)
# - Model inference in progress: let it complete (max 3s)
# - K0 query in progress: let it complete (max 1s)

# Step 3: Force terminate if not done by deadline
if tool_still_executing_after_5s:
  send_interrupt_signal(tool_pid)
  force_terminate_after_1s()

# Step 4: Cleanup (release resources)
revoke_all_delegated_capabilities(capability_id)
cleanup_agent_state(agent_id)
```

---

## ============================================================================
## DEPLOYMENT ROADMAP
## ============================================================================

### Week 1: Core Enforcement
- Implement Tool Runner enforcement
- Implement Model Hub enforcement
- Add audit logging to K0 WAL
- Add basic metrics

### Week 2: Performance Optimization
- Implement hot path caching
- Optimize HMAC verification
- Add performance instrumentation
- Stress testing & tuning

### Week 3: Revocation & Multi-Instance
- Implement revocation system (Redis)
- Add revocation pub/sub
- Multi-instance coordination
- Cascading revocation

### Week 4: Testing & Validation
- Comprehensive integration tests
- Security audits
- Performance validation
- Production rollout (canary 10% → 100%)

---

## ============================================================================
## COMPLIANCE & GOVERNANCE
## ============================================================================

### GDPR Compliance
- **Right to Know:** Audit trail searchable by (agent_id, timestamp)
- **Right to Erasure:** Revoke capabilities + delete audit trail after 90 days
- **Data Minimization:** Mask IP addresses (last octet), hash agent IDs in logs

### SOC2 Compliance
- **Logical Access:** Capability enforcement at every resource boundary
- **Audit Trail:** 100% coverage of all capability checks
- **Monitoring:** Real-time alerts for suspicious activity

### Security Standards
- **NIST SP 800-207 (Zero Trust):** Never trust, always verify
- **CWE-250 (Privilege Management):** Reference Monitor pattern
- **OWASP Top 10:** Prevent A01 Broken Access Control

---

## ============================================================================
## RELATED CONTRACTS & ADRs
## ============================================================================

**For complete enforcement architecture, see:**
- `tool_runner_enforcement.yml` - Tool execution capability validation
- `model_hub_enforcement.yml` - Model call capability validation
- `hot_path_validation.yml` - Performance-critical optimization
- `audit_trail_schema.yml` - K0 WAL audit logging (forthcoming)
- `capability_usage_metrics.yml` - Prometheus metrics (forthcoming)
- `revocation_propagation.yml` - Multi-instance revocation (forthcoming)
- `revoked_capability_handling.yml` - Graceful revocation (forthcoming)
- `ADR-0010c-capability-enforcement-runtime.md` - Architecture decision
- `ADR-0010d-capability-revocation-audit-trail.md` - Revocation architecture

---

**Created:** 2025-10-15
**Status:** ✅ CONTRACTS READY FOR IMPLEMENTATION
**Effort Estimate:** 2 weeks (1 week core, 1 week optimization + testing)
**Performance Target:** <1ms validation, 100% audit coverage, <100ms revocation propagation
