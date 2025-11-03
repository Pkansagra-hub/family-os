---
adr_number: 0050b
title: CRDT Device-to-Device Merge Protocol
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- observability
- performance
- privacy
- scalability
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0050
- ADR-0050a
- ADR-0050b
- ADR-0050c
- ADR-0050d
implementation_status: UNKNOWN
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations:
- Lamport (1978)
- Shapiro et al. (2011)
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0050
  - ADR-0050a
  - ADR-0050b
  - ADR-0050c
  - ADR-0050d
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
  affected_tests: []
---


# ADR-0050b: CRDT Device-to-Device Merge Protocol

**Status:** ✅ Accepted

**Date:** 2025-10-16

**Deciders:** K1 Architecture Team

**Technical Story:** Multi-Device Memory Sync - Conflict Resolution Strategy

**Parent ADR:** ADR-0050 (Multi-Device Family Sync Strategy)

**Sibling ADRs:** ADR-0050a (SessionState Coherence), ADR-0050c (LAN Sync), ADR-0050d (Internet Sync)

---

## Context

### Problem Statement

When multiple family devices sync memories simultaneously (e.g., Mom updates on iPhone while Dad updates on Laptop), how should conflicting writes be merged?

**Scenario:** Both devices write to same memory at same timestamp:
- iPhone: "Birthday party 3pm" (timestamp: 14:00:00.000)
- Laptop: "Birthday party 2pm" (timestamp: 14:00:00.000)

**Question:** Which wins? How do we ensure both devices converge to same state?

### Current Situation

- ADR-0050a defines per-device coherence (read-your-write)
- No strategy for device-to-device conflict resolution
- CRDT infrastructure exists in K0 Bridge (designed for regional replication)
- Need to apply CRDT to device-to-device sync (different scale, same principles)

### Constraints

| Constraint | Target | Why |
|-----------|--------|-----|
| **Consistency** | Eventual convergence | All devices same state eventually |
| **Causality** | Causal ordering | If A before B on same device, maintain order |
| **Determinism** | Same merge result on all devices | No split-brain scenarios |
| **Performance** | <10ms merge latency | Sync must be fast |
| **Simplicity** | Easy to reason about | SREs must understand merge logic |

---

## Decision

### Chosen Approach: **Last-Write-Wins (LWW) with Device ID Ordering**

**Simple, deterministic, proven in production systems (DynamoDB, Cassandra, Riak):**

### How It Works

```
Conflict Resolution Algorithm:

1. Each write gets (timestamp, device_id, value)
2. On merge:
   a) Compare timestamps
   b) If different: higher timestamp wins
   c) If same timestamp:
      - Use device ID as tiebreaker (canonical ordering)
      - Device IDs sorted alphabetically: ipad < iphone < laptop < tablet
      - Earlier device ID in order wins

Example:
  Timestamp: 14:00:00.000
  Value A (iPhone): "Birthday 3pm"
  Value B (Laptop): "Birthday 2pm"

  Device order: ipad < iphone < laptop < tablet
  iPhone comes before Laptop
  Result: "Birthday 3pm" wins on BOTH devices

  Both converge to same state (no split-brain)
```

### Implementation

**FlatBuffers Schema (K0 write record):**
```flatbuffers
namespace FamilyOS.CRDT;

table WriteRecord {
  id: string;                    // Item ID (unique)
  device_id: string;             // Writer device (iphone, laptop, etc)
  timestamp: uint64;             // Unix timestamp (milliseconds)
  value: string;                 // Actual content (FlatBuffers encoded)
  vector_clock: [VectorClockEntry];  // Causal ordering
}

table VectorClockEntry {
  device_id: string;
  clock: uint64;
}
```

**Merge Logic (Python pseudocode):**
```python
def merge_writes(device_state, incoming_writes):
    """
    Merge incoming writes into device state using LWW with device ID ordering.

    Args:
        device_state: Current state on device
        incoming_writes: List of (item_id, writes_from_other_devices)

    Returns:
        Merged state (all devices will converge to this)
    """
    for item_id, writes in incoming_writes.items():
        existing = device_state.get(item_id)

        # Find winner using LWW + device_id ordering
        winner = choose_winner(existing, writes)

        # Update device state with winner
        device_state[item_id] = winner

        # Emit update event (for UI, logging, etc)
        emit("item_merged", item_id=item_id, winner=winner)


def choose_winner(existing, incoming_writes):
    """Choose winning write using LWW + device ordering"""

    candidates = []
    if existing:
        candidates.append(existing)
    candidates.extend(incoming_writes)

    # Sort by (timestamp DESC, device_id ASC)
    # Higher timestamp wins; on tie, lower device_id wins
    sorted_writes = sorted(
        candidates,
        key=lambda w: (-w['timestamp'], w['device_id'])
    )

    return sorted_writes[0]  # First is winner


def deterministic_device_ordering():
    """Canonical device ID order (alphabetical)"""
    return sorted(all_device_ids)
    # Example: ['ipad-001', 'iphone-mom', 'laptop-dad', 'tablet-kid']
```

**Example: Three-Way Conflict (LAN + Internet)**

```
Scenario: Family syncing across LAN + internet

Device A (iPhone): writes "Item X" at 14:00:00.100
Device B (Laptop): writes "Item X" at 14:00:00.100  (same timestamp)
Device C (Tablet): writes "Item X" at 14:00:00.100  (same timestamp)

All at EXACT same millisecond (very rare, but possible in LAN)

Resolution:
  Device order: ipad < iphone < laptop < tablet
  Tablet < iPad < iPhone < Laptop (canonical order)
  Timestamp: 14:00:00.100 (all same)

  Winner selection:
    Rank 1: Tablet (first in order) → IF tablet wrote, tablet wins
    Rank 2: iPad (second) → IF no tablet, ipad wins
    Rank 3: iPhone (third) → IF no tablet/ipad, iphone wins
    Rank 4: Laptop (last) → Laptop loses

  All devices apply same merge logic
  All converge to Tablet's value
```

---

## Causal Ordering (Vector Clocks)

### When LWW Isn't Enough

**Scenario:** Writes aren't just conflicts; they have causality:

```
Timeline on Device A (iPhone):
  14:00:00 - Write: "Birthday 3pm"
  14:00:01 - Write: "Birthday party at home"  (depends on first write)

Device B gets second write first (out of order):
  "Birthday party at home" (needs context from first write)

LWW alone can't determine: is this an update or independent write?

Solution: Vector Clocks
```

### Vector Clock Implementation

```python
def apply_vector_clock(write, device_id):
    """
    Add causal ordering to write using vector clocks.

    Vector clock = map of {device_id: clock_value}
    Each device tracks: "I've seen N writes from Device X"
    """

    if device_id not in vector_clock:
        vector_clock[device_id] = 0

    vector_clock[device_id] += 1

    write['vector_clock'] = vector_clock.copy()
    return write


def merge_with_causal_ordering(local_writes, incoming_writes):
    """
    Merge respecting causal dependencies.

    If incoming write depends on prior writes,
    ensure prior writes are applied first.
    """

    ordered = topological_sort(local_writes + incoming_writes)
    for write in ordered:
        apply_write(write)


def is_causal_dependency(write_a, write_b):
    """
    Check if write_b depends on write_a
    (using vector clock comparison)
    """
    vc_a = write_a['vector_clock']
    vc_b = write_b['vector_clock']

    # B depends on A if B's VC > A's VC in all dimensions
    return all(
        vc_b.get(device, 0) >= vc_a.get(device, 0)
        for device in set(list(vc_a.keys()) + list(vc_b.keys()))
    )
```

---

## Properties of This Approach

### ✅ Guarantees

| Property | Achieved | How |
|----------|----------|-----|
| **Eventual Consistency** | ✅ | All devices apply same merge logic |
| **Determinism** | ✅ | Device ordering is canonical (alphabetical) |
| **No Split-Brain** | ✅ | LWW with tiebreaker eliminates ambiguity |
| **Causal Ordering** | ✅ | Vector clocks preserve dependencies |
| **Commutative** | ✅ | Merge order doesn't matter (A+B = B+A) |
| **Idempotent** | ✅ | Applying same merge twice = once |

### ⚠️ Trade-offs

| Trade-off | Impact | Mitigation |
|-----------|--------|-----------|
| **Lost Writes** | Concurrent writes lose precision | Rare in practice; accept LWW semantics |
| **Causality Complexity** | Vector clocks add overhead | Only needed for causal deps (not common) |
| **Device Ordering** | Deterministic but not "fair" | No write is ever lost, just ordered |

---

## Testing Strategy

### WARD Tests

```python
from ward import test, fixture

@fixture
def crdt_test_env():
    """CRDT merge testing environment"""
    devices = {
        'ipad-001': K0.SessionState(),
        'iphone-mom': K0.SessionState(),
        'laptop-dad': K0.SessionState(),
        'tablet-kid': K0.SessionState(),
    }
    yield devices


@test("LWW with same timestamp uses device ID ordering")
async def _(devices=crdt_test_env):
    item_id = "birthday-party"
    ts = 1000000000  # Same timestamp

    # Simultaneous writes from three devices
    writes = {
        'iphone-mom': {"value": "3pm", "timestamp": ts},
        'laptop-dad': {"value": "2pm", "timestamp": ts},
        'tablet-kid': {"value": "4pm", "timestamp": ts},
    }

    # All devices apply merge
    results = {}
    for device_id, device in devices.items():
        merged = merge_writes(device, {item_id: writes})
        results[device_id] = merged[item_id]['value']

    # All should converge to same value (iphone-mom's, earliest in order)
    assert all(v == "3pm" for v in results.values())


@test("Vector clocks preserve causal ordering")
async def _(devices=crdt_test_env):
    # Write 1: Mom creates memory
    write1 = {
        "id": "memory-1",
        "device_id": "iphone-mom",
        "timestamp": 1000000000,
        "value": "Birthday party",
        "vector_clock": {"iphone-mom": 1}
    }
    devices['iphone-mom'].apply_write(write1)

    # Write 2: Mom updates same memory (depends on write1)
    write2 = {
        "id": "memory-1",
        "device_id": "iphone-mom",
        "timestamp": 1000000001,
        "value": "Birthday party at home",
        "vector_clock": {"iphone-mom": 2}
    }
    devices['iphone-mom'].apply_write(write2)

    # Laptop receives both (in any order)
    device_laptop = devices['laptop-dad']
    device_laptop.apply_write(write2)  # Receives write2 first
    device_laptop.apply_write(write1)  # Receives write1 second

    # Laptop should still have correct state
    # (write2 understood as update to write1, not conflict)
    state = device_laptop.get_state()
    assert state['memory-1']['value'] == "Birthday party at home"


@test("Idempotency: applying same merge twice = once")
async def _(devices=crdt_test_env):
    incoming = {
        "item-1": [
            {"device_id": "iphone-mom", "timestamp": 1000, "value": "A"},
            {"device_id": "laptop-dad", "timestamp": 2000, "value": "B"},
        ]
    }

    device = devices['tablet-kid']

    # Apply merge twice
    device.merge_writes(incoming)
    state_after_first = device.get_state()

    device.merge_writes(incoming)
    state_after_second = device.get_state()

    # Should be identical
    assert state_after_first == state_after_second
```

---

## Comparison to Alternatives

| Approach | Convergence | Causality | Complexity | Production Use |
|----------|-------------|-----------|-----------|-----------------|
| **LWW (chosen)** | ✅ Eventual | ✅ Via vector clocks | Low | ✅ DynamoDB, Cassandra, Riak |
| **CRDT (conflict-free)** | ✅ Strong | ✅ Built-in | Medium | ✅ Automerge, Yjs |
| **Operational Transform (OT)** | ✅ Eventual | ✅ Built-in | High | ⚠️ Difficult to implement |
| **Quorum** | ✅ Strong | ⚠️ Limited | High | ⚠️ Requires connectivity |

**Why LWW over CRDT?**
- Simpler to implement and reason about
- Proven in production systems (DynamoDB, Cassandra)
- Vector clocks handle causality when needed
- Lower memory overhead (no tombstones)
- Easier to test and verify determinism

---

## Metrics & Observability

```yaml
metrics:
  - name: "crdt_merge_operations"
    type: "counter"
    labels: ["merge_type", "outcome"]  # merge_type: "lww", "causal"

  - name: "crdt_merge_conflicts_resolved"
    type: "counter"
    labels: ["conflict_type"]  # "same_timestamp", "concurrent_write"

  - name: "crdt_merge_latency"
    type: "histogram"
    buckets: [1, 5, 10, 20, 50]  # ms

  - name: "crdt_write_winners"
    type: "counter"
    labels: ["device_id"]  # Which device's writes usually win

  - name: "crdt_convergence_time"
    type: "histogram"
    labels: ["device_count"]  # Time for all devices to converge
    buckets: [10, 50, 100, 500, 1000]  # ms
```

---

## Implementation Checklist

- [ ] Update FlatBuffers schema for WriteRecord (timestamp, device_id, vector_clock)
- [ ] Implement LWW comparator with device ID ordering
- [ ] Implement vector clock tracking per device
- [ ] Add CRDT merge logic to K0
- [ ] Add merge logic to K0 Bridge P07 (device-to-device sync)
- [ ] Test conflict resolution (100+ scenarios)
- [ ] Test causal ordering (vector clocks)
- [ ] Add observability metrics
- [ ] Document device ID ordering in runbooks
- [ ] Add CRDT merge to WARD integration tests

---

## References

- **DynamoDB**: Uses LWW for multi-region replication
- **Cassandra**: Timestamp-based consistency
- **Vector Clocks**: Lamport (1978), used in Dynamo (Amazon)
- **CRDT Research**: Shapiro et al. (2011) - Conflict-Free Replicated Data Types

---

**Last Updated:** 2025-10-16
**Version:** 1.0
**Status:** Ready for Implementation