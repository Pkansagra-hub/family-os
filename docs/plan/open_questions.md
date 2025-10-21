# 🤔 OPEN QUESTIONS — K1 Roadmap Blockers & Ambiguities

**Date:** October 16, 2025
**Status:** ACTIVE (Session 4 - Phase 3)
**Total Questions:** 18
**Blocking:** 6 (High Priority)
**Clarification Needed:** 12 (Medium Priority)

---

## 🔴 BLOCKING QUESTIONS (Must Resolve Before Coding)

### Q1: Multi-Device Family Sync Strategy
**Status:** ✅ **RESOLVED (2025-10-16)** → ADR-0050 Family Complete
**Severity:** CRITICAL (was BLOCKING)
**Category:** Q1 Architecture Decision

**Question:**
How should FamilyOS implement multi-device synchronization with device-first, privacy-first design? Three phases:
- **Phase 0 (Prerequisite):** Per-device coherence guarantees (ADR-0050a) ✅
- **Phase 1 (M2-M3, LAN):** mDNS discovery + TCP P07 sync + manual "Sync Now" button (ADR-0050c) ✅
- **Phase 2 (M4-M5, E2EE Internet):** Device certificates + STUN + QUIC + ChaCha20-Poly1305 (ADR-0050d) ✅

**Decision Made:** Device-First Hybrid Strategy ✅
- **No cloud intermediary** - Devices communicate peer-to-peer with privacy-first model
- **CRDT Merge Algorithm** - Last-Write-Wins + device ID ordering + vector clocks (ADR-0050b) ✅
- **LAN Preference** - Devices use local network when home, fallback to E2EE internet when remote
- **Zero-Knowledge Architecture** - No server can read encrypted device data

**Related ADRs (All Complete):**
- ADR-0050 (Multi-Device Family Sync Strategy) ✅ COMPLETE
- ADR-0050a (SessionState Coherence Guarantees - per-device) ✅ COMPLETE
- ADR-0050b (CRDT Device-to-Device Merge) ✅ COMPLETE
- ADR-0050c (LAN-First Sync Implementation - Phase 1) ✅ COMPLETE
- ADR-0050d (P2P E2EE Internet Sync - Phase 2) ✅ COMPLETE

**Related Issues (All Planned):**
- E2.1 (Multi-Device LAN Sync) - Phase 1 epic M2-M3
- E2.2 (P2P E2EE Internet Sync) - Phase 2 epic M4-M5
- I2.1.1-2.1.8 (mDNS service registration, TCP P07 handler, 5s sync loop)
- I2.2.1-2.2.8 (STUN integration, QUIC handler, E2EE encryption)

**Resolution Timeline:**
- 2025-10-15: Strategy discussion + device-first pivot approved
- 2025-10-16: All 4 ADRs created + comprehensive documentation complete
- Implementation: Phase 1 epics added to SEQUENTIAL_ROADMAP.yaml

**Decision Owner:** Architecture Team + Product Manager ✅
**Approval Authority:** CTO/VP Engineering ✅

---

### ~~Q1: Multi-Region Deployment Strategy~~ (REPLACED BY Q1 MULTI-DEVICE STRATEGY)
**Status:** SUPERSEDED (see Q1 above for device-first strategy)

**Previous Question (DEPRECATED):**
How should user requests be routed across multi-region K1 deployment? Three viable options:
- **Option A:** DNS Geo-Routing (Route53 geolocation) → nearest region
- **Option B:** Smart Client Routing (client probes, auto-switches) → optimal region
- **Option C:** Central Gateway Router (API Gateway + Lambda@Edge) → managed routing

**Why Superseded:**
FamilyOS pivoted to device-first architecture (Phase 4 Q1 decision) - cloud-centric multi-region deployment no longer applicable for multi-device sync. Devices route directly to each other (P2P) rather than to cloud regions.

**Related:** New approach documented in ADR-0050 family above ✅

---

### Q2: Tool Execution Timeout vs. Resource Limits
**Status:** BLOCKING
**Severity:** CRITICAL
**Category:** Implementation Ambiguity

**Question:**
When tools exceed 30s timeout or 512MB memory limit, what should happen?
- Option A: Hard kill + error response (fast, may lose context)
- Option B: Graceful shutdown with partial results (slow, may keep trying)
- Option C: Resource-aware throttling (reduce quality to complete within limits)

**Impact on Roadmap:**
- I3.7.3 (Tool Resource Limits): implementation approach changes
- E3.1 (Tool Runner): error handling paths differ significantly
- E4.4 (Intent Classifier): if classifier times out, how to handle?

**Related ADRs:**
- ADR-0033 (Tool Runner)
- ADR-0033b (Tool Timeouts)
- ADR-0032b (Resource Limits)

**Related Issues:**
- I3.7.3 (Resource limits implementation)
- I3.1.X (Tool runner architecture)

**Escalation Path:**
1. Tech Lead (Execution Layer) → Architecture Review
2. If unresolved → Planner ADR discussion

**Resolution Deadline:** Before M3 Start

---

### Q3: KV Cache Eviction Under Contention
**Status:** BLOCKING
**Severity:** HIGH
**Category:** Performance Unknown

**Question:**
When KV cache hit rate drops below 75% (our target), what triggers recovery?
- Option A: Evict least-used sessions immediately (preemptive)
- Option B: Wait for natural eviction + prioritize future allocations (reactive)
- Option C: Predictive eviction based on access patterns (complex, higher overhead)

**Impact on Roadmap:**
- I5.6.2 (KV Cache Eviction Policy): policy logic depends on choice
- E5.6 (KV Cache Manager): monitoring + metrics change
- E5.0 (Performance Budgets): hit rate tracking becomes critical

**Related ADRs:**
- ADR-0025 (KV Cache)
- ADR-0025a (Cache Eviction)
- ADR-0024 (Performance Budgets)

**Related Issues:**
- I5.6.2 (Eviction policy implementation)
- I5.0.2 (Metrics for cache hits)

**Escalation Path:**
1. Performance Engineer → Profiling/Testing
2. If unclear → Benchmarking sprint before M5

**Resolution Deadline:** Before M5 Start

---

### Q4: HITL Escalation Approval Model
**Status:** BLOCKING
**Severity:** HIGH
**Category:** HITL Protocol Ambiguity

**Question:**
When a RED band operation needs human approval, what's the approval model?
- Option A: Async callback (fire-and-forget, best effort)
- Option B: Blocking wait (up to 30s timeout, then fallback)
- Option C: Staged approval (tier1 → tier2 → manager, each with timeout)

**Impact on Roadmap:**
- I6.1.1 (HITL Protocol implementation): core logic changes
- I6.1.2 (Context-Aware Escalation): routing logic differs
- E6.2 (Message Queue): queue structure may need priority lanes

**Related ADRs:**
- ADR-0052 (HITL Protocols)
- ADR-0052b (Escalation Routing)
- ADR-0061 (Band Policies)

**Related Issues:**
- I6.1.1 (HITL Request/Response)
- I6.1.2 (Context-Aware Escalation)

**Escalation Path:**
1. Product Manager (HITL) → Use Case Review
2. If unresolved → Customer Advisory Board

**Resolution Deadline:** Before M6 Start

---

### Q5: Learning Loop Feedback Integration Timing
**Status:** BLOCKING
**Severity:** HIGH
**Category:** Architecture Design

**Question:**
When should learning loop feedback be applied?
- Option A: Real-time (every turn) - high update frequency, potential instability
- Option B: Batch daily (aggregate feedback, more stable) - stale for >24h
- Option C: Hybrid (online learning + daily batch validation) - complex, moderate overhead

**Impact on Roadmap:**
- I6.5.1 (Feedback Signal Collection): storage model changes
- E6.5 (Learning Loop Foundation): frequency of updates affects performance
- E5.0 (Performance Budgets): additional metric tracking needed

**Related ADRs:**
- ADR-0059 (Learning Loop)
- ADR-0059a (Feedback Integration)

**Related Issues:**
- I6.5.1 (Signal collection & aggregation)

**Escalation Path:**
1. ML Engineer → Learning System Design
2. If unresolved → Research Discussion

**Resolution Deadline:** Before M6-M7 Transition

---

### Q6: PII Detection False Positive Strategy
**Status:** BLOCKING
**Severity:** MEDIUM
**Category:** Performance/Accuracy Tradeoff

**Question:**
If PII detection has <95% recall (misses some PII), what's our fallback?
- Option A: Conservative flagging (higher false positives, safer but UX impact)
- Option B: Accept some risk (lower false positives, better UX, compliance risk)
- Option C: Staged detection (fast check + manual review queue for uncertain cases)

**Impact on Roadmap:**
- I5.4.1 (PII Detection Engine): accuracy target + strategy
- E5.4 (PII Redaction): pipeline changes based on approach
- E5.0 (Performance Budgets): adds human review queue cost

**Related ADRs:**
- ADR-0035 (PII Redaction)
- ADR-0035a (PII Detection)

**Related Issues:**
- I5.4.1 (PII detection implementation)

**Escalation Path:**
1. Security Lead → Compliance Review
2. If unresolved → Legal Counsel

**Resolution Deadline:** Before M5 Approval

---

## ⚠️ CLARIFICATION NEEDED (Medium Priority)

### Q7: Actor Model Mailbox Size Limits
**Status:** CLARIFICATION
**Category:** Implementation Detail

**Question:**
In I1.1.1 (MPSC Mailbox), what should max queue depth be?
- Current spec: "backpressure when > 80% full" but no max size defined
- Suggested options: 1K msgs (conservative), 10K msgs (moderate), 100K msgs (aggressive)

**Related Issues:**
- I1.1.1 (MPSC Mailbox with Backpressure)

**Suggested Resolution:** Define in ADR-0002a, set for E1.1

---

### Q8: Voice Backpressure Quality Tiers
**Status:** CLARIFICATION
**Category:** Voice/UX Design

**Question:**
In I6.4.1 (Voice Backpressure Stages), what exactly means "reduce ASR latency target to 200ms"?
- Do we skip silence padding? Use faster model? Lower sample rate?
- How does this affect accuracy?

**Related Issues:**
- I6.4.1 (Voice Backpressure Stages)

**Suggested Resolution:** Define quality ladder in ADR-0057a, test degradation impact

---

### Q9: REST API Session Timeout
**Status:** CLARIFICATION
**Category:** API Design

**Question:**
In I4.8.1 (REST Session Endpoints), how long should sessions remain valid?
- No activity timeout defined (1h? 24h? indefinite?)
- Should session lifetime differ by tier (FREE vs PRO)?

**Related Issues:**
- I4.8.1 (REST Session Endpoints)

**Suggested Resolution:** Define in ADR-0040, align with SessionState eviction

---

### Q10: Agent Supervisor Blacklist Duration
**Status:** CLARIFICATION
**Category:** Fault Tolerance

**Question:**
In I1.1.3 (Supervisor Health Monitoring), current spec says "1 hour blacklist if crash > 3x/10min"
- Should blacklist grow adaptive (1h → 2h → 4h → permanent)?
- Or reset after successful session?

**Related Issues:**
- I1.1.3 (Supervisor with Health Monitoring)

**Suggested Resolution:** Clarify in ADR-0002b, test failure recovery scenarios

---

### Q11: Cost Attribution Granularity
**Status:** CLARIFICATION
**Category:** Observability/Billing

**Question:**
In I5.9.1 (Cost Tracking), should costs be tracked at:
- Option A: Request level (most granular, lots of data)
- Option B: Session level (moderate, easier aggregation)
- Option C: Daily level (least granular, easier reporting)

**Related Issues:**
- I5.9.1 (Cost Tracking & Attribution)
- I5.9.2 (Billing & Reporting)

**Suggested Resolution:** Define in ADR-0031, align with cost model

---

### Q12: Protocol Monitor Timeout Propagation
**Status:** CLARIFICATION
**Category:** Protocol Validation

**Question:**
In E1.2 (Protocol Monitor), when a protocol times out, should:
- Option A: Immediately fail and error response
- Option B: Escalate to supervisor for recovery
- Option C: Attempt re-negotiation

**Related Issues:**
- E1.2 issues (MPST Protocol Validation)

**Suggested Resolution:** Clarify timeout policies in ADR-0003 before I1.2.x implementation

---

### Q13: K0 Bridge Batch Window Jitter
**Status:** CLARIFICATION
**Category:** Performance Tuning

**Question:**
In I2.4.1 (K0 Bridge Manager), batch window is "100ms or 1000 deltas (whichever first)"
- Should there be jitter to avoid thundering herd when many sessions batch together?
- Suggested: add ±20% jitter to 100ms window

**Related Issues:**
- I2.4.1 (K0 Bridge Manager)

**Suggested Resolution:** Benchmark batch completion timing before M2 start

---

### Q14: Band Classification Confidence Threshold
**Status:** CLARIFICATION
**Category:** Security Policy

**Question:**
In I5.2.1 (Band Classification), how confident must classifier be before assigning a band?
- Suggested: GREEN > 95%, AMBER > 80%, RED manual
- Should uncertain operations default to RED (safe) or GREEN (permissive)?

**Related Issues:**
- I5.2.1 (Band Classification Engine)

**Suggested Resolution:** Define confidence thresholds in ADR-0061a, align with security risk

---

### Q15: SessionState Delta Compression
**Status:** CLARIFICATION
**Category:** Storage Optimization

**Question:**
In I2.3.2 (Delta Serialization), should deltas be compressed?
- FlatBuffers provides schema-based compression hints
- But adds CPU overhead (~5ms per 10KB delta)
- Worth it for 30% size savings?

**Related Issues:**
- I2.3.2 (Delta Serialization Pipeline)

**Suggested Resolution:** Benchmark compression ratio vs. latency before M2 start

---

### Q16: Cognitive Trace ID Sampling Rate
**Status:** CLARIFICATION
**Category:** Observability Overhead

**Question:**
In I1.8.1 (Cognitive Tracing), should trace collection be:
- Option A: 100% (comprehensive, higher overhead ~10% latency increase)
- Option B: Sampled 10% (lower overhead, representative sampling)
- Option C: Adaptive (sample based on load)

**Related Issues:**
- I1.8.1 (Cognitive Tracing implementation)

**Suggested Resolution:** Benchmark trace overhead before E1.8 implementation

---

### Q17: Tool Registry Update Frequency
**Status:** CLARIFICATION
**Category:** Maintainability

**Question:**
In E3.5 (Tool Registry), how often should tool catalog be refreshed?
- Real-time (HTTP check on each lookup) - expensive
- Periodic (cache for 1h) - might miss updates
- Event-driven (subscribe to tool updates) - complex but efficient

**Related Issues:**
- E3.5 issues (Tool Registry & Dynamic Discovery)

**Suggested Resolution:** Propose caching strategy in ADR-0007b

---

### Q18: Learning Loop Drift Detection Threshold
**Status:** CLARIFICATION
**Category:** Quality Assurance

**Question:**
In E6.5 (Learning Loop Foundation), at what drift should we alert/retrain?
- Feedback score decline > 10%?
- Accuracy drop > 5%?
- Define clear triggers before implementation

**Related Issues:**
- I6.5.1 (Feedback Signal Collection)

**Suggested Resolution:** Define drift detection thresholds in ADR-0059b

---

## 📋 Summary by Resolution Path

### By Resolution Path:

**Engineering Lead / Architecture Review:**
- Q1 (Multi-region strategy)
- Q5 (Learning loop timing)
- Q7 (Mailbox size limits)

**Performance / Profiling:**
- Q3 (KV cache eviction)
- Q13 (Batch window jitter)
- Q16 (Trace sampling)

**Security / Compliance:**
- Q6 (PII false positives)
- Q14 (Band confidence)

**Product / UX:**
- Q2 (Tool timeout strategy)
- Q8 (Voice quality tiers)
- Q9 (Session timeout)

**Technical Design (ADR Discussions):**
- Q4 (HITL approval model)
- Q10 (Supervisor blacklist)
- Q11 (Cost granularity)
- Q12 (Protocol timeouts)
- Q15 (Delta compression)
- Q17 (Tool registry updates)
- Q18 (Drift detection)

---

## 🚨 Blocking Resolution Timeline

| Question | Deadline | Owner | Status |
|----------|----------|-------|--------|
| Q1 | Before M2 start | Arch Lead | OPEN |
| Q2 | Before M3 start | Tech Lead (E3) | OPEN |
| Q3 | Before M5 start | Perf Eng | OPEN |
| Q4 | Before M6 start | Product (HITL) | OPEN |
| Q5 | Before M6-M7 | ML Eng | OPEN |
| Q6 | Before M5 approval | Security Lead | OPEN |

---

## 📞 Escalation Contacts

- **Architecture Lead:** Point of escalation for design decisions
- **VP Engineering:** Final authority for blocking technical decisions
- **Product Manager:** Authority for UX/HITL decisions
- **Security Lead:** Authority for security/compliance decisions
- **Performance Engineer:** Authority for performance tradeoffs

---

## ✅ Next Steps

1. **Sessions 5-6:** Address each blocking question (Q1-Q6)
2. **Session 7:** Address clarification questions (Q7-Q18)
3. **Before M1 Approval:** Ensure no "BLOCKING" questions remain
4. **Update Roadmap:** Incorporate resolutions into relevant ADRs and issues
5. **Document Decisions:** Create decision records for each resolution

---

**Last Updated:** 2025-10-16
**Next Review:** Before M2 Start Approval
**Owner:** Architecture Team
