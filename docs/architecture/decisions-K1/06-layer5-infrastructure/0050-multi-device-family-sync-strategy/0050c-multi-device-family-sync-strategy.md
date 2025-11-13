---
adr_number: 0050c
affected_layers:
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
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
- scalability
- security
- testing
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: null
implementation_phase: null
implementation_status: COMPLETED
propagation:
  affected_adrs:
  - ADR-0001
  - ADR-0001a
  - ADR-0017
  - ADR-0019
  - ADR-0024
  - ADR-0036
  - ADR-0050
  - ADR-0050a
  - ADR-0050b
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
  - Updating API contracts or schemas
related_adrs:
- ADR-0001
- ADR-0001a
- ADR-0017
- ADR-0019
- ADR-0024
- ADR-0036
- ADR-0050
- ADR-0050a
- ADR-0050b
related_contracts: []
related_diagrams: []
research_citations: []
status: PROPOSED
superseded_by: []
supersedes: []
title: Multi-Device Family Sync Strategy (Device-First, Hybrid)
---

# ADR-0050c: Multi-Device Family Sync Strategy (Device-First, Hybrid)

**Status:** ✅ Accepted

**Date:** 2025-10-16

**Deciders:** Product Team, Architecture

**Technical Story:** Q1 Resolution - Device-Centric Multi-Device Sync for FamilyOS

**Related Decision:** ADR-0050 (SessionState Coherence Guarantees)

**Parent ADR:** ADR-0050 (SessionState Coherence)

**Child ADRs:**
- 0050c-i (LAN Sync Implementation - Phase 1)
- 0050c-ii (P2P E2EE Internet Sync - Phase 2)
- 0050c-iii (Device Discovery & Topology)

**Related Architecture:**
- ADR-0001: K0/K1 Kernel Split
- ADR-0001a: K0 Bridge Communication
- ADR-0017: SessionState 6-Section Design
- ADR-0019: FlatBuffers Serialization (for device sync)
- ADR-0050a: Cross-Tier Coherence
- ADR-0050b: Master-Replica Replication (device-to-device)

---

## Context

### Problem Statement

FamilyOS is a privacy-first, device-centric system where every family member has personal devices (phone, tablet, laptop). **How should family memories and agent state sync across these devices?**

Key constraints:
1. **Privacy-first:** Family data MUST never leave family possession
2. **Device-autonomous:** Each device runs full K0 (memory) + K1 (agents)
3. **Network-aware:** Sync differently when home (LAN) vs. remote (internet)
4. **Low-latency:** LAN sync <1ms, internet sync <500ms P95
5. **Offline-capable:** Works without constant internet
6. **Future extensible:** Future home hub should enhance (not replace) device autonomy

### Current Situation

- K0 and K1 designed as full dual-kernel per device
- No multi-device sync strategy defined
- ADR-0050 (Coherence) is per-session, not per-family
- ADR-0050b (Master-Replica) designed for cross-region but applies to device-to-device
- Family data currently siloed to individual devices

### Constraints

| Constraint | Target | Why |
|-----------|--------|-----|
| **Privacy** | Zero cloud intermediary | Data ownership |
| **LAN Latency** | <1ms sync | Same-network performance |
| **Internet Latency** | <500ms P95 | Acceptable for remote devices |
| **TTFT (single device)** | <150ms | ADR-0024 budget maintained |
| **Offline** | Full functionality | No internet requirement |
| **Device Capability** | K0+K1 on any modern smartphone | 6-8GB RAM, 128GB+ storage available |
| **Battery** | Minimal sync overhead | Energy-efficient protocols |
| **Scalability** | 6-10 family devices typical | Some families have 20+, OK with degradation |

### Forces at Play

| Force | Direction | Impact |
|-------|-----------|--------|
| **Privacy imperative** | Device-local first | Zero cloud dependency |
| **Latency optimization** | LAN preferred, internet fallback | Use best available network |
| **Complexity** | Simple for MVP, progressive enhancement | Phase 1 (LAN), Phase 2 (Internet) |
| **Family autonomy** | Control own infrastructure | No vendor lock-in |
| **Device heterogeneity** | iOS, Android, macOS, Windows | Protocol must be agnostic |
| **Future extensibility** | Home hub enhancement, not control | Hub adds capabilities, doesn't gate access |

---

## Decision

### Chosen Approach: **HYBRID STRATEGY (Phase 1 + Phase 2)**

**Two phases, unblocks MVP in M2-M3 with clear Phase 2 path:**

---

## PHASE 1 (M2-M3, 4-5 weeks): LAN-First Sync

**Mechanism:** Devices discover and sync via local WiFi when home; devices can manually sync when apart

### Architecture (Phase 1)

```
┌─────────────────────────────────────────┐
│         Family Home (Same WiFi)          │
│                                          │
│  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ iPhone   │  │ Laptop   │  │ Tablet │ │
│  │ K0 + K1  │  │ K0 + K1  │  │ K0+K1  │ │
│  └──────────┘  └──────────┘  └────────┘ │
│       ↑          ↑ mDNS discovery         ↑ │
│       └──────────┼──────────────────────┘  │
│       (device discovery via mDNS)          │
│                                          │
│  ┌─────────────────────────────────────┐ │
│  │ K0 Bridge P07: CRDT Sync            │ │
│  │ - Devices announce presence (mDNS)  │ │
│  │ - Automatic discovery on same WiFi  │ │
│  │ - Direct device-to-device sync      │ │
│  │ - LWW (Last-Write-Wins) merge       │ │
│  │ - Latency: <1ms                     │ │
│  └─────────────────────────────────────┘ │
│                                          │
└─────────────────────────────────────────┘

When all devices are home on same WiFi:
  ✅ Mom adds memory on iPhone
  ✅ Tablet sees memory <50ms (LAN latency)
  ✅ Dad's laptop sees memory <50ms
  ✅ No internet needed
  ✅ No cloud storage
  ✅ 100% family privacy
```

### How It Works (Phase 1)

**Initialization:**
1. Each device runs K0 + K1 locally
2. On startup, device announces via mDNS: `familyos-{device-id}._tcp.local`
3. Other devices on same WiFi detect via mDNS listener
4. Devices establish peer-to-peer connections (TCP over LAN)

**Sync:**
```python
# Device A (iPhone) writes memory
k0.write(memory_item)  # Local write

# K0 broadcasts via K0 Bridge P07
k0_bridge.broadcast_change(memory_item)

# Device B (Laptop) on same WiFi receives
k0_bridge.receive_change()  # Via TCP connection
k0_merge(memory_item)  # CRDT merge (LWW - Last Write Wins)
```

**Multi-Write Conflict (CRDT):**
```
Scenario: Mom writes "Birthday party 3pm" on iPhone at 14:00:00
          Dad writes "Birthday party 2pm" on Laptop at 14:00:00
          (same timestamp, different values)

Resolution (LWW):
  - Device IDs have canonical ordering (iPhone < Laptop alphabetically)
  - iPhone timestamp: 14:00:00.0001 (by device order)
  - Laptop timestamp: 14:00:00.0002
  - Result: iPhone wins (earlier timestamp)
  - Final value: "Birthday party 3pm" (Mom's version)

  Mom sees: "Birthday party 3pm" immediately
  Dad sees: Update message within <100ms
  Both converge to same state
```

**When Devices Leave Home:**
- Device loses WiFi connection
- mDNS discovery stops
- Local modifications continue (offline capability)
- Sync pauses until Phase 2 (internet sync) is built

**Future: Manual Sync Button (MVP)**
- While Phase 2 is being built
- User can manually trigger sync upload/download
- Temporary workaround for remote devices

### Phase 1 Implementation (4-5 weeks)

| Week | Task | Owner | Details |
|------|------|-------|---------|
| **1** | Device startup & mDNS registration | Backend | Each device announces on startup |
| **1** | Peer discovery module | Backend | Scan LAN for other family devices |
| **2** | K0 Bridge P07 TCP sync | Backend | Direct device-to-device TCP |
| **2** | CRDT merge (LWW conflict resolution) | Backend | Last-Write-Wins per device ID |
| **3** | Testing: Multi-device LAN sync | QA | 3-6 device combinations |
| **3** | Conflict resolution testing | QA | Simultaneous writes from devices |
| **4** | Manual sync UI (MVP) | Frontend | Button for remote devices |
| **4** | Integration with SessionState | Backend | Update K0 persistence |
| **5** | Observability: Sync metrics | DevOps | mDNS discovery times, merge latency |

### Latency Profile (Phase 1)

```
Single Device (normal):
├─ Write to local K0: 1ms
├─ TTFT for K1 inference: 150ms (unchanged)
└─ TOTAL: 151ms ✅

Multi-Device LAN Sync:
├─ Device A writes to K0: 1ms
├─ K0 broadcasts via mDNS: 5ms (LAN discovery)
├─ Device B receives: 2ms (TCP)
├─ Device B CRDT merge: 3ms
├─ Device B updates SessionState: 2ms
└─ TOTAL latency for sync: ~13ms ✅ (<50ms target)
```

### Strengths (Phase 1)

- ✅ **Zero cloud:** No internet required, no vendor dependency
- ✅ **Simple:** mDNS discovery + TCP + CRDT merge
- ✅ **Fast:** <1ms LAN latency
- ✅ **Offline:** Devices work independently
- ✅ **Privacy:** 100% local, family-owned
- ✅ **MVP ready:** Unblocks M2-M3 start
- ✅ **Extensible:** Clear path to Phase 2

### Weaknesses (Phase 1)

- ⚠️ No remote sync while away from home
- ⚠️ Manual sync button temporarily (until Phase 2)
- ⚠️ mDNS reliability on some WiFi networks
- ⚠️ No cross-WiFi sync (different networks)

---

## PHASE 2 (M4-M5, 8-9 weeks): P2P E2EE Internet Sync

**Mechanism:** Devices sync via E2EE internet protocol when remote; automatic LAN fallback when home

### Architecture (Phase 2)

```
┌────────────────────────────────────────────┐
│  Device Network (Any Internet Connection)   │
│                                             │
│  Mom at Office (Office WiFi)               │
│     ↓ K0 local changes                     │
│     ↓ E2EE encrypted tunnel                │
│     ↓ P2P connection to other devices      │
│     ↓ CRDT merge (same as Phase 1)         │
│                          ↓                 │
│  Dad at Home (Home WiFi)                   │
│     ↓ Receives E2EE message                │
│     ↓ CRDT merge with LAN changes          │
│                                             │
│  Kids at School (School WiFi)              │
│     ↓ Same protocol                        │
│                                             │
│  ✅ No cloud relay, no intermediary        │
│  ✅ E2E encrypted end-to-end               │
│  ✅ Device-to-device connection            │
│  ✅ Automatic LAN preference when home     │
│  ✅ Latency: 50-200ms over internet        │
│  ✅ Privacy: 100% maintained               │
└────────────────────────────────────────────┘
```

### How It Works (Phase 2)

**E2EE Protocol (Similar to Signal/WhatsApp):**

1. **Device Certificates:** Each device gets unique E2EE cert
2. **Handshake:** Devices authenticate via cert verification
3. **Message Format:** FlatBuffers schema wrapped in E2EE encryption
4. **Transport:** Uses K0 Bridge P07 (already designed for cross-device)
5. **Fallback:** Automatic LAN preference (mDNS first, then internet)

```python
# Device A (remote, office WiFi)
memory_change = k0.get_delta()  # Get changes since last sync

# Wrap in K0 Bridge P07 message with E2EE
p07_message = K0Bridge.P07(
    sender_device_id="iphone-mom",
    receiver_device_ids=["laptop-dad", "tablet-kid"],
    content=FlatBuffersEncode(memory_change),
    encryption="AES256-GCM",  # E2EE
    signature="ED25519"  # Authentication
)

# Send via internet (device-to-device tunnel)
device_router.send_p2p(p07_message)

# Device B (home, receives via LAN or internet)
p07_message = device_router.receive()
memory_change = E2EEDecrypt(p07_message.content)
k0_merge(memory_change)  # CRDT merge
```

**Hybrid Network Detection:**

```python
# On every sync opportunity
devices_on_lan = mDNS.discover()

if devices_on_lan:
    # Prefer LAN (faster, no internet needed)
    sync_via_lan(devices_on_lan)
else:
    # Fall back to internet E2EE
    sync_via_internet_e2ee()
```

### Phase 2 Implementation (8-9 weeks, parallel to Phase 1)

| Week | Task | Owner | Details |
|------|------|-------|---------|
| **1-2** (M3 overlap) | E2EE cert infrastructure | Backend | Device certs, rotation, revocation |
| **2-3** | P2P internet tunnel | Backend | Device-to-device connection mgmt |
| **3-4** | K0 Bridge P07 encryption | Backend | FlatBuffers + AES256-GCM |
| **4-5** | Network detection (LAN vs internet) | Backend | Automatic preference logic |
| **5-6** | CRDT merge (same as Phase 1) | Backend | Reuse from Phase 1 |
| **6-7** | Testing: Multi-device internet sync | QA | Latency, encryption, fallback |
| **7-8** | Cross-country testing | QA | USA → Europe → Asia |
| **8-9** | GA rollout (feature flag) | Ops | Gradual rollout to users |

### Latency Profile (Phase 2)

```
LAN Home (automatic fallback):
├─ Device A writes: 1ms
├─ mDNS discovery (local): 5ms
├─ LAN sync: 13ms
└─ TOTAL: 19ms ✅ (same as Phase 1)

Internet Remote (office):
├─ Device A writes: 1ms
├─ Network detection: 50ms
├─ E2EE encrypt: 5ms
├─ Internet tunnel to Device B: 120ms (US-EU typical)
├─ E2EE decrypt: 5ms
├─ CRDT merge: 3ms
└─ TOTAL: ~180ms ✅ (<500ms target)

Automatic Fallback:
├─ Device at home left home WiFi: 5s
├─ Network detection: 10ms
├─ Fallback to internet: automatic
├─ Next change syncs via internet: 180ms
└─ When home again: automatic LAN preference
```

### Strengths (Phase 2)

- ✅ **Full autonomy:** Sync works anywhere, anytime
- ✅ **E2EE:** No cloud intermediary sees data
- ✅ **Hybrid:** LAN when possible, internet when needed
- ✅ **Transparent:** Users don't see the difference
- ✅ **Privacy maintained:** Still 100% family-owned
- ✅ **Global:** Works across countries

### Weaknesses (Phase 2)

- ⚠️ Complex E2EE infrastructure
- ⚠️ Device cert management & rotation
- ⚠️ Internet latency (unavoidable physics, 100-500ms)
- ⚠️ Requires careful testing (P2P, firewalls, NAT)

---

## FUTURE: Home Hub (Optional, Post-M5)

### Why Home Hub (Not Required, Optional Enhancement)

```
┌─────────────────────────────────────────────┐
│  Home Hub (Alexa-like device, optional)      │
│  ┌────────────────────────────────────────┐  │
│  │  K0 (full memory store)                │  │
│  │  K1 (advanced agents)                  │  │
│  │  Acts as LAN coordinator               │  │
│  └────────────────────────────────────────┘  │
│              ↑ WiFi                          │
│    ┌─────────┼─────────┐                    │
│    ↓         ↓         ↓                    │
│  iPhone   Laptop    Tablet                  │
│  (K0+K1) (K0+K1)   (K0+K1)                 │
│  Full     Full       Full                   │
│  Local    Local      Local                  │
│                                              │
│ Hub benefits:                                │
│  - Faster discovery on larger networks      │
│  - Advanced agent capabilities              │
│  - Backup storage (optional)                │
│  - Ambient features (voice, routines)       │
│                                              │
│ NOT required - all devices work standalone  │
└─────────────────────────────────────────────┘
```

**Hub is enhancement, not dependency:**
- Devices work full K0+K1 without hub
- Hub adds convenience, not gating
- Can be added anytime (M6+)
- Source-accessible under a proprietary license, family-owned, privacy-first

---

## Comparison: FamilyOS vs. Cloud Architecture

| Aspect | FamilyOS (Device-First) | Cloud Model (NOT us) |
|--------|------------------------|----------------------|
| **Data Storage** | Each device (SQLite) | Cloud database |
| **Sync Method** | LAN + P2P E2EE | DNS geolocation routing |
| **Latency (home)** | <1ms LAN | 50-150ms cloud |
| **Privacy** | 100% family-owned | Cloud provider sees data |
| **Cost** | Free (owned devices) | $1.50-1.80/user/month |
| **Offline** | Full functionality | No (requires cloud) |
| **Vendor** | Source-accessible, portable | AWS/GCP/Azure lock-in |
| **Control** | Family | Company / government |

---

## ADR Dependencies & Consequences

### Blocks (Now Unblocked ✅)

- **E2.8 (SessionState Coherence):** Blocked waiting for sync strategy → NOW UNBLOCKED
  - Can implement ADR-0050 per-device
- **E2.1 (Multi-Device LAN Sync):** New epic (Phase 1)
- **E2.2 (P2P E2EE Internet Sync):** New epic (Phase 2)

### Related ADRs

| ADR | Purpose | Relationship |
|-----|---------|--------------|
| **ADR-0001** | K0/K1 Kernel Split | Each device runs both |
| **ADR-0001a** | K0 Bridge Communication | Enables P07 device-to-device |
| **ADR-0017** | SessionState 6-Section Design | Synced via CRDT |
| **ADR-0019** | FlatBuffers Serialization | Device-to-device messages |
| **ADR-0050** | SessionState Coherence | Per-device coherence (CRDT merge) |
| **ADR-0050a** | Cross-Tier Coherence | Device-local tiers only |
| **ADR-0050b** | Master-Replica Replication | Device-to-device CRDT |
| **ADR-0024** | Performance Budgets | <1ms LAN, <500ms internet |
| **ADR-0036** | E2EE for RED band | Used in P2P internet sync |

### Consequences

**Positive:**
- ✅ Privacy: Zero cloud intermediary
- ✅ Autonomy: Family owns infrastructure
- ✅ Performance: <1ms LAN sync
- ✅ Offline: Works without internet
- ✅ Cost: Zero per-user cloud cost
- ✅ Extensibility: Clear Phase 2 path
- ✅ Unblocks M2 start immediately

**Trade-offs:**
- ⚠️ Phase 1 no remote sync (manual button temporarily)
- ⚠️ Phase 2 requires complex E2EE infrastructure
- ⚠️ mDNS reliability depends on WiFi network
- ⚠️ Device heterogeneity (iOS/Android/macOS/Windows) increases testing burden

---

## Implementation Timeline

### PHASE 1 (M2-M3): LAN-First Sync
- **Start:** 2025-10-23 (Week 1 of M2)
- **Deliverable:** Multi-device LAN sync (Phase 1)
- **Unblocks:** E2.8, E2.1
- **Success:** 3-6 devices sync <50ms on LAN

### PHASE 2 (M4-M5): P2P E2EE Internet
- **Start:** 2025-01-06 (M4, parallel planning)
- **Build:** During M3 (don't block Phase 1)
- **Deploy:** M5 (feature flag)
- **Unblocks:** E2.2, cross-device autonomy
- **Success:** Devices sync <500ms over internet

### Future: Home Hub (Post-M5)
- Optional enhancement
- Requires Phase 1 + 2 stable
- Design: TBD (not Q1)

---

## Verification Strategy

### Testing (WARD Framework)

```python
from ward import test, fixture
import asyncio

@fixture
async def multidevice_lan_setup():
    """Fixture: 3+ devices on test LAN"""
    setup = MultiDeviceLANTestBed()
    await setup.initialize_devices(count=3)
    yield setup
    await setup.teardown()

@test("mDNS discovery finds all devices on LAN")
async def _(setup=multidevice_lan_setup):
    devices = await setup.discover_devices()
    assert len(devices) >= 3
    assert all(d.online for d in devices)

@test("LAN sync <50ms for single write")
async def _(setup=multidevice_lan_setup):
    device_a, device_b = setup.devices[:2]

    start = time.time()
    await device_a.k0.write(memory_item)
    await wait_for_sync(device_b)
    latency = (time.time() - start) * 1000  # ms

    assert latency < 50
    assert device_b.k0.read(memory_item.id) == memory_item

@test("CRDT merge resolves conflicts (LWW)")
async def _(setup=multidevice_lan_setup):
    device_a, device_b = setup.devices[:2]

    # Simultaneous writes
    item_a = MemoryItem(id="1", value="A", ts=1000)
    item_b = MemoryItem(id="1", value="B", ts=1000)

    await asyncio.gather(
        device_a.k0.write(item_a),
        device_b.k0.write(item_b)
    )

    # Wait for convergence
    await asyncio.sleep(0.5)

    # Both should have same value (A wins per device ID order)
    result_a = device_a.k0.read("1")
    result_b = device_b.k0.read("1")
    assert result_a == result_b
    assert result_a.value == "A"  # Canonical winner

@test("Manual sync (Phase 1 MVP) transfers all changes")
async def _(setup=multidevice_lan_setup):
    device_a, device_b = setup.devices[:2]

    # Simulate device_b offline
    await device_b.disconnect_lan()

    # Write on device_a
    for i in range(10):
        await device_a.k0.write(MemoryItem(id=f"item-{i}"))

    # Manually sync
    await device_a.manual_sync_to_device(device_b.id)

    # Verify all 10 items on device_b
    items_b = await device_b.k0.list_all()
    assert len(items_b) == 10
```

### Observability Metrics

```yaml
metrics:
  - name: "multidevice_lan_discovery_latency"
    type: "histogram"
    buckets: [10, 50, 100, 500, 1000]  # ms
    labels: ["device_count"]

  - name: "sync_latency_lan"
    type: "histogram"
    buckets: [1, 5, 10, 20, 50, 100]  # ms
    labels: ["device_pair"]

  - name: "crdt_merge_conflicts"
    type: "counter"
    labels: ["conflict_type"]  # "lww_write", "concurrent_write"

  - name: "manual_sync_completeness"
    type: "gauge"
    labels: ["device_id"]  # % of items transferred

  - name: "internet_sync_latency"
    type: "histogram"
    buckets: [50, 100, 200, 500, 1000]  # ms (Phase 2)
    labels: ["source_region", "dest_region"]
```

---

## Sign-Off & Next Steps

### Decision Captured ✅

**HYBRID STRATEGY (Device-First):**
- **Phase 1 (M2-M3):** LAN-first sync
- **Phase 2 (M4-M5):** P2P E2EE internet sync
- **Zero cloud dependency** throughout

### Roadmap Updates Needed

```yaml
Milestones to update:
  M2:
    - Remove "E5.11 Kubernetes Deployment" (cloud, not family)
    - Add E2.1: Multi-Device LAN Sync
  M3:
    - Parallel planning for Phase 2
  M4-M5:
    - E2.2: P2P E2EE Internet Sync
```

### Implementation Owner

- **Phase 1:** Backend + QA (mDNS, CRDT, manual sync UI)
- **Phase 2:** Backend + DevOps (E2EE infrastructure, P2P tunnels)

### Timeline

- **Phase 1 start:** 2025-10-23 (M2 Week 1)
- **Phase 1 complete:** 2025-12-01 (M3 end)
- **Phase 2 start:** 2025-01-06 (M4 Week 1)
- **Phase 2 complete:** 2025-03-01 (M5 end)

---

## Rationale

### Why Device-First?

1. **Privacy:** Family data stays in family devices
2. **Economics:** Devices already owned (no cloud subscription)
3. **Autonomy:** No vendor dependency
4. **Performance:** LAN <1ms vs cloud 50-150ms
5. **Offline:** Works without internet

### Why Hybrid (Phase 1 + Phase 2)?

1. **MVP speed:** Phase 1 unblocks M2 start
2. **Risk reduction:** mDNS well-tested, no complex E2EE yet
3. **Progressive enhancement:** Phase 2 improves, doesn't replace
4. **Clear path:** No rework between phases

### Why NOT Cloud?

- ❌ Violates privacy-first principle
- ❌ Data in vendor hands (GDPR, privacy laws)
- ❌ Per-user subscription cost
- ❌ Vendor lock-in
- ❌ No offline capability
- ❌ Latency higher (50-150ms vs <1ms LAN)

---

## References

### Research & Standards

- **mDNS (RFC 6762):** Multicast DNS for local service discovery
- **CRDT Research:** Conflict-free replicated data types (Shapiro et al. 2011)
- **Signal Protocol:** E2EE messaging (Open Whisper Systems)
- **QUIC Protocol:** UDP-based P2P transport (RFC 9000)

### Architecture Diagrams

- `architecture_diagrams/k1_agent_lifecycle_fsm.mmd` (device lifecycle)
- `architecture_diagrams/k0_k1_integration_architecture.mmd` (device-local K0/K1)
- Related: ADR-0001 (K0/K1 split)

---

**Last Updated:** 2025-10-16
**Version:** 1.0 (Device-First, Hybrid)
**Status:** Ready for Implementation
**Approval:** ✅ Product Team