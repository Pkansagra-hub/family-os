# 🚨 RISKS REGISTER — K1 Roadmap Technical & Delivery Risks

**Date:** October 16, 2025
**Status:** ACTIVE (Session 4 - Phase 3)
**Total Risks:** 22
**Critical (P×I ≥ 12):** 8
**High (P×I 6-11):** 9
**Medium (P×I 3-5):** 5

---

## 📊 Risk Scoring Methodology

**Probability:** 1-5 (1=unlikely, 5=certain)
**Impact:** 1-5 (1=minimal, 5=catastrophic)
**Risk Score:** P × I (max 25)
**Severity:** ≥12 = Critical | 6-11 = High | 3-5 = Medium | <3 = Low

---

## 🔴 CRITICAL RISKS (P×I ≥ 12)

### R1: SessionState Coherence Failure Under High Concurrency
**Probability:** 4 (Likely if not carefully designed)
**Impact:** 5 (Loss of user data, compliance violation)
**Score:** 20 (CRITICAL)

**Description:**
Write-through coherence (I2.8.1) across hot/warm/cold tiers could fail under high concurrent writes, leading to:
- Stale reads (user sees old data)
- Lost writes (concurrent update collisions)
- Compliance breach (GDPR requires data integrity)

**Related ADRs:** ADR-0050, ADR-0050a-b, ADR-0018
**Related Issues:** I2.8.1, I2.7.1-3, I2.3.2
**Related Milestones:** M2 (E2.8: Coherence), M5 (E5.0: Observability)

**Mitigation:**
1. ✅ Use CRDTs or operational transform for conflict resolution (ADR-0050a)
2. ✅ Implement write-ahead logging (WAL) in K0 bridge (I2.4.1)
3. ✅ Comprehensive WARD tests for concurrent access patterns (I2.8.1)
4. ✅ Monitor coherence violations in E5.0 (metrics + alerts)
5. ✅ Define fallback to RED band (manual review) if coherence fails

**Owner:** M2 Tech Lead (SessionState)
**Verification:** WARD tests must cover ≥100 concurrent sessions
**Action:** Flag before M2 start if coherence model (Q1) unresolved

---

### R2: Tool Execution Timeout Cascades
**Probability:** 4 (Likely if tools are CPU-intensive)
**Impact:** 5 (System degradation, user experience impact)
**Score:** 20 (CRITICAL)

**Description:**
Tool timeouts (30s, ADR-0032b) could cascade:
- Tool A times out → escalates to RED band → HITL queue overloads → backpressure triggered → system throttles
- If backpressure is too aggressive, could trigger complete session rejection

**Related ADRs:** ADR-0033, ADR-0032b, ADR-0057
**Related Issues:** I3.7.3, I6.4.1
**Related Milestones:** M3 (E3.1: Tool Runner), M6 (E6.4: Backpressure)

**Mitigation:**
1. ✅ Define clear timeout strategy before M3 start (Q2 in OPEN_QUESTIONS)
2. ✅ Implement resource-aware throttling (reduce model quality, not full rejection)
3. ✅ Separate tool timeout from system backpressure (different escalation paths)
4. ✅ Add circuit breaker per tool (ADR-0009): after 3 consecutive timeouts, block for 5min
5. ✅ WARD tests for timeout scenarios (I3.7.3)

**Owner:** M3 Tech Lead (Execution)
**Verification:** Load tests with tool timeouts → verify no cascade
**Action:** Resolve Q2 before M3 start approval

---

### R3: KV Cache Hit Rate Below 75% Target
**Probability:** 4 (Likely if cache sizing wrong)
**Impact:** 5 (Model latency increases 2-3x, TTFT budget exceeded)
**Score:** 20 (CRITICAL)

**Description:**
If KV cache hit rate drops below 75%:
- Each cache miss → expensive KV recomputation
- TTFT increases from 150ms target → 300-500ms (budget breach)
- System can't scale (cost increases dramatically)

**Related ADRs:** ADR-0025, ADR-0024 (Performance Budgets)
**Related Issues:** I5.6.2 (Eviction), I5.0.2 (Metrics)
**Related Milestones:** M5 (E5.0: Perf, E5.6: KV Cache)

**Mitigation:**
1. ✅ Define cache sizing strategy before M5 (512MB allocation rules)
2. ✅ Implement predictive eviction vs. LRU (Q3 in OPEN_QUESTIONS)
3. ✅ Add hit rate metrics in E5.0 (I5.0.2)
4. ✅ Set alerts for hit rate < 75% (I5.0.5: Alerting Rules)
5. ✅ Load tests with realistic workload before M5 approval
6. ✅ Fallback: if hit rate stays <70%, trigger emergency cache expansion (cloud tier)

**Owner:** M5 Tech Lead (Infrastructure)
**Verification:** Hit rate ≥75% measured under realistic load (1K concurrent sessions)
**Action:** Resolve Q3 before M5 start

---

### R4: HITL Response Timeout → Orphaned Operations
**Probability:** 4 (Likely in high-load scenarios)
**Impact:** 5 (User operations fail silently, data loss)
**Score:** 20 (CRITICAL)

**Description:**
If HITL approvers don't respond within timeout (30s, ADR-0052):
- Current spec unclear on fallback (Q4: OPEN_QUESTIONS)
- Could lead to:
  - Silent failure (operation abandoned)
  - Retry storms (operation requeued repeatedly)
  - Stale HITL requests (approver reviews old request, applies to wrong session)

**Related ADRs:** ADR-0052, ADR-0052b, ADR-0061
**Related Issues:** I6.1.1, I6.1.2
**Related Milestones:** M6 (E6.1: HITL)

**Mitigation:**
1. ✅ Define HITL approval model before M6 (Q4 in OPEN_QUESTIONS)
2. ✅ Implement staged escalation (tier1 → tier2 → manager, each with timeout)
3. ✅ Audit trail of all HITL decisions (E2.5: Receipt Manager)
4. ✅ Dead-letter queue for failed approvals (move to manual review)
5. ✅ WARD tests for HITL timeout scenarios (I6.1.1)
6. ✅ Metrics for HITL response time (I5.0.2)

**Owner:** M6 Tech Lead (HITL)
**Verification:** HITL responses logged and audited; timeouts handled gracefully
**Action:** Resolve Q4 before M6 start; implement I2.5 (Receipts) before HITL

---

### R5: Multi-Region Data Consistency Violations
**Probability:** 4 (Likely if coherence model wrong, Q1)
**Impact:** 5 (Compliance issues, user confusion)
**Score:** 20 (CRITICAL)

**Description:**
If multi-region strategy (Q1) is eventual consistency:
- User sees different data in different regions
- Could violate compliance (GDPR requires consistency)
- Could lose money (billing system sees different session state)

**Related ADRs:** ADR-0050 (Coherence), ADR-0020 (Multi-tier storage)
**Related Issues:** I2.8.1 (Coherence), I2.7.1-3 (Multi-tier)
**Related Milestones:** M2 (E2.8: Coherence)

**Mitigation:**
1. ✅ Define multi-region strategy before M2 (Q1 in OPEN_QUESTIONS)
2. ✅ If eventual consistency, define maximum drift bounds
3. ✅ Implement read-my-writes guarantee (session always reads from home region)
4. ✅ Add region-aware routing in E5.2 (Band Manager)
5. ✅ WARD tests for cross-region scenarios (I2.8.1)
6. ✅ Compliance audit trail (all region switches logged)

**Owner:** Architecture Lead
**Verification:** Consistency violations < 0.01% (1 in 10K), maximum drift < 5s
**Action:** Resolve Q1 before M2 start; document consistency guarantees

---

### R6: PII Detection False Negatives → Compliance Breach
**Probability:** 3 (Possible if detection model inadequate)
**Impact:** 5 (Compliance violation, legal liability)
**Score:** 15 (CRITICAL)

**Description:**
PII detector misses sensitive data (< 95% recall):
- Real PII ends up in logs/metrics (unencrypted)
- Compliance violation (GDPR, CCPA, HIPAA)
- Legal liability if discovered

**Related ADRs:** ADR-0035 (PII Redaction), ADR-0035a (PII Detection)
**Related Issues:** I5.4.1 (PII Detection Engine)
**Related Milestones:** M5 (E5.4: PII)

**Mitigation:**
1. ✅ Define PII types explicitly: email, SSN, phone, credit card, passport, medical, financial
2. ✅ Use hybrid detection (regex + ML classifier) for higher accuracy
3. ✅ Implement staged detection (fast check + manual review for uncertain)
4. ✅ Set alert if false negative rate > 1% (I5.0.5)
5. ✅ Regular audits of logs for missed PII (monthly scan)
6. ✅ Default to RED band (manual review) for uncertain data
7. ✅ WARD tests with ground truth (false neg rate < 0.5%)

**Owner:** M5 Tech Lead (Security)
**Verification:** False negative rate < 0.5%, false positive rate < 5%
**Action:** Benchmark detection accuracy before M5 start; resolve Q6 before approval

---

### R7: Learning Loop Instability → Worse Performance
**Probability:** 3 (Possible if feedback integration wrong)
**Impact:** 5 (System degrades over time, user experience suffers)
**Score:** 15 (CRITICAL)

**Description:**
Learning loop feedback (E6.5) could cause system to degrade:
- If feedback signals are noisy → model learns wrong patterns
- If feedback is applied too frequently → model oscillates
- If feedback has delay → model learns stale patterns

**Related ADRs:** ADR-0059 (Learning Loop), ADR-0059a (Feedback Integration)
**Related Issues:** I6.5.1 (Feedback Signal Collection)
**Related Milestones:** M6-M7 (E6.5: Learning Foundation)

**Mitigation:**
1. ✅ Define feedback integration timing before M6 (Q5 in OPEN_QUESTIONS)
2. ✅ Implement signal validation: outlier detection, confidence scoring
3. ✅ Use batch learning + daily validation (stable, not real-time)
4. ✅ Add model versioning: keep N previous versions, roll back if metrics degrade
5. ✅ Monitoring: track model metrics over time (accuracy, recall, precision)
6. ✅ WARD tests with synthetic feedback patterns

**Owner:** M6-M7 Tech Lead (Learning)
**Verification:** Performance improvements ≥2% week-over-week (no degradation)
**Action:** Resolve Q5 before M6-M7; implement drift detection (ADR-0059c)

---

### R8: Band Classification Misconfiguration → Security Bypass
**Probability:** 3 (Possible if classification rules wrong)
**Impact:** 5 (RED band operations bypass approval, compliance breach)
**Score:** 15 (CRITICAL)

**Description:**
Band classification (I5.2.1) could misclassify sensitive operations:
- RED band operation classified as GREEN → skips approval → security bypass
- Compliance violation if RED data treated as public
- If discovered, immediate remediation required

**Related ADRs:** ADR-0032 (Security), ADR-0061 (Band Policies)
**Related Issues:** I5.2.1 (Band Classification)
**Related Milestones:** M5 (E5.2: Band Manager)

**Mitigation:**
1. ✅ Define classification rules explicitly (ADR-0061)
2. ✅ Default to RED (most restrictive) when uncertain
3. ✅ Manual review queue for borderline cases (I5.2.1)
4. ✅ Confidence thresholds (Q14 in OPEN_QUESTIONS)
5. ✅ Audit all band assignments (log + review daily)
6. ✅ WARD tests for classification accuracy
7. ✅ Regular penetration tests (Q4 2025)

**Owner:** M5 Tech Lead (Security)
**Verification:** Band misclassification rate < 0.1% (1 in 1000)
**Action:** Define classification rules before M5; resolve Q14

---

## � Q1 SPECIAL: MULTI-DEVICE FAMILY SYNC RISKS (ADR-0050 Family)

### R-Q1.1: CRDT Deterministic Merge Fails → Devices Diverge
**Probability:** 3 (Likely if CRDT algorithm has edge cases)
**Impact:** 5 (Multi-device state divergence, data corruption)
**Score:** 15 (CRITICAL)

**Description:**
CRDT merge algorithm (ADR-0050b: Last-Write-Wins + device ID ordering + vector clocks) could fail if:
- Vector clocks not synchronized across devices (network latency issues)
- Device ID collision (rare but possible)
- Concurrent writes on same field from different devices
- Result: Some devices show User A's data, others show User B's data

**Related ADRs:** ADR-0050b (CRDT Merge), ADR-0050a (Coherence Guarantees)
**Related Issues:** E2.1.x (Phase 1 LAN sync), E2.2.x (Phase 2 E2EE sync)
**Related Milestones:** M2-M3 (Phase 1), M4-M5 (Phase 2)

**Mitigation:**
1. ✅ Use proven CRDT library (e.g., Yjs, Automerge) - NOT custom implementation
2. ✅ Comprehensive WARD tests for merge logic (100+ scenarios: concurrency, network delays, device failures)
3. ✅ Device ID generation strategy (UUID v4 + MAC address) - highly unlikely collision
4. ✅ Vector clock validation in K0 bridge before merge
5. ✅ Fallback: Detect divergence via checksum, trigger manual sync
6. ✅ Monitor divergence rates in observability (E5.9)

**Owner:** M2 Tech Lead (Multi-Device Sync)
**Verification:** WARD tests must include concurrent writes + network partitions + device crashes
**Action:** Use battle-tested CRDT; custom implementation is high risk

---

### R-Q1.2: E2EE Device Certificate Rotation Breaks Sync
**Probability:** 3 (Likely if cert management not robust)
**Impact:** 5 (Multi-device communication fails, sync blocked)
**Score:** 15 (CRITICAL)

**Description:**
ADR-0050d (P2P E2EE) uses device certificates (Ed25519 signing + X25519 encryption). If cert rotation fails:
- Device A rotates cert → Device B still has old cert → messages fail to decrypt
- No fallback mechanism → sync is blocked until manual intervention
- Result: "Why can't my phone and tablet talk?"

**Related ADRs:** ADR-0050d (P2P E2EE Internet Sync), ADR-0050c (LAN Sync)
**Related Issues:** E2.2.x (Phase 2 E2EE sync implementation)
**Related Milestones:** M4-M5 (E2.2: Phase 2 start)

**Mitigation:**
1. ✅ Implement cert versioning (old + new cert valid during transition window)
2. ✅ Backward compatibility: device can send with old cert while accepting new
3. ✅ Grace period: 24-48h overlap before old cert expires
4. ✅ Automated cert refresh: K0 store device cert state, trigger rotation periodically
5. ✅ Fallback to LAN sync (Phase 1) if E2EE certs broken
6. ✅ Alert user if cert sync fails (show in UI: "Sync temporarily unavailable, reconnect devices")

**Owner:** M4 Tech Lead (E2EE Implementation)
**Verification:** WARD tests with cert rotation scenarios; E2E test with real device pairs
**Action:** Design cert management strategy before M4 start; include grace period logic

---

### R-Q1.3: LAN Discovery Fails on Certain Networks
**Probability:** 3 (Likely on corporate networks with mDNS blocked)
**Impact:** 4 (LAN sync unavailable; fallback to E2EE or manual)
**Score:** 12 (HIGH)

**Description:**
ADR-0050c (LAN Sync) uses mDNS for device discovery. mDNS fails on:
- Corporate/university networks with mDNS blocked
- Networks with firewall rules preventing .local traffic
- Some WiFi 6E networks with aggressive filtering
- Result: Devices can't find each other on LAN, sync requires manual entry

**Related ADRs:** ADR-0050c (LAN-First Sync), ADR-0050d (E2EE fallback)
**Related Issues:** E2.1.1 (mDNS discovery implementation)
**Related Milestones:** M2-M3 (E2.1: Phase 1 start)

**Mitigation:**
1. ✅ Manual device pairing fallback (enter device ID + QR code)
2. ✅ Dual discovery: mDNS + manual entry option
3. ✅ Fallback to E2EE P2P (Phase 2) automatically if LAN discovery fails
4. ✅ Detect mDNS failure and alert user (UI: "Devices not found on WiFi. Try manual pairing?")
5. ✅ Implement TCP unicast fallback (if mDNS fails, try direct IP if user provides)
6. ✅ Documentation: "Why can't my devices sync on corporate WiFi?"

**Owner:** M2 Tech Lead (LAN Implementation)
**Verification:** Test on 10+ network types (home, corporate, university, mobile hotspot, WiFi 6E)
**Action:** Implement fallback strategies before Phase 1 release (M3 end)

---

## �🟠 HIGH RISKS (P×I 6-11)

### R9: Backpressure Cascade Triggers System Shutdown
**Probability:** 3 (Possible if backpressure logic aggressive)
**Impact:** 4 (All new sessions rejected, service unavailable)
**Score:** 12 (HIGH)

**Description:**
Backpressure cascade (E5.7) could trigger too early:
- If load > 80% → reduce quality
- If load > 95% → reject new sessions
- If sustained → entire system stops accepting new work

**Related ADRs:** ADR-0057 (Backpressure), ADR-0061 (Load Control)
**Related Issues:** I6.4.1 (Voice Backpressure), E5.7 (Cascade)
**Related Milestones:** M5-M6 (E5.7, E6.4)

**Mitigation:**
1. ✅ Define backpressure thresholds clearly (ADR-0057)
2. ✅ Test with realistic load to find sweet spot
3. ✅ Separate concerns: tool timeouts ≠ system backpressure
4. ✅ Implement adaptive backpressure (grow recovery threshold as load decreases)
5. ✅ Metrics for backpressure state (I5.0.2: how often triggered?)
6. ✅ Manual override for emergency (human operator can disable backpressure)

**Owner:** M5 Tech Lead (Infrastructure)
**Verification:** Load tests show graceful degradation (no binary on/off)
**Action:** Implement adaptive thresholds; avoid hard rejection

---

### R10: Voice Pipeline Latency Exceeds Budget Under Load
**Probability:** 3 (Likely if component latencies underestimated)
**Impact:** 4 (TTFT > 150ms, user experience suffers)
**Score:** 12 (HIGH)

**Description:**
Voice pipeline (E4.2) could exceed TTFT budget under load:
- ASR latency: 100-200ms (variable by model)
- Intent classification: 50ms
- TTS: 100-150ms
- Total: 250-500ms (exceeds 150ms budget)

**Related ADRs:** ADR-0056 (Voice Pipeline), ADR-0024 (Performance Budgets)
**Related Issues:** E4.2 issues
**Related Milestones:** M4 (E4.2: Voice)

**Mitigation:**
1. ✅ Benchmark each component before M4 (ASR, intent, TTS)
2. ✅ Implement parallel processing where possible (ASR + TTS async)
3. ✅ Use faster models for voice (whisper.fast vs. standard)
4. ✅ Cache previous intents (likely to repeat)
5. ✅ Implement graceful degradation (faster TTS at lower quality if needed)
6. ✅ Voice backpressure (I6.4.1): reduce quality before exceeding TTFT

**Owner:** M4 Tech Lead (Ingress/Voice)
**Verification:** TTFT P95 < 150ms under 1K concurrent voice sessions
**Action:** Benchmark components before M4 start; add to E5.0 performance metrics

---

### R11: Agent Fabric Scalability Bottleneck
**Probability:** 2 (Unlikely if designed correctly, but possible)
**Impact:** 4 (System doesn't scale beyond certain agent count)
**Score:** 8 (HIGH)

**Description:**
Agent fabric (E1.1-E1.3) could have scalability bottlenecks:
- Supervisor overhead grows O(N) with agent count
- Mailbox queue contention under high message throughput
- Scheduler starvation (low-priority agents never get CPU time)

**Related ADRs:** ADR-0002 (Actor Model), ADR-0002b (Supervisor), ADR-0002c (Router)
**Related Issues:** I1.1.2 (Router), I1.1.3 (Supervisor)
**Related Milestones:** M1 (E1.1-E1.3)

**Mitigation:**
1. ✅ WARD tests with increasing agent counts (up to 1000+)
2. ✅ Hierarchical supervision (supervisors can supervise other supervisors)
3. ✅ Fair scheduling with priority lanes (I1.1.2: fast vs. smart lanes)
4. ✅ Metrics for supervisor overhead (I5.0.2)
5. ✅ Profile with py-spy before E1.3 completion

**Owner:** M1 Tech Lead (Agent Fabric)
**Verification:** Supervisor overhead < 5% CPU per 100 agents
**Action:** Load tests with 500+ agents before M1 approval

---

### R12: K0 Bridge Write Latency Spike
**Probability:** 3 (Likely if batching not tuned)
**Impact:** 3 (SessionState writes delayed, feels sluggish)
**Score:** 9 (HIGH)

**Description:**
K0 bridge batching (I2.4.1) could batch writes too aggressively:
- 100ms batch window means up to 100ms write latency
- If batch fills up (1000 deltas), write latency decreases but queue grows
- Under high load, queue could backup → memory pressure

**Related ADRs:** ADR-0001a (K0 Bridge), ADR-0022 (Batching)
**Related Issues:** I2.4.1 (K0 Bridge Manager)
**Related Milestones:** M2 (E2.4)

**Mitigation:**
1. ✅ Tune batch window (100ms seems reasonable, but test)
2. ✅ Implement jitter to avoid thundering herd (Q13 in OPEN_QUESTIONS)
3. ✅ Add metrics for batch latency distribution (I5.0.2)
4. ✅ Fallback: if queue > 10K, reduce batch window to 50ms
5. ✅ WARD tests with varying write rates

**Owner:** M2 Tech Lead (State)
**Verification:** Write latency P99 < 200ms under all load conditions
**Action:** Benchmark batch window; resolve Q13

---

### R13: REST API Rate Limiting Bypass
**Probability:** 2 (Unlikely if implemented correctly)
**Impact:** 4 (DoS vulnerability, service degradation)
**Score:** 8 (HIGH)

**Description:**
Rate limiting (I4.8.4) could have bypass vulnerabilities:
- Distributed attack bypasses per-instance limit (need global counter)
- Token bucket can be gamed (burst allowance exploited)
- Missing authentication could allow unlimited requests

**Related ADRs:** ADR-0047 (API Rate Limiting)
**Related Issues:** I4.8.4 (Rate Limiting Implementation)
**Related Milestones:** M4 (E4.8)

**Mitigation:**
1. ✅ Use distributed rate limiter (Redis-backed) vs. in-process
2. ✅ Conservative burst allowance (10% of per-minute rate max)
3. ✅ Mandatory authentication before rate limiting checked
4. ✅ Monitor for suspicious patterns (I5.0.2: metrics)
5. ✅ WARD tests for rate limit bypass attempts
6. ✅ Security review before M4 approval

**Owner:** M4 Tech Lead (Ingress)
**Verification:** Distributed attack cannot bypass rate limits
**Action:** Implement distributed rate limiter; security audit before M4

---

### R14: Tool Output Sanitization Performance Hit
**Probability:** 2 (Unlikely if implemented efficiently)
**Impact:** 3 (Tool latency increases, TTFT budget impact)
**Score:** 6 (HIGH)

**Description:**
Tool output sanitization (I3.7.4) could slow tool execution:
- Scanning tool output for PII could take 50-100ms per output
- For fast tools, sanitization becomes bottleneck
- Could violate tool execution time budget (30s per tool)

**Related ADRs:** ADR-0032c (Output Sanitization), ADR-0035 (PII Redaction)
**Related Issues:** I3.7.4 (Tool Output Sanitization)
**Related Milestones:** M3 (E3.7)

**Mitigation:**
1. ✅ Optimize regex patterns for PII detection
2. ✅ Use streaming sanitization (process output incrementally)
3. ✅ Skip sanitization for low-risk outputs (GREEN band)
4. ✅ Parallel sanitization on separate thread pool
5. ✅ Metrics for sanitization latency (I5.0.2)
6. ✅ Profile before E3.7 completion

**Owner:** M3 Tech Lead (Execution)
**Verification:** Sanitization latency < 10ms per 1KB output
**Action:** Benchmark sanitization overhead before M3 approval

---

### R15: SessionState Serialization Format Stability
**Probability:** 1 (Unlikely if versioning correct)
**Impact:** 4 (Need migration, data loss possible)
**Score:** 4 (MEDIUM-HIGH)

**Description:**
FlatBuffers schema for SessionState (I2.3.1) could have breaking changes:
- If schema evolves, old SessionState can't be read (compatibility broken)
- Migration could lose data if not carefully designed
- Downtime required for migration

**Related ADRs:** ADR-0019a (SessionState Schema), ADR-0013 (Schema Versioning)
**Related Issues:** I2.3.1 (FlatBuffers Schema Design)
**Related Milestones:** M2 (E2.3)

**Mitigation:**
1. ✅ Use FlatBuffers versioning (add version field)
2. ✅ Always support N-1 schema versions (backward compatibility)
3. ✅ Add migration logic for schema updates
4. ✅ Test migration with real data before deploying
5. ✅ WARD tests for schema evolution

**Owner:** M2 Tech Lead (State)
**Verification:** Schema changes are backward compatible
**Action:** Review ADR-0013 before I2.3.1; implement versioning

---

## 🟡 MEDIUM RISKS (P×I 3-5)

### R16: Observability Metrics Overhead
**Probability:** 2 (Unlikely if sampling tuned)
**Impact:** 2 (Slight latency increase, minimal impact)
**Score:** 4 (MEDIUM)

**Description:**
Metrics collection (I5.0.2) could add overhead:
- Counter increments add CPU cost
- Histogram bucket assignments are expensive
- At high throughput, metrics collection could become bottleneck

**Related ADRs:** ADR-0024a (Prometheus Metrics)
**Related Issues:** I5.0.2 (Metrics Export)
**Related Milestones:** M5 (E5.0)

**Mitigation:**
1. ✅ Use sampling for high-frequency metrics
2. ✅ Batch metric updates (don't update counter on every op)
3. ✅ Profile metrics overhead before E5.0 completion
4. ✅ Implement metrics off-switch for performance testing

**Owner:** M5 Tech Lead (Infrastructure)
**Verification:** Metrics overhead < 2% latency increase

---

### R17: Cost Tracking Attribution Accuracy
**Probability:** 2 (Unlikely if implementation correct)
**Impact:** 2 (Billing discrepancies, customer disputes)
**Score:** 4 (MEDIUM)

**Description:**
Cost attribution (I5.9.1) could be inaccurate:
- Lost trace_ids could cause unattributed costs
- Concurrent tool calls could be double-counted
- Regional cost variance could be missed

**Related ADRs:** ADR-0031 (Cost Tracking)
**Related Issues:** I5.9.1 (Cost Attribution), I5.9.2 (Billing)
**Related Milestones:** M5-M7 (E5.9)

**Mitigation:**
1. ✅ Comprehensive trace_id tracking (E1.8: Cognitive Tracing)
2. ✅ Regular audits of attributed vs. actual costs (monthly)
3. ✅ Unattributed costs → reserve account (investigate later)
4. ✅ WARD tests for cost accuracy

**Owner:** M5 Tech Lead (Infrastructure)
**Verification:** Cost attribution accuracy > 99%

---

### R18: Thermal Manager False Positives
**Probability:** 2 (Possible if thresholds wrong)
**Impact:** 2 (Model gets throttled unnecessarily)
**Score:** 4 (MEDIUM)

**Description:**
Thermal monitoring (I5.5.1) could trigger false alerts:
- Temperature sensors sometimes give noisy readings
- Could cause unnecessary throttling (quality degradation)

**Related ADRs:** ADR-0026 (Thermal Monitoring)
**Related Issues:** I5.5.1 (Thermal Monitoring)
**Related Milestones:** M5 (E5.5)

**Mitigation:**
1. ✅ Sensor reading averaging (filter out spikes)
2. ✅ Alert threshold set conservatively (85°C, not 80°C)
3. ✅ Separate alert from throttle threshold (alert at 85, throttle at 90)
4. ✅ Metrics for alert frequency (should be rare)

**Owner:** M5 Tech Lead (Infrastructure)
**Verification:** False positive rate < 5%

---

### R19: Protocol Monitor Overhead
**Probability:** 2 (Unlikely if protocol checks efficient)
**Impact:** 2 (Slight latency increase per protocol check)
**Score:** 4 (MEDIUM)

**Description:**
Protocol validation (E1.2) could add latency:
- Scribble state machine checks on every message
- Could be expensive if state space large

**Related ADRs:** ADR-0003 (MPST Protocol Monitor)
**Related Issues:** E1.2 issues
**Related Milestones:** M1 (E1.2)

**Mitigation:**
1. ✅ Pre-compile protocol state machines (vs. runtime interpretation)
2. ✅ Profile protocol overhead before E1.2 completion
3. ✅ Cache state transitions (likely repeats)

**Owner:** M1 Tech Lead (Foundation)
**Verification:** Protocol validation overhead < 1% latency

---

### R20: Voice Intent Classification Ambiguity
**Probability:** 2 (Possible with natural language)
**Impact:** 2 (Escalate to HITL, slower turn)
**Score:** 4 (MEDIUM)

**Description:**
Intent classifier (I4.4) could frequently be ambiguous:
- Some user intents are genuinely ambiguous
- Classifier might return marginal confidence scores
- Escalation to HITL (E4.5, E6.1) could become bottleneck

**Related ADRs:** ADR-0058 (Intent Classifier)
**Related Issues:** I4.4, E4.5, E6.1
**Related Milestones:** M4 (E4.4), M6 (E6.1)

**Mitigation:**
1. ✅ Confidence threshold tuning (Q8 in OPEN_QUESTIONS)
2. ✅ Multi-label classification (support multiple likely intents)
3. ✅ Clarification prompts for marginal cases (vs. full HITL escalation)
4. ✅ Metrics for HITL escalation rate (should be < 5%)

**Owner:** M4 Tech Lead (Ingress/Voice)
**Verification:** Intent classification confidence > 90% for 95% of cases

---

### R21: Dependency Resolution in DAG
**Probability:** 1 (Unlikely if DAG correct)
**Impact:** 3 (Dependency cycle causes freeze)
**Score:** 3 (MEDIUM)

**Description:**
Circular dependency in milestone DAG could halt roadmap:
- If E2.X depends on E3.Y, but E3.Y depends on E2.X
- Roadmap sequencing breaks
- Blocking discovery (should be caught in validation)

**Related Issues:** All depends_on relationships
**Related Milestones:** All

**Mitigation:**
1. ✅ Validate DAG before roadmap publication (topological sort)
2. ✅ Review all depends_on relationships in SEQUENTIAL_ROADMAP.yaml
3. ✅ Automated CI check: no circular deps allowed

**Owner:** Architecture Team
**Verification:** Topological sort succeeds, no cycles detected

---

### R22: Performance Budget Miscalibration
**Probability:** 1 (Unlikely if budgets reasonable)
**Impact:** 3 (System doesn't meet SLAs, requires redesign)
**Score:** 3 (MEDIUM)

**Description:**
Performance budgets (I5.0.1) could be too aggressive:
- TTFT < 150ms might be unachievable with certain model
- E2E < 2000ms might require all operations to be parallel (not always possible)
- Could force unnecessary architecture changes mid-development

**Related ADRs:** ADR-0024 (Performance Budgets)
**Related Issues:** I5.0.1
**Related Milestones:** M5 (E5.0)

**Mitigation:**
1. ✅ Justify each budget with data (benchmark vs. competition)
2. ✅ Sensitivity analysis (what if 10% slower?)
3. ✅ Review with team before commitment
4. ✅ Flexibility to adjust if unfeasible (documented decision)

**Owner:** Architecture Lead + M5 Tech Lead
**Verification:** Budgets achievable with reasonable engineering effort

---

## 📋 Risk Summary by Milestone

| Milestone | Critical Risks | High Risks | Medium Risks | Mitigation Owner |
|-----------|---|---|---|---|
| M1 | 0 | 1 (R11) | 1 (R19, R21) | M1 Tech Lead |
| M2 | 2 (R1, R5) | 2 (R12) | 1 (R15) | M2 Tech Lead |
| M3 | 1 (R2) | 2 (R14) | 0 | M3 Tech Lead |
| M4 | 0 | 2 (R10, R13) | 1 (R20) | M4 Tech Lead |
| M5 | 1 (R3) | 3 (R6, R9) | 3 (R16, R17, R18) | M5 Tech Lead |
| M6-M7 | 2 (R4, R7) | 0 | 0 | M6-M7 Tech Lead |

---

## 🔄 Risk Monitoring Schedule

**Weekly (M1 Phase):**
- R1, R2, R3, R4, R5, R6, R7, R8, R11 (critical + high agent fabric)

**Bi-Weekly (M2-M4 Phase):**
- All risks tracked in sprint retrospectives
- Update probability/impact if status changes

**Monthly (M5-M7 Phase):**
- Formal risk review meeting
- Escalate any emerging risks

---

## ✅ Baseline Risk Acceptance

**Known Risks Accepted (Design Constraints):**
- TTFT budget (150ms) could exceed under heavy load → backpressure mitigates
- Learning loop could initially make performance worse → batch validation prevents
- PII detection has false negatives → RED band fallback mitigates

**Risk Owners:**
- **Critical Risks:** CTO + Architecture Lead (weekly sync)
- **High Risks:** Tech Lead per milestone (bi-weekly sync)
- **Medium Risks:** Team tracking (monthly review)

---

**Last Updated:** 2025-10-16
**Next Review:** Before M2 Start Approval
**Owner:** Architecture Team + Risk Committee
