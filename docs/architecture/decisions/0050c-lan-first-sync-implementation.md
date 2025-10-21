# ADR-0050c: LAN-First Sync Implementation (Phase 1)

**Status:** ✅ Accepted

**Date:** 2025-10-16

**Deciders:** K1 Architecture Team, Backend Lead

**Technical Story:** Multi-Device Family Sync - Phase 1 LAN Discovery & Sync

**Parent ADR:** ADR-0050 (Multi-Device Family Sync Strategy)

**Sibling ADRs:** ADR-0050a (SessionState Coherence), ADR-0050b (CRDT Merge), ADR-0050d (Internet Sync)

---

## Context

### Problem Statement

**Phase 1 Implementation:** When all family devices are on the same WiFi network at home, how should they discover each other and sync memories with <1ms latency?

### Current Situation

- ADR-0050 defines hybrid strategy (LAN + Internet)
- ADR-0050b defines CRDT merge logic
- No implementation details for LAN discovery (mDNS) or TCP sync
- No MVP manual sync for when devices are remote

### Constraints

| Constraint | Target | Why |
|-----------|--------|-----|
| **Discovery latency** | <100ms for 6 devices | Acceptable for UI |
| **Sync latency** | <50ms per change | Real-time feel |
| **mDNS support** | All modern WiFi | Standard RFC 6762 |
| **Battery impact** | <2% per hour idle | Constant network overhead acceptable |
| **Scalability** | 6-10 devices typical | Some families 20+, graceful degrade |
| **Offline** | Works without internet | No cloud fallback required |

---

## Decision

### **Phase 1: mDNS Discovery + TCP Sync + Manual Upload**

**Three components:**

#### 1. Device Discovery (mDNS)

**How it works:**
- Each device announces via Multicast DNS on startup
- Service name: `familyos-{device-id}._tcp.local`
- Includes device type (iPhone, Laptop, Tablet) in metadata
- Broadcast every 60 seconds (keep-alive)

**Setup:**

```python
import zeroconf

# Device startup
device_id = "iphone-mom"
device_type = "iOS"
ip_address = "192.168.1.100"

# Announce service
info = zeroconf.ServiceInfo(
    "_familyos._tcp.local.",
    f"familyos-{device_id}._tcp.local.",
    addresses=[socket.inet_aton(ip_address)],
    port=9000,  # K0 Bridge P07 listener port
    properties={
        "device_id": device_id,
        "device_type": device_type,
        "k0_version": "1.0",
        "capabilities": "sync,crdt,e2ee"  # Phase 1 + future
    },
    server=f"{device_id}.local."
)

zeroconf_instance = zeroconf.Zeroconf()
zeroconf_instance.register_service(info)
```

#### 2. Peer Discovery & Connection

**Listener (background on each device):**

```python
class FamilyOSServiceBrowser:
    def __init__(self):
        self.peers = {}  # Known devices
        self.browser = None

    def start_browsing(self):
        """Start listening for other family devices"""
        self.browser = zeroconf.ServiceBrowser(
            self.zeroconf,
            "_familyos._tcp.local.",
            handlers=[self.on_service_change]
        )

    def on_service_change(self, zeroconf, service_type, name, state_change):
        """Called when a device is added/removed from network"""
        if state_change == zeroconf.ServiceStateChange.Added:
            self.on_device_discovered(name)
        elif state_change == zeroconf.ServiceStateChange.Removed:
            self.on_device_lost(name)

    def on_device_discovered(self, service_name):
        """Device appeared on LAN"""
        info = self.zeroconf.get_service_info(
            "_familyos._tcp.local.",
            service_name
        )

        device_id = info.properties.get("device_id")
        ip_address = socket.inet_ntoa(info.addresses[0])
        port = info.port

        print(f"✅ Discovered: {device_id} at {ip_address}:{port}")

        # Try to establish sync connection
        self.establish_peer_connection(device_id, ip_address, port)

    def on_device_lost(self, service_name):
        """Device left network"""
        device_id = service_name.split(".")[0].replace("familyos-", "")
        print(f"❌ Lost: {device_id}")
        if device_id in self.peers:
            del self.peers[device_id]
```

#### 3. TCP Sync Channel

**Peer connection (TCP persistent):**

```python
class P07SyncChannel:
    """K0 Bridge P07 sync channel over TCP"""

    def __init__(self, local_device_id, peer_device_id, peer_ip, peer_port):
        self.local_device_id = local_device_id
        self.peer_device_id = peer_device_id
        self.socket = None
        self.synced_until = 0  # Watermark

    async def connect(self):
        """Establish TCP connection to peer"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        await self.socket.connect((self.peer_ip, self.peer_port))

        # Handshake: exchange device IDs and vector clocks
        await self.send_handshake()
        await self.receive_handshake()

    async def send_handshake(self):
        """Send our device ID + current vector clock"""
        handshake = {
            "device_id": self.local_device_id,
            "vector_clock": self.get_vector_clock(),
            "sync_since": self.synced_until
        }
        msg = FlatBuffersEncode(handshake)
        await self.send_message(msg)

    async def sync_changes(self):
        """Push/pull changes with peer"""

        # 1. Get delta (changes since last sync)
        delta = k0.get_delta(since=self.synced_until)

        # 2. Wrap in P07 message
        p07_msg = K0BridgeP07Message(
            sender_device_id=self.local_device_id,
            receiver_device_id=self.peer_device_id,
            changes=delta,
            vector_clock=self.get_vector_clock(),
            timestamp=time.time_ms()
        )

        # 3. Send to peer
        await self.send_message(FlatBuffersEncode(p07_msg))

        # 4. Receive peer's changes
        peer_msg = await self.receive_message()

        # 5. Merge with CRDT logic (ADR-0050b)
        for change in peer_msg.changes:
            k0.merge_crdt(change)  # LWW merge

        # 6. Update watermark
        self.synced_until = time.time_ms()
```

#### 4. Continuous Sync Loop

**Background sync (every 5 seconds or on change):**

```python
class SyncManager:
    async def continuous_sync(self):
        """Background: keep all peers in sync"""
        while True:
            try:
                # Discover peers on LAN
                peers = await self.discover_peers()

                # Sync with all active peers
                for peer_id, connection in peers.items():
                    if not connection.connected:
                        await connection.connect()

                    await connection.sync_changes()

                # Wait before next sync
                await asyncio.sleep(5)  # 5s interval

            except Exception as e:
                logger.error(f"Sync error: {e}")
                await asyncio.sleep(10)  # Backoff on error
```

#### 5. Manual Sync (MVP Workaround for Phase 1)

**Until Phase 2 (internet sync), remote devices need manual trigger:**

```python
# UI Button: "Sync Now"
async def manual_sync_to_peer(peer_device_id):
    """
    User manually triggers sync.
    Used while away from home (Phase 1 MVP).
    Replaced by automatic internet sync in Phase 2.
    """

    # Find peer (must be discoverable somehow, e.g., QR code, contact)
    # or show list of recent devices

    # Initiate connection
    connection = await establish_connection(peer_device_id)

    # Full delta sync
    delta = k0.get_full_delta()
    await connection.sync_changes(delta)

    print(f"✅ Synced with {peer_device_id}")
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────┐
│           Family Home (Same WiFi)            │
│                                              │
│  ┌──────────────┐  ┌──────────────┐         │
│  │ Device A     │  │ Device B     │         │
│  │ (iPhone)     │  │ (Laptop)     │         │
│  │              │  │              │         │
│  │ mDNS Listen  │  │ mDNS Listen  │         │
│  │ P07 Server   │  │ P07 Server   │         │
│  │ K0 Local     │  │ K0 Local     │         │
│  └──────────────┘  └──────────────┘         │
│        ↑                    ↑                 │
│        └────── mDNS Discovery ────────┘     │
│               (broadcast ~1 min)            │
│                                              │
│        ┌─────── TCP Sync Channel ─────┐     │
│        │ K0 Bridge P07 sync            │     │
│        │ CRDT merge (LWW)              │     │
│        │ Latency: <1ms                 │     │
│        └───────────────────────────────┘     │
│                                              │
└─────────────────────────────────────────────┘
```

---

## Implementation Plan (4-5 weeks, M2-M3)

| Week | Task | Owner | Details |
|------|------|-------|---------|
| **W1** | mDNS registration module | Backend | Device announcements |
| **W1** | Peer discovery listener | Backend | ServiceBrowser integration |
| **W2** | TCP P07 sync channel | Backend | Connection management |
| **W2** | Handshake protocol | Backend | Device ID + vector clock exchange |
| **W3** | CRDT merge integration | Backend | Use ADR-0050b logic |
| **W3** | Continuous sync loop | Backend | Background 5s interval |
| **W4** | Manual sync UI | Frontend | "Sync Now" button for Phase 1 MVP |
| **W4** | Integration testing | QA | 3-6 device combinations |
| **W5** | Observability | DevOps | mDNS metrics, sync latency |

---

## Testing Strategy

### WARD Tests

```python
@test("mDNS announces device on startup")
async def _():
    device = await create_test_device("iphone-mom")

    # Start mDNS
    await device.start_mdns_broadcast()

    # Other device discovers
    discoverer = create_test_device("laptop-dad")
    discovered = await discoverer.discover_devices(timeout=2)

    assert "iphone-mom" in discovered
    assert discovered["iphone-mom"]["ip"] == device.local_ip


@test("TCP sync channel <50ms for single change")
async def _():
    device_a = await create_test_device("iphone-mom")
    device_b = await create_test_device("laptop-dad")

    # Establish sync channel
    channel = await device_a.establish_sync_channel(device_b)

    # Write on device A
    start = time.time()
    await device_a.k0.write(MemoryItem(id="1", value="Hello"))

    # Wait for sync to device B
    await wait_for_sync(device_b)
    latency_ms = (time.time() - start) * 1000

    # Check latency
    assert latency_ms < 50

    # Check item on device B
    item_b = await device_b.k0.read("1")
    assert item_b.value == "Hello"


@test("Manual sync transfers all items from Phase 1 MVP button")
async def _():
    device_remote = await create_test_device("iphone-mom")
    device_home = await create_test_device("laptop-dad")

    # Simulate remote: device_remote not on LAN
    await device_remote.disconnect_lan()

    # Write 10 items on remote
    for i in range(10):
        await device_remote.k0.write(MemoryItem(id=f"item-{i}"))

    # User manually triggers sync (via QR, contact, etc)
    await device_remote.manual_sync_to(device_home.device_id)

    # All 10 items should be on home device
    items = await device_home.k0.list_all()
    assert len(items) == 10
```

### Integration Tests

- 3-device LAN sync
- 6-device LAN sync (larger family)
- Rapid writes (10 changes/sec per device)
- Simultaneous conflicts (CRDT merge verification)
- Network dropouts (reconnect & resync)
- mDNS broadcast failures (graceful degrade)

---

## Latency Targets

```
mDNS Discovery:  <100ms per device
TCP Connection:  <50ms
Sync Delta:      <20ms per change
CRDT Merge:      <10ms
Total Sync:      <50ms end-to-end ✅
```

---

## Observability Metrics

```yaml
metrics:
  - name: "mdns_discovery_latency"
    type: "histogram"
    buckets: [10, 50, 100, 200, 500]  # ms
    labels: ["device_type"]

  - name: "peer_connections_active"
    type: "gauge"

  - name: "sync_channel_latency"
    type: "histogram"
    buckets: [5, 10, 20, 50, 100]  # ms
    labels: ["peer_device"]

  - name: "crdt_merges_per_sync"
    type: "histogram"
    labels: ["conflict_count"]

  - name: "manual_sync_completeness"
    type: "gauge"
    labels: ["device_pair"]  # % items transferred
```

---

## Limitations & Known Issues (Phase 1)

| Issue | Impact | Workaround | Phase 2 Fix |
|-------|--------|-----------|-----------|
| **No internet sync** | Remote devices can't sync | Manual "Sync Now" button | Automatic P2P E2EE |
| **mDNS reliability** | Poor on congested WiFi | Retry with backoff | Add internet fallback |
| **Battery drain** | Continuous mDNS/TCP | Configurable interval (5-60s) | Optimize in Phase 2 |
| **Firewall blocks** | Corporate WiFi may block mDNS | Manual sync fallback | Internet E2EE in Phase 2 |
| **Family size >20** | mDNS overhead high | Not typical, acceptable | Optimize in Phase 2 |

---

## Transition to Phase 2

**What changes in Phase 2 (Internet Sync)?**

- ✅ Keep: mDNS discovery (works on all networks)
- ✅ Keep: TCP sync protocol (same P07 messages)
- ✅ Keep: CRDT merge (same logic)
- ❌ Remove: Manual "Sync Now" button (automatic)
- ✅ Add: E2EE encryption wrapper (ADR-0050d)
- ✅ Add: Internet tunnel (QUIC or similar)
- ✅ Add: Automatic network detection (LAN vs internet preference)

**Zero changes needed to Phase 1 code for Phase 2** - we just add layers.

---

## References

- **Zeroconf/mDNS:** RFC 6762 (Multicast DNS)
- **Python zeroconf:** https://pypi.org/project/zeroconf/
- **K0 Bridge P07:** ADR-0001a
- **CRDT Merge:** ADR-0050b

---

**Last Updated:** 2025-10-16
**Version:** 1.0
**Status:** Ready for Implementation
