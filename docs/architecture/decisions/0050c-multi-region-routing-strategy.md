# ADR-0050c: Multi-Region Routing Strategy

**Status:** ✅ Accepted

**Date:** 2025-10-16

**Deciders:** Product Manager, Engineering Lead, Infrastructure Lead, Backend Lead

**Technical Story:** Q1 Resolution - Multi-Region Routing for K1 Dual-Kernel Deployment

**Related Decision:** ADR-0050 (SessionState Coherence Guarantees)

**Parent ADR:** ADR-0050

**Child ADRs:** 0050c-i (Phase 1 DNS implementation), 0050c-ii (Phase 2 CRDT migration)

---

## Context

### Problem Statement

K1 Intelligence Module is a production dual-kernel system (ADR-0001) consisting of:
- **K0 (Memory Microkernel)**: Durable storage with SQLite WAL, policy enforcement, receipts
- **K1 (Agentic Intelligence Kernel)**: Real-time orchestrator with 52 modules, 5 layers, Actor Model

Both kernels must be deployed in **multiple geographic regions** (US-East, EU-Central, APAC-Singapore) for:
1. **Low latency** to end users across the globe
2. **Regional compliance** (data residency in EU, APAC)
3. **Fault tolerance** (regional failover)
4. **Cost efficiency** (per-user pricing model)

**Critical Question:** How should user requests be routed to the best K1 region when both K0 (data) and K1 (orchestration) live in separate regions?

### Current Situation

- K1 and K0 are fully decoupled (ADR-0001: K0/K1 Kernel Split)
- K1 communicates with K0 via K0 Bridge (ADR-0001a: K0-Bridge Communication Protocol) with <10ms latency requirement
- Each region has standalone K0 (PostgreSQL/DynamoDB) and K1 clusters
- SessionState (64KB soft limit, ADR-0017) lives in region-local K0 databases
- Users connect via WebSocket/REST/SSE from their device
- No global routing strategy yet defined

**Blocking Issues:**
- E2.8 (SessionState Coherence) depends on routing decision
- E2.7 (Multi-Tier Storage) depends on cross-region replication strategy
- E5.11 (Kubernetes Deployment) needs endpoint strategy

### Constraints

| Constraint | Target | Why |
|-----------|--------|-----|
| **TTFT Latency (P95)** | <150ms | ADR-0024: Performance Budgets |
| **K0↔K1 Bridge Latency** | <10ms | ADR-0001a: K0 Bridge SLA |
| **SessionState Size** | 64KB soft limit | ADR-0017: 6-section design |
| **Regional Failover** | <30s detection | SLA for session continuity |
| **Operational Complexity** | Manageable 24/7 | SRE team support requirement |
| **Dual Kernel Shipping** | K0 + K1 together | ADR-0001: Microkernel boundary |

### Forces at Play

| Force | Direction | Impact |
|-------|-----------|--------|
| **Latency optimization** | Minimize regional hops | User sees <70ms same-region RTT |
| **Session consistency** | Maximize read-your-write guarantee | ADR-0050: Session guarantees within region |
| **Implementation velocity** | Fast to ship in M2-M3 | Unblocks cohesion work (E2.8, E2.7) |
| **Travel scenarios** | Handle user movement | London → Singapore mid-session |
| **CRDT complexity** | Minimize distributed systems burden | Build Phase 2 infrastructure gradually |
| **Deployment coupling** | K0 + K1 ship together | No independent regional deployment |

---

## Decision

### Chosen Approach: **HYBRID STRATEGY (Phase 1 → Phase 2)**

We adopt a **two-phase hybrid strategy** leveraging the dual-kernel architecture (ADR-0001):

#### **PHASE 1 (M2-M3, 4-5 weeks): DNS Geo-Routing**

**Mechanism:** Route users to nearest region via DNS geolocation (Route53, Cloudflare)

```
User in London (Client)
    ↓ DNS Query: k1.example.com
    ↓ Route53 Geolocation Policy:
       - EU IP ranges → eu-central-1.k1.example.com
       - US IP ranges → us-east-1.k1.example.com
       - APAC IP ranges → ap-southeast-1.k1.example.com
    ↓ Client TCP connects to nearest K1 cluster
    ↓ K1 authenticates, creates session in region-local K0
    ↓ SessionState lives in eu-central-1 K0 database
    ↓ K1↔K0 communication <10ms (same region, ADR-0001a)
    ↓ Response streamed back to client
```

**Implementation (4-5 weeks):**

| Phase | Task | Effort | Owner |
|-------|------|--------|-------|
| **Week 1** | Deploy K1+K0 to us-east-1, eu-central-1, ap-southeast-1 | 2w | Infrastructure |
| **Week 1** | Set up Route53 geolocation policies + health checks | 3d | DevOps |
| **Week 2** | Deploy PostgreSQL/DynamoDB per region (standalone, no replication) | 1w | Database |
| **Week 3-4** | Failover testing, runbooks, monitoring | 2w | QA + Ops |
| **Total** | **4-5 weeks** | | |

**Latency Profile (Phase 1):**

```
Same-Region Happy Path (London user → EU):
├─ DNS lookup (cached): 1ms
├─ TCP + TLS handshake: 15ms (London ↔ eu-central-1)
├─ K1 authentication: 20ms
├─ K1 request routing (Pure Actor orchestrator, ADR-0006): 30ms
├─ K0 Bridge (K1 ↔ K0, <10ms per ADR-0001a): 8ms
├─ K0 SessionState lookup: 5ms
├─ LLM inference (Model Hub placement, ADR-0027): 50ms
├─ Response streaming: 10ms
└─ TOTAL TTFT: ~70ms ✅ (under 150ms budget per ADR-0024)

Cross-Region Failover (London user → US, EU failed):
├─ DNS health check detects EU failure: 5-10s
├─ Route53 propagates to client: 10-30s
├─ Client TCP connects to us-east-1 (140ms RTT): 140ms
├─ K1 re-authenticates: 20ms
├─ K0 session lookup (not in US DB): MISS → recreate session from K0 receipts
├─ Session recovery (K0 audit trail, ADR-0038): 200-500ms
├─ Resume processing: 30ms
└─ TOTAL FAILOVER TIME: 30-60s ⚠️ (acceptable SLA, temporary)
```

**Strengths (Phase 1):**
- ✅ **Simplicity**: Standard DNS behavior, no client logic
- ✅ **Fast to ship**: Unblocks E2.8, E2.7 in M2-M3
- ✅ **Low operational burden**: Route53 is AWS-managed
- ✅ **Cost efficient**: No cross-region replication ($1.50/user)
- ✅ **Same-region guarantee**: K1↔K0 latency <10ms always met
- ✅ **Dual-kernel aligned**: K0 stays region-local, no complexity

**Weaknesses (Phase 1):**
- ❌ Cross-region travel: London user flies to Singapore → 480ms latency spike during travel
- ⚠️ Regional outage: All EU users affected if eu-central-1 fails (but health-check failover available)
- ⚠️ DNS stickiness: 60-300s failover latency due to DNS TTL

**Who builds Phase 1:**
- **Infrastructure**: Deploy dual-kernel to 3 regions
- **DevOps**: Route53 + health checks
- **Backend**: Ensure regional databases are standalone

---

#### **PHASE 2 (M4-M5, 8-9 weeks): Smart Client Routing**

**Mechanism:** Client probes all regions, picks fastest, auto-migrates session using CRDT merge (K0 Bridge, ADR-0001a)

**Architecture (Phase 2):**

```
User App Startup:
    ↓ Run latency probes to all regions:
       - Ping us-east-1: 120ms
       - Ping eu-central-1: 45ms ← FASTEST
       - Ping ap-southeast-1: 200ms
    ↓ Client connects to eu-central-1 (fastest K1 endpoint)
    ↓ SessionState created in eu-central-1 K0
    
    [Later: User travels London → Singapore]
    ↓ Re-probe latencies:
       - Ping us-east-1: 180ms
       - Ping eu-central-1: 300ms
       - Ping ap-southeast-1: 20ms ← FASTEST NOW
    ↓ K1 detects latency ratio > 2x → initiate migration
    ↓ K0 exports SessionState snapshot (FlatBuffers delta, ADR-0019)
    ↓ K0 Bridge syncs to ap-southeast-1 K0 (CRDT merge, ADR-0050b)
    ↓ Conflict resolution: LWW for conflicts, causal ordering preserved
    ↓ Client reconnects to ap-southeast-1 K1
    ↓ Resume from checkpoint (no session loss)
```

**When to build Phase 2:**
- After Phase 1 stable in production (M3-M4)
- When travel use case becomes important
- Build infrastructure in parallel (don't block M2-M3)

**Latency Profile (Phase 2):**

```
Optimal Case (London → EU, 90ms normal):
├─ Latency probes: 20ms
├─ TCP + TLS: 15ms
├─ K1 auth: 20ms
├─ K1→K0 (K0 Bridge): 8ms
├─ LLM inference: 50ms
└─ TOTAL: ~90ms ✅

Session Migration (London → Singapore mid-turn):
├─ Latency probes detect: 5ms
├─ Pause current request: 50ms
├─ Export SessionState (100MB): 200ms
├─ CRDT merge (K0 ↔ K0): 100ms
├─ Resume in new region: 50ms
└─ TOTAL MIGRATION: ~400ms (user sees spike, but auto-transparent)
```

---

## Multi-Region K0 + K1 Deployment Model

### **How K0 and K1 Deploy Together**

Since K0 and K1 ship as unified dual-kernel system (ADR-0001):

| Component | Deployment Model | Notes |
|-----------|-----------------|-------|
| **K0 (Memory Microkernel)** | Per-region standalone SQLite + WAL | Each region has independent database |
| **K1 (Agentic Kernel)** | Per-region 52-module cluster (5 layers) | Communicates to local K0 via Bridge |
| **K0 Bridge (ADR-0001a)** | Intra-region HTTP/2 multiplexing | K1 ↔ K0 <10ms SLA always met |
| **K0↔K0 Sync (Phase 2)** | Cross-region async CRDT (K0 Bridge P07) | Only if user migrates between regions |
| **Shared Config** | Global config server (ConfigMap/Secrets) | Shared hot-reload (ADR-0059: Learning Loop) |

### **Why This Works:**

1. **Phase 1 simplicity**: Each region is independent; no cross-region coupling
   - K0 stays region-local → No distributed consistency burden
   - K1 stays region-local → No scheduler changes needed
   - Both ship together → Single deployment artifact

2. **Phase 2 upgrade path**: K0 Bridge already exists (ADR-0001a)
   - Adds P07 (E2EE Sync) for session migration
   - Leverages CRDT infrastructure (ADR-0050b already designed)
   - Transparent to end-user (no client changes until Phase 2)

3. **Operational clarity**: "Ship together, scale together"
   - SREs see one deployment unit (K0+K1)
   - Performance budgets apply to both
   - Observability unified (ADR-0029: Prometheus metrics)

---

## Consequences

### ✅ Positive Consequences

| Consequence | Impact | Timing |
|-------------|--------|--------|
| **Unblocks E2.8 (SessionState Coherence)** | Can implement ADR-0050 guarantees per-region | M2 starts immediately |
| **Unblocks E2.7 (Multi-Tier Storage)** | Clear region-local K0 storage strategy | M2 starts immediately |
| **Meets TTFT budget** | 70ms same-region latency ✅ | M2 achieves |
| **Fast failover** | Route53 health checks → <30s detection | M2-M3 ops |
| **Cost efficient** | $1.50/user (cheapest option) | M2+ budgets |
| **Operational simplicity** | Route53 is battle-tested, low complexity | M2+ SRE ready |
| **Dual-kernel aligned** | K0 stays standalone, K1 stays coordinated | Architecture preserved |
| **Future migration path** | Phase 2 CRDT built gradually, no rush | M4-M5 planning |

### ⚠️ Trade-offs

| Trade-off | Resolution | Timeline |
|-----------|-----------|----------|
| **Travel scenario** | Cross-region travel = 480ms latency spike | Phase 2 (M4-M5) solves |
| **Regional outage impact** | EU users see 480ms during failover | Acceptable SLA; 5% of users travel |
| **DNS propagation** | 60-300s failover delay | Health checks detect faster |
| **No immediate CRDT** | CRDT infrastructure deferred | Build Phase 2 in parallel |

### 📊 Cost Comparison

| Aspect | Phase 1 (DNS) | Phase 2 (CRDT) | Delta |
|--------|---------------|----------------|-------|
| **K1 Orchestrator (per region)** | $3K | $3K | — |
| **K0 Storage (per region)** | $1.5K | $1.5K | — |
| **Cross-region replication** | $0 | +$2K | +$2K |
| **Network probes** | $0 | +$1K | +$1K |
| **Total/month (3 regions)** | ~$15K | ~$18K | +20% |
| **Per-user (10K users)** | **$1.50** | $1.80 | +$0.30 |

---

## ADR Dependencies

### **References**

| ADR | Purpose | Relationship |
|-----|---------|--------------|
| **ADR-0001** | K0/K1 Kernel Split | Parent: Dual-kernel foundation |
| **ADR-0001a** | K0 Bridge Communication | Enables K1↔K0 <10ms (same region) |
| **ADR-0001f** | K0/K1 Pipeline Boundary | Enforces port contracts (P01-P20) |
| **ADR-0017** | SessionState 6-Section Design | SessionState lives in K0 per-region |
| **ADR-0019** | FlatBuffers Serialization | SessionState export/import (Phase 2) |
| **ADR-0024** | Performance Budgets | TTFT <150ms, K0↔K1 <10ms |
| **ADR-0027** | Model Placement Cascade | LLM inference in K1 per region |
| **ADR-0038** | Audit Trail to K0 Receipts | Session recovery on failover |
| **ADR-0050** | SessionState Coherence | Parent: Read-your-write guarantees |
| **ADR-0050a** | Cross-Tier Coherence | Multi-tier consistency (Phase 1+) |
| **ADR-0050b** | Master-Replica Replication | Async replication for Phase 2 |
| **ADR-0059** | Learning Loop | Config hot-reload across regions |

### **Blocks**

- **E2.8 (SessionState Coherence)**: Blocked until routing strategy defined → **NOW UNBLOCKED ✅**
- **E2.7 (Multi-Tier Storage)**: Blocked until regional data strategy defined → **NOW UNBLOCKED ✅**
- **E5.11 (Kubernetes Deployment)**: Blocked until endpoint strategy defined → **NOW UNBLOCKED ✅**

### **Blocked By**

None (no dependencies)

---

## Implementation Plan

### **Phase 1 (M2-M3, Weeks 1-5)**

**Sprint 1 (Week 1):**
- [ ] Infrastructure deploys K0+K1 to us-east-1, eu-central-1, ap-southeast-1
- [ ] DevOps sets up Route53 geolocation records + health checks
- [ ] Monitoring: Add region tags to all Prometheus metrics (ADR-0029)

**Sprint 2-3 (Weeks 2-3):**
- [ ] Database: Deploy PostgreSQL/DynamoDB per region (standalone)
- [ ] K1: Test regional authentication flow (WebSocket/REST/SSE)
- [ ] K0: Verify per-region SessionState isolation (no cross-region leakage)

**Sprint 4 (Week 4):**
- [ ] Failover testing: Simulate region failures, verify Route53 reroute
- [ ] Runbooks: Document manual failover, recovery procedures
- [ ] Load testing: Validate latency under load (50ms+ p95 budget headroom)

**Sprint 5 (Week 5):**
- [ ] Ops training: SRE team runthrough
- [ ] Observability: Deploy cross-region dashboards (latency, availability)
- [ ] Staged rollout: Internal → beta users → general availability

**Success Criteria (Phase 1):**
- ✅ TTFT P95 <70ms same-region
- ✅ Regional failover detected <30s
- ✅ No session loss on failover (K0 receipts recoverable)
- ✅ E2.8, E2.7, E5.11 unblocked

---

### **Phase 2 (M4-M5, Parallel Planning)**

**Build in Parallel (don't block Phase 1):**
- [ ] K0 Bridge: Implement P07 (E2EE Sync) for cross-region CRDT
- [ ] CRDT: Implement LWW merge for SessionState conflicts
- [ ] Client: Build latency probe library (mobile + web)
- [ ] Testing: Chaos tests for session migration

**Deploy Phase 2 (Week 1 of M5 onwards):**
- [ ] Enable smart client routing opt-in (feature flag)
- [ ] Beta: Test with early-adopter users
- [ ] Monitor: Migration success rate, latency improvements
- [ ] GA: Roll out to all users

---

## Verification Strategy

### **Testing (WARD Framework)**

```python
from ward import test, fixture
import asyncio

@fixture
async def multi_region_setup():
    """Fixture: K0+K1 deployed in 3 regions"""
    setup = MultiRegionTestBed()
    await setup.deploy_regions(["us-east-1", "eu-central-1", "ap-southeast-1"])
    yield setup
    await setup.teardown()

@test("DNS geo-routing routes London user to EU")
async def _(setup=multi_region_setup):
    # London IP should resolve to eu-central-1
    endpoint = await dns_resolve("k1.example.com", client_ip="85.1.2.3")
    assert endpoint == "eu-central-1.k1.example.com"

@test("K1 same-region latency <70ms")
async def _(setup=multi_region_setup):
    # Measure TTFT for London → EU request
    latency = await measure_ttft(
        region="eu-central-1",
        user_location="London"
    )
    assert latency < 70  # ms

@test("Route53 health checks detect regional failure")
async def _(setup=multi_region_setup):
    # Simulate EU region failure
    await setup.regions["eu-central-1"].kill()
    
    # Health check should detect within 30s
    time_to_detect = await wait_for_route53_update()
    assert time_to_detect < 30  # seconds

@test("K0 session recovery on failover")
async def _(setup=multi_region_setup):
    # User in EU, session in eu-central-1
    session = await setup.create_session(region="eu-central-1")
    
    # Simulate failover to US
    await setup.regions["eu-central-1"].kill()
    
    # Session should be recoverable from audit trail (ADR-0038)
    recovered_session = await setup.recover_session(session.id)
    assert recovered_session is not None
    assert recovered_session.beliefs == session.beliefs  # No data loss
```

### **Observability Metrics (ADR-0029)**

```yaml
# Prometheus metrics to track
metrics:
  - name: "k1_request_latency_by_region"
    type: "histogram"
    buckets: [10, 50, 70, 100, 150, 200]  # ms
    labels: ["region", "user_location"]
    
  - name: "route53_failover_latency"
    type: "histogram"
    buckets: [5, 10, 20, 30, 60]  # seconds
    
  - name: "k0_session_availability_by_region"
    type: "gauge"
    labels: ["region"]
    
  - name: "cross_region_session_migrations"
    type: "counter"
    labels: ["from_region", "to_region"]  # Phase 2
```

### **Monitoring Alerts**

```yaml
alerts:
  - name: "RegionalLatencySpike"
    condition: "k1_request_latency_by_region > 150ms for 5min"
    severity: "warning"
    
  - name: "FailoverDetectionSlow"
    condition: "route53_failover_latency > 60s"
    severity: "critical"
    
  - name: "SessionLoss"
    condition: "k0_session_availability_by_region < 0.95"
    severity: "critical"
```

---

## Rationale

### **Why Phase 1 DNS Geo-Routing?**

1. **Simplicity wins**: Route53 is AWS-managed, proven, low-ops burden
2. **Fast to ship**: Unblocks E2.8, E2.7, E5.11 in M2-M3 (critical path)
3. **Cost efficient**: No cross-region replication ($1.50/user vs $1.80/user)
4. **Dual-kernel aligned**: K0 stays standalone per-region, no distributed systems complexity
5. **Performance**: 70ms same-region latency well under 150ms budget
6. **Risk low**: Proven technology; Route53 health checks handle failover

### **Why Not Phase 1 Smart Client or Gateway Router?**

| Option | Issue | Impact |
|--------|-------|--------|
| **Smart Client (Option B)** | Requires CRDT infrastructure NOW | 8-9 weeks, blocks M2 start |
| | Client library changes needed | Deployment friction across platforms |
| | CRDT bugs = data loss risk | High complexity for first solution |
| **Gateway Router (Option C)** | Lambda@Edge routing complexity | Unnecessary complexity vs DNS |
| | WebSocket on API Gateway awkward | AWS API Gateway limitations |
| | Doesn't solve travel scenario | Same 480ms as DNS for travel |
| | Single point of failure (gateway) | Contradicts microkernel philosophy |

### **Why Phase 2 Smart Client?**

1. **Travel scenario solved**: London → Singapore = auto-switch (200ms vs 480ms)
2. **Built on proven foundation**: K0 Bridge + CRDT already designed (ADR-0050b)
3. **No rush**: Phase 1 handles 95% of users; travel is 5% edge case
4. **Learn first**: Phase 1 teaches us real-world latency patterns
5. **Infrastructure ready**: Build CRDT gradually in M3-M4, deploy M5

---

## Related Documents

### **Linked Decisions**
- **ADR Master Reference:** `docs/ADR_MASTER_REFERENCE.md`
- **K1 Architecture:** `docs/k1_module_analysis.md`
- **Performance Budgets:** `contracts/agent_lifecycle/performance_budgets.yml`
- **K0/K1 Bridge:** `contracts/k0_bridge/README.md`

### **Planning References**
- **Q1 Resolution Analysis:** `docs/plan/Q1_RESOLUTION_MEETING_ROUTING_OPTIONS.md`
- **Sequential Roadmap:** `docs/plan/SEQUENTIAL_ROADMAP.yaml` (M2-M5)
- **Open Questions:** `docs/OPEN_QUESTIONS.md` (Q1 entry)

### **Research Foundations**

| Paper | Concept | Application |
|-------|---------|-------------|
| **Terry et al. (1994)** | Session Guarantees | Read-Your-Writes consistency within region (ADR-0050) |
| **Amazon Route53** | Geolocation Routing | DNS-based regional routing (Phase 1) |
| **CRDT Research** | Conflict-Free Replication | Session migration Phase 2 (ADR-0050b) |
| **gRPC / Protobuf** | RPC Contracts | K0 Bridge architecture (ADR-0001a) |

---

## Sign-Off

**Decision Owner:** Product Manager, Engineering Lead

**Approval Date:** 2025-10-16

**Implementation Start:** 2025-10-23 (M2, Week 1)

**Phase 1 Target:** 2025-12-01 (M2-M3, production)

**Phase 2 Target:** 2025-02-01 (M4-M5, optional upgrade)

---

## Questions & Decisions to Lock In

### **Q1: Is the travel scenario important for MVP?**
✅ **Answer:** Defer to Phase 2 (M4-M5). Phase 1 serves 95% of use cases.

### **Q2: What's acceptable latency during cross-region failover?**
✅ **Answer:** 30-60s for DNS propagation is acceptable SLA. Session recovery via K0 receipts (ADR-0038).

### **Q3: Should we replicate K0 data cross-region in Phase 1?**
✅ **Answer:** NO. Keep regions standalone. Add replication only in Phase 2 if needed.

### **Q4: Is DNS geolocation accuracy acceptable (~5% misroute rate with VPN)?**
✅ **Answer:** YES. Route53 fallback to us-east-1 primary handles misroutes. Auto-failover on health checks.

### **Q5: Do K0 and K1 always ship together to each region?**
✅ **Answer:** YES (ADR-0001 mandate). Single deployment artifact = easier operations.

---

## Next Steps

1. ✅ **Get this ADR reviewed & approved** → Stakeholder sign-off
2. ⏳ **Create sub-ADRs**:
   - ADR-0050c-i: Phase 1 DNS Implementation Details
   - ADR-0050c-ii: Phase 2 CRDT Session Migration Protocol
3. ⏳ **Update roadmap**:
   - Add AWS Route53 setup to E5.11 (Kubernetes Deployment)
   - Add K0 per-region database to E2.7 (Multi-Tier Storage)
   - Link Phase 2 planning to M4-M5 epics
4. ⏳ **Spike investigation**:
   - Route53 failover latency validation (real test)
   - K0 session recovery performance testing
   - Regional deployment automation

---

**Last Updated:** 2025-10-16
**Version:** 1.0
**Status:** Ready for Implementation
