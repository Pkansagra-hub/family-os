# Clarification Protocol & Barge-In Protocol - Comprehensive Contracts Summary

**Creation Date:** 2025-10-16  
**ADR References:** ADR-0003b (6 Core Protocol Implementations), ADR-0003 (MPST Protocol Validation)  
**Status:** ✅ COMPLETED (Issue 2.6.3 & 2.6.4)

---

## 📋 Overview

Comprehensive contracts created for two critical K1 protocols with deep analysis across all spheres:
- **Observability** (Prometheus metrics, OpenTelemetry tracing, structured logging)
- **Security** (Authentication, authorization, audit trails, PII protection)
- **Performance** (Latency budgets, SLOs, error budgets)
- **Reliability** (Timeout policies, fallback strategies, state management)
- **Compliance** (GDPR, HIPAA, SOC2)

---

## 📁 Clarification Protocol Contracts (5 files)

**Location:** `contracts/protocols/clarification/`

### 1. clarification_protocol_fsm.yml
**Purpose:** FSM definition with all states and transitions  
**Key Features:**
- 3-state FSM: `start` → `request_sent` → `waiting_response` → `resolved`/`timeout`/`fallback`/`cancelled`
- Priority levels: `BLOCKING` (60s, no fallback), `OPTIONAL` (30s, with fallback), `LOW` (10s, best-effort)
- Force modes: graceful drain vs immediate termination
- Timeout policies with sub-timeouts for monitoring
- Performance: <500ms P95 roundtrip (excluding user think time)

**Metrics:**
- `clarification_request_generated_total` (by agent, priority, question_type)
- `clarification_response_rate` target: >95%
- `clarification_timeout_percentage` target: <5%

---

### 2. clarification_request_contract.yml
**Purpose:** ClarificationRequest message schema (FlatBuffers)  
**Key Fields:**
- `clarification_id` (UUID v4)
- `question` (max 1000 chars)
- `options` (2-10 choices for multiple_choice)
- `fallback_answer` (for OPTIONAL priority)
- `priority` (BLOCKING/OPTIONAL/LOW)
- `timeout_ms` (default 60s, configurable)
- `pii_detected` / `pii_redaction_applied` flags
- `agent_confidence` (0.0-1.0)

**Observability:**
- Logged with PII redaction
- Metrics: requests_generated_total, by_agent, by_priority
- Distributed tracing via `cognitive_trace_id`

**Security:**
- Privacy bands: GREEN/AMBER/RED/BLACK
- Audit trail in k0_clarification_audit_log

---

### 3. clarification_response_contract.yml
**Purpose:** ClarificationResponse message schema (FlatBuffers)  
**Key Fields:**
- `response_id` (UUID v4)
- `clarification_id` (references request)
- `answer` (user's response)
- `user_confidence` (0.0-1.0)
- `implicit_confidence` (inferred from response characteristics)
- `response_time_ms` (100-300000ms)
- `hesitation_indicators` (typing delays, corrections)
- `pii_detected` flag

**Quality Metrics:**
- `quality_score` = 0.5×confidence + 0.3×(1-hesitation) + 0.2×(1-corrections)
- Ambiguity detection
- Response validation

**Observability:**
- `clarification_response_time_ms` histogram (SLO target: P95 <5s)
- Implicit confidence histogram
- Validation error tracking

---

### 4. observability_metrics.yml
**Comprehensive Observability Contract**

**Prometheus Metrics (20+ counters, histograms, gauges):**

*Counters:*
- `clarification_request_generated_total`
- `clarification_response_received_total`
- `clarification_timeout_total`
- `clarification_fallback_applied_total`
- `clarification_pii_detected_total`
- `clarification_security_violation_total`

*Histograms:*
- `clarification_response_time_ms` (P95 <5000ms)
- `clarification_latency_ms` (P95 <500ms)
- `clarification_confidence_histogram`

*Gauges:*
- `clarification_active_total`
- `clarification_response_rate` (SLO: >95%)
- `clarification_timeout_percentage` (SLO: <5%)

**Distributed Tracing:**
- Spans: `clarification_request_generated`, `clarification_waiting`, `clarification_response_received`, `clarification_complete`
- Dynamic sampling: 100% for BLOCKING, 10% for OPTIONAL
- Parent trace from parent protocol

**Structured Logging:**
- JSON format with trace correlation
- Fields: clarification_id, agent_id, priority, timeout_ms, response_time_ms, confidence

**Dashboards & Alerts:**
- Grafana dashboard: "Clarification Protocol - Overview"
- Alert: `HighClarificationTimeoutRate` (>10%)
- Alert: `LowClarificationResponseRate` (<90%)
- Alert: `ClarificationSecurityViolation` (critical)

**SLOs:**
- Response Rate ≥95% (error budget: 5%)
- Latency P95 <500ms (error budget: 50ms)
- Timeout Rate <5% (error budget: 5%)
- Security Compliance: 0% violations (error budget: 0%, zero tolerance)

---

### 5. security_privacy_audit.yml
**Comprehensive Security & Compliance Contract**

**Privacy Bands:**
- `GREEN`: Public, no PII → stored in k0_clarification_log, 90-day retention
- `AMBER`: Identifiable, low sensitivity → encrypted storage, 30-day retention
- `RED`: Highly sensitive (health/financial) → AWS KMS vault, 7-day retention
- `BLACK`: Restricted → audit-only, special handling

**PII Detection & Redaction:**
- Hybrid: Regex patterns + BERT-NER ML model
- Regex: Email, SSN, phone, credit card (100% precision)
- BERT-NER: Person, location, organization entities (95% recall, <5ms latency)
- Redaction strategies: Hash (email), Vault (SSN/CC), Tokenization (names/addresses)

**Audit Trail (7-year retention, GDPR/HIPAA compliant):**
- Events: request_generated, response_received, timeout, deletion
- Immutable: HMAC-SHA256 per record
- Tamper detection: Immediate alert
- Access control: Security team read, compliance officer audit

**Compliance:**
- GDPR: Article 17 (Right to Erasure), Article 13 (Information), Article 20 (Portability)
- HIPAA: PHI encryption, access logs, minimum necessary
- PCI DSS: Credit card tokenization, TLS 1.2+
- SOC2: Audit controls, access controls

---

## 📁 Barge-In Protocol Contracts (5 files)

**Location:** `contracts/protocols/barge_in/`

### 1. barge_in_protocol_fsm.yml
**Purpose:** FSM definition with interrupt handling  
**Key Features:**
- 4-state FSM: `streaming` → `interrupted` → `draining` → `resumed`/`terminated`/`timeout`
- Interrupt reasons: `STOP` (immediate), `NEW_INPUT` (graceful), `RECONSIDER`, `CLARIFICATION`
- Force modes: `graceful` (500ms drain), `immediate` (10ms termination)
- 6 transitions with latency budgets
- State capture for resumption

**Performance Targets:**
- Interrupt latency: <120ms P95 (5+10+5+10+5+20 budget allocation)
- Drain time: <500ms hard timeout
- Max concurrent: unlimited (one per session)

---

### 2. barge_in_signal_contract.yml
**Purpose:** BargeInSignal message schema (FlatBuffers)  
**Key Fields:**
- `signal_id` (UUID v4)
- `reason` (STOP/NEW_INPUT/RECONSIDER/CLARIFICATION)
- `force_mode` (graceful/immediate)
- `force_timeout_ms` (100-5000ms)
- `new_input` (if reason==NEW_INPUT)
- `priority` (URGENT/HIGH/NORMAL)
- `authentication_token` (JWT validation)
- `signature` (HMAC-SHA256 for tamper detection)

**Security:**
- User authentication required
- Session validation
- Device binding
- Rate limiting: max 10 signals/second
- HMAC signature verification

**Latency:**
- <5ms to receive and validate
- <120ms critical path (user click to agent paused)

---

### 3. drain_resume_contract.yml
**Purpose:** Drain and resumption handshake messages  
**Key Messages:**

*DrainStatus (Agent → Orchestrator):*
- `drain_status` (INITIATED/RUNNING/COMPLETED/FAILED/TIMEOUT)
- `tasks_remaining` (how many in-flight tasks)
- `eta_ms` (time to finish)
- `cancellable_count` vs `must_complete_count`
- `state_snapshot` (serialized agent state for resumption)

*ResumptionApproved (Orchestrator → Agent):*
- `new_task_id` (task after resumption)
- `new_task_type` (SAME_TASK_RETRY, NEW_TASK_DIFFERENT_INPUT)
- `preserved_state` (agent state to restore)

*TerminationApproved (Orchestrator → Agent):*
- `cleanup_action` (GRACEFUL_SHUTDOWN, FORCE_KILL, PRESERVE_STATE)

**Performance:**
- Drain: <500ms total
- Resumption: <100ms approval + execution
- State capture: <30ms

---

### 4. observability_metrics.yml
**Comprehensive Observability Contract**

**Prometheus Metrics (25+ counters, histograms, gauges):**

*Counters:*
- `barge_in_signal_received_total`
- `barge_in_interrupt_success_total`
- `barge_in_drain_completed_total`
- `barge_in_timeout_total`
- `barge_in_security_violation_total`

*Histograms:*
- `barge_in_latency_ms` (SLO target: P95 <120ms)
- `barge_in_latency_breakdown_ms` (by component)
- `barge_in_drain_time_ms` (SLO target: P95 <400ms)

*Gauges:*
- `barge_in_active_total`
- `barge_in_success_rate` (SLO: >99%)
- `barge_in_drain_failure_rate` (SLO: <1%)

**Distributed Tracing:**
- Spans: `barge_in_signal_received`, `barge_in_interrupt_delivery`, `agent_drain`, `barge_in_resumption`, `barge_in_complete`
- 100% sampling (all barge-ins traced, critical)
- Parent trace propagated

**Structured Logging:**
- Events: signal_received, drain_started, drain_completed, resumed, errors
- Fields: signal_id, reason, force_mode, tasks_remaining, drain_status
- JSON format with trace correlation

**Dashboards & Alerts:**
- Grafana: "Barge-In Protocol - Overview/Latency/Reliability"
- Alert: `HighInterruptLatency` (>150ms → page engineer)
- Alert: `InterruptSuccessRateLow` (<99% → critical)
- Alert: `StateCorruptionDetected` (→ immediate escalation)

**SLOs:**
- Interrupt Latency: P95 <120ms (error budget: 20ms)
- Interrupt Success Rate: >99% (error budget: 1%)
- Drain Reliability: <1% failure rate (error budget: 1%)
- Security Compliance: 0% violations (zero tolerance)

---

### 5. security_audit.yml
**Comprehensive Security & Compliance Contract**

**Authentication:**
- Session validation (JWT token)
- Device binding (device fingerprint)
- Optional MFA for RED-band sessions

**Authorization:**
- User must have `INTERRUPT_TASK` capability
- User can only interrupt their own tasks (except admins with audit trail)
- Space-level access: GREEN (any user), AMBER (AMBER_ACCESS), RED (RED_ACCESS), BLACK (restricted)

**Threat Prevention:**
- **Interrupt Flooding:** Max 10 signals/sec, rate limiting
- **Unauthorized Interrupt:** User A can't interrupt User B's task
- **Session Hijacking:** Device fingerprint + MFA
- **State Manipulation:** Validate drain status state machine
- **Privilege Escalation:** Prevent RED-band interrupt without permission

**Audit Trail (7-year retention, GDPR/SOC2 compliant):**
- Events: signal_received, authorization_check, drain_initiated, resumption_approved, security_violation
- Immutable: HMAC-SHA256 per record
- Tamper detection: Immediate alert
- Access control: Security team full read, compliance audit

**Compliance:**
- GDPR: Secure processing, audit trails
- SOC2 Type II: Security monitoring, incident response
- Incident Response: Unauthorized interrupt, flooding, state corruption

---

## 🎯 Key Achievements

### Observability Comprehensiveness
✅ **Metrics:** 20+ Prometheus metrics per protocol  
✅ **Tracing:** OpenTelemetry spans with parent-child relationships  
✅ **Logging:** Structured JSON with trace correlation  
✅ **Dashboards:** Grafana dashboards with SLO targets  
✅ **Alerts:** Real-time alerts for SLO breaches  

### Security Depth
✅ **Authentication:** Multi-layer (JWT, device, MFA)  
✅ **Authorization:** Capability-based, space-aware  
✅ **PII Protection:** Hybrid ML+regex detection, encryption, vault  
✅ **Audit Trail:** 7-year GDPR/HIPAA compliant, tamper-proof  
✅ **Threat Prevention:** Rate limiting, injection detection, escalation detection  

### Performance & Latency
✅ **Clarification:** <500ms P95 protocol latency (60s user timeout)  
✅ **Barge-In:** <120ms P95 interrupt latency (critical UX)  
✅ **Error Budgets:** Monthly tracking, SLO enforcement  
✅ **Component Breakdown:** Per-stage latency allocation  

### Compliance & Governance
✅ **GDPR:** Right to erasure, data portability, consent  
✅ **HIPAA:** PHI encryption, access logs, minimum necessary  
✅ **SOC2:** Audit controls, security monitoring  
✅ **Immutable Audit:** HMAC-SHA256 tamper protection  

---

## 📊 Contract Statistics

| Metric | Clarification | Barge-In | Total |
|--------|---------------|----------|-------|
| **Contract Files** | 5 | 5 | 10 |
| **Prometheus Metrics** | 20+ | 25+ | 45+ |
| **FSM States** | 7 | 6 | 13 |
| **Audit Events** | 6 | 5 | 11 |
| **SLO Targets** | 4 | 4 | 8 |
| **Compliance Standards** | GDPR, HIPAA, SOC2, PCI DSS | GDPR, SOC2 Type II | Full stack |
| **Latency Budgets (ms)** | 500ms (P95) | 120ms (P95) | Dual budget |
| **Lines of Configuration** | ~1200 YAML | ~1400 YAML | ~2600 |

---

## 🔗 Related Contracts & ADRs

**ADR References:**
- **ADR-0003:** MPST Protocol Validation (parent)
- **ADR-0003a:** Protocol Definition Language (PDL)
- **ADR-0003b:** 6 Core Protocol Implementations (this epic)
- **ADR-0010:** Capability-Based Security
- **ADR-0016:** FlatBuffers Schemas
- **ADR-0024:** Observability & Monitoring
- **ADR-0035:** PII Detection & Redaction
- **ADR-0046:** Barge-In Fast-Path Optimization

**Related Contracts:**
- `contracts/actor_model/mailbox/message_envelope.yml` (base message format)
- `contracts/security/capabilities/capability_token_schema.yml` (auth for interrupts)
- `contracts/privacy/regex_patterns/regex_pattern_registry.yml` (PII detection)
- `contracts/privacy/vault/aes_256_gcm_encryption.yml` (PII storage)

---

## ✅ Completeness Checklist

- [x] FSM definition with all states and transitions
- [x] Message schemas (FlatBuffers compatible)
- [x] Observability (metrics, tracing, logging)
- [x] Security (authentication, authorization, audit)
- [x] PII protection (detection, redaction, vault)
- [x] Compliance (GDPR, HIPAA, SOC2)
- [x] Latency budgets (P95, P99, error budgets)
- [x] Performance targets (throughput, resource usage)
- [x] SLO definitions (target, window, consequence)
- [x] Timeout policies (with sub-timeouts)
- [x] Fallback strategies (graceful degradation)
- [x] Error handling (violations, recovery)
- [x] Composition rules (with other protocols)
- [x] Incident response procedures
- [x] Usage examples (realistic scenarios)

---

## 📝 Notes

1. **User Think Time:** Clarification response time (~5000ms) is NOT part of system SLO (user is external)
2. **Critical Path:** Barge-in <120ms P95 is UX-critical for responsiveness
3. **State Preservation:** Drain captures state for resumption of same task
4. **Error Budget:** Monthly reset enables SLO tracking with tolerance
5. **Security First:** Every signal requires auth+validation before processing
6. **Audit Trail:** Immutable 7-year retention meets regulatory requirements
7. **Composability:** Both protocols properly handle nesting and interruption

---

**Status:** ✅ Ready for implementation  
**Next Steps:** ADR validation, FlatBuffers code generation, implementation in k1/protocols/
